#!/usr/bin/env python3
"""NON-SCIENTIFIC full-path GPU memory canary for Grounded ActionMatched-v2.

Uses synthetic text/token content only: no ALFWorld game/reset and no scientific population.
Exercises exact Qwen load, greedy generation, four-layer capture, persistent-KV scoring,
and one intervention session repeatedly. It fails closed on OOM or insufficient VRAM headroom.
"""
from __future__ import annotations
import argparse, gc, json, time
from typing import Any

import torch
import action_matched_grounded_v2_optimized_runtime_v1 as am
import action_matched_grounded_v2_optimized_science_driver_v1 as drv
import action_matched_grounded_v2_optimization_v1 as opt

LAYERS=(7,14,21,27)

def _ids(tok:Any,text:str)->list[int]: return [int(x) for x in tok.encode(text,add_special_tokens=False)]

def _synthetic_commands(n:int=24)->list[str]:
    return [f"take synthetic object {i} from synthetic receptacle {i%7}" for i in range(n)]

def _one_iteration(tok:Any,model:Any,rep:int,counter:dict[str,int])->None:
    device=next(model.parameters()).device
    # Representative generation path without parsing/study semantics.
    body=("SYNTHETIC MEMORY CANARY. Produce deterministic diagnostic tokens only. "*80)+f" iteration={rep}"
    prefix=[int(x) for x in tok.apply_chat_template([{'role':'user','content':body}],tokenize=True,add_generation_prompt=True,enable_thinking=False)]
    with torch.inference_mode():
        out=model.generate(input_ids=torch.tensor([prefix],dtype=torch.long,device=device),do_sample=False,max_new_tokens=128,use_cache=True,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id)
    del out

    # Representative source lengths + all four capture sites in one forward per side.
    seed=_ids(tok,("SYNTHETIC SOURCE STATE ACTION HISTORY FUTURE PLAN "*90))
    if len(seed)<256: raise RuntimeError('CANARY_SOURCE_TOO_SHORT')
    A=seed[:min(len(seed),768)]
    B=list(A); B[-8:]=list(reversed(B[-8:]))
    vecs=am.capture_pair_residuals(model,A,B,LAYERS)

    commands=_synthetic_commands()
    reset=am.render_reset('synthetic task', 'synthetic observation '+('x '*180), commands)
    reset_prefix,tail=am.split_reset_action(tok,reset)
    sess=am.PersistentTokenSession(model,reset_prefix,layer=0,vector=None)
    try:
        sess.append_ids(tail,event='CANARY_ACTION_PROMPT')
        sess.score_candidates(am.action_suffixes(tok,commands))
    finally:
        if not sess.closed: sess.close()

    # One intervention-bearing session exercises hook + KV + exact scorer geometry.
    v=vecs[LAYERS[1]]
    sess=am.PersistentTokenSession(model,reset_prefix,layer=LAYERS[1],vector=v,mode='add',scale=1.0)
    try:
        sess.append_ids(tail,event='CANARY_INTERVENTION_ACTION_PROMPT')
        sess.score_candidates(am.action_suffixes(tok,commands))
    finally:
        if not sess.closed: sess.close()
    del vecs, sess, prefix, A, B, seed

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--expected-device',default='NVIDIA GeForce RTX 5060')
    ap.add_argument('--repetitions',type=int,default=10)
    ap.add_argument('--minimum-free-mb',type=float,default=opt.MINIMUM_FREE_VRAM_MB)
    args=ap.parse_args()
    if args.repetitions<2: raise SystemExit('repetitions must be >=2')
    tok,model,_prov=drv.load_model(args.expected_device)
    device=next(model.parameters()).device
    if getattr(device,'type',str(device))!='cuda': raise RuntimeError('CUDA_REQUIRED')
    forwards={'n':0}
    def pre_hook(_m,_args): forwards['n']+=1
    h=model.register_forward_pre_hook(pre_hook)
    samples=[]; oom_events=0; start_alloc=float(torch.cuda.memory_allocated(device))/(1024**2)
    t0=time.perf_counter()
    try:
        for rep in range(args.repetitions):
            opt.reset_cuda_peak_memory(device)
            try:
                _one_iteration(tok,model,rep,forwards)
                snap=opt.require_cuda_headroom(device,minimum_free_mb=args.minimum_free_mb)
            except Exception as exc:
                if exc.__class__.__name__=='OutOfMemoryError' or 'out of memory' in str(exc).lower(): oom_events+=1
                raise
            samples.append(dict(iteration=rep,**snap))
            gc.collect(); torch.cuda.empty_cache(); torch.cuda.synchronize(device)
    finally:
        h.remove()
    elapsed=time.perf_counter()-t0
    final_alloc=float(torch.cuda.memory_allocated(device))/(1024**2)
    report={
      'kind':'ACTION_MATCHED_GROUNDED_V2_FULL_PATH_MEMORY_CANARY_V1',
      'scientific_execution':False,'alfworld_access':False,'repetitions':args.repetitions,
      'peak_allocated_mb':max(float(x['peak_allocated_mb']) for x in samples),
      'peak_reserved_mb':max(float(x['peak_reserved_mb']) for x in samples),
      'minimum_free_vram_mb':min(float(x['free_mb']) for x in samples),
      'minimum_peak_reserved_headroom_mb':min(float(x['peak_reserved_headroom_mb']) for x in samples),
      'oom_events':oom_events,'forward_count':forwards['n'],'elapsed_seconds':elapsed,
      'final_allocated_mb':final_alloc,
      'memory_growth_after_repetitions_mb':final_alloc-start_alloc,
      'required_minimum_free_mb':float(args.minimum_free_mb),
      'samples':samples,
    }
    print(json.dumps(report,sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
