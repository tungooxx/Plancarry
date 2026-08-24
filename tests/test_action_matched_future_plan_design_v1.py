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
    assert P['source_representation']['active_residual'].startswith('FP32 r_AB')
    assert P['causal_runtime']['injections_per_rollout']==1 and not P['causal_runtime']['reinjection']
    assert P['primary_endpoint']['immediate_action_excluded'] is True
def test_bidirectional_metric_math():
    # Synthetic A-oriented effect: +r favors A, -r favors B, nuisances small.
    m0=0.10; mp=0.30; mm=-0.15; rplus=0.13; rminus=0.07; unrel=0.11; action=0.09; der=0.12
    forward=mp-m0; reverse=m0-mm; bid=min(forward,reverse)
    nuisance=max(abs(rplus-rminus)/2,abs(unrel-m0),abs(action-m0),abs(der-m0))
    joint=bid-nuisance
    assert round(forward,6)==0.2 and round(reverse,6)==0.25 and joint>0.15
    # Saturated/invariant v2-like behavior must fail exactly.
    m0=mp=mm=rplus=rminus=unrel=action=der=0.2
    bid=min(mp-m0,m0-mm); nuisance=max(abs(rplus-rminus)/2,abs(unrel-m0),abs(action-m0),abs(der-m0))
    assert bid-nuisance==0.0
def test_old_splits_prohibited():
    text='\n'.join(P['prohibitions'])
    assert 'old LocalContinuation-v2 confirmation32..51' in text
    assert 'valid_seen' in text and 'valid_unseen' in text
    assert P['confirmation_policy']['operating_point'].startswith('import exact selected')
