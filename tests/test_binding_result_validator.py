from copy import deepcopy

import binding_result_validator as v


def episode(binding_iaa=False, noop_iaa=False, passive_iaa=False, flat_iaa=False, *, binding_success=True, noop_success=True):
    vals = {
        "binding_json": (binding_iaa, binding_success),
        "noop_json": (noop_iaa, noop_success),
        "passive_json": (passive_iaa, False),
        "flat_neutral": (flat_iaa, False),
    }
    arms = {}
    for name, (iaa, success) in vals.items():
        arms[name] = {"iaa": iaa, "gdaa": iaa, "success": success, "rpa": False}
    return {"all_guards_pass": True, "arms": arms}


def make_result(eps):
    n = len(eps)
    metrics = {name: v.arm_metrics(eps, name) for name in v.ARM_NAMES}
    paired = {
        "binding_vs_noop_iaa": v.paired_bool(eps, "binding_json", "noop_json", "iaa"),
        "binding_vs_passive_iaa": v.paired_bool(eps, "binding_json", "passive_json", "iaa"),
        "flat_vs_noop_iaa": v.paired_bool(eps, "flat_neutral", "noop_json", "iaa", two_sided=True),
        "binding_vs_noop_gdaa": v.paired_bool(eps, "binding_json", "noop_json", "gdaa"),
        "binding_vs_noop_success": v.paired_bool(eps, "binding_json", "noop_json", "success", two_sided=True),
    }
    complete = n == v.TARGET_ELIGIBLE
    guards = all(ep["all_guards_pass"] for ep in eps)
    conditions = None
    if complete and guards:
        b, no = metrics["binding_json"], metrics["noop_json"]
        conditions = {
            "binding_vs_noop_iaa_p_le_0_05": paired["binding_vs_noop_iaa"]["p"] <= 0.05,
            "binding_vs_passive_iaa_p_le_0_05": paired["binding_vs_passive_iaa"]["p"] <= 0.05,
            "binding_iaa_advantage_vs_noop_ge_0_25": b["iaa_rate"] - no["iaa_rate"] >= 0.25,
            "binding_success_not_worse_than_noop_by_gt_0_10": b["success_rate"] >= no["success_rate"] - 0.10,
        }
    return {
        "experiment_id": v.EXPERIMENT_ID, "hypothesis_id": v.HYPOTHESIS_ID,
        "model": v.MODEL, "temperature": 0, "split": "train",
        "candidate_salt": v.CANDIDATE_SALT, "candidate_pool_sha256": v.CANDIDATE_POOL_SHA256,
        "candidate_population_count": 790, "max_games_scanned": v.MAX_GAMES_SCANNED,
        "target_eligible_episodes": v.TARGET_ELIGIBLE,
        "qualification_max_environment_actions": v.QUALIFICATION_MAX_ENV_ACTIONS,
        "post_reset_max_environment_actions": v.POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap_proxy_tokens": v.MEMORY_CAP_PROXY_TOKENS,
        "binding_wrapper": v.BINDING_WRAPPER, "noop_wrapper": v.NOOP_WRAPPER,
        "scientific_result": "NOT_ASSESSED", "episodes": eps,
        "aggregate": {
            "scientific_result": "NOT_ASSESSED", "eligible_found": n,
            "target_eligible_episodes": v.TARGET_ELIGIBLE,
            "all_episode_guards_pass": guards, "metrics": metrics,
            "paired_tests": paired, "preregistered_condition_evaluations": conditions,
        },
    }


def strong_supported_eps():
    # 12 binding-only IAA wins; 4 ties at 0 => p=1/4096 vs both controls, +0.75 rate.
    return [episode(binding_iaa=True, binding_success=True, noop_success=True) for _ in range(12)] + [episode() for _ in range(4)]


def test_supported_requires_all_frozen_primary_and_utility_conditions():
    out = v.validate_result(make_result(strong_supported_eps()))
    assert out["preregistered_outcome"] == "SUPPORTED_WITHIN_DISCOVERY_SCOPE"
    assert out["primary_iaa_supported"] is True
    assert out["task_success_noninferiority_passed"] is True


def test_behaviorally_effective_but_utility_negative_is_separate():
    eps = [episode(binding_iaa=True, binding_success=False, noop_success=True) for _ in range(12)] + [episode(binding_success=False, noop_success=True) for _ in range(4)]
    out = v.validate_result(make_result(eps))
    assert out["primary_iaa_supported"] is True
    assert out["task_success_noninferiority_passed"] is False
    assert out["preregistered_outcome"] == "BEHAVIORALLY_EFFECTIVE_BUT_UTILITY_NEGATIVE"


def test_no_primary_iaa_advantage_weakens_binding_mechanism():
    eps = [episode(binding_iaa=True, noop_iaa=True, passive_iaa=True) for _ in range(16)]
    out = v.validate_result(make_result(eps))
    assert out["primary_iaa_supported"] is False
    assert out["preregistered_outcome"] == "WEAKEN_REJECT_CONTROL_CHANNEL_BINDING_INSUFFICIENCY"


def test_insufficient_cohort_is_inconclusive():
    out = v.validate_result(make_result(strong_supported_eps()[:15]))
    assert out["preregistered_outcome"] == "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"


def test_guard_failure_is_invalid_not_mechanistic_refutation():
    x = make_result(strong_supported_eps())
    x["episodes"][0]["all_guards_pass"] = False
    x["aggregate"]["all_episode_guards_pass"] = False
    out = v.validate_result(x)
    assert out["preregistered_outcome"] == "INVALID_GUARD_FAILURE"


def test_wrong_candidate_hash_fails_closed():
    x = make_result(strong_supported_eps())
    x["candidate_pool_sha256"] = "bad"
    assert v.validate_result(x)["preregistered_outcome"] == "INVALID_GUARD_FAILURE"


def test_aggregate_p_value_tampering_fails_closed():
    x = make_result(strong_supported_eps())
    x["aggregate"]["paired_tests"]["binding_vs_noop_iaa"]["p"] = 1.0
    out = v.validate_result(x)
    assert out["aggregate_consistent"] is False
    assert out["preregistered_outcome"] == "INVALID_GUARD_FAILURE"


def test_flat_neutral_cannot_rescue_primary_failure():
    eps = [episode(flat_iaa=True) for _ in range(16)]
    out = v.validate_result(make_result(eps))
    assert out["preregistered_outcome"] == "WEAKEN_REJECT_CONTROL_CHANNEL_BINDING_INSUFFICIENCY"


def test_frozen_local_source_hashes_pass():
    out = v.validate_result(make_result(strong_supported_eps()), workspace="/workspace/local-vlm/LLM/plancarry")
    assert out["sources_ok"] is True
    assert all(out["source_checks"].values())
