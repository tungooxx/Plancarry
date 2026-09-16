from openai import OpenAI
from alfworld_qualify import TOOL
import json
client=OpenAI(base_url="http://127.0.0.1:11434/v1",api_key="ollama")
r=client.chat.completions.create(model="qwen2.5:7b-instruct",messages=[{"role":"system","content":"Synthetic transport compatibility test only. You must call the provided choose_action tool exactly once."},{"role":"user","content":"There is exactly one synthetic option, numbered 0. Call choose_action with index 0."}],tools=[TOOL],tool_choice="required",temperature=0,max_tokens=96)
m=r.choices[0].message
if not m.tool_calls: raise SystemExit("NO_TOOL_CALL")
tc=m.tool_calls[0]
args=json.loads(tc.function.arguments)
out={"finish_reason":r.choices[0].finish_reason,"tool_name":tc.function.name,"arguments":args,"tool_call_count":len(m.tool_calls)}
print(json.dumps(out,sort_keys=True))
if len(m.tool_calls)!=1: raise SystemExit("WRONG_TOOL_CALL_COUNT")
if tc.function.name!="choose_action": raise SystemExit("WRONG_TOOL_NAME")
if args.get("index")!=0: raise SystemExit("WRONG_INDEX")
