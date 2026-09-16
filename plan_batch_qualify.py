#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,tempfile,sys
from pathlib import Path
from openai import OpenAI
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import plancarry_harness as base
import plan_runtime as p
import plan_interruption_harness as x

def atomic(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
 try:
  with os.fdopen(fd,'w') as f: json.dump(obj,f,indent=2,ensure_ascii=False)
  os.replace(tmp,path)
 except Exception:
  try: os.unlink(tmp)
  except OSError: pass
  raise

def load_inst(iid): return next(v for v in base.load_instances() if v['id']==iid)

def init_state(iid,model):
 inst=load_inst(iid); rt=p.PlanRuntime(inst)
 return {'instance_id':iid,'model':model,'protocol_hash':x.protocol_hash(),'messages':x.task_messages(rt.observation()),'actions':[],'turn':0,'done':False,'success':False,'stopped':False,'state_hash':rt.state_hash(),'usage':[],'invalid_no_tool':[]}

def resume_runtime(st):
 inst=load_inst(st['instance_id']); recs=[p.PlanActionRecord(**a) for a in st['actions']]; return inst,p.replay(inst,recs)

def step(st,client):
 inst,rt=resume_runtime(st); msg,u,bad=x.model_turn(client,st['model'],st['messages']); st['usage'].extend(u); st['invalid_no_tool'].extend(bad)
 if msg is None: st['done']=True; st['termination']='no_tool_retry_exhausted'; return st
 tc=msg.tool_calls[0]
 try: raw=json.loads(tc.function.arguments or '{}')
 except Exception: raw={}
 args=x.normalize_args(tc.function.name,raw); rec=rt.execute(tc.function.name,args)
 st['messages'].append(x.assistant_dict(msg)); st['messages'].append({'role':'tool','tool_call_id':tc.id,'content':rec.observation})
 st['actions'].append(rec.__dict__); st['turn']+=1; st['success']=rt.success; st['stopped']=rt.stopped; st['done']=bool(rt.success or rt.stopped); st['state_hash']=rt.state_hash()
 return st

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--ids',nargs='+',required=True); ap.add_argument('--outdir',required=True); ap.add_argument('--model',default=x.MODEL); ap.add_argument('--max-turns',type=int,default=8); args=ap.parse_args()
 outdir=Path(args.outdir); client=OpenAI(base_url=x.BASE_URL,api_key='ollama',timeout=90); summary=[]
 for iid in args.ids:
  path=outdir/f'{iid}.json'
  st=json.load(open(path)) if path.exists() else init_state(iid,args.model)
  if st.get('protocol_hash')!=x.protocol_hash(): raise RuntimeError(f'protocol mismatch for {iid}')
  while not st.get('done') and st.get('turn',0)<args.max_turns:
   st=step(st,client); atomic(path,st)
   last=st['actions'][-1] if st['actions'] else None
   print(json.dumps({'instance_id':iid,'turn':st['turn'],'action':last['normalized'] if last else None,'error':last['error'] if last else None,'success':st['success'],'done':st['done']},ensure_ascii=False),flush=True)
  summary.append({'instance_id':iid,'target':load_inst(iid)['target'],'turns':st['turn'],'success':st['success'],'done':st['done'],'stopped':st['stopped'],'path':str(path)})
 print('SUMMARY',json.dumps(summary,indent=2))
if __name__=='__main__': main()
