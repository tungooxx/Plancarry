#!/usr/bin/env python3
"""PlanCarry interruption-resumption harness.

Engineering/science separation:
- This file implements the intervention mechanics only.
- Smoke outputs are NOT scientific evidence until run through the canonical
  Research OS preregistration/execution/inspection pipeline.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import tiktoken
from openai import OpenAI
from plancraft.environment.actions import MoveAction, SmeltAction, convert_to_slot_index
from plancraft.environment.env import PlancraftEnvironment, target_and_inventory_to_text_obs
from plancraft.environment.search import gold_search_recipe

DEFAULT_DATASET = Path("/workspace/local-vlm/LLM/agent-scaling-llama-local/datasets/plancraft-test.json")
DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_BASE_URL = "http://192.168.1.51:11434/v1"
SYSTEM_PROMPT = """You are solving a Minecraft crafting task in Plancraft.
Use exactly one tool call per turn. Continue until the target item is present in a normal inventory slot.
You may search recipes. Do not invent items or slots. If a tool reports an error, inspect the new observation and change strategy.
Crafting grid slots are [A1]-[C3], output is [0], inventory is [I1]-[I36]. Never move or smelt directly into [0].
When a recipe creates an item in [0], move it from [0] to a free inventory slot to collect it.
For search, recipe_name must be a non-empty exact Minecraft item name using snake_case.
IMPORTANT: recipe search output shows the ingredients REQUIRED and the crafting-grid DESTINATION slots where those ingredients must be placed; those recipe slots do not mean the ingredient is already there. Before moving an ingredient, verify the CURRENT INVENTORY contains an item whose type string EXACTLY matches the required recipe ingredient. Related, raw, colored, wood-family, or similarly named items are NOT substitutes. If the exact required ingredient is absent, search that exact ingredient's recipe and craft/smelt it first, then return to the parent recipe.
If the observation shows any item in output slot [0], ALWAYS collect that output before doing anything else: move FROM [0] TO an empty [I#] inventory slot. Never move TO [0]. Never choose an occupied inventory slot as the destination for collecting output.
Use smelt only when the recipe actually requires smelting; ordinary crafting uses move actions into the crafting grid.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for Minecraft crafting/smelting recipes for an item.",
            "parameters": {
                "type": "object",
                "properties": {"recipe_name": {"type": "string"}},
                "required": ["recipe_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": "Move a quantity from one visible slot to another slot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slot_from": {"type": "string", "description": "e.g. [I2], [A1], [0]"},
                    "slot_to": {"type": "string", "description": "e.g. [I5], [B2]"},
                    "quantity": {"type": "integer", "minimum": 1},
                },
                "required": ["slot_from", "slot_to", "quantity"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "smelt",
            "description": "Smelt a quantity from one inventory slot and place the output in another inventory slot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slot_from": {"type": "string"},
                    "slot_to": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1},
                },
                "required": ["slot_from", "slot_to", "quantity"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "impossible",
            "description": "Stop only if the task is certainly impossible with the supplied inventory.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]

ENC = tiktoken.get_encoding("cl100k_base")


def token_count(text: str) -> int:
    return len(ENC.encode(text or ""))


def clip_tokens(text: str, budget: int) -> str:
    ids = ENC.encode(text or "")[: max(0, budget)]
    return ENC.decode(ids)


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_instances(path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    return json.loads(path.read_text())["instances"]


def clarify_recipe_text(text: str, recipe_name: str) -> str:
    """Rephrase recipe-slot lines without changing recipe content.

    Plancraft's native `item at [B2]` wording is ambiguous to small tool models;
    this makes the role of the grid coordinate explicit as a destination.
    """
    out = [f"RECIPE SEARCH for exact item: {recipe_name}"]
    for raw in (text or "").splitlines():
        line = raw.strip()
        m = re.fullmatch(r"([A-Za-z0-9_]+) at \[([ABC][123])\]", line)
        if m:
            item, slot = m.groups()
            out.append(
                f"REQUIRED exact ingredient '{item}' -> PLACE INTO crafting destination '[{slot}]'. "
                f"The destination '[{slot}]' is NOT a source inventory slot."
            )
        elif line:
            out.append(line)
    return "\n".join(out)


def inventory_hash(target: str, inventory: dict[int, dict[str, Any]], success: bool = False) -> str:
    canonical = {
        "target": target,
        "inventory": {str(k): v for k, v in sorted(inventory.items())},
        "success": bool(success),
    }
    return hashlib.sha256(stable_json(canonical).encode()).hexdigest()


def check_success(inventory: dict[int, dict[str, Any]], target: str) -> bool:
    return any(slot != 0 and item.get("type") == target and item.get("quantity", 0) > 0 for slot, item in inventory.items())


@dataclass
class ActionRecord:
    name: str
    args: dict[str, Any]
    normalized: str
    observation: str
    state_hash: str
    success: bool
    error: str | None = None


class CraftRuntime:
    def __init__(self, instance: dict[str, Any]):
        self.instance = copy.deepcopy(instance)
        self.target = instance["target"]
        inv = {int(k): copy.deepcopy(v) for k, v in instance["slotted_inventory"].items()}
        self.env = PlancraftEnvironment(inventory=inv, resolution="low")
        self.success = check_success(self.inventory, self.target)
        self.stopped = False

    @property
    def inventory(self) -> dict[int, dict[str, Any]]:
        return self.env.step()["inventory"]

    def observation(self) -> str:
        inv = self.inventory
        text = target_and_inventory_to_text_obs(self.target, inv)
        if 0 in inv and inv[0].get("quantity", 0) > 0:
            occupied = {slot for slot in inv if 10 <= slot <= 45}
            free = next((slot for slot in range(10, 46) if slot not in occupied), None)
            item = inv[0]
            out_type = item.get("type")
            if free is not None and out_type == self.target:
                # Only the actual task target receives an automatic collection hint.
                # Non-target outputs may be intended intermediates OR unrelated
                # partial-grid side recipes; deciding which requires trajectory state.
                label = f"[I{free - 9}]"
                text += (
                    f"\nACTION_HINT: output slot [0] contains the TASK TARGET {out_type} quantity {item.get('quantity')}. "
                    f"Collect it now with move(slot_from=\"[0]\", slot_to=\"{label}\", quantity={item.get('quantity')}). "
                    "Do not move anything into [0]."
                )
            elif out_type != self.target:
                text += (
                    f"\nOUTPUT_NOTE: slot [0] currently contains non-target item {out_type} quantity {item.get('quantity')}. "
                    "A partial crafting grid can create an unrelated side recipe. DO NOT collect this non-target output unless your current plan explicitly intended to craft this exact item as an intermediate. "
                    "If you are assembling a different searched recipe, leave [0] alone and continue placing that recipe's missing exact ingredients; [0] will update when the grid matches the intended recipe."
                )
        return text

    def state_hash(self) -> str:
        return inventory_hash(self.target, self.inventory, self.success)

    def execute(self, name: str, args: dict[str, Any]) -> ActionRecord:
        error = None
        try:
            if name == "search":
                obs = clarify_recipe_text(gold_search_recipe(str(args["recipe_name"])), str(args["recipe_name"]))
            elif name == "move":
                before = inventory_hash(self.target, self.inventory, self.success)
                act = MoveAction(
                    slot_from=convert_to_slot_index(str(args["slot_from"])),
                    slot_to=convert_to_slot_index(str(args["slot_to"])),
                    quantity=int(args["quantity"]),
                )
                self.env.step(act)
                self.success = check_success(self.inventory, self.target)
                after = inventory_hash(self.target, self.inventory, self.success)
                obs = self.observation()
                if after == before:
                    error = "NO_STATE_CHANGE: source may be empty, destination occupied, or move invalid"
                    obs = f"ERROR: {error}\n{obs}"
            elif name == "smelt":
                before = inventory_hash(self.target, self.inventory, self.success)
                act = SmeltAction(
                    slot_from=convert_to_slot_index(str(args["slot_from"])),
                    slot_to=convert_to_slot_index(str(args["slot_to"])),
                    quantity=int(args["quantity"]),
                )
                self.env.step(act)
                self.success = check_success(self.inventory, self.target)
                after = inventory_hash(self.target, self.inventory, self.success)
                obs = self.observation()
                if after == before:
                    error = "NO_STATE_CHANGE: source may be invalid, destination occupied, or item not smeltable"
                    obs = f"ERROR: {error}\n{obs}"
            elif name == "impossible":
                self.stopped = True
                self.success = bool(self.instance.get("impossible", False))
                obs = f"Stopped as impossible. reason={args.get('reason','')}"
            else:
                raise ValueError(f"unknown tool {name}")
        except Exception as e:  # invalid tool calls are part of agent behavior, not harness failure
            error = f"{type(e).__name__}: {e}"
            obs = f"ERROR: {error}\n{self.observation()}"
        norm = stable_json({"name": name, "args": args})
        return ActionRecord(name, args, norm, obs, self.state_hash(), self.success, error)


def replay(instance: dict[str, Any], prefix: Iterable[ActionRecord]) -> CraftRuntime:
    rt = CraftRuntime(instance)
    for rec in prefix:
        out = rt.execute(rec.name, rec.args)
        # Search calls can contain verbose recipe strings but must still reproduce the same state.
        if out.error != rec.error:
            raise AssertionError(f"replay error mismatch for {rec.normalized}: {out.error!r} != {rec.error!r}")
    return rt


def normalize_slot(value: Any) -> str:
    s = str(value or "").strip()
    if re.fullmatch(r"(?:I\d+|[ABC][123]|0)", s, flags=re.I):
        return f"[{s.upper()}]"
    return s


def _shrink_value(v: Any) -> Any:
    if isinstance(v, str):
        ids = ENC.encode(v)
        if len(ids) <= 1:
            return ""
        return ENC.decode(ids[: max(1, len(ids) // 2)])
    if isinstance(v, list):
        if len(v) > 1:
            return v[:-1]
        if len(v) == 1:
            nv = _shrink_value(v[0])
            return [nv] if nv not in ("", [], {}) else []
        return v
    if isinstance(v, dict):
        if not v:
            return v
        # Shrink the largest serialized child first, preserving keys/schema.
        key = max(v, key=lambda k: token_count(stable_json(v[k])))
        nv = dict(v)
        nv[key] = _shrink_value(nv[key])
        if nv[key] in ("", [], {}):
            nv.pop(key, None)
        return nv
    return v


def fit_json_budget(obj: dict[str, Any], budget: int) -> str:
    """Return syntactically valid compact JSON under a proxy-token budget."""
    cur = copy.deepcopy(obj)
    text = stable_json(cur)
    for _ in range(256):
        if token_count(text) <= budget:
            return text
        # Preserve intended_next_action/current_subgoal/objective longest; shrink
        # lower-priority evidence/history fields first.
        priorities = [
            "important_evidence", "unresolved_uncertainties", "rejected_or_failed_actions",
            "completed_steps", "constraints_dependencies", "objective", "current_subgoal",
            "intended_next_action",
        ]
        changed = False
        for key in priorities:
            if key in cur and cur[key] not in ("", [], {}):
                before = stable_json(cur[key])
                cur[key] = _shrink_value(cur[key])
                if stable_json(cur[key]) != before:
                    changed = True
                    break
        text = stable_json(cur)
        if not changed:
            break
    # Last-resort valid shell: never emit truncated/invalid JSON.
    shell = {"objective": str(obj.get("objective", "")), "current_subgoal": str(obj.get("current_subgoal", "")), "intended_next_action": obj.get("intended_next_action", {})}
    text = stable_json(shell)
    while token_count(text) > budget and shell:
        key = max(shell, key=lambda k: token_count(stable_json(shell[k])))
        shell[key] = _shrink_value(shell[key])
        if shell[key] in ("", [], {}): shell.pop(key, None)
        text = stable_json(shell)
    return text


def sanitize_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Normalize model tool arguments to the declared semantic schema."""
    if not isinstance(args, dict):
        args = {}
    if name == "search":
        return {"recipe_name": str(args.get("recipe_name", ""))}
    if name in {"move", "smelt"}:
        return {
            "slot_from": normalize_slot(args.get("slot_from", "")),
            "slot_to": normalize_slot(args.get("slot_to", "")),
            "quantity": int(args.get("quantity", 1)),
        }
    if name == "impossible":
        return {"reason": str(args.get("reason", ""))}
    return {}


def get_required_tool_turn(
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
    max_no_tool_retries: int = 2,
) -> tuple[Any | None, list[dict[str, int]], list[dict[str, Any]]]:
    """Request exactly one tool call, retrying bounded no-tool responses uniformly."""
    usages: list[dict[str, int]] = []
    invalid: list[dict[str, Any]] = []
    for attempt in range(max_no_tool_retries + 1):
        msg, usage = call_tool_model(client, model, messages)
        usages.append(usage)
        if msg.tool_calls:
            return msg, usages, invalid
        invalid.append({"attempt": attempt + 1, "content": msg.content or ""})
        messages.append({"role": "assistant", "content": msg.content or ""})
        if attempt < max_no_tool_retries:
            messages.append({
                "role": "user",
                "content": "ERROR: You must continue by making exactly one of the available tool calls. Do not answer with prose only.",
            })
    return None, usages, invalid


def assistant_msg_dict(msg: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return d


def call_tool_model(client: OpenAI, model: str, messages: list[dict[str, Any]], max_tokens: int = 256) -> tuple[Any, dict[str, int]]:
    r = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice="required",
        temperature=0,
        max_tokens=max_tokens,
    )
    usage = {
        "prompt_tokens": int(getattr(r.usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(r.usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(r.usage, "total_tokens", 0) or 0),
    }
    return r.choices[0].message, usage


def call_text_model(client: OpenAI, model: str, prompt: str, max_tokens: int) -> tuple[str, dict[str, int]]:
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Follow the requested compression format. Do not add commentary."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=max_tokens,
    )
    usage = {
        "prompt_tokens": int(getattr(r.usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(r.usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(r.usage, "total_tokens", 0) or 0),
    }
    return (r.choices[0].message.content or "").strip(), usage


def trace_text(prefix: list[ActionRecord]) -> str:
    parts = []
    for i, r in enumerate(prefix, 1):
        parts.append(f"STEP {i}\nACTION {r.normalized}\nOBSERVATION {r.observation}")
    return "\n\n".join(parts)


def generic_summary(client: OpenAI, model: str, instance: dict[str, Any], prefix: list[ActionRecord], budget: int) -> tuple[str, dict[str, int]]:
    trace = trace_text(prefix)
    prompt = f"""Write a concise free-form handoff for a fresh agent that must continue this unfinished task after a context reset.
Do NOT copy the trace verbatim and do NOT use a fixed JSON/schema. Preserve task-relevant progress, failures, constraints/evidence, and the likely next useful action. Use no more than about {budget} tokens.
TARGET: {instance['target']}
TRACE:\n{trace}"""
    txt, usage = call_text_model(client, model, prompt, max_tokens=max(64, budget + 32))
    return clip_tokens(txt, budget), usage


def plancarry_state(client: OpenAI, model: str, instance: dict[str, Any], prefix: list[ActionRecord], current_obs: str, budget: int) -> tuple[str, dict[str, int]]:
    trace = trace_text(prefix)
    prompt = f"""Compress this interrupted trajectory into a task-instance execution handoff for a fresh agent.
Return ONLY compact JSON with exactly these top-level keys:
objective, completed_steps, current_subgoal, constraints_dependencies, rejected_or_failed_actions, important_evidence, intended_next_action, unresolved_uncertainties.
Interpret state AFTER the FINAL trajectory observation: do not describe a subgoal as current if the final observation shows it is already completed. Preserve any pending parent goal/recipe that must be resumed after an intermediate finishes.
`intended_next_action` MUST be null or a machine-readable object of the form {{"tool":"search|craft|impossible","args":{{...}}}} using the exact tool arguments learned from the trace when available. For a pending parent retry, preserve its exact recipe_name and recipe_index rather than emitting prose such as "craft X".
Do not invent facts. Make it useful for continuing rather than retelling. Fit within about {budget} tokens.
TARGET: {instance['target']}
CURRENT OBSERVATION:\n{current_obs}
TRACE:\n{trace}"""
    txt, usage = call_text_model(client, model, prompt, max_tokens=max(96, budget + 64))
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip(), flags=re.I | re.S)
    try:
        obj = json.loads(txt)
        if not isinstance(obj, dict):
            raise ValueError("PlanCarry handoff must be a JSON object")
    except Exception:
        # A failed structured serialization is explicit and valid rather than silently
        # emitting a syntactically truncated handoff.
        obj = {
            "objective": f"Craft {instance['target']}",
            "completed_steps": [],
            "current_subgoal": "Continue from the current observation",
            "constraints_dependencies": {},
            "rejected_or_failed_actions": [],
            "important_evidence": {},
            "intended_next_action": {},
            "unresolved_uncertainties": ["model_serialization_failed"],
        }
    required = ["objective","completed_steps","current_subgoal","constraints_dependencies","rejected_or_failed_actions","important_evidence","intended_next_action","unresolved_uncertainties"]
    obj = {k: obj.get(k, [] if k in {"completed_steps","rejected_or_failed_actions","unresolved_uncertainties"} else {}) for k in required}
    if not isinstance(obj.get("objective"), str): obj["objective"] = str(obj["objective"])
    if not isinstance(obj.get("current_subgoal"), str): obj["current_subgoal"] = str(obj["current_subgoal"])
    return fit_json_budget(obj, budget), usage


def truncation_memory(prefix: list[ActionRecord], budget: int) -> str:
    ids = ENC.encode(trace_text(prefix))
    return ENC.decode(ids[-budget:]) if ids else ""


def task_messages(current_obs: str, memory: str | None = None) -> list[dict[str, Any]]:
    user = current_obs
    if memory is not None:
        user += "\n\nMEMORY FROM BEFORE THE FORCED RESET:\n" + memory
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def generate_prefix(client: OpenAI, model: str, instance: dict[str, Any], reset_after: int) -> tuple[list[ActionRecord], list[dict[str, Any]], list[dict[str, int]]]:
    rt = CraftRuntime(instance)
    messages = task_messages(rt.observation())
    prefix: list[ActionRecord] = []
    usages = []
    for _ in range(reset_after):
        msg, turn_usages, invalid = get_required_tool_turn(client, model, messages)
        usages.extend(turn_usages)
        if msg is None:
            raise RuntimeError(f"model exhausted no-tool retries before prefix action; invalid={invalid}")
        tc = msg.tool_calls[0]
        try:
            raw_args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"invalid tool JSON: {tc.function.arguments}") from e
        args = sanitize_args(tc.function.name, raw_args)
        rec = rt.execute(tc.function.name, args)
        prefix.append(rec)
        messages.append(assistant_msg_dict(msg))
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": rec.observation})
        if rt.success or rt.stopped:
            break
    return prefix, messages, usages


def qualify_successful_trace(
    client: OpenAI,
    model: str,
    instance: dict[str, Any],
    max_steps: int,
) -> tuple[list[ActionRecord], list[list[dict[str, Any]]], list[dict[str, int]]]:
    """Run uninterrupted and retain message snapshots after each semantic action."""
    rt = CraftRuntime(instance)
    messages = task_messages(rt.observation())
    actions: list[ActionRecord] = []
    snapshots: list[list[dict[str, Any]]] = []
    usages: list[dict[str, int]] = []
    for _ in range(max_steps):
        if rt.success or rt.stopped:
            break
        msg, turn_usages, invalid = get_required_tool_turn(client, model, messages)
        usages.extend(turn_usages)
        if msg is None:
            break
        tc = msg.tool_calls[0]
        try:
            raw_args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            raw_args = {}
        args = sanitize_args(tc.function.name, raw_args)
        rec = rt.execute(tc.function.name, args)
        actions.append(rec)
        messages.append(assistant_msg_dict(msg))
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": rec.observation})
        snapshots.append(copy.deepcopy(messages))
    if not rt.success:
        return [], [], usages
    return actions, snapshots, usages


def continue_arm(
    client: OpenAI,
    model: str,
    instance: dict[str, Any],
    prefix: list[ActionRecord],
    messages: list[dict[str, Any]],
    post_steps: int,
) -> dict[str, Any]:
    rt = replay(instance, prefix)
    reset_hash = rt.state_hash()
    actions: list[ActionRecord] = []
    usages: list[dict[str, int]] = []
    no_tool_turns: list[dict[str, Any]] = []
    termination_reason = "step_budget_exhausted"
    for _ in range(post_steps):
        if rt.success or rt.stopped:
            termination_reason = "success" if rt.success else "model_stopped"
            break
        msg, turn_usages, invalid = get_required_tool_turn(client, model, messages)
        usages.extend(turn_usages)
        no_tool_turns.extend(invalid)
        if msg is None:
            termination_reason = "no_tool_retry_exhausted"
            break
        tc = msg.tool_calls[0]
        try:
            raw_args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            raw_args = {}
        args = sanitize_args(tc.function.name, raw_args)
        rec = rt.execute(tc.function.name, args)
        actions.append(rec)
        messages.append(assistant_msg_dict(msg))
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": rec.observation})
    prior = {r.normalized for r in prefix}
    seen: set[str] = set()
    redundant = 0
    for r in actions:
        if r.normalized in prior or r.normalized in seen:
            redundant += 1
        seen.add(r.normalized)
    return {
        "reset_hash": reset_hash,
        "success": rt.success,
        "stopped": rt.stopped,
        "post_steps": len(actions),
        "model_turns": len(usages),
        "no_tool_turn_count": len(no_tool_turns),
        "no_tool_turns": no_tool_turns,
        "termination_reason": termination_reason,
        "first_action": actions[0].normalized if actions else None,
        "actions": [asdict(a) for a in actions],
        "redundant_or_repeated_actions": redundant,
        "final_hash": rt.state_hash(),
        "usage": usages,
    }


def choose_candidate(instances: list[dict[str, Any]], min_optimal: int = 3, max_optimal: int = 8, start: int = 0) -> dict[str, Any]:
    candidates = [x for x in instances if not x.get("impossible") and isinstance(x.get("optimal_path_length"), int) and min_optimal <= x["optimal_path_length"] <= max_optimal]
    candidates.sort(key=lambda x: (x["optimal_path_length"], x.get("id", "")))
    if start >= len(candidates):
        raise IndexError("candidate index out of range")
    return candidates[start]


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    client = OpenAI(base_url=args.base_url, api_key="ollama", timeout=args.timeout)
    instances = load_instances(Path(args.dataset))
    skipped = []
    selected = None
    prefix = None
    full_messages = None
    prefix_usage = None
    # Qualify only tasks this exact backbone can solve uninterrupted. This makes
    # the scientific question "does interruption damage a viable trajectory?" rather
    # than "can memory rescue an already-broken plan?".
    if args.instance_id:
        pool = [x for x in instances if x.get("id") == args.instance_id]
        if not pool:
            raise RuntimeError(f"unknown --instance-id {args.instance_id}")
    else:
        pool = []
        for ci in range(args.candidate_start, args.candidate_start + args.max_candidate_tries):
            try:
                pool.append(choose_candidate(instances, min_optimal=args.min_optimal, max_optimal=args.max_optimal, start=ci))
            except IndexError:
                break
    for inst in pool:
        actions, snapshots, pu = qualify_successful_trace(client, args.model, inst, args.qualify_steps)
        if len(actions) <= args.reset_after or not snapshots:
            skipped.append({"id": inst.get("id"), "reason": "uninterrupted_not_successful_or_too_short"})
            continue
        selected = inst
        prefix = actions[:args.reset_after]
        full_messages = snapshots[args.reset_after - 1]
        prefix_usage = pu
        break
    if selected is None or prefix is None or full_messages is None:
        raise RuntimeError(f"no uninterrupted-success candidate; skipped={skipped}")

    reset_rt = replay(selected, prefix)
    reset_hash = reset_rt.state_hash()
    current_obs = reset_rt.observation()

    gen_summary, summary_usage = generic_summary(client, args.model, selected, prefix, args.memory_budget)
    pc_state, pc_usage = plancarry_state(client, args.model, selected, prefix, current_obs, args.memory_budget)
    trunc = truncation_memory(prefix, args.memory_budget)

    memories = {
        "observation_only": None,
        "truncation": trunc,
        "generic_summary": gen_summary,
        "plancarry": pc_state,
    }

    arms: dict[str, Any] = {}
    # Full-history reference preserves exact pre-reset dialogue.
    arms["full_history"] = continue_arm(client, args.model, selected, prefix, copy.deepcopy(full_messages), args.post_steps)
    for name, mem in memories.items():
        rt = replay(selected, prefix)
        if rt.state_hash() != reset_hash:
            raise AssertionError(f"reset hash mismatch before arm {name}")
        arms[name] = continue_arm(client, args.model, selected, prefix, task_messages(rt.observation(), mem), args.post_steps)
        arms[name]["memory"] = mem
        arms[name]["memory_proxy_tokens"] = token_count(mem or "")

    # Invariant: every arm starts from exactly the same environment state.
    reset_hashes = {v["reset_hash"] for v in arms.values()}
    if reset_hashes != {reset_hash}:
        raise AssertionError(f"cross-arm reset hash mismatch: {reset_hashes}")

    ref_first = arms["full_history"]["first_action"]
    for name, arm in arms.items():
        arm["first_action_matches_full_history"] = arm["first_action"] == ref_first if ref_first else None
        if name != "full_history" and arm["success"] and arms["full_history"]["success"]:
            arm["extra_post_steps_vs_full_history"] = arm["post_steps"] - arms["full_history"]["post_steps"]
        else:
            arm["extra_post_steps_vs_full_history"] = None

    baseline_status_path = Path(args.baseline_status_file)
    baseline_status = baseline_status_path.read_text() if baseline_status_path.exists() else ""
    baseline_status_hash = hashlib.sha256(baseline_status.encode()).hexdigest()
    current_status = os.popen(f"cd {args.baseline_repo} && git status --porcelain=v1").read()
    current_status_hash = hashlib.sha256(current_status.encode()).hexdigest()

    out = {
        "kind": "ENGINEERING_SMOKE_NOT_SCIENTIFIC_EVIDENCE",
        "timestamp_unix": time.time(),
        "model": args.model,
        "base_url": args.base_url,
        "temperature": 0,
        "dataset": args.dataset,
        "instance_id": selected.get("id"),
        "target": selected["target"],
        "optimal_path_length_metadata": selected.get("optimal_path_length"),
        "reset_after": args.reset_after,
        "post_step_budget": args.post_steps,
        "compressed_memory_budget_proxy_tokens": args.memory_budget,
        "memory_tokenizer": "tiktoken_cl100k_base_proxy_not_llama_native",
        "prefix": [asdict(a) for a in prefix],
        "prefix_usage": prefix_usage,
        "reset_hash": reset_hash,
        "memory_generation_usage": {"generic_summary": summary_usage, "plancarry": pc_usage},
        "arms": arms,
        "skipped_candidates": skipped,
        "invariants": {
            "all_reset_hashes_identical": len(reset_hashes) == 1,
            "baseline_repo_status_unchanged": baseline_status_hash == current_status_hash,
            "baseline_status_hash_before": baseline_status_hash,
            "baseline_status_hash_after": current_status_hash,
        },
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DEFAULT_DATASET))
    ap.add_argument("--instance-id", default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--reset-after", type=int, default=3)
    ap.add_argument("--post-steps", type=int, default=8)
    ap.add_argument("--memory-budget", type=int, default=192)
    ap.add_argument("--min-optimal", type=int, default=3)
    ap.add_argument("--max-optimal", type=int, default=8)
    ap.add_argument("--qualify-steps", type=int, default=12)
    ap.add_argument("--candidate-start", type=int, default=0)
    ap.add_argument("--max-candidate-tries", type=int, default=8)
    ap.add_argument("--baseline-repo", default="/workspace/local-vlm/LLM/agent-scaling-llama-local")
    ap.add_argument("--baseline-status-file", default="/workspace/local-vlm/LLM/plancarry/baseline_repo_status.txt")
    ap.add_argument("--output", default="/workspace/local-vlm/LLM/plancarry/results/engineering_smoke.json")
    args = ap.parse_args()
    result = run_smoke(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({
        "kind": result["kind"],
        "instance_id": result["instance_id"],
        "target": result["target"],
        "reset_hash": result["reset_hash"],
        "invariants": result["invariants"],
        "arms": {k: {
            "success": v["success"],
            "post_steps": v["post_steps"],
            "first_action_matches_full_history": v["first_action_matches_full_history"],
            "redundant_or_repeated_actions": v["redundant_or_repeated_actions"],
            "memory_proxy_tokens": v.get("memory_proxy_tokens"),
        } for k,v in result["arms"].items()},
        "output": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()
