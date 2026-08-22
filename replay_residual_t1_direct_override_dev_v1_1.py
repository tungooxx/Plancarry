#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys, hashlib
from pathlib import Path
import replay_residual_natural_packet_producer_v2_1 as p

ROOT=Path(__file__).resolve().parent
BIND=ROOT/'results/design/plancarry_replay_residual_t1_population_binding_v1_20260821.json'
OUT=Path('results/science/plancarry_replay_residual_t1_user_override_dev_packets_v1')
SUMMARY=ROOT/'results/science/plancarry_replay_residual_t1_user_override_dev_gate_v1.json'

def fsync_json_new(path:Path,obj):
    if path.exists(): raise RuntimeError(f'REFUSE_EXISTING:{path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    tmp=path.with_name('.'+path.name+f'.tmp.{os.getpid()}')
    with open(tmp,'xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    os.link(tmp,path); tmp.unlink()
    return hashlib.sha256(raw).hexdigest()

def main():
    if (ROOT/OUT).exists() or SUMMARY.exists(): raise RuntimeError('T1_OVERRIDE_OUTPUT_ALREADY_EXISTS')
    b=json.loads(BIND.read_text())
    rows=b['development']['families']
    if [int(x['frozen_index']) for x in rows] != list(range(32)): raise RuntimeError('DEV_BINDING_DRIFT')
    p.verify_frozen_bindings(ROOT)
    tok,model,prov=p.load_production_runtime(ROOT)
    planner=lambda task,obs:p.torch_generate_plan(tok,model,task,obs)
    scorer=lambda prefix,suffix:p.torch_suffix_mean_logprob(model,prefix,suffix)
    packets=[]
    for n,row in enumerate(rows,1):
        packets.append(p.produce_stage1_attempt(row,tok,prov,p.default_runtime_factory,planner,scorer))
        print(json.dumps({'attempted':n,'total':32}),flush=True)
    packets=p.apply_stage2(tok,packets)
    from replay_residual_natural_packet_validator_v2_1 import validate_packet_directory
    p.atomic_publish_packet_set(ROOT,packets,final_rel=OUT,validator_fn=validate_packet_directory,tokenizer=tok)
    q=[int(x['frozen_index']) for x in packets if bool(x.get('qualified'))]
    e=[int(x['frozen_index']) for x in packets if bool(x.get('trajectory_eligible'))]
    status='T1_DEVELOPMENT_READY_FOR_CAUSAL_GRID' if len(q)>=16 else 'INCONCLUSIVE_T1_DEVELOPMENT_EXPRESSIVITY'
    out={
      'kind':'PLANCARRY_REPLAY_RESIDUAL_T1_USER_DIRECTED_GATE_OVERRIDE_DEV_V1',
      'status':status,'attempted_n':32,'trajectory_eligible_n':len(e),'qualified_count':len(q),
      'qualified_indices':q,'minimum_required':16,
      't1_prereg_sha256':'77a7d9c9ee597551da8e8ef0b8a2c79038990968e3f62735ff90ed8c9c7d55e2',
      'population_binding_sha256':hashlib.sha256(BIND.read_bytes()).hexdigest(),
      'producer_sha256':hashlib.sha256((ROOT/'replay_residual_natural_packet_producer_v2_1.py').read_bytes()).hexdigest(),
      'runtime_sha256':hashlib.sha256((ROOT/'alfworld_runtime.py').read_bytes()).hexdigest(),
      'user_directed_override':True,
      'original_prereg_sanity_activation_gate_satisfied':False,
      'interpretation':'Scientific T1 development natural-checkpoint gate under explicit user-directed activation override; does not retroactively satisfy original sanity prerequisite.',
      'no_replacement':True,'reserve_52_63_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,
    }
    sha=fsync_json_new(SUMMARY,out)
    print(json.dumps({'T1_DEV_TERMINAL':out,'summary_sha256':sha}),flush=True)
    return 0
if __name__=='__main__': raise SystemExit(main())
