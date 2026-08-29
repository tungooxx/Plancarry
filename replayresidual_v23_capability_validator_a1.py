import copy
import hashlib
import json
import math
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
FINGERPRINT_FIELDS = (
    "actual_gpu_name", "actual_gpu_uuid_if_available", "driver_version", "cuda_runtime", "compute_capability",
    "model_id", "revision", "dtype", "quantization", "offload", "torch", "transformers", "tokenizers",
)
NUMERIC_FIELDS = (
    "total_vram_mib", "driver_free_vram_before_canary_mib", "peak_reserved_mib",
    "post_canary_reserved_mib", "repeat_reserved_span_mib",
)

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

def compute_runtime_fingerprint(a):
    return _sha256({k: a.get(k) for k in FINGERPRINT_FIELDS})

def _finite_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))

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
    for k in NUMERIC_FIELDS:
        if not _finite_number(a.get(k)):
            errors.append(f"NONFINITE_OR_NONNUMERIC:{k}")
    if errors:
        return errors
    for k in ("total_vram_mib", "driver_free_vram_before_canary_mib", "peak_reserved_mib", "post_canary_reserved_mib", "repeat_reserved_span_mib"):
        if float(a[k]) < 0:
            errors.append(f"NEGATIVE_NUMERIC:{k}")
    if float(a["peak_reserved_mib"]) > float(a["total_vram_mib"]):
        errors.append("PEAK_RESERVED_GT_TOTAL")
    if float(a["post_canary_reserved_mib"]) > float(a["total_vram_mib"]):
        errors.append("POST_RESERVED_GT_TOTAL")
    if float(a["driver_free_vram_before_canary_mib"]) > float(a["total_vram_mib"]):
        errors.append("DRIVER_FREE_GT_TOTAL")
    if a.get("cuda_available") is not True:
        errors.append("CUDA_AVAILABLE_NOT_TRUE_BOOL")
    if a.get("bf16_supported") is not True:
        errors.append("BF16_SUPPORTED_NOT_TRUE_BOOL")
    for k, v in REQUIRED_RUNTIME.items():
        if a.get(k) != v:
            errors.append(f"ATTESTED_RUNTIME_MISMATCH:{k}")
    oom=a.get("oom_events")
    repeat=a.get("repeat_count")
    oom_is_int=isinstance(oom,int) and not isinstance(oom,bool) and oom>=0
    repeat_is_int=isinstance(repeat,int) and not isinstance(repeat,bool) and repeat>=0
    if not oom_is_int:
        errors.append("OOM_EVENTS_NOT_NONNEGATIVE_INTEGER")
    elif oom != 0:
        errors.append("CANARY_OOM")
    if not repeat_is_int:
        errors.append("REPEAT_COUNT_NOT_NONNEGATIVE_INTEGER")
    elif repeat < 3:
        errors.append("CANARY_REPEAT_COUNT_LT3")
    if float(a.get("repeat_reserved_span_mib", 1e18)) > 64:
        errors.append("CANARY_RESERVED_GROWTH")
    layers=a.get("capture_layers")
    if layers != EXPECTED_LAYERS or not isinstance(layers,list) or any(not isinstance(x,int) or isinstance(x,bool) for x in layers):
        errors.append("CANARY_LAYER_SET_MISMATCH")
    hooks = a.get("hook_count_by_layer", [])
    if not isinstance(hooks,list) or len(hooks) != 4 or any(not isinstance(x,int) or isinstance(x,bool) or x != 1 for x in hooks):
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
    if not str(a.get("actual_gpu_uuid_if_available", "")).strip():
        errors.append("ACTUAL_GPU_UUID_REQUIRED_FOR_EXECUTION_BINDING")
    if not str(a.get("driver_version", "")).strip():
        errors.append("DRIVER_VERSION_NOT_RECORDED")
    if not str(a.get("cuda_runtime", "")).strip():
        errors.append("CUDA_RUNTIME_NOT_RECORDED")
    if not str(a.get("compute_capability", "")).strip():
        errors.append("COMPUTE_CAPABILITY_NOT_RECORDED")
    try:
        expected_fp = compute_runtime_fingerprint(a)
    except Exception:
        errors.append("RUNTIME_FINGERPRINT_INPUT_INVALID")
    else:
        if a.get("runtime_fingerprint") != expected_fp:
            errors.append("RUNTIME_FINGERPRINT_MISMATCH")
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
