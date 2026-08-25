#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import torch
import localcontinuation_science_driver_v1 as runtime_v1

AUTHORITY_COMMIT='578a21c40c1cec2500a50edcd8daa643cceac6bd'
AUTHORITY_REVIEW_COMMIT='a413d535b2c5a9c8da9fb7e751f80f3eaeceecee'
AUTHORITY_REVIEW_SHA256='dd2ee03768e7d99f08cfd4c87002d059066361eecdcae9b4f1cdc7096c17ea40'
POPULATION_SHA256='ad2d525124b333b7dd04617bf52dd04c8196b5b67325a44274f3c0cbe576215f'
ZERO_EPS=1e-8
NUISANCE_ORDER=('NEXT_ACTION_PRESERVED_LATE_NULL','PAST_ACTIONS_ONLY','PLAN_BLOCK_DERANGED')
ACTIVE='PLAN_UNIQUE_ORTHOGONAL'
NO_PATCH='NO_PATCH'
SPEC=('RANDOM_EQ_UNIQUE_NORM','NUISANCE_COMPONENT_EQ_UNIQUE_NORM','NEXT_ACTION_EQ_UNIQUE_NORM','PAST_ACTIONS_EQ_UNIQUE_NORM','DERANGED_EQ_UNIQUE_NORM','UNRELATED_PLAN_UNIQUE_EQ_NORM')

class PlanUniqueProjectionError(RuntimeError): pass

def sha_json(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def _f64(x:torch.Tensor)->torch.Tensor: return x.detach().to(dtype=torch.float64,device='cpu').reshape(-1)
def _f32(x:torch.Tensor)->torch.Tensor: return x.detach().to(dtype=torch.float32,device='cpu').reshape(-1)
def norm(x:torch.Tensor)->float: return float(torch.linalg.vector_norm(x).item())

def project_unique(r_plan:torch.Tensor,nuisance:Mapping[str,torch.Tensor])->dict[str,Any]:
    r=_f64(r_plan); qs=[]; kept=[]; dropped=[]
    for name in NUISANCE_ORDER:
        if name not in nuisance: raise PlanUniqueProjectionError(f'NUISANCE_MISSING:{name}')
        v=_f64(nuisance[name])
        if v.numel()!=r.numel(): raise PlanUniqueProjectionError(f'DIM_MISMATCH:{name}')
        w=v.clone()
        for q in qs: w=w-torch.dot(q,w)*q
        tol=max(1e-10,1e-6*norm(v))
        if norm(w)<=tol:
            dropped.append(name); continue
        q=w/torch.linalg.vector_norm(w); qs.append(q); kept.append(name)
    comp=torch.zeros_like(r)
    for q in qs: comp=comp+torch.dot(q,r)*q
    unique=r-comp
    # Frozen numerical invariants.
    for i,q in enumerate(qs):
        for j,z in enumerate(qs):
            if i!=j and abs(float(torch.dot(q,z)))>1e-8: raise PlanUniqueProjectionError('BASIS_ORTHOGONALITY_FAIL')
        if abs(float(torch.dot(unique,q)))>max(1e-8,1e-6*norm(unique)): raise PlanUniqueProjectionError('UNIQUE_ORTHOGONALITY_FAIL')
    denom=max(norm(r),1e-30)
    if norm((unique+comp)-r)/denom>1e-8: raise PlanUniqueProjectionError('RECONSTRUCTION_FAIL')
    return {'r_unique':_f32(unique),'nuisance_component':comp,'basis':[q.clone() for q in qs],
            'kept_nuisance_names':kept,'dropped_nuisance_names':dropped,'unique_l2':norm(unique),'plan_l2':norm(r),
            'projection_numeric_dtype':'float64'}

def project_through_basis(v:torch.Tensor,basis:Sequence[torch.Tensor])->torch.Tensor:
    x=_f64(v)
    for q0 in basis:
        q=_f64(q0); x=x-torch.dot(q,x)*q
    return x

def _scaled(v:torch.Tensor,target:float,label:str)->torch.Tensor:
    x=_f64(v); n=norm(x)
    if target<=ZERO_EPS: return torch.zeros_like(x,dtype=torch.float32)
    if n<=ZERO_EPS: raise PlanUniqueProjectionError(f'REQUIRED_CONTROL_ZERO:{label}')
    y=x*(float(target)/n)
    if abs(norm(y)-target)>max(1e-10,1e-8*target): raise PlanUniqueProjectionError(f'NORM_MATCH_FAIL_F64:{label}')
    return _f32(y)

def vectors_for_grid(source:Mapping[str,Any],packet:Mapping[str,Any],layer:int)->dict[str,Any]:
    raw=_f32(source['active']); controls=source.get('controls',{})
    nuis={name:_f32(controls[name]) for name in NUISANCE_ORDER if name in controls}
    proj=project_unique(raw,nuis)
    target=float(proj['unique_l2']); z=target<=ZERO_EPS
    out={ACTIVE:torch.zeros_like(raw) if z else proj['r_unique']}
    if z:
        for arm in SPEC: out[arm]=torch.zeros_like(raw)
        return {**proj,'vectors':out,'zero_unique':True,'constructible':True,'target_norm':target}
    out['NUISANCE_COMPONENT_EQ_UNIQUE_NORM']=_scaled(proj['nuisance_component'],target,'NUISANCE_COMPONENT')
    out['NEXT_ACTION_EQ_UNIQUE_NORM']=_scaled(controls['NEXT_ACTION_PRESERVED_LATE_NULL'],target,'NEXT_ACTION')
    out['PAST_ACTIONS_EQ_UNIQUE_NORM']=_scaled(controls['PAST_ACTIONS_ONLY'],target,'PAST_ACTIONS')
    out['DERANGED_EQ_UNIQUE_NORM']=_scaled(controls['PLAN_BLOCK_DERANGED'],target,'DERANGED')
    unrelated=project_through_basis(controls['UNRELATED_PLAN'],proj['basis'])
    out['UNRELATED_PLAN_UNIQUE_EQ_NORM']=_scaled(unrelated,target,'UNRELATED_PROJECTED')
    key=f"ReplayResidualLocalContinuation|RANDOM_EQ_NORM|{packet['family']}|{packet['game_path']}|L{int(layer)}"
    out['RANDOM_EQ_UNIQUE_NORM']=runtime_v1.rademacher(int(raw.numel()),target,key)
    if abs(norm(out['RANDOM_EQ_UNIQUE_NORM'])-target)>max(1e-5,1e-4*target): raise PlanUniqueProjectionError('RANDOM_NORM_FAIL')
    return {**proj,'vectors':out,'zero_unique':False,'constructible':True,'target_norm':target,
            'unrelated_projected_l2':norm(unrelated),'random_key':key}
