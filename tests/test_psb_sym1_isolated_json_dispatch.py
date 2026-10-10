"""PSB-SYM-1 PR7-based JSON-only dispatcher, real native CPU regression.

No model, paid GPU, historical ALFWorld TRAIN or scientific G0/G1.
"""
import json,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
from psb_sym1_isolated_public_bridge import isolated_pair
from psb_sym1_isolated_json_dispatch import dispatch,dispatch_json,make_isolated_prefix_pair

GAME=ROOT/"research/fixtures/psb_sym1_prospective_frozen_game.json"


class NativeDispatchTests(unittest.TestCase):
    def test_plain_json_public_field_schema(self):
        a,_=isolated_pair(GAME)
        response=json.loads(dispatch_json(a,b'{"command":"observe"}'))
        self.assertEqual({"status","observation","score","done"},set(response))
        self.assertIn("foyer",response["observation"])
        self.assertNotIn("quest",json.dumps(response).lower())

    def test_invalid_debug_or_fork_rpc_disallowed(self):
        a,_=isolated_pair(GAME)
        for raw in [
            b'{"command":"debug"}',b'{"command":"controller_copy"}',
            b'{"command":"reset"}',b'{"command":"observe","inspect":"facts"}',
            b'{"command":"act","action":"go east","private":"_winning_policy"}',
            b'{"command":"act","action":0}',b'[]',b'not-json',b'',
            b'\xff',b'{"command":"observe"}'*300,
        ]:
            with self.subTest(raw=raw[:60]):
                answer=json.loads(dispatch_json(a,raw))
                self.assertEqual(1,len(answer))
                self.assertIn(answer["status"],{"INVALID_REQUEST","ENGINE_ERROR"})

    def test_true_independence_of_game_quest_and_reward_under_hidden_mutation(self):
        a,b=make_isolated_prefix_pair(GAME,("go east","look"))
        self.assertIsNot(a._env._game,b._env._game)
        self.assertIsNot(a._env._inform7,b._env._inform7)
        self.assertIsNot(a._env._game.quests[0],b._env._game.quests[0])
        a._env._game.quests[0].reward=9
        self.assertEqual(b._env._game.quests[0].reward,1)
        for g in (a,b):
            self.assertEqual("OK",dispatch(g,{"command":"act","action":"go north"})["status"])
            self.assertEqual("OK",dispatch(g,{"command":"act","action":"go east"})["status"])
        self.assertEqual(9,dispatch(a,{"command":"observe"})["score"])
        self.assertEqual(1,dispatch(b,{"command":"observe"})["score"])

    def test_recipient_guide_has_identical_common_prefix_and_divergent_routes(self):
        a,b=make_isolated_prefix_pair(GAME,("go east","look"))
        self.assertEqual(dispatch(a,{"command":"observe"}),dispatch(b,{"command":"observe"}))
        a1=dispatch(a,{"command":"act","action":"go north"})
        b1=dispatch(b,{"command":"act","action":"go east"})
        self.assertIn("gallery",a1["observation"])
        self.assertIn("workshop",b1["observation"])
        a2=dispatch(a,{"command":"act","action":"go east"})
        b2=dispatch(b,{"command":"act","action":"go north"})
        self.assertEqual((True,1),(a2["done"],a2["score"]))
        self.assertEqual((True,1),(b2["done"],b2["score"]))

    def test_secret_walkthrough_and_shared_room_mutation_cannot_leak(self):
        a,b=isolated_pair(GAME)
        a._env._game.infos["r_0"].name="A4_FORBIDDEN_ALIAS"
        a._env._game.metadata["walkthrough"]="PRIVATE_DONOR_ROUTE"
        observed=json.loads(dispatch_json(b,b'{"command":"observe"}'))
        txt=json.dumps(observed)
        self.assertNotIn("PRIVATE_DONOR_ROUTE",txt)
        self.assertNotIn("A4_FORBIDDEN_ALIAS",txt)
        self.assertEqual("OK",observed["status"])

    def test_bad_prefix_rejected_before_scientific_attempt(self):
        for commands in [(),("go east","go south"),("go east",None)]:
            with self.subTest(commands=commands):
                with self.assertRaises((ValueError,RuntimeError)):
                    make_isolated_prefix_pair(GAME,commands)

    def test_terminal_cannot_act_and_error_contains_no_backend(self):
        a,_=make_isolated_prefix_pair(GAME,("go east","look"))
        dispatch(a,{"command":"act","action":"go north"})
        dispatch(a,{"command":"act","action":"go east"})
        end=dispatch(a,{"command":"act","action":"look"})
        self.assertEqual({"status":"TERMINAL"},end)

    def test_untrusted_json_nonprimitive_error_sanitized(self):
        a,_=isolated_pair(GAME)
        self.assertEqual({"status":"INVALID_REQUEST"},dispatch(a,{"command":"act","action":{}}))
        self.assertEqual({"status":"INVALID_REQUEST"},dispatch(a,{"command":"observe","x":[]}))
        self.assertEqual(b'{"status":"INVALID_REQUEST"}',dispatch_json(a,b'\xff'))


if __name__=="__main__":
    unittest.main()
