#!/usr/bin/env python3
"""Pure statistics/selection authority for Grounded ActionMatched-v2.
No model or environment access. Mirrors reviewed prereg SHA 23101c5e...
"""
from __future__ import annotations
import hashlib, json, math, os
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

AUTHORITY_COMMIT='b30028eb25f12be60ac96af8c6f6ee2926db82e4'
AUTHORITY_TREE='ff83ceb0833ea454af1f209a06047c3fded2c059'
PREREG_SHA256='23101c5ed38c12196e3b2b760001a1f7f0801d363de49ddd4963d9a35b86060b'
SEMANTIC_DIFF_SHA256='933d6e5a0a1de3b1f001304736c9399601193d4a3184dfe160f027629ccef58a'
STATIC_AUDIT_SHA256='4e203bef9bad1ded8e16994c45c4fb578402d8bb8242dc280319af4a5446589c'
AUTHORITY_TEST_SHA256='9edc00c99438d683ab62d61e41b211c0931b8be8d2a9da1b916d7673119e04dc'
POPULATION_SHA256='49ada50d70257e1106d30a39e69567af5c4892367e8972a09f4ba575029729bc'
CONSTRUCTIBILITY_SHA256='72459bd19f68a35bbc25e57671658689012748ff89d332ed2058d6bd7a212e42'
AUTHORITY_REVIEW_SHA256='d9de986b318f855d8c04ae8f6d56588b02ca4ef6c7224c7e6c08ddcc28e84b4f'
AUTHORITY_REVIEW_COMMIT='fb12e179f7b065f17eb0079f37c0fcee97d465c8'
SESSION_RUNTIME_SHA256='585e44ec5cd2395be0804b865de85ac36c5db79117cf4061566cf16a9749e3b6'
RANDOM_SOURCE_SHA256='7768a45cd41048ebcabd27a0be6602b41642fa95f425883e199a94c3c2291592'
LAYERS=(7,14,21,27); ALPHAS=(0.25,0.5,1.0)
SEMANTIC=('UNRELATED_PAIR_RESIDUAL','ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY','FUTURE_ACTION_SEQUENCE_ONLY')
RANDOM='RANDOM_EQ_NORM'; ACTIVE='ACTIVE'; NO_PATCH='NO_PATCH'

class ContractError(RuntimeError): pass

def canonical_sha(obj:Any)->str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def sha_file(path:str|Path)->str:
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def binding_payload()->dict[str,Any]:
    return {
        'authority_commit':AUTHORITY_COMMIT,'authority_tree':AUTHORITY_TREE,
        'prereg_sha256':PREREG_SHA256,'semantic_diff_sha256':SEMANTIC_DIFF_SHA256,
        'static_audit_sha256':STATIC_AUDIT_SHA256,'authority_test_sha256':AUTHORITY_TEST_SHA256,
        'population_sha256':POPULATION_SHA256,'constructibility_sha256':CONSTRUCTIBILITY_SHA256,
        'authority_review_sha256':AUTHORITY_REVIEW_SHA256,'authority_review_commit':AUTHORITY_REVIEW_COMMIT,
        'session_runtime_sha256':SESSION_RUNTIME_SHA256,'random_source_sha256':RANDOM_SOURCE_SHA256,
        'science_execution_forbidden_until_executable_review_pass':True,
    }

def grid_key(layer:int,alpha:float)->str: return f'L{int(layer)}_A{float(alpha):g}'

def _finite(x:Any,label:str)->float:
    y=float(x)
    if not math.isfinite(y): raise ContractError(f'NONFINITE:{label}')
    return y

def _validity(margins:Mapping[str,Any])->Mapping[str,Any]:
    x=margins.get('_validity',{})
    if x is None: return {}
    if not isinstance(x,Mapping): raise ContractError('INVALID_VALIDITY_MAP')
    return x

def _signpair(row:Mapping[str,Any],arm:str)->tuple[float,float]:
    x=row.get(arm)
    if not isinstance(x,Mapping) or '+' not in x or '-' not in x: raise ContractError(f'MISSING_BOTH_SIGNS:{arm}')
    return _finite(x['+'],arm+'+'),_finite(x['-'],arm+'-')

def a4_components(margins:Mapping[str,Any])->dict[str,Any]:
    m0=_finite(margins[NO_PATCH],'m0'); ap,am=_signpair(margins,ACTIVE)
    forward=ap-m0; reverse=m0-am; bidi=min(forward,reverse)
    rp,rm=_signpair(margins,RANDOM); random_half=abs(rp-rm)/2.0
    nuis={}
    for arm in SEMANTIC:
        p,n=_signpair(margins,arm); nuis[arm]=max(abs(p-m0),abs(n-m0))
    valid=_validity(margins)
    specificity_valid=bool(valid.get('active_nondegenerate',True)) and all(bool(valid.get(k,True)) for k in SEMANTIC)
    max_future=max(random_half,*[nuis[k] for k in SEMANTIC if k!='FUTURE_ACTION_SEQUENCE_ONLY'])
    max_semantic=max(random_half,*[nuis[k] for k in SEMANTIC])
    jf=bidi-max_future; js=bidi-max_semantic
    if not specificity_valid:
        # Reviewed denominator rule: retain family but force every joint endpoint non-positive.
        jf=min(0.0,jf); js=min(0.0,js)
    return {
      'forward':forward,'reverse':reverse,'bidirectional':bidi,'active_swap_span':abs(ap-am)/2.0,
      'random_halfspan':random_half,'unrelated_shift':nuis['UNRELATED_PAIR_RESIDUAL'],
      'action_history_shift':nuis['ACTION_HISTORY_MATCHED_NULL'],'deranged_shift':nuis['FUTURE_TOKEN_DERANGED'],
      'next_divergent_action_only_shift':nuis['NEXT_DIVERGENT_ACTION_ONLY'],
      'future_action_sequence_only_shift':nuis['FUTURE_ACTION_SEQUENCE_ONLY'],
      'joint_future_state_margin':jf,'joint_semantic_plan_margin':js,'specificity_valid':specificity_valid,
    }

def _branch_signs(row:Mapping[str,Any],arm:str)->tuple[float,float,float,float]:
    x=row.get(arm)
    if not isinstance(x,Mapping) or '+' not in x or '-' not in x: raise ContractError(f'MISSING_BOTH_SIGNS_A5:{arm}')
    p=x['+']; n=x['-']
    if not isinstance(p,Mapping) or not isinstance(n,Mapping) or not all(k in p and k in n for k in ('A','B')):
        raise ContractError(f'MISSING_BRANCH_MARGINS:{arm}')
    return _finite(p['A'],arm+'+A'),_finite(n['A'],arm+'-A'),_finite(p['B'],arm+'+B'),_finite(n['B'],arm+'-B')

def a5_components(margins:Mapping[str,Any])->dict[str,Any]:
    base=margins.get(NO_PATCH)
    if not isinstance(base,Mapping) or not all(k in base for k in ('A','B')): raise ContractError('MISSING_A5_NO_PATCH')
    a0=_finite(base['A'],'qA0'); b0=_finite(base['B'],'qB0')
    ap,am,bp,bm=_branch_signs(margins,ACTIVE)
    forward=ap-a0; reverse=bm-b0; bidi=min(forward,reverse)
    rp,rm,rbp,rbm=_branch_signs(margins,RANDOM)
    random5=max(abs(rp-rm)/2.0,abs(rbp-rbm)/2.0)
    nuis={}
    for arm in SEMANTIC:
        qa_p,qa_m,qb_p,qb_m=_branch_signs(margins,arm)
        nuis[arm]=max(abs(qa_p-a0),abs(qa_m-a0),abs(qb_p-b0),abs(qb_m-b0))
    valid=_validity(margins)
    specificity_valid=bool(valid.get('active_nondegenerate',True)) and all(bool(valid.get(k,True)) for k in SEMANTIC)
    max_future=max(random5,*[nuis[k] for k in SEMANTIC if k!='FUTURE_ACTION_SEQUENCE_ONLY'])
    max_semantic=max(random5,*[nuis[k] for k in SEMANTIC])
    jf=bidi-max_future; js=bidi-max_semantic
    if not specificity_valid:
        jf=min(0.0,jf); js=min(0.0,js)
    return {
      'forward5':forward,'reverse5':reverse,'bidirectional5':bidi,'random5':random5,
      'unrelated5':nuis['UNRELATED_PAIR_RESIDUAL'],'action_history5':nuis['ACTION_HISTORY_MATCHED_NULL'],
      'deranged5':nuis['FUTURE_TOKEN_DERANGED'],'next_divergent_action_only5':nuis['NEXT_DIVERGENT_ACTION_ONLY'],
      'future_action_sequence_only5':nuis['FUTURE_ACTION_SEQUENCE_ONLY'],
      'joint_future_state_continuation5':jf,'joint_semantic_plan_continuation5':js,'specificity_valid5':specificity_valid,
    }

def aggregate_point(rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
    if len(rows)!=20: raise ContractError(f'DEVELOPMENT_DENOMINATOR_MUST_BE_20:{len(rows)}')
    a4=[a4_components(r['a4_margins']) for r in rows]; a5=[a5_components(r['a5_margins']) for r in rows]
    return {
      'n':20,'median_joint_semantic_plan_margin':median(x['joint_semantic_plan_margin'] for x in a4),
      'median_bidirectional':median(x['bidirectional'] for x in a4),
      'median_active_swap_span':median(x['active_swap_span'] for x in a4),
      'positive_bidirectional':sum(x['bidirectional']>0 for x in a4),
      'positive_joint_semantic_plan_margin':sum(x['joint_semantic_plan_margin']>0 for x in a4),
      'median_joint_semantic_plan_continuation5':median(x['joint_semantic_plan_continuation5'] for x in a5),
      'median_bidirectional5':median(x['bidirectional5'] for x in a5),
      'positive_joint_semantic_plan_continuation5':sum(x['joint_semantic_plan_continuation5']>0 for x in a5),
      'invalid_specificity_A4':sum(not x['specificity_valid'] for x in a4),
      'invalid_specificity_A5':sum(not x['specificity_valid5'] for x in a5),
      'per_family':[{'index':int(r['index']),**x,**y} for r,x,y in zip(rows,a4,a5)],
    }

def _check_binding(obj:Mapping[str,Any])->None:
    for k,v in binding_payload().items():
        if obj.get(k)!=v: raise ContractError(f'BINDING_DRIFT:{k}')

def select_development(payload:Mapping[str,Any],seal_path:str|Path|None=None)->dict[str,Any]:
    if payload.get('phase')!='ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT': raise ContractError('WRONG_DEVELOPMENT_PHASE')
    for flag in ('confirmation_accessed','reserve_accessed','valid_seen_accessed','valid_unseen_accessed'):
        if payload.get(flag) is not False: raise ContractError(f'DEVELOPMENT_SPLIT_ISOLATION:{flag}')
    _check_binding(payload)
    eligible=payload.get('eligible_indices')
    if not isinstance(eligible,list): raise ContractError('ELIGIBLE_INDICES_MISSING')
    if len(eligible)<20:
        if payload.get('grid_results') not in ({},None): raise ContractError('GRID_FORBIDDEN_BELOW_20')
        attempted=payload.get('attempted_count'); reasons=payload.get('ineligibility_reason_counts')
        if not isinstance(attempted,int) or isinstance(attempted,bool) or attempted<=0 or attempted<len(eligible): raise ContractError('ATTEMPTED_COUNT_INVALID')
        if not isinstance(reasons,Mapping): raise ContractError('INELIGIBILITY_REASON_COUNTS_MISSING')
        norm={}
        for k,v in reasons.items():
            if not isinstance(k,str) or not k or not isinstance(v,int) or isinstance(v,bool) or v<=0: raise ContractError('INELIGIBILITY_REASON_COUNTS_INVALID')
            norm[k]=v
        norm={k:norm[k] for k in sorted(norm)}
        if sum(norm.values())!=attempted-len(eligible): raise ContractError('INELIGIBILITY_REASON_COUNT_MISMATCH')
        return {'kind':'ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT_TERMINAL_V1','status':'INCONCLUSIVE_GROUNDED_PAIR_CONSTRUCTIBILITY','eligible_count':len(eligible),'attempted_count':attempted,'ineligibility_reason_counts':norm,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY','confirmation_accessed':False,**binding_payload()}
    if len(eligible)!=20: raise ContractError('EXACTLY_FIRST20_ELIGIBLE_REQUIRED')
    grids=payload.get('grid_results'); aggs={}
    if not isinstance(grids,Mapping): raise ContractError('GRID_RESULTS_MISSING')
    for layer in LAYERS:
        for alpha in ALPHAS:
            key=grid_key(layer,alpha); rows=grids.get(key)
            if not isinstance(rows,list): raise ContractError(f'MISSING_GRID:{key}')
            if [int(r['index']) for r in rows]!=[int(x) for x in eligible]: raise ContractError(f'GRID_DENOMINATOR_DRIFT:{key}')
            aggs[key]=aggregate_point(rows)
    selected_key=sorted(aggs,key=lambda k:(-aggs[k]['median_joint_semantic_plan_margin'],-aggs[k]['median_bidirectional'],-aggs[k]['median_active_swap_span'],float(k.split('_A')[1]),int(k[1:].split('_A')[0])))[0]
    sel=aggs[selected_key]; layer=int(selected_key[1:].split('_A')[0]); alpha=float(selected_key.split('_A')[1])
    pass_a4=sel['median_joint_semantic_plan_margin']>=0.05 and sel['median_bidirectional']>=0.05 and sel['positive_bidirectional']>=15
    pass_a5=sel['median_joint_semantic_plan_continuation5']>=0.05 and sel['median_bidirectional5']>=0.05 and sel['positive_joint_semantic_plan_continuation5']>=15
    common={'kind':'ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT_TERMINAL_V1','eligible_count':20,'selected_layer':layer,'selected_alpha':alpha,'selected_grid_key':selected_key,'all_grid_aggregates':aggs,'confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY',**binding_payload()}
    if not (pass_a4 and pass_a5): return {**common,'status':'DEVELOPMENT_FUTILITY_STOP','a4_gate_pass':pass_a4,'a5_gate_pass':pass_a5}
    seal={'kind':'ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT_SELECTION_V1','status':'DEVELOPMENT_SELECTION_PASS','selected_layer':layer,'selected_alpha':alpha,'selected_grid_key':selected_key,'eligible_indices':[int(x) for x in eligible],'all_grid_aggregates':aggs,'development_payload_sha256':canonical_sha(payload),'confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY',**binding_payload()}
    if seal_path is not None: atomic_write_new(seal_path,seal)
    return {**common,'status':'DEVELOPMENT_SELECTION_PASS','a4_gate_pass':True,'a5_gate_pass':True,'seal_sha256':canonical_sha(seal)}

def exact_binom_tail(k:int,n:int=20)->float:
    if not 0<=k<=n: raise ContractError('BINOM_RANGE')
    return sum(math.comb(n,j) for j in range(k,n+1))/(2**n)

def holm_two(p:Mapping[str,float])->dict[str,Any]:
    if set(p)!={'H4','H5'}: raise ContractError('HOLM_REQUIRES_H4_H5')
    order=sorted(p,key=lambda k:(float(p[k]),k)); first,second=order
    r1=float(p[first])<=0.025; r2=r1 and float(p[second])<=0.05
    return {'order':order,'thresholds':{first:0.025,second:0.05},'reject':{first:r1,second:r2},'all_reject':r1 and r2}

def evaluate_confirmation(payload:Mapping[str,Any],seal:Mapping[str,Any],seal_sha256:str)->dict[str,Any]:
    if payload.get('phase')!='ACTION_MATCHED_GROUNDED_V2_CONFIRMATION': raise ContractError('WRONG_CONFIRMATION_PHASE')
    for flag in ('reserve_accessed','valid_seen_accessed','valid_unseen_accessed'):
        if payload.get(flag) is not False: raise ContractError(f'CONFIRMATION_ISOLATION:{flag}')
    _check_binding(payload); _check_binding(seal)
    if canonical_sha(seal)!=seal_sha256 or payload.get('development_seal_sha256')!=seal_sha256: raise ContractError('SEAL_HASH_MISMATCH')
    if seal.get('status')!='DEVELOPMENT_SELECTION_PASS': raise ContractError('DEVELOPMENT_NOT_PASSED')
    if int(payload.get('selected_layer',-1))!=int(seal['selected_layer']) or float(payload.get('selected_alpha',-9))!=float(seal['selected_alpha']): raise ContractError('OPERATING_POINT_RETUNED')
    rows=payload.get('families')
    if not isinstance(rows,list): raise ContractError('CONFIRMATION_ROWS_MISSING')
    eligible=[r for r in rows if bool(r.get('eligible'))]
    if len(eligible)<20:
        return {'kind':'ACTION_MATCHED_GROUNDED_V2_CONFIRMATION_RESULT_V1','status':'INCONCLUSIVE_CONFIRMATION_CONSTRUCTIBILITY','eligible_count':len(eligible),'scientific_result':'NOT_ASSESSED','strong_semantic_plan_support':False,**binding_payload()}
    if len(rows)!=20 or len(eligible)!=20: raise ContractError('CONFIRMATION_MUST_BE_FIRST20_ELIGIBLE_ONLY')
    a4=[a4_components(r['a4_margins']) for r in rows]; a5=[a5_components(r['a5_margins']) for r in rows]
    k4=sum(x['joint_semantic_plan_margin']>0 for x in a4); k5=sum(x['joint_semantic_plan_continuation5']>0 for x in a5)
    p={'H4':exact_binom_tail(k4),'H5':exact_binom_tail(k5)}; holm=holm_two(p)
    med4=median(x['joint_semantic_plan_margin'] for x in a4); bid4=median(x['bidirectional'] for x in a4)
    med5=median(x['joint_semantic_plan_continuation5'] for x in a5); bid5=median(x['bidirectional5'] for x in a5)
    h4=holm['reject']['H4'] and k4>=15 and med4>=0.05 and bid4>=0.05
    h5=holm['reject']['H5'] and k5>=15 and med5>=0.05 and bid5>=0.05
    supported=bool(h4 and h5)
    # Frozen secondary scope is descriptive only: remove exactly the
    # FUTURE_ACTION_SEQUENCE_ONLY nuisance and reuse the same predeclared
    # effect-size guards. It cannot rescue H4/H5 or receive a Holm/sign-test
    # scientific-support label. If these guards pass while strong semantics
    # fail, the only additional nuisance is future-action-sequence identity.
    fs4=[x['joint_future_state_margin'] for x in a4]; fs5=[x['joint_future_state_continuation5'] for x in a5]
    kfs4=sum(x>0 for x in fs4); kfs5=sum(x>0 for x in fs5)
    medfs4=median(fs4); medfs5=median(fs5)
    future_state_a4=(kfs4>=15 and medfs4>=0.05 and bid4>=0.05)
    future_state_a5=(kfs5>=15 and medfs5>=0.05 and bid5>=0.05)
    narrowed=bool((not supported) and future_state_a4 and future_state_a5)
    if supported:
        status='SUPPORTED_ACTION_MATCHED_GROUNDED_V2_SEMANTIC_PLAN_CARRIER'
    elif narrowed:
        status='NARROWED_FUTURE_ACTION_SEQUENCE_CARRIER_DESCRIPTIVE_ONLY'
    else:
        status='NOT_SUPPORTED_ACTION_MATCHED_GROUNDED_V2_SEMANTIC_PLAN_CARRIER'
    return {'kind':'ACTION_MATCHED_GROUNDED_V2_CONFIRMATION_RESULT_V1','status':status,'eligible_count':20,'denominator':20,'positive_counts':{'H4':k4,'H5':k5},'p_values':p,'holm':holm,'medians':{'joint_semantic_plan_margin':med4,'bidirectional':bid4,'joint_semantic_plan_continuation5':med5,'bidirectional5':bid5},'co_primary_pass':{'H4':h4,'H5':h5},'strong_semantic_plan_support':supported,'secondary_future_action_sequence_scope':{'descriptive_only':True,'positive_counts':{'A4_future_state':kfs4,'A5_future_state':kfs5},'medians':{'joint_future_state_margin':medfs4,'joint_future_state_continuation5':medfs5},'effect_guards_pass':{'A4':future_state_a4,'A5':future_state_a5},'narrowed_future_action_sequence_carrier':narrowed,'cannot_rescue_or_relabel_strong_semantic_support':True},'narrow_future_action_sequence_scope_cannot_rescue':True,'selected_layer':int(seal['selected_layer']),'selected_alpha':float(seal['selected_alpha']),'scientific_result':'ASSESSED_CONFIRMATION_ONLY','per_family':[{'index':int(r['index']),**x,**y} for r,x,y in zip(rows,a4,a5)],**binding_payload()}

def atomic_write_new(path:str|Path,obj:Any)->str:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists(): raise ContractError(f'REFUSE_EXISTING:{p}')
    raw=(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode(); tmp=p.with_name('.'+p.name+'.tmp')
    if tmp.exists(): raise ContractError(f'REFUSE_STALE_TEMP:{tmp}')
    with open(tmp,'xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    os.rename(tmp,p); d=os.open(p.parent,os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)
    return hashlib.sha256(raw).hexdigest()
