import copy,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]; SRC=ROOT/"results/design/plancarry_replayresidual_v22_unified_execution_contract_template_20260828.json"; DST=ROOT/"results/design/plancarry_replayresidual_v23_explicit_rtx4090_successor_contract_a2_20260828.json"; AUD=ROOT/"results/design/plancarry_replayresidual_v23_explicit_rtx4090_successor_static_audit_a2_20260828.json"
assert hashlib.sha256(SRC.read_bytes()).hexdigest()=="691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1"
s=json.loads(SRC.read_bytes()); d=json.loads(DST.read_bytes()); a=json.loads(AUD.read_bytes()); r=d["model_runtime"]
assert r["device_name_required"]=="NVIDIA GeForce RTX 4090" and r["minimum_vram_mib"]==24000 and r["minimum_compute_capability"]=="8.9" and r["minimum_free_vram_before_science_mib"]==4096 and r["remote_execution_required"] is True
assert d["scientific_variables_changed"]==[]
for k in ["authoritative_sources","canonical_hashing","conflict_resolution","executor","observable_input_contract","packet_schema","planner","population","qualification"]: assert d[k]==s[k]
for k in ["model_id","revision","dtype","quantization","offload","enable_thinking","temperature","torch","transformers","tokenizers","device"]: assert r[k]==s["model_runtime"][k]
assert d["device_provenance_successor"]["live_host_attestation_required_before_registration_decision_execution"] is True
assert d["device_provenance_successor"]["artifact_durability_gate_required_before_science"] is True
t=copy.deepcopy(d); expected=t.pop("canonical_object_sha256_without_self_field"); raw=json.dumps(t,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode(); assert hashlib.sha256(raw).hexdigest()==expected
assert a["unexpected_delta_paths"]==[] and a["provider_offer_bound"] is False and a["provider_lifecycle_executed"] is False and a["model_calls"]==0 and a["environment_execution"]==0
print("PASS_V23_RTX4090_STATIC_FREEZE")
