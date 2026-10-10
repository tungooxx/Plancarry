#!/usr/bin/env python3
"""Trusted-only ALFWorld walkthrough -> real native PDDL action bridge.

The ORIGINAL game.tw-pddl embeds a privileged walkthrough with short human
object names ("sofa 1"). The real TextWorld 1.7 / Fast Downward 20.6.4 PddlEnv
admissible menu uses coordinate-encoded object IDs ("sofa_bar__plus_...").
This tool checks whether each original trusted walkthrough action uniquely
maps to an actually admissible native action, executes it, and verifies actual
native terminal PDDL goal/score. No walkthrough or privileged hint is ever
returned to an evaluated agent or included in its prompt.

Research engineering ONLY on the 11 ALREADY historically environment-inspected
Pilot40/Binding180 original TRAIN games. It DOES NOT produce model-owned
source plans, demonstrate A/B causal effect, or certify native RNG state/G0.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

ORIGINAL_ARCHIVE_SHA="5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf"
ORIGINAL_PATH_ROOT="/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/"

_NATIVE_ENTITY=re.compile(r"\b([a-zA-Z0-9]+)_bar_[a-zA-Z0-9_+-]+")
_WALKTHROUGH_ENTITY=re.compile(r"\b([a-zA-Z]+)\s+\d+")


def normalized_native_command(value: str) -> str:
    if type(value) is not str or len(value)>512:
        raise ValueError("Invalid native command")
    return _NATIVE_ENTITY.sub(lambda match:match.group(1).lower(),value.lower())


def normalized_original_command(value: str) -> str:
    if type(value) is not str or len(value)>512:
        raise ValueError("Invalid original walkthrough step")
    return _WALKTHROUGH_ENTITY.sub(lambda match:match.group(1).lower(),value.lower())


def unique_native_match(original: str, native_menu: list[str]) -> str:
    """Strict exact normalized action identity, fail closed for 0 or >1 hits.

    Index removal is acceptable solely for trusted oracle engineering
    because the real PDDL menu and terminal native goal are independently
    checked. It is NOT a semantic proof of instance number equivalence.
    """
    if type(native_menu) is not list or len(set(native_menu)) != len(native_menu):
        raise ValueError("Untrusted native action menu")
    expect=normalized_original_command(original)
    matches=[x for x in native_menu if normalized_native_command(x)==expect]
    if len(matches)!=1:
        raise ValueError(f"Trusted oracle normalized command match count={len(matches)}")
    return matches[0]


def run_one(path: Path, task_sha256: str) -> dict:
    from textworld.core import EnvInfos
    from textworld.envs.pddl.pddl import PddlEnv
    from bind_alfworld_original_public_task import original_public_task

    report=original_public_task(path)
    if report["task_instruction_sha256"]!=task_sha256:
        raise ValueError("Mismatch original public task digest")
    private_game=json.loads(path.read_bytes())
    if private_game.get("solvable") is not True:
        raise ValueError("Original source not declared solvable")
    private_oracle=private_game.get("walkthrough")
    if type(private_oracle) is not list or not 0<len(private_oracle)<=80:
        raise ValueError("Missing original private oracle route")
    # private_oracle is used in trusted local verifier ONLY, not returned.
    env=PddlEnv(EnvInfos(admissible_commands=True,objective=True))
    try:
        env.load(str(path))
        env.reset()
        steps=0
        native_unique=[]
        for item in private_oracle:
            if env._pddl_state.check_goal():
                raise ValueError("Already goal before last original walkthrough step")
            menu=env.state.get("admissible_commands")
            command=unique_native_match(item, menu)
            state, score, done=env.step(command)
            steps+=1
            native_unique.append(len(set(menu))==len(menu))
            if steps<len(private_oracle) and (done or env._pddl_state.check_goal()):
                raise ValueError("Oracle claimed unnecessary post-goal steps")
        if not env._pddl_state.check_goal() or score != 1 or not done:
            raise ValueError("Original walkthrough not native terminal goal with score1")
        return {
            "game_sha256":report["source_game_sha256"],
            "original_public_task_sha256":report["task_instruction_sha256"],
            "privileged_oracle_step_count":len(private_oracle),
            "executed_native_steps":steps,
            "each_native_step_unique_legal_menu_match":all(native_unique),
            "native_terminal_goal_reached":True,
            "native_terminal_score":1,
            "native_episode_done":True,
            "safe_to_expose_oracle_to_agent":False,
            "model_authored_source_plan":False,
        }
    finally:
        env.close()


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--original-root",type=Path,required=True)
    p.add_argument("--old-inspected-matrix",type=Path,required=True)
    p.add_argument("--original-790-identity-manifest",type=Path,required=True)
    p.add_argument("--exec-temp",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--max-games",type=int,default=11)
    args=p.parse_args()
    args.exec_temp.mkdir(parents=True,exist_ok=True)
    if os.statvfs(args.exec_temp).f_flag & getattr(os,"ST_NOEXEC",8):
        raise ValueError("Native PDDL loader requires exec-capable TMPDIR")
    for k in ("TMPDIR","TMP","TEMP"):
        os.environ[k]=str(args.exec_temp.resolve())
    import tempfile
    tempfile.tempdir=None
    root=args.original_root.resolve()
    if root.name!="json_2.1.1" or not 1<=args.max_games<=11:
        raise ValueError("Original ALFWorld source population violated")
    matrix=json.loads(args.old_inspected_matrix.read_text())
    games=matrix["per_game_overlap"]
    if len(games)!=11:
        raise ValueError("Expected 11 previously inspected source games")
    manifest=json.loads(args.original_790_identity_manifest.read_text())
    if manifest.get("dataset_sha256")!=ORIGINAL_ARCHIVE_SHA:
        raise ValueError("Original source archive mismatch")
    refs={x["relative_path"]:x for x in manifest["source_files_sorted"]}
    if len(refs)!=790:
        raise ValueError("Expected original 790 source hash manifest")
    results=[]
    for case in games[:args.max_games]:
        historical=case["game_path"]
        if not historical.startswith(ORIGINAL_PATH_ROOT):
            raise ValueError("Historical absolute source identity invalid")
        relative=Path(historical[len(ORIGINAL_PATH_ROOT):])
        file=(root/relative).resolve()
        if not file.is_relative_to(root) or str(relative) not in refs:
            raise ValueError("Historical original game path missing")
        raw=file.read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if digest!=refs[str(relative)]["game_sha256"]:
            raise ValueError("Original game byte source mismatch")
        from bind_alfworld_original_public_task import original_public_task
        pub=original_public_task(file)
        try:
            record=run_one(file,pub["task_instruction_sha256"])
            record["status"]="NATIVE_ORIGINAL_WALKTHROUGH_GOAL_VERIFIED"
        except (ValueError,RuntimeError,KeyError,TypeError) as exc:
            record={
                "game_sha256":digest,
                "original_public_task_sha256":pub["task_instruction_sha256"],
                "status":"NATIVE_ORIGINAL_WALKTHROUGH_NOT_VERIFIED",
                "failure_type":type(exc).__name__,
                "failure_sha256":hashlib.sha256(str(exc).encode()).hexdigest(),
                "model_authored_source_plan":False,
            }
        record["original_game_relative_path"]=str(relative)
        results.append(record)
    count=sum(x["status"]=="NATIVE_ORIGINAL_WALKTHROUGH_GOAL_VERIFIED" for x in results)
    report={
        "schema":"plancarry.bind.native-original-oracle-to-pddl-goal-attestation.v1",
        "source_archive_sha256":ORIGINAL_ARCHIVE_SHA,
        "cohort":"11 previously environmentally inspected source games ONLY",
        "cases_checked":len(results),
        "native_goal_verified_count":count,
        "cases":results,
        "private_original_oracle_only_used_by_trusted_verifier":True,
        "source_oracle_ever_emitted_in_report":False,
        "model_authored_source_plan_count":0,
        "realized_llm_calls":0,
        "scientific_gate":"NOT_AUTHORIZED",
        "full_native_rng_clone_attested":False,
        "no_false_model_effect_claim":True,
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "status":"REAL_ORIGINAL_ALFWORLD_NATIVE_WALKTHROUGH_GOAL_AUDIT",
        "verified":count,
        "checked":len(results),
        "failures":[
            {"case":j,"type":x.get("failure_type")}
            for j,x in enumerate(results) if x["status"]!="NATIVE_ORIGINAL_WALKTHROUGH_GOAL_VERIFIED"
        ],
        "oracle_shared_with_model":False,
        "G0_CERTIFIED":False,
    },sort_keys=True),flush=True)
    return 0 if count==len(results) else 2


if __name__=="__main__":
    raise SystemExit(main())
