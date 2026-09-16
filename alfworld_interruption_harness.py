#!/usr/bin/env python3
"""Five-arm PlanCarry engineering comparator on official ALFWorld TextWorld.

This is engineering validation only until a prospective Research OS experiment
is preregistered and executed through research_experiment_execute.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, re, sys
from pathlib import Path
from typing import Any

import tiktoken
from openai import OpenAI

sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import alfworld_runtime as a
import alfworld_qualify as q

BASE_URL=q.BASE_URL
MODEL=q.MODEL
ENC=tiktoken.get_encoding('cl100k_base')


def token_count(text:str)->int: return len(ENC.encode(text or ''))

def clip_tail(text:str,budget:int)->str:
    ids=ENC.encode(text or '')
    return ENC.decode(ids[-budget:]) if budget>0 else ''

def fit_json_budget(obj:dict[str,Any],budget:int)->str:
    """Return valid JSON within budget by degrading low-priority detail only."""
    def dump(x): return json.dumps(x,ensure_ascii=False,separators=(',',':'))
    work=copy.deepcopy(obj)
    if token_count(dump(work))<=budget: return dump(work)
    # Remove verbose evidence first, but preserve objective/subgoal/next action.
    for key in ['unresolved_uncertainties','rejected_or_failed_actions','important_evidence','completed_steps','constraints_dependencies']:
        if key in work:
            if isinstance(work[key],list): work[key]=work[key][-1:]
            elif isinstance(work[key],dict): work[key]={}
        if token_count(dump(work))<=budget: return dump(work)
    # Compress strings while retaining machine-readable next action.
    for key in ['current_subgoal','objective']:
        if isinstance(work.get(key),str) and len(work[key])>64: work[key]=work[key][:64]
        if token_count(dump(work))<=budget: return dump(work)
    # Minimal schema fallback; still valid JSON.
    mini={k:work.get(k) for k in ['objective','current_subgoal','intended_next_action']}
    text=dump(mini)
    if token_count(text)>budget:
        mini['current_subgoal']='continue objective'
        text=dump(mini)
    if token_count(text)>budget:
        # Last fallback preserves objective; intended action may be removed if needed.
        mini={'objective':str(work.get('objective',''))[:80]}
        text=dump(mini)
    if token_count(text)>budget: raise ValueError(f'memory budget {budget} too small for minimal valid state')
    return text


def qualification_prefix(d:dict[str,Any], reset_after:int):
    if not d.get('success'): raise ValueError('qualification must be successful')
    if reset_after<1 or reset_after>=len(d['actions']): raise ValueError('reset must be before successful terminal action')
    records=[a.AlfActionRecord(**x) for x in d['actions'][:reset_after]]
    # qualification has exactly assistant/tool per successful env action; no invalid turns in accepted smoke.
    if d.get('invalid_model_turns',0)!=0: raise ValueError('qualification with invalid model turns is not accepted')
    prefix_messages=copy.deepcopy(d['messages'][:2+2*reset_after])
    return records,prefix_messages


def trace_text(d:dict[str,Any],reset_after:int)->str:
    parts=['INITIAL TASK OBSERVATION:\n'+d['initial_observation']]
    for i,x in enumerate(d['actions'][:reset_after],1):
        parts.append(f"STEP {i}\nACTION: {x['command']}\nOBSERVATION: {x['observation']}")
    return '\n\n'.join(parts)


def generic_summary(client:OpenAI,model:str,d:dict[str,Any],reset_after:int,budget:int):
    prompt=f'''Summarize the interrupted ALFWorld trajectory for a fresh agent that must continue the same unfinished task after a context reset. Preserve whatever information is most useful. Do not prescribe a schema. Keep the summary within about {budget} tokens.\n\n{trace_text(d,reset_after)}'''
    r=client.chat.completions.create(model=model,messages=[{'role':'system','content':'Compress the prior task trajectory faithfully. Do not invent facts.'},{'role':'user','content':prompt}],temperature=0,max_tokens=max(64,budget+32))
    text=(r.choices[0].message.content or '').strip()
    ids=ENC.encode(text)[:budget]
    return ENC.decode(ids), {'prompt_tokens':int(getattr(r.usage,'prompt_tokens',0) or 0),'completion_tokens':int(getattr(r.usage,'completion_tokens',0) or 0),'total_tokens':int(getattr(r.usage,'total_tokens',0) or 0)}


def parse_goal(initial_obs:str)->str:
    m=re.search(r'Your task is to:\s*(.+?)(?:\n|$)',initial_obs,re.I)
    return m.group(1).strip() if m else initial_obs.strip().splitlines()[-1]


def compile_plancarry(d:dict[str,Any],reset_after:int,budget:int)->str:
    """Compile only facts present in the observed prefix; never use future actions."""
    prefix=d['actions'][:reset_after]
    objective=parse_goal(d['initial_observation'])
    completed=[x['command'] for x in prefix]
    failures=[x['command'] for x in prefix if x.get('error')]
    last_obs=prefix[-1]['observation'] if prefix else d['initial_observation']
    goal_lower=objective.lower()
    intended=None
    subgoal='continue the unfinished task'
    evidence={'last_observation':last_obs}
    # Generic ALFWorld pick/place extraction from the task and observed prefix.
    # This uses only visible task text + visible actions/observations.
    obj_match=re.search(r'put (?:some |a |an )?(.+?) (?:on|in) (.+?)(?:\.|$)',goal_lower)
    if obj_match:
        obj=obj_match.group(1).strip(); dest=obj_match.group(2).strip()
        take=[x['command'] for x in prefix if x['command'].startswith('take ') and obj in x['command'].lower()]
        if take:
            # Resolve a numbered destination only if it was explicitly visited in the prefix.
            visited=[x['command'][len('go to '):] for x in prefix if x['command'].startswith('go to ') and dest in x['command'].lower()]
            if visited:
                target=visited[-1]
                intended=f'go to {target}'
                subgoal=f'deliver held {obj} to {target}'
                evidence={'held_object':obj,'destination':target,'last_observation':last_obs}
            else:
                subgoal=f'find destination {dest} while holding {obj}'
        else:
            subgoal=f'find and take {obj}, then deliver it to {dest}'
    state={
        'objective':objective,
        'completed_steps':completed,
        'current_subgoal':subgoal,
        'constraints_dependencies':[],
        'rejected_or_failed_actions':failures,
        'important_evidence':evidence,
        'intended_next_action':intended,
        'unresolved_uncertainties':[],
    }
    return fit_json_budget(state,budget)


def truncated_memory(d:dict[str,Any],reset_after:int,budget:int)->str:
    return clip_tail(trace_text(d,reset_after),budget)


def fresh_messages(obs:str,commands:list[str],memory:str|None)->list[dict[str,Any]]:
    user=q.surface(obs,commands)
    if memory is not None:
        user += '\n\nMEMORY FROM BEFORE THE FORCED RESET:\n'+memory
    return [{'role':'system','content':q.SYSTEM},{'role':'user','content':user}]


def is_information_command(command:str)->bool:
    c=command.strip().lower()
    return c in {'inventory','look','help'} or c.startswith('examine ')

def first_progress_action(actions:list[dict[str,Any]]|list[a.AlfActionRecord])->str|None:
    for x in actions:
        cmd=x.command if hasattr(x,'command') else str(x.get('command',''))
        if not is_information_command(cmd): return cmd
    return None

def consecutive_repeat_count(actions:list[a.AlfActionRecord])->int:
    return sum(1 for i in range(1,len(actions)) if actions[i].command==actions[i-1].command)

def prefix_reversal_count(prefix:list[a.AlfActionRecord],actions:list[a.AlfActionRecord])->int:
    """Count simple object-placement reversals of already-completed prefix progress."""
    taken=[]; placed=[]
    for x in prefix:
        m=re.match(r'^take (.+?) from (.+)$',x.command,re.I)
        if m: taken.append((m.group(1).lower(),m.group(2).lower()))
        m=re.match(r'^move (.+?) to (.+)$',x.command,re.I)
        if m: placed.append((m.group(1).lower(),m.group(2).lower()))
    n=0
    for x in actions:
        m=re.match(r'^move (.+?) to (.+)$',x.command,re.I)
        if m and (m.group(1).lower(),m.group(2).lower()) in taken: n+=1
        m=re.match(r'^take (.+?) from (.+)$',x.command,re.I)
        if m and (m.group(1).lower(),m.group(2).lower()) in placed: n+=1
    return n


def continue_arm(client:OpenAI,model:str,game_file:str,prefix:list[a.AlfActionRecord],messages:list[dict[str,Any]],post_steps:int)->dict[str,Any]:
    rt=a.replay(game_file,prefix,max_steps=max(50,len(prefix)+post_steps+5))
    reset_hash=rt.hash(); actions=[]; usage=[]; invalid=0
    termination='step_budget_exhausted'
    try:
        for _ in range(post_steps):
            if rt.won or rt.done:
                termination='success' if rt.won else 'env_done'; break
            msg,u=q.call(client,model,messages); usage.append(u)
            if not msg.tool_calls:
                invalid+=1; messages.append({'role':'assistant','content':msg.content or ''}); messages.append({'role':'user','content':'You must call choose_action with one valid index.'}); continue
            tc=msg.tool_calls[0]
            try: idx=int(json.loads(tc.function.arguments or '{}').get('index',-1))
            except Exception: idx=-1
            messages.append(q.assistant_dict(msg))
            if idx<0 or idx>=len(rt.admissible_commands):
                invalid+=1
                messages.append({'role':'tool','tool_call_id':tc.id,'content':q.surface(f'INVALID INDEX {idx}; state unchanged.',rt.admissible_commands)})
                continue
            command=rt.admissible_commands[idx]
            rec=rt.step(command); actions.append(rec)
            messages.append({'role':'tool','tool_call_id':tc.id,'content':q.surface(rec.observation,rec.admissible_commands)})
        if rt.won: termination='success'
        elif rt.done: termination='env_done'
        return {'reset_hash':reset_hash,'success':bool(rt.won),'done':bool(rt.done),'score':float(rt.score),'termination_reason':termination,
                'post_steps':len(actions),'first_action':actions[0].command if actions else None,'first_progress_action':first_progress_action(actions),
                'actions':[x.__dict__ for x in actions],
                'consecutive_repeat_count':consecutive_repeat_count(actions),'prefix_reversal_count':prefix_reversal_count(prefix,actions),
                'invalid_model_turns':invalid,'final_hash':rt.hash(),'usage':usage}
    finally: rt.close()


def run(args):
    d=json.load(open(args.qualification)); prefix,full_messages=qualification_prefix(d,args.reset_after)
    rr=a.replay(d['game_file'],prefix,max_steps=50)
    try:
        reset_hash=rr.hash(); obs=rr.observation; cmds=list(rr.admissible_commands)
    finally: rr.close()
    client=OpenAI(base_url=args.base_url,api_key='ollama',timeout=90)
    gsum,gusage=generic_summary(client,args.model,d,args.reset_after,args.memory_budget)
    trunc=truncated_memory(d,args.reset_after,args.memory_budget)
    pc=compile_plancarry(d,args.reset_after,args.memory_budget)
    memories={'observation_only':None,'truncation':trunc,'generic_summary':gsum,'plancarry':pc}
    arms={'full_history':continue_arm(client,args.model,d['game_file'],prefix,copy.deepcopy(full_messages),args.post_steps)}
    for name,mem in memories.items():
        r=a.replay(d['game_file'],prefix,max_steps=50)
        try:
            if r.hash()!=reset_hash: raise AssertionError(f'reset mismatch before {name}')
            arms[name]=continue_arm(client,args.model,d['game_file'],prefix,fresh_messages(r.observation,list(r.admissible_commands),mem),args.post_steps)
        finally:r.close()
        arms[name]['memory']=mem; arms[name]['memory_proxy_tokens']=token_count(mem or '')
    hashes={v['reset_hash'] for v in arms.values()}
    ref=arms['full_history']['first_action']
    ref_progress=arms['full_history']['first_progress_action']
    ref_steps=arms['full_history']['post_steps'] if arms['full_history']['success'] else None
    for v in arms.values():
        v['first_action_matches_full_history']=(v['first_action']==ref if ref else None)
        v['first_progress_action_matches_full_history']=(v['first_progress_action']==ref_progress if ref_progress else None)
        v['extra_post_steps_vs_full_history']=(v['post_steps']-ref_steps if ref_steps is not None and v['success'] else None)
    return {
      'kind':'ENGINEERING_SMOKE_NOT_SCIENTIFIC_EVIDENCE','model':args.model,'game_file':d['game_file'],'qualification':args.qualification,
      'reset_after':args.reset_after,'reset_hash':reset_hash,'reset_observation':obs,'reset_admissible_commands':cmds,
      'post_step_budget':args.post_steps,'compressed_memory_budget_proxy_tokens':args.memory_budget,'memory_tokenizer':'cl100k_proxy_not_qwen_native',
      'prefix':[x.__dict__ for x in prefix],'memory_generation_usage':{'generic_summary':gusage,'plancarry':{'compiler':'deterministic_visible_prefix','total_tokens':0}},
      'arms':arms,'invariants':{'all_reset_hashes_identical':len(hashes)==1,'qualification_success':bool(d['success']),'qualification_invalid_model_turns':d.get('invalid_model_turns',0),
                 'expert_plan_exposed':False,'future_actions_used_by_plancarry_compiler':False}
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--qualification',required=True); ap.add_argument('--reset-after',type=int,required=True); ap.add_argument('--post-steps',type=int,default=6); ap.add_argument('--memory-budget',type=int,default=96); ap.add_argument('--model',default=MODEL); ap.add_argument('--base-url',default=BASE_URL); ap.add_argument('--output',required=True); args=ap.parse_args()
    r=run(args); Path(args.output).write_text(json.dumps(r,indent=2,ensure_ascii=False))
    print(json.dumps({'kind':r['kind'],'reset_hash':r['reset_hash'],'invariants':r['invariants'],'arms':{k:{'success':v['success'],'post_steps':v['post_steps'],'first_action':v['first_action'],'first_match':v['first_action_matches_full_history'],'progress_action':v['first_progress_action'],'progress_match':v['first_progress_action_matches_full_history'],'loops':v['consecutive_repeat_count'],'reversals':v['prefix_reversal_count'],'invalid':v['invalid_model_turns'],'memory_tokens':v.get('memory_proxy_tokens')} for k,v in r['arms'].items()},'memories':{k:r['arms'][k].get('memory') for k in ['truncation','generic_summary','plancarry']},'output':args.output},indent=2,ensure_ascii=False))
if __name__=='__main__': main()
