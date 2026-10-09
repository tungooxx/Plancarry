#!/usr/bin/env python3
"""Read-only ALFWorld historical family membership audit for PlanCarry G0.

Classifies already-listed/selected family identities only. NEVER certifies
non-consumption, simulator-state freshness, or G1 execution authorization.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

ORIGINAL_ROOT = "/opt/gpu-lab/data/plancarry-alfworld/"
INNER_PREFIX = "json_2.1.1/train/pick_and_place_simple-"
ARCHIVE_SHA256 = "5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf"
BINDING_DIGEST = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
BIND_SALT = "plancarry-binding-v1-2026-08-18"
HISTORY_SCAN_MODE = "METADATA_ONLY_REGEX_FAMILY_IDS_NO_JSON_OUTCOME_PARSE"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def family_from_game_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    found = [p for p in parts if p.startswith("pick_and_place_simple-")]
    if len(found) != 1 or len(parts) < 3 or parts[-1] != "game.tw-pddl":
        raise ValueError("Noncanonical TRAIN game path")
    return found[0]


def reconcile(population: list[str], indexed_families: set[str],
              selected_binding: list[str]) -> dict[str, Any]:
    if not population or len(population) != len(set(population)):
        raise ValueError("Empty/duplicate game population")
    pop_by_family = Counter(family_from_game_path(p) for p in population)
    original_set = set(population)
    if len(selected_binding) != len(set(selected_binding)) or not set(selected_binding) <= original_set:
        raise ValueError("Invalid or foreign Binding selection")
    binding_family_set = {family_from_game_path(p) for p in selected_binding}
    families = set(pop_by_family)
    excluded_inside_archive = (indexed_families | binding_family_set) & families
    not_in_two_records = sorted(families - excluded_inside_archive)
    binding_missed = sorted(binding_family_set - indexed_families)
    ghosts = sorted(indexed_families - families)
    return {
        "status": "BOUNDED_SELECTION_FAMILY_EXPOSURE_RECONCILED",
        "scientific_gate": "NOT_AUTHORIZED",
        "historical_coverage": "INCOMPLETE",
        "game_population_count": len(population),
        "unique_train_source_families": len(families),
        "indexed_historical_families_total": len(indexed_families),
        "indexed_historical_families_present_in_archive": len(indexed_families & families),
        "indexed_historical_family_names_not_in_archive": ghosts,
        "binding_v1_selected_game_count": len(selected_binding),
        "binding_v1_selected_family_count": len(binding_family_set),
        "binding_selected_families_missing_from_history_index_count": len(binding_missed),
        "binding_selected_families_missing_from_history_index": binding_missed,
        "historical_index_plus_binding_selected_families_in_archive": len(excluded_inside_archive),
        "families_not_in_these_two_records_count": len(not_in_two_records),
        "game_paths_not_in_these_two_records_count": sum(pop_by_family[f] for f in not_in_two_records),
        "families_not_in_these_two_records": not_in_two_records,
        "candidate_game_count_by_family": {f: pop_by_family[f] for f in not_in_two_records},
        "interpretation": ("These are historical family-name selections and metadata mentions, not a complete actual "
                           "model-consumption ledger. Neither absence nor inclusion alone proves a successful model call."),
        "next_gate": "BLOCKED_INDEPENDENT_HISTORICAL_NON_CONSUMPTION_AND_FULL_STATE_ATTESTATION",
    }


def build(archive: Path, history: Path, binding: Path) -> dict[str, Any]:
    archive_digest = sha(archive.read_bytes())
    if archive_digest != ARCHIVE_SHA256:
        raise ValueError("Original archive SHA256 mismatch")
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("Archive CRC mismatch")
        names = sorted(x for x in z.namelist()
                       if x.startswith(INNER_PREFIX) and x.endswith("/game.tw-pddl"))
    pop = [ORIGINAL_ROOT + x for x in names]
    if len(pop) != 790:
        raise ValueError(f"Expected original 790 games, got {len(pop)}")
    expected = sorted(pop, key=lambda p: sha((BIND_SALT + "\n" + p).encode()))[:180]
    if sha(("\n".join(expected) + "\n").encode()) != BINDING_DIGEST:
        raise ValueError("Original Binding-180 checksum mismatch")
    hist = json.loads(history.read_text(encoding="utf-8"))
    frozen = json.loads(binding.read_text(encoding="utf-8"))
    if hist.get("scan_mode") != HISTORY_SCAN_MODE:
        raise ValueError("Historical index scan semantics changed")
    listed = hist.get("exposed_exact_families")
    if not isinstance(listed, list) or len(listed) != hist.get("exposed_exact_family_count"):
        raise ValueError("Historical family-index size inconsistent")
    if len(listed) != len(set(listed)) or not all(isinstance(x, str) for x in listed):
        raise ValueError("Invalid historical family list")
    recorded = frozen.get("selected_absolute_paths")
    if recorded != expected:
        raise ValueError("Selection list differs from original preregistered Binding180")
    result = reconcile(pop, set(listed), recorded)
    result.update(archive_sha256=archive_digest, binding_selected_sha256=BINDING_DIGEST,
                  historical_index_sha256=sha(history.read_bytes()),
                  original_binding_selection_json_sha256=sha(binding.read_bytes()))
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--history", type=Path, required=True)
    p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = build(args.archive, args.history, args.binding)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "INVALID_AUDIT_INPUT", "scientific_gate": "NOT_AUTHORIZED", "error": str(exc)}))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, (list, dict))}, sort_keys=True))
    return 0  # only an offline audit computation, NOT an execution gate


if __name__ == "__main__":
    raise SystemExit(main())
