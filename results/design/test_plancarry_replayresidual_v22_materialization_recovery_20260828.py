#!/usr/bin/env python3
from __future__ import annotations
import copy, hashlib, importlib.util, json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'results/design'
PARENT=D/'plancarry_replay_residual_unified_execution_contract_v2_1_rw_20260821.json'
TEMPLATE=D/'plancarry_replayresidual_v22_unified_execution_contract_template_20260828.json'
BINDER=D/'plancarry_replayresidual_v22_postregistration_binding_20260828.py'
ADAPTER=D/'plancarry_replayresidual_v22_registered_packet_adapter_20260828.py'
LAUNCHER=D/'plancarry_replayresidual_v22_technical_successor_launcher_20260828.sh'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(PARENT)=='83370fbfc65c4818ada159a0e3c83cf778b88ed02f964bcf7887e5cea3843158'
assert sha(TEMPLATE)=='691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1'
assert sha(ROOT/'replay_residual_natural_packet_producer_v2_2_technical_successor.py')=='d1be7ecbabc1ac3d8d24587a57e53141623b320615400a5acd0d9b7437635ab8'
assert sha(ROOT/'replay_residual_natural_packet_producer_v2_1_py313_compat.py')=='5e2caea4d6c6d2139dd696950299f3d2ad4cadb21dbcc1a0670e2d7805677472'
assert sha(ROOT/'replay_residual_textworld_py313_compat_v1.py')=='a08a1e1e5536afc11d94868de40eaea89cb929ef43b59a1102f378446284a7f4'
assert sha(D/'plancarry_replayresidual_v22_technical_successor_policy_v1_20260822.json')=='c9ee11ccaad981441c1462a60b59b9bd4ffa021b149ac4f0d18df568f4724c70'
assert sha(D/'plancarry_replayresidual_v22_technical_successor_policy_independent_review_a2_20260822.json')=='7044718fbef271fb86d8243e4345e2970894a66d65326be2c9d292af9214c750'
assert sha(D/'plancarry_replayresidual_v22_execution_attestation_contract_v1_20260822.json')=='40ae9747f675dc136a59ecc6e2c7ae28d4d329860566c542cbf1691d84bbc666'
assert sha(D/'plancarry_replayresidual_v22_execution_attestation_contract_v1_static_audit_20260822.json')=='825ed04dbf87e890abf9e9d2085e2fe39722696327dfbd49aa3ebe3435292ad1'
assert sha(D/'plancarry_replayresidual_v22_execution_attestation_independent_review_a2_20260822.json')=='a03a4cc7f2d7c83fe8df3112edba5b373bd0d4241d6f20731a373f62adc39765'
assert json.loads((D/'plancarry_replayresidual_v22_execution_attestation_independent_review_a2_20260822.json').read_text())['verdict']=='PASS_FOR_REPLAYRESIDUAL_V22_EXECUTION_ATTESTATION'
assert json.loads((D/'plancarry_replayresidual_v22_technical_successor_policy_independent_review_a2_20260822.json').read_text())['verdict']=='PASS_FOR_REPLAYRESIDUAL_V22_TECHNICAL_SUCCESSOR_POLICY'

parent=json.loads(PARENT.read_text()); new=json.loads(TEMPLATE.read_text())
def diffs(a,b,p=''):
 out=[]
 if type(a)!=type(b): return [p]
 if isinstance(a,dict):
  for k in sorted(set(a)|set(b)):
   q=f'{p}.{k}' if p else k
   if k not in a or k not in b: out.append(q)
   else: out.extend(diffs(a[k],b[k],q))
 elif isinstance(a,list):
  if a!=b: out.append(p)
 elif a!=b: out.append(p)
 return out
actual=set(diffs(parent,new))
allowed={'kind','version','work_item_id','canonical_object_sha256_without_self_field','output_semantics.final_target_dir','output_semantics.representation_sanity_result_target','technical_successor_v2_2'}
assert actual==allowed,(actual,allowed)
assert new['technical_successor_v2_2']['scientific_variables_changed']==[]
assert new['output_semantics']['final_target_dir'].endswith('_v2_2_technical_retry1')
assert new['technical_successor_v2_2']['output_binding']['old_v2_1_packet_or_result_contents_may_be_successor_input'] is False
# Every exact parent scientific/scoring/control object not on the tiny allowed-path list remains deep-equal.
for k in ['model_runtime','population','planner','executor','qualification','replay_conditions','sanity_binding','packet_schema','observable_input_contract','trajectory','phase_isolation','prohibitions','authoritative_sources']:
 assert parent[k]==new[k],k

# Old science paths may never occur as terminal literals in executable successor source.
def assert_no_terminal_old_path(text:str,old:str):
 start=0
 while True:
  i=text.find(old,start)
  if i<0:return
  j=i+len(old)
  assert j<len(text) and text[j]=='_',f'terminal old path leaked: {old}'
  start=j
for p in [BINDER,ADAPTER,LAUNCHER]:
 text=p.read_text()
 assert_no_terminal_old_path(text,'results/science/plancarry_replay_residual_sanity_packets_v2')
 assert 'results/science/plancarry_replay_residual_representation_sanity_v2_1.json' not in text

# Dynamically import only pure engineering modules (production imports are deferred).
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(D))
import plancarry_replayresidual_v22_postregistration_binding_20260828 as binding
import plancarry_replayresidual_v22_registered_packet_adapter_20260828 as adapter
with tempfile.TemporaryDirectory() as td:
 td=Path(td); bound=td/'bound.json'
 obj=binding.bind_contract(ROOT,'11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333','a'*64,binding.REQUIRED_MATERIALIZATION_REVIEW_VERDICT)
 bound.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
 binding.validate_bound(obj,binding.load_template(ROOT))
 tam=copy.deepcopy(obj); tam['executor']['action_budget']=13; tam['canonical_object_sha256_without_self_field']=binding.canonical_no_self_hash(tam)
 try: binding.validate_bound(tam,binding.load_template(ROOT))
 except RuntimeError as e: assert 'DRIFT_OUTSIDE_POSTREGISTRATION_FIELDS' in str(e)
 else: raise AssertionError('scientific tamper accepted')
 try: binding.bind_contract(ROOT,'11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333','a'*64,'MATERIAL_REPAIR_REQUIRED')
 except RuntimeError as e: assert 'NOT_EXACT_PASS' in str(e)
 else: raise AssertionError('non-PASS review accepted')
 # Synthetic publication metadata rebind: dummy packet bytes must not change.
 adapter.ROOT=ROOT; adapter._load_bound(bound)
 packetdir=td/'packets'; packetdir.mkdir(); hashes={}
 for idx in adapter.frozen.DEV_INDICES:
  name=adapter.frozen.packet_filename(idx)
  pkt={'initial_observation':'obs','task_instruction':'task','plan_provenance':{'planner':'called'},'qualification_stage1_reasons':['PLAN_ACCEPTANCE_FAILED'],'qualification_stage2_reasons':['NOT_IN_FROZEN_TRAJECTORY_ELIGIBLE_E'],'actions':[]}
  b=(json.dumps(pkt,sort_keys=True,separators=(',',':'))+'\n').encode(); (packetdir/name).write_bytes(b); hashes[name]=hashlib.sha256(b).hexdigest()
 oldm={'kind':'REPLAY_RESIDUAL_V2_1_PACKET_SET_MANIFEST','producer_contract_sha256':adapter.frozen.CONTRACT_SHA256,'packet_contract_version':adapter.frozen.PACKET_CONTRACT_VERSION,'experiment_id':'fbfeb9e9-4850-46c7-ad13-326cbe8da380','prediction_id':'d3208f84-ad00-47e3-ad77-c6a320e08c2d','indices':list(adapter.frozen.DEV_INDICES),'packet_sha256_by_filename':hashes,'attempted_count':32,'trajectory_eligible_count':0,'final_qualified_count':0,'minimum_final_qualified':adapter.frozen.MIN_FINAL_QUALIFIED,'below_minimum_label':'INCONCLUSIVE_INSUFFICIENT_NATURAL_TRAJECTORIES','no_replacement':True,'anchor_cycle':adapter.frozen.ANCHOR_CYCLE,'publication_mode':'PRIVATE_INPROGRESS_FSYNC_VALIDATE_ATOMIC_RENAME_NO_RESUME','scientific_result':'NOT_ASSESSED_PACKET_PRODUCTION_ONLY'}
 (packetdir/'manifest.json').write_bytes(adapter.frozen.canonical_json_bytes(oldm))
 oldp={'kind':'REPLAY_RESIDUAL_V2_1_PACKET_SET_PROVENANCE','contract_path':str(adapter.frozen.CONTRACT_REL),'contract_sha256':adapter.frozen.CONTRACT_SHA256,'review_path':str(adapter.frozen.REVIEW_REL),'review_sha256':adapter.frozen.REVIEW_SHA256,'protocol_sha256':adapter.frozen.PROTOCOL_SHA256,'packet_manifest_sha256':adapter.frozen.sha256_file(packetdir/'manifest.json'),'model_calls_during_engineering':0,'environment_execution_during_engineering':0,'scientific_outcomes_accessed_during_engineering':False}
 (packetdir/'provenance.json').write_bytes(adapter.frozen.canonical_json_bytes(oldp))
 before={n:hashlib.sha256((packetdir/n).read_bytes()).hexdigest() for n in hashes}
 adapter._rewrite_hidden_identity(packetdir,oldm); adapter._validate_successor_dir(packetdir)
 after={n:hashlib.sha256((packetdir/n).read_bytes()).hexdigest() for n in hashes}
 assert before==after
 m=json.loads((packetdir/'manifest.json').read_text()); assert m['experiment_id'].startswith('11111111-') and m['prediction_id'].startswith('22222222-')
 scan=adapter.scan_technical_errors(packetdir); assert scan['technical_valid'] is True,scan
 bad=packetdir/adapter.frozen.packet_filename(0); bp=json.loads(bad.read_text()); bp['qualification_stage1_reasons'].append('NameError:name r is not defined'); bad.write_text(json.dumps(bp,sort_keys=True,separators=(',',':'))+'\n')
 # Repair manifest packet hash only so successor integrity still passes and scanner sees the semantic technical error.
 m=json.loads((packetdir/'manifest.json').read_text()); m['packet_sha256_by_filename'][bad.name]=hashlib.sha256(bad.read_bytes()).hexdigest(); (packetdir/'manifest.json').write_bytes(adapter.frozen.canonical_json_bytes(m))
 pr=json.loads((packetdir/'provenance.json').read_text()); pr['packet_manifest_sha256']=adapter.frozen.sha256_file(packetdir/'manifest.json'); (packetdir/'provenance.json').write_bytes(adapter.frozen.canonical_json_bytes(pr))
 scan=adapter.scan_technical_errors(packetdir); assert scan['technical_valid'] is False and any(x['type']=='STAGE1_TECHNICAL_REASON' for x in scan['technical_errors'])

# Launcher preflight must be executable and explicitly no-science.
r=subprocess.run(['bash',str(LAUNCHER),'preflight'],cwd=ROOT,text=True,capture_output=True,check=True)
out=json.loads(r.stdout.strip().splitlines()[-1]); assert out['status']=='READY_NO_SCIENCE' and out['model_calls']==0 and out['environment_execution']==0 and out['old_v21_science_reads']==0
print(json.dumps({'verdict':'PASS_STATIC_PRE_SCIENCE_V22_MATERIALIZATION','semantic_diff_paths':sorted(actual),'template_sha256':sha(TEMPLATE),'binder_sha256':sha(BINDER),'adapter_sha256':sha(ADAPTER),'launcher_sha256':sha(LAUNCHER),'preflight':out},sort_keys=True))
