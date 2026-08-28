import copy
import hashlib
import json
import pathlib
import sys

REQUIRED_RUNTIME = {
    "model_id": "Qwen/Qwen3-1.7B",
    "revision": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    "dtype": "bfloat16",
    "quantization": "NONE",
    "offload": "NONE",
    "torch": "2.13.0+cu130",
    "transformers": "4.51.3",
    "tokenizers": "0.21.1",
}
EXPECTED_LAYERS = [7, 14, 21, 27]
EXPECTED_CANARY = {
    "model_id": REQUIRED_RUNTIME["model_id"],
    "revision": REQUIRED_RUNTIME["revision"],
    "dtype": REQUIRED_RUNTIME["dtype"],
    "quantization": REQUIRED_RUNTIME["quantization"],
    "offload": REQUIRED_RUNTIME["offload"],
    "study_packet_access": False,
    "future_split_access": False,
    "environment_execution": 0,
    "prefix_token_count": 128,
    "teacher_forced_suffix_token_count": 128,
    "capture_layers": EXPECTED_LAYERS,
    "hook_count_per_layer": 1,
    "scientific_result": "NOT_ASSESSED_RUNTIME_CANARY_ONLY",
}
REQUIRED_ATTESTATION_FIELDS = [
    "actual_gpu_name",
    "actual_gpu_uuid_if_available",
    "driver_version",
    "cuda_runtime",
    "compute_capability",
    "total_vram_mib",
    "driver_free_vram_before_canary_mib",
    "peak_reserved_mib",
    "post_canary_reserved_mib",
    "repeat_reserved_span_mib",
    "bf16_supported",
    "oom_events",
    "runtime_fingerprint",
    "cuda_available",
    "repeat_count",
    "capture_layers",
    "hook_count_by_layer",
    "model_id",
    "revision",
    "dtype",
    "quantization",
    "offload",
    "torch",
    "transformers",
    "tokenizers",
]

def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def _sha256(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()

def validate_contract(c):
    errors = []
    if "canonical_object_sha256_without_self_field" not in c:
        errors.append("CONTRACT_SELF_HASH_MISSING")
    else:
        body = copy.deepcopy(c)
        expected = body.pop("canonical_object_sha256_without_self_field")
        if _sha256(body) != expected:
            errors.append("CONTRACT_SELF_HASH_MISMATCH")
    mr = c.get("model_runtime", {})
    if "device_name_required" in mr:
        errors.append("EXACT_GPU_NAME_LOCK_FORBIDDEN")
    if c.get("scientific_protocol_variables_changed") != []:
        errors.append("SCIENCE_DELTA_NONEMPTY")
    if c.get("estimand_changed") is not False:
        errors.append("ESTIMAND_CHANGED")
    adm = c.get("execution_capability_admission", {})
    if adm.get("gpu_name_whitelist") is not None or adm.get("gpu_name_blacklist") is not None:
        errors.append("GPU_NAME_LIST_FORBIDDEN")
    if adm.get("provider_or_instance_whitelist") is not None:
        errors.append("PROVIDER_IDENTITY_LOCK_FORBIDDEN")
    for k, v in REQUIRED_RUNTIME.items():
        if mr.get(k) != v:
            errors.append(f"RUNTIME_MISMATCH:{k}")
    canary = adm.get("exact_model_stress_canary", {})
    for k, v in EXPECTED_CANARY.items():
        if canary.get(k) != v:
            errors.append(f"CANARY_CONTRACT_MISMATCH:{k}")
    required = c.get("runtime_attestation", {}).get("required_actual_fields", [])
    for k in REQUIRED_ATTESTATION_FIELDS:
        if k not in required:
            errors.append(f"REQUIRED_ATTESTATION_FIELD_MISSING:{k}")
    return errors

def validate_attestation(c, a):
    errors = validate_contract(c)
    required = c.get("runtime_attestation", {}).get("required_actual_fields", [])
    for k in required:
        if k not in a:
            errors.append(f"MISSING_ATTESTATION:{k}")
    if errors:
        return errors
    if not a.get("cuda_available", False):
        errors.append("CUDA_UNAVAILABLE")
    if not a.get("bf16_supported", False):
        errors.append("BF16_UNSUPPORTED")
    for k, v in REQUIRED_RUNTIME.items():
        if a.get(k) != v:
            errors.append(f"ATTESTED_RUNTIME_MISMATCH:{k}")
    if int(a.get("oom_events", -1)) != 0:
        errors.append("CANARY_OOM")
    if int(a.get("repeat_count", 0)) < 3:
        errors.append("CANARY_REPEAT_COUNT_LT3")
    if float(a.get("repeat_reserved_span_mib", 1e18)) > 64:
        errors.append("CANARY_RESERVED_GROWTH")
    if a.get("capture_layers") != EXPECTED_LAYERS:
        errors.append("CANARY_LAYER_SET_MISMATCH")
    hooks = a.get("hook_count_by_layer", [])
    if len(hooks) != 4 or any(int(x) != 1 for x in hooks):
        errors.append("CANARY_HOOK_COUNT")
    peak = float(a.get("peak_reserved_mib", 1e18))
    total = float(a.get("total_vram_mib", 0))
    free = float(a.get("driver_free_vram_before_canary_mib", 0))
    head = float(c["execution_capability_admission"]["memory_headroom_policy"]["minimum_headroom_mib"])
    if total - peak < head:
        errors.append("TOTAL_VRAM_HEADROOM_LT_REQUIRED")
    if free - peak < head:
        errors.append("LIVE_FREE_VRAM_HEADROOM_LT_REQUIRED")
    if not str(a.get("actual_gpu_name", "")).strip():
        errors.append("ACTUAL_GPU_NAME_NOT_RECORDED")
    return errors

def load_contract(path):
    return json.loads(pathlib.Path(path).read_text())

if __name__ == "__main__":
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: capability_validator CONTRACT.json [ATTESTATION.json]")
    c = load_contract(sys.argv[1])
    errors = validate_contract(c) if len(sys.argv) == 2 else validate_attestation(c, json.loads(pathlib.Path(sys.argv[2]).read_text()))
    print(json.dumps({"pass": not errors, "errors": errors}, sort_keys=True))
    raise SystemExit(0 if not errors else 2)
