"""Synthetic offline tests for family-name source-custody audit; no model calls."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from bind_g0_historical_family_exposure_reconcile import (
    family_from_game_path, reconcile,
)


def path(family: str, trial: str) -> str:
    return ("/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/train/"
            + family + "/" + trial + "/game.tw-pddl")


A = "pick_and_place_simple-Book-None-Desk-201"
B = "pick_and_place_simple-Pen-None-Shelf-202"
C = "pick_and_place_simple-Box-None-Drawer-203"
GHOST = "pick_and_place_simple-Ghost-None-Fridge-999"


class HistoricalFamilyAuditTests(unittest.TestCase):
    def setUp(self):
        self.a1, self.a2 = path(A, "trial_1"), path(A, "trial_2")
        self.b1, self.b2 = path(B, "trial_3"), path(B, "trial_4")
        self.c1 = path(C, "trial_5")
        self.pop = [self.a1, self.a2, self.b1, self.b2, self.c1]

    def test_sources_selected_by_binding_close_family_gap(self):
        r = reconcile(self.pop, {A, GHOST}, [self.b2])
        self.assertEqual(r["historical_index_plus_binding_selected_families_in_archive"], 2)
        self.assertEqual(r["binding_selected_families_missing_from_history_index"], [B])
        self.assertEqual(r["game_paths_not_in_these_two_records_count"], 1)
        self.assertEqual(r["families_not_in_these_two_records"], [C])

    def test_never_grants_science_authorization(self):
        r = reconcile(self.pop, {A}, [self.b1])
        self.assertEqual(r["scientific_gate"], "NOT_AUTHORIZED")
        self.assertIn("BLOCKED_", r["next_gate"])

    def test_all_games_of_named_family_are_conservatively_excluded(self):
        r = reconcile(self.pop, {A}, [self.b1])
        self.assertEqual(r["families_not_in_these_two_records_count"], 1)
        self.assertEqual(r["candidate_game_count_by_family"], {C: 1})

    def test_index_phantom_family_is_explicit_not_silently_counted_in_archive(self):
        r = reconcile(self.pop, {A, GHOST}, [self.b1])
        self.assertEqual(r["indexed_historical_family_names_not_in_archive"], [GHOST])
        self.assertEqual(r["indexed_historical_families_present_in_archive"], 1)

    def test_selected_binding_game_must_be_in_population(self):
        with self.assertRaises(ValueError):
            reconcile(self.pop, {A}, [path(GHOST, "trial_unknown")])

    def test_selected_binding_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            reconcile(self.pop, {A}, [self.a1, self.a1])

    def test_duplicate_population_rejected(self):
        with self.assertRaises(ValueError):
            reconcile(self.pop + [self.a1], {A}, [self.b1])

    def test_noncanonical_game_path_rejected(self):
        with self.assertRaises(ValueError):
            family_from_game_path("/tmp/valid_seen/pick_and_place_simple-Book-None-Desk-201/game.pddl")

    def test_family_parsed_from_full_original_path(self):
        self.assertEqual(family_from_game_path(self.a1), A)

    def test_source_selection_is_not_model_use(self):
        r = reconcile(self.pop, {A}, [self.b1])
        self.assertEqual(r["historical_coverage"], "INCOMPLETE")
        self.assertNotEqual(r["status"], "PASS")
        self.assertNotIn("model_use_count", r)


if __name__ == "__main__":
    unittest.main()
