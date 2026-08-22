#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT=/workspace/local-vlm/LLM/plancarry
cd "$ROOT"
TP=/opt/gpu-lab/envs/plancarry-rr-tokenizer4513/lib/python3.13/site-packages
AP=/opt/gpu-lab/envs/plancarry-rr-alfworld-py313-v21/lib/python3.13/site-packages
export PYTHONPATH="$TP:$AP"
export HF_HOME="$ROOT/.hf_cache_qwen3_v21"
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export ALFWORLD_DATA=/opt/gpu-lab/data/plancarry-alfworld
PY=/opt/gpu-lab/envs/attribot-official/bin/python
PACKETS="$ROOT/results/science/plancarry_replay_residual_sanity_packets_v2"
OUT="$ROOT/results/science/plancarry_replay_residual_representation_sanity_v2_1.json"
TMP=$(mktemp -d "$ROOT/.replayresidual_v21_capture_recovery.XXXXXX")
BRIDGE_PID=''
SIDECAR_PID=''
cleanup() {
  set +e
  if [[ -n "$SIDECAR_PID" ]]; then kill "$SIDECAR_PID" 2>/dev/null || true; wait "$SIDECAR_PID" 2>/dev/null || true; fi
  if [[ -n "$BRIDGE_PID" ]]; then kill "$BRIDGE_PID" 2>/dev/null || true; wait "$BRIDGE_PID" 2>/dev/null || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM
[[ -d "$PACKETS" ]] || { echo 'RECOVERY_PACKET_SET_MISSING' >&2; exit 61; }
[[ ! -e "$OUT" ]] || { echo 'REFUSE_EXISTING_SANITY_RESULT' >&2; exit 62; }
# Fail closed on exact reviewed executable bytes before touching the model.
[[ "$(sha256sum whitebox_bridge_prefixstable_proto.py | awk '{print $1}')" == "d8c5ad9abd3cf45181a07cf8f1f837e7b36d3c47d59e7dc7cc4225f1a5e66404" ]]
[[ "$(sha256sum replay_residual_capture_only_sidecar_v1.py | awk '{print $1}')" == "9bc1b5976798c37a989fb4aa4a9e91b2d6004f90185713687c8bf13fee35e3aa" ]]
[[ "$(sha256sum replay_residual_sanity_runner_v1.py | awk '{print $1}')" == "7a2c45dadb89a6e0736e53638132b69a38792ab83a3915a9d67ef937ce0a1bd3" ]]
[[ "$(sha256sum replay_residual_natural_packet_validator_v2_1.py | awk '{print $1}')" == "f63fc8508c262452a2f72f617cc5dbc79a9f2c595c96ebda5f3916651fab44f2" ]]
# Revalidate the complete atomically published all-32 packet set; no packet regeneration and no outcome inspection.
"$PY" - <<'PY'
from pathlib import Path
from transformers import AutoTokenizer
from replay_residual_natural_packet_validator_v2_1 import validate_packet_directory
tok=AutoTokenizer.from_pretrained('Qwen/Qwen3-1.7B',revision='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e',trust_remote_code=False)
validate_packet_directory(Path('/workspace/local-vlm/LLM/plancarry/results/science/plancarry_replay_residual_sanity_packets_v2'),tok)
print('RECOVERY_PACKET_VALIDATOR_PASS', flush=True)
PY
UP_TOKEN=$($PY - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)
DOWN_TOKEN=$($PY - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)
printf '%s\n' "$UP_TOKEN" > "$TMP/upstream.token"
export PLANCARRY_WHITEBOX_TOKEN="$UP_TOKEN"
"$PY" whitebox_bridge_prefixstable_proto.py \
  --host 127.0.0.1 --port 8892 --disable-patch \
  --model-id Qwen/Qwen3-1.7B \
  --revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --device cuda --dtype bfloat16 \
  --expected-device-substring 'NVIDIA GeForce RTX 3050 Laptop GPU' \
  >"$TMP/bridge.log" 2>&1 &
BRIDGE_PID=$!
wait_health() {
  local url="$1" token="$2"
  "$PY" - "$url" "$token" <<'PY'
import sys,time,urllib.request
url,token=sys.argv[1],sys.argv[2]
last=None
for _ in range(180):
    try:
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=2) as r:
            if r.status==200: raise SystemExit(0)
    except Exception as e:
        last=repr(e)
    time.sleep(1)
raise SystemExit('HEALTH_TIMEOUT:'+str(last))
PY
}
wait_health http://127.0.0.1:8892/health "$UP_TOKEN"
export PLANCARRY_REPLAY_SANITY_TOKEN="$DOWN_TOKEN"
"$PY" replay_residual_capture_only_sidecar_v1.py \
  --host 127.0.0.1 --port 8893 \
  --upstream http://127.0.0.1:8892 \
  --upstream-token-file "$TMP/upstream.token" \
  --downstream-token-env PLANCARRY_REPLAY_SANITY_TOKEN \
  >"$TMP/sidecar.log" 2>&1 &
SIDECAR_PID=$!
wait_health http://127.0.0.1:8893/health "$DOWN_TOKEN"
"$PY" replay_residual_sanity_runner_v1.py \
  --episode-dir "$PACKETS" \
  --output "$OUT" \
  --url http://127.0.0.1:8893 \
  --token "$DOWN_TOKEN"
