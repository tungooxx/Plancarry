#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,shutil,uuid
from pathlib import Path
from typing import Any,Callable,Mapping,Sequence
import replay_residual_natural_packet_producer_v2_1 as v21
import replay_residual_sanity_protocol_v1 as sp

FINAL_PREREG_REL=Path('results/design/plancarry_replayresidual_localcontinuation_prereg_final_v1_20260823.json')
FINAL_PREREG_SHA256='a6972b33caaf7f2b7b28af248acd528a540e077bfdb59283f5f288de5e297ec8'
FINAL_REVIEW_REL=Path('results/design/plancarry_replayresidual_localcontinuation_prereg_final_v1_independent_review_a3_20260823.json')
FINAL_REVIEW_SHA256='c9c89ebe87980e2169d8534b43d6955b477cd94d5ea14c70604c8af5b6a1c1b6'
POPULATION_REL=Path('results/design/plancarry_replayresidual_localcontinuation_fresh_population_v1_20260823.json')
POPULATION_SHA256='adba81b7073707ef01589fbd022106e678f8542182f780f6f789ef1a47dff543'
POPULATION_REVIEW_REL=Path('results/design/plancarry_replayresidual_localcontinuation_fresh_population_independent_review_a4_20260823.json')
POPULATION_REVIEW_SHA256='bd730ea81e7bfea75fa7eb79e357505c794e6300c5ad53500bffe092947c82b0'
PRODUCER_SHA256='bb05eb8b3b02f15d32f768212730712f2f0a04062729a57ca4993be2031dec55'
PROTOCOL_SHA256='9af0d247e8bb9cb5e17d11727008d827dab0c088d5c28142726be20cd2d883ef'
SESSION_SHA256='585e44ec5cd2395be0804b865de85ac36c5db79117cf4061566cf16a9749e3b6'
ALFWORLD_RUNTIME_SHA256='53e550f70711a3779409c565ecbd3e2fd971751a03633dad3566d5569a6fb3c6'
TEXTWORLD_COMPAT_SHA256='cee3c3818b5856507179dd9f5c5c819260d1cd51c746faa012c612f79bf2fc83'
TEXTWORLD_COMPAT_REVIEW_SHA256='32f8b5b2161c8f57fa2c7721df32e587b6431ee9c93cdd07a75e1ef00b7c1893'
PHASE_RANGES={'development':tuple(range(0,32)),'confirmation':tuple(range(32,52)),'reserve_replication':tuple(range(52,64))}
PHASE_LABEL={'development':'development','confirmation':'confirmation','reserve_replication':'reserve'}
MIN_STAGE2={'development':16,'confirmation':15,'reserve_replication':10}
REFERENCE_ACTIONS_REQUIRED=5
CUT_AFTER_ACTION=2
PACKET_CONTRACT='PLANCARRY_LOCALCONTINUATION_REFERENCE_PACKET_V1'

class PacketContractError(RuntimeError):pass

def sha_file(path:str|Path)->str:
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def canonical_bytes(obj:Any)->bytes:return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha_json(obj:Any)->str:return hashlib.sha256(canonical_bytes(obj)).hexdigest()
def family_from_game_path(game_path:str)->str:
 parts=str(game_path).replace('\\','/').split('/')
 if len(parts)!=5 or parts[0]!='json_2.1.1' or parts[1]!='train' or not parts[2].startswith('pick_and_place_simple-') or not parts[3].startswith('trial_') or parts[4]!='game.tw-pddl':raise PacketContractError(f'NONCANONICAL_LOCALCONTINUATION_GAME_PATH:{game_path}')
 return parts[2]
def verify_bindings(root:str|Path='.') -> None:
 root=Path(root)
 req={root/FINAL_PREREG_REL:FINAL_PREREG_SHA256,root/FINAL_REVIEW_REL:FINAL_REVIEW_SHA256,root/POPULATION_REL:POPULATION_SHA256,root/POPULATION_REVIEW_REL:POPULATION_REVIEW_SHA256,root/'replay_residual_natural_packet_producer_v2_1.py':PRODUCER_SHA256,root/'replay_residual_sanity_protocol_v1.py':PROTOCOL_SHA256,root/'replay_residual_t1_session_runtime_v1.py':SESSION_SHA256,root/'alfworld_runtime.py':ALFWORLD_RUNTIME_SHA256,root/'textworld_py313_compat.py':TEXTWORLD_COMPAT_SHA256,root/'results/design/plancarry_textworld_py313_compat_semantic_scope_independent_review_a3_20260823.json':TEXTWORLD_COMPAT_REVIEW_SHA256}
 for path,expected in req.items():
  if not path.is_file():raise PacketContractError(f'FROZEN_BINDING_MISSING:{path}')
  got=sha_file(path)
  if got!=expected:raise PacketContractError(f'FROZEN_BINDING_DRIFT:{path}:{got}:{expected}')
def _selected_rows(root:str|Path='.') -> list[dict[str,Any]]:
 verify_bindings(root);data=json.loads((Path(root)/POPULATION_REL).read_text());rows=[dict(x) for x in data['selected']]
 if [int(x['frozen_index']) for x in rows]!=list(range(64)):raise PacketContractError('POPULATION_INDEX_DRIFT')
 if len({str(x['game_path']) for x in rows})!=64:raise PacketContractError('POPULATION_DUPLICATE_PATH')
 for row in rows:row['family']=family_from_game_path(str(row['game_path']))
 return rows
def load_population_phase(phase:str,root:str|Path='.') -> list[dict[str,Any]]:
 if phase not in PHASE_RANGES:raise PacketContractError(f'UNKNOWN_PHASE:{phase}')
 by={int(x['frozen_index']):x for x in _selected_rows(root)};rows=[dict(by[i]) for i in PHASE_RANGES[phase]]
 if any(str(r['phase'])!=PHASE_LABEL[phase] for r in rows):raise PacketContractError('POPULATION_PHASE_LABEL_DRIFT')
 return rows

def local_stage1_eligibility(plan_ok:bool,actions:Sequence[Mapping[str,Any]],runtime_errors:Sequence[Any]=())->tuple[bool,list[str]]:
 reasons=[]
 if not plan_ok:reasons.append('PLAN_ACCEPTANCE_FAILED')
 if runtime_errors:reasons.append('RUNTIME_OR_ACTION_ERROR')
 if len(actions)<REFERENCE_ACTIONS_REQUIRED:reasons.append('REFERENCE_ACTION_COUNT_LT5')
 if len(actions)>v21.ACTION_BUDGET:reasons.append('REFERENCE_ACTION_COUNT_EXCEEDS_BUDGET')
 for j,row in enumerate(list(actions)[:REFERENCE_ACTIONS_REQUIRED],1):
  cmd=str(row.get('command',''));pre=[str(x) for x in row.get('admissible_commands',[])]
  if row.get('accepted') is not True or row.get('error') not in (None,''):reasons.append(f'ACTION_{j}_NOT_ACCEPTED')
  if row.get('was_admissible') is not True or cmd not in pre:reasons.append(f'ACTION_{j}_NOT_CURRENT_ADMISSIBLE')
  if not v21.is_nontrivial(cmd):reasons.append(f'ACTION_{j}_TRIVIAL')
 return (not reasons),reasons

def _base(row:Mapping[str,Any],prov:Mapping[str,Any],phase:str)->dict[str,Any]:
 p=v21._packet_base(row,prov)
 p.update({'localcontinuation_packet_contract':PACKET_CONTRACT,'phase':phase,'final_prereg_sha256':FINAL_PREREG_SHA256,'final_review_sha256':FINAL_REVIEW_SHA256,'population_manifest_sha256':POPULATION_SHA256,'population_review_sha256':POPULATION_REVIEW_SHA256,'textworld_compat_review_sha256':TEXTWORLD_COMPAT_REVIEW_SHA256,'task_success_required':False,'reference_action_count_required':REFERENCE_ACTIONS_REQUIRED,'cut_after_action':CUT_AFTER_ACTION,'producer_source_sha256':PRODUCER_SHA256,'control_builder_source_sha256':PROTOCOL_SHA256,'stage1_runtime_errors':[]})
 return p

def produce_stage1_attempt(row:Mapping[str,Any],phase:str,tokenizer:Any,model_provenance:Mapping[str,Any],runtime_factory:Callable[[str],Any],planner_fn:Callable[[str,str],Any],command_score_fn:Callable[[Sequence[int],Sequence[int]],float])->dict[str,Any]:
 if int(row['frozen_index']) not in PHASE_RANGES[phase]:raise PacketContractError('ROW_OUTSIDE_PHASE')
 packet=_base(row,model_provenance,phase);runtime=None;errors=[];planner=None
 try:
  runtime=runtime_factory(str(row['game_path']));packet['initial_observation']=str(runtime.observation);packet['task_instruction']=v21.extract_task_instruction(packet['initial_observation']);planner=planner_fn(packet['task_instruction'],packet['initial_observation'])
  accepted,count=v21.accept_plan_new_ids(tokenizer,planner.new_ids)
  if accepted!=planner.plan_text or count!=planner.complete_block_token_count:raise RuntimeError('PLANNER_RESULT_ACCEPTANCE_MISMATCH')
  packet['plan_text']=planner.plan_text;packet['plan_provenance']=v21.plan_provenance(tokenizer,planner);packet['prompt_provenance']=v21.prompt_provenance_for_planner(planner)
  for step in range(1,v21.ACTION_BUDGET+1):
   if bool(runtime.done) or bool(runtime.won):break
   commands=sorted(str(x) for x in runtime.admissible_commands)
   choice=v21.choose_admissible_command(tokenizer,packet['task_instruction'],planner.plan_text,packet['actions'],str(runtime.observation),commands,command_score_fn)
   was=choice.command in commands
   if not was:raise RuntimeError('CHOICE_NOT_CURRENT_ADMISSIBLE_COMMAND')
   pre=str(runtime.hash());record=runtime.step(choice.command);a=v21.action_row(step,choice,pre,record,commands);a['accepted']=record.error is None;a['was_admissible']=bool(was);packet['actions'].append(a)
   if record.error:errors.append(str(record.error));break
  packet['success']=bool(getattr(runtime,'won',False))
 except Exception as exc:
  errors.append(f'{type(exc).__name__}:{exc}')
  if not packet.get('plan_provenance'):packet['plan_provenance']=v21.plan_provenance(tokenizer,planner)
 finally:
  if runtime is not None:
   try:runtime.close()
   except Exception:pass
 packet['stage1_runtime_errors']=list(errors);eligible,reasons=local_stage1_eligibility(planner is not None and bool(packet.get('plan_text')),packet['actions'],errors);packet['trajectory_eligible']=bool(eligible);packet['qualification_stage1_reasons']=reasons;packet['qualified']=False;packet['qualification_stage2_reasons']=['STAGE2_NOT_RUN'];packet['trajectory_sha256']=sp.trajectory_digest(packet)
 return packet

def validate_reference_packet(packet:Mapping[str,Any],phase:str,root:str|Path='.') -> None:
 rows={int(x['frozen_index']):x for x in load_population_phase(phase,root)};idx=int(packet.get('frozen_index',-1))
 if idx not in rows:raise PacketContractError('PACKET_PHASE_INDEX_LEAK')
 e=rows[idx]
 if str(packet.get('game_path'))!=str(e['game_path']):raise PacketContractError('PACKET_MANIFEST_PATH_MISMATCH')
 if str(packet.get('family'))!=str(e['family']):raise PacketContractError('PACKET_MANIFEST_FAMILY_MISMATCH')
 req={'localcontinuation_packet_contract':PACKET_CONTRACT,'final_prereg_sha256':FINAL_PREREG_SHA256,'final_review_sha256':FINAL_REVIEW_SHA256,'population_manifest_sha256':POPULATION_SHA256,'population_review_sha256':POPULATION_REVIEW_SHA256,'producer_source_sha256':PRODUCER_SHA256,'control_builder_source_sha256':PROTOCOL_SHA256,'textworld_compat_review_sha256':TEXTWORLD_COMPAT_REVIEW_SHA256}
 for k,v in req.items():
  if packet.get(k)!=v:raise PacketContractError(f'PACKET_BINDING_MISMATCH:{k}')
 eligible,reasons=local_stage1_eligibility(bool(packet.get('plan_text')),packet.get('actions',[]),packet.get('stage1_runtime_errors',[]))
 if bool(packet.get('trajectory_eligible'))!=eligible or list(packet.get('qualification_stage1_reasons',[]))!=reasons:raise PacketContractError('PACKET_STAGE1_RECLASSIFICATION_MISMATCH')
 if packet.get('task_success_required') is not False:raise PacketContractError('TASK_SUCCESS_MUST_NOT_GATE')
 if packet.get('trajectory_sha256')!=sp.trajectory_digest(dict(packet)):raise PacketContractError('TRAJECTORY_HASH_MISMATCH')


def reclassify_stage1(packet:Mapping[str,Any],manifest_row:Mapping[str,Any],phase:str|None=None)->dict[str,Any]:
 x=dict(packet); idx=int(manifest_row['frozen_index']); inferred=phase
 if inferred is None:
  matches=[name for name,inds in PHASE_RANGES.items() if idx in inds]
  if len(matches)!=1: raise PacketContractError('MANIFEST_ROW_PHASE_UNRESOLVED')
  inferred=matches[0]
 x['frozen_index']=idx; x['game_path']=str(manifest_row['game_path']); x['family']=family_from_game_path(str(manifest_row['game_path'])); x['phase']=inferred
 x.update({'localcontinuation_packet_contract':PACKET_CONTRACT,'final_prereg_sha256':FINAL_PREREG_SHA256,'final_review_sha256':FINAL_REVIEW_SHA256,'population_manifest_sha256':POPULATION_SHA256,'population_review_sha256':POPULATION_REVIEW_SHA256,'textworld_compat_review_sha256':TEXTWORLD_COMPAT_REVIEW_SHA256,'task_success_required':False,'reference_action_count_required':REFERENCE_ACTIONS_REQUIRED,'cut_after_action':CUT_AFTER_ACTION,'producer_source_sha256':PRODUCER_SHA256,'control_builder_source_sha256':PROTOCOL_SHA256})
 acts=[dict(a) for a in x.get('actions',[])]
 for a in acts:
  a.setdefault('accepted',a.get('error') in (None,'')); a.setdefault('was_admissible',str(a.get('command','')) in [str(c) for c in a.get('admissible_commands',[])])
 x['actions']=acts; x.setdefault('stage1_runtime_errors',[])
 ok,reasons=local_stage1_eligibility(bool(x.get('plan_text')),acts,x['stage1_runtime_errors']); x['trajectory_eligible']=ok; x['qualification_stage1_reasons']=reasons; x.setdefault('qualified',False); x.setdefault('qualification_stage2_reasons',['STAGE2_NOT_RUN'])
 x['trajectory_sha256']=sp.trajectory_digest(x); return x

def apply_stage2_phase(tokenizer:Any,packets:Sequence[dict[str,Any]],phase:str,root:str|Path='.') -> list[dict[str,Any]]:
 expected=list(PHASE_RANGES[phase])
 if [int(p.get('frozen_index',-1)) for p in packets]!=expected:raise PacketContractError(f'STAGE2_REQUIRES_COMPLETE_PHASE_E:{phase}')
 for p in packets:validate_reference_packet(p,phase,root)
 eligible=v21.frozen_eligible_order(packets);e_indices=[int(x['frozen_index']) for x in eligible];e_sha=sha_json(e_indices);result=[dict(p) for p in packets];by={int(p['frozen_index']):p for p in result}
 if len(eligible)<2:
  for p in result:p['qualified']=False;p['qualification_stage2_reasons']=['FROZEN_E_SIZE_LT_2'];p['frozen_E_indices_sha256']=e_sha
  return result
 for source in eligible:
  p=by[int(source['frozen_index'])];p['frozen_E_indices_sha256']=e_sha;donor=v21.unrelated_donor_for(source,eligible)
  if donor is None:p['qualified']=False;p['qualification_stage2_reasons']=['NO_DIFFERENT_FAMILY_DONOR_IN_FROZEN_E'];continue
  try:
   slots=sp.build_condition_slots(tokenizer,p,str(donor['plan_text']),anchor_cycle=2)
   if set(slots)!=set(sp.CONDITIONS) or any(len(ids)!=sp.PLAN_SLOT_TOKENS for ids in slots.values()):raise PacketContractError('ALL_SEVEN_EXACT128_CONTROLS_REQUIRED')
   p['control_provenance']={'condition_names':list(sp.CONDITIONS),'condition_slot_token_ids_sha256_by_condition':{name:v21.sha256_json(list(slots[name])) for name in sp.CONDITIONS},'unrelated_donor_frozen_index':int(donor['frozen_index']),'unrelated_donor_ordering_key':v21.unrelated_ordering_key(donor),'anchor_cycle':2,'control_builder_source_sha256':PROTOCOL_SHA256,'frozen_E_indices':e_indices,'frozen_E_indices_sha256':e_sha};p['qualified']=True;p['qualification_stage2_reasons']=[]
  except Exception as exc:p['qualified']=False;p['qualification_stage2_reasons']=[f'CONTROL_CONSTRUCTION_FAILED:{type(exc).__name__}:{exc}']
 for p in result:
  p.setdefault('frozen_E_indices_sha256',e_sha)
  if not p.get('trajectory_eligible'):p['qualified']=False;p['qualification_stage2_reasons']=['NOT_IN_FROZEN_TRAJECTORY_ELIGIBLE_E']
 return result

def build_phase_packets(phase:str,tokenizer:Any,model_provenance:Mapping[str,Any],runtime_factory:Callable[[str],Any],planner_fn:Callable[[str,str],Any],command_score_fn:Callable[[Sequence[int],Sequence[int]],float],root:str|Path='.',progress_fn:Callable[[int,int],None]|None=None)->list[dict[str,Any]]:
 rows=load_population_phase(phase,root);packets=[]
 for n,row in enumerate(rows,1):packets.append(produce_stage1_attempt(row,phase,tokenizer,model_provenance,runtime_factory,planner_fn,command_score_fn));progress_fn and progress_fn(n,len(rows))
 return apply_stage2_phase(tokenizer,packets,phase,root)

def validate_phase_packets(packets:Sequence[Mapping[str,Any]],phase:str,root:str|Path='.') -> dict[str,Any]:
 expected=list(PHASE_RANGES[phase])
 if [int(p.get('frozen_index',-1)) for p in packets]!=expected:raise PacketContractError('PACKET_SET_INDEX_MISMATCH')
 for p in packets:validate_reference_packet(p,phase,root)
 return {'phase':phase,'attempted_count':len(packets),'trajectory_eligible_count':sum(bool(p.get('trajectory_eligible')) for p in packets),'stage2_qualified_count':sum(bool(p.get('qualified')) for p in packets),'minimum_stage2_qualified':MIN_STAGE2[phase]}
def _write_fsync(path:Path,payload:bytes)->None:
 with path.open('xb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
def atomic_publish_packet_set(root:str|Path,phase:str,packets:Sequence[Mapping[str,Any]],target_rel:str|Path)->tuple[Path,dict[str,Any]]:
 root=Path(root);target=root/Path(target_rel);summary=validate_phase_packets(packets,phase,root)
 if target.exists():raise PacketContractError(f'REFUSE_EXISTING_PACKET_DIR:{target}')
 target.parent.mkdir(parents=True,exist_ok=True);stage=target.with_name('.'+target.name+f'.inprogress.{uuid.uuid4().hex}');stage.mkdir(mode=0o700)
 try:
  hashes={}
  for p in packets:
   name=f"packet_{int(p['frozen_index']):02d}.json";raw=json.dumps(p,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False).encode()+b'\n';_write_fsync(stage/name,raw);hashes[name]=hashlib.sha256(raw).hexdigest()
  manifest={'kind':'PLANCARRY_LOCALCONTINUATION_PACKET_MANIFEST_V1','packet_contract':PACKET_CONTRACT,'phase':phase,'indices':list(PHASE_RANGES[phase]),'packet_hashes':hashes,'packet_count':len(packets),**summary,'final_prereg_sha256':FINAL_PREREG_SHA256,'final_review_sha256':FINAL_REVIEW_SHA256,'population_manifest_sha256':POPULATION_SHA256,'population_review_sha256':POPULATION_REVIEW_SHA256,'textworld_compat_sha256':TEXTWORLD_COMPAT_SHA256,'textworld_compat_review_sha256':TEXTWORLD_COMPAT_REVIEW_SHA256,'no_replacement':True,'scientific_result':'NOT_ASSESSED_PACKET_PRODUCTION_ONLY'}
  _write_fsync(stage/'manifest.json',json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n');_write_fsync(stage/'provenance.json',json.dumps({'kind':'PLANCARRY_LOCALCONTINUATION_PACKET_PROVENANCE_V1','phase':phase,'producer_sha256':PRODUCER_SHA256,'protocol_sha256':PROTOCOL_SHA256,'session_sha256':SESSION_SHA256,'alfworld_runtime_sha256':ALFWORLD_RUNTIME_SHA256,'textworld_compat_sha256':TEXTWORLD_COMPAT_SHA256,'textworld_compat_review_sha256':TEXTWORLD_COMPAT_REVIEW_SHA256},sort_keys=True,indent=2).encode()+b'\n')
  fd=os.open(stage,os.O_RDONLY);os.fsync(fd);os.close(fd);os.rename(stage,target);fd=os.open(target.parent,os.O_RDONLY);os.fsync(fd);os.close(fd);return target,manifest
 finally:
  if stage.exists():shutil.rmtree(stage,ignore_errors=True)


def produce_phase_stage1(phase:str,tokenizer:Any,model_provenance:Mapping[str,Any],runtime_factory:Callable[[str],Any],planner_fn:Callable[[str,str],Any],command_score_fn:Callable[[Sequence[int],Sequence[int]],float],root:str|Path='.',progress_fn:Callable[[int,int],None]|None=None)->list[dict[str,Any]]:
 rows=load_population_phase(phase,root); packets=[]
 for n,row in enumerate(rows,1):
  packets.append(produce_stage1_attempt(row,phase,tokenizer,model_provenance,runtime_factory,planner_fn,command_score_fn))
  if progress_fn: progress_fn(n,len(rows))
 return packets

def build_stage2_controls(tokenizer:Any,packets:Sequence[dict[str,Any]],phase:str,root:str|Path='.') -> list[dict[str,Any]]:
 return apply_stage2_phase(tokenizer,packets,phase,root)

def atomic_publish_phase_packets(root:str|Path,phase:str,packets:Sequence[Mapping[str,Any]],target_rel:str|Path)->tuple[Path,str]:
 target,manifest=atomic_publish_packet_set(root,phase,packets,target_rel)
 return target,sha_json(manifest)
