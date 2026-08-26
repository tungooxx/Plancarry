from __future__ import annotations
import time
from types import SimpleNamespace
import torch
from transformers.cache_utils import DynamicCache
import replay_residual_t1_session_runtime_v1 as legacy
import planunique_fast_runtime_v1 as fast

class TinyBlock(torch.nn.Module):
    def __init__(self,h): super().__init__(); self.lin=torch.nn.Linear(h,h,bias=False)
    def forward(self,x): return torch.tanh(self.lin(x))
class TinyModel(torch.nn.Module):
    def __init__(self,vocab=128,h=64,layers=6):
        super().__init__(); self.config=SimpleNamespace(hidden_size=h); self.embed=torch.nn.Embedding(vocab,h); self.layers=torch.nn.ModuleList([TinyBlock(h) for _ in range(layers)]); self.lm_head=torch.nn.Linear(h,vocab,bias=False)
    def forward(self,input_ids,attention_mask=None,past_key_values=None,use_cache=True):
        cache=past_key_values if past_key_values is not None else DynamicCache(); past_len=int(cache.get_seq_length()) if past_key_values is not None else 0
        x=self.embed(input_ids)+float(past_len)*1e-3
        for i,b in enumerate(self.layers):
            x=b(x)
            if use_cache:
                kv=x.unsqueeze(1); cache.update(kv.detach(),kv.detach(),i)
        return SimpleNamespace(logits=self.lm_head(x),past_key_values=cache if use_cache else None)

def model():
    torch.manual_seed(20260826); return TinyModel().eval()

def test_exact_equivalence_and_live_kv_immutability():
    m=model(); prefix=list(range(1,97)); cand={f'cmd-{i:02d}':[2+i%60,3+(i*3)%60,4+(i*7)%60] for i in range(24)}
    a=legacy.PersistentTokenSession(m,prefix,layer=2,vector=None); b=fast.PlanUniquePersistentTokenSession(m,prefix,layer=2,vector=None)
    before=legacy.cache_digest(b.past_key_values); ctx=b.context_len; hooks=b.hook_count
    ca,ra=a.score_candidates(cand); cb,rb=b.score_candidates(cand)
    assert ca==cb
    for k in cand:
        assert ra[k].token_count==rb[k].token_count
        assert ra[k].suffix_token_ids_sha256==rb[k].suffix_token_ids_sha256
        assert ra[k].logprob_sum==rb[k].logprob_sum
        assert ra[k].mean_logprob==rb[k].mean_logprob
    assert legacy.cache_digest(b.past_key_values)==before and b.context_len==ctx and b.hook_count==hooks

def test_lexical_tie_break_preserved():
    m=model(); s=fast.PlanUniquePersistentTokenSession(m,[1,2,3],layer=0,vector=None)
    chosen,rows=s.score_candidates({'zeta':[4],'alpha':[4]}); assert chosen=='alpha'; assert rows['alpha'].mean_logprob==rows['zeta'].mean_logprob

def test_benchmark_guard_amortization_material():
    m=model(); prefix=list(range(1,97)); cand={f'cmd-{i:02d}':[2+i%60,3+(i*3)%60] for i in range(48)}
    a=legacy.PersistentTokenSession(m,prefix,layer=2,vector=None); b=fast.PlanUniquePersistentTokenSession(m,prefix,layer=2,vector=None)
    t=time.perf_counter(); ca,ra=a.score_candidates(cand); old=time.perf_counter()-t
    t=time.perf_counter(); cb,rb=b.score_candidates(cand); new=time.perf_counter()-t
    assert ca==cb and all(ra[k].mean_logprob==rb[k].mean_logprob for k in cand)
    # CPU synthetic cache should already benefit; exact Qwen benchmark is a separate canary.
    assert new < old, (old,new)
    print({'legacy_s':old,'fast_s':new,'speedup':old/new})

def test_planunique_no_patch_cache_reuses_alpha_independent_arm():
    import planunique_science_driver_v1 as driver
    calls=[]
    original=driver.fast_runtime.msa2_arm
    original_sha=driver._vector_sha
    try:
        def fake(tok,model,p,base_reset,layer,vector,alpha,arm,asha):
            calls.append((arm,float(alpha)))
            return {'msa2':0.5,'reference_action_margin_family':0.1,'hook_count':0,'session_id_hash':'s','arm_name':arm,'selected_layer':int(layer),'selected_alpha':float(alpha),'active_residual_sha256':asha,'injected_vector_sha256':None,'reset_prefix_sha256':'r','reset_snapshot_sha256':'x'}
        driver.fast_runtime.msa2_arm=fake; driver._vector_sha=lambda v:'a'
        p={'frozen_index':7}; base_reset={'reset_snapshot_sha256':'x'}; vp={'vectors':{driver.ACTIVE:object(), **{a:object() for a in driver.SPEC}},'zero_unique':False,'unique_l2':1.0}
        cache={}
        r1=driver._run_msa(None,None,p,base_reset,14,0.5,vp,cache)
        r2=driver._run_msa(None,None,p,base_reset,14,1.0,vp,cache)
        no_patch_calls=[x for x in calls if x[0]==driver.NO_PATCH]
        assert no_patch_calls==[(driver.NO_PATCH,0.5)]
        assert r1['arms'][driver.NO_PATCH]['selected_alpha']==0.5
        assert r2['arms'][driver.NO_PATCH]['selected_alpha']==1.0
        for key in ('msa2','reference_action_margin_family','session_id_hash','reset_snapshot_sha256'):
            assert r1['arms'][driver.NO_PATCH][key]==r2['arms'][driver.NO_PATCH][key]
    finally:
        driver.fast_runtime.msa2_arm=original; driver._vector_sha=original_sha
