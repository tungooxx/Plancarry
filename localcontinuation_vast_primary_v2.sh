#!/usr/bin/env bash
# PRE-SCIENCE handoff wrapper. This script never starts/stops/creates a provider.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
MODE="${1:-preflight}"
[[ "$MODE" == "preflight" || "$MODE" == "development" ]] || { echo "MODE_MUST_BE_PREFLIGHT_OR_DEVELOPMENT" >&2; exit 90; }
: "${PLANCARRY_V2_EXPECTED_GIT_COMMIT:?must bind independently reviewed v2 handoff commit}"
: "${PLANCARRY_V2_DRIVER_SHA256:?must bind independently reviewed v2 driver SHA256}"
: "${PLANCARRY_V2_PHASE_SHA256:?must bind independently reviewed v2 phase-runner SHA256}"
: "${PLANCARRY_PYTHON:=/opt/gpu-lab/envs/plancarry-replayresidual-t1-retry/bin/python}"
export CUBLAS_WORKSPACE_CONFIG="${CUBLAS_WORKSPACE_CONFIG:-:4096:8}"
[[ -x "$PLANCARRY_PYTHON" ]] || { echo "PYTHON_NOT_EXECUTABLE:$PLANCARRY_PYTHON" >&2; exit 91; }
[[ "$(git rev-parse HEAD)" == "$PLANCARRY_V2_EXPECTED_GIT_COMMIT" ]] || { echo "GIT_COMMIT_MISMATCH" >&2; exit 92; }
[[ "$(sha256sum localcontinuation_science_driver_v2.py | awk '{print $1}')" == "$PLANCARRY_V2_DRIVER_SHA256" ]] || { echo "DRIVER_SHA256_MISMATCH" >&2; exit 93; }
[[ "$(sha256sum localcontinuation_phase_runner_v2.py | awk '{print $1}')" == "$PLANCARRY_V2_PHASE_SHA256" ]] || { echo "PHASE_SHA256_MISMATCH" >&2; exit 94; }

COMMON=(
  --expected-git-commit "$PLANCARRY_V2_EXPECTED_GIT_COMMIT"
  --expected-driver-sha256 "$PLANCARRY_V2_DRIVER_SHA256"
  --expected-phase-sha256 "$PLANCARRY_V2_PHASE_SHA256"
)
if [[ "$MODE" == "preflight" ]]; then
  exec "$PLANCARRY_PYTHON" localcontinuation_science_driver_v2.py --phase preflight "${COMMON[@]}"
fi

: "${LOCALCONT_V2_DEVELOPMENT_AUTHORIZATION:?development requires canonical authorization}"
[[ "$LOCALCONT_V2_DEVELOPMENT_AUTHORIZATION" == "RESEARCH_DECISION_BOUND" ]] || { echo "DEVELOPMENT_AUTHORIZATION_MISMATCH" >&2; exit 95; }
: "${LOCALCONT_V2_EXPECTED_DEVICE_NAME:?development requires independently bound device name}"
# The wrapper is development-only and stops after the development terminal/seal.
exec "$PLANCARRY_PYTHON" localcontinuation_science_driver_v2.py \
  --phase development "${COMMON[@]}" --expected-device "$LOCALCONT_V2_EXPECTED_DEVICE_NAME"
