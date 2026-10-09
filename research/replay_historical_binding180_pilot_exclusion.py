#!/usr/bin/env python3
"""Read-only historical cohort integrity reproduction for PlanCarry Binding v1 / pilot v2.

Engineering provenance audit only. No model, rollout, GPU, paid API or scientific gate.
Requires original ALFWorld 0.4.2 ZIP and four frozen JSON manifests as local files.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = "/opt/gpu-lab/data/plancarry-alfworld/"
ZIP_PREFIX = "json_2.1.1/train/pick_and_place_simple-"
BIND_SALT = "plancarry-binding-v1-2026-08-18"
PILOT_SALT = "plancarry-latent-ab-pilot-v2-2026-08-19"
BIND_POOL_SHA256 = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
EXPECTED_ARCHIVE_SHA256 = "5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf"
GDAA_FILENAMES = (
    "gdaa_train_candidate_manifest_v1.json",
    "gdaa_train_candidate_manifest_disjoint_v1.json",
    "gdaa_train_candidate_manifest_fresh_v2.json",
)
PILOT_FILENAME = "latent_ab_pilot_manifest_v2.json"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build_report(archive: Path, manifest_dir: Path) -> dict:
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("Source ZIP CRC integrity failed")
        pop = sorted(ROOT + n for n in z.namelist()
                     if n.startswith(ZIP_PREFIX) and n.endswith("/game.tw-pddl"))
    if len(pop) != 790 or len(set(pop)) != 790:
        raise ValueError(f"Original TRAIN universe is not exactly 790 distinct games: {len(pop)}")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    if archive_hash != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("ALFWorld archive SHA256 is not the independently recovered source asset")
    binding = sorted(pop, key=lambda p: sha(BIND_SALT + "\n" + p))[:180]
    binding_hash = sha("\n".join(binding) + "\n")
    if binding_hash != BIND_POOL_SHA256:
        raise ValueError("Frozen historical Binding v1 selected-list SHA256 mismatch")
    docs = [json.loads((manifest_dir / f).read_text(encoding="utf-8")) for f in GDAA_FILENAMES]
    pilot = json.loads((manifest_dir / PILOT_FILENAME).read_text(encoding="utf-8"))
    for d in docs:
        if d.get("split") != "train" or len(d.get("candidates", [])) != 90:
            raise ValueError("Unexpected GDAA train candidate manifest")
    if pilot.get("split") != "train" or len(pilot.get("candidates", [])) != 40:
        raise ValueError("Unexpected pilot train candidate manifest")
    gdaa = set().union(*(d["candidates"] for d in docs))
    true = set(binding)
    actual_inter = sorted(gdaa & true)
    actual_pilot = [x for x in pilot["candidates"] if x in true]
    wrong_binding = sorted(pop, key=lambda p: sha(BIND_SALT + p))[:180]
    wrong = set(wrong_binding)
    wrong_inter = sorted(gdaa & wrong)
    reconstructed_pilot = sorted((x for x in pop if x not in (wrong | gdaa)),
                                 key=lambda p: sha(PILOT_SALT + p))[:40]
    exact_pilot = reconstructed_pilot == pilot["candidates"]
    if len(gdaa) != 199 or len(actual_inter) != 19 or len(actual_pilot) != 11:
        raise ValueError("Observed historical overlap disagrees with verified frozen fixtures")
    if len(wrong_inter) != 47 or len(wrong | gdaa) != 332 or not exact_pilot:
        raise ValueError("Historical missing-newline mechanism did not reproduce all pilot paths")
    return {
        "verdict": "HISTORICAL_PILOT_EXCLUSION_BUG_EXACTLY_REPRODUCED",
        "science_gate": "NOT_AUTHORIZED",
        "source_archive_sha256": archive_hash,
        "source_train_game_count": len(pop),
        "binding_v1_true_selected_count": len(binding),
        "binding_v1_frozen_selected_list_sha256": binding_hash,
        "gdaa_union_paths": len(gdaa),
        "actual_binding_gdaa_overlap": len(actual_inter),
        "actual_prior_union": len(true | gdaa),
        "reported_prior_union": pilot["excluded_union_count"],
        "actual_pilot_selection_overlapping_true_binding_count": len(actual_pilot),
        "actual_pilot_overlap_paths": actual_pilot,
        "incorrect_omitted_newline_binding_gdaa_overlap": len(wrong_inter),
        "incorrect_omitted_newline_prior_union": len(wrong | gdaa),
        "buggy_replay_matches_all_40_pilot_paths_and_order": exact_pilot,
        "true_binding_selected_absolute_paths": binding,
        "scope_limit": "Path selection integrity only; cannot prove actual episode/model consumption or prospective G1 freshness",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--manifests", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        report = build_report(args.archive, args.manifests)
    except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({"verdict": "BLOCKED_SOURCE_INTEGRITY", "reason": str(exc), "science_gate": "NOT_AUTHORIZED"}))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in
                     ("actual_pilot_overlap_paths", "true_binding_selected_absolute_paths")}, indent=2))
    print("AUDIT_FILE", str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
