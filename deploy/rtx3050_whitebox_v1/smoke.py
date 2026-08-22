#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os
from whitebox_client import WhiteboxClient

def unwrap(body):
    if isinstance(body,dict) and body.get('ok') is True and isinstance(body.get('result'),dict): return body['result']
    return body
def maxdiff(a,b): return max(abs(float(x['logprob_sum'])-float(y['logprob_sum'])) for x,y in zip(a,b))
def normalize(v):
    n=math.sqrt(sum(float(x)*float(x) for x in v)); return [0.0 for _ in v] if n<=1e-12 else [float(x)/n for x in v]
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--url',default=os.getenv('PLANCARRY_WHITEBOX_URL','http://127.0.0.1:8765')); p.add_argument('--token',default=os.getenv('PLANCARRY_WHITEBOX_TOKEN','')); a=p.parse_args()
    if not a.token: raise SystemExit('PLANCARRY_WHITEBOX_TOKEN required')
    c=WhiteboxClient(a.url,a.token,timeout=120.0); info=unwrap(c.model_info()); layer=min(13,int(info['num_layers'])-1)
    reset='SYNTHETIC PROTOCOL CHECK\nSTATE: neutral\n<STATE_END>\n'
    src_a=reset+'PLAN OPTIONS\nOPTION A: choose alpha\nOPTION B: choose beta\nACTIVE ORDER: A THEN B\n<STATE_END>\n'
    src_b=reset+'PLAN OPTIONS\nOPTION A: choose alpha\nOPTION B: choose beta\nACTIVE ORDER: B THEN A\n<STATE_END>\n'
    suffixes=[' alpha',' beta']
    h0=unwrap(c.capture(reset,layer,-1))['vector']; ha=unwrap(c.capture(src_a,layer,-1))['vector']; hb=unwrap(c.capture(src_b,layer,-1))['vector']
    base=unwrap(c.score_sequences(reset+'ACTION:',suffixes))['scores']
    zero=unwrap(c.patch_score(reset+'ACTION:',suffixes,layer,[0.0]*len(h0),-1,'add',1.0))['scores']
    selfp=unwrap(c.patch_score(reset+'ACTION:',suffixes,layer,h0,-1,'replace',1.0))['scores']
    d=normalize([float(x)-float(y) for x,y in zip(ha,hb)])
    nonzero=unwrap(c.patch_score(reset+'ACTION:',suffixes,layer,d,-1,'add',0.1))['scores']
    checks={
      'mode_real_or_mock': info.get('mode') in {'real','mock'},
      'hidden_dim_matches': len(h0)==int(info['hidden_size'])==len(ha)==len(hb),
      'zero_add_le_1e_6': maxdiff(base,zero)<=1e-6,
      'self_patch_check': (maxdiff(base,selfp)<=1e-4) if info.get('mode')=='real' else all(math.isfinite(float(x['logprob_sum'])) for x in selfp),
      'nonzero_scores_finite': all(math.isfinite(float(x['logprob_sum'])) for x in nonzero),
      'scientific_result_not_assessed': info.get('scientific_result')=='NOT_ASSESSED',
    }
    out={'ok':all(checks.values()),'checks':checks,'metrics':{'zero_add_max_abs':maxdiff(base,zero),'self_patch_max_abs':maxdiff(base,selfp),'contrast_norm':math.sqrt(sum(x*x for x in d)),'nonzero_max_abs':maxdiff(base,nonzero)},'backend_mode':info.get('mode'),'scientific_result':'NOT_ASSESSED'}
    print(json.dumps(out,indent=2,sort_keys=True)); return 0 if out['ok'] else 2
if __name__=='__main__': raise SystemExit(main())
