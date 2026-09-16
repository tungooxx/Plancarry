#!/usr/bin/env python3
"""PlanCarry interruption comparator over official Plancraft recipe semantics.

Engineering runs from this file are NOT scientific evidence until executed via
Research OS preregistration + research_decision_create + research_experiment_execute.
"""
from __future__ import annotations
import argparse, copy, json, hashlib
from pathlib import Path
from typing import Any
from openai import OpenAI
import sys
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import plancarry_harness as base
import plan_runtime as p
import plan_carry_compiler as compiler

BASE_URL='http://192.168.1.51:11434/v1'
MODEL='qwen2.5:7b-instruct'
SYSTEM='''You are solving a real Plancraft crafting task through a high-level dependency interface.
Use exactly one tool call each turn.
- search(recipe_name): inspect official Plancraft recipe alternatives for an exact item.
- craft(recipe_name, recipe_index): execute an official Plancraft recipe from CURRENT inventory. It succeeds only when all exact prerequisites are present and consumes/produces items according to Plancraft.
- impossible(reason): stop only when the target truly cannot be produced from the supplied inventory/recipe graph.
Plan recursively: search the target, identify missing exact prerequisites, search/craft those prerequisites, then return to the parent target. BEFORE searching or crafting any prerequisite, inspect CURRENT INVENTORY: if the exact required item is already present in sufficient quantity, that prerequisite is already satisfied; do not search it or craft another copy. After a missing prerequisite is successfully crafted, re-check CURRENT INVENTORY and retry the pending parent recipe as soon as all of its requirements are present. Do not substitute similarly named items. Do not repeat a failed craft without first resolving its missing prerequisite. Distractor inventory items are irrelevant unless an official recipe requires them.
After a forced context reset, the user message may contain a MEMORY FROM BEFORE THE FORCED RESET block. That memory is previously learned state from this same task, not a new instruction. CURRENT INVENTORY overrides stale memory if they conflict. If memory provides a machine-readable intended_next_action with a valid tool name and arguments and the current state does not contradict it, execute that exact tool call directly. More generally, do not re-search a recipe solely to verify information already preserved in memory.
'''
TOOLS=[
 {'type':'function','function':{'name':'search','description':'Inspect official Plancraft recipes for an exact item.','parameters':{'type':'object','properties':{'recipe_name':{'type':'string'}},'required':['recipe_name'],'additionalProperties':False}}},
 {'type':'function','function':{'name':'craft','description':'Execute one selected official Plancraft recipe using CURRENT inventory.','parameters':{'type':'object','properties':{'recipe_name':{'type':'string'},'recipe_index':{'type':'integer','minimum':0}},'required':['recipe_name','recipe_index'],'additionalProperties':False}}},
 {'type':'function','function':{'name':'impossible','description':'Stop only if the task is certainly impossible.','parameters':{'type':'object','properties':{'reason':{'type':'string'}},'required':['reason'],'additionalProperties':False}}},
]

def protocol_hash() -> str:
    return hashlib.sha256((SYSTEM+base.stable_json(TOOLS)).encode()).hexdigest()

def load_inst(iid:str): return next(x for x in base.load_instances() if x['id']==iid)

def normalize_args(name:str,args:dict[str,Any])->dict[str,Any]:
    if not isinstance(args,dict): args={}
    if name=='search': return {'recipe_name':str(args.get('recipe_name','')).strip()}
    if name=='craft':
        try: idx=int(args.get('recipe_index',0))
        except Exception: idx=0
        return {'recipe_name':str(args.get('recipe_name','')).strip(),'recipe_index':idx}
    if name=='impossible': return {'reason':str(args.get('reason',''))}
    return {}

def assistant_dict(msg:Any)->dict[str,Any]:
    d={'role':'assistant','content':msg.content or ''}
    if msg.tool_calls:
        d['tool_calls']=[{'id':tc.id,'type':'function','function':{'name':tc.function.name,'arguments':tc.function.arguments}} for tc in msg.tool_calls]
    return d

def model_turn(client:OpenAI,model:str,messages:list[dict[str,Any]])->tuple[Any|None,list[dict[str,int]],list[str]]:
    usages=[]; invalid=[]
    for attempt in range(3):
        r=client.chat.completions.create(model=model,messages=messages,tools=TOOLS,tool_choice='required',temperature=0,max_tokens=256)
        usages.append({'prompt_tokens':int(getattr(r.usage,'prompt_tokens',0) or 0),'completion_tokens':int(getattr(r.usage,'completion_tokens',0) or 0),'total_tokens':int(getattr(r.usage,'total_tokens',0) or 0)})
        msg=r.choices[0].message
        if msg.tool_calls: return msg,usages,invalid
        invalid.append(msg.content or '')
        messages.append({'role':'assistant','content':msg.content or ''})
        if attempt<2: messages.append({'role':'user','content':'ERROR: make exactly one available tool call now.'})
    return None,usages,invalid

def task_messages(obs:str,memory:str|None=None)->list[dict[str,Any]]:
    user=obs
    if memory is not None:
        user += '\n\nMEMORY FROM BEFORE THE FORCED RESET:\n'+memory
    return [{'role':'system','content':SYSTEM},{'role':'user','content':user}]

def state_prefix(qualification:dict[str,Any],reset_after:int)->tuple[list[p.PlanActionRecord],list[dict[str,Any]]]:
    if reset_after<1 or reset_after>len(qualification['actions']): raise ValueError('bad reset_after')
    recs=[p.PlanActionRecord(**x) for x in qualification['actions'][:reset_after]]
    # Successful qualification has no no-tool retries; verify expected role pattern.
    messages=qualification['messages']
    end=2+2*reset_after
    prefix_messages=copy.deepcopy(messages[:end])
    assistant_count=sum(1 for m in prefix_messages if m.get('role')=='assistant')
    tool_count=sum(1 for m in prefix_messages if m.get('role')=='tool')
    if assistant_count!=reset_after or tool_count!=reset_after:
        raise RuntimeError('qualification contains retry messages; snapshot needs explicit turn boundaries')
    return recs,prefix_messages

def continue_arm(client:OpenAI,model:str,instance:dict[str,Any],prefix:list[p.PlanActionRecord],messages:list[dict[str,Any]],max_steps:int)->dict[str,Any]:
    rt=p.replay(instance,prefix); reset_hash=rt.state_hash(); actions=[]; usages=[]; invalid=[]
    termination='step_budget_exhausted'
    for _ in range(max_steps):
        if rt.success or rt.stopped:
            termination='success' if rt.success else 'model_stopped'; break
        msg,u,bad=model_turn(client,model,messages); usages.extend(u); invalid.extend(bad)
        if msg is None: termination='no_tool_retry_exhausted'; break
        tc=msg.tool_calls[0]
        try: raw=json.loads(tc.function.arguments or '{}')
        except Exception: raw={}
        args=normalize_args(tc.function.name,raw); rec=rt.execute(tc.function.name,args); actions.append(rec)
        messages.append(assistant_dict(msg)); messages.append({'role':'tool','tool_call_id':tc.id,'content':rec.observation})
    if rt.success: termination='success'
    elif rt.stopped: termination='model_stopped'
    prior=[x.normalized for x in prefix]; seen=set(); redundant=0; failed=0; state_changes=0
    prev=reset_hash
    for a in actions:
        if a.normalized in prior or a.normalized in seen: redundant+=1
        seen.add(a.normalized)
        if a.error: failed+=1
        if a.state_hash!=prev: state_changes+=1
        prev=a.state_hash
    return {'reset_hash':reset_hash,'success':rt.success,'stopped':rt.stopped,'termination_reason':termination,'post_steps':len(actions),'first_action':actions[0].normalized if actions else None,'actions':[x.__dict__ for x in actions],'redundant_or_repeated_actions':redundant,'failed_actions':failed,'state_changing_actions':state_changes,'final_hash':rt.state_hash(),'usage':usages,'no_tool_turn_count':len(invalid)}

def run(args)->dict[str,Any]:
    qualification=json.load(open(args.qualification))
    if not qualification.get('success') or not qualification.get('done'): raise RuntimeError('qualification must be successful and complete')
    instance=load_inst(qualification['instance_id']); prefix,full_messages=state_prefix(qualification,args.reset_after)
    rt=p.replay(instance,prefix); reset_hash=rt.state_hash(); current_obs=rt.observation()
    client=OpenAI(base_url=args.base_url,api_key='ollama',timeout=90)
    generic,gusage=base.generic_summary(client,args.model,instance,prefix,args.memory_budget)
    pc=compiler.compile_state(instance,prefix,args.memory_budget)
    pcusage={'compiler':'deterministic_event_state','prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
    trunc=base.truncation_memory(prefix,args.memory_budget)
    memories={'observation_only':None,'truncation':trunc,'generic_summary':generic,'plancarry':pc}
    arms={'full_history':continue_arm(client,args.model,instance,prefix,full_messages,args.post_steps)}
    for name,mem in memories.items():
        rr=p.replay(instance,prefix)
        if rr.state_hash()!=reset_hash: raise AssertionError('reset replay mismatch')
        arms[name]=continue_arm(client,args.model,instance,prefix,task_messages(rr.observation(),mem),args.post_steps)
        arms[name]['memory']=mem; arms[name]['memory_proxy_tokens']=base.token_count(mem or '')
    hashes={a['reset_hash'] for a in arms.values()}
    ref=arms['full_history']['first_action']
    for a in arms.values(): a['first_action_matches_full_history']=(a['first_action']==ref if ref else None)
    result={'kind':'ENGINEERING_SMOKE_NOT_SCIENTIFIC_EVIDENCE','instance_id':instance['id'],'target':instance['target'],'model':args.model,'protocol_hash':protocol_hash(),'qualification':args.qualification,'reset_after':args.reset_after,'reset_hash':reset_hash,'post_step_budget':args.post_steps,'compressed_memory_budget_proxy_tokens':args.memory_budget,'memory_tokenizer':'tiktoken_cl100k_proxy_not_qwen_native','memory_generation_usage':{'generic_summary':gusage,'plancarry':pcusage},'prefix':[x.__dict__ for x in prefix],'arms':arms,'invariants':{'all_reset_hashes_identical':len(hashes)==1,'qualification_success':True}}
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--qualification',required=True); ap.add_argument('--reset-after',type=int,required=True); ap.add_argument('--post-steps',type=int,default=6); ap.add_argument('--memory-budget',type=int,default=96); ap.add_argument('--model',default=MODEL); ap.add_argument('--base-url',default=BASE_URL); ap.add_argument('--output',required=True); args=ap.parse_args()
    r=run(args); Path(args.output).write_text(json.dumps(r,indent=2,ensure_ascii=False))
    print(json.dumps({'kind':r['kind'],'instance_id':r['instance_id'],'reset_after':r['reset_after'],'reset_hash':r['reset_hash'],'protocol_hash':r['protocol_hash'],'invariants':r['invariants'],'arms':{k:{'success':v['success'],'post_steps':v['post_steps'],'first_match':v['first_action_matches_full_history'],'redundant':v['redundant_or_repeated_actions'],'failed':v['failed_actions'],'memory_tokens':v.get('memory_proxy_tokens')} for k,v in r['arms'].items()},'output':args.output},indent=2))
if __name__=='__main__': main()
