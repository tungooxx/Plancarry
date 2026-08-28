from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[2]
def load(p): return json.loads((ROOT/p).read_text())
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha_file(p): return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def sha_obj(x): return hashlib.sha256(canon(x)).hexdigest()
SRC='results/design/plancarry_replayresidual_v22_unified_execution_contract_bound_a4_20260828.json'
REG='results/design/plancarry_replayresidual_v22_successor_registration_a4_20260828.json'
NEW='results/design/plancarry_replayresidual_v23_local_rtx3050_successor_authority_a4_20260828.json'
s=load(SRC); r=load(REG); n=load(NEW)
assert sha_file('results/design/plancarry_replayresidual_v22_unified_execution_contract_template_20260828.json')=='691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1'
assert sha_file(SRC)=='f125b6f8a0c96ca74beb75893e9ac6a40ea2ea436306e73c4b0667150ecd3726'
assert sha_file(REG)=='1149e656d96c58844952e09ccce007adf33deed899404c5691a71bc1fbd2e633'
assert r['user_compute_constraint']['backend']=='VAST_REQUIRED' and r['user_compute_constraint']['local_gpu_execution_forbidden'] is True
assert n['execution_authority']['backend']=='LOCAL' and n['execution_authority']['instance_id_required']=='local'
assert n['execution_authority']['remote_execution_required'] is False
assert n['execution_authority']['device_name_required']==s['model_runtime']['device_name_required']=='NVIDIA GeForce RTX 3050 Laptop GPU'
assert n['scientific_protocol_inheritance']['scientific_protocol_variables_changed']==[] and n['scientific_protocol_inheritance']['estimand_changed'] is False
for k,h in n['scientific_protocol_inheritance']['section_sha256'].items(): assert sha_obj(s[k])==h,(k,sha_obj(s[k]),h)
assert n['scientific_protocol_inheritance']['model_id']==s['model_runtime']['model_id']=='Qwen/Qwen3-1.7B'
assert n['scientific_protocol_inheritance']['model_revision']==s['model_runtime']['revision']=='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'
assert n['scientific_protocol_inheritance']['dtype']=='bfloat16'
assert s['population']['development_indices']==list(range(32)); assert s['population']['sealed_reserve_indices']==[32,63]
assert s['sanity_binding']['candidate_layers']==[7,14,21,27]
assert s['qualification']['minimum_final_qualified']==16
assert len(s['replay_conditions'])==7
assert n['output_targets']['packet']!=s['output_semantics']['final_target_dir']
assert n['output_targets']['result']!=s['output_semantics']['representation_sanity_result_target']
selfh=n['canonical_object_sha256_without_self_field']; assert selfh==sha_obj({k:v for k,v in n.items() if k!='canonical_object_sha256_without_self_field'})
for bad in ['reserve32..63','valid_seen','valid_unseen','T1','T1R','KV']:
 assert any(bad in x for x in n['prohibitions'])
print('PASS_V23_LOCAL_RTX3050_AUTHORITY_OVERLAY')
