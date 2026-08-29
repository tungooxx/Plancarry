from __future__ import annotations
import copy, hashlib, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/'results/design/plancarry_cpds_recurrent_realization_feature_basis_v1_20260829.json'
AUDIT=ROOT/'results/design/plancarry_cpds_recurrent_realization_static_audit_v1_20260829.json'
D=2048

def _canon(o): return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def load_contract(): return json.loads(CONTRACT.read_text())
def load_audit(): return json.loads(AUDIT.read_text())
def validate_self_hash(d):
    x=copy.deepcopy(d); got=x.pop('canonical_object_sha256_without_self_field',None)
    if got!=hashlib.sha256(_canon(x)).hexdigest(): raise ValueError('CONTRACT_SELF_HASH')
    return True

def validate_contract(d):
    validate_self_hash(d)
    if d['schema']!='PLANCARRY_CPDS_RECURRENT_REALIZATION_FEATURE_BASIS_V1': raise ValueError('SCHEMA')
    if d['scientific_result']!='NOT_ASSESSED' or d['science_execution_forbidden'] is not True: raise ValueError('PRE_SCIENCE_SCOPE')
    a=d['authority']
    if a['constructibility_commit']!='c1c6517ff4678c2a9b151f67a1ff4dd6f5aae244' or a['constructibility_review_verdict']!='PASS_FOR_CPDS_GRAPHFORK_GEOMETRY_DUPLICATE_REPAIR': raise ValueError('CONSTRUCTIBILITY_AUTHORITY')
    if a['statistical_commit']!='df17c5ee3a3d2c6bccd70367886216cd043d40f3' or a['statistical_review_verdict']!='PASS_FOR_CPDS_V3_STATISTICAL_REPAIR': raise ValueError('STATISTICAL_AUTHORITY')
    if a['planroute']!='USER_NOOP_RETIRED' or a['successorfeature']!='STATIC_BASELINE_ONLY': raise ValueError('USER_POLICY')
    m=d['frozen_model_basis']
    if (m['model_id'],m['revision'],m['config_sha256'],m['hidden_size']) != ('Qwen/Qwen3-1.7B','70d244cc86ccca08cf5af4e1e306ecf908b1ad5e','1ddb5b89ebc90dcb417a45c213d818577e65976454d29385c8f6140771d95197',D): raise ValueError('MODEL_BASIS')
    if m['new_trainable_parameters']!=0 or m['carrier_numeric_dtype']!='FLOAT32': raise ValueError('CAPACITY')
    r=d['recurrent_state']; g=d['adapter_G']
    if r['state_dim']!=D or r['state_capacity_bytes']!=8192 or r['F_trainable_parameters']!=0 or r['F_fit_recipe']!='NONE': raise ValueError('F_AUTHORITY')
    if g['G_trainable_parameters']!=0 or g['G_fit_recipe']!='NONE' or g['nonexecuting'] is not True or any(g[k] for k in ['can_execute_action','can_force_single_action','can_mutate_environment']): raise ValueError('G_AUTHORITY')
    if d['matched_information_control']['transform']!='P(x)[i]=(-1)^i * x[(i+1) mod 2048] for i=0..2047': raise ValueError('MATCHED_INFO_TRANSFORM')
    if set(d['arm_realization']) != {'NO_CARRY','STATIC_ONESHOT','STATIC_REPEAT','ALIGNED_RECURSION','TRANSITION_PERMUTED','MATCHED_INFORMATION'}: raise ValueError('ARM_SET')
    s=d['statistics_binding']
    if s['statistical_contract_changed'] is not False or (s['n'],s['positive_each_min'])!=(33,22): raise ValueError('STATISTICS_DRIFT')
    return True

def unit_l2(v):
    if len(v)!=D or any(not math.isfinite(float(x)) for x in v): raise ValueError('VECTOR')
    n2=0.0
    for x in v: n2 += float(x)*float(x)
    if not math.isfinite(n2) or n2<=0.0: raise ValueError('ZERO_OR_NONFINITE_NORM')
    n=math.sqrt(n2)
    out=[float(x)/n for x in v]
    if any(not math.isfinite(x) for x in out): raise ValueError('NORMALIZED_VECTOR')
    return out

def F(z,x): return unit_l2([a+b for a,b in zip(unit_l2(z),unit_l2(x))])
def P(x):
    u=unit_l2(x)
    return [((-1.0) if i%2 else 1.0)*u[(i+1)%D] for i in range(D)]
def G_delta(z,q):
    uz,uq=unit_l2(z),unit_l2(q)
    return sum(a*b for a,b in zip(uz,uq))
def fold(z0,xs):
    z=unit_l2(z0)
    for x in xs: z=F(z,x)
    return z
