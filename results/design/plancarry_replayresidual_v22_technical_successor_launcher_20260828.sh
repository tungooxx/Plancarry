#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
TP=/opt/gpu-lab/envs/plancarry-rr-tokenizer4513/lib/python3.13/site-packages
AP=/opt/gpu-lab/envs/plancarry-rr-alfworld-py313-v21/lib/python3.13/site-packages
export PYTHONPATH="$TP:$AP${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME="${HF_HOME:-$ROOT/.hf_cache_qwen3_v21}"
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export ALFWORLD_DATA="${ALFWORLD_DATA:-/opt/gpu-lab/data/plancarry-alfworld}"
STATIC_PY="${PLANCARRY_STATIC_PYTHON:-python3}"
PY="${PLANCARRY_PYTHON:-}"
PACKETS="$ROOT/results/science/plancarry_replay_residual_sanity_packets_v2_2_technical_retry1"
OUT="$ROOT/results/science/plancarry_replay_residual_representation_sanity_v2_2_technical_retry1.json"
TEMPLATE="$ROOT/results/design/plancarry_replayresidual_v22_unified_execution_contract_template_20260828.json"
BINDER="$ROOT/results/design/plancarry_replayresidual_v22_postregistration_binding_20260828.py"
ADAPTER="$ROOT/results/design/plancarry_replayresidual_v22_registered_packet_adapter_20260828.py"

sha_eq(){ [[ "$(sha256sum "$1" | awk '{print $1}')" == "$2" ]] || { echo "SHA256_MISMATCH:$1" >&2; exit 70; }; }
verify_static(){
  sha_eq results/design/plancarry_replay_residual_unified_execution_contract_v2_1_rw_20260821.json 83370fbfc65c4818ada159a0e3c83cf778b88ed02f964bcf7887e5cea3843158
  sha_eq replay_residual_natural_packet_producer_v2_2_technical_successor.py d1be7ecbabc1ac3d8d24587a57e53141623b320615400a5acd0d9b7437635ab8
  sha_eq replay_residual_natural_packet_producer_v2_1_py313_compat.py 5e2caea4d6c6d2139dd696950299f3d2ad4cadb21dbcc1a0670e2d7805677472
  sha_eq replay_residual_textworld_py313_compat_v1.py a08a1e1e5536afc11d94868de40eaea89cb929ef43b59a1102f378446284a7f4
  sha_eq results/design/plancarry_replayresidual_v22_technical_successor_policy_v1_20260822.json c9ee11ccaad981441c1462a60b59b9bd4ffa021b149ac4f0d18df568f4724c70
  sha_eq results/design/plancarry_replayresidual_v22_technical_successor_policy_independent_review_a2_20260822.json 7044718fbef271fb86d8243e4345e2970894a66d65326be2c9d292af9214c750
  sha_eq results/design/plancarry_replayresidual_v22_execution_attestation_contract_v1_20260822.json 40ae9747f675dc136a59ecc6e2c7ae28d4d329860566c542cbf1691d84bbc666
  sha_eq results/design/plancarry_replayresidual_v22_execution_attestation_contract_v1_static_audit_20260822.json 825ed04dbf87e890abf9e9d2085e2fe39722696327dfbd49aa3ebe3435292ad1
  sha_eq results/design/plancarry_replayresidual_v22_execution_attestation_independent_review_a2_20260822.json a03a4cc7f2d7c83fe8df3112edba5b373bd0d4241d6f20731a373f62adc39765
  sha_eq "$TEMPLATE" 691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1
  sha_eq "$BINDER" 3ef7dc647a8cf478fd35ae9ae8c1a2e0b5d0f76b60691b42a1a0ecce9ad03545
  sha_eq "$ADAPTER" 94402dfb7d6de174773fbefb9d5733f73b1dbc9648d6d1a36764c3e6dd0f77c0
  sha_eq replay_residual_natural_packet_validator_v2_1.py f63fc8508c262452a2f72f617cc5dbc79a9f2c595c96ebda5f3916651fab44f2
  sha_eq replay_residual_sanity_runner_v1.py 7a2c45dadb89a6e0736e53638132b69a38792ab83a3915a9d67ef937ce0a1bd3
  sha_eq replay_residual_capture_only_sidecar_v1.py 9bc1b5976798c37a989fb4aa4a9e91b2d6004f90185713687c8bf13fee35e3aa
  sha_eq whitebox_bridge_prefixstable_proto.py d8c5ad9abd3cf45181a07cf8f1f837e7b36d3c47d59e7dc7cc4225f1a5e66404
  "$STATIC_PY" - "$TEMPLATE" <<'PY'
import hashlib,json,sys
p=sys.argv[1]; x=json.load(open(p)); t=x['technical_successor_v2_2']
assert t['scientific_variables_changed']==[]
assert t['registration_binding']['successor_experiment_id']=='UNBOUND_REQUIRES_POSTREGISTRATION_BINDING'
assert t['execution_attestation']['independent_review_sha256']=='a03a4cc7f2d7c83fe8df3112edba5b373bd0d4241d6f20731a373f62adc39765'
assert t['output_binding']['old_v2_1_packet_or_result_contents_may_be_successor_input'] is False
print('V22_TEMPLATE_STATIC_BINDING_PASS')
PY
}
preflight(){
  verify_static
  [[ ! -e "$PACKETS" ]] || { echo 'REFUSE_EXISTING_V22_PACKET_TARGET' >&2; exit 71; }
  [[ ! -e "$OUT" ]] || { echo 'REFUSE_EXISTING_V22_RESULT_TARGET' >&2; exit 72; }
  printf '%s\n' '{"status":"READY_NO_SCIENCE","model_calls":0,"model_loads":0,"environment_execution":0,"scientific_result_reads":0,"old_v21_science_reads":0,"reserve_access":false,"valid_seen_access":false,"valid_unseen_access":false,"registration_bound":false,"reset_canary_required_before_execute":true,"native_execution_attestation_required":true}'
}
validate_reset_canary(){
  local p="$1"
  "$STATIC_PY" - "$p" <<'PY'
import hashlib,json,sys
p=sys.argv[1]; x=json.load(open(p))
assert x.get('kind')=='REPLAYRESIDUAL_V22_RESET_COMPATIBILITY_CANARY'
assert x.get('technical_status')=='PASS'
assert x.get('attestation_contract_sha256')=='40ae9747f675dc136a59ecc6e2c7ae28d4d329860566c542cbf1691d84bbc666'
assert x.get('compat_shim_sha256')=='a08a1e1e5536afc11d94868de40eaea89cb929ef43b59a1102f378446284a7f4'
assert x.get('study_cohort_access') is False and int(x.get('model_calls',-1))==0 and int(x.get('environment_actions',-1))==0
assert x.get('environment_reset') is True and x.get('initial_observation_nonempty') is True and x.get('admissible_commands_nonempty') is True
assert x.get('target_kind') in {'SYNTHETIC_TEXTWORLD_GRAMMAR_CANARY','PROSPECTIVELY_FROZEN_NON_STUDY_GAME'}
print('RESET_COMPATIBILITY_CANARY_PASS')
PY
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
  [[ "${REPLAYRESIDUAL_V22_EXECUTION_AUTHORIZATION:-}" == 'RESEARCH_DECISION_BOUND' ]] || { echo 'RESEARCH_DECISION_AUTHORIZATION_REQUIRED' >&2; exit 73; }
  local bound="${REPLAYRESIDUAL_V22_BOUND_CONTRACT:-}"; [[ -n "$bound" && -f "$bound" ]] || { echo 'BOUND_CONTRACT_REQUIRED' >&2; exit 74; }
  local canary="${REPLAYRESIDUAL_V22_RESET_CANARY_ATTESTATION:-}"; [[ -n "$canary" && -f "$canary" ]] || { echo 'RESET_CANARY_ATTESTATION_REQUIRED' >&2; exit 75; }
  local attest="${REPLAYRESIDUAL_V22_EXECUTION_ATTESTATION:-}"; [[ -n "$attest" ]] || { echo 'EXECUTION_ATTESTATION_TARGET_REQUIRED' >&2; exit 76; }
  [[ ! -e "$PACKETS" ]] || { echo 'REFUSE_EXISTING_V22_PACKET_TARGET' >&2; exit 77; }
  [[ ! -e "$OUT" ]] || { echo 'REFUSE_EXISTING_V22_RESULT_TARGET' >&2; exit 78; }
  [[ ! -e "$attest" ]] || { echo 'REFUSE_EXISTING_EXECUTION_ATTESTATION' >&2; exit 79; }
  "$PY" "$BINDER" validate-bound --root "$ROOT" --input "$bound" >/dev/null
  validate_reset_canary "$canary" >/dev/null
  local TMP; TMP=$(mktemp -d "$ROOT/.replayresidual_v22_exec.XXXXXX")
  local BRIDGE_PID='' SIDECAR_PID='' CURRENT_STAGE='packet_production'
  cleanup(){ set +e; [[ -z "$SIDECAR_PID" ]] || { kill "$SIDECAR_PID" 2>/dev/null || true; wait "$SIDECAR_PID" 2>/dev/null || true; }; [[ -z "$BRIDGE_PID" ]] || { kill "$BRIDGE_PID" 2>/dev/null || true; wait "$BRIDGE_PID" 2>/dev/null || true; }; rm -rf "$TMP"; }
  write_failure_attestation(){
    local code="$1" line="$2" stage="$3"
    [[ -e "$attest" ]] && return 0
    "$PY" - "$attest" "$bound" "$code" "$line" "$stage" "$PACKETS" <<'PY'
import hashlib,json,os,sys,tempfile
out,bound,code,line,stage,packet_dir=sys.argv[1:]
b=json.load(open(bound)); rb=b['technical_successor_v2_2']['registration_binding']
# The packet producer's technical scan is the first point after which every study-side
# reset/planner/parser/executor/eligibility stage is known to have completed without a
# technical error.  Preserve that distinction in failure attestations rather than
# falsely claiming that no prior stage ran.
packet_phase_passed = stage in {'capture_runtime_initialization','representation_sanity_evaluation','native_execution_attestation_finalize'}
metric_completed = stage == 'native_execution_attestation_finalize'
actions=0
if packet_phase_passed and os.path.isdir(packet_dir):
    for name in os.listdir(packet_dir):
        if name.startswith('packet_') and name.endswith('.json'):
            try:
                actions += len(json.load(open(os.path.join(packet_dir,name))).get('actions',[]))
            except Exception:
                pass
stages={'runtime_initialized':packet_phase_passed,'environment_reset':packet_phase_passed,'initial_observation_received':packet_phase_passed,'planner_called':packet_phase_passed,'plan_parsed':packet_phase_passed,'executor_started':packet_phase_passed,'scientific_eligibility_evaluated':packet_phase_passed,'scientific_metric_evaluated':metric_completed,'environment_actions_executed':actions}
obj={'kind':'PLANCARRY_REPLAYRESIDUAL_V22_EXECUTION_ATTESTATION','attestation_contract_sha256':'40ae9747f675dc136a59ecc6e2c7ae28d4d329860566c542cbf1691d84bbc666','attestation_review_sha256':'a03a4cc7f2d7c83fe8df3112edba5b373bd0d4241d6f20731a373f62adc39765','bound_contract_sha256':hashlib.sha256(open(bound,'rb').read()).hexdigest(),'successor_experiment_id':rb['successor_experiment_id'],'successor_prediction_id':rb['successor_prediction_id'],'technical_status':'FAIL','episode_state':'TECHNICAL_ERROR','technical_valid':False,'measurement_reached':False,'technical_errors':[{'stage':stage,'type':'LAUNCHER_OR_RUNTIME_FAILURE','message':f'exit={code}:line={line}'}],'stages':stages}
os.makedirs(os.path.dirname(os.path.abspath(out)),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=os.path.basename(out)+'.tmp.',dir=os.path.dirname(os.path.abspath(out)))
with os.fdopen(fd,'w') as f: json.dump(obj,f,sort_keys=True,separators=(',',':')); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.replace(tmp,out)
PY
  }
  on_err(){ local code=$? line=${BASH_LINENO[0]:-0}; write_failure_attestation "$code" "$line" "$CURRENT_STAGE" || true; exit "$code"; }
  trap cleanup EXIT INT TERM
  trap on_err ERR
  "$PY" "$ADAPTER" produce --root "$ROOT" --bound-contract "$bound" >"$TMP/packet_producer.log" 2>&1
  CURRENT_STAGE='packet_publication_validation'
  "$PY" "$ADAPTER" validate --root "$ROOT" --bound-contract "$bound" --packet-dir "$PACKETS" >"$TMP/packet_validator.log" 2>&1
  CURRENT_STAGE='packet_technical_attestation'
  "$PY" "$ADAPTER" attest --root "$ROOT" --bound-contract "$bound" --packet-dir "$PACKETS" --output "$attest" >"$TMP/phase1_attestation.log" 2>&1
  [[ ! -e "$attest" ]] || { echo 'PHASE1_ATTESTATION_UNEXPECTED_TERMINAL_ARTIFACT' >&2; exit 80; }
  CURRENT_STAGE='capture_runtime_initialization'
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
  "$PY" whitebox_bridge_prefixstable_proto.py --host 127.0.0.1 --port 8892 --disable-patch --model-id Qwen/Qwen3-1.7B --revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e --device cuda --dtype bfloat16 --expected-device-substring 'NVIDIA GeForce RTX 3050 Laptop GPU' >"$TMP/bridge.log" 2>&1 &
  BRIDGE_PID=$!; wait_health http://127.0.0.1:8892/health "$UP_TOKEN"
  export PLANCARRY_REPLAY_SANITY_TOKEN="$DOWN_TOKEN"
  "$PY" replay_residual_capture_only_sidecar_v1.py --host 127.0.0.1 --port 8893 --upstream http://127.0.0.1:8892 --upstream-token-file "$TMP/upstream.token" --downstream-token-env PLANCARRY_REPLAY_SANITY_TOKEN >"$TMP/sidecar.log" 2>&1 &
  SIDECAR_PID=$!; wait_health http://127.0.0.1:8893/health "$DOWN_TOKEN"
  CURRENT_STAGE='representation_sanity_evaluation'
  "$PY" replay_residual_sanity_runner_v1.py --episode-dir "$PACKETS" --output "$OUT" --url http://127.0.0.1:8893 --token "$DOWN_TOKEN" >"$TMP/sanity_runner.log" 2>&1
  CURRENT_STAGE='native_execution_attestation_finalize'
  "$PY" "$ADAPTER" attest --root "$ROOT" --bound-contract "$bound" --packet-dir "$PACKETS" --result "$OUT" --output "$attest" >"$TMP/final_attestation.log" 2>&1
  [[ -s "$attest" ]] || { echo 'FINAL_ATTESTATION_MISSING' >&2; exit 81; }
  trap - ERR
  printf '%s\n' '{"status":"V22_EXECUTION_TERMINAL_ATTESTATION_READY","partial_scientific_outcomes_printed":false,"next_required_step":"research_execution_attest_before_research_experiment_sync_or_assessment"}'
}
case "${1:-}" in
  preflight) preflight ;;
  execute) execute ;;
  *) echo 'usage: launcher {preflight|execute}' >&2; exit 64 ;;
esac
