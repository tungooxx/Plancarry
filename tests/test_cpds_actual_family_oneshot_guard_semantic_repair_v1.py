import hashlib,json,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
P=ROOT/'results/design/plancarry_cpds_actual_family_oneshot_guard_semantic_repair_v1_20260830.json'
S=ROOT/'results/design/plancarry_cpds_actual_family_execution_semantics_v1_20260830.json'
V=ROOT/'results/design/plancarry_cpds_v4_branch_preference_endpoint_contract_a2_20260830.json'
class TestOneShotGuardSemanticRepair(unittest.TestCase):
 def setUp(self): self.p=json.loads(P.read_text()); self.s=json.loads(S.read_text()); self.v=json.loads(V.read_text())
 def test_self_hash(self):
  x=dict(self.p); got=x.pop('canonical_object_sha256_without_self_field'); raw=json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode(); self.assertEqual(got,hashlib.sha256(raw).hexdigest())
 def test_source_hashes_and_commit_bound(self):
  self.assertEqual(self.p['authority']['source_execution_semantics_commit'],'b921627c98b1846f8ad74430d21220e943fabaf9')
  self.assertEqual(self.p['authority']['source_execution_semantics_tree'],'41dcb4255b75bd67779fd5acf231fbbeed2cd498')
  self.assertEqual(self.p['authority']['source_execution_semantics_file_sha256'],hashlib.sha256(S.read_bytes()).hexdigest())
  self.assertEqual(self.p['authority']['v4_endpoint_file_sha256'],hashlib.sha256(V.read_bytes()).hexdigest())
 def test_redundancy_is_algebraically_explicit(self):
  a=self.p['algebraic_fact']; self.assertTrue(a['score_map_identity_required']); self.assertTrue(a['D_STATIC_ONESHOT_equals_D_STATIC_REPEAT']); self.assertTrue(a['C_oneshot_equals_C_static'])
  self.assertIn('C_oneshot equals C_static',self.s['branch_scoring']['oneshot_static_relation'])
 def test_effective_confirmation_support_has_no_oneshot_guard(self):
  req=self.p['semantic_repair']['effective_confirmation_support_requires']; self.assertEqual(len(req),7); self.assertFalse(any('oneshot' in x.lower() for x in req))
  self.assertIn('median C_oneshot >0',self.v['confirmation_rule']['support_requires'])  # immutable history remains visible
  paths=[x['json_path'] for x in self.p['supersession']['exact_inherited_fields_superseded']]; self.assertIn('confirmation_rule.support_requires',paths); self.assertIn('practical_effect_guards.median_C_oneshot_gt0',paths)
 def test_oneshot_retained_only_as_diagnostic(self):
  d=self.p['semantic_repair']['retain_for_transparency']; self.assertEqual(d['arm'],'STATIC_ONESHOT'); self.assertEqual(d['status'],'REDUNDANT_DIAGNOSTIC_CONSISTENCY_ONLY'); self.assertFalse(d['decision_authority']); self.assertFalse(d['support_authority']); self.assertFalse(d['independent_evidence_family'])
  self.assertIn('STATIC_ONESHOT',self.p['preserved_authority']['six_arms'])
 def test_primary_nonredundant_discriminators(self):
  self.assertEqual(self.p['semantic_repair']['effective_recurrence_specific_discriminators'],['C_static','C_permuted','C_information'])
  self.assertEqual(self.p['preserved_authority']['C_static_formula'],'D_ALIGNED_RECURSION-D_STATIC_REPEAT'); self.assertEqual(self.p['preserved_authority']['C_permuted_formula'],'D_ALIGNED_RECURSION-D_TRANSITION_PERMUTED')
 def test_statistics_and_development_are_unchanged(self):
  a=self.p['preserved_authority']; self.assertEqual((a['n'],a['positive_each_min']),(33,22)); self.assertEqual(a['p_22_of_33'],0.04007165622897446); self.assertEqual(a['p_21_of_33'],0.08137782872654498); self.assertTrue(a['IUT_both_static_and_permuted_required']); self.assertTrue(a['development_gates_unchanged']); self.assertFalse(a['development_C_oneshot_guard'])
  d=self.v['development_rule']; self.assertEqual(d['positive_static_min'],22); self.assertEqual(d['positive_permuted_min'],22); self.assertEqual(d['median_C_static_nats_min'],.05); self.assertEqual(d['median_C_permuted_nats_min'],.05); self.assertNotIn('median_C_oneshot_gt0',d)
 def test_actual_family_geometry_unchanged(self):
  self.assertEqual(self.s['actual_development_structure']['common_prefix_transition_count_per_family'],2); self.assertTrue(self.s['actual_development_structure']['immediate_step_is_not_an_F_input'])
  self.assertEqual(self.s['arms']['ALIGNED_RECURSION']['prefix_orders']['BRANCH_POINT'],[0,1]); self.assertEqual(self.s['arms']['TRANSITION_PERMUTED']['prefix_orders']['BRANCH_POINT'],[1,0]); self.assertEqual(self.s['arms']['STATIC_ONESHOT']['G_exposure_locations'],['BRANCH_POINT'])
 def test_confirmation_and_planroute_stay_sealed(self):
  a=self.p['preserved_authority']; self.assertEqual(a['confirmation'],'HARD_SEALED_NO_RUNTIME_ROUTE'); self.assertEqual(a['planroute'],'USER_NOOP_RETIRED'); self.assertFalse(self.p['future_confirmation_rule']['confirmation_accessed_during_repair']); self.assertIn('NO_CONFIRMATION_BODY_OR_OUTCOMES',self.p['non_authorizations'])
 def test_adapter_requires_review_pass_not_completion(self):
  e=self.p['development_execution_effect']; self.assertTrue(e['repair_completion_alone_is_not_sufficient']); self.assertEqual(e['adapter_may_resume_after'],'ONE_FRESH_NON_AUTHOR_EXACT_PASS_OF_THIS_IMMUTABLE_DELTA')
if __name__=='__main__': unittest.main()
