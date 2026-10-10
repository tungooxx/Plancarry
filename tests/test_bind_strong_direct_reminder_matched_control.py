"""Strongest-equivalent direct plan reminder parity (NO scientific execution).

The two provenance SHA values below are synthetic stand-ins and are NOT
evidence of any model-authored source plan.
"""
import hashlib
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from bind_strong_direct_reminder_matched_control import (
    SourcePlan,MatchedPair,paired_messages,reciprocal_preflight,check_shape
)


def fixture():
    sha=lambda value:hashlib.sha256(value.encode()).hexdigest()
    return MatchedPair(
        source_game_sha256="40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67",
        goal="Reach the vault.",
        shared_actual_prefix=("go east","look"),
        public_observation="Goal: Reach the vault.\nCurrent room: hub",
        ordered_legal_commands=("go north","go east","go west","look","inventory"),
        plan_a=SourcePlan("sourceA",("go east","look","go north","go east"),sha("unverified A")),
        plan_b=SourcePlan("sourceB",("go east","look","go east","go north"),sha("unverified B")),
    )


class ReminderControlTests(unittest.TestCase):
    def test_both_messages_contain_same_exact_serialized_goal_plan_and_menu(self):
        record=paired_messages(fixture(),"A")
        self.assertEqual(record["messages"]["BIND"]["role"],"user")
        self.assertEqual(record["messages"]["DIRECT_REMINDER"]["role"],"user")
        shared=record["same_semantic_payload"]
        self.assertIn(shared,record["messages"]["BIND"]["content"])
        self.assertIn(shared,record["messages"]["DIRECT_REMINDER"]["content"])
        self.assertEqual(hashlib.sha256(shared.encode()).hexdigest(),
                         record["semantic_payload_sha256"])
        atoms=json.loads(shared)
        self.assertEqual(["go north","go east"],atoms["donor_future_actions"])
        self.assertEqual("sourceA",atoms["plan_id"])
        self.assertEqual(["go north","go east","go west","look","inventory"],atoms["ordered_legal_commands"])
        self.assertIn("take the next action",record["messages"]["DIRECT_REMINDER"]["content"].lower())

    def test_reciprocal_donor_identity_changes_only_selected_source(self):
        pre=reciprocal_preflight(fixture())
        self.assertEqual("A->B",pre["a_donor"]["direction"])
        self.assertEqual("B->A",pre["b_donor"]["direction"])
        left=json.loads(pre["a_donor"]["same_semantic_payload"])
        right=json.loads(pre["b_donor"]["same_semantic_payload"])
        self.assertEqual("sourceA",left["plan_id"])
        self.assertEqual("sourceB",right["plan_id"])
        self.assertEqual(left["goal"],right["goal"])
        self.assertEqual(left["ordered_legal_commands"],right["ordered_legal_commands"])
        self.assertEqual(left["public_observation"],right["public_observation"])

    def test_no_science_claims_or_token_parity_claimed(self):
        record=paired_messages(fixture(),"B")
        self.assertEqual("NOT_AUTHORIZED",record["science_gate"])
        for key in ("model_owned_plan_attested","simulator_complete_state_attested",
                    "tokenizer_realized_costs_matched","legal_action_menu_altered"):
            self.assertFalse(record[key])
        self.assertIn("MISSING_MODEL_AUTHORED_SOURCE_HISTORY",record["blockers"])

    def test_actual_common_information_action_prefix_is_preserved(self):
        atoms=json.loads(paired_messages(fixture(),"A")["same_semantic_payload"])
        self.assertEqual(["go east","look"],atoms["actual_common_prefix_actions"])

    def test_reject_source_alias_or_no_fork(self):
        orig=fixture()
        bad=replace(orig,plan_b=replace(orig.plan_b,plan_id=orig.plan_a.plan_id))
        with self.assertRaises(ValueError):check_shape(bad)
        bad=replace(orig,plan_b=replace(orig.plan_b,whole_actions=orig.plan_a.whole_actions))
        with self.assertRaises(ValueError):check_shape(bad)

    def test_reject_earlier_information_action_divergence(self):
        original=fixture()
        bad=replace(original,plan_a=replace(original.plan_a,
            whole_actions=("go east","inventory","go north","go east")))
        with self.assertRaises(ValueError):check_shape(bad)

    def test_reject_legal_menu_reorder_or_duplicate_as_artifact(self):
        original=fixture()
        with self.assertRaises(ValueError):
            check_shape(replace(original,ordered_legal_commands=("go north","go north")))
        # Different *ordered* menus are a different candidate; no comparison
        # across those paired contexts is allowed from one record.
        shared=paired_messages(original,"B")["same_semantic_payload"]
        self.assertIn('"ordered_legal_commands":',shared)

    def test_reject_wrong_legal_fork_actions(self):
        original=fixture()
        bad=replace(original,plan_a=replace(original.plan_a,
            whole_actions=("go east","look","teleport to future","go east")))
        with self.assertRaises(ValueError):check_shape(bad)

    def test_reject_missing_source_id_or_source_hash(self):
        original=fixture()
        with self.assertRaises(ValueError):
            check_shape(replace(original,source_game_sha256="missing"))
        with self.assertRaises(ValueError):
            check_shape(replace(original,plan_a=replace(original.plan_a,
                source_record_sha256="no-model-source-record")))

    def test_unknown_donor_not_rendered(self):
        with self.assertRaises(ValueError):paired_messages(fixture(),"neither")


if __name__=="__main__":
    unittest.main()
