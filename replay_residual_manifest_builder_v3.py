#!/usr/bin/env python3
import json,hashlib
from pathlib import Path
import replay_residual_manifest_builder_v1 as b
OUT=Path('results/design/plancarry_replay_residual_delayed48_manifest_v1.json')
CANDIDATE_SALT='plancarry-replay-residual-v1-delayed48-candidate-order-2026-08-21'
def sha(x):return hashlib.sha256(x.encode()).hexdigest()
def main():
 ex,exsrc=b.exclusion_families()
 fams=[p for p in b.BASE.glob('pick_two_obj_and_place-*') if p.is_dir() and p.name not in ex]
 fams.sort(key=lambda p:sha(CANDIDATE_SALT+'|'+p.name))
 audit=[];sel=[]
 for rank,f in enumerate(fams):
  try:r=b.build_family(f)
  except Exception as e:r={'family':f.name,'eligible':False,'reason':'EXCEPTION','error':f'{type(e).__name__}:{e}'}
  delayed_ok=bool(r.get('eligible')) and bool(r.get('delayed_divergence')) and len(r.get('common_prefix_actions',[]))>=1
  reason=r.get('reason') if not r.get('eligible') else (None if delayed_ok else 'NOT_DELAYED_DIVERGENCE')
  audit.append({'candidate_rank':rank,'family':f.name,'environment_eligible':bool(r.get('eligible')),'selected_eligible':delayed_ok,'reason':reason})
  if delayed_ok:
   sel.append(r)
   print(json.dumps({'candidate_rank':rank,'selected_n':len(sel),'family':f.name,'common_prefix_len':len(r['common_prefix_actions'])},sort_keys=True),flush=True)
   if len(sel)==48:break
 if len(sel)<48:raise RuntimeError(f'INSUFFICIENT_FRESH_DELAYED_ELIGIBLE {len(sel)}<48 after {len(audit)} scanned')
 for i,r in enumerate(sel):r['frozen_pair_index']=i;r['replay_residual_split']='development' if i<24 else 'confirmation'
 dev={r['family'] for r in sel[:24]};con={r['family'] for r in sel[24:]}
 out={'kind':'PLANCARRY_REPLAY_RESIDUAL_DELAYED48_MANIFEST_V1','scientific_result':'NOT_ASSESSED','model_calls':0,'environment_only':True,
 'source_split':'train','task_type':'pick_two_obj_and_place','trial_salt':b.TRIAL_SALT,'candidate_order_salt':CANDIDATE_SALT,
 'selection_rule':'Exclude all prior top-level selected two-object families; hash-order remaining train families; environment-validate in fixed order; require delayed_divergence=true and >=1 common prefix action; take first48; indices0..23 development,24..47 sealed confirmation.',
 'prior_selected_family_exclusion_count':len(ex),'prior_selected_family_exclusion_sources':exsrc,'scan_count':len(audit),'selected_pair_count':48,
 'development_n':24,'confirmation_n':24,'development_confirmation_family_overlap':len(dev&con),'all_delayed_divergence':all(r['delayed_divergence'] for r in sel),
 'min_common_prefix_actions':min(len(r['common_prefix_actions']) for r in sel),'max_common_prefix_actions':max(len(r['common_prefix_actions']) for r in sel),
 'both_branch_replay_success_all':all(r['branch_a_won'] and r['branch_b_won'] for r in sel),'valid_seen_consumed':False,'valid_unseen_consumed':False,
 'selected_pairs':sel,'scan_audit':audit}
 OUT.parent.mkdir(parents=True,exist_ok=True);raw=(json.dumps(out,indent=2,sort_keys=True)+'\n').encode();OUT.write_bytes(raw)
 print('FINAL '+json.dumps({'path':str(OUT),'sha256':hashlib.sha256(raw).hexdigest(),'scan_count':len(audit),'selected':48,'min_common_prefix':out['min_common_prefix_actions'],'max_common_prefix':out['max_common_prefix_actions'],'excluded':len(ex)},sort_keys=True),flush=True)
if __name__=='__main__':main()
