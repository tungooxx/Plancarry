#!/usr/bin/env python3
"""BIND and PSB-SYM-1 fair DIRECT_REMINDER null: preflight only.

This module builds the TWO different nonexecuting intervention frames over
the EXACT SAME byte-serialized public-plan semantic payload. It cannot
authenticate model-authored source histories, decide experimental random
assignments, guarantee model-specific token parity or authorize G0/G1/G2.
It neither filters nor reranks actions. No model, TRAIN execution or GPU.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Literal

_HEX_SHA=re.compile(r"^[a-f0-9]{64}$")
_SOURCE_ATTESTATION="MISSING_MODEL_AUTHORED_SOURCE_HISTORY"
_TOKEN_ATTESTATION="MISSING_MODEL_TOKENIZER_AND_REALIZED_BUDGET_AUDIT"
_COMMON_FRAME=(
    "You are given a proposed future plan whose model authorship is "
    "not independently attested here, and the current public task context. "
    "The legal action menu and task goal are immutable. This text "
    "must not modify, filter, hide, reorder, force, or execute an action. "
    "Only choose an action through the same external legal-action tool."
)
_BIND_INSTRUCTION=(
    "Plan-state binding: plan_id is the active commitment identity for this "
    "decision. Prefer the next action belonging to that exact plan_id while "
    "respecting the unchanged public legal-action menu."
)
_DIRECT_INSTRUCTION=(
    "Direct plan reminder: follow plan_id as your full future plan. Take the "
    "next action written in this exact plan_id while respecting the "
    "unchanged public legal-action menu."
)

@dataclass(frozen=True)
class SourcePlan:
    plan_id:str
    whole_actions:tuple[str,...]
    source_record_sha256:str


@dataclass(frozen=True)
class MatchedPair:
    source_game_sha256:str
    goal:str
    shared_actual_prefix:tuple[str,...]
    public_observation:str
    ordered_legal_commands:tuple[str,...]
    plan_a:SourcePlan
    plan_b:SourcePlan


def _canonical(payload:dict)->str:
    return json.dumps(payload,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False)


def check_shape(pair:MatchedPair)->None:
    if not isinstance(pair,MatchedPair):
        raise ValueError("MatchedPair required")
    if not _HEX_SHA.fullmatch(pair.source_game_sha256):
        raise ValueError("Unpinned source game bytes")
    if not isinstance(pair.goal,str) or not pair.goal.strip() or len(pair.goal)>1000:
        raise ValueError("Missing goal")
    if not isinstance(pair.public_observation,str) or len(pair.public_observation)>10000:
        raise ValueError("Missing public observation")
    prefix=pair.shared_actual_prefix
    if not isinstance(prefix,tuple) or len(prefix)<1:
        raise ValueError("Actual common prefix missing")
    if not all(type(x) is str and x and len(x)<512 for x in prefix):
        raise ValueError("Invalid actual prefix")
    menu=pair.ordered_legal_commands
    if not isinstance(menu,tuple) or len(menu)<2 or len(set(menu))!=len(menu):
        raise ValueError("Ordered legal command menu invalid")
    if not all(type(x) is str and x and len(x)<512 for x in menu):
        raise ValueError("Invalid legal commands")
    if pair.plan_a.plan_id==pair.plan_b.plan_id:
        raise ValueError("Plan identities cannot alias")
    # These hashes purport to bind the COMPLETE source-plan history records.
    # Different model-owned A/B histories with diverging later actions cannot
    # share that exact byte identity; matching IDs alone are not provenance.
    # This is necessary consistency checking, never attestation of either hash.
    if pair.plan_a.source_record_sha256==pair.plan_b.source_record_sha256:
        raise ValueError("Distinct divergent source histories cannot share a source-record digest")
    for plan in (pair.plan_a,pair.plan_b):
        if not plan.plan_id or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",plan.plan_id):
            raise ValueError("Unsafe plan identifier")
        if not _HEX_SHA.fullmatch(plan.source_record_sha256):
            raise ValueError("Missing external source-record digest")
        if not isinstance(plan.whole_actions,tuple) or len(plan.whole_actions)<=len(prefix):
            raise ValueError("Plan lacks a later fork")
        if plan.whole_actions[:len(prefix)]!=prefix:
            raise ValueError("Plan's common prefix differs")
        if not all(type(x) is str and x and len(x)<512 for x in plan.whole_actions):
            raise ValueError("Invalid plan actions")
    i=len(prefix)
    a,b=pair.plan_a.whole_actions[i],pair.plan_b.whole_actions[i]
    if a==b:
        raise ValueError("No later divergent action")
    if a not in menu or b not in menu:
        raise ValueError("Both proposed later-fork actions must be legal")
    # This is only a shape check; it does not prove complete native state,
    # model ownership, source success or full historical non-consumption.


def paired_messages(pair:MatchedPair, donor:Literal["A","B"])->dict:
    """Both arms use identical role and identical exact semantic JSON bytes.

    Strong DIRECT_REMINDER is deliberately imperative, not weakened to force
    a desired statistical advantage for BIND. Equal-content != token parity.
    """
    check_shape(pair)
    if donor not in ("A","B"):raise ValueError("Only A/B donor direction")
    selected=pair.plan_a if donor=="A" else pair.plan_b
    other=pair.plan_b if donor=="A" else pair.plan_a
    future=selected.whole_actions[len(pair.shared_actual_prefix):]
    payload={
        "goal":pair.goal,
        "public_observation":pair.public_observation,
        "ordered_legal_commands":list(pair.ordered_legal_commands),
        "plan_id":selected.plan_id,
        "donor_future_actions":list(future),
        "donor_source_record_sha256":selected.source_record_sha256,
        "actual_common_prefix_actions":list(pair.shared_actual_prefix),
    }
    shared=_canonical(payload)
    binding="\n\n".join((_COMMON_FRAME,_BIND_INSTRUCTION,shared))
    direct="\n\n".join((_COMMON_FRAME,_DIRECT_INSTRUCTION,shared))
    if binding==direct:raise AssertionError("Interventions indistinguishable")
    if shared not in binding or shared not in direct:
        raise AssertionError("Information parity failed")
    return {
        "schema":"plancarry.intervention-strong-direct-null-preflight.v1",
        "direction":donor+"->"+("B" if donor=="A" else "A"),
        "donor_plan_id":selected.plan_id,
        "recipient_source_plan_id":other.plan_id,
        "same_role_for_both":"user",
        "same_semantic_payload":shared,
        "semantic_payload_sha256":hashlib.sha256(shared.encode("utf8")).hexdigest(),
        # Byte-cost diagnostics are observable without any model call and
        # show that identical semantic payload is NOT equal prompt budget.
        # Model-specific token counts, attention and actual spend remain unknown.
        "prompt_utf8_bytes":{
            "BIND":len(binding.encode("utf8")),
            "DIRECT_REMINDER":len(direct.encode("utf8")),
        },
        "prompt_byte_delta_bind_minus_direct":len(binding.encode("utf8"))-len(direct.encode("utf8")),
        "messages":{
            "BIND":{"role":"user","content":binding},
            "DIRECT_REMINDER":{"role":"user","content":direct},
        },
        "legal_action_menu_altered":False,
        "model_owned_plan_attested":False,
        "simulator_complete_state_attested":False,
        "tokenizer_realized_costs_matched":False,
        "science_gate":"NOT_AUTHORIZED",
        "blockers":[_SOURCE_ATTESTATION,_TOKEN_ATTESTATION,
                    "MISSING_INDEPENDENT_DESIGN_REVIEW_AND_AUTHORITY"],
    }


def reciprocal_preflight(pair:MatchedPair)->dict:
    arm_a=paired_messages(pair,"A")
    arm_b=paired_messages(pair,"B")
    return {
        "schema":"plancarry.reciprocal-direct-null-engineering-only.v1",
        "a_donor":arm_a,
        "b_donor":arm_b,
        "no_randomization_performed":True,
        "science_gate":"NOT_AUTHORIZED",
        "model_calls":0,
    }
