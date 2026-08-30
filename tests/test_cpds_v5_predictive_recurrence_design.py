import json, math, pathlib, unittest
P=pathlib.Path(__file__).parents[1]/'results/design/plancarry_cpds_v5_predictive_recurrence_repair_a1_20260830.json'
class T(unittest.TestCase):
 def setUp(self): self.d=json.loads(P.read_text())
 def test_same_cpds_no_discovery(self):
  self.assertEqual(self.d['parent_hypothesis_id'],'5d262191-9177-49ce-86ff-4944832aa1dc')
  self.assertFalse(self.d['scope']['new_discovery_round']); self.assertFalse(self.d['scope']['new_hypothesis'])
  self.assertEqual(self.d['scope']['planroute'],'USER_NOOP_RETIRED')
 def test_v4_failure_bound(self):
  self.assertEqual(self.d['source_v4_negative_result_id'],'ae770645-0850-4dff-9b21-06c28ba2eceb')
  self.assertEqual(self.d['v4_diagnosis']['observed']['positive_static'],3)
  self.assertEqual(self.d['v4_diagnosis']['observed']['positive_permuted'],15)
 def test_near_commutative_witness(self):
  c=self.d['v4_diagnosis']['F_structural_failure']['orthogonal_two_update_witness']['cosine_aligned_permuted']
  self.assertAlmostEqual(c,0.25+1/math.sqrt(2),places=15); self.assertGreater(c,0.95)
 def test_v5_bounded_not_gain_rescue(self):
  m=self.d['v5_enabling_method']; self.assertEqual(m['state_width'],256)
  self.assertIn('coefficient fixed exactly 1.0',m['G']); self.assertIn('bounded [-1,1]',m['G'])
 def test_strong_controls_and_old_gates(self):
  self.assertIn('STATIC_REPEAT',self.d['arms']); self.assertIn('TRANSITION_PERMUTED',self.d['arms'])
  g=self.d['development_gates']; self.assertEqual(g['n'],33); self.assertEqual(g['positive_static_min'],22); self.assertEqual(g['positive_permuted_min'],22)
  self.assertEqual(g['median_C_static_nats_min'],0.05); self.assertEqual(g['median_C_permuted_nats_min'],0.05); self.assertFalse(g['C_oneshot_used_as_gate'])
 def test_no_v4_outcome_tuning_and_seal(self):
  self.assertIn('forbidden',self.d['training_and_evaluation_partition']['v4_development_use'])
  self.assertIn('HARD_SEALED',self.d['scope']['v4_confirmation'])
  self.assertIn('NO_CONFIRMATION_ACCESS',self.d['non_authorizations'])
if __name__=='__main__': unittest.main()
