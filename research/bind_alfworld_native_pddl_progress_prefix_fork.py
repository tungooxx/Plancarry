#!/usr/bin/env python3
"""CPU native ALFWorld PDDL nontrivial shared-progress-action A/B proof.

Uses previously inspected 11 Pilot40/BIND180 overlap games, genuine
TextWorld/PddlEnv and independent Fast Downward libs. Both branches
execute LOOK then same legal GO TO movement, and then divergent actions.
No LLM, GPU, source qualification, confirmation or scientific G0 claim.
"""
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path

def run_game(path:Path)->dict:
    from fast_downward.interface import Atom
    from textworld.core import EnvInfos
    from textworld.envs.pddl.pddl import PddlEnv
    def new_env():
        e=PddlEnv(EnvInfos(admissible_commands=True,facts=True,objective=True))
        e.load(str(path));e.reset()
        return e
    def snapshot(e):
        n=e.downward_lib.get_state_size()
        if not 0<n<10000: raise ValueError("Invalid native state size")
        atoms=(Atom*n)();e.downward_lib.get_state(atoms)
        return {"atoms":[v.name for v in atoms],
            "logical_facts":sorted(map(str,e.state.get("_facts",[]))),
            "feedback":str(e.state.get("feedback","")),
            "menu":list(e.state.get("admissible_commands",[])),
            "goal":bool(e._pddl_state.check_goal())}
    def digest(obj):
        return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def step(e,action):
        if action not in snapshot(e)["menu"]:raise ValueError("Non-admissible action")
        e.step(action)
        return snapshot(e)
    a,b=new_env(),new_env()
    try:
        if a.downward_lib is b.downward_lib:raise ValueError("Aliased native libs")
        pre_a,pre_b=snapshot(a),snapshot(b)
        if pre_a!=pre_b:raise ValueError("Reset mismatch")
        if step(a,"look")!=step(b,"look"):raise ValueError("Look-prefix mismatch")
        movements=[v for v in snapshot(a)["menu"] if v.startswith("go to ")]
        if len(movements)<3:raise ValueError("Not enough progress/fork actions")
        progress=movements[0]
        pa,pb=step(a,progress),step(b,progress)
        if pa!=pb:raise ValueError("Common real progress action mismatch")
        if pa==pre_a:raise ValueError("Real progress action has no effect")
        moves=[v for v in pa["menu"] if v.startswith("go to ") and v!=progress]
        if len(moves)<2:raise ValueError("No two alternate legal fork actions")
        saved_b=snapshot(b)
        fa=step(a,moves[0])
        if snapshot(b)!=saved_b:raise ValueError("A transition changed B")
        fb=step(b,moves[1])
        if fa==fb:raise ValueError("Different fork actions same final snapshot")
        return {"game_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "initial_native_atoms":len(pre_a["atoms"]),
            "initial_sha256":digest(pre_a),
            "common_prefix":["look",progress],
            "progress_action":progress,
            "progress_sha256":digest(pa),
            "fork_A":moves[0],
            "fork_B":moves[1],
            "fork_A_sha256":digest(fa),
            "fork_B_sha256":digest(fb),
            "independent_native_handles":True,
            "identical_nontrivial_prefix":True,
            "B_unchanged_during_A_fork":True,
            "fork_state_diverged":True}
    finally:
        a.close();b.close()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--original-root",type=Path,required=True)
    parser.add_argument("--historical-inspected-matrix",type=Path,required=True)
    parser.add_argument("--exec-temp",type=Path,required=True)
    parser.add_argument("--max-games",type=int,default=11)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    args.exec_temp.mkdir(parents=True,exist_ok=True)
    if os.statvfs(args.exec_temp).f_flag & getattr(os,"ST_NOEXEC",8):
        raise ValueError("NOEXEC temp prevents real native PDDL shared library")
    for k in ("TMPDIR","TMP","TEMP"):os.environ[k]=str(args.exec_temp.resolve())
    import tempfile
    tempfile.tempdir=None
    root=args.original_root.resolve()
    if root.name!="json_2.1.1":raise ValueError("Wrong original source")
    meta=json.loads(args.historical_inspected_matrix.read_text())
    items=meta["per_game_overlap"]
    if len(items)!=11 or not 1<=args.max_games<=11:
        raise ValueError("Only 11 historically inspected original games")
    old="/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/"
    reports=[]
    for x in items[:args.max_games]:
        path=x["game_path"]
        if not path.startswith(old):raise ValueError("Invalid game identity")
        rel=Path(path[len(old):])
        if ".." in rel.parts or rel.parts[0]!="train" or rel.name!="game.tw-pddl":
            raise ValueError("Invalid original game path")
        game=(root/rel).resolve()
        if not game.is_relative_to(root):raise ValueError("Out of source root")
        rec=run_game(game)
        rec["historically_inspected_game_relative_path"]=str(rel)
        reports.append(rec)
    output={"schema":"plancarry.bind.alfworld.native-pddl-nontrivial-prefix.v1",
        "source_population":"11 previously environmentally inspected Pilot40/BIND180 games",
        "native_backend":"TextWorld 1.7.0 + fast-downward-textworld 20.6.4",
        "game_count":len(reports),"results":reports,
        "model_calls":0,"scientific_gate":"NOT_AUTHORIZED",
        "G0_CERTIFIED":False,"complete_native_rng_witness":False}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":"REAL_NATIVE_NONTRIVIAL_PREFIX_PASS",
        "games":len(reports),
        "atom_counts":[r["initial_native_atoms"] for r in reports],
        "all_nontrivial_prefix_and_isolation":True,
        "science":"NOT_AUTHORIZED","model_calls":0},sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main())
