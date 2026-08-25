#!/usr/bin/env python3
"""Execution-ready ActionMatched FuturePlan v1 driver.

IMPORTANT: importing or running --phase preflight performs no model load and no
ALFWorld game reset. Development/confirmation are explicit scientific execution
entry points and must later be bound to a canonical ResearchDecision.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

import action_matched_future_plan_phase_runner_v1 as phase
import action_matched_future_plan_runtime_v1 as am
import localcontinuation_science_driver_v1 as lc

ROOT=Path(__file__).resolve().parent
DEV_PACKET_DIR=Path('results/science/plancarry_action_matched_future_plan_development_packets_v1')
DEV_PAYLOAD=Path('results/science/plancarry_action_matched_future_plan_development_grid_v1.json')
DEV_SEAL=Path('results/science/plancarry_action_matched_future_plan_development_selection_v1.json')
DEV_TERMINAL=Path('results/science/plancarry_action_matched_future_plan_development_terminal_v1.json')
CONF_PACKET_DIR=Path('results/science/plancarry_action_matched_future_plan_confirmation_packets_v1')
CONF_PAYLOAD=Path('results/science/plancarry_action_matched_future_plan_confirmation_payload_v1.json')
CONF_RESULT=Path('results/science/plancarry_action_matched_future_plan_confirmation_result_v1.json')
IMPLEMENTATION_REVIEW_REQUIRED=True
PAIR_INSTRUCTION=json.loads((ROOT/am.PREREG_REL).read_text())['plan_pair_generation']['prompt']
POOL={'development':range(0,64),'confirmation':range(64,128)}

class ExecutionContractError(RuntimeError): pass

def _sha(obj:Any)->str: return phase.canonical_sha(obj)
def _rel(path:Path)->Path: return ROOT/path

def _load_population(phase_name:str)->list[dict[str,Any]]:
    am.verify_frozen_design(ROOT)
    data=json.loads(_rel(am.POP_REL).read_text()); rows=[dict(x) for x in data['selected']]
    if [int(x['frozen_index']) for x in rows]!=list(range(160)): raise ExecutionContractError('POPULATION_INDEX_DRIFT')
    if len({str(x['game_path']) for x in rows})!=160: raise ExecutionContractError('POPULATION_DUPLICATE_PATH')
    want=list(POOL[phase_name]); by={int(x['frozen_index']):x for x in rows}; out=[by[i] for i in want]
    expected_label='development_pool' if phase_name=='development' else 'confirmation_pool'
    if any(str(x['phase'])!=expected_label for x in out): raise ExecutionContractError('POPULATION_PHASE_DRIFT')
    return out

def _runtime_factory(game_path:str):
    from alfworld_runtime import AlfRuntime, ACTIVE_DATA_ROOT
    p=Path(str(game_path))
    if p.is_absolute() or '..' in p.parts: raise ExecutionContractError('NONCANONICAL_GAME_PATH')
    return AlfRuntime(str(ACTIVE_DATA_ROOT/p),max_steps=12)

def _extract_task(obs:str)->str:
    from replay_residual_natural_packet_producer_v2_1 import extract_task_instruction
    return extract_task_instruction(obs)
def _nontrivial(cmd:str)->bool:
    from replay_residual_natural_packet_producer_v2_1 import is_nontrivial
    return bool(is_nontrivial(cmd))
def _family(path:str)->str:
    import localcontinuation_packet_builder_v1 as pb
    return pb.family_from_game_path(path)

def load_model(expected_device:str):
    tok,model,prov=lc.load_runtime(expected_device)
    tokenprov=am.verify_tokenizer(tok)
    return tok,model,{**prov,'actionmatched_tokenizer_provenance':tokenprov}

def _reset_runtime(packet:Mapping[str,Any]):
    rt=_runtime_factory(str(packet['game_path']))
    try:
        for j,row in enumerate(packet['pre_cut_actions']):
            if str(rt.hash())!=str(row['pre_state_hash']): raise ExecutionContractError(f'PRECUT_REPLAY_PRESTATE:{j}')
            rec=rt.step(str(row['command']))
            if rec.error or str(rec.state_hash)!=str(row['post_state_hash']): raise ExecutionContractError(f'PRECUT_REPLAY_POSTSTATE:{j}')
        if str(rt.hash())!=str(packet['cut_state_hash']): raise ExecutionContractError('CUT_STATE_REPLAY_MISMATCH')
        return rt
    except Exception:
        rt.close(); raise

def _session_base(tok:Any,packet:Mapping[str,Any])->dict[str,Any]:
    rt=_reset_runtime(packet)
    try:
        obs=str(rt.observation); commands=sorted(str(x) for x in rt.admissible_commands)
        text=am.render_reset(str(packet['task_instruction']),obs,commands); prefix,tail=am.split_reset_action(tok,text)
        return {'prefix_ids':prefix,'action_prompt_ids':tail,'observation':obs,'commands':commands,'state_hash':str(rt.hash()),
                'reset_prefix_sha256':am.token_ids_sha256(prefix),'reset_snapshot_sha256':_sha({'task':packet['task_instruction'],'observation':obs,'commands':commands,'state_hash':str(rt.hash()),'serialization':text})}
    finally: rt.close()

def _choose_two_precut(tok:Any,model:Any,rt:Any,task:str)->list[dict[str,Any]]:
    text=am.render_reset(task,str(rt.observation),sorted(str(x) for x in rt.admissible_commands)); prefix,tail=am.split_reset_action(tok,text)
    sess=am.PersistentTokenSession(model,prefix,layer=0,vector=None); sess.append_ids(tail,event='PRECUT_ACTION_PROMPT_1')
    actions=[]
    try:
        for step in (1,2):
            cmds=[c for c in sorted(str(x) for x in rt.admissible_commands) if _nontrivial(c)]
            if not cmds: raise ExecutionContractError('NO_NONTRIVIAL_ADMISSIBLE_COMMAND')
            best,scores=sess.score_candidates(am.action_suffixes(tok,cmds)); pre=str(rt.hash()); sess.append_ids(am.action_suffixes(tok,[best])[best],event=f'PRECUT_ACTION_{step}')
            rec=rt.step(best)
            if rec.error: raise ExecutionContractError(f'PRECUT_RUNTIME_ERROR:{rec.error}')
            actions.append({'step':step,'command':best,'observation':str(rt.observation),'pre_state_hash':pre,'post_state_hash':str(rec.state_hash),'admissible_commands':cmds,'chosen_mean_logprob':float(scores[best].mean_logprob)})
            if step<2:
                sess.append_ids(am.continuation_ids(tok,str(rt.observation),rt.admissible_commands),event=f'PRECUT_OBS_{step}')
        prov=sess.close(); sess=None
        if prov['hook_count']!=0: raise ExecutionContractError('PRECUT_UNEXPECTED_HOOK')
        return actions
    finally:
        if sess is not None and not sess.closed:
            try:sess.close()
            except Exception:pass

def _branch_records(packet:Mapping[str,Any],branch:str)->dict[str,Any]:
    pair=packet['pair']; rt=_reset_runtime(packet)
    try:
        sh=str(pair['shared_action3'])
        if sh not in rt.admissible_commands or not _nontrivial(sh): raise ExecutionContractError('SHARED_ACTION_INVALID')
        pre3=str(rt.hash()); r3=rt.step(sh)
        if r3.error: raise ExecutionContractError('SHARED_ACTION_ERROR')
        post3=str(rt.hash()); obs3=str(rt.observation); cmds3=sorted(str(x) for x in rt.admissible_commands)
        a4=str(pair[f'{branch}4']); a5=str(pair[f'{branch}5'])
        if a4 not in cmds3 or not _nontrivial(a4): raise ExecutionContractError(f'{branch}4_INVALID')
        pre4=str(rt.hash()); r4=rt.step(a4)
        if r4.error: raise ExecutionContractError(f'{branch}4_ERROR')
        obs4=str(rt.observation); cmds4=sorted(str(x) for x in rt.admissible_commands); post4=str(rt.hash())
        if a5 not in cmds4 or not _nontrivial(a5): raise ExecutionContractError(f'{branch}5_INVALID')
        if len(cmds4)<2: raise ExecutionContractError(f'{branch}5_NO_ALTERNATIVE')
        pre5=str(rt.hash()); r5=rt.step(a5)
        if r5.error: raise ExecutionContractError(f'{branch}5_ERROR')
        return {'shared':{'command':sh,'pre_state_hash':pre3,'post_state_hash':post3,'observation':obs3,'admissible_commands_after':cmds3},
                'a4':{'command':a4,'pre_state_hash':pre4,'post_state_hash':post4,'observation':obs4,'admissible_commands_after':cmds4},
                'a5':{'command':a5,'pre_state_hash':pre5,'post_state_hash':str(rt.hash()),'observation':str(rt.observation)}}
    finally: rt.close()

def produce_pair_attempt(tok:Any,model:Any,row:Mapping[str,Any],model_prov:Mapping[str,Any])->dict[str,Any]:
    packet={'frozen_index':int(row['frozen_index']),'game_path':str(row['game_path']),'phase':str(row['phase']),'family':_family(str(row['game_path'])),
            'eligible':False,'ineligibility_reasons':[],'model_provenance':dict(model_prov)}
    rt=None
    try:
        rt=_runtime_factory(packet['game_path']); initial=str(rt.observation); task=_extract_task(initial); packet['initial_observation']=initial; packet['task_instruction']=task
        actions=_choose_two_precut(tok,model,rt,task); packet['pre_cut_actions']=actions; packet['cut_observation']=str(rt.observation); packet['cut_admissible_commands']=sorted(str(x) for x in rt.admissible_commands); packet['cut_state_hash']=str(rt.hash())
        pair_result=am.pair_plan_once(tok,model,PAIR_INSTRUCTION,task,packet['cut_observation'],actions,packet['cut_admissible_commands']); packet.update(pair_result); pair=packet['pair']
        packet['action_ids_sha256']={k:am.token_ids_sha256(v) for k,v in packet['action_ids'].items()}
        packet['future_derangement_ids']=am.validate_future_segments_constructible(packet['action_ids'])
        packet['future_derangement_ids_sha256']={k:am.token_ids_sha256(v) for k,v in packet['future_derangement_ids'].items()}
        if pair['shared_action3'] not in packet['cut_admissible_commands']: raise ExecutionContractError('PAIR_SHARED_NOT_CUT_ADMISSIBLE')
        if pair['A4']==pair['B4']: raise ExecutionContractError('PAIR_A4_B4_NOT_DISTINCT')
        A=_branch_records(packet,'A'); B=_branch_records(packet,'B')
        if A['shared']!=B['shared']: raise ExecutionContractError('SHARED_BRANCH_REPLAY_MISMATCH')
        packet['branch_A']=A; packet['branch_B']=B
        prefix=am.common_source_prefix(tok,task,packet['cut_observation'],actions,packet['cut_admissible_commands']); packet['source_common_prefix_ids_sha256']=am.token_ids_sha256(prefix); packet['source_common_prefix_ids']=prefix
        for cond in ('ACTIVE','ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY'):
            AA,BB=am.source_condition_ids(prefix,packet['action_ids'],cond)
            packet.setdefault('source_condition_provenance',{})[cond]={'A_ids_sha256':am.token_ids_sha256(AA),'B_ids_sha256':am.token_ids_sha256(BB),'token_count':len(AA),'source_end_position':len(AA)-1,
                                                                                'branch5_source':'neutral_cycle_only' if cond=='NEXT_DIVERGENT_ACTION_ONLY' else 'condition_defined'}
        packet['eligible']=True
    except (ExecutionContractError, am.RuntimeContractError) as exc:
        msg=str(exc)
        allowed=(
            'NO_NONTRIVIAL_ADMISSIBLE_COMMAND','PRECUT_RUNTIME_ERROR:',
            'PAIR_FULLMATCH_REQUIRED','PAIR_EMPTY_ACTION','PAIR_ACTION_EMPTY_IDS',
            'PAIR_SHARED_NOT_CUT_ADMISSIBLE','PAIR_A4_B4_NOT_DISTINCT',
            'SHARED_ACTION_INVALID','SHARED_ACTION_ERROR','A4_INVALID','A4_ERROR','A5_INVALID','A5_ERROR',
            'B4_INVALID','B4_ERROR','B5_INVALID','B5_ERROR','A5_NO_ALTERNATIVE','B5_NO_ALTERNATIVE',
            'SHARED_BRANCH_REPLAY_MISMATCH','DERANGEMENT_UNCONSTRUCTIBLE'
        )
        if not msg.startswith(allowed):
            raise
        packet['ineligibility_reasons']=[f'{type(exc).__name__}:{msg}']
    finally:
        if rt is not None: rt.close()
    packet['packet_semantic_sha256']=_sha({k:v for k,v in packet.items() if k!='packet_semantic_sha256'})
    return packet

def _scan_first20(tok:Any,model:Any,phase_name:str,model_prov:Mapping[str,Any])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    attempts=[]; eligible=[]
    for row in _load_population(phase_name):
        pkt=produce_pair_attempt(tok,model,row,model_prov); attempts.append(pkt)
        print(json.dumps({'stage':'actionmatched_pair_scan','phase':phase_name,'attempted':len(attempts),'eligible':len(eligible)+int(pkt['eligible'])}),flush=True)
        if pkt['eligible']:
            eligible.append(pkt)
            if len(eligible)==20: break
    return attempts,eligible

def _donor_map(eligible:Sequence[Mapping[str,Any]])->dict[int,int]:
    out={}; n=len(eligible)
    for pos,p in enumerate(eligible):
        for d in range(1,n):
            q=eligible[(pos+d)%n]
            if str(q['family'])!=str(p['family']): out[int(p['frozen_index'])]=int(q['frozen_index']); break
        if int(p['frozen_index']) not in out: raise ExecutionContractError('NO_DIFFERENT_FAMILY_DONOR')
    return out

def _source_ids(packet:Mapping[str,Any],condition:str)->tuple[list[int],list[int]]:
    return am.source_condition_ids(packet['source_common_prefix_ids'],packet['action_ids'],condition)

def _capture_vectors(model:Any,packet:Mapping[str,Any],donor:Mapping[str,Any],layer:int)->dict[str,Any]:
    import torch
    activeA,activeB=_source_ids(packet,'ACTIVE'); raw=am.capture_pair_residual(model,activeA,activeB,layer); norm=float(torch.linalg.vector_norm(raw).item())
    out={'ACTIVE':raw,'active_l2':norm,'active_sha256':am.vector_sha256_fp32(raw)}
    for cond in ('ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY'):
        A,B=_source_ids(packet,cond); out[cond]=am.rescale(am.capture_pair_residual(model,A,B,layer),norm)
    dA,dB=_source_ids(donor,'ACTIVE'); out['UNRELATED_PAIR_RESIDUAL']=am.rescale(am.capture_pair_residual(model,dA,dB,layer),norm)
    out['RANDOM_EQ_NORM']=lc.rademacher(int(raw.numel()),norm,f"ReplayResidualLocalContinuation|RANDOM_EQ_NORM|{packet['family']}|{packet['game_path']}|L{int(layer)}")
    return out

def _start_session(model:Any,base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,sign:int=1):
    v=None if vector is None else vector*(1 if sign>0 else -1)
    s=am.PersistentTokenSession(model,base['prefix_ids'],layer=int(layer),vector=v,mode='add',scale=float(alpha) if v is not None else 1.0); s.append_ids(base['action_prompt_ids'],event='ACTION_PROMPT_RESET'); return s

def _teacher_shared(tok:Any,sess:Any,rt:Any,packet:Mapping[str,Any])->None:
    sh=str(packet['pair']['shared_action3']); cmds=sorted(str(x) for x in rt.admissible_commands)
    if sh not in cmds: raise ExecutionContractError('SHARED_NOT_ADMISSIBLE_RUNTIME')
    sess.append_ids(am.action_suffixes(tok,cmds)[sh],event='TEACHER_SHARED_ACTION3'); rec=rt.step(sh)
    if rec.error or str(rec.state_hash)!=str(packet['branch_A']['shared']['post_state_hash']): raise ExecutionContractError('SHARED_REPLAY_STATE_DRIFT')
    sess.append_ids(am.continuation_ids(tok,str(rt.observation),rt.admissible_commands),event='TEACHER_OBS3')

def _a4_margin(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,sign:int)->float:
    rt=_reset_runtime(packet); sess=None
    try:
        sess=_start_session(model,base,layer,vector,alpha,sign); _teacher_shared(tok,sess,rt,packet)
        return am.score_margin(sess,tok,str(packet['pair']['A4']),str(packet['pair']['B4']))
    finally:
        if sess is not None and not sess.closed: sess.close()
        rt.close()

def _a5_margin(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,sign:int,branch:str)->float:
    rt=_reset_runtime(packet); sess=None
    try:
        sess=_start_session(model,base,layer,vector,alpha,sign); _teacher_shared(tok,sess,rt,packet)
        a4=str(packet['pair'][f'{branch}4']); cmds=sorted(str(x) for x in rt.admissible_commands); sess.append_ids(am.action_suffixes(tok,cmds)[a4],event=f'TEACHER_{branch}4'); rec=rt.step(a4)
        exp=packet[f'branch_{branch}']['a4']
        if rec.error or str(rec.state_hash)!=str(exp['post_state_hash']): raise ExecutionContractError(f'{branch}4_REPLAY_STATE_DRIFT')
        sess.append_ids(am.continuation_ids(tok,str(rt.observation),rt.admissible_commands),event=f'TEACHER_{branch}_OBS4')
        return am.reference_margin(sess,tok,str(packet['pair'][f'{branch}5']),rt.admissible_commands)
    finally:
        if sess is not None and not sess.closed: sess.close()
        rt.close()

def _eval_point(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],vectors:Mapping[str,Any],layer:int,alpha:float)->dict[str,Any]:
    arms=('ACTIVE','RANDOM_EQ_NORM','UNRELATED_PAIR_RESIDUAL','ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY')
    a4={'NO_PATCH':_a4_margin(tok,model,packet,base,layer,None,alpha,1)}; a5={'NO_PATCH':{'A':_a5_margin(tok,model,packet,base,layer,None,alpha,1,'A'),'B':_a5_margin(tok,model,packet,base,layer,None,alpha,1,'B')}}
    for arm in arms:
        a4[arm]={'+':_a4_margin(tok,model,packet,base,layer,vectors[arm],alpha,1),'-':_a4_margin(tok,model,packet,base,layer,vectors[arm],alpha,-1)}
        a5[arm]={'+':{'A':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,1,'A'),'B':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,1,'B')},
                 '-':{'A':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,-1,'A'),'B':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,-1,'B')}}
    zmax,smax=lc.sentinels(model,base,layer)
    if zmax>1e-6 or smax>1e-6: raise ExecutionContractError('PLUMBING_SENTINEL_FAIL')
    return {'index':int(packet['frozen_index']),'a4_margins':a4,'a5_margins':a5,'zero_add_no_patch_maxabs':zmax,'self_replace_no_patch_maxabs':smax,'active_residual_sha256':vectors['active_sha256'],'active_residual_l2':vectors['active_l2'],'reset_snapshot_sha256':base['reset_snapshot_sha256']}

def _atomic_packet_set(attempts:Sequence[Mapping[str,Any]],eligible:Sequence[Mapping[str,Any]],target:Path,phase_name:str)->str:
    p=_rel(target)
    if p.exists(): raise ExecutionContractError(f'PACKET_DIR_EXISTS:{p}')
    tmp=p.with_name('.'+p.name+'.inprogress')
    if tmp.exists(): raise ExecutionContractError(f'STALE_PACKET_TEMP:{tmp}')
    tmp.mkdir(parents=True)
    try:
        files=[]
        for row in attempts:
            name=f"attempt_{int(row['frozen_index']):03d}.json"; raw=(json.dumps(row,sort_keys=True,indent=2,allow_nan=False)+'\n').encode(); fp=tmp/name
            with open(fp,'xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            files.append({'frozen_index':int(row['frozen_index']),'name':name,'sha256':hashlib.sha256(raw).hexdigest(),'eligible':bool(row['eligible'])})
        manifest={'kind':'ACTION_MATCHED_FUTURE_PLAN_PACKET_SCAN_V1','phase':phase_name,'attempted_indices':[int(x['frozen_index']) for x in attempts],'eligible_indices':[int(x['frozen_index']) for x in eligible],'eligible_count':len(eligible),'first20_policy':True,'files':files,'confirmation_accessed':phase_name=='confirmation',**phase.binding_payload()}
        raw=(json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        with open(tmp/'manifest.json','xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.rename(tmp,p); d=os.open(p.parent,os.O_RDONLY)
        try:os.fsync(d)
        finally:os.close(d)
        return hashlib.sha256(raw).hexdigest()
    except Exception:
        shutil.rmtree(tmp,ignore_errors=True); raise

def execution_provenance(model_prov:Mapping[str,Any])->dict[str,Any]:
    return {'kind':'ACTION_MATCHED_FUTURE_PLAN_EXECUTION_PROVENANCE_V1','driver_sha256':am.sha_file(Path(__file__)),'runtime_sha256':am.sha_file(ROOT/'action_matched_future_plan_runtime_v1.py'),'phase_runner_sha256':am.sha_file(ROOT/'action_matched_future_plan_phase_runner_v1.py'),'validator_sha256':am.sha_file(ROOT/'action_matched_future_plan_validator_v1.py'),'launcher_sha256':am.sha_file(ROOT/'action_matched_future_plan_vast_primary_v1.sh'),'implementation_test_sha256':am.sha_file(ROOT/'tests/test_action_matched_future_plan_implementation_v1.py'),'session_runtime_sha256':am.sha_file(ROOT/'replay_residual_t1_session_runtime_v1.py'),'low_level_localcontinuation_runtime_sha256':am.sha_file(ROOT/'localcontinuation_science_driver_v1.py'),'model_provenance':dict(model_prov),'one_shot_reset_prefix':True,'same_persistent_kv':True,'reinjection':False,'scientific_variables_changed':[],'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}

def _refuse(paths:Sequence[Path])->None:
    for p in paths:
        if _rel(p).exists(): raise ExecutionContractError(f'OUTPUT_EXISTS_BEFORE_MODEL_LOAD:{p}')

def development(tok:Any,model:Any,model_prov:Mapping[str,Any])->dict[str,Any]:
    _refuse([DEV_PACKET_DIR,DEV_PAYLOAD,DEV_SEAL,DEV_TERMINAL])
    attempts,eligible=_scan_first20(tok,model,'development',model_prov); packet_manifest_sha=_atomic_packet_set(attempts,eligible,DEV_PACKET_DIR,'development')
    ep=execution_provenance(model_prov); common={'phase':'ACTION_MATCHED_FUTURE_PLAN_DEVELOPMENT','eligible_indices':[int(x['frozen_index']) for x in eligible],'scan_attempted_indices':[int(x['frozen_index']) for x in attempts],'packet_manifest_sha256':packet_manifest_sha,'execution_provenance':ep,'execution_provenance_sha256':_sha(ep),'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}
    if len(eligible)<20:
        payload={**common,'grid_results':{}}; phase.atomic_write_new(_rel(DEV_PAYLOAD),payload); term=phase.select_development(payload); phase.atomic_write_new(_rel(DEV_TERMINAL),term); return term
    donor_map=_donor_map(eligible); by={int(x['frozen_index']):x for x in eligible}; bases={int(x['frozen_index']):_session_base(tok,x) for x in eligible}; sources={}
    for pos,pkt in enumerate(eligible,1):
        i=int(pkt['frozen_index']); sources[i]={}
        for layer in phase.LAYERS: sources[i][layer]=_capture_vectors(model,pkt,by[donor_map[i]],layer)
        print(json.dumps({'stage':'actionmatched_sources','done':pos,'total':20}),flush=True)
    grids={}
    for layer in phase.LAYERS:
        for alpha in phase.ALPHAS:
            key=phase.grid_key(layer,alpha); rows=[]
            for pos,pkt in enumerate(eligible,1):
                i=int(pkt['frozen_index']); rows.append(_eval_point(tok,model,pkt,bases[i],sources[i][layer],layer,alpha)); print(json.dumps({'stage':'actionmatched_grid','layer':layer,'alpha':alpha,'done':pos,'total':20}),flush=True)
            grids[key]=rows
    payload={**common,'grid_results':grids,'donor_map':donor_map}; phase.atomic_write_new(_rel(DEV_PAYLOAD),payload); term=phase.select_development(payload,_rel(DEV_SEAL)); phase.atomic_write_new(_rel(DEV_TERMINAL),term); return term

def _load_seal(expected_sha:str)->tuple[dict[str,Any],str]:
    p=_rel(DEV_SEAL)
    if not p.is_file(): raise ExecutionContractError('DEVELOPMENT_SEAL_MISSING')
    raw=p.read_bytes(); got=hashlib.sha256(raw).hexdigest(); seal=json.loads(raw)
    # phase.atomic_write_new hashes raw pretty JSON; expected runtime binding is file SHA, while semantic seal SHA is canonical. Accept only exact caller file hash.
    if got!=expected_sha: raise ExecutionContractError(f'DEVELOPMENT_SEAL_FILE_SHA_MISMATCH:{got}:{expected_sha}')
    if seal.get('status')!='DEVELOPMENT_SELECTION_PASS' or seal.get('confirmation_accessed') is not False: raise ExecutionContractError('INVALID_DEVELOPMENT_SEAL')
    for k,v in phase.binding_payload().items():
        if seal.get(k)!=v: raise ExecutionContractError(f'SEAL_BINDING_DRIFT:{k}')
    return seal,got

def confirmation(tok:Any,model:Any,model_prov:Mapping[str,Any],seal:Mapping[str,Any],seal_file_sha:str)->dict[str,Any]:
    attempts,eligible=_scan_first20(tok,model,'confirmation',model_prov); packet_manifest_sha=_atomic_packet_set(attempts,eligible,CONF_PACKET_DIR,'confirmation')
    common={'phase':'ACTION_MATCHED_FUTURE_PLAN_CONFIRMATION','selected_layer':int(seal['selected_layer']),'selected_alpha':float(seal['selected_alpha']),'development_seal_sha256':phase.canonical_sha(seal),'development_seal_file_sha256':seal_file_sha,'packet_manifest_sha256':packet_manifest_sha,'scan_attempted_indices':[int(x['frozen_index']) for x in attempts],'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}
    if len(eligible)<20:
        payload={**common,'families':[{'index':int(x['frozen_index']),'eligible':True} for x in eligible]}; phase.atomic_write_new(_rel(CONF_PAYLOAD),payload); result={'kind':'ACTION_MATCHED_FUTURE_PLAN_CONFIRMATION_RESULT_V1','status':'INCONCLUSIVE_CONFIRMATION_CONSTRUCTIBILITY','eligible_count':len(eligible),'scientific_result':'NOT_ASSESSED',**phase.binding_payload()}; phase.atomic_write_new(_rel(CONF_RESULT),result); return result
    donor_map=_donor_map(eligible); by={int(x['frozen_index']):x for x in eligible}; layer=int(seal['selected_layer']); alpha=float(seal['selected_alpha']); rows=[]
    for pos,pkt in enumerate(eligible,1):
        i=int(pkt['frozen_index']); base=_session_base(tok,pkt); vecs=_capture_vectors(model,pkt,by[donor_map[i]],layer); row=_eval_point(tok,model,pkt,base,vecs,layer,alpha); row['eligible']=True; rows.append(row); print(json.dumps({'stage':'actionmatched_confirmation','done':pos,'total':20}),flush=True)
    payload={**common,'families':rows,'donor_map':donor_map}; phase.atomic_write_new(_rel(CONF_PAYLOAD),payload)
    # evaluate_confirmation binds semantic canonical seal hash; pass exactly that, separately storing file SHA above.
    semantic_sha=phase.canonical_sha(seal); payload['development_seal_sha256']=semantic_sha
    result=phase.evaluate_confirmation(payload,seal,semantic_sha); phase.atomic_write_new(_rel(CONF_RESULT),result); return result

def preflight()->dict[str,Any]:
    am.verify_frozen_design(ROOT); rows=_load_population('development')
    return {'status':'READY_NO_SCIENCE','kind':'ACTION_MATCHED_FUTURE_PLAN_PREFLIGHT_V1','development_pool_indices':[int(x['frozen_index']) for x in rows],'model_calls':0,'model_loads':0,'environment_execution':0,'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}

def main(argv:Sequence[str]|None=None)->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['preflight','development','confirmation'],required=True); ap.add_argument('--expected-device',default='NVIDIA GeForce RTX 4060 Ti'); ap.add_argument('--development-seal-file-sha256'); args=ap.parse_args(argv)
    if args.phase=='preflight': print(json.dumps({'ACTION_MATCHED_PREFLIGHT':preflight()},sort_keys=True)); return 0
    if args.phase=='development': _refuse([DEV_PACKET_DIR,DEV_PAYLOAD,DEV_SEAL,DEV_TERMINAL])
    else:
        if not args.development_seal_file_sha256: raise ExecutionContractError('--development-seal-file-sha256 required')
        # Critical fail-closed order: validate seal and output absence before model load or confirmation population/game access.
        seal,seal_file_sha=_load_seal(args.development_seal_file_sha256); _refuse([CONF_PACKET_DIR,CONF_PAYLOAD,CONF_RESULT])
    # Fail closed on immutable scientific authority before any model load.
    # _load_population re-verifies later, but the execution boundary must reject drift first.
    am.verify_frozen_design(ROOT)
    tok,model,prov=load_model(args.expected_device)
    if args.phase=='development': out=development(tok,model,prov)
    else: out=confirmation(tok,model,prov,seal,seal_file_sha)
    print(json.dumps({'ACTION_MATCHED_TERMINAL':out},sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
