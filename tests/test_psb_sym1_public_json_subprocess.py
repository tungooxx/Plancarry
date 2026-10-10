"""Real TextWorld 1.7 native two-process public-only PSB IPC integration tests.

No LLM, historical ALFWorld TRAIN, GPU, confirmation, or science G1.
"""
from __future__ import annotations
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORKER=ROOT/"research/psb_sym1_public_json_subprocess.py"
GAME=ROOT/"research/fixtures/psb_sym1_prospective_frozen_game.json"


class Child:
    def __init__(self):
        self.process=subprocess.Popen(
            [sys.executable,"-u",str(WORKER),"--frozen-game",str(GAME)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=ROOT/"research",bufsize=0)
    def send(self,obj):
        raw=obj if type(obj) is bytes else json.dumps(obj,separators=(",",":")).encode("utf-8")
        self.process.stdin.write(raw+b"\n")
        self.process.stdin.flush()
        result=self.process.stdout.readline()
        if not result:raise AssertionError("Native worker died without public response")
        return json.loads(result)
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=4)
        for s in (self.process.stdin,self.process.stdout,self.process.stderr):
            if s is not None:s.close()


class ProcessIsolation(unittest.TestCase):
    def test_two_independent_os_pids_same_prefix_divergent_goal_routes(self):
        a,b=Child(),Child()
        try:
            self.assertNotEqual(a.process.pid,b.process.pid)
            self.assertEqual(a.send({"command":"observe"}),b.send({"command":"observe"}))
            for move in ("go east","look"):
                x=a.send({"command":"act","action":move})
                y=b.send({"command":"act","action":move})
                self.assertEqual(x,y)
                self.assertEqual("OK",x["status"])
            for x in ("go north","go east"):
                end_a=a.send({"command":"act","action":x})
            for y in ("go east","go north"):
                end_b=b.send({"command":"act","action":y})
            self.assertEqual((True,1),(end_a["done"],end_a["score"]))
            self.assertEqual((True,1),(end_b["done"],end_b["score"]))
            self.assertEqual({"status":"TERMINAL"},a.send({"command":"act","action":"look"}))
            self.assertEqual({"status":"TERMINAL"},b.send({"command":"act","action":"look"}))
        finally:a.close();b.close()

    def test_duplicate_command_cannot_move_or_inspect_hidden_objects(self):
        a=Child()
        try:
            before=a.send({"command":"observe"})
            wrong=a.send(b'{"command":"observe","command":"act","action":"go east"}')
            self.assertEqual({"status":"INVALID_REQUEST"},wrong)
            self.assertEqual(before,a.send({"command":"observe"}))
            self.assertEqual({"status":"INVALID_REQUEST"},
                             a.send({"command":"get_quest"}))
            forbidden=json.dumps(a.send({"command":"observe"})).lower()
            for key in ("walkthrough","private_policy","_facts","_game","_winning_policy"):
                self.assertNotIn(key,forbidden)
        finally:a.close()

    def test_native_actions_truncate_at_same_finite_budget(self):
        a,b=Child(),Child()
        try:
            for _ in range(12):
                x=a.send({"command":"act","action":"look"})
                y=b.send({"command":"act","action":"inventory"})
                self.assertEqual("OK",x["status"])
                self.assertEqual("OK",y["status"])
            self.assertTrue(x["done"])
            self.assertTrue(y["done"])
            self.assertEqual((0,0),(x["score"],y["score"]))
            self.assertEqual({"status":"TERMINAL"},a.send({"command":"act","action":"look"}))
            self.assertEqual({"status":"TERMINAL"},b.send({"command":"act","action":"look"}))
        finally:a.close();b.close()

    def test_oversized_json_frame_rejected_and_worker_terminated(self):
        a=Child()
        try:
            result=a.send(b'{"command":"observe","unused":"' + b'X'*2050+b'"}')
            self.assertEqual({"status":"INVALID_REQUEST"},result)
            self.assertEqual(2,a.process.wait(timeout=7))
        finally:a.close()


if __name__=="__main__":
    unittest.main()
