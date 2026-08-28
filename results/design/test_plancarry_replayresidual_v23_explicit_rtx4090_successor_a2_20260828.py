import copy,hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]
SRC=ROOT/"results/design/plancarry_replayresidual_v22_unified_execution_contract_template_20260828.json"
DST=ROOT/"results/design/plancarry_replayresidual_v23_explicit_rtx4090_successor_contract_a2_20260828.json"
AUD=ROOT/"results/design/plancarry_replayresidual_v23_explicit_rtx4090_successor_static_audit_a2_20260828.json"
PRE=json.loads(subprocess.check_output(["git","show","8e4ec08184057e1b51a3339840cfac38550e3607:results/design/plancarry_replayresidual_v23_explicit_rtx4090_successor_contract_a2_20260828.json"],cwd=ROOT))
assert hashlib.sha256(SRC.read_bytes()).hexdigest()=="691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1"
s=json.loads(SRC.read_bytes()); d=json.loads(DST.read_bytes()); a=json.loads(AUD.read_bytes()); r=d["model_runtime"]
assert r["device_name_required"]=="NVIDIA GeForce RTX 4090" and r["minimum_vram_mib"]==24000 and r["minimum_compute_capability"]=="8.9" and r["minimum_free_vram_before_science_mib"]==4096 and r["remote_execution_required"] is True
assert d["registered_execution_authority_fields_changed"]==["model_runtime.device_name_required","model_runtime.minimum_vram_mib","model_runtime.minimum_compute_capability","model_runtime.minimum_free_vram_before_science_mib","model_runtime.remote_execution_required","output_semantics.final_target_dir","output_semantics.representation_sanity_result_target"]
assert d["scientific_protocol_variables_changed"]==[] and d["estimand_changed"] is False
assert "scientific_variables_changed" not in d and "scientific_variables_inheritance" not in d
for k in ["authoritative_sources","canonical_hashing","conflict_resolution","executor","observable_input_contract","packet_schema","planner","population","qualification"]: assert d[k]==s[k]
for k in ["model_id","revision","dtype","quantization","offload","enable_thinking","temperature","torch","transformers","tokenizers","device"]: assert r[k]==s["model_runtime"][k]
for k in ["device_name_required","minimum_vram_mib","minimum_compute_capability","minimum_free_vram_before_science_mib","remote_execution_required"]: assert r[k]==PRE["model_runtime"][k]
assert d["output_semantics"]==PRE["output_semantics"] and d["device_provenance_successor"]==PRE["device_provenance_successor"]
assert d["version"]=="2.3-explicit-rtx4090-device-successor" and d["work_item_id"]=="c7ab059c-1013-43b1-8cdd-006879a14c8e"
assert d["lineage_repair_work_item_id"]=="4b1206bd-21a2-4d94-9b08-9468a09e4a34"
ra=d["registration_and_authority"]
assert ra["old_experiment_id"]=="e9a95d91-7b68-4ffc-9f1c-ec3dc5c3c6e9" and ra["old_device_name_required"]=="NVIDIA GeForce RTX 3050 Laptop GPU"
assert ra["old_experiment_execution"]=="IMMUTABLE_RTX3050_ONLY_DO_NOT_MUTATE_OR_REINTERPRET"
assert ra["new_successor_experiment_required"] is True and ra["new_successor_prediction_required"] is True
assert "NEW V2.3" in ra["successor_requirement"] and "V2.1" not in ra["successor_requirement"] and "5ac34da1" not in json.dumps(ra)
def _paths(x,y,p=""):
 out=[]
 if isinstance(x,dict) and isinstance(y,dict):
  for k in sorted(set(x)|set(y)):
   q=f"{p}.{k}" if p else k
   if k not in x or k not in y: out.append(q)
   else: out.extend(_paths(x[k],y[k],q))
 elif x!=y: out.append(p)
 return out
assert set(_paths(PRE,d))=={"canonical_object_sha256_without_self_field","lineage_repair_work_item_id","registration_and_authority.new_successor_experiment_required","registration_and_authority.new_successor_prediction_required","registration_and_authority.old_device_name_required","registration_and_authority.old_experiment_execution","registration_and_authority.old_experiment_id","registration_and_authority.successor_requirement","version","work_item_id"}
t=copy.deepcopy(d); expected=t.pop("canonical_object_sha256_without_self_field"); raw=json.dumps(t,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode(); assert hashlib.sha256(raw).hexdigest()==expected
assert a["predecessor_delta_is_metadata_only"] is True and a["scientific_protocol_variables_changed"]==[] and a["estimand_changed"] is False
assert a["provider_lifecycle_executed"] is False and a["model_calls"]==0 and a["environment_execution"]==0
assert a["predecessor_commit"]=="8e4ec08184057e1b51a3339840cfac38550e3607" and a["lineage_identity_repaired"] is True
assert a["target_sha256"]==hashlib.sha256(DST.read_bytes()).hexdigest()
print("PASS_V23_RTX4090_LINEAGE_AUTHORITY_REPAIR")
