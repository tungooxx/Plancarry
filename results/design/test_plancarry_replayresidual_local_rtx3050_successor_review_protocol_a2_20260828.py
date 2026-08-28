import copy,hashlib,json,pathlib
R=pathlib.Path(__file__).resolve().parents[2]
P=R/"results/design/plancarry_replayresidual_local_rtx3050_successor_review_protocol_a2_20260828.json"
T=R/"results/design/plancarry_replayresidual_v22_unified_execution_contract_template_20260828.json"
B=R/"results/design/plancarry_replayresidual_v22_unified_execution_contract_bound_a4_20260828.json"
assert hashlib.sha256(T.read_bytes()).hexdigest()=="691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1"
assert hashlib.sha256(B.read_bytes()).hexdigest()=="f125b6f8a0c96ca74beb75893e9ac6a40ea2ea436306e73c4b0667150ecd3726"
p=json.loads(P.read_bytes())
assert p["target_bytes_inspected_before_freeze"] is False
d=p["authorized_successor_execution_delta"]; assert d["device_name_required"]=="NVIDIA GeForce RTX 3050 Laptop GPU" and d["instance_id_required"]=="local" and d["remote_execution_required"] is False and d["observed_local_vram_mib"]==4096 and d["observed_local_driver"]=="581.95"
s=p["scientific_invariance_requirements"]; assert s["scientific_protocol_variables_changed"]==[] and s["estimand_changed"] is False and s["population"]["development_indices"]==list(range(32)) and s["population"]["sealed_reserve_indices"]==list(range(32,64))
assert p["model_calls"]==p["model_loads"]==p["environment_execution"]==0 and p["scientific_outcomes_accessed"] is False and p["future_split_access"] is False and p["provider_lifecycle"] is False
t=copy.deepcopy(p); expected=t.pop("canonical_object_sha256_without_self_field"); raw=json.dumps(t,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode(); assert hashlib.sha256(raw).hexdigest()==expected
print("PASS_LOCAL_RTX3050_SUCCESSOR_PROSPECTIVE_REVIEW_PROTOCOL")
