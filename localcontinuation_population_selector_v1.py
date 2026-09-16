#!/usr/bin/env python3
"""Deterministic input-only population selector for ReplayResidual-LocalContinuation.

This module deliberately does not discover ALFWorld data. Candidate and exposed game
paths must be supplied explicitly by the caller. Synthetic engineering tests do not
freeze any real scientific population.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Iterable, Sequence

SALT = "ReplayResidualLocalContinuation|V1|"
DEVELOPMENT_N = 32
CONFIRMATION_N = 20
RESERVE_N = 12
TOTAL_N = DEVELOPMENT_N + CONFIRMATION_N + RESERVE_N
_KIND = "PLANCARRY_REPLAYRESIDUAL_LOCALCONTINUATION_POPULATION_SELECTION_V1"
_CANONICAL_RE = re.compile(
    r"^json_2\.1\.1/train/"
    r"pick_and_place_simple-[^/]+/"
    r"trial_[^/]+/game\.tw-pddl$"
)
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class SelectionError(ValueError):
    """Fail-closed selector input/contract violation."""


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_paths(paths: Sequence[str]) -> str:
    return hashlib.sha256(("\n".join(paths) + ("\n" if paths else "")).encode("utf-8")).hexdigest()


def normalize_game_path(raw: object) -> str:
    if not isinstance(raw, str):
        raise SelectionError("PATH_NOT_STRING")
    path = raw.strip().replace("\\", "/")
    if not path:
        raise SelectionError("EMPTY_PATH")
    if path.startswith("/") or _DRIVE_RE.match(path):
        raise SelectionError(f"ABSOLUTE_PATH_FORBIDDEN:{path}")
    if "//" in path:
        raise SelectionError(f"EMPTY_PATH_SEGMENT:{path}")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SelectionError(f"NONCANONICAL_PATH_SEGMENT:{path}")
    if not _CANONICAL_RE.fullmatch(path):
        raise SelectionError(f"NONCANONICAL_ALFWORLD_PATH:{path}")
    return path


def normalize_unique_paths(values: Iterable[object], *, label: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        path = normalize_game_path(raw)
        if path in seen:
            raise SelectionError(f"DUPLICATE_{label.upper()}_PATH:{path}")
        seen.add(path)
        normalized.append(path)
    return normalized


def load_path_list(filename: str, *, label: str) -> list[str]:
    with open(filename, "r", encoding="utf-8") as handle:
        text = handle.read()
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SelectionError(f"INVALID_{label.upper()}_JSON:{exc.msg}") from exc
        if not isinstance(raw, list):
            raise SelectionError(f"{label.upper()}_JSON_NOT_LIST")
        values = raw
    else:
        values = [line for line in text.splitlines() if line.strip()]
    return normalize_unique_paths(values, label=label)


def _rank_digest(path: str) -> str:
    return sha256_text(SALT + path)


def select_population(inventory: Sequence[str], exposed: Sequence[str]) -> dict[str, object]:
    inventory_paths = normalize_unique_paths(inventory, label="inventory")
    exposed_paths = normalize_unique_paths(exposed, label="exposed")
    inventory_set = set(inventory_paths)
    exposed_set = set(exposed_paths)

    unknown_exposed = sorted(exposed_set - inventory_set)
    if unknown_exposed:
        raise SelectionError(f"EXPOSED_PATH_NOT_IN_INVENTORY:{unknown_exposed[0]}")

    remaining = sorted(inventory_set - exposed_set, key=lambda path: (_rank_digest(path), path))
    if len(remaining) < TOTAL_N:
        raise SelectionError(f"INSUFFICIENT_UNEXPOSED_PATHS:{len(remaining)}<{TOTAL_N}")

    selected = remaining[:TOTAL_N]
    phases = (
        ["development"] * DEVELOPMENT_N
        + ["confirmation"] * CONFIRMATION_N
        + ["reserve"] * RESERVE_N
    )
    rows = [
        {
            "frozen_index": index,
            "phase": phase,
            "game_path": path,
            "rank_sha256": _rank_digest(path),
        }
        for index, (phase, path) in enumerate(zip(phases, selected, strict=True))
    ]

    selected_set = set(selected)
    if len(selected_set) != TOTAL_N:
        raise AssertionError("INTERNAL_SELECTION_DUPLICATE")
    if selected_set & exposed_set:
        raise AssertionError("INTERNAL_EXPOSURE_LEAK")
    phase_sets = {
        phase: {row["game_path"] for row in rows if row["phase"] == phase}
        for phase in ("development", "confirmation", "reserve")
    }
    if phase_sets["development"] & phase_sets["confirmation"]:
        raise AssertionError("INTERNAL_DEV_CONFIRMATION_OVERLAP")
    if phase_sets["development"] & phase_sets["reserve"]:
        raise AssertionError("INTERNAL_DEV_RESERVE_OVERLAP")
    if phase_sets["confirmation"] & phase_sets["reserve"]:
        raise AssertionError("INTERNAL_CONFIRMATION_RESERVE_OVERLAP")

    canonical_inventory = sorted(inventory_set)
    canonical_exposed = sorted(exposed_set)
    return {
        "kind": _KIND,
        "scientific_result": "NOT_ASSESSED_POPULATION_SELECTION_ONLY",
        "hypothesis_id": "a7982eda-fbfd-419b-96ad-dcb83ccff6e6",
        "salt": SALT,
        "selection_rule": "Exclude exact exposed paths; rank remaining exact relative paths by SHA256(salt+path) with lexical tie-break; take first64; indices0..31 development,32..51 untouched confirmation,52..63 reserve.",
        "source_split": "train",
        "task_family": "pick_and_place_simple",
        "inventory_n": len(canonical_inventory),
        "exposed_n": len(canonical_exposed),
        "remaining_unexposed_n": len(remaining),
        "development_n": DEVELOPMENT_N,
        "confirmation_n": CONFIRMATION_N,
        "reserve_n": RESERVE_N,
        "selected_n": TOTAL_N,
        "inventory_sha256": sha256_paths(canonical_inventory),
        "exposed_sha256": sha256_paths(canonical_exposed),
        "selected_paths_sha256": sha256_paths(selected),
        "development_confirmation_overlap": 0,
        "development_reserve_overlap": 0,
        "confirmation_reserve_overlap": 0,
        "exposed_selected_overlap": 0,
        "model_calls": 0,
        "environment_execution": 0,
        "selected": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, help="JSON-list or newline-list of canonical relative game paths")
    parser.add_argument("--exposed", required=True, help="JSON-list or newline-list of exposed canonical relative game paths")
    parser.add_argument("--output", required=True, help="New JSON output path; existing files are refused")
    args = parser.parse_args()

    inventory = load_path_list(args.inventory, label="inventory")
    exposed = load_path_list(args.exposed, label="exposed")
    result = select_population(inventory, exposed)
    raw = canonical_json_bytes(result)

    try:
        with open(args.output, "xb") as handle:
            handle.write(raw)
            handle.flush()
    except FileExistsError as exc:
        raise SelectionError(f"OUTPUT_ALREADY_EXISTS:{args.output}") from exc

    print(json.dumps({"output": args.output, "sha256": hashlib.sha256(raw).hexdigest(), "selected_n": TOTAL_N}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
