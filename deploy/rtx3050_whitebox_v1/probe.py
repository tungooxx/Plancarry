#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os
from whitebox_client import WhiteboxClient
EXPECTED={
 "api_version":"plancarry-whitebox-v1",
 "mode":"real",
 "model_id":"Qwen/Qwen2.5-1.5B-Instruct",
 "model_revision_requested":"989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
 "model_commit_resolved":"989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
 "transformers_version":"4.46.3",
 "tokenizers_version":"0.20.3",
 "quantization":"NONE",
 "num_layers":28,
 "hidden_size":1536,
}
def unwrap(body):
    if isinstance(body,dict) and body.get('ok') is True and isinstance(body.get('result'),dict): return body['result']
    return body
def validate_info(info):
    errors=[]
    for k,v in EXPECTED.items():
        if info.get(k)!=v: errors.append(f'{k}: expected {v!r}, got {info.get(k)!r}')
    if info.get('device')!='cuda': errors.append(f"device: expected 'cuda', got {info.get('device')!r}")
    if info.get('dtype') not in {'torch.float16','float16'}: errors.append(f"dtype: expected float16, got {info.get('dtype')!r}")
    if 'rtx 3050' not in str(info.get('device_name','')).lower(): errors.append(f"device_name is not RTX 3050: {info.get('device_name')!r}")
    if info.get('scientific_result')!='NOT_ASSESSED': errors.append('scientific_result must remain NOT_ASSESSED')
    return errors
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--url',default=os.getenv('PLANCARRY_WHITEBOX_URL','http://192.168.1.51:8765')); p.add_argument('--token',default=os.getenv('PLANCARRY_WHITEBOX_TOKEN','')); a=p.parse_args()
    if not a.token: raise SystemExit('PLANCARRY_WHITEBOX_TOKEN required')
    c=WhiteboxClient(a.url,a.token,timeout=15.0); health=unwrap(c.health()); info=unwrap(c.model_info()); errors=validate_info(info)
    out={'ok':not errors,'url':a.url,'health':health,'model_info':info,'errors':errors}
    print(json.dumps(out,indent=2,sort_keys=True)); return 0 if not errors else 2
if __name__=='__main__': raise SystemExit(main())
