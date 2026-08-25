#!/usr/bin/env bash
set -euo pipefail
PHASE="${1:-preflight}"
PY="${PLANCARRY_PYTHON:-/opt/gpu-lab/envs/plancarry-replayresidual-t1-retry/bin/python}"
case "$PHASE" in
 preflight) exec "$PY" planunique_science_driver_v1.py preflight ;;
 development)
   test "${PLANUNIQUE_DEVELOPMENT_AUTHORIZATION:-}" = RESEARCH_DECISION_BOUND || { echo 'PLANUNIQUE development requires ResearchDecision binding' >&2; exit 41; }
   test -n "${PLANUNIQUE_EXPECTED_DEVICE_NAME:-}" || { echo 'PLANUNIQUE expected device required' >&2; exit 42; }
   exec "$PY" planunique_science_driver_v1.py development --expected-device "$PLANUNIQUE_EXPECTED_DEVICE_NAME" ;;
 confirmation)
   test "${PLANUNIQUE_CONFIRMATION_AUTHORIZATION:-}" = RESEARCH_DECISION_BOUND || { echo 'PLANUNIQUE confirmation requires ResearchDecision binding' >&2; exit 43; }
   test -n "${PLANUNIQUE_EXPECTED_DEVICE_NAME:-}" || { echo 'PLANUNIQUE expected device required' >&2; exit 44; }
   exec "$PY" planunique_science_driver_v1.py confirmation --expected-device "$PLANUNIQUE_EXPECTED_DEVICE_NAME" ;;
 *) echo 'usage: planunique_vast_primary_v1.sh {preflight|development|confirmation}' >&2; exit 2;;
esac
