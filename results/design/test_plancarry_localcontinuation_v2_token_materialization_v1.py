from __future__ import annotations
import collections, hashlib, itertools, json, os, pathlib, re
from transformers import AutoTokenizer
REV="70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
SNAP=pathlib.Path(os.environ.get("PLANCARRY_QWEN3_TOKENIZER_SNAPSHOT",f".hf_cache_qwen3_v21/hub/models--Qwen--Qwen3-1.7B/snapshots/{REV}"))
EXPECTED_FILES={"tokenizer.json":"aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4","tokenizer_config.json":"d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101","config.json":"1ddb5b89ebc90dcb417a45c213d818577e65976454d29385c8f6140771d95197","vocab.json":"ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910","merges.txt":"8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5"}
def H(b):return hashlib.sha256(b).hexdigest()
def C(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def balanced(x):
 x=list(x);n=len(x);k=4 if n>=8 else 2;q,r=divmod(n,k);sizes=[q+(i<r) for i in range(k)];bs=[];j=0
 for z in sizes:bs.append(x[j:j+z]);j+=z
 return [v for b in bs[1:]+bs[:1] for v in b]
def strong(x):
 x=list(x)
 if len(x)<2 or len(set(x))<2:raise ValueError
 y=balanced(x)
 if y!=x and y[-1]!=x[-1]:return y,"primary"
 for off in range(1,len(x)):
  y=x[off:]+x[:off]
  if y!=x and y[-1]!=x[-1]:return y,"fallback"
 raise ValueError
def map_plan(tok,text):
 m=re.fullmatch(r"(<PLAN>)(.*?)(</PLAN>)",text,re.I|re.S);assert m
 enc=tok(text,add_special_tokens=False,return_offsets_mapping=True);ids=list(enc["input_ids"]);offs=[tuple(x) for x in enc["offset_mapping"]]
 oe=m.end(1);cs=m.start(3);mutable=[i for i,(a,b) in enumerate(offs) if b>a and a>=oe and b<=cs]
 frozen=[i for i in range(len(ids)) if i not in mutable]
 vals=[ids[i] for i in mutable]; y,method=strong(vals);out=ids.copy()
 for i,v in zip(mutable,y):out[i]=v
 assert len(out)==len(ids) and collections.Counter(out)==collections.Counter(ids)
 assert all(out[i]==ids[i] for i in frozen);assert y!=vals and y[-1]!=vals[-1]
 return ids,offs,mutable,frozen,out,method
assert SNAP.is_dir(),SNAP
for n,h in EXPECTED_FILES.items():assert H((SNAP/n).read_bytes())==h,(n,H((SNAP/n).read_bytes()))
tok=AutoTokenizer.from_pretrained(str(SNAP),local_files_only=True,use_fast=True)
primitive=" neutral context remains unchanged.";cycle=tok.encode(primitive,add_special_tokens=False);assert cycle==[20628,2266,8458,34857,13],cycle
stream=(cycle*((128+len(cycle)-1)//len(cycle)))[:128];assert len(stream)==128
assert H(C(stream))=="557e30342fe6309165f388724a14895474db6d7ef82e4a3679c4459f4f7ae287"
assert tok.encode("\n",add_special_tokens=False)==[198]
# Includes the common tokenizer-merge case where one token spans the literal opening-tag end and newline.
for text in ["<PLAN>go kitchen take mug put table</PLAN>","<PLAN>\nmove move move then put mug\n</PLAN>","<PLAN>inspect; take mug. place mug</PLAN>","<PLAN> go kitchen then place mug</PLAN>"]:
 map_plan(tok,text)
constructible=primary=fallback=all_equal=0
for n in range(2,11):
 for x in itertools.product(range(3),repeat=n):
  if len(set(x))<2:
   all_equal+=1
   try:strong(x);raise AssertionError("expected fail")
   except ValueError:pass
   continue
  y,m=strong(x);constructible+=1;assert collections.Counter(y)==collections.Counter(x) and y!=list(x) and y[-1]!=x[-1]
  primary+=m=="primary";fallback+=m=="fallback"
assert (constructible,primary,fallback,all_equal)==(88542,59046,29496,27),(constructible,primary,fallback,all_equal)
contract=json.load(open("results/design/plancarry_localcontinuation_v2_constructible_control_contract_v1_20260824.json"))
prereg=json.load(open("results/design/plancarry_localcontinuation_v2_final_prereg_v1_20260824.json"))
mat=json.load(open("results/design/plancarry_localcontinuation_v2_token_materialization_repair_a2_20260824.json"))
assert contract["slot_geometry"]["neutral_filler"]["literal_stream_ids"]==stream
assert prereg["slot_geometry_v2"]["neutral_filler"]["literal_stream_ids_sha256"]==H(C(stream))
assert mat["past_actions_separator"]["ids"]==[198]
assert mat["model_calls"]==mat["alfworld_study_execution"]==mat["vast_usage"]==0
print(json.dumps({"status":"PASS","filler_sha256":H(C(stream)),"separator_ids":[198],"constructible":constructible,"primary":primary,"fallback":fallback,"all_equal_fail_closed":all_equal,"model_calls":0,"alfworld_study_execution":0,"vast_usage":0},sort_keys=True))
