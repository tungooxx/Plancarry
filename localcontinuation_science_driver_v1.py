#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,math,os,sys
from pathlib import Path
from typing import Any,Mapping,Sequence
import localcontinuation_packet_builder_v1 as pb
import localcontinuation_phase_runner_v1 as phase

ROOT=Path(__file__).resolve().parent
PACKET_DIR={'development':Path('results/science/plancarry_replayresidual_localcontinuation_dev_packets_v1'),'confirmation':Path('results/science/plancarry_replayresidual_localcontinuation_confirmation_packets_v1'),'reserve':Path('results/science/plancarry_replayresidual_localcontinuation_reserve_packets_v1')}
DEV_PAYLOAD=Path('results/science/plancarry_replayresidual_localcontinuation_development_grid_v1.json')
DEV_SEAL=Path('results/science/plancarry_replayresidual_localcontinuation_development_selection_v1.json')
DEV_TERMINAL=Path('results/science/plancarry_replayresidual_localcontinuation_development_terminal_v1.json')
CONF_PAYLOAD=Path('results/science/plancarry_replayresidual_localcontinuation_confirmation_payload_v1.json')
CONF_RESULT=Path('results/science/plancarry_replayresidual_localcontinuation_primary_result_v1.json')
RES_PAYLOAD=Path('results/science/plancarry_replayresidual_localcontinuation_replication_payload_v1.json')
RES_RESULT=Path('results/science/plancarry_replayresidual_localcontinuation_replication_result_v1.json')
MODEL_ID='Qwen/Qwen3-1.7B';MODEL_REVISION='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e';MODEL_DTYPE='bfloat16';TRANSFORMERS_VERSION='4.51.3';TOKENIZERS_VERSION='0.21.1';TORCH_VERSION='2.13.0+cu130'
LAYERS=phase.LAYERS;ALPHAS=phase.ALPHAS
SEMANTIC={'NEXT_ACTION_PRESERVED_LATE_NULL':'NEXT_ACTION_PRESERVED_LATE_NULL','UNRELATED_PLAN':'UNRELATED_PLAN','SHUFFLED_PLAN':'SHUFFLED_PLAN','GENERIC_HISTORY':'GENERIC_HISTORY'}

class ExecutionContractError(RuntimeError):pass

def sha_file(p:str|Path)->str:return pb.sha_file(p)
def atomic(path:Path,obj:Any)->str:return phase.atomic_write_new(ROOT/path,obj)
def _ids(tok:Any,text:str)->list[int]:
 out=tok.encode(text,add_special_tokens=False)
 return [int(x) for x in out]
def suffix_map(tok:Any,commands:Sequence[str])->dict[str,list[int]]:
 out={}
 for c in sorted(str(x) for x in commands):
  ids=_ids(tok,' '+c)
  if not ids:raise ExecutionContractError('EMPTY_ACTION_SUFFIX')
  out[c]=ids
 return out
def continuation_ids(tok:Any,observation:str,commands:Sequence[str])->list[int]:
 import replay_residual_sanity_protocol_v1 as sp
 text='\nOBSERVATION: '+str(observation).strip()+'\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+'\nACTION:'
 ids=sp.tok_encode(tok,text)
 if not ids:raise ExecutionContractError('EMPTY_CONTINUATION_IDS')
 return ids

def expected_source_hashes()->dict[Path,str]:
 return {ROOT/'replay_residual_natural_packet_producer_v2_1.py':pb.PRODUCER_SHA256,ROOT/'replay_residual_sanity_protocol_v1.py':pb.PROTOCOL_SHA256,ROOT/'replay_residual_t1_session_runtime_v1.py':pb.SESSION_SHA256,ROOT/'alfworld_runtime.py':pb.ALFWORLD_RUNTIME_SHA256,ROOT/'textworld_py313_compat.py':pb.TEXTWORLD_COMPAT_SHA256}
def verify_sources()->None:
 pb.verify_bindings(ROOT)
 for p,e in expected_source_hashes().items():
  g=sha_file(p)
  if g!=e:raise ExecutionContractError(f'FROZEN_SOURCE_DRIFT:{p}:{g}:{e}')

def execution_provenance(model_provenance:Mapping[str,Any])->dict[str,Any]:
 return {
  'schema':'PLANCARRY_LOCALCONTINUATION_EXECUTION_PROVENANCE_V1',
  'driver_sha256':sha_file(Path(__file__)),
  'packet_builder_sha256':sha_file(ROOT/'localcontinuation_packet_builder_v1.py'),
  'phase_runner_sha256':sha_file(ROOT/'localcontinuation_phase_runner_v1.py'),
  'validator_sha256':sha_file(ROOT/'localcontinuation_validator_v1.py'),
  'session_runtime_sha256':pb.SESSION_SHA256,
  'natural_packet_producer_sha256':pb.PRODUCER_SHA256,
  'sanity_protocol_sha256':pb.PROTOCOL_SHA256,
  'alfworld_runtime_sha256':pb.ALFWORLD_RUNTIME_SHA256,
  'textworld_compat_sha256':pb.TEXTWORLD_COMPAT_SHA256,
  'vector_schema':'ACTIVE=h_PLAN_PRESENT(t2)-h_NEUTRAL_FILLER(t2),FP32; nonzero semantic/random controls active-norm matched; zero active retained/nonpositive',
  'control_schema':'ACTIVE,NO_PATCH,ZERO_ADD,SELF_REPLACE,RANDOM_EQ_NORM,NEXT_ACTION_PRESERVED_LATE_NULL,UNRELATED_PLAN,SHUFFLED_PLAN,GENERIC_HISTORY,VISIBLE_TEXT_PLAN',
  'session_schema':'one reset-prefix intervention at selected layer/last-token-before-ACTION; same persistent KV thereafter; no reinjection',
  'model_provenance':dict(model_provenance),
 }

def execution_binding(model_provenance:Mapping[str,Any])->dict[str,Any]:
 ep=execution_provenance(model_provenance)
 return {'execution_provenance':ep,'execution_provenance_sha256':phase.sha_json(ep)}

def load_runtime(expected_device:str):
 import torch,transformers,tokenizers as tokenizers_pkg
 from transformers import AutoModelForCausalLM,AutoTokenizer
 if str(torch.__version__)!=TORCH_VERSION:raise ExecutionContractError(f'TORCH_VERSION_MISMATCH:{torch.__version__}:{TORCH_VERSION}')
 if str(transformers.__version__)!=TRANSFORMERS_VERSION:raise ExecutionContractError(f'TRANSFORMERS_VERSION_MISMATCH:{transformers.__version__}:{TRANSFORMERS_VERSION}')
 if str(tokenizers_pkg.__version__)!=TOKENIZERS_VERSION:raise ExecutionContractError(f'TOKENIZERS_VERSION_MISMATCH:{tokenizers_pkg.__version__}:{TOKENIZERS_VERSION}')
 if not torch.cuda.is_available():raise ExecutionContractError('CUDA_REQUIRED')
 device=torch.cuda.get_device_name(0)
 if device!=expected_device:raise ExecutionContractError(f'EXPECTED_DEVICE_MISMATCH:{device}:{expected_device}')
 tok=AutoTokenizer.from_pretrained(MODEL_ID,revision=MODEL_REVISION,trust_remote_code=False)
 model=AutoModelForCausalLM.from_pretrained(MODEL_ID,revision=MODEL_REVISION,torch_dtype=torch.bfloat16,trust_remote_code=False).to('cuda');model.eval()
 prov={'model_id':MODEL_ID,'revision':MODEL_REVISION,'dtype':MODEL_DTYPE,'transformers_version':TRANSFORMERS_VERSION,'tokenizers_version':TOKENIZERS_VERSION,'torch_version':TORCH_VERSION,'quantization':'NONE','offload':'NONE','enable_thinking':False,'device_name':device}
 return tok,model,prov

def runtime_factory(game_path:str):
 from alfworld_runtime import AlfRuntime,ACTIVE_DATA_ROOT
 p=Path(game_path)
 if p.is_absolute() or '..' in p.parts:raise ExecutionContractError('NONCANONICAL_GAME_PATH')
 full=ACTIVE_DATA_ROOT/p
 return AlfRuntime(str(full),max_steps=12)

def produce_packets(phase_name:str,tok:Any,model:Any,prov:Mapping[str,Any])->list[dict[str,Any]]:
 import replay_residual_natural_packet_producer_v2_1 as v21
 builder_phase='reserve_replication' if phase_name=='reserve' else phase_name
 planner=lambda task,obs:v21.torch_generate_plan(tok,model,task,obs)
 scorer=lambda pre,suf:v21.torch_suffix_mean_logprob(model,pre,suf)
 packets=pb.build_phase_packets(builder_phase,tok,prov,runtime_factory,planner,scorer,ROOT,lambda d,t:print(json.dumps({'stage':'local_reference','phase':phase_name,'done':d,'total':t}),flush=True))
 target,manifest=pb.atomic_publish_packet_set(ROOT,builder_phase,packets,PACKET_DIR[phase_name])
 print(json.dumps({'stage':'packet_set_frozen','phase':phase_name,'path':str(target.relative_to(ROOT)),'manifest_semantic_sha256':pb.sha_json(manifest),'qualified':sum(bool(x.get('qualified')) for x in packets)}),flush=True)
 return packets

def replay_to_reset(packet:Mapping[str,Any]):
 rt=runtime_factory(str(packet['game_path']))
 try:
  for j,row in enumerate(packet['actions'][:2]):
   if rt.hash()!=str(row['pre_state_hash']):raise ExecutionContractError(f'REPLAY_PRESTATE_MISMATCH:{j}')
   rec=rt.step(str(row['command']))
   if rec.error or rec.state_hash!=str(row['post_state_hash']):raise ExecutionContractError(f'REPLAY_POSTSTATE_MISMATCH:{j}')
  return rt
 except Exception:
  rt.close();raise

def exact_reset_tokens(tok:Any,packet:Mapping[str,Any],obs:str,commands:Sequence[str],visible_plan_slot_text:str|None=None):
 import replay_residual_sanity_protocol_v1 as sp
 prefix=''
 if visible_plan_slot_text is not None:prefix='VISIBLE PLAN SLOT\n'+visible_plan_slot_text+'\n'
 block=prefix+'TASK\n'+str(packet['task_instruction']).strip()+'\nCURRENT OBSERVATION\n'+str(obs).strip()+'\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+'\n<STATE_END>'
 full=block+'\nACTION:';ids=sp.tok_encode(tok,full);cand=[]
 for k in range(1,len(ids)):
  if sp.tok_decode(tok,ids[:k]).endswith('<STATE_END>\n') and sp.tok_decode(tok,ids[k:])=='ACTION:':cand.append(k)
 if len(cand)!=1:raise ExecutionContractError(f'RESET_ACTION_TOKEN_SPLIT_NOT_UNIQUE:{cand}')
 k=cand[0]
 if sp.tok_decode(tok,ids)!=full:raise ExecutionContractError('RESET_FULL_TOKEN_ROUNDTRIP_FAILED')
 return full,ids[:k],ids[k:]

def base_reset(tok:Any,packet:Mapping[str,Any],visible_plan_slot_ids:Sequence[int]|None=None)->dict[str,Any]:
 from replay_residual_t1_session_runtime_v1 import token_ids_sha256
 import replay_residual_sanity_protocol_v1 as sp
 rt=replay_to_reset(packet)
 try:
  obs=str(rt.observation);commands=sorted(str(x) for x in rt.admissible_commands);state=rt.hash();full,prefix,tail=exact_reset_tokens(tok,packet,obs,commands,None)
  visible_sha=None
  if visible_plan_slot_ids is not None:
   slot=[int(x) for x in visible_plan_slot_ids]
   if len(slot)!=128:raise ExecutionContractError('VISIBLE_PLAN_SLOT_NOT_EXACT128')
   head=sp.tok_encode(tok,'VISIBLE PLAN SLOT (EXACT 128 TOKENS)\n');sep=sp.tok_encode(tok,'\n')
   prefix=head+slot+sep+prefix;visible_sha=token_ids_sha256(slot)
   full='VISIBLE PLAN SLOT (EXACT 128 TOKENS)\n'+sp.tok_decode(tok,slot)+'\n'+full
  return {'observation':obs,'commands':commands,'state_hash':state,'prefix_ids':prefix,'action_prompt_ids':tail,'reset_prefix_sha256':token_ids_sha256(prefix),'reset_snapshot_sha256':hashlib.sha256(json.dumps({'world_state_sha256':state,'current_observation':obs,'admissible_actions':commands,'task_instruction':str(packet['task_instruction']).strip(),'reset_serialization':full},sort_keys=True,separators=(',',':')).encode()).hexdigest(),'reset_serialization':full,'visible_plan_slot_token_ids_sha256':visible_sha}
 finally:rt.close()

def capture_sources(tok:Any,model:Any,packet:Mapping[str,Any],donor_plan:str,layers:Sequence[int])->dict[int,dict[str,Any]]:
 import torch,replay_residual_sanity_protocol_v1 as sp
 from replay_residual_t1_session_runtime_v1 import capture_activation_ids,vector_sha256_fp32
 conditions=('PLAN_PRESENT','NEUTRAL_FILLER','SHUFFLED_PLAN','UNRELATED_PLAN','GENERIC_HISTORY','NEXT_ACTION_PRESERVED_LATE_NULL')
 slots=sp.build_condition_slots(tok,dict(packet),donor_plan,2);ids={c:sp.build_replay(tok,dict(packet),slots[c],2)[1] for c in conditions}
 if len({len(x) for x in ids.values()})!=1:raise ExecutionContractError('SOURCE_REPLAY_ALIGNMENT_FAILED')
 out={}
 for layer in layers:
  h={c:capture_activation_ids(model,ids[c],layer,-1).detach().float().cpu() for c in conditions};neutral=h['NEUTRAL_FILLER'];raw=h['PLAN_PRESENT']-neutral
  out[int(layer)]={'active':raw,'active_l2':float(torch.linalg.vector_norm(raw).item()),'active_sha256':vector_sha256_fp32(raw),'controls':{c:h[c]-neutral for c in conditions if c not in ('PLAN_PRESENT','NEUTRAL_FILLER')}}
 return out

def rescale_to(v:Any,target:float):
 import torch
 x=v.detach().float().cpu();n=float(torch.linalg.vector_norm(x).item())
 if target<=1e-8 or n<=1e-12:return torch.zeros_like(x),True
 y=x*(float(target)/n);got=float(torch.linalg.vector_norm(y).item());return y,abs(got-target)<=max(1e-5,1e-4*target)
def rademacher(dim:int,target:float,key:str):
 import torch
 signs=[];counter=0
 while len(signs)<dim:
  b=hashlib.sha256(f'{key}|{counter}'.encode()).digest();counter+=1
  for byte in b:
   for bit in range(8):
    signs.append(1.0 if ((byte>>bit)&1) else -1.0)
    if len(signs)>=dim:break
   if len(signs)>=dim:break
 x=torch.tensor(signs,dtype=torch.float32)
 if target<=1e-8:return torch.zeros_like(x)
 return x/torch.linalg.vector_norm(x)*float(target)

def sentinels(model:Any,base:Mapping[str,Any],layer:int)->tuple[float,float]:
 import torch
 from replay_residual_t1_session_runtime_v1 import PersistentTokenSession,capture_activation_ids
 b=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=None);b.append_ids(base['action_prompt_ids'],event='ACTION_SENTINEL');blog=b.next_logits.detach().float().cpu();bprov=b.provenance();b.close()
 z=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=torch.zeros(int(model.config.hidden_size),dtype=torch.float32));z.append_ids(base['action_prompt_ids'],event='ACTION_SENTINEL');zmax=float(torch.max(torch.abs(z.next_logits.detach().float().cpu()-blog)).item());zprov=z.provenance();z.close()
 selfv=capture_activation_ids(model,base['prefix_ids'],layer,-1).detach().float().cpu();s=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=selfv,mode='replace');s.append_ids(base['action_prompt_ids'],event='ACTION_SENTINEL');smax=float(torch.max(torch.abs(s.next_logits.detach().float().cpu()-blog)).item());sprov=s.provenance();s.close()
 if zmax>1e-6 or smax>1e-6 or zprov['cache_sha256']!=bprov['cache_sha256'] or sprov['cache_sha256']!=bprov['cache_sha256']:raise ExecutionContractError(f"PLUMBING_SENTINEL_FAIL:zero={zmax}:self={smax}:zero_cache={zprov['cache_sha256']==bprov['cache_sha256']}:self_cache={sprov['cache_sha256']==bprov['cache_sha256']}")
 return zmax,smax

def msa2_arm(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,arm:str,active_residual_sha256:str)->dict[str,Any]:
 from replay_residual_t1_session_runtime_v1 import PersistentTokenSession
 rt=replay_to_reset(packet);sess=None;rows=[]
 try:
  if rt.hash()!=base['state_hash'] or str(rt.observation)!=base['observation'] or sorted(str(x) for x in rt.admissible_commands)!=base['commands']:raise ExecutionContractError('ARM_RESET_STATE_MISMATCH')
  scale=alpha if vector is not None else 1.0;sess=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=vector,mode='add',scale=scale);sess.append_ids(base['action_prompt_ids'],event='ACTION_PROMPT_0')
  for ref_pos in (2,3):
   ref=packet['actions'][ref_pos]
   if rt.hash()!=str(ref['pre_state_hash']):raise ExecutionContractError(f'MSA2_REFERENCE_PRESTATE_MISMATCH:{ref_pos+1}')
   cmds=sorted(str(x) for x in rt.admissible_commands)
   if str(ref['command']) not in cmds:raise ExecutionContractError('REFERENCE_ACTION_NOT_ADMISSIBLE')
   sess.append_ids(suffix_map(tok,cmds)[str(ref['command'])],event=f'TEACHER_ACTION_{ref_pos+1}')
   rec=rt.step(str(ref['command']))
   if rec.error or rec.state_hash!=str(ref['post_state_hash']):raise ExecutionContractError('MSA2_TEACHER_REPLAY_MISMATCH')
   sess.append_ids(continuation_ids(tok,rt.observation,rt.admissible_commands),event=f'TEACHER_OBS_{ref_pos+1}')
   score_ref=packet['actions'][ref_pos+1];cmds2=sorted(str(x) for x in rt.admissible_commands)
   if rt.hash()!=str(score_ref['pre_state_hash']):raise ExecutionContractError('MSA2_SCORE_STATE_MISMATCH')
   if cmds2!=sorted(str(x) for x in score_ref['admissible_commands']):raise ExecutionContractError('MSA2_SCORE_ADMISSIBLE_MISMATCH')
   _best,scores=sess.score_candidates(suffix_map(tok,cmds2));scoremap={c:float(r.mean_logprob) for c,r in scores.items()}
   rows.append({'state_match':True,'admissible_match':True,'reference_action':str(score_ref['command']),'scores':scoremap})
  msa,margin=phase.matched_state_msa2(rows);prov=sess.close();sess=None
  return {'msa2':msa,'reference_action_margin_family':margin,'hook_count':int(prov['hook_count']),'session_id_hash':prov['session_id_hash'],'arm_name':arm,'selected_layer':int(layer),'selected_alpha':float(alpha),'active_residual_sha256':str(active_residual_sha256),'injected_vector_sha256':prov['injected_vector_sha256'],'reset_prefix_sha256':prov['reset_prefix_sha256'],'reset_snapshot_sha256':base['reset_snapshot_sha256']}
 finally:
  if sess is not None and not sess.closed:
   try:sess.close()
   except Exception:pass
  rt.close()
def autonomous_arm(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,arm:str,active_residual_sha256:str,mode:str='add',continue_to_budget:bool=False,external_reset_snapshot_sha256:str|None=None,session_scale:float|None=None)->dict[str,Any]:
 from replay_residual_t1_session_runtime_v1 import PersistentTokenSession
 rt=replay_to_reset(packet);sess=None;acts=[];accepted=0
 try:
  if rt.hash()!=base['state_hash']:raise ExecutionContractError('AUTON_RESET_STATE_MISMATCH')
  scale=1.0 if mode=='replace' else (alpha if vector is not None else 1.0)
  sess=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=vector,mode=mode,scale=scale);sess.append_ids(base['action_prompt_ids'],event='ACTION_PROMPT_0')
  limit=12 if continue_to_budget else 3
  for step in range(limit):
   if rt.done or rt.won:break
   cmds=sorted(str(x) for x in rt.admissible_commands)
   if not cmds:break
   pre=rt.hash();cmd,_scores,_=sess.choose_and_commit(suffix_map(tok,cmds),event=f'ACTION_{step+1}');rec=rt.step(cmd);ok=rec.error is None;accepted+=int(ok);acts.append({'command':cmd,'pre_state_hash':pre,'post_state_hash':rec.state_hash,'accepted':ok})
   if not ok or rt.done or rt.won:break
   sess.append_ids(continuation_ids(tok,rt.observation,rt.admissible_commands),event=f'OBS_{step+1}')
  primary_acts=acts[:3];lca=phase.local_continuation_lca2(packet['actions'][:5],primary_acts);primary_valid=sum(1 for x in primary_acts if x['accepted']);prov=sess.close();sess=None
  out={'lca2':lca,'task_success':1.0 if rt.won else 0.0,'valid_action_rate':float(primary_valid/len(primary_acts)) if primary_acts else 0.0,'generated_action_count':len(primary_acts),'descriptive_total_action_count':len(acts),'hook_count':int(prov['hook_count']),'session_id_hash':prov['session_id_hash'],'arm_name':arm,'selected_layer':int(layer),'selected_alpha':float(alpha),'active_residual_sha256':str(active_residual_sha256),'injected_vector_sha256':prov['injected_vector_sha256'],'reset_prefix_sha256':prov['reset_prefix_sha256'],'reset_snapshot_sha256':base['reset_snapshot_sha256'],'external_reset_snapshot_sha256':external_reset_snapshot_sha256,'visible_plan_slot_token_ids_sha256':base.get('visible_plan_slot_token_ids_sha256'),'first_action_excluded':True}
  if external_reset_snapshot_sha256 is not None:out['external_reset_snapshot_sha256']=str(external_reset_snapshot_sha256)
  if base.get('visible_plan_slot_token_ids_sha256') is not None:out['visible_plan_slot_token_ids_sha256']=base['visible_plan_slot_token_ids_sha256']
  return out
 finally:
  if sess is not None and not sess.closed:
   try:sess.close()
   except Exception:pass
  rt.close()
def vectors_for_grid(src:Mapping[str,Any],packet:Mapping[str,Any],layer:int)->dict[str,Any]:
 import torch
 raw=src['active'];norm=float(src['active_l2']);out={'ACTIVE_PLAN_RESIDUAL':raw}
 for arm,cond in SEMANTIC.items():
  out[arm],ok=rescale_to(src['controls'][cond],norm)
  if not ok:raise ExecutionContractError(f'CONTROL_NORM_GUARD_FAIL:{arm}')
 rand=rademacher(int(raw.numel()),norm,f"ReplayResidualLocalContinuation|RANDOM_EQ_NORM|{packet['family']}|{packet['game_path']}|L{layer}")
 if norm>1e-8 and abs(float(torch.linalg.vector_norm(rand).item())-norm)>max(1e-5,1e-4*norm):raise ExecutionContractError('RANDOM_NORM_GUARD_FAIL')
 out['RANDOM_EQ_NORM']=rand;return out

def donor_plan(packet:Mapping[str,Any],by:Mapping[int,Mapping[str,Any]])->str:
 idx=int(packet['control_provenance']['unrelated_donor_frozen_index'])
 if idx not in by or idx==int(packet['frozen_index']):raise ExecutionContractError('DONOR_INVALID')
 return str(by[idx]['plan_text'])

def visible_plan_slot_ids(tok:Any,packet:Mapping[str,Any],donor:str)->list[int]:
 import replay_residual_sanity_protocol_v1 as sp
 slots=sp.build_condition_slots(tok,dict(packet),donor,2)
 ids=[int(x) for x in slots['PLAN_PRESENT']]
 if len(ids)!=128:raise ExecutionContractError('VISIBLE_PLAN_SLOT_NOT_EXACT128')
 # Standalone roundtrip guarantees these are the exact frozen slot IDs; the descriptive ceiling inserts these IDs directly.
 sp.exact_token_text(tok,ids,label='visible_plan_slot')
 return ids

def development(tok:Any,model:Any,prov:Mapping[str,Any])->dict[str,Any]:
 if any((ROOT/p).exists() for p in (PACKET_DIR['development'],DEV_PAYLOAD,DEV_TERMINAL,DEV_SEAL)):raise ExecutionContractError('DEVELOPMENT_OUTPUT_EXISTS')
 packets=produce_packets('development',tok,model,prov);by={int(x['frozen_index']):x for x in packets};qualified=[i for i in phase.DEV if bool(by[i].get('qualified'))]
 families=[{'index':i,'qualified':i in qualified} for i in phase.DEV]
 bindings={'final_prereg_sha256':pb.FINAL_PREREG_SHA256,'final_review_sha256':pb.FINAL_REVIEW_SHA256,'population_manifest_sha256':pb.POPULATION_SHA256,'population_review_sha256':pb.POPULATION_REVIEW_SHA256}
 ep=execution_provenance(prov);eph=phase.sha_json(ep)
 if len(qualified)<16:
  payload={'phase':'LOCALCONTINUATION_DEVELOPMENT','families':families,'grid_results':{},'execution_provenance':ep,'execution_provenance_sha256':eph,'confirmation_accessed':False,'reserve_accessed':False,**bindings};atomic(DEV_PAYLOAD,payload);term=phase.select_development(payload);atomic(DEV_TERMINAL,term);return term
 bases={};sources={}
 for pos,i in enumerate(qualified,1):
  pkt=by[i];donor=donor_plan(pkt,by);bases[i]=base_reset(tok,pkt);sources[i]=capture_sources(tok,model,pkt,donor,LAYERS);print(json.dumps({'stage':'dev_source_base','done':pos,'qualified':len(qualified)}),flush=True)
 grids={}
 for layer in LAYERS:
  for alpha in ALPHAS:
   key=phase.grid_key(layer,alpha);rows={}
   for pos,i in enumerate(qualified,1):
    pkt=by[i];base=bases[i];src=sources[i][layer];active_sha=str(src['active_sha256']);vecs=vectors_for_grid(src,pkt,layer);arms={}
    arms['NO_PATCH']=msa2_arm(tok,model,pkt,base,layer,None,alpha,'NO_PATCH',active_sha)
    arms['ACTIVE_PLAN_RESIDUAL']=msa2_arm(tok,model,pkt,base,layer,vecs['ACTIVE_PLAN_RESIDUAL'],alpha,'ACTIVE_PLAN_RESIDUAL',active_sha)
    for arm in phase.SPEC:arms[arm]=msa2_arm(tok,model,pkt,base,layer,vecs[arm],alpha,arm,active_sha)
    rows[str(i)]={'arms':arms,'active_raw_residual_l2':float(src['active_l2']),'active_residual_sha256':active_sha,'reset_snapshot_sha256':base['reset_snapshot_sha256']}
    print(json.dumps({'stage':'dev_grid','layer':layer,'alpha':alpha,'done':pos,'qualified':len(qualified)}),flush=True)
   grids[key]=rows
 payload={'phase':'LOCALCONTINUATION_DEVELOPMENT','families':families,'grid_results':grids,'execution_provenance':ep,'execution_provenance_sha256':eph,'confirmation_accessed':False,'reserve_accessed':False,**bindings};atomic(DEV_PAYLOAD,payload);term=phase.select_development(payload,ROOT/DEV_SEAL);atomic(DEV_TERMINAL,term);return term

def confirmation_or_reserve(which:str,tok:Any,model:Any,prov:Mapping[str,Any],expected_seal_sha:str,primary_status:str|None=None)->dict[str,Any]:
 if which not in ('confirmation','reserve'):raise ExecutionContractError('bad phase')
 seal,seal_sha=phase.load_seal(ROOT/DEV_SEAL,expected_seal_sha);payload_path=CONF_PAYLOAD if which=='confirmation' else RES_PAYLOAD;result_path=CONF_RESULT if which=='confirmation' else RES_RESULT
 if (ROOT/PACKET_DIR[which]).exists() or (ROOT/payload_path).exists() or (ROOT/result_path).exists():raise ExecutionContractError(f'{which.upper()}_OUTPUT_EXISTS')
 if which=='reserve':
  if primary_status!='SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1':raise ExecutionContractError('RESERVE_LOCKED_UNTIL_PRIMARY_SUPPORT')
  if not (ROOT/CONF_RESULT).is_file() or json.loads((ROOT/CONF_RESULT).read_text()).get('status')!='SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1':raise ExecutionContractError('PRIMARY_RESULT_NOT_SUPPORTED')
 bindings={'final_prereg_sha256':pb.FINAL_PREREG_SHA256,'final_review_sha256':pb.FINAL_REVIEW_SHA256,'population_manifest_sha256':pb.POPULATION_SHA256,'population_review_sha256':pb.POPULATION_REVIEW_SHA256};ep=execution_provenance(prov);eph=phase.sha_json(ep)
 if eph!=seal.get('execution_provenance_sha256'):raise ExecutionContractError('EXECUTION_PROVENANCE_DIFFERS_FROM_DEVELOPMENT_SEAL')
 packets=produce_packets(which,tok,model,prov);by={int(x['frozen_index']):x for x in packets};indices=phase.CONF if which=='confirmation' else phase.RESERVE;qualified=[i for i in indices if bool(by[i].get('qualified'))];layer=int(seal['selected_layer']);alpha=float(seal['selected_alpha']);families=[]
 minq=15 if which=='confirmation' else 10
 if len(qualified)<minq:
  families=[{'index':i,'qualified':i in qualified} for i in indices];payload={'phase':'LOCALCONTINUATION_CONFIRMATION' if which=='confirmation' else 'LOCALCONTINUATION_REPLICATION','families':families,'selected_layer':layer,'selected_alpha':alpha,'development_seal_sha256':seal_sha,'execution_provenance':ep,'execution_provenance_sha256':eph,'reserve_accessed':False if which=='confirmation' else True,'valid_seen_accessed':False,'valid_unseen_accessed':False,**bindings};atomic(payload_path,payload);res=phase.evaluate_confirmation(payload,seal,seal_sha) if which=='confirmation' else phase.evaluate_replication(payload,seal,seal_sha,primary_status or '');atomic(result_path,res);return res
 import torch
 from replay_residual_t1_session_runtime_v1 import capture_activation_ids
 for pos,i in enumerate(indices,1):
  pkt=by[i]
  if i not in qualified:families.append({'index':i,'qualified':False,'active_raw_residual_l2':0.0});continue
  donor=donor_plan(pkt,by);base=base_reset(tok,pkt);src=capture_sources(tok,model,pkt,donor,[layer])[layer];active_sha=str(src['active_sha256']);vecs=vectors_for_grid(src,pkt,layer);zmax,smax=sentinels(model,base,layer);arms={}
  arms['NO_PATCH']=autonomous_arm(tok,model,pkt,base,layer,None,alpha,'NO_PATCH',active_sha,continue_to_budget=True)
  arms['ACTIVE_PLAN_RESIDUAL']=autonomous_arm(tok,model,pkt,base,layer,vecs['ACTIVE_PLAN_RESIDUAL'],alpha,'ACTIVE_PLAN_RESIDUAL',active_sha,continue_to_budget=True)
  for arm in phase.SPEC:arms[arm]=autonomous_arm(tok,model,pkt,base,layer,vecs[arm],alpha,arm,active_sha)
  zero=torch.zeros_like(vecs['ACTIVE_PLAN_RESIDUAL']);selfv=capture_activation_ids(model,base['prefix_ids'],layer,-1).detach().float().cpu()
  arms['ZERO_ADD']=autonomous_arm(tok,model,pkt,base,layer,zero,alpha,'ZERO_ADD',active_sha)
  arms['SELF_REPLACE']=autonomous_arm(tok,model,pkt,base,layer,selfv,alpha,'SELF_REPLACE',active_sha,mode='replace')
  vbase=base_reset(tok,pkt,visible_plan_slot_ids(tok,pkt,donor));arms['VISIBLE_TEXT_PLAN']=autonomous_arm(tok,model,pkt,vbase,layer,None,alpha,'VISIBLE_TEXT_PLAN',active_sha,external_reset_snapshot_sha256=base['reset_snapshot_sha256'])
  msa={'NO_PATCH':msa2_arm(tok,model,pkt,base,layer,None,alpha,'NO_PATCH',active_sha),'ACTIVE_PLAN_RESIDUAL':msa2_arm(tok,model,pkt,base,layer,vecs['ACTIVE_PLAN_RESIDUAL'],alpha,'ACTIVE_PLAN_RESIDUAL',active_sha)}
  for arm in phase.SPEC:msa[arm]=msa2_arm(tok,model,pkt,base,layer,vecs[arm],alpha,arm,active_sha)
  families.append({'index':i,'qualified':True,'active_raw_residual_l2':float(src['active_l2']),'active_residual_sha256':active_sha,'reset_snapshot_sha256':base['reset_snapshot_sha256'],'arms':arms,'matched_state_secondary':msa,'zero_add_no_patch_maxabs':zmax,'self_replace_no_patch_maxabs':smax});print(json.dumps({'stage':which,'done':pos,'total':len(indices)}),flush=True)
 payload={'phase':'LOCALCONTINUATION_CONFIRMATION' if which=='confirmation' else 'LOCALCONTINUATION_REPLICATION','families':families,'selected_layer':layer,'selected_alpha':alpha,'development_seal_sha256':seal_sha,'execution_provenance':ep,'execution_provenance_sha256':eph,'reserve_accessed':False if which=='confirmation' else True,'valid_seen_accessed':False,'valid_unseen_accessed':False,**bindings};atomic(payload_path,payload);res=phase.evaluate_confirmation(payload,seal,seal_sha) if which=='confirmation' else phase.evaluate_replication(payload,seal,seal_sha,primary_status or '');atomic(result_path,res);return res

def main(argv:Sequence[str]|None=None)->int:
 ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['preflight','development','confirmation','reserve'],required=True);ap.add_argument('--expected-device',default='NVIDIA GeForce RTX 4070 SUPER');ap.add_argument('--development-seal-sha256');ap.add_argument('--primary-status');args=ap.parse_args(argv)
 verify_sources()
 if args.phase=='preflight':
  dev=pb.load_population_phase('development',ROOT)
  result={'status':'READY_NO_SCIENCE','experiment_id':'6ccf7bd9-6622-404d-9f25-fcf7dbc41795','prediction_id':'c19837d5-1cac-4ce6-8555-614b9664768b','development_indices':[int(x['frozen_index']) for x in dev],'expected_device':args.expected_device,'model_calls':0,'environment_execution':0,'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,'vast_started_by_this_process':False}
  print(json.dumps({'LOCALCONTINUATION_PREFLIGHT':result},sort_keys=True));return 0
 if args.phase=='development':
  if any((ROOT/p).exists() for p in (PACKET_DIR['development'],DEV_PAYLOAD,DEV_TERMINAL,DEV_SEAL)):raise ExecutionContractError('DEVELOPMENT_OUTPUT_EXISTS_BEFORE_MODEL_LOAD')
 else:
  if not args.development_seal_sha256:raise ExecutionContractError('--development-seal-sha256 required after development freeze')
  phase.load_seal(ROOT/DEV_SEAL,args.development_seal_sha256)
  payload_path=CONF_PAYLOAD if args.phase=='confirmation' else RES_PAYLOAD;result_path=CONF_RESULT if args.phase=='confirmation' else RES_RESULT
  if (ROOT/PACKET_DIR[args.phase]).exists() or (ROOT/payload_path).exists() or (ROOT/result_path).exists():raise ExecutionContractError(f'{args.phase.upper()}_OUTPUT_EXISTS_BEFORE_MODEL_LOAD')
  if args.phase=='reserve':
   if args.primary_status!='SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1':raise ExecutionContractError('reserve requires exact supported primary status')
   if not (ROOT/CONF_RESULT).is_file() or json.loads((ROOT/CONF_RESULT).read_text()).get('status')!='SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1':raise ExecutionContractError('reserve requires supported immutable primary result file')
 tok,model,prov=load_runtime(args.expected_device)
 if args.phase=='development':result=development(tok,model,prov)
 else:result=confirmation_or_reserve(args.phase,tok,model,prov,args.development_seal_sha256,args.primary_status)
 print(json.dumps({'LOCALCONTINUATION_TERMINAL':result},sort_keys=True),flush=True);return 0
if __name__=='__main__':raise SystemExit(main())
