#!/usr/bin/env python3
"""Integrate strongest DIRECT_REMINDER control with original native ALFWorld PDDL.

Engineering prompt-integration audit on ONLY previously environment-inspected
Pilot40/BIND180 11 games. Real native TextWorld/PddlEnv instances, shared
actual information/movement prefix and two legal later-fork commands.

The two 'donor source plans' are MECHANICALLY CHOSEN placeholders and HAVE NOT
been authored/succeeded by any model. A public task *descriptor* parsed from
historical directory names is NOT the official natural-language ALFWorld goal.
Never classify this preflight as G0/G1/G2/G3 model outcome evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from bind_strong_direct_reminder_matched_control import (
    SourcePlan, MatchedPair, reciprocal_preflight,
)

OLD_ROOT="/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/"
EXPECTED_ARCHIVE="5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def descriptor(path: Path) -> str:
    family=path.parent.parent.name
    m=re.fullmatch(r"pick_and_place_simple-(.+?)-None-(.+)-\d+",family)
    if m is None:
        raise ValueError("Invalid original task family metadata")
    # Descriptive task identity ONLY. Not an attested public agent instruction.
    return f"Source task descriptor: pick_and_place_simple; object_type={m[1]}; target_type={m[2]}"


def run_case(file: Path) -> dict:
    from fast_downward.interface import Atom
    from textworld.core import EnvInfos
    from textworld.envs.pddl.pddl import PddlEnv

    def initialize():
        e=PddlEnv(EnvInfos(admissible_commands=True,facts=True,objective=True))
        e.load(str(file))
        e.reset()
        return e

    def native(e):
        n=e.downward_lib.get_state_size()
        if not 0<n<10000:raise ValueError("Native state unreasonable")
        values=(Atom*n)()
        e.downward_lib.get_state(values)
        return {
            "atoms":[v.name for v in values],
            "facts":sorted(map(str,e.state.get("_facts",[]))),
            "feedback":str(e.state.get("feedback","")),
            "ordered_commands":list(e.state.get("admissible_commands",[])),
            "goal_reached":bool(e._pddl_state.check_goal()),
        }

    def do(e,command):
        if command not in native(e)["ordered_commands"]:
            raise ValueError("Command not in real ordered menu")
        e.step(command)

    a,b=initialize(),initialize()
    try:
        if a.downward_lib is b.downward_lib:
            raise ValueError("A/B native handles alias")
        if native(a)!=native(b):raise ValueError("Reset full native projection unequal")
        do(a,"look");do(b,"look")
        if native(a)!=native(b):raise ValueError("Look native projection unequal")
        choices=[x for x in native(a)["ordered_commands"] if x.startswith("go to ")]
        if len(choices)<3:raise ValueError("No real move/branch candidate")
        prefix=("look",choices[0])
        do(a,prefix[1]);do(b,prefix[1])
        state_a,state_b=native(a),native(b)
        if state_a!=state_b:raise ValueError("Native state after movement unequal")
        legal=tuple(state_a["ordered_commands"])
        fork=[x for x in legal if x.startswith("go to ") and x!=prefix[1]]
        if len(fork)<2:raise ValueError("No two actual later-fork actions")
        donor_a=prefix+(fork[0],)
        donor_b=prefix+(fork[1],)
        game_sha=sha(file.read_bytes())
        source_a=sha(json.dumps({
            "MECHANICAL_PLACEHOLDER_NO_MODEL_AUTHORED_PLAN":True,
            "game_sha":game_sha,"actions":donor_a
        },sort_keys=True).encode())
        source_b=sha(json.dumps({
            "MECHANICAL_PLACEHOLDER_NO_MODEL_AUTHORED_PLAN":True,
            "game_sha":game_sha,"actions":donor_b
        },sort_keys=True).encode())
        goal=descriptor(file)
        common_feedback=state_a["feedback"]
        pair=MatchedPair(
            source_game_sha256=game_sha,
            goal=goal,
            shared_actual_prefix=prefix,
            public_observation=common_feedback,
            ordered_legal_commands=legal,
            plan_a=SourcePlan("mechanicalA",donor_a,source_a),
            plan_b=SourcePlan("mechanicalB",donor_b,source_b),
        )
        result=reciprocal_preflight(pair)
        b_hold=native(b)
        do(a,fork[0])
        if native(b)!=b_hold:raise ValueError("A unexpectedly changed B")
        do(b,fork[1])
        if native(a)==native(b):raise ValueError("Fork outcome not distinct")
        entries=[]
        for direction in ("a_donor","b_donor"):
            record=result[direction]
            bind=record["messages"]["BIND"]["content"]
            direct=record["messages"]["DIRECT_REMINDER"]["content"]
            if record["same_semantic_payload"] not in bind or record["same_semantic_payload"] not in direct:
                raise AssertionError("Shared source information lost")
            entries.append({
                "direction":record["direction"],
                "shared_payload_sha256":record["semantic_payload_sha256"],
                "BIND_prompt_sha256":sha(bind.encode()),
                "DIRECT_REMINDER_prompt_sha256":sha(direct.encode()),
                "BIND_UTF8_bytes":len(bind.encode()),
                "DIRECT_REMINDER_UTF8_bytes":len(direct.encode()),
                "same_public_ordered_menu":True,
                "same_public_observation":True,
                "same_instruction_role":True,
                "model_specific_token_parity_certified":False,
            })
        return {
            "task_family":file.parent.parent.name,
            "game_sha256":game_sha,
            "task_descriptor_is_official_agent_goal":False,
            "native_atom_count":len(state_a["atoms"]),
            "real_common_prefix_actions":list(prefix),
            "prefix_native_projection_sha256":sha(json.dumps(state_a,sort_keys=True).encode()),
            "public_observation_sha256":sha(common_feedback.encode()),
            "public_observation_bytes":len(common_feedback.encode()),
            "ordered_legal_commands_sha256":sha(json.dumps(legal).encode()),
            "mechanical_probes_future_forks":fork[:2],
            "legal_forks_diverge":True,
            "A_native_step_did_not_mutate_B":True,
            "paired_control_previews":entries,
            "model_owned_successful_source_paths":False,
            "frozen_model_tokenizer_available":False,
        }
    finally:
        a.close();b.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dataset-root",type=Path,required=True)
    p.add_argument("--historical-matrix",type=Path,required=True)
    p.add_argument("--exec-tmp",type=Path,required=True)
    p.add_argument("--max-games",type=int,default=11)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    args.exec_tmp.mkdir(parents=True,exist_ok=True)
    if os.statvfs(args.exec_tmp).f_flag & getattr(os,"ST_NOEXEC",8):
        raise ValueError("NOEXEC native library temp")
    for k in ("TMPDIR","TMP","TEMP"):
        os.environ[k]=str(args.exec_tmp.resolve())
    import tempfile
    tempfile.tempdir=None
    root=args.dataset_root.resolve()
    if root.name!="json_2.1.1":raise ValueError("Wrong original dataset root")
    matrix=json.loads(args.historical_matrix.read_text())
    cases=matrix["per_game_overlap"]
    if len(cases)!=11 or not 1<=args.max_games<=11:
        raise ValueError("Only 11 historical inspected games authorized here")
    outcomes=[]
    for row in cases[:args.max_games]:
        orig=row["game_path"]
        if not orig.startswith(OLD_ROOT):raise ValueError("Unverified original identity")
        rel=Path(orig[len(OLD_ROOT):])
        if ".." in rel.parts or rel.parts[0]!="train" or rel.name!="game.tw-pddl":
            raise ValueError("Invalid source path")
        file=(root/rel).resolve()
        if not file.is_relative_to(root):raise ValueError("Source escape")
        outcomes.append(run_case(file))
    audit={
        "schema":"plancarry.bind.real-alfworld-native-prompt-parity.integration.v1",
        "source_archive_sha256":EXPECTED_ARCHIVE,
        "case_count":len(outcomes),
        "cases":outcomes,
        "source_scope":"Previously environmentally inspected original Pilot40/BIND180 overlap only",
        "model_owned_plans_generated":False,
        "source_plan_probes_mechanically_selected_only":True,
        "goal_descriptors_derived_from_source_family_not_agent_instructions":True,
        "same_semantic_future_plan_and_native_public_tool_context":True,
        "tokenizer_parity_certified":False,
        "full_native_rng_state_certificate":False,
        "model_calls":0,
        "scientific_gate":"NOT_AUTHORIZED",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(audit,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "status":"REAL_ALFWORLD_PDDL_PAIRED_STRONG_NULL_PROMPT_INTEGRATION_PASS",
        "cases":len(outcomes),
        "directions":sum(len(x["paired_control_previews"]) for x in outcomes),
        "native_atom_counts":[x["native_atom_count"] for x in outcomes],
        "model_source_competence":False,
        "model_tokenizer_parity":False,
        "model_calls":0,
        "G1_authorized":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
