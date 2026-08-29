import copy
import hashlib
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import cpds_executable_readiness_v1 as m
import cpds_graphfork_constructibility_v1 as gf


def family(tag):
    return {
        "source_graph_id": "graph-" + tag,
        "goal_canonical": "goal-" + tag,
        "reset_observation_canonical": "reset-" + tag,
        "allowed_pre_reset_history_canonical": ["look-" + tag],
        "immediate_next_command_canonical": "open-" + tag,
        "common_prefix_transition_keys": [tag + "-t1", tag + "-t2", tag + "-t3"],
        "branch_A_equivalence_class": [tag + "-A"],
        "branch_B_equivalence_class": [tag + "-B"],
        "divergence_depth_after_immediate": 2,
        "local_source_competence_preoutcome": True,
    }


def geometry():
    g=gf._geometry()
    g["state_capacity_id"]="CPDS_NATIVE2048_FLOAT32_8192B_V1"
    g["representation_budget_id"]="QWEN3_FINAL_NORMALIZED_HIDDEN_NATIVE2048_V1"
    g["information_volume_id"]="NATIVE2048_UNIT_VECTOR_PER_MATCHED_STATE_V1"
    g["serialization_or_numeric_budget_id"]="CANONICAL_JSON_TO_NATIVE2048_FLOAT32_V1"
    g["z0_identity_id"]="PRE_RESET_NATIVE2048_UNIT_Z0_V1"
    g["F_callable_id"]="CPDS_NATIVE2048_UNIT_SUM_RECURRENCE_V1"
    g["F_parameters_id"]="ZERO_TRAINABLE_PARAMETERS"
    g["G_callable_id"]="CPDS_PARAMETER_FREE_COSINE_WHOLE_ACTION_RERANK_V1"
    return g


def build_split(prefix, namespace):
    fs=[family(f"{prefix}{i:02d}") for i in range(33)]
    snap=gf.seal_source_snapshot(prefix+"-source",fs)
    ss=snap["snapshot_sha256"]
    man=gf.build_generator_run_manifest(snap,namespace,ss)
    return snap,ss,man,man["manifest_sha256"]


def word_factory(base=0):
    def f(fid):
        k=(int(fid[:8],16)+base)%720
        return iter([65535,k])
    return f


class TestCPDSExecutableReadinessV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev=build_split("dev",m.DEVELOPMENT_NAMESPACE)
        cls.conf=build_split("conf",m.CONFIRMATION_NAMESPACE)
        cls.code_sha=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()

    def test_01_contract_scope_and_self_hash(self):
        self.assertTrue(m.validate_contract())
        d=json.loads(m.CONTRACT_PATH.read_text())
        self.assertEqual(d["scientific_result"],"NOT_ASSESSED")
        self.assertTrue(d["science_execution_forbidden"])
        self.assertEqual(d["exact_arms"],list(m.EXACT_ARMS))

    def test_02_external_immutable_authority_and_working_bytes(self):
        snap=m.verify_external_authorities()
        self.assertTrue(m.validate_authority_snapshot(snap))
        self.assertEqual(snap["candidate"]["commit"],m.CANDIDATE_COMMIT)
        self.assertEqual(snap["v3_statistics"]["files"]["results/design/plancarry_cpds_randomized_arm_slot_inference_spec_v1_20260829.json"],"cdcad645a3c30cc92eebd573eeb9b4e6497ea2769db990566b3863850f3649c7")

    def test_03_authority_identity_or_byte_tamper_fails(self):
        s=m.collect_external_authority_snapshot()
        bad=copy.deepcopy(s); bad["candidate"]["tree"]="0"*40
        with self.assertRaises(ValueError): m.validate_authority_snapshot(bad)
        bad=copy.deepcopy(s); p=next(iter(bad["candidate"]["files"])); bad["candidate"]["files"][p]="0"*64
        with self.assertRaises(ValueError): m.validate_authority_snapshot(bad)
        bad=copy.deepcopy(s); p=next(iter(bad["working_files"])); bad["working_files"][p]="f"*64
        with self.assertRaises(ValueError): m.validate_authority_snapshot(bad)

    def test_04_factoradic_is_full_720_bijection(self):
        ps=[m.factoradic_unrank(i) for i in range(720)]
        self.assertEqual(len(set(ps)),720)
        self.assertEqual(set(ps),set(itertools.permutations(m.EXACT_ARMS)))
        with self.assertRaises(ValueError): m.factoradic_unrank(720)

    def test_05_rejection_mapping_is_unbiased_and_first_accept_wins(self):
        counts=[0]*720
        for w in range(m.REJECTION_CUTOFF): counts[w%720]+=1
        self.assertEqual(set(counts),{90})
        words,accepted,idx=m.draw_uniform_assignment_index(iter([65535,64800,719,3]))
        self.assertEqual(words,[65535,64800,719]); self.assertEqual((accepted,idx),(719,719))
        with self.assertRaises(ValueError): m.draw_uniform_assignment_index(iter([65535,64800]))

    def test_06_assignment_record_tamper_and_redraw_fail_closed(self):
        cert=self.dev[2]["certificates"][0]
        r=m.build_assignment_record(m.DEVELOPMENT_NAMESPACE,cert,iter([65535,17]),self.code_sha)
        self.assertTrue(m.validate_assignment_record(r,cert,m.DEVELOPMENT_NAMESPACE,self.code_sha))
        for mut in ("assignment_index","arm_permutation","accepted_word_u16","generator_code_sha256"):
            b=copy.deepcopy(r)
            if mut=="assignment_index": b[mut]=18
            elif mut=="arm_permutation": b[mut]=list(reversed(b[mut]))
            elif mut=="accepted_word_u16": b[mut]=18
            else: b[mut]="0"*64
            with self.assertRaises(ValueError,msg=mut): m.validate_assignment_record(b,cert,m.DEVELOPMENT_NAMESPACE,self.code_sha)
        b=copy.deepcopy(r); b["draw_words_u16_in_order"]=[17,18]
        with self.assertRaises(ValueError): m.validate_assignment_record(b,cert,m.DEVELOPMENT_NAMESPACE,self.code_sha)

    def test_07_assignment_manifest_exact_33_and_tamper_rejection(self):
        snap,ss,man,ms=self.dev
        a=m.build_assignment_manifest(man,ms,word_factory(),self.code_sha)
        self.assertEqual(len(a["records"]),33)
        self.assertTrue(m.validate_assignment_manifest(a,man,ms,self.code_sha))
        b=copy.deepcopy(a); b["records"]=b["records"][:-1]; b["assignment_manifest_sha256"]=m.assignment_manifest_identity(b)
        with self.assertRaises(ValueError): m.validate_assignment_manifest(b,man,ms,self.code_sha)
        b=copy.deepcopy(a); b["records"][0]["family_id"]=b["records"][1]["family_id"]; b["assignment_manifest_sha256"]=m.assignment_manifest_identity(b)
        with self.assertRaises(ValueError): m.validate_assignment_manifest(b,man,ms,self.code_sha)

    def test_08_two_split_bundle_atomic_disjoint_and_no_redraw(self):
        ds,dss,dm,dms=self.dev; cs,css,cm,cms=self.conf
        b=m.freeze_two_split_bundle(ds,dss,dm,dms,cs,css,cm,cms,word_factory(0),word_factory(1),development_arm_outcomes_opened=False,generator_code_sha256=self.code_sha)
        self.assertTrue(m.validate_two_split_bundle(b,ds,dm,dms,cs,cm,cms,self.code_sha))
        self.assertTrue(b["confirmation_outcomes_untouched"])
        with self.assertRaises(ValueError):
            m.freeze_two_split_bundle(ds,dss,dm,dms,cs,css,cm,cms,word_factory(),word_factory(),development_arm_outcomes_opened=False,existing_bundle=b,generator_code_sha256=self.code_sha)
        with self.assertRaises(ValueError):
            m.freeze_two_split_bundle(ds,dss,dm,dms,cs,css,cm,cms,word_factory(),word_factory(),development_arm_outcomes_opened=True,generator_code_sha256=self.code_sha)

    def test_09_bundle_write_is_create_once(self):
        ds,dss,dm,dms=self.dev; cs,css,cm,cms=self.conf
        b=m.freeze_two_split_bundle(ds,dss,dm,dms,cs,css,cm,cms,word_factory(),word_factory(),development_arm_outcomes_opened=False,generator_code_sha256=self.code_sha)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"freeze.json"
            h=m.write_bundle_once(p,b); self.assertEqual(h,hashlib.sha256(p.read_bytes()).hexdigest())
            with self.assertRaises(ValueError): m.write_bundle_once(p,b)

    def test_10_cross_split_overlap_or_namespace_reuse_fails(self):
        ds,dss,dm,dms=self.dev
        # Same source cannot masquerade as independent confirmation.
        cm=gf.build_generator_run_manifest(ds,m.CONFIRMATION_NAMESPACE,dss); cms=cm["manifest_sha256"]
        with self.assertRaises(ValueError):
            m.freeze_two_split_bundle(ds,dss,dm,dms,ds,dss,cm,cms,word_factory(),word_factory(),development_arm_outcomes_opened=False,generator_code_sha256=self.code_sha)

    def _packet_authority(self):
        snap,ss,man,ms=self.dev
        cert=man["certificates"][0]
        fam=next(f for f in snap["families"] if gf.structural_family_key(f)==cert["structural_family_key_sha256"])
        packet=gf.build_constructibility_packet(snap,ss,man,ms,cert["family_id"],gf._records(fam),geometry())
        return {"packet":packet,"snapshot":snap,"source_seal":ss,"manifest":man,"manifest_seal":ms},cert

    def test_11_runtime_plan_preserves_six_arms_and_slot_isolation(self):
        auth,cert=self._packet_authority()
        rec=m.build_assignment_record(m.DEVELOPMENT_NAMESPACE,cert,iter([5]),self.code_sha)
        plan=m.build_family_runtime_plan(auth,rec,["open fridge","close fridge","look"],self.code_sha)
        self.assertTrue(m.validate_family_runtime_plan(plan,auth,rec,["open fridge","close fridge","look"],self.code_sha))
        self.assertEqual({s["arm_id"] for s in plan["slots"]},set(m.EXACT_ARMS))
        self.assertEqual(len({s["isolated_mutable_state_scope_id"] for s in plan["slots"]}),6)
        self.assertTrue(all(s["cross_slot_mutable_inputs"]==[] for s in plan["slots"]))

    def test_12_static_repeat_scratch_cannot_reach_G_or_endpoint(self):
        auth,cert=self._packet_authority(); rec=m.build_assignment_record(m.DEVELOPMENT_NAMESPACE,cert,iter([0]),self.code_sha)
        plan=m.build_family_runtime_plan(auth,rec,["a","b"],self.code_sha)
        slot=next(s for s in plan["slots"] if s["arm_id"]=="STATIC_REPEAT")
        self.assertTrue(slot["scratch_only"]); self.assertFalse(slot["scratch_state_reaches_G"]); self.assertFalse(slot["scratch_state_reaches_endpoint"])
        bad=copy.deepcopy(plan); target=next(s for s in bad["slots"] if s["arm_id"]=="STATIC_REPEAT"); target["scratch_state_reaches_G"]=True
        with self.assertRaises(ValueError): m.validate_family_runtime_plan(bad,auth,rec,["a","b"],self.code_sha)

    def test_13_permuted_arm_is_same_observed_multiset_wrong_order_no_future(self):
        auth,cert=self._packet_authority(); rec=m.build_assignment_record(m.DEVELOPMENT_NAMESPACE,cert,iter([0]),self.code_sha)
        plan=m.build_family_runtime_plan(auth,rec,["a","b"],self.code_sha)
        slot=next(s for s in plan["slots"] if s["arm_id"]=="TRANSITION_PERMUTED")
        observed=[r["transition_key"] for r in auth["packet"]["observed_transition_records"]]
        self.assertEqual(sorted(slot["transition_order"]),sorted(observed)); self.assertNotEqual(slot["transition_order"],observed); self.assertFalse(slot["future_transition_preview_allowed"])
        bad=copy.deepcopy(auth); bad["packet"]["observed_transition_records"][0]["causally_observed"]=False; bad["packet"]["packet_sha256"]=gf.packet_identity(bad["packet"])
        with self.assertRaises(ValueError): m.build_family_runtime_plan(bad,rec,["a","b"],self.code_sha)

    def test_14_G_candidate_set_must_be_exact_and_scores_finite(self):
        base=["a","b","c"]
        rows=[{"action":a,"adjusted_whole_action_logscore":float(i)} for i,a in enumerate(base)]
        self.assertTrue(m.validate_g_score_output(base,rows))
        bad=copy.deepcopy(rows); bad.pop()
        with self.assertRaises(ValueError): m.validate_g_score_output(base,bad)
        bad=copy.deepcopy(rows); bad[1]["action"]="x"
        with self.assertRaises(ValueError): m.validate_g_score_output(base,bad)
        bad=copy.deepcopy(rows); bad[1]["adjusted_whole_action_logscore"]=float("nan")
        with self.assertRaises(ValueError): m.validate_g_score_output(base,bad)

    def test_15_runtime_plan_tamper_arm_or_cross_slot_fails(self):
        auth,cert=self._packet_authority(); rec=m.build_assignment_record(m.DEVELOPMENT_NAMESPACE,cert,iter([0]),self.code_sha)
        plan=m.build_family_runtime_plan(auth,rec,["a","b"],self.code_sha)
        bad=copy.deepcopy(plan); bad["slots"][0]["arm_id"]="ALIGNED_RECURSION"
        with self.assertRaises(ValueError): m.validate_family_runtime_plan(bad,auth,rec,["a","b"],self.code_sha)
        bad=copy.deepcopy(plan); bad["slots"][1]["isolated_mutable_state_scope_id"]=bad["slots"][0]["isolated_mutable_state_scope_id"]
        with self.assertRaises(ValueError): m.validate_family_runtime_plan(bad,auth,rec,["a","b"],self.code_sha)

    def test_16_static_audit_zero_prohibited_actions(self):
        a=json.loads(m.AUDIT_PATH.read_text())
        self.assertEqual(a["scientific_result"],"NOT_ASSESSED")
        self.assertTrue(all(a["checks"].values()))
        self.assertTrue(all(v==0 for v in a["prohibited_actions_observed"].values()))

    def test_17_static_preflight_is_not_science(self):
        p=m.static_preflight()
        self.assertEqual(p["status"],"PASS_PRE_SCIENCE_STATIC_READINESS")
        self.assertEqual(p["scientific_result"],"NOT_ASSESSED")
        for k in ["model_calls","environment_execution","gpu_provider_lifecycle","experiment_or_decision_actions","arm_outcomes_opened","future_split_access"]:
            self.assertEqual(p[k],0)

    def test_18_zero_tolerance_guard_counters_fail_closed(self):
        good={k:0 for k in m.ZERO_TOLERANCE_GUARDS}
        self.assertTrue(m.validate_zero_tolerance_guard_counters(good))
        for key in m.ZERO_TOLERANCE_GUARDS:
            bad=copy.deepcopy(good); bad[key]=1
            with self.assertRaises(ValueError,msg=key): m.validate_zero_tolerance_guard_counters(bad)
        bad=copy.deepcopy(good); bad[m.ZERO_TOLERANCE_GUARDS[0]]=False
        with self.assertRaises(ValueError): m.validate_zero_tolerance_guard_counters(bad)

if __name__ == "__main__": unittest.main()
