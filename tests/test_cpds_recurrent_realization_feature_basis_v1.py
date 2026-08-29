import copy, hashlib, json, math, unittest
from pathlib import Path
import cpds_recurrent_realization_contract_validator_v1 as m
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'results/design'
C=D/'plancarry_cpds_recurrent_realization_feature_basis_v1_20260829.json'
A=D/'plancarry_cpds_recurrent_realization_static_audit_v1_20260829.json'

def vec(pos, val=1.0):
    x=[0.0]*2048; x[pos]=val; return x
class TestCPDSRecurrentRealizationV1(unittest.TestCase):
    def test_01_contract_self_hash_and_scope(self):
        d=json.loads(C.read_text()); self.assertTrue(m.validate_contract(d)); self.assertTrue(d['science_execution_forbidden']); self.assertEqual(d['scientific_result'],'NOT_ASSESSED')
    def test_02_exact_authorities(self):
        d=m.load_contract()['authority']; self.assertEqual(d['constructibility_commit'],'c1c6517ff4678c2a9b151f67a1ff4dd6f5aae244'); self.assertEqual(d['statistical_commit'],'df17c5ee3a3d2c6bccd70367886216cd043d40f3')
    def test_03_native_width_is_not_arbitrary_gru16(self):
        d=m.load_contract(); self.assertEqual(d['frozen_model_basis']['hidden_size'],2048); self.assertEqual(d['recurrent_state']['state_dim'],2048); self.assertEqual(d['frozen_model_basis']['new_trainable_parameters'],0); self.assertIn('not a claim',d['frozen_model_basis']['minimality_rationale'])
    def test_04_parameter_free_F_is_bounded_and_order_sensitive(self):
        z0=vec(0); a=vec(1); b=vec(2)
        zab=m.fold(z0,[a,b]); zba=m.fold(z0,[b,a])
        self.assertAlmostEqual(sum(x*x for x in zab),1.0,places=12); self.assertNotEqual(zab,zba)
    def test_05_scramble_is_nonidentity_norm_preserving_and_invertible_shape(self):
        x=m.unit_l2([float((i%17)-8) for i in range(2048)]); y=m.P(x)
        self.assertNotEqual(x,y); self.assertAlmostEqual(sum(v*v for v in y),1.0,places=12); self.assertEqual(len(y),2048)
    def test_06_G_is_cosine_bounded_and_nonexecuting(self):
        self.assertAlmostEqual(m.G_delta(vec(0),vec(0)),1.0,places=12); self.assertAlmostEqual(m.G_delta(vec(0),vec(1)),0.0,places=12)
        g=m.load_contract()['adapter_G']; self.assertTrue(g['nonexecuting']); self.assertFalse(g['can_execute_action']); self.assertFalse(g['can_force_single_action']); self.assertFalse(g['can_mutate_environment'])
    def test_07_exact_six_arm_algebra_preserved(self):
        self.assertEqual(set(m.load_contract()['arm_realization']),{'NO_CARRY','STATIC_ONESHOT','STATIC_REPEAT','ALIGNED_RECURSION','TRANSITION_PERMUTED','MATCHED_INFORMATION'})
    def test_08_permuted_future_preview_forbidden(self):
        t=m.load_contract()['runtime_timing_and_isolation']; self.assertIn('already causally occurred',t['permuted_rule']); self.assertIn('no future preview',m.load_contract()['arm_realization']['TRANSITION_PERMUTED'])
    def test_09_matched_budgets_and_static_scratch_isolation(self):
        t=m.load_contract()['runtime_timing_and_isolation']; self.assertIn('2048xFLOAT32',t['matched_budget_rule']); self.assertIn('no directed path',m.load_contract()['arm_realization']['STATIC_REPEAT'])
    def test_10_no_fit_no_search(self):
        d=m.load_contract(); txt=json.dumps(d)
        self.assertEqual(d['recurrent_state']['F_fit_recipe'],'NONE'); self.assertEqual(d['adapter_G']['G_fit_recipe'],'NONE')
        self.assertIn('state-dimension search',txt); self.assertIn('gain/temperature search',txt)
    def test_11_statistics_unchanged(self):
        s=m.load_contract()['statistics_binding']; self.assertFalse(s['statistical_contract_changed']); self.assertEqual((s['n'],s['positive_each_min']),(33,22)); self.assertAlmostEqual(s['joint_power_lower_bound_reference'],0.8025570627867475,places=15)
    def test_12_fail_closed_vector_path(self):
        with self.assertRaises(ValueError): m.unit_l2([0.0]*2048)
        bad=[0.0]*2048; bad[5]=float('nan')
        with self.assertRaises(ValueError): m.unit_l2(bad)
    def test_13_tamper_contract_self_hash_fails(self):
        d=m.load_contract(); d['recurrent_state']['state_dim']=16
        with self.assertRaises(ValueError): m.validate_contract(d)
    def test_14_audit_no_prohibited_actions(self):
        a=json.loads(A.read_text()); self.assertTrue(all(v==0 for v in a['prohibited_actions_observed'].values())); self.assertTrue(all(a['checks'].values())); self.assertEqual(a['scientific_result'],'NOT_ASSESSED')

    def test_15_full_lineage_and_dead_assumptions_explicit(self):
        d=m.load_contract(); L=d["lineage_reconstruction"]; stages={x["stage"] for x in L["original_discovery_basis"]}
        self.assertTrue({"source-binding v2.6/v2.7 and Qwen3 recovery","direct-T1 natural checkpoint","LocalContinuation-v1","LocalContinuation-v2","ActionMatched","PlanUnique-v1.2","Grounded-v2","ReplayResidual V2.3"} <= stages)
        dead=" ".join(L["dead_assumptions_explicitly_not_inherited"])
        self.assertIn("whole-task success",dead); self.assertIn("one-shot single residual vector sufficiency",dead); self.assertIn("deterministic reordering",dead)
    def test_16_method_mechanism_distinguished(self):
        d=m.load_contract(); self.assertIn("enabling_method",d); self.assertIn("mechanistic_hypothesis",d)
        mm=d["lineage_reconstruction"]["method_mechanism_distinction"]; self.assertIn("low-assumption",mm["enabling_method_role"]); self.assertIn("temporally aligned",mm["mechanism_role"])
    def test_17_not_planunique_one_shot_retest(self):
        d=m.load_contract(); txt=d["scope_and_terminals"]["not_planunique_retest"]
        self.assertIn("not a retest",txt); self.assertIn("ordered multi-transition recurrence",txt); self.assertIn("changing only temporal order",txt)


    def test_18_verbatim_falsified_prerequisites_declared(self):
        L=m.load_contract()["lineage_reconstruction"]; f=L["falsified_prerequisites_verbatim"]
        self.assertEqual(len(f),15); self.assertTrue(any("valid_seen" in x for x in f)); self.assertTrue(any("Different deterministic ordering" in x for x in f)); self.assertTrue(any("single raw nuisance-orthogonal residual" in x for x in f))
        self.assertEqual(len(L["falsified_prerequisite_responses"]),len(f)); self.assertTrue(all(x["status"]=="NOT_INHERITED" for x in L["falsified_prerequisite_responses"]))
    def test_19_confirmation_independence_failures_not_inherited(self):
        L=m.load_contract()["lineage_reconstruction"]; stages={x["stage"] for x in L["original_discovery_basis"]}
        self.assertIn("untouched-confirmation pool failure",stages); self.assertIn("same-population deterministic-order independence failure",stages)
        dead=" ".join(L["dead_assumptions_explicitly_not_inherited"]); self.assertIn("valid_seen",dead); self.assertIn("same-population deterministic ordering",dead)


    def test_20_lineage_audit_limitation_is_fail_honest(self):
        d=m.load_contract(); x=d["lineage_audit_limitation"]
        self.assertFalse(x["latest_hypothesis_lineage_audit_passed"]); self.assertEqual(x["blocking_code"],"DISCOVERY_LINEAGE_INCOMPLETE")
        self.assertEqual(x["falsified_prerequisites_still_relevant"],[]); self.assertEqual(x["design_fields_missing"],[])
        self.assertFalse(x["discovery_context_observation"]["explicit_lineage_for_overlap_records"]); self.assertEqual(x["discovery_context_observation"]["parent_ids"],[])
        self.assertIn("does not claim",x["not_a_pass_claim"])

if __name__=='__main__': unittest.main()
