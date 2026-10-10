#!/usr/bin/env python3
"""No-model independent-process ALFWorld PDDL reset/prefix/fork replay gate.

Only the 11 historically environment-inspected Pilot40/Binding180 overlap
games are eligible. Uses real TextWorld 1.7.0 + Fast Downward 20.6.4,
two separate OS Python processes per game. NO new TRAIN model inference,
qualification or permission to pass scientific BIND-v0.3 G0/G1.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ARCHIVE_SHA = "5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf"
MATRIX_SHA = "ea9376a6c86c41afb24dc00e14d5ff5849b44e4900e2f8a1ebfc60deea4201d5"
LEGACY_ROOT = "/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/"
EXPECTED_GAME_COUNT = 11


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def child_replay(path: Path, arm: str) -> dict:
    from fast_downward.interface import Atom
    from textworld.core import EnvInfos
    from textworld.envs.pddl.pddl import PddlEnv

    env = PddlEnv(EnvInfos(admissible_commands=True, facts=True, objective=True))
    try:
        env.load(str(path))
        env.reset()

        def snapshot():
            size = env.downward_lib.get_state_size()
            if not 0 < size < 10000:
                raise ValueError("Native Atom size out of audited bounds")
            entries = (Atom * size)()
            env.downward_lib.get_state(entries)
            state = env.state
            return {
                "native_atom_count": size,
                "native_atoms_sha256": digest([x.name for x in entries]),
                "logical_facts_sha256": digest(sorted(str(x) for x in state.get("_facts", ()))),
                "feedback_sha256": hashlib.sha256(str(state.get("feedback", "")).encode()).hexdigest(),
                "ordered_menu": list(state.get("admissible_commands", [])),
                "public_goal": bool(env._pddl_state.check_goal()),
            }

        def step(cmd):
            if cmd not in snapshot()["ordered_menu"]:
                raise ValueError("Native engine rejects action in common/fork prefix")
            env.step(cmd)
            return snapshot()

        reset = snapshot()
        looked = step("look")
        movements = [x for x in looked["ordered_menu"] if x.startswith("go to ")]
        if len(movements) < 3:
            raise ValueError("No matching real progress and two fork exits")
        progress = movements[0]
        post_progress = step(progress)
        if post_progress == reset:
            raise ValueError("Supposed progress did not change captured state")
        forks = [x for x in post_progress["ordered_menu"] if x.startswith("go to ") and x != progress]
        if len(forks) < 2:
            raise ValueError("No 2 legal distinct fork actions")
        chosen = forks[0 if arm == "A" else 1]
        after_fork = step(chosen)
        return {
            "pid": os.getpid(),
            "game_sha256": file_sha(path),
            "arm": arm,
            "prefix_actions": ["look", progress],
            "prefix_snapshots": [reset, looked, post_progress],
            "fork_action": chosen,
            "after_fork": after_fork,
            "engine_source": "real native PddlEnv and FastDownward Atom get_state",
        }
    finally:
        env.close()


def invoke_worker(py: str, script: str, game: Path, arm: str, exec_tmp: Path):
    e = dict(os.environ)
    for k in ("TMPDIR", "TMP", "TEMP"):
        e[k] = str(exec_tmp)
    # Two distinct subprocess interpreters. No shareable Python env refs.
    proc = subprocess.run(
        [py, script, "--child", str(game), arm],
        env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=90, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PDDL worker {arm} failed rc={proc.returncode}: {proc.stderr[-500:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def run_pinned(archive, root, manifest, exec_tmp, max_games):
    if file_sha(archive) != ARCHIVE_SHA:
        raise ValueError("Original public ALFWorld archive SHA mismatch")
    if file_sha(manifest) != MATRIX_SHA:
        raise ValueError("Historical inspected 11-game matrix SHA mismatch")
    if root.name != "json_2.1.1":
        raise ValueError("Wrong original ALFWorld game root")
    if not exec_tmp.is_dir() or os.statvfs(exec_tmp).f_flag & getattr(os, "ST_NOEXEC", 8):
        raise ValueError("Native Fast Downward temp must support library execution")
    records = json.loads(manifest.read_text())["per_game_overlap"]
    if len(records) != EXPECTED_GAME_COUNT or not 1 <= max_games <= EXPECTED_GAME_COUNT:
        raise ValueError("May inspect ONLY the original 11 environment-inspected games")
    results = []
    for row in records[:max_games]:
        old = row["game_path"]
        if not old.startswith(LEGACY_ROOT):
            raise ValueError("Invalid historical game namespace")
        rel = Path(old[len(LEGACY_ROOT):])
        if ".." in rel.parts or rel.parts[0] != "train" or rel.name != "game.tw-pddl":
            raise ValueError("Invalid historic game path")
        game = (root / rel).resolve()
        if not game.is_relative_to(root.resolve()):
            raise ValueError("Historical game outside source root")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(invoke_worker, sys.executable, str(Path(__file__).resolve()), game, "A", exec_tmp)
            fb = pool.submit(invoke_worker, sys.executable, str(Path(__file__).resolve()), game, "B", exec_tmp)
            a, b = fa.result(), fb.result()
        if a["pid"] == b["pid"]:
            raise ValueError("A/B used SAME OS process")
        if a["prefix_actions"] != b["prefix_actions"]:
            raise ValueError("Common prefix actions differ")
        if a["prefix_snapshots"] != b["prefix_snapshots"]:
            raise ValueError("Independent-process state/menu/feedback snapshots diverged")
        if a["fork_action"] == b["fork_action"]:
            raise ValueError("Different forks were not distinct")
        if a["after_fork"] == b["after_fork"]:
            raise ValueError("Native fork paths did not yield observable divergence")
        if a["game_sha256"] != b["game_sha256"]:
            raise ValueError("Different original source game bytes")
        results.append({
            "source_relative_path": str(rel),
            "game_sha256": a["game_sha256"],
            "separate_OS_processes": True,
            "common_prefix": a["prefix_actions"],
            "prefix_snapshots_sha256": digest(a["prefix_snapshots"]),
            "native_atom_counts": [x["native_atom_count"] for x in a["prefix_snapshots"]],
            "fork_A": a["fork_action"], "fork_B": b["fork_action"],
            "divergence_sha256_A": digest(a["after_fork"]),
            "divergence_sha256_B": digest(b["after_fork"]),
        })
    return {
        "schema": "plancarry.bind.real-pddl.independent-os-process-prefix.v1",
        "source": "EXACT_ORIGINAL_ALFWORLD_ARCHIVE",
        "source_zip_sha256": ARCHIVE_SHA,
        "historical_inspected_matrix_sha256": MATRIX_SHA,
        "games_verified": len(results),
        "real_native_textworld_pddl": True,
        "two_separate_OS_processes_per_game": True,
        "complete_rng_state_attested": False,
        "complete_historical_model_non_consumption_attested": False,
        "model_calls": 0,
        "science_gate": "NOT_AUTHORIZED",
        "results": results,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--child", nargs=2, metavar=("FILE", "ARM"))
    p.add_argument("--archive", type=Path)
    p.add_argument("--original-root", type=Path)
    p.add_argument("--historical-matrix", type=Path)
    p.add_argument("--exec-temp", type=Path)
    p.add_argument("--max-games", type=int, default=1)
    p.add_argument("--out", type=Path)
    x = p.parse_args()
    if x.child:
        print(canonical(child_replay(Path(x.child[0]), x.child[1])))
        return 0
    if not all([x.archive,x.original_root,x.historical_matrix,x.exec_temp,x.out]):
        raise SystemExit("Explicit verified source/backend arguments required")
    data = run_pinned(x.archive, x.original_root, x.historical_matrix, x.exec_temp, x.max_games)
    x.out.parent.mkdir(parents=True, exist_ok=True)
    x.out.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print(canonical({"status":"REAL_PDDL_PROCESS_ISOLATION_PREFIX_ONLY","games":data["games_verified"],
                     "native":True,"science_gate":"NOT_AUTHORIZED","full_rng":False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
