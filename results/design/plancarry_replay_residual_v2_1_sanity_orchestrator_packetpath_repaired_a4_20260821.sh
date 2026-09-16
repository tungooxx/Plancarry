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
TMP=$(mktemp -d "$ROOT/.replayresidual_v21_exec.XXXXXX")
BRIDGE_PID=''
SIDECAR_PID=''
cleanup() {
  set +e
  if [[ -n "$SIDECAR_PID" ]]; then kill "$SIDECAR_PID" 2>/dev/null || true; wait "$SIDECAR_PID" 2>/dev/null || true; fi
  if [[ -n "$BRIDGE_PID" ]]; then kill "$BRIDGE_PID" 2>/dev/null || true; wait "$BRIDGE_PID" 2>/dev/null || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM
[[ ! -e "$PACKETS" ]]
[[ ! -e "$OUT" ]]
# Phase 1: exact frozen all-32 natural-plan packet production; atomic publication only after all32 validation.
"$PY" replay_residual_natural_packet_producer_v2_1.py --root "$ROOT" --execute-science
# Phase 2: fresh model process; capture path only. /patch_score is disabled at the bridge and absent at the sidecar.
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
  --expected-device-substring 'NVIDIA GeForce RTX 3050 Laptop GPU' &
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
            if r.status==200:
                sys.exit(0)
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
  --downstream-token-env PLANCARRY_REPLAY_SANITY_TOKEN &
SIDECAR_PID=$!
wait_health http://127.0.0.1:8893/health "$DOWN_TOKEN"
"$PY" replay_residual_sanity_runner_v1.py \
  --episode-dir "$PACKETS" \
  --output "$OUT" \
  --url http://127.0.0.1:8893 \
  --token "$DOWN_TOKEN"
