#!/usr/bin/env python3
"""Compatibility entrypoint for the frozen V2.1 ReplayResidual packet producer.

The scientific producer implementation remains imported byte-for-byte from
``replay_residual_natural_packet_producer_v2_1``.  This wrapper changes only
its ALFWorld runtime factory by installing the TextWorld 1.7.0 / CPython 3.13
EvalSymbol compatibility shim before constructing AlfRuntime.
"""
from __future__ import annotations

from typing import Any, Sequence

import replay_residual_natural_packet_producer_v2_1 as frozen
from replay_residual_textworld_py313_compat_v1 import install_textworld_py313_eval_compat


def replayresidual_runtime_factory(game_path: str) -> Any:
    install_textworld_py313_eval_compat()
    from alfworld_runtime import AlfRuntime, DATA_ROOT
    return AlfRuntime(str(DATA_ROOT / game_path), max_steps=frozen.ACTION_BUDGET)


def main(argv: Sequence[str] | None = None) -> int:
    # Process-local substitution only; the frozen producer's planner, executor,
    # qualification, controls, publication, and provenance code are untouched.
    frozen.default_runtime_factory = replayresidual_runtime_factory
    return frozen.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
