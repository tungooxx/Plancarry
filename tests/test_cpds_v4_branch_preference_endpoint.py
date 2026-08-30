import hashlib
import json
import math
import pathlib
import subprocess
import unittest
from math import comb

ROOT=pathlib.Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'results/design/plancarry_cpds_v4_branch_preference_endpoint_contract_a2_20260830.json'
AUDIT=ROOT/'results/design/plancarry_cpds_v4_branch_preference_endpoint_audit_a2_20260830.json'
RECURRENT=ROOT/'results/design/plancarry_cpds_recurrent_realization_feature_basis_v1_20260829.json'
ACTUAL_AUDIT=ROOT/'results/design/plancarry_cpds_actual_33x2_preoutcome_freeze_audit_v1_20260829.json'
V3='df17c5ee3a3d2c6bccd70367886216cd043d40f3'

def load(p): return json.loads(p.read_text())
def canonical_bytes(o): return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def git_show(path): return subprocess.check_output(['git','show',f'{V3}:{path}'],cwd=ROOT)
def tail(n,k,p=.5): return sum(comb(n,j)*(p**j)*((1-p)**(n-j)) for j in range(k,n+1))
def kcrit(n):
    for k in range(n+1):
        if tail(n,k,.5)<=.05: return k
    return n+1
def power(n,q=.75):
    k=kcrit(n)
    if k>n: return 0.0
    return tail(n,k,q)
def joint_lower(n,q=.75): return max(0.0,2*power(n,q)-1)
def contrasts(m):
    n=m['NO_CARRY']
    d={k:abs(v-n) for k,v in m.items()}
    return {
      'static':d['ALIGNED_RECURSION']-d['STATIC_REPEAT'],
      'permuted':d['ALIGNED_RECURSION']-d['TRANSITION_PERMUTED'],
      'information':d['ALIGNED_RECURSION']-d['MATCHED_INFORMATION'],
      'oneshot':d['ALIGNED_RECURSION']-d['STATIC_ONESHOT'],
      'nocarry':d['ALIGNED_RECURSION'],
    }

class TestCPDSV4BranchPreferenceEndpoint(unittest.TestCase):
  def test_01_contract_self_hash(self):
    o=load(CONTRACT); got=o.pop('canonical_object_sha256_without_self_field')
    self.assertEqual(got,sha(canonical_bytes(o)))

  def test_02_protected_authority_hashes(self):
    c=load(CONTRACT)['authority']
    self.assertEqual(sha(RECURRENT.read_bytes()),c['recurrent_realization_file_sha256'])
    self.assertEqual(sha(git_show('results/design/plancarry_cpds_numeric_statistical_decision_contract_v3_20260829.json')),c['v3_statistical_contract_sha256'])
    self.assertEqual(sha(git_show('results/design/plancarry_cpds_randomized_arm_slot_inference_spec_v1_20260829.json')),c['v3_randomized_slot_spec_sha256'])
    self.assertEqual(c['actual_33x2_freeze_commit'],'e4c1ed318c96f5a2e6ac3e059d5e43dfec14d16a')
    self.assertEqual(c['transaction_sha256'],'c00a289a098a99831e50f9d8808608abc6b71d4ef0a53d9d7d834a7cc1f13049')
    self.assertEqual(c['assignment_bundle_sha256'],'d01568854cabce0d2a219db3da71cd4c384f6680cf72dba455e21af21d59a002')

  def test_03_branch_label_swap_invariance(self):
    examples=[
      {'NO_CARRY':.2,'STATIC_ONESHOT':.1,'STATIC_REPEAT':.45,'ALIGNED_RECURSION':.9,'TRANSITION_PERMUTED':-.15,'MATCHED_INFORMATION':.3},
      {'NO_CARRY':-1.2,'STATIC_ONESHOT':.0,'STATIC_REPEAT':-1.6,'ALIGNED_RECURSION':-2.3,'TRANSITION_PERMUTED':-.9,'MATCHED_INFORMATION':-1.1},
      {'NO_CARRY':0.0,'STATIC_ONESHOT':0.0,'STATIC_REPEAT':0.0,'ALIGNED_RECURSION':0.0,'TRANSITION_PERMUTED':0.0,'MATCHED_INFORMATION':0.0},
    ]
    for m in examples:
      self.assertEqual(contrasts(m),contrasts({k:-v for k,v in m.items()}))

  def test_04_pairwise_arm_swap_antisymmetry(self):
    m={'NO_CARRY':.2,'STATIC_ONESHOT':.1,'STATIC_REPEAT':.45,'ALIGNED_RECURSION':.9,'TRANSITION_PERMUTED':-.15,'MATCHED_INFORMATION':.3}
    mapping={'static':'STATIC_REPEAT','permuted':'TRANSITION_PERMUTED','information':'MATCHED_INFORMATION','oneshot':'STATIC_ONESHOT'}
    base=contrasts(m)
    for key,comp in mapping.items():
      x=dict(m); x['ALIGNED_RECURSION'],x[comp]=x[comp],x['ALIGNED_RECURSION']
      self.assertTrue(math.isclose(contrasts(x)[key],-base[key],rel_tol=0,abs_tol=1e-15))

  def test_05_all_720_assignments_have_pairwise_sign_symmetry(self):
    import itertools
    arms=['NO_CARRY','STATIC_ONESHOT','STATIC_REPEAT','ALIGNED_RECURSION','TRANSITION_PERMUTED','MATCHED_INFORMATION']
    slot_margin=[-1.7,-.6,.1,.55,1.2,2.4]
    for key,comp in [('static','STATIC_REPEAT'),('permuted','TRANSITION_PERMUTED')]:
      vals=[]
      for perm in itertools.permutations(arms):
        m={arm:slot_margin[i] for i,arm in enumerate(perm)}
        vals.append(contrasts(m)[key])
      self.assertEqual(len(vals),720)
      pos=sorted(round(v,12) for v in vals if v>0)
      neg=sorted(round(-v,12) for v in vals if v<0)
      self.assertEqual(pos,neg)
      self.assertEqual(sum(v>0 for v in vals),sum(v<0 for v in vals))

  def test_06_n33_k22_exact_tail(self):
    c=load(CONTRACT)['fixed_cohort_randomization_inference']
    self.assertEqual(c['n'],33); self.assertEqual(c['positive_each_min'],22)
    self.assertTrue(math.isclose(tail(33,22),0.04007165622897446,rel_tol=0,abs_tol=1e-17))
    self.assertTrue(math.isclose(tail(33,21),0.08137782872654498,rel_tol=0,abs_tol=1e-17))
    self.assertLessEqual(tail(33,22),.05); self.assertGreater(tail(33,21),.05)

  def test_07_n33_joint_power_minimality(self):
    self.assertGreaterEqual(joint_lower(33,.75),.8)
    self.assertTrue(math.isclose(power(33,.75),0.9012785313933738,rel_tol=0,abs_tol=1e-15))
    self.assertTrue(math.isclose(joint_lower(33,.75),0.8025570627867475,rel_tol=0,abs_tol=1e-15))
    self.assertTrue(all(joint_lower(n,.75)<.8 for n in range(1,33)))

  def test_08_zero_and_no_filtering(self):
    c=load(CONTRACT)
    self.assertEqual(c['fixed_cohort_randomization_inference']['zero'],'NONPOSITIVE')
    self.assertTrue(c['orientation_invariant_endpoint']['tie_rule'].startswith('Exact C=0'))
    self.assertTrue(c['validity_and_isolation']['all_33_each_split_required'])
    self.assertFalse(c['validity_and_isolation']['family_filtering_after_scores'])
    self.assertFalse(c['validity_and_isolation']['replacement_after_scores'])

  def test_09_effect_interpretation_is_unsigned_not_correctness(self):
    c=load(CONTRACT); e=c['practical_effect_guards']['effect_interpretation']
    self.assertTrue(math.isclose(math.exp(.05),1.0512710963760241,rel_tol=0,abs_tol=1e-15))
    self.assertIn('unsigned branch-mass-ratio displacement factor',e)
    self.assertIn('neither a raw probability ratio nor a correctness-direction claim',e)
    ep=json.dumps(c['orientation_invariant_endpoint'],sort_keys=True).lower()
    self.assertNotIn('correct_branch',ep); self.assertNotIn('opposing_branch',ep)
    self.assertNotIn('preferred_branch',ep); self.assertNotIn('task_correct',ep)

  def test_10_evaluator_only_branch_classes_no_carrier_path(self):
    c=load(CONTRACT)
    self.assertEqual(c['branch_semantics']['correctness_semantics'],'UNDEFINED_AND_FORBIDDEN')
    self.assertIn('no directed path to z0',c['branch_semantics']['carrier_visibility'])
    self.assertIn('score map must be sealed before evaluator-only A/B class membership',c['branch_semantics']['evaluator_opening_rule'])

  def test_11_full_failed_assumption_accounting(self):
    rows=load(CONTRACT)['lineage_reconciliation']
    self.assertEqual(len(rows),12)
    self.assertEqual([r['id'] for r in rows],[f'L{i:02d}_'+suffix for i,suffix in [
      (1,'SYMBOLIC_AB_BINDING'),(2,'STEP1_STEP2_BINDING'),(3,'MODEL_ONLY_RECOVERY'),(4,'NATURAL_EXECUTOR_QUALIFICATION'),
      (5,'FIXED_SLOT_CONTROL'),(6,'MSA2_SPECIFICITY'),(7,'ACTIONMATCHED_PREVALENCE'),(8,'ONE_SHOT_RESIDUAL_SUFFICIENCY'),
      (9,'END_TASK_SUCCESS_ENTRY'),(10,'UNTOUCHED_VALID_SEEN'),(11,'REORDERING_INDEPENDENCE'),(12,'REFERENCE_ROUTE_CORRECTNESS')]])
    self.assertTrue(all(r['status']=='NOT_INHERITED' for r in rows))

  def test_12_support_scope_narrowed(self):
    c=load(CONTRACT)['confirmation_rule']
    self.assertIn('branch-preference displacement magnitude',c['support_scope'])
    for forbidden in ('route correctness','branch semantic identity','end-task success','superpopulation prevalence'):
      self.assertIn(forbidden,c['support_scope'])

  def test_13_v3_endpoint_directed_semantics_explicitly_superseded(self):
    c=load(CONTRACT)['supersession']
    self.assertIn('correct/opposing',c['v3_superseded'])
    self.assertIn('n=33/k=22',c['v3_reused'])

  def test_14_practical_guards_and_development_are_precommitted(self):
    c=load(CONTRACT)
    g=c['practical_effect_guards']; d=c['development_rule']
    self.assertEqual(g['median_C_static_nats_min'],.05); self.assertEqual(g['median_C_permuted_nats_min'],.05)
    self.assertEqual(d['positive_static_min'],22); self.assertEqual(d['positive_permuted_min'],22)
    self.assertEqual(d['on_failure'],'DEVELOPMENT_FUTILITY_STOP_CONFIRMATION_REMAINS_SEALED')

  def test_15_no_science_authorization(self):
    c=load(CONTRACT)
    self.assertEqual(c['scientific_result'],'NOT_ASSESSED')
    self.assertIn('NO_MODEL_FORWARD',c['non_authorizations'])
    self.assertIn('NO_DEVELOPMENT_OUTCOMES',c['non_authorizations'])
    self.assertIn('NO_CONFIRMATION_OUTCOMES',c['non_authorizations'])
    self.assertEqual(c['preserved_authority']['planroute'],'USER_NOOP_RETIRED')

  def test_16_audit_hash_closure(self):
    a=load(AUDIT); x=dict(a); got=x.pop('canonical_object_sha256_without_self_field')
    self.assertEqual(got,sha(canonical_bytes(x)))
    self.assertEqual(a['contract_sha256'],sha(CONTRACT.read_bytes()))
    self.assertEqual(a['test_sha256'],sha(pathlib.Path(__file__).read_bytes()))
    self.assertEqual(a['model_loads'],0); self.assertEqual(a['model_forwards'],0); self.assertEqual(a['environment_execution'],0)
    self.assertEqual(a['development_outcome_access'],0); self.assertEqual(a['confirmation_outcome_access'],0)

if __name__=='__main__': unittest.main()
