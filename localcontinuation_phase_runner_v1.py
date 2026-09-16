#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, math, os, statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

FINAL_PREREG_SHA256='a6972b33caaf7f2b7b28af248acd528a540e077bfdb59283f5f288de5e297ec8'
FINAL_REVIEW_SHA256='c9c89ebe87980e2169d8534b43d6955b477cd94d5ea14c70604c8af5b6a1c1b6'
POPULATION_SHA256='adba81b7073707ef01589fbd022106e678f8542182f780f6f789ef1a47dff543'
POPULATION_REVIEW_SHA256='bd730ea81e7bfea75fa7eb79e357505c794e6300c5ad53500bffe092947c82b0'
LAYERS=(7,14,21,27); ALPHAS=(0.25,0.5,1.0)
DEV=tuple(range(32)); CONF=tuple(range(32,52)); RESERVE=tuple(range(52,64))
ACTIVE='ACTIVE_PLAN_RESIDUAL'; NO_PATCH='NO_PATCH'
SPEC=('RANDOM_EQ_NORM','NEXT_ACTION_PRESERVED_LATE_NULL','UNRELATED_PLAN','SHUFFLED_PLAN','GENERIC_HISTORY')
ALL_ARMS=(ACTIVE,NO_PATCH,'ZERO_ADD','SELF_REPLACE','RANDOM_EQ_NORM','NEXT_ACTION_PRESERVED_LATE_NULL','UNRELATED_PLAN','SHUFFLED_PLAN','GENERIC_HISTORY','VISIBLE_TEXT_PLAN')
EQ_ATOL=1e-6

class LocalContinuationContractError(RuntimeError):
    pass

def canonical_json_bytes(obj:Any)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha_json(obj:Any)->str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()
def file_sha(path:str|Path)->str:
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def mean(xs:Sequence[float])->float:
    if not xs: raise LocalContinuationContractError('empty mean')
    return float(sum(float(x) for x in xs)/len(xs))
def grid_key(layer:int,alpha:float)->str:
    return f'{int(layer)}:{float(alpha):g}'
def _finite01(v:Any,name:str)->float:
    x=float(v)
    if not math.isfinite(x) or x<0.0 or x>1.0: raise LocalContinuationContractError(f'{name} outside [0,1]')
    return x
def _lca(v:Any,name:str)->float:
    x=float(v)
    if x not in (0.0,0.5,1.0): raise LocalContinuationContractError(f'{name} outside exact LCA2 support')
    return x
def _hex64(value:Any)->bool:
    v=str(value)
    return len(v)==64 and all(c in '0123456789abcdef' for c in v)

def exact_one_sided_sign_p(positives:int,n:int)->float:
    positives=int(positives); n=int(n)
    if n<=0 or positives<0 or positives>n: raise LocalContinuationContractError('invalid sign count')
    return float(sum(math.comb(n,k) for k in range(positives,n+1))/(2**n))
def holm_two(p_by_name:Mapping[str,float])->dict[str,Any]:
    if set(p_by_name)!={'d_no_patch','d_specificity'}: raise LocalContinuationContractError('wrong Holm family')
    rows=sorted((float(p),str(n)) for n,p in p_by_name.items())
    p1,n1=rows[0]; p2,n2=rows[1]; a=p1<=.025; b=a and p2<=.05; d={n1:a,n2:b}
    return {'fwer':.05,'ordered':[[n1,p1,.025],[n2,p2,.05]],'decisions':d,'both_pass':all(d.values())}

def atomic_write_new(path:str|Path,obj:Any)->str:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists(): raise LocalContinuationContractError(f'refuse existing output:{p}')
    raw=json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False).encode()+b'\n'
    tmp=p.with_name(f'.{p.name}.tmp.{os.getpid()}.{hashlib.sha256(raw).hexdigest()[:12]}')
    with open(tmp,'xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    try: os.link(tmp,p)
    except FileExistsError as e: raise LocalContinuationContractError(f'refuse existing output:{p}') from e
    finally:
        try: tmp.unlink()
        except FileNotFoundError: pass
    dfd=os.open(p.parent,os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return hashlib.sha256(raw).hexdigest()

def _check_bindings(payload:Mapping[str,Any])->None:
    req={'final_prereg_sha256':FINAL_PREREG_SHA256,'final_review_sha256':FINAL_REVIEW_SHA256,'population_manifest_sha256':POPULATION_SHA256,'population_review_sha256':POPULATION_REVIEW_SHA256}
    for k,v in req.items():
        if payload.get(k)!=v: raise LocalContinuationContractError(f'binding mismatch:{k}')
def _family_map(payload:Mapping[str,Any],indices:Sequence[int])->dict[int,Mapping[str,Any]]:
    out={}
    for row in payload.get('families',[]):
        i=int(row.get('index',-1))
        if i in out: raise LocalContinuationContractError(f'duplicate family:{i}')
        out[i]=row
    if set(out)!=set(indices): raise LocalContinuationContractError(f'family index mismatch:{sorted(out)}')
    return out

def _validate_seal_mapping(seal:Mapping[str,Any])->None:
    if seal.get('kind')!='PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_SELECTION_V1' or seal.get('status')!='FROZEN_LOCALCONTINUATION_DEVELOPMENT_SELECTION': raise LocalContinuationContractError('invalid development seal')
    _check_bindings(seal)
    if seal.get('confirmation_accessed') is not False: raise LocalContinuationContractError('seal must predate confirmation access')
    if list(seal.get('development_indices',[]))!=list(DEV): raise LocalContinuationContractError('seal development indices mismatch')
    if int(seal.get('qualified_count',-1))<16: raise LocalContinuationContractError('seal qualified count below development gate')
    if int(seal.get('selected_layer',-1)) not in LAYERS or float(seal.get('selected_alpha',-1)) not in ALPHAS: raise LocalContinuationContractError('seal operating point outside frozen grid')
    ep=seal.get('execution_provenance')
    if not isinstance(ep,dict): raise LocalContinuationContractError('seal execution provenance missing')
    if seal.get('execution_provenance_sha256')!=sha_json(ep): raise LocalContinuationContractError('seal execution provenance hash mismatch')
    if not _hex64(seal.get('selected_point_family_provenance_sha256')): raise LocalContinuationContractError('seal selected-point provenance hash invalid')
    if not _hex64(seal.get('development_payload_sha256')): raise LocalContinuationContractError('seal development payload hash invalid')
def load_seal(path:str|Path,expected_sha256:str|None=None)->tuple[dict[str,Any],str]:
    p=Path(path)
    if not p.is_file(): raise LocalContinuationContractError('development seal missing')
    got=file_sha(p)
    if expected_sha256 is not None and got!=expected_sha256: raise LocalContinuationContractError(f'development seal hash mismatch:{got}:{expected_sha256}')
    seal=json.loads(p.read_text())
    _validate_seal_mapping(seal)
    return seal,got

def reference_action_margin(scores:Mapping[str,float],reference_action:str)->float:
    vals={str(k):float(v) for k,v in scores.items()}; ref=str(reference_action)
    if ref not in vals: raise LocalContinuationContractError('reference action absent from scores')
    if not all(math.isfinite(v) for v in vals.values()): raise LocalContinuationContractError('nonfinite candidate score')
    others=[v for k,v in vals.items() if k!=ref]
    if not others: raise LocalContinuationContractError('TECHNICAL_INVALID_MARGIN_UNDEFINED')
    return vals[ref]-max(others)
def top1_command(scores:Mapping[str,float])->str:
    if not scores: raise LocalContinuationContractError('empty scores')
    vals={str(k):float(v) for k,v in scores.items()}
    if not all(math.isfinite(float(v)) for v in vals.values()): raise LocalContinuationContractError('nonfinite score')
    return sorted(vals,key=lambda c:(-vals[c],c))[0]
def matched_state_msa2(rows:Sequence[Mapping[str,Any]])->tuple[float,float]:
    if len(rows)!=2: raise LocalContinuationContractError('MSA2 requires exactly positions4,5')
    ind=[]; marg=[]
    for r in rows:
        if r.get('state_match') is not True or r.get('admissible_match') is not True: raise LocalContinuationContractError('matched-state guard fail')
        scores={str(k):float(v) for k,v in r.get('scores',{}).items()}; ref=str(r.get('reference_action',''))
        ind.append(1.0 if top1_command(scores)==ref else 0.0); marg.append(reference_action_margin(scores,ref))
    return mean(ind),mean(marg)
def local_continuation_lca2(reference_actions:Sequence[Mapping[str,Any]],generated_actions:Sequence[Mapping[str,Any]])->float:
    if len(reference_actions)<5: raise LocalContinuationContractError('reference requires five actions')
    score=0.0
    for gpos,rpos in ((1,3),(2,4)):
        if gpos>=len(generated_actions): continue
        g=generated_actions[gpos]; r=reference_actions[rpos]
        if str(g.get('command'))==str(r.get('command')) and str(g.get('pre_state_hash'))==str(r.get('pre_state_hash')): score+=.5
    return score

def _validate_arm_provenance(arm_name:str,arm:Mapping[str,Any],layer:int,alpha:float,active_sha256:str,reset_snapshot_sha256:str)->None:
    if str(arm.get('arm_name'))!=str(arm_name): raise LocalContinuationContractError(f'arm provenance name mismatch:{arm_name}')
    if int(arm.get('selected_layer',-1))!=int(layer) or float(arm.get('selected_alpha',-9))!=float(alpha): raise LocalContinuationContractError(f'arm provenance operating point mismatch:{arm_name}')
    if str(arm.get('active_residual_sha256'))!=str(active_sha256) or not _hex64(active_sha256): raise LocalContinuationContractError(f'arm active residual hash mismatch:{arm_name}')
    if not _hex64(reset_snapshot_sha256): raise LocalContinuationContractError(f'family reset snapshot invalid:{arm_name}')
    if arm_name=='VISIBLE_TEXT_PLAN':
        if str(arm.get('external_reset_snapshot_sha256'))!=str(reset_snapshot_sha256): raise LocalContinuationContractError('visible-plan external reset snapshot mismatch')
        if not _hex64(arm.get('reset_snapshot_sha256')) or not _hex64(arm.get('visible_plan_slot_token_ids_sha256')): raise LocalContinuationContractError('visible-plan provenance missing')
    elif str(arm.get('reset_snapshot_sha256'))!=str(reset_snapshot_sha256): raise LocalContinuationContractError(f'arm reset snapshot mismatch:{arm_name}')
    if not _hex64(arm.get('reset_prefix_sha256')) or not _hex64(arm.get('session_id_hash')): raise LocalContinuationContractError(f'arm session provenance missing:{arm_name}')
    hook=int(arm.get('hook_count',-1)); expected=0 if arm_name in (NO_PATCH,'VISIBLE_TEXT_PLAN') else 1
    if hook!=expected: raise LocalContinuationContractError(f'arm hook count mismatch:{arm_name}:{hook}:{expected}')
    injected=arm.get('injected_vector_sha256')
    if expected==0:
        if injected is not None: raise LocalContinuationContractError(f'arm unexpected injected vector:{arm_name}')
    elif not _hex64(injected): raise LocalContinuationContractError(f'arm injected vector hash invalid:{arm_name}')

def select_development(payload:Mapping[str,Any],seal_path:str|Path|None=None)->dict[str,Any]:
    if payload.get('phase')!='LOCALCONTINUATION_DEVELOPMENT': raise LocalContinuationContractError('wrong phase')
    if payload.get('confirmation_accessed') is not False or payload.get('reserve_accessed') is not False: raise LocalContinuationContractError('development population isolation violated')
    _check_bindings(payload)
    execution_provenance=payload.get('execution_provenance')
    if not isinstance(execution_provenance,dict) or payload.get('execution_provenance_sha256')!=sha_json(execution_provenance): raise LocalContinuationContractError('development execution provenance missing or corrupt')
    fams=_family_map(payload,DEV); qualified=[i for i in DEV if bool(fams[i].get('qualified'))]
    if len(qualified)<16:
        if payload.get('grid_results') not in ({},None): raise LocalContinuationContractError('causal grid forbidden below development gate')
        return {'kind':'PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_V1','status':'INCONCLUSIVE_LOCALCONTINUATION_DEVELOPMENT_EXPRESSIVITY','qualified_count':len(qualified),'denominator':32,'confirmation_accessed':False}
    grids=payload.get('grid_results',{}); expected={grid_key(l,a) for l in LAYERS for a in ALPHAS}
    if set(grids)!=expected: raise LocalContinuationContractError('grid key mismatch')
    aggs={}
    for l in LAYERS:
        for a in ALPHAS:
            key=grid_key(l,a); rows=grids[key]
            if {int(x) for x in rows}!=set(qualified): raise LocalContinuationContractError(f'grid denominator mismatch:{key}')
            joint=[]; am=[]; rm=[]; zero_raw=0
            for i in qualified:
                row=rows[str(i)]; arms=row.get('arms',{})
                if not all(x in arms for x in (ACTIVE,NO_PATCH,*SPEC)): raise LocalContinuationContractError(f'missing arms:{i}:{key}')
                active_sha=str(row.get('active_residual_sha256','')); reset_sha=str(row.get('reset_snapshot_sha256',''))
                for arm_name in (ACTIVE,NO_PATCH,*SPEC): _validate_arm_provenance(arm_name,arms[arm_name],l,a,active_sha,reset_sha)
                vals={x:float(arms[x]['msa2']) for x in (ACTIVE,NO_PATCH,*SPEC)}
                if any(v not in (0.0,0.5,1.0) for v in vals.values()): raise LocalContinuationContractError('MSA2 exact support violation')
                av=vals[ACTIVE]; np=vals[NO_PATCH]; sp=max(vals[c] for c in SPEC)
                m=float(arms[ACTIVE].get('reference_action_margin_family'))
                if not math.isfinite(m): raise LocalContinuationContractError('nonfinite ACTIVE margin')
                raw=float(row.get('active_raw_residual_l2',float('nan')))
                if not math.isfinite(raw) or raw<0: raise LocalContinuationContractError('invalid active raw residual norm')
                j=min(av-np,av-sp)
                if raw<=1e-8: j=min(0.0,j); zero_raw+=1
                joint.append(j); am.append(av); rm.append(m)
            aggs[key]={'layer':l,'alpha':a,'qualified_count':len(qualified),'zero_raw_residual_count':zero_raw,'median_joint_margin_ms':float(statistics.median(joint)),'median_active_msa2':float(statistics.median(am)),'mean_active_msa2':mean(am),'median_active_reference_action_margin_family':float(statistics.median(rm))}
    selected=sorted(aggs.values(),key=lambda r:(-r['median_joint_margin_ms'],-r['median_active_msa2'],-r['median_active_reference_action_margin_family'],r['alpha'],r['layer']))[0]
    if selected['median_joint_margin_ms']<.05 or selected['mean_active_msa2']<.50:
        return {'kind':'PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_V1','status':'INCONCLUSIVE_LOCALCONTINUATION_DEVELOPMENT_FUTILITY','qualified_count':len(qualified),'denominator':32,'selected_candidate':selected,'all_grid_aggregates':aggs,'confirmation_accessed':False}
    selected_key=grid_key(selected['layer'],selected['alpha']); selected_rows=grids[selected_key]
    selected_point_provenance={}
    for i in qualified:
        row=selected_rows[str(i)]
        selected_point_provenance[str(i)]={'active_raw_residual_l2':float(row['active_raw_residual_l2']),'active_residual_sha256':str(row['active_residual_sha256']),'reset_snapshot_sha256':str(row['reset_snapshot_sha256']),'arms':{arm:{k:row['arms'][arm].get(k) for k in ('arm_name','selected_layer','selected_alpha','active_residual_sha256','injected_vector_sha256','reset_snapshot_sha256','reset_prefix_sha256','hook_count','session_id_hash')} for arm in (ACTIVE,NO_PATCH,*SPEC)}}
    seal={'kind':'PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_SELECTION_V1','status':'FROZEN_LOCALCONTINUATION_DEVELOPMENT_SELECTION','final_prereg_sha256':FINAL_PREREG_SHA256,'final_review_sha256':FINAL_REVIEW_SHA256,'population_manifest_sha256':POPULATION_SHA256,'population_review_sha256':POPULATION_REVIEW_SHA256,'development_indices':list(DEV),'qualified_indices':qualified,'qualified_count':len(qualified),'development_payload_sha256':sha_json(payload),'execution_provenance':execution_provenance,'execution_provenance_sha256':sha_json(execution_provenance),'selected_point_family_provenance_sha256':sha_json(selected_point_provenance),'selection_rule':'max median joint_margin_ms; tie median ACTIVE MSA2, median ACTIVE reference margin, lower alpha, earlier layer','selected_layer':int(selected['layer']),'selected_alpha':float(selected['alpha']),'selected_grid_key':selected_key,'all_grid_aggregates':aggs,'confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY'}
    out=dict(seal)
    if seal_path is not None: out['seal_file_sha256']=atomic_write_new(seal_path,seal)
    return out

def _per_family_confirmation(fam:Mapping[str,Any],layer:int,alpha:float)->dict[str,Any]:
    qualified=bool(fam.get('qualified'))
    if not qualified:
        return {'qualified':False,'active':0.0,'no_patch':0.0,'d_no_patch':0.0,'d_specificity':0.0,'valid_action_rate_available':False,'active_valid_action_rate':None,'no_patch_valid_action_rate':None,'zero_add_no_patch_maxabs':None,'self_replace_no_patch_maxabs':None,'active_task_success':None,'no_patch_task_success':None,'zero_raw_residual':False}
    arms=fam.get('arms',{})
    if not all(a in arms for a in ALL_ARMS): raise LocalContinuationContractError('confirmation missing arms')
    active_sha=str(fam.get('active_residual_sha256','')); reset_sha=str(fam.get('reset_snapshot_sha256',''))
    for arm_name in ALL_ARMS: _validate_arm_provenance(arm_name,arms[arm_name],layer,alpha,active_sha,reset_sha)
    lca={a:_lca(arms[a].get('lca2'),f'{a}.lca2') for a in ALL_ARMS}
    av=_finite01(arms[ACTIVE].get('valid_action_rate'),f'{ACTIVE}.valid_action_rate'); nv=_finite01(arms[NO_PATCH].get('valid_action_rate'),f'{NO_PATCH}.valid_action_rate')
    raw=float(fam.get('active_raw_residual_l2',float('nan')))
    if not math.isfinite(raw) or raw<0: raise LocalContinuationContractError('invalid active raw residual norm')
    no=lca[NO_PATCH]; spec=max(lca[c] for c in SPEC); actual_active=lca[ACTIVE]; zero_raw=raw<=1e-8
    active=0.0 if zero_raw else actual_active
    dno=min(0.0,active-no) if zero_raw else active-no
    dsp=min(0.0,active-spec) if zero_raw else active-spec
    z=float(fam.get('zero_add_no_patch_maxabs',float('nan'))); s=float(fam.get('self_replace_no_patch_maxabs',float('nan')))
    if not math.isfinite(z) or not math.isfinite(s) or z<0 or s<0: raise LocalContinuationContractError('invalid plumbing sentinel')
    ats=_finite01(arms[ACTIVE].get('task_success',0.0),f'{ACTIVE}.task_success'); nts=_finite01(arms[NO_PATCH].get('task_success',0.0),f'{NO_PATCH}.task_success')
    return {'qualified':True,'active':active,'actual_active_descriptive':actual_active,'no_patch':no,'d_no_patch':dno,'d_specificity':dsp,'valid_action_rate_available':True,'active_valid_action_rate':av,'no_patch_valid_action_rate':nv,'zero_add_no_patch_maxabs':z,'self_replace_no_patch_maxabs':s,'active_task_success':ats,'no_patch_task_success':nts,'zero_raw_residual':zero_raw}

def _evaluate_primary(payload:Mapping[str,Any],seal:Mapping[str,Any],seal_sha256:str,indices:Sequence[int],min_q:int,pos_req:int,supported:str,inconclusive:str,refuted:str)->dict[str,Any]:
    _check_bindings(payload); _validate_seal_mapping(seal); fams=_family_map(payload,indices)
    ep=payload.get('execution_provenance')
    if not isinstance(ep,dict) or payload.get('execution_provenance_sha256')!=sha_json(ep): raise LocalContinuationContractError('causal execution provenance missing or corrupt')
    if payload.get('execution_provenance_sha256')!=seal.get('execution_provenance_sha256'): raise LocalContinuationContractError('execution provenance differs from development seal')
    if int(payload.get('selected_layer',-1))!=int(seal['selected_layer']) or float(payload.get('selected_alpha',-9))!=float(seal['selected_alpha']): raise LocalContinuationContractError('op point retuned')
    if payload.get('development_seal_sha256')!=seal_sha256: raise LocalContinuationContractError('seal binding mismatch')
    q=sum(bool(fams[i].get('qualified')) for i in indices); n=len(indices)
    if q<min_q:
        return {'kind':'PLANCARRY_LOCALCONTINUATION_CAUSAL_V1','status':inconclusive,'qualified_count':q,'denominator':n,'selected_layer':seal['selected_layer'],'selected_alpha':seal['selected_alpha']}
    rows=[{'index':i,**_per_family_confirmation(fams[i],int(seal['selected_layer']),float(seal['selected_alpha']))} for i in indices]
    dno=[x['d_no_patch'] for x in rows]; dsp=[x['d_specificity'] for x in rows]; pno=sum(x>0 for x in dno); psp=sum(x>0 for x in dsp)
    pv={'d_no_patch':exact_one_sided_sign_p(pno,n),'d_specificity':exact_one_sided_sign_p(psp,n)}; holm=holm_two(pv)
    qrows=[x for x in rows if x['qualified']]
    msa_secondary=[]
    for i in indices:
        fam=fams[i]
        if not bool(fam.get('qualified')): continue
        ms=fam.get('matched_state_secondary')
        if not isinstance(ms,dict) or not all(a in ms for a in (ACTIVE,NO_PATCH,*SPEC)): raise LocalContinuationContractError('matched-state secondary missing')
        vals={a:_lca(ms[a].get('msa2'),f'matched_state_secondary.{a}.msa2') for a in (ACTIVE,NO_PATCH,*SPEC)}
        msa_secondary.append(vals)
    av=mean([x['active_valid_action_rate'] for x in qrows]); nv=mean([x['no_patch_valid_action_rate'] for x in qrows]); act=mean([x['active'] for x in rows])
    zmax=max(x['zero_add_no_patch_maxabs'] for x in qrows); smax=max(x['self_replace_no_patch_maxabs'] for x in qrows)
    guards={'mean_ACTIVE_LCA2_ge_0_50':act>=.50,'mean_d_no_patch_ge_0_15':mean(dno)>=.15,'mean_d_specificity_ge_0_10':mean(dsp)>=.10,'positive_d_no_patch_required':pno>=pos_req,'positive_d_specificity_required':psp>=pos_req,'ACTIVE_valid_action_rate_ge_0_95':av>=.95,'ACTIVE_valid_not_below_NO_PATCH_by_more_than_0_05':av>=nv-.05,'zero_add_no_patch_maxabs_le_1e_6':zmax<=EQ_ATOL,'self_replace_no_patch_maxabs_le_1e_6':smax<=EQ_ATOL}
    status=supported if holm['both_pass'] and all(guards.values()) else refuted
    return {'kind':'PLANCARRY_LOCALCONTINUATION_CAUSAL_V1','status':status,'denominator':n,'effect_denominator':n,'valid_action_rate_denominator':q,'qualified_count':q,'zero_raw_residual_count':sum(x['zero_raw_residual'] for x in qrows),'positive_counts':{'d_no_patch':pno,'d_specificity':psp},'p_values':pv,'holm':holm,'means':{'ACTIVE_LCA2':act,'d_no_patch':mean(dno),'d_specificity':mean(dsp)},'valid_action_rates':{'ACTIVE':av,'NO_PATCH':nv},'task_success_secondary_qualified':{'ACTIVE':mean([x['active_task_success'] for x in qrows]),'NO_PATCH':mean([x['no_patch_task_success'] for x in qrows])},'matched_state_MSA2_secondary_qualified':{a:mean([x[a] for x in msa_secondary]) for a in (ACTIVE,NO_PATCH,*SPEC)},'plumbing_maxabs':{'ZERO_ADD_vs_NO_PATCH':zmax,'SELF_REPLACE_vs_NO_PATCH':smax},'effect_guards':guards,'all_effect_guards_pass':all(guards.values()),'per_family':rows,'selected_layer':int(seal['selected_layer']),'selected_alpha':float(seal['selected_alpha']),'first_action_excluded':True,'world_state_match_required':True,'stage2_unqualified_primary_contribution':'ACTIVE_LCA2=0,d_no_patch=0,d_specificity=0,nonpositive_sign','zero_raw_primary_contribution':'ACTIVE_LCA2=0,d_no_patch<=0,d_specificity<=0,nonpositive_sign'}

def evaluate_confirmation(payload:Mapping[str,Any],seal:Mapping[str,Any],seal_sha256:str)->dict[str,Any]:
    if payload.get('phase')!='LOCALCONTINUATION_CONFIRMATION': raise LocalContinuationContractError('wrong confirmation phase')
    if payload.get('reserve_accessed') is not False or payload.get('valid_seen_accessed') is not False or payload.get('valid_unseen_accessed') is not False: raise LocalContinuationContractError('confirmation population isolation violated')
    return _evaluate_primary(payload,seal,seal_sha256,CONF,15,15,'SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1','INCONCLUSIVE_LOCALCONTINUATION_CONFIRMATION_EXPRESSIVITY','REFUTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1')
def evaluate_replication(payload:Mapping[str,Any],seal:Mapping[str,Any],seal_sha256:str,primary_status:str)->dict[str,Any]:
    if primary_status!='SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1': raise LocalContinuationContractError('reserve locked until primary support')
    if payload.get('phase')!='LOCALCONTINUATION_REPLICATION': raise LocalContinuationContractError('wrong replication phase')
    if payload.get('valid_seen_accessed') is not False or payload.get('valid_unseen_accessed') is not False: raise LocalContinuationContractError('replication population isolation violated')
    return _evaluate_primary(payload,seal,seal_sha256,RESERVE,10,10,'REPLICATED_REPLAYRESIDUAL_LOCALCONTINUATION_T1','INCONCLUSIVE_LOCALCONTINUATION_REPLICATION_EXPRESSIVITY','NOT_REPLICATED_REPLAYRESIDUAL_LOCALCONTINUATION_T1')
