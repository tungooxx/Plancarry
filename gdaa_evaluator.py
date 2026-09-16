"""Pure route-independent ALFWorld continuation evaluator.

GDAA is intentionally outcome-blind: it uses only the visible task text,
the reset-state admissible-command set, and the evaluated arm's actions.
It does not accept a reference suffix, expert plan, reward, or terminal success.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_INFO_EXACT = {"inventory", "look", "help"}


def normalize_entity_type(text: str) -> str:
    """Normalize an ALFWorld entity instance/type for exact type comparison."""
    value = text.strip().lower().rstrip(".!?")
    value = re.sub(r"\s+\d+$", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def _visible_task_text(initial_observation_or_task: str) -> str:
    match = re.search(
        r"Your task is to:\s*(.+?)(?:\n|$)", initial_observation_or_task, re.IGNORECASE
    )
    return (match.group(1) if match else initial_observation_or_task).strip()


def parse_pick_and_place_goal(initial_observation_or_task: str) -> tuple[str, str] | None:
    """Return normalized (object_type, destination_type), or None if out of scope."""
    task = _visible_task_text(initial_observation_or_task)
    match = re.match(
        r"^put\s+(?:some\s+|a\s+|an\s+)?(.+?)\s+(?:on|in)\s+(.+?)[.!?]?$",
        task,
        re.IGNORECASE,
    )
    if not match:
        return None
    obj = normalize_entity_type(match.group(1))
    dest = normalize_entity_type(match.group(2))
    return (obj, dest) if obj and dest else None


def is_information_command(command: str) -> bool:
    command = command.strip().lower()
    return command in _INFO_EXACT or command.startswith("examine ")


def first_progress_action(actions: Iterable[str | Mapping[str, object]]) -> str | None:
    """Use the existing frozen semantics: skip look/help/inventory/examine only."""
    for item in actions:
        command = str(item.get("command", "")) if isinstance(item, Mapping) else str(item)
        if command and not is_information_command(command):
            return command
    return None


def goal_directed_action_set(
    initial_observation_or_task: str, reset_admissible_commands: Iterable[str]
) -> frozenset[str] | None:
    """Return direct goal-advancing reset actions, or None when GDAA is undefined."""
    goal = parse_pick_and_place_goal(initial_observation_or_task)
    if goal is None:
        return None
    goal_obj, goal_dest = goal
    positive: set[str] = set()
    for raw in reset_admissible_commands:
        command = str(raw).strip()
        go = re.match(r"^go\s+to\s+(.+)$", command, re.IGNORECASE)
        if go and normalize_entity_type(go.group(1)) == goal_dest:
            positive.add(command)
            continue
        move = re.match(r"^move\s+(.+?)\s+to\s+(.+)$", command, re.IGNORECASE)
        if move:
            moved_obj = normalize_entity_type(move.group(1))
            moved_dest = normalize_entity_type(move.group(2))
            if moved_obj == goal_obj and moved_dest == goal_dest:
                positive.add(command)
    return frozenset(positive) if positive else None


def gdaa_score(
    initial_observation_or_task: str,
    reset_admissible_commands: Iterable[str],
    actions: Iterable[str | Mapping[str, object]],
) -> bool | None:
    """Score first non-information action against the direct goal-action set.

    None means the evaluator is undefined for this reset (unparseable goal or
    no exact-type direct target action in the reset admissible-command set).
    """
    positive = goal_directed_action_set(initial_observation_or_task, reset_admissible_commands)
    if positive is None:
        return None
    first = first_progress_action(actions)
    return False if first is None else first in positive
