#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from typing import Any,Mapping,Sequence
import localcontinuation_controls_v2 as controls
import localcontinuation_science_driver_v2 as inherited_v2
import localcontinuation_science_driver_v1 as runtime_v1
import replay_residual_natural_packet_producer_v2_1 as v21
import planunique_packet_builder_v1 as pb
import planunique_projection_v1 as projection
import planunique_phase_runner_v1 as phase

ROOT=Path(__file__).resolve().parent
MODEL_ID='Qwen/Qwen3-1.7B';MODEL_REVISION='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e';MODEL_DTYPE='bfloat16'
LAYERS=phase.LAYERS;ALPHAS=phase.ALPHAS;ACTIVE=phase.ACTIVE;NO_PATCH=phase.NO_PATCH;SPEC=phase.SPEC
PACKET_DIR={'development':Path('results/science/plancarry_planunique_v1_2_development_packets'),'confirmation':Path('results/science/plancarry_planunique_v1_2_confirmation_packets')}
DEV_PAYLOAD=Path('results/science/plancarry_planunique_v1_2_development_grid.json');DEV_SEAL=Path('results/science/plancarry_planunique_v1_2_development_selection.json');DEV_TERMINAL=Path('results/science/plancarry_planunique_v1_2_development_terminal.json')
CONF_PAYLOAD=Path('results/science/plancarry_planunique_v1_2_confirmation.json');CONF_TERMINAL=Path('results/science/plancarry_planunique_v1_2_confirmation_terminal.json')
class ExecutionContractError(RuntimeError):pass
class _NoSemanticTokenizer:
 def encode(self,*a,**k):raise AssertionError('STAGE2_SEMANTIC_RETOKENIZATION_FORBIDDEN')
 def __call__(self,*a,**k):raise AssertionError('STAGE2_SEMANTIC_RETOKENIZATION_FORBIDDEN')

def sha_file(p:str|Path)->str:return pb.sha_file(p)
def git_head()->str:return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def _atomic(path:Path,obj:Any)->str:return phase.atomic_write_new(ROOT/path,obj)
def verify_sources()->dict[str,Any]:
 pb.verify_bindings(ROOT)
 if sha_file(ROOT/'localcontinuation_science_driver_v1.py')!='7768a45cd41048ebcabd27a0be6602b41642fa95f425883e199a94c3c2291592':raise ExecutionContractError('RUNTIME_V1_DRIFT')
 if sha_file(ROOT/'localcontinuation_controls_v2.py')!=pb.CONTROLS_SHA256:raise ExecutionContractError('V2_CONTROLS_DRIFT')
 return {'authority_commit':pb.AUTHORITY_COMMIT,'authority_review_sha256':projection.AUTHORITY_REVIEW_SHA256,'population_sha256':pb.POPULATION_SHA256,'model':MODEL_ID,'revision':MODEL_REVISION}

def preflight()->dict[str,Any]:
 b=verify_sources(); return {'kind':'PLANUNIQUE_V1_2_PREFLIGHT','status':'READY_NO_SCIENCE',**b,'model_calls':0,'model_loads':0,'environment_execution':0,'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False}

def _write_packet_set(packets:Sequence[Mapping[str,Any]],target:Path,phase_name:str)->dict[str,Any]:
 p=ROOT/target;tmp=p.with_name('.'+p.name+'.inprogress')
 if p.exists() or tmp.exists():raise ExecutionContractError(f'PACKET_OUTPUT_EXISTS:{target}')
 tmp.mkdir(parents=True)
 try:
  hashes={}
  for row in packets:
   i=int(row['frozen_index']);raw=json.dumps(row,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False).encode()+b'\n';fn=f'packet_{i:02d}.json';(tmp/fn).write_bytes(raw);hashes[fn]=hashlib.sha256(raw).hexdigest()
  man={'kind':'PLANCARRY_PLANUNIQUE_PACKET_SET_V1_2','phase':phase_name,'indices':[int(x['frozen_index']) for x in packets],'packet_sha256':hashes,'stage1_eligible_count':sum(bool(x.get('trajectory_eligible')) for x in packets),'semantic_stage2_qualified_count':sum(bool(x.get('qualified')) for x in packets),'population_sha256':pb.POPULATION_SHA256,'authority_commit':pb.AUTHORITY_COMMIT}
  (tmp/'manifest.json').write_text(json.dumps(man,sort_keys=True,indent=2)+'\n');os.rename(tmp,p);return man
 except Exception:shutil.rmtree(tmp,ignore_errors=True);raise

def produce_packets(phase_name:str,tok:Any,model:Any,prov:Mapping[str,Any])->list[dict[str,Any]]:
 rows=pb.load_population_phase(phase_name,ROOT);opening,closing=controls.frozen_tag_ids(tok);planner=lambda task,obs:v21.torch_generate_plan(tok,model,task,obs);scorer=lambda prefix,suffix:_suffix_mean_logprob_vram_bounded(model,prefix,suffix);stage1=[]
 for pos,row in enumerate(rows,1):
  stage1.append(pb.produce_stage1_attempt(row,phase_name,tok,prov,runtime_v1.runtime_factory,planner,scorer,opening,closing));print(json.dumps({'stage':'planunique_stage1','phase':phase_name,'done':pos,'total':len(rows)}),flush=True)
 packets=pb.apply_stage2_phase(stage1,phase_name,controls.NEUTRAL_FILLER_IDS,ROOT);pb.validate_phase_packets(packets,phase_name,ROOT);_write_packet_set(packets,PACKET_DIR[phase_name],phase_name);return packets

def _donor(packet:Mapping[str,Any],by:Mapping[int,Mapping[str,Any]])->Mapping[str,Any]:
 cp=packet.get('control_provenance',{});i=int(cp.get('unrelated_donor_frozen_index',-1))
 if i not in by or i==int(packet['frozen_index']) or str(by[i]['family'])==str(packet['family']):raise ExecutionContractError('DONOR_INVALID')
 return by[i]

def _suffix_mean_logprob_vram_bounded(model:Any,prefix_ids:Sequence[int],suffix_ids:Sequence[int])->float:
    """Exact frozen FP32 suffix log-probability while materializing only required LM-head rows.

    Qwen3 ``logits_to_keep`` changes only which final hidden-state rows are sent through
    the unchanged LM head.  The transformer sees the exact same full token sequence.
    Required prediction positions are prefix_len-1 .. prefix_len+suffix_len-2, exactly
    matching replay_residual_natural_packet_producer_v2_1.torch_suffix_mean_logprob.
    """
    import math,torch
    p=[int(x) for x in prefix_ids];s=[int(x) for x in suffix_ids]
    if not p or not s:raise RuntimeError('EMPTY_PREFIX_OR_SUFFIX')
    device=next(model.parameters()).device
    full=torch.tensor([p+s],dtype=torch.long,device=device)
    keep=torch.arange(len(p)-1,len(p)+len(s)-1,dtype=torch.long,device=device)
    with torch.inference_mode():
        logits=model(input_ids=full,logits_to_keep=keep).logits.float()
        if tuple(logits.shape[:2])!=(1,len(s)):raise RuntimeError(f'VRAM_SCORE_LOGIT_GEOMETRY:{tuple(logits.shape)}:{len(s)}')
        logp=torch.log_softmax(logits,dim=-1)
        row=torch.arange(len(s),device=logp.device)
        target=torch.tensor(s,dtype=torch.long,device=logp.device)
        score=logp[0,row,target].mean()
    value=float(score.detach().cpu().item())
    if not math.isfinite(value):raise RuntimeError('NONFINITE_CANDIDATE_SCORE')
    return value

def capture_sources(tok:Any,model:Any,packet:Mapping[str,Any],donor:Mapping[str,Any],layers:Sequence[int]):return inherited_v2.capture_sources_v2(tok,model,packet,donor,layers)
def _vector_sha(v:Any)->str:
 from replay_residual_t1_session_runtime_v1 import vector_sha256_fp32
 return vector_sha256_fp32(v)
def _construct(source:Mapping[str,Any],packet:Mapping[str,Any],layer:int):
 try:return projection.vectors_for_grid(source,packet,layer),None
 except projection.PlanUniqueProjectionError as e:
  if str(e).startswith('REQUIRED_CONTROL_ZERO:'):return None,str(e)
  raise

def _base(tok:Any,p:Mapping[str,Any]):return runtime_v1.base_reset(tok,p)
def _run_msa(tok:Any,model:Any,p:Mapping[str,Any],base:Mapping[str,Any],layer:int,alpha:float,vpack:Mapping[str,Any])->dict[str,Any]:
 vectors=vpack['vectors'];asha=_vector_sha(vectors[ACTIVE]);arms={}
 for arm in (ACTIVE,NO_PATCH,*SPEC):arms[arm]=runtime_v1.msa2_arm(tok,model,p,base,layer,None if arm==NO_PATCH else vectors[arm],alpha,arm,asha)
 return {'arms':arms,'zero_unique':bool(vpack['zero_unique']),'unique_l2':float(vpack['unique_l2']),'active_residual_sha256':asha,'reset_snapshot_sha256':base['reset_snapshot_sha256']}

def development(tok:Any,model:Any,prov:Mapping[str,Any])->dict[str,Any]:
 for p in (*PACKET_DIR.values(),DEV_PAYLOAD,DEV_SEAL,DEV_TERMINAL):
  if (ROOT/p).exists():raise ExecutionContractError(f'OUTPUT_EXISTS:{p}')
 packets=produce_packets('development',tok,model,prov);by={int(x['frozen_index']):x for x in packets};sem=[i for i in phase.DEV if bool(by[i].get('qualified'))]
 sources={};construct={l:{} for l in LAYERS};layer_ok={l:[] for l in LAYERS}
 for i in sem:
  pkt=by[i];srcs=capture_sources(tok,model,pkt,_donor(pkt,by),LAYERS);sources[i]=srcs
  for l in LAYERS:
   vp,reason=_construct(srcs[l],pkt,l);construct[l][i]={'vectors':vp,'reason':reason}
   if vp is not None:layer_ok[l].append(i)
 e=phase.freeze_e_common(layer_ok)
 payload={'phase':'PLANUNIQUE_DEVELOPMENT_V1_2','families':[{'index':i,'stage1_eligible':bool(by[i].get('trajectory_eligible')),'semantic_stage2_qualified':bool(by[i].get('qualified'))} for i in phase.DEV],'layer_constructible_indices':layer_ok,'e_common_indices':e,'grid_results':{},'plumbing_sentinels_pass':False,'authority_commit':pb.AUTHORITY_COMMIT,'population_sha256':pb.POPULATION_SHA256,'model_provenance':dict(prov),'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False}
 if len(e)<24:
  _atomic(DEV_PAYLOAD,payload);term=phase.select_development(payload);_atomic(DEV_TERMINAL,term);return term
 sentinel_pass=True
 for l in LAYERS:
  for i in e:
   try:runtime_v1.sentinels(model,_base(tok,by[i]),l)
   except Exception:sentinel_pass=False;raise
 payload['plumbing_sentinels_pass']=sentinel_pass
 for l in LAYERS:
  for a in ALPHAS:
   key=phase.grid_key(l,a);rows={}
   for i in e:rows[str(i)]=_run_msa(tok,model,by[i],_base(tok,by[i]),l,a,construct[l][i]['vectors'])
   payload['grid_results'][key]=rows
 _atomic(DEV_PAYLOAD,payload);term=phase.select_development(payload,ROOT/DEV_SEAL);_atomic(DEV_TERMINAL,term);return term

def confirmation(tok:Any,model:Any,prov:Mapping[str,Any])->dict[str,Any]:
 if not (ROOT/DEV_SEAL).is_file():raise ExecutionContractError('CONFIRMATION_REQUIRES_DEVELOPMENT_SEAL')
 if (ROOT/CONF_PAYLOAD).exists() or (ROOT/CONF_TERMINAL).exists() or (ROOT/PACKET_DIR['confirmation']).exists():raise ExecutionContractError('CONFIRMATION_OUTPUT_EXISTS')
 seal=json.loads((ROOT/DEV_SEAL).read_text());
 if seal.get('status')!='FROZEN_PLANUNIQUE_DEVELOPMENT_SELECTION' or seal.get('authority_commit')!=pb.AUTHORITY_COMMIT or seal.get('population_sha256')!=pb.POPULATION_SHA256:raise ExecutionContractError('DEVELOPMENT_SEAL_INVALID')
 layer=int(seal['selected_layer']);alpha=float(seal['selected_alpha']);packets=produce_packets('confirmation',tok,model,prov);by={int(x['frozen_index']):x for x in packets};vps={};sources={}
 for i in phase.CONF:
  if not bool(by[i].get('qualified')):continue
  src=capture_sources(tok,model,by[i],_donor(by[i],by),[layer])[layer];sources[i]=src;vp,reason=_construct(src,by[i],layer)
  if vp is not None:vps[i]=vp
 if len(vps)<15:
  fam=[{'index':i,'stage2_qualified':i in vps,'zero_unique':bool(vps[i]['zero_unique']) if i in vps else False} for i in phase.CONF];payload={'phase':'PLANUNIQUE_CONFIRMATION_V1_2','families':fam,'selected_layer':layer,'selected_alpha':alpha};_atomic(CONF_PAYLOAD,payload);term=phase.evaluate_confirmation(payload);_atomic(CONF_TERMINAL,term);return term
 fam=[]
 for i in phase.CONF:
  if i not in vps:fam.append({'index':i,'stage2_qualified':False,'zero_unique':False});continue
  vp=vps[i];base=_base(tok,by[i]);asha=_vector_sha(vp['vectors'][ACTIVE]);outs={}
  for arm in (ACTIVE,NO_PATCH,*SPEC):outs[arm]=runtime_v1.autonomous_arm(tok,model,by[i],base,layer,None if arm==NO_PATCH else vp['vectors'][arm],alpha,arm,asha)
  fam.append({'index':i,'stage2_qualified':True,'zero_unique':bool(vp['zero_unique']),'active_lca2':float(outs[ACTIVE]['lca2']),'no_patch_lca2':float(outs[NO_PATCH]['lca2']),'max_specificity_lca2':max(float(outs[a]['lca2']) for a in SPEC),'active_valid_action_rate':float(outs[ACTIVE]['valid_action_rate']),'no_patch_valid_action_rate':float(outs[NO_PATCH]['valid_action_rate'])})
 payload={'phase':'PLANUNIQUE_CONFIRMATION_V1_2','families':fam,'selected_layer':layer,'selected_alpha':alpha,'development_seal_sha256':sha_file(ROOT/DEV_SEAL)};_atomic(CONF_PAYLOAD,payload);term=phase.evaluate_confirmation(payload);_atomic(CONF_TERMINAL,term);return term

def load_runtime(expected_device:str):return runtime_v1.load_runtime(expected_device)
def main(argv:Sequence[str]|None=None)->int:
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['preflight','development','confirmation']);ap.add_argument('--expected-device',default=os.environ.get('PLANUNIQUE_EXPECTED_DEVICE_NAME',''));args=ap.parse_args(argv)
 if args.phase=='preflight':print(json.dumps({'PLANUNIQUE_PREFLIGHT':preflight()},sort_keys=True));return 0
 auth=os.environ.get('PLANUNIQUE_DEVELOPMENT_AUTHORIZATION' if args.phase=='development' else 'PLANUNIQUE_CONFIRMATION_AUTHORIZATION')
 if auth!='RESEARCH_DECISION_BOUND':raise ExecutionContractError('RESEARCH_DECISION_BOUND_AUTHORIZATION_REQUIRED')
 if not args.expected_device:raise ExecutionContractError('EXPECTED_DEVICE_REQUIRED')
 verify_sources();tok,model,prov=load_runtime(args.expected_device);result=development(tok,model,prov) if args.phase=='development' else confirmation(tok,model,prov);print(json.dumps({'PLANUNIQUE_TERMINAL':result},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
