#!/usr/bin/env python3
"""Frozen Goal-Directed Action Agreement (GDAA) scorer for PlanCarry ALFWorld.

The scorer is deliberately limited to visible task text and reset admissible
commands. It never reads expert plans, future suffixes, rewards, or hidden facts.
"""
from __future__ import annotations

import re
from typing import Iterable

INFORMATION_EXACT = {"inventory", "look", "help"}


def is_information_command(command: str) -> bool:
    c = (command or "").strip().lower()
    return c in INFORMATION_EXACT or c.startswith("examine ")


def normalize_entity_type(text: str) -> str:
    """Normalize ALFWorld entity display text to an exact comparable type."""
    s = (text or "").strip().lower().rstrip(".!?")
    s = re.sub(r"\s+\d+$", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def parse_pick_place_goal(goal_text: str) -> tuple[str, str] | None:
    """Parse visible `put ... OBJECT on|in DESTINATION` task text."""
    text = (goal_text or "").strip().lower()
    # Accept a full initial observation containing `Your task is to:` as well
    # as the already-extracted task sentence.
    m_task = re.search(r"your task is to:\s*(.+?)(?:\n|$)", text, re.I)
    if m_task:
        text = m_task.group(1).strip()
    m = re.match(
        r"^put\s+(?:some\s+|a\s+|an\s+)?(.+?)\s+(?:on|in)\s+(.+?)[.!]?$",
        text,
        re.I,
    )
    if not m:
        return None
    obj = normalize_entity_type(m.group(1))
    dest = normalize_entity_type(m.group(2))
    if not obj or not dest:
        return None
    return obj, dest


def direct_goal_action_set(goal_text: str, admissible_commands: Iterable[str]) -> set[str] | None:
    """Return exact-type direct goal-advancing reset commands, or None if undefined."""
    parsed = parse_pick_place_goal(goal_text)
    if parsed is None:
        return None
    goal_obj, goal_dest = parsed
    positive: set[str] = set()
    for raw in admissible_commands:
        cmd = str(raw).strip()
        mg = re.match(r"^go to\s+(.+)$", cmd, re.I)
        if mg and normalize_entity_type(mg.group(1)) == goal_dest:
            positive.add(cmd)
            continue
        mm = re.match(r"^move\s+(.+?)\s+to\s+(.+)$", cmd, re.I)
        if mm:
            obj_t = normalize_entity_type(mm.group(1))
            dest_t = normalize_entity_type(mm.group(2))
            if obj_t == goal_obj and dest_t == goal_dest:
                positive.add(cmd)
    return positive if positive else None


def gdaa_score(
    first_progress_action: str | None,
    goal_text: str,
    admissible_commands: Iterable[str],
) -> bool | None:
    """Score first non-information action; undefined scorer remains None."""
    positive = direct_goal_action_set(goal_text, admissible_commands)
    if positive is None:
        return None
    if first_progress_action is None:
        return False
    return str(first_progress_action).strip() in positive


def frozen_sentinels() -> dict[str, bool]:
    """Hand-scripted construct guards frozen before scientific execution."""
    return {
        "toilet_not_toiletpaperhanger": direct_goal_action_set(
            "put some tissuebox on toilet.",
            ["go to toiletpaperhanger 1", "go to toilet 1"],
        ) == {"go to toilet 1"},
        "sofa_direct_navigation_positive": gdaa_score(
            "go to sofa 2",
            "put some remotecontrol on sofa.",
            ["go to sofa 1", "go to sofa 2", "go to shelf 1"],
        ) is True,
        "direct_placement_positive": gdaa_score(
            "move toiletpaper 2 to toiletpaperhanger 1",
            "put some toiletpaper on toiletpaperhanger.",
            ["move toiletpaper 2 to toiletpaperhanger 1", "go to toilet 1"],
        ) is True,
        "wrong_receptacle_negative": gdaa_score(
            "move remotecontrol 1 to shelf 2",
            "put some remotecontrol on sofa.",
            ["move remotecontrol 1 to shelf 2", "go to sofa 1"],
        ) is False,
        "non_target_navigation_negative": gdaa_score(
            "go to diningtable 1",
            "put some bowl on coffeetable.",
            ["go to diningtable 1", "go to coffeetable 1"],
        ) is False,
        "unparseable_is_undefined": direct_goal_action_set(
            "do something ambiguous", ["go to desk 1"]
        ) is None,
        "no_exact_target_is_undefined": direct_goal_action_set(
            "put some bowl on coffeetable.", ["go to diningtable 1"]
        ) is None,
    }
