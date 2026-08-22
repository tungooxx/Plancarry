#!/usr/bin/env python3
"""Execute the frozen ReplayResidual v1.1 representation-sanity evaluation.

Input is a complete set of 32 development episode packets produced by a
separately authorized natural-trajectory qualification stage. This executable
never reads the sealed 32..63 population and has no causal intervention path.
It writes exactly one final result atomically after all captures complete.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from replay_residual_sanity_client_v1 import CaptureOnlyClient
import replay_residual_sanity_protocol_v1 as p


def _runtime_check(info: dict[str, Any]) -> None:
    if info.get("model_id") != p.MODEL_ID:
        raise RuntimeError(f"MODEL_ID_MISMATCH:{info.get('model_id')}")
    if info.get("model_revision_requested") != p.MODEL_REVISION:
        raise RuntimeError(f"MODEL_REVISION_MISMATCH:{info.get('model_revision_requested')}")
    if info.get("model_commit_resolved") != p.MODEL_REVISION:
        raise RuntimeError(f"MODEL_COMMIT_MISMATCH:{info.get('model_commit_resolved')}")
    if "RTX 3050" not in str(info.get("device_name", "")):
        raise RuntimeError(f"DEVICE_MISMATCH:{info.get('device_name')}")
    if str(info.get("dtype")) not in {"torch.bfloat16", "bfloat16"}:
        raise RuntimeError(f"DTYPE_MISMATCH:{info.get('dtype')}")
    if info.get("quantization") != "NONE":
        raise RuntimeError(f"QUANTIZATION_MISMATCH:{info.get('quantization')}")
    expected_versions = {
        "transformers_version": p.TRANSFORMERS_VERSION,
        "tokenizers_version": p.TOKENIZERS_VERSION,
        "torch_version": p.TORCH_VERSION,
    }
    for key, expected in expected_versions.items():
        if str(info.get(key)) != expected:
            raise RuntimeError(f"RUNTIME_VERSION_MISMATCH:{key}:{info.get(key)}:{expected}")


def _load_packets(episode_dir: Path, root: Path, tokenizer: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = p.development_manifest(root)
    expected_episode_names = {f"packet_{idx:02d}.json" for idx in p.DEV_INDICES}
    required_metadata_names = {"manifest.json", "provenance.json"}
    json_names = {path.name for path in episode_dir.glob("*.json")}

    missing_metadata = sorted(required_metadata_names - json_names)
    if missing_metadata:
        raise RuntimeError(f"EPISODE_DIR_MISSING_REQUIRED_METADATA:{missing_metadata}")
    unexpected_json = sorted(json_names - expected_episode_names - required_metadata_names)
    if unexpected_json:
        raise RuntimeError(f"EPISODE_DIR_UNEXPECTED_JSON_SIDECAR:{unexpected_json}")
    missing_episode_files = sorted(expected_episode_names - json_names)
    if missing_episode_files:
        raise RuntimeError(f"EPISODE_SET_MUST_BE_EXACT_0_31:missing_files={missing_episode_files}")

    by_idx: dict[int, dict[str, Any]] = {}
    for expected_idx in p.DEV_INDICES:
        path = episode_dir / f"packet_{expected_idx:02d}.json"
        obj = json.loads(path.read_text(encoding="utf-8"))
        idx = int(obj.get("frozen_index", -1))
        if idx != expected_idx:
            raise RuntimeError(f"EPISODE_FILENAME_INDEX_MISMATCH:expected={expected_idx}:observed={idx}:{path}")
        if idx not in p.DEV_INDICES:
            raise RuntimeError(f"EPISODE_DIR_CONTAINS_NONDEVELOPMENT_INDEX:{idx}:{path}")
        if idx in by_idx:
            raise RuntimeError(f"DUPLICATE_EPISODE_INDEX:{idx}")
        by_idx[idx] = obj
    if set(by_idx) != set(p.DEV_INDICES):
        missing = sorted(set(p.DEV_INDICES) - set(by_idx))
        extra = sorted(set(by_idx) - set(p.DEV_INDICES))
        raise RuntimeError(f"EPISODE_SET_MUST_BE_EXACT_0_31:missing={missing}:extra={extra}")
    packets = [by_idx[i] for i in p.DEV_INDICES]
    for packet, row in zip(packets, manifest):
        p.validate_episode_packet(packet, row, tokenizer)
    return packets, manifest

def _qualified_donors(packets: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> dict[int, str]:
    qualified = [x for x in packets if bool(x.get("qualified", False))]
    if len(qualified) < p.MIN_QUALIFIED:
        return {}
    rank = {int(row["frozen_index"]): str(row["family_rank_sha256"]) for row in manifest}
    ordered = sorted(qualified, key=lambda x: (rank[int(x["frozen_index"])], int(x["frozen_index"])))
    out: dict[int, str] = {}
    for i, packet in enumerate(ordered):
        donor = ordered[(i + 1) % len(ordered)]
        if donor["family"] == packet["family"]:
            raise RuntimeError("UNRELATED_DONOR_FAMILY_COLLISION")
        out[int(packet["frozen_index"])] = str(donor["plan_text"])
    return out


def _metadata(info: dict[str, Any], packet: dict[str, Any], replay_text: str, slot_text: str,
              condition: str, layer: int, token_index: int) -> dict[str, Any]:
    return {
        "model_id": info["model_id"],
        "model_revision": info["model_commit_resolved"],
        "transformers_version": str(info["transformers_version"]),
        "tokenizers_version": str(info["tokenizers_version"]),
        "torch_version": str(info["torch_version"]),
        "family": str(packet["family"]),
        "game_path_sha256": p.sha256_text(str(packet["game_path"])),
        "trajectory_sha256": p.trajectory_digest(packet),
        "replay_transcript_sha256": p.sha256_text(replay_text),
        "plan_block_sha256": p.sha256_text(slot_text),
        "condition": condition,
        "layer": int(layer),
        "site": p.SITE,
        "token_index": int(token_index),
        "dtype": "float32",
        "shape": None,  # filled after capture
        "cohort_manifest_sha256": p.COHORT_SHA256,
        "design_sha256": p.DESIGN_SHA256,
    }


def _capture_family(packet: dict[str, Any], unrelated_plan: str, tokenizer: Any,
                    client: Any, info: dict[str, Any]) -> dict[str, Any]:
    anchor_slots = {
        1: p.build_condition_slots(tokenizer, packet, unrelated_plan, 1),
        2: p.build_condition_slots(tokenizer, packet, unrelated_plan, 2),
    }
    replays: dict[int, dict[str, tuple[str, list[int], list[int]]]] = {1: {}, 2: {}}
    for anchor in (1, 2):
        full_lengths = set()
        terminal_suffixes = set()
        for condition in p.CONDITIONS:
            slot_ids = anchor_slots[anchor][condition]
            replay_text, replay_ids = p.build_replay(tokenizer, packet, slot_ids, anchor)
            full_lengths.add(len(replay_ids))
            terminal_suffixes.add(replay_text[-len("<STATE_END>"):])
            replays[anchor][condition] = (replay_text, replay_ids, slot_ids)
        # Frozen v1.1 requires exact 128-token slots and the same trajectory/world
        # replay with capture at the same final pre-ACTION position. BPE boundary
        # merges at the plan/suffix seam are allowed only if the complete replay
        # length (hence final capture index) remains identical in every arm.
        if len(full_lengths) != 1 or terminal_suffixes != {"<STATE_END>"}:
            raise RuntimeError(f"REPLAY_CAPTURE_POSITION_ALIGNMENT_FAILED:t{anchor}:full={sorted(full_lengths)}:terminal={sorted(terminal_suffixes)}")

    captures: dict[str, dict[str, dict[str, Any]]] = {}
    vectors: dict[str, dict[int, dict[str, list[float]]]] = {c: {1: {}, 2: {}} for c in p.CONDITIONS}
    for condition in p.CONDITIONS:
        captures[condition] = {}
        for anchor in (1, 2):
            replay_text, replay_ids, slot_ids = replays[anchor][condition]
            slot_text = p.exact_token_text(tokenizer, slot_ids, label=f"slot_{condition}_t{anchor}")
            for layer in p.LAYERS:
                row = client.capture(replay_text, layer, -1)
                vec = [float(x) for x in row.get("vector", [])]
                if not vec or int(row.get("hidden_size", -1)) != len(vec):
                    raise RuntimeError("CAPTURE_VECTOR_SCHEMA_FAILED")
                resolved = int(row.get("token_index_resolved", -999999))
                if resolved != len(replay_ids) - 1:
                    raise RuntimeError(f"CAPTURE_ANCHOR_INDEX_MISMATCH:{resolved}:{len(replay_ids)-1}")
                md = _metadata(info, packet, replay_text, slot_text, condition, layer, resolved)
                md["shape"] = [len(vec)]
                payload_hash = p.payload_sha256(md, vec)
                p.validate_payload(md, vec, payload_hash)
                key = f"t{anchor}:L{layer}"
                captures[condition][key] = {
                    "metadata": md,
                    "payload_sha256": payload_hash,
                    "raw_l2": p.l2(vec),
                    "vector": vec,
                }
                vectors[condition][anchor][layer] = vec

    layer_metrics: dict[str, Any] = {}
    plan_residuals: dict[int, dict[int, list[float]]] = {1: {}, 2: {}}
    for layer in p.LAYERS:
        residuals: dict[str, dict[int, list[float]]] = {}
        for condition in p.CONDITIONS:
            residuals[condition] = {}
            for anchor in (1, 2):
                residuals[condition][anchor] = p.residual(
                    vectors[condition][anchor][layer],
                    vectors["NEUTRAL_FILLER"][anchor][layer],
                )
        plan_residuals[1][layer] = residuals["PLAN_PRESENT"][1]
        plan_residuals[2][layer] = residuals["PLAN_PRESENT"][2]
        same = p.cosine(residuals["PLAN_PRESENT"][1], residuals["PLAN_PRESENT"][2])
        controls = {c: p.cosine(residuals["PLAN_PRESENT"][1], residuals[c][2]) for c in p.CONTROL_CONDITIONS}
        margin = same - max(controls.values())
        layer_metrics[str(layer)] = {
            "same_plan_temporal_cosine": same,
            "control_cosines": controls,
            "family_layer_selectivity_margin": margin,
            "plan_residual_t1_l2": p.l2(residuals["PLAN_PRESENT"][1]),
            "plan_residual_t2_l2": p.l2(residuals["PLAN_PRESENT"][2]),
        }
    aggregate = p.median([layer_metrics[str(layer)]["family_layer_selectivity_margin"] for layer in p.LAYERS])
    return {
        "frozen_index": int(packet["frozen_index"]),
        "family": packet["family"],
        "game_path": packet["game_path"],
        "trajectory_sha256": p.trajectory_digest(packet),
        "family_aggregate_margin": aggregate,
        "layer_metrics": layer_metrics,
        "captures": captures,
        "_plan_residuals": plan_residuals,
    }


def _retrieval(families: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for layer in p.LAYERS:
        correct = 0
        for query in families:
            q = query["_plan_residuals"][1][layer]
            ranked = []
            for target in families:
                score = p.cosine(q, target["_plan_residuals"][2][layer])
                ranked.append((score, str(target["family"])))
            ranked.sort(key=lambda x: (-x[0], x[1]))
            if ranked[0][1] == str(query["family"]):
                correct += 1
        out[str(layer)] = correct / len(families)
    return out


def _finalize(families: list[dict[str, Any]], qualified_count: int) -> dict[str, Any]:
    if qualified_count < p.MIN_QUALIFIED:
        return {
            "label": "INCONCLUSIVE_INSUFFICIENT_NATURAL_TRAJECTORIES",
            "qualified_count": qualified_count,
            "requirements": {"qualified_count>=16": False},
        }
    retrieval = _retrieval(families)
    aggregate_margins = [float(f["family_aggregate_margin"]) for f in families]
    all_layer_rows = [f["layer_metrics"][str(layer)] for f in families for layer in p.LAYERS]
    same = [float(x["same_plan_temporal_cosine"]) for x in all_layer_rows]
    alt = [float(x["control_cosines"]["ALT_NEUTRAL_POSITION"]) for x in all_layer_rows]
    late = [float(x["control_cosines"]["NEXT_ACTION_PRESERVED_LATE_NULL"]) for x in all_layer_rows]
    stats = {
        "qualified_count": qualified_count,
        "median_family_aggregate_margin": p.median(aggregate_margins),
        "positive_family_fraction": sum(x > 0.0 for x in aggregate_margins) / len(aggregate_margins),
        "median_same_plan_temporal_cosine": p.median(same),
        "median_alt_neutral_position_cosine": p.median(alt),
        "median_next_action_preserved_late_null_cosine": p.median(late),
        "same_minus_alt_median_gap": p.median(same) - p.median(alt),
        "same_minus_late_null_median_gap": p.median(same) - p.median(late),
        "retrieval_top1_by_layer": retrieval,
        "median_across_layer_retrieval_top1": p.median(list(retrieval.values())),
    }
    req = {
        "qualified_count>=16": qualified_count >= 16,
        "median family_aggregate_margin >= 0.05": stats["median_family_aggregate_margin"] >= 0.05,
        "at least 70% of qualified families have family_aggregate_margin > 0": stats["positive_family_fraction"] >= 0.70,
        "median same-plan temporal cosine exceeds median ALT_NEUTRAL_POSITION cosine by >=0.10": stats["same_minus_alt_median_gap"] >= 0.10,
        "median across-layer same-family retrieval top1 accuracy >=0.25": stats["median_across_layer_retrieval_top1"] >= 0.25,
        "median same-plan temporal cosine exceeds median NEXT_ACTION_PRESERVED_LATE_NULL cosine by >=0.05": stats["same_minus_late_null_median_gap"] >= 0.05,
    }
    label = "PASS_REPLAY_RESIDUAL_SANITY" if all(req.values()) else "FAIL_REPLAY_RESIDUAL_SANITY"
    return {"label": label, "requirements": req, **stats}


def evaluate_packets(packets: list[dict[str, Any]], manifest: list[dict[str, Any]], tokenizer: Any,
                     client: Any, info: dict[str, Any]) -> dict[str, Any]:
    qualified = [x for x in packets if bool(x.get("qualified", False))]
    if len(qualified) < p.MIN_QUALIFIED:
        return {
            "kind": "PLANCARRY_REPLAY_RESIDUAL_SANITY_V1_1_RESULT",
            "scientific_result": "NOT_ASSESSED_BY_ENGINEERING" if info.get("mode") == "engineering-fake" else "ASSESSED_BY_FROZEN_SANITY_GATE",
            "gate": _finalize([], len(qualified)),
            "qualified_indices": [int(x["frozen_index"]) for x in qualified],
            "development_population_indices": list(p.DEV_INDICES),
            "design_sha256": p.DESIGN_SHA256,
            "cohort_manifest_sha256": p.COHORT_SHA256,
            "untouched_population_sha256": p.UNTOUCHED_SHA256,
        }
    donors = _qualified_donors(packets, manifest)
    family_results = []
    for packet in qualified:
        family_results.append(_capture_family(packet, donors[int(packet["frozen_index"])], tokenizer, client, info))
    gate = _finalize(family_results, len(qualified))
    # Internal residuals are needed only while computing retrieval; they are not serialized.
    for row in family_results:
        row.pop("_plan_residuals", None)
    return {
        "kind": "PLANCARRY_REPLAY_RESIDUAL_SANITY_V1_1_RESULT",
        "scientific_result": "NOT_ASSESSED_BY_ENGINEERING" if info.get("mode") == "engineering-fake" else "ASSESSED_BY_FROZEN_SANITY_GATE",
        "gate": gate,
        "qualified_indices": [int(x["frozen_index"]) for x in qualified],
        "development_population_indices": list(p.DEV_INDICES),
        "family_results": family_results,
        "design_sha256": p.DESIGN_SHA256,
        "cohort_manifest_sha256": p.COHORT_SHA256,
        "untouched_population_sha256": p.UNTOUCHED_SHA256,
        "sealed_population_accessed": False,
        "causal_intervention_requests": 0,
    }


def atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError(f"OUTPUT_EXISTS_REFUSE_OVERWRITE:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".tmp.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            f.write("\n")
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise


def load_tokenizer() -> Any:
    from transformers import AutoTokenizer  # type: ignore
    return AutoTokenizer.from_pretrained(p.MODEL_ID, revision=p.MODEL_REVISION, trust_remote_code=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--episode-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--url", default=os.environ.get("PLANCARRY_WHITEBOX_URL", "http://127.0.0.1:8765"))
    ap.add_argument("--token", default=os.environ.get("PLANCARRY_WHITEBOX_TOKEN", ""))
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    p.load_authoritative(root)
    tokenizer = load_tokenizer()
    packets, manifest = _load_packets(Path(args.episode_dir), root, tokenizer)
    client = CaptureOnlyClient(args.url, args.token)
    info = client.model_info(); _runtime_check(info)
    result = evaluate_packets(packets, manifest, tokenizer, client, info)
    atomic_write_json(Path(args.output), result)
    print(json.dumps({"result_path": args.output, "gate": result["gate"], "scientific_result": result["scientific_result"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
