#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PLANCARRY_PYTHON:-/opt/gpu-lab/envs/plancarry-replayresidual-t1-retry/bin/python}"
case "${1:-}" in
  preflight)
    exec "$PY" "$ROOT/cpds_development_runtime_v1.py" --preflight
    ;;
  development)
    # SEPARATE_REVIEWED_EXECUTION_WORKITEM: historical fail-closed requirement; the reviewed adapter release satisfies it before scientific authorization.
    test "${CPDS_DEVELOPMENT_AUTHORIZATION:-}" = "RESEARCH_DECISION_BOUND" || { echo 'CPDS_DEVELOPMENT_REQUIRES_RESEARCH_DECISION_BOUND' >&2; exit 64; }
    "$PY" "$ROOT/cpds_development_runtime_v1.py" --preflight >/dev/null
    exec "$PY" "$ROOT/cpds_development_driver_v1.py"
    ;;
  *) echo 'usage: cpds_development_primary_v1.sh {preflight|development}' >&2; exit 64 ;;
esac
