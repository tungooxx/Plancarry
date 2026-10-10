"""Native, CPU-only security regression for PSB-SYM-1 model-facing tool boundary.

Requires PR #6's frozen_public_room_names()/render_public() hardening.
No model, GPU, ALFWorld TRAIN, confirmation or science authorization.
"""
import json
import unittest
from pathlib import Path

from psb_sym1_blind_public_tool_gateway import (
    SOURCE_SHA256, BlindSymbolicGateway, agent_tool_dispatch,
)

FIXTURE = Path(__file__).resolve().parents[1] / "research/fixtures/psb_sym1_prospective_frozen_game.json"


class ModelBoundaryTests(unittest.TestCase):
    def new(self):
        return BlindSymbolicGateway(FIXTURE)

    def test_public_reset_contains_only_whitelisted_fields(self):
        response=agent_tool_dispatch(self.new(),{"command":"observe"})
        self.assertEqual({"observation","legal_actions","done","score"},set(response))
        self.assertIn("foyer",response["observation"])
        self.assertEqual(["go east","inventory","look"],response["legal_actions"])
        self.assertFalse(response["done"])

    def test_reject_privileged_tool_calls_and_extra_json_keys(self):
        gateway=self.new()
        for request in (
            {"command":"debug"},{"command":"copy"},{"command":"reset"},
            {"command":"state"},{"command":"observe","facts":True},
            {"command":"act","action":"look","inspect":"_winning_policy"},
            {"command":"act","action":0},{"command":"act","action":"go west"},
        ):
            with self.subTest(request=request):
                answer=agent_tool_dispatch(gateway,request)
                self.assertEqual({"error"},set(answer))
                self.assertNotIn("_winning_policy",json.dumps(answer))

    def test_public_payload_has_no_private_data(self):
        gateway=self.new()
        gateway._env._game.metadata["walkthrough"]="VERY_SECRET_WINNING_PLAN_SENTINEL"
        gateway._env._game.metadata["private_policy"]={"all_steps":"VERY_SECRET_POLICY"}
        public=agent_tool_dispatch(gateway,{"command":"observe"})
        payload=json.dumps(public)
        for forbidden in ("_facts","_game","_winning_policy","VERY_SECRET","private_policy","walkthrough"):
            self.assertNotIn(forbidden,payload)

    def test_fork_after_actual_common_prefix_and_two_winning_routes(self):
        a=self.new()
        agent_tool_dispatch(a,{"command":"act","action":"go east"})
        agent_tool_dispatch(a,{"command":"act","action":"look"})
        b=a.controller_copy()
        self.assertEqual(agent_tool_dispatch(a,{"command":"observe"}),
                         agent_tool_dispatch(b,{"command":"observe"}))
        aa=agent_tool_dispatch(a,{"command":"act","action":"go north"})
        bb=agent_tool_dispatch(b,{"command":"act","action":"go east"})
        self.assertIn("gallery",aa["observation"])
        self.assertIn("workshop",bb["observation"])
        aa=agent_tool_dispatch(a,{"command":"act","action":"go east"})
        bb=agent_tool_dispatch(b,{"command":"act","action":"go north"})
        self.assertEqual((True,1),(aa["done"],aa["score"]))
        self.assertEqual((True,1),(bb["done"],bb["score"]))
        self.assertEqual({"error"},set(agent_tool_dispatch(a,{"command":"act","action":"look"})))

    def test_adversarial_private_room_name_mutation_isolated_from_peer(self):
        a=self.new()
        b=a.controller_copy()
        self.assertIsNot(a._env._game,b._env._game)
        self.assertIsNot(a._env._inform7,b._env._inform7)
        self.assertIsNot(a._env._game_progression,b._env._game_progression)
        a._env._game.infos["r_0"].name="A4_SPOOFED_ROOM_PRIVATE"
        answer=agent_tool_dispatch(b,{"command":"observe"})
        self.assertEqual({"observation","legal_actions","done","score"},set(answer))
        self.assertIn("Current room: foyer",answer["observation"])
        self.assertNotIn("A4_SPOOFED_ROOM",json.dumps(answer))
        self.assertEqual({"error":"Environment unavailable"},
                         agent_tool_dispatch(a,{"command":"observe"}))

    def test_bad_source_digest_rejected_before_reset(self):
        with self.assertRaises(ValueError):
            BlindSymbolicGateway(FIXTURE,source_sha256="0"*64)

    def test_terminal_horizon_prevents_extra_action(self):
        g=BlindSymbolicGateway(FIXTURE,max_turns=1)
        public=agent_tool_dispatch(g,{"command":"act","action":"go east"})
        self.assertTrue(public["done"])
        self.assertEqual({"error":"Episode finished"},
                         agent_tool_dispatch(g,{"command":"act","action":"look"}))

    def test_bad_request_type_returns_constant_error(self):
        g=self.new()
        for arg in (None,[],3,"__dict__",{"command":"observe","x":"debug"}):
            self.assertEqual({"error":"Invalid request"},agent_tool_dispatch(g,arg))

    def test_fork_replays_entire_real_prefix_with_distinct_native_engine(self):
        a=self.new()
        before=agent_tool_dispatch(a,{"command":"observe"})
        for action in ("go east","look"):
            result=agent_tool_dispatch(a,{"command":"act","action":action})
            self.assertEqual({"observation","legal_actions","done","score"},set(result))
        b=a.controller_copy()
        self.assertIsNot(a._env._game,b._env._game)
        self.assertIsNot(a._env._inform7,b._env._inform7)
        self.assertIsNot(a._env._game_progression,b._env._game_progression)
        self.assertEqual(("go east","look"),a._history)
        self.assertEqual(a._history,b._history)
        self.assertEqual(a._prefix_witnesses,b._prefix_witnesses)
        self.assertEqual(agent_tool_dispatch(a,{"command":"observe"}),
                         agent_tool_dispatch(b,{"command":"observe"}))
        self.assertNotEqual(before["observation"],result["observation"])
        a_next=agent_tool_dispatch(a,{"command":"act","action":"go north"})
        self.assertIn("gallery",a_next["observation"])
        self.assertIn("hub",agent_tool_dispatch(b,{"command":"observe"})["observation"])

    def test_replay_detects_unlogged_native_step_and_blocks_fork(self):
        a=self.new()
        a._env.step("go east")
        with self.assertRaisesRegex(RuntimeError,"outside recorded actions"):
            a.controller_copy()

    def test_private_room_tampering_blocks_only_original_fork(self):
        a=self.new()
        old=a._env._game.infos["r_0"].name
        try:
            a._env._game.infos["r_0"].name="FORGED_ROOM"
            with self.assertRaises((ValueError,RuntimeError)):
                a.controller_copy()
        finally:
            a._env._game.infos["r_0"].name=old
        b=a.controller_copy()
        self.assertIn("foyer",agent_tool_dispatch(b,{"command":"observe"})["observation"])

    def test_terminal_episode_can_be_reconstructed_without_extra_actions(self):
        a=self.new()
        for action in ("go east","look","go north","go east"):
            result=agent_tool_dispatch(a,{"command":"act","action":action})
        self.assertEqual((True,1),(result["done"],result["score"]))
        b=a.controller_copy()
        self.assertEqual(agent_tool_dispatch(a,{"command":"observe"}),
                         agent_tool_dispatch(b,{"command":"observe"}))
        self.assertEqual({"error":"Episode finished"},
                         agent_tool_dispatch(b,{"command":"act","action":"look"}))

    def test_invalid_action_has_no_native_step_or_log(self):
        a=self.new()
        self.assertEqual({"error":"Invalid action"},
                         agent_tool_dispatch(a,{"command":"act","action":"teleport"}))
        self.assertEqual((),a._history)
        self.assertEqual(1,len(a._prefix_witnesses))
        self.assertEqual(agent_tool_dispatch(a,{"command":"observe"}),
                         agent_tool_dispatch(a.controller_copy(),{"command":"observe"}))


if __name__=="__main__":
    unittest.main()
