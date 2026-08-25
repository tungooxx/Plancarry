#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any,Callable,Mapping,Sequence
import localcontinuation_controls_v2 as controls
import localcontinuation_packet_builder_v2 as inherited
import localcontinuation_packet_builder_v1 as v1pb
import replay_residual_natural_packet_producer_v2_1 as v21
import replay_residual_sanity_protocol_v1 as sp

AUTHORITY_COMMIT='578a21c40c1cec2500a50edcd8daa643cceac6bd'
PREREG_REL=Path('results/design/plancarry_planunique_orthogonal_residual_v1_1_prereg_20260825.json'); PREREG_SHA256='2b2f955156b2b9ec0643774d6bb7e4674476f7707dfa0a0a11e48bc14433c2c5'
CONTROL_REL=Path('results/design/plancarry_planunique_orthogonal_residual_v1_1_control_contract_20260825.json'); CONTROL_SHA256='08a728e09817ffcdb5c33305dcaa383c12bf97feffbdab6af6bca76a4701d0b2'
PROJECTION_REL=Path('results/design/plancarry_planunique_orthogonal_residual_v1_1_projection_property_test_20260825.json'); PROJECTION_SHA256='ff2fb78444cadab2a52680713cdd7e0e2e13d35a94438df1ee5967795103d631'
STATIC_REL=Path('results/design/plancarry_planunique_orthogonal_residual_v1_1_static_audit_20260825.json'); STATIC_SHA256='5502379f6ca141460a877bce96a1534ba83b17279eeed742bd5c931d7bbdd160'
POPULATION_REL=Path('results/design/plancarry_planunique_orthogonal_residual_v1_fresh_population_20260824.json'); POPULATION_SHA256='ad2d525124b333b7dd04617bf52dd04c8196b5b67325a44274f3c0cbe576215f'
FINAL_MANIFEST_REL=Path('results/design/plancarry_planunique_final_authority_v1_2_20260825.json'); FINAL_MANIFEST_SHA256='c52a75e347595dd494cbe31d69f1598999bd373ce2d4b806bf84015e2eac2a4e'
FINAL_AUDIT_REL=Path('results/design/plancarry_planunique_final_authority_v1_2_composition_audit_a4_20260825.json'); FINAL_AUDIT_SHA256='0f890bce338eb58cbd923f490b9b27b986fbe6fd2d5cc3966ad0922f6337a28d'
CONTROLS_SHA256='c93bc0b76110a88eb54dfc0b0d2ea63f13b515140b68e927c12da2f495ec0367'
V2_PACKET_BUILDER_SHA256='cfb2b616cf2ba5bd7f81adda5c09a42bf7f26e4d99b4a8de5793ed0779d85685'
PHASE_RANGES={'development':tuple(range(32)),'confirmation':tuple(range(32,52)),'reserve_replication':tuple(range(52,64))}
PHASE_LABEL={'development':'development','confirmation':'confirmation','reserve_replication':'reserve'}
PACKET_CONTRACT='PLANCARRY_PLANUNIQUE_REFERENCE_PACKET_V1_2'; CUT_AFTER_ACTION=2; REFERENCE_ACTIONS_REQUIRED=5
class PlanUniquePacketError(RuntimeError):pass

def sha_file(p:str|Path)->str:
 h=hashlib.sha256();
 with Path(p).open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''): h.update(c)
 return h.hexdigest()
def sha_json(x:Any)->str:return controls.sha_json(x)
def verify_bindings(root:str|Path='.'):
 root=Path(root); req={PREREG_REL:PREREG_SHA256,CONTROL_REL:CONTROL_SHA256,PROJECTION_REL:PROJECTION_SHA256,STATIC_REL:STATIC_SHA256,POPULATION_REL:POPULATION_SHA256,FINAL_MANIFEST_REL:FINAL_MANIFEST_SHA256,FINAL_AUDIT_REL:FINAL_AUDIT_SHA256,Path('localcontinuation_controls_v2.py'):CONTROLS_SHA256,Path('localcontinuation_packet_builder_v2.py'):V2_PACKET_BUILDER_SHA256}
 for rel,exp in req.items():
  p=root/rel
  if not p.is_file() or sha_file(p)!=exp: raise PlanUniquePacketError(f'FROZEN_BINDING_DRIFT:{rel}')

def selected_rows(root:str|Path='.'):
 verify_bindings(root); d=json.loads((Path(root)/POPULATION_REL).read_text()); rows=[dict(x) for x in d['selected']]
 if [int(x['frozen_index']) for x in rows]!=list(range(64)) or len({x['game_path'] for x in rows})!=64: raise PlanUniquePacketError('POPULATION_DRIFT')
 for r in rows:r['family']=v1pb.family_from_game_path(str(r['game_path']))
 return rows
def load_population_phase(phase:str,root:str|Path='.'):
 if phase not in PHASE_RANGES:raise PlanUniquePacketError(f'UNKNOWN_PHASE:{phase}')
 by={int(x['frozen_index']):x for x in selected_rows(root)}; rows=[dict(by[i]) for i in PHASE_RANGES[phase]]
 if any(str(r['phase'])!=PHASE_LABEL[phase] for r in rows):raise PlanUniquePacketError('PHASE_LABEL_DRIFT')
 return rows

def _base(row:Mapping[str,Any],prov:Mapping[str,Any],phase:str):
 p=v21._packet_base(row,prov);p.update({'planunique_packet_contract':PACKET_CONTRACT,'phase':phase,'planunique_authority_commit':AUTHORITY_COMMIT,'planunique_prereg_sha256':PREREG_SHA256,'planunique_control_contract_sha256':CONTROL_SHA256,'planunique_projection_property_sha256':PROJECTION_SHA256,'planunique_static_audit_sha256':STATIC_SHA256,'planunique_population_sha256':POPULATION_SHA256,'planunique_final_manifest_sha256':FINAL_MANIFEST_SHA256,'planunique_final_composition_audit_sha256':FINAL_AUDIT_SHA256,'inherited_v2_controls_sha256':CONTROLS_SHA256,'inherited_v2_packet_builder_sha256':V2_PACKET_BUILDER_SHA256,'task_success_required':False,'reference_action_count_required':5,'cut_after_action':2,'stage1_runtime_errors':[],'v2_control_constructibility_provenance':None})
 return p

def produce_stage1_attempt(row:Mapping[str,Any],phase:str,tokenizer:Any,model_provenance:Mapping[str,Any],runtime_factory:Callable[[str],Any],planner_fn:Callable[[str,str],Any],command_score_fn:Callable[[Sequence[int],Sequence[int]],float],open_tag_ids:Sequence[int],close_tag_ids:Sequence[int]):
 if int(row['frozen_index']) not in PHASE_RANGES[phase]:raise PlanUniquePacketError('ROW_OUTSIDE_PHASE')
 packet=_base(row,model_provenance,phase); runtime=None; errors=[]; planner=None
 try:
  runtime=runtime_factory(str(row['game_path']));packet['initial_observation']=str(runtime.observation);packet['task_instruction']=v21.extract_task_instruction(packet['initial_observation']);planner=planner_fn(packet['task_instruction'],packet['initial_observation']);accepted,count=v21.accept_plan_new_ids(tokenizer,planner.new_ids)
  if accepted!=planner.plan_text or count!=planner.complete_block_token_count:raise RuntimeError('PLANNER_RESULT_ACCEPTANCE_MISMATCH')
  packet['plan_text']=planner.plan_text;packet['plan_provenance']=v21.plan_provenance(tokenizer,planner);packet['prompt_provenance']=v21.prompt_provenance_for_planner(planner)
  for step in range(1,v21.ACTION_BUDGET+1):
   if bool(runtime.done) or bool(runtime.won):break
   cmds=sorted(str(x) for x in runtime.admissible_commands);choice=v21.choose_admissible_command(tokenizer,packet['task_instruction'],planner.plan_text,packet['actions'],str(runtime.observation),cmds,command_score_fn)
   if choice.command not in cmds:raise RuntimeError('CHOICE_NOT_CURRENT_ADMISSIBLE_COMMAND')
   pre=str(runtime.hash());rec=runtime.step(choice.command);a=v21.action_row(step,choice,pre,rec,cmds);a['accepted']=rec.error is None;a['was_admissible']=True;packet['actions'].append(a)
   if rec.error:errors.append(str(rec.error));break
  packet['success']=bool(getattr(runtime,'won',False))
 except Exception as exc:
  errors.append(f'{type(exc).__name__}:{exc}')
  if not packet.get('plan_provenance'):packet['plan_provenance']=v21.plan_provenance(tokenizer,planner)
 finally:
  if runtime is not None:
   try:runtime.close()
   except Exception:pass
 packet['stage1_runtime_errors']=errors
 ok,reasons,guard=inherited.local_stage1_eligibility_v2(tokenizer,str(packet.get('plan_text','')),packet.get('actions',[]),errors,open_tag_ids,close_tag_ids)
 packet['trajectory_eligible']=bool(ok);packet['qualification_stage1_reasons']=list(reasons);packet['v2_control_constructibility_provenance']=guard;packet['qualified']=False;packet['qualification_stage2_reasons']=['STAGE2_NOT_RUN'];packet['trajectory_sha256']=sp.trajectory_digest(packet);return packet

def validate_reference_packet(packet:Mapping[str,Any],phase:str,root:str|Path='.'):
 rows={int(x['frozen_index']):x for x in load_population_phase(phase,root)};i=int(packet.get('frozen_index',-1))
 if i not in rows:raise PlanUniquePacketError('PACKET_PHASE_INDEX_LEAK')
 e=rows[i]
 if str(packet.get('game_path'))!=str(e['game_path']) or str(packet.get('family'))!=str(e['family']):raise PlanUniquePacketError('PACKET_MANIFEST_MISMATCH')
 req={'planunique_packet_contract':PACKET_CONTRACT,'planunique_authority_commit':AUTHORITY_COMMIT,'planunique_prereg_sha256':PREREG_SHA256,'planunique_control_contract_sha256':CONTROL_SHA256,'planunique_projection_property_sha256':PROJECTION_SHA256,'planunique_static_audit_sha256':STATIC_SHA256,'planunique_population_sha256':POPULATION_SHA256,'planunique_final_manifest_sha256':FINAL_MANIFEST_SHA256,'planunique_final_composition_audit_sha256':FINAL_AUDIT_SHA256,'inherited_v2_controls_sha256':CONTROLS_SHA256,'inherited_v2_packet_builder_sha256':V2_PACKET_BUILDER_SHA256}
 for k,v in req.items():
  if packet.get(k)!=v:raise PlanUniquePacketError(f'PACKET_BINDING:{k}')
 ok,reasons=inherited.stored_stage1_eligibility_v2(packet)
 if bool(packet.get('trajectory_eligible'))!=ok or list(packet.get('qualification_stage1_reasons',[]))!=list(reasons):raise PlanUniquePacketError('STAGE1_RECLASSIFICATION')
 if packet.get('task_success_required') is not False or packet.get('trajectory_sha256')!=sp.trajectory_digest(dict(packet)):raise PlanUniquePacketError('PACKET_INVARIANT')

def apply_stage2_phase(packets:Sequence[dict[str,Any]],phase:str,neutral_filler_ids:Sequence[int],root:str|Path='.'):
 controls.verify_neutral_filler_ids(neutral_filler_ids); expected=list(PHASE_RANGES[phase])
 if [int(p.get('frozen_index',-1)) for p in packets]!=expected:raise PlanUniquePacketError('STAGE2_REQUIRES_COMPLETE_PHASE_E')
 for p in packets:validate_reference_packet(p,phase,root)
 eligible=v21.frozen_eligible_order(packets);ei=[int(x['frozen_index']) for x in eligible];esh=sha_json(ei);result=[dict(p) for p in packets];by={int(p['frozen_index']):p for p in result}
 if len(eligible)<2:
  for p in result:p['qualified']=False;p['qualification_stage2_reasons']=['FROZEN_E_SIZE_LT_2'];p['frozen_E_indices_sha256']=esh
  return result
 for source in eligible:
  p=by[int(source['frozen_index'])];p['frozen_E_indices_sha256']=esh;donor=v21.unrelated_donor_for(source,eligible)
  if donor is None:p['qualified']=False;p['qualification_stage2_reasons']=['NO_DIFFERENT_FAMILY_DONOR_IN_FROZEN_E'];continue
  try:
   _slots,meta=controls.build_semantic_slots(p,donor,neutral_filler_ids);p['control_provenance']={**meta,'unrelated_donor_frozen_index':int(donor['frozen_index']),'unrelated_donor_ordering_key':v21.unrelated_ordering_key(donor),'anchor_cycle':2,'frozen_E_indices':ei,'frozen_E_indices_sha256':esh,'planunique_control_contract_sha256':CONTROL_SHA256,'controls_source_sha256':CONTROLS_SHA256,'stage2_semantic_tokenizer_calls':0};p['qualified']=True;p['qualification_stage2_reasons']=[]
  except Exception as exc:p['qualified']=False;p['qualification_stage2_reasons']=[f'CONTROL_CONSTRUCTION_FAILED:{type(exc).__name__}:{exc}']
 for p in result:
  p.setdefault('frozen_E_indices_sha256',esh)
  if not p.get('trajectory_eligible'):p['qualified']=False;p['qualification_stage2_reasons']=['NOT_IN_FROZEN_TRAJECTORY_ELIGIBLE_E']
 return result

def validate_phase_packets(packets:Sequence[Mapping[str,Any]],phase:str,root:str|Path='.'):
 if [int(p.get('frozen_index',-1)) for p in packets]!=list(PHASE_RANGES[phase]):raise PlanUniquePacketError('PACKET_SET_INDEX')
 for p in packets:validate_reference_packet(p,phase,root)
 return {'phase':phase,'attempted_count':len(packets),'trajectory_eligible_count':sum(bool(p.get('trajectory_eligible')) for p in packets),'semantic_stage2_qualified_count':sum(bool(p.get('qualified')) for p in packets)}
