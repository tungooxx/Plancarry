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
    game_path = directory / "psb-sym1-new-prospective-game.json"
    game.save(str(game_path))
    return game_path


def native_preflight():
    try:
        import textworld
        from textworld.core import EnvInfos
        from textworld.envs.tw import TextWorldEnv
    except (ImportError, OSError) as exc:
        return {"status": "BLOCKED_NATIVE_DEPENDENCIES_UNAVAILABLE",
                "detail": type(exc).__name__, "scientific_gate": "NOT_AUTHORIZED"}

    with tempfile.TemporaryDirectory(prefix="psb-sym1-prospective-") as name:
        path = build_prospective_game(textworld, Path(name))
        game_sha = hashlib.sha256(path.read_bytes()).hexdigest()

        info = EnvInfos(admissible_commands=True, facts=True, objective=True,
                        moves=True, last_action=True)
        base = TextWorldEnv(info)
        base.load(str(path))
        base.reset()

        source = snapshot(base)
        for command in ("go east", "look"):
            invoke(base, command)
        copied_at = snapshot(base)

        # Real native cloning, not an invented record or a mirror of one object.
        arm_a = base.copy()
        arm_b = base.copy()
        if id(arm_a) == id(arm_b) or id(arm_a._game_progression) == id(arm_b._game_progression):
            raise AssertionError("Not independent native game progression instances")
        if not (snapshot(arm_a) == copied_at == snapshot(arm_b)):
            raise AssertionError("Copied environment projections differ before fork")

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
        if not all("vault" in " ".join(z["facts"]).lower() for z in (end_a, end_b)):
            raise AssertionError("Goal room not present in final-state projection")

        # Real TextWorldEnv(.json) has a placeholder raw observation, hence
        # no model/agent experiment until an independent non-oracle renderer is fixed.
        renderer_ready = "To get text observation use" not in str(copied_at["observation"])
        status = ("NATIVE_COPY_PARITY_AND_RENDERER_PROBE_ONLY" if renderer_ready
                  else "NATIVE_COPY_PARITY_ONLY_RENDERER_UNAVAILABLE")
        return {
            "status": status,
            "scientific_gate": "NOT_AUTHORIZED",
            "scope": "Newly generated native TextWorld symbolic JSON game; not PDDL or ALFWorld.",
            "game_sha256": game_sha,
            "prefix_actions": ["go east", "look"],
            "fork_actions": {"A": ["go north", "go east"],
                             "B": ["go east", "go north"]},
            "post_prefix_projection_sha256": hashlib.sha256(
                json.dumps(copied_at, sort_keys=True).encode()).hexdigest(),
            "native_cloned_gameprogressions_distinct": True,
            "mechanically_both_win": True,
            "terminal_scores": [end_a["score"], end_b["score"]],
            "terminal_action_counts": [end_a["moves"], end_b["moves"]],
            "public_renderer_ready": renderer_ready,
            "G0_CERTIFIED": False,
            "MODEL_OWNED_SOURCE_PLANS_VERIFIED": False,
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args = p.parse_args()
    try:
        result = native_preflight()
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
