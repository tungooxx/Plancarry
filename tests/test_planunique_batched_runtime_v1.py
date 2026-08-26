from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from types import SimpleNamespace
import torch
from transformers.cache_utils import DynamicCache
import replay_residual_t1_session_runtime_v1 as legacy
import planunique_batched_runtime_v1 as batched

class TinyBlock(torch.nn.Module):
    def __init__(self,h): super().__init__(); self.lin=torch.nn.Linear(h,h,bias=False)
    def forward(self,x): return torch.tanh(self.lin(x))

class TinyModel(torch.nn.Module):
    def __init__(self,vocab=160,h=48,layers=4):
        super().__init__(); self.config=SimpleNamespace(hidden_size=h); self.embed=torch.nn.Embedding(vocab,h); self.layers=torch.nn.ModuleList([TinyBlock(h) for _ in range(layers)]); self.lm_head=torch.nn.Linear(h,vocab,bias=False); self.forward_calls=0
    def forward(self,input_ids,attention_mask=None,past_key_values=None,use_cache=True):
        self.forward_calls += 1
        cache=past_key_values if past_key_values is not None else DynamicCache()
        past_len=int(cache.get_seq_length()) if past_key_values is not None else 0
        x=self.embed(input_ids)+float(past_len)*1e-3
        for i,b in enumerate(self.layers):
            x=b(x)
            if use_cache:
                kv=x.unsqueeze(1); cache.update(kv.detach(),kv.detach(),i)
        return SimpleNamespace(logits=self.lm_head(x),past_key_values=cache if use_cache else None)

def model():
    torch.manual_seed(20260827); return TinyModel().eval()

def assert_rows_close(a,b,cand,atol=1e-6):
    for k in cand:
        assert a[k].token_count==b[k].token_count
        assert a[k].suffix_token_ids_sha256==b[k].suffix_token_ids_sha256
        assert abs(a[k].logprob_sum-b[k].logprob_sum)<=atol,(k,a[k],b[k])
        assert abs(a[k].mean_logprob-b[k].mean_logprob)<=atol,(k,a[k],b[k])

def test_grouped_equivalence_variable_lengths_and_live_kv_immutability():
    m=model(); prefix=list(range(1,65)); cand={f'cmd-{i:02d}':[2+i, 30+(i*3)%80, 50+(i*5)%70, 70+(i*7)%60, 90+(i*11)%50][:1+(i%5)] for i in range(13)}
    a=legacy.PersistentTokenSession(m,prefix,layer=2,vector=None); b=batched.PlanUniqueBatchedTokenSession(m,prefix,layer=2,vector=None)
    before=legacy.cache_digest(b.past_key_values); ctx=b.context_len; hooks=b.hook_count
    ca,ra=a.score_candidates(cand); cb,rb=b.score_candidates(cand)
    assert ca==cb; assert_rows_close(ra,rb,cand)
    assert legacy.cache_digest(b.past_key_values)==before
    assert b.context_len==ctx and b.hook_count==hooks

def test_grouped_model_forward_count_reduced_materially():
    m=model(); prefix=list(range(1,65)); cand={f'cmd-{i:02d}':[2+i,40+i,80+i,120+i] for i in range(12)}
    a=legacy.PersistentTokenSession(m,prefix,layer=1,vector=None); m.forward_calls=0; ca,ra=a.score_candidates(cand); legacy_calls=m.forward_calls
    b=batched.PlanUniqueBatchedTokenSession(m,prefix,layer=1,vector=None); m.forward_calls=0; cb,rb=b.score_candidates(cand); grouped_calls=m.forward_calls
    assert ca==cb; assert_rows_close(ra,rb,cand)
    assert legacy_calls==12*3,legacy_calls
    assert grouped_calls==3*3,grouped_calls
    assert grouped_calls*4==legacy_calls

def test_grouping_more_than_one_chunk_preserves_sorted_candidate_binding():
    m=model(); cand={'zeta':[4,5,6], 'alpha':[4,5,6], **{f'k{i}':[10+i,20+i] for i in range(7)}}
    a=legacy.PersistentTokenSession(m,[1,2,3],layer=0,vector=None); b=batched.PlanUniqueBatchedTokenSession(m,[1,2,3],layer=0,vector=None)
    ca,ra=a.score_candidates(cand); cb,rb=b.score_candidates(cand)
    assert ca==cb; assert_rows_close(ra,rb,cand)
    assert ra['alpha'].mean_logprob==ra['zeta'].mean_logprob and rb['alpha'].mean_logprob==rb['zeta'].mean_logprob
    assert sorted([r for r in rb.values() if r.mean_logprob==rb['alpha'].mean_logprob], key=lambda r:(-r.mean_logprob,r.command))[0].command=='alpha'

def test_intervention_hook_does_not_refire_and_live_cache_unchanged():
    m=model(); v=torch.linspace(-.1,.1,m.config.hidden_size); cand={f'c{i}':[20+i,40+i,60+i] for i in range(8)}
    s=batched.PlanUniqueBatchedTokenSession(m,[1,2,3,4],layer=1,vector=v,mode='add',scale=.5)
    assert s.hook_count==1
    before=legacy.cache_digest(s.past_key_values); ctx=s.context_len
    s.score_candidates(cand)
    assert s.hook_count==1 and s.context_len==ctx and legacy.cache_digest(s.past_key_values)==before

def test_single_token_candidates_need_zero_model_forwards_after_session_init():
    m=model(); s=batched.PlanUniqueBatchedTokenSession(m,[1,2,3],layer=0,vector=None); m.forward_calls=0
    chosen,rows=s.score_candidates({f'c{i}':[10+i] for i in range(9)})
    assert m.forward_calls==0
    assert chosen in rows and all(r.token_count==1 for r in rows.values())

def test_fail_closed_empty_map_and_empty_suffix():
    m=model(); s=batched.PlanUniqueBatchedTokenSession(m,[1,2,3],layer=0,vector=None)
    try: s.score_candidates({}); assert False
    except legacy.SessionContractError: pass
    try: s.score_candidates({'x':[]}); assert False
    except legacy.SessionContractError: pass

def test_planunique_no_patch_cache_reuses_alpha_independent_arm():
    import planunique_science_driver_v1 as driver
    calls=[]; original=driver.batched_runtime.msa2_arm; original_sha=driver._vector_sha
    try:
        def fake(tok,model,p,base_reset,layer,vector,alpha,arm,asha):
            calls.append((arm,float(alpha)))
            return {'msa2':0.5,'reference_action_margin_family':0.1,'hook_count':0,'session_id_hash':'s','arm_name':arm,'selected_layer':int(layer),'selected_alpha':float(alpha),'active_residual_sha256':asha,'injected_vector_sha256':None,'reset_prefix_sha256':'r','reset_snapshot_sha256':'x'}
        driver.batched_runtime.msa2_arm=fake; driver._vector_sha=lambda v:'a'
        p={'frozen_index':7}; base_reset={'reset_snapshot_sha256':'x'}; vp={'vectors':{driver.ACTIVE:object(), **{a:object() for a in driver.SPEC}},'zero_unique':False,'unique_l2':1.0}; cache={}
        r1=driver._run_msa(None,None,p,base_reset,14,0.5,vp,cache); r2=driver._run_msa(None,None,p,base_reset,14,1.0,vp,cache)
        assert [x for x in calls if x[0]==driver.NO_PATCH]==[(driver.NO_PATCH,0.5)]
        assert r1['arms'][driver.NO_PATCH]['selected_alpha']==0.5 and r2['arms'][driver.NO_PATCH]['selected_alpha']==1.0
    finally:
        driver.batched_runtime.msa2_arm=original; driver._vector_sha=original_sha

def test_frozen_group_size_is_four():
    assert batched.CANDIDATE_GROUP_SIZE==4
