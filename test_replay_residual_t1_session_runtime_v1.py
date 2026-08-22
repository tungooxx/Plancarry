from __future__ import annotations
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
from types import SimpleNamespace
import unittest

import torch
from transformers.cache_utils import DynamicCache

import replay_residual_t1_session_runtime_v1 as r


class TinyBlock(torch.nn.Module):
    def __init__(self, h):
        super().__init__(); self.lin=torch.nn.Linear(h,h,bias=False)
    def forward(self,x): return torch.tanh(self.lin(x))


class TinySessionModel(torch.nn.Module):
    def __init__(self,vocab=32,h=8,layers=3):
        super().__init__()
        self.config=SimpleNamespace(hidden_size=h)
        self.embed=torch.nn.Embedding(vocab,h)
        self.layers=torch.nn.ModuleList([TinyBlock(h) for _ in range(layers)])
        self.lm_head=torch.nn.Linear(h,vocab,bias=False)
    def forward(self,input_ids,attention_mask=None,past_key_values=None,use_cache=True):
        cache=past_key_values if past_key_values is not None else DynamicCache()
        past_len=int(cache.get_seq_length()) if past_key_values is not None else 0
        x=self.embed(input_ids) + float(past_len)*1e-3
        for i,block in enumerate(self.layers):
            x=block(x)
            if use_cache:
                kv=x.unsqueeze(1)
                cache.update(kv.detach(),kv.detach(),i)
        return SimpleNamespace(logits=self.lm_head(x),past_key_values=cache if use_cache else None)


def model_on_device():
    torch.manual_seed(20260821)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    dtype=torch.bfloat16 if device.type=='cuda' else torch.float32
    m=TinySessionModel().to(device=device,dtype=dtype).eval()
    return m,device,dtype


class TestRuntime(unittest.TestCase):
    def test_exact_token_session_invariants(self):
        m,device,dtype=model_on_device()
        prefix=[1,2,3,4]
        vec=torch.linspace(-0.2,0.2,m.config.hidden_size,device=device,dtype=torch.float32)
        s=r.PersistentTokenSession(m,prefix,layer=1,vector=vec,mode='add',scale=0.5)
        self.assertEqual(s.hook_count,1)
        self.assertEqual(s.context_len,len(prefix))
        before=r.cache_digest(s.past_key_values)
        cand={'zeta':[5,6], 'alpha':[7,8]}
        c1,rows1=s.score_candidates(cand)
        c2,rows2=s.score_candidates(cand)
        self.assertEqual(c1,c2)
        self.assertEqual({k:v.mean_logprob for k,v in rows1.items()},{k:v.mean_logprob for k,v in rows2.items()})
        self.assertEqual(before,r.cache_digest(s.past_key_values))
        self.assertEqual(s.context_len,len(prefix))
        command,scores,action=s.choose_and_commit(cand)
        self.assertEqual(action['context_len_after'],len(prefix)+2)
        obs=s.append_ids([9,10,11],event='OBSERVATION')
        self.assertEqual(obs['context_len_after'],len(prefix)+5)
        self.assertEqual(r.cache_seq_len(s.past_key_values),len(prefix)+5)
        self.assertEqual(s.hook_count,1)
        prov=s.close(); self.assertEqual(prov['hook_count'],1); self.assertEqual(prov['append_event_count'],2)

    def test_zero_add_matches_no_patch(self):
        m0,device,dtype=model_on_device(); state=m0.state_dict()
        m1,_,_=model_on_device(); m1.load_state_dict(state)
        prefix=[2,3,4]
        zero=torch.zeros(m0.config.hidden_size,device=device,dtype=torch.float32)
        a=r.PersistentTokenSession(m0,prefix,layer=0,vector=None)
        b=r.PersistentTokenSession(m1,prefix,layer=0,vector=zero,mode='add',scale=1.0)
        maxabs=float((a.next_logits-b.next_logits).abs().max().item())
        self.assertLessEqual(maxabs,r.ENGINEERING_EQUIV_ATOL)
        # Cache equality is expected because zero-add is mathematically a no-op.
        self.assertEqual(r.cache_digest(a.past_key_values),r.cache_digest(b.past_key_values))
        self.assertEqual(a.hook_count,0); self.assertEqual(b.hook_count,1)

    def test_lexical_tie_break_and_direct_ids(self):
        m,_,_=model_on_device(); s=r.PersistentTokenSession(m,[1,3],layer=0,vector=None)
        chosen,rows=s.score_candidates({'zeta':[4], 'alpha':[4]})
        self.assertEqual(chosen,'alpha')
        self.assertEqual(rows['alpha'].suffix_token_ids_sha256,r.token_ids_sha256([4]))
        self.assertEqual(rows['zeta'].suffix_token_ids_sha256,r.token_ids_sha256([4]))

    def test_capture_exact_ids(self):
        m,_,_=model_on_device(); v=r.capture_activation_ids(m,[1,2,3],1,-1)
        self.assertEqual(tuple(v.shape),(m.config.hidden_size,))

    def test_rejects_bad_contracts(self):
        m,device,_=model_on_device()
        with self.assertRaises(r.SessionContractError): r.PersistentTokenSession(m,[],layer=0,vector=None)
        with self.assertRaises(r.SessionContractError): r.PersistentTokenSession(m,[1],layer=99,vector=None)
        s=r.PersistentTokenSession(m,[1],layer=0,vector=None)
        with self.assertRaises(r.SessionContractError): s.score_candidates({})
        with self.assertRaises(r.SessionContractError): s.append_ids([],event='X')


if __name__=='__main__': unittest.main(verbosity=2)
