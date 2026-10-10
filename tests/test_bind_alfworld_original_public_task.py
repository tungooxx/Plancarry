"""Validate the real public ALFWorld grammar task, not a filename guess.

No LLM or native game execution. Real extracted source used only when the
PLANCARRY_ALFWORLD_ROOT environment variable points to the original corpus.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from bind_alfworld_original_public_task import original_public_task

ROOT=Path(os.environ.get("PLANCARRY_ALFWORLD_ROOT","/root/not-mounted-original-alfworld"))

class OriginalPublicTaskTests(unittest.TestCase):
    def real(self):
        example=ROOT/"train/pick_and_place_simple-Lettuce-None-CounterTop-25/trial_T20190907_000052_389529/game.tw-pddl"
        if not example.is_file():self.skipTest("Original ALFWorld source not mounted")
        return example

    def test_exact_task_is_not_directory_descriptor(self):
        value=original_public_task(self.real())
        self.assertEqual("Your task is to: put some lettuce on countertop.",
                         value["task_instruction"])
        self.assertEqual("ORIGINAL_TEXTWORLD_PUBLIC_GRAMMAR_TASK_RHS",
                         value["provenance"])
        self.assertTrue(value["is_public_intro_task"])
        self.assertNotIn("walkthrough",value)

    def test_all_original_790_contain_valid_public_instructions(self):
        self.real()
        files=list((ROOT/"train").glob("pick_and_place_simple-*/trial_*/game.tw-pddl"))
        self.assertEqual(790,len(files))
        tasks=[original_public_task(p) for p in files]
        self.assertTrue(all(x["is_public_intro_task"] for x in tasks))
        self.assertEqual(280,len(set(x["task_instruction"] for x in tasks)))

    def test_duplicate_task_definition_fails_closed(self):
        p=self.real()
        data=json.loads(p.read_text())
        # Duplicate embedded public grammar stanza is an invalid source schema.
        from bind_alfworld_original_public_task import _TASK
        task_match=_TASK.search(data["grammar"])
        self.assertIsNotNone(task_match)
        data["grammar"] += "\n" + task_match.group(0)
        with tempfile.TemporaryDirectory() as t:
            q=Path(t)/"game.tw-pddl"
            q.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                original_public_task(q)

    def test_missing_public_intro_reference_fails_closed(self):
        p=self.real()
        data=json.loads(p.read_text())
        self.assertIn("#task#",data["grammar"])
        data["grammar"]=data["grammar"].replace("#task#","OMITTED_TASK",1)
        with tempfile.TemporaryDirectory() as t:
            q=Path(t)/"game.tw-pddl"
            q.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                original_public_task(q)

    def test_walkthrough_sentinel_not_returned(self):
        p=self.real()
        data=json.loads(p.read_text())
        data["walkthrough"]=["HIDDEN_PRIVILEGED_WINNING_PLAN_DO_NOT_SHOW"]
        with tempfile.TemporaryDirectory() as t:
            q=Path(t)/"game.tw-pddl"
            q.write_text(json.dumps(data))
            response=original_public_task(q)
        self.assertNotIn("HIDDEN_PRIVILEGED_WINNING_PLAN_DO_NOT_SHOW",
                         json.dumps(response))

if __name__=="__main__":
    unittest.main()
