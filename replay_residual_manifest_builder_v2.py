#!/usr/bin/env python3
import json,hashlib
from pathlib import Path
import replay_residual_manifest_builder_v1 as b
OUT=Path('results/design/plancarry_replay_residual_fresh48_manifest_v1.json')
CANDIDATE_SALT='plancarry-replay-residual-v1-candidate-order-2026-08-21'
def sha(x):return hashlib.sha256(x.encode()).hexdigest()
def main():
 ex,exsrc=b.exclusion_families()
 fams=[p for p in b.BASE.glob('pick_two_obj_and_place-*') if p.is_dir() and p.name not in ex]
 fams.sort(key=lambda p:sha(CANDIDATE_SALT+'|'+p.name))
 audit=[];sel=[]
 for rank,f in enumerate(fams):
  try:r=b.build_family(f)
  except Exception as e:r={'family':f.name,'eligible':False,'reason':'EXCEPTION','error':f'{type(e).__name__}:{e}'}
  audit.append({'candidate_rank':rank,'family':f.name,'eligible':bool(r.get('eligible')),'reason':r.get('reason')})
  if r.get('eligible'):
   sel.append(r)
   print(json.dumps({'candidate_rank':rank,'eligible_n':len(sel),'family':f.name,'delayed':r.get('delayed_divergence')},sort_keys=True),flush=True)
   if len(sel)==48:break
 if len(sel)<48:raise RuntimeError(f'INSUFFICIENT_FRESH_ELIGIBLE {len(sel)}<48 after {len(audit)} scanned')
 for i,r in enumerate(sel):r['frozen_pair_index']=i;r['replay_residual_split']='development' if i<24 else 'confirmation'
 dev={r['family'] for r in sel[:24]};con={r['family'] for r in sel[24:]}
 out={'kind':'PLANCARRY_REPLAY_RESIDUAL_FRESH48_MANIFEST_V1','scientific_result':'NOT_ASSESSED','model_calls':0,'environment_only':True,
 'source_split':'train','task_type':'pick_two_obj_and_place','trial_salt':b.TRIAL_SALT,'candidate_order_salt':CANDIDATE_SALT,
 'selection_rule':'Exclude all prior top-level selected two-object families; hash-order remaining train families; environment-validate in that fixed order; take first48 eligible; indices0..23 development and24..47 sealed confirmation.',
 'prior_selected_family_exclusion_count':len(ex),'prior_selected_family_exclusion_sources':exsrc,'scan_count':len(audit),'selected_pair_count':48,
 'development_n':24,'confirmation_n':24,'development_confirmation_family_overlap':len(dev&con),'delayed_divergence_selected':sum(bool(r['delayed_divergence']) for r in sel),
 'both_branch_replay_success_all':all(r['branch_a_won'] and r['branch_b_won'] for r in sel),'valid_seen_consumed':False,'valid_unseen_consumed':False,
 'selected_pairs':sel,'scan_audit':audit}
 OUT.parent.mkdir(parents=True,exist_ok=True);raw=(json.dumps(out,indent=2,sort_keys=True)+'\n').encode();OUT.write_bytes(raw)
 print('FINAL '+json.dumps({'path':str(OUT),'sha256':hashlib.sha256(raw).hexdigest(),'scan_count':len(audit),'selected':48,'delayed':out['delayed_divergence_selected'],'excluded':len(ex)},sort_keys=True),flush=True)
if __name__=='__main__':main()
