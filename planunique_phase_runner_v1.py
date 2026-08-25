#!/usr/bin/env python3
from __future__ import annotations
import math, statistics
from pathlib import Path
from typing import Any, Mapping, Sequence
import localcontinuation_phase_runner_v1 as v1
import planunique_projection_v1 as proj

LAYERS=(14,21); ALPHAS=(0.5,1.0,2.0,4.0); DEV=tuple(range(32)); CONF=tuple(range(32,52))
ACTIVE=proj.ACTIVE; NO_PATCH=proj.NO_PATCH; SPEC=proj.SPEC; ALL=(ACTIVE,NO_PATCH,*SPEC)
ERR=v1.LocalContinuationContractError
sha_json=v1.sha_json; atomic_write_new=v1.atomic_write_new; mean=v1.mean; grid_key=v1.grid_key

def _finite(x:Any)->float:
    y=float(x)
    if not math.isfinite(y): raise ERR('NONFINITE')
    return y

def freeze_e_common(layer_constructible:Mapping[int,Sequence[int]])->list[int]:
    if set(int(k) for k in layer_constructible)!=set(LAYERS): raise ERR('LAYER_CONSTRUCTIBILITY_KEYS')
    sets=[set(int(i) for i in layer_constructible[l]) for l in LAYERS]
    for s in sets:
        if not s.issubset(set(DEV)): raise ERR('CONSTRUCTIBILITY_INDEX_OUTSIDE_DEV')
    return sorted(set.intersection(*sets))

def _row_deltas(row:Mapping[str,Any])->tuple[float,float,float,float,float]:
    arms=row['arms']
    if any(a not in arms for a in ALL): raise ERR('MISSING_ARM')
    av=_finite(arms[ACTIVE]['reference_action_margin_family']); np=_finite(arms[NO_PATCH]['reference_action_margin_family'])
    mx=max(_finite(arms[a]['reference_action_margin_family']) for a in SPEC)
    dnp=av-np; dsp=av-mx; joint=min(dnp,dsp)
    if bool(row.get('zero_unique',False)):
        dnp=min(dnp,0.0); dsp=min(dsp,0.0); joint=min(joint,0.0)
    amsa=_finite(arms[ACTIVE]['msa2']); nmsa=_finite(arms[NO_PATCH]['msa2'])
    return dnp,dsp,joint,amsa,nmsa

def select_development(payload:Mapping[str,Any],seal_path:str|Path|None=None)->dict[str,Any]:
    if payload.get('phase')!='PLANUNIQUE_DEVELOPMENT_V1_2': raise ERR('WRONG_PHASE')
    for f in ('confirmation_accessed','reserve_accessed','valid_seen_accessed','valid_unseen_accessed'):
        if payload.get(f) is not False: raise ERR(f'SPLIT_ISOLATION:{f}')
    e=[int(i) for i in payload.get('e_common_indices',[])]
    if e!=sorted(set(e)) or not set(e).issubset(set(DEV)): raise ERR('E_COMMON_INVALID')
    if len(e)<24:
        if payload.get('grid_results') not in ({},None): raise ERR('GRID_FORBIDDEN_BELOW_E_COMMON_GATE')
        return {'kind':'PLANCARRY_PLANUNIQUE_DEVELOPMENT_V1_2','status':'INCONCLUSIVE_PLANUNIQUE_COMMON_DENOMINATOR_CONSTRUCTIBILITY','e_common_count':len(e),'denominator':32,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY'}
    grids=payload.get('grid_results',{}); expected={grid_key(l,a) for l in LAYERS for a in ALPHAS}
    if set(grids)!=expected: raise ERR('GRID_KEY_MISMATCH')
    ag={}
    for l in LAYERS:
      for a in ALPHAS:
        key=grid_key(l,a); rows=grids[key]
        if {int(i) for i in rows}!=set(e): raise ERR(f'E_COMMON_DENOMINATOR_DRIFT:{key}')
        dnp=[]; dsp=[]; joint=[]; am=[]; nm=[]
        for i in e:
            x=_row_deltas(rows[str(i)]); dnp.append(x[0]);dsp.append(x[1]);joint.append(x[2]);am.append(x[3]);nm.append(x[4])
        ag[key]={'layer':l,'alpha':a,'denominator':len(e),'median_joint_margin_nats':float(statistics.median(joint)),
                 'positive_joint_fraction':sum(x>0 for x in joint)/len(joint),'median_d_no_patch':float(statistics.median(dnp)),
                 'mean_active_msa2':mean(am),'mean_no_patch_msa2':mean(nm)}
    selected=sorted(ag.values(),key=lambda r:(-r['median_joint_margin_nats'],-r['positive_joint_fraction'],-r['median_d_no_patch'],r['alpha'],r['layer']))[0]
    passed=(selected['median_joint_margin_nats']>=0.05 and selected['positive_joint_fraction']>=0.625 and selected['mean_active_msa2']>=selected['mean_no_patch_msa2']-0.05 and bool(payload.get('plumbing_sentinels_pass',False)))
    if not passed:
        return {'kind':'PLANCARRY_PLANUNIQUE_DEVELOPMENT_V1_2','status':'DEVELOPMENT_FUTILITY','e_common_count':len(e),'selected_candidate':selected,'all_grid_aggregates':ag,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY'}
    seal={'kind':'PLANCARRY_PLANUNIQUE_DEVELOPMENT_SELECTION_V1_2','status':'FROZEN_PLANUNIQUE_DEVELOPMENT_SELECTION','authority_commit':proj.AUTHORITY_COMMIT,'authority_review_sha256':proj.AUTHORITY_REVIEW_SHA256,'population_sha256':proj.POPULATION_SHA256,
          'e_common_indices':e,'e_common_count':len(e),'selected_layer':int(selected['layer']),'selected_alpha':float(selected['alpha']),'selected_grid_key':grid_key(selected['layer'],selected['alpha']),'all_grid_aggregates':ag,
          'selection_rule':'max median joint; tie higher positive fraction, higher median d_no_patch, lower alpha, earlier layer','development_payload_sha256':sha_json(payload),'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY'}
    out=dict(seal)
    if seal_path is not None: out['seal_file_sha256']=atomic_write_new(seal_path,seal)
    return out

def evaluate_confirmation(payload:Mapping[str,Any])->dict[str,Any]:
    if payload.get('phase')!='PLANUNIQUE_CONFIRMATION_V1_2': raise ERR('WRONG_CONFIRMATION_PHASE')
    rows={int(r['index']):r for r in payload.get('families',[])}
    if set(rows)!=set(CONF): raise ERR('CONFIRMATION_ALL20_REQUIRED')
    qualified=[i for i in CONF if bool(rows[i].get('stage2_qualified'))]
    if len(qualified)<15:
        return {'kind':'PLANCARRY_PLANUNIQUE_CONFIRMATION_V1_2','status':'INCONCLUSIVE_PLANUNIQUE_CONFIRMATION_QUALIFICATION','qualified_count':len(qualified),'denominator':20,'scientific_result':'NOT_ASSESSED'}
    cnp=[]; csp=[]; pos_np=0; pos_sp=0; active_valid=[]; no_valid=[]
    for i in CONF:
        r=rows[i]
        if not bool(r.get('stage2_qualified')):
            dnp=dsp=-1.0
        else:
            a=_finite(r['active_lca2']); n=_finite(r['no_patch_lca2']); s=_finite(r['max_specificity_lca2']); dnp=a-n; dsp=a-s
            if bool(r.get('zero_unique')):
                dnp=min(dnp,0.0); dsp=min(dsp,0.0)
            active_valid.append(_finite(r['active_valid_action_rate'])); no_valid.append(_finite(r['no_patch_valid_action_rate']))
        cnp.append(dnp);csp.append(dsp);pos_np+=int(dnp>0);pos_sp+=int(dsp>0)
    p={'d_no_patch':v1.exact_one_sided_sign_p(pos_np,20),'d_specificity':v1.exact_one_sided_sign_p(pos_sp,20)}; holm=v1.holm_two(p)
    mnp=mean(cnp); msp=mean(csp); competence=(mean(active_valid)>=mean(no_valid)-0.05) if active_valid else False
    supported=bool(holm['both_pass']) and mnp>=0.10 and msp>=0.10 and competence
    return {'kind':'PLANCARRY_PLANUNIQUE_CONFIRMATION_V1_2','status':'SUPPORTED_PLANUNIQUE_T1' if supported else 'REFUTED_PLANUNIQUE_T1','qualified_count':len(qualified),'denominator':20,'positive_no_patch':pos_np,'positive_specificity':pos_sp,'p_values':p,'holm':holm,'lower_bound_mean_d_no_patch':mnp,'lower_bound_mean_d_specificity':msp,'qualified_valid_action_guard_pass':competence,'scientific_result':'SUPPORTED' if supported else 'REFUTED'}
