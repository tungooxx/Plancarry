"""CPU-only bounded negative/positive cases for PlanCarry historical source selection."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from bind_g0_scoped_historical_manifest_reconcile import (
    PRE_SCIENCE_FILES, PRIOR_AUDIT, path_family, manifest_selected_families, run,
)


def fixture(tmp):
    expected = [
        "pick_and_place_simple-A-None-Desk-1",
        "pick_and_place_simple-B-None-Desk-2",
        "pick_and_place_simple-C-None-Desk-3",
    ]
    # The operational audit is pinned to 34 (not synthetic stand-in).
    allnames = [f"pick_and_place_simple-TestObject{i}-None-Desk-{i}" for i in range(34)]
    baseline = {"scientific_gate":"NOT_AUTHORIZED","historical_coverage":"INCOMPLETE",
                "families_not_in_these_two_records":allnames,
                "candidate_game_count_by_family":{name:2 for name in allnames}}
    p=tmp/PRIOR_AUDIT;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(baseline))
    def path(family):
        return f"train/{family}/trial_T0123/game.tw-pddl"
    rows=[
        {"model_calls":0,"environment_execution":0,"scientific_result":"NOT_ASSESSED",
         "development":[{"family":allnames[0],"game_path":path(allnames[0])}],
         "confirmation":[{"family":allnames[1],"game_path":path(allnames[1])}]},
        {"model_calls":0,"environment_execution":0,"scientific_result":"NOT_ASSESSED",
         "selected_n":1,"selected":[{"game_path":path(allnames[0])}]},
        {"model_calls":0,"environment_execution":0,"scientific_result":"NOT_ASSESSED",
         "selected_n":1,"selected":[{"game_path":path(allnames[1])}]},
        {"model_calls":0,"environment_execution":0,"scientific_result":"NOT_ASSESSED",
         "selected_n":1,"selected":[{"game_path":path(allnames[2])}]},
    ]
    for rel,row in zip(PRE_SCIENCE_FILES,rows):
        p=tmp/rel;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(row))
    return allnames


class GateTests(unittest.TestCase):
    def test_path_strict_original_train(self):
        self.assertEqual(path_family("json_2.1.1/train/pick_and_place_simple-A/trial_T1/game.tw-pddl"),"pick_and_place_simple-A")
        with self.assertRaises(ValueError):
            path_family("valid_seen/pick_and_place_simple-A/trial_T1/game.tw-pddl")

    def test_zero_call_records_do_not_certify_global_nonuse(self):
        with tempfile.TemporaryDirectory() as td:
            names=fixture(Path(td))
            obj=run(Path(td))
            self.assertEqual(3,obj["union_selected_in_four_planning_records"])
            self.assertEqual(31,obj["no_selection_in_these_four_additional_records"])
            self.assertFalse(obj["GLOBAL_SOURCE_NONCONSUMPTION_ATTESTED"])
            self.assertEqual("NOT_AUTHORIZED",obj["scientific_gate"])

    def test_nonzero_model_calls_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            fixture(Path(td))
            file=Path(td)/PRE_SCIENCE_FILES[0]
            d=json.loads(file.read_text());d["model_calls"]=1
            file.write_text(json.dumps(d))
            with self.assertRaises(ValueError):run(Path(td))

    def test_nonzero_environment_executions_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            fixture(Path(td))
            file=Path(td)/PRE_SCIENCE_FILES[2]
            d=json.loads(file.read_text());d["environment_execution"]=1
            file.write_text(json.dumps(d))
            with self.assertRaises(ValueError):run(Path(td))

    def test_science_result_cannot_claim_assessment(self):
        with tempfile.TemporaryDirectory() as td:
            fixture(Path(td))
            file=Path(td)/PRE_SCIENCE_FILES[1]
            d=json.loads(file.read_text());d["scientific_result"]="PASS"
            file.write_text(json.dumps(d))
            with self.assertRaises(ValueError):run(Path(td))

    def test_selected_count_not_claimed_incorrectly(self):
        with tempfile.TemporaryDirectory() as td:
            fixture(Path(td))
            file=Path(td)/PRE_SCIENCE_FILES[2]
            d=json.loads(file.read_text());d["selected_n"]=12
            file.write_text(json.dumps(d))
            with self.assertRaises(ValueError):run(Path(td))

    def test_record_family_must_match_path(self):
        with tempfile.TemporaryDirectory() as td:
            fixture(Path(td))
            file=Path(td)/PRE_SCIENCE_FILES[0]
            d=json.loads(file.read_text());d["development"][0]["family"]="DIFFERENT"
            file.write_text(json.dumps(d))
            with self.assertRaises(ValueError):run(Path(td))

    def test_missing_historical_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            fixture(Path(td))
            (Path(td)/PRE_SCIENCE_FILES[3]).unlink()
            with self.assertRaises(OSError):run(Path(td))


if __name__=="__main__":
    unittest.main()
