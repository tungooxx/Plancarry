from __future__ import annotations

import inspect
import unittest
from collections import Counter
from pathlib import Path

import variable_slot_controls_v1 as v


class VariableSlotControlContractTests(unittest.TestCase):
    def test_all_lengths_8_to_512_exact_and_deterministic(self):
        action3 = (701, 709)
        for L in range(8, 513):
            with self.subTest(L=L):
                plan = tuple(1000 + i for i in range(L))
                a = v.build_control_payloads(plan, action3, v.SYNTHETIC_TEST_CONTRACT)
                b = v.build_control_payloads(plan, action3, v.SYNTHETIC_TEST_CONTRACT)
                self.assertEqual(a, b)
                self.assertEqual(a["slot_length_L"], L)
                self.assertEqual(a["source_anchor_offset"], L - 1)
                self.assertTrue(a["no_tokenizer_decode_reencode"])
                for ids in a["controls"].values():
                    self.assertEqual(len(ids), L)
                self.assertEqual(Counter(a["controls"]["ORDER_NULL"]), Counter(plan))
                order = a["order_null_provenance"]["output_source_block_order"]
                self.assertEqual(order, [1, 2, 3, 0])
                self.assertTrue(all(src != out for out, src in enumerate(order)))
                self.assertNotEqual(a["order_null_provenance"]["original_final_block_output_index"], 3)
                self.assertEqual(set(a["source_anchor_offsets"].values()), {L - 1})

    def test_adversarial_one_clause_no_punctuation_and_repeated_token_analogues(self):
        cases = {
            "one_clause": tuple(range(200, 240)),
            "no_punctuation": tuple(500 + (i % 11) for i in range(73)),
            "repeated_token": (1, 1, 2, 2, 3, 3, 4, 4, 1, 2, 1, 2, 3, 4, 3, 4),
        }
        for name, plan in cases.items():
            with self.subTest(name=name):
                out = v.build_control_payloads(plan, (801, 809), v.SYNTHETIC_TEST_CONTRACT)
                self.assertEqual(len(out["controls"]["ORDER_NULL"]), len(plan))
                self.assertEqual(Counter(out["controls"]["ORDER_NULL"]), Counter(plan))
                self.assertTrue(out["order_null_provenance"]["all_block_indices_deranged"])
                self.assertNotEqual(out["order_null_provenance"]["original_final_block_output_index"], 3)

    def test_action_only_has_no_plan_or_later_action_inputs(self):
        sig = inspect.signature(v.build_action_only_pair)
        self.assertEqual(list(sig.parameters), ["length", "action3_ids", "contract"])
        p1 = tuple(range(1000, 1064))
        p2 = tuple(range(2000, 2064))
        a1 = v.build_control_payloads(p1, (901, 907), v.SYNTHETIC_TEST_CONTRACT)
        a2 = v.build_control_payloads(p2, (901, 907), v.SYNTHETIC_TEST_CONTRACT)
        self.assertEqual(a1["controls"]["ACTION_ONLY_NULL"], a2["controls"]["ACTION_ONLY_NULL"])
        self.assertEqual(a1["controls"]["ACTION_ONLY_NEUTRAL"], a2["controls"]["ACTION_ONLY_NEUTRAL"])
        self.assertEqual(
            a1["action_only_provenance"]["forbidden_inputs"],
            ["plan_ids", "reference_action4_ids", "reference_action5_ids", "future_observations"],
        )
        changed = v.build_control_payloads(p1, (911, 919), v.SYNTHETIC_TEST_CONTRACT)
        self.assertNotEqual(a1["controls"]["ACTION_ONLY_NULL"], changed["controls"]["ACTION_ONLY_NULL"])

    def test_neutral_depends_only_on_length_and_frozen_contract(self):
        L = 96
        self.assertEqual(
            v.build_neutral(L, v.SYNTHETIC_TEST_CONTRACT),
            v.build_control_payloads(tuple(range(L)), (701,), v.SYNTHETIC_TEST_CONTRACT)["controls"]["NEUTRAL_L"],
        )
        self.assertEqual(
            v.build_neutral(L, v.SYNTHETIC_TEST_CONTRACT),
            v.build_control_payloads(tuple(range(1000, 1000 + L)), (701,), v.SYNTHETIC_TEST_CONTRACT)["controls"]["NEUTRAL_L"],
        )

    def test_short_slots_and_overlong_action_fail_closed(self):
        for L in range(0, 8):
            with self.subTest(L=L):
                with self.assertRaisesRegex(v.VariableSlotContractError, "SLOT_TOO_SHORT"):
                    v.build_control_payloads(tuple(range(L)), (1,), v.SYNTHETIC_TEST_CONTRACT)
        with self.assertRaisesRegex(v.VariableSlotContractError, "ACTION_ONLY_CONTENT_EXCEEDS_SLOT"):
            v.build_control_payloads(tuple(range(8)), tuple(range(10)), v.SYNTHETIC_TEST_CONTRACT)

    def test_no_decode_reencode_or_science_dependencies(self):
        src = Path(v.__file__).read_text(encoding="utf-8")
        forbidden_calls = (".decode(", ".encode(", "AutoTokenizer", "transformers", "torch", "alfworld", "textworld")
        for token in forbidden_calls:
            self.assertNotIn(token, src)


    def test_zero_information_controls_fail_closed(self):
        with self.assertRaisesRegex(v.VariableSlotContractError, "ORDER_NULL_IDENTICAL_TO_PLAN"):
            v.build_order_null((42,) * 32)
        with self.assertRaisesRegex(v.VariableSlotContractError, "ORDER_NULL_IDENTICAL_TO_PLAN"):
            v.build_order_null((1, 2, 3, 4) * 4)

        action_neutral = v.FrozenTokenContract(
            neutral_cycle_ids=(5,),
            action_wrapper_prefix_ids=(101,),
            action_wrapper_suffix_ids=(107,),
            contract_name="ACTION_PAIR_IDENTICAL_FIXTURE",
        )
        with self.assertRaisesRegex(v.VariableSlotContractError, "ACTION_ONLY_PAIR_IDENTICAL"):
            v.build_action_only_pair(8, (5, 5), action_neutral)

        active_neutral = v.FrozenTokenContract(
            neutral_cycle_ids=(1, 2),
            action_wrapper_prefix_ids=(),
            action_wrapper_suffix_ids=(),
            contract_name="ACTIVE_PAIR_IDENTICAL_FIXTURE",
        )
        with self.assertRaisesRegex(v.VariableSlotContractError, "ACTIVE_PAIR_IDENTICAL"):
            v.build_control_payloads((1, 2, 1, 2, 1, 2, 1, 2), (9,), active_neutral)

    def test_invalid_token_ids_fail_closed(self):
        with self.assertRaisesRegex(v.VariableSlotContractError, "PLAN_INVALID_TOKEN_ID"):
            v.build_control_payloads((1, 2, 3, 4, 5, 6, 7, -1), (9,), v.SYNTHETIC_TEST_CONTRACT)
        with self.assertRaisesRegex(v.VariableSlotContractError, "ACTION3_INVALID_TOKEN_ID"):
            v.build_control_payloads(tuple(range(8)), (True,), v.SYNTHETIC_TEST_CONTRACT)


if __name__ == "__main__":
    unittest.main()
