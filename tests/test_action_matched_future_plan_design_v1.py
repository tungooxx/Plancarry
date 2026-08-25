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
    m0=0.10; mp=0.30; mm=-0.15; rplus=0.13; rminus=0.07; unrel=0.11; action=0.09; der=0.12; a4only=0.115
    forward=mp-m0; reverse=m0-mm; bid=min(forward,reverse)
    nuisance=max(abs(rplus-rminus)/2,abs(unrel-m0),abs(action-m0),abs(der-m0),abs(a4only-m0))
    joint=bid-nuisance
    assert round(forward,6)==0.2 and round(reverse,6)==0.25 and joint>0.15
    # Saturated/invariant v2-like behavior must fail exactly.
    m0=mp=mm=rplus=rminus=unrel=action=der=a4only=0.2
    bid=min(mp-m0,m0-mm); nuisance=max(abs(rplus-rminus)/2,abs(unrel-m0),abs(action-m0),abs(der-m0),abs(a4only-m0))
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
    assert '+UNRELATED_PAIR_RESIDUAL' in c['family_components']['unrelated5']
