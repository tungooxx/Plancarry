from __future__ import annotations
import argparse, hashlib, json, os, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from alfworld_runtime import ACTIVE_DATA_ROOT, AlfRuntime, stable_json as alf_stable_json
from whitebox_client import WhiteboxClient

DESIGN_PATH=Path('results/design/plancarry_qwen3_17b_expressivity_recovery_design_v1.json')
MANIFEST_PATH=Path('results/design/plancarry_qwen3_17b_expressivity_recovery_manifest_v1.json')
DESIGN_SHA='51e3f81671eddb306af3d15d4c34ba8b1301543e2efe2fce8ad0d514d0b5ec81'
MANIFEST_SHA='bff529503ac72371102e8689be0ecf92b367b1fe039d6e62444c00b54a27d8b5'
MODEL_ID='Qwen/Qwen3-1.7B'
MODEL_REV='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'
EXPECTED_DEVICE='NVIDIA GeForce RTX 3050 Laptop GPU'
EXPECTED_TRANSFORMERS='4.51.3'
EXPECTED_TOKENIZERS='0.21.1'
EXPECTED_TORCH='2.13.0+cu130'
PASS_MIN=12
N=20

def sha_bytes(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def sha_text(s:str)->str: return hashlib.sha256(s.encode()).hexdigest()
def hjson(x:Any)->str: return hashlib.sha256(alf_stable_json(x).encode('utf-8')).hexdigest()
def lex_bag(s:str): return sorted(re.findall(r'\w+|[^\w\s]',s.lower()))

def task_line(obs:str)->str:
    rows=[line.strip() for line in obs.splitlines() if line.strip().startswith('Your task is to:')]
    if len(rows)!=1: raise RuntimeError(f'TASK_TEXT_EXTRACTION_FAILED count={len(rows)}')
    return rows[0]

def clause(obj:dict[str,Any], target:str)->str:
    return f'Complete {obj["object"]} from {obj["source"]} into {target}.'

@dataclass
class PairContext:
    idx:int; family:str; delayed_divergence:bool; reset_block:str; active_a:str; active_b:str; command_a:str; command_b:str
    @property
    def suffixes(self)->list[str]: return [' '+self.command_a,' '+self.command_b]
    @property
    def scoring_prompt(self)->str: return self.reset_block+'ACTION:'
    def source_scoring_prompt(self, which:str)->str:
        src={'active_a':self.active_a,'active_b':self.active_b}[which]
        return src+'ACTION:'

def load_bundle():
    if sha_bytes(DESIGN_PATH)!=DESIGN_SHA: raise RuntimeError('DESIGN_SHA_MISMATCH')
    if sha_bytes(MANIFEST_PATH)!=MANIFEST_SHA: raise RuntimeError('MANIFEST_SHA_MISMATCH')
    d=json.loads(DESIGN_PATH.read_text()); m=json.loads(MANIFEST_PATH.read_text())
    if d['recovery_model']['model_id']!=MODEL_ID or d['recovery_model']['revision']!=MODEL_REV: raise RuntimeError('MODEL_BINDING_MISMATCH')
    if d['held_fixed_from_v26']['source_competence']!={'source_a_margin_min':0.1,'source_b_margin_max':-0.1,'family_competent_rule':'both thresholds','cohort_pass_min':12,'cohort_n':20}: raise RuntimeError('COMPETENCE_RULE_MISMATCH')
    if m['selected_pair_count']!=20 or len(m['selected_pairs'])!=20: raise RuntimeError('MANIFEST_N_MISMATCH')
    if m.get('model_calls')!=0 or not m.get('environment_only'): raise RuntimeError('MANIFEST_NOT_ENV_ONLY')
    return d,m

def build_context(pair:dict[str,Any], idx:int)->PairContext:
    root=Path(ACTIVE_DATA_ROOT)
    game=(root/pair['game_path']).resolve()
    rt=AlfRuntime(str(game),max_steps=40)
    try:
        initial_observation=rt.observation
        for command in pair['common_prefix_actions']:
            out=rt.step(command)
            if out.error: raise RuntimeError(f'RESET_REPLAY_INVALID_COMMAND pair={idx} {out.error}')
        if rt.hash()!=pair['reset_state_hash']: raise RuntimeError(f'RESET_STATE_HASH_MISMATCH pair={idx}')
        if sha_text(rt.observation)!=pair['reset_observation_sha256']: raise RuntimeError(f'RESET_OBSERVATION_HASH_MISMATCH pair={idx}')
        commands=list(rt.admissible_commands)
        if commands!=pair['reset_admissible_commands'] or hjson(commands)!=pair['reset_admissible_commands_sha256']:
            raise RuntimeError(f'RESET_COMMANDS_HASH_MISMATCH pair={idx}')
        task=task_line(initial_observation); reset_obs=rt.observation
    finally: rt.close()
    sorted_commands=sorted(commands)
    reset_block=(f'TASK\n{task}\nCURRENT OBSERVATION\n{reset_obs}\nADMISSIBLE COMMANDS\n'+"\n".join(sorted_commands)+'\n<STATE_END>\n')
    # Exact option orientation inherited from v2.6 SHA256 parity rule.
    bit=int(hashlib.sha256(f'{MANIFEST_SHA}|{idx}|option_orientation_v1'.encode('utf-8')).hexdigest()[0:2],16)%2
    if bit==0:
        oa,ob=pair['object_a'],pair['object_b']; ca_cmd,cb_cmd=pair['a_first_divergent_action'],pair['b_first_divergent_action']
    else:
        oa,ob=pair['object_b'],pair['object_a']; ca_cmd,cb_cmd=pair['b_first_divergent_action'],pair['a_first_divergent_action']
    if ca_cmd not in commands or cb_cmd not in commands or ca_cmd==cb_cmd: raise RuntimeError(f'DIVERGENT_COMMAND_GUARD_FAILED pair={idx}')
    ca,cb=clause(oa,pair['target_receptacle']),clause(ob,pair['target_receptacle'])
    active_a=reset_block+f'PLAN OPTIONS\nOPTION A: {ca}\nOPTION B: {cb}\nACTIVE ORDER: A THEN B\n<STATE_END>\n'
    active_b=active_a.replace('ACTIVE ORDER: A THEN B','ACTIVE ORDER: B THEN A',1)
    if lex_bag(active_a)!=lex_bag(active_b): raise RuntimeError(f'LEXICAL_MULTISET_GUARD_FAILED pair={idx}')
    return PairContext(idx,pair['family'],bool(pair['delayed_divergence']),reset_block,active_a,active_b,ca_cmd,cb_cmd)

def validate_model_info(info:dict[str,Any]):
    checks={
      'mode':info.get('mode')=='real','model_id':info.get('model_id')==MODEL_ID,
      'revision_requested':info.get('model_revision_requested')==MODEL_REV,'revision_resolved':info.get('model_commit_resolved')==MODEL_REV,
      'device':str(info.get('device'))=='cuda','device_name':str(info.get('device_name'))==EXPECTED_DEVICE,
      'dtype':str(info.get('dtype')).lower() in {'torch.bfloat16','bfloat16','bf16'},
      'transformers':info.get('transformers_version')==EXPECTED_TRANSFORMERS,'tokenizers':info.get('tokenizers_version')==EXPECTED_TOKENIZERS,
      'torch':info.get('torch_version')==EXPECTED_TORCH,'quantization':str(info.get('quantization')).upper()=='NONE',
      'layers':int(info.get('num_layers',-1))==28,'hidden_size':int(info.get('hidden_size',-1))==2048,
    }
    bad=[k for k,v in checks.items() if not v]
    if bad: raise RuntimeError(f'BRIDGE_PROVENANCE_GATE_FAILED {bad} info={info}')

def score_pair(client:WhiteboxClient,prompt:str,suffixes:list[str]):
    r=client.score_sequences(prompt,suffixes); rows=r['scores']
    means=[float(x['logprob_sum'])/int(x['token_count']) for x in rows]
    margin=means[0]-means[1]
    # Same monotonic logistic q used in v2.6; only margin thresholds gate qualification.
    import math
    q=1.0/(1.0+math.exp(-margin))
    return q,margin,means

def source_competence(client:WhiteboxClient,ctx:PairContext):
    qa,ma,_=score_pair(client,ctx.source_scoring_prompt('active_a'),ctx.suffixes)
    qb,mb,_=score_pair(client,ctx.source_scoring_prompt('active_b'),ctx.suffixes)
    return {'margin_source_a':ma,'margin_source_b':mb,'q_source_a':qa,'q_source_b':qb,'competent':ma>=0.10 and mb<=-0.10}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',required=True); ap.add_argument('--token-env',default='PLANCARRY_WHITEBOX_TOKEN'); ap.add_argument('--output',required=True)
    args=ap.parse_args(); outp=Path(args.output)
    if outp.exists(): raise RuntimeError('OUTPUT_EXISTS_REFUSING_OVERWRITE')
    _,manifest=load_bundle()
    token=os.environ.get(args.token_env,'');
    if not token: raise RuntimeError('WHITEBOX_TOKEN_MISSING')
    client=WhiteboxClient(args.base_url,token,None); info=client.model_info(); validate_model_info(info)
    contexts={i:build_context(p,i) for i,p in enumerate(manifest['selected_pairs'])}
    competence={str(i):source_competence(client,contexts[i]) for i in range(N)}
    count=sum(1 for x in competence.values() if x['competent'])
    status='PASS_MODEL_EXPRESSIVITY_QWEN3_17B' if count>=PASS_MIN else 'INCONCLUSIVE_MODEL_ONLY_RECOVERY'
    obj={'kind':'PLANCARRY_QWEN3_17B_EXPRESSIVITY_RECOVERY_RESULT_V1','status':status,'scientific_result':'NOT_ASSESSED_T1_EXPRESSIVITY_ONLY',
      'competent_count':count,'n':N,'required_min':PASS_MIN,'competence':competence,'model_info':info,
      'frozen_refs':{'design_sha256':DESIGN_SHA,'manifest_sha256':MANIFEST_SHA,'model_id':MODEL_ID,'model_revision':MODEL_REV},
      'causal_interventions_computed':False,'layer_alpha_search_computed':False,'confirmation_requests_made':False,'valid_seen_consumed':False,'valid_unseen_consumed':False}
    outp.parent.mkdir(parents=True,exist_ok=True); raw=(json.dumps(obj,indent=2,sort_keys=True)+'\n').encode(); outp.write_bytes(raw)
    print(json.dumps({'output':str(outp),'sha256':hashlib.sha256(raw).hexdigest(),'status':status,'competent_count':count,'n':N},sort_keys=True),flush=True)
if __name__=='__main__': main()
