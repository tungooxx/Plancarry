#!/usr/bin/env bash
set -euo pipefail
PHASE="${1:-}"
PY="${PLANCARRY_PYTHON:-python}"
DEVICE="${ACTION_MATCHED_GROUNDED_V2_EXPECTED_DEVICE:-NVIDIA GeForce RTX 3050 Laptop GPU}"
verify_exec_binding() {
  : "${ACTION_MATCHED_GROUNDED_V2_EXPECTED_GIT_COMMIT:?expected git commit required}"
  : "${ACTION_MATCHED_GROUNDED_V2_DRIVER_SHA256:?driver sha required}"
  : "${ACTION_MATCHED_GROUNDED_V2_RUNTIME_SHA256:?runtime sha required}"
  : "${ACTION_MATCHED_GROUNDED_V2_PHASE_SHA256:?phase sha required}"
  : "${ACTION_MATCHED_GROUNDED_V2_VALIDATOR_SHA256:?validator sha required}"
  : "${ACTION_MATCHED_GROUNDED_V2_SHELL_SHA256:?shell sha required}"
  test "$(git rev-parse HEAD)" = "$ACTION_MATCHED_GROUNDED_V2_EXPECTED_GIT_COMMIT" || { echo 'git commit drift' >&2; exit 65; }
  test "$(sha256sum action_matched_grounded_v2_science_driver_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_GROUNDED_V2_DRIVER_SHA256" || { echo 'driver hash drift' >&2; exit 66; }
  test "$(sha256sum action_matched_grounded_v2_runtime_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_GROUNDED_V2_RUNTIME_SHA256" || { echo 'runtime hash drift' >&2; exit 67; }
  test "$(sha256sum action_matched_grounded_v2_phase_runner_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_GROUNDED_V2_PHASE_SHA256" || { echo 'phase hash drift' >&2; exit 68; }
  test "$(sha256sum action_matched_grounded_v2_validator_v1.py | awk '{print $1}')" = "$ACTION_MATCHED_GROUNDED_V2_VALIDATOR_SHA256" || { echo 'validator hash drift' >&2; exit 69; }
  test "$(sha256sum "$0" | awk '{print $1}')" = "$ACTION_MATCHED_GROUNDED_V2_SHELL_SHA256" || { echo 'launcher hash drift' >&2; exit 70; }
}
case "$PHASE" in
  preflight) exec "$PY" action_matched_grounded_v2_science_driver_v1.py --phase preflight ;;
  development)
    test "${ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT_AUTHORIZATION:-}" = "RESEARCH_DECISION_BOUND" || { echo 'development requires RESEARCH_DECISION_BOUND' >&2; exit 61; }
    verify_exec_binding
    exec "$PY" action_matched_grounded_v2_science_driver_v1.py --phase development --expected-device "$DEVICE" ;;
  confirmation)
    test "${ACTION_MATCHED_GROUNDED_V2_CONFIRMATION_AUTHORIZATION:-}" = "RESEARCH_DECISION_BOUND" || { echo 'confirmation requires RESEARCH_DECISION_BOUND' >&2; exit 62; }
    test -n "${ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT_SEAL_FILE_SHA256:-}" || { echo 'confirmation requires development seal file SHA' >&2; exit 63; }
    verify_exec_binding
    exec "$PY" action_matched_grounded_v2_science_driver_v1.py --phase confirmation --expected-device "$DEVICE" --development-seal-file-sha256 "$ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT_SEAL_FILE_SHA256" ;;
  *) echo 'usage: action_matched_grounded_v2_primary_v1.sh {preflight|development|confirmation}' >&2; exit 64 ;;
esac
