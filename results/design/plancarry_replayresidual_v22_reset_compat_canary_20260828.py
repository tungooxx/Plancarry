#!/usr/bin/env python3
"""Zero-model, zero-action reset compatibility canary for ReplayResidual V2.2.

The canary constructs a tiny synthetic TextWorld game in a private temporary
folder, installs the already reviewed CPython-3.13 TextWorld shim, compiles the
synthetic game, opens it, and calls reset exactly once.  It never opens ALFWorld
study data and never calls env.step or any model/tokenizer API.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

ATTESTATION_CONTRACT_SHA256 = "40ae9747f675dc136a59ecc6e2c7ae28d4d329860566c542cbf1691d84bbc666"
COMPAT_SHIM_SHA256 = "a08a1e1e5536afc11d94868de40eaea89cb929ef43b59a1102f378446284a7f4"
EXPECTED_INSTANCE_ID = "vast_48954592"
EXPECTED_DEVICE_NAME = "NVIDIA GeForce RTX 3080"
EXPECTED_PYTHON = (3, 13, 15)
EXPECTED_PACKAGES = {
    "torch": "2.13.0+cu130",
    "transformers": "4.51.3",
    "tokenizers": "0.21.1",
    "textworld": "1.7.0",
    "alfworld": "0.4.2",
}
MODEL_CALLS = 0
ENVIRONMENT_ACTIONS = 0
STUDY_COHORT_ACCESS = False
TARGET_KIND = "SYNTHETIC_TEXTWORLD_GRAMMAR_CANARY"


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_version(name: str) -> str:
    return importlib.metadata.version(name)


def _query_gpu_name() -> str:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        text=True,
    )
    names = [x.strip() for x in out.splitlines() if x.strip()]
    if names != [EXPECTED_DEVICE_NAME]:
        raise RuntimeError(f"VAST_DEVICE_NAME_MISMATCH:{names!r}:{EXPECTED_DEVICE_NAME!r}")
    return names[0]


def verify_static_runtime(root: pathlib.Path, instance_id: str) -> dict[str, Any]:
    if instance_id != EXPECTED_INSTANCE_ID:
        raise RuntimeError(f"VAST_INSTANCE_ID_MISMATCH:{instance_id!r}:{EXPECTED_INSTANCE_ID!r}")
    if tuple(sys.version_info[:3]) != EXPECTED_PYTHON:
        raise RuntimeError(f"PYTHON_VERSION_MISMATCH:{tuple(sys.version_info[:3])!r}:{EXPECTED_PYTHON!r}")
    shim = root / "replay_residual_textworld_py313_compat_v1.py"
    got_shim = _sha256_file(shim)
    if got_shim != COMPAT_SHIM_SHA256:
        raise RuntimeError(f"COMPAT_SHIM_SHA256_MISMATCH:{got_shim}")
    versions = {name: _package_version(name) for name in EXPECTED_PACKAGES if name != "torch"}
    import torch
    versions["torch"] = str(torch.__version__)
    if versions != EXPECTED_PACKAGES:
        raise RuntimeError(f"PACKAGE_VERSION_MISMATCH:{versions!r}:{EXPECTED_PACKAGES!r}")
    return {"package_versions": versions, "device_name": _query_gpu_name()}


def run_synthetic_reset() -> dict[str, Any]:
    import textworld
    from textworld import GameMaker, GameOptions
    from replay_residual_textworld_py313_compat_v1 import install_textworld_py313_eval_compat

    shim_provenance = install_textworld_py313_eval_compat()
    maker = GameMaker()
    room = maker.new_room("reset canary room")
    maker.set_player(room)
    token = maker.new(type="o", name="reset canary token")
    room.add(token)
    maker.set_quest_from_commands(["take reset canary token"])
    game = maker.build()
    with tempfile.TemporaryDirectory(prefix="plancarry-rr-v22-reset-canary-") as td:
        options = GameOptions()
        options.path = str(pathlib.Path(td) / "synthetic_reset_canary.z8")
        compiled = textworld.generator.compile_game(game, options)
        infos = textworld.EnvInfos(admissible_commands=True)
        env = textworld.start(compiled, infos)
        try:
            state = env.reset()
            if isinstance(state, tuple):
                state = state[0]
            observation = str(state)
            commands = list(getattr(state, "admissible_commands", []) or [])
        finally:
            env.close()
    if not observation.strip():
        raise RuntimeError("SYNTHETIC_RESET_EMPTY_OBSERVATION")
    if not commands:
        raise RuntimeError("SYNTHETIC_RESET_EMPTY_ADMISSIBLE_COMMANDS")
    return {
        "environment_reset": True,
        "initial_observation_nonempty": True,
        "admissible_commands_nonempty": True,
        "admissible_command_count": len(commands),
        "shim_provenance": shim_provenance,
    }


def atomic_json(path: pathlib.Path, obj: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError(f"REFUSE_EXISTING_CANARY_ATTESTATION:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".tmp.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, separators=(",", ":"))
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    root = pathlib.Path(args.root).resolve()
    runtime = verify_static_runtime(root, args.instance_id)
    reset = run_synthetic_reset()
    obj = {
        "kind": "REPLAYRESIDUAL_V22_RESET_COMPATIBILITY_CANARY",
        "technical_status": "PASS",
        "target_kind": TARGET_KIND,
        "attestation_contract_sha256": ATTESTATION_CONTRACT_SHA256,
        "compat_shim_sha256": COMPAT_SHIM_SHA256,
        "instance_id": EXPECTED_INSTANCE_ID,
        "device_name": runtime["device_name"],
        "python_version": ".".join(map(str, EXPECTED_PYTHON)),
        "package_versions": runtime["package_versions"],
        "study_cohort_access": STUDY_COHORT_ACCESS,
        "model_calls": MODEL_CALLS,
        "model_loads": 0,
        "environment_actions": ENVIRONMENT_ACTIONS,
        **reset,
    }
    atomic_json(pathlib.Path(args.output), obj)
    print(json.dumps({"status": "RESET_COMPATIBILITY_CANARY_PASS", "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
