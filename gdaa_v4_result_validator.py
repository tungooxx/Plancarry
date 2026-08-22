"""Read-only final-result validator for frozen GDAA v4 Experiment a21eaaa3....

No model calls and no GDAA recomputation from hidden/reference information. The
validator re-expresses the prospectively frozen identity, aggregate-consistency,
true-technical validity, cohort-completeness and natural-divergence decision law.
Ordinary model-invalid turns are behavioral outcomes and are not validity failures.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPERIMENT_ID = "44f469b8-a9a7-4b07-b2dc-c204e8a2793b"
MANIFEST_SHA256 = "62d700e5d407e71ae1db030cb454e1b78a1c4bd505f24997024de4ecb71f008d"
BINDING_POOL_SHA256 = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
PRIOR_V3_MANIFEST_SHA256 = "5beaeb849cc6abbee4397c1f8d5021700e272b799e356a2d77d47f920af4d418"
GDAA_SCORER_SHA256 = "610d8337e37f7b8f0ac1f08fb83af312c4a743cbc7719a73ff4809b1f418f7ac"
RUNNER_SHA256 = "cda984594ca6df460ba2d51474f42761d5cdda121911a432c27083f5d93a2c66"
MODEL = "qwen2.5:7b-instruct"
TARGET_ELIGIBLE = 8
MAX_GAMES_SCANNED = 90
POST_RESET_MAX_ENV_ACTIONS = 8
MEMORY_CAP_PROXY_TOKENS = 48
ARMS = ("observation_only", "tail_truncation", "generic_summary", "plancarry")


class ResultContractError(ValueError):
    pass


def _bool(value: Any) -> bool:
    return value is True


def _event_count(arm_result: dict[str, Any], event_type: str) -> int:
    events = arm_result.get("invalid_turn_events", [])
    return sum(isinstance(e, dict) and e.get("type") == event_type for e in events)


def validate_result(result: dict[str, Any]) -> dict[str, Any]:
    agg = result.get("aggregate")
    episodes = result.get("episodes")
    if not isinstance(agg, dict) or not isinstance(episodes, list):
        raise ResultContractError("final artifact must contain aggregate object and episodes list")
    isolation = result.get("binding_isolation")
    if not isinstance(isolation, dict):
        isolation = {}

    identity_checks = {
        "experiment_id": result.get("experiment_id") == EXPERIMENT_ID,
        "candidate_manifest_sha256": result.get("candidate_manifest_sha256") == MANIFEST_SHA256,
        "binding_pool_sha256": isolation.get("binding_pool_sha256") == BINDING_POOL_SHA256,
        "binding_overlap_zero": isolation.get("cross_binding_overlap_count") == 0,
        "prior_v3_manifest_sha256": isolation.get("prior_v3_manifest_sha256") == PRIOR_V3_MANIFEST_SHA256,
        "prior_v3_overlap_zero": isolation.get("cross_v3_manifest_overlap_count") == 0,
        "binding_candidate_count": isolation.get("binding_candidate_count") == 180,
        "prior_v3_candidate_count": isolation.get("prior_v3_candidate_count") == 90,
        "fresh_source_pool_count": isolation.get("fresh_source_pool_count") == 520,
        "gdaa_candidate_count": isolation.get("gdaa_candidate_count") == 90,
        "model": result.get("model") == MODEL,
        "temperature_zero": result.get("temperature") == 0,
        "target_eligible": result.get("target_eligible_episodes") == TARGET_ELIGIBLE,
        "max_games_scanned": result.get("max_games_scanned") == MAX_GAMES_SCANNED,
        "post_reset_horizon": result.get("post_reset_max_environment_actions") == POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap": result.get("memory_cap_proxy_tokens") == MEMORY_CAP_PROXY_TOKENS,
        "valid_unseen_not_consumed": result.get("valid_unseen_consumed") is False,
        "gdaa_scorer_source_sha256": result.get("gdaa_scorer_source_sha256") == GDAA_SCORER_SHA256,
        "runner_source_sha256": result.get("runner_source_sha256") == RUNNER_SHA256,
        "runner_did_not_self_assess_science": result.get("scientific_result") == "NOT_ASSESSED",
        "aggregate_did_not_self_assess_science": agg.get("scientific_result") == "NOT_ASSESSED",
    }

    n = len(episodes)
    episode_guards = [ep.get("all_guards_pass") is True for ep in episodes if isinstance(ep, dict)]
    all_episode_guards = len(episode_guards) == n and all(episode_guards)
    all_gdaa_defined = all(
        isinstance(ep, dict)
        and isinstance(ep.get("arms"), dict)
        and all(
            arm in ep["arms"]
            and isinstance(ep["arms"][arm], dict)
            and ep["arms"][arm].get("gdaa") is not None
            for arm in ARMS
        )
        for ep in episodes
    )
    no_true_technical_failures = all(
        isinstance(ep, dict)
        and isinstance(ep.get("arms"), dict)
        and all(ep["arms"].get(arm, {}).get("technical_failure") is None for arm in ARMS)
        for ep in episodes
    )

    recomputed_metrics: dict[str, dict[str, int]] = {}
    natural_divergence = 0
    for arm in ARMS:
        successes = gdaa_count = rpa_count = undefined = divergence = 0
        invalid_turns = no_tool = invalid_index = cap_terminations = 0
        for ep in episodes:
            arm_result = ep["arms"][arm]
            success = _bool(arm_result.get("success"))
            gdaa = arm_result.get("gdaa")
            rpa = _bool(arm_result.get("reference_progress_agreement"))
            successes += int(success)
            gdaa_count += int(gdaa is True)
            undefined += int(gdaa is None)
            rpa_count += int(rpa)
            divergence += int(success and gdaa is True and not rpa)
            invalid_turns += int(arm_result.get("invalid_model_turns", 0))
            no_tool += _event_count(arm_result, "NO_TOOL_CALL")
            invalid_index += _event_count(arm_result, "INVALID_INDEX")
            cap_terminations += int(arm_result.get("termination_reason") == "MODEL_INVALID_TURN_CAP_REACHED")
        natural_divergence += divergence
        recomputed_metrics[arm] = {
            "n": n,
            "successes": successes,
            "gdaa_count": gdaa_count,
            "gdaa_undefined_count": undefined,
            "rpa_count": rpa_count,
            "successful_gdaa1_rpa0_count": divergence,
            "invalid_model_turns": invalid_turns,
            "invalid_no_tool_call_count": no_tool,
            "invalid_index_count": invalid_index,
            "model_invalid_turn_cap_terminations": cap_terminations,
        }

    aggregate_consistency_checks = {
        "evaluated_episodes": agg.get("evaluated_episodes") == n,
        "eligible_found": agg.get("eligible_found") == n,
        "target_eligible_episodes": agg.get("target_eligible_episodes") == TARGET_ELIGIBLE,
        "all_episode_guards_pass": agg.get("all_episode_guards_pass") is all_episode_guards,
        "all_gdaa_defined": agg.get("all_gdaa_defined") is all_gdaa_defined,
        "natural_divergence_count": agg.get("natural_successful_gdaa1_rpa0_count_all_arms") == natural_divergence,
    }
    agg_metrics = agg.get("metrics") if isinstance(agg.get("metrics"), dict) else {}
    for arm in ARMS:
        reported = agg_metrics.get(arm) if isinstance(agg_metrics.get(arm), dict) else {}
        for key, value in recomputed_metrics[arm].items():
            aggregate_consistency_checks[f"{arm}.{key}"] = reported.get(key) == value

    identity_ok = all(identity_checks.values())
    aggregate_consistent = all(aggregate_consistency_checks.values())
    guards_ok = all_episode_guards and all_gdaa_defined and no_true_technical_failures
    cohort_complete = n == TARGET_ELIGIBLE and agg.get("eligible_found") == TARGET_ELIGIBLE

    if not identity_ok or not aggregate_consistent or not guards_ok:
        preregistered_outcome = "FAIL"
        outcome_reason = "frozen identity, aggregate consistency, scorer definition, or true validity guard failed"
    elif not cohort_complete:
        preregistered_outcome = "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"
        outcome_reason = "fewer than 8 eligible episodes in the completed frozen scan"
    elif natural_divergence >= 1:
        preregistered_outcome = "PASS"
        outcome_reason = "at least one natural successful trajectory had GDAA=1 and exact RPA=0"
    else:
        preregistered_outcome = "INCONCLUSIVE_NO_NATURAL_ROUTE_DIVERGENCE"
        outcome_reason = "complete valid cohort but no natural successful GDAA=1/RPA=0 trajectory"

    return {
        "validator_for_experiment_id": EXPERIMENT_ID,
        "identity_checks": identity_checks,
        "aggregate_consistency_checks": aggregate_consistency_checks,
        "identity_ok": identity_ok,
        "aggregate_consistent": aggregate_consistent,
        "cohort_complete": cohort_complete,
        "all_episode_guards_pass": all_episode_guards,
        "all_gdaa_defined": all_gdaa_defined,
        "no_true_technical_failures": no_true_technical_failures,
        "natural_successful_gdaa1_rpa0_count_all_arms": natural_divergence,
        "recomputed_metrics": recomputed_metrics,
        "preregistered_outcome": preregistered_outcome,
        "outcome_reason": outcome_reason,
        "scientific_scope_note": (
            "PASS supports GDAA route-invariance/construct validity only within the frozen fresh train-development scope. "
            "It does not establish PlanCarry superiority or independent replication. Model-invalid turns are behavioral "
            "outcomes by preregistration; true execution/identity/scorer/leakage failures remain invalidating."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_json")
    args = parser.parse_args()
    result = json.loads(Path(args.result_json).read_text())
    print(json.dumps(validate_result(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
