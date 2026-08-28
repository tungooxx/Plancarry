#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
ROOT=D.parent.parent
H=lambda b:hashlib.sha256(b).hexdigest()
HT=lambda s:H(s.encode())
def rel(s):
 m='/json_2.1.1/'
 if m in s:return s.split(m,1)[1]
 if s.startswith('json_2.1.1/'):return s[len('json_2.1.1/'):]
 return s
A=json.loads((D/'plancarry_exec_persistence_locus_exposure_audit_v1_20260828.json').read_text())
M=json.loads((D/'plancarry_exec_fresh_train_manifest_v1_20260828.json').read_text())
P=json.loads((D/'plancarry_exec_persistence_locus_prereg_v1_20260828.json').read_text())
assert len(M['candidates'])==176==M['candidate_count']==P['population']['max_scan']
assert len(set(M['candidates']))==176
assert M['candidate_pool_sha256']==HT('\n'.join(M['candidates'])+'\n')
assert P['population']['target_eligible']==16 and P['runtime']['post_reset_environment_action_horizon']==8
assert P['metrics']['later_visible_goal_progress']['first_action_excluded'] is True
assert P['statistics']['alpha']==0.05 and '>= 0.25' in P['statistics']['primary_effect_guard']
# Exact one-sided paired-binomial tail is frozen; 5-0 discordants passes .05, 4-0 does not.
import math
def one_sided(w,l):
 d=w+l
 return 1.0 if d==0 else sum(math.comb(d,k) for k in range(w,d+1))/(2**d)
assert abs(one_sided(5,0)-0.03125)<1e-15
assert abs(one_sided(4,0)-0.0625)<1e-15
assert one_sided(0,0)==1.0
assert len(P['terminal_rules']['primary_gate_components'])==4
assert P['statistics']['primary_absolute_guard'].endswith('>= 0.50')
assert P['stale_commitment_policy']['no_rescue'] is True
assert 'no excluding stale-fallback episodes' in P['terminal_rules']['no_rescue']
# Reconstruct exact binding pool from frozen 790-path inventory.
inv=json.loads((D/'plancarry_localcontinuation_canonical_inventory_v1_20260823.json').read_text())
I={rel(x) for x in inv};absI=['/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/'+r for r in I]
babs=sorted(absI,key=lambda p:HT('plancarry-binding-v1-2026-08-18\n'+p))[:180]
assert HT('\n'.join(babs)+'\n')=='d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee'
bind={rel(x) for x in babs}
# Reconstruct exact GDAA union.
gdaa=set()
for src in A['gdaa_development_union']['sources']:
 x=json.loads((ROOT/src['file']).read_text());assert H((ROOT/src['file']).read_bytes())==src['file_sha256'];gdaa|={rel(v) for v in x['candidates']}
assert len(gdaa)==199
# Reconstruct fixed historical exposure source list only (new artifacts cannot mutate the pre-freeze set).
artifact=set()
for src in A['historical_design_artifact_exposure']['sources']:
 p=ROOT/src['file'];assert H(p.read_bytes())==src['file_sha256'];x=json.loads(p.read_text())
 def walk(v):
  if isinstance(v,dict):
   for z in v.values():walk(z)
  elif isinstance(v,list):
   for z in v:walk(z)
  elif isinstance(v,str) and 'pick_and_place_simple-' in v and v.endswith('/game.tw-pddl'):
   r=rel(v)
   if r in I:artifact.add(r)
 walk(x)
assert len(artifact)==544
assert not(set(M['candidates'])&bind) and not(set(M['candidates'])&gdaa) and not(set(M['candidates'])&artifact)
excluded=bind|gdaa|artifact;fresh=I-excluded
assert len(excluded)==614 and len(fresh)==176
rank=sorted(fresh,key=lambda r:(HT(M['selection_salt']+'\n'+r),r))
assert rank==M['candidates']
assert A['fresh_capacity']['selected_scan_pool_sha256']==M['candidate_pool_sha256']
assert all(A['disjointness'].values())
# Recompute self-excluded canonical payload hashes.
for obj in (A,M,P):
 q=dict(obj);expected=q.pop('payload_sha256');assert H(json.dumps(q,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode())==expected
print('PASS_PLANCARRY_EXEC_PRE_SCIENCE_FREEZE')
