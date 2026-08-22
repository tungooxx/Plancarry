#!/usr/bin/env python3
"""Restart-safe one-turn agent runner on official Plancraft recipe semantics."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from pathlib import Path
from typing import Any
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import plancarry_harness as h
import plan_runtime as p
from openai import OpenAI

MODEL='qwen2.5:7b-instruct'
BASE_URL='http://192.168.1.51:11434/v1'
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

def atomic(path:Path,obj:Any):
 path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
 try:
  with os.fdopen(fd,'w') as f: json.dump(obj,f,indent=2,ensure_ascii=False)
  os.replace(tmp,path)
 except Exception:
  try: os.unlink(tmp)
  except OSError: pass
  raise

def load_inst(iid): return next(x for x in h.load_instances() if x['id']==iid)

def init(path:Path,iid:str,model:str):
 inst=load_inst(iid); rt=p.PlanRuntime(inst)
 st={'instance_id':iid,'model':model,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':rt.observation()}], 'actions':[], 'turn':0,'done':False,'success':False,'stopped':False,'state_hash':rt.state_hash(),'usage':[]}
 atomic(path,st); print(json.dumps({'initialized':str(path),'instance_id':iid,'target':inst['target'],'state_hash':rt.state_hash()}))

def replay(st):
 inst=load_inst(st['instance_id']); recs=[p.PlanActionRecord(**x) for x in st['actions']]; return inst,p.replay(inst,recs)

def assistant_dict(msg):
 d={'role':'assistant','content':msg.content or ''}
 if msg.tool_calls:
  d['tool_calls']=[{'id':tc.id,'type':'function','function':{'name':tc.function.name,'arguments':tc.function.arguments}} for tc in msg.tool_calls]
 return d

def one_call(client,model,messages):
 r=client.chat.completions.create(model=model,messages=messages,tools=TOOLS,tool_choice='required',temperature=0,max_tokens=256)
 u={'prompt_tokens':int(getattr(r.usage,'prompt_tokens',0) or 0),'completion_tokens':int(getattr(r.usage,'completion_tokens',0) or 0),'total_tokens':int(getattr(r.usage,'total_tokens',0) or 0)}
 return r.choices[0].message,u

def step(path:Path,base_url:str):
 st=json.load(open(path)); inst,rt=replay(st)
 if st.get('done'):
  print(json.dumps({'already_done':True,'success':st['success'],'turn':st['turn']})); return
 client=OpenAI(base_url=base_url,api_key='ollama',timeout=90)
 msg=None; invalid=[]
 for attempt in range(3):
  m,u=one_call(client,st['model'],st['messages']); st['usage'].append(u)
  if m.tool_calls: msg=m; break
  invalid.append(m.content or ''); st['messages'].append({'role':'assistant','content':m.content or ''}); st['messages'].append({'role':'user','content':'ERROR: make exactly one available tool call now.'})
 if msg is None:
  st['done']=True; st['termination']='no_tool_retry_exhausted'; atomic(path,st); print(json.dumps({'done':True,'termination':st['termination'],'invalid':invalid})); return
 tc=msg.tool_calls[0]
 try: args=json.loads(tc.function.arguments or '{}')
 except Exception: args={}
 if tc.function.name=='search': args={'recipe_name':str(args.get('recipe_name','')).strip()}
 elif tc.function.name=='craft':
  try: idx=int(args.get('recipe_index',0))
  except: idx=0
  args={'recipe_name':str(args.get('recipe_name','')).strip(),'recipe_index':idx}
 elif tc.function.name=='impossible': args={'reason':str(args.get('reason',''))}
 rec=rt.execute(tc.function.name,args)
 st['messages'].append(assistant_dict(msg)); st['messages'].append({'role':'tool','tool_call_id':tc.id,'content':rec.observation})
 st['actions'].append(rec.__dict__); st['turn']+=1; st['success']=rt.success; st['stopped']=rt.stopped; st['done']=bool(rt.success or rt.stopped); st['state_hash']=rt.state_hash()
 atomic(path,st)
 print(json.dumps({'turn':st['turn'],'action':rec.normalized,'error':rec.error,'success':rt.success,'stopped':rt.stopped,'done':st['done'],'observation':rec.observation[:2400],'state_hash':st['state_hash']},ensure_ascii=False,indent=2))

def show(path):
 st=json.load(open(path)); print(json.dumps({k:v for k,v in st.items() if k not in {'messages','usage'}},indent=2,ensure_ascii=False))

ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
a=sp.add_parser('init'); a.add_argument('--state',required=True); a.add_argument('--instance-id',required=True); a.add_argument('--model',default=MODEL)
a=sp.add_parser('step'); a.add_argument('--state',required=True); a.add_argument('--base-url',default=BASE_URL)
a=sp.add_parser('show'); a.add_argument('--state',required=True)
a=ap.parse_args(); path=Path(a.state)
if a.cmd=='init': init(path,a.instance_id,a.model)
elif a.cmd=='step': step(path,a.base_url)
else: show(path)
