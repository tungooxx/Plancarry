import hashlib, json, pathlib, unittest
ROOT=pathlib.Path(__file__).parents[1]
P=ROOT/"results/design/plancarry_cpds_v5_post_adversarial_design_repair_a1_20260831.json"
D=ROOT/"results/design/plancarry_cpds_v5_post_adversarial_semantic_diff_a1_20260831.json"
class T(unittest.TestCase):
 def setUp(self): self.d=json.loads(P.read_text()); self.x=json.loads(D.read_text())
 def test_attack_nulls_all_bound(self):
  self.assertEqual(set(self.d["null_models_addressed"]),{"670cd5dc-c8c9-464c-a862-5922768ab282","f40e6226-0a54-4b6f-a3ad-59b1fc7b4e7f","b85d42bb-c4c3-4534-82bc-a35dfc48c09d"})
  for a in ["ZERO_Z0_RECURSION","DONOR_Z0_RECURSION","LAST_TRANSITION_ONLY","BAGGED_TRANSITIONS","STATIC_PREDICTIVE_SHARED_G"]: self.assertIn(a,self.d["arms"])
 def test_static_capacity_and_shared_g(self):
  s=self.d["protected_scientific_semantics"]["static_baseline"]
  self.assertEqual(s["recurrent_state_encoder_params"],1443328); self.assertEqual(s["state_encoder_params"],1443072)
  self.assertLess(s["relative_difference_fraction"],0.00018); self.assertTrue(s["shares_exact_Wa_G"]); self.assertFalse(s["post_reset_transition_access"])
 def test_recipe_frozen_exactly(self):
  r=self.d["training_contract"]["exact_recurrent_recipe"]
  self.assertEqual((r["seed"],r["optimizer"],r["learning_rate"],r["epochs"],r["batch_sequences"]),(20260830,"AdamW",0.0003,32,8))
  self.assertEqual(r["betas"],[0.9,0.999]); self.assertEqual(r["eps"],1e-8); self.assertEqual(r["weight_decay"],0.0001)
  self.assertEqual(r["gradient_clip_norm"],1.0); self.assertEqual(r["secondary_contrastive_weight"],0.25)
  self.assertEqual(r["early_stopping"],"NONE"); self.assertEqual(r["checkpoint_selection"],"FINAL_EPOCH_ONLY"); self.assertFalse(r["calibration_model_selection"])
  self.assertEqual(r["recurrent_static_joint_weight"],{"RECURRENT":0.5,"STATIC_PREDICTIVE_SHARED_G":0.5})
 def test_z0_and_local_order_are_hard_gates(self):
  g=self.d["development_gates"]
  self.assertEqual(g["logic"],"ALL_CONJUNCTIVE_IUT_NO_RESCUE")
  for k in ["C_zero_z0","C_donor_z0","C_last_transition","C_bagged","C_static_predictive"]: self.assertEqual(g["positive_count_min_each"][k],22)
  for k in ["C_last_transition","C_bagged","C_static_predictive"]: self.assertEqual(g["median_effect_nats_min"][k],0.05)
  self.assertIn("C_zero_z0",g["median_strict_gt_zero"]); self.assertIn("C_donor_z0",g["median_strict_gt_zero"])
 def test_calibration_cannot_select_model_or_see_endpoints(self):
  c=self.d["predevelopment_constructibility_gate"]
  self.assertFalse(c["model_selection"]); self.assertIn("no V4/V5 branch endpoints",c["data"])
  req=" ".join(c["requirements"])
  for x in ["ZERO_Z0_RECURSION","DONOR_Z0_RECURSION","LAST_TRANSITION_ONLY","BAGGED_TRANSITIONS","STATIC_PREDICTIVE_SHARED_G"]: self.assertIn(x,req)
 def test_confirmation_and_planroute_hard_walls(self):
  self.assertEqual(self.d["scope"]["v4_confirmation"],"HARD_SEALED_NEVER_REPURPOSED")
  self.assertEqual(self.d["scope"]["planroute"],"USER_NOOP_RETIRED")
  n=set(self.d["non_authorizations"]); self.assertIn("NO_TRAIN_EXECUTION",n); self.assertIn("NO_CALIBRATION_EXECUTION",n); self.assertIn("NO_V5_DEVELOPMENT_EXECUTION",n); self.assertIn("NO_CONFIRMATION_ACCESS",n)
 def test_claim_ceiling_not_gru_specific(self):
  c=self.d["scope"]["claim"]
  self.assertIn("does not uniquely identify GRU-256",c); self.assertIn("bundled",c)
 def test_semantic_diff_flags_material_drift_no_code(self):
  self.assertTrue(self.d["scientific_variable_drift_from_5f08cf2"]); self.assertTrue(self.x["scientific_variable_drift"])
  self.assertFalse(self.x["implementation_files_modified"]); self.assertFalse(self.x["model_or_environment_execution"])
 def test_design_hashes_self_consistent(self):
  self.assertEqual(self.x["target_design_sha256"],hashlib.sha256(P.read_bytes()).hexdigest())
  p=self.d["protected_scientific_semantics"]
  h=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
  self.assertEqual(self.d["scientific_spec_hash"],h); self.assertEqual(self.x["target_scientific_spec_hash"],h)
if __name__=="__main__": unittest.main()
