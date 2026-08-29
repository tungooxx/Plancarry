#!/usr/bin/env python3
"""Registered-identity adapter for corrected ReplayResidual V2.3 packet production.

This adapter preserves the frozen V2.1 scientific packet producer and the reviewed
Python3.13/TextWorld compatibility wrappers. It changes only the public successor
packet path plus post-registration manifest/provenance identity, after the full
frozen V2.1 validator has already passed in a hidden same-parent directory.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, os, shutil, sys, tempfile, uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))

import plancarry_replayresidual_v23_execution_binding_20260828 as binding
import replay_residual_natural_packet_producer_v2_1 as frozen
import replay_residual_natural_packet_producer_v2_2_technical_successor as thin

TEMPLATE_SHA256=binding.TEMPLATE_SHA256
SUCCESSOR_POLICY_SHA256=binding.POLICY_SHA256
SUCCESSOR_POLICY_REVIEW_SHA256=binding.POLICY_REVIEW_SHA256
ATTESTATION_CONTRACT_SHA256=binding.ATTESTATION_CONTRACT_SHA256
ATTESTATION_REVIEW_SHA256=binding.ATTESTATION_REVIEW_SHA256
THIN_WRAPPER_SHA256='d1be7ecbabc1ac3d8d24587a57e53141623b320615400a5acd0d9b7437635ab8'
SUCCESSOR_PACKET_REL=Path('results/science/plancarry_replay_residual_sanity_packets_v2_3_capability_successor1')
_ALLOWED_STAGE1={
 'PLAN_ACCEPTANCE_FAILED','NOT_WON_WITHIN_ACTION_BUDGET','TRAJECTORY_HAS_FEWER_THAN_4_ACTIONS',
 'TRAJECTORY_EXCEEDS_ACTION_BUDGET','FIRST_TWO_ACTIONS_NOT_BOTH_NONTRIVIAL','FIRST_TWO_ACTIONS_UNAVAILABLE',
 'FEWER_THAN_TWO_POST_CUT_NONTRIVIAL_ACTIONS'
}
_ALLOWED_STAGE2={'FROZEN_E_SIZE_LT_2','NO_DIFFERENT_FAMILY_DONOR_IN_FROZEN_E','NOT_IN_FROZEN_TRAJECTORY_ELIGIBLE_E'}
_ORIGINAL_ATOMIC=thin._ORIGINAL_ATOMIC_PUBLISH
_BOUND:dict[str,Any]|None=None
_BOUND_PATH:Path|None=None
_BOUND_SHA256:str|None=None


def v23_validate_model_provenance(prov:Mapping[str,Any])->None:
 # V2.3: device marketing name is provenance only, never admission authority.
 for key,expected in frozen.EXPECTED_MODEL_PROVENANCE.items():
  if prov.get(key)!=expected:
   raise RuntimeError(f'MODEL_PROVENANCE_MISMATCH:{key}:{prov.get(key)!r}:{expected!r}')
 device_name=prov.get('device_name')
 if not isinstance(device_name,str) or not device_name.strip():
  raise RuntimeError('MODEL_DEVICE_PROVENANCE_REQUIRED')


def v23_load_production_runtime(root:Path):
 # Exact frozen runtime, but capability-bound rather than product-name-bound.
 import torch
 import transformers
 import tokenizers as tokenizers_pkg
 from transformers import AutoModelForCausalLM,AutoTokenizer
 if str(torch.__version__)!=frozen.TORCH_VERSION:
  raise RuntimeError(f'TORCH_VERSION_MISMATCH:{torch.__version__}:{frozen.TORCH_VERSION}')
 if str(transformers.__version__)!=frozen.TRANSFORMERS_VERSION:
  raise RuntimeError(f'TRANSFORMERS_VERSION_MISMATCH:{transformers.__version__}:{frozen.TRANSFORMERS_VERSION}')
 if str(tokenizers_pkg.__version__)!=frozen.TOKENIZERS_VERSION:
  raise RuntimeError(f'TOKENIZERS_VERSION_MISMATCH:{tokenizers_pkg.__version__}:{frozen.TOKENIZERS_VERSION}')
 if not torch.cuda.is_available():
  raise RuntimeError('CUDA_REQUIRED')
 if not bool(torch.cuda.is_bf16_supported()):
  raise RuntimeError('NATIVE_BF16_REQUIRED')
 device_name=str(torch.cuda.get_device_name(0))
 if not device_name.strip():
  raise RuntimeError('MODEL_DEVICE_PROVENANCE_REQUIRED')
 tokenizer=AutoTokenizer.from_pretrained(frozen.MODEL_ID,revision=frozen.MODEL_REVISION,trust_remote_code=False)
 model=AutoModelForCausalLM.from_pretrained(
  frozen.MODEL_ID,revision=frozen.MODEL_REVISION,torch_dtype=torch.bfloat16,trust_remote_code=False,
 ).to('cuda')
 model.eval()
 prov=frozen.derive_model_provenance(device_name)
 v23_validate_model_provenance(prov)
 return tokenizer,model,prov




def install_v23_capability_overrides()->None:
 # Patch only process-local operational admission hooks. Frozen science bytes stay unchanged.
 frozen.validate_model_provenance=v23_validate_model_provenance
 frozen.load_production_runtime=v23_load_production_runtime
 import replay_residual_natural_packet_validator_v2_1 as packet_validator
 packet_validator.validate_model_provenance=v23_validate_model_provenance

def _sha_file(p:Path)->str:
 return hashlib.sha256(p.read_bytes()).hexdigest()

def _load_json(p:Path)->dict[str,Any]:
 return json.loads(p.read_text(encoding='utf-8'))

def _atomic_json(path:Path,obj:dict[str,Any])->None:
 if path.exists(): raise RuntimeError(f'OUTPUT_EXISTS_REFUSE_OVERWRITE:{path}')
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix=path.name+'.tmp.',dir=str(path.parent))
 try:
  with os.fdopen(fd,'wb') as f:
   b=frozen.canonical_json_bytes(obj); f.write(b); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,path); frozen._fsync_dir(path.parent)
 except Exception:
  try: os.unlink(tmp)
  except FileNotFoundError: pass
  raise

def _replace_json(path:Path,obj:dict[str,Any])->None:
 fd,tmp=tempfile.mkstemp(prefix=path.name+'.tmp.',dir=str(path.parent))
 try:
  with os.fdopen(fd,'wb') as f:
   b=frozen.canonical_json_bytes(obj); f.write(b); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,path); frozen._fsync_dir(path.parent)
 except Exception:
  try: os.unlink(tmp)
  except FileNotFoundError: pass
  raise

def _bound_info()->dict[str,str]:
 if _BOUND is None or _BOUND_PATH is None or _BOUND_SHA256 is None: raise RuntimeError('BOUND_CONTRACT_NOT_LOADED')
 info=binding.validate_bound(_BOUND,binding.load_template(ROOT))
 return {**info,'bound_contract_sha256':_BOUND_SHA256,'bound_contract_path':str(_BOUND_PATH)}
def _successor_meta()->dict[str,Any]:
 i=_bound_info()
 return {
  'contract_sha256':binding.CONTRACT_SHA256,'bound_binding_sha256':i['bound_contract_sha256'],
  'successor_experiment_id':i['experiment_id'],'successor_prediction_id':i['prediction_id'],
  'independent_design_review_sha256':binding.REVIEW_SHA256,
  'independent_design_review_verdict':binding.REVIEW_VERDICT,
  'runtime_fingerprint':i['runtime_fingerprint'],
  'capability_attestation_sha256':i['capability_attestation_sha256'],
  'thin_output_wrapper_sha256':THIN_WRAPPER_SHA256,'scientific_variables_changed':[]
 }

def _load_bound(path:Path)->None:
 global _BOUND,_BOUND_PATH,_BOUND_SHA256
 p=path.resolve(); obj=_load_json(p); binding.validate_bound(obj,binding.load_template(ROOT))
 _BOUND=obj; _BOUND_PATH=p; _BOUND_SHA256=_sha_file(p)

def _rewrite_hidden_identity(hidden:Path,old_manifest:dict[str,Any])->dict[str,Any]:
 info=_bound_info(); meta=_successor_meta()
 mp=hidden/'manifest.json'; pp=hidden/'provenance.json'
 old_prov=_load_json(pp)
 manifest=copy.deepcopy(old_manifest)
 manifest['kind']='REPLAY_RESIDUAL_V2_3_CAPABILITY_SUCCESSOR_PACKET_SET_MANIFEST'
 manifest['experiment_id']=info['experiment_id']; manifest['prediction_id']=info['prediction_id']
 manifest['capability_successor_v2_3']=meta
 expected=copy.deepcopy(old_manifest); expected['kind']=manifest['kind']; expected['experiment_id']=info['experiment_id']; expected['prediction_id']=info['prediction_id']; expected['capability_successor_v2_3']=meta
 if manifest!=expected: raise RuntimeError('MANIFEST_REBIND_DRIFT')
 _replace_json(mp,manifest)
 provenance=copy.deepcopy(old_prov)
 provenance['kind']='REPLAY_RESIDUAL_V2_3_CAPABILITY_SUCCESSOR_PACKET_SET_PROVENANCE'
 provenance['packet_manifest_sha256']=frozen.sha256_file(mp)
 provenance['capability_successor_v2_3']=meta
 expectedp=copy.deepcopy(old_prov); expectedp['kind']=provenance['kind']; expectedp['packet_manifest_sha256']=provenance['packet_manifest_sha256']; expectedp['capability_successor_v2_3']=meta
 if provenance!=expectedp: raise RuntimeError('PROVENANCE_REBIND_DRIFT')
 _replace_json(pp,provenance)
 return manifest

def _validate_successor_dir(directory:Path)->dict[str,Any]:
 info=_bound_info(); meta=_successor_meta(); d=directory.resolve()
 expected_names={frozen.packet_filename(i) for i in frozen.DEV_INDICES}|{'manifest.json','provenance.json'}
 actual={p.name for p in d.iterdir() if p.is_file()} if d.is_dir() else set()
 if actual!=expected_names: raise RuntimeError('SUCCESSOR_FILE_SET_MISMATCH')
 m=_load_json(d/'manifest.json'); p=_load_json(d/'provenance.json')
 if m.get('kind')!='REPLAY_RESIDUAL_V2_3_CAPABILITY_SUCCESSOR_PACKET_SET_MANIFEST': raise RuntimeError('SUCCESSOR_MANIFEST_KIND_MISMATCH')
 if m.get('experiment_id')!=info['experiment_id'] or m.get('prediction_id')!=info['prediction_id']: raise RuntimeError('SUCCESSOR_IDENTITY_MISMATCH')
 if m.get('producer_contract_sha256')!=frozen.CONTRACT_SHA256 or m.get('indices')!=list(frozen.DEV_INDICES) or int(m.get('attempted_count',-1))!=32 or not bool(m.get('no_replacement')): raise RuntimeError('SUCCESSOR_PARENT_SCIENCE_BINDING_MISMATCH')
 if m.get('capability_successor_v2_3')!=meta: raise RuntimeError('SUCCESSOR_MANIFEST_META_MISMATCH')
 hashes=m.get('packet_sha256_by_filename',{})
 if set(hashes)!={frozen.packet_filename(i) for i in frozen.DEV_INDICES}: raise RuntimeError('SUCCESSOR_PACKET_HASH_KEYSET_MISMATCH')
 for name,want in hashes.items():
  if frozen.sha256_file(d/name)!=want: raise RuntimeError(f'SUCCESSOR_PACKET_HASH_MISMATCH:{name}')
 if p.get('contract_sha256')!=frozen.CONTRACT_SHA256 or p.get('review_sha256')!=frozen.REVIEW_SHA256 or p.get('protocol_sha256')!=frozen.PROTOCOL_SHA256: raise RuntimeError('SUCCESSOR_PARENT_PROVENANCE_MISMATCH')
 if p.get('packet_manifest_sha256')!=frozen.sha256_file(d/'manifest.json') or p.get('capability_successor_v2_3')!=meta: raise RuntimeError('SUCCESSOR_PROVENANCE_MISMATCH')
 if int(p.get('model_calls_during_engineering',-1))!=0 or int(p.get('environment_execution_during_engineering',-1))!=0 or p.get('scientific_outcomes_accessed_during_engineering') is not False: raise RuntimeError('SUCCESSOR_ENGINEERING_ISOLATION_PROVENANCE_MISMATCH')
 return m

def successor_rebinding_atomic_publish(root:Path,packets:Sequence[Mapping[str,Any]],final_rel:Path=SUCCESSOR_PACKET_REL,validator_fn=None,tokenizer=None):
 if Path(final_rel)!=SUCCESSOR_PACKET_REL: raise RuntimeError('UNEXPECTED_SUCCESSOR_PUBLIC_TARGET')
 final=root/SUCCESSOR_PACKET_REL
 if final.exists(): raise FileExistsError(f'FINAL_PACKET_TARGET_ALREADY_EXISTS:{final}')
 hidden_rel=SUCCESSOR_PACKET_REL.parent/f'.{SUCCESSOR_PACKET_REL.name}.prebind.{os.getpid()}.{uuid.uuid4().hex}'
 hidden=root/hidden_rel
 try:
  hidden_path,old_manifest=_ORIGINAL_ATOMIC(root,packets,final_rel=hidden_rel,validator_fn=validator_fn,tokenizer=tokenizer)
  if hidden_path!=hidden: raise RuntimeError('HIDDEN_PUBLICATION_PATH_MISMATCH')
  successor_manifest=_rewrite_hidden_identity(hidden,old_manifest)
  _validate_successor_dir(hidden)
  if final.exists(): raise FileExistsError(f'FINAL_TARGET_RACE:{final}')
  os.rename(hidden,final); frozen._fsync_dir(final.parent)
  return final,successor_manifest
 except Exception:
  shutil.rmtree(hidden,ignore_errors=True); raise

def scan_technical_errors(directory:Path)->dict[str,Any]:
 _validate_successor_dir(directory)
 errors=[]; actions=0
 for idx in frozen.DEV_INDICES:
  pkt=_load_json(directory/frozen.packet_filename(idx))
  if not str(pkt.get('initial_observation','')).strip(): errors.append({'index':idx,'stage':'environment_reset','type':'EMPTY_INITIAL_OBSERVATION'})
  if not str(pkt.get('task_instruction','')).strip(): errors.append({'index':idx,'stage':'initial_observation_received','type':'EMPTY_TASK_INSTRUCTION'})
  if not isinstance(pkt.get('plan_provenance'),dict) or not pkt.get('plan_provenance'): errors.append({'index':idx,'stage':'planner_called','type':'PLANNER_PROVENANCE_MISSING'})
  for r in pkt.get('qualification_stage1_reasons',[]):
   if r=='INVALID_COMMAND_OR_EXECUTION_ERROR' or r not in _ALLOWED_STAGE1: errors.append({'index':idx,'stage':'executor_started','type':'STAGE1_TECHNICAL_REASON','message':str(r)})
  for r in pkt.get('qualification_stage2_reasons',[]):
   if r not in _ALLOWED_STAGE2 and r!='': errors.append({'index':idx,'stage':'scientific_eligibility_evaluated','type':'STAGE2_TECHNICAL_REASON','message':str(r)})
  for a in pkt.get('actions',[]):
   actions+=1
   if a.get('error'): errors.append({'index':idx,'stage':'executor_started','type':'ACTION_ERROR','message':str(a.get('error'))})
 return {'technical_errors':errors,'environment_actions_executed':actions,'technical_valid':not errors}
def _write_attestation(path:Path,obj:dict[str,Any])->None: _atomic_json(path,obj)
def attest(directory:Path,result_path:Path|None,output:Path)->int:
 scan=scan_technical_errors(directory); info=_bound_info(); base={
  'kind':'PLANCARRY_REPLAYRESIDUAL_V23_EXECUTION_ATTESTATION','attestation_contract_sha256':ATTESTATION_CONTRACT_SHA256,
  'attestation_review_sha256':ATTESTATION_REVIEW_SHA256,'bound_contract_sha256':info['bound_contract_sha256'],
  'successor_experiment_id':info['experiment_id'],'successor_prediction_id':info['prediction_id'],'technical_errors':scan['technical_errors'],
  'stages':{'runtime_initialized':False,'environment_reset':False,'initial_observation_received':False,'planner_called':False,'plan_parsed':False,'executor_started':False,'scientific_eligibility_evaluated':False,'scientific_metric_evaluated':False,'environment_actions_executed':scan['environment_actions_executed']}
 }
 if scan['technical_errors']:
  base.update({'technical_status':'FAIL','episode_state':'TECHNICAL_ERROR','technical_valid':False,'measurement_reached':False})
  _write_attestation(output,base); print(json.dumps({'status':'TECHNICAL_ERROR','attestation':str(output)},sort_keys=True)); return 2
 if result_path is None:
  print(json.dumps({'status':'PHASE1_TECHNICAL_PASS_NO_ATTESTATION_WRITTEN','environment_actions_executed':scan['environment_actions_executed']},sort_keys=True)); return 0
 if not result_path.is_file(): raise RuntimeError('RESULT_MISSING_FOR_FINAL_ATTESTATION')
 result=_load_json(result_path); m=_load_json(directory/'manifest.json')
 if result.get('development_population_indices')!=list(frozen.DEV_INDICES) or result.get('sealed_population_accessed') is not False or int(result.get('causal_intervention_requests',-1))!=0: raise RuntimeError('RESULT_SCOPE_OR_CAUSAL_GUARD_MISMATCH')
 q=int(m.get('final_qualified_count',-1)); gate=str(result.get('gate',''))
 if q<0 or not gate: raise RuntimeError('RESULT_TERMINAL_GATE_MISSING')
 base['stages']={'runtime_initialized':True,'environment_reset':True,'initial_observation_received':True,'planner_called':True,'plan_parsed':True,'executor_started':True,'scientific_eligibility_evaluated':True,'scientific_metric_evaluated':True,'environment_actions_executed':scan['environment_actions_executed']}
 base.update({'technical_status':'PASS','episode_state':'QUALIFIED' if q>=frozen.MIN_FINAL_QUALIFIED else 'PROTOCOL_REACHED_NOT_ELIGIBLE','technical_valid':True,'measurement_reached':True,'final_qualified_count':q,'terminal_gate':gate,'result_sha256':_sha_file(result_path),'packet_manifest_sha256':frozen.sha256_file(directory/'manifest.json')})
 _write_attestation(output,base); print(json.dumps({'status':'ATTESTATION_PASS','attestation':str(output),'episode_state':base['episode_state']},sort_keys=True)); return 0

def main(argv:Sequence[str]|None=None)->int:
 ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
 for name in ('produce','validate','attest'):
  sp=sub.add_parser(name); sp.add_argument('--root',default='.'); sp.add_argument('--bound-contract',required=True)
  if name in ('validate','attest'): sp.add_argument('--packet-dir',required=True)
  if name=='attest': sp.add_argument('--result'); sp.add_argument('--output',required=True)
 args=ap.parse_args(argv); root=Path(args.root).resolve()
 global ROOT; ROOT=root
 _load_bound(Path(args.bound_contract))
 if args.cmd=='produce':
  if _sha_file(root/'replay_residual_natural_packet_producer_v2_2_technical_successor.py')!=THIN_WRAPPER_SHA256: raise RuntimeError('THIN_WRAPPER_SHA_MISMATCH')
  # V2.3 capability-bound execution: retain device name only as provenance.
  install_v23_capability_overrides()
  thin.SUCCESSOR_PACKET_TARGET_REL=SUCCESSOR_PACKET_REL
  os.chdir(root); thin._ORIGINAL_ATOMIC_PUBLISH=successor_rebinding_atomic_publish
  return int(thin.main(['--root',str(root),'--execute-science']))
 if args.cmd=='validate': _validate_successor_dir(Path(args.packet_dir)); print(json.dumps({'status':'SUCCESSOR_PACKET_SET_VALID','bound_contract_sha256':_BOUND_SHA256},sort_keys=True)); return 0
 return attest(Path(args.packet_dir),Path(args.result) if args.result else None,Path(args.output))
if __name__=='__main__': raise SystemExit(main())
