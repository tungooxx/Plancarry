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
# Exact one-sided paired-binomial tail is frozen; 5-0 discordants passes .05, 4-0 does not.
import math
def one_sided(w,l):
 d=w+l
 return 1.0 if d==0 else sum(math.comb(d,k) for k in range(w,d+1))/(2**d)
assert abs(one_sided(5,0)-0.03125)<1e-15
assert abs(one_sided(4,0)-0.0625)<1e-15
assert one_sided(0,0)==1.0
assert P['stale_commitment_policy']['no_rescue'] is True
assert 'no excluding stale-fallback episodes' in P['terminal_rules']['no_rescue']

# Repaired terminal-gate logic: two adherence contrasts form a fixed Holm family.
def paired_one_sided(w,l):
 d=w+l
 return 1.0 if d==0 else sum(math.comb(d,k) for k in range(w,d+1))/(2**d)
def holm2(p_a,p_b):
 lo,hi=sorted([p_a,p_b])
 return lo<=0.025 and hi<=0.05
def repaired_gate(ext_iaa,bind_iaa,pass_iaa,ext_later,bind_later,ext_success,bind_success):
 # Inputs are 16-element booleans.
 def paired(a,b):
  w=sum(x and not y for x,y in zip(a,b)); l=sum((not x) and y for x,y in zip(a,b))
  return paired_one_sided(w,l)
 p_bind=paired(ext_iaa,bind_iaa); p_pass=paired(ext_iaa,pass_iaa)
 iaa_effect_bind=sum(ext_iaa)/16-sum(bind_iaa)/16
 iaa_effect_pass=sum(ext_iaa)/16-sum(pass_iaa)/16
 p_later=paired(ext_later,bind_later)
 later_effect=sum(ext_later)/16-sum(bind_later)/16
 return (
  holm2(p_bind,p_pass)
  and iaa_effect_bind>=0.25 and iaa_effect_pass>=0.25 and sum(ext_iaa)/16>=0.50
  and p_later<=0.05 and later_effect>=0.25 and sum(ext_later)/16>=0.50
  and sum(ext_success)>=sum(bind_success)
 )
assert len(P['terminal_rules']['primary_gate_components'])==8
assert P['statistics']['adherence_primary_family']['multiplicity'].startswith('Holm step-down FWER 0.05')
# Exact p-value canaries.
assert abs(paired_one_sided(5,0)-0.03125)<1e-15
assert abs(paired_one_sided(4,0)-0.0625)<1e-15
assert paired_one_sided(0,0)==1.0
# A3 false-pass counterexample from independent review MUST now fail:
# external and binding both adhere/succeed 16/16, while external later-progress is 8/16 vs binding 0/16.
ones=[True]*16; zeros=[False]*16; half=[True]*8+[False]*8
assert repaired_gate(ones,ones,zeros,half,zeros,ones,ones) is False
# Binding-match kill remains fail-closed even if external downstream progress is perfect.
assert repaired_gate(ones,ones,zeros,ones,zeros,ones,ones) is False
# Lower TaskSuccess cannot pass even with strong adherence and downstream progress.
ext_iaa=ones; bind_iaa=zeros; passive_iaa=zeros; ext_later=ones; bind_later=zeros
ext_success=[True]*15+[False]; bind_success=ones
assert repaired_gate(ext_iaa,bind_iaa,passive_iaa,ext_later,bind_later,ext_success,bind_success) is False
# Positive sentinel: strong adherence advantage over BOTH comparators, later progress advantage, TaskSuccess parity.
assert repaired_gate(ones,zeros,zeros,ones,zeros,ones,ones) is True
assert 'one-step external executable-controller utility' in P['terminal_rules']['pass_claim_scope']
assert 'does NOT establish persistence beyond the forced action1 state transition' in P['terminal_rules']['pass_claim_scope']

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
