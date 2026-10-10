#!/usr/bin/env python3
"""Bounded G0 source-selection provenance reconciliation for PlanCarry.

Read-only inspection of four historical PRE-SCIENCE selection manifests.
NO historical global "unused" certificate is created from model_calls=0:
that declaration is scoped strictly to each record's own selection operation.
No TRAIN game is opened and no model execution is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PRE_SCIENCE_FILES = (
    "results/design/plancarry_replayresidual_phi4mini_crossmodel_manifest_v2_family_unexposed_a3_20260821.json",
    "results/design/plancarry_localcontinuation_v2_fresh_population_v1_20260824.json",
    "results/design/plancarry_action_matched_future_plan_population_v1_20260825.json",
    "results/design/plancarry_replayresidual_localcontinuation_fresh_population_v1_20260823.json",
)
PRIOR_AUDIT = "research/BIND_G0_HISTORICAL_FAMILY_EXPOSURE_790_AUDIT_20261010.json"
SCHEMA = "plancarry.bind.g0.multi-manifest-scoped-zero-call-trace.v1"


def path_family(path: str) -> str:
    if not isinstance(path, str):
        raise ValueError("Expected a game path string")
    path = path.removeprefix("json_2.1.1/")
    bits = path.split("/")
    if len(bits) != 4 or bits[0] != "train" or not bits[1].startswith("pick_and_place_simple-") or not bits[2].startswith("trial_") or bits[3] != "game.tw-pddl":
        raise ValueError("Unrecognized canonical original TRAIN path")
    return bits[1]


def manifest_selected_families(data: dict, kind: int) -> set[str]:
    if kind == 0:
        phases = ("development", "confirmation")
        if not all(isinstance(data.get(p), list) for p in phases):
            raise ValueError("Missing crossmodel selected phase lists")
        entries = data["development"] + data["confirmation"]
        if not all(isinstance(x, dict) and path_family(x["game_path"]) == x["family"] for x in entries):
            raise ValueError("Inconsistent crossmodel family/path")
        return {x["family"] for x in entries}
    if not isinstance(data.get("selected"), list):
        raise ValueError("Missing selected game list")
    entries = data["selected"]
    if data.get("selected_n") != len(entries):
        raise ValueError("Selected count fails closed")
    return {path_family(x["game_path"]) for x in entries}


def run(repo_root: Path) -> dict:
    prior_file = repo_root / PRIOR_AUDIT
    prior_bytes = prior_file.read_bytes()
    prior = json.loads(prior_bytes)
    if prior.get("scientific_gate") != "NOT_AUTHORIZED" or prior.get("historical_coverage") != "INCOMPLETE":
        raise ValueError("Prior audit is not a partial/unauthorized original input")
    families = prior["families_not_in_these_two_records"]
    counts = prior["candidate_game_count_by_family"]
    if len(families) != 34 or len(set(families)) != 34 or set(counts) != set(families):
        raise ValueError("Expected original bounded 34-family source candidate population")
    records = []
    union = set()
    for k, relpath in enumerate(PRE_SCIENCE_FILES):
        raw = (repo_root / relpath).read_bytes()
        data = json.loads(raw)
        # Zero model calls is scoped to this single frozen selection artifact.
        if data.get("model_calls") != 0 or data.get("environment_execution") != 0:
            raise ValueError("Cannot classify as selection-only if execution counters differ from 0")
        if not str(data.get("scientific_result","")).startswith("NOT_ASSESSED"):
            raise ValueError("Manifest scientific result must be unassessed")
        selected = manifest_selected_families(data, k)
        matches = set(families) & selected
        union.update(matches)
        records.append({
            "path": relpath,
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "selection_family_count": len(selected),
            "original_34_families_selected": len(matches),
            "selected_from_original_34": sorted(matches),
            "local_record_model_calls": 0,
            "local_record_environment_execution": 0,
            "interpretation": "SELECTION_ONLY_LOCAL_RECORD_NOT_GLOBAL_NONCONSUMPTION",
        })
    no_additional_reference = sorted(set(families)-union)
    return {
        "schema": SCHEMA,
        "scientific_gate": "NOT_AUTHORIZED",
        "status": "SCOPED_HISTORICAL_SELECTION_RECORDS_RECONCILED",
        "original_baseline": {"file": PRIOR_AUDIT,
                              "sha256": hashlib.sha256(prior_bytes).hexdigest(),
                              "candidate_families": len(families),
                              "candidate_game_paths": sum(counts.values())},
        "manifests": records,
        "union_selected_in_four_planning_records": len(union),
        "union_selected_games_in_original_candidate_families": sum(counts[x] for x in union),
        "no_selection_in_these_four_additional_records": len(no_additional_reference),
        "no_selection_family_names": no_additional_reference,
        "no_selection_game_count": sum(counts[x] for x in no_additional_reference),
        "no_selection_game_count_by_family": {x:counts[x] for x in no_additional_reference},
        "GLOBAL_SOURCE_NONCONSUMPTION_ATTESTED": False,
        "FULL_SIMULATOR_STATE_ATTESTED": False,
        "g0_decision": "BLOCKED_HISTORICAL_SOURCE_USAGE_AND_FULL_STATE_ATTESTATION",
        "limitations": [
            "Four documents are frozen pre-science population selections, NOT a ledger of every historical model prompt/response.",
            "Their declared model_calls=0 applies only to those record-producing operations, not all jobs or later execution.",
            "Selection mentions are NOT themselves model inference, and a missing mention is NOT proof of being unused.",
            "Historical 2026-Aug local job registry has no complete persisted runtime request/response transcripts.",
            "No TRAIN game, model, or external execution is used in this audit.",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    try:
        result = run(a.repo_root)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"scientific_gate":"NOT_AUTHORIZED","status":"INVALID_AUDIT", "error":str(exc)}))
        return 2
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
                      "science":result["scientific_gate"],
                      "records":len(result["manifests"]),
                      "planning_mentioned_families":result["union_selected_in_four_planning_records"],
                      "not_in_four_records":result["no_selection_family_names"],
                      "g0_decision":result["g0_decision"]},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
