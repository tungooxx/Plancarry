"""Native TextWorld 1.7.0 PSB-SYM-1 renderer source/branch-isolation tests.

Engineering-only against one SHA-pinned prospective symbolic fixture.
Never opens ALFWorld/TRAIN, calls an LLM, or approves scientific G0.
"""
from __future__ import annotations
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from psb_sym1_textworld_native_copy_preflight import (
    PUBLIC_TASK_GOAL, frozen_public_room_names, render_public,
    snapshot, invoke, native_preflight,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "research/fixtures/psb_sym1_prospective_frozen_game.json"
SOURCE_SHA = "40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67"


def native_environment():
    from textworld.core import EnvInfos
    from textworld.envs.tw import TextWorldEnv
    options = EnvInfos(admissible_commands=True, facts=True, objective=True,
                       moves=True, last_action=True)
    env = TextWorldEnv(options)
    env.load(str(FIXTURE))
    env.reset()
    return env


class PsbFrozenPublicRendererTests(unittest.TestCase):
    def test_exact_original_fixture_digest_and_room_map(self):
        self.assertEqual(SOURCE_SHA, hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        names = frozen_public_room_names(FIXTURE, SOURCE_SHA)
        self.assertEqual("foyer", names["r_0"])
        self.assertEqual("vault", names["r_4"])
        with self.assertRaises(TypeError):
            names["r_0"] = "MUTATED"

    def test_source_digest_failure_closed_before_render(self):
        with tempfile.TemporaryDirectory(prefix="psb-g0-native-source-") as td:
            p = Path(td) / "fake-source.json"
            p.write_bytes(FIXTURE.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                frozen_public_room_names(p, SOURCE_SHA)

    def test_real_native_renderer_before_and_after_shared_mutation(self):
        base = native_environment()
        a, b = base.copy(), base.copy()
        names = frozen_public_room_names(FIXTURE, SOURCE_SHA)
        first = render_public(b, names)
        self.assertIn("Current room: foyer", first)
        self.assertEqual(first, render_public(a, names))
        self.assertIs(a._game, b._game)
        old = a._game.infos["r_0"].name
        try:
            a._game.infos["r_0"].name = "A4_SPOOFED_ROOM"
            with self.assertRaisesRegex(ValueError, "metadata drift"):
                render_public(b, names)
        finally:
            a._game.infos["r_0"].name = old
        self.assertEqual(first, render_public(b, names))

    def test_mutation_at_new_location_is_rejected(self):
        base = native_environment()
        a, b = base.copy(), base.copy()
        names = frozen_public_room_names(FIXTURE, SOURCE_SHA)
        invoke(a, "go east", names)
        invoke(b, "go east", names)
        self.assertIn("Current room: hub", render_public(b, names))
        old = a._game.infos["r_1"].name
        try:
            a._game.infos["r_1"].name = "SECRET_ROUTE"
            with self.assertRaisesRegex(ValueError, "metadata drift"):
                render_public(b, names)
        finally:
            a._game.infos["r_1"].name = old
        self.assertIn("Current room: hub", render_public(b, names))

    def test_private_oracle_metadata_never_enters_public_projection(self):
        env = native_environment()
        names = frozen_public_room_names(FIXTURE, SOURCE_SHA)
        env._game.metadata["walkthrough"] = ["SECRET_ROUTE_DO_NOT_SHOW"]
        text = render_public(env, names)
        self.assertNotIn("SECRET_ROUTE", text)
        self.assertNotIn("walkthrough", text)
        self.assertNotIn("_winning_policy", text)
        self.assertNotIn("game_progression", text)
        self.assertIn(PUBLIC_TASK_GOAL, text)

    def test_independent_native_common_prefix_remains_equal(self):
        base = native_environment()
        a, b = base.copy(), base.copy()
        names = frozen_public_room_names(FIXTURE, SOURCE_SHA)
        self.assertEqual(snapshot(a, names), snapshot(b, names))
        for command in ("go east", "look"):
            left = invoke(a, command, names)
            right = invoke(b, command, names)
            self.assertEqual(left, right)
        stable_b = snapshot(b, names)
        invoke(a, "go north", names)
        self.assertEqual(stable_b, snapshot(b, names))

    def test_entire_frozen_native_preflight_remains_unprivileged(self):
        status = native_preflight(frozen_game=FIXTURE, expected_game_sha256=SOURCE_SHA)
        self.assertEqual("NATIVE_COPY_PARITY_AND_RENDERER_PROBE_ONLY", status["status"])
        self.assertEqual("NOT_AUTHORIZED", status["scientific_gate"])
        self.assertFalse(status["G0_CERTIFIED"])
        self.assertFalse(status["MODEL_OWNED_SOURCE_PLANS_VERIFIED"])


if __name__ == "__main__":
    unittest.main()
