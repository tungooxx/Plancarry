from copy import deepcopy

import gdaa_result_validator as v


def arm(success=False, gdaa=False, rpa=False):
    return {
        "success": success,
        "gdaa": gdaa,
        "reference_progress_agreement": rpa,
    }


def episode(divergent_arm=None):
    arms = {name: arm() for name in v.ARMS}
    if divergent_arm:
        arms[divergent_arm] = arm(success=True, gdaa=True, rpa=False)
    return {"all_guards_pass": True, "arms": arms}


def result(episodes):
    n = len(episodes)
    metrics = {}
    natural = 0
    for name in v.ARMS:
        succ = sum(ep["arms"][name]["success"] is True for ep in episodes)
        gdaa = sum(ep["arms"][name]["gdaa"] is True for ep in episodes)
        undef = sum(ep["arms"][name]["gdaa"] is None for ep in episodes)
        rpa = sum(ep["arms"][name]["reference_progress_agreement"] is True for ep in episodes)
        div = sum(
            ep["arms"][name]["success"] is True
            and ep["arms"][name]["gdaa"] is True
            and ep["arms"][name]["reference_progress_agreement"] is not True
            for ep in episodes
        )
        natural += div
        metrics[name] = {
            "n": n, "successes": succ, "gdaa_count": gdaa,
            "gdaa_undefined_count": undef, "rpa_count": rpa,
            "successful_gdaa1_rpa0_count": div,
        }
    return {
        "experiment_id": v.EXPERIMENT_ID,
        "candidate_manifest_sha256": v.MANIFEST_SHA256,
        "binding_isolation": {
            "binding_pool_sha256": v.BINDING_POOL_SHA256,
            "cross_manifest_overlap_count": 0,
            "binding_candidate_count": 180,
            "gdaa_candidate_count": 90,
        },
        "model": v.MODEL, "temperature": 0,
        "target_eligible_episodes": v.TARGET_ELIGIBLE,
        "max_games_scanned": v.MAX_GAMES_SCANNED,
        "post_reset_max_environment_actions": v.POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap_proxy_tokens": v.MEMORY_CAP_PROXY_TOKENS,
        "valid_unseen_consumed": False,
        "gdaa_scorer_source_sha256": v.GDAA_SCORER_SHA256,
        "runner_source_sha256": v.RUNNER_SHA256,
        "scientific_result": "NOT_ASSESSED",
        "episodes": episodes,
        "aggregate": {
            "scientific_result": "NOT_ASSESSED",
            "evaluated_episodes": n, "eligible_found": n,
            "target_eligible_episodes": v.TARGET_ELIGIBLE,
            "all_episode_guards_pass": all(ep["all_guards_pass"] for ep in episodes),
            "all_gdaa_defined": all(
                ep["arms"][name]["gdaa"] is not None for ep in episodes for name in v.ARMS
            ),
            "natural_successful_gdaa1_rpa0_count_all_arms": natural,
            "metrics": metrics,
        },
    }


def test_pass_requires_natural_successful_route_divergence():
    eps = [episode("plancarry")] + [episode() for _ in range(7)]
    out = v.validate_result(result(eps))
    assert out["preregistered_outcome"] == "PASS"
    assert out["natural_successful_gdaa1_rpa0_count_all_arms"] == 1


def test_complete_no_divergence_is_inconclusive_not_fail():
    out = v.validate_result(result([episode() for _ in range(8)]))
    assert out["preregistered_outcome"] == "INCONCLUSIVE_NO_NATURAL_ROUTE_DIVERGENCE"


def test_insufficient_eligible_is_inconclusive():
    out = v.validate_result(result([episode() for _ in range(7)]))
    assert out["preregistered_outcome"] == "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"


def test_binding_overlap_is_fail_guard():
    x = result([episode("observation_only")] + [episode() for _ in range(7)])
    x["binding_isolation"]["cross_manifest_overlap_count"] = 1
    out = v.validate_result(x)
    assert out["preregistered_outcome"] == "FAIL"
    assert not out["identity_ok"]


def test_undefined_gdaa_is_fail_guard_even_if_successful():
    x = result([episode("plancarry")] + [episode() for _ in range(7)])
    x["episodes"][0]["arms"]["generic_summary"]["gdaa"] = None
    # update reported aggregate so only the actual frozen GDAA-defined guard fails
    x["aggregate"]["all_gdaa_defined"] = False
    x["aggregate"]["metrics"]["generic_summary"]["gdaa_undefined_count"] = 1
    out = v.validate_result(x)
    assert out["preregistered_outcome"] == "FAIL"
    assert out["aggregate_consistent"]
    assert not out["all_gdaa_defined"]


def test_aggregate_tampering_fails_closed():
    x = result([episode("plancarry")] + [episode() for _ in range(7)])
    x["aggregate"]["metrics"]["plancarry"]["successes"] = 8
    out = v.validate_result(x)
    assert out["preregistered_outcome"] == "FAIL"
    assert not out["aggregate_consistent"]


def test_wrong_frozen_source_hash_fails_closed():
    x = result([episode("plancarry")] + [episode() for _ in range(7)])
    x["gdaa_scorer_source_sha256"] = "bad"
    out = v.validate_result(x)
    assert out["preregistered_outcome"] == "FAIL"
    assert not out["identity_checks"]["gdaa_scorer_source_sha256"]


def test_validator_never_changes_terminal_success_into_gdaa():
    eps = [episode() for _ in range(8)]
    eps[0]["arms"]["plancarry"] = arm(success=True, gdaa=False, rpa=False)
    out = v.validate_result(result(eps))
    assert out["recomputed_metrics"]["plancarry"]["successes"] == 1
    assert out["recomputed_metrics"]["plancarry"]["gdaa_count"] == 0
    assert out["recomputed_metrics"]["plancarry"]["successful_gdaa1_rpa0_count"] == 0
    assert out["preregistered_outcome"] == "INCONCLUSIVE_NO_NATURAL_ROUTE_DIVERGENCE"
