import copy
import unittest

import cpds_graphfork_constructibility_v1 as m


def family(tag="x"):
    return {
        "source_graph_id": "g-" + tag,
        "goal_canonical": "goal",
        "reset_observation_canonical": "reset",
        "allowed_pre_reset_history_canonical": ["look"],
        "immediate_next_command_canonical": "open",
        "common_prefix_transition_keys": [tag + "-t1", tag + "-t2", tag + "-t3"],
        "branch_A_equivalence_class": [tag + "-a"],
        "branch_B_equivalence_class": [tag + "-b"],
        "divergence_depth_after_immediate": 2,
        "local_source_competence_preoutcome": True,
    }


def geometry():
    return {
        "state_capacity_id": "UNFROZEN_STATE_CAPACITY",
        "representation_budget_id": "UNFROZEN_REPRESENTATION_BUDGET",
        "information_volume_id": "UNFROZEN_INFORMATION_VOLUME",
        "serialization_or_numeric_budget_id": "UNFROZEN_SERIALIZATION_OR_NUMERIC_BUDGET",
        "base_policy_id": "FROZEN_BASE_POLICY_PLACEHOLDER",
        "prompt_contract_id": "FROZEN_PROMPT_CONTRACT_PLACEHOLDER",
        "z0_identity_id": "PREOUTCOME_Z0_IDENTITY",
        "F_callable_id": "UNFROZEN_F_CALLABLE",
        "F_parameters_id": "UNFROZEN_F_PARAMETERS",
        "G_callable_id": "UNFROZEN_G_CALLABLE",
        "G_exposure_locations": ["RESET_PREFIX", "POST_TRANSITION_1", "POST_TRANSITION_2", "BRANCH_POINT"],
        "updater_invocation_sites": ["AFTER_OBS_1", "AFTER_OBS_2", "AFTER_OBS_3"],
        "runtime_call_geometry": ["G_EXPOSURE", "UPDATE_SLOT", "G_EXPOSURE", "UPDATE_SLOT", "G_EXPOSURE", "UPDATE_SLOT", "G_EXPOSURE"],
        "update_timing_budget": "MATCHED_PRE_BRANCH",
        "carrier_provenance_sources": ["MODEL_VISIBLE_PRE_RESET", "RUNTIME_CAUSALLY_OBSERVED"],
        "oneshot_G_exposure_location": "RESET_PREFIX",
        "G_can_execute_action": False,
        "G_can_force_single_action": False,
        "G_can_mutate_environment": False,
    }


def records(f):
    return [
        {"transition_key": k, "observed_index": i, "provenance": "RUNTIME_CAUSALLY_OBSERVED", "causally_observed": True}
        for i, k in enumerate(f["common_prefix_transition_keys"])
    ]


class TestCPDSGraphForkConstructibilityV2(unittest.TestCase):
    def authority(self, tag="x", namespace=m.DEVELOPMENT_NAMESPACE):
        f = family(tag)
        s = m.seal_source_snapshot("source-" + tag, [f])
        ss = s["snapshot_sha256"]
        man = m.build_generator_run_manifest(s, namespace, ss)
        ms = man["manifest_sha256"]
        return f, s, ss, man, ms

    def packet(self, tag="x"):
        f, s, ss, man, ms = self.authority(tag)
        p = m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], records(f), geometry())
        return f, s, ss, man, ms, p

    def test_reviewed_authority_and_self_test(self):
        self.assertTrue(m.verify_reviewed_authority())
        st = m.self_test()
        self.assertEqual(st["status"], "PASS_CONSTRUCTIBLE")
        self.assertEqual(st["scientific_result"], "NOT_ASSESSED")
        self.assertEqual(st["model_calls"], 0)
        self.assertEqual(st["environment_execution"], 0)

    def test_source_edit_self_rehash_fails_external_seal(self):
        _, s, ss, _, _ = self.authority("src")
        bad = copy.deepcopy(s)
        bad["families"][0]["goal_canonical"] = "forged"
        bad["snapshot_sha256"] = m.source_snapshot_identity(bad)
        with self.assertRaisesRegex(ValueError, "EXTERNAL_SOURCE_SEAL_MISMATCH"):
            m.validate_source_snapshot(bad, ss)

    def test_manifest_certificate_edit_self_rehash_fails_external_seal_and_rebuild(self):
        _, s, ss, man, ms = self.authority("man")
        bad = copy.deepcopy(man)
        bad["certificates"][0]["structural_family_key_sha256"] = "1" * 64
        bad["certificates"][0]["family_id"] = m._certificate_family_id("1" * 64, bad["cohort_namespace"], bad["source_snapshot_sha256"])
        bad["certificates"][0] = dict(bad["certificates"][0])
        bad["structural_family_key_sha256s"] = ["1" * 64]
        bad["family_ids"] = [bad["certificates"][0]["family_id"]]
        bad["certificate_sha256s"] = [m.certificate_identity(bad["certificates"][0])]
        bad["manifest_sha256"] = m.manifest_identity(bad)
        with self.assertRaisesRegex(ValueError, "EXTERNAL_MANIFEST_SEAL_MISMATCH"):
            m.validate_generator_run_manifest(bad, ms)
        with self.assertRaisesRegex(ValueError, "CERTIFICATE_REBUILD_MISMATCH"):
            m.validate_manifest_against_source(bad, bad["manifest_sha256"], s, ss)

    def test_packet_self_rehash_cannot_override_source_or_certificate_authority(self):
        f, s, ss, man, ms, p = self.packet("pkt")
        bad = copy.deepcopy(p)
        bad["certificate_sha256"] = "f" * 64
        bad["packet_sha256"] = m.packet_identity(bad)
        with self.assertRaisesRegex(ValueError, "PACKET_CERTIFICATE_BINDING"):
            m.validate_constructibility_packet(bad, s, ss, man, ms)
        forged_source = copy.deepcopy(s)
        forged_source["families"][0]["goal_canonical"] = "changed"
        forged_source["snapshot_sha256"] = m.source_snapshot_identity(forged_source)
        with self.assertRaisesRegex(ValueError, "EXTERNAL_SOURCE_SEAL_MISMATCH"):
            m.validate_constructibility_packet(p, forged_source, ss, man, ms)

    def test_observed_transition_records_are_source_bound_and_causal(self):
        f, s, ss, man, ms = self.authority("obs")
        good = records(f)
        p = m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], good, geometry())
        self.assertTrue(m.validate_constructibility_packet(p, s, ss, man, ms))
        invented = copy.deepcopy(good); invented[1]["transition_key"] = "invented"
        with self.assertRaisesRegex(ValueError, "OBSERVED_TRANSITION_SOURCE_BINDING"):
            m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], invented, geometry())
        future = copy.deepcopy(good); future[1]["causally_observed"] = False
        with self.assertRaisesRegex(ValueError, "FUTURE_OR_UNOBSERVED_TRANSITION"):
            m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], future, geometry())
        reordered = [good[1], good[0], good[2]]
        with self.assertRaisesRegex(ValueError, "OBSERVED_TRANSITION_SOURCE_BINDING|OBSERVED_TRANSITION_INDEX"):
            m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], reordered, geometry())

    def test_full_exact_six_arm_algebra(self):
        _, s, ss, man, ms, p = self.packet("six")
        self.assertEqual([a["arm_id"] for a in p["arms"]], list(m.EXACT_ARM_IDS))
        self.assertTrue(m.validate_constructibility_packet(p, s, ss, man, ms))
        missing = copy.deepcopy(p); missing["arms"].pop(); missing["packet_sha256"] = m.packet_identity(missing)
        with self.assertRaisesRegex(ValueError, "ARM_LIST_SCHEMA|ARM_SET"):
            m.validate_constructibility_packet(missing, s, ss, man, ms)
        extra = copy.deepcopy(p); extra["arms"].append(copy.deepcopy(extra["arms"][0])); extra["arms"][-1]["arm_id"] = "EXTRA"; extra["packet_sha256"] = m.packet_identity(extra)
        with self.assertRaisesRegex(ValueError, "ARM_LIST_SCHEMA|ARM_SET"):
            m.validate_constructibility_packet(extra, s, ss, man, ms)
        duplicate = copy.deepcopy(p); duplicate["arms"][1]["arm_id"] = "NO_CARRY"; duplicate["packet_sha256"] = m.packet_identity(duplicate)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ARM"):
            m.validate_constructibility_packet(duplicate, s, ss, man, ms)

    def test_static_repeat_cannot_mutate_into_aligned_update(self):
        _, s, ss, man, ms, p = self.packet("static")
        bad = copy.deepcopy(p)
        next(a for a in bad["arms"] if a["arm_id"] == "STATIC_REPEAT")["update_operation"] = "F_ALIGNED"
        bad["packet_sha256"] = m.packet_identity(bad)
        with self.assertRaisesRegex(ValueError, "STATIC_REPEAT_SEMANTICS|STATIC_REPEAT_BECAME_ALIGNED"):
            m.validate_constructibility_packet(bad, s, ss, man, ms)

    def test_matched_information_cannot_mutate_into_aligned_update(self):
        _, s, ss, man, ms, p = self.packet("mi")
        bad = copy.deepcopy(p)
        next(a for a in bad["arms"] if a["arm_id"] == "MATCHED_INFORMATION")["update_operation"] = "F_ALIGNED"
        bad["packet_sha256"] = m.packet_identity(bad)
        with self.assertRaisesRegex(ValueError, "MATCHED_INFORMATION_SEMANTICS|MATCHED_INFORMATION_BECAME_ALIGNED"):
            m.validate_constructibility_packet(bad, s, ss, man, ms)

    def test_permuted_only_order_differs_and_is_deterministic(self):
        _, s, ss, man, ms, p = self.packet("perm")
        amap = {a["arm_id"]: a for a in p["arms"]}
        obs = [r["transition_key"] for r in p["observed_transition_records"]]
        self.assertNotEqual(amap["TRANSITION_PERMUTED"]["transition_order"], obs)
        self.assertCountEqual(amap["TRANSITION_PERMUTED"]["transition_order"], obs)
        self.assertEqual(amap["TRANSITION_PERMUTED"]["update_operation"], amap["ALIGNED_RECURSION"]["update_operation"])
        bad = copy.deepcopy(p)
        next(a for a in bad["arms"] if a["arm_id"] == "TRANSITION_PERMUTED")["transition_order"] = obs
        bad["packet_sha256"] = m.packet_identity(bad)
        with self.assertRaisesRegex(ValueError, "PERMUTATION_IDENTITY"):
            m.validate_constructibility_packet(bad, s, ss, man, ms)
        bad2 = copy.deepcopy(p)
        next(a for a in bad2["arms"] if a["arm_id"] == "TRANSITION_PERMUTED")["G_exposure_locations"] = ["shift"]
        bad2["packet_sha256"] = m.packet_identity(bad2)
        with self.assertRaisesRegex(ValueError, "TRANSITION_PERMUTED_GEOMETRY_MISMATCH"):
            m.validate_constructibility_packet(bad2, s, ss, man, ms)

    def test_no_carry_and_static_oneshot_semantics_are_machine_bound(self):
        _, s, ss, man, ms, p = self.packet("nulls")
        amap = {a["arm_id"]: a for a in p["arms"]}
        self.assertEqual(amap["NO_CARRY"]["G_exposure_locations"], [])
        self.assertEqual(amap["STATIC_ONESHOT"]["G_exposure_locations"], ["RESET_PREFIX"])
        bad = copy.deepcopy(p)
        next(a for a in bad["arms"] if a["arm_id"] == "NO_CARRY")["state_capacity_id"] = "UNFROZEN_STATE_CAPACITY"
        bad["packet_sha256"] = m.packet_identity(bad)
        with self.assertRaisesRegex(ValueError, "NO_CARRY_STATE_PRESENT"):
            m.validate_constructibility_packet(bad, s, ss, man, ms)
        bad2 = copy.deepcopy(p)
        next(a for a in bad2["arms"] if a["arm_id"] == "STATIC_ONESHOT")["G_exposure_locations"] = ["BRANCH_POINT"]
        bad2["packet_sha256"] = m.packet_identity(bad2)
        with self.assertRaisesRegex(ValueError, "STATIC_ONESHOT_EXPOSURE"):
            m.validate_constructibility_packet(bad2, s, ss, man, ms)

    def test_G_nonexecuting_and_provenance_leak_fail_closed(self):
        f, s, ss, man, ms = self.authority("g")
        g = geometry(); g["G_can_force_single_action"] = True
        with self.assertRaisesRegex(ValueError, "G_NONEXECUTING_BOUNDARY"):
            m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], records(f), g)
        g2 = geometry(); g2["carrier_provenance_sources"].append("EVALUATOR_SECRET")
        with self.assertRaisesRegex(ValueError, "CARRIER_PROVENANCE_NOT_ALLOWED|CARRIER_PROVENANCE_LEAK"):
            m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], records(f), g2)

    def test_endpoint_first_action_exclusion_cannot_be_rehashed_away(self):
        _, s, ss, man, ms, p = self.packet("end")
        bad = copy.deepcopy(p); bad["first_action_in_primary_endpoint"] = True; bad["packet_sha256"] = m.packet_identity(bad)
        with self.assertRaisesRegex(ValueError, "ENDPOINT"):
            m.validate_constructibility_packet(bad, s, ss, man, ms)

    def test_confirmation_independence_and_resampled_dev_attack(self):
        f1, ds, dss, dm, dms = self.authority("d")
        f2 = family("c")
        cs = m.seal_source_snapshot("source-c", [f2]); css = cs["snapshot_sha256"]
        cm = m.build_generator_run_manifest(cs, "CPDS_CONFIRMATION_GRAPH_FAMILIES_V1", css); cms = cm["manifest_sha256"]
        self.assertTrue(m.validate_confirmation_disjointness(dm, cm, ds, cs, dss, css, dms, cms))
        same_source = copy.deepcopy(ds)
        sm = m.build_generator_run_manifest(same_source, "CPDS_CONFIRMATION_GRAPH_FAMILIES_V1", dss)
        with self.assertRaisesRegex(ValueError, "SOURCE_SNAPSHOT_NOT_INDEPENDENT|SOURCE_SNAPSHOT_ID_NOT_INDEPENDENT"):
            m.validate_confirmation_disjointness(dm, sm, ds, same_source, dss, dss, dms, sm["manifest_sha256"])
        overlap_source = m.seal_source_snapshot("conf-overlap", [f1]); overlap_ss = overlap_source["snapshot_sha256"]
        overlap_m = m.build_generator_run_manifest(overlap_source, "CPDS_CONFIRMATION_GRAPH_FAMILIES_V1", overlap_ss)
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_FAMILY_OVERLAP"):
            m.validate_confirmation_disjointness(dm, overlap_m, ds, overlap_source, dss, overlap_ss, dms, overlap_m["manifest_sha256"])

    def test_summary_revalidates_external_authority_and_never_becomes_science(self):
        _, s, ss, man, ms, p = self.packet("sum")
        auth = {"packet": p, "snapshot": s, "source_seal": ss, "manifest": man, "manifest_seal": ms}
        good = m.constructibility_summary([auth], 1)
        zero = m.constructibility_summary([], 0)
        inc = m.constructibility_summary([auth], 2, ["PREOUTCOME_REJECT"])
        self.assertEqual(good["label"], "PASS_CONSTRUCTIBLE")
        self.assertEqual(zero["label"], "CONSTRUCTIBILITY_INCONCLUSIVE")
        self.assertEqual(inc["label"], "CONSTRUCTIBILITY_INCONCLUSIVE")
        for x in (good, zero, inc):
            self.assertEqual(x["scientific_result"], "NOT_ASSESSED")
            self.assertFalse(x["mechanistic_support_or_refutation_available"])
        forged = copy.deepcopy(auth)
        forged["packet"] = copy.deepcopy(p)
        forged["packet"]["certificate_sha256"] = "0" * 64
        forged["packet"]["packet_sha256"] = m.packet_identity(forged["packet"])
        with self.assertRaisesRegex(ValueError, "PACKET_CERTIFICATE_BINDING"):
            m.constructibility_summary([forged], 1)

    def test_packet_and_manifest_are_deterministic(self):
        f, s, ss, man, ms = self.authority("det")
        p1 = m.build_constructibility_packet(s, ss, man, ms, man["family_ids"][0], records(f), geometry())
        p2 = m.build_constructibility_packet(copy.deepcopy(s), ss, copy.deepcopy(man), ms, man["family_ids"][0], records(f), geometry())
        self.assertEqual(m.canonical_bytes(p1), m.canonical_bytes(p2))
        self.assertEqual(p1["packet_sha256"], p2["packet_sha256"])

    def test_recursive_forbidden_generator_input_still_fails(self):
        f = family("forbidden"); f["nested"] = {"teacher_plan": "secret"}
        s = m.seal_source_snapshot("forbidden", [f]); ss = s["snapshot_sha256"]
        with self.assertRaises(ValueError):
            m.build_generator_run_manifest(s, m.DEVELOPMENT_NAMESPACE, ss)


if __name__ == "__main__":
    unittest.main()
