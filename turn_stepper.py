#!/usr/bin/env python3
"""Restart-safe one-turn Plancraft runner for engineering qualification."""
import argparse, json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import plancarry_harness as h
from openai import OpenAI


def atomic_write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w') as f: json.dump(obj,f,indent=2,ensure_ascii=False)
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def init_state(path, iid, model):
    inst=next(x for x in h.load_instances() if x['id']==iid)
    rt=h.CraftRuntime(inst)
    st={'instance_id':iid,'model':model,'messages':h.task_messages(rt.observation()),'actions':[],'done':False,'success':False,'stopped':False,'turn':0}
    atomic_write(path,st)
    print(json.dumps({'initialized':str(path),'instance_id':iid,'target':inst['target'],'state_hash':rt.state_hash()}))


def replay_state(st):
    inst=next(x for x in h.load_instances() if x['id']==st['instance_id'])
    recs=[h.ActionRecord(**x) for x in st['actions']]
    return inst,h.replay(inst,recs)


def step(path, base_url):
    st=json.load(open(path)); inst,rt=replay_state(st)
    if st.get('done'):
        print(json.dumps({'already_done':True,'success':st.get('success'),'turn':st.get('turn')})); return
    client=OpenAI(base_url=base_url,api_key='ollama',timeout=90)
    messages=st['messages']
    msg,usages,invalid=h.get_required_tool_turn(client,st['model'],messages)
    if msg is None:
        st['done']=True; st['termination']='no_tool_retry_exhausted'; atomic_write(path,st)
        print(json.dumps({'done':True,'termination':st['termination'],'invalid':invalid})); return
    tc=msg.tool_calls[0]
    try: raw=json.loads(tc.function.arguments or '{}')
    except Exception: raw={}
    args=h.sanitize_args(tc.function.name,raw)
    rec=rt.execute(tc.function.name,args)
    messages.append(h.assistant_msg_dict(msg)); messages.append({'role':'tool','tool_call_id':tc.id,'content':rec.observation})
    st['messages']=messages; st['actions'].append(rec.__dict__); st['turn']=int(st.get('turn',0))+1
    st['success']=rt.success; st['stopped']=rt.stopped; st['done']=bool(rt.success or rt.stopped)
    st.setdefault('usage',[]).extend(usages); st.setdefault('invalid_no_tool',[]).extend(invalid)
    st['state_hash']=rt.state_hash()
    atomic_write(path,st)
    print(json.dumps({'turn':st['turn'],'action':rec.normalized,'error':rec.error,'success':rt.success,'stopped':rt.stopped,'done':st['done'],'observation':rec.observation[:1800],'state_hash':st['state_hash']},ensure_ascii=False,indent=2))


def show(path):
    st=json.load(open(path)); print(json.dumps({k:v for k,v in st.items() if k not in {'messages','usage'}},ensure_ascii=False,indent=2))

ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
a=sub.add_parser('init'); a.add_argument('--state',required=True); a.add_argument('--instance-id',required=True); a.add_argument('--model',default='qwen2.5:7b-instruct')
a=sub.add_parser('step'); a.add_argument('--state',required=True); a.add_argument('--base-url',default=h.DEFAULT_BASE_URL)
a=sub.add_parser('show'); a.add_argument('--state',required=True)
args=ap.parse_args(); p=Path(args.state)
if args.cmd=='init': init_state(p,args.instance_id,args.model)
elif args.cmd=='step': step(p,args.base_url)
else: show(p)
