#!/usr/bin/env python3
"""Extract ALFWorld's ORIGINAL PUBLIC task sentence from game.tw-pddl grammar.

The canonical JSON game embeds a TextWorld grammar string with intro
referencing #task# and a task rhs containing the natural-language instruction.
Never infer task instructions from source directory names, PDDL winning
condition, or privileged walkthrough. Fail closed if the public grammar
sentence is unavailable, duplicate, malformed, or not referenced by intro.
Only the exact task text returned here may enter an agent's task context.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_TASK = re.compile(r'(?s)"task"\s*:\s*\[\s*\{\s*"rhs"\s*:\s*("(?:\\.|[^"\\])*")')
_INTRO = re.compile(r'(?s)"intro"\s*:\s*\[\s*\{\s*"rhs"\s*:\s*("(?:\\.|[^"\\])*")')


def original_public_task(path: Path) -> dict:
    source = Path(path)
    raw = source.read_bytes()
    game = json.loads(raw)
    if not isinstance(game, dict):
        raise ValueError("Original ALFWorld game must be a JSON object")
    grammar = game.get("grammar")
    if not isinstance(grammar, str) or not grammar.startswith("grammar ::"):
        raise ValueError("Original TextWorld grammar missing")
    tasks = _TASK.findall(grammar)
    intros = _INTRO.findall(grammar)
    if len(tasks) != 1 or len(intros) != 1:
        raise ValueError("Original game must have exactly one public task and intro")
    task = json.loads(tasks[0])
    intro = json.loads(intros[0])
    if not isinstance(task, str) or not (
        task.startswith("Your task is to: ")
        and task.endswith(".")
        and len(task) <= 500
        and "\n" not in task
    ):
        raise ValueError("Malformed original public task sentence")
    if not isinstance(intro, str) or intro.count("#task#") != 1:
        raise ValueError("Public grammar intro does not uniquely reference task")
    if not isinstance(game.get("pddl_problem"), str):
        raise ValueError("PDDL problem missing from original game")
    # Crucial: do NOT include game['walkthrough'] or PDDL goal in public reply.
    return {
        "task_instruction": task,
        "task_instruction_sha256": hashlib.sha256(task.encode("utf-8")).hexdigest(),
        "source_game_sha256": hashlib.sha256(raw).hexdigest(),
        "provenance": "ORIGINAL_TEXTWORLD_PUBLIC_GRAMMAR_TASK_RHS",
        "is_public_intro_task": True,
    }
