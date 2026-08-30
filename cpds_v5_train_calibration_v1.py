from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import torch
import torch.nn.functional as F

from cpds_v5_partition_v1 import partition_name, validate_blind_reserved_overlap, validate_source_graph_disjoint
from cpds_v5_predictive_recurrence_v1 import (
    BASE_MODEL_ID, BASE_MODEL_REVISION, CPDSV5Adapter, G_GAIN, NATIVE_WIDTH, REALIZATION,
    STATE_WIDTH, canonical_bytes, deterministic_nonidentity_permutation, save_deterministic_checkpoint,
    sha256_file, unit_l2,
)

RECIPE_PATH = Path(__file__).resolve().parent / "results/design/plancarry_cpds_v5_training_recipe_a1_20260830.json"
PACKET_SCHEMA = "PLANCARRY_CPDS_V5_PRECOMPUTED_FEATURE_SEQUENCE_V1"
CALIBRATION_PASS = "CALIBRATION_CONSTRUCTIBILITY_PASS_NOT_SCIENTIFIC_SUPPORT"
CALIBRATION_FAIL = "CONSTRUCTIBILITY_INCONCLUSIVE_NO_V5_DEVELOPMENT"


def load_recipe(path: Path = RECIPE_PATH) -> dict[str, Any]:
    d = json.loads(path.read_text(encoding="utf-8"))
    if d["realization"] != REALIZATION or d["adapter"]["G_gain"] != G_GAIN or d["adapter"]["state_width"] != STATE_WIDTH:
        raise ValueError("RECIPE_IDENTITY")
    if d["training"]["early_stopping"] != "NONE" or d["training"]["checkpoint_selection"] != "FINAL_EPOCH_ONLY" or d["training"]["calibration_model_selection"]:
        raise ValueError("POSTHOC_MODEL_SELECTION_FORBIDDEN")
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
    forbidden = {"branch_A", "branch_B", "branch_A_equivalence_class", "branch_B_equivalence_class", "evaluator_label", "outcome"}
    def walk_keys(x: Any) -> set[str]:
        if isinstance(x, dict):
            out=set(x)
            for v in x.values(): out |= walk_keys(v)
            return out
        if isinstance(x, list):
            out=set()
            for v in x: out |= walk_keys(v)
            return out
        return set()
    if forbidden & walk_keys(d):
        raise ValueError("EVALUATOR_OR_OUTCOME_FIELD_FORBIDDEN")
    if d.get("base_model_id") != BASE_MODEL_ID or d.get("base_model_revision") != BASE_MODEL_REVISION:
        raise ValueError("BASE_MODEL_IDENTITY")
    if partition_name(d["source_graph_id"]) != d["partition"]:
        raise ValueError("PACKET_PARTITION")
    if len(d.get("updates", [])) < 2:
        raise ValueError("NEED_AT_LEAST_TWO_TRANSITIONS")
    return d


def load_packet_dir(packet_dir: str | Path, expected_partition: str, reserved_v4_hash_file: str | Path | None = None) -> list[dict[str, Any]]:
    packet_dir = Path(packet_dir)
    if expected_partition not in ("TRAIN", "CALIBRATION"):
        raise ValueError("PARTITION")
    packets = [_packet(p) for p in sorted(packet_dir.glob("*.json"))]
    if not packets:
        raise ValueError("NO_PACKETS")
    if any(p["partition"] != expected_partition for p in packets):
        raise ValueError("PARTITION_MIX")
    graph_ids = [p["source_graph_id"] for p in packets]
    if len(graph_ids) != len(set(graph_ids)):
        raise ValueError("DUPLICATE_SOURCE_GRAPH")
    candidate_hashes = [p["structural_key_sha256"] for p in packets]
    if reserved_v4_hash_file is not None:
        reserved = json.loads(Path(reserved_v4_hash_file).read_text(encoding="utf-8"))
        if not isinstance(reserved, list):
            raise ValueError("RESERVED_HASH_FORMAT")
        validate_blind_reserved_overlap(candidate_hashes, reserved)
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
    pos_s = torch.dot(z, pos); neg_s = torch.dot(z, neg)
    return F.softplus(-(pos_s - neg_s))


def sequence_training_loss(model: CPDSV5Adapter, packet: Mapping[str, Any], secondary_weight: float) -> torch.Tensor:
    z = model.z0(_vec(packet["pre_reset_hidden"], NATIVE_WIDTH, "PRE_RESET"))
    losses = []
    for upd in packet["updates"]:
        z = model.step(z, _vec(upd["transition_hidden"], NATIVE_WIDTH, "TRANSITION"))
        losses.append(_site_loss(model, z, upd["prediction_site"]))
        if "next_transition_hidden" in upd and "negative_transition_hidden" in upd:
            losses.append(float(secondary_weight) * _contrastive_loss(model, z, upd))
    return torch.stack(losses).mean()


def train_model(train_packets: Sequence[Mapping[str, Any]], recipe: Mapping[str, Any]) -> tuple[CPDSV5Adapter, dict[str, Any]]:
    cfg = recipe["training"]
    seed = int(cfg["seed"])
    random.seed(seed); torch.manual_seed(seed); torch.set_num_threads(int(cfg["torch_num_threads"]))
    torch.use_deterministic_algorithms(True)
    model = CPDSV5Adapter().cpu().train()
    opt = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]), betas=tuple(cfg["betas"]), eps=float(cfg["eps"]), weight_decay=float(cfg["weight_decay"]))
    order_gen = random.Random(seed)
    epoch_losses = []
    batch_n = int(cfg["batch_sequences"])
    for epoch in range(int(cfg["epochs"])):
        order = list(range(len(train_packets))); order_gen.shuffle(order)
        opt.zero_grad(set_to_none=True); pending = 0; total = 0.0
        for j, idx in enumerate(order):
            loss = sequence_training_loss(model, train_packets[idx], float(cfg["secondary_contrastive_weight"]))
            loss.backward(); total += float(loss.detach()); pending += 1
            if pending == batch_n or j == len(order)-1:
                torch.nn.utils.clip_grad_norm_(model.parameters(), float(cfg["gradient_clip_norm"]))
                opt.step(); opt.zero_grad(set_to_none=True); pending = 0
        epoch_losses.append(total / len(order))
    return model.eval(), {"epoch_losses": epoch_losses, "final_train_loss": epoch_losses[-1], "epochs": int(cfg["epochs"]), "seed": seed}


def _final_site(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    site = packet.get("final_prediction_site")
    if not isinstance(site, dict):
        raise ValueError("FINAL_PREDICTION_SITE")
    return site


def _final_states(model: CPDSV5Adapter, packet: Mapping[str, Any]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    z0 = model.z0(_vec(packet["pre_reset_hidden"], NATIVE_WIDTH, "PRE_RESET"))
    ts = [_vec(u["transition_hidden"], NATIVE_WIDTH, "TRANSITION") for u in packet["updates"]]
    aligned = model.fold(z0, ts)
    pi = deterministic_nonidentity_permutation(packet["source_graph_id"], len(ts))
    permuted = model.fold(z0, [ts[i] for i in pi])
    return z0, aligned, permuted


def calibration_gate(model: CPDSV5Adapter, calibration_packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    aligned_losses=[]; static_losses=[]; permuted_losses=[]; nonidentity=[]; g_ok=[]
    with torch.no_grad():
        for p in calibration_packets:
            z0, za, zp = _final_states(model,p)
            if not all(torch.isfinite(z).all() and float(torch.sum(z*z)) > 0 for z in (z0,za,zp)):
                raise ValueError("CALIBRATION_STATE_INVALID")
            nonidentity.append(not torch.equal(za, zp))
            site = _final_site(p)
            aligned_losses.append(float(_site_loss(model, za, site)))
            static_losses.append(float(_site_loss(model, z0, site)))
            permuted_losses.append(float(_site_loss(model, zp, site)))
            acts = torch.stack([_vec(x,NATIVE_WIDTH,"ACTION") for x in site["action_features"]])
            d = model.g_delta(za,acts)
            g_ok.append(bool(torch.isfinite(d).all() and torch.all(d>=-1.000001) and torch.all(d<=1.000001) and not torch.all(d == d[0])))
    med_a=float(median(aligned_losses)); med_s=float(median(static_losses)); med_p=float(median(permuted_losses))
    checks={
        "finite_nonzero_states": True,
        "aligned_permuted_nonidentical_every_sequence": all(nonidentity),
        "median_aligned_loss_lt_static": med_a < med_s,
        "median_aligned_loss_lt_permuted": med_a < med_p,
        "G_bounded_finite_nonconstant_every_sequence": all(g_ok),
        "branch_evaluator_outcome_path_count": 0,
    }
    passed = (
        checks["finite_nonzero_states"] is True
        and checks["aligned_permuted_nonidentical_every_sequence"] is True
        and checks["median_aligned_loss_lt_static"] is True
        and checks["median_aligned_loss_lt_permuted"] is True
        and checks["G_bounded_finite_nonconstant_every_sequence"] is True
        and checks["branch_evaluator_outcome_path_count"] == 0
    )
    return {
        "schema":"PLANCARRY_CPDS_V5_CALIBRATION_CONSTRUCTIBILITY_V1",
        "scientific_result":"NOT_ASSESSED_PREDEVELOPMENT_CONSTRUCTIBILITY_ONLY",
        "status": CALIBRATION_PASS if passed else CALIBRATION_FAIL,
        "n_sequences":len(calibration_packets),
        "median_predictive_loss":{"ALIGNED":med_a,"STATIC_Z0":med_s,"TRANSITION_PERMUTED":med_p},
        "checks":checks,
        "v5_development_authorized":False,
        "confirmation_status":"HARD_SEALED_NO_RUNTIME_ROUTE",
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="mode",required=True)
    t=sub.add_parser("train"); t.add_argument("--train-dir",required=True); t.add_argument("--reserved-v4-hashes"); t.add_argument("--checkpoint",required=True); t.add_argument("--manifest",required=True)
    c=sub.add_parser("calibrate"); c.add_argument("--calibration-dir",required=True); c.add_argument("--reserved-v4-hashes"); c.add_argument("--checkpoint",required=True); c.add_argument("--checkpoint-sha256",required=True); c.add_argument("--result",required=True)
    args=ap.parse_args(); recipe=load_recipe(); recipe_sha=sha256_file(RECIPE_PATH)
    if args.mode=="train":
        packets=load_packet_dir(args.train_dir,"TRAIN",args.reserved_v4_hashes)
        model,train_info=train_model(packets,recipe)
        ck=save_deterministic_checkpoint(args.checkpoint,model,recipe_sha256=recipe_sha,provenance={"partition":"TRAIN","packet_count":len(packets),"source_graph_ids_sha256":hashlib.sha256(canonical_bytes(sorted(p["source_graph_id"] for p in packets))).hexdigest()})
        manifest={"schema":"PLANCARRY_CPDS_V5_TRAIN_FREEZE_V1","scientific_result":"NOT_ASSESSED_TRAIN_ONLY","realization":REALIZATION,"recipe_sha256":recipe_sha,"checkpoint_sha256":ck["sha256"],"checkpoint_bytes":ck["bytes"],"train":train_info,"development_access":False,"confirmation_access":False}
        Path(args.manifest).write_bytes(canonical_bytes(manifest)); return 0
    packets=load_packet_dir(args.calibration_dir,"CALIBRATION",args.reserved_v4_hashes)
    model=CPDSV5Adapter().cpu().eval()
    from cpds_v5_predictive_recurrence_v1 import load_deterministic_checkpoint
    load_deterministic_checkpoint(args.checkpoint,model,expected_sha256=args.checkpoint_sha256)
    result=calibration_gate(model,packets); result["checkpoint_sha256"]=args.checkpoint_sha256; result["recipe_sha256"]=recipe_sha
    Path(args.result).write_bytes(canonical_bytes(result)); return 0

if __name__=="__main__": raise SystemExit(main())
