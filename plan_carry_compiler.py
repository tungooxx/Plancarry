#!/usr/bin/env python3
"""Deterministic PlanCarry compiler for the Plancraft dependency runtime.

This compiler does not ask an LLM to retell the trajectory. It derives a
compact continuation state from observed tool events and CURRENT environment
state. Recipe details are only used for a recipe that was already exposed or
attempted in the observed trace.
"""
from __future__ import annotations
import json, re
from typing import Any
import plan_runtime as p
import plancarry_harness as base


def _missing_exact_items(lines:list[str])->list[str]:
    out=[]
    for line in lines:
        # requirement_status emits e.g. sugar x1 (need 1, have 0)
        m=re.match(r"^([a-z0-9_]+) x(\d+)",line)
        if m: out.append(m.group(1))
    return out


def compile_state(instance:dict[str,Any], prefix:list[p.PlanActionRecord], budget:int=96)->str:
    rt=p.replay(instance,prefix)
    searched=[]
    successful_crafts=[]
    failed_crafts=[]
    for i,rec in enumerate(prefix):
        if rec.name=='search':
            name=str(rec.args.get('recipe_name',''))
            if name and name not in searched: searched.append(name)
        elif rec.name=='craft':
            frame={'step':i+1,'recipe_name':str(rec.args.get('recipe_name','')),'recipe_index':int(rec.args.get('recipe_index',0)),'error':rec.error}
            if rec.error: failed_crafts.append(frame)
            else: successful_crafts.append(frame)

    pending=[]
    intended=None
    current_subgoal='Re-evaluate target from current state'
    # A failed craft remains a pending parent until its result exists or a later
    # successful execution of that exact recipe occurs.
    for f in failed_crafts:
        name=f['recipe_name']; idx=f['recipe_index']
        later_success=any(s['step']>f['step'] and s['recipe_name']==name and s['recipe_index']==idx for s in successful_crafts)
        if later_success: continue
        recipes=list(p.RECIPES.get(name,[]))
        if idx<0 or idx>=len(recipes): continue
        recipe=recipes[idx]
        sat,miss=p.requirement_status(recipe,rt.inventory)
        frame={'parent_action':{'tool':'craft','args':{'recipe_name':name,'recipe_index':idx}},'satisfied_now':sat,'missing_now':miss,'status':'ready_to_retry' if recipe.can_craft_from_inventory(rt.inventory) else 'blocked'}
        pending.append(frame)

    if pending:
        parent=pending[-1]
        if parent['status']=='ready_to_retry':
            intended=parent['parent_action']
            current_subgoal=f"Resume pending parent recipe {intended['args']['recipe_name']}"
        else:
            missing_items=_missing_exact_items(parent['missing_now'])
            if missing_items:
                item=missing_items[0]
                if item not in searched:
                    intended={'tool':'search','args':{'recipe_name':item}}
                    current_subgoal=f"Find recipe for missing prerequisite {item}"
                else:
                    # Search was observed, so choosing a craftable recipe index does
                    # not introduce unobserved recipe knowledge.
                    craftable=[]
                    for idx,r in enumerate(p.RECIPES.get(item,[])):
                        if r.can_craft_from_inventory(rt.inventory): craftable.append(idx)
                    if craftable:
                        intended={'tool':'craft','args':{'recipe_name':item,'recipe_index':craftable[0]}}
                        current_subgoal=f"Craft missing prerequisite {item}"
                    else:
                        intended={'tool':'search','args':{'recipe_name':item}}
                        current_subgoal=f"Resolve missing prerequisite {item}"
    elif not rt.success:
        # If there is no pending failed parent, preserve the most recently
        # searched target/subgoal as evidence but do not invent a recipe action.
        item=searched[-1] if searched else instance['target']
        intended={'tool':'search','args':{'recipe_name':item}}
        current_subgoal=f"Continue planning for {item}"

    state={
        'objective':instance['target'],
        'completed_steps':[{'tool':'craft','args':{'recipe_name':s['recipe_name'],'recipe_index':s['recipe_index']}} for s in successful_crafts],
        'current_subgoal':current_subgoal,
        'constraints_dependencies':pending,
        'rejected_or_failed_actions':[{'tool':'craft','args':{'recipe_name':f['recipe_name'],'recipe_index':f['recipe_index']},'status':'pending_or_failed'} for f in failed_crafts],
        'important_evidence':{'searched_recipes':searched,'current_state_hash':rt.state_hash()},
        'intended_next_action':intended,
        'unresolved_uncertainties':[],
    }
    return base.fit_json_budget(state,budget)
