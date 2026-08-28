#!/usr/bin/env python3
"""Execution-preparation driver for reviewed Grounded ActionMatched-v2.
`--phase preflight` is zero-science. Development/confirmation remain forbidden
until a separate independent executable review and canonical ResearchDecision.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

import action_matched_grounded_v2_constructibility as gc
import action_matched_grounded_v2_phase_runner_v1 as phase
import action_matched_grounded_v2_optimized_runtime_v1 as am
import action_matched_grounded_v2_optimization_v1 as gpuopt
import localcontinuation_science_driver_v1 as lc

ROOT=Path(__file__).resolve().parent
DEV_PACKET_DIR=Path('results/science/plancarry_action_matched_grounded_v2_development_packets_v1')
DEV_PAYLOAD=Path('results/science/plancarry_action_matched_grounded_v2_development_grid_v1.json')
DEV_SEAL=Path('results/science/plancarry_action_matched_grounded_v2_development_selection_v1.json')
DEV_TERMINAL=Path('results/science/plancarry_action_matched_grounded_v2_development_terminal_v1.json')
CONF_PACKET_DIR=Path('results/science/plancarry_action_matched_grounded_v2_confirmation_packets_v1')
CONF_PAYLOAD=Path('results/science/plancarry_action_matched_grounded_v2_confirmation_payload_v1.json')
CONF_RESULT=Path('results/science/plancarry_action_matched_grounded_v2_confirmation_result_v1.json')
POOL={'development':range(0,64),'confirmation':range(64,128)}
SEMANTIC=('UNRELATED_PAIR_RESIDUAL','ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY','FUTURE_ACTION_SEQUENCE_ONLY')

class ExecutionContractError(RuntimeError): pass

def _sha(obj:Any)->str: return phase.canonical_sha(obj)
def _rel(path:Path)->Path: return ROOT/path

def _load_population(phase_name:str)->list[dict[str,Any]]:
    am.verify_frozen_design(ROOT)
    data=json.loads(_rel(am.POP_REL).read_text()); paths=[dict(x) for x in data['paths']]
    if [int(x['index']) for x in paths]!=list(range(160)): raise ExecutionContractError('POPULATION_INDEX_DRIFT')
    if len({str(x['game_path']) for x in paths})!=160: raise ExecutionContractError('POPULATION_DUPLICATE_PATH')
    want=list(POOL[phase_name]); by={int(x['index']):x for x in paths}
    return [{'frozen_index':i,'game_path':str(by[i]['game_path']),'rank_sha256':str(by[i]['rank_sha256']),'phase':phase_name} for i in want]

def _runtime_factory(game_path:str):
    from alfworld_runtime import AlfRuntime, DATA_ROOT
    p=Path(str(game_path))
    if p.is_absolute() or '..' in p.parts or len(p.parts)!=2: raise ExecutionContractError('NONCANONICAL_GROUNDED_GAME_PATH')
    full=DATA_ROOT/'train'/p/'game.tw-pddl'
    if not full.is_file(): raise ExecutionContractError(f'GAME_FILE_MISSING:{game_path}')
    return AlfRuntime(str(full),max_steps=12)

def _extract_task(obs:str)->str:
    from replay_residual_natural_packet_producer_v2_1 import extract_task_instruction
    return extract_task_instruction(obs)
def _nontrivial(cmd:str)->bool:
    from replay_residual_natural_packet_producer_v2_1 import is_nontrivial
    return bool(is_nontrivial(cmd))
def _family(path:str)->str:
    p=gc.normalize_game_path(path); return p.split('/')[0]

def load_model(expected_device:str):
    tok,model,prov=lc.load_runtime(expected_device)
    tokenprov=am.verify_tokenizer(tok)
    return tok,model,{**prov,'grounded_v2_tokenizer_provenance':tokenprov}

def _score_current(tok:Any,model:Any,task:str,rt:Any,*,nontrivial_only:bool)->tuple[list[str],dict[str,float]]:
    commands=sorted(str(x) for x in rt.admissible_commands)
    if nontrivial_only: commands=[x for x in commands if _nontrivial(x)]
    if not commands: raise ExecutionContractError('NO_NONTRIVIAL_ADMISSIBLE_COMMAND' if nontrivial_only else 'NO_ADMISSIBLE_COMMAND')
    text=am.render_reset(task,str(rt.observation),sorted(str(x) for x in rt.admissible_commands)); prefix,tail=am.split_reset_action(tok,text)
    sess=am.PersistentTokenSession(model,prefix,layer=0,vector=None); sess.append_ids(tail,event='CONSTRUCTION_ACTION_PROMPT')
    try:
        _best,rows=sess.score_candidates(am.action_suffixes(tok,commands))
        scores={c:float(rows[c].mean_logprob) for c in commands}
    finally:
        prov=sess.close()
    if prov['hook_count']!=0: raise ExecutionContractError('CONSTRUCTION_UNEXPECTED_HOOK')
    return commands,scores

def _choose_two_precut(tok:Any,model:Any,rt:Any,task:str)->list[dict[str,Any]]:
    text=am.render_reset(task,str(rt.observation),sorted(str(x) for x in rt.admissible_commands)); prefix,tail=am.split_reset_action(tok,text)
    sess=am.PersistentTokenSession(model,prefix,layer=0,vector=None); sess.append_ids(tail,event='PRECUT_ACTION_PROMPT_1'); out=[]
    try:
        for step in (1,2):
            cmds=[x for x in sorted(str(x) for x in rt.admissible_commands) if _nontrivial(x)]
            if not cmds: raise ExecutionContractError('NO_NONTRIVIAL_ADMISSIBLE_COMMAND')
            best,scores=sess.score_candidates(am.action_suffixes(tok,cmds)); pre=str(rt.hash())
            suffix=am.action_suffixes(tok,[best])[best]; sess.append_ids(suffix,event=f'PRECUT_ACTION_{step}')
            rec=rt.step(best)
            if rec.error: raise ExecutionContractError(f'PRECUT_RUNTIME_ERROR:{rec.error}')
            out.append({'step':step,'command':best,'observation':str(rt.observation),'pre_state_hash':pre,'post_state_hash':str(rec.state_hash),'admissible_commands_before':cmds,'chosen_mean_logprob':float(scores[best].mean_logprob)})
            if step<2: sess.append_ids(am.continuation_ids(tok,str(rt.observation),rt.admissible_commands),event=f'PRECUT_OBS_{step}')
        prov=sess.close(); sess=None
        if prov['hook_count']!=0: raise ExecutionContractError('PRECUT_UNEXPECTED_HOOK')
        return out
    finally:
        if sess is not None and not sess.closed:
            try:sess.close()
            except Exception:pass

def _replay_to_cut(packet:Mapping[str,Any]):
    rt=_runtime_factory(str(packet['game_path']))
    try:
        for j,row in enumerate(packet['pre_cut_records']):
            if str(rt.hash())!=str(row['pre_state_hash']): raise ExecutionContractError(f'PRECUT_REPLAY_PRESTATE:{j}')
            rec=rt.step(str(row['command']))
            if rec.error or str(rec.state_hash)!=str(row['post_state_hash']): raise ExecutionContractError(f'PRECUT_REPLAY_POSTSTATE:{j}')
        if str(rt.hash())!=str(packet['cut_state_hash']): raise ExecutionContractError('CUT_STATE_REPLAY_MISMATCH')
        return rt
    except Exception:
        rt.close(); raise

def _replay_to_post_a3(packet:Mapping[str,Any],shared_a3:str,post_a3_hash:str):
    rt=_replay_to_cut(packet)
    try:
        if shared_a3 not in rt.admissible_commands: raise ExecutionContractError('SHARED_A3_REPLAY_NOT_ADMISSIBLE')
        rec=rt.step(shared_a3)
        if rec.error or str(rec.state_hash)!=str(post_a3_hash): raise ExecutionContractError('POST_A3_CLONE_STATE_MISMATCH')
        return rt
    except Exception:
        rt.close(); raise

def _construct_branch(tok:Any,model:Any,packet:Mapping[str,Any],task:str,shared_a3:str,post_a3_hash:str,a4:str,branch:str)->dict[str,Any]:
    rt=_replay_to_post_a3(packet,shared_a3,post_a3_hash)
    try:
        if a4 not in rt.admissible_commands or not _nontrivial(a4): raise gc.ConstructibilityError(f'{branch}4_INVALID')
        pre4=str(rt.hash()); rec=rt.step(a4)
        if rec.error: raise gc.ConstructibilityError(f'{branch}4_ERROR')
        post4=str(rt.hash()); obs4=str(rt.observation); all_after=sorted(str(x) for x in rt.admissible_commands)
        nontriv,scores=_score_current(tok,model,task,rt,nontrivial_only=True); a5=gc.frozen_rank(nontriv,scores,label=f'branch_{branch}_after_A4')[0]
        if len(all_after)<2: raise gc.ConstructibilityError(f'{branch}5_NO_ALTERNATIVE')
        return {'action4':a4,'pre4_state_hash':pre4,'post4_state_hash':post4,'observation4':obs4,'all_admissibles_after4':all_after,'nontrivial_admissibles_after4':nontriv,'scores_after4':scores,'action5':a5}
    finally: rt.close()

def produce_grounded_attempt(tok:Any,model:Any,row:Mapping[str,Any],model_prov:Mapping[str,Any])->dict[str,Any]:
    packet={'frozen_index':int(row['frozen_index']),'game_path':str(row['game_path']),'phase':str(row['phase']),'family':_family(str(row['game_path'])),'eligible':False,'ineligibility_reasons':[],'model_provenance':dict(model_prov)}
    rt=None
    try:
        rt=_runtime_factory(packet['game_path']); initial=str(rt.observation); task=_extract_task(initial); packet['initial_observation']=initial; packet['task_instruction']=task
        pre=_choose_two_precut(tok,model,rt,task); packet['pre_cut_records']=pre; packet['cut_state_hash']=str(rt.hash()); packet['cut_observation']=str(rt.observation); packet['cut_all_admissible_commands']=sorted(str(x) for x in rt.admissible_commands)
        cut_adm,cut_scores=_score_current(tok,model,task,rt,nontrivial_only=True); shared=gc.frozen_rank(cut_adm,cut_scores,label='cut2')[0]
        rec3=rt.step(shared)
        if rec3.error: raise gc.ConstructibilityError('SHARED_ACTION_ERROR')
        post3_hash=str(rt.hash()); obs3=str(rt.observation); post_all=sorted(str(x) for x in rt.admissible_commands)
        post_adm,post_scores=_score_current(tok,model,task,rt,nontrivial_only=True); ranks=gc.frozen_rank(post_adm,post_scores,label='post_action3')
        if len(ranks)<2: raise gc.ConstructibilityError('POST_A3_LT2_NONTRIVIAL')
        bit=gc.orientation_bit(packet['game_path']); rank1,rank2=ranks[:2]; a4,b4=(rank1,rank2) if bit==0 else (rank2,rank1)
        A=_construct_branch(tok,model,packet,task,shared,post3_hash,a4,'A'); B=_construct_branch(tok,model,packet,task,shared,post3_hash,b4,'B')
        if A['action5']==B['action5']: raise gc.ConstructibilityError('A5_EQUALS_B5')
        pair=gc.construct_grounded_pair(game_path=packet['game_path'],pre_cut_actions=[x['command'] for x in pre],pre_cut_actions_model_own_nontrivial=True,
            cut_admissibles=cut_adm,cut_scores=cut_scores,post_action3_admissibles=post_adm,post_action3_scores=post_scores,
            branch_a_admissibles=A['nontrivial_admissibles_after4'],branch_a_scores=A['scores_after4'],branch_b_admissibles=B['nontrivial_admissibles_after4'],branch_b_scores=B['scores_after4'],
            cut_state_hash=packet['cut_state_hash'],post_action3_state_hash=post3_hash,branch_a_state_hash=A['post4_state_hash'],branch_b_state_hash=B['post4_state_hash'],
            common_observation3=obs3,branch_a_observation=A['observation4'],branch_b_observation=B['observation4'],executed_shared_action3=shared,branch_a_action4_executed=a4,branch_b_action4_executed=b4)
        packet['grounded_pair']=pair.to_dict(); packet['post_a3_all_admissible_commands']=post_all; packet['branch_A']=A; packet['branch_B']=B
        actions={'A3':shared,'A4':a4,'B4':b4,'A5':A['action5'],'B5':B['action5']}; ids=am.tokenize_actions_once(tok,actions); packet['action_strings']=actions; packet['action_ids']=ids; packet['action_ids_sha256']={k:am.token_ids_sha256(v) for k,v in ids.items()}
        # Exactly two one-shot representations, only after all grounded sequence/provenance is frozen.
        planA=am.plan_materialize_once(tok,model,task,packet['cut_observation'],pre,packet['cut_all_admissible_commands'],shared,a4,A['action5'])
        planB=am.plan_materialize_once(tok,model,task,packet['cut_observation'],pre,packet['cut_all_admissible_commands'],shared,b4,B['action5'])
        packet['plan_A']=planA; packet['plan_B']=planB
        prefix=am.common_source_prefix(tok,task,packet['cut_observation'],pre,packet['cut_all_admissible_commands']); packet['source_common_prefix_ids']=prefix; packet['source_common_prefix_ids_sha256']=am.token_ids_sha256(prefix)
        packet['source_condition_provenance']={}
        for cond in ('ACTIVE','ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY','FUTURE_ACTION_SEQUENCE_ONLY'):
            src=am.source_condition_ids(prefix,ids,planA,planB,cond)
            packet['source_condition_provenance'][cond]={'A_ids_sha256':am.token_ids_sha256(src['A_ids']),'B_ids_sha256':am.token_ids_sha256(src['B_ids']),'token_count':src['token_count'],'source_end_position':src['source_end_position'],'slot_lengths':src['slot_lengths']}
        packet['construction_clone_contract']='deterministic replay to exact hidden-facts state hash before A/B branch execution'
        packet['eligible']=True
    except gc.ConstructibilityError as exc:
        packet['ineligibility_reasons']=[f'ConstructibilityError:{exc}']
    except am.RuntimeContractError as exc:
        msg=str(exc); allowed=('PLAN_FULLMATCH_REQUIRED','PLAN_ACTION_ROUNDTRIP_MISMATCH','PLAN_RATIONALE_INVALID','PLAN_TOKEN_LENGTH_GT96','RATIONALE_DERANGEMENT_UNCONSTRUCTIBLE','RATIONALE_DERANGEMENT_POSTCONDITION')
        if not msg.startswith(allowed): raise
        packet['ineligibility_reasons']=[f'RuntimeContractError:{msg}']
    except ExecutionContractError as exc:
        msg=str(exc); allowed=('NO_NONTRIVIAL_ADMISSIBLE_COMMAND','PRECUT_RUNTIME_ERROR:')
        if not msg.startswith(allowed): raise
        packet['ineligibility_reasons']=[f'ExecutionContractError:{msg}']
    finally:
        if rt is not None: rt.close()
    packet['packet_semantic_sha256']=_sha({k:v for k,v in packet.items() if k!='packet_semantic_sha256'})
    return packet

def _ineligibility_reason_counts(attempts:Sequence[Mapping[str,Any]])->dict[str,int]:
    counts:dict[str,int]={}
    for pkt in attempts:
        if bool(pkt.get('eligible')):
            continue
        reasons=pkt.get('ineligibility_reasons')
        if not isinstance(reasons,list) or not reasons or any(not isinstance(x,str) or not x for x in reasons):
            raise ExecutionContractError('INELIGIBILITY_REASON_MISSING')
        for reason in reasons:
            counts[reason]=counts.get(reason,0)+1
    return {k:counts[k] for k in sorted(counts)}

def _scan_first20(tok:Any,model:Any,phase_name:str,model_prov:Mapping[str,Any])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    attempts=[]; eligible=[]
    device=next(model.parameters()).device
    for row in _load_population(phase_name):
        gpuopt.reset_cuda_peak_memory(device)
        try:
            pkt=produce_grounded_attempt(tok,model,row,model_prov)
        except Exception as exc:
            # CUDA OOM and other technical failures must propagate; they are never
            # converted to constructibility ineligibility.
            if exc.__class__.__name__ in ('OutOfMemoryError','CudaError') or 'out of memory' in str(exc).lower():
                raise gpuopt.TechnicalMemoryError(f'CUDA_OOM_TECHNICAL:{type(exc).__name__}:{exc}') from exc
            raise
        mem=gpuopt.require_cuda_headroom(device)
        print(json.dumps({'stage':'grounded_v2_memory','phase':phase_name,'frozen_index':int(row['frozen_index']),**mem},sort_keys=True),flush=True)
        attempts.append(pkt)
        print(json.dumps({'stage':'grounded_v2_scan','phase':phase_name,'attempted':len(attempts),'eligible':len(eligible)+int(pkt['eligible'])}),flush=True)
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
        if int(p['frozen_index']) not in out: raise ExecutionContractError('NO_DIFFERENT_FAMILY_DONOR_AFTER_E_FREEZE')
    return out

def _reset_to_cut(packet:Mapping[str,Any]): return _replay_to_cut(packet)

def _session_base(tok:Any,packet:Mapping[str,Any])->dict[str,Any]:
    rt=_reset_to_cut(packet)
    try:
        obs=str(rt.observation); commands=sorted(str(x) for x in rt.admissible_commands); text=am.render_reset(str(packet['task_instruction']),obs,commands); prefix,tail=am.split_reset_action(tok,text)
        return {'prefix_ids':prefix,'action_prompt_ids':tail,'observation':obs,'commands':commands,'state_hash':str(rt.hash()),'reset_prefix_sha256':am.token_ids_sha256(prefix),'reset_snapshot_sha256':_sha({'task':packet['task_instruction'],'observation':obs,'commands':commands,'state_hash':str(rt.hash()),'serialization':text})}
    finally: rt.close()

def _source_ids(packet:Mapping[str,Any],condition:str)->dict[str,Any]:
    return am.source_condition_ids(packet['source_common_prefix_ids'],packet['action_ids'],packet['plan_A'],packet['plan_B'],condition)

def _capture_vectors_all_layers(model:Any,packet:Mapping[str,Any],donor:Mapping[str,Any],layers:Sequence[int])->dict[int,dict[str,Any]]:
    import torch
    req=[int(x) for x in layers]
    active=_source_ids(packet,'ACTIVE'); raw_by=am.capture_pair_residuals(model,active['A_ids'],active['B_ids'],req)
    out={}
    for layer in req:
        raw=raw_by[layer]; norm=float(torch.linalg.vector_norm(raw).item()); active_ok=norm>1e-8
        out[layer]={'ACTIVE':raw if active_ok else torch.zeros_like(raw),'active_l2':norm,'active_sha256':am.vector_sha256_fp32(raw),'_validity':{'active_nondegenerate':active_ok},'_raw_control_l2':{}}
    for cond in ('ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY','FUTURE_ACTION_SEQUENCE_ONLY'):
        src=_source_ids(packet,cond); rv_by=am.capture_pair_residuals(model,src['A_ids'],src['B_ids'],req)
        for layer in req:
            target=float(out[layer]['active_l2']); mv,ok,rn=am.match_control_norm(rv_by[layer],target); out[layer][cond]=mv; out[layer]['_validity'][cond]=bool(ok); out[layer]['_raw_control_l2'][cond]=rn
    d=_source_ids(donor,'ACTIVE'); drv_by=am.capture_pair_residuals(model,d['A_ids'],d['B_ids'],req)
    for layer in req:
        target=float(out[layer]['active_l2']); mv,ok,rn=am.match_control_norm(drv_by[layer],target); out[layer]['UNRELATED_PAIR_RESIDUAL']=mv; out[layer]['_validity']['UNRELATED_PAIR_RESIDUAL']=bool(ok); out[layer]['_raw_control_l2']['UNRELATED_PAIR_RESIDUAL']=rn
        if bool(out[layer]['_validity']['active_nondegenerate']):
            out[layer]['RANDOM_EQ_NORM']=lc.rademacher(int(out[layer]['ACTIVE'].numel()),target,f"ReplayResidualLocalContinuation|RANDOM_EQ_NORM|{packet['family']}|{packet['game_path']}|L{int(layer)}")
        else:
            out[layer]['RANDOM_EQ_NORM']=torch.zeros_like(out[layer]['ACTIVE'])
    return out

def _capture_vectors(model:Any,packet:Mapping[str,Any],donor:Mapping[str,Any],layer:int)->dict[str,Any]:
    import torch
    active=_source_ids(packet,'ACTIVE'); raw=am.capture_pair_residual(model,active['A_ids'],active['B_ids'],layer); norm=float(torch.linalg.vector_norm(raw).item()); active_ok=norm>1e-8
    out={'ACTIVE':raw if active_ok else torch.zeros_like(raw),'active_l2':norm,'active_sha256':am.vector_sha256_fp32(raw),'_validity':{'active_nondegenerate':active_ok},'_raw_control_l2':{}}
    for cond in ('ACTION_HISTORY_MATCHED_NULL','FUTURE_TOKEN_DERANGED','NEXT_DIVERGENT_ACTION_ONLY','FUTURE_ACTION_SEQUENCE_ONLY'):
        src=_source_ids(packet,cond); rv=am.capture_pair_residual(model,src['A_ids'],src['B_ids'],layer); mv,ok,rn=am.match_control_norm(rv,norm); out[cond]=mv; out['_validity'][cond]=bool(ok); out['_raw_control_l2'][cond]=rn
    d=_source_ids(donor,'ACTIVE'); drv=am.capture_pair_residual(model,d['A_ids'],d['B_ids'],layer); mv,ok,rn=am.match_control_norm(drv,norm); out['UNRELATED_PAIR_RESIDUAL']=mv; out['_validity']['UNRELATED_PAIR_RESIDUAL']=bool(ok); out['_raw_control_l2']['UNRELATED_PAIR_RESIDUAL']=rn
    if active_ok: out['RANDOM_EQ_NORM']=lc.rademacher(int(raw.numel()),norm,f"ReplayResidualLocalContinuation|RANDOM_EQ_NORM|{packet['family']}|{packet['game_path']}|L{int(layer)}")
    else: out['RANDOM_EQ_NORM']=torch.zeros_like(raw)
    return out

def _start_session(model:Any,base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,sign:int=1):
    v=None if vector is None else vector*(1 if sign>0 else -1)
    s=am.PersistentTokenSession(model,base['prefix_ids'],layer=int(layer),vector=v,mode='add',scale=float(alpha) if v is not None else 1.0); s.append_ids(base['action_prompt_ids'],event='ACTION_PROMPT_RESET'); return s

def _teacher_shared(tok:Any,sess:Any,rt:Any,packet:Mapping[str,Any])->None:
    sh=str(packet['action_strings']['A3']); cmds=sorted(str(x) for x in rt.admissible_commands)
    if sh not in cmds: raise ExecutionContractError('SHARED_NOT_ADMISSIBLE_RUNTIME')
    sess.append_ids(am.action_suffixes(tok,cmds)[sh],event='TEACHER_SHARED_A3'); rec=rt.step(sh)
    if rec.error or str(rec.state_hash)!=str(packet['grounded_pair']['post_action3_state_hash']): raise ExecutionContractError('SHARED_REPLAY_STATE_DRIFT')
    sess.append_ids(am.continuation_ids(tok,str(rt.observation),rt.admissible_commands),event='TEACHER_OBS3')

def _a4_margin(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,sign:int)->float:
    rt=_reset_to_cut(packet); sess=None
    try:
        sess=_start_session(model,base,layer,vector,alpha,sign); _teacher_shared(tok,sess,rt,packet)
        return am.score_margin(sess,tok,str(packet['action_strings']['A4']),str(packet['action_strings']['B4']))
    finally:
        if sess is not None and not sess.closed: sess.close()
        rt.close()

def _a5_margin(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],layer:int,vector:Any|None,alpha:float,sign:int,branch:str)->float:
    rt=_reset_to_cut(packet); sess=None
    try:
        sess=_start_session(model,base,layer,vector,alpha,sign); _teacher_shared(tok,sess,rt,packet)
        a4=str(packet['action_strings'][f'{branch}4']); cmds=sorted(str(x) for x in rt.admissible_commands); sess.append_ids(am.action_suffixes(tok,cmds)[a4],event=f'TEACHER_{branch}4'); rec=rt.step(a4)
        exp=packet[f'branch_{branch}']
        if rec.error or str(rec.state_hash)!=str(exp['post4_state_hash']): raise ExecutionContractError(f'{branch}4_REPLAY_STATE_DRIFT')
        sess.append_ids(am.continuation_ids(tok,str(rt.observation),rt.admissible_commands),event=f'TEACHER_{branch}_OBS4')
        return am.reference_margin(sess,tok,str(packet['action_strings'][f'{branch}5']),sorted(str(x) for x in rt.admissible_commands))
    finally:
        if sess is not None and not sess.closed: sess.close()
        rt.close()

def _eval_point(tok:Any,model:Any,packet:Mapping[str,Any],base:Mapping[str,Any],vectors:Mapping[str,Any],layer:int,alpha:float)->dict[str,Any]:
    arms=('ACTIVE','RANDOM_EQ_NORM',*SEMANTIC)
    validity={'active_nondegenerate':bool(vectors['_validity']['active_nondegenerate']),**{k:bool(vectors['_validity'][k]) for k in SEMANTIC}}
    a4={'NO_PATCH':_a4_margin(tok,model,packet,base,layer,None,alpha,1),'_validity':validity}; a5={'NO_PATCH':{'A':_a5_margin(tok,model,packet,base,layer,None,alpha,1,'A'),'B':_a5_margin(tok,model,packet,base,layer,None,alpha,1,'B')},'_validity':validity}
    for arm in arms:
        a4[arm]={'+':_a4_margin(tok,model,packet,base,layer,vectors[arm],alpha,1),'-':_a4_margin(tok,model,packet,base,layer,vectors[arm],alpha,-1)}
        a5[arm]={'+':{'A':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,1,'A'),'B':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,1,'B')},'-':{'A':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,-1,'A'),'B':_a5_margin(tok,model,packet,base,layer,vectors[arm],alpha,-1,'B')}}
    zmax,smax=lc.sentinels(model,base,layer)
    if zmax>1e-6 or smax>1e-6: raise ExecutionContractError('PLUMBING_SENTINEL_FAIL')
    return {'index':int(packet['frozen_index']),'a4_margins':a4,'a5_margins':a5,'zero_add_no_patch_maxabs':zmax,'self_replace_no_patch_maxabs':smax,'active_residual_sha256':vectors['active_sha256'],'active_residual_l2':vectors['active_l2'],'control_validity':validity,'raw_control_l2':vectors['_raw_control_l2'],'reset_snapshot_sha256':base['reset_snapshot_sha256']}

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
        manifest={'kind':'ACTION_MATCHED_GROUNDED_V2_PACKET_SCAN_V1','phase':phase_name,'attempted_indices':[int(x['frozen_index']) for x in attempts],'eligible_indices':[int(x['frozen_index']) for x in eligible],'eligible_count':len(eligible),'first20_policy':True,'files':files,'confirmation_accessed':phase_name=='confirmation','reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}
        raw=(json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        with open(tmp/'manifest.json','xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.rename(tmp,p); d=os.open(p.parent,os.O_RDONLY)
        try:os.fsync(d)
        finally:os.close(d)
        return hashlib.sha256(raw).hexdigest()
    except Exception:
        shutil.rmtree(tmp,ignore_errors=True); raise

def execution_provenance(model_prov:Mapping[str,Any])->dict[str,Any]:
    return {'kind':'ACTION_MATCHED_GROUNDED_V2_EXECUTION_PROVENANCE_V1','driver_sha256':am.sha_file(Path(__file__)),'runtime_sha256':am.sha_file(ROOT/'action_matched_grounded_v2_optimized_runtime_v1.py'),'phase_runner_sha256':am.sha_file(ROOT/'action_matched_grounded_v2_phase_runner_v1.py'),'validator_sha256':am.sha_file(ROOT/'action_matched_grounded_v2_validator_v1.py'),'launcher_sha256':am.sha_file(ROOT/'action_matched_grounded_v2_optimized_primary_v1.sh'),'optimization_sha256':am.sha_file(ROOT/'action_matched_grounded_v2_optimization_v1.py'),'implementation_test_sha256':am.sha_file(ROOT/'tests/test_action_matched_grounded_v2_executable_v1.py'),'optimization_test_sha256':am.sha_file(ROOT/'tests/test_action_matched_grounded_v2_optimization_v1.py'),'constructibility_sha256':phase.CONSTRUCTIBILITY_SHA256,'session_runtime_sha256':phase.SESSION_RUNTIME_SHA256,'model_provenance':dict(model_prov),'one_reset_prefix_intervention':True,'same_persistent_kv':True,'reinjection':False,'scientific_variables_changed':[],'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}

def _refuse(paths:Sequence[Path])->None:
    for p in paths:
        if _rel(p).exists(): raise ExecutionContractError(f'OUTPUT_EXISTS_BEFORE_MODEL_LOAD:{p}')

def development(tok:Any,model:Any,model_prov:Mapping[str,Any])->dict[str,Any]:
    _refuse([DEV_PACKET_DIR,DEV_PAYLOAD,DEV_SEAL,DEV_TERMINAL]); attempts,eligible=_scan_first20(tok,model,'development',model_prov); packet_manifest_sha=_atomic_packet_set(attempts,eligible,DEV_PACKET_DIR,'development')
    ep=execution_provenance(model_prov); reason_counts=_ineligibility_reason_counts(attempts); common={'phase':'ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT','eligible_indices':[int(x['frozen_index']) for x in eligible],'scan_attempted_indices':[int(x['frozen_index']) for x in attempts],'attempted_count':len(attempts),'ineligibility_reason_counts':reason_counts,'packet_manifest_sha256':packet_manifest_sha,'execution_provenance':ep,'execution_provenance_sha256':_sha(ep),'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}
    if len(eligible)<20:
        payload={**common,'grid_results':{}}; phase.atomic_write_new(_rel(DEV_PAYLOAD),payload); term=phase.select_development(payload); phase.atomic_write_new(_rel(DEV_TERMINAL),term); return term
    donor_map=_donor_map(eligible); by={int(x['frozen_index']):x for x in eligible}; bases={int(x['frozen_index']):_session_base(tok,x) for x in eligible}; sources={}
    device=next(model.parameters()).device
    for pos,pkt in enumerate(eligible,1):
        i=int(pkt['frozen_index']); gpuopt.reset_cuda_peak_memory(device)
        sources[i]=_capture_vectors_all_layers(model,pkt,by[donor_map[i]],phase.LAYERS)
        mem=gpuopt.require_cuda_headroom(device)
        print(json.dumps({'stage':'grounded_v2_memory','phase':'development_sources','frozen_index':i,**mem},sort_keys=True),flush=True)
        print(json.dumps({'stage':'grounded_v2_sources','done':pos,'total':20}),flush=True)
    grids={}
    for layer in phase.LAYERS:
        for alpha in phase.ALPHAS:
            key=phase.grid_key(layer,alpha); rows=[]
            for pos,pkt in enumerate(eligible,1):
                i=int(pkt['frozen_index']); gpuopt.reset_cuda_peak_memory(device)
                row=_eval_point(tok,model,pkt,bases[i],sources[i][layer],layer,alpha)
                mem=gpuopt.require_cuda_headroom(device)
                print(json.dumps({'stage':'grounded_v2_memory','phase':'development_grid','frozen_index':i,'layer':layer,'alpha':alpha,**mem},sort_keys=True),flush=True)
                rows.append(row); print(json.dumps({'stage':'grounded_v2_grid','layer':layer,'alpha':alpha,'done':pos,'total':20}),flush=True)
            grids[key]=rows
    payload={**common,'grid_results':grids,'donor_map':donor_map}; phase.atomic_write_new(_rel(DEV_PAYLOAD),payload); term=phase.select_development(payload,_rel(DEV_SEAL)); phase.atomic_write_new(_rel(DEV_TERMINAL),term); return term

def _load_seal(expected_file_sha:str)->tuple[dict[str,Any],str]:
    p=_rel(DEV_SEAL)
    if not p.is_file(): raise ExecutionContractError('DEVELOPMENT_SEAL_MISSING')
    raw=p.read_bytes(); got=hashlib.sha256(raw).hexdigest(); seal=json.loads(raw)
    if got!=expected_file_sha: raise ExecutionContractError(f'DEVELOPMENT_SEAL_FILE_SHA_MISMATCH:{got}:{expected_file_sha}')
    if seal.get('status')!='DEVELOPMENT_SELECTION_PASS' or seal.get('confirmation_accessed') is not False: raise ExecutionContractError('INVALID_DEVELOPMENT_SEAL')
    for k,v in phase.binding_payload().items():
        if seal.get(k)!=v: raise ExecutionContractError(f'SEAL_BINDING_DRIFT:{k}')
    return seal,got

def confirmation(tok:Any,model:Any,model_prov:Mapping[str,Any],seal:Mapping[str,Any],seal_file_sha:str)->dict[str,Any]:
    attempts,eligible=_scan_first20(tok,model,'confirmation',model_prov); packet_manifest_sha=_atomic_packet_set(attempts,eligible,CONF_PACKET_DIR,'confirmation')
    common={'phase':'ACTION_MATCHED_GROUNDED_V2_CONFIRMATION','selected_layer':int(seal['selected_layer']),'selected_alpha':float(seal['selected_alpha']),'development_seal_sha256':phase.canonical_sha(seal),'development_seal_file_sha256':seal_file_sha,'packet_manifest_sha256':packet_manifest_sha,'scan_attempted_indices':[int(x['frozen_index']) for x in attempts],'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}
    if len(eligible)<20:
        payload={**common,'families':[{'index':int(x['frozen_index']),'eligible':True} for x in eligible]}; phase.atomic_write_new(_rel(CONF_PAYLOAD),payload); result=phase.evaluate_confirmation(payload,seal,phase.canonical_sha(seal)); phase.atomic_write_new(_rel(CONF_RESULT),result); return result
    donor_map=_donor_map(eligible); by={int(x['frozen_index']):x for x in eligible}; layer=int(seal['selected_layer']); alpha=float(seal['selected_alpha']); rows=[]
    device=next(model.parameters()).device
    for pos,pkt in enumerate(eligible,1):
        i=int(pkt['frozen_index']); gpuopt.reset_cuda_peak_memory(device)
        base=_session_base(tok,pkt); vecs=_capture_vectors(model,pkt,by[donor_map[i]],layer); row=_eval_point(tok,model,pkt,base,vecs,layer,alpha); row['eligible']=True
        mem=gpuopt.require_cuda_headroom(device)
        print(json.dumps({'stage':'grounded_v2_memory','phase':'confirmation','frozen_index':i,'layer':layer,'alpha':alpha,**mem},sort_keys=True),flush=True)
        rows.append(row); print(json.dumps({'stage':'grounded_v2_confirmation','done':pos,'total':20}),flush=True)
    payload={**common,'families':rows,'donor_map':donor_map}; phase.atomic_write_new(_rel(CONF_PAYLOAD),payload); result=phase.evaluate_confirmation(payload,seal,phase.canonical_sha(seal)); phase.atomic_write_new(_rel(CONF_RESULT),result); return result

def preflight()->dict[str,Any]:
    am.verify_frozen_design(ROOT); rows=_load_population('development'); _refuse([DEV_PACKET_DIR,DEV_PAYLOAD,DEV_SEAL,DEV_TERMINAL])
    return {'status':'READY_NO_SCIENCE','kind':'ACTION_MATCHED_GROUNDED_V2_PREFLIGHT_V1','development_pool_indices':[int(x['frozen_index']) for x in rows],'model_calls':0,'model_loads':0,'environment_execution':0,'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**phase.binding_payload()}

def main(argv:Sequence[str]|None=None)->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['preflight','development','confirmation'],required=True); ap.add_argument('--expected-device',default='NVIDIA GeForce RTX 3050 Laptop GPU'); ap.add_argument('--development-seal-file-sha256'); args=ap.parse_args(argv)
    if args.phase=='preflight': print(json.dumps({'ACTION_MATCHED_GROUNDED_V2_PREFLIGHT':preflight()},sort_keys=True)); return 0
    if args.phase=='development': _refuse([DEV_PACKET_DIR,DEV_PAYLOAD,DEV_SEAL,DEV_TERMINAL])
    else:
        if not args.development_seal_file_sha256: raise ExecutionContractError('--development-seal-file-sha256 required')
        seal,seal_file_sha=_load_seal(args.development_seal_file_sha256); _refuse([CONF_PACKET_DIR,CONF_PAYLOAD,CONF_RESULT])
    am.verify_frozen_design(ROOT); tok,model,prov=load_model(args.expected_device)
    out=development(tok,model,prov) if args.phase=='development' else confirmation(tok,model,prov,seal,seal_file_sha)
    print(json.dumps({'ACTION_MATCHED_GROUNDED_V2_TERMINAL':out},sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
