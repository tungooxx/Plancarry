#!/usr/bin/env python3
"""CPU original ALFWorld PDDL Python RNG channel perturbation probe.

Tests only 11 historically ENVIRONMENT-inspected Pilot40/Binding180 games.
In two *separate* OS Python processes per game, deliberately set disjoint
Python random and NumPy RNG streams, burn different numbers of random draws,
and replay the *same* 4 valid native game actions. Pinned native Atom/facts/
ordered public commands/feedback equality is the measured outcome.

This is a limited EXTERNAL PYTHON RNG perturbation test. Passing is NOT a
complete Fast Downward C++ RNG/internal-state attestation, a reset-clone
certificate, an accepted BIND v0.3 G0 or G1 execution authority.
No model, paid GPU, new TRAIN game or confirmation.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys

ZIP_SHA = "5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf"
MATRIX_SHA = "ea9376a6c86c41afb24dc00e14d5ff5849b44e4900e2f8a1ebfc60deea4201d5"
OLD_ROOT = "/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/"
REQUIRED_SHAS = {
    "textworld.envs.pddl.textgen": "f947c1a0add69fe3b309c71e9904a4990af934ed479296fb10972effa8c43f5e",
    "textworld.envs.pddl.pddl": "3795f5fb7471c7a4551e137267785ffb3e21e49653d17491d6be963b41f454b4",
    "textworld.envs.pddl.logic": "7c5ea3b0ddc21dc105c1e5c5979006a9d47365b556c10c048973bd62eb0ad35e",
    "fast_downward.interface": "c5c23ec7d6d8acd845fb6788c8edd01f7d527ee1f0148ba333e7bacc517c151b",
    "fast_downward.native": "339350d63ca18f5c63d4a12ab72490d33b5af2af2bd7f4865d264ebdcbd1d3be",
}

def file_sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def canon(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def digest(x):
    return hashlib.sha256(canon(x).encode()).hexdigest()

def pinned_runtime():
    import fast_downward
    for mod, expected in REQUIRED_SHAS.items():
        if mod == "fast_downward.native":
            f=Path(fast_downward.__file__).parent/"libdownward.so"
        else:
            f=Path(importlib.util.find_spec(mod).origin)
        if file_sha(f)!=expected:
            raise ValueError("Native RNG stress runtime code/ABI bytes are UNATTESTED: "+mod)
    return REQUIRED_SHAS

def child(game: Path, seed: int, burn: int):
    if seed < 0 or burn < 0:
        raise ValueError("Invalid external RNG perturbation")
    import numpy as np
    from fast_downward.interface import Atom
    from textworld.core import EnvInfos
    from textworld.envs.pddl.pddl import PddlEnv
    random.seed(seed)
    np.random.seed(seed % (2**32-1))
    rng_initial = digest({"python_random": repr(random.getstate()),"numpy":repr(np.random.get_state())})
    env=PddlEnv(EnvInfos(admissible_commands=True,facts=True,objective=True))
    try:
        env.load(str(game))
        env.reset()
        def snap():
            size=env.downward_lib.get_state_size()
            if not 0<size<10000:
                raise ValueError("Native state out of pinned bounds")
            atoms=(Atom*size)()
            env.downward_lib.get_state(atoms)
            state=env.state
            return {
              "native_atoms_sha256":digest([z.name for z in atoms]),
              "native_atoms_count":size,
              "pddl_facts_sha256":digest(sorted(str(x) for x in state.get("_facts",()))),
              "ordered_commands":list(state.get("admissible_commands",[])),
              "feedback_sha256":hashlib.sha256(str(state.get("feedback","")).encode()).hexdigest(),
              "goal":bool(env._pddl_state.check_goal()),
            }
        def disturb():
            # Verify external streams really differ without leaking their
            # state into the model-facing simulator projection.
            for _ in range(burn):
                random.random()
                np.random.random()
        trace=[snap()]
        disturb()
        def step(action):
            if action not in trace[-1]["ordered_commands"]:
                raise ValueError("Action not in verified native public menu")
            env.step(action)
            trace.append(snap())
            disturb()
        step("look")
        moves=[x for x in trace[-1]["ordered_commands"] if x.startswith("go to ")]
        if len(moves)<3:
            raise ValueError("Missing historically observed native route choices")
        step(moves[0])
        if (trace[-1]["native_atoms_sha256"]==trace[1]["native_atoms_sha256"]
                and trace[-1]["pddl_facts_sha256"]==trace[1]["pddl_facts_sha256"]):
            raise ValueError("Movement failed to change native logical state")
        # Exercise another information-only action *after* true progression.
        step("look")
        futures=[x for x in trace[-1]["ordered_commands"] if x.startswith("go to ") and x!=moves[0]]
        if not futures:
            raise ValueError("No further real game action")
        step(futures[0])
        if len(trace)!=5:
            raise AssertionError("Expected reset + 4 real actions")
        return {
            "game_sha256":file_sha(game),
            "seed":seed,
            "burn_per_milestone":burn,
            "rng_initial":rng_initial,
            "rng_final":digest({"python_random":repr(random.getstate()),"numpy":repr(np.random.get_state())}),
            "actual_actions":["look", moves[0],"look",futures[0]],
            "native_trace":trace,
            "backend":"TextWorld PDDL and Fast Downward native actual apply_operator",
        }
    finally:
        env.close()

def run_worker(py, script, game, seed, burn, exec_tmp):
    env=dict(os.environ)
    for k in ("TMPDIR","TMP","TEMP"):
        env[k]=str(exec_tmp)
    proc=subprocess.run([py,script,"--child",str(game),str(seed),str(burn)],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                        check=False,timeout=90,env=env)
    if proc.returncode:
        raise RuntimeError("Pinned PDDL child failed rc="+str(proc.returncode)+" "+proc.stderr[-400:])
    return json.loads(proc.stdout.strip().splitlines()[-1])

def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--child",nargs=3)
    pa.add_argument("--archive",type=Path)
    pa.add_argument("--original-root",type=Path)
    pa.add_argument("--historical-matrix",type=Path)
    pa.add_argument("--exec-temp",type=Path)
    pa.add_argument("--max-games",type=int,default=1)
    pa.add_argument("--output",type=Path)
    args=pa.parse_args()
    if args.child:
        print(canon(child(Path(args.child[0]),int(args.child[1]),int(args.child[2]))))
        return 0
    if not all((args.archive,args.original_root,args.historical_matrix,args.exec_temp,args.output)):
        raise SystemExit("All exact original ALFWorld provenance and output paths required")
    pin=pinned_runtime()
    if file_sha(args.archive)!=ZIP_SHA or file_sha(args.historical_matrix)!=MATRIX_SHA:
        raise ValueError("Original archive or historical used-game identity tampered")
    root=args.original_root.resolve()
    if root.name!="json_2.1.1":
        raise ValueError("Unexpected ALFWorld original extraction root")
    if os.statvfs(args.exec_temp).f_flag & getattr(os,"ST_NOEXEC",8):
        raise ValueError("Fast Downward shared library execution is disabled")
    rows=json.loads(args.historical_matrix.read_text())["per_game_overlap"]
    if len(rows)!=11 or not 1<=args.max_games<=11:
        raise ValueError("Never expand beyond the historical 11 already inspected")
    results=[]
    for x in rows[:args.max_games]:
        old=x["game_path"]
        if not old.startswith(OLD_ROOT):raise ValueError("Invalid historical name")
        relative=Path(old[len(OLD_ROOT):])
        if ".." in relative.parts or relative.parts[0]!="train" or relative.name!="game.tw-pddl":
            raise ValueError("Wrong historical game identity")
        game=(root/relative).resolve()
        if not game.is_relative_to(root):raise ValueError("Source path escaped root")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as q:
            one=q.submit(run_worker,sys.executable,str(Path(__file__).resolve()),game,0,2,args.exec_temp)
            two=q.submit(run_worker,sys.executable,str(Path(__file__).resolve()),game,987654321,103,args.exec_temp)
            a,b=one.result(),two.result()
        if a["rng_initial"]==b["rng_initial"] or a["rng_final"]==b["rng_final"]:
            raise ValueError("RNG perturbation control was ineffective")
        if a["actual_actions"]!=b["actual_actions"]:
            raise ValueError("External RNG perturbed legal native action sequence")
        if a["native_trace"]!=b["native_trace"]:
            raise ValueError("External RNG perturbed native observable state/feedback")
        if a["game_sha256"]!=b["game_sha256"]:
            raise ValueError("Game bytes changed across native workers")
        results.append({
            "game_relative_path":str(relative),
            "game_sha256":a["game_sha256"],
            "same_native_action_sequence":a["actual_actions"],
            "native_trace_sha256":digest(a["native_trace"]),
            "native_atoms_count":[v["native_atoms_count"] for v in a["native_trace"]],
            "external_rng_initial_state_distinct":True,
            "external_rng_final_state_distinct":True,
            "native_trace_identical_under_external_rng_perturbation":True,
        })
    report={
        "schema":"plancarry.bind.native-pddl.python-rng-channel-perturbation.v1",
        "source":"original exact ALFWorld PDDL 11 historically inspected only",
        "original_archive_sha256":ZIP_SHA,
        "historical_inspected_matrix_sha256":MATRIX_SHA,
        "runtime_source_and_binary_sha256":pin,
        "games":len(results),
        "external_rng_channels_tested":["Python random global","NumPy legacy global"],
        "external_rng_perturbations":{"A":{"seed":0,"burn_per_milestone":2},"B":{"seed":987654321,"burn_per_milestone":103}},
        "all_external_rng_channels_distinct_and_native_traces_equal":True,
        "full_Cplusplus_native_RNG_or_python_object_state_attested":False,
        "historical_model_use_ledger_complete":False,
        "scientific_gate":"NOT_AUTHORIZED",
        "G0_CERTIFIED":False,"model_calls":0,"paid_GPU_calls":0,
        "results":results}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(canon({"status":"NATIVE_EXTERNAL_PYTHON_RNG_STRESS_PASS_ONLY",
                 "games":len(results),"full_native_rng_certified":False,
                 "science_gate":"NOT_AUTHORIZED"}))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
