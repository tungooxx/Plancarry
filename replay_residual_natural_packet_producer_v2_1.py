#!/usr/bin/env python3
"""Exact V2.1 natural-plan packet producer for ReplayResidual representation sanity.

This module is engineering plumbing for the prospectively frozen V2.1 contract.
It does not expose hidden-state capture, patching, residual injection, or T1
analysis.  Production model/environment imports are deliberately deferred to
explicit execution entry points so unit tests remain synthetic and pre-science.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from replay_residual_sanity_protocol_v1 import (
    CONDITIONS,
    DEV_INDICES,
    MODEL_DTYPE,
    MODEL_ID,
    MODEL_REVISION,
    PLAN_SLOT_TOKENS,
    TORCH_VERSION,
    TOKENIZERS_VERSION,
    TRANSFORMERS_VERSION,
    build_condition_slots,
    canonical_json_bytes,
    development_manifest,
    trajectory_digest,
)

CONTRACT_REL = Path("results/design/plancarry_replay_residual_unified_execution_contract_v2_1_rw_20260821.json")
CONTRACT_SHA256 = "83370fbfc65c4818ada159a0e3c83cf778b88ed02f964bcf7887e5cea3843158"
REVIEW_REL = Path("results/design/plancarry_replay_residual_v2_1_a3_independent_review_v1_20260821.json")
REVIEW_SHA256 = "f6008a9f26a41c789f385c5efc33fde1f256811da0cd04ac49125898e2340743"
PROTOCOL_SHA256 = "9af0d247e8bb9cb5e17d11727008d827dab0c088d5c28142726be20cd2d883ef"
PACKET_CONTRACT_VERSION = "REPLAY_RESIDUAL_NATURAL_PACKET_V2_1"
FINAL_TARGET_REL = Path("results/science/plancarry_replay_residual_sanity_packets_v2")
ACTION_BUDGET = 12
INTERRUPTION_AFTER = 2
MIN_FINAL_QUALIFIED = 16
NONTRIVIAL_EXCLUDED = ("help", "inventory", "look")
ANCHOR_CYCLE = 2
EXPECTED_DEVICE_NAME = "NVIDIA GeForce RTX 3050 Laptop GPU"

PLANNER_SYSTEM = (
    "You are planning an ALFWorld household task. Produce a concise ordered plan using only information "
    "in the task instruction and initial observation. Do not reveal chain-of-thought or hidden reasoning. "
    "Do not invent hidden world facts. Output only one <PLAN>...</PLAN> block."
)
PLANNER_USER_TEMPLATE = (
    "TASK\n{task_instruction}\nINITIAL OBSERVATION\n{initial_observation}\n"
    "Write the action-level plan now. Keep the complete <PLAN>...</PLAN> block within 96 model tokens."
)
EXECUTOR_SYSTEM = (
    "You are executing an ALFWorld household task. The visible plan is advisory state from your own earlier "
    "planning turn. Choose the single best current admissible command to continue the task. Do not invent "
    "actions or hidden facts."
)
EXECUTOR_USER_TEMPLATE = (
    "TASK\n{task_instruction}\nPLAN\n{plan_text}\nHISTORY\n{history}\nCURRENT OBSERVATION\n{observation}\n"
    "ADMISSIBLE COMMANDS\n{commands}\nACTION:"
)
TASK_RE = re.compile(r"Your task is to:\s*(.+?)(?:\n|$)", re.I)
PLAN_RE = re.compile(r"<PLAN>.*?</PLAN>", re.I | re.S)
REASONING_MARKERS = ("<think>", "</think>", "reasoning trace", "chain-of-thought")

REQUIRED_ACTION_FIELDS = (
    "step", "command", "observation", "score_fp32_mean_logprob", "done", "won",
    "pre_state_hash", "post_state_hash", "admissible_commands", "admissible_commands_sha256",
    "action_prompt_token_ids_sha256", "candidate_suffix_token_ids_sha256_by_command",
    "candidate_score_vector_sha256", "error",
)
REQUIRED_PACKET_FIELDS = (
    "packet_contract_version", "frozen_index", "family", "game_path", "game_path_sha256",
    "task_instruction", "initial_observation", "trajectory_eligible", "qualified",
    "qualification_stage1_reasons", "qualification_stage2_reasons", "model_provenance",
    "prompt_provenance", "plan_provenance", "actions", "success", "interruption_after",
    "trajectory_sha256", "control_provenance", "producer_contract_sha256",
)
EXPECTED_MODEL_PROVENANCE = {
    "model_id": MODEL_ID,
    "revision": MODEL_REVISION,
    "dtype": MODEL_DTYPE,
    "transformers_version": TRANSFORMERS_VERSION,
    "tokenizers_version": TOKENIZERS_VERSION,
    "torch_version": TORCH_VERSION,
    "quantization": "NONE",
    "offload": "NONE",
    "enable_thinking": False,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def verify_frozen_bindings(root: Path) -> None:
    pairs = ((root / CONTRACT_REL, CONTRACT_SHA256), (root / REVIEW_REL, REVIEW_SHA256),
             (root / Path("replay_residual_sanity_protocol_v1.py"), PROTOCOL_SHA256))
    for path, expected in pairs:
        got = sha256_file(path)
        if got != expected:
            raise RuntimeError(f"FROZEN_BINDING_HASH_MISMATCH:{path}:{got}:{expected}")


def extract_task_instruction(initial_observation: str) -> str:
    matches = list(TASK_RE.finditer(str(initial_observation)))
    if not matches:
        raise RuntimeError("TASK_INSTRUCTION_EXTRACTION_FAILED")
    text = matches[-1].group(1).strip()
    if not text:
        raise RuntimeError("TASK_INSTRUCTION_EXTRACTION_EMPTY")
    return text


def _ids(value: Any) -> list[int]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list) and value and isinstance(value[0], list):
        if len(value) != 1:
            raise RuntimeError("EXPECTED_SINGLE_SEQUENCE")
        value = value[0]
    return [int(x) for x in value]


def planner_messages(task_instruction: str, initial_observation: str) -> tuple[list[dict[str, str]], str]:
    user = PLANNER_USER_TEMPLATE.format(task_instruction=task_instruction, initial_observation=initial_observation)
    return ([{"role": "system", "content": PLANNER_SYSTEM}, {"role": "user", "content": user}], user)


def planner_prefix_ids(tokenizer: Any, task_instruction: str, initial_observation: str) -> tuple[list[int], str]:
    messages, user = planner_messages(task_instruction, initial_observation)
    ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False)
    return _ids(ids), user


def accept_plan_new_ids(tokenizer: Any, new_ids: Sequence[int]) -> tuple[str, int]:
    decoded = tokenizer.decode([int(x) for x in new_ids], skip_special_tokens=True,
                               clean_up_tokenization_spaces=False)
    plan_text = str(decoded).strip()  # whitespace-only canonicalization is frozen.
    lowered = plan_text.lower()
    if any(marker in lowered for marker in REASONING_MARKERS):
        raise RuntimeError("PLAN_REASONING_MARKER_FORBIDDEN")
    if not PLAN_RE.fullmatch(plan_text):
        raise RuntimeError("PLAN_EXACT_FULLMATCH_REQUIRED")
    if len(re.findall(r"<PLAN>", plan_text, flags=re.I)) != 1 or len(re.findall(r"</PLAN>", plan_text, flags=re.I)) != 1:
        raise RuntimeError("PLAN_EXACTLY_ONE_COMPLETE_BLOCK_REQUIRED")
    plan_ids = _ids(tokenizer.encode(plan_text, add_special_tokens=False))
    if len(plan_ids) > 96:
        raise RuntimeError(f"PLAN_COMPLETE_BLOCK_TOO_LONG:{len(plan_ids)}>96")
    return plan_text, len(plan_ids)


@dataclass(frozen=True)
class PlannerResult:
    plan_text: str
    complete_block_token_count: int
    new_ids: tuple[int, ...]
    planner_chat_token_ids: tuple[int, ...]
    planner_user_rendered: str


def torch_generate_plan(tokenizer: Any, model: Any, task_instruction: str, initial_observation: str) -> PlannerResult:
    """One exact greedy planner call. Imported Torch is execution-time only."""
    import torch  # type: ignore
    prefix_ids, user = planner_prefix_ids(tokenizer, task_instruction, initial_observation)
    device = next(model.parameters()).device
    input_ids = torch.tensor([prefix_ids], dtype=torch.long, device=device)
    with torch.inference_mode():
        out = model.generate(
            input_ids=input_ids,
            do_sample=False,
            max_new_tokens=128,
            use_cache=True,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
        )
    seq = _ids(out)
    if len(seq) < len(prefix_ids) or seq[:len(prefix_ids)] != prefix_ids:
        raise RuntimeError("PLANNER_GENERATION_PREFIX_MISMATCH")
    new_ids = seq[len(prefix_ids):]
    plan_text, n = accept_plan_new_ids(tokenizer, new_ids)
    return PlannerResult(plan_text, n, tuple(new_ids), tuple(prefix_ids), user)


def serialize_history(actions: Sequence[Mapping[str, Any]]) -> str:
    chunks = []
    for i, row in enumerate(actions, 1):
        chunks.append(f"STEP {i}\nACTION: {row['command']}\nOBSERVATION: {row['observation']}")
    return "\n".join(chunks)


def executor_prefix_and_suffixes(
    tokenizer: Any,
    task_instruction: str,
    plan_text: str,
    history_actions: Sequence[Mapping[str, Any]],
    observation: str,
    admissible_commands: Sequence[str],
) -> tuple[str, list[int], dict[str, list[int]], list[str]]:
    commands = sorted(str(x) for x in admissible_commands)
    if not commands:
        raise RuntimeError("NO_ADMISSIBLE_COMMANDS")
    if len(commands) != len(set(commands)):
        raise RuntimeError("DUPLICATE_ADMISSIBLE_COMMANDS")
    user = EXECUTOR_USER_TEMPLATE.format(
        task_instruction=task_instruction,
        plan_text=plan_text,
        history=serialize_history(history_actions),
        observation=observation,
        commands="\n".join(commands),
    )
    if not user.endswith("ACTION:"):
        raise RuntimeError("EXECUTOR_USER_MUST_END_ACTION_LITERAL")
    messages = [{"role": "system", "content": EXECUTOR_SYSTEM}, {"role": "user", "content": user}]
    prefix = _ids(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False))
    suffixes = {cmd: _ids(tokenizer.encode(" " + cmd, add_special_tokens=False)) for cmd in commands}
    if any(not ids for ids in suffixes.values()):
        raise RuntimeError("EMPTY_CANDIDATE_SUFFIX")
    return user, prefix, suffixes, commands


def torch_suffix_mean_logprob(model: Any, prefix_ids: Sequence[int], suffix_ids: Sequence[int]) -> float:
    """Arithmetic mean FP32 teacher-forced suffix-token log probability."""
    import torch  # type: ignore
    p = [int(x) for x in prefix_ids]
    s = [int(x) for x in suffix_ids]
    if not p or not s:
        raise RuntimeError("EMPTY_PREFIX_OR_SUFFIX")
    device = next(model.parameters()).device
    full = torch.tensor([p + s], dtype=torch.long, device=device)
    with torch.inference_mode():
        logits = model(input_ids=full).logits.float()
        logp = torch.log_softmax(logits, dim=-1)
        vals = []
        for offset, token_id in enumerate(s):
            absolute = len(p) + offset
            vals.append(logp[0, absolute - 1, token_id])
        score = torch.stack(vals).mean()
    value = float(score.detach().cpu().item())
    if not math.isfinite(value):
        raise RuntimeError("NONFINITE_CANDIDATE_SCORE")
    return value


@dataclass(frozen=True)
class ChoiceResult:
    command: str
    chosen_score: float
    user_rendered: str
    prefix_ids: tuple[int, ...]
    suffix_ids_by_command: Mapping[str, tuple[int, ...]]
    score_by_command: Mapping[str, float]


def choose_admissible_command(
    tokenizer: Any,
    task_instruction: str,
    plan_text: str,
    history_actions: Sequence[Mapping[str, Any]],
    observation: str,
    admissible_commands: Sequence[str],
    score_fn: Callable[[Sequence[int], Sequence[int]], float],
) -> ChoiceResult:
    user, prefix, suffixes, commands = executor_prefix_and_suffixes(
        tokenizer, task_instruction, plan_text, history_actions, observation, admissible_commands
    )
    scores: dict[str, float] = {}
    for command in commands:
        value = float(score_fn(prefix, suffixes[command]))
        if not math.isfinite(value):
            raise RuntimeError("NONFINITE_CANDIDATE_SCORE")
        scores[command] = value
    best = max(scores.values())
    command = min(cmd for cmd, value in scores.items() if value == best)
    return ChoiceResult(
        command=command,
        chosen_score=scores[command],
        user_rendered=user,
        prefix_ids=tuple(prefix),
        suffix_ids_by_command={k: tuple(v) for k, v in suffixes.items()},
        score_by_command=dict(scores),
    )


def is_nontrivial(command: str) -> bool:
    return str(command) not in NONTRIVIAL_EXCLUDED


def stage1_eligibility(plan_ok: bool, success: bool, actions: Sequence[Mapping[str, Any]], errors: Sequence[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not plan_ok:
        reasons.append("PLAN_ACCEPTANCE_FAILED")
    if not success:
        reasons.append("NOT_WON_WITHIN_ACTION_BUDGET")
    if len(actions) < 4:
        reasons.append("TRAJECTORY_HAS_FEWER_THAN_4_ACTIONS")
    if len(actions) > ACTION_BUDGET:
        reasons.append("TRAJECTORY_EXCEEDS_ACTION_BUDGET")
    if len(actions) >= 2 and not all(is_nontrivial(str(x["command"])) for x in actions[:2]):
        reasons.append("FIRST_TWO_ACTIONS_NOT_BOTH_NONTRIVIAL")
    elif len(actions) < 2:
        reasons.append("FIRST_TWO_ACTIONS_UNAVAILABLE")
    post = [x for x in actions[INTERRUPTION_AFTER:] if is_nontrivial(str(x["command"]))]
    if len(post) < 2:
        reasons.append("FEWER_THAN_TWO_POST_CUT_NONTRIVIAL_ACTIONS")
    if errors or any(x.get("error") for x in actions):
        reasons.append("INVALID_COMMAND_OR_EXECUTION_ERROR")
    return (not reasons), reasons


def prompt_provenance_for_planner(result: PlannerResult) -> dict[str, str]:
    return {
        "planner_system_sha256": sha256_text(PLANNER_SYSTEM),
        "planner_user_rendered_sha256": sha256_text(result.planner_user_rendered),
        "planner_chat_token_ids_sha256": sha256_json(list(result.planner_chat_token_ids)),
        "executor_system_sha256": sha256_text(EXECUTOR_SYSTEM),
        "executor_user_template_sha256": sha256_text(EXECUTOR_USER_TEMPLATE),
    }


def empty_prompt_provenance() -> dict[str, str]:
    return {
        "planner_system_sha256": sha256_text(PLANNER_SYSTEM),
        "planner_user_rendered_sha256": sha256_text(""),
        "planner_chat_token_ids_sha256": sha256_json([]),
        "executor_system_sha256": sha256_text(EXECUTOR_SYSTEM),
        "executor_user_template_sha256": sha256_text(EXECUTOR_USER_TEMPLATE),
    }


def plan_provenance(tokenizer: Any, result: PlannerResult | None) -> dict[str, Any]:
    if result is None:
        return {
            "plan_text": "", "plan_text_sha256": sha256_text(""), "plan_token_ids_sha256": sha256_json([]),
            "complete_block_token_count": 0, "planner_new_ids_sha256": sha256_json([]),
        }
    plan_ids = _ids(tokenizer.encode(result.plan_text, add_special_tokens=False))
    return {
        "plan_text": result.plan_text,
        "plan_text_sha256": sha256_text(result.plan_text),
        "plan_token_ids_sha256": sha256_json(plan_ids),
        "complete_block_token_count": result.complete_block_token_count,
        "planner_new_ids_sha256": sha256_json(list(result.new_ids)),
    }


def default_control_provenance() -> dict[str, Any]:
    return {
        "condition_names": list(CONDITIONS),
        "condition_slot_token_ids_sha256_by_condition": {},
        "unrelated_donor_frozen_index": None,
        "unrelated_donor_ordering_key": None,
        "anchor_cycle": ANCHOR_CYCLE,
        "control_builder_source_sha256": PROTOCOL_SHA256,
    }


def action_row(
    step: int,
    choice: ChoiceResult,
    pre_state_hash: str,
    record: Any,
    pre_commands: Sequence[str],
) -> dict[str, Any]:
    score_vector = [{"command": c, "score": float(choice.score_by_command[c])} for c in sorted(choice.score_by_command)]
    suffix_hashes = {c: sha256_json(list(choice.suffix_ids_by_command[c])) for c in sorted(choice.suffix_ids_by_command)}
    return {
        "step": int(step),
        "command": choice.command,
        "observation": str(record.observation),
        "score_fp32_mean_logprob": float(choice.chosen_score),
        "done": bool(record.done),
        "won": bool(record.won),
        "pre_state_hash": str(pre_state_hash),
        "post_state_hash": str(record.state_hash),
        "admissible_commands": sorted(str(x) for x in pre_commands),
        "admissible_commands_sha256": sha256_json(sorted(str(x) for x in pre_commands)),
        "action_prompt_token_ids_sha256": sha256_json(list(choice.prefix_ids)),
        "candidate_suffix_token_ids_sha256_by_command": suffix_hashes,
        "candidate_score_vector_sha256": sha256_json(score_vector),
        "error": record.error,
    }


def _packet_base(row: Mapping[str, Any], model_provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet_contract_version": PACKET_CONTRACT_VERSION,
        "frozen_index": int(row["frozen_index"]),
        "family": str(row["family"]),
        "game_path": str(row["game_path"]),
        "game_path_sha256": sha256_text(str(row["game_path"])),
        "task_instruction": "",
        "initial_observation": "",
        "trajectory_eligible": False,
        "qualified": False,
        "qualification_stage1_reasons": [],
        "qualification_stage2_reasons": ["STAGE2_NOT_RUN"],
        "model_provenance": dict(model_provenance),
        "prompt_provenance": empty_prompt_provenance(),
        "plan_provenance": {},
        "plan_text": "",
        "actions": [],
        "success": False,
        "interruption_after": INTERRUPTION_AFTER,
        "trajectory_sha256": "",
        "control_provenance": default_control_provenance(),
        "producer_contract_sha256": CONTRACT_SHA256,
    }


def produce_stage1_attempt(
    row: Mapping[str, Any],
    tokenizer: Any,
    model_provenance: Mapping[str, Any],
    runtime_factory: Callable[[str], Any],
    planner_fn: Callable[[str, str], PlannerResult],
    command_score_fn: Callable[[Sequence[int], Sequence[int]], float],
) -> dict[str, Any]:
    packet = _packet_base(row, model_provenance)
    runtime = None
    errors: list[str] = []
    planner: PlannerResult | None = None
    try:
        runtime = runtime_factory(str(row["game_path"]))
        packet["initial_observation"] = str(runtime.observation)
        packet["task_instruction"] = extract_task_instruction(packet["initial_observation"])
        planner = planner_fn(packet["task_instruction"], packet["initial_observation"])
        # Revalidate independently even if planner_fn is injected.
        accepted, count = accept_plan_new_ids(tokenizer, planner.new_ids)
        if accepted != planner.plan_text or count != planner.complete_block_token_count:
            raise RuntimeError("PLANNER_RESULT_ACCEPTANCE_MISMATCH")
        packet["plan_text"] = planner.plan_text
        packet["plan_provenance"] = plan_provenance(tokenizer, planner)
        packet["prompt_provenance"] = prompt_provenance_for_planner(planner)

        for step in range(1, ACTION_BUDGET + 1):
            if bool(runtime.done) or bool(runtime.won):
                break
            commands = sorted(str(x) for x in runtime.admissible_commands)
            choice = choose_admissible_command(
                tokenizer,
                packet["task_instruction"],
                planner.plan_text,
                packet["actions"],
                str(runtime.observation),
                commands,
                command_score_fn,
            )
            if choice.command not in commands:
                raise RuntimeError("CHOICE_NOT_CURRENT_ADMISSIBLE_COMMAND")
            pre_hash = str(runtime.hash())
            record = runtime.step(choice.command)
            row_action = action_row(step, choice, pre_hash, record, commands)
            packet["actions"].append(row_action)
            if record.error:
                errors.append(str(record.error))
                break
            if bool(record.done) or bool(record.won):
                break
        packet["success"] = bool(getattr(runtime, "won", False))
    except Exception as exc:
        errors.append(f"{type(exc).__name__}:{exc}")
        if not packet["plan_provenance"]:
            packet["plan_provenance"] = plan_provenance(tokenizer, planner)
    finally:
        if runtime is not None:
            try:
                runtime.close()
            except Exception:
                pass

    plan_ok = planner is not None and bool(packet["plan_text"])
    eligible, reasons = stage1_eligibility(plan_ok, bool(packet["success"]), packet["actions"], errors)
    if errors:
        reasons.extend(x for x in errors if x not in reasons)
    packet["trajectory_eligible"] = bool(eligible)
    packet["qualification_stage1_reasons"] = reasons
    packet["trajectory_sha256"] = trajectory_digest(packet)
    return packet


def unrelated_ordering_key(packet: Mapping[str, Any]) -> str:
    payload = "ReplayResidual|UNRELATED_PLAN|" + str(packet["family"]) + "|" + str(packet["game_path"])
    return sha256_text(payload)


def frozen_eligible_order(packets: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted((p for p in packets if bool(p.get("trajectory_eligible"))), key=unrelated_ordering_key)


def unrelated_donor_for(recipient: Mapping[str, Any], eligible_order: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if len(eligible_order) < 2:
        return None
    positions = [i for i, p in enumerate(eligible_order) if int(p["frozen_index"]) == int(recipient["frozen_index"])]
    if len(positions) != 1:
        raise RuntimeError("RECIPIENT_NOT_UNIQUE_IN_FROZEN_E")
    start = positions[0]
    for delta in range(1, len(eligible_order) + 1):
        candidate = eligible_order[(start + delta) % len(eligible_order)]
        if str(candidate["family"]) != str(recipient["family"]):
            return candidate
    return None


def apply_stage2(tokenizer: Any, packets: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if [int(p["frozen_index"]) for p in packets] != list(DEV_INDICES):
        raise RuntimeError("STAGE2_REQUIRES_ALL32_IN_FIXED_ORDER")
    eligible = frozen_eligible_order(packets)
    result = [dict(p) for p in packets]
    by_index = {int(p["frozen_index"]): p for p in result}
    if len(eligible) < 2:
        for p in result:
            p["qualified"] = False
            p["qualification_stage2_reasons"] = ["FROZEN_E_SIZE_LT_2"]
        return result
    for source in eligible:
        p = by_index[int(source["frozen_index"])]
        donor = unrelated_donor_for(source, eligible)
        if donor is None:
            p["qualified"] = False
            p["qualification_stage2_reasons"] = ["NO_DIFFERENT_FAMILY_DONOR_IN_FROZEN_E"]
            continue
        donor_idx = int(donor["frozen_index"])
        donor_key = unrelated_ordering_key(donor)
        try:
            slots = build_condition_slots(tokenizer, p, str(donor["plan_text"]), anchor_cycle=ANCHOR_CYCLE)
            if set(slots) != set(CONDITIONS) or any(len(ids) != PLAN_SLOT_TOKENS for ids in slots.values()):
                raise RuntimeError("ALL_SEVEN_EXACT128_CONTROLS_REQUIRED")
            p["control_provenance"] = {
                "condition_names": list(CONDITIONS),
                "condition_slot_token_ids_sha256_by_condition": {name: sha256_json(list(slots[name])) for name in CONDITIONS},
                "unrelated_donor_frozen_index": donor_idx,
                "unrelated_donor_ordering_key": donor_key,
                "anchor_cycle": ANCHOR_CYCLE,
                "control_builder_source_sha256": PROTOCOL_SHA256,
            }
            p["qualified"] = True
            p["qualification_stage2_reasons"] = []
        except Exception as exc:
            p["qualified"] = False
            p["qualification_stage2_reasons"] = [f"CONTROL_CONSTRUCTION_FAILED:{type(exc).__name__}:{exc}"]
            p["control_provenance"] = {
                **default_control_provenance(),
                "unrelated_donor_frozen_index": donor_idx,
                "unrelated_donor_ordering_key": donor_key,
            }
    for p in result:
        if not p.get("trajectory_eligible"):
            p["qualified"] = False
            p["qualification_stage2_reasons"] = ["NOT_IN_FROZEN_TRAJECTORY_ELIGIBLE_E"]
    return result


def all32_attempts(
    manifest_rows: Sequence[Mapping[str, Any]],
    tokenizer: Any,
    model_provenance: Mapping[str, Any],
    runtime_factory: Callable[[str], Any],
    planner_fn: Callable[[str, str], PlannerResult],
    command_score_fn: Callable[[Sequence[int], Sequence[int]], float],
    progress_fn: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    if [int(r["frozen_index"]) for r in manifest_rows] != list(DEV_INDICES):
        raise RuntimeError("PRODUCER_REQUIRES_EXACT_DEVELOPMENT_INDICES_0_TO_31")
    packets = []
    for i, row in enumerate(manifest_rows, 1):
        packets.append(produce_stage1_attempt(row, tokenizer, model_provenance, runtime_factory, planner_fn, command_score_fn))
        if progress_fn is not None:
            progress_fn(i, len(manifest_rows))  # coarse attempted-count progress only
    return apply_stage2(tokenizer, packets)


def validate_packet_minimal(packet: Mapping[str, Any]) -> None:
    missing = [k for k in REQUIRED_PACKET_FIELDS if k not in packet]
    if missing:
        raise RuntimeError("PACKET_REQUIRED_FIELDS_MISSING:" + ",".join(missing))
    if packet["packet_contract_version"] != PACKET_CONTRACT_VERSION:
        raise RuntimeError("PACKET_CONTRACT_VERSION_MISMATCH")
    if packet["producer_contract_sha256"] != CONTRACT_SHA256:
        raise RuntimeError("PACKET_PRODUCER_CONTRACT_HASH_MISMATCH")
    if int(packet["frozen_index"]) not in DEV_INDICES:
        raise RuntimeError("PACKET_INDEX_OUTSIDE_DEVELOPMENT")
    if len(packet.get("actions", [])) > ACTION_BUDGET:
        raise RuntimeError("PACKET_ACTION_BUDGET_EXCEEDED")
    for row in packet.get("actions", []):
        missing_action = [k for k in REQUIRED_ACTION_FIELDS if k not in row]
        if missing_action:
            raise RuntimeError("ACTION_FIELDS_MISSING:" + ",".join(missing_action))
    if bool(packet.get("qualified")) and not bool(packet.get("trajectory_eligible")):
        raise RuntimeError("QUALIFIED_NOT_TRAJECTORY_ELIGIBLE")
    if packet["trajectory_sha256"] != trajectory_digest(dict(packet)):
        raise RuntimeError("TRAJECTORY_HASH_MISMATCH")


def packet_filename(index: int) -> str:
    return f"packet_{index:02d}.json"


def _write_fsync(path: Path, payload: bytes) -> None:
    with path.open("xb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def build_packet_manifest(packets: Sequence[Mapping[str, Any]], packet_hashes: Mapping[str, str]) -> dict[str, Any]:
    final_count = sum(bool(p["qualified"]) for p in packets)
    eligible_count = sum(bool(p["trajectory_eligible"]) for p in packets)
    return {
        "kind": "REPLAY_RESIDUAL_V2_1_PACKET_SET_MANIFEST",
        "producer_contract_sha256": CONTRACT_SHA256,
        "packet_contract_version": PACKET_CONTRACT_VERSION,
        "experiment_id": "fbfeb9e9-4850-46c7-ad13-326cbe8da380",
        "prediction_id": "d3208f84-ad00-47e3-ad77-c6a320e08c2d",
        "indices": list(DEV_INDICES),
        "packet_sha256_by_filename": dict(packet_hashes),
        "attempted_count": len(packets),
        "trajectory_eligible_count": eligible_count,
        "final_qualified_count": final_count,
        "minimum_final_qualified": MIN_FINAL_QUALIFIED,
        "below_minimum_label": None if final_count >= MIN_FINAL_QUALIFIED else "INCONCLUSIVE_INSUFFICIENT_NATURAL_TRAJECTORIES",
        "no_replacement": True,
        "anchor_cycle": ANCHOR_CYCLE,
        "publication_mode": "PRIVATE_INPROGRESS_FSYNC_VALIDATE_ATOMIC_RENAME_NO_RESUME",
        "scientific_result": "NOT_ASSESSED_PACKET_PRODUCTION_ONLY",
    }


def atomic_publish_packet_set(
    root: Path,
    packets: Sequence[Mapping[str, Any]],
    final_rel: Path = FINAL_TARGET_REL,
    validator_fn: Callable[[Path, Any], Any] | None = None,
    tokenizer: Any | None = None,
) -> tuple[Path, dict[str, Any]]:
    if [int(p["frozen_index"]) for p in packets] != list(DEV_INDICES) or len(packets) != 32:
        raise RuntimeError("ATOMIC_PUBLICATION_REQUIRES_EXACT_ALL32")
    final = root / final_rel
    if final.exists():
        raise FileExistsError(f"FINAL_PACKET_TARGET_ALREADY_EXISTS:{final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = final.parent / f".{final.name}.inprogress.{os.getpid()}.{uuid.uuid4().hex}"
    staging.mkdir(mode=0o700)
    try:
        hashes: dict[str, str] = {}
        for p in packets:
            validate_packet_minimal(p)
            name = packet_filename(int(p["frozen_index"]))
            payload = canonical_json_bytes(p)
            _write_fsync(staging / name, payload)
            hashes[name] = sha256_bytes(payload)
        manifest = build_packet_manifest(packets, hashes)
        manifest_bytes = canonical_json_bytes(manifest)
        _write_fsync(staging / "manifest.json", manifest_bytes)
        provenance = {
            "kind": "REPLAY_RESIDUAL_V2_1_PACKET_SET_PROVENANCE",
            "contract_path": str(CONTRACT_REL),
            "contract_sha256": CONTRACT_SHA256,
            "review_path": str(REVIEW_REL),
            "review_sha256": REVIEW_SHA256,
            "protocol_sha256": PROTOCOL_SHA256,
            "packet_manifest_sha256": sha256_bytes(manifest_bytes),
            "model_calls_during_engineering": 0,
            "environment_execution_during_engineering": 0,
            "scientific_outcomes_accessed_during_engineering": False,
        }
        _write_fsync(staging / "provenance.json", canonical_json_bytes(provenance))
        _fsync_dir(staging)

        expected_files = {packet_filename(i) for i in DEV_INDICES} | {"manifest.json", "provenance.json"}
        actual_files = {p.name for p in staging.iterdir() if p.is_file()}
        if actual_files != expected_files:
            raise RuntimeError(f"STAGING_FILE_SET_MISMATCH:{sorted(actual_files)}")
        for name, expected in hashes.items():
            if sha256_file(staging / name) != expected:
                raise RuntimeError(f"STAGING_PACKET_HASH_MISMATCH:{name}")
        if validator_fn is not None:
            validator_fn(staging, tokenizer)
        if final.exists():
            raise FileExistsError(f"FINAL_TARGET_RACE:{final}")
        os.rename(staging, final)  # same-parent atomic directory publication
        _fsync_dir(final.parent)
        return final, manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def derive_model_provenance(device_name: str) -> dict[str, Any]:
    out = dict(EXPECTED_MODEL_PROVENANCE)
    out["device_name"] = str(device_name)
    return out


def validate_model_provenance(prov: Mapping[str, Any]) -> None:
    for key, expected in EXPECTED_MODEL_PROVENANCE.items():
        if prov.get(key) != expected:
            raise RuntimeError(f"MODEL_PROVENANCE_MISMATCH:{key}:{prov.get(key)!r}:{expected!r}")
    if str(prov.get("device_name", "")) != EXPECTED_DEVICE_NAME:
        raise RuntimeError(f"MODEL_DEVICE_NAME_MISMATCH:{prov.get('device_name')!r}:{EXPECTED_DEVICE_NAME!r}")


def load_production_runtime(root: Path) -> tuple[Any, Any, Mapping[str, Any]]:
    """Load exact frozen Qwen3 runtime only in an explicit scientific execution."""
    import torch  # type: ignore
    import transformers  # type: ignore
    import tokenizers as tokenizers_pkg  # type: ignore
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    if str(torch.__version__) != TORCH_VERSION:
        raise RuntimeError(f"TORCH_VERSION_MISMATCH:{torch.__version__}:{TORCH_VERSION}")
    if str(transformers.__version__) != TRANSFORMERS_VERSION:
        raise RuntimeError(f"TRANSFORMERS_VERSION_MISMATCH:{transformers.__version__}:{TRANSFORMERS_VERSION}")
    if str(tokenizers_pkg.__version__) != TOKENIZERS_VERSION:
        raise RuntimeError(f"TOKENIZERS_VERSION_MISMATCH:{tokenizers_pkg.__version__}:{TOKENIZERS_VERSION}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA_REQUIRED")
    device_name = torch.cuda.get_device_name(0)
    if device_name != EXPECTED_DEVICE_NAME:
        raise RuntimeError(f"RTX3050_REQUIRED:{device_name}:{EXPECTED_DEVICE_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, torch_dtype=torch.bfloat16, trust_remote_code=False,
    ).to("cuda")
    model.eval()
    prov = derive_model_provenance(device_name)
    validate_model_provenance(prov)
    return tokenizer, model, prov


def default_runtime_factory(game_path: str) -> Any:
    from alfworld_runtime import AlfRuntime, DATA_ROOT
    return AlfRuntime(str(DATA_ROOT / game_path), max_steps=ACTION_BUDGET)


def execute_scientific_packet_production(root: Path) -> Path:
    """Explicit packet-production phase. This is not representation-sanity outcome inspection."""
    verify_frozen_bindings(root)
    tokenizer, model, provenance = load_production_runtime(root)
    manifest = development_manifest(root)
    planner = lambda task, obs: torch_generate_plan(tokenizer, model, task, obs)
    scorer = lambda prefix, suffix: torch_suffix_mean_logprob(model, prefix, suffix)
    packets = all32_attempts(
        manifest, tokenizer, provenance, default_runtime_factory, planner, scorer,
        progress_fn=lambda done, total: print(json.dumps({"attempted": done, "total": total}), flush=True),
    )
    from replay_residual_natural_packet_validator_v2_1 import validate_packet_directory
    final, _manifest = atomic_publish_packet_set(root, packets, validator_fn=validate_packet_directory, tokenizer=tokenizer)
    return final


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--execute-science", action="store_true",
                        help="Explicitly execute the frozen all-32 packet-production phase. Never implied by import/test.")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    verify_frozen_bindings(root)
    if not args.execute_science:
        print(json.dumps({"status": "READY_NO_EXECUTION", "contract_sha256": CONTRACT_SHA256}, sort_keys=True))
        return 0
    final = execute_scientific_packet_production(root)
    print(json.dumps({"status": "PACKETS_PUBLISHED", "path": str(final)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
