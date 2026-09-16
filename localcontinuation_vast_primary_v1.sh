#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
: "${PLANCARRY_EXPECTED_GIT_COMMIT:?PLANCARRY_EXPECTED_GIT_COMMIT must be bound after independent executable review}"
: "${LOCALCONT_EXPECTED_DEVICE_NAME:=NVIDIA GeForce RTX 4070 SUPER}"
: "${PLANCARRY_PYTHON:=/opt/gpu-lab/envs/plancarry-replayresidual-t1-retry/bin/python}"
export CUBLAS_WORKSPACE_CONFIG="${CUBLAS_WORKSPACE_CONFIG:-:4096:8}"
ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "$ACTUAL_COMMIT" == "$PLANCARRY_EXPECTED_GIT_COMMIT" ]] || { echo "GIT_COMMIT_MISMATCH:$ACTUAL_COMMIT:$PLANCARRY_EXPECTED_GIT_COMMIT" >&2; exit 91; }
[[ "$LOCALCONT_EXPECTED_DEVICE_NAME" == "NVIDIA GeForce RTX 4070 SUPER" ]] || { echo "DEVICE_BINDING_MISMATCH:$LOCALCONT_EXPECTED_DEVICE_NAME" >&2; exit 92; }
[[ -x "$PLANCARRY_PYTHON" ]] || { echo "PYTHON_NOT_EXECUTABLE:$PLANCARRY_PYTHON" >&2; exit 93; }
for p in results/science/plancarry_replayresidual_localcontinuation_dev_packets_v1 results/science/plancarry_replayresidual_localcontinuation_development_grid_v1.json results/science/plancarry_replayresidual_localcontinuation_development_selection_v1.json results/science/plancarry_replayresidual_localcontinuation_development_terminal_v1.json results/science/plancarry_replayresidual_localcontinuation_confirmation_packets_v1 results/science/plancarry_replayresidual_localcontinuation_confirmation_payload_v1.json results/science/plancarry_replayresidual_localcontinuation_primary_result_v1.json; do
 [[ ! -e "$p" ]] || { echo "REFUSE_EXISTING_PRIMARY_OUTPUT:$p" >&2; exit 94; }
done
# This reviewed Vast handoff is DEVELOPMENT-ONLY. It must stop before any
# confirmation model/environment request. A separate fresh ResearchDecision is
# required after the development seal/futility outcome is frozen and assessed.
"$PLANCARRY_PYTHON" localcontinuation_science_driver_v1.py --phase development --expected-device "$LOCALCONT_EXPECTED_DEVICE_NAME"
if [[ -f results/science/plancarry_replayresidual_localcontinuation_development_selection_v1.json ]]; then
  echo "DEVELOPMENT_SELECTION_FROZEN; confirmation remains sealed pending separate ResearchDecision"
else
  STATUS="$($PLANCARRY_PYTHON -c "import json; print(json.load(open('results/science/plancarry_replayresidual_localcontinuation_development_terminal_v1.json'))['status'])")"
  echo "DEVELOPMENT_TERMINAL:$STATUS; confirmation remains sealed"
fi
