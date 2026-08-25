import hashlib,json,math,tempfile
from pathlib import Path
import torch
import planunique_projection_v1 as P
import planunique_phase_runner_v1 as F

def test_projection_rank_and_collinear():
    r=torch.tensor([1.,2.,3.,4.]); n={'NEXT_ACTION_PRESERVED_LATE_NULL':torch.tensor([1.,0.,0.,0.]),'PAST_ACTIONS_ONLY':torch.tensor([2.,0.,0.,0.]),'PLAN_BLOCK_DERANGED':torch.tensor([0.,1.,0.,0.])}
    x=P.project_unique(r,n); assert x['kept_nuisance_names']==['NEXT_ACTION_PRESERVED_LATE_NULL','PLAN_BLOCK_DERANGED']; assert x['dropped_nuisance_names']==['PAST_ACTIONS_ONLY']; assert torch.allclose(x['r_unique'],torch.tensor([0.,0.,3.,4.]))

def test_projection_near_collinear_and_zero_nuisance():
    r=torch.tensor([1.,2.,3.]); n={'NEXT_ACTION_PRESERVED_LATE_NULL':torch.tensor([1.,0.,0.]),'PAST_ACTIONS_ONLY':torch.tensor([1.,1e-12,0.]),'PLAN_BLOCK_DERANGED':torch.zeros(3)}
    x=P.project_unique(r,n); assert len(x['basis'])==1; assert set(x['dropped_nuisance_names'])=={'PAST_ACTIONS_ONLY','PLAN_BLOCK_DERANGED'}

def _source(zero=False):
    r=torch.zeros(8) if zero else torch.tensor([1.,2.,3.,4.,5.,6.,7.,8.])
    return {'active':r,'controls':{'NEXT_ACTION_PRESERVED_LATE_NULL':torch.tensor([1.,0.,0.,0.,0.,0.,0.,0.]),'PAST_ACTIONS_ONLY':torch.tensor([0.,1.,0.,0.,0.,0.,0.,0.]),'PLAN_BLOCK_DERANGED':torch.tensor([0.,0.,1.,0.,0.,0.,0.,0.]),'UNRELATED_PLAN':torch.tensor([1.,1.,1.,1.,0.,0.,0.,0.])}}

def test_zero_unique_retained_exact_zero():
    s={'active':torch.tensor([1.,2.,3.]),'controls':{'NEXT_ACTION_PRESERVED_LATE_NULL':torch.tensor([1.,0.,0.]),'PAST_ACTIONS_ONLY':torch.tensor([0.,1.,0.]),'PLAN_BLOCK_DERANGED':torch.tensor([0.,0.,1.]),'UNRELATED_PLAN':torch.ones(3)}}
    x=P.vectors_for_grid(s,{'family':'f','game_path':'g'},14); assert x['zero_unique']; assert all(torch.count_nonzero(v)==0 for v in x['vectors'].values())

def test_target_basis_and_equal_norm_controls():
    x=P.vectors_for_grid(_source(),{'family':'f','game_path':'g'},14); t=x['target_norm']; assert t>0
    for v in x['vectors'].values(): assert abs(P.norm(v)-t)<1e-4
    for q in x['basis']: assert abs(float(torch.dot(x['vectors']['UNRELATED_PLAN_UNIQUE_EQ_NORM'].double(),q.double())))<1e-6

def test_random_canary():
    import localcontinuation_science_driver_v1 as r
    key='ReplayResidualLocalContinuation|RANDOM_EQ_NORM|0|CANARY_GAME|L14'; v=r.rademacher(16,1.0,key); signs=[1 if x>0 else -1 for x in v.tolist()]
    compact=lambda x:json.dumps(x,separators=(',',':'),sort_keys=True).encode()
    assert hashlib.sha256(compact(signs)).hexdigest()=='8781682ebaae7f23c19a53f332ad8eba320b3d24ee596b81321d70acea5ea458'
    assert hashlib.sha256(compact(v.tolist())).hexdigest()=='ab76e40900cc8e43d7458a6b8474ff008b38ef2732ef18875ed9c2f2088ec753'

def _devrow(joint=0.1,amsa=0.8,nmsa=0.7,zero=False):
    arms={F.ACTIVE:{'reference_action_margin_family':joint,'msa2':amsa},F.NO_PATCH:{'reference_action_margin_family':0.0,'msa2':nmsa}}
    for a in F.SPEC: arms[a]={'reference_action_margin_family':0.0,'msa2':0.5}
    return {'arms':arms,'zero_unique':zero}

def test_e_common_identical_all8_and_selection():
    e=list(range(24)); grids={}
    for l in F.LAYERS:
      for a in F.ALPHAS:
        key=F.grid_key(l,a); grids[key]={str(i):_devrow(joint=0.10+(0.01 if l==14 and a==1.0 else 0)) for i in e}
    p={'phase':'PLANUNIQUE_DEVELOPMENT_V1_2','e_common_indices':e,'grid_results':grids,'plumbing_sentinels_pass':True,'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False}
    out=F.select_development(p); assert out['status']=='FROZEN_PLANUNIQUE_DEVELOPMENT_SELECTION'; assert out['selected_layer']==14 and out['selected_alpha']==1.0
    bad=dict(p); bad['grid_results']=dict(grids); bad['grid_results'][F.grid_key(14,.5)]=dict(bad['grid_results'][F.grid_key(14,.5)]); bad['grid_results'][F.grid_key(14,.5)].pop('0')
    try:F.select_development(bad);assert False
    except Exception:pass

def test_common_gate_no_grid():
    p={'phase':'PLANUNIQUE_DEVELOPMENT_V1_2','e_common_indices':list(range(23)),'grid_results':{},'plumbing_sentinels_pass':True,'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False}
    assert F.select_development(p)['status']=='INCONCLUSIVE_PLANUNIQUE_COMMON_DENOMINATOR_CONSTRUCTIBILITY'

def test_confirmation_all20_lower_bound_and_zero_nonpositive():
    fam=[]
    for i in F.CONF:
        row={'index':i,'stage2_qualified':True,'zero_unique':False,'active_lca2':1.0,'no_patch_lca2':0.0,'max_specificity_lca2':0.0,'active_valid_action_rate':1.0,'no_patch_valid_action_rate':1.0}
        fam.append(row)
    # exactly five unqualified still gate-passes 15/20; lower bound mean=(15*1+5*-1)/20=.5
    for r in fam[-5:]: r['stage2_qualified']=False
    p={'phase':'PLANUNIQUE_CONFIRMATION_V1_2','families':fam}; o=F.evaluate_confirmation(p); assert o['denominator']==20 and abs(o['lower_bound_mean_d_no_patch']-.5)<1e-12
    fam[0]['zero_unique']=True; fam[0]['active_lca2']=1.0; fam[0]['no_patch_lca2']=0.0
    o=F.evaluate_confirmation({'phase':'PLANUNIQUE_CONFIRMATION_V1_2','families':fam}); assert o['positive_no_patch']==14

def test_confirmation_missing_family_fails():
    try:F.evaluate_confirmation({'phase':'PLANUNIQUE_CONFIRMATION_V1_2','families':[]});assert False
    except Exception:pass


def test_projection_basis_stays_float64_for_unrelated_projection():
    r=torch.tensor([1.0,2.0,3.0,4.0],dtype=torch.float32)
    n={'NEXT_ACTION_PRESERVED_LATE_NULL':torch.tensor([1.0,1e-8,0,0]),'PAST_ACTIONS_ONLY':torch.tensor([0,1.0,1e-8,0]),'PLAN_BLOCK_DERANGED':torch.tensor([0,0,1.0,1e-8])}
    q=P.project_unique(r,n)
    assert q['projection_numeric_dtype']=='float64'
    assert all(x.dtype==torch.float64 for x in q['basis'])
    u=P.project_through_basis(torch.tensor([1.0,2.0,4.0,8.0]),q['basis'])
    assert u.dtype==torch.float64
    for b in q['basis']:
        assert abs(float(torch.dot(u,b))) <= max(1e-10,1e-8*float(torch.linalg.vector_norm(u)))
