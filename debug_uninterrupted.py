import json, sys
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import plancarry_harness as h
from openai import OpenAI
iid=sys.argv[1] if len(sys.argv)>1 else 'TEST0174'
max_steps=int(sys.argv[2]) if len(sys.argv)>2 else 10
inst=next(x for x in h.load_instances() if x['id']==iid)
client=OpenAI(base_url=h.DEFAULT_BASE_URL,api_key='ollama',timeout=90)
rt=h.CraftRuntime(inst); msgs=h.task_messages(rt.observation())
print('INSTANCE',iid,'TARGET',inst['target'],'OBS0',rt.observation().replace('\n',' | '),flush=True)
for i in range(max_steps):
    msg, usages, invalid=h.get_required_tool_turn(client,'qwen2.5:7b-instruct',msgs)
    if msg is None: print('NO_TOOL',invalid,flush=True); break
    tc=msg.tool_calls[0]
    try: raw=json.loads(tc.function.arguments or '{}')
    except Exception: raw={}
    args=h.sanitize_args(tc.function.name,raw); rec=rt.execute(tc.function.name,args)
    print('STEP',i+1,rec.normalized,'ERR',rec.error,'SUCCESS',rec.success,flush=True)
    print('OBS',rec.observation.replace('\n',' | ')[:1800],flush=True)
    msgs.append(h.assistant_msg_dict(msg)); msgs.append({'role':'tool','tool_call_id':tc.id,'content':rec.observation})
    if rt.success or rt.stopped: break
print('FINAL_SUCCESS',rt.success,'STOPPED',rt.stopped,flush=True)
