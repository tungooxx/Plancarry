#!/usr/bin/env python3
"""PSB-SYM-1 strict model-facing public-tool adapter (engineering only).

No model invocation, scientific execution permission, training, or confirmation.
Only the public goal, current room, legal commands, terminal flag and score
cross the boundary. Hidden TextWorld state, quest, policies and native facts
remain trusted-controller-only. Raw backend exceptions are never returned.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

SOURCE_SHA256 = "40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67"
VISIBLE_KEYS = frozenset({"observation", "legal_actions", "done", "score"})
MAX_TURNS = 12


class PublicToolError(Exception):
    """Deliberately content-free failure for agent-visible invalid calls."""


class BlindSymbolicGateway:
    """Trusted controller has engine access. Model caller sees only return dicts.

    Do not directly expose Python object attributes to an evaluated model.
    Access to env/state is isolated by the application/controller process.
    """

    def __init__(self, frozen_game: Path, source_sha256: str = SOURCE_SHA256, max_turns: int = MAX_TURNS):
        if not (isinstance(max_turns, int) and not isinstance(max_turns, bool)
                and 1 <= max_turns <= MAX_TURNS):
            raise ValueError("Unsupported frozen horizon")
        path = Path(frozen_game)
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source_sha256 or source_sha256 != SOURCE_SHA256:
            raise ValueError("Wrong frozen game or hash")
        import textworld
        from textworld.core import EnvInfos
        from textworld.envs.tw import TextWorldEnv
        from psb_sym1_textworld_native_copy_preflight import frozen_public_room_names
        self._source = path
        self._names: Mapping[str,str] = frozen_public_room_names(path, source_sha256)
        self._request_infos = EnvInfos(admissible_commands=True,facts=True,objective=True)
        self._env = TextWorldEnv(self._request_infos)
        self._env.load(str(self._source))
        self._env.reset()
        self._turns = 0
        self._done = False
        self._score = 0
        self._max_turns = max_turns
        # These commitments remain trusted-controller-only. The future agent
        # sees exactly observe()/act() payloads, never private native facts.
        from psb_sym1_textworld_native_copy_preflight import snapshot
        self._history: tuple[str, ...] = ()
        self._prefix_witnesses = (snapshot(self._env, self._names),)

    @classmethod
    def _from_copy(cls, original: "BlindSymbolicGateway"):
        """Reconstruct an isolated native engine; never soft-copy Game/Inform7.

        Only a deterministic, same-source, byte/state-matched replay is
        eligible to fork. This is a one-fixture engineering invariant, not
        full RNG/process isolation or a scientific state-equivalence proof.
        """
        if len(original._history) != original._turns or (
            len(original._prefix_witnesses) != original._turns + 1
        ):
            raise RuntimeError("Incomplete original native action history")
        # Refuse to bless a source already mutated at its public boundary.
        old_public = original._public()
        from psb_sym1_textworld_native_copy_preflight import snapshot
        if snapshot(original._env, original._names) != original._prefix_witnesses[-1]:
            raise RuntimeError("Original native state changed outside recorded actions")
        fresh = cls(original._source, SOURCE_SHA256, original._max_turns)
        if (fresh._env._game is original._env._game
                or fresh._env._inform7 is original._env._inform7
                or fresh._env._game_progression is original._env._game_progression):
            raise RuntimeError("Native fork still shares mutable engine references")
        if fresh._prefix_witnesses != original._prefix_witnesses[:1]:
            raise RuntimeError("Frozen native reset did not replay identically")
        for i, action in enumerate(original._history, 1):
            # A recorded action must reproduce the original witness after
            # EVERY common-prefix step, not just coincide at the final room.
            fresh.act(action)
            if fresh._prefix_witnesses[i] != original._prefix_witnesses[i]:
                raise RuntimeError("Native prefix replay diverged")
        if (fresh._history != original._history or fresh._turns != original._turns
                or fresh._done != original._done or fresh._score != original._score
                or fresh._public() != old_public):
            raise RuntimeError("Native fork public/terminal parity mismatch")
        return fresh

    def controller_copy(self) -> "BlindSymbolicGateway":
        """Only privileged evaluator/controller may fork; never expose via LLM tool."""
        return self._from_copy(self)

    def _public(self) -> dict:
        from psb_sym1_textworld_native_copy_preflight import render_public
        obs = render_public(self._env, self._names)
        cmds = self._env.state.get("admissible_commands")
        if not isinstance(cmds,list) or len(set(cmds)) != len(cmds):
            raise ValueError("Native action order is invalid")
        public = {
            "observation": str(obs),
            "legal_actions": list(cmds),
            "done": bool(self._done),
            "score": int(self._score),
        }
        if set(public)!=VISIBLE_KEYS:
            raise ValueError("Public boundary fields unexpectedly changed")
        return public

    def observe(self) -> dict:
        """Model-visible observation: exactly four whitelisted fields."""
        try:
            return self._public()
        except Exception:
            raise PublicToolError("Environment unavailable") from None

    def act(self, action: str) -> dict:
        """Model-visible exact legal command, never permissive command repair."""
        if not isinstance(action, str):
            raise PublicToolError("Invalid action")
        if self._done or self._turns >= self._max_turns:
            raise PublicToolError("Episode finished")
        try:
            menu = self._public()["legal_actions"]
            if action not in menu:
                raise PublicToolError("Invalid action")
            _, score, done = self._env.step(action)
            self._turns += 1
            self._score = int(score)
            self._done = bool(done) or self._turns >= self._max_turns
            public = self._public()
            from psb_sym1_textworld_native_copy_preflight import snapshot
            next_witness = snapshot(self._env, self._names)
            self._history += (action,)
            self._prefix_witnesses += (next_witness,)
            return public
        except PublicToolError:
            raise
        except Exception:
            # Do not reveal backend metadata, full state, original exception
            # strings, file paths, winning plans, or internal stack frames.
            raise PublicToolError("Environment unavailable") from None


def agent_tool_dispatch(gateway: BlindSymbolicGateway, request: dict) -> dict:
    """The sole IPC entry point. No introspection/reset/fork/debug RPC."""
    if not isinstance(request,dict):
        return {"error":"Invalid request"}
    command=request.get("command")
    if command=="observe" and set(request)=={"command"}:
        try:return gateway.observe()
        except PublicToolError:return {"error":"Environment unavailable"}
    if command=="act" and set(request)=={"command","action"}:
        try:return gateway.act(request["action"])
        except PublicToolError as exc:return {"error":str(exc)}
    return {"error":"Invalid request"}
