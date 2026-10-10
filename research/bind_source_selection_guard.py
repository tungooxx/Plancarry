#!/usr/bin/env python3
"""Fail-closed static check for historical BIND/Pilot cohort-selection drift.

Only checks deterministic SHA-256 source-selection consistency and literal
membership. Original Binding hashes the ABSOLUTE runtime source path, not
the relative train/... path used for candidate membership. Never certifies actual prior LLM use, unseen TRAIN status, source
competence, or permission to run a model/experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "plancarry.bind.selection-audit.v0.2"
# Original Binding-v1 source SHA preimage hashes an ABSOLUTE path.
# The manifest stores relative train/... for membership only.
ORIGINAL_BINDING_PATH_ROOT = "/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1"


def _pick(paths: list[str], salt: str, n: int, *, legacy: bool) -> list[str]:
    # Correct frozen Binding source rule has the newline delimiter.
    prefix = salt if legacy else salt + "\n"
    return sorted(paths, key=lambda p: hashlib.sha256(
        (prefix + ORIGINAL_BINDING_PATH_ROOT + "/" + p).encode("utf-8")
    ).hexdigest())[:n]


def audit(value: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return {"verdict": "INVALID_INPUT", "errors": ["expected JSON object"], "scientific_gate": "NOT_AUTHORIZED"}
    if set(value) != {"schema", "population", "binding_selected", "pilot_selected", "binding_salt", "binding_count", "hash_preimage_root"}:
        errors.append("unexpected/missing top-level fields")
    if value.get("schema") != SCHEMA:
        errors.append("invalid schema")
    if value.get("hash_preimage_root") != ORIGINAL_BINDING_PATH_ROOT:
        errors.append("historical source hash root must be exact original absolute path")
    pop, bind, pilot = (value.get(k) for k in ("population", "binding_selected", "pilot_selected"))
    for label, group in (("population", pop), ("binding_selected", bind), ("pilot_selected", pilot)):
        if not isinstance(group, list) or not group or not all(isinstance(x, str) and x for x in group):
            errors.append(f"invalid {label} path list")
        elif len(group) != len(set(group)):
            errors.append(f"duplicate {label} path")
        elif any("\\" in x or x.startswith("/") or ".." in x.split("/") or "." in x.split("/") or "//" in x for x in group):
            errors.append(f"noncanonical {label} path")
        elif any(not x.startswith("train/pick_and_place_simple-") or not x.endswith("/game.tw-pddl") for x in group):
            errors.append(f"non-target TRAIN path in {label}")
    salt = value.get("binding_salt")
    if not isinstance(salt, str) or not salt:
        errors.append("missing binding_salt")
    n = value.get("binding_count")
    if type(n) is not int or n <= 0 or not isinstance(pop, list) or n > len(pop):
        errors.append("invalid binding_count")
    if isinstance(pop, list) and isinstance(bind, list) and isinstance(pilot, list):
        if not set(bind).issubset(pop) or not set(pilot).issubset(pop):
            errors.append("selected candidate absent from original population")
        if isinstance(n, int) and len(bind) != n:
            errors.append("binding_count disagrees with selection size")
    if errors:
        return {"verdict": "INVALID_INPUT", "errors": errors, "scientific_gate": "NOT_AUTHORIZED"}
    assert isinstance(pop, list) and isinstance(bind, list) and isinstance(pilot, list)
    assert isinstance(salt, str) and isinstance(n, int)
    correct = _pick(pop, salt, n, legacy=False)
    wrong = _pick(pop, salt, n, legacy=True)
    matches_correct = bind == correct
    # Preserve strict order; the salted prefix is part of the source contract.
    matches_legacy = bind == wrong and wrong != correct
    overlap = sorted(set(bind) & set(pilot))
    if matches_legacy:
        verdict = "BLOCKED_LEGACY_SALT_MISMATCH"
    elif not matches_correct:
        verdict = "BLOCKED_BINDING_SELECTION_MISMATCH"
    elif overlap:
        verdict = "BLOCKED_SELECTED_COHORT_OVERLAP"
    else:
        verdict = "BLOCKED_GLOBAL_USAGE_UNATTESTED"
    return {
        "verdict": verdict,
        "scientific_gate": "NOT_AUTHORIZED",
        "errors": [],
        "hash_namespace": "historical_original_absolute_path_v1",
        "hash_preimage_root": ORIGINAL_BINDING_PATH_ROOT,
        "binding_selection_matches_correct_delimiter": matches_correct,
        "binding_selection_matches_wrong_legacy_delimiter": matches_legacy,
        "binding_count": len(bind),
        "pilot_count": len(pilot),
        "literal_overlap_count": len(overlap),
        "literal_overlaps": overlap,
        "environment_inspection_count": None,
        "model_inference_count": None,
        "note": "Path membership is not execution exposure. Need independent run-level full-history audit for G0; never issue science PASS.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection_evidence_json", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.selection_evidence_json.read_text(encoding="utf-8"))
        result = audit(value)
    except (OSError, ValueError, UnicodeError, TypeError) as e:
        result = {"verdict": "INVALID_INPUT", "errors": [str(e)], "scientific_gate": "NOT_AUTHORIZED"}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 2 if result["verdict"] == "INVALID_INPUT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
