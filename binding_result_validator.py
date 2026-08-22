"""Read-only final-artifact validator for the frozen PlanCarry binding study.

No model calls. No partial-result support. This only replays the preregistered
Experiment 49a5eed0-dc91-497a-a0e7-f9b5fc4cd5b1 decision law from a completed
JSON artifact and checks that aggregate statistics agree with episode records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

EXPERIMENT_ID = "49a5eed0-dc91-497a-a0e7-f9b5fc4cd5b1"
HYPOTHESIS_ID = "71aa4c3f-0b6d-42ea-b773-f69b011d5a62"
MODEL = "qwen2.5:7b-instruct"
CANDIDATE_SALT = "plancarry-binding-v1-2026-08-18"
CANDIDATE_POOL_SHA256 = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
TARGET_ELIGIBLE = 16
MAX_GAMES_SCANNED = 180
QUALIFICATION_MAX_ENV_ACTIONS = 30
POST_RESET_MAX_ENV_ACTIONS = 8
MEMORY_CAP_PROXY_TOKENS = 48
RUNNER_SOURCE_SHA256 = "01a253d06d215d02e41a228e42a744d5d284aded044f97f7d144c91d71f864e8"
GDAA_SOURCE_SHA256 = "a51db409173bb0cfc9211d4122601aa9b8a0580edf2c6e9143b2fbe7271e8d1f"
ARM_NAMES = ("passive_json", "noop_json", "binding_json", "flat_neutral")
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


class ResultContractError(ValueError):
    pass


def one_sided_exact_p(wins: int, losses: int) -> float:
    n = wins + losses
    if n <= 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / (2**n)


def two_sided_exact_p(wins: int, losses: int) -> float:
    n = wins + losses
    if n <= 0:
        return 1.0
    m = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, k) for k in range(0, m + 1)) / (2**n))


def paired_bool(episodes: list[dict[str, Any]], a: str, b: str, field: str, *, two_sided=False) -> dict[str, Any]:
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
    p = two_sided_exact_p(wins, losses) if two_sided else one_sided_exact_p(wins, losses)
    return {
        "a": a, "b": b, "field": field,
        "wins_a": wins, "losses_a": losses,
        "ties_both_1": both1, "ties_both_0": both0,
        "discordant_pairs": wins + losses, "p": p,
        "test": "two_sided_exact_paired_binomial" if two_sided else "one_sided_exact_paired_binomial",
    }


def arm_metrics(episodes: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    n = len(episodes)
    iaa = sum(bool(ep["arms"][arm]["iaa"]) for ep in episodes)
    gdaa = sum(bool(ep["arms"][arm]["gdaa"]) for ep in episodes)
    success = sum(bool(ep["arms"][arm]["success"]) for ep in episodes)
    rpa = sum(bool(ep["arms"][arm]["rpa"]) for ep in episodes)
    return {
        "n": n,
        "iaa_count": iaa, "iaa_rate": iaa / n if n else None,
        "gdaa_count": gdaa, "gdaa_rate": gdaa / n if n else None,
        "success_count": success, "success_rate": success / n if n else None,
        "rpa_count": rpa, "rpa_rate": rpa / n if n else None,
    }


def _same_number(a: Any, b: Any, tol: float = 1e-12) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    return a == b


def validate_result(result: dict[str, Any], *, workspace: str | None = None) -> dict[str, Any]:
    agg = result.get("aggregate")
    episodes = result.get("episodes")
    if not isinstance(agg, dict) or not isinstance(episodes, list):
        raise ResultContractError("final artifact must contain aggregate object and episodes list")

    identity_checks = {
        "experiment_id": result.get("experiment_id") == EXPERIMENT_ID,
        "hypothesis_id": result.get("hypothesis_id") == HYPOTHESIS_ID,
        "model": result.get("model") == MODEL,
        "temperature_zero": result.get("temperature") == 0,
        "split_train": result.get("split") == "train",
        "candidate_salt": result.get("candidate_salt") == CANDIDATE_SALT,
        "candidate_pool_sha256": result.get("candidate_pool_sha256") == CANDIDATE_POOL_SHA256,
        "candidate_population_count": result.get("candidate_population_count") == 790,
        "max_games_scanned": result.get("max_games_scanned") == MAX_GAMES_SCANNED,
        "target_eligible_episodes": result.get("target_eligible_episodes") == TARGET_ELIGIBLE,
        "qualification_horizon": result.get("qualification_max_environment_actions") == QUALIFICATION_MAX_ENV_ACTIONS,
        "post_reset_horizon": result.get("post_reset_max_environment_actions") == POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap": result.get("memory_cap_proxy_tokens") == MEMORY_CAP_PROXY_TOKENS,
        "binding_wrapper": result.get("binding_wrapper") == BINDING_WRAPPER,
        "noop_wrapper": result.get("noop_wrapper") == NOOP_WRAPPER,
        "runner_did_not_self_assess_science": result.get("scientific_result") == "NOT_ASSESSED",
        "aggregate_did_not_self_assess_science": agg.get("scientific_result") == "NOT_ASSESSED",
    }

    source_checks: dict[str, bool | None] = {
        "runner_source_sha256": None,
        "gdaa_source_sha256": None,
    }
    if workspace is not None:
        root = Path(workspace)
        runner = root / "alfworld_binding_runner.py"
        gdaa = root / "alfworld_gdaa.py"
        source_checks = {
            "runner_source_sha256": runner.is_file() and hashlib.sha256(runner.read_bytes()).hexdigest() == RUNNER_SOURCE_SHA256,
            "gdaa_source_sha256": gdaa.is_file() and hashlib.sha256(gdaa.read_bytes()).hexdigest() == GDAA_SOURCE_SHA256,
        }

    n = len(episodes)
    episode_structure_ok = all(
        isinstance(ep, dict)
        and isinstance(ep.get("arms"), dict)
        and all(name in ep["arms"] and isinstance(ep["arms"][name], dict) for name in ARM_NAMES)
        for ep in episodes
    )
    if not episode_structure_ok and n:
        raise ResultContractError("episode arm structure is malformed")

    all_guards = all(ep.get("all_guards_pass") is True for ep in episodes)
    metrics = {name: arm_metrics(episodes, name) for name in ARM_NAMES}
    paired = {
        "binding_vs_noop_iaa": paired_bool(episodes, "binding_json", "noop_json", "iaa"),
        "binding_vs_passive_iaa": paired_bool(episodes, "binding_json", "passive_json", "iaa"),
        "flat_vs_noop_iaa": paired_bool(episodes, "flat_neutral", "noop_json", "iaa", two_sided=True),
        "binding_vs_noop_gdaa": paired_bool(episodes, "binding_json", "noop_json", "gdaa"),
        "binding_vs_noop_success": paired_bool(episodes, "binding_json", "noop_json", "success", two_sided=True),
    }

    consistency: dict[str, bool] = {
        "eligible_found": agg.get("eligible_found") == n,
        "target_eligible_episodes": agg.get("target_eligible_episodes") == TARGET_ELIGIBLE,
        "all_episode_guards_pass": agg.get("all_episode_guards_pass") is all_guards,
    }
    reported_metrics = agg.get("metrics") if isinstance(agg.get("metrics"), dict) else {}
    for name in ARM_NAMES:
        rep = reported_metrics.get(name) if isinstance(reported_metrics.get(name), dict) else {}
        for key, val in metrics[name].items():
            consistency[f"metrics.{name}.{key}"] = _same_number(rep.get(key), val)
    reported_tests = agg.get("paired_tests") if isinstance(agg.get("paired_tests"), dict) else {}
    for test_name, calc in paired.items():
        rep = reported_tests.get(test_name) if isinstance(reported_tests.get(test_name), dict) else {}
        for key, val in calc.items():
            consistency[f"paired.{test_name}.{key}"] = _same_number(rep.get(key), val)

    complete = n == TARGET_ELIGIBLE
    binding = metrics["binding_json"]
    noop = metrics["noop_json"]
    conditions = {
        "binding_vs_noop_iaa_p_le_0_05": paired["binding_vs_noop_iaa"]["p"] <= 0.05,
        "binding_vs_passive_iaa_p_le_0_05": paired["binding_vs_passive_iaa"]["p"] <= 0.05,
        "binding_iaa_advantage_vs_noop_ge_0_25": (
            complete and binding["iaa_rate"] is not None and noop["iaa_rate"] is not None
            and binding["iaa_rate"] - noop["iaa_rate"] >= 0.25
        ),
        "binding_success_not_worse_than_noop_by_gt_0_10": (
            complete and binding["success_rate"] is not None and noop["success_rate"] is not None
            and binding["success_rate"] >= noop["success_rate"] - 0.10
        ),
    }
    reported_conditions = agg.get("preregistered_condition_evaluations")
    if complete and all_guards:
        consistency["preregistered_condition_evaluations_present"] = isinstance(reported_conditions, dict)
        if isinstance(reported_conditions, dict):
            for key, val in conditions.items():
                consistency[f"condition.{key}"] = reported_conditions.get(key) is val
    else:
        consistency["preregistered_condition_evaluations_absent"] = reported_conditions is None

    identity_ok = all(identity_checks.values())
    sources_ok = all(v is True for v in source_checks.values()) if workspace is not None else None
    aggregate_consistent = all(consistency.values())
    primary_iaa_supported = all(
        conditions[k] for k in (
            "binding_vs_noop_iaa_p_le_0_05",
            "binding_vs_passive_iaa_p_le_0_05",
            "binding_iaa_advantage_vs_noop_ge_0_25",
        )
    )
    utility_ok = conditions["binding_success_not_worse_than_noop_by_gt_0_10"]

    if not identity_ok or not aggregate_consistent or not all_guards or (sources_ok is False):
        outcome = "INVALID_GUARD_FAILURE"
        reason = "frozen identity/source/result-consistency or episode validity guard failed"
    elif not complete:
        outcome = "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"
        reason = "fewer than 16 eligible episodes in the completed frozen scan"
    elif primary_iaa_supported and utility_ok:
        outcome = "SUPPORTED_WITHIN_DISCOVERY_SCOPE"
        reason = "both prespecified IAA tests, >=0.25 IAA advantage, and TaskSuccess noninferiority all passed"
    elif primary_iaa_supported and not utility_ok:
        outcome = "BEHAVIORALLY_EFFECTIVE_BUT_UTILITY_NEGATIVE"
        reason = "binding met all primary IAA mechanism criteria but TaskSuccess fell >0.10 below noop"
    else:
        outcome = "WEAKEN_REJECT_CONTROL_CHANNEL_BINDING_INSUFFICIENCY"
        reason = "complete valid cohort did not satisfy all prespecified primary IAA advantage criteria"

    return {
        "validator_for_experiment_id": EXPERIMENT_ID,
        "identity_checks": identity_checks,
        "source_checks": source_checks,
        "identity_ok": identity_ok,
        "sources_ok": sources_ok,
        "aggregate_consistency_checks": consistency,
        "aggregate_consistent": aggregate_consistent,
        "cohort_complete": complete,
        "all_episode_guards_pass": all_guards,
        "recomputed_metrics": metrics,
        "recomputed_paired_tests": paired,
        "preregistered_condition_evaluations": conditions,
        "primary_iaa_supported": primary_iaa_supported,
        "task_success_noninferiority_passed": utility_ok,
        "preregistered_outcome": outcome,
        "outcome_reason": reason,
        "flat_neutral_note": "flat_neutral is diagnostic only and cannot rescue primary binding failure.",
        "scope_note": (
            "SUPPORTED applies only to the frozen train-split mechanism-discovery scope and does not establish generic "
            "PlanCarry superiority or independent replication. INVALID is technical/validity failure, not scientific refutation."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result_json")
    ap.add_argument("--workspace", default=None)
    args = ap.parse_args()
    result = json.loads(Path(args.result_json).read_text())
    print(json.dumps(validate_result(result, workspace=args.workspace), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
