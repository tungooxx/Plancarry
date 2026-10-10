#!/usr/bin/env python3
"""PSB-SYM-1 engineering-only isolated TextWorld 1.7.0 public bridge.

This is NOT an LLM tool, proof of model behavior, G0 certificate, or a
general-purpose TextWorld safety boundary. Expose only JSON-primitive results
of observe()/act() to a non-Python client, never the bridge or env objects.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_GAME_SHA256 = "40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67"
FIXTURE_NAME = "psb_sym1_prospective_frozen_game.json"
PUBLIC_GOAL = "Reach the vault."
ROOMS = {"r_0": "foyer", "r_1": "hub", "r_2": "gallery",
         "r_3": "workshop", "r_4": "vault"}
ALLOWED_COMMANDS = frozenset(("look", "inventory", "go north",
                               "go south", "go east", "go west"))
STATUS_OK = "OK"
STATUS_INVALID_ACTION = "INVALID_ACTION"
STATUS_GUARD_VIOLATION = "GUARD_VIOLATION"
STATUS_ENGINE_ERROR = "ENGINE_ERROR"
STATUS_TERMINAL = "TERMINAL"
SCIENTIFIC_GATE = "NOT_AUTHORIZED"


class SourceMismatch(ValueError):
    """Immutable game source missing/altered."""


def _checked_game(path: Path) -> Path:
    path = Path(path)
    if path.name != FIXTURE_NAME:
        raise SourceMismatch("WRONG_FIXTURE_NAME")
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED_GAME_SHA256:
        raise SourceMismatch("SOURCE_DIGEST_MISMATCH")
    return path


def _public_observation(env: Any) -> str:
    """Whitelist only fixed objective, player room, ordered legal menu.

    Never serialize env.state, exceptions, private facts, Game, Quest,
    walkthrough, solver state or winning policy into model-visible output.
    """
    state = env.state
    if state.get("objective") != PUBLIC_GOAL:
        raise ValueError("UNTRUSTED_GOAL")
    candidates = [p for p in env._game_progression.state.facts
                  if p.name == "at" and len(p.arguments) == 2
                  and p.arguments[0].name == "P"
                  and p.arguments[1].type == "r"]
    if len(candidates) != 1:
        raise ValueError("AMBIGUOUS_POSITION")
    room_id = candidates[0].arguments[1].name
    if room_id not in ROOMS:
        raise ValueError("UNKNOWN_ROOM")
    name = ROOMS[room_id]
    # Whitelist fixture data, not arbitrary mutable Game metadata.
    if env._game.infos[room_id].name != name:
        raise ValueError("ROOM_LABEL_DRIFT")
    menu = state.get("admissible_commands")
    if not isinstance(menu, list) or not menu:
        raise ValueError("NO_LEGAL_MENU")
    if any(type(x) is not str or x not in ALLOWED_COMMANDS for x in menu):
        raise ValueError("UNSAFE_COMMAND")
    if len(set(menu)) != len(menu):
        raise ValueError("DUPLICATE_COMMAND")
    return ("Goal: " + PUBLIC_GOAL + "\n"
            + "Current room: " + name + "\n"
            + "Available actions (in native order):\n"
            + "".join("- " + action + "\n" for action in menu))


class GuardedSymbolicEnv:
    """One independently loaded native TextWorld environment per arm.

    Bridge instances own private engine objects. A model must receive only
    observe()/act() JSON outputs via a separate host, NEVER the Python object.
    """

    def __init__(self, frozen_fixture: Path):
        from textworld.core import EnvInfos
        from textworld.envs.tw import TextWorldEnv

        fixed = _checked_game(Path(frozen_fixture))
        env = TextWorldEnv(EnvInfos(admissible_commands=True, objective=True,
                                   moves=True, policy_commands=False, facts=False))
        env.load(str(fixed))
        env.reset()
        self._env = env
        self._tainted = False
        # Reject changing source object metadata even before agent exposure.
        if self.observe()["status"] != STATUS_OK:
            raise ValueError("PUBLIC_RENDERER_REJECTED_FIXTURE")

    def observe(self) -> dict[str, Any]:
        if self._tainted:
            return {"status": STATUS_GUARD_VIOLATION}
        try:
            text = _public_observation(self._env)
            state = self._env.state
            return {"status": STATUS_OK, "observation": text,
                    "done": bool(state.get("won") or state.get("lost")),
                    "score": int(self._env._game_progression.score)}
        except Exception:
            self._tainted = True
            return {"status": STATUS_GUARD_VIOLATION}

    def act(self, command: str) -> dict[str, Any]:
        before = self.observe()
        if before["status"] != STATUS_OK:
            return before
        if before["done"]:
            return {"status": STATUS_TERMINAL}
        # Reject all non-exact strings, whitespace tricks and unsupported cmds.
        if type(command) is not str or command not in ALLOWED_COMMANDS:
            return {"status": STATUS_INVALID_ACTION}
        menu = tuple(self._env.state["admissible_commands"])
        if command not in menu:
            return {"status": STATUS_INVALID_ACTION}
        try:
            self._env.step(command)
        except Exception:
            self._tainted = True
            # Engine/exception trace and its internal facts MUST NOT be shown.
            return {"status": STATUS_ENGINE_ERROR}
        return self.observe()


def isolated_pair(frozen_fixture: Path) -> tuple[GuardedSymbolicEnv,
                                                  GuardedSymbolicEnv]:
    """Never use TextWorldEnv.copy(): it soft-shares Game/Inform7 references."""
    a = GuardedSymbolicEnv(frozen_fixture)
    b = GuardedSymbolicEnv(frozen_fixture)
    for attr in ("_env",):
        if getattr(a, attr) is getattr(b, attr):
            raise AssertionError("ENGINE_ALIAS")
    for attr in ("_game", "_inform7", "_game_progression", "state"):
        if getattr(a._env, attr) is getattr(b._env, attr):
            raise AssertionError("NATIVE_ALIAS_" + attr)
    return a, b


def engineering_preflight(frozen_fixture: Path) -> dict[str, Any]:
    """Single fixture mechanical replay. Never a scientific G0/G1 test."""
    a, b = isolated_pair(frozen_fixture)
    if a.observe() != b.observe():
        raise AssertionError("RESET_PUBLIC_PARITY_FAILED")

    a_origin = a._env._game.infos["r_0"].name
    b_origin = b.observe()
    a._env._game.infos["r_0"].name = "A4_ALIAS_PROBE"
    if b.observe() != b_origin:
        raise AssertionError("CROSS_ARM_PUBLIC_RENDER_LEAK")
    a._env._game.infos["r_0"].name = a_origin

    prefix = ("go east", "look")
    for command in prefix:
        if a.act(command) != b.act(command):
            raise AssertionError("PREFIX_PUBLIC_PARITY_FAILED")
    # At the fork both arms have the same *native* state projection too.
    facts_a = sorted(map(str, a._env._game_progression.state.facts))
    facts_b = sorted(map(str, b._env._game_progression.state.facts))
    if facts_a != facts_b:
        raise AssertionError("FORK_FACTS_DIFFER")
    for command in ("go north", "go east"):
        if a.act(command)["status"] != STATUS_OK:
            raise AssertionError("A_FORK_FAILED")
    for command in ("go east", "go north"):
        if b.act(command)["status"] != STATUS_OK:
            raise AssertionError("B_FORK_FAILED")
    end_a, end_b = a.observe(), b.observe()
    if not (end_a["done"] and end_b["done"]
            and end_a["score"] == end_b["score"] == 1):
        raise AssertionError("ROUTE_GOAL_FAILED")
    if (a._env._moves, b._env._moves) != (4, 4):
        raise AssertionError("ACTION_BUDGET_FAILED")
    return {"status": "ISOLATED_NATIVE_PUBLIC_BRIDGE_STRUCTURAL_ONLY",
            "scientific_gate": SCIENTIFIC_GATE,
            "fixture_sha256": EXPECTED_GAME_SHA256,
            "copy_used": False, "instances_share_game": False,
            "instances_share_inform7": False, "common_prefix": list(prefix),
            "forks": {"A": ["go north", "go east"],
                      "B": ["go east", "go north"]},
            "terminal_scores": [1, 1], "terminal_moves": [4, 4],
            "no_model_calls": True,
            "not_proof_of_complete_rng_or_PDDL_state": True}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-game", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = engineering_preflight(args.frozen_game)
        code = 0
    except Exception:
        result = {"status": "BLOCKED_NATIVE_PUBLIC_BRIDGE",
                  "scientific_gate": SCIENTIFIC_GATE}
        code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
