from __future__ import annotations

import inspect
import unittest
from collections import Counter
from pathlib import Path

import variable_slot_controls_v2 as v


class VariableSlotV2DiagnosticTests(unittest.TestCase):
    def test_derangement_catalog_is_deterministic_and_strict(self):
        self.assertGreater(len(v.DERANGEMENT_ORDERS), 0)
        self.assertEqual(tuple(sorted(v.DERANGEMENT_ORDERS)), v.DERANGEMENT_ORDERS)
        for order in v.DERANGEMENT_ORDERS:
            self.assertTrue(all(source != out for out, source in enumerate(order)))
            self.assertNotEqual(order.index(3), 3)

    def test_all_lengths_8_to_512_exact_deterministic_and_value_nonidentical(self):
        action3 = (701, 709)
        for length in range(8, 513):
            with self.subTest(length=length):
                plan = tuple(1000 + index for index in range(length))
                first = v.build_control_payloads(plan, action3, v.SYNTHETIC_TEST_CONTRACT)
                second = v.build_control_payloads(plan, action3, v.SYNTHETIC_TEST_CONTRACT)
                self.assertEqual(first, second)
                self.assertTrue(first["science_execution_forbidden"])
                self.assertEqual(first["slot_length_L"], length)
                self.assertEqual(first["source_anchor_offset"], length - 1)
                self.assertEqual(set(first["source_anchor_offsets"].values()), {length - 1})
                for ids in first["controls"].values():
                    self.assertEqual(len(ids), length)
                order_null = first["controls"]["ORDER_NULL"]
                self.assertEqual(Counter(order_null), Counter(plan))
                self.assertNotEqual(order_null, plan)
                provenance = first["order_null_provenance"]
                self.assertTrue(provenance["all_block_indices_deranged"])
                self.assertTrue(provenance["token_multiset_preserved"])
                self.assertTrue(provenance["value_level_nonidentity"])
                self.assertNotEqual(provenance["original_final_block_output_index"], 3)

    def test_boundary_lengths(self):
        for length in (8, 9, 15, 16, 31, 64, 96, 128, 256, 512):
            with self.subTest(length=length):
                plan = tuple((index * 17 + 3) % 997 for index in range(length))
                payload = v.build_control_payloads(plan, (811, 823), v.SYNTHETIC_TEST_CONTRACT)
                self.assertEqual({len(ids) for ids in payload["controls"].values()}, {length})
                self.assertEqual(set(payload["source_anchor_offsets"].values()), {length - 1})

    def test_one_clause_and_no_punctuation_integer_analogues(self):
        cases = (
            tuple(range(200, 240)),
            tuple(500 + (index % 11) for index in range(73)),
        )
        for plan in cases:
            payload = v.build_control_payloads(plan, (801, 809), v.SYNTHETIC_TEST_CONTRACT)
            self.assertNotEqual(payload["controls"]["ORDER_NULL"], plan)
            self.assertEqual(Counter(payload["controls"]["ORDER_NULL"]), Counter(plan))

    def test_repeated_but_multivalue_plan_is_constructible(self):
        plan = tuple([42] * 32 + [43] * 32 + [42] * 32 + [44] * 32)
        payload = v.build_control_payloads(plan, (801, 809), v.SYNTHETIC_TEST_CONTRACT)
        self.assertNotEqual(payload["controls"]["ORDER_NULL"], plan)
        self.assertEqual(Counter(payload["controls"]["ORDER_NULL"]), Counter(plan))

    def test_all_identical_plan_fails_closed(self):
        with self.assertRaisesRegex(v.VariableSlotContractError, "ORDER_NULL_VALUE_DERANGEMENT_UNCONSTRUCTIBLE"):
            v.build_control_payloads((42,) * 128, (801, 809), v.SYNTHETIC_TEST_CONTRACT)

    def test_block_periodic_value_degenerate_plan_fails_closed_if_no_semantic_change(self):
        # Multiple distinct values but four identical contiguous blocks: moving
        # whole blocks cannot destroy value order. This must not be mislabeled.
        block = (1, 2, 1, 2)
        plan = block * 4
        with self.assertRaisesRegex(v.VariableSlotContractError, "ORDER_NULL_VALUE_DERANGEMENT_UNCONSTRUCTIBLE"):
            v.build_control_payloads(plan, (801,), v.SYNTHETIC_TEST_CONTRACT)

    def test_action_only_has_no_plan_or_later_action_inputs(self):
        signature = inspect.signature(v.build_action_only_pair)
        self.assertEqual(list(signature.parameters), ["length", "action3_ids", "contract"])
        first_plan = tuple(range(1000, 1064))
        second_plan = tuple(range(2000, 2064))
        first = v.build_control_payloads(first_plan, (901, 907), v.SYNTHETIC_TEST_CONTRACT)
        second = v.build_control_payloads(second_plan, (901, 907), v.SYNTHETIC_TEST_CONTRACT)
        self.assertEqual(first["controls"]["ACTION_ONLY_NULL"], second["controls"]["ACTION_ONLY_NULL"])
        self.assertEqual(first["controls"]["ACTION_ONLY_NEUTRAL"], second["controls"]["ACTION_ONLY_NEUTRAL"])
        self.assertEqual(
            first["action_only_provenance"]["forbidden_inputs"],
            ["plan_ids", "reference_action4_ids", "reference_action5_ids", "future_observations"],
        )
        self.assertFalse(first["action_only_provenance"]["truncation"])

    def test_action_content_overflow_and_short_slot_fail_closed(self):
        with self.assertRaisesRegex(v.VariableSlotContractError, "PLAN_EMPTY"):
            v.build_control_payloads((), (1,), v.SYNTHETIC_TEST_CONTRACT)
        for length in range(1, 8):
            with self.subTest(length=length):
                with self.assertRaisesRegex(v.VariableSlotContractError, "SLOT_TOO_SHORT"):
                    v.build_control_payloads(tuple(range(length)), (1,), v.SYNTHETIC_TEST_CONTRACT)
        with self.assertRaisesRegex(v.VariableSlotContractError, "ACTION_ONLY_CONTENT_EXCEEDS_SLOT"):
            v.build_control_payloads(tuple(range(8)), tuple(range(10)), v.SYNTHETIC_TEST_CONTRACT)

    def test_neutral_is_plan_independent_at_fixed_length(self):
        length = 96
        first = v.build_control_payloads(tuple(range(length)), (701,), v.SYNTHETIC_TEST_CONTRACT)
        second = v.build_control_payloads(tuple(range(1000, 1000 + length)), (701,), v.SYNTHETIC_TEST_CONTRACT)
        self.assertEqual(first["controls"]["NEUTRAL_L"], second["controls"]["NEUTRAL_L"])

    def test_invalid_token_ids_fail_closed(self):
        with self.assertRaisesRegex(v.VariableSlotContractError, "PLAN_INVALID_TOKEN_ID"):
            v.build_control_payloads((1, 2, 3, 4, 5, 6, 7, -1), (9,), v.SYNTHETIC_TEST_CONTRACT)
        with self.assertRaisesRegex(v.VariableSlotContractError, "ACTION3_INVALID_TOKEN_ID"):
            v.build_control_payloads(tuple(range(8)), (True,), v.SYNTHETIC_TEST_CONTRACT)

    def test_no_decode_reencode_or_science_dependencies(self):
        source = Path(v.__file__).read_text(encoding="utf-8")
        forbidden = (
            ".decode(", ".encode(", "AutoTokenizer", "transformers", "torch", "alfworld", "textworld",
            "requests", "subprocess", "results/science", "packet_",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertTrue(v.SCIENCE_EXECUTION_FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
