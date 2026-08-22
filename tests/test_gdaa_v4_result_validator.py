from copy import deepcopy
import gdaa_v4_result_validator as v


def arm(success=False, gdaa=False, rpa=False, invalid=0, events=None, termination="environment_action_budget_exhausted", technical=None):
    return {
        "success": success,
        "gdaa": gdaa,
        "reference_progress_agreement": rpa,
        "invalid_model_turns": invalid,
        "invalid_turn_events": list(events or []),
        "termination_reason": termination,
        "technical_failure": technical,
    }


def episode(divergent_arm=None):
    arms = {name: arm() for name in v.ARMS}
    if divergent_arm:
        arms[divergent_arm] = arm(success=True, gdaa=True, rpa=False)
    return {"all_guards_pass": True, "arms": arms}


def result(episodes):
    n=len(episodes); metrics={}; natural=0
    for name in v.ARMS:
        succ=sum(ep["arms"][name]["success"] is True for ep in episodes)
        gd=sum(ep["arms"][name]["gdaa"] is True for ep in episodes)
        und=sum(ep["arms"][name]["gdaa"] is None for ep in episodes)
        rp=sum(ep["arms"][name]["reference_progress_agreement"] is True for ep in episodes)
        div=sum(ep["arms"][name]["success"] is True and ep["arms"][name]["gdaa"] is True and ep["arms"][name]["reference_progress_agreement"] is not True for ep in episodes)
        inv=sum(int(ep["arms"][name].get("invalid_model_turns",0)) for ep in episodes)
        nt=sum(sum(e.get("type")=="NO_TOOL_CALL" for e in ep["arms"][name].get("invalid_turn_events",[])) for ep in episodes)
        ii=sum(sum(e.get("type")=="INVALID_INDEX" for e in ep["arms"][name].get("invalid_turn_events",[])) for ep in episodes)
        cap=sum(ep["arms"][name].get("termination_reason")=="MODEL_INVALID_TURN_CAP_REACHED" for ep in episodes)
        natural+=div
        metrics[name]={"n":n,"successes":succ,"gdaa_count":gd,"gdaa_undefined_count":und,"rpa_count":rp,"successful_gdaa1_rpa0_count":div,"invalid_model_turns":inv,"invalid_no_tool_call_count":nt,"invalid_index_count":ii,"model_invalid_turn_cap_terminations":cap}
    all_guards=all(ep["all_guards_pass"] for ep in episodes)
    return {
        "experiment_id":v.EXPERIMENT_ID,
        "candidate_manifest_sha256":v.MANIFEST_SHA256,
        "binding_isolation":{
            "binding_pool_sha256":v.BINDING_POOL_SHA256,
            "cross_binding_overlap_count":0,
            "prior_v3_manifest_sha256":v.PRIOR_V3_MANIFEST_SHA256,
            "cross_v3_manifest_overlap_count":0,
            "binding_candidate_count":180,
            "prior_v3_candidate_count":90,
            "fresh_source_pool_count":520,
            "gdaa_candidate_count":90,
        },
        "model":v.MODEL,"temperature":0,"target_eligible_episodes":v.TARGET_ELIGIBLE,
        "max_games_scanned":v.MAX_GAMES_SCANNED,"post_reset_max_environment_actions":v.POST_RESET_MAX_ENV_ACTIONS,
        "memory_cap_proxy_tokens":v.MEMORY_CAP_PROXY_TOKENS,"valid_unseen_consumed":False,
        "gdaa_scorer_source_sha256":v.GDAA_SCORER_SHA256,"runner_source_sha256":v.RUNNER_SHA256,
        "scientific_result":"NOT_ASSESSED","episodes":episodes,
        "aggregate":{"scientific_result":"NOT_ASSESSED","evaluated_episodes":n,"eligible_found":n,"target_eligible_episodes":v.TARGET_ELIGIBLE,"all_episode_guards_pass":all_guards,"all_gdaa_defined":all(ep["arms"][name]["gdaa"] is not None for ep in episodes for name in v.ARMS),"natural_successful_gdaa1_rpa0_count_all_arms":natural,"metrics":metrics}
    }


def test_behavioral_invalid_turn_cap_does_not_invalidate_complete_pass():
    eps=[episode("generic_summary")]+[episode() for _ in range(7)]
    eps[1]["arms"]["tail_truncation"] = arm(False, False, False, invalid=9, events=[{"type":"NO_TOOL_CALL"} for _ in range(9)], termination="MODEL_INVALID_TURN_CAP_REACHED", technical=None)
    x=result(eps)
    out=v.validate_result(x)
    assert out["identity_ok"] and out["aggregate_consistent"] and out["no_true_technical_failures"]
    assert out["recomputed_metrics"]["tail_truncation"]["invalid_model_turns"]==9
    assert out["recomputed_metrics"]["tail_truncation"]["model_invalid_turn_cap_terminations"]==1
    assert out["preregistered_outcome"]=="PASS"


def test_true_technical_failure_fails_even_if_divergence_exists():
    eps=[episode("generic_summary")]+[episode() for _ in range(7)]
    eps[2]["arms"]["tail_truncation"]["technical_failure"]="MODEL_CALL_EXCEPTION:RuntimeError:x"
    eps[2]["all_guards_pass"]=False
    x=result(eps)
    out=v.validate_result(x)
    assert out["aggregate_consistent"]
    assert out["no_true_technical_failures"] is False
    assert out["preregistered_outcome"]=="FAIL"


def test_prior_v3_overlap_fails_identity():
    x=result([episode("plancarry")]+[episode() for _ in range(7)])
    x["binding_isolation"]["cross_v3_manifest_overlap_count"]=1
    out=v.validate_result(x)
    assert out["preregistered_outcome"]=="FAIL"
    assert out["identity_checks"]["prior_v3_overlap_zero"] is False


def test_no_divergence_is_inconclusive():
    out=v.validate_result(result([episode() for _ in range(8)]))
    assert out["preregistered_outcome"]=="INCONCLUSIVE_NO_NATURAL_ROUTE_DIVERGENCE"


def test_insufficient_is_inconclusive():
    out=v.validate_result(result([episode() for _ in range(7)]))
    assert out["preregistered_outcome"]=="INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"
