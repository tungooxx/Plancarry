from __future__ import annotations

import collections
import itertools
import json
import unittest
from pathlib import Path

import localcontinuation_controls_v2 as c
import localcontinuation_packet_builder_v2 as pb
import localcontinuation_validator_v2 as validator


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        return list(str(text).encode("utf-8"))


class TestLocalContinuationV2Controls(unittest.TestCase):
    def test_exhaustive_strict_derangement_counts(self):
        op, cl = [7001, 7002], [7003, 7004]
        constructible = all_equal = primary = fallback = 0
        for n in range(2, 11):
            for x in itertools.product(range(3), repeat=n):
                tagged = op + list(x) + cl
                if len(set(x)) < 2:
                    all_equal += 1
                    with self.assertRaisesRegex(c.V2ControlError, "INTERIOR_ALL_EQUAL"):
                        c.plan_block_deranged(tagged, op, cl)
                    continue
                out, meta = c.plan_block_deranged(tagged, op, cl)
                yi = out[len(op) : -len(cl)]
                constructible += 1
                self.assertEqual(out[:len(op)], op)
                self.assertEqual(out[-len(cl):], cl)
                self.assertEqual(len(out), len(tagged))
                self.assertEqual(collections.Counter(out), collections.Counter(tagged))
                self.assertNotEqual(yi, list(x))
                self.assertNotEqual(yi[-1], x[-1])
                if meta["method"] == "BALANCED_BLOCK_LEFT_ROTATE":
                    primary += 1
                else:
                    fallback += 1
        self.assertEqual((constructible, primary, fallback, all_equal), (88542, 59046, 29496, 27))

    def test_tag_mismatch_and_short_fail_closed(self):
        op, cl = [1, 2], [3, 4]
        with self.assertRaisesRegex(c.V2ControlError, "TAG_SPAN_MISMATCH"):
            c.plan_block_deranged([9, 2, 5, 6, 3, 4], op, cl)
        with self.assertRaisesRegex(c.V2ControlError, "INTERIOR_TOO_SHORT"):
            c.plan_block_deranged(op + [7] + cl, op, cl)

    def test_past_actions_is_exact_40_separator_40_max81(self):
        a1, a2 = list(range(512)), list(range(1000, 1512))
        out = c.past_actions_only_content(a1, a2)
        self.assertEqual(out[:40], a1[:40])
        self.assertEqual(out[40:41], list(c.PAST_ACTION_SEPARATOR_IDS))
        self.assertEqual(out[41:], a2[:40])
        self.assertEqual(len(out), 81)
        for n1 in (0, 1, 40, 41, 96, 512):
            for n2 in (0, 1, 40, 41, 96, 512):
                self.assertLessEqual(len(c.past_actions_only_content(range(n1), range(n2))), 81)

    def test_next_action_exact_and_guard(self):
        for n in (0, 1, 32, 64, 96):
            ids = list(range(n))
            self.assertEqual(c.next_action_preserved_content(ids), ids)
        with self.assertRaisesRegex(c.V2ControlError, "ACTION3_GT96_STAGE1_INELIGIBLE"):
            c.next_action_preserved_content(range(97))

    def test_exact128_slot_geometry_synthetic(self):
        filler = list(range(10000, 10128))
        for n in range(97):
            content = list(range(n))
            out = c._make_slot_ids_unchecked(content, filler)
            self.assertEqual(len(out), 128)
            self.assertEqual(out[:n], content)
        with self.assertRaisesRegex(c.V2ControlError, "CONTENT_GT96"):
            c._make_slot_ids_unchecked(range(97), filler)

    def test_frozen_filler_rejects_wrong_ids(self):
        with self.assertRaisesRegex(c.V2ControlError, "NEUTRAL_FILLER_SHA256"):
            c.verify_neutral_filler_ids(range(128))

    def test_direct_id_replay_geometry_no_slot_decode(self):
        tok = FakeTokenizer()
        packet = {
            "task_instruction": "put thing",
            "initial_observation": "room",
            "actions": [
                {"command": "a1", "observation": "o1"},
                {"command": "a2", "observation": "o2"},
                {"command": "a3", "observation": "o3"},
            ],
        }
        provenances = {}
        for name, offset in [("A", 0), ("B", 1000), ("C", 2000)]:
            slot = list(range(offset, offset + 128))
            replay, prov = c.build_replay_ids(tok, packet, slot, 2)
            self.assertEqual(replay[prov["slot_start_index"]:prov["slot_end_index_exclusive"]], slot)
            provenances[name] = prov
        c.assert_condition_invariant_replay_geometry(provenances)
        validator.validate_replay_geometry(provenances)

    def test_stage1_constructibility_fake_tokenizer(self):
        tok = FakeTokenizer()
        op, cl = c.frozen_tag_ids(tok)
        plan = "<PLAN>abcde</PLAN>"
        guard = c.stage1_constructibility_guard(tok, plan, "move", op, cl)
        self.assertLessEqual(guard["plan_content_token_count"], 96)
        self.assertLessEqual(guard["action3_token_count"], 96)
        self.assertIn(guard["derangement_method"], ("BALANCED_BLOCK_LEFT_ROTATE", "SMALLEST_VALID_LEFT_ROTATION"))

    def test_arm_set_matches_frozen_prereg_and_contract(self):
        root = Path(__file__).resolve().parents[1]
        prereg = json.loads((root / pb.FINAL_PREREG_REL).read_text())
        contract = json.loads((root / pb.CONTROL_CONTRACT_REL).read_text())
        expected = [x for x in contract["causal_arms"] if x != "ACTIVE_PLAN_RESIDUAL"]
        self.assertEqual(prereg["causal_runtime_and_controls"]["intervention_controls"], expected)
        self.assertEqual(c.intervention_controls_from_arms(), expected)
        self.assertEqual(list(c.CAUSAL_ARMS), contract["causal_arms"])
        self.assertEqual(list(c.SPECIFICITY_MAX_CONTROLS), contract["specificity_max_controls"])

    def test_frozen_bindings_and_fresh_split(self):
        root = Path(__file__).resolve().parents[1]
        pb.verify_bindings(root)
        self.assertEqual(len(pb.load_population_phase("development", root)), 32)
        self.assertEqual(len(pb.load_population_phase("confirmation", root)), 20)
        self.assertEqual(len(pb.load_population_phase("reserve_replication", root)), 12)
        self.assertEqual(pb.load_population_phase("development", root)[0]["frozen_index"], 0)
        self.assertEqual(pb.load_population_phase("confirmation", root)[0]["frozen_index"], 32)
        self.assertEqual(pb.load_population_phase("reserve_replication", root)[0]["frozen_index"], 52)

    def test_split_flags_fail_closed(self):
        validator.validate_split_access_flags({"confirmation_accessed": False, "reserve_accessed": False, "valid_seen_accessed": False, "valid_unseen_accessed": False}, "development")
        with self.assertRaisesRegex(validator.V2ValidationError, "SPLIT_ISOLATION"):
            validator.validate_split_access_flags({"confirmation_accessed": True, "reserve_accessed": False, "valid_seen_accessed": False, "valid_unseen_accessed": False}, "development")

    def test_full_development_stage2_synthetic_pipeline(self):
        tok = FakeTokenizer()
        op, cl = c.frozen_tag_ids(tok)
        root = Path(__file__).resolve().parents[1]
        rows = pb.load_population_phase("development", root)
        packets = []
        for row in rows:
            packet = pb._base(row, {"synthetic": True}, "development")
            packet["task_instruction"] = "synthetic task"
            packet["initial_observation"] = "synthetic observation"
            packet["plan_text"] = f"<PLAN>abc{int(row['frozen_index'])}</PLAN>"
            packet["success"] = False
            packet["actions"] = []
            for step in range(1, 6):
                command = f"move object{step}"
                packet["actions"].append({
                    "step": step,
                    "command": command,
                    "observation": f"obs{step}",
                    "admissible_commands": [command, "look"],
                    "accepted": True,
                    "was_admissible": True,
                    "error": None,
                })
            packet["stage1_runtime_errors"] = []
            ok, reasons, guard = pb.local_stage1_eligibility_v2(tok, packet["plan_text"], packet["actions"], [], op, cl)
            self.assertTrue(ok, reasons)
            packet["trajectory_eligible"] = True
            packet["qualification_stage1_reasons"] = []
            packet["v2_control_constructibility_provenance"] = guard
            packet["qualified"] = False
            packet["qualification_stage2_reasons"] = ["STAGE2_NOT_RUN"]
            import replay_residual_sanity_protocol_v1 as sp
            packet["trajectory_sha256"] = sp.trajectory_digest(packet)
            packets.append(packet)
        filler = list(range(50000, 50128))
        old = c.NEUTRAL_FILLER_IDS_SHA256
        c.NEUTRAL_FILLER_IDS_SHA256 = c.sha_json(filler)
        try:
            out = pb.apply_stage2_phase(tok, packets, "development", filler, op, cl, root)
            self.assertEqual(len(out), 32)
            self.assertGreaterEqual(sum(bool(x["qualified"]) for x in out), 16)
            for packet in out:
                if packet["trajectory_eligible"]:
                    self.assertTrue(packet["qualified"], packet["qualification_stage2_reasons"])
                    prov = packet["control_provenance"]
                    self.assertEqual(set(prov["condition_names"]), set(c.SCIENCE_CONDITIONS))
                    self.assertNotEqual(prov["unrelated_donor_frozen_index"], packet["frozen_index"])
                    self.assertEqual(sorted(prov["frozen_E_indices"]), list(range(32)))
            e_orders = {tuple(x["control_provenance"]["frozen_E_indices"]) for x in out if x.get("qualified")}
            self.assertEqual(len(e_orders), 1)
            rebuilt = validator.validate_stage2_reconstruction(out, "development", tok, filler, op, cl, root)
            self.assertEqual(rebuilt["reconstruction"], "PASS")
        finally:
            c.NEUTRAL_FILLER_IDS_SHA256 = old

    def test_stage1_action3_gt96_fails_before_E(self):
        tok = FakeTokenizer()
        op, cl = c.frozen_tag_ids(tok)
        actions=[]
        for step in range(1,6):
            command = ("x" * 97) if step == 3 else f"move object{step}"
            actions.append({"command":command,"admissible_commands":[command],"accepted":True,"was_admissible":True,"error":None})
        ok, reasons, guard = pb.local_stage1_eligibility_v2(tok, "<PLAN>abcdef</PLAN>", actions, [], op, cl)
        self.assertFalse(ok)
        self.assertIsNone(guard)
        self.assertTrue(any("ACTION3_GT96_STAGE1_INELIGIBLE" in r for r in reasons), reasons)


if __name__ == "__main__":
    unittest.main()
