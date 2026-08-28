#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export HF_HOME="${HF_HOME:-$ROOT/.hf_cache_qwen3_v23}"
export ALFWORLD_DATA="${ALFWORLD_DATA:-/opt/gpu-lab/data/plancarry-alfworld}"
PY="${PLANCARRY_PYTHON:-}"
STATIC_PY="${PLANCARRY_STATIC_PYTHON:-${PY:-python3}}"
PACKETS="$ROOT/results/science/plancarry_replay_residual_sanity_packets_v2_3_capability_successor1"
OUT="$ROOT/results/science/plancarry_replay_residual_representation_sanity_v2_3_capability_successor1.json"
CONTRACT="$ROOT/results/design/plancarry_replayresidual_v23_capability_bound_cuda_successor_contract_a1_20260828.json"
VALIDATOR="$ROOT/replayresidual_v23_capability_validator_a1.py"
BINDER="$ROOT/results/design/plancarry_replayresidual_v23_execution_binding_20260828.py"
ADAPTER="$ROOT/results/design/plancarry_replayresidual_v23_registered_packet_adapter_20260828.py"

sha_eq(){ [[ "$(sha256sum "$1" | awk '{print $1}')" == "$2" ]] || { echo "SHA256_MISMATCH:$1" >&2; exit 70; }; }
verify_static(){
  sha_eq "$CONTRACT" 1289bbf073e4f4c6411a82cdac069ff9fe9094cacb92e4ccb333712d8af4a3bc
  sha_eq "$VALIDATOR" a04a79fed515323bd42067d52bd5590506cc336e8de43345876524fc47507293
  sha_eq "$BINDER" 31a2c8cf46c3fbd3b23bae0252a107dd5811f0d6a0c87a372c0e544bdd865d1f
  sha_eq "$ADAPTER" b1906d5b3830f738c63ec82554b0d1a2a0d9fb0005e99e98c94f1f8002216bc8
  # Frozen scientific machinery is inherited byte-for-byte from V2.2.
  sha_eq replay_residual_natural_packet_producer_v2_2_technical_successor.py d1be7ecbabc1ac3d8d24587a57e53141623b320615400a5acd0d9b7437635ab8
  sha_eq replay_residual_natural_packet_producer_v2_1_py313_compat.py 5e2caea4d6c6d2139dd696950299f3d2ad4cadb21dbcc1a0670e2d7805677472
  sha_eq replay_residual_natural_packet_producer_v2_1.py bb05eb8b3b02f15d32f768212730712f2f0a04062729a57ca4993be2031dec55
  sha_eq replay_residual_textworld_py313_compat_v1.py a08a1e1e5536afc11d94868de40eaea89cb929ef43b59a1102f378446284a7f4
  sha_eq replay_residual_natural_packet_validator_v2_1.py f63fc8508c262452a2f72f617cc5dbc79a9f2c595c96ebda5f3916651fab44f2
  sha_eq replay_residual_sanity_runner_v1.py 7a2c45dadb89a6e0736e53638132b69a38792ab83a3915a9d67ef937ce0a1bd3
  sha_eq replay_residual_capture_only_sidecar_v1.py 9bc1b5976798c37a989fb4aa4a9e91b2d6004f90185713687c8bf13fee35e3aa
  sha_eq whitebox_bridge_prefixstable_proto.py d8c5ad9abd3cf45181a07cf8f1f837e7b36d3c47d59e7dc7cc4225f1a5e66404
}
validate_binding_and_capability(){
  local bound="${REPLAYRESIDUAL_V23_BOUND_BINDING:-}" canary="${REPLAYRESIDUAL_V23_CAPABILITY_ATTESTATION:-}"
  [[ -n "$bound" && -f "$bound" ]] || { echo 'V23_BOUND_BINDING_REQUIRED' >&2; exit 74; }
  [[ -n "$canary" && -f "$canary" ]] || { echo 'V23_CAPABILITY_ATTESTATION_REQUIRED' >&2; exit 75; }
  "$STATIC_PY" "$BINDER" validate-bound --root "$ROOT" --input "$bound" >/dev/null
  "$STATIC_PY" "$VALIDATOR" "$CONTRACT" "$canary" >/dev/null
  local current_uuid
  current_uuid=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1 | tr -d "[:space:]")
  [[ -n "$current_uuid" ]] || { echo 'CURRENT_GPU_UUID_REQUIRED' >&2; exit 83; }
  "$STATIC_PY" - "$bound" "$canary" "$current_uuid" <<'PY'
import hashlib,json,sys
b=json.load(open(sys.argv[1])); a=json.load(open(sys.argv[2])); current_uuid=sys.argv[3]
assert b['experiment_id']=='47972f24-71ca-4001-8a1e-ca3dddb7c621'
assert b['prediction_id']=='55ab178a-67cb-4d82-a91c-cc9cac14b189'
assert a['runtime_fingerprint']==b['runtime_fingerprint']
canary_sha=hashlib.sha256(open(sys.argv[2],'rb').read()).hexdigest()
assert canary_sha==b['capability_attestation_sha256']
assert b['superseded_registration_execution_forbidden'] is True
assert b['packet_target']=='results/science/plancarry_replay_residual_sanity_packets_v2_3_capability_successor1'
assert b['result_target']=='results/science/plancarry_replay_residual_representation_sanity_v2_3_capability_successor1.json'
assert a['actual_gpu_uuid_if_available']==current_uuid
print('V23_BINDING_CAPABILITY_PASS')
PY
}
preflight(){
  verify_static
  [[ -n "$PY" && -x "$PY" ]] || { echo 'EXACT_PLANCARRY_PYTHON_REQUIRED' >&2; exit 82; }
  validate_binding_and_capability
  [[ ! -e "$PACKETS" ]] || { echo 'REFUSE_EXISTING_V23_PACKET_TARGET' >&2; exit 71; }
  [[ ! -e "$OUT" ]] || { echo 'REFUSE_EXISTING_V23_RESULT_TARGET' >&2; exit 72; }
  printf '%s\n' '{"status":"READY_NO_SCIENCE","experiment_id":"47972f24-71ca-4001-8a1e-ca3dddb7c621","prediction_id":"55ab178a-67cb-4d82-a91c-cc9cac14b189","model_calls":0,"model_loads":0,"environment_execution":0,"scientific_result_reads":0,"reserve_access":false,"valid_seen_access":false,"valid_unseen_access":false,"capability_attestation_valid":true,"gpu_name_admission":false}'
}
wait_health(){
  local url="$1" token="$2"
  "$PY" - "$url" "$token" <<'PY'
import sys,time,urllib.request
url,token=sys.argv[1],sys.argv[2]; last=None
for _ in range(180):
    try:
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=2) as r:
            if r.status==200: raise SystemExit(0)
    except Exception as e: last=repr(e)
    time.sleep(1)
raise SystemExit('HEALTH_TIMEOUT:'+str(last))
PY
}
execute(){
  verify_static
  [[ -n "$PY" && -x "$PY" ]] || { echo 'EXACT_PLANCARRY_PYTHON_REQUIRED' >&2; exit 82; }
  [[ "${REPLAYRESIDUAL_V23_EXECUTION_AUTHORIZATION:-}" == 'RESEARCH_DECISION_BOUND' ]] || { echo 'RESEARCH_DECISION_AUTHORIZATION_REQUIRED' >&2; exit 73; }
  validate_binding_and_capability
  local bound="$REPLAYRESIDUAL_V23_BOUND_BINDING"
  local attest="${REPLAYRESIDUAL_V23_EXECUTION_ATTESTATION:-}"; [[ -n "$attest" ]] || { echo 'EXECUTION_ATTESTATION_TARGET_REQUIRED' >&2; exit 76; }
  [[ ! -e "$PACKETS" ]] || { echo 'REFUSE_EXISTING_V23_PACKET_TARGET' >&2; exit 77; }
  [[ ! -e "$OUT" ]] || { echo 'REFUSE_EXISTING_V23_RESULT_TARGET' >&2; exit 78; }
  [[ ! -e "$attest" ]] || { echo 'REFUSE_EXISTING_EXECUTION_ATTESTATION' >&2; exit 79; }
  local TMP; TMP=$(mktemp -d "$ROOT/.replayresidual_v23_exec.XXXXXX")
  local BRIDGE_PID='' SIDECAR_PID=''
  cleanup(){ set +e; [[ -z "${SIDECAR_PID:-}" ]] || { kill "$SIDECAR_PID" 2>/dev/null || true; wait "$SIDECAR_PID" 2>/dev/null || true; }; [[ -z "${BRIDGE_PID:-}" ]] || { kill "$BRIDGE_PID" 2>/dev/null || true; wait "$BRIDGE_PID" 2>/dev/null || true; }; [[ -z "${TMP:-}" ]] || rm -rf "$TMP"; }
  trap cleanup EXIT INT TERM
  "$PY" "$ADAPTER" produce --root "$ROOT" --bound-contract "$bound" >"$TMP/packet_producer.log" 2>&1
  "$PY" "$ADAPTER" validate --root "$ROOT" --bound-contract "$bound" --packet-dir "$PACKETS" >"$TMP/packet_validator.log" 2>&1
  "$PY" "$ADAPTER" attest --root "$ROOT" --bound-contract "$bound" --packet-dir "$PACKETS" --output "$attest" >"$TMP/phase1_attestation.log" 2>&1
  [[ ! -e "$attest" ]] || { echo 'PHASE1_ATTESTATION_UNEXPECTED_TERMINAL_ARTIFACT' >&2; exit 80; }
  local UP_TOKEN DOWN_TOKEN
  UP_TOKEN=$($PY - <<'PY'
import secrets; print(secrets.token_urlsafe(48))
PY
)
  DOWN_TOKEN=$($PY - <<'PY'
import secrets; print(secrets.token_urlsafe(48))
PY
)
  printf '%s\n' "$UP_TOKEN" > "$TMP/upstream.token"
  export PLANCARRY_WHITEBOX_TOKEN="$UP_TOKEN"
  # Empty expected-device substring deliberately disables product-name admission;
  # capability/runtime admission was validated above from the frozen V2.3 attestation.
  "$PY" whitebox_bridge_prefixstable_proto.py --host 127.0.0.1 --port 8892 --disable-patch --model-id Qwen/Qwen3-1.7B --revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e --device cuda --dtype bfloat16 --expected-device-substring '' >"$TMP/bridge.log" 2>&1 &
  BRIDGE_PID=$!; wait_health http://127.0.0.1:8892/health "$UP_TOKEN"
  export PLANCARRY_REPLAY_SANITY_TOKEN="$DOWN_TOKEN"
  "$PY" replay_residual_capture_only_sidecar_v1.py --host 127.0.0.1 --port 8893 --upstream http://127.0.0.1:8892 --upstream-token-file "$TMP/upstream.token" --downstream-token-env PLANCARRY_REPLAY_SANITY_TOKEN >"$TMP/sidecar.log" 2>&1 &
  SIDECAR_PID=$!; wait_health http://127.0.0.1:8893/health "$DOWN_TOKEN"
  "$PY" replay_residual_sanity_runner_v1.py --episode-dir "$PACKETS" --output "$OUT" --url http://127.0.0.1:8893 --token "$DOWN_TOKEN" >"$TMP/sanity_runner.log" 2>&1
  "$PY" "$ADAPTER" attest --root "$ROOT" --bound-contract "$bound" --packet-dir "$PACKETS" --result "$OUT" --output "$attest" >"$TMP/final_attestation.log" 2>&1
  [[ -s "$attest" ]] || { echo 'FINAL_ATTESTATION_MISSING' >&2; exit 81; }
  printf '%s\n' '{"status":"V23_EXECUTION_TERMINAL_ATTESTATION_READY","partial_scientific_outcomes_printed":false,"next_required_step":"research_execution_attest_before_scientific_assessment"}'
}
case "${1:-}" in
  preflight) preflight ;;
  execute) execute ;;
  *) echo 'usage: launcher {preflight|execute}' >&2; exit 64 ;;
esac
