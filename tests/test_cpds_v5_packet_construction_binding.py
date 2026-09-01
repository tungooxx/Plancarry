from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

import cpds_actual_33x2_freeze_v1 as fr
import cpds_graphfork_contract_validator_v2 as gv2
from cpds_v5_partition_v1 import partition_name

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "design"
BEHAVIOR = D / "plancarry_cpds_v5_packet_behavior_manifest_a1_20260901.json"
CONTRACT = D / "plancarry_cpds_v5_packet_construction_binding_a1_20260901.json"
DIFF = D / "plancarry_cpds_v5_packet_construction_semantic_diff_a1_20260901.json"
CENSUS = D / "plancarry_cpds_actual_33x2_candidate_census_v1_20260829.json"
SOURCE = D / "plancarry_cpds_alfworld_static_source_authority_v1_20260829.json"
SOURCE_FILES = D / "plancarry_cpds_alfworld_train_file_manifest_v1_20260829.json"
UNITS = D / "plancarry_cpds_alfworld_static_graph_units_v1_20260829.json"
RESERVED = D / "plancarry_cpds_v5_v4_reserved_structural_key_hash_seal_a3_20260830.json"
RECIPE = D / "plancarry_cpds_v5_training_recipe_a1_20260830.json"
V4_RUNTIME = D / "plancarry_cpds_development_runtime_contract_v1_20260830.json"

BASE = "46c9d8214b4716097e603b9b6f53a4eb670abe5b"
DESIGN = "9b17ce8acd746494b7e0ca83f99af4dd1b1b67d3"
SPEC = "3a730d7fca46ae1c9736d3546588fb08143212f0ba52e580f70b7ba450a189b2"
RECIPE_SHA = "861537f18959bcff736e7cbe30fdf07e128c7621ed5fb4e3522d598f77acab8c"
SOURCE_SEAL = "a2ca2421f0c4405c403d09ca7f9e78066f57a1c2ee931600bbbc249ddff8810f"
BEHAVIOR_MANIFEST_SHA = "ad2f6972552ffae34847d4d551626d041cf65f24db4ebbcae3470a8f9eeb80bb"
BEHAVIOR_FILE_SHA = "d107d8d846fc82f002bd2f698f66029f4e1afcf9aae6a78e9755331040bf42cc"
CONTRACT_SHA = "0e388caa2e03bd4eb3186764851f1d04108df28cdf2acacb12a1af307764155b"
CONTRACT_FILE_SHA = "12260e9ebcdaa8b2b9af157695319cac41989d136e22f345c2cc6307b6d3e666"
DIFF_AUDIT_SHA = "56bad80007731fc66e24bbd58c2866df9f28a323004903f11975abf1278e9bba"
DIFF_FILE_SHA = "681ec36e57af4a99dcc63bd1fb0ace8c469aac9a2c4bbaddda13105dfe56df3a"
DONOR_DOMAIN = "CPDS_V5_CONTRASTIVE_DONOR_RING_V1"
PACKET_ID_DOMAIN = "CPDS_V5_PACKET_ID_V1"
TRACE_VERSION = "IMMEDIATE_EXCLUDED_COMMON1_COMMON2_EXAMINE_STAGING2_V1"


def canonical_bytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha_obj(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def self_hash(obj, field):
    x = copy.deepcopy(obj)
    expected = x.pop(field)
    return expected, sha_obj(x)


def packet_id(partition, source_graph_id, structural_key_sha256):
    return sha_obj({
        "domain": PACKET_ID_DOMAIN,
        "trace_version": TRACE_VERSION,
        "partition": partition,
        "source_graph_id": source_graph_id,
        "structural_key_sha256": structural_key_sha256,
    })


def donor_key(partition, source_graph_id, structural_key_sha256):
    return hashlib.sha256((DONOR_DOMAIN + "\0" + partition + "\0" + source_graph_id + "\0" + structural_key_sha256).encode("utf-8")).hexdigest()


class PacketBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.behavior = json.loads(BEHAVIOR.read_text())
        cls.contract = json.loads(CONTRACT.read_text())
        cls.diff = json.loads(DIFF.read_text())
        cls.census = json.loads(CENSUS.read_text())
        cls.reserved = json.loads(RESERVED.read_text())
        cls.rows = cls.behavior["rows"]

    def test_exact_authority_and_self_hashes(self):
        self.assertEqual(sha_file(BEHAVIOR), BEHAVIOR_FILE_SHA)
        self.assertEqual(sha_file(CONTRACT), CONTRACT_FILE_SHA)
        self.assertEqual(sha_file(DIFF), DIFF_FILE_SHA)
        self.assertEqual(self_hash(self.behavior, "manifest_sha256"), (BEHAVIOR_MANIFEST_SHA, BEHAVIOR_MANIFEST_SHA))
        self.assertEqual(self_hash(self.contract, "contract_sha256"), (CONTRACT_SHA, CONTRACT_SHA))
        self.assertEqual(self_hash(self.diff, "audit_sha256"), (DIFF_AUDIT_SHA, DIFF_AUDIT_SHA))
        self.assertEqual(sha_file(SOURCE), "c7f1bf6418c235d3805f653d3cef0907369ef82eff274c27a4ca787061eabce8")
        self.assertEqual(sha_file(CENSUS), "c40cda82d565e0bcd789cbf4204805a4efbcf462a7f83f46e648bc64e0790fb9")
        self.assertEqual(sha_file(UNITS), "c2ad460d533552fe26e810241a05b22b8fbe3cae749169d282c120f286d6b092")
        self.assertEqual(sha_file(RESERVED), "e2d6cecb4a13ff27cd5f2e76fd6d1e021fa27cf1e1d582aeb1808b2f40f075e2")
        self.assertEqual(sha_file(RECIPE), RECIPE_SHA)
        self.assertEqual(sha_file(V4_RUNTIME), "3dd4d52676b26e7c7e4fc4394cb0b16378b3560aa4711f574ce8ee1d2385ddaa")
        self.assertEqual(self.contract["authority"]["base_schema_repair_commit"], BASE)
        self.assertEqual(self.contract["authority"]["repaired_design_commit"], DESIGN)
        self.assertEqual(self.contract["authority"]["protected_scientific_spec_hash"], SPEC)
        self.assertEqual(self.contract["authority"]["source_authority_seal"], SOURCE_SEAL)

    def test_exact_population_reserve_and_partition(self):
        self.assertEqual(self.census["eligible_static_fork_count"], 1993)
        reserve = set(self.reserved["structural_family_key_sha256s"])
        self.assertEqual(len(reserve), 66)
        self.assertEqual(len(self.rows), 1927)
        self.assertEqual(len({r["source_graph_id"] for r in self.rows}), 1927)
        self.assertEqual(len({r["packet_id"] for r in self.rows}), 1927)
        census_by_graph = {r["source_graph_id"]: r for r in self.census["eligible_records"]}
        for r in self.rows:
            self.assertNotIn(r["structural_key_sha256"], reserve)
            self.assertEqual(census_by_graph[r["source_graph_id"]]["structural_family_key_sha256"], r["structural_key_sha256"])
            self.assertEqual(partition_name(r["source_graph_id"]), r["partition"])
            self.assertIn(r["partition"], ("TRAIN", "CALIBRATION"))
            self.assertEqual(r["packet_id"], packet_id(r["partition"], r["source_graph_id"], r["structural_key_sha256"]))
        counts = {p: sum(r["partition"] == p for r in self.rows) for p in ("TRAIN", "CALIBRATION")}
        self.assertEqual(counts, {"TRAIN": 1504, "CALIBRATION": 423})
        self.assertEqual(sha_obj(sorted(r["source_graph_id"] for r in self.rows if r["partition"] == "TRAIN")), "68080f7bbc7f67a4614dd003496aaab929f66093c8a9ddc41489efc1ca85163b")
        self.assertEqual(sha_obj(sorted(r["source_graph_id"] for r in self.rows if r["partition"] == "CALIBRATION")), "e9bbabd85d489e0dd81459e0cd2b59ae5547f8589a3625044ef236b20ab6a175")
        self.assertEqual(self.contract["source_population"]["DEVELOPMENT_count"], 0)
        self.assertEqual(self.contract["source_population"]["CONFIRMATION_count"], 0)

    def test_every_behavior_row_rederives_from_authenticated_static_pddl(self):
        manifest_map = fr._source_manifest_map()
        file_by_rel = {r["relative_path"]: r for r in json.loads(SOURCE_FILES.read_text())}
        for r in self.rows:
            candidate, reason = fr._derive_candidate(r["source_graph_id"], manifest_map)
            self.assertIsNone(reason, r["source_graph_id"])
            self.assertIsNotNone(candidate)
            self.assertEqual(gv2.structural_family_key(candidate["family"]), r["structural_key_sha256"])
            witness = candidate["witness"]
            self.assertEqual(witness["pre_reset_steps"], [])
            self.assertEqual(r["goal_canonical"], candidate["family"]["goal_canonical"])
            self.assertEqual(r["reset_state_id"], witness["reset_state_id"])
            self.assertEqual(r["immediate_symbolic_command"], witness["immediate_step"]["command"])
            self.assertEqual(r["update_symbolic_commands"], [x["command"] for x in witness["common_prefix_steps"]])
            self.assertEqual(r["update_transition_keys"], [x["transition_key"] for x in witness["common_prefix_steps"]])
            expected_continuation = fr._examine(candidate["staging_2_receptacle"])
            self.assertEqual(r["continuation_symbolic_command"], expected_continuation)
            self.assertEqual(r["primary_target_symbolic_commands"], [r["update_symbolic_commands"][1], expected_continuation])
            branch_members = set(candidate["family"]["branch_A_equivalence_class"]) | set(candidate["family"]["branch_B_equivalence_class"])
            self.assertNotIn(expected_continuation, branch_members)
            rel = r["source_graph_id"] + "/game.tw-pddl"
            self.assertEqual(r["game_tw_pddl_sha256"], file_by_rel[rel]["sha256"])

    def test_behavior_manifest_contains_no_evaluator_or_endpoint_fields(self):
        raw = json.dumps(self.behavior["rows"], sort_keys=True, ensure_ascii=False)
        for forbidden in ("branch_A", "branch_B", "evaluator_label", "outcome", "correctness", "endpoint"):
            self.assertNotIn(forbidden, raw)
        for r in self.rows:
            self.assertEqual(len(r["update_symbolic_commands"]), 2)
            self.assertEqual(len(r["negative_donor_source_graph_ids"]), 2)

    def test_structure_only_same_partition_donor_ring(self):
        by_graph = {r["source_graph_id"]: r for r in self.rows}
        for part in ("TRAIN", "CALIBRATION"):
            cohort = [r for r in self.rows if r["partition"] == part]
            order = sorted(cohort, key=lambda r: (donor_key(part, r["source_graph_id"], r["structural_key_sha256"]), r["source_graph_id"]))
            self.assertEqual(sha_obj([r["source_graph_id"] for r in order]), self.behavior["donor_ring_order_source_graph_ids_sha256"][part])
            n = len(order)
            for i, r in enumerate(order):
                expected = [order[(i + 1) % n]["source_graph_id"], order[(i + 2) % n]["source_graph_id"]]
                self.assertEqual(r["negative_donor_source_graph_ids"], expected)
                self.assertNotIn(r["source_graph_id"], expected)
                self.assertNotEqual(expected[0], expected[1])
                self.assertTrue(all(by_graph[g]["partition"] == part for g in expected))
        # Ring identity is invariant to artifact row ordering.
        reversed_rows = list(reversed(self.rows))
        for part in ("TRAIN", "CALIBRATION"):
            order = sorted([r for r in reversed_rows if r["partition"] == part], key=lambda r: (donor_key(part, r["source_graph_id"], r["structural_key_sha256"]), r["source_graph_id"]))
            self.assertEqual(sha_obj([r["source_graph_id"] for r in order]), self.behavior["donor_ring_order_source_graph_ids_sha256"][part])

    def test_packet_mapping_matches_existing_consumer_and_preserves_two_update_geometry(self):
        src = (ROOT / "cpds_v5_train_calibration_v1.py").read_text()
        for literal in (
            "PLANCARRY_CPDS_V5_PRECOMPUTED_FEATURE_SEQUENCE_V1",
            'packet["pre_reset_hidden"]', 'packet["updates"]', 'upd["transition_hidden"]', 'upd["prediction_site"]',
            'update["next_transition_hidden"]', 'update["negative_transition_hidden"]', 'packet.get("final_prediction_site")',
        ):
            self.assertIn(literal, src)
        packet = self.contract["packet_contract"]
        self.assertEqual(packet["updates_exactly"], 2)
        self.assertTrue(packet["final_prediction_site_equals_update_1_prediction_site"])
        self.assertEqual(self.contract["behavior_trace"]["update_count"], 2)
        self.assertIn("EXCLUDED", self.contract["behavior_trace"]["first_action_policy"])
        self.assertIn("NEVER folded", self.contract["behavior_trace"]["update_1"]["next_transition_positive"])
        self.assertEqual(self.contract["contrastive_negative"]["selection_inputs"], ["partition", "source_graph_id", "structural_key_sha256"])

    def test_no_scientific_authority_drift_and_execution_remains_sealed(self):
        self.assertTrue(self.diff["protected_scientific_spec_hash_unchanged"])
        self.assertFalse(self.diff["architecture_arms_gates_training_recipe_changed"])
        self.assertTrue(self.diff["newly_bound_science_critical_operationalization"])
        self.assertTrue(self.diff["requires_independent_semantic_binding_review"])
        na = self.contract["non_authorizations"]
        self.assertTrue(all(v is False for v in na.values()))
        self.assertEqual(self.contract["scope"]["v4_confirmation"], "HARD_SEALED_NEVER_REPURPOSED")
        self.assertFalse(self.contract["scope"]["v5_development_authorized"])
        self.assertFalse(self.contract["scope"]["v5_confirmation_authorized"])
        self.assertIn("fresh independent non-author", self.contract["review_requirement"])


if __name__ == "__main__":
    unittest.main()
