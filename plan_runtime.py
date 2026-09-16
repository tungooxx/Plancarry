#!/usr/bin/env python3
"""High-level Plancraft dependency-planning runtime for PlanCarry.

Uses the official `plancraft.environment.recipes.RECIPES` objects and their
`can_craft_from_inventory` / `craft_from_inventory` methods. The abstraction
removes 3x3-grid motor control while preserving real Plancraft instances,
recipe alternatives, ingredient consumption, production counts, distractor
inventory, and smelting/crafting dependencies.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Any

from plancraft.environment.recipes import RECIPES, ShapelessRecipe, ShapedRecipe, SmeltingRecipe, id_to_item


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def aggregate_inventory(instance: dict[str, Any]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for item in instance["slotted_inventory"].values():
        c[item["type"]] += int(item["quantity"])
    return dict(sorted(c.items()))


def inventory_hash(target: str, inventory: dict[str, int], done: bool = False) -> str:
    return hashlib.sha256(stable_json({"target": target, "inventory": dict(sorted(inventory.items())), "done": bool(done)}).encode()).hexdigest()


def recipe_repr(recipe: Any) -> str:
    try:
        body = recipe.__prompt_repr__()
    except Exception:
        body = repr(recipe)
    return body.strip()


def search_recipe(name: str) -> str:
    recipes = list(RECIPES.get(name, []))
    if not recipes:
        return f"NO_RECIPE: no Plancraft recipe found for exact item '{name}'."
    lines = [f"RECIPES for exact item '{name}' ({len(recipes)} alternative(s)):"]
    for i, recipe in enumerate(recipes):
        lines.append(f"RECIPE_INDEX {i} TYPE {recipe.recipe_type} RESULT {recipe.result.count} {recipe.result.item}")
        for line in recipe_repr(recipe).splitlines():
            lines.append(f"  {line}")
    return "\n".join(lines)



def requirement_status(recipe: Any, inventory: dict[str, int]) -> tuple[list[str], list[str]]:
    """Summarize selected official recipe requirements against CURRENT inventory."""
    satisfied: list[str] = []
    missing: list[str] = []
    if isinstance(recipe, ShapelessRecipe):
        candidates=[]
        for alt in recipe.ingredients:
            miss={k:max(0,int(v)-int(inventory.get(k,0))) for k,v in alt.items()}
            miss={k:v for k,v in miss.items() if v>0}
            candidates.append(((sum(miss.values()),len(miss),stable_json(alt)),alt,miss))
        _,alt,miss=min(candidates,key=lambda x:x[0])
        for item,count in sorted(alt.items()):
            have=int(inventory.get(item,0))
            if have>=count: satisfied.append(f"{item} x{count} (have {have})")
            else: missing.append(f"{item} x{count-have} (need {count}, have {have})")
    elif isinstance(recipe, SmeltingRecipe):
        present=sorted(i for i in recipe.ingredient if inventory.get(i,0)>0)
        if present: satisfied.append(f"one_of({','.join(sorted(recipe.ingredient))}) via {present[0]} x1")
        else: missing.append(f"one_of({','.join(sorted(recipe.ingredient))}) x1")
    elif isinstance(recipe, ShapedRecipe):
        counts={k:int(v) for k,v in inventory.items()}
        cells=[]
        for row in recipe.kernel:
            for item_set in row:
                names=sorted(x for x in (id_to_item(i) for i in item_set) if x is not None)
                if names: cells.append(names)
        cells.sort(key=lambda xs:(sum(counts.get(x,0) for x in xs),len(xs),xs))
        for names in cells:
            choices=[x for x in names if counts.get(x,0)>0]
            if choices:
                pick=max(choices,key=lambda x:(counts.get(x,0),x)); counts[pick]-=1; satisfied.append(f"{pick} x1")
            else: missing.append(f"one_of({','.join(names)}) x1")
    return satisfied, missing

def craft_recipe(name: str, recipe_index: int, inventory: dict[str, int]) -> tuple[dict[str, int], str, bool]:
    recipes = list(RECIPES.get(name, []))
    if not recipes:
        return copy.deepcopy(inventory), f"ERROR NO_RECIPE: no recipe for exact item '{name}'. Search first or choose another item.", False
    if recipe_index < 0 or recipe_index >= len(recipes):
        return copy.deepcopy(inventory), f"ERROR BAD_RECIPE_INDEX: {recipe_index}; valid indices are 0..{len(recipes)-1}.", False
    recipe = recipes[recipe_index]
    before = copy.deepcopy(inventory)
    if not recipe.can_craft_from_inventory(before):
        satisfied, missing = requirement_status(recipe, before)
        sat_text = "; ".join(satisfied) if satisfied else "none"
        miss_text = "; ".join(missing) if missing else "unresolved alternative assignment"
        return before, (
            f"ERROR MISSING_INGREDIENTS: cannot execute recipe_index={recipe_index} for '{name}' from CURRENT inventory.\n"
            f"Selected official Plancraft recipe:\n{recipe_repr(recipe)}\n"
            f"ALREADY_SATISFIED: {sat_text}\n"
            f"MISSING_EXACT_PREREQUISITES: {miss_text}\n"
            "Resolve ONLY the missing prerequisite item(s), then retry this pending parent recipe."
        ), False
    after = recipe.craft_from_inventory(before)
    if after is None:
        return before, f"ERROR RECIPE_EXECUTION_FAILED for '{name}' recipe_index={recipe_index}.", False
    result = recipe.result
    return dict(sorted(after.items())), (
        f"CRAFT_OK: executed official Plancraft {recipe.recipe_type} recipe_index={recipe_index} for '{name}'. "
        f"Produced {result.count} {result.item}."
    ), True


def inventory_text(target: str, inventory: dict[str, int]) -> str:
    lines = [f"TARGET: {target}", "CURRENT INVENTORY:"]
    for item, qty in sorted(inventory.items()):
        lines.append(f"- {item}: {qty}")
    return "\n".join(lines)


@dataclass
class PlanActionRecord:
    name: str
    args: dict[str, Any]
    normalized: str
    observation: str
    state_hash: str
    success: bool
    error: str | None = None


class PlanRuntime:
    def __init__(self, instance: dict[str, Any]):
        self.instance = copy.deepcopy(instance)
        self.target = instance["target"]
        self.inventory = aggregate_inventory(instance)
        self.success = self.inventory.get(self.target, 0) > 0
        self.stopped = False

    def state_hash(self) -> str:
        return inventory_hash(self.target, self.inventory, self.success)

    def observation(self) -> str:
        return inventory_text(self.target, self.inventory)

    def execute(self, name: str, args: dict[str, Any]) -> PlanActionRecord:
        error = None
        obs = ""
        if name == "search":
            recipe_name = str(args.get("recipe_name", "")).strip()
            obs = search_recipe(recipe_name)
        elif name == "craft":
            recipe_name = str(args.get("recipe_name", "")).strip()
            try:
                recipe_index = int(args.get("recipe_index", 0))
            except Exception:
                recipe_index = 0
            new_inv, event, changed = craft_recipe(recipe_name, recipe_index, self.inventory)
            if changed:
                self.inventory = new_inv
                self.success = self.inventory.get(self.target, 0) > 0
                obs = event + "\n" + self.observation()
            else:
                error = event.splitlines()[0]
                obs = event + "\n" + self.observation()
        elif name == "impossible":
            self.stopped = True
            obs = f"STOPPED_AS_IMPOSSIBLE: {args.get('reason','')}"
        else:
            error = f"ERROR UNKNOWN_TOOL: {name}"
            obs = error + "\n" + self.observation()
        norm = stable_json({"name": name, "args": args})
        return PlanActionRecord(name, args, norm, obs, self.state_hash(), self.success, error)


def replay(instance: dict[str, Any], records: list[PlanActionRecord]) -> PlanRuntime:
    rt = PlanRuntime(instance)
    for rec in records:
        out = rt.execute(rec.name, rec.args)
        if out.state_hash != rec.state_hash:
            raise AssertionError(f"replay state mismatch after {rec.normalized}: {out.state_hash} != {rec.state_hash}")
    return rt
