#!/usr/bin/env python3
"""Native ALFWorld PDDL A/B prefix/isolation engineering preflight.

REAL TextWorld 1.7.0 + fast-downward-textworld 20.6.4.
Uses ONLY historically already environment-inspected Pilot40/Binding180
overlap games from an existing named research audit; no LLM calls.
The actual native Downward get_state() Atom array, TextWorld public
action order/feedback and logical facts are compared across independent
PddlEnv constructor instances. No proxy 'hash of sorted actions' claim.
Not a PDDL state clone proof, certified RNG witness or science G0 PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def content_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_probe(game: Path) -> dict:
    import textworld
    from textworld.core import EnvInfos
    from textworld.envs.pddl.pddl import PddlEnv
    from fast_downward.interface import Atom

    infos = EnvInfos(admissible_commands=True, facts=True, objective=True)
    def make():
        env = PddlEnv(infos)
        env.load(str(game))
        env.reset()
        return env

    def state(env) -> dict:
        size = env.downward_lib.get_state_size()
        if size <= 0 or size >= 10000:
            raise ValueError("Invalid native Downward state size")
        array = (Atom * size)()
        env.downward_lib.get_state(array)
        return {
            "native_downward_atom_names": [item.name for item in array],
            "logical_state_facts": sorted(map(str, env.state.get("_facts", []))),
            "ordered_commands": list(env.state.get("admissible_commands", [])),
            "raw_feedback": str(env.state.get("feedback", "")),
            "native_goal": bool(env._pddl_state.check_goal()),
        }

    def digest(value: dict) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    a = make()
    b = make()
    try:
        if a.downward_lib is b.downward_lib:
            raise ValueError("PddlEnv native library handles are shared")
        pre_a, pre_b = state(a), state(b)
        if pre_a != pre_b:
            raise ValueError("Native reset state/observation/commands differ")
        if "look" not in pre_a["ordered_commands"]:
            raise ValueError("Common-prefix look is not admissible")
        a.step("look")
        b.step("look")
        post_a, post_b = state(a), state(b)
        if post_a != post_b:
            raise ValueError("Native common-prefix state/observation/commands differ")
        targets = [c for c in post_a["ordered_commands"] if c.startswith("go to ")]
        if not targets:
            raise ValueError("No legal action available for fork")
        b_baseline = state(b)
        a.step(targets[0])
        a_after, b_after = state(a), state(b)
        if b_after != b_baseline:
            raise ValueError("A's native transition changed B")
        if a_after == b_after:
            raise ValueError("A's native transition did not produce meaningful divergence")
        return {
            "game_sha256": content_sha(game),
            "initial_native_atoms": len(pre_a["native_downward_atom_names"]),
            "initial_legal_command_count": len(pre_a["ordered_commands"]),
            "initial_projection_sha256": digest(pre_a),
            "prefix_action": "look",
            "post_prefix_projection_sha256": digest(post_a),
            "A_post_fork_projection_sha256": digest(a_after),
            "B_post_fork_projection_sha256": digest(b_after),
            "distinct_native_handles": True,
            "common_prefix_exact_match": True,
            "B_unchanged_after_A_fork": True,
            "A_B_diverged_after_fork": True,
            "science_status": "ENGINEERING_PRECHECK_ONLY_NOT_G0_CERTIFIED",
        }
    finally:
        a.close()
        b.close()


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--previously-inspected-matrix",type=Path,required=True)
    parser.add_argument("--max-games",type=int,default=4)
    parser.add_argument("--exec-tmpdir",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()

    # The host's /tmp can be mounted NOEXEC, which makes libdownward.so fail.
    args.exec_tmpdir.mkdir(parents=True,exist_ok=True)
    if os.statvfs(args.exec_tmpdir).f_flag & getattr(os,"ST_NOEXEC",8):
        print(json.dumps({"status":"BLOCKED_NOEXEC_PDDL_TEMP"}))
        return 2
    os.environ["TMPDIR"] = str(args.exec_tmpdir.resolve())
    os.environ["TMP"] = os.environ["TMPDIR"]
    os.environ["TEMP"] = os.environ["TMPDIR"]
    import tempfile
    tempfile.tempdir = None

    try:
        matrix=json.loads(args.previously_inspected_matrix.read_bytes())
        prior=matrix["per_game_overlap"]
        if args.max_games < 1 or args.max_games > 11 or len(prior) != 11:
            raise ValueError("Only bounded historically-inspected Pilot40/Binding180 overlap cases allowed")
        root=args.source_root.resolve()
        if root.name!="json_2.1.1":
            raise ValueError("Wrong ALFWorld source root")
        old="/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/"
        reports=[]
        for item in prior[:args.max_games]:
            oldpath=item["game_path"]
            if not oldpath.startswith(old):
                raise ValueError("Missing original game identity")
            name=oldpath[len(old):]
            rel=Path(name)
            if rel.parts[0]!="train" or rel.name!="game.tw-pddl" or ".." in rel.parts:
                raise ValueError("Unexpected historical source member")
            game=(root/rel).resolve()
            if not game.is_relative_to(root) or not game.is_file():
                raise ValueError("Original restored game unavailable")
            result=native_probe(game)
            result["historically_inspected_game_relative_path"]=name
            result["prior_pilot_environment_inspection_job"]="local_7bd88fb99ccd406e"
            reports.append(result)
    except (KeyError,ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({"status":"BLOCKED_PDDL_ENGINEERING_PRECHECK","reason":str(exc)[:350]}))
        return 2

    report={
        "schema":"plancarry.bind.alfworld.real-pddl-native-prefix-check.v1",
        "science_status":"NOT_AUTHORIZED",
        "real_backend":"TextWorld-1.7.0 + fast-downward-textworld-20.6.4",
        "source_archive_sha256":"5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf",
        "historical_considered_source":"Previously environment-inspected only; no claim global non-consumption",
        "game_count":len(reports),
        "results":reports,
        "model_calls":0,
        "G0_CERTIFIED":False,
        "full_rng_state_authority":False,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":"REAL_PDDL_PREFIX_ENGINEERING_PASS","game_count":len(reports),
      "all_native_reset_equal":all(x["common_prefix_exact_match"] for x in reports),
      "all_B_unchanged_at_fork":all(x["B_unchanged_after_A_fork"] for x in reports),
      "native_atom_counts":[x["initial_native_atoms"] for x in reports],
      "scientific_gate":"NOT_AUTHORIZED","report_file":str(args.output)},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
