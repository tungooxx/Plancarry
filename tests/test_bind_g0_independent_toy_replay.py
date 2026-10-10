"""CPU-only genuine toy execution -> PR3 byte-prefix checker integration."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from bind_g0_ab_prefix_byte_equality import structural_audit
from bind_g0_independent_toy_replay import actual_toy_prefix, ToyPddlLike, _b64


class IndependentToyReplayTests(unittest.TestCase):
    def test_same_seed_three_real_toy_transitions_match(self):
        r = structural_audit(actual_toy_prefix())
        self.assertEqual("MATCHED_SYNTHETIC_PREFIX_ONLY", r["status"])
        self.assertEqual(4, r["verified_prefix_steps"])
        self.assertEqual("NOT_AUTHORIZED", r["scientific_gate"])

    def test_independent_instances_are_not_identical_labels(self):
        r = actual_toy_prefix()
        self.assertNotEqual(r["A"]["independent_instance_id"], r["B"]["independent_instance_id"])

    def test_first_reset_rng_difference_detected(self):
        r = structural_audit(actual_toy_prefix(seed_a=17, seed_b=18))
        self.assertIn("step_0.rng_state_b64", r["failures"])
        self.assertEqual("NOT_AUTHORIZED", r["scientific_gate"])

    def test_reordered_menu_detected_at_reset(self):
        r = structural_audit(actual_toy_prefix(reverse_menu_b=True))
        self.assertIn("step_0.ordered_commands", r["failures"])

    def test_hidden_drift_detected_with_same_public_action(self):
        r = structural_audit(actual_toy_prefix(perturb_transition_b=True))
        self.assertIn("step_1.full_hidden_state_b64", r["failures"])

    def test_stochastic_difference_reflected_in_observation_bytes(self):
        r = structural_audit(actual_toy_prefix(seed_a=17, seed_b=18))
        self.assertIn("step_1.observation_b64", r["failures"])

    def test_real_toy_stops_illegal_action_before_log_construction(self):
        with self.assertRaises(ValueError):
            actual_toy_prefix(actions=(b"teleport into future",))

    def test_real_toy_rejects_second_precondition_violating_action(self):
        with self.assertRaises(ValueError):
            actual_toy_prefix(actions=(b"open drawer",))

    def test_correct_transition_but_forged_future_action_is_detected(self):
        r = actual_toy_prefix()
        for side in ("A","B"):
            r[side]["steps"][1]["actual_action_b64"]=_b64(b"teleport")
        observed=structural_audit(r)
        self.assertIn("step_1.A.action_not_admissible", observed["failures"])
        self.assertIn("step_1.B.action_not_admissible", observed["failures"])

    def test_toy_data_cannot_claim_real_backend_authority(self):
        r=actual_toy_prefix()
        r["backend"]["backend_kind"]="ALFWORLD_REAL"
        with self.assertRaises(ValueError):
            structural_audit(r)

    def test_toy_input_cannot_forge_full_state_authority(self):
        r=actual_toy_prefix()
        r["backend"]["full_state_export_provenance"]="INDEPENDENTLY_ATTESTED"
        with self.assertRaises(ValueError):
            structural_audit(r)

    def test_all_normal_runs_are_unprivileged(self):
        for seed in (0,1,2,100,20261010):
            result=structural_audit(actual_toy_prefix(seed_a=seed,seed_b=seed))
            self.assertEqual("MATCHED_SYNTHETIC_PREFIX_ONLY",result["status"])
            self.assertEqual("NOT_AUTHORIZED",result["scientific_gate"])


if __name__=="__main__":
    unittest.main()
