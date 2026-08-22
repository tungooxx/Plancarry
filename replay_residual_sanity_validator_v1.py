#!/usr/bin/env python3
"""Static/result validator for ReplayResidual sanity v1.1 executable."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

import replay_residual_sanity_protocol_v1 as p

RUNNER = Path(__file__).resolve().parent / "replay_residual_sanity_runner_v1.py"
CLIENT = Path(__file__).resolve().parent / "replay_residual_sanity_client_v1.py"
PROTOCOL = Path(__file__).resolve().parent / "replay_residual_sanity_protocol_v1.py"


def _source_surface_checks() -> dict[str, bool]:
    runner = RUNNER.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")
    protocol = PROTOCOL.read_text(encoding="utf-8")
    # Parse every file first: source-level checks are not regex-only syntax guesses.
    ast.parse(runner); ast.parse(client); ast.parse(protocol)
    forbidden_fragments = ("patch" + "_score", "/" + "patch" + "_score", "inject" + "ion")
    no_causal_surface = all(x not in runner and x not in client for x in forbidden_fragments)
    checks = {
        "runner_client_no_causal_surface": no_causal_surface,
        "runner_refuses_overwrite": "OUTPUT_EXISTS_REFUSE_OVERWRITE" in runner,
        "runner_exact_dev_population": "EPISODE_SET_MUST_BE_EXACT_0_31" in runner,
        "runner_atomic_final_write": "os.replace" in runner and "mkstemp" in runner,
        "client_capture_only_allowlist": '_ALLOWED_POST = frozenset({"/score_sequences", "/capture"})' in client,
        "protocol_exact_authoritative_hashes": all(x in protocol for x in (p.DESIGN_SHA256, p.COHORT_SHA256, p.UNTOUCHED_SHA256)),
        "protocol_exact_layers": "LAYERS = (7, 14, 21, 27)" in protocol,
        "protocol_exact_128": "PLAN_SLOT_TOKENS = 128" in protocol,
        "protocol_payload_hash": "canonical_json_bytes(metadata) + raw" in protocol,
        "protocol_reasoning_fail_closed": "REASONING_TRACE_GUARD_FAILED" in protocol,
        "protocol_late_null": "NEXT_ACTION_PRESERVED_LATE_NULL" in protocol,
    }
    return checks


def validate_result(obj: dict[str, Any]) -> dict[str, bool]:
    checks = {
        "kind": obj.get("kind") == "PLANCARRY_REPLAY_RESIDUAL_SANITY_V1_1_RESULT",
        "design_hash": obj.get("design_sha256") == p.DESIGN_SHA256,
        "cohort_hash": obj.get("cohort_manifest_sha256") == p.COHORT_SHA256,
        "untouched_hash": obj.get("untouched_population_sha256") == p.UNTOUCHED_SHA256,
        "development_population": obj.get("development_population_indices") == list(p.DEV_INDICES),
        "no_sealed_access": obj.get("sealed_population_accessed", False) is False,
        "zero_causal_requests": int(obj.get("causal_intervention_requests", 0)) == 0,
        "gate_label": obj.get("gate", {}).get("label") in {
            "PASS_REPLAY_RESIDUAL_SANITY", "FAIL_REPLAY_RESIDUAL_SANITY", "INCONCLUSIVE_INSUFFICIENT_NATURAL_TRAJECTORIES"
        },
    }
    for family in obj.get("family_results", []):
        if int(family.get("frozen_index", -1)) not in p.DEV_INDICES:
            checks["family_indices_development_only"] = False
            break
    else:
        checks["family_indices_development_only"] = True
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    p.load_authoritative(root)
    checks = _source_surface_checks()
    if args.result:
        checks.update({"result_" + k: v for k, v in validate_result(json.loads(Path(args.result).read_text(encoding="utf-8"))).items()})
    passed = all(checks.values())
    print(json.dumps({"passed": passed, "checks": checks, "passed_count": sum(checks.values()), "total": len(checks)}, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
