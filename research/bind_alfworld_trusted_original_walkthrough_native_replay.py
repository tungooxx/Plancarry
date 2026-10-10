#!/usr/bin/env python3
"""Trusted-only ALFWorld walkthrough -> real native PDDL action bridge.

The ORIGINAL game.tw-pddl embeds a privileged walkthrough with short human
object names ("sofa 1"). The real TextWorld 1.7 / Fast Downward 20.6.4 PddlEnv
admissible menu uses coordinate-encoded object IDs ("sofa_bar__plus_...").
This tool searches a bounded, source-oracle action-TYPE skeleton over legal
native actions, failing closed on missing or ambiguous unresolved routes, and
requires an actual native terminal PDDL goal/score. Original numerical object
IDs are NOT certified equivalent to encoded PDDL coordinates. No walkthrough or privileged hint is ever
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


def run_one(path: Path, task_sha256: str, max_nodes: int = 96) -> dict:
    """Verify existence of a native PDDL win matching the original action-TYPE
    skeleton; do not claim exact original numbered instance alias semantics.

    Privileged walkthrough and success-gated search are trusted verifier data
    only. The successful native trajectory MUST NOT become a "model-owned"
    plan or enter an LLM prompt as a source-generated plan.
    """
    from textworld.core import EnvInfos
    from textworld.envs.pddl.pddl import PddlEnv
    from fast_downward.interface import Atom
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
    if type(max_nodes) is not int or not 1<=max_nodes<=128:
        raise ValueError("Invalid bounded verification budget")
    expected_types=[normalized_original_command(c) for c in private_oracle]

    env=PddlEnv(EnvInfos(admissible_commands=True,objective=True))
    def reset_native_signature() -> tuple:
        n=env.downward_lib.get_state_size()
        if not 0<n<10000:
            raise ValueError("Invalid native PDDL state size")
        atoms=(Atom*n)()
        env.downward_lib.get_state(atoms)
        return (tuple(x.name for x in atoms),
                tuple(env.state.get("admissible_commands",[])),
                bool(env._pddl_state.check_goal()))
    try:
        env.load(str(path))
        env.reset()
        baseline=reset_native_signature()
        frontier=[()]          # tuples of exactly legal raw native actions
        expansions=0
        ambiguous_nodes=0
        verified=None
        while frontier and expansions<max_nodes:
            prefix=frontier.pop()
            expansions+=1
            env.reset()
            if reset_native_signature()!=baseline:
                raise ValueError("Repeated native reset is not exact")
            score=0
            done=False
            for action in prefix:
                if action not in env.state.get("admissible_commands",[]):
                    raise ValueError("Deterministic replay lost actual legal action")
                _,score,done=env.step(action)
            if len(prefix)==len(private_oracle):
                if done and score==1 and env._pddl_state.check_goal():
                    verified=prefix
                    break
                continue
            if done or env._pddl_state.check_goal():
                continue
            menu=env.state.get("admissible_commands")
            if type(menu) is not list or len(menu)!=len(set(menu)):
                raise ValueError("Native admissible menu corrupted")
            matches=[x for x in menu
                     if normalized_native_command(x)==expected_types[len(prefix)]]
            if len(matches)>1:
                ambiguous_nodes+=1
            # Source game instance numbers are NOT blindly treated as
            # equivalent to coordinate-encoded PDDL IDs. Branch and demand
            # actual native terminal goal for any candidate accepted.
            for candidate in reversed(matches):
                frontier.append(prefix+(candidate,))
        if verified is None:
            raise ValueError("No source-type-skeleton native terminal goal within bounded search")
        return {
            "game_sha256":report["source_game_sha256"],
            "original_public_task_sha256":report["task_instruction_sha256"],
            "privileged_original_oracle_action_count":len(private_oracle),
            "executed_native_steps":len(verified),
            "bounded_native_prefix_expansions":expansions,
            "ambiguous_native_type_match_nodes_encountered":ambiguous_nodes,
            "native_terminal_goal_reached":True,
            "native_terminal_score":1,
            "native_episode_done":True,
            "verified_claim":"EXISTS_PDDL_GOAL_ROUTE_WITH_ORIGINAL_ORACLE_ACTION_TYPE_SKELETON",
            "original_numbered_instance_aliases_proven_equivalent":False,
            "safe_to_expose_oracle_or_native_solution_to_agent":False,
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
            record["status"]="NATIVE_ORIGINAL_TYPE_SKELETON_GOAL_VERIFIED"
        except (ValueError,RuntimeError,KeyError,TypeError) as exc:
            record={
                "game_sha256":digest,
                "original_public_task_sha256":pub["task_instruction_sha256"],
                "status":"NATIVE_ORIGINAL_TYPE_SKELETON_NOT_VERIFIED",
                "failure_type":type(exc).__name__,
                "failure_sha256":hashlib.sha256(str(exc).encode()).hexdigest(),
                "model_authored_source_plan":False,
            }
        record["original_game_relative_path"]=str(relative)
        results.append(record)
    count=sum(x["status"]=="NATIVE_ORIGINAL_TYPE_SKELETON_GOAL_VERIFIED" for x in results)
    report={
        "schema":"plancarry.bind.native-original-oracle-to-pddl-goal-attestation.v1",
        "source_archive_sha256":ORIGINAL_ARCHIVE_SHA,
        "cohort":"11 previously environmentally inspected source games ONLY",
        "cases_checked":len(results),
        "native_goal_verified_count":count,
        "cases":results,
        "private_original_oracle_only_used_by_trusted_verifier":True,
        "source_oracle_ever_emitted_in_report":False,
        "native_verified_routes_ever_exposed_as_model_owned":False,
        "original_instance_ordinal_to_encoded_PDDL_ID_equivalence_proven":False,
        "model_authored_source_plan_count":0,
        "realized_llm_calls":0,
        "scientific_gate":"NOT_AUTHORIZED",
        "full_native_rng_clone_attested":False,
        "search_uses_private_oracle_skeleton_and_goal_criterion":True,
        "no_false_model_effect_claim":True,
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "status":"REAL_ORIGINAL_ALFWORLD_NATIVE_ACTION_TYPE_SKELETON_GOAL_AUDIT",
        "verified":count,
        "checked":len(results),
        "failures":[
            {"case":j,"type":x.get("failure_type")}
            for j,x in enumerate(results) if x["status"]!="NATIVE_ORIGINAL_TYPE_SKELETON_GOAL_VERIFIED"
        ],
        "oracle_shared_with_model":False,
        "G0_CERTIFIED":False,
    },sort_keys=True),flush=True)
    return 0 if count==len(results) else 2


if __name__=="__main__":
    raise SystemExit(main())
