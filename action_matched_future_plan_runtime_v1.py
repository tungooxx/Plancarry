#!/usr/bin/env python3
"""Exact-token runtime helpers for ActionMatched FuturePlan v1.
No population execution occurs at import. Functions operate on caller-supplied exact IDs/state.
"""
from __future__ import annotations
import hashlib, json, math, re
from pathlib import Path
from typing import Any, Mapping, Sequence
import action_matched_future_plan_phase_runner_v1 as phase
from replay_residual_t1_session_runtime_v1 import PersistentTokenSession, capture_activation_ids, token_ids_sha256, vector_sha256_fp32
from localcontinuation_controls_v2 import strong_interior_derangement

PREREG_REL=Path('results/design/plancarry_action_matched_future_plan_prereg_v1_20260825.json')
PREREG_SHA256=phase.PREREG_SHA256
POP_REL=Path('results/design/plancarry_action_matched_future_plan_population_v1_20260825.json')
POP_SHA256=phase.POPULATION_SHA256
STATIC_REL=Path('results/design/plancarry_action_matched_future_plan_static_audit_v1_20260825.json')
RANDOM_CONTROL_REPAIR_REL=Path('results/design/plancarry_action_matched_future_plan_random_control_repair_a2_20260825.json')
RANDOM_SOURCE_REL=Path('localcontinuation_science_driver_v1.py')
SERIALIZATION_AUDIT_REL=Path('results/design/plancarry_action_matched_future_plan_token_serialization_repair_a4_20260825.json')
DESIGN_TEST_REL=Path('tests/test_action_matched_future_plan_design_v1.py')
HELPER_REL=Path('localcontinuation_controls_v2.py')
MODEL_ID='Qwen/Qwen3-1.7B'; REVISION='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'
TRANSFORMERS_VERSION='4.51.3'; TOKENIZERS_VERSION='0.21.1'; TORCH_VERSION='2.13.0+cu130'
NEWLINE_IDS=(198,); SOURCE_END_IDS=(18858,13077,10898,29); NEUTRAL_CYCLE=(20628,2266,8458,34857,13)
CANARY_IDS=(151644,872,198,31981,32601,3495,19508,8642,151645,198,151644,77091,198,151667,271,151668,271)
PAIR_RE=re.compile(r'\A<PLAN_PAIR>\n<SHARED_ACTION>([^\n<>]+)</SHARED_ACTION>\n<PLAN_A_ACTION4>([^\n<>]+)</PLAN_A_ACTION4>\n<PLAN_A_ACTION5>([^\n<>]+)</PLAN_A_ACTION5>\n<PLAN_B_ACTION4>([^\n<>]+)</PLAN_B_ACTION4>\n<PLAN_B_ACTION5>([^\n<>]+)</PLAN_B_ACTION5>\n</PLAN_PAIR>\Z')

class RuntimeContractError(RuntimeError): pass

def sha_file(p:str|Path)->str:
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def verify_frozen_design(root:str|Path='.') -> None:
    r=Path(root)
    checks=((PREREG_REL,PREREG_SHA256,'PREREG_DRIFT'),(STATIC_REL,phase.STATIC_AUDIT_SHA256,'STATIC_AUDIT_DRIFT'),(RANDOM_CONTROL_REPAIR_REL,phase.RANDOM_CONTROL_REPAIR_SHA256,'RANDOM_CONTROL_REPAIR_DRIFT'),(RANDOM_SOURCE_REL,phase.RANDOM_SOURCE_SHA256,'RANDOM_SOURCE_DRIFT'),(SERIALIZATION_AUDIT_REL,phase.SERIALIZATION_AUDIT_SHA256,'SERIALIZATION_AUDIT_DRIFT'),(DESIGN_TEST_REL,phase.DESIGN_TEST_SHA256,'DESIGN_TEST_DRIFT'),(HELPER_REL,phase.DERANGEMENT_HELPER_SHA256,'DERANGEMENT_HELPER_DRIFT'),(POP_REL,POP_SHA256,'POPULATION_DRIFT'))
    for rel,want,label in checks:
        if sha_file(r/rel)!=want: raise RuntimeContractError(label)

def _ids(tok:Any,text:str)->list[int]: return [int(x) for x in tok.encode(str(text),add_special_tokens=False)]
def _pad(ids:Sequence[int],n:int)->list[int]:
    x=[int(v) for v in ids]
    if len(x)>n: raise RuntimeContractError('PAD_TARGET_SHORTER_THAN_IDS')
    return x+[NEUTRAL_CYCLE[i%len(NEUTRAL_CYCLE)] for i in range(n-len(x))]

def verify_tokenizer(tok:Any)->dict[str,Any]:
    if tok.__class__.__name__!='Qwen2TokenizerFast': raise RuntimeContractError('TOKENIZER_CLASS_DRIFT')
    if _ids(tok,'\n')!=list(NEWLINE_IDS) or _ids(tok,'<SOURCE_END>')!=list(SOURCE_END_IDS): raise RuntimeContractError('TOKEN_CONSTANT_DRIFT')
    can=[int(x) for x in tok.apply_chat_template([{'role':'user','content':'SERIALIZATION CANARY'}],tokenize=True,add_generation_prompt=True,enable_thinking=False)]
    if can!=list(CANARY_IDS): raise RuntimeContractError('CHAT_TEMPLATE_CANARY_DRIFT')
    return {'newline_ids_sha256':token_ids_sha256(NEWLINE_IDS),'source_end_ids_sha256':token_ids_sha256(SOURCE_END_IDS),'neutral_cycle_ids_sha256':token_ids_sha256(NEUTRAL_CYCLE),'chat_template_canary_ids_sha256':token_ids_sha256(CANARY_IDS)}

def render_reset(task:str,obs:str,commands:Sequence[str])->str:
    return 'TASK\n'+str(task).strip()+'\nCURRENT OBSERVATION\n'+str(obs).strip()+'\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+'\n<STATE_END>\nACTION:'
def split_reset_action(tok:Any,text:str)->tuple[list[int],list[int]]:
    ids=_ids(tok,text); valid=[]
    for k in range(1,len(ids)):
        p=tok.decode(ids[:k],skip_special_tokens=False,clean_up_tokenization_spaces=False); q=tok.decode(ids[k:],skip_special_tokens=False,clean_up_tokenization_spaces=False)
        if p.endswith('<STATE_END>\n') and q=='ACTION:': valid.append(k)
    if len(valid)!=1: raise RuntimeContractError(f'RESET_ACTION_SPLIT_NONUNIQUE:{valid}')
    k=valid[0]; return ids[:k],ids[k:]
def action_suffixes(tok:Any,commands:Sequence[str])->dict[str,list[int]]:
    out={c:_ids(tok,' '+c) for c in sorted(str(x) for x in commands)}
    if not out or any(not x for x in out.values()): raise RuntimeContractError('EMPTY_ACTION_SUFFIX')
    return out

def continuation_ids(tok:Any,obs:str,commands:Sequence[str])->list[int]:
    return _ids(tok,'\nOBSERVATION: '+str(obs).strip()+'\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+'\nACTION:')
def pair_user_render(instruction:str,task:str,cut_obs:str,actions:Sequence[Mapping[str,Any]],commands:Sequence[str])->str:
    if len(actions)!=2: raise RuntimeContractError('PAIR_RENDER_REQUIRES_TWO_ACTIONS')
    return (str(instruction)+'\n\nTASK\n'+str(task).strip()+'\nCURRENT OBSERVATION\n'+str(cut_obs).strip()+'\nPAST ACTIONS\n'
            f"STEP 1\nACTION: {actions[0]['command']}\nOBSERVATION: {actions[0]['observation']}\nSTEP 2\nACTION: {actions[1]['command']}\nOBSERVATION: {actions[1]['observation']}\nCURRENT ADMISSIBLE COMMANDS\n"+'\n'.join(sorted(str(x) for x in commands)))
def parse_pair(text:str)->dict[str,str]:
    m=PAIR_RE.fullmatch(str(text).strip())
    if not m: raise RuntimeContractError('PAIR_FULLMATCH_REQUIRED')
    vals=[x.strip() for x in m.groups()]
    if any(not x for x in vals): raise RuntimeContractError('PAIR_EMPTY_ACTION')
    shared,a4,a5,b4,b5=vals
    if (a4,a5)>(b4,b5): a4,a5,b4,b5=b4,b5,a4,a5
    return {'shared_action3':shared,'A4':a4,'A5':a5,'B4':b4,'B5':b5}
def pair_plan_once(tok:Any,model:Any,instruction:str,task:str,cut_obs:str,actions:Sequence[Mapping[str,Any]],commands:Sequence[str])->dict[str,Any]:
    import torch
    user=pair_user_render(instruction,task,cut_obs,actions,commands); prefix=[int(x) for x in tok.apply_chat_template([{'role':'user','content':user}],tokenize=True,add_generation_prompt=True,enable_thinking=False)]
    device=next(model.parameters()).device
    with torch.inference_mode(): out=model.generate(input_ids=torch.tensor([prefix],dtype=torch.long,device=device),do_sample=False,max_new_tokens=192,use_cache=True,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id)
    seq=[int(x) for x in out.tolist()[0]]
    if seq[:len(prefix)]!=prefix: raise RuntimeContractError('PAIR_GENERATION_PREFIX_MISMATCH')
    new=seq[len(prefix):]; text=tok.decode(new,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(); pair=parse_pair(text)
    ids={k:_ids(tok,v) for k,v in pair.items()}
    if any(not x for x in ids.values()): raise RuntimeContractError('PAIR_ACTION_EMPTY_IDS')
    return {'pair':pair,'action_ids':ids,'user_sha256':hashlib.sha256(user.encode()).hexdigest(),'prefix_ids_sha256':token_ids_sha256(prefix),'generated_ids_sha256':token_ids_sha256(new),'decoded_sha256':hashlib.sha256(text.encode()).hexdigest()}
def common_source_prefix(tok:Any,task:str,cut_obs:str,actions:Sequence[Mapping[str,Any]],commands:Sequence[str])->list[int]:
    if len(actions)!=2: raise RuntimeContractError('SOURCE_PREFIX_TWO_ACTIONS_REQUIRED')
    text=('TASK\n'+str(task).strip()+'\nCUT OBSERVATION\n'+str(cut_obs).strip()+'\nPAST ACTIONS\n'
          f"STEP 1\nACTION: {actions[0]['command']}\nOBSERVATION: {actions[0]['observation']}\nSTEP 2\nACTION: {actions[1]['command']}\nOBSERVATION: {actions[1]['observation']}\nCUT ADMISSIBLE COMMANDS\n"+'\n'.join(sorted(str(x) for x in commands))+'\n<PAIR_SOURCE>\nSHARED ACTION:\n')
    return _ids(tok,text)
def _exact_future_derangement(ids:Sequence[int],segment_name:str)->list[int]:
    """Pinned reviewed per-segment derangement; no alternate algorithm."""
    x=[int(v) for v in ids]
    try:
        y,meta=strong_interior_derangement(x)
    except Exception as exc:
        raise RuntimeContractError(f'DERANGEMENT_UNCONSTRUCTIBLE:{segment_name}') from exc
    y=[int(v) for v in y]
    if len(y)!=len(x) or sorted(y)!=sorted(x) or y==x or y[-1]==x[-1]:
        raise RuntimeContractError(f'DERANGEMENT_POSTCONDITION_FAIL:{segment_name}')
    if meta.get('method') not in {'BALANCED_BLOCK_LEFT_ROTATE','SMALLEST_VALID_LEFT_ROTATION'}:
        raise RuntimeContractError(f'DERANGEMENT_METHOD_DRIFT:{segment_name}')
    return y

def validate_future_segments_constructible(action_ids:Mapping[str,Sequence[int]])->dict[str,list[int]]:
    out={}
    for key in ('A4','A5','B4','B5'):
        if key not in action_ids:
            raise RuntimeContractError(f'DERANGEMENT_SEGMENT_MISSING:{key}')
        out[key]=_exact_future_derangement(action_ids[key],key)
    return out

def source_condition_ids(prefix:Sequence[int],action_ids:Mapping[str,Sequence[int]],condition:str)->tuple[list[int],list[int]]:
    sh=[int(x) for x in action_ids['shared_action3']]; a4=[int(x) for x in action_ids['A4']]; a5=[int(x) for x in action_ids['A5']]; b4=[int(x) for x in action_ids['B4']]; b5=[int(x) for x in action_ids['B5']]
    L4=max(len(a4),len(b4)); L5=max(len(a5),len(b5)); n5=[NEUTRAL_CYCLE[i%len(NEUTRAL_CYCLE)] for i in range(L5)]
    def assemble(shared:Sequence[int],s4:Sequence[int],s5:Sequence[int])->list[int]: return [*map(int,prefix),*map(int,shared),*NEWLINE_IDS,*_pad(s4,L4),*NEWLINE_IDS,*_pad(s5,L5),*NEWLINE_IDS,*SOURCE_END_IDS]
    if condition=='ACTIVE': A,B=assemble(sh,a4,a5),assemble(sh,b4,b5)
    elif condition=='NEXT_DIVERGENT_ACTION_ONLY': A,B=assemble(sh,a4,n5),assemble(sh,b4,n5)
    elif condition=='ACTION_HISTORY_MATCHED_NULL':
        ns=[NEUTRAL_CYCLE[i%len(NEUTRAL_CYCLE)] for i in range(len(sh))]; z4=[NEUTRAL_CYCLE[i%len(NEUTRAL_CYCLE)] for i in range(L4)]
        A,B=assemble(sh,z4,n5),assemble(ns,z4,n5)
    elif condition=='FUTURE_TOKEN_DERANGED':
        d=validate_future_segments_constructible(action_ids); A=assemble(sh,d['A4'],d['A5']); B=assemble(sh,d['B4'],d['B5'])
    else: raise RuntimeContractError(f'UNKNOWN_SOURCE_CONDITION:{condition}')
    if len(A)!=len(B) or A[-len(SOURCE_END_IDS):]!=list(SOURCE_END_IDS) or B[-len(SOURCE_END_IDS):]!=list(SOURCE_END_IDS): raise RuntimeContractError('SOURCE_GEOMETRY_DRIFT')
    return A,B
def capture_pair_residual(model:Any,A:Sequence[int],B:Sequence[int],layer:int)->Any:
    a=capture_activation_ids(model,A,int(layer),-1).detach().float().cpu(); b=capture_activation_ids(model,B,int(layer),-1).detach().float().cpu(); return a-b
def rescale(v:Any,target:float):
    import torch
    x=torch.as_tensor(v,dtype=torch.float32).detach().cpu(); n=float(torch.linalg.vector_norm(x).item())
    if target<=1e-8: return torch.zeros_like(x)
    if n<=1e-12: raise RuntimeContractError('REQUIRED_CONTROL_ZERO_NORM')
    y=x*(target/n); got=float(torch.linalg.vector_norm(y).item())
    if abs(got-target)>max(1e-5,1e-4*target): raise RuntimeContractError('CONTROL_NORM_MISMATCH')
    return y
def score_margin(session:PersistentTokenSession,tok:Any,a:str,b:str)->float:
    sm=action_suffixes(tok,[a,b]); _best,rows=session.score_candidates(sm); return float(rows[a].mean_logprob-rows[b].mean_logprob)
def reference_margin(session:PersistentTokenSession,tok:Any,reference:str,commands:Sequence[str])->float:
    cmds=sorted(str(x) for x in commands)
    if reference not in cmds or len(cmds)<2: raise RuntimeContractError('REFERENCE_MARGIN_UNDEFINED')
    _best,rows=session.score_candidates(action_suffixes(tok,cmds)); ref=float(rows[reference].mean_logprob); return ref-max(float(v.mean_logprob) for k,v in rows.items() if k!=reference)
