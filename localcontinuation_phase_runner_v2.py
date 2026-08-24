#!/usr/bin/env python3
"""Development-only LocalContinuation-v2 selector/seal adapter.

Scientific/statistical primitives are inherited unchanged from the independently
reviewed v1 phase runner.  This module only rebinds immutable v2 authority and
replaces the two v1 semantic-control arm names with the prospectively frozen v2
arm set.  Confirmation/replication evaluation is intentionally absent.
"""
from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

import localcontinuation_controls_v2 as controls
import localcontinuation_phase_runner_v1 as v1

DESIGN_COMMIT = "d538f98f9860319a57a0f3db4952fdcd7b7f2ebd"
IMPLEMENTATION_COMMIT = "72d2b8883caafb724b0c6fb4f04e2881c0342fa1"
ENGINEERING_RESULT_ID = "d7d4b5cb-f6c2-4c83-9198-f7c84b4a882f"
FINAL_PREREG_SHA256 = "73aa5277b7fb20bcaebd5963e82cd62553b60b0a1bb975e8e223e0e4c1e8a716"
POPULATION_SHA256 = "59a4d79bceff17700411753828fe58b36826cc723557fd0b171a367c352d1b18"
EXECUTABLE_REVIEW_WORK_ITEM_ID = "76f2ee3c-bfb9-4e4f-adff-52cc007b38bf"
EXECUTABLE_REVIEW_SHA256 = "99a93039d8aa352f73acaf5435627a70ce90cf280386b1860c3dbb6c2a3911c3"

LAYERS = tuple(v1.LAYERS)
ALPHAS = tuple(v1.ALPHAS)
DEV = tuple(range(32))
ACTIVE = "ACTIVE_PLAN_RESIDUAL"
NO_PATCH = "NO_PATCH"
SPEC = tuple(controls.SPECIFICITY_MAX_CONTROLS)
ALL_DEVELOPMENT_ARMS = (ACTIVE, NO_PATCH, *SPEC)

LocalContinuationContractError = v1.LocalContinuationContractError
sha_json = v1.sha_json
file_sha = v1.file_sha
atomic_write_new = v1.atomic_write_new
mean = v1.mean
grid_key = v1.grid_key
matched_state_msa2 = v1.matched_state_msa2


def binding_payload() -> dict[str, Any]:
    return {
        "design_commit": DESIGN_COMMIT,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "engineering_result_id": ENGINEERING_RESULT_ID,
        "final_prereg_sha256": FINAL_PREREG_SHA256,
        "population_manifest_sha256": POPULATION_SHA256,
        "independent_executable_review_work_item_id": EXECUTABLE_REVIEW_WORK_ITEM_ID,
        "independent_executable_review_sha256": EXECUTABLE_REVIEW_SHA256,
    }


def _check_bindings(payload: Mapping[str, Any]) -> None:
    for key, value in binding_payload().items():
        if payload.get(key) != value:
            raise LocalContinuationContractError(f"v2 binding mismatch:{key}")


def _family_map(payload: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    out: dict[int, Mapping[str, Any]] = {}
    for row in payload.get("families", []):
        idx = int(row.get("index", -1))
        if idx in out:
            raise LocalContinuationContractError(f"duplicate v2 family:{idx}")
        out[idx] = row
    if set(out) != set(DEV):
        raise LocalContinuationContractError(f"v2 development family index mismatch:{sorted(out)}")
    return out


def _validate_arm_provenance(
    arm_name: str,
    arm: Mapping[str, Any],
    layer: int,
    alpha: float,
    active_sha256: str,
    reset_snapshot_sha256: str,
) -> None:
    # The v1 validator is arm-name agnostic except for the unchanged NO_PATCH
    # and VISIBLE_TEXT_PLAN plumbing semantics. Reusing it preserves the exact
    # hook/session/vector provenance contract.
    v1._validate_arm_provenance(arm_name, arm, layer, alpha, active_sha256, reset_snapshot_sha256)


def select_development(payload: Mapping[str, Any], seal_path: str | Path | None = None) -> dict[str, Any]:
    if payload.get("phase") != "LOCALCONTINUATION_DEVELOPMENT_V2":
        raise LocalContinuationContractError("wrong v2 development phase")
    for flag in ("confirmation_accessed", "reserve_accessed", "valid_seen_accessed", "valid_unseen_accessed"):
        if payload.get(flag) is not False:
            raise LocalContinuationContractError(f"v2 development split isolation violated:{flag}")
    _check_bindings(payload)
    execution_provenance = payload.get("execution_provenance")
    if not isinstance(execution_provenance, dict) or payload.get("execution_provenance_sha256") != sha_json(execution_provenance):
        raise LocalContinuationContractError("v2 execution provenance missing or corrupt")

    fams = _family_map(payload)
    qualified = [i for i in DEV if bool(fams[i].get("qualified"))]
    if len(qualified) < 16:
        if payload.get("grid_results") not in ({}, None):
            raise LocalContinuationContractError("v2 causal grid forbidden below development gate")
        return {
            "kind": "PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_V2",
            "status": "INCONCLUSIVE_LOCALCONTINUATION_V2_DEVELOPMENT_EXPRESSIVITY",
            "qualified_count": len(qualified),
            "denominator": 32,
            "confirmation_accessed": False,
            "reserve_accessed": False,
            "valid_seen_accessed": False,
            "valid_unseen_accessed": False,
            **binding_payload(),
        }

    grids = payload.get("grid_results", {})
    expected = {grid_key(layer, alpha) for layer in LAYERS for alpha in ALPHAS}
    if set(grids) != expected:
        raise LocalContinuationContractError("v2 grid key mismatch")

    aggregates: dict[str, dict[str, Any]] = {}
    for layer in LAYERS:
        for alpha in ALPHAS:
            key = grid_key(layer, alpha)
            rows = grids[key]
            if {int(x) for x in rows} != set(qualified):
                raise LocalContinuationContractError(f"v2 grid denominator mismatch:{key}")
            joint: list[float] = []
            active_msa: list[float] = []
            ref_margins: list[float] = []
            zero_raw = 0
            for idx in qualified:
                row = rows[str(idx)]
                arms = row.get("arms", {})
                if not all(name in arms for name in ALL_DEVELOPMENT_ARMS):
                    raise LocalContinuationContractError(f"v2 missing arms:{idx}:{key}")
                active_sha = str(row.get("active_residual_sha256", ""))
                reset_sha = str(row.get("reset_snapshot_sha256", ""))
                for arm_name in ALL_DEVELOPMENT_ARMS:
                    _validate_arm_provenance(arm_name, arms[arm_name], layer, alpha, active_sha, reset_sha)
                vals = {name: float(arms[name]["msa2"]) for name in ALL_DEVELOPMENT_ARMS}
                if any(value not in (0.0, 0.5, 1.0) for value in vals.values()):
                    raise LocalContinuationContractError("v2 MSA2 exact support violation")
                active_value = vals[ACTIVE]
                no_patch = vals[NO_PATCH]
                specificity = max(vals[name] for name in SPEC)
                margin = float(arms[ACTIVE].get("reference_action_margin_family"))
                if not math.isfinite(margin):
                    raise LocalContinuationContractError("v2 nonfinite ACTIVE margin")
                raw = float(row.get("active_raw_residual_l2", float("nan")))
                if not math.isfinite(raw) or raw < 0:
                    raise LocalContinuationContractError("v2 invalid active raw residual norm")
                value = min(active_value - no_patch, active_value - specificity)
                if raw <= 1e-8:
                    value = min(0.0, value)
                    zero_raw += 1
                joint.append(value)
                active_msa.append(active_value)
                ref_margins.append(margin)
            aggregates[key] = {
                "layer": int(layer),
                "alpha": float(alpha),
                "qualified_count": len(qualified),
                "zero_raw_residual_count": zero_raw,
                "median_joint_margin_ms": float(statistics.median(joint)),
                "median_active_msa2": float(statistics.median(active_msa)),
                "mean_active_msa2": mean(active_msa),
                "median_active_reference_action_margin_family": float(statistics.median(ref_margins)),
            }

    selected = sorted(
        aggregates.values(),
        key=lambda row: (
            -row["median_joint_margin_ms"],
            -row["median_active_msa2"],
            -row["median_active_reference_action_margin_family"],
            row["alpha"],
            row["layer"],
        ),
    )[0]
    if selected["median_joint_margin_ms"] < 0.05 or selected["mean_active_msa2"] < 0.50:
        return {
            "kind": "PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_V2",
            "status": "INCONCLUSIVE_LOCALCONTINUATION_V2_DEVELOPMENT_FUTILITY",
            "qualified_count": len(qualified),
            "denominator": 32,
            "selected_candidate": selected,
            "all_grid_aggregates": aggregates,
            "confirmation_accessed": False,
            "reserve_accessed": False,
            "valid_seen_accessed": False,
            "valid_unseen_accessed": False,
            **binding_payload(),
        }

    selected_key = grid_key(selected["layer"], selected["alpha"])
    selected_rows = grids[selected_key]
    selected_point_provenance: dict[str, Any] = {}
    for idx in qualified:
        row = selected_rows[str(idx)]
        selected_point_provenance[str(idx)] = {
            "active_raw_residual_l2": float(row["active_raw_residual_l2"]),
            "active_residual_sha256": str(row["active_residual_sha256"]),
            "reset_snapshot_sha256": str(row["reset_snapshot_sha256"]),
            "arms": {
                arm: {
                    key: row["arms"][arm].get(key)
                    for key in (
                        "arm_name",
                        "selected_layer",
                        "selected_alpha",
                        "active_residual_sha256",
                        "injected_vector_sha256",
                        "reset_snapshot_sha256",
                        "reset_prefix_sha256",
                        "hook_count",
                        "session_id_hash",
                    )
                }
                for arm in ALL_DEVELOPMENT_ARMS
            },
        }

    seal = {
        "kind": "PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_SELECTION_V2",
        "status": "FROZEN_LOCALCONTINUATION_V2_DEVELOPMENT_SELECTION",
        **binding_payload(),
        "development_indices": list(DEV),
        "qualified_indices": qualified,
        "qualified_count": len(qualified),
        "development_payload_sha256": sha_json(payload),
        "execution_provenance": execution_provenance,
        "execution_provenance_sha256": sha_json(execution_provenance),
        "selected_point_family_provenance_sha256": sha_json(selected_point_provenance),
        "selection_rule": "max median joint_margin_ms; tie median ACTIVE MSA2, median ACTIVE reference margin, lower alpha, earlier layer",
        "selected_layer": int(selected["layer"]),
        "selected_alpha": float(selected["alpha"]),
        "selected_grid_key": selected_key,
        "all_grid_aggregates": aggregates,
        "confirmation_accessed": False,
        "reserve_accessed": False,
        "valid_seen_accessed": False,
        "valid_unseen_accessed": False,
        "scientific_result": "NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY",
    }
    out = dict(seal)
    if seal_path is not None:
        out["seal_file_sha256"] = atomic_write_new(seal_path, seal)
    return out
