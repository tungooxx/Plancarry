#!/usr/bin/env python3
"""Environment-only matched A/B pair builder for PlanCarry-Latent v2.

No language-model call is made. No expert high-level/low-level plan is read.
Goal type comes from the task-family path; object/source identities come from
TextWorld reset facts and admissible commands. Both A/B orderings are replayed
from the same reset state to prove task-validity before freezing a pair.
"""
from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path
from typing import Any
from alfworld_runtime import AlfRuntime, replay, _facts, stable_json

ROOT=Path(os.path.realpath('/opt/gpu-lab/data/plancarry-alfworld'))
BASE=ROOT/'json_2.1.1'/'valid_train'
TRIAL_SALT='plancarry-latent-v2-pair-audit-2026-08-19'
PAIR_SALT='plancarry-latent-v2-frozen-pairs-2026-08-19'
TARGET_PAIRS=40

def sha(x:str)->str: return hashlib.sha256(x.encode()).hexdigest()
def hjson(x:Any)->str: return hashlib.sha256(stable_json(x).encode()).hexdigest()

def choose_trial(family:Path)->Path:
    games=sorted(family.glob('trial_*/game.tw-pddl'))
    return min(games,key=lambda p:sha(TRIAL_SALT+'|'+family.name+'|'+p.parent.name))

def family_goal(name:str)->tuple[str,str]:
    m=re.match(r'^pick_two_obj_and_place-(.+?)-None-(.+?)-\d+$',name)
    if not m: raise ValueError(name)
    return m.group(1).lower(),m.group(2).lower()

def strip_typed(x:str)->str:
    return re.sub(r'\s*:\s*(?:object|receptacle|otype|rtype|location|agent)\s*$', '', x.strip(), flags=re.I)

def parse_fact_state(info:dict[str,Any])->dict[str,Any]:
    obj_type={}; rec_type={}; in_rec={}; openable=set()
    for f in _facts(info):
        low=f.lower()
        m=re.match(r'objecttype\((.*?),\s*(.*?)\)$',low)
        if m: obj_type[strip_typed(m.group(1))]=strip_typed(m.group(2)).removesuffix('type'); continue
        m=re.match(r'receptacletype\((.*?),\s*(.*?)\)$',low)
        if m: rec_type[strip_typed(m.group(1))]=strip_typed(m.group(2)).removesuffix('type'); continue
        m=re.match(r'inreceptacle\((.*?),\s*(.*?)\)$',low)
        if m: in_rec[strip_typed(m.group(1))]=strip_typed(m.group(2)); continue
        m=re.match(r'openable\((.*?)\)$',low)
        if m: openable.add(strip_typed(m.group(1))); continue
    return {'obj_type':obj_type,'rec_type':rec_type,'in_rec':in_rec,'openable':openable}

def exact_command(rt:AlfRuntime, text:str)->str:
    if text not in rt.admissible_commands:
        raise RuntimeError(f'missing admissible {text!r}; have={rt.admissible_commands}')
    return text

def do(rt:AlfRuntime, text:str, records:list):
    out=rt.step(exact_command(rt,text))
    if out.error: raise RuntimeError(out.error)
    records.append(out)
    return out

def go_open(rt:AlfRuntime, rec:str, records:list):
    do(rt,f'go to {rec}',records)
    if f'open {rec}' in rt.admissible_commands:
        do(rt,f'open {rec}',records)

def branch_from_reset(game:str, prefix_records:list, first:dict, second:dict, target_rec:str)->dict[str,Any]:
    rt=replay(game,prefix_records,max_steps=40)
    records=[]
    try:
        # At delayed reset we are already at/open the common source. Immediate pairs start elsewhere.
        if f'take {first["object"]} from {first["source"]}' not in rt.admissible_commands:
            go_open(rt,first['source'],records)
        first_divergent = f'take {first["object"]} from {first["source"]}' if not records else records[0].command
        do(rt,f'take {first["object"]} from {first["source"]}',records)
        go_open(rt,target_rec,records)
        do(rt,f'move {first["object"]} to {target_rec}',records)
        go_open(rt,second['source'],records)
        do(rt,f'take {second["object"]} from {second["source"]}',records)
        go_open(rt,target_rec,records)
        do(rt,f'move {second["object"]} to {target_rec}',records)
        return {'valid':bool(rt.won),'done':bool(rt.done),'final_hash':rt.hash(),'actions':[x.command for x in records],'first_divergent':first_divergent}
    finally: rt.close()

def build_family(family:Path)->dict[str,Any]:
    game=choose_trial(family); target_type,target_rec_type=family_goal(family.name)
    rt=AlfRuntime(str(game),max_steps=40); prefix=[]
    try:
        initial_hash=rt.hash(); initial_obs=rt.observation; initial_commands=list(rt.admissible_commands)
        fs=parse_fact_state(rt.info)
        target_recs=sorted(r for r,t in fs['rec_type'].items() if t==target_rec_type and f'go to {r}' in initial_commands)
        if not target_recs: return {'family':family.name,'eligible':False,'reason':'NO_TARGET_RECEPTACLE_COMMAND'}
        target_rec=target_recs[0]
        objects=[]
        for o,t in fs['obj_type'].items():
            if t!=target_type: continue
            src=fs['in_rec'].get(o)
            if not src: continue
            # Objects already in any goal-type receptacle are not candidate unfinished commitments.
            if fs['rec_type'].get(src)==target_rec_type: continue
            objects.append({'object':o,'source':src,'source_type':fs['rec_type'].get(src),'source_openable':src in fs['openable']})
        objects.sort(key=lambda x:(x['source'],x['object']))
        if len(objects)<2: return {'family':family.name,'eligible':False,'reason':'LT2_UNFINISHED_TARGET_OBJECTS'}
        by_source={}
        for x in objects: by_source.setdefault(x['source'],[]).append(x)
        delayed_groups=[(s,xs) for s,xs in by_source.items() if len(xs)>=2]
        delayed_groups.sort(key=lambda z:(-len(z[1]),z[0]))
        if delayed_groups:
            src,xs=delayed_groups[0]
            pair=xs[:2]
            go_open(rt,src,prefix)
            delayed=True
        else:
            # Immediate-divergence fallback: choose two different sources deterministically.
            first_by_source=[sorted(xs,key=lambda x:x['object'])[0] for s,xs in sorted(by_source.items())]
            if len(first_by_source)<2: return {'family':family.name,'eligible':False,'reason':'NO_TWO_DISTINCT_SOURCES'}
            pair=first_by_source[:2]
            delayed=False
        reset_hash=rt.hash(); reset_obs=rt.observation; reset_cmds=list(rt.admissible_commands)
        prefix_actions=[x.command for x in prefix]
    finally: rt.close()
    a,b=pair[0],pair[1]
    ba=branch_from_reset(str(game),prefix,a,b,target_rec)
    bb=branch_from_reset(str(game),prefix,b,a,target_rec)
    if not (ba['valid'] and bb['valid']):
        return {'family':family.name,'eligible':False,'reason':'BRANCH_REPLAY_NOT_BOTH_SUCCESS','a_valid':ba['valid'],'b_valid':bb['valid']}
    # The active plan strings contain the exact same lexical clauses; only order changes.
    clause_a=f'Complete {a["object"]} from {a["source"]} into {target_rec}.'
    clause_b=f'Complete {b["object"]} from {b["source"]} into {target_rec}.'
    active_a='ACTIVE PLAN ORDER\n1. '+clause_a+'\n2. '+clause_b+'\nCHECKPOINT'
    active_b='ACTIVE PLAN ORDER\n1. '+clause_b+'\n2. '+clause_a+'\nCHECKPOINT'
    lexical_a='ARCHIVED NON-ACTIVE PLAN ORDER\n1. '+clause_a+'\n2. '+clause_b+'\nCHECKPOINT'
    lexical_b='ARCHIVED NON-ACTIVE PLAN ORDER\n1. '+clause_b+'\n2. '+clause_a+'\nCHECKPOINT'
    lex_bag=lambda s:sorted(re.findall(r'\w+|[^\w\s]',s.lower()))
    return {
      'family':family.name,'eligible':True,'game_path':str(game.relative_to(ROOT)).replace('\\','/'),'trial':game.parent.name,
      'target_object_type':target_type,'target_receptacle_type':target_rec_type,'target_receptacle':target_rec,
      'object_a':a,'object_b':b,'delayed_divergence':delayed,'common_prefix_actions':prefix_actions,
      'initial_state_hash':initial_hash,'reset_state_hash':reset_hash,'reset_observation_sha256':sha(reset_obs),
      'reset_admissible_commands':reset_cmds,'reset_admissible_commands_sha256':hjson(reset_cmds),
      'a_first_divergent_action':ba['first_divergent'],'b_first_divergent_action':bb['first_divergent'],
      'branch_a_actions':ba['actions'],'branch_b_actions':bb['actions'],'branch_a_won':ba['valid'],'branch_b_won':bb['valid'],
      'active_plan_a':active_a,'active_plan_b':active_b,'lexical_control_a':lexical_a,'lexical_control_b':lexical_b,
      'active_lexical_multiset_equal':lex_bag(active_a)==lex_bag(active_b),
      'lexical_control_multiset_equal':lex_bag(lexical_a)==lex_bag(lexical_b),
      'source_plan_clause_sha256s':sorted([sha(clause_a),sha(clause_b)]),
    }

def main():
    families=sorted(p for p in BASE.glob('pick_two_obj_and_place-*') if p.is_dir())
    rows=[]
    for i,f in enumerate(families,1):
        try: r=build_family(f)
        except Exception as e: r={'family':f.name,'eligible':False,'reason':'EXCEPTION','error':f'{type(e).__name__}: {e}'}
        rows.append(r); print(json.dumps({'i':i,'family':f.name,'eligible':r.get('eligible'),'delayed':r.get('delayed_divergence'),'reason':r.get('reason')},sort_keys=True),flush=True)
    elig=[r for r in rows if r.get('eligible')]
    elig.sort(key=lambda r:sha(PAIR_SALT+'|'+r['family']+'|'+r['trial']))
    selected=elig[:TARGET_PAIRS]
    for idx,r in enumerate(selected): r['frozen_pair_index']=idx; r['split']='discovery' if idx<20 else 'confirmation'
    out={'kind':'PLANCARRY_LATENT_V2_MATCHED_PAIR_MANIFEST','scientific_result':'NOT_ASSESSED','model_calls':0,'expert_plan_fields_read':False,
      'environment_only':True,'source_split':'valid_train','one_trial_per_family':True,'trial_salt':TRIAL_SALT,'pair_salt':PAIR_SALT,
      'family_count':len(rows),'eligible_family_count':len(elig),'selected_pair_count':len(selected),'target_pair_count':TARGET_PAIRS,
      'delayed_divergence_selected':sum(r['delayed_divergence'] for r in selected),'immediate_divergence_selected':sum(not r['delayed_divergence'] for r in selected),
      'active_lexical_multiset_equal_all':all(r['active_lexical_multiset_equal'] for r in selected),'both_branch_replay_success_all':all(r['branch_a_won'] and r['branch_b_won'] for r in selected),
      'valid_seen_consumed':False,'valid_unseen_consumed':False,'selected_pairs':selected,'all_family_audit':rows}
    Path('results/design').mkdir(parents=True,exist_ok=True)
    p=Path('results/design/plancarry_latent_v2_matched_pair_manifest.json')
    raw=(json.dumps(out,indent=2,sort_keys=True)+'\n').encode();p.write_bytes(raw)
    summary={k:v for k,v in out.items() if k not in {'selected_pairs','all_family_audit'}}; summary['manifest_sha256']=hashlib.sha256(raw).hexdigest()
    print('FINAL '+json.dumps(summary,sort_keys=True),flush=True)

if __name__=='__main__': main()
