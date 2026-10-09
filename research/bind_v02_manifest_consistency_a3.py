#!/usr/bin/env python3
"""A3 independent consistency challenge for BIND-v0.2 historical source manifests.

Static metadata/set audit only. NEVER certifies novelty, independent custody,
source competence, model execution authority, or scientific gate success.
Run: python research/bind_v02_manifest_consistency_a3.py V1.json DISJOINT.json FRESH.json PILOT.json
Always exits nonzero: 2 invalid input, 3 source/custody still blocked.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EXCLUSION_SHA = re.compile(r"frozen binding-v1 180-candidate pool ([a-f0-9]{64})")


def audit(v1: dict[str, Any], disjoint: dict[str, Any],
          fresh: dict[str, Any], pilot: dict[str, Any]) -> dict[str, Any]:
    files = (v1, disjoint, fresh, pilot)
    errors: list[str] = []
    sets: list[set[str]] = []
    lists: list[list[str]] = []
    expected = (90, 90, 90, 40)
    for i, (doc, n) in enumerate(zip(files, expected)):
        if not isinstance(doc, dict):
            errors.append(f"manifest[{i}] must be a JSON object")
            doc = {}
        xs = doc.get("candidates")
        if not isinstance(xs, list) or len(xs) != n or any(
            not isinstance(x, str) or not x.endswith("/game.tw-pddl")
            for x in xs
        ):
            errors.append(f"manifest[{i}] must list {n} game.tw-pddl paths")
            xs = []
        if len(set(xs)) != len(xs):
            errors.append(f"manifest[{i}] contains duplicate paths")
        if doc.get("candidate_count") != n:
            errors.append(f"manifest[{i}].candidate_count wrong")
        lists.append(xs)
        sets.append(set(xs))

    o, d, f, p = lists
    O, D, F, P = sets
    sorted_gdaa = all(xs == sorted(xs) for xs in (o, d, f))
    common = [x for x in o if x in D]
    disjoint_extra = [x for x in d if x not in O]
    correct_prefix = d[:len(common)] == common and all(
        x > o[-1] for x in disjoint_extra
    ) if o else False
    binding_tags = []
    for i in (1, 2):
        order = files[i].get("ordering", "") if isinstance(files[i], dict) else ""
        match = EXCLUSION_SHA.search(order) if isinstance(order, str) else None
        binding_tags.append(match.group(1) if match else None)
    common_binding_exclusion = (
        len(binding_tags) == 2
        and binding_tags[0] is not None
        and binding_tags[0] == binding_tags[1]
    )
    same_reported_universe = (
        v1.get("pool_size") == 790
        and disjoint.get("pool_size") == 610
        and fresh.get("pool_size") == 520
        and pilot.get("train_population") == 790
    )
    if not sorted_gdaa:
        errors.append("GDAA paths are not lexicographically sorted")
    if not correct_prefix:
        errors.append("DISJOINT is not lexicographic V1 survivor prefix + later paths")
    if not common_binding_exclusion:
        errors.append("DISJOINT/FRESH do not reference identical frozen binding exclusion")
    if not same_reported_universe:
        errors.append("universe/pool cardinalities are not the asserted 790,610,520")
    if O & F or D & F or (O | D | F) & P:
        errors.append("unexpected GDAA/FRESH/PILOT overlap")

    gdaa_union = len(O | D | F)
    v1_missing = len(O - D)
    inferred_binding_overlap = v1_missing if not errors else None
    claimed_binding = pilot.get("excluded_binding_count")
    claimed_gdaa = pilot.get("excluded_gdaa_union_count")
    claimed_union = pilot.get("excluded_union_count")
    if any(type(x) is not int for x in
           (claimed_binding, claimed_gdaa, claimed_union)):
        errors.append("PILOT historical exclusion counts must be integers")
        pilot_implied_overlap = None
    else:
        pilot_implied_overlap = claimed_binding + claimed_gdaa - claimed_union
        if claimed_binding != 180 or claimed_gdaa != gdaa_union:
            errors.append("PILOT counts do not match declared source pools")
    conflict = (
        not errors and inferred_binding_overlap is not None
        and inferred_binding_overlap != pilot_implied_overlap
    )
    return {
        "verdict": ("INVALID_AUDIT_INPUT" if errors else
                    "UNRESOLVED_PROVENANCE_CONFLICT" if conflict else
                    "SOURCE_FRESHNESS_UNATTESTED"),
        "scientific_gate": "NOT_AUTHORIZED",
        "errors": errors,
        "source_path_counts": [len(s) for s in sets],
        "v1_disjoint_intersection": len(O & D),
        "v1_missing_from_disjoint": v1_missing,
        "gdaa_union": gdaa_union,
        "four_manifest_union": len(O | D | F | P),
        "disjoint_and_fresh_shared_binding_exclusion_sha": binding_tags[0] if common_binding_exclusion else None,
        "binding_gdaa_overlap_inferred_if_metadata_true": inferred_binding_overlap,
        "binding_gdaa_overlap_implied_by_pilot_counts": pilot_implied_overlap,
        "overlap_discrepancy": (
            pilot_implied_overlap - inferred_binding_overlap
            if conflict else None
        ),
        "meaning": ("Conditional contradiction between frozen source-selection "
                    "semantics and PILOT exclusion arithmetic; no path-freshness "
                    "or execution authorization is established."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("v1", "disjoint", "fresh", "pilot"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    try:
        docs = [json.loads(getattr(args, k).read_text(encoding="utf-8"))
                for k in ("v1", "disjoint", "fresh", "pilot")]
        report = audit(*docs)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        report = {"verdict": "INVALID_AUDIT_INPUT",
                  "scientific_gate": "NOT_AUTHORIZED", "errors": [str(exc)]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["verdict"] == "INVALID_AUDIT_INPUT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
