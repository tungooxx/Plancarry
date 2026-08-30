import hashlib, json, pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
C=ROOT/'results/design/plancarry_cpds_actual_family_execution_semantics_v1_20260830.json'
SRC=ROOT/'results/design/plancarry_cpds_actual_development_source_snapshot_v2_20260829.json'
V4=ROOT/'results/design/plancarry_cpds_v4_branch_preference_endpoint_contract_a2_20260830.json'
REC=ROOT/'results/design/plancarry_cpds_recurrent_realization_feature_basis_v1_20260829.json'
class TestActualExecutionSemantics(unittest.TestCase):
 def setUp(self):
  self.c=json.loads(C.read_text()); self.src=json.loads(SRC.read_text()); self.v4=json.loads(V4.read_text()); self.rec=json.loads(REC.read_text())
 def test_self_hash(self):
  x=dict(self.c); got=x.pop('canonical_object_sha256_without_self_field')
  raw=json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
  self.assertEqual(got,hashlib.sha256(raw).hexdigest())
 def test_actual_development_is_33_by_two(self):
  self.assertEqual(len(self.src['families']),33)
  self.assertTrue(all(len(f['common_prefix_transition_keys'])==2 for f in self.src['families']))
 def test_timeline_exact(self):
  t=self.c['actual_timeline']
  self.assertEqual(t['matched_G_exposure_locations'],['RESET_PREFIX','POST_TRANSITION_1','BRANCH_POINT'])
  self.assertEqual(t['prefix_replay_F_calls_by_G_site'],[0,1,2]); self.assertEqual(t['total_F_calls_per_matched_arm'],3)
  self.assertTrue(self.c['actual_development_structure']['immediate_step_is_not_an_F_input'])
 def test_matched_geometry(self):
  for a in ['STATIC_REPEAT','ALIGNED_RECURSION','TRANSITION_PERMUTED','MATCHED_INFORMATION']:
   self.assertEqual(self.c['arms'][a]['G_exposure_locations'],['RESET_PREFIX','POST_TRANSITION_1','BRANCH_POINT'])
   self.assertEqual(self.c['arms'][a]['F_calls_by_site'],[0,1,2])
 def test_aligned_and_permuted_causal_prefix(self):
  self.assertEqual(self.c['arms']['ALIGNED_RECURSION']['prefix_orders']['POST_TRANSITION_1'],[0])
  self.assertEqual(self.c['arms']['TRANSITION_PERMUTED']['prefix_orders']['POST_TRANSITION_1'],[0])
  self.assertEqual(self.c['arms']['ALIGNED_RECURSION']['prefix_orders']['BRANCH_POINT'],[0,1])
  self.assertEqual(self.c['arms']['TRANSITION_PERMUTED']['prefix_orders']['BRANCH_POINT'],[1,0])
 def test_oneshot_exactly_one_branch_call(self):
  o=self.c['arms']['STATIC_ONESHOT']
  self.assertEqual(o['G_exposure_locations'],['BRANCH_POINT']); self.assertEqual(o['F_calls_by_site'],[0,0,0]); self.assertEqual(o['branch_state'],'SEALED_Z0')
 def test_no_carry_no_interface(self):
  self.assertEqual(self.c['arms']['NO_CARRY']['G_exposure_locations'],[])
  self.assertEqual(self.c['arms']['NO_CARRY']['branch_state'],'NO_CPDS_STATE')
 def test_v4_development_guard_unchanged(self):
  d=self.v4['development_rule']
  self.assertEqual(d['positive_static_min'],22); self.assertEqual(d['positive_permuted_min'],22)
  self.assertEqual(d['median_C_static_nats_min'],0.05); self.assertEqual(d['median_C_permuted_nats_min'],0.05)
  self.assertTrue(d['median_C_information_gt0']); self.assertTrue(d['median_D_aligned_gt0'])
  self.assertNotIn('median_C_oneshot_gt0',d)
  self.assertFalse(self.c['preserved_science']['development_C_oneshot_guard'])
 def test_recurrent_formula_identity_preserved(self):
  self.assertEqual(self.c['arms']['ALIGNED_RECURSION']['branch_state'],'F(F(z0,x1),x2)')
  self.assertIn('unit_l2',json.dumps(self.rec))
  self.assertEqual(self.c['arms']['TRANSITION_PERMUTED']['branch_state'],'F(F(z0,x2),x1)')
 def test_oneshot_redundancy_is_explicit_not_hidden(self):
  self.assertIn('C_oneshot equals C_static',self.c['branch_scoring']['oneshot_static_relation'])
  self.assertTrue(self.c['preserved_science']['confirmation_C_oneshot_guard_retained'])
 def test_guards_are_mechanical_and_nonfiltering(self):
  g=self.c['mechanical_guards']
  self.assertEqual(g['immediate_action_invariance']['split_rule'].count('33'),2)
  self.assertIn('never filters/replaces',g['immediate_action_invariance']['split_rule'])
  self.assertIn('Required count 33/33',g['graph_admissibility']['split_rule'])
  self.assertIn('never post-score family filtering or replacement',g['graph_admissibility']['split_rule'])
  self.assertIn('No new generic-competence numeric gate',g['generic_competence'])
 def test_confirmation_and_planroute_remain_closed(self):
  self.assertEqual(self.c['preserved_science']['confirmation'],'HARD_SEALED_NO_RUNTIME_ROUTE')
  self.assertEqual(self.c['preserved_science']['planroute'],'USER_NOOP_RETIRED')
  self.assertIn('NO_CONFIRMATION_BODY_OR_OUTCOMES',self.c['non_authorizations'])
if __name__=='__main__': unittest.main()
