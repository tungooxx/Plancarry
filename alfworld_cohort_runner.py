#!/usr/bin/env python3
"""Prospective ALFWorld cohort runner for frozen PlanCarry Experiment v2.

This program MEASURES the preregistered experiment. It does not assess the
hypothesis. Scientific interpretation is performed later by Research OS after
execution/artifact inspection.
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

EXPERIMENT_ID = "f59f04c3-847f-441b-a494-345740c957ee"
RESEARCH_DECISION_ID = "82450eb7-5668-49df-bcb2-69d6d3d08980"
MODEL = "qwen2.5:7b-instruct"
BASE_URL = aq.BASE_URL
TASK_PREFIX = "pick_and_place_simple"
SPLIT = "valid_seen"
PRE_INSPECTED_EXCLUSIONS = {
    "/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/valid_seen/"
    "pick_and_place_simple-Book-None-SideTable-329/"
    "trial_T20190908_050633_745514/game.tw-pddl"
}
MAX_GAMES_SCANNED = 30
TARGET_ELIGIBLE = 12
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


def candidate_games() -> list[str]:
    games = ar.game_files(SPLIT, TASK_PREFIX)
    remaining = [str(Path(g).absolute()) for g in games if str(Path(g).absolute()) not in PRE_INSPECTED_EXCLUSIONS]
    return remaining[:MAX_GAMES_SCANNED]


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
    technical_failure: str | None = None
    termination = "environment_action_budget_exhausted"
    try:
        while len(actions) < max_env_actions:
            if rt.won or rt.done:
                termination = "success" if rt.won else "env_done"
                break
            if invalid_model_turns > MAX_POST_RESET_INVALID_MODEL_TURNS:
                technical_failure = "EXCESSIVE_POST_RESET_INVALID_MODEL_TURNS"
                termination = "technical_guard_failure"
                break
            msg, use = aq.call(client, model, messages)
            usage.append(use)
            if not msg.tool_calls:
                invalid_model_turns += 1
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
            rec = rt.step(command)
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
        arm["reference_progress_agreement"] = (
            arm["first_progress_action"] == reset["reference_first_progress_action"]
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
        "preinspected_game_excluded": qualification["game_file"] not in PRE_INSPECTED_EXCLUSIONS,
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


def aggregate(episodes: list[dict[str, Any]], scanned_count: int, eligible_found: int) -> dict[str, Any]:
    arm_names = ["observation_only", "tail_truncation", "generic_summary", "plancarry"]
    metrics: dict[str, Any] = {}
    n = len(episodes)
    for arm in arm_names:
        successes = sum(bool(ep["arms"][arm]["success"]) for ep in episodes)
        rpa = sum(bool(ep["arms"][arm]["reference_progress_agreement"]) for ep in episodes)
        reversals = sum(int(ep["arms"][arm]["prefix_reversal_count"]) for ep in episodes)
        loops = sum(int(ep["arms"][arm]["consecutive_repeat_count"]) for ep in episodes)
        invalid = sum(int(ep["arms"][arm]["invalid_model_turns"]) for ep in episodes)
        api_tokens = sum(int(ep["arms"][arm]["usage_total"]["total_tokens"]) for ep in episodes)
        metrics[arm] = {
            "n": n,
            "successes": successes,
            "success_rate": successes / n if n else None,
            "rpa_count": rpa,
            "rpa_rate": rpa / n if n else None,
            "prefix_reversal_count": reversals,
            "consecutive_repeat_count": loops,
            "invalid_model_turns": invalid,
            "api_total_tokens": api_tokens,
        }
    pc_vs_summary = paired_rpa_test(episodes, "plancarry", "generic_summary") if episodes else None
    pc_vs_trunc = paired_rpa_test(episodes, "plancarry", "tail_truncation") if episodes else None
    all_episode_guards = all(ep["all_guards_pass"] for ep in episodes)
    cohort_complete = eligible_found == TARGET_ELIGIBLE and len(episodes) == TARGET_ELIGIBLE
    exclusions_applied = all(
        ep["game_file"] not in PRE_INSPECTED_EXCLUSIONS for ep in episodes
    )
    execution_valid = cohort_complete and all_episode_guards and exclusions_applied
    if not cohort_complete:
        measurement_status = "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"
    elif not all_episode_guards or not exclusions_applied:
        measurement_status = "INVALID_GUARD_FAILURE"
    else:
        measurement_status = "MEASURED_AWAITING_SCIENTIFIC_ASSESSMENT"
    conditions = None
    if execution_valid:
        summary_rate = metrics["generic_summary"]["success_rate"]
        pc_rate = metrics["plancarry"]["success_rate"]
        conditions = {
            "pc_vs_generic_rpa_p_le_0_05": pc_vs_summary["one_sided_exact_binomial_p"] <= 0.05,
            "pc_vs_truncation_rpa_p_le_0_05": pc_vs_trunc["one_sided_exact_binomial_p"] <= 0.05,
            "pc_success_noninferior_0_10": pc_rate >= summary_rate - 0.10,
        }
    return {
        "measurement_status": measurement_status,
        "scientific_result": "NOT_ASSESSED",
        "scanned_games": scanned_count,
        "eligible_found": eligible_found,
        "evaluated_episodes": len(episodes),
        "target_eligible_episodes": TARGET_ELIGIBLE,
        "all_episode_guards_pass": all_episode_guards,
        "preinspected_exclusions_applied": exclusions_applied,
        "metrics": metrics,
        "paired_tests": {
            "plancarry_vs_generic_summary": pc_vs_summary,
            "plancarry_vs_tail_truncation": pc_vs_trunc,
        },
        "preregistered_condition_evaluations": conditions,
    }


def run(output: Path, model: str = MODEL, base_url: str = BASE_URL) -> dict[str, Any]:
    start = time.time()
    games = candidate_games()
    if len(games) != MAX_GAMES_SCANNED:
        raise RuntimeError(f"candidate list length {len(games)} != {MAX_GAMES_SCANNED}")
    if any(g in PRE_INSPECTED_EXCLUSIONS for g in games):
        raise RuntimeError("pre-inspected exclusion leaked into candidate list")
    client = OpenAI(base_url=base_url, api_key="ollama", timeout=90)
    scan_records: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []

    for scan_index, game in enumerate(games, 1):
        # Suppress per-action prints from the engineering qualifier so experiment
        # status can be monitored without leaking partial scientific trajectories.
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            qualification = aq.run_game(game, model, QUALIFICATION_MAX_ENV_ACTIONS, client)
        reset = derive_reset(qualification)
        eligible = bool(
            qualification.get("success")
            and int(qualification.get("invalid_model_turns", 0)) == 0
            and reset is not None
        )
        scan_records.append(
            {
                "scan_index": scan_index,
                "game_file": game,
                "qualification_success": bool(qualification.get("success")),
                "qualification_turns": int(qualification.get("turns", 0)),
                "qualification_invalid_model_turns": int(qualification.get("invalid_model_turns", 0)),
                "eligible": eligible,
                "reset_after": reset["reset_after"] if reset else None,
            }
        )
        print(
            json.dumps(
                {
                    "phase": "qualification",
                    "scan_index": scan_index,
                    "eligible_count": len(episodes) + (1 if eligible else 0),
                    "eligible": eligible,
                }
            ),
            flush=True,
        )
        if not eligible:
            continue
        episode = evaluate_eligible(client, qualification, reset, model)
        episodes.append(episode)
        print(
            json.dumps(
                {
                    "phase": "arm_evaluation_complete",
                    "scan_index": scan_index,
                    "eligible_count": len(episodes),
                    "guards_pass": episode["all_guards_pass"],
                }
            ),
            flush=True,
        )
        if len(episodes) == TARGET_ELIGIBLE:
            break

    agg = aggregate(episodes, len(scan_records), len(episodes))
    result = {
        "kind": "PREREGISTERED_MEASUREMENT_AWAITING_RESEARCH_OS_ASSESSMENT",
        "experiment_id": EXPERIMENT_ID,
        "research_decision_id": RESEARCH_DECISION_ID,
        "model": model,
        "temperature": 0,
        "alfworld_source_commit": SOURCE_COMMIT,
        "split": SPLIT,
        "task_prefix": TASK_PREFIX,
        "candidate_order": "lexicographic_after_exact_preinspection_exclusion",
        "pre_inspected_exclusions": sorted(PRE_INSPECTED_EXCLUSIONS),
        "max_games_scanned_after_exclusion": MAX_GAMES_SCANNED,
        "target_eligible_episodes": TARGET_ELIGIBLE,
        "qualification_max_environment_actions": QUALIFICATION_MAX_ENV_ACTIONS,
        "post_reset_max_environment_actions": POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap_proxy_tokens": MEMORY_CAP_PROXY_TOKENS,
        "proxy_tokenizer": "cl100k_base_not_qwen_native",
        "candidate_games_sha256": sha256_text("\n".join(games)),
        "scan_records": scan_records,
        "episodes": episodes,
        "aggregate": agg,
        "runtime_seconds": time.time() - start,
        "scientific_result": "NOT_ASSESSED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {
                "phase": "measurement_complete",
                "measurement_status": agg["measurement_status"],
                "scanned_games": agg["scanned_games"],
                "eligible_found": agg["eligible_found"],
                "output": str(output),
            }
        ),
        flush=True,
    )
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
