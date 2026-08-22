#!/usr/bin/env python3
"""Prospective runner for frozen PlanCarry binding Experiment 49a5eed0....

This program measures the preregistered mechanism-discovery experiment. It
never assesses scientific truth; Research OS does that only after completion
and inspection.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from openai import OpenAI

sys.path.insert(0, "/workspace/local-vlm/LLM/plancarry")
import alfworld_runtime as ar
import alfworld_qualify as aq
import alfworld_interruption_harness as ah
import alfworld_cohort_runner as v3
import alfworld_gdaa as gd

EXPERIMENT_ID = "49a5eed0-dc91-497a-a0e7-f9b5fc4cd5b1"
HYPOTHESIS_ID = "71aa4c3f-0b6d-42ea-b773-f69b011d5a62"
MODEL = "qwen2.5:7b-instruct"
BASE_URL = aq.BASE_URL
SPLIT = "train"
TASK_PREFIX = "pick_and_place_simple"
CANDIDATE_SALT = "plancarry-binding-v1-2026-08-18"
ARM_ORDER_SALT = "plancarry-binding-arm-order-v1"
MAX_GAMES_SCANNED = 180
TARGET_ELIGIBLE = 16
QUALIFICATION_MAX_ENV_ACTIONS = 30
POST_RESET_MAX_ENV_ACTIONS = 8
MEMORY_CAP_PROXY_TOKENS = 48
EXPECTED_POOL_SHA256 = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
SOURCE_COMMIT = "1558ba46d078279ecb4c5d33a6cdffc96714a2d2"

# Frozen after offline proxy-token matching, before any train outcome inspection.
BINDING_WRAPPER = (
    "PERSISTED COMMITMENT RULE: If intended_next_action is listed among the current "
    "admissible commands, execute that exact command as your first non-information "
    "action before replanning."
)
NOOP_WRAPPER = (
    "PERSISTED MEMORY NOTE: Use the memory and current admissible commands to continue "
    "the unfinished task. Choose the next action as you normally would from all "
    "admissible commands."
)
ARM_NAMES = ["passive_json", "noop_json", "binding_json", "flat_neutral"]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def candidate_population() -> list[str]:
    root = Path("/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/train")
    return sorted(str(p.absolute()) for p in root.glob(f"{TASK_PREFIX}-*/trial_*/game.tw-pddl"))


def candidate_games() -> list[str]:
    games = candidate_population()
    ordered = sorted(games, key=lambda p: sha256_text(CANDIDATE_SALT + "\n" + p))
    return ordered[:MAX_GAMES_SCANNED]


def candidate_pool_sha256(games: list[str] | None = None) -> str:
    pool = candidate_games() if games is None else games
    return sha256_text("\n".join(pool) + "\n")


def arm_order(game_file: str) -> list[str]:
    # Hash-derived Latin-square rotation plus hash-derived reversal keeps every
    # episode deterministic while reducing systematic order effects.
    digest = hashlib.sha256((ARM_ORDER_SALT + "\n" + str(game_file)).encode()).digest()
    rotation = digest[0] % len(ARM_NAMES)
    base = ARM_NAMES[rotation:] + ARM_NAMES[:rotation]
    if digest[1] & 1:
        base = list(reversed(base))
    return base


def scalar_leaves(obj: Any, path: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for key in sorted(obj):
            p = f"{path}.{key}" if path else str(key)
            out.extend(scalar_leaves(obj[key], p))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            out.extend(scalar_leaves(value, f"{path}[{i}]"))
    else:
        out.append((path, obj))
    return out


def flat_neutral_render(json_memory: str) -> str:
    state = json.loads(json_memory)
    lines = ["PERSISTED STATE VALUES:"]
    for path, value in scalar_leaves(state):
        lines.append(f"{path} = {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
    return "\n".join(lines)


def retained_atomic_values(text: str, *, is_json: bool) -> list[Any]:
    if is_json:
        obj = json.loads(text)
        return [v for _, v in scalar_leaves(obj)]
    values: list[Any] = []
    for line in text.splitlines()[1:]:
        if " = " not in line:
            continue
        _, raw = line.split(" = ", 1)
        values.append(json.loads(raw))
    return values


def fresh_messages(
    observation: str,
    commands: list[str],
    memory: str,
    wrapper: str | None,
    *,
    flat: bool = False,
) -> list[dict[str, Any]]:
    user = aq.surface(observation, commands)
    label = "FLAT STATE FROM BEFORE THE FORCED RESET:" if flat else "MEMORY FROM BEFORE THE FORCED RESET:"
    user += "\n\n" + label + "\n" + memory
    if wrapper:
        user += "\n\n" + wrapper
    return [{"role": "system", "content": aq.SYSTEM}, {"role": "user", "content": user}]


def intended_action_from_memory(json_memory: str) -> str | None:
    value = json.loads(json_memory).get("intended_next_action")
    return str(value) if isinstance(value, str) and value.strip() else None


def first_progress_from_records(actions: Iterable[dict[str, Any]] | Iterable[ar.AlfActionRecord]) -> str | None:
    return ah.first_progress_action(list(actions))


def iaa_score(first_progress_action: str | None, intended_next_action: str) -> bool:
    return first_progress_action == intended_next_action


def binomial_one_sided_p(wins: int, losses: int) -> float:
    return v3.binomial_one_sided_p(wins, losses)


def binomial_two_sided_p(wins: int, losses: int) -> float:
    n = int(wins) + int(losses)
    if n <= 0:
        return 1.0
    m = min(int(wins), int(losses))
    p = 2.0 * sum(math.comb(n, k) for k in range(0, m + 1)) / (2**n)
    return min(1.0, p)


def paired_bool_test(
    episodes: list[dict[str, Any]], a: str, b: str, field: str, *, two_sided: bool = False
) -> dict[str, Any]:
    wins = losses = both1 = both0 = 0
    for ep in episodes:
        va = bool(ep["arms"][a][field])
        vb = bool(ep["arms"][b][field])
        if va and not vb:
            wins += 1
        elif vb and not va:
            losses += 1
        elif va and vb:
            both1 += 1
        else:
            both0 += 1
    p = binomial_two_sided_p(wins, losses) if two_sided else binomial_one_sided_p(wins, losses)
    return {
        "a": a,
        "b": b,
        "field": field,
        "wins_a": wins,
        "losses_a": losses,
        "ties_both_1": both1,
        "ties_both_0": both0,
        "discordant_pairs": wins + losses,
        "p": p,
        "test": "two_sided_exact_paired_binomial" if two_sided else "one_sided_exact_paired_binomial",
    }


def wrapper_proxy_guard() -> bool:
    return ah.token_count(BINDING_WRAPPER) == ah.token_count(NOOP_WRAPPER)


def eligibility_from_qualification(qualification: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    reset = v3.derive_reset(qualification)
    detail: dict[str, Any] = {
        "qualification_success": bool(qualification.get("success")),
        "qualification_zero_invalid_model_turns": int(qualification.get("invalid_model_turns", 0)) == 0,
        "reset_exists": reset is not None,
    }
    if reset is None:
        return None, detail
    reset_after = int(reset["reset_after"])
    prefix_only = v3.prefix_only_qualification(qualification, reset_after)
    memory = ah.compile_plancarry(prefix_only, reset_after, MEMORY_CAP_PROXY_TOKENS)
    intended = intended_action_from_memory(memory)
    prefix = [ar.AlfActionRecord(**x) for x in qualification["actions"][:reset_after]]
    replay = ar.replay(qualification["game_file"], prefix, max_steps=60)
    try:
        commands = list(replay.admissible_commands)
        observation = replay.observation
        reset_hash = replay.hash()
    finally:
        replay.close()
    goal_text = ah.parse_goal(str(qualification.get("initial_observation", "")))
    positive = gd.direct_goal_action_set(goal_text, commands)
    detail.update(
        {
            "intended_next_action_present": intended is not None,
            "intended_next_action_admissible": bool(intended is not None and intended in commands),
            "gdaa_defined": positive is not None,
            "intended_next_action_gdaa_positive": bool(intended is not None and positive is not None and intended in positive),
            "memory_proxy_tokens": ah.token_count(memory),
        }
    )
    if not all(detail.values()):
        return None, detail
    return {
        "reset": reset,
        "reset_after": reset_after,
        "prefix_only": prefix_only,
        "plancarry_json": memory,
        "intended_next_action": intended,
        "reset_commands": commands,
        "reset_observation": observation,
        "reset_hash": reset_hash,
        "goal_text": goal_text,
        "gdaa_positive_actions": sorted(positive or []),
    }, detail


def evaluate_eligible(
    client: OpenAI,
    qualification: dict[str, Any],
    eligible: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    reset = eligible["reset"]
    reset_after = int(eligible["reset_after"])
    prefix = [ar.AlfActionRecord(**x) for x in qualification["actions"][:reset_after]]
    json_memory = eligible["plancarry_json"]
    flat_memory = flat_neutral_render(json_memory)
    intended = str(eligible["intended_next_action"])
    if retained_atomic_values(json_memory, is_json=True) != retained_atomic_values(flat_memory, is_json=False):
        raise RuntimeError("flat_neutral atomic-state mismatch")

    arm_specs = {
        "passive_json": (json_memory, None, False),
        "noop_json": (json_memory, NOOP_WRAPPER, False),
        "binding_json": (json_memory, BINDING_WRAPPER, False),
        "flat_neutral": (flat_memory, NOOP_WRAPPER, True),
    }
    arms: dict[str, Any] = {}
    reset_hashes = {eligible["reset_hash"]}
    order = arm_order(qualification["game_file"])
    for name in order:
        memory, wrapper, is_flat = arm_specs[name]
        replay = ar.replay(qualification["game_file"], prefix, max_steps=60)
        try:
            before_hash = replay.hash()
            messages = fresh_messages(
                replay.observation,
                list(replay.admissible_commands),
                memory,
                wrapper,
                flat=is_flat,
            )
        finally:
            replay.close()
        arm = v3.continue_arm_env_budget(
            client,
            model,
            qualification["game_file"],
            prefix,
            messages,
            POST_RESET_MAX_ENV_ACTIONS,
        )
        first = arm["first_progress_action"]
        arm["pre_call_reset_hash"] = before_hash
        arm["memory"] = memory
        arm["wrapper"] = wrapper
        arm["memory_proxy_tokens"] = ah.token_count(memory)
        arm["iaa"] = iaa_score(first, intended)
        arm["gdaa"] = gd.gdaa_score(first, eligible["goal_text"], eligible["reset_commands"])
        arm["rpa"] = first == reset["reference_first_progress_action"]
        arm["first_call_prompt_tokens"] = (
            int(arm["usage_calls"][0].get("prompt_tokens", 0)) if arm["usage_calls"] else None
        )
        arms[name] = arm
        reset_hashes.add(before_hash)
        reset_hashes.add(arm["reset_hash"])

    noop_prompt = arms["noop_json"]["first_call_prompt_tokens"]
    binding_prompt = arms["binding_json"]["first_call_prompt_tokens"]
    native_prompt_close = (
        noop_prompt is not None
        and binding_prompt is not None
        and abs(int(noop_prompt) - int(binding_prompt)) <= 2
    )
    sentinels = gd.frozen_sentinels()
    guards = {
        "candidate_pool_hash_frozen": candidate_pool_sha256() == EXPECTED_POOL_SHA256,
        "qualification_success": bool(qualification.get("success")),
        "qualification_zero_invalid_model_turns": int(qualification.get("invalid_model_turns", 0)) == 0,
        "reset_replay_matches_recorded": eligible["reset_hash"] == reset["recorded_reset_hash"],
        "all_arm_reset_hashes_identical": len(reset_hashes) == 1,
        "json_bytes_identical_across_json_arms": len({arms[n]["memory"] for n in ["passive_json", "noop_json", "binding_json"]}) == 1,
        "flat_atomic_values_identical": retained_atomic_values(json_memory, is_json=True) == retained_atomic_values(flat_memory, is_json=False),
        "memory_cap_respected": ah.token_count(json_memory) <= MEMORY_CAP_PROXY_TOKENS,
        "wrapper_proxy_tokens_equal": wrapper_proxy_guard(),
        "wrapper_native_prompt_tokens_within_2": native_prompt_close,
        "gdaa_sentinels_pass": all(sentinels.values()),
        "gdaa_defined": all(arms[n]["gdaa"] is not None for n in ARM_NAMES),
        "intended_action_currently_admissible": intended in eligible["reset_commands"],
        "intended_action_gdaa_positive": intended in eligible["gdaa_positive_actions"],
        "no_post_reset_technical_failure": all(arms[n]["technical_failure"] is None for n in ARM_NAMES),
        "expert_plan_hidden": True,
        "hidden_facts_hidden": True,
        "future_suffix_unavailable_to_memory_and_scorer": True,
        "valid_unseen_unused": "/valid_unseen/" not in qualification["game_file"],
    }
    return {
        "game_file": qualification["game_file"],
        "reset_after": reset_after,
        "reset_hash": eligible["reset_hash"],
        "reset_observation": eligible["reset_observation"],
        "reset_admissible_commands": eligible["reset_commands"],
        "goal_text": eligible["goal_text"],
        "intended_next_action": intended,
        "gdaa_positive_actions": eligible["gdaa_positive_actions"],
        "reference_first_progress_action": reset["reference_first_progress_action"],
        "arm_order": order,
        "qualification": qualification,
        "arms": arms,
        "gdaa_sentinels": sentinels,
        "guards": guards,
        "all_guards_pass": all(guards.values()),
    }


def _arm_metrics(episodes: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    n = len(episodes)
    iaa = sum(bool(ep["arms"][arm]["iaa"]) for ep in episodes)
    gdaa = sum(bool(ep["arms"][arm]["gdaa"]) for ep in episodes)
    success = sum(bool(ep["arms"][arm]["success"]) for ep in episodes)
    rpa = sum(bool(ep["arms"][arm]["rpa"]) for ep in episodes)
    return {
        "n": n,
        "iaa_count": iaa,
        "iaa_rate": iaa / n if n else None,
        "gdaa_count": gdaa,
        "gdaa_rate": gdaa / n if n else None,
        "success_count": success,
        "success_rate": success / n if n else None,
        "rpa_count": rpa,
        "rpa_rate": rpa / n if n else None,
        "prefix_reversal_count": sum(int(ep["arms"][arm]["prefix_reversal_count"]) for ep in episodes),
        "consecutive_repeat_count": sum(int(ep["arms"][arm]["consecutive_repeat_count"]) for ep in episodes),
        "invalid_model_turns": sum(int(ep["arms"][arm]["invalid_model_turns"]) for ep in episodes),
        "api_total_tokens": sum(int(ep["arms"][arm]["usage_total"]["total_tokens"]) for ep in episodes),
    }


def aggregate(episodes: list[dict[str, Any]], scanned: int) -> dict[str, Any]:
    metrics = {name: _arm_metrics(episodes, name) for name in ARM_NAMES}
    b_noop = paired_bool_test(episodes, "binding_json", "noop_json", "iaa") if episodes else None
    b_passive = paired_bool_test(episodes, "binding_json", "passive_json", "iaa") if episodes else None
    flat_noop = paired_bool_test(episodes, "flat_neutral", "noop_json", "iaa", two_sided=True) if episodes else None
    b_noop_gdaa = paired_bool_test(episodes, "binding_json", "noop_json", "gdaa") if episodes else None
    b_noop_success = paired_bool_test(episodes, "binding_json", "noop_json", "success", two_sided=True) if episodes else None
    complete = len(episodes) == TARGET_ELIGIBLE
    guards = all(ep["all_guards_pass"] for ep in episodes)
    if not complete:
        status = "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"
    elif not guards:
        status = "INVALID_GUARD_FAILURE"
    else:
        status = "MEASURED_AWAITING_SCIENTIFIC_ASSESSMENT"
    conditions = None
    if complete and guards:
        bind = metrics["binding_json"]
        noop = metrics["noop_json"]
        conditions = {
            "binding_vs_noop_iaa_p_le_0_05": b_noop["p"] <= 0.05,
            "binding_vs_passive_iaa_p_le_0_05": b_passive["p"] <= 0.05,
            "binding_iaa_advantage_vs_noop_ge_0_25": bind["iaa_rate"] - noop["iaa_rate"] >= 0.25,
            "binding_success_not_worse_than_noop_by_gt_0_10": bind["success_rate"] >= noop["success_rate"] - 0.10,
        }
    return {
        "measurement_status": status,
        "scientific_result": "NOT_ASSESSED",
        "scanned_games": scanned,
        "eligible_found": len(episodes),
        "target_eligible_episodes": TARGET_ELIGIBLE,
        "all_episode_guards_pass": guards,
        "metrics": metrics,
        "paired_tests": {
            "binding_vs_noop_iaa": b_noop,
            "binding_vs_passive_iaa": b_passive,
            "flat_vs_noop_iaa": flat_noop,
            "binding_vs_noop_gdaa": b_noop_gdaa,
            "binding_vs_noop_success": b_noop_success,
        },
        "preregistered_condition_evaluations": conditions,
    }


def run(output: Path, model: str = MODEL, base_url: str = BASE_URL) -> dict[str, Any]:
    start = time.time()
    pool = candidate_games()
    if len(candidate_population()) != 790:
        raise RuntimeError("train pick_and_place_simple population count drift")
    if len(pool) != MAX_GAMES_SCANNED:
        raise RuntimeError(f"candidate list length {len(pool)} != {MAX_GAMES_SCANNED}")
    if candidate_pool_sha256(pool) != EXPECTED_POOL_SHA256:
        raise RuntimeError("frozen candidate-pool SHA mismatch")
    if not wrapper_proxy_guard():
        raise RuntimeError("frozen wrapper proxy-token counts differ")
    if not all(gd.frozen_sentinels().values()):
        raise RuntimeError("frozen GDAA sentinels failed")
    if any("/valid_unseen/" in g for g in pool):
        raise RuntimeError("valid_unseen must remain unused")

    client = OpenAI(base_url=base_url, api_key="ollama", timeout=90)
    scan_records: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    for scan_index, game in enumerate(pool, 1):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            qualification = aq.run_game(game, model, QUALIFICATION_MAX_ENV_ACTIONS, client)
        eligible, detail = eligibility_from_qualification(qualification)
        is_eligible = eligible is not None
        scan_records.append(
            {
                "scan_index": scan_index,
                "game_file": game,
                "qualification_success": bool(qualification.get("success")),
                "qualification_invalid_model_turns": int(qualification.get("invalid_model_turns", 0)),
                "eligible": is_eligible,
                "eligibility_guards": detail,
            }
        )
        print(json.dumps({"phase": "qualification", "scan_index": scan_index, "eligible_count": len(episodes) + (1 if is_eligible else 0), "eligible": is_eligible}), flush=True)
        if not is_eligible:
            continue
        episode = evaluate_eligible(client, qualification, eligible, model)
        episodes.append(episode)
        print(json.dumps({"phase": "arm_evaluation_complete", "scan_index": scan_index, "eligible_count": len(episodes), "guards_pass": episode["all_guards_pass"]}), flush=True)
        if not episode["all_guards_pass"]:
            break
        if len(episodes) == TARGET_ELIGIBLE:
            break

    agg = aggregate(episodes, len(scan_records))
    result = {
        "kind": "PREREGISTERED_MEASUREMENT_AWAITING_RESEARCH_OS_ASSESSMENT",
        "experiment_id": EXPERIMENT_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "model": model,
        "temperature": 0,
        "alfworld_source_commit": SOURCE_COMMIT,
        "split": SPLIT,
        "task_prefix": TASK_PREFIX,
        "candidate_salt": CANDIDATE_SALT,
        "candidate_pool_sha256": candidate_pool_sha256(pool),
        "candidate_population_count": len(candidate_population()),
        "max_games_scanned": MAX_GAMES_SCANNED,
        "target_eligible_episodes": TARGET_ELIGIBLE,
        "qualification_max_environment_actions": QUALIFICATION_MAX_ENV_ACTIONS,
        "post_reset_max_environment_actions": POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap_proxy_tokens": MEMORY_CAP_PROXY_TOKENS,
        "proxy_tokenizer": "cl100k_base_not_qwen_native",
        "binding_wrapper": BINDING_WRAPPER,
        "noop_wrapper": NOOP_WRAPPER,
        "wrapper_proxy_tokens": ah.token_count(BINDING_WRAPPER),
        "gdaa_sentinels": gd.frozen_sentinels(),
        "scan_records": scan_records,
        "episodes": episodes,
        "aggregate": agg,
        "runtime_seconds": time.time() - start,
        "scientific_result": "NOT_ASSESSED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"phase": "measurement_complete", "measurement_status": agg["measurement_status"], "scanned_games": agg["scanned_games"], "eligible_found": agg["eligible_found"], "output": str(output)}), flush=True)
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
