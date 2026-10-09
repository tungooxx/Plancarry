#!/usr/bin/env python3
"""Read-only static + synthetic G0 inspection of the original ALFWorld runtime.

Never imports ALFWorld/TextWorld, never opens TRAIN games or calls a model.
Reports whether the *legacy digest* is a complete simulator-state certificate.
A detected limitation is NOT evidence that two specific empirical states differ.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "plancarry.bind.g0.legacy-state-hash-limit.v1"
RUNTIME_FUNCS = ("stable_json", "_facts", "_commands", "state_hash")
FULL_STATE_APIS = frozenset({
    "clone", "save_state", "restore_state", "load_state",
    "export_full_state", "import_full_state", "snapshot", "set_state",
})


def load_original_functions(source: str) -> tuple[dict[str, Any], set[str], str]:
    """Compile only unchanged stdlib-only source functions via AST isolation."""
    tree = ast.parse(source)
    funcs = {
        x.name: x for x in tree.body
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = set(RUNTIME_FUNCS) - set(funcs)
    if missing:
        raise ValueError(f"Original runtime missing functions: {sorted(missing)}")
    runtime = next(
        (x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "AlfRuntime"),
        None,
    )
    if runtime is None:
        raise ValueError("No original AlfRuntime class")
    methods = {
        x.name for x in runtime.body
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # Function bodies are byte-for-byte faithful to the original AST; external
    # ALFWorld import and ACTIVE_DATA_ROOT side effects are never executed.
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations", asname=None)], level=0
    )
    mod = ast.fix_missing_locations(ast.Module(
        body=[future] + [funcs[n] for n in RUNTIME_FUNCS], type_ignores=[]
    ))
    env: dict[str, Any] = {
        "json": json, "hashlib": hashlib, "Path": Path
    }
    exec(compile(mod, "<isolated_original_alfworld_state_hash>", "exec"), env, env)
    snippet = ast.get_source_segment(source, funcs["state_hash"]) or ""
    return env, methods, snippet


def audit_source(source: str) -> dict[str, Any]:
    if not source:
        raise ValueError("Cannot audit empty source")
    functions, methods, snippet = load_original_functions(source)
    h = functions["state_hash"]
    path = "/synthetic/pick_and_place_simple-Book-None-Desk-1/trial_SYNTH/game.tw-pddl"
    obs = "Synthetic room. Do not load any actual dataset."
    info = {
        "admissible_commands": ["go to desk 1", "go to fridge 1"],
        "facts": ["on(book,table)"],
        "private_rng_state": "SEED_A",
        "private_inventory_cache": {"book": "desk"},
    }
    baseline = h(path, obs, info, 0.0, False)
    permuted = dict(info, admissible_commands=list(reversed(info["admissible_commands"])))
    rng_changed = dict(info, private_rng_state="SEED_B")
    cache_changed = dict(info, private_inventory_cache={"book": "fridge"})
    same_if_reordered = baseline == h(path, obs, permuted, 0.0, False)
    same_if_rng_changed = baseline == h(path, obs, rng_changed, 0.0, False)
    same_if_hidden_cache_changed = baseline == h(path, obs, cache_changed, 0.0, False)
    has_restorable_state_api = bool(methods & FULL_STATE_APIS)
    # The assertion is a scope of proof, not an existence claim about live
    # simulator internal states. Hidden names are intentionally synthetic.
    return {
        "schema": AUDIT_SCHEMA,
        "source_file_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "scientific_gate": "NOT_AUTHORIZED",
        "verdict": "BLOCKED_FULL_STATE_AUTHORITY_FROM_LEGACY_HASH",
        "original_alf_runtime_methods": sorted(methods),
        "full_state_named_method_present": has_restorable_state_api,
        "state_hash_sorts_action_menu_in_source": "sorted(_commands(info))" in snippet,
        "synthetic_probe": {
            "baseline_hash": baseline,
            "action_menu_order_changed": permuted["admissible_commands"] != info["admissible_commands"],
            "hash_unchanged_when_action_order_reversed": same_if_reordered,
            "hash_unchanged_when_omitted_rng_field_changed": same_if_rng_changed,
            "hash_unchanged_when_omitted_private_field_changed": same_if_hidden_cache_changed,
        },
        "scope": (
            "The existing digest is invariant to the tested changes. This proves "
            "digest equality is INSUFFICIENT to certify byte-exact ordered command menus, "
            "hidden-state/RNG equality, or complete clone/replay. It does not prove "
            "two actual ALFWorld states have different RNG or are otherwise invalid."
        ),
        "required_before_G1": (
            "Independently authenticated complete game state export/restore + RNG "
            "or demonstrably equivalent state clones and full ordered public action "
            "and returned observation byte comparison; the digest proxy alone cannot pass G0."
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    try:
        data = audit_source(a.source.read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError, TypeError, KeyError) as exc:
        print(json.dumps({
            "scientific_gate": "NOT_AUTHORIZED",
            "verdict": "INVALID_RUNTIME_SOURCE",
            "error": str(exc),
        }))
        return 2
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "scientific_gate": data["scientific_gate"],
        "verdict": data["verdict"],
        "synthetic_probe": data["synthetic_probe"],
        "source_file_sha256": data["source_file_sha256"],
    }, sort_keys=True))
    return 0  # Means the offline audit ran; it is NOT permission to run G1.


if __name__ == "__main__":
    raise SystemExit(main())
