"""Synthetic CPU-only regression: source selection has exactly one SHA delimiter."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from bind_source_selection_guard import SCHEMA, _pick, audit


def fixture():
    population = [f"train/pick_and_place_simple-Book-None-Desk-{i}/trial_T000000000000_{i}/game.tw-pddl" for i in range(50)]
    salt = "plancarry-binding-v1"
    return {
        "schema": SCHEMA, "population": population, "binding_salt": salt,
        "binding_count": 12,
        "binding_selected": _pick(population, salt, 12, legacy=False),
        "pilot_selected": [],
    }


class Tests(unittest.TestCase):
    def assert_invalid(self, obj):
        self.assertEqual("INVALID_INPUT", audit(obj)["verdict"])

    def test_fixture_no_bogus_pass(self):
        x = fixture(); x["pilot_selected"] = [p for p in x["population"] if p not in x["binding_selected"]][:10]
        r = audit(x)
        self.assertEqual("BLOCKED_GLOBAL_USAGE_UNATTESTED", r["verdict"])
        self.assertEqual("NOT_AUTHORIZED", r["scientific_gate"])
        self.assertIsNone(r["model_inference_count"])

    def test_legacy_missing_newline_detected(self):
        x = fixture(); x["binding_selected"] = _pick(x["population"], x["binding_salt"], 12, legacy=True)
        x["pilot_selected"] = [p for p in x["population"] if p not in x["binding_selected"]][:10]
        r = audit(x)
        self.assertEqual("BLOCKED_LEGACY_SALT_MISMATCH", r["verdict"])
        self.assertTrue(r["binding_selection_matches_wrong_legacy_delimiter"])

    def test_correct_selection_but_pilot_overlap(self):
        x = fixture(); x["pilot_selected"] = x["binding_selected"][:4]
        r = audit(x)
        self.assertEqual("BLOCKED_SELECTED_COHORT_OVERLAP", r["verdict"])
        self.assertEqual(4, r["literal_overlap_count"])
        self.assertIsNone(r["environment_inspection_count"])

    def test_binding_reorder_invalid_selection(self):
        x = fixture(); x["pilot_selected"] = x["population"][-2:]
        x["binding_selected"] = list(reversed(x["binding_selected"]))
        self.assertEqual("BLOCKED_BINDING_SELECTION_MISMATCH", audit(x)["verdict"])

    def test_non_target_split(self):
        x = fixture(); x["population"][0] = x["population"][0].replace("train/", "valid_seen/")
        x["pilot_selected"] = x["population"][-1:]
        self.assert_invalid(x)

    def test_extra_unknown_field(self):
        x = fixture(); x["pilot_selected"] = x["population"][-1:]; x["passed_g0"] = True
        self.assert_invalid(x)

    def test_duplicate_population(self):
        x = fixture(); x["population"].append(x["population"][0]); x["pilot_selected"] = x["population"][-2:-1]
        self.assert_invalid(x)

    def test_bool_binding_count(self):
        x = fixture(); x["binding_count"] = True; x["pilot_selected"] = x["population"][-1:]
        self.assert_invalid(x)

    def test_not_in_population(self):
        x = fixture(); x["pilot_selected"] = ["train/pick_and_place_simple-Cup-None-Desk-5/trial_T9999/game.tw-pddl"]
        self.assert_invalid(x)

    def test_absolute_and_parent_escape_paths(self):
        x = fixture(); x["pilot_selected"] = ["/train/pick_and_place_simple-Book-None-Desk-5/trial_T9999/game.tw-pddl"]
        self.assert_invalid(x)

    def test_empty_pilot_invalid(self):
        self.assert_invalid(fixture())

    def test_false_model_success_not_inferred(self):
        x = fixture(); x["pilot_selected"] = x["binding_selected"][:2]
        r = audit(x)
        self.assertNotIn("PASS", r["verdict"])
        self.assertEqual("NOT_AUTHORIZED", r["scientific_gate"])


if __name__ == "__main__":
    unittest.main()
