from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "results" / "design") not in sys.path:
    sys.path.insert(0, str(ROOT / "results" / "design"))

import replay_residual_natural_packet_producer_v2_1 as frozen
import plancarry_replayresidual_v22_vast3080_registered_adapter_20260828 as host
import plancarry_replayresidual_v22_reset_compat_canary_20260828 as canary


class HostAdapterTests(unittest.TestCase):
    def setUp(self):
        self.old = frozen.EXPECTED_DEVICE_NAME

    def tearDown(self):
        frozen.EXPECTED_DEVICE_NAME = self.old

    def test_process_local_device_guard_only(self):
        frozen.EXPECTED_DEVICE_NAME = host.SOURCE_DEVICE_NAME
        host.install_host_binding()
        self.assertEqual(frozen.EXPECTED_DEVICE_NAME, host.VAST_DEVICE_NAME)

    def test_rejects_unexpected_prior_binding(self):
        frozen.EXPECTED_DEVICE_NAME = "NVIDIA GeForce RTX 4090"
        with self.assertRaisesRegex(RuntimeError, "UNEXPECTED_PREEXISTING_DEVICE_BINDING"):
            host.install_host_binding()

    def test_main_delegates_argv_unchanged(self):
        frozen.EXPECTED_DEVICE_NAME = host.SOURCE_DEVICE_NAME
        with mock.patch.object(host.registered, "main", return_value=17) as m:
            self.assertEqual(host.main(["validate", "--root", "."]), 17)
            m.assert_called_once_with(["validate", "--root", "."])
            self.assertEqual(frozen.EXPECTED_DEVICE_NAME, host.VAST_DEVICE_NAME)


class ResetCanaryStaticTests(unittest.TestCase):
    def test_frozen_zero_science_flags(self):
        self.assertEqual(canary.MODEL_CALLS, 0)
        self.assertEqual(canary.ENVIRONMENT_ACTIONS, 0)
        self.assertFalse(canary.STUDY_COHORT_ACCESS)
        self.assertEqual(canary.TARGET_KIND, "SYNTHETIC_TEXTWORLD_GRAMMAR_CANARY")

    def test_wrong_instance_fails_before_reset(self):
        with self.assertRaisesRegex(RuntimeError, "VAST_INSTANCE_ID_MISMATCH"):
            canary.verify_static_runtime(ROOT, "vast_wrong")

    def test_wrong_python_fails_closed(self):
        with mock.patch.object(canary, "EXPECTED_PYTHON", (99, 0, 0)):
            with self.assertRaisesRegex(RuntimeError, "PYTHON_VERSION_MISMATCH"):
                canary.verify_static_runtime(ROOT, canary.EXPECTED_INSTANCE_ID)

    def test_gpu_name_exact(self):
        with mock.patch("subprocess.check_output", return_value=canary.EXPECTED_DEVICE_NAME + "\n"):
            self.assertEqual(canary._query_gpu_name(), canary.EXPECTED_DEVICE_NAME)
        with mock.patch("subprocess.check_output", return_value="NVIDIA GeForce RTX 4090\n"):
            with self.assertRaisesRegex(RuntimeError, "VAST_DEVICE_NAME_MISMATCH"):
                canary._query_gpu_name()

    def test_atomic_json_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "x.json"
            canary.atomic_json(p, {"a": 1})
            with self.assertRaisesRegex(RuntimeError, "REFUSE_EXISTING_CANARY_ATTESTATION"):
                canary.atomic_json(p, {"a": 2})


class HostLauncherStaticTests(unittest.TestCase):
    def test_launcher_is_exact_three_substitution_derivative(self):
        launcher=(ROOT / "results/design/plancarry_replayresidual_v22_vast3080_host_launcher_20260828.sh").read_text()
        self.assertIn("HOST_LAUNCHER_PATCH_OCCURRENCE_MISMATCH", launcher)
        self.assertIn("plancarry_replayresidual_v22_vast3080_registered_adapter_20260828.py", launcher)
        self.assertIn("NVIDIA GeForce RTX 3080", launcher)
        self.assertIn("scientific_variables_changed", launcher)
        self.assertNotIn("valid_seen", launcher)
        self.assertNotIn("valid_unseen", launcher)



if __name__ == "__main__":
    unittest.main()
