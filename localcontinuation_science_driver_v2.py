#!/usr/bin/env python3
"""Development-only LocalContinuation-v2 heavy-execution adapter.

This file is a PRE-SCIENCE handoff.  It composes the independently reviewed
v2 exact-token packet/control implementation with the already reviewed v1
reset/session/MSA2 primitives.  No confirmation/reserve/valid-split entry point
exists here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

import localcontinuation_controls_v2 as controls
import localcontinuation_packet_builder_v2 as pb
import localcontinuation_phase_runner_v2 as phase
import localcontinuation_validator_v2 as validator
import localcontinuation_science_driver_v1 as runtime_v1

ROOT = Path(__file__).resolve().parent
PACKET_DIR = Path("results/science/plancarry_localcontinuation_v2_development_packets")
DEV_PAYLOAD = Path("results/science/plancarry_localcontinuation_v2_development_grid.json")
DEV_SEAL = Path("results/science/plancarry_localcontinuation_v2_development_selection.json")
DEV_TERMINAL = Path("results/science/plancarry_localcontinuation_v2_development_terminal.json")
PACKET_INPROGRESS = PACKET_DIR.with_name(f".{PACKET_DIR.name}.inprogress")
OUTPUT_PATHS = (PACKET_DIR, PACKET_INPROGRESS, DEV_PAYLOAD, DEV_SEAL, DEV_TERMINAL)

MODEL_ID = "Qwen/Qwen3-1.7B"
MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
MODEL_DTYPE = "bfloat16"
TRANSFORMERS_VERSION = "4.51.3"
TOKENIZERS_VERSION = "0.21.1"
TORCH_VERSION = "2.13.0+cu130"
TOKENIZER_SNAPSHOT_DEFAULT = ROOT / ".hf_cache_qwen3_v21" / "hub" / "models--Qwen--Qwen3-1.7B" / "snapshots" / MODEL_REVISION
TOKENIZER_FILE_SHA256 = {
    "tokenizer.json": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    "tokenizer_config.json": "d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101",
    "config.json": "1ddb5b89ebc90dcb417a45c213d818577e65976454d29385c8f6140771d95197",
    "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
    "merges.txt": "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5",
}
A1_REVIEW_REL = Path("results/design/plancarry_localcontinuation_v2_final_executable_independent_review_a1_20260824.json")
A1_REVIEW_SHA256 = "99a93039d8aa352f73acaf5435627a70ce90cf280386b1860c3dbb6c2a3911c3"
V1_SCIENCE_DRIVER_SHA256 = "7768a45cd41048ebcabd27a0be6602b41642fa95f425883e199a94c3c2291592"
LAYERS = tuple(phase.LAYERS)
ALPHAS = tuple(phase.ALPHAS)
ACTIVE = phase.ACTIVE
NO_PATCH = phase.NO_PATCH
SPEC = tuple(phase.SPEC)

# These are the ONLY functions imported from the old science orchestrator.
# They are reusable low-level runtime primitives; its v1 packet/control/phase
# orchestration functions are intentionally never called.
_SAFE_V1_REUSE = (
    "load_runtime",
    "runtime_factory",
    "base_reset",
    "msa2_arm",
    "rescale_to",
    "rademacher",
)
_FORBIDDEN_V1_ORCHESTRATION = (
    "produce_packets",
    "development",
    "confirmation_or_reserve",
    "capture_sources",
    "vectors_for_grid",
    "donor_plan",
    "visible_plan_slot_ids",
)


class ExecutionContractError(RuntimeError):
    pass


class _Stage2SemanticTokenizerForbidden:
    def encode(self, *_args: Any, **_kwargs: Any) -> list[int]:
        raise AssertionError("STAGE2_SEMANTIC_RETOKENIZATION_FORBIDDEN")

    def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("STAGE2_SEMANTIC_RETOKENIZATION_FORBIDDEN")


def sha_file(path: str | Path) -> str:
    return pb.sha_file(path)


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _require_hex64(value: str, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ExecutionContractError(f"{label}_NOT_SHA256:{text}")
    return text


def _require_git40(value: str, label: str) -> str:
    text = str(value)
    if len(text) != 40 or any(ch not in "0123456789abcdef" for ch in text):
        raise ExecutionContractError(f"{label}_NOT_GIT40:{text}")
    return text


def verify_sources(expected_git_commit: str, expected_driver_sha256: str, expected_phase_sha256: str) -> dict[str, Any]:
    pb.verify_bindings(ROOT)
    expected_commit = _require_git40(expected_git_commit, "EXPECTED_GIT_COMMIT")
    expected_driver = _require_hex64(expected_driver_sha256, "EXPECTED_DRIVER_SHA256")
    expected_phase = _require_hex64(expected_phase_sha256, "EXPECTED_PHASE_SHA256")
    got_head = _git_head()
    if got_head != expected_commit:
        raise ExecutionContractError(f"GIT_COMMIT_MISMATCH:{got_head}:{expected_commit}")
    checks = {
        ROOT / A1_REVIEW_REL: A1_REVIEW_SHA256,
        ROOT / "localcontinuation_science_driver_v1.py": V1_SCIENCE_DRIVER_SHA256,
        ROOT / "localcontinuation_science_driver_v2.py": expected_driver,
        ROOT / "localcontinuation_phase_runner_v2.py": expected_phase,
    }
    for path, expected in checks.items():
        if not path.is_file():
            raise ExecutionContractError(f"HANDOFF_SOURCE_MISSING:{path}")
        got = sha_file(path)
        if got != expected:
            raise ExecutionContractError(f"HANDOFF_SOURCE_DRIFT:{path}:{got}:{expected}")
    return {
        "git_commit": got_head,
        "driver_sha256": expected_driver,
        "phase_runner_v2_sha256": expected_phase,
        "v2_controls_sha256": pb.CONTROLS_SHA256,
        "v2_packet_builder_sha256": sha_file(ROOT / "localcontinuation_packet_builder_v2.py"),
        "v2_validator_sha256": sha_file(ROOT / "localcontinuation_validator_v2.py"),
        "v1_science_driver_sha256": V1_SCIENCE_DRIVER_SHA256,
        "v1_phase_runner_sha256": pb.V1_PHASE_RUNNER_SHA256,
        "v1_session_runtime_sha256": pb.V1_SESSION_SHA256,
        "v1_protocol_sha256": pb.V1_PROTOCOL_SHA256,
        "a1_executable_review_sha256": A1_REVIEW_SHA256,
    }


def tokenizer_report(tokenizer: Any) -> dict[str, Any]:
    primitive = [int(x) for x in tokenizer.encode(controls.NEUTRAL_FILLER_PRIMITIVE_TEXT, add_special_tokens=False)]
    separator = [int(x) for x in tokenizer.encode("\n", add_special_tokens=False)]
    if primitive != list(controls.NEUTRAL_FILLER_PRIMITIVE_IDS):
        raise ExecutionContractError(f"TOKENIZER_NEUTRAL_PRIMITIVE_DRIFT:{primitive}")
    if separator != list(controls.PAST_ACTION_SEPARATOR_IDS):
        raise ExecutionContractError(f"TOKENIZER_SEPARATOR_DRIFT:{separator}")
    controls.verify_neutral_filler_ids(controls.NEUTRAL_FILLER_IDS)
    opening, closing = controls.frozen_tag_ids(tokenizer)
    return {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "transformers_version": TRANSFORMERS_VERSION,
        "tokenizers_version": TOKENIZERS_VERSION,
        "neutral_filler_primitive_ids": primitive,
        "neutral_filler_stream_sha256": controls.NEUTRAL_FILLER_IDS_SHA256,
        "past_action_separator_ids": separator,
        "opening_tag_ids_sha256": controls.sha_json(opening),
        "closing_tag_ids_sha256": controls.sha_json(closing),
        "model_forward_calls": 0,
        "model_loaded": False,
    }


def verify_tokenizer_only() -> tuple[Any, dict[str, Any]]:
    import transformers
    import tokenizers as tokenizers_pkg
    from transformers import AutoTokenizer

    if str(transformers.__version__) != TRANSFORMERS_VERSION:
        raise ExecutionContractError(f"TRANSFORMERS_VERSION_MISMATCH:{transformers.__version__}:{TRANSFORMERS_VERSION}")
    if str(tokenizers_pkg.__version__) != TOKENIZERS_VERSION:
        raise ExecutionContractError(f"TOKENIZERS_VERSION_MISMATCH:{tokenizers_pkg.__version__}:{TOKENIZERS_VERSION}")
    snapshot = Path(os.environ.get("PLANCARRY_QWEN3_TOKENIZER_SNAPSHOT", str(TOKENIZER_SNAPSHOT_DEFAULT))).resolve()
    if not snapshot.is_dir():
        raise ExecutionContractError(f"TOKENIZER_SNAPSHOT_MISSING:{snapshot}")
    verified_files = {}
    for name, expected in TOKENIZER_FILE_SHA256.items():
        path = snapshot / name
        if not path.is_file():
            raise ExecutionContractError(f"TOKENIZER_FILE_MISSING:{path}")
        got = sha_file(path)
        if got != expected:
            raise ExecutionContractError(f"TOKENIZER_FILE_DRIFT:{name}:{got}:{expected}")
        verified_files[name] = got
    tokenizer = AutoTokenizer.from_pretrained(
        str(snapshot),
        trust_remote_code=False,
        local_files_only=True,
        use_fast=True,
    )
    report = tokenizer_report(tokenizer)
    report["snapshot_path"] = str(snapshot)
    report["snapshot_file_sha256"] = verified_files
    return tokenizer, report


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _write_fsync(path: Path, raw: bytes) -> str:
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()


def atomic_publish_packet_set(packets: Sequence[Mapping[str, Any]], target_rel: str | Path) -> tuple[Path, dict[str, Any]]:
    target = ROOT / Path(target_rel)
    if target.exists():
        raise ExecutionContractError(f"REFUSE_EXISTING_PACKET_DIR:{target}")
    temp = target.with_name(f".{target.name}.inprogress")
    if temp.exists():
        raise ExecutionContractError(f"REFUSE_STALE_INPROGRESS_PACKET_DIR:{temp}")
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.mkdir()
    try:
        file_rows: list[dict[str, Any]] = []
        for packet in packets:
            idx = int(packet["frozen_index"])
            name = f"packet_{idx:02d}.json"
            raw = json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
            digest = _write_fsync(temp / name, raw)
            file_rows.append({"frozen_index": idx, "name": name, "sha256": digest})
        manifest = {
            "kind": "PLANCARRY_LOCALCONTINUATION_V2_DEVELOPMENT_PACKET_SET",
            "phase": "development",
            "indices": list(range(32)),
            "attempted_count": len(packets),
            "trajectory_eligible_count": sum(bool(p.get("trajectory_eligible")) for p in packets),
            "stage2_qualified_count": sum(bool(p.get("qualified")) for p in packets),
            "complete_E_before_donor": True,
            "stage2_semantic_tokenizer_calls": 0,
            "confirmation_accessed": False,
            "reserve_accessed": False,
            "valid_seen_accessed": False,
            "valid_unseen_accessed": False,
            "files": file_rows,
            **phase.binding_payload(),
        }
        manifest_raw = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        manifest["manifest_file_sha256"] = _write_fsync(temp / "manifest.json", manifest_raw)
        dir_fd = os.open(temp, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        os.rename(temp, target)
        parent_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return target, manifest
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def produce_packets(tokenizer: Any, model: Any, model_provenance: Mapping[str, Any]) -> list[dict[str, Any]]:
    import replay_residual_natural_packet_producer_v2_1 as v21

    rows = pb.load_population_phase("development", ROOT)
    if [int(row["frozen_index"]) for row in rows] != list(range(32)):
        raise ExecutionContractError("V2_DEVELOPMENT_POPULATION_NOT_0_31")
    opening, closing = controls.frozen_tag_ids(tokenizer)
    planner = lambda task, obs: v21.torch_generate_plan(tokenizer, model, task, obs)
    scorer = lambda prefix, suffix: v21.torch_suffix_mean_logprob(model, prefix, suffix)
    stage1: list[dict[str, Any]] = []
    for position, row in enumerate(rows, 1):
        stage1.append(
            pb.produce_stage1_attempt(
                row,
                "development",
                tokenizer,
                model_provenance,
                runtime_v1.runtime_factory,
                planner,
                scorer,
                opening,
                closing,
            )
        )
        print(json.dumps({"stage": "v2_stage1", "done": position, "total": 32}), flush=True)
    packets = pb.apply_stage2_phase(
        _Stage2SemanticTokenizerForbidden(),
        stage1,
        "development",
        controls.NEUTRAL_FILLER_IDS,
        opening,
        closing,
        ROOT,
    )
    pb.validate_phase_packets(packets, "development", tokenizer, opening, closing, ROOT)
    validator.validate_packet_set(packets, "development", tokenizer, opening, closing, ROOT)
    validator.validate_stage2_reconstruction(
        packets, "development", _Stage2SemanticTokenizerForbidden(), controls.NEUTRAL_FILLER_IDS, opening, closing, ROOT
    )
    target, manifest = atomic_publish_packet_set(packets, PACKET_DIR)
    print(
        json.dumps(
            {
                "stage": "v2_packet_set_frozen",
                "path": str(target.relative_to(ROOT)),
                "qualified": int(manifest["stage2_qualified_count"]),
                "complete_E_before_donor": True,
                "stage2_semantic_tokenizer_calls": 0,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return packets


def _donor_packet(packet: Mapping[str, Any], by_index: Mapping[int, Mapping[str, Any]]) -> Mapping[str, Any]:
    provenance = packet.get("control_provenance")
    if not isinstance(provenance, Mapping):
        raise ExecutionContractError("V2_DONOR_REQUIRES_CONTROL_PROVENANCE")
    idx = int(provenance.get("unrelated_donor_frozen_index", -1))
    if idx not in by_index or idx == int(packet["frozen_index"]):
        raise ExecutionContractError("V2_DONOR_INVALID")
    donor = by_index[idx]
    if str(donor.get("family")) == str(packet.get("family")):
        raise ExecutionContractError("V2_DONOR_SAME_FAMILY")
    return donor


def source_replay_ids_v2(tokenizer: Any, packet: Mapping[str, Any], donor: Mapping[str, Any]) -> tuple[dict[str, list[int]], dict[str, Any]]:
    slots, semantic_meta = controls.build_semantic_slots(packet, donor, controls.NEUTRAL_FILLER_IDS)
    replay_ids: dict[str, list[int]] = {}
    replay_provenance: dict[str, Mapping[str, Any]] = {}
    for condition in controls.SCIENCE_CONDITIONS:
        ids, provenance = controls.build_replay_ids(tokenizer, packet, slots[condition], 2)
        replay_ids[condition] = ids
        replay_provenance[condition] = provenance
    controls.assert_condition_invariant_replay_geometry(replay_provenance)
    return replay_ids, {
        "semantic": semantic_meta,
        "replay": {key: dict(value) for key, value in replay_provenance.items()},
        "stage2_semantic_tokenizer_calls": 0,
        "serialization": "DIRECT_PREFIX_IDS_PLUS_EXACT128_SLOT_IDS_PLUS_SUFFIX_IDS_NO_SLOT_DECODE_RETOKENIZE",
    }


def capture_sources_v2(
    tokenizer: Any,
    model: Any,
    packet: Mapping[str, Any],
    donor: Mapping[str, Any],
    layers: Sequence[int],
) -> dict[int, dict[str, Any]]:
    import torch
    from replay_residual_t1_session_runtime_v1 import capture_activation_ids, vector_sha256_fp32

    replay_ids, replay_meta = source_replay_ids_v2(tokenizer, packet, donor)
    out: dict[int, dict[str, Any]] = {}
    for layer in layers:
        hidden = {
            condition: capture_activation_ids(model, replay_ids[condition], int(layer), -1).detach().float().cpu()
            for condition in controls.SCIENCE_CONDITIONS
        }
        neutral = hidden["NEUTRAL_FILLER"]
        raw = hidden["PLAN_PRESENT"] - neutral
        out[int(layer)] = {
            "active": raw,
            "active_l2": float(torch.linalg.vector_norm(raw).item()),
            "active_sha256": vector_sha256_fp32(raw),
            "controls": {
                condition: hidden[condition] - neutral
                for condition in controls.SCIENCE_CONDITIONS
                if condition not in ("PLAN_PRESENT", "NEUTRAL_FILLER")
            },
            "replay_provenance": replay_meta,
        }
    return out


def vectors_for_grid_v2(source: Mapping[str, Any], packet: Mapping[str, Any], layer: int) -> dict[str, Any]:
    import torch

    raw = source["active"]
    norm = float(source["active_l2"])
    out: dict[str, Any] = {ACTIVE: raw}
    for arm in SPEC:
        if arm == "RANDOM_EQ_NORM":
            continue
        if arm not in source["controls"]:
            raise ExecutionContractError(f"V2_SOURCE_CONTROL_MISSING:{arm}")
        out[arm], ok = runtime_v1.rescale_to(source["controls"][arm], norm)
        if not ok:
            raise ExecutionContractError(f"V2_CONTROL_NORM_GUARD_FAIL:{arm}")
    random = runtime_v1.rademacher(
        int(raw.numel()),
        norm,
        f"ReplayResidualLocalContinuation|RANDOM_EQ_NORM|{packet['family']}|{packet['game_path']}|L{int(layer)}",
    )
    if norm > 1e-8 and abs(float(torch.linalg.vector_norm(random).item()) - norm) > max(1e-5, 1e-4 * norm):
        raise ExecutionContractError("V2_RANDOM_NORM_GUARD_FAIL")
    out["RANDOM_EQ_NORM"] = random
    return out


def execution_provenance(
    model_provenance: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    tokenizer_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "PLANCARRY_LOCALCONTINUATION_EXECUTION_PROVENANCE_V2",
        **dict(source_binding),
        "v2_control_schema": list(controls.CAUSAL_ARMS),
        "v2_specificity_controls": list(controls.SPECIFICITY_MAX_CONTROLS),
        "vector_schema": "ACTIVE=h_PLAN_PRESENT(t2)-h_NEUTRAL_FILLER(t2),FP32; v2 stored-ID semantic controls are neutral-referenced and active-norm matched; RANDOM uses unchanged SHA256-Rademacher",
        "session_schema": "unchanged reviewed v1 one reset-prefix intervention at selected layer/last-token-before-ACTION; same persistent KV thereafter; no reinjection",
        "packet_schema": "v2 Stage1 materializes plan/action IDs once pre-E; complete E freezes before donor; Stage2 consumes stored IDs only; direct exact128 replay",
        "safe_v1_runtime_reuse": list(_SAFE_V1_REUSE),
        "forbidden_v1_orchestration": list(_FORBIDDEN_V1_ORCHESTRATION),
        "tokenizer_provenance": dict(tokenizer_provenance),
        "model_provenance": dict(model_provenance),
        "scientific_variables_changed": [],
        "confirmation_accessed": False,
        "reserve_accessed": False,
        "valid_seen_accessed": False,
        "valid_unseen_accessed": False,
    }


def _atomic(path: Path, obj: Any) -> str:
    return phase.atomic_write_new(ROOT / path, obj)


def _refuse_development_outputs() -> None:
    for relative in OUTPUT_PATHS:
        if (ROOT / relative).exists():
            raise ExecutionContractError(f"V2_DEVELOPMENT_OUTPUT_EXISTS_BEFORE_MODEL_LOAD:{relative}")


def development(
    tokenizer: Any,
    model: Any,
    model_provenance: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    tokenizer_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    packets = produce_packets(tokenizer, model, model_provenance)
    by = {int(packet["frozen_index"]): packet for packet in packets}
    qualified = [idx for idx in phase.DEV if bool(by[idx].get("qualified"))]
    families = [{"index": idx, "qualified": idx in qualified} for idx in phase.DEV]
    execution = execution_provenance(model_provenance, source_binding, tokenizer_provenance)
    execution_sha = phase.sha_json(execution)
    common = {
        "phase": "LOCALCONTINUATION_DEVELOPMENT_V2",
        "families": families,
        "execution_provenance": execution,
        "execution_provenance_sha256": execution_sha,
        "confirmation_accessed": False,
        "reserve_accessed": False,
        "valid_seen_accessed": False,
        "valid_unseen_accessed": False,
        **phase.binding_payload(),
    }
    if len(qualified) < 16:
        payload = {**common, "grid_results": {}}
        validator.validate_split_access_flags(payload, "development")
        _atomic(DEV_PAYLOAD, payload)
        terminal = phase.select_development(payload)
        _atomic(DEV_TERMINAL, terminal)
        return terminal

    bases: dict[int, Mapping[str, Any]] = {}
    sources: dict[int, Mapping[int, Mapping[str, Any]]] = {}
    for position, idx in enumerate(qualified, 1):
        packet = by[idx]
        donor = _donor_packet(packet, by)
        bases[idx] = runtime_v1.base_reset(tokenizer, packet)
        sources[idx] = capture_sources_v2(tokenizer, model, packet, donor, LAYERS)
        print(json.dumps({"stage": "v2_dev_source_base", "done": position, "qualified": len(qualified)}), flush=True)

    grids: dict[str, Any] = {}
    for layer in LAYERS:
        for alpha in ALPHAS:
            key = phase.grid_key(layer, alpha)
            rows: dict[str, Any] = {}
            for position, idx in enumerate(qualified, 1):
                packet = by[idx]
                base = bases[idx]
                source = sources[idx][layer]
                active_sha = str(source["active_sha256"])
                vectors = vectors_for_grid_v2(source, packet, layer)
                arms: dict[str, Any] = {
                    NO_PATCH: runtime_v1.msa2_arm(tokenizer, model, packet, base, layer, None, alpha, NO_PATCH, active_sha),
                    ACTIVE: runtime_v1.msa2_arm(tokenizer, model, packet, base, layer, vectors[ACTIVE], alpha, ACTIVE, active_sha),
                }
                for arm in SPEC:
                    arms[arm] = runtime_v1.msa2_arm(tokenizer, model, packet, base, layer, vectors[arm], alpha, arm, active_sha)
                rows[str(idx)] = {
                    "arms": arms,
                    "active_raw_residual_l2": float(source["active_l2"]),
                    "active_residual_sha256": active_sha,
                    "reset_snapshot_sha256": str(base["reset_snapshot_sha256"]),
                }
                print(
                    json.dumps(
                        {"stage": "v2_dev_grid", "layer": layer, "alpha": alpha, "done": position, "qualified": len(qualified)}
                    ),
                    flush=True,
                )
            grids[key] = rows

    payload = {**common, "grid_results": grids}
    validator.validate_split_access_flags(payload, "development")
    _atomic(DEV_PAYLOAD, payload)
    terminal = phase.select_development(payload, ROOT / DEV_SEAL)
    _atomic(DEV_TERMINAL, terminal)
    return terminal


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["preflight", "development"], required=True)
    parser.add_argument("--expected-git-commit", required=True)
    parser.add_argument("--expected-driver-sha256", required=True)
    parser.add_argument("--expected-phase-sha256", required=True)
    parser.add_argument("--expected-device")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    source_binding = verify_sources(args.expected_git_commit, args.expected_driver_sha256, args.expected_phase_sha256)
    tokenizer, tokenizer_provenance = verify_tokenizer_only()
    rows = pb.load_population_phase("development", ROOT)
    indices = [int(row["frozen_index"]) for row in rows]
    if indices != list(range(32)):
        raise ExecutionContractError(f"V2_PREFLIGHT_DEVELOPMENT_INDICES:{indices}")
    _refuse_development_outputs()

    if args.phase == "preflight":
        result = {
            "status": "READY_NO_SCIENCE",
            "development_indices": indices,
            "source_binding": source_binding,
            "tokenizer_provenance": tokenizer_provenance,
            "model_calls": 0,
            "model_loads": 0,
            "environment_execution": 0,
            "confirmation_accessed": False,
            "reserve_accessed": False,
            "valid_seen_accessed": False,
            "valid_unseen_accessed": False,
            "vast_started_by_this_process": False,
            "authorization": "PRE_SCIENCE_ONLY",
        }
        print(json.dumps({"LOCALCONTINUATION_V2_PREFLIGHT": result}, sort_keys=True))
        return 0

    if not args.expected_device:
        raise ExecutionContractError("--expected-device required for development")
    runtime_tokenizer, model, model_provenance = runtime_v1.load_runtime(args.expected_device)
    runtime_tokenizer_provenance = tokenizer_report(runtime_tokenizer)
    tokenizer_core_keys = (
        "model_id", "revision", "transformers_version", "tokenizers_version",
        "neutral_filler_primitive_ids", "neutral_filler_stream_sha256",
        "past_action_separator_ids", "opening_tag_ids_sha256", "closing_tag_ids_sha256",
    )
    for key in tokenizer_core_keys:
        if runtime_tokenizer_provenance.get(key) != tokenizer_provenance.get(key):
            raise ExecutionContractError(f"RUNTIME_TOKENIZER_DIFFERS_FROM_PREFLIGHT_TOKENIZER:{key}")
    terminal = development(runtime_tokenizer, model, model_provenance, source_binding, tokenizer_provenance)
    print(json.dumps({"LOCALCONTINUATION_V2_TERMINAL": terminal}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
