"""Offline synthetic unit tests for G0 PDDL/Gym copy-surface audit.

No trained data, PDDL environment, API model call, or G0 authority.
"""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from bind_g0_pddl_clone_surface_audit import (
    EXPECTED_UPSTREAM_COMMIT, FILES, audit,
)


def fixture():
    return {
        "core": '''
from copy import deepcopy
class Environment:
    def copy(self):
        raise NotImplementedError()
class GameState(dict):
    def copy(self):
        return deepcopy(self)
''',
        "pddl": '''
class PddlEnv(Environment):
    def reset(self):
        return self._pddl_state
''',
        "batch": '''
class SyncBatchEnv(Environment):
    def reset(self):
        return self.envs
''',
        "gym_batch": '''
class TextworldBatchGymEnv:
    def reset(self):
        return self.batch_env
''',
        "local_runtime": '''
class AlfRuntime:
    def __init__(self): pass
    def hash(self): pass
    def step(self, action): pass
    def close(self): pass
''',
    }


class PddlCloneSurfaceTests(unittest.TestCase):
    def test_exact_expected_sources(self):
        self.assertEqual(len(FILES), 5)

    def test_abstract_copy_not_permitted_by_backend(self):
        r = audit(fixture(), EXPECTED_UPSTREAM_COMMIT)
        self.assertTrue(r["observations"]["core_environment_copy_is_abstract_not_implemented"])
        self.assertFalse(r["observations"]["pddl_env_overrides_copy"])

    def test_game_state_readout_copy_not_full_env_clone(self):
        r = audit(fixture(), EXPECTED_UPSTREAM_COMMIT)
        self.assertTrue(r["observations"]["game_state_copy_is_deepcopy_of_reported_readout"])
        self.assertEqual(r["g0_state_equivalence"], "BLOCKED_STATE_EQUIVALENCE")

    def test_missing_gym_clone_interface_detected(self):
        r = audit(fixture(), EXPECTED_UPSTREAM_COMMIT)
        self.assertFalse(r["observations"]["gym_batch_exposes_copy_or_clone"])
        self.assertFalse(r["observations"]["synchronous_batch_env_overrides_copy"])

    def test_local_wrapper_has_no_full_export_restore(self):
        r = audit(fixture(), EXPECTED_UPSTREAM_COMMIT)
        self.assertFalse(r["observations"]["plancarry_alf_runtime_exposes_full_state_export_restore"])

    def test_never_grants_science_authorization(self):
        r = audit(fixture(), EXPECTED_UPSTREAM_COMMIT)
        self.assertEqual(r["scientific_gate"], "NOT_AUTHORIZED")
        self.assertFalse(r["upstream_matches_original_installed_package_digest"])

    def test_detects_added_pddl_copy(self):
        xs = fixture()
        xs["pddl"] += "\n    def copy(self): return PddlEnv()\n"
        r = audit(xs, EXPECTED_UPSTREAM_COMMIT)
        self.assertTrue(r["observations"]["pddl_env_overrides_copy"])
        self.assertEqual(r["scientific_gate"], "NOT_AUTHORIZED")

    def test_detects_local_wrapper_extra_api_but_no_autopass(self):
        xs = fixture()
        xs["local_runtime"] += "\n    def save_state(self): return b'data'\n"
        r = audit(xs, EXPECTED_UPSTREAM_COMMIT)
        self.assertTrue(r["observations"]["plancarry_alf_runtime_exposes_full_state_export_restore"])
        self.assertEqual(r["g0_state_equivalence"], "BLOCKED_STATE_EQUIVALENCE")

    def test_upstream_revision_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            audit(fixture(), "0" * 40)

    def test_missing_upstream_source_rejected(self):
        xs = fixture()
        xs.pop("gym_batch")
        with self.assertRaises(ValueError):
            audit(xs, EXPECTED_UPSTREAM_COMMIT)

    def test_missing_pddl_class_rejected(self):
        xs = fixture()
        xs["pddl"] = "class OtherEnv: pass"
        with self.assertRaises(ValueError):
            audit(xs, EXPECTED_UPSTREAM_COMMIT)

    def test_invalid_syntax_rejected(self):
        xs = fixture()
        xs["pddl"] = "def bad("
        with self.assertRaises(SyntaxError):
            audit(xs, EXPECTED_UPSTREAM_COMMIT)


if __name__ == "__main__":
    unittest.main()
