#!/usr/bin/env python3
"""Qualify uninterrupted LLM trajectories on official ALFWorld TextWorld games."""
from __future__ import annotations
import argparse,json,hashlib,sys,time
from pathlib import Path
from typing import Any
from openai import OpenAI
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import alfworld_runtime as a

BASE_URL='http://192.168.1.51:11434/v1'
MODEL='qwen2.5:7b-instruct'
SYSTEM='''You are solving an ALFWorld household task. At every turn, select exactly one action from the numbered ADMISSIBLE COMMANDS. Use the current observation and the full interaction history to complete the stated task efficiently. Never invent an action outside the list. Use the choose_action tool only.'''
TOOL={'type':'function','function':{'name':'choose_action','description':'Choose one currently admissible ALFWorld command by its numbered index.','parameters':{'type':'object','properties':{'index':{'type':'integer','minimum':0}},'required':['index'],'additionalProperties':False}}}

def surface(obs:str,commands:list[str])->str:
    return obs+'\n\nADMISSIBLE COMMANDS:\n'+'\n'.join(f'[{i}] {c}' for i,c in enumerate(commands))

def assistant_dict(msg:Any)->dict[str,Any]:
    d={'role':'assistant','content':msg.content or ''}
    if msg.tool_calls:
        d['tool_calls']=[{'id':tc.id,'type':'function','function':{'name':tc.function.name,'arguments':tc.function.arguments}} for tc in msg.tool_calls]
    return d

def call(client,model,messages):
    r=client.chat.completions.create(model=model,messages=messages,tools=[TOOL],tool_choice='required',temperature=0,max_tokens=96)
    u={'prompt_tokens':int(getattr(r.usage,'prompt_tokens',0) or 0),'completion_tokens':int(getattr(r.usage,'completion_tokens',0) or 0),'total_tokens':int(getattr(r.usage,'total_tokens',0) or 0)}
    return r.choices[0].message,u

def run_game(game_file:str,model:str,max_turns:int,client:OpenAI)->dict[str,Any]:
    rt=a.AlfRuntime(game_file,max_steps=max_turns+5)
    initial_hash=rt.hash(); initial_obs=rt.observation
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':surface(rt.observation,rt.admissible_commands)}]
    records=[]; usage=[]; invalid=0
    try:
        for turn in range(max_turns):
            if rt.won or rt.done: break
            msg,u=call(client,model,messages); usage.append(u)
            if not msg.tool_calls:
                invalid+=1; messages.append({'role':'assistant','content':msg.content or ''}); messages.append({'role':'user','content':'You must call choose_action with one valid index.'}); continue
            tc=msg.tool_calls[0]
            try: idx=int(json.loads(tc.function.arguments or '{}').get('index',-1))
            except Exception: idx=-1
            messages.append(assistant_dict(msg))
            if idx<0 or idx>=len(rt.admissible_commands):
                invalid+=1
                messages.append({'role':'tool','tool_call_id':tc.id,'content':surface(f'INVALID INDEX {idx}; state unchanged.',rt.admissible_commands)})
                continue
            command=rt.admissible_commands[idx]
            rec=rt.step(command); records.append(rec)
            messages.append({'role':'tool','tool_call_id':tc.id,'content':surface(rec.observation,rec.admissible_commands)})
            print(json.dumps({'game':Path(game_file).parent.parent.name,'turn':turn+1,'command':command,'score':rec.score,'done':rec.done,'won':rec.won,'state_hash':rec.state_hash}),flush=True)
        return {
            'kind':'ENGINEERING_QUALIFICATION_NOT_SCIENTIFIC_EVIDENCE','game_file':game_file,'model':model,'system_sha256':hashlib.sha256(SYSTEM.encode()).hexdigest(),
            'initial_observation':initial_obs,'initial_hash':initial_hash,'success':bool(rt.won),'done':bool(rt.done),'score':float(rt.score),
            'turns':len(records),'invalid_model_turns':invalid,'actions':[r.__dict__ for r in records],'messages':messages,'usage':usage,
            'final_hash':rt.hash(),'hidden_fact_count_initial':None,
        }
    finally: rt.close()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--model',default=MODEL); ap.add_argument('--max-turns',type=int,default=30); ap.add_argument('--max-games',type=int,default=6); ap.add_argument('--task-prefix',default='pick_and_place_simple'); ap.add_argument('--outdir',required=True); args=ap.parse_args()
    games=a.game_files('valid_seen',args.task_prefix); outdir=Path(args.outdir); outdir.mkdir(parents=True,exist_ok=True)
    client=OpenAI(base_url=BASE_URL,api_key='ollama',timeout=90)
    summary=[]
    for game in games[:args.max_games]:
        print('QUALIFY',game,flush=True)
        r=run_game(game,args.model,args.max_turns,client)
        slug=Path(game).parent.parent.name+'__'+Path(game).parent.name
        p=outdir/(slug+'.json'); p.write_text(json.dumps(r,indent=2,ensure_ascii=False))
        summary.append({'game_file':game,'success':r['success'],'turns':r['turns'],'score':r['score'],'invalid_model_turns':r['invalid_model_turns'],'path':str(p)})
        if r['success']: break
    print('SUMMARY '+json.dumps(summary,indent=2),flush=True)
if __name__=='__main__': main()
