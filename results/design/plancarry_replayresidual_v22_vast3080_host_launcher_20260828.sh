#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
TARGET_INSTANCE='vast_48954592'
TARGET_DEVICE='NVIDIA GeForce RTX 3080'
SOURCE_LAUNCHER="$ROOT/results/design/plancarry_replayresidual_v22_technical_successor_launcher_20260828.sh"
HOST_ADAPTER="$ROOT/results/design/plancarry_replayresidual_v22_vast3080_registered_adapter_20260828.py"
CANARY="$ROOT/results/design/plancarry_replayresidual_v22_reset_compat_canary_20260828.py"
BOUND="$ROOT/results/design/plancarry_replayresidual_v22_unified_execution_contract_bound_a4_20260828.json"
PACKETS="$ROOT/results/science/plancarry_replay_residual_sanity_packets_v2_2_technical_retry1"
RESULT="$ROOT/results/science/plancarry_replay_residual_representation_sanity_v2_2_technical_retry1.json"
PY="${PLANCARRY_PYTHON:-}"

sha_eq(){ [[ "$(sha256sum "$1" | awk '{print $1}')" == "$2" ]] || { echo "SHA256_MISMATCH:$1" >&2; exit 70; }; }

verify_host_static(){
  [[ "${REPLAYRESIDUAL_V22_VAST_INSTANCE_ID:-}" == "$TARGET_INSTANCE" ]] || { echo 'VAST_INSTANCE_BINDING_REQUIRED' >&2; exit 83; }
  [[ -n "$PY" && -x "$PY" ]] || { echo 'EXACT_PLANCARRY_PYTHON_REQUIRED' >&2; exit 82; }
  sha_eq "$SOURCE_LAUNCHER" bdfc84b6e8fb3062cde1e1c76abf3edf775ae0c65b9ca8a57c02dffc22fb4e65
  sha_eq "$HOST_ADAPTER" 4c2a26c317a51488911007bcb4b3e3b2dfd92907252eeb3ce3549779c9efe80d
  sha_eq "$CANARY" 52e6065915dd5406bf9d44e9669e48d711a307d73c2b722cc9f424b3de39f396
  sha_eq "$BOUND" f125b6f8a0c96ca74beb75893e9ac6a40ea2ea436306e73c4b0667150ecd3726
  local device
  device="$(nvidia-smi --query-gpu=name --format=csv,noheader | sed -e 's/[[:space:]]*$//' -e '/^$/d')"
  [[ "$device" == "$TARGET_DEVICE" ]] || { echo "VAST_DEVICE_NAME_MISMATCH:$device:$TARGET_DEVICE" >&2; exit 84; }
  "$PY" - <<'PY'
import importlib.metadata,sys,torch
assert tuple(sys.version_info[:3])==(3,13,15), sys.version
want={'torch':'2.13.0+cu130','transformers':'4.51.3','tokenizers':'0.21.1','textworld':'1.7.0','alfworld':'0.4.2'}
got={k:importlib.metadata.version(k) for k in want if k!='torch'}; got['torch']=str(torch.__version__)
assert got==want,(got,want)
print('V22_VAST_RUNTIME_VERSION_BINDING_PASS')
PY
  [[ ! -e "$PACKETS" ]] || { echo 'REFUSE_EXISTING_V22_PACKET_TARGET' >&2; exit 71; }
  [[ ! -e "$RESULT" ]] || { echo 'REFUSE_EXISTING_V22_RESULT_TARGET' >&2; exit 72; }
}

render_launcher(){
  local out="$1"
  "$PY" - "$SOURCE_LAUNCHER" "$out" <<'PY'
import pathlib,sys
src=pathlib.Path(sys.argv[1]).read_text(); out=pathlib.Path(sys.argv[2])
subs=[
('ADAPTER="$ROOT/results/design/plancarry_replayresidual_v22_registered_packet_adapter_20260828.py"','ADAPTER="$ROOT/results/design/plancarry_replayresidual_v22_vast3080_registered_adapter_20260828.py"'),
('sha_eq "$ADAPTER" 94402dfb7d6de174773fbefb9d5733f73b1dbc9648d6d1a36764c3e6dd0f77c0','sha_eq "$ADAPTER" 4c2a26c317a51488911007bcb4b3e3b2dfd92907252eeb3ce3549779c9efe80d'),
("--expected-device-substring 'NVIDIA GeForce RTX 3050 Laptop GPU'","--expected-device-substring 'NVIDIA GeForce RTX 3080'")]
for old,new in subs:
    if src.count(old)!=1: raise SystemExit('HOST_LAUNCHER_PATCH_OCCURRENCE_MISMATCH:'+old)
    src=src.replace(old,new)
out.write_text(src)
PY
  chmod 700 "$out"
}

validate_host_canary(){
  local p="$1"
  "$PY" - "$p" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['kind']=='REPLAYRESIDUAL_V22_RESET_COMPATIBILITY_CANARY'
assert x['technical_status']=='PASS'
assert x['instance_id']=='vast_48954592'
assert x['device_name']=='NVIDIA GeForce RTX 3080'
assert x['python_version']=='3.13.15'
assert x['package_versions']=={'torch':'2.13.0+cu130','transformers':'4.51.3','tokenizers':'0.21.1','textworld':'1.7.0','alfworld':'0.4.2'}
assert x['study_cohort_access'] is False and x['model_calls']==0 and x['model_loads']==0 and x['environment_actions']==0
assert x['environment_reset'] is True and x['initial_observation_nonempty'] is True and x['admissible_commands_nonempty'] is True
print('V22_VAST_HOST_CANARY_BINDING_PASS')
PY
}

preflight(){
  verify_host_static
  local tmp
  tmp="$(mktemp "$ROOT/results/design/.v22_vast3080_launcher.XXXXXX.sh")"
  trap 'rm -f "$tmp"' RETURN
  render_launcher "$tmp"
  REPLAYRESIDUAL_V22_VAST_INSTANCE_ID="$TARGET_INSTANCE" bash "$tmp" preflight
  printf '%s\n' '{"status":"READY_NO_SCIENCE_VAST3080","instance_id":"vast_48954592","device_name":"NVIDIA GeForce RTX 3080","scientific_variables_changed":[],"model_calls":0,"model_loads":0,"environment_execution":0,"study_cohort_access":false,"future_split_access":false}'
  rm -f "$tmp"; trap - RETURN
}

reset_canary(){
  verify_host_static
  local out="${REPLAYRESIDUAL_V22_RESET_CANARY_ATTESTATION:-}"
  [[ -n "$out" ]] || { echo 'RESET_CANARY_ATTESTATION_TARGET_REQUIRED' >&2; exit 85; }
  "$PY" "$CANARY" --root "$ROOT" --instance-id "$TARGET_INSTANCE" --output "$out"
  validate_host_canary "$out"
}

execute(){
  verify_host_static
  local canary="${REPLAYRESIDUAL_V22_RESET_CANARY_ATTESTATION:-}"
  [[ -n "$canary" && -f "$canary" ]] || { echo 'RESET_CANARY_ATTESTATION_REQUIRED' >&2; exit 75; }
  validate_host_canary "$canary"
  local tmp
  tmp="$(mktemp "$ROOT/results/design/.v22_vast3080_launcher.XXXXXX.sh")"
  trap 'rm -f "$tmp"' EXIT INT TERM
  render_launcher "$tmp"
  bash "$tmp" execute
}

case "${1:-}" in
  preflight) preflight ;;
  reset-canary) reset_canary ;;
  execute) execute ;;
  *) echo 'usage: host_launcher {preflight|reset-canary|execute}' >&2; exit 64 ;;
esac
