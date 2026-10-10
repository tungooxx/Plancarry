#!/usr/bin/env python3
"""PSB-SYM-1 CPU-only native TextWorld 1.7.0 symbolic-copy feasibility probe.

Uses TextWorld's actual GameMaker, GameProgression and TextWorldEnv.copy().
Generates a NEW in-memory symbolic game and saves only its freshly generated
JSON to a temporary directory. NEVER reads ALFWorld TRAIN/valid_seen, calls
an LLM, or grants G0/G1/G2/G3 scientific execution permission.

Even full PASS of this script would be a native-backend ENGINEERING smoke test,
NOT an independently attested complete backend copy/renderer or model effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


PUBLIC_TASK_GOAL = "Reach the vault."


def render_public(env) -> str:
    """Only the public task goal, current player room and legal action menu.

    Do NOT include complete world facts, future solution, policy commands,
    quest trees, RNG, game graph or the private native-state digest.
    """
    state = env.state
    goal = state.get("objective")
    if not isinstance(goal, str) or goal != PUBLIC_TASK_GOAL:
        raise ValueError("Game's public objective is missing or drifted")
    facts = env._game_progression.state.facts
    positions = [p for p in facts
                 if p.name == "at" and len(p.arguments) == 2
                 and p.arguments[0].name == "P" and p.arguments[1].type == "r"]
    if len(positions) != 1:
        raise ValueError("Ambiguous public player position")
    room_id = positions[0].arguments[1].name
    room_name = env._game.infos[room_id].name
    if not isinstance(room_name, str) or not room_name:
        raise ValueError("Missing public room name")
    commands = state.get("admissible_commands")
    if not isinstance(commands, list) or len(set(commands)) != len(commands):
        raise ValueError("Native ordered action menu unavailable/duplicated")
    if not all(isinstance(command, str) and command for command in commands):
        raise ValueError("Invalid public command string")
    return (f"Goal: {goal}\n"
            f"Current room: {room_name}\n"
            "Available actions (in native order):\n"
            + "".join(f"- {cmd}\n" for cmd in commands))

def snapshot(env):
    """Restricted engineering projection; NOT a complete backend certificate."""
    gp = env._game_progression
    if gp is None:
        raise RuntimeError("Uninitialized native game progression")
    facts = sorted(str(p) for p in gp.state.facts)
    quests = [
        {"nb_completions": q.nb_completions,
         "win": [(e.triggered, e.untriggerable) for e in q.win_events],
         "fail": [(e.triggered, e.untriggerable) for e in q.fail_events]}
        for q in gp.quest_progressions
    ]
    state = env.state
    return {
        "facts": facts,
        "quests": quests,
        "valid_actions": sorted(str(a) for a in gp.valid_actions),
        "ordered_public_commands": list(state["admissible_commands"]),
        "observation": str(state.feedback),
        "public_observation": render_public(env),
        "moves": env._moves,
        "won": bool(state.get("won")),
        "lost": bool(state.get("lost")),
        "score": int(gp.score),
        "goal": str(state["objective"]),
    }


def invoke(env, command):
    before = snapshot(env)
    if command not in before["ordered_public_commands"]:
        raise AssertionError(f"Native engine says action is NOT admissible: {command!r}")
    state, score, done = env.step(command)
    after = snapshot(env)
    if state.get("done", False) != done:
        raise AssertionError("Inconsistent native done bit")
    if gp_score := (int(score) != after["score"]):
        raise AssertionError("Native score differs from captured progression")
    return before, after


def build_prospective_game(textworld, directory):
    from textworld.generator.game import Event, Quest

    options = textworld.GameOptions()
    options.seeds = 20261010
    maker = textworld.GameMaker(options)

    foyer = maker.new_room("foyer")
    hub = maker.new_room("hub")
    gallery = maker.new_room("gallery")
    workshop = maker.new_room("workshop")
    vault = maker.new_room("vault")

    maker.set_player(foyer)
    maker.connect(foyer.east, hub.west)
    maker.connect(hub.north, gallery.south)
    maker.connect(hub.east, workshop.west)
    maker.connect(gallery.east, vault.west)
    maker.connect(workshop.north, vault.south)

    goal = maker.new_fact("at", maker.player, vault)
    maker.quests = [Quest(win_events=[Event(conditions={goal})])]
    game = maker.build()
    game._objective = PUBLIC_TASK_GOAL
    game_path = directory / "psb-sym1-new-prospective-game.json"
    game.save(str(game_path))
    return game_path


def native_preflight(frozen_game: Path | None = None, expected_game_sha256: str | None = None):
    try:
        import textworld
        from textworld.core import EnvInfos
        from textworld.envs.tw import TextWorldEnv
    except (ImportError, OSError) as exc:
        return {"status": "BLOCKED_NATIVE_DEPENDENCIES_UNAVAILABLE",
                "detail": type(exc).__name__, "scientific_gate": "NOT_AUTHORIZED"}

    with tempfile.TemporaryDirectory(prefix="psb-sym1-prospective-") as name:
        newly_frozen = False
        if frozen_game is None:
            if expected_game_sha256 is not None:
                raise ValueError("Digest expectation requires an existing frozen-game path")
            path = build_prospective_game(textworld, Path(name))
        else:
            if frozen_game.name != "psb_sym1_prospective_frozen_game.json":
                raise ValueError("Frozen file name must be the dedicated PSB-SYM-1 fixture")
            if frozen_game.exists():
                if expected_game_sha256 is None:
                    raise ValueError("Cannot reuse frozen source without expected SHA256")
                path = frozen_game
            else:
                if expected_game_sha256 is not None:
                    raise ValueError("Expected immutable source is missing; never silently regenerate")
                staging = build_prospective_game(textworld, Path(name))
                frozen_game.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents overwriting an already frozen
                # source when two workers race; use digest-pinned replay later.
                with frozen_game.open("xb") as output:
                    output.write(staging.read_bytes())
                path = frozen_game
                newly_frozen = True
        game_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_game_sha256 is not None and game_sha != expected_game_sha256:
            raise ValueError("Frozen TextWorld game bytes differ from committed SHA256")

        info = EnvInfos(admissible_commands=True, facts=True, objective=True,
                        moves=True, last_action=True)
        base = TextWorldEnv(info)
        base.load(str(path))
        base.reset()

        source = snapshot(base)
        # Copy immediately after RESET then apply exact same real prefix
        # action to each native instance. The complete engine projection
        # and exact externally visible renderer output must match each step.
        arm_a = base.copy()
        arm_b = base.copy()
        if id(arm_a) == id(arm_b) or id(arm_a._game_progression) == id(arm_b._game_progression):
            raise AssertionError("Not independent native game progression instances")
        if not (snapshot(arm_a) == snapshot(base) == snapshot(arm_b)):
            raise AssertionError("Cloned reset projections differ")
        prefix = ("go east", "look")
        prefix_checks = []
        for command in prefix:
            a_before, a_after = invoke(arm_a, command)
            b_before, b_after = invoke(arm_b, command)
            if a_before != b_before or a_after != b_after:
                raise AssertionError("Native A/B common-prefix state or renderer diverged")
            prefix_checks.append({"action": command,
                                  "snapshot_sha256": hashlib.sha256(
                                      json.dumps(a_after, sort_keys=True).encode()).hexdigest(),
                                  "public_bytes_sha256": hashlib.sha256(
                                      render_public(arm_a).encode()).hexdigest()})
        copied_at = snapshot(arm_a)

        shared_game_before = sorted(str(x) for x in base._game.world.state.facts)
        b_before = snapshot(arm_b)
        invoke(arm_a, "go north")  # A fork
        if snapshot(arm_b) != b_before:
            raise AssertionError("A's mutation changed B's native state")
        if sorted(str(x) for x in base._game.world.state.facts) != shared_game_before:
            raise AssertionError("A's progression changed shared Game initial world")

        invoke(arm_b, "go east")   # B fork, from identical pre-fork state
        invoke(arm_a, "go east")   # gallery -> vault, terminal
        invoke(arm_b, "go north")  # workshop -> vault, terminal

        end_a, end_b = snapshot(arm_a), snapshot(arm_b)
        if not (end_a["won"] and end_b["won"] and
                not end_a["lost"] and not end_b["lost"]):
            raise AssertionError("Two mechanically distinct routes did not both win")
        if end_a["score"] != end_b["score"]:
            raise AssertionError("Two routes have different terminal reward")
        if end_a["moves"] != end_b["moves"]:
            raise AssertionError("Two routes have different total action cost")
        # Room display names need not appear in symbolic Proposition.__str__;
        # rely on actual native quest completion plus terminal reward instead.

        # Real TextWorldEnv(.json) has a placeholder raw observation, hence
        # no model/agent experiment until an independent non-oracle renderer is fixed.
        # Check pre-fork rendering against the TWO copies at the SAME prefix
        # boundary; after their divergent rollouts, their room labels SHOULD
        # differ and must never be compared as if they were same state.
        renderer_ready = copied_at["public_observation"].startswith("Goal: Reach the vault.")
        status = ("NATIVE_COPY_PARITY_AND_RENDERER_PROBE_ONLY" if renderer_ready
                  else "NATIVE_COPY_PARITY_ONLY_RENDERER_UNAVAILABLE")
        return {
            "status": status,
            "scientific_gate": "NOT_AUTHORIZED",
            "scope": "Newly generated native TextWorld symbolic JSON game; not PDDL or ALFWorld.",
            "game_sha256": game_sha,
            "frozen_game_reused": frozen_game is not None and not newly_frozen,
            "frozen_game_created_this_run": newly_frozen,
            "frozen_game_expected_digest_matched": expected_game_sha256 == game_sha if expected_game_sha256 else False,
            "prefix_actions": list(prefix),
            "prefix_checks": prefix_checks,
            "fork_actions": {"A": ["go north", "go east"],
                             "B": ["go east", "go north"]},
            "post_prefix_projection_sha256": hashlib.sha256(
                json.dumps(copied_at, sort_keys=True).encode()).hexdigest(),
            "native_cloned_gameprogressions_distinct": True,
            "mechanically_both_win": True,
            "terminal_scores": [end_a["score"], end_b["score"]],
            "terminal_action_counts": [end_a["moves"], end_b["moves"]],
            "public_renderer_ready": renderer_ready,
            "public_renderer_kind": "public-goal-current-room-ordered-actions-only",
            "public_renderer_src_independently_reviewed": False,
            "G0_CERTIFIED": False,
            "MODEL_OWNED_SOURCE_PLANS_VERIFIED": False,
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--frozen-game",type=Path,default=None)
    p.add_argument("--expected-game-sha256",type=str,default=None)
    args = p.parse_args()
    try:
        result = native_preflight(frozen_game=args.frozen_game,
                                  expected_game_sha256=args.expected_game_sha256)
    except Exception as err:
        result = {"status": "BLOCKED_NATIVE_BACKEND_PREFLIGHT",
                  "error_type": type(err).__name__,
                  "error": str(err)[:350],
                  "scientific_gate": "NOT_AUTHORIZED"}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"].startswith("NATIVE_COPY_PARITY") else 2


if __name__=="__main__":
    sys.exit(main())
