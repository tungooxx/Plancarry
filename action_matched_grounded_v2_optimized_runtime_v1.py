#!/usr/bin/env python3
"""Exact-token/runtime helpers for reviewed Grounded ActionMatched-v2.
Import is zero-science: no model load and no ALFWorld access.
"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any, Mapping, Sequence

import action_matched_grounded_v2_phase_runner_v1 as phase
from localcontinuation_controls_v2 import strong_interior_derangement
from replay_residual_t1_session_runtime_v1 import capture_activation_ids, token_ids_sha256, vector_sha256_fp32
from action_matched_grounded_v2_optimization_v1 import OptimizedPersistentTokenSession as PersistentTokenSession, capture_activation_ids_multi

ROOT=Path(__file__).resolve().parent
PREREG_REL=Path('results/design/plancarry_action_matched_grounded_v2_science_ready_prereg_v1_20260825.json')
SEMANTIC_DIFF_REL=Path('results/design/plancarry_action_matched_grounded_v2_science_authority_semantic_diff_v1_20260825.json')
STATIC_REL=Path('results/design/plancarry_action_matched_grounded_v2_science_authority_static_audit_v1_20260825.json')
AUTH_TEST_REL=Path('tests/test_action_matched_grounded_v2_science_authority_v1.py')
POP_REL=Path('results/design/plancarry_action_matched_grounded_v2_fresh_population_20260825.json')
CONSTRUCT_REL=Path('action_matched_grounded_v2_constructibility.py')
SESSION_REL=Path('replay_residual_t1_session_runtime_v1.py')
RANDOM_SOURCE_REL=Path('localcontinuation_science_driver_v1.py')
MODEL_ID='Qwen/Qwen3-1.7B'; REVISION='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'
PLAN_RE=re.compile(r'\A<PLAN>\n<ACTION_3>([^\n<>]+)</ACTION_3>\n<ACTION_4>([^\n<>]+)</ACTION_4>\n<ACTION_5>([^\n<>]+)</ACTION_5>\n<RATIONALE>([^\n<>]+)</RATIONALE>\n</PLAN>\Z')
CANARY_MESSAGES=[{'role':'user','content':'SERIALIZATION CANARY'}]

class RuntimeContractError(RuntimeError): pass

def sha_file(p:str|Path)->str:
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def _authority()->dict[str,Any]:
    return json.loads((ROOT/PREREG_REL).read_text())

def verify_frozen_design(root:str|Path=ROOT)->None:
    r=Path(root)
    checks=(
      (PREREG_REL,phase.PREREG_SHA256,'PREREG_DRIFT'),
      (SEMANTIC_DIFF_REL,phase.SEMANTIC_DIFF_SHA256,'SEMANTIC_DIFF_DRIFT'),
      (STATIC_REL,phase.STATIC_AUDIT_SHA256,'STATIC_AUDIT_DRIFT'),
      (AUTH_TEST_REL,phase.AUTHORITY_TEST_SHA256,'AUTHORITY_TEST_DRIFT'),
      (POP_REL,phase.POPULATION_SHA256,'POPULATION_DRIFT'),
      (CONSTRUCT_REL,phase.CONSTRUCTIBILITY_SHA256,'CONSTRUCTIBILITY_DRIFT'),
      (SESSION_REL,phase.SESSION_RUNTIME_SHA256,'SESSION_RUNTIME_DRIFT'),
      (RANDOM_SOURCE_REL,phase.RANDOM_SOURCE_SHA256,'RANDOM_SOURCE_DRIFT'),
    )
    for rel,want,label in checks:
        if sha_file(r/rel)!=want: raise RuntimeContractError(label)
    p=json.loads((r/PREREG_REL).read_text())
    if p.get('science_execution_forbidden') is not True: raise RuntimeContractError('AUTHORITY_SCIENCE_GUARD_DRIFT')
    if p['population']['manifest_sha256']!=phase.POPULATION_SHA256: raise RuntimeContractError('POPULATION_BINDING_DRIFT')

def _ids(tok:Any,text:str)->list[int]: return [int(x) for x in tok.encode(str(text),add_special_tokens=False)]
def _neutral(n:int)->list[int]:
    cyc=[int(x) for x in _authority()['token_serialization']['neutral_cycle_ids']]
    return [cyc[i%len(cyc)] for i in range(int(n))]
def _pad(ids:Sequence[int],n:int)->list[int]:
    x=[int(v) for v in ids]
    if len(x)>int(n): raise RuntimeContractError('TRUNCATION_FORBIDDEN')
    return x+_neutral(int(n)-len(x))

def verify_tokenizer(tok:Any)->dict[str,Any]:
    from transformers.utils.hub import cached_file
    p=_authority(); ts=p['token_serialization']; prov=ts['tokenizer_provenance']
    if tok.__class__.__name__!=prov['class']: raise RuntimeContractError('TOKENIZER_CLASS_DRIFT')
    # Exact local tokenizer assets, revision-bound.
    asset_actual={}
    for name,want in prov['asset_sha256'].items():
        fp=cached_file(MODEL_ID,name,revision=REVISION,local_files_only=True)
        if not fp: raise RuntimeContractError(f'TOKENIZER_ASSET_MISSING:{name}')
        got=sha_file(fp); asset_actual[name]=got
        if got!=want: raise RuntimeContractError(f'TOKENIZER_ASSET_DRIFT:{name}')
    can=[int(x) for x in tok.apply_chat_template(CANARY_MESSAGES,tokenize=True,add_generation_prompt=True,enable_thinking=False)]
    if can!=[int(x) for x in prov['chat_template_canary_ids']]: raise RuntimeContractError('CHAT_TEMPLATE_CANARY_DRIFT')
    for group in ('grounded_wrapper_tokens','plan_wrapper_tokens'):
        for name,obj in ts[group].items():
            if _ids(tok,obj['text']) != [int(x) for x in obj['ids']]: raise RuntimeContractError(f'WRAPPER_TOKEN_DRIFT:{group}:{name}')
    return {'class':tok.__class__.__name__,'asset_sha256':asset_actual,'chat_template_canary_ids_sha256':token_ids_sha256(can)}

def render_reset(task:str,obs:str,commands:Sequence[str])->str:
    return 'TASK\n'+str(task).strip()+'\nCURRENT OBSERVATION\n'+str(obs).strip()+'\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+'\n<STATE_END>\nACTION:'
def split_reset_action(tok:Any,text:str)->tuple[list[int],list[int]]:
    ids=_ids(tok,text); valid=[]
    for k in range(1,len(ids)):
        a=tok.decode(ids[:k],skip_special_tokens=False,clean_up_tokenization_spaces=False)
        b=tok.decode(ids[k:],skip_special_tokens=False,clean_up_tokenization_spaces=False)
        if a.endswith('<STATE_END>\n') and b=='ACTION:': valid.append(k)
    if len(valid)!=1: raise RuntimeContractError(f'RESET_ACTION_SPLIT_NONUNIQUE:{valid}')
    k=valid[0]; return ids[:k],ids[k:]
def action_suffixes(tok:Any,commands:Sequence[str])->dict[str,list[int]]:
    out={c:_ids(tok,' '+c) for c in sorted(str(x) for x in commands)}
    if not out or any(not x for x in out.values()): raise RuntimeContractError('EMPTY_ACTION_SUFFIX')
    return out
def continuation_ids(tok:Any,obs:str,commands:Sequence[str])->list[int]:
    return _ids(tok,'\nOBSERVATION: '+str(obs).strip()+'\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+'\nACTION:')

def tokenize_actions_once(tok:Any,actions:Mapping[str,str])->dict[str,list[int]]:
    required=('A3','A4','B4','A5','B5')
    if set(actions)!=set(required): raise RuntimeContractError('ACTION_KEY_SET_DRIFT')
    out={k:_ids(tok,str(actions[k])) for k in required}
    if any(not v for v in out.values()): raise RuntimeContractError('EMPTY_ACTION_SOURCE_IDS')
    return out

def plan_user_render(task_instruction:str,cut_observation:str,pre_cut_records:Sequence[Mapping[str,Any]],cut_commands:Sequence[str],action3:str,action4:str,action5:str)->str:
    if len(pre_cut_records)!=2: raise RuntimeContractError('PLAN_RENDER_TWO_PRECUT_REQUIRED')
    p=_authority()['plan_materialization']
    vals={
      'instruction':p['instruction'],'task_instruction':str(task_instruction).strip(),'cut_observation':str(cut_observation).strip(),
      'action1':str(pre_cut_records[0]['command']),'obs1':str(pre_cut_records[0]['observation']),
      'action2':str(pre_cut_records[1]['command']),'obs2':str(pre_cut_records[1]['observation']),
      'commands':'\n'.join(sorted(str(x) for x in cut_commands)),
      'action3':str(action3),'action4':str(action4),'action5':str(action5),
    }
    return p['dynamic_user_template'].format(**vals)

def parse_plan_block(text:str,expected_actions:Sequence[str])->dict[str,str]:
    clean=str(text).strip(); m=PLAN_RE.fullmatch(clean)
    if not m: raise RuntimeContractError('PLAN_FULLMATCH_REQUIRED')
    a3,a4,a5,why=m.groups()
    expected=tuple(str(x) for x in expected_actions)
    if (a3,a4,a5)!=expected: raise RuntimeContractError('PLAN_ACTION_ROUNDTRIP_MISMATCH')
    if not why or why!=why.strip() or '<' in why or '>' in why: raise RuntimeContractError('PLAN_RATIONALE_INVALID')
    return {'text':clean,'A3':a3,'A4':a4,'A5':a5,'rationale':why}

def tokenize_plan_block(tok:Any,parsed:Mapping[str,str])->dict[str,Any]:
    text=str(parsed['text']); m=PLAN_RE.fullmatch(text)
    if not m: raise RuntimeContractError('PLAN_TOKENIZE_REPARSE_FAIL')
    enc=tok(text,add_special_tokens=False,return_offsets_mapping=True)
    ids=[int(x) for x in enc['input_ids']]; offsets=[tuple(int(y) for y in x) for x in enc['offset_mapping']]
    if len(ids)>96: raise RuntimeContractError('PLAN_TOKEN_LENGTH_GT96')
    r0,r1=m.span(4)
    mutable=[i for i,(a,b) in enumerate(offsets) if b>a and a>=r0 and b<=r1]
    if len(mutable)<2 or len({ids[i] for i in mutable})<2: raise RuntimeContractError('RATIONALE_DERANGEMENT_UNCONSTRUCTIBLE')
    vals=[ids[i] for i in mutable]
    try:
        y,meta=strong_interior_derangement(vals)
    except Exception as exc:
        raise RuntimeContractError('RATIONALE_DERANGEMENT_UNCONSTRUCTIBLE') from exc
    y=[int(x) for x in y]
    if len(y)!=len(vals) or sorted(y)!=sorted(vals) or y==vals or y[-1]==vals[-1]:
        # Frozen fallback: smallest valid ordinary left rotation.
        found=None
        for off in range(1,len(vals)):
            z=vals[off:]+vals[:off]
            if z!=vals and z[-1]!=vals[-1]: found=z; break
        if found is None: raise RuntimeContractError('RATIONALE_DERANGEMENT_POSTCONDITION')
        y=found; meta={'method':'SMALLEST_VALID_LEFT_ROTATION'}
    der=list(ids)
    for pos,val in zip(mutable,y): der[pos]=int(val)
    frozen=[i for i in range(len(ids)) if i not in set(mutable)]
    if any(der[i]!=ids[i] for i in frozen): raise RuntimeContractError('DERANGEMENT_FROZEN_POSITION_DRIFT')
    if sorted(der)!=sorted(ids): raise RuntimeContractError('DERANGEMENT_FULL_MULTISET_DRIFT')
    return {
      'input_ids':ids,'offset_mapping':[list(x) for x in offsets],'input_ids_sha256':token_ids_sha256(ids),
      'rationale_char_span':[r0,r1],'mutable_rationale_positions':mutable,
      'deranged_input_ids':der,'deranged_input_ids_sha256':token_ids_sha256(der),'derangement_method':meta.get('method'),
    }

def plan_materialize_once(tok:Any,model:Any,task_instruction:str,cut_observation:str,pre_cut_records:Sequence[Mapping[str,Any]],cut_commands:Sequence[str],action3:str,action4:str,action5:str)->dict[str,Any]:
    import torch
    user=plan_user_render(task_instruction,cut_observation,pre_cut_records,cut_commands,action3,action4,action5)
    prefix=[int(x) for x in tok.apply_chat_template([{'role':'user','content':user}],tokenize=True,add_generation_prompt=True,enable_thinking=False)]
    device=next(model.parameters()).device
    with torch.inference_mode():
        out=model.generate(input_ids=torch.tensor([prefix],dtype=torch.long,device=device),do_sample=False,max_new_tokens=128,use_cache=True,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id)
    seq=[int(x) for x in out.tolist()[0]]
    if seq[:len(prefix)]!=prefix: raise RuntimeContractError('PLAN_GENERATION_PREFIX_MISMATCH')
    new=seq[len(prefix):]
    text=tok.decode(new,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
    parsed=parse_plan_block(text,(action3,action4,action5)); toks=tokenize_plan_block(tok,parsed)
    return {
      'text':parsed['text'],'rationale':parsed['rationale'],'rendered_user_sha256':hashlib.sha256(user.encode()).hexdigest(),
      'chat_prefix_ids_sha256':token_ids_sha256(prefix),'generated_suffix_ids_sha256':token_ids_sha256(new),
      'decoded_plan_sha256':hashlib.sha256(parsed['text'].encode()).hexdigest(),**toks,
    }

def common_source_prefix(tok:Any,task:str,cut_obs:str,pre_cut_records:Sequence[Mapping[str,Any]],commands:Sequence[str])->list[int]:
    if len(pre_cut_records)!=2: raise RuntimeContractError('SOURCE_PREFIX_TWO_PRECUT_REQUIRED')
    template=_authority()['token_serialization']['common_prefix_template']
    text=template.format(task_instruction=str(task).strip(),cut_observation=str(cut_obs).strip(),
        action1=pre_cut_records[0]['command'],obs1=pre_cut_records[0]['observation'],
        action2=pre_cut_records[1]['command'],obs2=pre_cut_records[1]['observation'],
        commands='\n'.join(sorted(str(x) for x in commands)))
    return _ids(tok,text)

def source_condition_ids(common_prefix_ids:Sequence[int],action_ids:Mapping[str,Sequence[int]],plan_a:Mapping[str,Any],plan_b:Mapping[str,Any],condition:str)->dict[str,Any]:
    ts=_authority()['token_serialization']; gw=ts['grounded_wrapper_tokens']
    sh=[int(x) for x in action_ids['A3']]; a4=[int(x) for x in action_ids['A4']]; b4=[int(x) for x in action_ids['B4']]; a5=[int(x) for x in action_ids['A5']]; b5=[int(x) for x in action_ids['B5']]
    pa=[int(x) for x in plan_a['input_ids']]; pb=[int(x) for x in plan_b['input_ids']]; pda=[int(x) for x in plan_a['deranged_input_ids']]; pdb=[int(x) for x in plan_b['deranged_input_ids']]
    L3=len(sh); L4=max(len(a4),len(b4)); L5=max(len(a5),len(b5)); LP=max(len(pa),len(pb))
    n3=_neutral(L3); n4=_neutral(L4); n5=_neutral(L5); np=_neutral(LP)
    W={k:[int(x) for x in v['ids']] for k,v in gw.items()}
    def assemble(s3,s4,s5,sp):
        slots={'A3':_pad(s3,L3),'A4':_pad(s4,L4),'A5':_pad(s5,L5),'PLAN':_pad(sp,LP)}
        ids=[*map(int,common_prefix_ids),*W['shared_prefix'],*slots['A3'],*W['sep_a4'],*slots['A4'],*W['sep_a5'],*slots['A5'],*W['sep_plan'],*slots['PLAN'],*W['source_end']]
        return ids,slots
    if condition=='ACTIVE': A=assemble(sh,a4,a5,pa); B=assemble(sh,b4,b5,pb)
    elif condition=='FUTURE_ACTION_SEQUENCE_ONLY': A=assemble(sh,a4,a5,np); B=assemble(sh,b4,b5,np)
    elif condition=='NEXT_DIVERGENT_ACTION_ONLY': A=assemble(sh,a4,n5,np); B=assemble(sh,b4,n5,np)
    elif condition=='FUTURE_TOKEN_DERANGED': A=assemble(sh,a4,a5,pda); B=assemble(sh,b4,b5,pdb)
    elif condition=='ACTION_HISTORY_MATCHED_NULL': A=assemble(sh,n4,n5,np); B=assemble(n3,n4,n5,np)
    else: raise RuntimeContractError(f'UNKNOWN_SOURCE_CONDITION:{condition}')
    Ai,As=A; Bi,Bs=B
    if len(Ai)!=len(Bi) or Ai[-len(W['source_end']):]!=W['source_end'] or Bi[-len(W['source_end']):]!=W['source_end']:
        raise RuntimeContractError('SOURCE_GEOMETRY_DRIFT')
    if condition=='NEXT_DIVERGENT_ACTION_ONLY' and (As['A5']!=n5 or Bs['A5']!=n5 or As['PLAN']!=np or Bs['PLAN']!=np):
        raise RuntimeContractError('NEXT_ONLY_FORBIDDEN_FUTURE_SLOT_CONTENT')
    if condition=='FUTURE_ACTION_SEQUENCE_ONLY' and (As['PLAN']!=np or Bs['PLAN']!=np):
        raise RuntimeContractError('SEQUENCE_ONLY_PLAN_NOT_NEUTRAL')
    return {'A_ids':Ai,'B_ids':Bi,'A_slots':As,'B_slots':Bs,'token_count':len(Ai),'source_end_position':len(Ai)-1,'slot_lengths':{'L3':L3,'L4':L4,'L5':L5,'LP':LP}}

def capture_pair_residual(model:Any,A:Sequence[int],B:Sequence[int],layer:int)->Any:
    a=capture_activation_ids(model,A,int(layer),-1).detach().float().cpu(); b=capture_activation_ids(model,B,int(layer),-1).detach().float().cpu(); return a-b

def capture_pair_residuals(model:Any,A:Sequence[int],B:Sequence[int],layers:Sequence[int])->dict[int,Any]:
    req=[int(x) for x in layers]
    aa=capture_activation_ids_multi(model,A,req,-1); bb=capture_activation_ids_multi(model,B,req,-1)
    return {layer:aa[layer].detach().float().cpu()-bb[layer].detach().float().cpu() for layer in req}

def match_control_norm(v:Any,target:float)->tuple[Any,bool,float]:
    import torch
    x=torch.as_tensor(v,dtype=torch.float32).detach().cpu(); n=float(torch.linalg.vector_norm(x).item())
    if target<=1e-8: return torch.zeros_like(x),False,n
    if n<=1e-8: return torch.zeros_like(x),False,n
    y=x*(float(target)/n); got=float(torch.linalg.vector_norm(y).item())
    if abs(got-target)>max(1e-5,1e-4*target): raise RuntimeContractError('CONTROL_NORM_MISMATCH')
    return y,True,n

def score_margin(session:PersistentTokenSession,tok:Any,a:str,b:str)->float:
    sm=action_suffixes(tok,[a,b]); _best,rows=session.score_candidates(sm); return float(rows[a].mean_logprob-rows[b].mean_logprob)
def reference_margin(session:PersistentTokenSession,tok:Any,reference:str,commands:Sequence[str])->float:
    cmds=sorted(str(x) for x in commands)
    if reference not in cmds or len(cmds)<2: raise RuntimeContractError('REFERENCE_MARGIN_UNDEFINED')
    _best,rows=session.score_candidates(action_suffixes(tok,cmds)); ref=float(rows[reference].mean_logprob)
    return ref-max(float(v.mean_logprob) for k,v in rows.items() if k!=reference)
