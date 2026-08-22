#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys, json

def run(args, env):
    p=subprocess.run([sys.executable,'whitebox_bridge.py',*args],cwd='.',env=env,text=True,capture_output=True,timeout=5)
    return p.returncode,p.stdout,p.stderr
base=os.environ.copy(); base.pop('PLANCARRY_WHITEBOX_TOKEN',None)
r1,o1,e1=run(['--model-id','dummy/model','--revision','deadbeef'],base)
env=base.copy(); env['PLANCARRY_WHITEBOX_TOKEN']='test-only-token'
r2,o2,e2=run(['--mock','--host','0.0.0.0'],env)
out={'scientific_result':'NOT_ASSESSED','model_inference_executed':False,
     'real_without_token_refused':r1==2 and 'PLANCARRY_WHITEBOX_TOKEN is required' in e1,
     'nonloopback_without_allow_refused':r2==2 and 'Refusing non-loopback bind' in e2}
out['pass']=all(v for k,v in out.items() if k not in {'scientific_result','model_inference_executed'})
from pathlib import Path; Path('results/engineering').mkdir(parents=True,exist_ok=True); Path('results/engineering/whitebox_bridge_startup_test.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(json.dumps(out,indent=2)); raise SystemExit(0 if out['pass'] else 1)
