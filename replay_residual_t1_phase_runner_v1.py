"""Pre-outcome phase sealing and statistics for frozen ReplayResidual T1 v1.1.

This module is deliberately model/environment agnostic.  It contains no ALFWorld,
TextWorld, Transformers, tokenizer, or model-loading path.  A future separately
reviewed scientific executor may provide exact-token/session outcomes to it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

T1_PREREG_SHA256 = "77a7d9c9ee597551da8e8ef0b8a2c79038990968e3f62735ff90ed8c9c7d55e2"
GAP_MATRIX_SHA256 = "8cd22aff1d89b7a54eaa07b833dc75ecc1286f6938e39ee72256dd9705cba895"
V2_1_CONTRACT_SHA256 = "83370fbfc65c4818ada159a0e3c83cf778b88ed02f964bcf7887e5cea3843158"
SESSION_RUNTIME_SHA256 = "585e44ec5cd2395be0804b865de85ac36c5db79117cf4061566cf16a9749e3b6"
SANITY_REQUIRED = "PASS_REPLAY_RESIDUAL_SANITY"
SUPPORTED_PRIMARY = "SUPPORTED_REPLAY_RESIDUAL_T1"
DEVELOPMENT_INDICES = tuple(range(0, 32))
CONFIRMATION_INDICES = tuple(range(32, 52))
T1R_INDICES = tuple(range(52, 64))
LAYERS = (7, 14, 21, 27)
ALPHAS = (0.25, 0.5, 1.0)
SOURCE_ANCHOR = "t2_only"
TARGET_SITE = "same_layer_reset_prefix_last_token_before_ACTION"
PRIMARY_ENDPOINT = "later_plan_agreement_LPA"
SPECIFICITY_CONTROLS = (
    "RANDOM_EQ_NORM",
    "NEXT_ACTION_PRESERVED_LATE_NULL",
    "UNRELATED_PLAN",
    "SHUFFLED_PLAN",
    "GENERIC_HISTORY",
)
TASK_SUCCESS_SPECIFICITY_CONTROLS = (
    "RANDOM_EQ_NORM",
    "NEXT_ACTION_PRESERVED_LATE_NULL",
    "UNRELATED_PLAN",
)
ACTIVE = "ACTIVE_PLAN_RESIDUAL"
NO_PATCH = "NO_PATCH"
REQUIRED_ARMS = (ACTIVE, NO_PATCH) + SPECIFICITY_CONTROLS
INTERVENTION_ARMS = (ACTIVE,) + SPECIFICITY_CONTROLS
ENGINEERING_EQUIV_ATOL = 1e-6
RAW_RESIDUAL_ZERO_ATOL = 1e-8


class T1PhaseContractError(RuntimeError):
    pass


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_json_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def self_sha256() -> str:
    return file_sha256(__file__)


def _require_sha(value: Any, label: str) -> str:
    s = str(value)
    if len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        raise T1PhaseContractError(f"{label} must be lowercase sha256")
    return s


def _require_number(value: Any, label: str, lo: float | None = None, hi: float | None = None) -> float:
    try:
        x = float(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise T1PhaseContractError(f"{label} must be numeric") from exc
    if not math.isfinite(x):
        raise T1PhaseContractError(f"{label} must be finite")
    if lo is not None and x < lo:
        raise T1PhaseContractError(f"{label} below {lo}")
    if hi is not None and x > hi:
        raise T1PhaseContractError(f"{label} above {hi}")
    return x


def _mean(xs: Sequence[float]) -> float:
    return float(sum(float(x) for x in xs) / len(xs)) if xs else 0.0


def grid_key(layer: int, alpha: float) -> str:
    return f"{int(layer)}:{float(alpha):g}"


def exact_one_sided_sign_p(positives: int, n: int) -> float:
    """P[X>=positives], X~Binomial(n,.5); zero/nonpositive pairs are failures."""
    positives, n = int(positives), int(n)
    if n <= 0 or positives < 0 or positives > n:
        raise T1PhaseContractError("invalid sign-test count")
    return float(sum(math.comb(n, k) for k in range(positives, n + 1)) / (2 ** n))


def holm_two(p_by_name: Mapping[str, float]) -> dict[str, Any]:
    if set(p_by_name) != {"d_no_patch", "d_specificity"}:
        raise T1PhaseContractError("Holm family must be exactly d_no_patch,d_specificity")
    rows = sorted(((float(p), str(name)) for name, p in p_by_name.items()), key=lambda x: (x[0], x[1]))
    first_p, first_name = rows[0]
    second_p, second_name = rows[1]
    first_pass = first_p <= 0.025
    second_pass = first_pass and second_p <= 0.05
    decisions = {first_name: bool(first_pass), second_name: bool(second_pass)}
    return {
        "fwer": 0.05,
        "ordered": [[first_name, first_p, 0.025], [second_name, second_p, 0.05]],
        "decisions": decisions,
        "both_pass": all(decisions.values()),
    }


def _atomic_write_new(path: str | Path, obj: Any) -> str:
    """Create exactly once via hard-link commit; never overwrite an existing target."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise T1PhaseContractError(f"refuse existing output: {target}")
    payload = json.dumps(obj, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    tmp = target.with_name(f".{target.name}.tmp.{os.getpid()}.{hashlib.sha256(payload).hexdigest()[:12]}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, target)
        except FileExistsError as exc:
            raise T1PhaseContractError(f"refuse existing output: {target}") from exc
        dfd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return file_sha256(target)


def _expected_grid_keys() -> set[str]:
    return {grid_key(l, a) for l in LAYERS for a in ALPHAS}


def _family_map(families: Sequence[Mapping[str, Any]], expected: Sequence[int]) -> dict[int, Mapping[str, Any]]:
    out: dict[int, Mapping[str, Any]] = {}
    for row in families:
        idx = int(row.get("index", -1))
        if idx in out:
            raise T1PhaseContractError(f"duplicate family index {idx}")
        out[idx] = row
    if set(out) != set(expected):
        raise T1PhaseContractError(f"family index set mismatch expected={list(expected)} got={sorted(out)}")
    return out


def _validate_base_family(row: Mapping[str, Any]) -> None:
    if not isinstance(row.get("qualified"), bool):
        raise T1PhaseContractError("qualified must be bool")
    if not row["qualified"]:
        return
    for key in (
        "reset_prefix_sha256",
        "reset_world_state_sha256",
        "reset_serialization_sha256",
        "task_instruction_sha256",
        "reset_observation_sha256",
        "admissible_actions_sha256",
        "reference_world_state_sequence_sha256",
    ):
        _require_sha(row.get(key), key)
    if int(row.get("reference_remaining_action_count", 0)) < 2:
        raise T1PhaseContractError("reference must have >=2 remaining actions")
    if row.get("primary_endpoint") != PRIMARY_ENDPOINT or row.get("lpa_excludes_first_action") is not True:
        raise T1PhaseContractError("primary LPA/first-action exclusion contract mismatch")
    if row.get("world_state_match_enforced") is not True:
        raise T1PhaseContractError("LPA world-state matching must be enforced")
    sent = row.get("engineering_sentinels", {})
    if _require_number(sent.get("zero_add_no_patch_maxabs"), "zero_add_no_patch_maxabs", 0.0) > ENGINEERING_EQUIV_ATOL:
        raise T1PhaseContractError("ZERO_ADD sentinel exceeds frozen tolerance")
    if _require_number(sent.get("self_replace_no_patch_maxabs"), "self_replace_no_patch_maxabs", 0.0) > ENGINEERING_EQUIV_ATOL:
        raise T1PhaseContractError("SELF_REPLACE sentinel exceeds frozen tolerance")


def _validate_arm(row: Mapping[str, Any], fam: Mapping[str, Any], arm: str) -> dict[str, float]:
    for key in (
        "reset_prefix_sha256",
        "reset_world_state_sha256",
        "reset_serialization_sha256",
        "task_instruction_sha256",
        "reset_observation_sha256",
        "admissible_actions_sha256",
    ):
        if row.get(key) != fam.get(key):
            raise T1PhaseContractError(f"{arm} reset provenance mismatch: {key}")
    if row.get("world_state_match_enforced") is not True or row.get("lpa_excludes_first_action") is not True:
        raise T1PhaseContractError(f"{arm} endpoint contract mismatch")
    expected_hooks = 1 if arm in INTERVENTION_ARMS else 0
    if int(row.get("hook_count", -1)) != expected_hooks:
        raise T1PhaseContractError(f"{arm} hook_count expected {expected_hooks}")
    if arm in INTERVENTION_ARMS and row.get("vector_norm_guard_passed") is not True:
        raise T1PhaseContractError(f"{arm} vector norm guard missing/fail")
    return {
        "lpa": _require_number(row.get("lpa"), f"{arm}.lpa", 0.0, 1.0),
        "task_success": _require_number(row.get("task_success"), f"{arm}.task_success", 0.0, 1.0),
        "valid_action_rate": _require_number(row.get("valid_action_rate"), f"{arm}.valid_action_rate", 0.0, 1.0),
    }


def _validate_grid_family(metric: Mapping[str, Any], fam: Mapping[str, Any]) -> tuple[dict[str, dict[str, float]], float]:
    if not fam["qualified"]:
        raise T1PhaseContractError("unqualified family must not have grid metrics")
    arms_raw = metric.get("arms")
    if not isinstance(arms_raw, dict) or set(arms_raw) != set(REQUIRED_ARMS):
        raise T1PhaseContractError("qualified grid metric arm set must equal frozen REQUIRED_ARMS")
    arms = {arm: _validate_arm(arms_raw[arm], fam, arm) for arm in REQUIRED_ARMS}
    raw_norm = _require_number(metric.get("active_raw_residual_l2"), "active_raw_residual_l2", 0.0)
    return arms, raw_norm


def _selection_margin(arms: Mapping[str, Mapping[str, float]], raw_norm: float) -> float:
    d = float(arms[ACTIVE]["lpa"] - max(arms[c]["lpa"] for c in SPECIFICITY_CONTROLS))
    return min(d, 0.0) if raw_norm <= RAW_RESIDUAL_ZERO_ATOL else d


def _validate_provenance(payload: Mapping[str, Any]) -> None:
    if payload.get("t1_prereg_sha256") != T1_PREREG_SHA256:
        raise T1PhaseContractError("T1 prereg hash drift")
    if payload.get("gap_matrix_sha256") != GAP_MATRIX_SHA256:
        raise T1PhaseContractError("gap matrix hash drift")
    if payload.get("v2_1_contract_sha256") != V2_1_CONTRACT_SHA256:
        raise T1PhaseContractError("V2.1 contract hash drift")
    if payload.get("session_runtime_sha256") != SESSION_RUNTIME_SHA256:
        raise T1PhaseContractError("session runtime hash drift")
    if payload.get("phase_runner_sha256") != self_sha256():
        raise T1PhaseContractError("phase runner self hash drift")
    if payload.get("source_anchor") != SOURCE_ANCHOR or payload.get("target_site") != TARGET_SITE:
        raise T1PhaseContractError("anchor/site drift")


def select_development(payload: Mapping[str, Any], seal_path: str | Path) -> dict[str, Any]:
    if payload.get("phase") != "T1_DEVELOPMENT" or payload.get("sanity_status") != SANITY_REQUIRED:
        raise T1PhaseContractError("development phase/sanity gate mismatch")
    _validate_provenance(payload)
    fams = _family_map(payload.get("families", []), DEVELOPMENT_INDICES)
    for fam in fams.values():
        _validate_base_family(fam)
    qualified = [i for i in DEVELOPMENT_INDICES if fams[i]["qualified"]]
    if len(qualified) < 16:
        return {"status": "INCONCLUSIVE_T1_DEVELOPMENT_EXPRESSIVITY", "qualified_count": len(qualified), "denominator": 32}

    grids = payload.get("grid_results")
    if not isinstance(grids, dict) or set(grids) != _expected_grid_keys():
        raise T1PhaseContractError("global grid must be exactly layers[7,14,21,27] x alpha[.25,.5,1]")
    vector_map = payload.get("vector_sha256_by_family_layer")
    if not isinstance(vector_map, dict):
        raise T1PhaseContractError("vector_sha256_by_family_layer missing")
    aggregates: dict[str, Any] = {}
    for layer in LAYERS:
        for alpha in ALPHAS:
            key = grid_key(layer, alpha)
            rows = grids[key]
            if not isinstance(rows, dict) or {int(x) for x in rows} != set(qualified):
                raise T1PhaseContractError(f"grid {key} must contain exactly all qualified development families")
            margins: list[float] = []
            active_success: list[float] = []
            for idx in qualified:
                arms, raw_norm = _validate_grid_family(rows[str(idx)], fams[idx])
                margins.append(_selection_margin(arms, raw_norm))
                active_success.append(arms[ACTIVE]["task_success"])
                family_vectors = vector_map.get(str(idx), {})
                _require_sha(family_vectors.get(str(layer)), f"vector[{idx}][{layer}]")
            aggregates[key] = {
                "layer": layer,
                "alpha": alpha,
                "qualified_count": len(qualified),
                "median_specificity_margin": float(statistics.median(margins)),
                "active_task_success_rate": _mean(active_success),
            }

    ordered = sorted(
        aggregates.values(),
        key=lambda r: (-r["median_specificity_margin"], -r["active_task_success_rate"], r["alpha"], r["layer"]),
    )
    selected = ordered[0]
    selected_layer = int(selected["layer"])
    selected_vectors = {str(i): _require_sha(vector_map[str(i)][str(selected_layer)], f"selected_vector[{i}]") for i in qualified}
    dev_payload_sha = canonical_json_sha256(payload)
    seal = {
        "kind": "PLANCARRY_REPLAY_RESIDUAL_T1_DEVELOPMENT_SELECTION_V1",
        "status": "FROZEN_T1_DEVELOPMENT_SELECTION",
        "t1_prereg_sha256": T1_PREREG_SHA256,
        "gap_matrix_sha256": GAP_MATRIX_SHA256,
        "v2_1_contract_sha256": V2_1_CONTRACT_SHA256,
        "session_runtime_sha256": SESSION_RUNTIME_SHA256,
        "phase_runner_sha256": self_sha256(),
        "development_indices": list(DEVELOPMENT_INDICES),
        "qualified_indices": qualified,
        "qualified_count": len(qualified),
        "development_payload_sha256": dev_payload_sha,
        "source_anchor": SOURCE_ANCHOR,
        "target_site": TARGET_SITE,
        "selection_rule": "max median specificity margin; tie ACTIVE TaskSuccess, lower alpha, earlier layer",
        "selected_layer": selected_layer,
        "selected_alpha": float(selected["alpha"]),
        "selected_vector_sha256_by_family": selected_vectors,
        "selected_vector_map_sha256": canonical_json_sha256(selected_vectors),
        "all_grid_aggregates": aggregates,
        "all_grid_aggregates_sha256": canonical_json_sha256(aggregates),
        "confirmation_accessed": False,
        "scientific_result": "NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY",
    }
    seal_sha = _atomic_write_new(seal_path, seal)
    out = dict(seal)
    out["seal_file_sha256"] = seal_sha
    return out


def _load_and_validate_seal(seal_path: str | Path, expected_sha256: str) -> dict[str, Any]:
    expected = _require_sha(expected_sha256, "expected seal sha")
    p = Path(seal_path)
    actual = file_sha256(p)
    if actual != expected:
        raise T1PhaseContractError("development seal sha mismatch")
    seal = json.loads(p.read_text())
    validate_t1_phase_artifact(seal)
    if seal.get("kind") != "PLANCARRY_REPLAY_RESIDUAL_T1_DEVELOPMENT_SELECTION_V1":
        raise T1PhaseContractError("wrong development seal kind")
    return seal


def _confirmation_family_values(fam: Mapping[str, Any]) -> dict[str, Any]:
    _validate_base_family(fam)
    if not fam["qualified"]:
        # Frozen all20 rule: unqualified stays in every denominator and cannot be a sign success.
        return {
            "qualified": False,
            "d_no_patch": 0.0,
            "d_specificity": 0.0,
            "active_task_success": 0.0,
            "no_patch_task_success": 0.0,
            "specificity_task_success": {c: 0.0 for c in TASK_SUCCESS_SPECIFICITY_CONTROLS},
            "active_valid_action_rate": 0.0,
            "no_patch_valid_action_rate": 0.0,
        }
    arms_raw = fam.get("arms")
    if not isinstance(arms_raw, dict) or set(arms_raw) != set(REQUIRED_ARMS):
        raise T1PhaseContractError("qualified confirmation family arm set must equal frozen REQUIRED_ARMS")
    arms = {arm: _validate_arm(arms_raw[arm], fam, arm) for arm in REQUIRED_ARMS}
    raw_norm = _require_number(fam.get("active_raw_residual_l2"), "active_raw_residual_l2", 0.0)
    d_no = float(arms[ACTIVE]["lpa"] - arms[NO_PATCH]["lpa"])
    d_sp = float(arms[ACTIVE]["lpa"] - max(arms[c]["lpa"] for c in SPECIFICITY_CONTROLS))
    if raw_norm <= RAW_RESIDUAL_ZERO_ATOL:
        d_no, d_sp = min(d_no, 0.0), min(d_sp, 0.0)
    return {
        "qualified": True,
        "d_no_patch": d_no,
        "d_specificity": d_sp,
        "active_task_success": arms[ACTIVE]["task_success"],
        "no_patch_task_success": arms[NO_PATCH]["task_success"],
        "specificity_task_success": {c: arms[c]["task_success"] for c in TASK_SUCCESS_SPECIFICITY_CONTROLS},
        "active_valid_action_rate": arms[ACTIVE]["valid_action_rate"],
        "no_patch_valid_action_rate": arms[NO_PATCH]["valid_action_rate"],
    }


def evaluate_confirmation(payload: Mapping[str, Any], seal: Mapping[str, Any], seal_sha256: str) -> dict[str, Any]:
    if payload.get("phase") != "T1_CONFIRMATION" or payload.get("sanity_status") != SANITY_REQUIRED:
        raise T1PhaseContractError("confirmation phase/sanity gate mismatch")
    _validate_provenance(payload)
    if int(payload.get("selected_layer", -1)) != int(seal["selected_layer"]):
        raise T1PhaseContractError("confirmation layer differs from frozen selection")
    if float(payload.get("selected_alpha", -1)) != float(seal["selected_alpha"]):
        raise T1PhaseContractError("confirmation alpha differs from frozen selection")
    if payload.get("development_seal_sha256") != seal_sha256:
        raise T1PhaseContractError("confirmation payload does not bind exact development seal")

    fams = _family_map(payload.get("families", []), CONFIRMATION_INDICES)
    # Validate qualification/provenance for all20 before even an inconclusive gate return.
    for fam in fams.values():
        _validate_base_family(fam)
    qualified_count = sum(bool(fams[i].get("qualified")) for i in CONFIRMATION_INDICES)
    if qualified_count < 16:
        return {
            "kind": "PLANCARRY_REPLAY_RESIDUAL_T1_CONFIRMATION_V1",
            "status": "INCONCLUSIVE_T1_CONFIRMATION_EXPRESSIVITY",
            "t1_prereg_sha256": T1_PREREG_SHA256,
            "gap_matrix_sha256": GAP_MATRIX_SHA256,
            "v2_1_contract_sha256": V2_1_CONTRACT_SHA256,
            "session_runtime_sha256": SESSION_RUNTIME_SHA256,
            "phase_runner_sha256": self_sha256(),
            "denominator": 20,
            "qualified_count": qualified_count,
            "development_seal_sha256": seal_sha256,
            "selected_layer": int(seal["selected_layer"]),
            "selected_alpha": float(seal["selected_alpha"]),
            "primary_endpoint": PRIMARY_ENDPOINT,
            "first_action_excluded": True,
        }

    per_family: list[dict[str, Any]] = []
    for idx in CONFIRMATION_INDICES:
        vals = _confirmation_family_values(fams[idx])
        per_family.append({"index": idx, **vals})
    if len(per_family) != 20:
        raise T1PhaseContractError("all20 denominator violated")

    d_no = [r["d_no_patch"] for r in per_family]
    d_sp = [r["d_specificity"] for r in per_family]
    pos_no, pos_sp = sum(x > 0.0 for x in d_no), sum(x > 0.0 for x in d_sp)
    pvals = {"d_no_patch": exact_one_sided_sign_p(pos_no, 20), "d_specificity": exact_one_sided_sign_p(pos_sp, 20)}
    holm = holm_two(pvals)

    active_ts = _mean([r["active_task_success"] for r in per_family])
    no_patch_ts = _mean([r["no_patch_task_success"] for r in per_family])
    ctrl_ts = {c: _mean([r["specificity_task_success"][c] for r in per_family]) for c in TASK_SUCCESS_SPECIFICITY_CONTROLS}
    active_valid = _mean([r["active_valid_action_rate"] for r in per_family])
    no_patch_valid = _mean([r["no_patch_valid_action_rate"] for r in per_family])
    guards = {
        "mean_d_no_patch_ge_0_15": _mean(d_no) >= 0.15,
        "mean_d_specificity_ge_0_10": _mean(d_sp) >= 0.10,
        "positive_d_no_patch_ge_70pct_all20": pos_no >= 14,
        "positive_d_specificity_ge_65pct_all20": pos_sp >= 13,
        "active_task_success_ge_0_50": active_ts >= 0.50,
        "active_minus_no_patch_task_success_ge_0_15": (active_ts - no_patch_ts) >= 0.15,
        "active_minus_max_three_specificity_task_success_ge_0_10": (active_ts - max(ctrl_ts.values())) >= 0.10,
        "active_valid_not_more_than_0_10_below_no_patch": active_valid >= (no_patch_valid - 0.10),
    }
    status = SUPPORTED_PRIMARY if holm["both_pass"] and all(guards.values()) else "REFUTED_REPLAY_RESIDUAL_T1"
    return {
        "kind": "PLANCARRY_REPLAY_RESIDUAL_T1_CONFIRMATION_V1",
        "status": status,
        "t1_prereg_sha256": T1_PREREG_SHA256,
        "gap_matrix_sha256": GAP_MATRIX_SHA256,
        "v2_1_contract_sha256": V2_1_CONTRACT_SHA256,
        "session_runtime_sha256": SESSION_RUNTIME_SHA256,
        "phase_runner_sha256": self_sha256(),
        "development_seal_sha256": seal_sha256,
        "selected_layer": int(seal["selected_layer"]),
        "selected_alpha": float(seal["selected_alpha"]),
        "denominator": 20,
        "qualified_count": qualified_count,
        "positive_counts": {"d_no_patch": pos_no, "d_specificity": pos_sp},
        "p_values": pvals,
        "holm": holm,
        "means": {"d_no_patch": _mean(d_no), "d_specificity": _mean(d_sp)},
        "task_success_rates": {"ACTIVE": active_ts, "NO_PATCH": no_patch_ts, **ctrl_ts},
        "valid_action_rates": {"ACTIVE": active_valid, "NO_PATCH": no_patch_valid},
        "effect_guards": guards,
        "all_effect_guards_pass": all(guards.values()),
        "per_family": per_family,
        "primary_endpoint": PRIMARY_ENDPOINT,
        "first_action_excluded": True,
    }


def run_confirmation_file(confirmation_path: str | Path, seal_path: str | Path, expected_seal_sha256: str, output_path: str | Path) -> dict[str, Any]:
    # IMPORTANT phase isolation: seal validation and output refusal happen before confirmation bytes are read.
    seal = _load_and_validate_seal(seal_path, expected_seal_sha256)
    if Path(output_path).exists():
        raise T1PhaseContractError(f"refuse existing output: {output_path}")
    payload = json.loads(Path(confirmation_path).read_text())
    result = evaluate_confirmation(payload, seal, expected_seal_sha256)
    result["confirmation_payload_sha256"] = canonical_json_sha256(payload)
    out_sha = _atomic_write_new(output_path, result)
    result["output_file_sha256"] = out_sha
    return result


def assert_t1r_unlocked(primary_status: str) -> None:
    if str(primary_status) != SUPPORTED_PRIMARY:
        raise T1PhaseContractError("T1R reserve is inaccessible until primary status is SUPPORTED_REPLAY_RESIDUAL_T1")


def validate_t1_phase_artifact(obj: Mapping[str, Any]) -> bool:
    kind = obj.get("kind")
    if kind == "PLANCARRY_REPLAY_RESIDUAL_T1_DEVELOPMENT_SELECTION_V1":
        if obj.get("status") != "FROZEN_T1_DEVELOPMENT_SELECTION":
            raise T1PhaseContractError("development artifact status drift")
        if obj.get("scientific_result") != "NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY":
            raise T1PhaseContractError("development artifact scientific-result drift")
        if obj.get("t1_prereg_sha256") != T1_PREREG_SHA256 or obj.get("gap_matrix_sha256") != GAP_MATRIX_SHA256 or obj.get("v2_1_contract_sha256") != V2_1_CONTRACT_SHA256:
            raise T1PhaseContractError("development artifact provenance drift")
        if obj.get("session_runtime_sha256") != SESSION_RUNTIME_SHA256 or obj.get("phase_runner_sha256") != self_sha256():
            raise T1PhaseContractError("development runtime/code drift")
        if tuple(obj.get("development_indices", [])) != DEVELOPMENT_INDICES:
            raise T1PhaseContractError("development population drift")
        qualified = obj.get("qualified_indices")
        if not isinstance(qualified, list) or any(not isinstance(i, int) for i in qualified) or len(set(qualified)) != len(qualified):
            raise T1PhaseContractError("development qualified_indices malformed")
        if any(i not in DEVELOPMENT_INDICES for i in qualified) or qualified != sorted(qualified):
            raise T1PhaseContractError("development qualified_indices drift")
        if int(obj.get("qualified_count", -1)) != len(qualified) or len(qualified) < 16:
            raise T1PhaseContractError("development qualified_count drift")
        selected_layer = int(obj.get("selected_layer", -1))
        selected_alpha = float(obj.get("selected_alpha", -1))
        if selected_layer not in LAYERS or selected_alpha not in ALPHAS:
            raise T1PhaseContractError("selected operating point outside frozen grid")
        if obj.get("source_anchor") != SOURCE_ANCHOR or obj.get("target_site") != TARGET_SITE:
            raise T1PhaseContractError("development anchor/site drift")
        if obj.get("selection_rule") != "max median specificity margin; tie ACTIVE TaskSuccess, lower alpha, earlier layer":
            raise T1PhaseContractError("development selection rule drift")
        if obj.get("confirmation_accessed") is not False:
            raise T1PhaseContractError("development seal claims confirmation access")
        _require_sha(obj.get("development_payload_sha256"), "development payload sha")
        vectors = obj.get("selected_vector_sha256_by_family")
        if not isinstance(vectors, dict) or set(vectors) != {str(i) for i in qualified}:
            raise T1PhaseContractError("selected vector family map drift")
        for idx in qualified:
            _require_sha(vectors[str(idx)], f"selected vector[{idx}]")
        expected_vector_map_sha = canonical_json_sha256(vectors)
        if obj.get("selected_vector_map_sha256") != expected_vector_map_sha:
            raise T1PhaseContractError("selected vector map sha drift")
        aggregates = obj.get("all_grid_aggregates")
        if not isinstance(aggregates, dict) or set(aggregates) != _expected_grid_keys():
            raise T1PhaseContractError("development aggregate grid drift")
        for layer in LAYERS:
            for alpha in ALPHAS:
                key = grid_key(layer, alpha)
                row = aggregates[key]
                if not isinstance(row, dict) or int(row.get("layer", -1)) != layer or float(row.get("alpha", -1)) != alpha:
                    raise T1PhaseContractError(f"development aggregate operating-point drift:{key}")
                if int(row.get("qualified_count", -1)) != len(qualified):
                    raise T1PhaseContractError(f"development aggregate qualified_count drift:{key}")
                _require_number(row.get("median_specificity_margin"), f"aggregate[{key}].median_specificity_margin")
                _require_number(row.get("active_task_success_rate"), f"aggregate[{key}].active_task_success_rate", 0.0, 1.0)
        if obj.get("all_grid_aggregates_sha256") != canonical_json_sha256(aggregates):
            raise T1PhaseContractError("development aggregate sha drift")
        ordered = sorted(
            aggregates.values(),
            key=lambda r: (-float(r["median_specificity_margin"]), -float(r["active_task_success_rate"]), float(r["alpha"]), int(r["layer"])),
        )
        best = ordered[0]
        if selected_layer != int(best["layer"]) or selected_alpha != float(best["alpha"]):
            raise T1PhaseContractError("selected operating point inconsistent with frozen tie-break")
        return True
    if kind == "PLANCARRY_REPLAY_RESIDUAL_T1_CONFIRMATION_V1":
        if int(obj.get("denominator", -1)) != 20:
            raise T1PhaseContractError("confirmation denominator drift")
        status = obj.get("status")
        if status not in {SUPPORTED_PRIMARY, "REFUTED_REPLAY_RESIDUAL_T1", "INCONCLUSIVE_T1_CONFIRMATION_EXPRESSIVITY"}:
            raise T1PhaseContractError("unknown confirmation status")
        if obj.get("t1_prereg_sha256") != T1_PREREG_SHA256 or obj.get("gap_matrix_sha256") != GAP_MATRIX_SHA256 or obj.get("v2_1_contract_sha256") != V2_1_CONTRACT_SHA256:
            raise T1PhaseContractError("confirmation protocol provenance drift")
        if obj.get("session_runtime_sha256") != SESSION_RUNTIME_SHA256 or obj.get("phase_runner_sha256") != self_sha256():
            raise T1PhaseContractError("confirmation runtime/code drift")
        if obj.get("primary_endpoint") != PRIMARY_ENDPOINT or obj.get("first_action_excluded") is not True:
            raise T1PhaseContractError("confirmation endpoint drift")
        _require_sha(obj.get("development_seal_sha256"), "development seal sha")
        if int(obj.get("selected_layer", -1)) not in LAYERS or float(obj.get("selected_alpha", -1)) not in ALPHAS:
            raise T1PhaseContractError("confirmation operating point outside frozen grid")
        qualified_count = int(obj.get("qualified_count", -1))
        if not 0 <= qualified_count <= 20:
            raise T1PhaseContractError("confirmation qualified_count malformed")
        if status == "INCONCLUSIVE_T1_CONFIRMATION_EXPRESSIVITY":
            if qualified_count >= 16:
                raise T1PhaseContractError("inconclusive confirmation contradicts >=16 qualification gate")
            forbidden_terminal = {"positive_counts", "p_values", "holm", "means", "effect_guards", "per_family"}
            if forbidden_terminal.intersection(obj):
                raise T1PhaseContractError("inconclusive artifact contains post-gate terminal statistics")
            return True
        if qualified_count < 16:
            raise T1PhaseContractError("terminal confirmation contradicts <16 qualification gate")
        rows = obj.get("per_family")
        if not isinstance(rows, list) or len(rows) != 20 or [r.get("index") for r in rows if isinstance(r, dict)] != list(CONFIRMATION_INDICES):
            raise T1PhaseContractError("confirmation per_family must be exact ordered all20")
        d_no=[]; d_sp=[]; active_ts=[]; nopatch_ts=[]; active_valid=[]; nopatch_valid=[]
        ctrl_ts={c:[] for c in TASK_SUCCESS_SPECIFICITY_CONTROLS}
        observed_q=0
        for expected_idx,row in zip(CONFIRMATION_INDICES,rows):
            if not isinstance(row, dict) or int(row.get("index",-1)) != expected_idx:
                raise T1PhaseContractError("confirmation per_family index drift")
            q=row.get("qualified")
            if not isinstance(q,bool):
                raise T1PhaseContractError("confirmation per_family qualified flag malformed")
            observed_q += int(q)
            dn=_require_number(row.get("d_no_patch"), f"family[{expected_idx}].d_no_patch")
            ds=_require_number(row.get("d_specificity"), f"family[{expected_idx}].d_specificity")
            ats=_require_number(row.get("active_task_success"), f"family[{expected_idx}].active_task_success",0.0,1.0)
            nts=_require_number(row.get("no_patch_task_success"), f"family[{expected_idx}].no_patch_task_success",0.0,1.0)
            av=_require_number(row.get("active_valid_action_rate"), f"family[{expected_idx}].active_valid_action_rate",0.0,1.0)
            nv=_require_number(row.get("no_patch_valid_action_rate"), f"family[{expected_idx}].no_patch_valid_action_rate",0.0,1.0)
            ct=row.get("specificity_task_success")
            if not isinstance(ct,dict) or set(ct)!=set(TASK_SUCCESS_SPECIFICITY_CONTROLS):
                raise T1PhaseContractError("confirmation per_family task-success control set drift")
            if not q and any(abs(float(x)) > 0.0 for x in (dn,ds,ats,nts,av,nv,*[ct[c] for c in TASK_SUCCESS_SPECIFICITY_CONTROLS])):
                raise T1PhaseContractError("unqualified confirmation family must contribute frozen zero values")
            d_no.append(dn); d_sp.append(ds); active_ts.append(ats); nopatch_ts.append(nts); active_valid.append(av); nopatch_valid.append(nv)
            for c in TASK_SUCCESS_SPECIFICITY_CONTROLS:
                ctrl_ts[c].append(_require_number(ct[c], f"family[{expected_idx}].specificity_task_success[{c}]",0.0,1.0))
        if observed_q != qualified_count:
            raise T1PhaseContractError("confirmation qualified_count inconsistent with all20 rows")
        pos_no=sum(x>0.0 for x in d_no); pos_sp=sum(x>0.0 for x in d_sp)
        expected_pos={"d_no_patch":pos_no,"d_specificity":pos_sp}
        if obj.get("positive_counts") != expected_pos:
            raise T1PhaseContractError("confirmation positive-count drift")
        expected_p={"d_no_patch":exact_one_sided_sign_p(pos_no,20),"d_specificity":exact_one_sided_sign_p(pos_sp,20)}
        if obj.get("p_values") != expected_p:
            raise T1PhaseContractError("confirmation sign-test p-value drift")
        expected_holm=holm_two(expected_p)
        if obj.get("holm") != expected_holm:
            raise T1PhaseContractError("confirmation Holm drift")
        expected_means={"d_no_patch":_mean(d_no),"d_specificity":_mean(d_sp)}
        if obj.get("means") != expected_means:
            raise T1PhaseContractError("confirmation mean-effect drift")
        ats=_mean(active_ts); nts=_mean(nopatch_ts); cmeans={c:_mean(ctrl_ts[c]) for c in TASK_SUCCESS_SPECIFICITY_CONTROLS}
        expected_ts={"ACTIVE":ats,"NO_PATCH":nts,**cmeans}
        if obj.get("task_success_rates") != expected_ts:
            raise T1PhaseContractError("confirmation task-success aggregate drift")
        av=_mean(active_valid); nv=_mean(nopatch_valid)
        if obj.get("valid_action_rates") != {"ACTIVE":av,"NO_PATCH":nv}:
            raise T1PhaseContractError("confirmation valid-action aggregate drift")
        expected_guards={
            "mean_d_no_patch_ge_0_15": expected_means["d_no_patch"] >= 0.15,
            "mean_d_specificity_ge_0_10": expected_means["d_specificity"] >= 0.10,
            "positive_d_no_patch_ge_70pct_all20": pos_no >= 14,
            "positive_d_specificity_ge_65pct_all20": pos_sp >= 13,
            "active_task_success_ge_0_50": ats >= 0.50,
            "active_minus_no_patch_task_success_ge_0_15": (ats-nts) >= 0.15,
            "active_minus_max_three_specificity_task_success_ge_0_10": (ats-max(cmeans.values())) >= 0.10,
            "active_valid_not_more_than_0_10_below_no_patch": av >= (nv-0.10),
        }
        if obj.get("effect_guards") != expected_guards or obj.get("all_effect_guards_pass") is not all(expected_guards.values()):
            raise T1PhaseContractError("confirmation effect-guard drift")
        expected_status=SUPPORTED_PRIMARY if expected_holm["both_pass"] and all(expected_guards.values()) else "REFUTED_REPLAY_RESIDUAL_T1"
        if status != expected_status:
            raise T1PhaseContractError("confirmation final status inconsistent with frozen decision rule")
        return True
    raise T1PhaseContractError("unknown T1 phase artifact kind")

def _main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("development")
    d.add_argument("--input", required=True); d.add_argument("--seal", required=True)
    c = sub.add_parser("confirmation")
    c.add_argument("--input", required=True); c.add_argument("--seal", required=True); c.add_argument("--seal-sha256", required=True); c.add_argument("--output", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--artifact", required=True)
    args = ap.parse_args()
    if args.cmd == "development":
        payload = json.loads(Path(args.input).read_text())
        print(json.dumps(select_development(payload, args.seal), sort_keys=True))
    elif args.cmd == "confirmation":
        print(json.dumps(run_confirmation_file(args.input, args.seal, args.seal_sha256, args.output), sort_keys=True))
    else:
        print(json.dumps({"valid": validate_t1_phase_artifact(json.loads(Path(args.artifact).read_text()))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
