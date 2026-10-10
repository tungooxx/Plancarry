#!/usr/bin/env python3
"""Independent CPU toy runtime to construct PlanCarry BIND G0 A/B replay evidence.

This is executable synthetic provenance, not hand-written/mirrored snapshots.
It deliberately has NO access to ALFWorld data, TextWorld, any LLM or model.
Toy-only snapshots cannot satisfy scientific G0 authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from bind_g0_ab_prefix_byte_equality import SCHEMA, structural_audit
except ModuleNotFoundError as exc:
    raise SystemExit("Install/access the pinned current PR3 checker in the same research/ path first") from exc


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class ToyPddlLike:
    instance_id: str
    seed: int
    reverse_menu: bool = False
    perturb_transition: bool = False
    scene: str = field(init=False, default="hall")
    last_observation: bytes = field(init=False, default=b"")
    steps: int = field(init=False, default=0)
    token: int = field(init=False, default=0)
    done: bool = field(init=False, default=False)
    score: int = field(init=False, default=0)
    generator: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.generator = random.Random(self.seed)
        self.scene = "hall"
        self.last_observation = b"toy hall. use look or go to desk."
        self.steps = 0
        self.done = False
        self.score = 0
        self.token = 0

    def legal_commands(self) -> list[bytes]:
        commands = [b"look", b"go to desk"] if self.scene == "hall" else [b"look", b"open drawer"]
        return list(reversed(commands)) if self.reverse_menu else commands

    def snapshot(self) -> dict[str, Any]:
        data = {"scene": self.scene, "steps": self.steps, "token": self.token,
                "done": self.done, "score": self.score}
        return {
            "full_hidden_state_b64": _b64(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()),
            "rng_state_b64": _b64(repr(self.generator.getstate()).encode()),
            "observation_b64": _b64(self.last_observation),
            "ordered_commands": [_b64(x) for x in self.legal_commands()],
            "score_b64": _b64(str(self.score).encode()),
            "done_b64": _b64(b"1" if self.done else b"0"),
        }

    def step(self, command: bytes) -> None:
        if self.done:
            raise ValueError("toy state already terminated")
        if command not in self.legal_commands():
            raise ValueError("illegal toy action " + repr(command))
        self.steps += 1
        self.token = self.generator.randrange(2 ** 20)
        if self.perturb_transition:
            self.token ^= 0x01
        if command == b"look":
            self.last_observation = ("toy " + self.scene + " scene; marker=" + str(self.token)).encode()
        elif command == b"go to desk":
            self.scene = "desk"
            self.last_observation = ("arrived toy desk; marker=" + str(self.token)).encode()
        elif command == b"open drawer":
            self.done = True
            self.score = 1
            self.last_observation = b"opened toy drawer"
        else:
            raise AssertionError("unreachable toy action")


def actual_toy_prefix(
    *, seed_a: int = 17, seed_b: int = 17,
    actions: tuple[bytes, ...] = (b"look", b"go to desk", b"open drawer"),
    reverse_menu_b: bool = False, perturb_transition_b: bool = False
) -> dict[str, Any]:
    if not actions:
        raise ValueError("Non-empty action prefix required")
    a = ToyPddlLike("independent-A", seed_a)
    b = ToyPddlLike("independent-B", seed_b, reverse_menu=reverse_menu_b,
                    perturb_transition=perturb_transition_b)
    if a is b or a.generator is b.generator:
        raise RuntimeError("Distinct toy runtime instances required")
    rows_a = [{"prefix_step": 0, "actual_action_b64": _b64(b"RESET"), "after": a.snapshot()}]
    rows_b = [{"prefix_step": 0, "actual_action_b64": _b64(b"RESET"), "after": b.snapshot()}]
    for i, command in enumerate(actions, 1):
        a.step(command)
        b.step(command)
        rows_a.append({"prefix_step": i, "actual_action_b64": _b64(command), "after": a.snapshot()})
        rows_b.append({"prefix_step": i, "actual_action_b64": _b64(command), "after": b.snapshot()})
    return {
        "schema": SCHEMA,
        "phase": "PRE_G1_SYNTHETIC_TOY",
        "source": {
            "game_sha256": _digest("toy:independent-pddl-like-reset-replay"),
            "goal_sha256": _digest("toy:open-drawer"),
            "simulator_sha256": _digest("toy:pddl-like-v1"),
            "renderer_sha256": _digest("toy:utf8-stdout"),
            "tokenizer_sha256": _digest("toy:raw-bytes"),
        },
        "backend": {
            "backend_kind": "SYNTHETIC_TOY",
            "backend_revision_sha256": _digest("ToyPddlLike:independent-transitions-v1"),
            "full_state_export_provenance": "TOY_ONLY_NOT_REAL_ATTESTATION",
            "rng_export_provenance": "TOY_ONLY_NOT_REAL_ATTESTATION",
        },
        "pair": "synthetic-independent-A-vs-B",
        "A": {"independent_instance_id": a.instance_id, "steps": rows_a},
        "B": {"independent_instance_id": b.instance_id, "steps": rows_b},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-a", type=int, default=17)
    parser.add_argument("--seed-b", type=int, default=17)
    parser.add_argument("--reverse-menu-b", action="store_true")
    parser.add_argument("--perturb-transition-b", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        trace = actual_toy_prefix(seed_a=args.seed_a, seed_b=args.seed_b,
                                  reverse_menu_b=args.reverse_menu_b,
                                  perturb_transition_b=args.perturb_transition_b)
        result = structural_audit(trace)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"scientific_gate": "NOT_AUTHORIZED", "status": "INVALID_TOY_RUNTIME", "error": str(exc)}))
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(trace, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "toy_trace_steps": len(trace["A"]["steps"]),
        "status": result["status"], "failures": result["failures"],
        "scientific_gate": result["scientific_gate"]}, sort_keys=True))
    return 0 if result["status"] == "MATCHED_SYNTHETIC_PREFIX_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
