#!/usr/bin/env python3
"""Portable and fail-closed BIND/ALFWorld ORIGINAL source resolution.

Only changes physical *storage* location. Preserves exact original 180-game
selection and immutable per-game bytes. No model, TextWorld runtime, TRAIN
rollout, G1, confirmation or scientific gate authorization is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ARCHIVE_SHA256 = "5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf"
OLD_LOGICAL_ROOT = Path("/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1")
OLD_SALT = "plancarry-binding-v1-2026-08-18"
EXPECTED_180_SHA256 = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"


def sha_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(source_root: Path) -> dict:
    if source_root.name != "json_2.1.1" or not source_root.is_dir():
        raise ValueError("source_root must be an extracted json_2.1.1 directory")
    actual = sorted((source_root / "train").glob("pick_and_place_simple-*/trial_*/game.tw-pddl"))
    if len(actual) != 790:
        raise ValueError(f"Original BIND pool mismatch: {len(actual)} != 790")
    logical_to_physical = {}
    for path in actual:
        relative = path.relative_to(source_root)
        logical = str(OLD_LOGICAL_ROOT / relative)
        if logical in logical_to_physical:
            raise ValueError("Duplicate canonical logical identity")
        logical_to_physical[logical] = path
    selected = sorted(
        logical_to_physical,
        key=lambda path: hashlib.sha256((OLD_SALT + "\n" + path).encode()).hexdigest()
    )[:180]
    cohort_hash = hashlib.sha256(("\n".join(selected) + "\n").encode()).hexdigest()
    if cohort_hash != EXPECTED_180_SHA256:
        raise ValueError("Frozen original 180 source selection has drifted")
    return {
        "schema": "plancarry.bind.alfworld.physical-root-logical-identity-bridge.v1",
        "source_archive_sha256": ARCHIVE_SHA256,
        "physical_root": str(source_root.resolve()),
        "historical_logical_root": str(OLD_LOGICAL_ROOT),
        "source_file_count": len(actual),
        "source_family_count": len({p.parent.parent.name for p in actual}),
        "historical_180_sha256": cohort_hash,
        "historical_180": [
            {
                "index": i,
                "canonical_id": logical,
                "relative_path": str(logical_to_physical[logical].relative_to(source_root)),
                "physical_file": str(logical_to_physical[logical].resolve()),
                "game_sha256": sha_bytes(logical_to_physical[logical]),
            }
            for i,logical in enumerate(selected)
        ],
        "scientific_gate": "NOT_AUTHORIZED_SOURCE_RESTORE_ONLY",
        "model_calls": 0,
        "environment_rollouts": 0,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    try:
        report=resolve(args.source_root)
    except (ValueError, OSError) as error:
        print(json.dumps({"status":"BLOCKED_SOURCE_ROOT","error":str(error)}))
        return 2
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "status":"ORIGINAL_ALFWORLD_180_COHORT_VERIFIED",
        "source_count":report["source_file_count"],
        "family_count":report["source_family_count"],
        "original_pool_sha256":report["historical_180_sha256"],
        "physical_root":report["physical_root"],
        "science":"NOT_AUTHORIZED_SOURCE_RESTORE_ONLY",
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
