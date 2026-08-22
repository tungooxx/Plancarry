"""Read-only validator for the frozen disjoint GDAA v3 result artifact.

This module contains no model calls and does not recompute GDAA from trajectories.
It checks the frozen execution/result contract and maps a *completed final artifact*
to the outcome categories preregistered for Experiment
bd09ff0f-5cc6-4846-a486-65e9c858200e.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPERIMENT_ID = "bd09ff0f-5cc6-4846-a486-65e9c858200e"
MANIFEST_SHA256 = "5beaeb849cc6abbee4397c1f8d5021700e272b799e356a2d77d47f920af4d418"
BINDING_POOL_SHA256 = "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
GDAA_SCORER_SHA256 = "610d8337e37f7b8f0ac1f08fb83af312c4a743cbc7719a73ff4809b1f418f7ac"
RUNNER_SHA256 = "43c292d5c6a0f6ebd1ed281215a2199869cacce3a1a56d8e29797d9f63b75640"
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


def validate_result(result: dict[str, Any]) -> dict[str, Any]:
    """Validate a final result and apply only the frozen preregistered outcome rule."""
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
        "binding_overlap_zero": isolation.get("cross_manifest_overlap_count") == 0,
        "binding_candidate_count": isolation.get("binding_candidate_count") == 180,
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

    recomputed_metrics: dict[str, dict[str, int]] = {}
    natural_divergence = 0
    for arm in ARMS:
        successes = gdaa_count = rpa_count = undefined = divergence = 0
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
        natural_divergence += divergence
        recomputed_metrics[arm] = {
            "n": n,
            "successes": successes,
            "gdaa_count": gdaa_count,
            "gdaa_undefined_count": undefined,
            "rpa_count": rpa_count,
            "successful_gdaa1_rpa0_count": divergence,
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
    guards_ok = all_episode_guards and all_gdaa_defined
    cohort_complete = n == TARGET_ELIGIBLE and agg.get("eligible_found") == TARGET_ELIGIBLE

    # Frozen decision law. Identity/guard violations are FAIL under the metric
    # construct preregistration but are *not* a scientific refutation of PlanCarry.
    if not identity_ok or not aggregate_consistent or not guards_ok:
        preregistered_outcome = "FAIL"
        outcome_reason = "frozen identity, result-consistency, or validity guard failed"
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
        "natural_successful_gdaa1_rpa0_count_all_arms": natural_divergence,
        "recomputed_metrics": recomputed_metrics,
        "preregistered_outcome": preregistered_outcome,
        "outcome_reason": outcome_reason,
        "scientific_scope_note": (
            "PASS supports GDAA route-invariance/construct validity only within the frozen train-development scope. "
            "It does not establish PlanCarry superiority or independent replication. FAIL from an execution/identity "
            "guard is an invalid/failed metric-construct run, not evidence that PlanCarry is scientifically false."
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
