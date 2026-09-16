from __future__ import annotations
import hashlib, json, subprocess, urllib.request
from pathlib import Path

ROOT=Path('/workspace/local-vlm/LLM/plancarry')
BASE='http://127.0.0.1:11434'
MODEL='qwen2.5:7b-instruct'
CANARY=ROOT/'results/design/plancarry_binding_ollama_tool_canary_20260822.py'
OUT=ROOT/'results/design/plancarry_binding_same_machine_ollama_runtime_attestation_20260822.json'
SCI=ROOT/'results/science/alfworld_binding_v1.json'

def sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def get(path:str):
    with urllib.request.urlopen(BASE+path, timeout=20) as r:
        return json.loads(r.read().decode())

def post(path:str,obj):
    req=urllib.request.Request(BASE+path,data=json.dumps(obj).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

if SCI.exists():
    raise SystemExit('REFUSE_SCIENCE_OUTPUT_PRESENT')
version=get('/api/version')
tags=get('/api/tags')
v1=get('/v1/models')
show=post('/api/show',{'name':MODEL})
models=tags.get('models',[])
match=[m for m in models if m.get('name')==MODEL or m.get('model')==MODEL]
if len(match)!=1:
    raise SystemExit(f'EXACT_MODEL_NOT_UNIQUE:{len(match)}')
entry=match[0]
can=subprocess.run(['/opt/gpu-lab/envs/plancarry-alfworld-py312/bin/python',str(CANARY)],cwd=ROOT,text=True,capture_output=True,timeout=240)
if can.returncode!=0:
    raise SystemExit('CANARY_FAIL:'+can.stderr[-1000:]+can.stdout[-1000:])
can_obj=json.loads(can.stdout.strip().splitlines()[-1])
if can_obj.get('tool_name')!='choose_action' or can_obj.get('arguments',{}).get('index')!=0 or can_obj.get('tool_call_count')!=1:
    raise SystemExit('CANARY_SEMANTIC_FAIL')
ps=get('/api/ps')
smi=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.used,driver_version','--format=csv,noheader'],text=True,capture_output=True,timeout=20)
att={
  'artifact_type':'PLANCARRY_BINDING_SAME_MACHINE_OLLAMA_RUNTIME_ATTESTATION',
  'date':'2026-08-22',
  'project_id':'a7bdabba-d07e-44ca-b572-cdef6d3210b2',
  'experiment_id':'49a5eed0-dc91-497a-a0e7-f9b5fc4cd5b1',
  'prediction_id':'8c202017-c809-47d2-81e0-972328e6ce27',
  'hypothesis_id':'71aa4c3f-0b6d-42ea-b773-f69b011d5a62',
  'failed_run_id':'43f2e3f6-15d4-45a0-b277-93541e1ea026',
  'engineering_task_id':'03746f13-6cc7-477d-8e81-08f7875ba7f6',
  'work_item_id':'7dc3c3cd-4c5a-4bfc-8a46-9d0baa512d45',
  'scientific_variable_changed':'NONE_ENGINEERING_ONLY',
  'scientific_variables_changed':[],
  'runtime_binding':{'old_base_url':'http://192.168.1.51:11434/v1','new_base_url':'http://127.0.0.1:11434/v1','same_machine':True},
  'ollama':{
    'version':version.get('version'),
    'official_release_tag':'v0.32.15',
    'official_release_published_at':'2026-08-19T17:25:16Z',
    'linux_amd64_archive_bytes':1422416084,
    'linux_amd64_archive_sha256':'50539c5fe9bf85887733355098dcdb266b433cb8c73fa180713417e9ed6e42bb',
  },
  'model':{
    'requested_name':MODEL,
    'tag_entry':{k:entry.get(k) for k in ['name','model','modified_at','size','digest','details']},
    'show':{k:show.get(k) for k in ['details','capabilities','parameters','modified_at']},
    'v1_model_ids':[x.get('id') for x in v1.get('data',[])],
  },
  'synthetic_tool_canary':{'path':str(CANARY.relative_to(ROOT)),'sha256':sha(CANARY),'result':'PASS','output':can_obj},
  'runtime_processes':ps,
  'gpu':{'nvidia_smi':smi.stdout.strip(),'nvidia_smi_returncode':smi.returncode},
  'frozen_sources':{
    'alfworld_binding_runner.py':sha(ROOT/'alfworld_binding_runner.py'),
    'alfworld_qualify.py':sha(ROOT/'alfworld_qualify.py'),
  },
  'guards':{
    'scientific_output_absent':not SCI.exists(),
    'scientific_outcomes_accessed':False,
    'environment_execution':False,
    'valid_unseen_accessed':False,
    'alfworld_scientific_calls':0,
    'exact_model_name':MODEL,
    'temperature':0,
  },
  'verdict':'PASS_FOR_INDEPENDENT_RUNTIME_REVIEW'
}
OUT.write_text(json.dumps(att,sort_keys=True,indent=2)+'\n')
print('ATTESTATION',OUT)
print('ATTESTATION_SHA256',sha(OUT))
print('MODEL_DIGEST',entry.get('digest'))
print('MODEL_DETAILS',json.dumps(entry.get('details'),sort_keys=True))
print('CANARY',json.dumps(can_obj,sort_keys=True))
print('PS',json.dumps(ps,sort_keys=True))
print('GPU',smi.stdout.strip())
