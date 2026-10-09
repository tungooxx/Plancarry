#!/usr/bin/env python3
"""Static backend-copy capability inventory for PlanCarry BIND-v0.3 G0.

Never imports TextWorld/ALFWorld, opens a game, or calls a model.
Pinned upstream SOURCE compatibility assessment, NOT installed version attestation,
G0 PASS, or a proof that no other valid full-state method could exist.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "plancarry.bind.g0.textworld-copy-surface-audit.v1"
EXPECTED_UPSTREAM_COMMIT = "6d88a0845bc904751d3b7f128d61f21cabdf6f70"
FILES = {
    "core": "textworld/core.py",
    "pddl": "textworld/envs/pddl/pddl.py",
    "batch": "textworld/envs/batch/batch_env.py",
    "gym_batch": "textworld/gym/envs/textworld_batch.py",
    "local_runtime": "alfworld_runtime.py",
}


def _classes(source: str) -> dict[str, dict[str, Any]]:
    tree = ast.parse(source)
    results = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {x.name: x for x in node.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))}
        results[node.name] = {
            "methods": sorted(methods),
            "copy_raises_not_implemented": ("copy" in methods and any(
                isinstance(x, ast.Raise) and isinstance(x.exc, (ast.Name, ast.Call))
                and ((x.exc.id if isinstance(x.exc, ast.Name) else getattr(x.exc.func, "id", None)) == "NotImplementedError")
                for x in ast.walk(methods["copy"])
            )),
        }
    return results


def audit(sources: dict[str, str], upstream_commit: str) -> dict[str, Any]:
    if set(sources) != set(FILES) or not all(isinstance(x, str) and x for x in sources.values()):
        raise ValueError("Must provide all five original or upstream source files")
    if upstream_commit != EXPECTED_UPSTREAM_COMMIT:
        raise ValueError("Upstream repository commit not pinned to audited version")
    cs = {key: _classes(src) for key, src in sources.items()}
    required = {
        "core": ["Environment", "GameState"],
        "pddl": ["PddlEnv"],
        "batch": ["SyncBatchEnv"],
        "gym_batch": ["TextworldBatchGymEnv"],
        "local_runtime": ["AlfRuntime"],
    }
    for key, needed in required.items():
        if any(name not in cs[key] for name in needed):
            raise ValueError("Missing expected backend class in " + key)
    env = cs["core"]["Environment"]
    game_state = cs["core"]["GameState"]
    pddl = cs["pddl"]["PddlEnv"]
    sync = cs["batch"]["SyncBatchEnv"]
    gym = cs["gym_batch"]["TextworldBatchGymEnv"]
    local = cs["local_runtime"]["AlfRuntime"]
    methods = lambda d: set(d["methods"])
    return {
        "schema": SCHEMA,
        "status": "BACKEND_COPY_SURFACE_STATIC_AUDITED",
        "scientific_gate": "NOT_AUTHORIZED",
        "g0_state_equivalence": "BLOCKED_STATE_EQUIVALENCE",
        "upstream_git_revision": upstream_commit,
        "local_runtime_is_historical_revision_attested": False,
        "upstream_matches_original_installed_package_digest": False,
        "sources_sha256": {key: hashlib.sha256(src.encode()).hexdigest() for key,src in sources.items()},
        "observations": {
            "core_environment_copy_declared": "copy" in methods(env),
            "core_environment_copy_is_abstract_not_implemented": env["copy_raises_not_implemented"],
            "game_state_copy_is_deepcopy_of_reported_readout": "copy" in methods(game_state) and "deepcopy" in sources["core"],
            "pddl_env_overrides_copy": "copy" in methods(pddl),
            "synchronous_batch_env_overrides_copy": "copy" in methods(sync),
            "gym_batch_exposes_copy_or_clone": bool(methods(gym) & {"copy", "clone"}),
            "plancarry_alf_runtime_exposes_copy_or_clone": bool(methods(local) & {"copy", "clone"}),
            "plancarry_alf_runtime_exposes_full_state_export_restore": bool(
                methods(local) & {"save_state", "restore_state", "export_full_state", "import_full_state", "snapshot", "load_state"}
            ),
        },
        "scope": ("Pinned upstream main (2026-09-29) is a static code snapshot, not evidence of the exact version "
                  "installed in Aug 2026. A GameState.copy() of reported readout does not clone the underlying "
                  "PDDL interpreter. No direct full-state clone API appears on the inspected original Plancarry "
                  "wrapper or upstream PddlEnv+Gym batch stack. This does not rule out custom independent reset/"
                  "replay or another verified backend with complete RNG/state snapshot support."),
        "pre_g1_need": ("Pin actual historically installed TextWorld/ALFWorld/PDDL backend versions and verify "
                        "complete state or transition-equivalent independently reset clones, including ordered "
                        "public action/observation bytes and full hidden facts/RNG, on synthetic toy games before "
                        "source/train games. An unchanged legacy state hash never suffices."),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream-root", type=Path, required=True)
    p.add_argument("--local-runtime", type=Path, required=True)
    p.add_argument("--upstream-commit", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    try:
        sources = {key: (args.local_runtime if key == "local_runtime" else args.upstream_root / path)
                   .read_text(encoding="utf-8") for key, path in FILES.items()}
        report = audit(sources, args.upstream_commit)
    except (OSError, ValueError, SyntaxError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "INVALID_AUDIT_INPUT", "scientific_gate": "NOT_AUTHORIZED",
                          "error": str(exc)}, sort_keys=True))
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0  # Successful STATIC AUDIT ONLY, never G0 execution permission.


if __name__ == "__main__":
    raise SystemExit(main())
