#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, math, os, sys, tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT=Path(__file__).resolve().parent
PACKETS=ROOT/'results/science/plancarry_replay_residual_t1_user_override_dev_packets_v1'
GATE=ROOT/'results/science/plancarry_replay_residual_t1_user_override_dev_gate_v1.json'
PAYLOAD_OUT=ROOT/'results/science/plancarry_replay_residual_t1_user_override_development_grid_v1.json'
SEAL_OUT=ROOT/'results/science/plancarry_replay_residual_t1_user_override_development_selection_v1.json'
AUDIT_OUT=ROOT/'results/science/plancarry_replay_residual_t1_user_override_development_execution_audit_v1.json'
T1_PREREG_SHA='77a7d9c9ee597551da8e8ef0b8a2c79038990968e3f62735ff90ed8c9c7d55e2'
GAP_SHA='8cd22aff1d89b7a54eaa07b833dc75ecc1286f6938e39ee72256dd9705cba895'
V21_SHA='83370fbfc65c4818ada159a0e3c83cf778b88ed02f964bcf7887e5cea3843158'
SESSION_SHA='585e44ec5cd2395be0804b865de85ac36c5db79117cf4061566cf16a9749e3b6'
PHASE_SHA='c5c412c9440df857202d6137d2f5c2a1068f364c9ef15487c67154764d21afd8'
DRIVER_KIND='PLANCARRY_REPLAYRESIDUAL_T1_DIRECT_OVERRIDE_CAUSAL_DEV_V1'
OVERRIDE_STATUS='USER_DIRECTED_SANITY_GATE_OVERRIDE'
OVERRIDE_SELECTION_KIND='PLANCARRY_REPLAY_RESIDUAL_T1_USER_OVERRIDE_DEVELOPMENT_SELECTION_V1'
OVERRIDE_SELECTION_STATUS='FROZEN_T1_DEVELOPMENT_SELECTION_USER_DIRECTED_SANITY_GATE_OVERRIDE'
LAYERS=(7,14,21,27)
ALPHAS=(0.25,0.5,1.0)
CONDITIONS=('PLAN_PRESENT','NEUTRAL_FILLER','SHUFFLED_PLAN','UNRELATED_PLAN','GENERIC_HISTORY','NEXT_ACTION_PRESERVED_LATE_NULL')
SPEC_CONTROLS=('RANDOM_EQ_NORM','NEXT_ACTION_PRESERVED_LATE_NULL','UNRELATED_PLAN','SHUFFLED_PLAN','GENERIC_HISTORY')


def sha_bytes(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def sha_text(s:str)->str: return sha_bytes(s.encode())
def canonical(obj:Any)->bytes: return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha_json(obj:Any)->str: return sha_bytes(canonical(obj))
def file_sha(p:Path)->str: return sha_bytes(p.read_bytes())
def pretty_json_bytes(obj:Any)->bytes: return (json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def pretty_json_sha(obj:Any)->str: return sha_bytes(pretty_json_bytes(obj))

def _override_inner_selection_path(public_path:Path)->Path:
    return public_path.with_name('.'+public_path.name+'.phase_selection.private')

def validate_override_development_seal_obj(seal:Mapping[str,Any])->dict[str,Any]:
    if seal.get('kind')!=OVERRIDE_SELECTION_KIND or seal.get('status')!=OVERRIDE_SELECTION_STATUS:
        raise RuntimeError('DIRECT_OVERRIDE_SELECTION_KIND_OR_STATUS_INVALID')
    pc=seal.get('prereg_compliance')
    if not isinstance(pc,Mapping) or pc.get('status')!=OVERRIDE_STATUS:
        raise RuntimeError('DIRECT_OVERRIDE_PREREG_COMPLIANCE_MISSING')
    if pc.get('original_sanity_pass_observed') is not False or pc.get('original_prereg_activation_gate_satisfied') is not False:
        raise RuntimeError('DIRECT_OVERRIDE_ORIGINAL_SANITY_PROVENANCE_INVALID')
    if seal.get('user_directed_sanity_gate_override') is not True or seal.get('original_sanity_pass_observed') is not False or seal.get('original_prereg_activation_gate_satisfied') is not False:
        raise RuntimeError('DIRECT_OVERRIDE_TOP_LEVEL_PROVENANCE_INVALID')
    if seal.get('compatibility_sanity_status')!='PASS_REPLAY_RESIDUAL_SANITY':
        raise RuntimeError('DIRECT_OVERRIDE_COMPATIBILITY_SENTINEL_INVALID')
    if seal.get('t1_prereg_sha256')!=T1_PREREG_SHA or seal.get('gap_matrix_sha256')!=GAP_SHA or seal.get('v2_1_contract_sha256')!=V21_SHA:
        raise RuntimeError('DIRECT_OVERRIDE_PROTOCOL_PROVENANCE_INVALID')
    if seal.get('phase_runner_sha256')!=PHASE_SHA or seal.get('session_runtime_sha256')!=SESSION_SHA:
        raise RuntimeError('DIRECT_OVERRIDE_RUNTIME_PROVENANCE_INVALID')
    driver_sha=str(seal.get('driver_sha256',''))
    if len(driver_sha)!=64 or any(c not in '0123456789abcdef' for c in driver_sha):
        raise RuntimeError('DIRECT_OVERRIDE_DRIVER_PROVENANCE_INVALID')
    if seal.get('scientific_result')!='NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY':
        raise RuntimeError('DIRECT_OVERRIDE_SCIENTIFIC_SCOPE_INVALID')
    for flag in ('confirmation_accessed','t1r_accessed','valid_seen_accessed','valid_unseen_accessed'):
        if seal.get(flag) is not False: raise RuntimeError(f'DIRECT_OVERRIDE_FUTURE_FLAG_INVALID:{flag}')
    inner=seal.get('phase_selection')
    if not isinstance(inner,Mapping): raise RuntimeError('DIRECT_OVERRIDE_INNER_SELECTION_MISSING')
    inner_sha=str(seal.get('phase_selection_file_sha256',''))
    if len(inner_sha)!=64 or pretty_json_sha(dict(inner))!=inner_sha:
        raise RuntimeError('DIRECT_OVERRIDE_INNER_SELECTION_HASH_MISMATCH')
    if inner.get('kind')!='PLANCARRY_REPLAY_RESIDUAL_T1_DEVELOPMENT_SELECTION_V1' or inner.get('status')!='FROZEN_T1_DEVELOPMENT_SELECTION':
        raise RuntimeError('DIRECT_OVERRIDE_INNER_SELECTION_INVALID')
    for key in ('selected_layer','selected_alpha','selected_vector_sha256_by_family','selected_vector_map_sha256','all_grid_aggregates','all_grid_aggregates_sha256','development_payload_sha256'):
        if seal.get(key)!=inner.get(key): raise RuntimeError(f'DIRECT_OVERRIDE_MIRROR_MISMATCH:{key}')
    return dict(seal)

def load_validate_override_development_seal(path:Path, expected_file_sha256:str|None=None)->dict[str,Any]:
    if not path.is_file(): raise RuntimeError(f'DIRECT_OVERRIDE_SELECTION_MISSING:{path}')
    actual=file_sha(path)
    if expected_file_sha256 is not None and actual!=str(expected_file_sha256):
        raise RuntimeError('DIRECT_OVERRIDE_SELECTION_FILE_HASH_MISMATCH')
    seal=json.loads(path.read_text())
    return validate_override_development_seal_obj(seal)

def write_override_development_selection(payload:Mapping[str,Any], phase:Any, public_path:Path)->dict[str,Any]:
    if public_path.exists(): raise RuntimeError(f'REFUSE_EXISTING:{public_path}')
    inner_path=_override_inner_selection_path(public_path)
    if inner_path.exists(): raise RuntimeError(f'REFUSE_EXISTING_PRIVATE_PHASE_SELECTION:{inner_path}')
    try:
        result=phase.select_development(payload,inner_path)
        if result.get('status')!='FROZEN_T1_DEVELOPMENT_SELECTION':
            return dict(result)
        if not inner_path.is_file(): raise RuntimeError('PRIVATE_PHASE_SELECTION_NOT_WRITTEN')
        inner_raw=inner_path.read_bytes(); inner_sha=sha_bytes(inner_raw); inner=json.loads(inner_raw)
        if result.get('seal_file_sha256')!=inner_sha: raise RuntimeError('PRIVATE_PHASE_SELECTION_RETURNED_HASH_MISMATCH')
        if pretty_json_sha(inner)!=inner_sha: raise RuntimeError('PRIVATE_PHASE_SELECTION_SERIALIZATION_MISMATCH')
        pc=dict(payload.get('prereg_compliance') or {})
        envelope={
            'kind':OVERRIDE_SELECTION_KIND,'status':OVERRIDE_SELECTION_STATUS,
            'prereg_compliance':pc,'user_directed_sanity_gate_override':True,
            'original_sanity_pass_observed':False,'original_prereg_activation_gate_satisfied':False,
            'compatibility_sanity_status':str(payload.get('sanity_status')),
            't1_prereg_sha256':T1_PREREG_SHA,'gap_matrix_sha256':GAP_SHA,'v2_1_contract_sha256':V21_SHA,
            'session_runtime_sha256':SESSION_SHA,'phase_runner_sha256':PHASE_SHA,
            'driver_kind':DRIVER_KIND,'driver_sha256':str(payload.get('driver_sha256')),
            'development_payload_sha256':inner.get('development_payload_sha256'),
            'phase_selection_file_sha256':inner_sha,'phase_selection':inner,
            'selected_layer':inner.get('selected_layer'),'selected_alpha':inner.get('selected_alpha'),
            'selected_vector_sha256_by_family':inner.get('selected_vector_sha256_by_family'),
            'selected_vector_map_sha256':inner.get('selected_vector_map_sha256'),
            'all_grid_aggregates':inner.get('all_grid_aggregates'),'all_grid_aggregates_sha256':inner.get('all_grid_aggregates_sha256'),
            'qualified_indices':inner.get('qualified_indices'),'qualified_count':inner.get('qualified_count'),
            'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY',
            'confirmation_accessed':False,'t1r_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,
        }
        validate_override_development_seal_obj(envelope)
        public_sha=atomic_json_new(public_path,envelope)
        out=dict(envelope); out['seal_file_sha256']=public_sha
        return out
    finally:
        try: inner_path.unlink()
        except FileNotFoundError: pass

def atomic_json_new(path:Path,obj:Any)->str:
    if path.exists(): raise RuntimeError(f'REFUSE_EXISTING:{path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    tmp=path.with_name('.'+path.name+f'.tmp.{os.getpid()}.{sha_bytes(raw)[:12]}')
    with open(tmp,'xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    try: os.link(tmp,path)
    except FileExistsError as e: raise RuntimeError(f'REFUSE_EXISTING:{path}') from e
    finally:
        try: tmp.unlink()
        except FileNotFoundError: pass
    dfd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return sha_bytes(raw)

def load_terminal_packets(tok:Any):
    from replay_residual_natural_packet_validator_v2_1 import validate_packet_directory
    if not GATE.is_file() or not PACKETS.is_dir(): raise RuntimeError('DEV_GATE_OR_PACKET_SET_MISSING')
    gate=json.loads(GATE.read_text())
    if gate.get('status')!='T1_DEVELOPMENT_READY_FOR_CAUSAL_GRID':
        raise RuntimeError(f"DEV_GATE_NOT_READY:{gate.get('status')}")
    if gate.get('qualified_count',0)<16 or gate.get('original_prereg_sanity_activation_gate_satisfied') is not False or gate.get('user_directed_override') is not True:
        raise RuntimeError('DEV_GATE_OVERRIDE_PROVENANCE_INVALID')
    validate_packet_directory(PACKETS,tok,ROOT)
    packets=[json.loads((PACKETS/f'packet_{i:02d}.json').read_text()) for i in range(32)]
    if [int(x['frozen_index']) for x in packets]!=list(range(32)): raise RuntimeError('DEV_PACKET_INDEX_DRIFT')
    q=[x for x in packets if bool(x.get('qualified'))]
    if len(q)!=int(gate['qualified_count']): raise RuntimeError('DEV_GATE_PACKET_QUALIFIED_COUNT_MISMATCH')
    return gate,packets

def exact_reset_tokens(tok:Any, packet:Mapping[str,Any], observation:str, commands:Sequence[str]):
    import replay_residual_sanity_protocol_v1 as sp
    block=(
        'TASK\n'+str(packet['task_instruction']).strip()+
        '\nCURRENT OBSERVATION\n'+str(observation).strip()+
        '\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+
        '\n<STATE_END>'
    )
    full=block+'\nACTION:'
    ids=sp.tok_encode(tok,full)
    candidates=[]
    for k in range(1,len(ids)):
        pre=sp.tok_decode(tok,ids[:k]); tail=sp.tok_decode(tok,ids[k:])
        if pre.endswith('<STATE_END>\n') and tail=='ACTION:': candidates.append(k)
    if len(candidates)!=1: raise RuntimeError(f'RESET_ACTION_TOKEN_SPLIT_NOT_UNIQUE:{candidates}')
    k=candidates[0]
    if sp.tok_decode(tok,ids)!=full: raise RuntimeError('RESET_FULL_TOKEN_ROUNDTRIP_FAILED')
    return block,full,ids[:k],ids[k:]

def make_runtime(packet:Mapping[str,Any]):
    from alfworld_runtime import AlfRuntime, DATA_ROOT
    return AlfRuntime(str(DATA_ROOT/str(packet['game_path'])),max_steps=14)

def replay_to_reset(packet:Mapping[str,Any]):
    rt=make_runtime(packet)
    try:
        if len(packet['actions'])<4: raise RuntimeError('REFERENCE_TOO_SHORT')
        for j,row in enumerate(packet['actions'][:2]):
            before=rt.hash()
            if before!=row['pre_state_hash']: raise RuntimeError(f'REPLAY_PRESTATE_MISMATCH:{j}')
            out=rt.step(str(row['command']))
            if out.error: raise RuntimeError(f'REPLAY_ACTION_ERROR:{j}:{out.error}')
            if out.state_hash!=row['post_state_hash']: raise RuntimeError(f'REPLAY_POSTSTATE_MISMATCH:{j}')
        return rt
    except Exception:
        rt.close(); raise

def source_vectors(tok:Any,model:Any,packet:Mapping[str,Any],donor_plan:str):
    import torch
    import replay_residual_sanity_protocol_v1 as sp
    from replay_residual_t1_session_runtime_v1 import capture_activation_ids, vector_sha256_fp32
    slots=sp.build_condition_slots(tok,dict(packet),donor_plan,2)
    ids_by={c:sp.build_replay(tok,dict(packet),slots[c],2)[1] for c in CONDITIONS}
    lens={len(v) for v in ids_by.values()}
    if len(lens)!=1: raise RuntimeError(f'SOURCE_REPLAY_ALIGNMENT_FAILED:{sorted(lens)}')
    out={}
    for layer in LAYERS:
        h={c:capture_activation_ids(model,ids_by[c],layer,-1).detach().float().cpu() for c in CONDITIONS}
        neutral=h['NEUTRAL_FILLER']
        raw=h['PLAN_PRESENT']-neutral
        residuals={c:h[c]-neutral for c in CONDITIONS if c not in ('PLAN_PRESENT','NEUTRAL_FILLER')}
        out[layer]={'active':raw,'controls':residuals,'active_sha256':vector_sha256_fp32(raw),'active_l2':float(torch.linalg.vector_norm(raw).item())}
    return out

def rescale_to(v:Any,target:float):
    import torch
    x=v.detach().float().cpu()
    n=float(torch.linalg.vector_norm(x).item())
    if target<=1e-8: return torch.zeros_like(x), True
    if n<=1e-12: return torch.zeros_like(x), False
    y=x*(float(target)/n)
    got=float(torch.linalg.vector_norm(y).item())
    ok=abs(got-target)<=max(1e-5,1e-4*target)
    return y,ok

def rademacher_like(dim:int,target:float,key:str):
    import torch
    signs=[]; counter=0
    while len(signs)<dim:
        b=hashlib.sha256(f'{key}|{counter}'.encode()).digest(); counter+=1
        for byte in b:
            for bit in range(8):
                signs.append(1.0 if ((byte>>bit)&1) else -1.0)
                if len(signs)>=dim: break
            if len(signs)>=dim: break
    x=torch.tensor(signs,dtype=torch.float32)
    if target<=1e-8: return torch.zeros_like(x)
    x=x/torch.linalg.vector_norm(x)*float(target)
    return x

def suffix_map(tok:Any,commands:Sequence[str]):
    out={}
    for c in sorted(str(x) for x in commands):
        ids=[int(x) for x in tok.encode(' '+c,add_special_tokens=False)]
        if not ids: raise RuntimeError('EMPTY_ACTION_SUFFIX')
        out[c]=ids
    return out

def continuation_ids(tok:Any,observation:str,commands:Sequence[str]):
    import replay_residual_sanity_protocol_v1 as sp
    text=('\nOBSERVATION: '+str(observation).strip()+
          '\nADMISSIBLE COMMANDS\n'+'\n'.join(sorted(str(x) for x in commands))+'\nACTION:')
    ids=sp.tok_encode(tok,text)
    if not ids: raise RuntimeError('EMPTY_CONTINUATION_IDS')
    return ids

def base_reset_provenance(tok:Any,packet:Mapping[str,Any]):
    from replay_residual_t1_session_runtime_v1 import token_ids_sha256
    rt=replay_to_reset(packet)
    try:
        obs=str(rt.observation); commands=sorted(str(x) for x in rt.admissible_commands); state=rt.hash()
        block,full,prefix,action_prompt=exact_reset_tokens(tok,packet,obs,commands)
        remaining=list(packet['actions'][2:])
        return {
            'observation':obs,'commands':commands,'state_hash':state,'block':block,'full':full,'prefix_ids':prefix,'action_prompt_ids':action_prompt,
            'reset_prefix_sha256':token_ids_sha256(prefix),'reset_world_state_sha256':state,
            'reset_serialization_sha256':sha_text(full),'task_instruction_sha256':sha_text(str(packet['task_instruction']).strip()),
            'reset_observation_sha256':sha_text(obs),'admissible_actions_sha256':sha_json(commands),
            'reference_world_state_sequence_sha256':sha_json([str(x['pre_state_hash']) for x in remaining]),
            'reference_remaining_action_count':len(remaining),
        }
    finally: rt.close()

def engineering_sentinels(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any]):
    import torch
    from replay_residual_t1_session_runtime_v1 import PersistentTokenSession,capture_activation_ids
    zmax=0.0; smax=0.0
    hidden=int(model.config.hidden_size)
    for layer in LAYERS:
        base_s=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=None)
        zero_s=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=torch.zeros(hidden,dtype=torch.float32),scale=1.0)
        self_vec=capture_activation_ids(model,base['prefix_ids'],layer,-1).detach().float().cpu()
        self_s=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=self_vec,mode='replace',scale=1.0)
        try:
            for s in (base_s,zero_s,self_s): s.append_ids(base['action_prompt_ids'],event='ACTION_PROMPT_SENTINEL')
            zmax=max(zmax,float(torch.max(torch.abs(zero_s.next_logits-base_s.next_logits)).item()))
            smax=max(smax,float(torch.max(torch.abs(self_s.next_logits-base_s.next_logits)).item()))
        finally:
            for s in (base_s,zero_s,self_s):
                if not s.closed: s.close()
    if zmax>1e-6 or smax>1e-6: raise RuntimeError(f'ENGINEERING_SENTINEL_FAIL:zero={zmax}:self={smax}')
    return {'zero_add_no_patch_maxabs':zmax,'self_replace_no_patch_maxabs':smax}

def rollout(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,arm:str,norm_guard:bool):
    from replay_residual_t1_session_runtime_v1 import PersistentTokenSession
    rt=replay_to_reset(packet)
    sess=None
    actions=[]; accepted=0
    try:
        if rt.hash()!=base['state_hash'] or str(rt.observation)!=base['observation'] or sorted(str(x) for x in rt.admissible_commands)!=base['commands']:
            raise RuntimeError('ARM_RESET_STATE_MISMATCH')
        sess=PersistentTokenSession(model,base['prefix_ids'],layer=layer,vector=vector,mode='add',scale=float(alpha) if vector is not None else 1.0)
        sess.append_ids(base['action_prompt_ids'],event='ACTION_PROMPT_0')
        for step in range(12):
            if bool(rt.done) or bool(rt.won): break
            commands=sorted(str(x) for x in rt.admissible_commands)
            if not commands: break
            pre=rt.hash()
            cmd,scores,_commit=sess.choose_and_commit(suffix_map(tok,commands),event=f'ACTION_{step+1}')
            rec=rt.step(cmd)
            ok=rec.error is None
            accepted+=int(ok)
            actions.append({'command':cmd,'pre_state_hash':pre,'post_state_hash':rec.state_hash,'accepted':ok})
            if not ok: break
            if bool(rt.done) or bool(rt.won): break
            sess.append_ids(continuation_ids(tok,rt.observation,rt.admissible_commands),event=f'OBSERVATION_AND_ACTION_PROMPT_{step+1}')
        ref=list(packet['actions'][2:]); m=len(ref)
        if m<2: raise RuntimeError('REFERENCE_REMAINING_LT2')
        matches=0
        for j in range(1,m):
            if j<len(actions) and actions[j]['command']==str(ref[j]['command']) and actions[j]['pre_state_hash']==str(ref[j]['pre_state_hash']): matches+=1
        lpa=float(matches/(m-1))
        prov=sess.close(); sess=None
        return {
            'lpa':lpa,'task_success':1.0 if bool(rt.won) else 0.0,'valid_action_rate':float(accepted/len(actions)) if actions else 0.0,
            'hook_count':int(prov['hook_count']),'vector_norm_guard_passed':bool(norm_guard),
            'reset_prefix_sha256':base['reset_prefix_sha256'],'reset_world_state_sha256':base['reset_world_state_sha256'],
            'reset_serialization_sha256':base['reset_serialization_sha256'],'task_instruction_sha256':base['task_instruction_sha256'],
            'reset_observation_sha256':base['reset_observation_sha256'],'admissible_actions_sha256':base['admissible_actions_sha256'],
            'world_state_match_enforced':True,'lpa_excludes_first_action':True,
            'session_id_hash':prov['session_id_hash'],'injected_vector_sha256':prov['injected_vector_sha256'],
            'generated_action_count':len(actions),'first_action_match':bool(actions and actions[0]['command']==str(ref[0]['command'])),
        }
    finally:
        if sess is not None and not sess.closed:
            try:sess.close()
            except Exception:pass
        rt.close()

def make_family_base(tok:Any,model:Any,packet:Mapping[str,Any]):
    base=base_reset_provenance(tok,packet)
    sent=engineering_sentinels(tok,model,packet,base)
    return {
        'index':int(packet['frozen_index']),'qualified':True,
        'reset_prefix_sha256':base['reset_prefix_sha256'],'reset_world_state_sha256':base['reset_world_state_sha256'],
        'reset_serialization_sha256':base['reset_serialization_sha256'],'task_instruction_sha256':base['task_instruction_sha256'],
        'reset_observation_sha256':base['reset_observation_sha256'],'admissible_actions_sha256':base['admissible_actions_sha256'],
        'reference_world_state_sequence_sha256':base['reference_world_state_sequence_sha256'],
        'reference_remaining_action_count':base['reference_remaining_action_count'],'primary_endpoint':'later_plan_agreement_LPA',
        'lpa_excludes_first_action':True,'world_state_match_enforced':True,'engineering_sentinels':sent,
    },base

def main()->int:
    if PAYLOAD_OUT.exists() or SEAL_OUT.exists() or AUDIT_OUT.exists(): raise RuntimeError('CAUSAL_DEV_OUTPUT_EXISTS')
    # Exact reviewed code identities must not drift.
    required={
      ROOT/'replay_residual_t1_session_runtime_v1.py':SESSION_SHA,
      ROOT/'replay_residual_t1_phase_runner_v1.py':PHASE_SHA,
      ROOT/'results/design/plancarry_replay_residual_t1_prereg_v1_1_20260821.json':T1_PREREG_SHA,
      ROOT/'results/design/plancarry_replay_residual_unified_execution_contract_v2_1_rw_20260821.json':V21_SHA,
    }
    for path,expected in required.items():
        got=file_sha(path)
        if got!=expected: raise RuntimeError(f'FROZEN_SOURCE_DRIFT:{path}:{got}:{expected}')
    import torch
    import replay_residual_natural_packet_producer_v2_1 as p
    import replay_residual_sanity_protocol_v1 as sp
    import replay_residual_t1_phase_runner_v1 as phase
    from replay_residual_textworld_py313_compat_v1 import make_runtime_factory
    from replay_residual_t1_session_runtime_v1 import vector_sha256_fp32
    p.default_runtime_factory=make_runtime_factory(p.default_runtime_factory)
    tok,model,model_prov=p.load_production_runtime(ROOT)
    gate,packets=load_terminal_packets(tok)
    by_idx={int(x['frozen_index']):x for x in packets}
    qualified=[int(x['frozen_index']) for x in packets if bool(x.get('qualified'))]
    families=[]; bases={}; source={}; vector_map={}
    for idx in range(32):
        packet=by_idx[idx]
        if idx not in qualified:
            families.append({'index':idx,'qualified':False}); continue
        donor_idx=int(packet['control_provenance']['unrelated_donor_frozen_index'])
        if donor_idx not in by_idx or donor_idx==idx: raise RuntimeError(f'UNRELATED_DONOR_INVALID:{idx}:{donor_idx}')
        donor_plan=str(by_idx[donor_idx]['plan_text'])
        fam,base=make_family_base(tok,model,packet); families.append(fam); bases[idx]=base
        source[idx]=source_vectors(tok,model,packet,donor_plan)
        vector_map[str(idx)]={str(layer):source[idx][layer]['active_sha256'] for layer in LAYERS}
        print(json.dumps({'stage':'source_capture','qualified_family_done':qualified.index(idx)+1,'qualified_total':len(qualified)}),flush=True)
    # NO_PATCH is independent of layer/alpha and is exactly reused under deterministic identical reset/session.
    no_patch={}
    for pos,idx in enumerate(qualified,1):
        no_patch[idx]=rollout(tok,model,by_idx[idx],bases[idx],7,None,1.0,'NO_PATCH',False)
        print(json.dumps({'stage':'no_patch','family_done':pos,'qualified_total':len(qualified)}),flush=True)
    grids={}
    for layer in LAYERS:
        for alpha in ALPHAS:
            key=phase.grid_key(layer,alpha); rows={}
            for pos,idx in enumerate(qualified,1):
                packet=by_idx[idx]; sv=source[idx][layer]; raw=sv['active']; raw_norm=float(sv['active_l2'])
                controls={}; guard={}
                for arm,cond in [('NEXT_ACTION_PRESERVED_LATE_NULL','NEXT_ACTION_PRESERVED_LATE_NULL'),('UNRELATED_PLAN','UNRELATED_PLAN'),('SHUFFLED_PLAN','SHUFFLED_PLAN'),('GENERIC_HISTORY','GENERIC_HISTORY')]:
                    controls[arm],guard[arm]=rescale_to(sv['controls'][cond],raw_norm)
                rand=rademacher_like(int(raw.numel()),raw_norm,f"ReplayResidual|RANDOM_EQ_NORM|{packet['family']}|{packet['game_path']}|L{layer}")
                import torch
                rand_guard=raw_norm<=1e-8 or abs(float(torch.linalg.vector_norm(rand).item())-raw_norm)<=max(1e-5,1e-4*raw_norm)
                arms={
                    'ACTIVE_PLAN_RESIDUAL':rollout(tok,model,packet,bases[idx],layer,raw,alpha,'ACTIVE_PLAN_RESIDUAL',True),
                    'NO_PATCH':dict(no_patch[idx]),
                    'RANDOM_EQ_NORM':rollout(tok,model,packet,bases[idx],layer,rand,alpha,'RANDOM_EQ_NORM',rand_guard),
                }
                for arm in ('NEXT_ACTION_PRESERVED_LATE_NULL','UNRELATED_PLAN','SHUFFLED_PLAN','GENERIC_HISTORY'):
                    if not guard[arm]: raise RuntimeError(f'CONTROL_RESIDUAL_ZERO_OR_NORM_GUARD_FAIL:{idx}:{layer}:{arm}')
                    arms[arm]=rollout(tok,model,packet,bases[idx],layer,controls[arm],alpha,arm,guard[arm])
                rows[str(idx)]={'active_raw_residual_l2':raw_norm,'arms':arms}
                print(json.dumps({'stage':'causal_grid','layer':layer,'alpha':alpha,'family_done':pos,'qualified_total':len(qualified)}),flush=True)
            grids[key]=rows
    payload={
        'phase':'T1_DEVELOPMENT',
        # Compatibility literal required by the independently reviewed phase validator. The actual gate is explicitly overridden below.
        'sanity_status':phase.SANITY_REQUIRED,
        'prereg_compliance':{'status':'USER_DIRECTED_SANITY_GATE_OVERRIDE','original_sanity_pass_observed':False,'original_prereg_activation_gate_satisfied':False},
        't1_prereg_sha256':T1_PREREG_SHA,'gap_matrix_sha256':GAP_SHA,'v2_1_contract_sha256':V21_SHA,
        'session_runtime_sha256':SESSION_SHA,'phase_runner_sha256':PHASE_SHA,'source_anchor':phase.SOURCE_ANCHOR,'target_site':phase.TARGET_SITE,
        'families':families,'vector_sha256_by_family_layer':vector_map,'grid_results':grids,
        'model_provenance':dict(model_prov),'dev_gate_sha256':file_sha(GATE),'dev_packet_manifest_sha256':file_sha(PACKETS/'manifest.json'),
        'driver_kind':DRIVER_KIND,'driver_sha256':file_sha(Path(__file__)),'confirmation_accessed':False,'t1r_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,
    }
    payload_sha=atomic_json_new(PAYLOAD_OUT,payload)
    result=write_override_development_selection(payload,phase,SEAL_OUT)
    if result.get('status')!=OVERRIDE_SELECTION_STATUS: raise RuntimeError(f"UNEXPECTED_SELECTION_RESULT:{result}")
    load_validate_override_development_seal(SEAL_OUT,result['seal_file_sha256'])
    audit={
      'kind':'PLANCARRY_REPLAYRESIDUAL_T1_DIRECT_OVERRIDE_DEVELOPMENT_EXECUTION_AUDIT_V1','driver_sha256':file_sha(Path(__file__)),
      'payload_sha256':payload_sha,'seal_sha256':file_sha(SEAL_OUT),'inner_phase_selection_sha256':result['phase_selection_file_sha256'],
      'qualified_count':len(qualified),'selected_layer':result['selected_layer'],'selected_alpha':result['selected_alpha'],
      'prereg_compliance':{'status':OVERRIDE_STATUS,'original_sanity_pass_observed':False,'original_prereg_activation_gate_satisfied':False},
      'compatibility_sanity_status':phase.SANITY_REQUIRED,
      'user_directed_sanity_gate_override':True,'original_prereg_sanity_activation_gate_satisfied':False,'confirmation_accessed':False,'t1r_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,
      'scientific_interpretation':'Exploratory direct-override development selection only; no confirmatory T1 claim until untouched confirmation32..51 executes under this frozen operating point and binds the override-specific seal envelope.'
    }
    audit_sha=atomic_json_new(AUDIT_OUT,audit)
    print(json.dumps({'T1_CAUSAL_DEV_TERMINAL':{'status':result['status'],'prereg_compliance_status':OVERRIDE_STATUS,'original_sanity_pass_observed':False,'original_prereg_activation_gate_satisfied':False,'compatibility_sanity_status':phase.SANITY_REQUIRED,'qualified_count':result['qualified_count'],'selected_layer':result['selected_layer'],'selected_alpha':result['selected_alpha'],'seal_file_sha256':result['seal_file_sha256'],'inner_phase_selection_sha256':result['phase_selection_file_sha256']},'payload_sha256':payload_sha,'audit_sha256':audit_sha}),flush=True)
    return 0

if __name__=='__main__': raise SystemExit(main())
