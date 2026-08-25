#!/usr/bin/env python3
"""Frozen pure-Python statistics/selection for ActionMatched FuturePlan v1.
No model/environment access. All formulas mirror prereg SHA c8b89e51....
"""
from __future__ import annotations
import hashlib, json, math, os
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

PREREG_SHA256='c8b89e5132cf2c66c2a357dc4d49f4d94de2a486a0ecc8939816188ab3b93207'
POPULATION_SHA256='b4225a3818b1fa757a492670317481081b173192f9129b61cf8370ad52d32bc7'
SERIALIZATION_AUDIT_SHA256='f2f0762b9cab14256e3bf766d6603423c6b0e0d8e9b65fb6ea63057782a9ddc2'
REVIEW_SHA256='64f7d4b62917489c4d96f970ea23301a4b01a2a4ccecd440a97a2c781fadc47f'
STATIC_AUDIT_SHA256='a44912893db2e30a118f95c5a7a700b601ecee370dd5c8bc553e0ea216c6cf33'
DESIGN_TEST_SHA256='8dcc1403924c5e9be8b91bb1cddc4e6a1deef6fed2388e1dafd1f8d04b07952b'
DERANGEMENT_HELPER_SHA256='c93bc0b76110a88eb54dfc0b0d2ea63f13b515140b68e927c12da2f495ec0367'
RANDOM_CONTROL_REPAIR_SHA256='1247f7a3696408fa5a0d5f5ccab3f42621cf709ebf7204e64bb293cf62662772'
RANDOM_SOURCE_SHA256='7768a45cd41048ebcabd27a0be6602b41642fa95f425883e199a94c3c2291592'
DERANGEMENT_REVIEW_SHA256='790aa1d0700b5bc3a77d748aaa7ee6e29407fea0d685639586b578696437fb42'
AUTHORITY_COMMIT='d564dca2e2e335e30862262b7e50f12498d30ce8'
REVIEW_COMMIT='d3105205c88f114b854ccb414897e39565f6d055'
LAYERS=(7,14,21,27); ALPHAS=(0.25,0.5,1.0)
SEMANTIC=('UNRELATED_PAIR_RESIDUAL','ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY')
RANDOM='RANDOM_EQ_NORM'; ACTIVE='ACTIVE'; NO_PATCH='NO_PATCH'

class ContractError(RuntimeError): pass

def canonical_sha(obj:Any)->str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def sha_file(path:str|Path)->str:
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def binding_payload()->dict[str,str]:
    return {'authority_commit':AUTHORITY_COMMIT,'review_commit':REVIEW_COMMIT,'prereg_sha256':PREREG_SHA256,'static_audit_sha256':STATIC_AUDIT_SHA256,'population_sha256':POPULATION_SHA256,'serialization_audit_sha256':SERIALIZATION_AUDIT_SHA256,'design_test_sha256':DESIGN_TEST_SHA256,'derangement_helper_sha256':DERANGEMENT_HELPER_SHA256,'derangement_review_sha256':DERANGEMENT_REVIEW_SHA256,'random_control_repair_sha256':RANDOM_CONTROL_REPAIR_SHA256,'random_source_sha256':RANDOM_SOURCE_SHA256,'independent_review_sha256':REVIEW_SHA256}

def grid_key(layer:int,alpha:float)->str: return f'L{int(layer)}_A{float(alpha):g}'

def _finite(x:Any,label:str)->float:
    y=float(x)
    if not math.isfinite(y): raise ContractError(f'NONFINITE:{label}')
    return y

def _signpair(row:Mapping[str,Any],arm:str)->tuple[float,float]:
    x=row.get(arm)
    if not isinstance(x,Mapping) or '+' not in x or '-' not in x: raise ContractError(f'MISSING_BOTH_SIGNS:{arm}')
    return _finite(x['+'],arm+'+'),_finite(x['-'],arm+'-')

def a4_components(margins:Mapping[str,Any])->dict[str,float]:
    m0=_finite(margins[NO_PATCH],'m0'); ap,am=_signpair(margins,ACTIVE)
    forward=ap-m0; reverse=m0-am; bidi=min(forward,reverse)
    rp,rm=_signpair(margins,RANDOM); random_half=abs(rp-rm)/2.0
    nuis={}
    for arm in SEMANTIC:
        p,n=_signpair(margins,arm); nuis[arm]=max(abs(p-m0),abs(n-m0))
    max_n=max([random_half,*nuis.values()])
    return {'forward':forward,'reverse':reverse,'bidirectional':bidi,'active_swap_span':abs(ap-am)/2.0,
            'random_halfspan':random_half,'unrelated_shift':nuis['UNRELATED_PAIR_RESIDUAL'],
            'action_history_shift':nuis['ACTION_HISTORY_MATCHED_NULL'],'deranged_shift':nuis['FUTURE_TOKEN_DERANGED'],
            'next_divergent_action_only_shift':nuis['NEXT_DIVERGENT_ACTION_ONLY'],'max_nuisance':max_n,
            'joint_future_margin':bidi-max_n}

def _branch_signs(row:Mapping[str,Any],arm:str)->tuple[float,float,float,float]:
    x=row.get(arm)
    if not isinstance(x,Mapping) or '+' not in x or '-' not in x: raise ContractError(f'MISSING_BOTH_SIGNS_A5:{arm}')
    p=x['+']; n=x['-']
    if not isinstance(p,Mapping) or not isinstance(n,Mapping) or not all(k in p and k in n for k in ('A','B')): raise ContractError(f'MISSING_BRANCH_MARGINS:{arm}')
    return _finite(p['A'],arm+'+A'),_finite(n['A'],arm+'-A'),_finite(p['B'],arm+'+B'),_finite(n['B'],arm+'-B')

def a5_components(margins:Mapping[str,Any])->dict[str,float]:
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
    max_n=max([random5,*nuis.values()])
    return {'forward5':forward,'reverse5':reverse,'bidirectional5':bidi,'random5':random5,
            'unrelated5':nuis['UNRELATED_PAIR_RESIDUAL'],'action_history5':nuis['ACTION_HISTORY_MATCHED_NULL'],
            'deranged5':nuis['FUTURE_TOKEN_DERANGED'],'next_divergent_action_only5':nuis['NEXT_DIVERGENT_ACTION_ONLY'],
            'max_nuisance5':max_n,'joint_continuation5':bidi-max_n}

def aggregate_point(rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
    if len(rows)!=20: raise ContractError(f'DEVELOPMENT_DENOMINATOR_MUST_BE_20:{len(rows)}')
    a4=[a4_components(r['a4_margins']) for r in rows]
    a5=[a5_components(r['a5_margins']) for r in rows]
    return {'n':20,'median_joint_future_margin':median(x['joint_future_margin'] for x in a4),
            'median_bidirectional':median(x['bidirectional'] for x in a4),
            'median_active_swap_span':median(x['active_swap_span'] for x in a4),
            'positive_bidirectional':sum(x['bidirectional']>0 for x in a4),
            'median_joint_continuation5':median(x['joint_continuation5'] for x in a5),
            'median_bidirectional5':median(x['bidirectional5'] for x in a5),
            'positive_joint_continuation5':sum(x['joint_continuation5']>0 for x in a5),
            'per_family':[{'index':int(r['index']),**x,**y} for r,x,y in zip(rows,a4,a5)]}

def select_development(payload:Mapping[str,Any],seal_path:str|Path|None=None)->dict[str,Any]:
    if payload.get('phase')!='ACTION_MATCHED_FUTURE_PLAN_DEVELOPMENT': raise ContractError('WRONG_DEVELOPMENT_PHASE')
    if payload.get('confirmation_accessed') is not False or payload.get('reserve_accessed') is not False or payload.get('valid_seen_accessed') is not False or payload.get('valid_unseen_accessed') is not False: raise ContractError('DEVELOPMENT_SPLIT_ISOLATION')
    for k,v in binding_payload().items():
        if payload.get(k)!=v: raise ContractError(f'BINDING_DRIFT:{k}')
    eligible=payload.get('eligible_indices')
    if not isinstance(eligible,list): raise ContractError('ELIGIBLE_INDICES_MISSING')
    if len(eligible)<20:
        if payload.get('grid_results') not in ({},None): raise ContractError('GRID_FORBIDDEN_BELOW_20')
        return {'kind':'ACTION_MATCHED_FUTURE_PLAN_DEVELOPMENT_TERMINAL_V1','status':'INCONCLUSIVE_ACTION_MATCHED_PAIR_CONSTRUCTIBILITY','eligible_count':len(eligible),'confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY',**binding_payload()}
    if len(eligible)!=20: raise ContractError('EXACTLY_FIRST20_ELIGIBLE_REQUIRED')
    grids=payload.get('grid_results'); aggs={}
    if not isinstance(grids,Mapping): raise ContractError('GRID_RESULTS_MISSING')
    for layer in LAYERS:
        for alpha in ALPHAS:
            k=grid_key(layer,alpha)
            rows=grids.get(k)
            if not isinstance(rows,list): raise ContractError(f'MISSING_GRID:{k}')
            if [int(r['index']) for r in rows] != [int(x) for x in eligible]: raise ContractError(f'GRID_DENOMINATOR_DRIFT:{k}')
            aggs[k]=aggregate_point(rows)
    selected_key=sorted(aggs,key=lambda k:(-aggs[k]['median_joint_future_margin'],-aggs[k]['median_bidirectional'],-aggs[k]['median_active_swap_span'],float(k.split('_A')[1]),int(k[1:].split('_A')[0])))[0]
    sel=aggs[selected_key]; layer=int(selected_key[1:].split('_A')[0]); alpha=float(selected_key.split('_A')[1])
    pass_a4=sel['median_joint_future_margin']>=0.05 and sel['median_bidirectional']>=0.05 and sel['positive_bidirectional']>=15
    pass_a5=sel['median_joint_continuation5']>=0.05 and sel['median_bidirectional5']>=0.05 and sel['positive_joint_continuation5']>=15
    common={'kind':'ACTION_MATCHED_FUTURE_PLAN_DEVELOPMENT_TERMINAL_V1','eligible_count':20,'selected_layer':layer,'selected_alpha':alpha,'selected_grid_key':selected_key,'all_grid_aggregates':aggs,'confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY',**binding_payload()}
    if not (pass_a4 and pass_a5): return {**common,'status':'DEVELOPMENT_FUTILITY_STOP','a4_gate_pass':pass_a4,'a5_gate_pass':pass_a5}
    seal={'kind':'ACTION_MATCHED_FUTURE_PLAN_DEVELOPMENT_SELECTION_V1','status':'DEVELOPMENT_SELECTION_PASS','selected_layer':layer,'selected_alpha':alpha,'selected_grid_key':selected_key,'eligible_indices':[int(x) for x in eligible],'all_grid_aggregates':aggs,'development_payload_sha256':canonical_sha(payload),'confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY',**binding_payload()}
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
    if payload.get('phase')!='ACTION_MATCHED_FUTURE_PLAN_CONFIRMATION': raise ContractError('WRONG_CONFIRMATION_PHASE')
    for flag in ('reserve_accessed','valid_seen_accessed','valid_unseen_accessed'):
        if payload.get(flag) is not False: raise ContractError(f'CONFIRMATION_ISOLATION:{flag}')
    for k,v in binding_payload().items():
        if payload.get(k)!=v or seal.get(k)!=v: raise ContractError(f'BINDING_DRIFT:{k}')
    if canonical_sha(seal)!=seal_sha256 or payload.get('development_seal_sha256')!=seal_sha256: raise ContractError('SEAL_HASH_MISMATCH')
    if seal.get('status')!='DEVELOPMENT_SELECTION_PASS': raise ContractError('DEVELOPMENT_NOT_PASSED')
    if int(payload.get('selected_layer',-1))!=int(seal['selected_layer']) or float(payload.get('selected_alpha',-9))!=float(seal['selected_alpha']): raise ContractError('OPERATING_POINT_RETUNED')
    rows=payload.get('families')
    if not isinstance(rows,list): raise ContractError('CONFIRMATION_ROWS_MISSING')
    eligible=[r for r in rows if bool(r.get('eligible'))]
    if len(eligible)<20: return {'kind':'ACTION_MATCHED_FUTURE_PLAN_CONFIRMATION_RESULT_V1','status':'INCONCLUSIVE_CONFIRMATION_CONSTRUCTIBILITY','eligible_count':len(eligible),'scientific_result':'NOT_ASSESSED',**binding_payload()}
    if len(eligible)!=20 or len(rows)!=20: raise ContractError('CONFIRMATION_MUST_BE_FIRST20_ELIGIBLE_ONLY')
    a4=[a4_components(r['a4_margins']) for r in rows]; a5=[a5_components(r['a5_margins']) for r in rows]
    k4=sum(x['joint_future_margin']>0 for x in a4); k5=sum(x['joint_continuation5']>0 for x in a5)
    p={'H4':exact_binom_tail(k4),'H5':exact_binom_tail(k5)}; holm=holm_two(p)
    med4=median(x['joint_future_margin'] for x in a4); bid4=median(x['bidirectional'] for x in a4)
    med5=median(x['joint_continuation5'] for x in a5); bid5=median(x['bidirectional5'] for x in a5)
    h4=holm['reject']['H4'] and k4>=15 and med4>=0.05 and bid4>=0.05
    h5=holm['reject']['H5'] and k5>=15 and med5>=0.05 and bid5>=0.05
    status='SUPPORTED_ACTION_MATCHED_MULTI_STEP_FUTURE_PLAN_CARRIER' if h4 and h5 else 'REFUTED_ACTION_MATCHED_MULTI_STEP_FUTURE_PLAN_CARRIER'
    return {'kind':'ACTION_MATCHED_FUTURE_PLAN_CONFIRMATION_RESULT_V1','status':status,'eligible_count':20,'denominator':20,'positive_counts':{'H4':k4,'H5':k5},'p_values':p,'holm':holm,'medians':{'joint_future_margin':med4,'bidirectional':bid4,'joint_continuation5':med5,'bidirectional5':bid5},'co_primary_pass':{'H4':h4,'H5':h5},'selected_layer':int(seal['selected_layer']),'selected_alpha':float(seal['selected_alpha']),'scientific_result':'ASSESSED_CONFIRMATION_ONLY','per_family':[{'index':int(r['index']),**x,**y} for r,x,y in zip(rows,a4,a5)],**binding_payload()}

def atomic_write_new(path:str|Path,obj:Any)->str:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists(): raise ContractError(f'REFUSE_EXISTING:{p}')
    raw=(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode(); tmp=p.with_name('.'+p.name+'.tmp')
    if tmp.exists(): raise ContractError(f'REFUSE_STALE_TEMP:{tmp}')
    with open(tmp,'xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    os.rename(tmp,p)
    d=os.open(p.parent,os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)
    return hashlib.sha256(raw).hexdigest()
