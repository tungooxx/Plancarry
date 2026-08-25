from __future__ import annotations
import copy, hashlib, json, tempfile
from pathlib import Path
import contextlib
import action_matched_future_plan_phase_runner_v1 as ph
import action_matched_future_plan_runtime_v1 as rt
import action_matched_future_plan_science_driver_v1 as drv

@contextlib.contextmanager
def raises(exc):
    try:
        yield
    except exc:
        return
    raise AssertionError(f"expected {exc.__name__}")

def a4(active=.20, nuisance=.01, neg_nuisance=None):
    neg=nuisance if neg_nuisance is None else neg_nuisance
    return {'NO_PATCH':0.0,'ACTIVE':{'+':active,'-':-active},'RANDOM_EQ_NORM':{'+':nuisance,'-':-nuisance},
            'UNRELATED_PAIR_RESIDUAL':{'+':nuisance,'-':-neg},'ACTION_HISTORY_MATCHED_NULL':{'+':nuisance,'-':-nuisance},
            'FUTURE_TOKEN_DERANGED':{'+':nuisance,'-':-nuisance},'NEXT_DIVERGENT_ACTION_ONLY':{'+':nuisance,'-':-nuisance}}
def a5(active=.20,nuisance=.01):
    base={'A':0.0,'B':0.0}; out={'NO_PATCH':base}
    out['ACTIVE']={'+':{'A':active,'B':active},'-':{'A':-active,'B':active}}
    for arm in ('RANDOM_EQ_NORM','UNRELATED_PAIR_RESIDUAL','ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY'):
        out[arm]={'+':{'A':nuisance,'B':nuisance},'-':{'A':-nuisance,'B':-nuisance}}
    return out
def row(i,active=.20,nuisance=.01,a5active=.20,a5nuis=.01): return {'index':i,'a4_margins':a4(active,nuisance),'a5_margins':a5(a5active,a5nuis)}
def payload(grids,inds=None):
    inds=list(range(20)) if inds is None else inds
    return {'phase':'ACTION_MATCHED_FUTURE_PLAN_DEVELOPMENT','eligible_indices':inds,'grid_results':grids,'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**ph.binding_payload()}

def test_sign_asymmetry_false_pass_guard():
    x=a4(active=.20,nuisance=.01,neg_nuisance=.25)
    c=ph.a4_components(x)
    assert abs(c['unrelated_shift']-.25)<1e-12
    assert c['joint_future_margin']<.05

def test_a5_orientation_uses_qb_negative_active():
    x=a5(.20,.01); c=ph.a5_components(x)
    assert abs(c['forward5']-.20)<1e-12 and abs(c['reverse5']-.20)<1e-12
    assert abs(c['joint_continuation5']-.19)<1e-12

def test_development_a4_only_selection_then_a5_futility_no_reselection():
    grids={}
    for L in ph.LAYERS:
        for A in ph.ALPHAS: grids[ph.grid_key(L,A)]=[row(i,.10,.01,.10,.01) for i in range(20)]
    # Best A4 point deliberately fails A5. A5-good runner-up MUST NOT be selected.
    grids[ph.grid_key(14,.5)]=[row(i,.30,.01,.01,.01) for i in range(20)]
    grids[ph.grid_key(21,.5)]=[row(i,.20,.01,.20,.01) for i in range(20)]
    t=ph.select_development(payload(grids))
    assert (t['selected_layer'],t['selected_alpha'])==(14,.5)
    assert t['status']=='DEVELOPMENT_FUTILITY_STOP' and t['a4_gate_pass'] is True and t['a5_gate_pass'] is False

def test_development_pass_and_atomic_seal():
    grids={ph.grid_key(L,A):[row(i) for i in range(20)] for L in ph.LAYERS for A in ph.ALPHAS}
    with tempfile.TemporaryDirectory() as td:
        sp=Path(td)/'seal.json'; t=ph.select_development(payload(grids),sp)
        assert t['status']=='DEVELOPMENT_SELECTION_PASS' and sp.is_file()
        seal=json.loads(sp.read_text()); assert seal['confirmation_accessed'] is False and len(seal['eligible_indices'])==20
        with raises(ph.ContractError): ph.atomic_write_new(sp,seal)

def test_confirmation_holm_both_coprimary_pass_and_tamper_fail():
    grids={ph.grid_key(L,A):[row(i) for i in range(20)] for L in ph.LAYERS for A in ph.ALPHAS}
    with tempfile.TemporaryDirectory() as td:
        sp=Path(td)/'seal.json'; ph.select_development(payload(grids),sp); seal=json.loads(sp.read_text()); ss=ph.canonical_sha(seal)
        cp={'phase':'ACTION_MATCHED_FUTURE_PLAN_CONFIRMATION','families':[dict(row(64+i),eligible=True) for i in range(20)],'selected_layer':seal['selected_layer'],'selected_alpha':seal['selected_alpha'],'development_seal_sha256':ss,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**ph.binding_payload()}
        res=ph.evaluate_confirmation(cp,seal,ss)
        assert res['status']=='SUPPORTED_ACTION_MATCHED_MULTI_STEP_FUTURE_PLAN_CARRIER' and res['holm']['all_reject'] is True
        bad=copy.deepcopy(seal); bad['selected_alpha']=999
        with raises(ph.ContractError): ph.evaluate_confirmation(cp,bad,ph.canonical_sha(bad))

def test_pair_source_geometry_and_a4_only_neutral_branch5():
    prefix=[101,102]; ids={'shared_action3':[3,4],'A4':[11,12],'A5':[31,32],'B4':[21,22,23],'B5':[41,42]}
    A,B=rt.source_condition_ids(prefix,ids,'ACTIVE'); X,Y=rt.source_condition_ids(prefix,ids,'NEXT_DIVERGENT_ACTION_ONLY')
    assert len(A)==len(B)==len(X)==len(Y) and A[-4:]==B[-4:]==X[-4:]==Y[-4:]==list(rt.SOURCE_END_IDS)
    # Locate the L5 slot immediately before newline+SOURCE_END and prove identical neutral construction.
    L5=2; start=len(X)-len(rt.SOURCE_END_IDS)-len(rt.NEWLINE_IDS)-L5
    assert X[start:start+L5]==Y[start:start+L5]==[rt.NEUTRAL_CYCLE[i%len(rt.NEUTRAL_CYCLE)] for i in range(L5)]

def test_derangement_preserves_multiset_rightmost_and_fails_all_equal():
    ids={'shared_action3':[7,8],'A4':[1,1,2,3],'A5':[4,5,4],'B4':[6,7,8,6,9],'B5':[10,11]}
    out=rt.validate_future_segments_constructible(ids)
    for k in ('A4','A5','B4','B5'):
        assert len(out[k])==len(ids[k]) and sorted(out[k])==sorted(ids[k])
        assert out[k]!=ids[k] and out[k][-1]!=ids[k][-1]
    bad=dict(ids); bad['B5']=[10,10]
    with raises(rt.RuntimeContractError): rt.validate_future_segments_constructible(bad)

def test_derangement_uses_pinned_reviewed_helper_only():
    src=Path('action_matched_future_plan_runtime_v1.py').read_text()
    assert 'strong_interior_derangement' in src
    assert 'def _strict_rotate' not in src
    assert 'hashlib.sha256(key.encode())' not in src

def test_population_binding_and_preflight_no_science():
    assert ph.sha_file(rt.POP_REL)==ph.POPULATION_SHA256
    x=drv.preflight()
    assert x['status']=='READY_NO_SCIENCE' and x['model_calls']==x['model_loads']==x['environment_execution']==0
    assert x['development_pool_indices']==list(range(64)) and x['confirmation_accessed'] is False and x['valid_seen_accessed'] is False

def test_confirmation_gate_precedes_model_load_in_source():
    src=Path('action_matched_future_plan_science_driver_v1.py').read_text()
    block=src[src.index("if args.phase=='development'"):src.index("print(json.dumps({'ACTION_MATCHED_TERMINAL'")]
    assert block.index('_load_seal') < block.index('load_model')
    assert block.index("_refuse([CONF_PACKET_DIR,CONF_PAYLOAD,CONF_RESULT])") < block.index('load_model')

def test_unexpected_exception_is_not_declared_ineligible_source_guard():
    src=Path('action_matched_future_plan_science_driver_v1.py').read_text()
    seg=src[src.index('def produce_pair_attempt'):src.index('def _scan_first20')]
    assert 'except Exception as exc' not in seg
    assert 'except (ExecutionContractError, am.RuntimeContractError) as exc' in seg


def test_full_authority_binding_and_tamper_fail_closed():
    rt.verify_frozen_design('.')
    assert ph.binding_payload()['authority_commit']=='d564dca2e2e335e30862262b7e50f12498d30ce8'
    assert ph.binding_payload()['independent_review_sha256']=='64f7d4b62917489c4d96f970ea23301a4b01a2a4ccecd440a97a2c781fadc47f'
    assert ph.binding_payload()['derangement_review_sha256']=='790aa1d0700b5bc3a77d748aaa7ee6e29407fea0d685639586b578696437fb42'
    assert ph.binding_payload()['random_control_repair_sha256']=='1247f7a3696408fa5a0d5f5ccab3f42621cf709ebf7204e64bb293cf62662772'
    assert ph.binding_payload()['random_source_sha256']=='7768a45cd41048ebcabd27a0be6602b41642fa95f425883e199a94c3c2291592'
    assert ph.binding_payload()['derangement_helper_sha256']=='c93bc0b76110a88eb54dfc0b0d2ea63f13b515140b68e927c12da2f495ec0367'

def test_a5_sign_asymmetry_false_pass_guard():
    x=a5(.20,.01)
    x['FUTURE_TOKEN_DERANGED']={'+':{'A':.01,'B':.01},'-':{'A':-.25,'B':-.25}}
    c=ph.a5_components(x)
    assert abs(c['deranged5']-.25)<1e-12
    assert c['joint_continuation5']<.05


def test_random_control_exact_inherited_key_and_canary():
    import math
    import localcontinuation_science_driver_v1 as lc
    key='ReplayResidualLocalContinuation|RANDOM_EQ_NORM|0|CANARY_GAME|L14'
    v=lc.rademacher(16,1.0,key)
    compact=lambda x: json.dumps(x,separators=(',',':'),sort_keys=True).encode()
    signs=[1 if float(x)>0 else -1 for x in v.tolist()]
    assert hashlib.sha256(compact(signs)).hexdigest()=='8781682ebaae7f23c19a53f332ad8eba320b3d24ee596b81321d70acea5ea458'
    assert hashlib.sha256(compact([float(x) for x in v.tolist()])).hexdigest()=='ab76e40900cc8e43d7458a6b8474ff008b38ef2732ef18875ed9c2f2088ec753'
    src=Path('action_matched_future_plan_science_driver_v1.py').read_text()
    assert 'ActionMatchedFuturePlan|' not in src
    assert 'am.rademacher(' not in src
    assert 'lc.rademacher(' in src
    assert 'ReplayResidualLocalContinuation|RANDOM_EQ_NORM|{packet[\'family\']}|{packet[\'game_path\']}|L{int(layer)}' in src
    assert not hasattr(rt,'rademacher')


def test_frozen_design_guard_precedes_model_load_in_source():
    src=Path('action_matched_future_plan_science_driver_v1.py').read_text()
    block=src[src.index("if args.phase=='development'"):src.index("print(json.dumps({'ACTION_MATCHED_TERMINAL'")]
    assert block.index('am.verify_frozen_design(ROOT)') < block.index('load_model')
    assert block.index('_load_seal') < block.index('am.verify_frozen_design(ROOT)')  # confirmation seal first


def test_first20_scan_policy_without_model_or_environment():
    old_load,old_prod=drv._load_population,drv.produce_pair_attempt
    rows=[{'frozen_index':i,'game_path':f'g{i}','phase':'development_pool'} for i in range(32)]
    # 7 deterministic misses before the 20th eligible; first20 should freeze at index26.
    misses={0,4,8,12,16,20,24}
    try:
        drv._load_population=lambda phase_name: rows
        drv.produce_pair_attempt=lambda tok,model,row,prov: {'frozen_index':row['frozen_index'],'eligible':row['frozen_index'] not in misses}
        attempts,eligible=drv._scan_first20(None,None,'development',{})
    finally:
        drv._load_population,drv.produce_pair_attempt=old_load,old_prod
    assert [x['frozen_index'] for x in attempts]==list(range(27))
    assert [x['frozen_index'] for x in eligible]==[i for i in range(27) if i not in misses]
    assert len(eligible)==20 and eligible[-1]['frozen_index']==26
    assert list(drv.POOL['development'])==list(range(64))
    assert list(drv.POOL['confirmation'])==list(range(64,128))


def test_future_derangement_exact_four_segments_before_padding():
    prefix=[901,902]
    ids={'shared_action3':[7,8], 'A4':[101,102,101], 'A5':[111,112], 'B4':[121,122,123,121], 'B5':[131,132,133]}
    d=rt.validate_future_segments_constructible(ids)
    A,B=rt.source_condition_ids(prefix,ids,'FUTURE_TOKEN_DERANGED')
    L4=max(len(ids['A4']),len(ids['B4'])); L5=max(len(ids['A5']),len(ids['B5']))
    def assemble(s4,s5):
        return [*prefix,*ids['shared_action3'],*rt.NEWLINE_IDS,*rt._pad(s4,L4),*rt.NEWLINE_IDS,*rt._pad(s5,L5),*rt.NEWLINE_IDS,*rt.SOURCE_END_IDS]
    assert A==assemble(d['A4'],d['A5'])
    assert B==assemble(d['B4'],d['B5'])
    for k in ('A4','A5','B4','B5'):
        assert len(d[k])==len(ids[k]) and sorted(d[k])==sorted(ids[k]) and d[k][-1]!=ids[k][-1]


def test_confirmation_denominator_fail_closed():
    grids={ph.grid_key(L,A):[row(i) for i in range(20)] for L in ph.LAYERS for A in ph.ALPHAS}
    with tempfile.TemporaryDirectory() as td:
        sp=Path(td)/'seal.json'; ph.select_development(payload(grids),sp); seal=json.loads(sp.read_text()); ss=ph.canonical_sha(seal)
        base={'phase':'ACTION_MATCHED_FUTURE_PLAN_CONFIRMATION','selected_layer':seal['selected_layer'],'selected_alpha':seal['selected_alpha'],'development_seal_sha256':ss,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**ph.binding_payload()}
        nineteen={**base,'families':[dict(row(64+i),eligible=True) for i in range(19)]}
        res=ph.evaluate_confirmation(nineteen,seal,ss)
        assert res['status']=='INCONCLUSIVE_CONFIRMATION_CONSTRUCTIBILITY' and res['eligible_count']==19
        twenty_plus_ineligible={**base,'families':[dict(row(64+i),eligible=True) for i in range(20)]+[dict(row(99),eligible=False)]}
        with raises(ph.ContractError): ph.evaluate_confirmation(twenty_plus_ineligible,seal,ss)


def test_science_launcher_requires_exact_future_execution_binding():
    src=Path('action_matched_future_plan_vast_primary_v1.sh').read_text()
    for key in ('ACTION_MATCHED_EXPECTED_GIT_COMMIT','ACTION_MATCHED_DRIVER_SHA256','ACTION_MATCHED_RUNTIME_SHA256','ACTION_MATCHED_PHASE_SHA256','ACTION_MATCHED_VALIDATOR_SHA256','ACTION_MATCHED_SHELL_SHA256'):
        assert key in src
    assert 'verify_exec_binding' in src
    assert src.index('verify_exec_binding', src.index('development)')) < src.index('exec "$PY"', src.index('development)'))
    assert src.index('verify_exec_binding', src.index('confirmation)')) < src.index('exec "$PY"', src.index('confirmation)'))


def test_execution_provenance_binds_all_final_stack_files():
    src=Path('action_matched_future_plan_science_driver_v1.py').read_text()
    for field in ('driver_sha256','runtime_sha256','phase_runner_sha256','validator_sha256','launcher_sha256','implementation_test_sha256','session_runtime_sha256','low_level_localcontinuation_runtime_sha256'):
        assert field in src
