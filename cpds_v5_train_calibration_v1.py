from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import torch
import torch.nn.functional as F

from cpds_v5_partition_v1 import (
    deterministic_z0_donor_index,
    partition_name,
    validate_blind_reserved_overlap,
)
from cpds_v5_provenance_v1 import (
    TRAIN_MANIFEST_SCHEMA,
    build_train_provenance,
    load_reserved_v4_hash_seal,
    validate_calibration_checkpoint_binding,
)
from cpds_v5_predictive_recurrence_v1 import (
    BASE_MODEL_ID,
    BASE_MODEL_REVISION,
    CPDSV5Adapter,
    G_GAIN,
    NATIVE_WIDTH,
    REALIZATION,
    STATE_WIDTH,
    canonical_bytes,
    deterministic_nonidentity_permutation,
    save_deterministic_checkpoint,
    sha256_file,
)

ROOT = Path(__file__).resolve().parent
RECIPE_PATH = ROOT / "results/design/plancarry_cpds_v5_training_recipe_a1_20260830.json"
REVIEWED_DESIGN_PATH = ROOT / "results/design/plancarry_cpds_v5_post_adversarial_design_repair_a1_20260831.json"
REVIEWED_RECIPE_SHA256 = "861537f18959bcff736e7cbe30fdf07e128c7621ed5fb4e3522d598f77acab8c"
REVIEWED_SCIENTIFIC_SPEC_HASH = "3a730d7fca46ae1c9736d3546588fb08143212f0ba52e580f70b7ba450a189b2"
PACKET_SCHEMA = "PLANCARRY_CPDS_V5_PRECOMPUTED_FEATURE_SEQUENCE_V1"
CALIBRATION_PASS = "CALIBRATION_CONSTRUCTIBILITY_PASS_NOT_SCIENTIFIC_SUPPORT"
CALIBRATION_FAIL = "CONSTRUCTIBILITY_INCONCLUSIVE_NO_V5_DEVELOPMENT"


def _canonical_json_no_newline(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load_reviewed_contract(path: Path = REVIEWED_DESIGN_PATH) -> dict[str, Any]:
    d = json.loads(path.read_text(encoding="utf-8"))
    protected = d.get("protected_scientific_semantics")
    if not isinstance(protected, dict):
        raise ValueError("REVIEWED_PROTECTED_SEMANTICS")
    h = hashlib.sha256(_canonical_json_no_newline(protected)).hexdigest()
    if h != REVIEWED_SCIENTIFIC_SPEC_HASH or d.get("scientific_spec_hash") != h:
        raise ValueError("REVIEWED_SCIENTIFIC_SPEC_HASH")
    tc = d.get("training_contract", {})
    rp = tc.get("recipe_provenance", {})
    if rp.get("file_sha256") != REVIEWED_RECIPE_SHA256:
        raise ValueError("REVIEWED_RECIPE_PROVENANCE")
    return d


def load_recipe(path: Path = RECIPE_PATH) -> dict[str, Any]:
    if sha256_file(path) != REVIEWED_RECIPE_SHA256:
        raise ValueError("RECIPE_SHA256")
    d = json.loads(path.read_text(encoding="utf-8"))
    if d["realization"] != REALIZATION or d["adapter"]["G_gain"] != G_GAIN or d["adapter"]["state_width"] != STATE_WIDTH:
        raise ValueError("RECIPE_IDENTITY")
    if d["training"]["early_stopping"] != "NONE" or d["training"]["checkpoint_selection"] != "FINAL_EPOCH_ONLY" or d["training"]["calibration_model_selection"]:
        raise ValueError("POSTHOC_MODEL_SELECTION_FORBIDDEN")
    reviewed = load_reviewed_contract()["training_contract"]["exact_recurrent_recipe"]
    cfg = d["training"]
    exact = {
        "seed": cfg["seed"], "torch_num_threads": cfg["torch_num_threads"],
        "optimizer": cfg["optimizer"], "learning_rate": cfg["learning_rate"],
        "betas": cfg["betas"], "eps": cfg["eps"], "weight_decay": cfg["weight_decay"],
        "epochs": cfg["epochs"], "batch_sequences": cfg["batch_sequences"],
        "gradient_clip_norm": cfg["gradient_clip_norm"],
        "secondary_contrastive_weight": cfg["secondary_contrastive_weight"],
        "early_stopping": cfg["early_stopping"], "checkpoint_selection": cfg["checkpoint_selection"],
        "calibration_model_selection": cfg["calibration_model_selection"],
    }
    for k, v in exact.items():
        if reviewed.get(k) != v:
            raise ValueError("RECIPE_REVIEWED_CONTRACT_MISMATCH:" + k)
    if reviewed.get("recurrent_static_joint_weight") != {"RECURRENT": 0.5, "STATIC_PREDICTIVE_SHARED_G": 0.5}:
        raise ValueError("JOINT_BRANCH_WEIGHT")
    return d


def _vec(x: Sequence[float], width: int, name: str) -> torch.Tensor:
    if len(x) != width:
        raise ValueError(name + "_WIDTH")
    t = torch.tensor(x, dtype=torch.float32)
    if not torch.isfinite(t).all():
        raise ValueError(name + "_NONFINITE")
    return t


def _packet(path: Path) -> dict[str, Any]:
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("schema") != PACKET_SCHEMA:
        raise ValueError("PACKET_SCHEMA")
    forbidden = {
        "branch_A", "branch_B", "branch_A_equivalence_class", "branch_B_equivalence_class",
        "evaluator_label", "outcome", "correctness", "endpoint",
    }
    def walk_keys(x: Any) -> set[str]:
        if isinstance(x, dict):
            out = set(x)
            for v in x.values(): out |= walk_keys(v)
            return out
        if isinstance(x, list):
            out = set()
            for v in x: out |= walk_keys(v)
            return out
        return set()
    if forbidden & walk_keys(d):
        raise ValueError("EVALUATOR_OR_OUTCOME_FIELD_FORBIDDEN")
    if d.get("base_model_id") != BASE_MODEL_ID or d.get("base_model_revision") != BASE_MODEL_REVISION:
        raise ValueError("BASE_MODEL_IDENTITY")
    if partition_name(d["source_graph_id"]) != d["partition"]:
        raise ValueError("PACKET_PARTITION")
    if not isinstance(d.get("packet_id"), str) or not d["packet_id"]:
        raise ValueError("PACKET_ID")
    if not isinstance(d.get("structural_key_sha256"), str) or len(d["structural_key_sha256"]) != 64:
        raise ValueError("STRUCTURAL_KEY_SHA256")
    if len(d.get("updates", [])) < 2:
        raise ValueError("NEED_AT_LEAST_TWO_TRANSITIONS")
    return d


def load_packet_dir(packet_dir: str | Path, expected_partition: str, reserved_v4_hash_file: str | Path | None, recipe: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    packet_dir = Path(packet_dir)
    if expected_partition not in ("TRAIN", "CALIBRATION"):
        raise ValueError("PARTITION")
    recipe = load_recipe() if recipe is None else recipe
    reserved_seal, _ = load_reserved_v4_hash_seal(reserved_v4_hash_file, recipe)
    packets = [_packet(p) for p in sorted(packet_dir.glob("*.json"))]
    if not packets:
        raise ValueError("NO_PACKETS")
    if any(p["partition"] != expected_partition for p in packets):
        raise ValueError("PARTITION_MIX")
    graph_ids = [p["source_graph_id"] for p in packets]
    if len(graph_ids) != len(set(graph_ids)):
        raise ValueError("DUPLICATE_SOURCE_GRAPH")
    packet_ids = [p["packet_id"] for p in packets]
    if len(packet_ids) != len(set(packet_ids)):
        raise ValueError("DUPLICATE_PACKET_ID")
    validate_blind_reserved_overlap([p["structural_key_sha256"] for p in packets], reserved_seal["structural_family_key_sha256s"])
    return packets


def _site_loss(model: CPDSV5Adapter, z: torch.Tensor, site: Mapping[str, Any]) -> torch.Tensor:
    base = torch.tensor(site["base_scores"], dtype=torch.float32)
    actions = torch.stack([_vec(x, NATIVE_WIDTH, "ACTION") for x in site["action_features"]])
    target = int(site["target_index"])
    if target < 0 or target >= len(base) or len(base) != len(actions):
        raise ValueError("TARGET_GEOMETRY")
    logits = model.adjusted_scores(base, z, actions)
    return F.cross_entropy(logits.unsqueeze(0), torch.tensor([target], dtype=torch.long))


def _contrastive_loss(model: CPDSV5Adapter, z: torch.Tensor, update: Mapping[str, Any]) -> torch.Tensor:
    pos = model.transition_input(_vec(update["next_transition_hidden"], NATIVE_WIDTH, "NEXT_TRANSITION"))
    neg = model.transition_input(_vec(update["negative_transition_hidden"], NATIVE_WIDTH, "NEG_TRANSITION"))
    return F.softplus(-(torch.dot(z, pos) - torch.dot(z, neg)))


def _branch_sequence_loss(model: CPDSV5Adapter, packet: Mapping[str, Any], secondary_weight: float, *, static: bool) -> torch.Tensor:
    hpre = _vec(packet["pre_reset_hidden"], NATIVE_WIDTH, "PRE_RESET")
    z = model.static_state(hpre) if static else model.z0(hpre)
    losses = []
    for upd in packet["updates"]:
        if not static:
            z = model.step(z, _vec(upd["transition_hidden"], NATIVE_WIDTH, "TRANSITION"))
        losses.append(_site_loss(model, z, upd["prediction_site"]))
        if "next_transition_hidden" in upd and "negative_transition_hidden" in upd:
            losses.append(float(secondary_weight) * _contrastive_loss(model, z, upd))
    return torch.stack(losses).mean()


def sequence_training_loss(model: CPDSV5Adapter, packet: Mapping[str, Any], secondary_weight: float) -> torch.Tensor:
    recurrent = _branch_sequence_loss(model, packet, secondary_weight, static=False)
    static = _branch_sequence_loss(model, packet, secondary_weight, static=True)
    return 0.5 * recurrent + 0.5 * static


def packet_order_key(packet: Mapping[str, Any], seed: int) -> str:
    return hashlib.sha256((packet["source_graph_id"] + packet["packet_id"] + str(int(seed))).encode("utf-8")).hexdigest()


def train_model(train_packets: Sequence[Mapping[str, Any]], recipe: Mapping[str, Any]) -> tuple[CPDSV5Adapter, dict[str, Any]]:
    cfg = recipe["training"]
    seed = int(cfg["seed"])
    random.seed(seed); torch.manual_seed(seed); torch.set_num_threads(int(cfg["torch_num_threads"]))
    torch.use_deterministic_algorithms(True)
    model = CPDSV5Adapter().cpu().train()
    opt = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]), betas=tuple(cfg["betas"]), eps=float(cfg["eps"]), weight_decay=float(cfg["weight_decay"]))
    order = sorted(range(len(train_packets)), key=lambda i: (packet_order_key(train_packets[i], seed), train_packets[i]["packet_id"]))
    epoch_losses = []
    batch_n = int(cfg["batch_sequences"])
    for _epoch in range(int(cfg["epochs"])):
        opt.zero_grad(set_to_none=True); pending = 0; total = 0.0
        for j, idx in enumerate(order):
            loss = sequence_training_loss(model, train_packets[idx], float(cfg["secondary_contrastive_weight"]))
            loss.backward(); total += float(loss.detach()); pending += 1
            if pending == batch_n or j == len(order) - 1:
                torch.nn.utils.clip_grad_norm_(model.parameters(), float(cfg["gradient_clip_norm"]))
                opt.step(); opt.zero_grad(set_to_none=True); pending = 0
        epoch_losses.append(total / len(order))
    return model.eval(), {
        "epoch_losses": epoch_losses,
        "final_train_loss": epoch_losses[-1],
        "epochs": int(cfg["epochs"]), "seed": seed,
        "packet_order_sha256": hashlib.sha256(canonical_bytes([train_packets[i]["packet_id"] for i in order])).hexdigest(),
        "joint_branch_weights": {"RECURRENT": 0.5, "STATIC_PREDICTIVE_SHARED_G": 0.5},
    }


def _final_site(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    site = packet.get("final_prediction_site")
    if not isinstance(site, dict):
        raise ValueError("FINAL_PREDICTION_SITE")
    return site


def calibration_donor_z0_map(packets: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Freeze every CALIBRATION donor identity from structure-only fields before scoring."""
    candidates = [
        {"source_graph_id": p["source_graph_id"], "structural_id": p["structural_key_sha256"], "phase": "CALIBRATION"}
        for p in packets
    ]
    out: dict[str, str] = {}
    for p in packets:
        i = deterministic_z0_donor_index(p["structural_key_sha256"], p["source_graph_id"], "CALIBRATION", candidates)
        out[p["packet_id"]] = packets[i]["packet_id"]
    if len(out) != len(packets):
        raise ValueError("DONOR_Z0_MAP_PACKET_ID_COLLISION")
    return out


def _final_states(model: CPDSV5Adapter, packet: Mapping[str, Any], donor_packet: Mapping[str, Any]) -> dict[str, torch.Tensor]:
    hpre = _vec(packet["pre_reset_hidden"], NATIVE_WIDTH, "PRE_RESET")
    z0 = model.z0(hpre)
    ts = [_vec(u["transition_hidden"], NATIVE_WIDTH, "TRANSITION") for u in packet["updates"]]
    pi = deterministic_nonidentity_permutation(packet["source_graph_id"], len(ts))
    donor_z0 = model.z0(_vec(donor_packet["pre_reset_hidden"], NATIVE_WIDTH, "DONOR_PRE_RESET"))
    return {
        "STATIC_REPEAT": z0,
        "STATIC_PREDICTIVE_SHARED_G": model.static_state(hpre),
        "ALIGNED_RECURSION": model.fold(z0, ts),
        "ZERO_Z0_RECURSION": model.fold_zero_z0(ts),
        "DONOR_Z0_RECURSION": model.fold(donor_z0, ts),
        "LAST_TRANSITION_ONLY": model.last_transition_only(z0, ts),
        "BAGGED_TRANSITIONS": model.bagged_transitions(z0, ts),
        "TRANSITION_PERMUTED": model.fold(z0, [ts[i] for i in pi]),
    }


def _unit_state(z: torch.Tensor) -> bool:
    if not torch.isfinite(z).all(): return False
    n = float(torch.linalg.vector_norm(z.float()).detach())
    return abs(n - 1.0) <= 1e-5


def calibration_gate(model: CPDSV5Adapter, calibration_packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(calibration_packets) < 2:
        raise ValueError("CALIBRATION_DONOR_Z0_REQUIRES_TWO_GRAPHS")
    losses = {k: [] for k in (
        "ALIGNED_RECURSION", "STATIC_REPEAT", "TRANSITION_PERMUTED", "ZERO_Z0_RECURSION",
        "DONOR_Z0_RECURSION", "LAST_TRANSITION_ONLY", "BAGGED_TRANSITIONS", "STATIC_PREDICTIVE_SHARED_G",
    )}
    # Freeze the complete structure-only donor mapping before any predictive endpoint is scored.
    donor_map = calibration_donor_z0_map(calibration_packets)
    by_packet_id = {p["packet_id"]: p for p in calibration_packets}
    donor_map_sha256 = hashlib.sha256(canonical_bytes(donor_map)).hexdigest()
    nonidentity = []; states_ok = []; g_ok = []
    with torch.no_grad():
        for p in calibration_packets:
            states = _final_states(model, p, by_packet_id[donor_map[p["packet_id"]]])
            states_ok.append(all(_unit_state(z) for z in states.values()))
            nonidentity.append(not torch.equal(states["ALIGNED_RECURSION"], states["TRANSITION_PERMUTED"]))
            site = _final_site(p)
            acts = torch.stack([_vec(x, NATIVE_WIDTH, "ACTION") for x in site["action_features"]])
            arm_g_ok = []
            for arm, z in states.items():
                losses[arm].append(float(_site_loss(model, z, site)))
                d = model.g_delta(z, acts)
                arm_g_ok.append(bool(torch.isfinite(d).all() and torch.all(d >= -1.000001) and torch.all(d <= 1.000001)))
            aligned_delta = model.g_delta(states["ALIGNED_RECURSION"], acts)
            arm_g_ok.append(not torch.all(aligned_delta == aligned_delta[0]))
            g_ok.append(all(arm_g_ok))
    med = {k: float(median(v)) for k, v in losses.items()}
    checks = {
        "finite_unit_states_every_arm_every_sequence": all(states_ok),
        "aligned_permuted_nonidentical_every_sequence": all(nonidentity),
        "median_aligned_loss_lt_static_repeat": med["ALIGNED_RECURSION"] < med["STATIC_REPEAT"],
        "median_aligned_loss_lt_permuted": med["ALIGNED_RECURSION"] < med["TRANSITION_PERMUTED"],
        "median_aligned_loss_lt_zero_z0": med["ALIGNED_RECURSION"] < med["ZERO_Z0_RECURSION"],
        "median_aligned_loss_lt_donor_z0": med["ALIGNED_RECURSION"] < med["DONOR_Z0_RECURSION"],
        "median_aligned_loss_lt_last_transition": med["ALIGNED_RECURSION"] < med["LAST_TRANSITION_ONLY"],
        "median_aligned_loss_lt_bagged": med["ALIGNED_RECURSION"] < med["BAGGED_TRANSITIONS"],
        "median_aligned_loss_lt_static_predictive": med["ALIGNED_RECURSION"] < med["STATIC_PREDICTIVE_SHARED_G"],
        "G_bounded_finite_and_aligned_nonconstant_every_sequence": all(g_ok),
        "branch_evaluator_outcome_path_count": 0,
        "calibration_model_selection": False,
    }
    passed = all(v is True for k, v in checks.items() if k not in ("branch_evaluator_outcome_path_count", "calibration_model_selection")) and checks["branch_evaluator_outcome_path_count"] == 0 and checks["calibration_model_selection"] is False
    return {
        "schema": "PLANCARRY_CPDS_V5_CALIBRATION_CONSTRUCTIBILITY_V2_POST_ADVERSARIAL",
        "scientific_result": "NOT_ASSESSED_PREDEVELOPMENT_CONSTRUCTIBILITY_ONLY",
        "status": CALIBRATION_PASS if passed else CALIBRATION_FAIL,
        "n_sequences": len(calibration_packets),
        "median_predictive_loss": med,
        "checks": checks,
        "scientific_spec_hash": REVIEWED_SCIENTIFIC_SPEC_HASH,
        "donor_z0_map_sha256": donor_map_sha256,
        "v5_development_authorized": False,
        "confirmation_status": "HARD_SEALED_NO_RUNTIME_ROUTE",
    }


def main() -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="mode", required=True)
    t = sub.add_parser("train"); t.add_argument("--train-dir", required=True); t.add_argument("--reserved-v4-hashes",required=True); t.add_argument("--checkpoint", required=True); t.add_argument("--manifest", required=True)
    c = sub.add_parser("calibrate"); c.add_argument("--calibration-dir", required=True); c.add_argument("--reserved-v4-hashes",required=True); c.add_argument("--checkpoint", required=True); c.add_argument("--checkpoint-sha256", required=True); c.add_argument("--train-manifest",required=True); c.add_argument("--train-manifest-sha256",required=True); c.add_argument("--result", required=True)
    args = ap.parse_args(); recipe = load_recipe(); contract = load_reviewed_contract(); recipe_sha = sha256_file(RECIPE_PATH)
    _, reserved_seal_sha = load_reserved_v4_hash_seal(args.reserved_v4_hashes, recipe)
    if args.mode == "train":
        packets = load_packet_dir(args.train_dir, "TRAIN", args.reserved_v4_hashes, recipe)
        model, train_info = train_model(packets, recipe)
        train_prov = build_train_provenance(packets, reserved_seal_sha)
        ck = save_deterministic_checkpoint(args.checkpoint, model, recipe_sha256=recipe_sha, provenance=train_prov)
        manifest = {
            "schema": TRAIN_MANIFEST_SCHEMA,
            "scientific_result": "NOT_ASSESSED_TRAIN_ONLY", "realization": REALIZATION,
            "scientific_spec_hash": contract["scientific_spec_hash"], "recipe_sha256": recipe_sha,
            "reserved_v4_hash_seal_sha256": reserved_seal_sha, "checkpoint_sha256": ck["sha256"],
            "checkpoint_bytes": ck["bytes"], "checkpoint_header_sha256": ck["header_sha256"],
            "train_provenance": train_prov, "train": train_info,
            "development_access": False, "confirmation_access": False,
        }
        Path(args.manifest).write_bytes(canonical_bytes(manifest)); return 0
    packets = load_packet_dir(args.calibration_dir, "CALIBRATION", args.reserved_v4_hashes, recipe)
    binding = validate_calibration_checkpoint_binding(
        checkpoint_path=args.checkpoint, checkpoint_sha256=args.checkpoint_sha256, recipe_sha256=recipe_sha,
        reserved_v4_hash_seal_sha256=reserved_seal_sha, train_manifest_path=args.train_manifest,
        train_manifest_sha256=args.train_manifest_sha256,
    )
    model = CPDSV5Adapter().cpu().eval()
    from cpds_v5_predictive_recurrence_v1 import load_deterministic_checkpoint
    load_deterministic_checkpoint(args.checkpoint, model, expected_sha256=args.checkpoint_sha256)
    result = calibration_gate(model, packets)
    result["checkpoint_sha256"] = args.checkpoint_sha256; result["recipe_sha256"] = recipe_sha
    result["reserved_v4_hash_seal_sha256"] = reserved_seal_sha; result["train_manifest_sha256"] = binding["train_manifest_sha256"]
    result["checkpoint_header_sha256"] = binding["checkpoint_header_sha256"]; result["train_source_provenance"] = binding["train_provenance"]
    Path(args.result).write_bytes(canonical_bytes(result)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
