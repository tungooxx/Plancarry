import json, hashlib, pathlib, statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]
D=ROOT/'results/design'
P=json.load(open(D/'plancarry_action_matched_future_plan_prereg_v1_20260825.json'))
M=json.load(open(D/'plancarry_action_matched_future_plan_population_v1_20260825.json'))
def test_population_freeze():
    assert M['selected_n']==160
    assert M['development_pool_n']==64 and M['confirmation_pool_n']==64 and M['reserve_pool_n']==32
    paths=[x['game_path'] for x in M['selected']]
    assert len(paths)==len(set(paths))==160
    assert M['overlap_checks']=={'historical_exposed':0,'v1_selected':0,'v2_selected':0,'within_selected_duplicates':0}
    assert M['model_calls']==M['environment_execution']==M['game_files_opened']==0
    assert hashlib.sha256('\n'.join(paths).encode()).hexdigest()==M['selected_paths_sha256']
def test_pair_semantics():
    q=P['plan_pair_generation']; assert q['calls_per_family']==1 and q['parse'].startswith('exact one fullmatch')
    assert 'exact same first action' in q['prompt'] and 'second actions MUST be different' in q['prompt']
    assert P['pair_validation']['development_fail'].startswith('fewer than20 eligible')
    assert 'complete source-control constructibility' in P['pair_validation']['eligibility_usage']
    assert 'before eligibility freeze' in ' '.join(P['pair_validation']['required'])
    assert 'A5/B5 continuation margin constructibility' in ' '.join(P['pair_validation']['required'])
    assert P['source_representation']['active_residual'].startswith('FP32 r_AB')
    assert P['causal_runtime']['injections_per_rollout']==1 and not P['causal_runtime']['reinjection']
    assert P['primary_endpoint']['immediate_action_excluded'] is True
def test_bidirectional_metric_math():
    # Synthetic A-oriented effect: +r favors A, -r favors B, nuisances small.
    m0=0.10; mp=0.30; mm=-0.15; rplus=0.13; rminus=0.07
    unrel_p=0.11; unrel_m=0.09; action_p=0.09; action_m=0.105; der_p=0.12; der_m=0.08; a4only_p=0.115; a4only_m=0.095
    forward=mp-m0; reverse=m0-mm; bid=min(forward,reverse)
    nuisance=max(abs(rplus-rminus)/2,max(abs(unrel_p-m0),abs(unrel_m-m0)),max(abs(action_p-m0),abs(action_m-m0)),max(abs(der_p-m0),abs(der_m-m0)),max(abs(a4only_p-m0),abs(a4only_m-m0)))
    joint=bid-nuisance
    assert round(forward,6)==0.2 and round(reverse,6)==0.25 and joint>0.15
    # Saturated/invariant v2-like behavior must fail exactly.
    m0=mp=mm=rplus=rminus=unrel_p=unrel_m=action_p=action_m=der_p=der_m=a4only_p=a4only_m=0.2
    bid=min(mp-m0,m0-mm); nuisance=max(abs(rplus-rminus)/2,max(abs(unrel_p-m0),abs(unrel_m-m0)),max(abs(action_p-m0),abs(action_m-m0)),max(abs(der_p-m0),abs(der_m-m0)),max(abs(a4only_p-m0),abs(a4only_m-m0)))
    assert bid-nuisance==0.0
def test_old_splits_prohibited():
    text='\n'.join(P['prohibitions'])
    assert 'old LocalContinuation-v2 confirmation32..51' in text
    assert 'valid_seen' in text and 'valid_unseen' in text
    assert P['confirmation_policy']['operating_point'].startswith('import exact selected')


def _neutral(n):
    cycle=[20628,2266,8458,34857,13]
    return [cycle[i%len(cycle)] for i in range(n)]

def _pad(ids,n):
    return list(ids)+_neutral(n-len(ids))

def test_next_divergent_action_only_exact_geometry():
    a4=[11,12,13]; b4=[21,22]; a5=[31,32,33,34]; b5=[41]
    L4=max(len(a4),len(b4)); L5=max(len(a5),len(b5))
    common=[101,102,103]; sep=[198]; end=[999]
    active_a=common+_pad(a4,L4)+sep+_pad(a5,L5)+end
    active_b=common+_pad(b4,L4)+sep+_pad(b5,L5)+end
    n5=_neutral(L5)
    a4only_a=common+_pad(a4,L4)+sep+n5+end
    a4only_b=common+_pad(b4,L4)+sep+n5+end
    assert len(active_a)==len(active_b)==len(a4only_a)==len(a4only_b)
    assert a4only_a[-1]==a4only_b[-1]==active_a[-1]==active_b[-1]==999
    assert a4only_a[len(common)+L4+1:-1]==a4only_b[len(common)+L4+1:-1]==n5
    assert a4only_a[len(common):len(common)+len(a4)]==a4
    assert a4only_b[len(common):len(common)+len(b4)]==b4
    assert all(x not in a5+b5 for x in n5)

def test_repaired_multistep_scope_and_coprimary_math():
    assert 'NEXT_DIVERGENT_ACTION_ONLY' in P['controls']
    fc=P['primary_endpoint']['family_components']
    assert 'next_divergent_action_only_shift' in fc and 'next_divergent_action_only_shift' in fc['joint_future_margin']
    c=P['continuation5_coprimary']; assert c['name']=='BIDIRECTIONAL_SECOND_FUTURE_ACTION_CONTINUATION'
    assert 'same frozen point' in c['claim_boundary'] or 'BOTH' in c['claim_boundary']
    # Synthetic persistence beyond A4 identity: active improves both A5/B5, A4-only null does not.
    qA0=0.10; qB0=0.05; qAp=0.22; qBm=0.18
    bid5=min(qAp-qA0,qBm-qB0)
    random5=0.01; unrel5=0.02; action5=0.015; der5=0.025; a4only5=0.03
    joint5=bid5-max(random5,unrel5,action5,der5,a4only5)
    assert bid5>=0.12 and joint5>=0.09
    assert 'Holm' in P['confirmation_policy']['primary_test'] and 'H4' in P['confirmation_policy']['primary_test'] and 'H5' in P['confirmation_policy']['primary_test']
    assert 'A5/B5 cannot select or retune' in P['development_selection']['pass_gate']
    assert '+RANDOM_EQ_NORM' in c['family_components']['random5']
    assert '+UNRELATED_PAIR_RESIDUAL' in c['family_components']['unrelated5'] and '-UNRELATED_PAIR_RESIDUAL' in c['family_components']['unrelated5']
    assert '+NEXT_DIVERGENT_ACTION_ONLY' in fc['next_divergent_action_only_shift'] and '-NEXT_DIVERGENT_ACTION_ONLY' in fc['next_divergent_action_only_shift']

def test_bidirectional_semantic_nuisance_sign_asymmetry_guard():
    fc=P['primary_endpoint']['family_components']
    c5=P['continuation5_coprimary']['family_components']
    for key,name in [('unrelated_shift','UNRELATED_PAIR_RESIDUAL'),('action_history_shift','ACTION_HISTORY_MATCHED_NULL'),('deranged_shift','FUTURE_TOKEN_DERANGED'),('next_divergent_action_only_shift','NEXT_DIVERGENT_ACTION_ONLY')]:
        assert ('+'+name) in fc[key] and ('-'+name) in fc[key]
    for key,name in [('unrelated5','UNRELATED_PAIR_RESIDUAL'),('action_history5','ACTION_HISTORY_MATCHED_NULL'),('deranged5','FUTURE_TOKEN_DERANGED'),('next_divergent_action_only5','NEXT_DIVERGENT_ACTION_ONLY')]:
        expr=c5[key]
        assert ('qA(+'+name) in expr and ('qA(-'+name) in expr and ('qB(+'+name) in expr and ('qB(-'+name) in expr
    # Exact A2 counterexample: bidirectional ACTIVE=.20; +C nuisance=.01 but omitted -C=.25.
    active_bid=0.20; plus_shift=0.01; minus_shift=0.25
    old_joint=active_bid-plus_shift
    robust_joint=active_bid-max(plus_shift,minus_shift)
    assert round(old_joint,6)==0.19
    assert round(robust_joint,6)==-0.05 and robust_joint < 0.05
    # Same failure mode for A5 across branch/sign states.
    a5_active_bid=0.20
    shifts=[0.01,0.25,0.02,0.03] # qA(+C), qA(-C), qB(+C), qB(-C) absolute shifts
    old_joint5=a5_active_bid-max(shifts[0],shifts[2])
    robust_joint5=a5_active_bid-max(shifts)
    assert round(old_joint5,6)==0.18
    assert round(robust_joint5,6)==-0.05 and robust_joint5 < 0.05
    orient=P['nuisance_orientation_contract']
    assert 'BOTH +alpha*C and -alpha*C' in orient['scope']
    assert 'Missing either sign' in orient['fail_closed']
