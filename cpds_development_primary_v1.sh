#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PLANCARRY_PYTHON:-/opt/gpu-lab/envs/plancarry-replayresidual-t1-retry/bin/python}"
case "${1:-}" in
  preflight)
    exec "$PY" "$ROOT/cpds_development_runtime_v1.py" --preflight
    ;;
  development)
    test "${CPDS_DEVELOPMENT_AUTHORIZATION:-}" = "RESEARCH_DECISION_BOUND" || { echo 'CPDS_DEVELOPMENT_REQUIRES_RESEARCH_DECISION_BOUND' >&2; exit 64; }
    # This PRE_SCIENCE WorkItem freezes the scorer/runtime API and exact Decision handoff,
    # but it deliberately does not execute model/environment science. A separately reviewed
    # execution WorkItem must invoke the frozen adapter after this preflight returns READY_NO_SCIENCE.
    "$PY" "$ROOT/cpds_development_runtime_v1.py" --preflight >/dev/null
    echo 'CPDS_DEVELOPMENT_EXECUTION_REQUIRES_SEPARATE_REVIEWED_EXECUTION_WORKITEM' >&2
    exit 65
    ;;
  *) echo 'usage: cpds_development_primary_v1.sh {preflight|development}' >&2; exit 64 ;;
esac
