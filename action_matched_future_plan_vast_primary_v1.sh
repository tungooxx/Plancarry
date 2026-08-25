#!/usr/bin/env bash
set -euo pipefail
PHASE="${1:-}"
PY="${PLANCARRY_PYTHON:-python}"
DEVICE="${ACTION_MATCHED_EXPECTED_DEVICE:-NVIDIA GeForce RTX 4060 Ti}"

verify_exec_binding() {
  : "${ACTION_MATCHED_EXPECTED_GIT_COMMIT:?ACTION_MATCHED_EXPECTED_GIT_COMMIT required}"
  : "${ACTION_MATCHED_DRIVER_SHA256:?ACTION_MATCHED_DRIVER_SHA256 required}"
  : "${ACTION_MATCHED_RUNTIME_SHA256:?ACTION_MATCHED_RUNTIME_SHA256 required}"
  : "${ACTION_MATCHED_PHASE_SHA256:?ACTION_MATCHED_PHASE_SHA256 required}"
  : "${ACTION_MATCHED_VALIDATOR_SHA256:?ACTION_MATCHED_VALIDATOR_SHA256 required}"
  : "${ACTION_MATCHED_SHELL_SHA256:?ACTION_MATCHED_SHELL_SHA256 required}"
  test "$(git rev-parse HEAD)" = "$ACTION_MATCHED_EXPECTED_GIT_COMMIT" || { echo 'git commit drift' >&2; exit 65; }
  test "$(sha256sum action_matched_future_plan_science_driver_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_DRIVER_SHA256" || { echo 'driver hash drift' >&2; exit 66; }
  test "$(sha256sum action_matched_future_plan_runtime_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_RUNTIME_SHA256" || { echo 'runtime hash drift' >&2; exit 67; }
  test "$(sha256sum action_matched_future_plan_phase_runner_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_PHASE_SHA256" || { echo 'phase hash drift' >&2; exit 68; }
  test "$(sha256sum action_matched_future_plan_validator_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_VALIDATOR_SHA256" || { echo 'validator hash drift' >&2; exit 69; }
  test "$(sha256sum "$0" | awk '{print $1}')" = "$ACTION_MATCHED_SHELL_SHA256" || { echo 'launcher hash drift' >&2; exit 70; }
}

case "$PHASE" in
  preflight) exec "$PY" action_matched_future_plan_science_driver_v1.py --phase preflight ;;
  development)
    test "${ACTION_MATCHED_DEVELOPMENT_AUTHORIZATION:-}" = "RESEARCH_DECISION_BOUND" || { echo 'development requires RESEARCH_DECISION_BOUND' >&2; exit 61; }
    verify_exec_binding
    exec "$PY" action_matched_future_plan_science_driver_v1.py --phase development --expected-device "$DEVICE" ;;
  confirmation)
    test "${ACTION_MATCHED_CONFIRMATION_AUTHORIZATION:-}" = "RESEARCH_DECISION_BOUND" || { echo 'confirmation requires RESEARCH_DECISION_BOUND' >&2; exit 62; }
    test -n "${ACTION_MATCHED_DEVELOPMENT_SEAL_FILE_SHA256:-}" || { echo 'confirmation requires seal file SHA' >&2; exit 63; }
    verify_exec_binding
    exec "$PY" action_matched_future_plan_science_driver_v1.py --phase confirmation --expected-device "$DEVICE" --development-seal-file-sha256 "$ACTION_MATCHED_DEVELOPMENT_SEAL_FILE_SHA256" ;;
  *) echo 'usage: action_matched_future_plan_vast_primary_v1.sh {preflight|development|confirmation}' >&2; exit 64 ;;
esac
