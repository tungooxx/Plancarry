#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,re
from pathlib import Path
from typing import Any
from alfworld_runtime import AlfRuntime,replay,_facts,stable_json
ROOT=Path('/opt/gpu-lab/data/plancarry-alfworld')
BASE=ROOT/'json_2.1.1'/'train'
TRIAL_SALT='plancarry-replay-residual-v1-trial-2026-08-21'
PAIR_SALT='plancarry-replay-residual-v1-fresh48-2026-08-21'
TARGET=48
OUT=Path('results/design/plancarry_replay_residual_fresh48_manifest_v1.json')
def sha(x:str)->str:return hashlib.sha256(x.encode()).hexdigest()
def hjson(x:Any)->str:return hashlib.sha256(stable_json(x).encode()).hexdigest()
def strip_typed(x:str)->str:return re.sub(r'\s*:\s*(?:object|receptacle|otype|rtype|location|agent)\s*$','',x.strip(),flags=re.I)
def choose_trial(family:Path)->Path:
 g=sorted(family.glob('trial_*/game.tw-pddl'))
 if not g: raise RuntimeError('NO_TRIAL_GAMES')
 return min(g,key=lambda p:sha(TRIAL_SALT+'|'+family.name+'|'+p.parent.name))
def family_goal(name:str):
 m=re.match(r'^pick_two_obj_and_place-(.+?)-None-(.+?)-\d+$',name)
 if not m: raise ValueError(name)
 return m.group(1).lower(),m.group(2).lower()
def parse_fact_state(info):
 obj_type={};rec_type={};in_rec={};openable=set()
 for f in _facts(info):
  low=f.lower()
  m=re.match(r'objecttype\((.*?),\s*(.*?)\)$',low)
  if m:obj_type[strip_typed(m.group(1))]=strip_typed(m.group(2)).removesuffix('type');continue
  m=re.match(r'receptacletype\((.*?),\s*(.*?)\)$',low)
  if m:rec_type[strip_typed(m.group(1))]=strip_typed(m.group(2)).removesuffix('type');continue
  m=re.match(r'inreceptacle\((.*?),\s*(.*?)\)$',low)
  if m:in_rec[strip_typed(m.group(1))]=strip_typed(m.group(2));continue
  m=re.match(r'openable\((.*?)\)$',low)
  if m:openable.add(strip_typed(m.group(1)));continue
 return {'obj_type':obj_type,'rec_type':rec_type,'in_rec':in_rec,'openable':openable}
def do(rt,text,records):
 if text not in rt.admissible_commands: raise RuntimeError('MISSING_ADMISSIBLE:'+text)
 out=rt.step(text)
 if out.error: raise RuntimeError(out.error)
 records.append(out);return out
def go_open(rt,rec,records):
 do(rt,f'go to {rec}',records)
 if f'open {rec}' in rt.admissible_commands:do(rt,f'open {rec}',records)
def branch(game,prefix,first,second,target):
 rt=replay(game,prefix,max_steps=40); rec=[]
 try:
  if f'take {first["object"]} from {first["source"]}' not in rt.admissible_commands:go_open(rt,first['source'],rec)
  first_div=f'take {first["object"]} from {first["source"]}' if not rec else rec[0].command
  do(rt,f'take {first["object"]} from {first["source"]}',rec);go_open(rt,target,rec);do(rt,f'move {first["object"]} to {target}',rec)
  go_open(rt,second['source'],rec);do(rt,f'take {second["object"]} from {second["source"]}',rec);go_open(rt,target,rec);do(rt,f'move {second["object"]} to {target}',rec)
  return {'valid':bool(rt.won),'actions':[x.command for x in rec],'first_divergent':first_div}
 finally:rt.close()
def build_family(family):
 game=choose_trial(family); target_type,target_rec_type=family_goal(family.name)
 rt=AlfRuntime(str(game),max_steps=40);prefix=[]
 try:
  initial_hash=rt.hash(); fs=parse_fact_state(rt.info); cmds=list(rt.admissible_commands)
  target_recs=sorted(r for r,t in fs['rec_type'].items() if t==target_rec_type and f'go to {r}' in cmds)
  if not target_recs:return {'family':family.name,'eligible':False,'reason':'NO_TARGET_RECEPTACLE_COMMAND'}
  target_rec=target_recs[0];objs=[]
  for o,t in fs['obj_type'].items():
   if t!=target_type:continue
   src=fs['in_rec'].get(o)
   if not src or fs['rec_type'].get(src)==target_rec_type:continue
   objs.append({'object':o,'source':src,'source_type':fs['rec_type'].get(src),'source_openable':src in fs['openable']})
  objs.sort(key=lambda x:(x['source'],x['object']))
  if len(objs)<2:return {'family':family.name,'eligible':False,'reason':'LT2_UNFINISHED_TARGET_OBJECTS'}
  by={}
  for x in objs:by.setdefault(x['source'],[]).append(x)
  groups=sorted([(s,xs) for s,xs in by.items() if len(xs)>=2],key=lambda z:(-len(z[1]),z[0]))
  if groups:
   src,xs=groups[0];pair=xs[:2];go_open(rt,src,prefix);delayed=True
  else:
   first=[sorted(xs,key=lambda x:x['object'])[0] for s,xs in sorted(by.items())]
   if len(first)<2:return {'family':family.name,'eligible':False,'reason':'NO_TWO_DISTINCT_SOURCES'}
   pair=first[:2];delayed=False
  reset_hash=rt.hash();obs=rt.observation;reset_cmds=list(rt.admissible_commands);prefix_actions=[x.command for x in prefix]
 finally:rt.close()
 a,b=pair;ba=branch(str(game),prefix,a,b,target_rec);bb=branch(str(game),prefix,b,a,target_rec)
 if not(ba['valid'] and bb['valid']):return {'family':family.name,'eligible':False,'reason':'BRANCH_REPLAY_NOT_BOTH_SUCCESS'}
 return {'family':family.name,'eligible':True,'game_path':str(game.relative_to(ROOT)).replace('\\','/'),'trial':game.parent.name,
 'target_object_type':target_type,'target_receptacle_type':target_rec_type,'target_receptacle':target_rec,'object_a':a,'object_b':b,
 'delayed_divergence':delayed,'common_prefix_actions':prefix_actions,'initial_state_hash':initial_hash,'reset_state_hash':reset_hash,
 'reset_observation_sha256':sha(obs),'reset_admissible_commands':reset_cmds,'reset_admissible_commands_sha256':hjson(reset_cmds),
 'a_first_divergent_action':ba['first_divergent'],'b_first_divergent_action':bb['first_divergent'],'branch_a_actions':ba['actions'],'branch_b_actions':bb['actions'],
 'branch_a_won':ba['valid'],'branch_b_won':bb['valid']}
def exclusion_families():
 ex=set();sources=[]
 for p in sorted(Path('results/design').glob('*.json')):
  try:d=json.load(open(p))
  except:continue
  if not isinstance(d,dict):continue
  rows=d.get('selected_pairs')
  if not isinstance(rows,list):continue
  fs={r.get('family') for r in rows if isinstance(r,dict) and isinstance(r.get('family'),str) and r['family'].startswith('pick_two_obj_and_place-')}
  if fs: ex|=fs;sources.append({'path':str(p),'n':len(fs),'families_sha256':sha('\n'.join(sorted(fs)))})
 return ex,sources
def main():
 ex,exsrc=exclusion_families();rows=[]
 fams=sorted(p for p in BASE.glob('pick_two_obj_and_place-*') if p.is_dir())
 for i,f in enumerate(fams,1):
  if f.name in ex:
   rows.append({'family':f.name,'eligible':False,'reason':'PRIOR_SELECTED_FAMILY_EXCLUDED'});continue
  try:r=build_family(f)
  except Exception as e:r={'family':f.name,'eligible':False,'reason':'EXCEPTION','error':f'{type(e).__name__}:{e}'}
  rows.append(r)
  if i%25==0: print(json.dumps({'scan':i,'eligible_so_far':sum(bool(x.get('eligible')) for x in rows)},sort_keys=True),flush=True)
 elig=[r for r in rows if r.get('eligible')];elig.sort(key=lambda r:sha(PAIR_SALT+'|'+r['family']+'|'+r['trial']))
 if len(elig)<TARGET:raise RuntimeError(f'INSUFFICIENT_FRESH_ELIGIBLE {len(elig)}<{TARGET}')
 sel=elig[:TARGET]
 for i,r in enumerate(sel):r['frozen_pair_index']=i;r['replay_residual_split']='development' if i<24 else 'confirmation'
 out={'kind':'PLANCARRY_REPLAY_RESIDUAL_FRESH48_MANIFEST_V1','scientific_result':'NOT_ASSESSED','model_calls':0,'environment_only':True,
 'source_split':'train','task_type':'pick_two_obj_and_place','trial_salt':TRIAL_SALT,'selection_salt':PAIR_SALT,'selection_rule':'SHA256 salt over fresh eligible family|trial; first48; indices0..23 development,24..47 sealed confirmation',
 'prior_selected_family_exclusion_count':len(ex),'prior_selected_family_exclusion_sources':exsrc,'scan_count':len(rows),'fresh_eligible_count':len(elig),'selected_pair_count':48,
 'development_n':24,'confirmation_n':24,'development_confirmation_family_overlap':0,'delayed_divergence_selected':sum(bool(r['delayed_divergence']) for r in sel),
 'both_branch_replay_success_all':all(r['branch_a_won'] and r['branch_b_won'] for r in sel),'valid_seen_consumed':False,'valid_unseen_consumed':False,
 'selected_pairs':sel,'scan_audit':[{'family':r['family'],'eligible':r.get('eligible',False),'reason':r.get('reason')} for r in rows]}
 OUT.parent.mkdir(parents=True,exist_ok=True);raw=(json.dumps(out,indent=2,sort_keys=True)+'\n').encode();OUT.write_bytes(raw)
 print('FINAL',json.dumps({'path':str(OUT),'sha256':hashlib.sha256(raw).hexdigest(),'fresh_eligible_count':len(elig),'selected':48,'delayed':out['delayed_divergence_selected'],'excluded':len(ex)},sort_keys=True),flush=True)
if __name__=='__main__':main()
