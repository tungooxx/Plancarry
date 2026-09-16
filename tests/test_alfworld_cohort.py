import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace/local-vlm/LLM/plancarry")
import alfworld_cohort_runner as c
import alfworld_interruption_harness as h

EXCLUDED = next(iter(c.PRE_INSPECTED_EXCLUSIONS))
FIXTURE = Path('/workspace/local-vlm/LLM/plancarry/results/alfworld_qualifications_v1/pick_and_place_simple-Book-None-SideTable-329__trial_T20190908_050633_745514.json')


def test_frozen_constants_exact():
    assert c.EXPERIMENT_ID == 'f59f04c3-847f-441b-a494-345740c957ee'
    assert c.RESEARCH_DECISION_ID == '82450eb7-5668-49df-bcb2-69d6d3d08980'
    assert c.MAX_GAMES_SCANNED == 30
    assert c.TARGET_ELIGIBLE == 12
    assert c.QUALIFICATION_MAX_ENV_ACTIONS == 30
    assert c.POST_RESET_MAX_ENV_ACTIONS == 8
    assert c.MEMORY_CAP_PROXY_TOKENS == 48
    assert EXCLUDED.endswith('pick_and_place_simple-Book-None-SideTable-329/trial_T20190908_050633_745514/game.tw-pddl')


def test_candidate_list_deterministic_and_excluded():
    a = c.candidate_games(); b = c.candidate_games()
    assert a == b == sorted(a)
    assert len(a) == 30
    assert EXCLUDED not in a
    assert all('pick_and_place_simple-' in x for x in a)


def test_exact_binomial_hand_cases():
    assert c.binomial_one_sided_p(5,0) == 0.03125
    assert c.binomial_one_sided_p(4,0) == 0.0625
    assert c.binomial_one_sided_p(0,0) == 1.0
    assert abs(c.binomial_one_sided_p(3,1) - 0.3125) < 1e-12


def test_reset_rule_on_excluded_engineering_fixture_only():
    d=json.load(open(FIXTURE))
    r=c.derive_reset(d)
    assert r is not None
    assert r['goal_object']=='book'
    assert r['reset_after']==4
    assert r['reference_first_progress_action']=='go to sidetable 1'
    assert r['recorded_reset_hash']==d['actions'][3]['state_hash']


def test_prefix_only_object_physically_removes_future_suffix():
    d=json.load(open(FIXTURE)); r=c.derive_reset(d); p=c.prefix_only_qualification(d,r['reset_after'])
    assert len(p['actions'])==4
    assert p['success'] is False
    assert 'reference_suffix' not in p
    # Compiler output must be invariant to arbitrary changes in the hidden future,
    # because the compiler receives p, not d.
    pc1=h.compile_plancarry(p,4,48)
    d2=copy.deepcopy(d); d2['actions'][4:]=[]
    p2=c.prefix_only_qualification(d2,4)
    pc2=h.compile_plancarry(p2,4,48)
    assert pc1==pc2
    assert h.token_count(pc1)<=48


def _synthetic_episode(pc,generic,trunc,obs=True,guards=True):
    def arm(v):
        return {'success':True,'reference_progress_agreement':v,'prefix_reversal_count':0,
                'consecutive_repeat_count':0,'invalid_model_turns':0,'usage_total':{'total_tokens':1}}
    return {'game_file':'synthetic','all_guards_pass':guards,'arms':{
        'observation_only':arm(obs),'tail_truncation':arm(trunc),
        'generic_summary':arm(generic),'plancarry':arm(pc)}}


def test_paired_test_counts_discordants():
    eps=[_synthetic_episode(True,False,False),_synthetic_episode(True,False,True),
         _synthetic_episode(False,True,False),_synthetic_episode(True,True,False)]
    x=c.paired_rpa_test(eps,'plancarry','generic_summary')
    assert x['wins_a']==2 and x['losses_a']==1 and x['discordant_pairs']==3


def test_aggregate_insufficient_cohort_is_inconclusive():
    eps=[_synthetic_episode(True,False,False) for _ in range(11)]
    x=c.aggregate(eps,30,11)
    assert x['measurement_status']=='INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT'
    assert x['scientific_result']=='NOT_ASSESSED'
    assert x['preregistered_condition_evaluations'] is None


def test_aggregate_guard_failure_is_invalid():
    eps=[_synthetic_episode(True,False,False) for _ in range(12)]
    eps[-1]['all_guards_pass']=False
    x=c.aggregate(eps,20,12)
    assert x['measurement_status']=='INVALID_GUARD_FAILURE'
    assert x['preregistered_condition_evaluations'] is None


def test_aggregate_valid_measures_but_does_not_assess():
    # 5 PC-only wins over each comparator -> one-sided p=0.03125; n=12.
    eps=[]
    for i in range(12):
        pc=True
        generic=False if i<5 else True
        trunc=False if i<5 else True
        eps.append(_synthetic_episode(pc,generic,trunc,obs=False))
    x=c.aggregate(eps,12,12)
    assert x['measurement_status']=='MEASURED_AWAITING_SCIENTIFIC_ASSESSMENT'
    assert x['scientific_result']=='NOT_ASSESSED'
    assert x['paired_tests']['plancarry_vs_generic_summary']['one_sided_exact_binomial_p']==0.03125
    assert x['preregistered_condition_evaluations']['pc_vs_generic_rpa_p_le_0_05'] is True
    assert x['preregistered_condition_evaluations']['pc_vs_truncation_rpa_p_le_0_05'] is True


def test_forbidden_information_guards_are_positive_pass_conditions():
    good=c.forbidden_information_guards(
        expert_plan_visible=False, hidden_facts_visible=False, future_suffix_visible=False
    )
    assert good == {
        'expert_plan_hidden': True,
        'hidden_facts_hidden': True,
        'future_suffix_unavailable_to_memory_compilers': True,
    }
    assert all(good.values())


def test_forbidden_information_guard_fails_if_any_forbidden_source_is_visible():
    for key in ['expert_plan_visible','hidden_facts_visible','future_suffix_visible']:
        args={'expert_plan_visible':False,'hidden_facts_visible':False,'future_suffix_visible':False}
        args[key]=True
        guards=c.forbidden_information_guards(**args)
        assert not all(guards.values())
