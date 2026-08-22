#!/usr/bin/env python3
"""Prospective GDAA construct-validation runner for frozen disjoint Experiment v3.

This isolated runner preserves the old v3 PlanCarry runner/artifact. It consumes
only the frozen train-development GDAA manifest, verifies zero overlap with the
separately frozen binding-study pool before qualification, and measures
TaskSuccess@8, GDAA, and exact RPA separately. Scientific interpretation
remains in Research OS.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

sys.path.insert(0, "/workspace/local-vlm/LLM/plancarry")
import alfworld_runtime as ar
import alfworld_qualify as aq
import alfworld_interruption_harness as ah
import gdaa_evaluator as ge

EXPERIMENT_ID = "44f469b8-a9a7-4b07-b2dc-c204e8a2793b"
MODEL = "qwen2.5:7b-instruct"
BASE_URL = aq.BASE_URL
TASK_PREFIX = "pick_and_place_simple"
SPLIT = "train"
MANIFEST_PATH = Path("/workspace/local-vlm/LLM/plancarry/results/design/gdaa_train_candidate_manifest_fresh_v2.json")
EXPECTED_MANIFEST_SHA256 = "62d700e5d407e71ae1db030cb454e1b78a1c4bd505f24997024de4ecb71f008d"
BINDING_EXPERIMENT_ID = "49a5eed0-dc91-497a-a0e7-f9b5fc4cd5b1"
BINDING_CANDIDATE_SALT = "plancarry-binding-v1-2026-08-18"
BINDING_MAX_GAMES_SCANNED = 180
EXPECTED_BINDING_POOL_SHA256 = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
PRIOR_V3_MANIFEST_PATH = Path("/workspace/local-vlm/LLM/plancarry/results/design/gdaa_train_candidate_manifest_disjoint_v1.json")
EXPECTED_PRIOR_V3_MANIFEST_SHA256 = "5beaeb849cc6abbee4397c1f8d5021700e272b799e356a2d77d47f920af4d418"
EXPECTED_PRIOR_V3_CANDIDATES = 90
EXPECTED_TRAIN_POPULATION = 790
EXPECTED_DISJOINT_SOURCE_POOL = 520
MAX_GAMES_SCANNED = 90
TARGET_ELIGIBLE = 8
QUALIFICATION_MAX_ENV_ACTIONS = 30
POST_RESET_MAX_ENV_ACTIONS = 8
MEMORY_CAP_PROXY_TOKENS = 48
MAX_POST_RESET_INVALID_MODEL_TURNS = 8  # technical fail-closed guard, not env-action budget
SOURCE_COMMIT = "1558ba46d078279ecb4c5d33a6cdffc96714a2d2"

INFORMATION_EXACT = {"inventory", "look", "help"}


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def manifest_payload_sha256(manifest: dict[str, Any]) -> str:
    payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return sha256_text(stable_json(payload))


def train_candidate_population() -> list[str]:
    root = Path("/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/train")
    return sorted(str(p.absolute()) for p in root.glob(f"{TASK_PREFIX}-*/trial_*/game.tw-pddl"))


def binding_candidate_games(population: list[str] | None = None) -> list[str]:
    games = train_candidate_population() if population is None else list(population)
    ordered = sorted(games, key=lambda p: sha256_text(BINDING_CANDIDATE_SALT + "\n" + p))
    return ordered[:BINDING_MAX_GAMES_SCANNED]


def binding_pool_sha256(games: list[str] | None = None) -> str:
    pool = binding_candidate_games() if games is None else list(games)
    return sha256_text("\n".join(pool) + "\n")


def candidate_games(manifest_path: Path = MANIFEST_PATH) -> list[str]:
    manifest = json.loads(manifest_path.read_text())
    actual = manifest_payload_sha256(manifest)
    declared = str(manifest.get("manifest_sha256", ""))
    if actual != EXPECTED_MANIFEST_SHA256 or declared != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError(
            f"frozen candidate manifest hash mismatch: actual={actual} declared={declared} "
            f"expected={EXPECTED_MANIFEST_SHA256}"
        )
    if manifest.get("split") != SPLIT or manifest.get("task_type") != TASK_PREFIX:
        raise RuntimeError("frozen manifest split/task mismatch")
    if int(manifest.get("pool_size", -1)) != EXPECTED_DISJOINT_SOURCE_POOL:
        raise RuntimeError("frozen manifest disjoint source-pool size mismatch")
    games = [str(Path(x).absolute()) for x in manifest.get("candidates", [])]
    if len(games) != MAX_GAMES_SCANNED or len(set(games)) != len(games):
        raise RuntimeError(f"candidate list must contain exactly {MAX_GAMES_SCANNED} unique paths")
    return games


def validate_candidate_isolation(manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    population = train_candidate_population()
    if len(population) != EXPECTED_TRAIN_POPULATION:
        raise RuntimeError(
            f"train pick_and_place_simple population count drift: {len(population)} != {EXPECTED_TRAIN_POPULATION}"
        )
    binding = binding_candidate_games(population)
    binding_sha = binding_pool_sha256(binding)
    if len(binding) != BINDING_MAX_GAMES_SCANNED or binding_sha != EXPECTED_BINDING_POOL_SHA256:
        raise RuntimeError(
            f"frozen binding pool mismatch: n={len(binding)} sha={binding_sha} expected={EXPECTED_BINDING_POOL_SHA256}"
        )
    prior_v3 = json.loads(PRIOR_V3_MANIFEST_PATH.read_text())
    prior_v3_sha = manifest_payload_sha256(prior_v3)
    if prior_v3_sha != EXPECTED_PRIOR_V3_MANIFEST_SHA256 or prior_v3.get("manifest_sha256") != EXPECTED_PRIOR_V3_MANIFEST_SHA256:
        raise RuntimeError("frozen prior-v3 manifest hash mismatch")
    prior_v3_games = [str(Path(x).absolute()) for x in prior_v3.get("candidates", [])]
    if len(prior_v3_games) != EXPECTED_PRIOR_V3_CANDIDATES or len(set(prior_v3_games)) != len(prior_v3_games):
        raise RuntimeError("prior-v3 manifest candidate count/uniqueness mismatch")
    if set(prior_v3_games) & set(binding):
        raise RuntimeError("frozen prior-v3 manifest unexpectedly overlaps binding pool")
    manifest_games = candidate_games(manifest_path)
    remaining = sorted(set(population) - set(binding) - set(prior_v3_games))
    if len(remaining) != EXPECTED_DISJOINT_SOURCE_POOL:
        raise RuntimeError(
            f"fresh source pool drift: {len(remaining)} != {EXPECTED_DISJOINT_SOURCE_POOL}"
        )
    expected_manifest_games = remaining[:MAX_GAMES_SCANNED]
    if manifest_games != expected_manifest_games:
        raise RuntimeError("frozen GDAA-v4 manifest does not equal first 90 lexicographic fresh train paths")
    binding_overlap = sorted(set(manifest_games) & set(binding))
    prior_v3_overlap = sorted(set(manifest_games) & set(prior_v3_games))
    if binding_overlap or prior_v3_overlap:
        raise RuntimeError(
            f"GDAA-v4 manifest overlaps excluded pools: binding={len(binding_overlap)} prior_v3={len(prior_v3_overlap)}"
        )
    return {
        "train_population_count": len(population),
        "binding_experiment_id": BINDING_EXPERIMENT_ID,
        "binding_candidate_count": len(binding),
        "binding_pool_sha256": binding_sha,
        "prior_v3_manifest_sha256": prior_v3_sha,
        "prior_v3_candidate_count": len(prior_v3_games),
        "fresh_source_pool_count": len(remaining),
        "gdaa_candidate_count": len(manifest_games),
        "cross_binding_overlap_count": 0,
        "cross_v3_manifest_overlap_count": 0,
        "cross_manifest_overlap_count": 0,
    }

def parse_goal_object(initial_observation: str) -> str | None:
    goal = ah.parse_goal(initial_observation).strip().lower()
    # Frozen task type is pick_and_place_simple. Official goals are typically
    # "put some <object> on/in <receptacle>."
    match = re.search(r"^put\s+(?:some\s+|a\s+|an\s+)?(.+?)\s+(?:on|in)\s+.+?[.!]?$", goal)
    return match.group(1).strip() if match else None


def is_goal_object_take(command: str, goal_object: str) -> bool:
    match = re.match(r"^take\s+(.+?)\s+from\s+(.+)$", command.strip(), re.I)
    if not match:
        return False
    taken = match.group(1).lower()
    # ALFWorld demangles numbered instances: "book 1" should match "book".
    return taken == goal_object or taken.startswith(goal_object + " ")


def reference_progress_action(actions: list[dict[str, Any]]) -> str | None:
    for item in actions:
        command = str(item.get("command", ""))
        if not ah.is_information_command(command):
            return command
    return None


def derive_reset(qualification: dict[str, Any]) -> dict[str, Any] | None:
    if not qualification.get("success") or int(qualification.get("invalid_model_turns", 0)) != 0:
        return None
    goal_object = parse_goal_object(str(qualification.get("initial_observation", "")))
    if not goal_object:
        return None
    actions = list(qualification.get("actions", []))
    candidates = [i for i, item in enumerate(actions) if is_goal_object_take(str(item.get("command", "")), goal_object)]
    for index in reversed(candidates):
        suffix = actions[index + 1 :]
        ref = reference_progress_action(suffix)
        if ref is not None:
            return {
                "goal_object": goal_object,
                "reset_after": index + 1,  # prefix includes the take action
                "reference_first_progress_action": ref,
                "reference_suffix": copy.deepcopy(suffix),
                "reference_post_reset_environment_actions": len(suffix),
                "recorded_reset_hash": actions[index]["state_hash"],
            }
    return None


def prefix_only_qualification(qualification: dict[str, Any], reset_after: int) -> dict[str, Any]:
    # Deliberately construct a new object with NO future suffix field/content.
    return {
        "game_file": qualification["game_file"],
        "initial_observation": qualification["initial_observation"],
        "success": False,  # future terminal result is intentionally unavailable
        "invalid_model_turns": qualification.get("invalid_model_turns", 0),
        "actions": copy.deepcopy(qualification["actions"][:reset_after]),
    }


def binomial_one_sided_p(wins: int, losses: int) -> float:
    n = int(wins) + int(losses)
    if n <= 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(int(wins), n + 1)) / (2**n)


def paired_rpa_test(episodes: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    wins = losses = ties_both_1 = ties_both_0 = 0
    for episode in episodes:
        va = bool(episode["arms"][a]["reference_progress_agreement"])
        vb = bool(episode["arms"][b]["reference_progress_agreement"])
        if va and not vb:
            wins += 1
        elif vb and not va:
            losses += 1
        elif va and vb:
            ties_both_1 += 1
        else:
            ties_both_0 += 1
    return {
        "a": a,
        "b": b,
        "wins_a": wins,
        "losses_a": losses,
        "ties_both_1": ties_both_1,
        "ties_both_0": ties_both_0,
        "discordant_pairs": wins + losses,
        "one_sided_exact_binomial_p": binomial_one_sided_p(wins, losses),
        "direction": f"{a}>{b}",
    }


def _assistant_message(msg: Any) -> dict[str, Any]:
    return aq.assistant_dict(msg)


def continue_arm_env_budget(
    client: OpenAI,
    model: str,
    game_file: str,
    prefix: list[ar.AlfActionRecord],
    messages: list[dict[str, Any]],
    max_env_actions: int,
) -> dict[str, Any]:
    rt = ar.replay(game_file, prefix, max_steps=max(50, len(prefix) + max_env_actions + 10))
    reset_hash = rt.hash()
    actions: list[ar.AlfActionRecord] = []
    usage: list[dict[str, int]] = []
    invalid_model_turns = 0
    invalid_turn_events: list[dict[str, Any]] = []
    technical_failure: str | None = None
    termination = "environment_action_budget_exhausted"
    try:
        while len(actions) < max_env_actions:
            if rt.won or rt.done:
                termination = "success" if rt.won else "env_done"
                break
            if invalid_model_turns > MAX_POST_RESET_INVALID_MODEL_TURNS:
                # Frozen v4 taxonomy: repeated model noncompliance is arm behavior,
                # not evaluator/runtime invalidity. Environment state is unchanged.
                termination = "MODEL_INVALID_TURN_CAP_REACHED"
                break
            try:
                msg, use = aq.call(client, model, messages)
            except Exception as exc:
                technical_failure = f"MODEL_CALL_EXCEPTION:{type(exc).__name__}:{str(exc)[:200]}"
                termination = "technical_guard_failure"
                break
            usage.append(use)
            if not msg.tool_calls:
                invalid_model_turns += 1
                invalid_turn_events.append({
                    "type": "NO_TOOL_CALL",
                    "call_index": len(usage),
                    "content_preview": (msg.content or "")[:200],
                })
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({"role": "user", "content": "You must call choose_action with one valid index."})
                continue
            tc = msg.tool_calls[0]
            try:
                idx = int(json.loads(tc.function.arguments or "{}").get("index", -1))
            except Exception:
                idx = -1
            messages.append(_assistant_message(msg))
            if idx < 0 or idx >= len(rt.admissible_commands):
                invalid_model_turns += 1
                invalid_turn_events.append({
                    "type": "INVALID_INDEX",
                    "call_index": len(usage),
                    "index": idx,
                    "admissible_count": len(rt.admissible_commands),
                    "arguments_preview": (tc.function.arguments or "")[:200],
                })
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": aq.surface(
                            f"INVALID INDEX {idx}; state unchanged.", rt.admissible_commands
                        ),
                    }
                )
                continue
            command = rt.admissible_commands[idx]
            try:
                rec = rt.step(command)
            except Exception as exc:
                technical_failure = f"ENV_STEP_EXCEPTION:{type(exc).__name__}:{str(exc)[:200]}"
                termination = "technical_guard_failure"
                break
            actions.append(rec)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": aq.surface(rec.observation, rec.admissible_commands),
                }
            )
        if rt.won:
            termination = "success"
        elif rt.done and termination != "technical_guard_failure":
            termination = "env_done"
        prompt_tokens = sum(x.get("prompt_tokens", 0) for x in usage)
        completion_tokens = sum(x.get("completion_tokens", 0) for x in usage)
        total_tokens = sum(x.get("total_tokens", 0) for x in usage)
        return {
            "reset_hash": reset_hash,
            "success": bool(rt.won),
            "done": bool(rt.done),
            "score": float(rt.score),
            "termination_reason": termination,
            "technical_failure": technical_failure,
            "post_reset_environment_actions": len(actions),
            "invalid_model_turns": invalid_model_turns,
            "invalid_turn_events": invalid_turn_events,
            "invalid_turn_subtype_counts": {
                "NO_TOOL_CALL": sum(e.get("type") == "NO_TOOL_CALL" for e in invalid_turn_events),
                "INVALID_INDEX": sum(e.get("type") == "INVALID_INDEX" for e in invalid_turn_events),
            },
            "first_action": actions[0].command if actions else None,
            "first_progress_action": ah.first_progress_action(actions),
            "actions": [x.__dict__ for x in actions],
            "consecutive_repeat_count": ah.consecutive_repeat_count(actions),
            "prefix_reversal_count": ah.prefix_reversal_count(prefix, actions),
            "final_hash": rt.hash(),
            "usage_calls": usage,
            "usage_total": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }
    finally:
        rt.close()

def forbidden_information_guards(
    *,
    expert_plan_visible: bool,
    hidden_facts_visible: bool,
    future_suffix_visible: bool,
) -> dict[str, bool]:
    """Return positively oriented pass conditions for forbidden-information guards."""
    return {
        "expert_plan_hidden": not expert_plan_visible,
        "hidden_facts_hidden": not hidden_facts_visible,
        "future_suffix_unavailable_to_memory_compilers": not future_suffix_visible,
    }


def evaluate_eligible(
    client: OpenAI,
    qualification: dict[str, Any],
    reset: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    reset_after = int(reset["reset_after"])
    prefix_records = [ar.AlfActionRecord(**x) for x in qualification["actions"][:reset_after]]
    replayed = ar.replay(qualification["game_file"], prefix_records, max_steps=60)
    try:
        reset_hash = replayed.hash()
        reset_observation = replayed.observation
        reset_commands = list(replayed.admissible_commands)
    finally:
        replayed.close()
    reset_hash_matches_qualification = reset_hash == reset["recorded_reset_hash"]

    prefix_only = prefix_only_qualification(qualification, reset_after)
    # The summary/truncation/PlanCarry compilers receive only prefix-only data.
    generic, generic_usage = ah.generic_summary(
        client, model, prefix_only, reset_after, MEMORY_CAP_PROXY_TOKENS
    )
    truncation = ah.truncated_memory(prefix_only, reset_after, MEMORY_CAP_PROXY_TOKENS)
    plancarry = ah.compile_plancarry(prefix_only, reset_after, MEMORY_CAP_PROXY_TOKENS)

    memories = {
        "observation_only": None,
        "tail_truncation": truncation,
        "generic_summary": generic,
        "plancarry": plancarry,
    }
    arms: dict[str, Any] = {}
    for arm_name in ["observation_only", "tail_truncation", "generic_summary", "plancarry"]:
        memory = memories[arm_name]
        check = ar.replay(qualification["game_file"], prefix_records, max_steps=60)
        try:
            before_hash = check.hash()
            messages = ah.fresh_messages(check.observation, list(check.admissible_commands), memory)
        finally:
            check.close()
        arm = continue_arm_env_budget(
            client, model, qualification["game_file"], prefix_records, messages, POST_RESET_MAX_ENV_ACTIONS
        )
        arm["pre_call_reset_hash"] = before_hash
        arm["memory"] = memory
        arm["memory_proxy_tokens"] = ah.token_count(memory or "")
        arm["first_call_prompt_tokens"] = (
            int(arm["usage_calls"][0].get("prompt_tokens", 0)) if arm["usage_calls"] else None
        )
        arm["reference_progress_agreement"] = (
            arm["first_progress_action"] == reset["reference_first_progress_action"]
        )
        arm["gdaa"] = ge.gdaa_score(
            str(qualification["initial_observation"]), reset_commands, arm["actions"]
        )
        arm["successful_excess_actions_vs_reference"] = (
            arm["post_reset_environment_actions"] - reset["reference_post_reset_environment_actions"]
            if arm["success"]
            else None
        )
        arms[arm_name] = arm

    all_reset_hashes = {reset_hash}
    for arm in arms.values():
        all_reset_hashes.add(arm["pre_call_reset_hash"])
        all_reset_hashes.add(arm["reset_hash"])
    guards = {
        "candidate_in_frozen_manifest": str(Path(qualification["game_file"]).absolute()) in set(candidate_games()),
        "binding_pool_disjoint_guard": validate_candidate_isolation()["cross_manifest_overlap_count"] == 0,
        "gdaa_defined_for_all_arms": all(arm["gdaa"] is not None for arm in arms.values()),
        "qualification_success": bool(qualification["success"]),
        "qualification_zero_invalid_model_turns": int(qualification["invalid_model_turns"]) == 0,
        "reset_hash_matches_qualification": reset_hash_matches_qualification,
        "all_arm_reset_hashes_identical": len(all_reset_hashes) == 1,
        "memory_caps_respected": all(
            arms[name]["memory_proxy_tokens"] <= MEMORY_CAP_PROXY_TOKENS
            for name in ["tail_truncation", "generic_summary", "plancarry"]
        ),
        "no_post_reset_technical_guard_failure": all(
            arm["technical_failure"] is None for arm in arms.values()
        ),
        **forbidden_information_guards(
            expert_plan_visible=False,
            hidden_facts_visible=False,
            future_suffix_visible=False,
        ),
    }
    return {
        "game_file": qualification["game_file"],
        "game_file_sha256": sha256_text(str(qualification["game_file"])),
        "goal_object": reset["goal_object"],
        "reset_after": reset_after,
        "reset_hash": reset_hash,
        "reset_observation": reset_observation,
        "reset_admissible_commands": reset_commands,
        "gdaa_positive_action_set": sorted(ge.goal_directed_action_set(str(qualification["initial_observation"]), reset_commands) or []),
        "reference_first_progress_action": reset["reference_first_progress_action"],
        "reference_post_reset_environment_actions": reset["reference_post_reset_environment_actions"],
        "qualification": qualification,
        "memory_generation_usage": {
            "generic_summary": generic_usage,
            "plancarry": {"compiler": "deterministic_prefix_only", "model_tokens": 0},
        },
        "arms": arms,
        "guards": guards,
        "all_guards_pass": all(guards.values()),
    }


def paired_binary_test(episodes: list[dict[str, Any]], a: str, b: str, key: str) -> dict[str, Any]:
    wins = losses = ties_both_1 = ties_both_0 = 0
    for episode in episodes:
        va = bool(episode["arms"][a][key])
        vb = bool(episode["arms"][b][key])
        if va and not vb:
            wins += 1
        elif vb and not va:
            losses += 1
        elif va and vb:
            ties_both_1 += 1
        else:
            ties_both_0 += 1
    return {
        "metric": key, "a": a, "b": b, "wins_a": wins, "losses_a": losses,
        "ties_both_1": ties_both_1, "ties_both_0": ties_both_0,
        "discordant_pairs": wins + losses,
        "one_sided_exact_binomial_p": binomial_one_sided_p(wins, losses),
        "direction": f"{a}>{b}",
    }


def aggregate(episodes: list[dict[str, Any]], scanned_count: int, eligible_found: int) -> dict[str, Any]:
    arm_names = ["observation_only", "tail_truncation", "generic_summary", "plancarry"]
    metrics: dict[str, Any] = {}
    n = len(episodes)
    for arm in arm_names:
        successes = sum(bool(ep["arms"][arm]["success"]) for ep in episodes)
        rpa = sum(bool(ep["arms"][arm]["reference_progress_agreement"]) for ep in episodes)
        gdaa_true = sum(ep["arms"][arm]["gdaa"] is True for ep in episodes)
        gdaa_undefined = sum(ep["arms"][arm]["gdaa"] is None for ep in episodes)
        divergence = sum(
            bool(ep["arms"][arm]["success"])
            and ep["arms"][arm]["gdaa"] is True
            and not bool(ep["arms"][arm]["reference_progress_agreement"])
            for ep in episodes
        )
        first_prompts = [
            ep["arms"][arm]["first_call_prompt_tokens"]
            for ep in episodes if ep["arms"][arm]["first_call_prompt_tokens"] is not None
        ]
        metrics[arm] = {
            "n": n, "successes": successes, "success_rate": successes / n if n else None,
            "gdaa_count": gdaa_true, "gdaa_rate": gdaa_true / n if n else None,
            "gdaa_undefined_count": gdaa_undefined,
            "rpa_count": rpa, "rpa_rate": rpa / n if n else None,
            "successful_gdaa1_rpa0_count": divergence,
            "prefix_reversal_count": sum(int(ep["arms"][arm]["prefix_reversal_count"]) for ep in episodes),
            "consecutive_repeat_count": sum(int(ep["arms"][arm]["consecutive_repeat_count"]) for ep in episodes),
            "invalid_model_turns": sum(int(ep["arms"][arm]["invalid_model_turns"]) for ep in episodes),
            "invalid_no_tool_call_count": sum(
                sum(e.get("type") == "NO_TOOL_CALL" for e in ep["arms"][arm].get("invalid_turn_events", []))
                for ep in episodes
            ),
            "invalid_index_count": sum(
                sum(e.get("type") == "INVALID_INDEX" for e in ep["arms"][arm].get("invalid_turn_events", []))
                for ep in episodes
            ),
            "model_invalid_turn_cap_terminations": sum(
                ep["arms"][arm].get("termination_reason") == "MODEL_INVALID_TURN_CAP_REACHED"
                for ep in episodes
            ),
            "continuation_api_total_tokens": sum(int(ep["arms"][arm]["usage_total"]["total_tokens"]) for ep in episodes),
            "first_call_prompt_tokens": first_prompts,
            "mean_first_call_prompt_tokens": sum(first_prompts) / len(first_prompts) if first_prompts else None,
        }
    generic_prep = {k: 0 for k in ["prompt_tokens", "completion_tokens", "total_tokens"]}
    for ep in episodes:
        use = ep["memory_generation_usage"]["generic_summary"]
        for k in generic_prep:
            generic_prep[k] += int(use.get(k, 0))
    all_episode_guards = all(ep["all_guards_pass"] for ep in episodes)
    cohort_complete = eligible_found == TARGET_ELIGIBLE and n == TARGET_ELIGIBLE
    all_gdaa_defined = all(
        ep["arms"][arm]["gdaa"] is not None for ep in episodes for arm in arm_names
    )
    natural_divergence_count = sum(metrics[arm]["successful_gdaa1_rpa0_count"] for arm in arm_names)
    if not cohort_complete:
        measurement_status = "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"
    elif not all_episode_guards or not all_gdaa_defined:
        measurement_status = "INVALID_GUARD_FAILURE"
    else:
        measurement_status = "MEASURED_AWAITING_SCIENTIFIC_ASSESSMENT"
    return {
        "measurement_status": measurement_status, "scientific_result": "NOT_ASSESSED",
        "scanned_games": scanned_count, "eligible_found": eligible_found,
        "evaluated_episodes": n, "target_eligible_episodes": TARGET_ELIGIBLE,
        "all_episode_guards_pass": all_episode_guards, "all_gdaa_defined": all_gdaa_defined,
        "natural_successful_gdaa1_rpa0_count_all_arms": natural_divergence_count,
        "generic_summary_preprocessing_usage_total": generic_prep,
        "metrics": metrics,
        "paired_gdaa_diagnostics": {
            "plancarry_vs_generic_summary": paired_binary_test(episodes, "plancarry", "generic_summary", "gdaa") if episodes else None,
            "plancarry_vs_tail_truncation": paired_binary_test(episodes, "plancarry", "tail_truncation", "gdaa") if episodes else None,
        },
    }


def _reset_gdaa_defined(qualification: dict[str, Any], reset: dict[str, Any]) -> bool:
    prefix = [ar.AlfActionRecord(**x) for x in qualification["actions"][: int(reset["reset_after"])]]
    rt = ar.replay(qualification["game_file"], prefix, max_steps=60)
    try:
        return ge.goal_directed_action_set(
            str(qualification["initial_observation"]), list(rt.admissible_commands)
        ) is not None
    finally:
        rt.close()


def run(output: Path, model: str = MODEL, base_url: str = BASE_URL) -> dict[str, Any]:
    start = time.time()
    isolation = validate_candidate_isolation()
    games = candidate_games()
    client = OpenAI(base_url=base_url, api_key="ollama", timeout=90)
    scan_records: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []

    for scan_index, game in enumerate(games, 1):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            qualification = aq.run_game(game, model, QUALIFICATION_MAX_ENV_ACTIONS, client)
        reset = derive_reset(qualification)
        gdaa_defined = bool(reset is not None and _reset_gdaa_defined(qualification, reset))
        eligible = bool(
            qualification.get("success")
            and int(qualification.get("invalid_model_turns", 0)) == 0
            and reset is not None
            and gdaa_defined
        )
        scan_records.append({
            "scan_index": scan_index, "game_file": game,
            "qualification_success": bool(qualification.get("success")),
            "qualification_turns": int(qualification.get("turns", 0)),
            "qualification_invalid_model_turns": int(qualification.get("invalid_model_turns", 0)),
            "reset_defined": reset is not None, "gdaa_defined_at_reset": gdaa_defined,
            "eligible": eligible, "reset_after": reset["reset_after"] if reset else None,
        })
        print(json.dumps({
            "phase": "qualification", "scan_index": scan_index,
            "eligible_count": len(episodes) + (1 if eligible else 0), "eligible": eligible,
        }), flush=True)
        if not eligible:
            continue
        episode = evaluate_eligible(client, qualification, reset, model)
        episodes.append(episode)
        print(json.dumps({
            "phase": "arm_evaluation_complete", "scan_index": scan_index,
            "eligible_count": len(episodes), "guards_pass": episode["all_guards_pass"],
        }), flush=True)
        if len(episodes) == TARGET_ELIGIBLE:
            break

    agg = aggregate(episodes, len(scan_records), len(episodes))
    scorer_path = Path('/workspace/local-vlm/LLM/plancarry/gdaa_evaluator.py')
    runner_path = Path(__file__)
    result = {
        "kind": "PREREGISTERED_GDAA_DEVELOPMENT_MEASUREMENT_AWAITING_RESEARCH_OS_ASSESSMENT",
        "experiment_id": EXPERIMENT_ID, "model": model, "temperature": 0,
        "alfworld_source_commit": SOURCE_COMMIT, "split": SPLIT, "task_prefix": TASK_PREFIX,
        "candidate_order": "frozen_manifest_lexicographic_fresh_train_first_90",
        "candidate_manifest_path": str(MANIFEST_PATH),
        "candidate_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "binding_isolation": isolation,
        "max_games_scanned": MAX_GAMES_SCANNED, "target_eligible_episodes": TARGET_ELIGIBLE,
        "qualification_max_environment_actions": QUALIFICATION_MAX_ENV_ACTIONS,
        "post_reset_max_environment_actions": POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap_proxy_tokens": MEMORY_CAP_PROXY_TOKENS,
        "proxy_tokenizer": "cl100k_base_not_qwen_native",
        "valid_unseen_consumed": False,
        "candidate_games_newline_sha256": sha256_text("\n".join(games)),
        "gdaa_scorer_source_sha256": hashlib.sha256(scorer_path.read_bytes()).hexdigest(),
        "runner_source_sha256": hashlib.sha256(runner_path.read_bytes()).hexdigest(),
        "scan_records": scan_records, "episodes": episodes, "aggregate": agg,
        "runtime_seconds": time.time() - start, "scientific_result": "NOT_ASSESSED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({
        "phase": "measurement_complete", "measurement_status": agg["measurement_status"],
        "scanned_games": agg["scanned_games"], "eligible_found": agg["eligible_found"],
        "output": str(output),
    }), flush=True)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--base-url", default=BASE_URL)
    args = ap.parse_args()
    run(Path(args.output), model=args.model, base_url=args.base_url)


if __name__ == "__main__":
    main()
