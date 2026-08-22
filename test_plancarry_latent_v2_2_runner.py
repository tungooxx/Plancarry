#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, math, tempfile
from pathlib import Path

import plancarry_latent_v2_2_validator as v
import plancarry_latent_v2_2_runner as r

ROOT=Path(__file__).resolve().parent


def info_ok():
    return {
      'mode':'real','model_id':r.EXPECTED_MODEL_ID,
      'model_revision_requested':r.EXPECTED_MODEL_REVISION,
      'model_commit_resolved':r.EXPECTED_MODEL_REVISION,
      'device':'cuda:0','device_name':'NVIDIA GeForce RTX 3050',
      'dtype':'torch.float16','transformers_version':r.EXPECTED_TRANSFORMERS,
      'tokenizers_version':r.EXPECTED_TOKENIZERS,'quantization':'NONE',
      'num_layers':28,'hidden_size':1536,'torch_version':'2.6.0+cu124'
    }


def fake_ctx(idx):
    return r.PairContext(idx,f'f{idx}',False,'RESET\n<STATE_END>','AA\n<STATE_END>','BB\n<STATE_END>',
                         'XA\n<STATE_END>','XB\n<STATE_END>','cmd a','cmd b',0)


class NoCallClient:
    def model_info(self): raise AssertionError('model_info must not be called before selection verification')


class PlumbingMock:
    def model_info(self): return info_ok()
    def capture(self,text,layer,token_index=-1): return {'sequence_length':5,'token_index_resolved':4,'hidden_size':4,'vector':[1.,2.,3.,4.]}
    def score_sequences(self,prompt,suffixes):
        return {'scores':[{'suffix':suffixes[0],'logprob_sum':-2.,'token_count':2},{'suffix':suffixes[1],'logprob_sum':-4.,'token_count':2}]}
    def patch_score(self,prompt,suffixes,layer,vector,token_index=-1,mode='add',scale=1.0):
        # exact identity for zero add and self replacement engineering guard test
        return self.score_sequences(prompt,suffixes)


def test_bundle_and_donor_map():
    b=v.require_frozen_bundle(ROOT)
    assert len(b['manifest']['selected_pairs'])==40
    assert b['donor_map']['model_outcomes_seen'] is False


def test_rademacher_and_stats():
    x=v.rademacher_direction('confirmation',20,6,1536)
    y=v.rademacher_direction('confirmation',20,6,1536)
    assert x==y and abs(v.l2(x)-1.0)<1e-12
    assert abs(v.exact_sign_tail(15)-0.020694732666015625)<1e-15
    assert abs(v.exact_sign_tail(16)-0.005908966064453125)<1e-15
    raw={n:0.005 for n in v.PRIMARY_TEST_NAMES}
    adj=v.holm_adjust(raw)
    assert max(adj.values())==0.02


def test_bridge_gate():
    r.validate_bridge_info(info_ok())
    bad=info_ok(); bad['device_name']='NVIDIA GeForce GTX 1650'
    try:r.validate_bridge_info(bad)
    except RuntimeError as e: assert 'device_name' in str(e)
    else: raise AssertionError('GTX1650 was not rejected')
    missing=info_ok(); missing.pop('tokenizers_version')
    try:r.validate_bridge_info(missing)
    except RuntimeError: pass
    else: raise AssertionError('unverifiable tokenizers version was not rejected')


def test_plumbing_mock():
    out=r.plumbing_guard(PlumbingMock(),{0:fake_ctx(0),1:fake_ctx(1)})
    assert out['passed'] and len(out['details'])==8


def test_selection_refusal_before_model_call():
    try:r.run_confirmation(NoCallClient(),Path('/definitely/missing.json'),'0'*64,Path('/tmp/never.json'))
    except (FileNotFoundError,ValueError): pass
    else: raise AssertionError('missing selection artifact was not rejected')


def test_selection_verifier():
    payload={
      'kind':'PLANCARRY_LATENT_V2_2_DISCOVERY_SELECTION',
      'scientific_result':'NOT_ASSESSED_DISCOVERY_SELECTION_ONLY',
      'confirmation_requests_made':False,
      'frozen_refs':{'prereg_sha256':v.PREREG_SHA256,'manifest_sha256':v.MANIFEST_SHA256,'donor_map_sha256':v.DONOR_MAP_SHA256},
      'selected_layer':6,'selected_alpha':0.05,
      'discovery_active_directions':{str(i):{'direction':[0.,1.]} for i in range(20)}
    }
    with tempfile.TemporaryDirectory() as td:
      p=Path(td)/'selection.json'; p.write_text(json.dumps(payload,sort_keys=True)+'\n')
      sha=hashlib.sha256(p.read_bytes()).hexdigest()
      got=v.verify_selection_artifact(p,sha); assert got['selected_layer']==6
      try:v.verify_selection_artifact(p,'f'*64)
      except ValueError as e: assert 'FROZEN_HASH_MISMATCH' in str(e)
      else: raise AssertionError('bad selection sha accepted')


def test_confirmation_decision():
    rows=[]
    for i in range(20,40):
      rows.append({'pair_index':i,'cpse_active':0.20,'cpse_archived':0.01,'cpse_random':0.00,'cpse_unrelated':0.02,'delta_a':0.10,'delta_b':0.10})
    d=v.confirmation_decision(rows,20,13)
    assert d['status']=='SUPPORTED_T1'
    assert all(x['k_positive']==20 for x in d['primary_inference'].values())
    d2=v.confirmation_decision(rows,15,13); assert d2['status']=='INCONCLUSIVE_MODEL_EXPRESSIVITY'


def test_environment_only_pair_replay():
    b=v.require_frozen_bundle(ROOT)
    rows={int(x['frozen_pair_index']):x for x in b['manifest']['selected_pairs']}
    for i in [0,39]:
      c=r.build_pair_context(rows[i])
      assert c.pair_index==i and c.command_a!=c.command_b
      assert c.scoring_prompt.endswith('<STATE_END>\nACTION:')
      assert set([c.command_a,c.command_b]).issubset(set(rows[i]['reset_admissible_commands']))


def main():
    tests=[x for n,x in sorted(globals().items()) if n.startswith('test_') and callable(x)]
    for t in tests:
      t(); print('PASS',t.__name__)
    print('ALL_PASS',len(tests))

class FullPipelineMock:
    def __init__(self): self.calls=[]
    def model_info(self): return info_ok()
    @staticmethod
    def _vec(kind, d=1536):
        v=[0.0]*d
        if kind=='aa': v[0]=1.0
        elif kind=='ab': v[0]=-1.0
        elif kind=='xa': v[1]=1.0
        elif kind=='xb': v[1]=-1.0
        else:
            for j in range(d): v[j]=0.01
        return v
    def capture(self,text,layer,token_index=-1):
        self.calls.append(('capture',text[:24],layer))
        if 'ACTIVE_A_' in text: kind='aa'
        elif 'ACTIVE_B_' in text: kind='ab'
        elif 'ARCHIVED_A_' in text: kind='xa'
        elif 'ARCHIVED_B_' in text: kind='xb'
        else: kind='reset'
        return {'sequence_length':7,'token_index_resolved':6,'hidden_size':1536,'vector':self._vec(kind),'backend':'mock-test'}
    def _scores(self, margin, suffixes):
        # mean LP A - mean LP B = margin, one token each
        return {'scores':[{'suffix':suffixes[0],'logprob_sum':margin/2,'token_count':1},
                          {'suffix':suffixes[1],'logprob_sum':-margin/2,'token_count':1}]}
    def score_sequences(self,prompt,suffixes):
        self.calls.append(('score',prompt[:24]))
        if 'ACTIVE_A_' in prompt: margin=0.20
        elif 'ACTIVE_B_' in prompt: margin=-0.20
        else: margin=0.0
        return self._scores(margin,suffixes)
    def patch_score(self,prompt,suffixes,layer,vector,token_index=-1,mode='add',scale=1.0):
        self.calls.append(('patch',layer,mode,float(scale)))
        if mode=='replace' or abs(float(scale))==0.0:
            return self.score_sequences(prompt,suffixes)
        # deterministic engineering-only perturbation. Active e0 strongest;
        # archived e1 weaker; random/unrelated are allowed to vary.
        margin=2.0*float(scale)*(float(vector[0]) + 0.2*float(vector[1]))
        return self._scores(margin,suffixes)


def _fake_split(split):
    inds=range(20) if split=='discovery' else range(20,40)
    out={}
    for i in inds:
        out[i]=r.PairContext(i,f'family-{i}',i%2==0,
            f'RESET_{i}\n<STATE_END>', f'ACTIVE_A_{i}\n<STATE_END>',f'ACTIVE_B_{i}\n<STATE_END>',
            f'ARCHIVED_A_{i}\n<STATE_END>',f'ARCHIVED_B_{i}\n<STATE_END>', 'cmd a','cmd b', i%2)
    return out


def test_full_mock_discovery_confirmation_protocol():
    old=r._contexts_for_split
    r._contexts_for_split=lambda manifest,split:_fake_split(split)
    try:
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); sel=td/'selection.json'; conf=td/'confirmation.json'
            c=FullPipelineMock()
            sha=r.run_discovery(c,sel)
            assert sel.exists() and hashlib.sha256(sel.read_bytes()).hexdigest()==sha
            selection=v.verify_selection_artifact(sel,sha)
            assert selection['confirmation_requests_made'] is False
            assert selection['selected_layer'] in r.EXPECTED_LAYERS
            assert selection['selected_alpha'] in r.EXPECTED_ALPHAS
            sha2=r.run_confirmation(c,sel,sha,conf)
            result=json.loads(conf.read_text())
            assert hashlib.sha256(conf.read_bytes()).hexdigest()==sha2
            assert len(result['rows'])==20
            assert sorted(x['pair_index'] for x in result['rows'])==list(range(20,40))
            assert result['cohort_expressivity']['overall_competent']==20
            assert result['decision']['primary_inference'] is not None
    finally:
        r._contexts_for_split=old

if __name__=='__main__': main()
