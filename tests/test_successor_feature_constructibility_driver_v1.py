from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import successor_feature_constructibility_driver_v1 as d
import successor_feature_label_binding_v2 as lb
import successor_feature_constructibility_v2 as sf

ROOT = Path(__file__).resolve().parents[1]


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prefix_ok():
    return {
        "eligible": True,
        "reasons": [],
        "primitive_bindings": {
            "action_primitive_sha256": d.ACTION_PRIMITIVE_SHA256,
            "runtime_primitive_sha256": d.RUNTIME_PRIMITIVE_SHA256,
        },
        "observable": {
            "task_instruction": "Put the red apple in/on the wooden box.",
            "history": [
                ["go to countertop 1", "You arrive at countertop 1. A red apple is here."],
                ["take apple 1 from countertop 1", "You pick up apple 1."],
            ],
            "current_observation": "You are at countertop 1 holding apple 1.",
            "admissible_commands": ["put apple 1 in/on box 1", "go to shelf 1", "go to cabinet 1"],
        },
        "shared_action_a3": "go to cabinet 1",
        "shared_action_phase": "CARRY_OR_SEEK_RECEPTACLE",
    }


def prefix_fail(reason="PREFIX_RUNTIME_ERROR"):
    return {
        "eligible": False,
        "reasons": [reason],
        "primitive_bindings": {
            "action_primitive_sha256": d.ACTION_PRIMITIVE_SHA256,
            "runtime_primitive_sha256": d.RUNTIME_PRIMITIVE_SHA256,
        },
        "observable": None,
        "shared_action_a3": None,
        "shared_action_phase": None,
    }


def scores_for(prefix, game_path, separated=True):
    obs = prefix["observable"]
    snapshot = lb.render_snapshot_utf8(obs["task_instruction"], obs["history"], obs["current_observation"], obs["admissible_commands"])
    a3 = prefix["shared_action_a3"]
    step2_scores = [2.0, 1.9, 0.0, -0.5, -1.0, -1.5]
    labels = sf.branch_labels_if_plausible(step2_scores)
    oriented = sf.orient_branches(game_path, *labels)
    branches = {}
    for n, branch in enumerate(oriented):
        if separated:
            row3 = [8.0 if i == n else 0.0 for i in range(6)]
            row4 = [8.0 if i == n else 0.0 for i in range(6)]
        else:
            row3 = [8.0 if i == 0 else 0.0 for i in range(6)]
            row4 = [8.0 if i == 0 else 0.0 for i in range(6)]
        row3_label = sf.PHASE_LABELS[max(range(6), key=lambda i: (row3[i], -i))]
        p3 = lb.render_label_prompt_utf8(snapshot, a3, [branch])
        p4 = lb.render_label_prompt_utf8(snapshot, a3, [branch, row3_label])
        branches[branch] = {
            "row3_prompt_sha256": h(p3), "row3_scores": row3,
            "row4_prompt_sha256": h(p4), "row4_scores": row4,
        }
    p2 = lb.render_label_prompt_utf8(snapshot, a3)
    return {"step2": {"prompt_sha256": h(p2), "scores": step2_scores}, "branches": branches}


def material(manifest, index=0, eligible=True, separated=True):
    row = manifest["paths"][index]
    p = prefix_ok() if eligible else prefix_fail()
    return {
        "index": index,
        "game_path": row["game_path"],
        "rank_sha256": row["rank_sha256"],
        "prefix": p,
        "score_bundle": scores_for(p, row["game_path"], separated) if eligible else None,
    }


class DriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = d.build_manifest(ROOT)

    def test_authority_and_manifest_are_deterministic(self):
        a = d.build_manifest(ROOT)
        b = d.build_manifest(ROOT)
        self.assertEqual(a, b)
        self.assertEqual(a["fixed_indices"], list(range(16)))
        self.assertEqual(len(a["paths"]), 16)
        self.assertNotIn("device_name", json.dumps(a))

    def test_authority_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in [d.PREREG_REL, d.POPULATION_REL, d.LABEL_BINDING_REL, d.ACTION_PRIMITIVE_REL, d.RUNTIME_PRIMITIVE_REL, d.SF_HELPER_REL, d.LABEL_HELPER_REL]:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, root / rel)
            with (root / d.PREREG_REL).open("ab") as f:
                f.write(b" ")
            with self.assertRaisesRegex(d.DriverContractError, "AUTHORITY_SHA256_MISMATCH"):
                d.verify_authority(root)

    def test_strict_index_rejects_bool_and_locked_splits(self):
        for bad in [True, False, -1, 16, 32, 36, 37, 1.0, "1"]:
            with self.assertRaises(sf.ContractError):
                d.strict_constructibility_index(bad)
        self.assertEqual(d.strict_constructibility_index(0), 0)
        self.assertEqual(d.strict_constructibility_index(15), 15)

    def test_prefix_failure_emits_packet_without_post_prefix_material(self):
        p = d.build_attempt_packet(material(self.manifest, 0, eligible=False), self.manifest)
        self.assertFalse(p["eligible"])
        self.assertEqual(p["eligibility_reasons"], ["PREFIX_RUNTIME_ERROR"])
        self.assertIsNone(p["constructibility"])
        d.validate_packet(p, self.manifest)

    def test_whole_task_or_future_prefix_reason_is_forbidden(self):
        m = material(self.manifest, 0, eligible=False)
        m["prefix"]["reasons"] = ["NOT_WON_WITHIN_ACTION_BUDGET"]
        with self.assertRaisesRegex(d.DriverContractError, "FORBIDDEN_OUTCOME_OR_FUTURE_CONCEPT"):
            d.build_attempt_packet(m, self.manifest)

    def test_eligible_packet_carriers_and_future_distance(self):
        p = d.build_attempt_packet(material(self.manifest, 0), self.manifest)
        self.assertTrue(p["eligible"])
        c = p["constructibility"]
        self.assertGreaterEqual(c["future_distance"], 0.5)
        for branch in c["branches"].values():
            self.assertEqual(len(branch["carrier"].encode("ascii")), 52)
            rows = sf.parse_carrier(branch["carrier"])
            self.assertEqual([sum(r) for r in rows], [255,255,255,255])
        self.assertEqual(p, d.build_attempt_packet(material(self.manifest, 0), self.manifest))

    def test_identical_future_rows_fail_even_with_distinct_row2(self):
        p = d.build_attempt_packet(material(self.manifest, 0, separated=False), self.manifest)
        self.assertFalse(p["eligible"])
        self.assertEqual(p["eligibility_reasons"], ["FUTURE_DISTANCE_BELOW_0_50"])
        self.assertEqual(p["constructibility"]["future_distance"], 0.0)

    def test_step2_prompt_hash_tamper_fails(self):
        m = material(self.manifest, 0)
        m["score_bundle"]["step2"]["prompt_sha256"] = "0"*64
        with self.assertRaisesRegex(d.DriverContractError, "STEP2_PROMPT_SHA256_MISMATCH"):
            d.build_attempt_packet(m, self.manifest)

    def test_runner_up_below_threshold_emits_ineligible_without_branch_calls(self):
        m = material(self.manifest, 0)
        p = m["prefix"]
        obs = p["observable"]
        snapshot = lb.render_snapshot_utf8(obs["task_instruction"], obs["history"], obs["current_observation"], obs["admissible_commands"])
        m["score_bundle"] = {"step2": {"prompt_sha256": h(lb.render_label_prompt_utf8(snapshot,p["shared_action_a3"])), "scores": [20,0,0,0,0,0]}, "branches": {}}
        packet = d.build_attempt_packet(m, self.manifest)
        self.assertFalse(packet["eligible"])
        self.assertIn("SECOND_BRANCH_PROBABILITY_BELOW_0_10", packet["eligibility_reasons"][0])

    def test_nonfinite_score_fails_closed(self):
        m = material(self.manifest, 0)
        m["score_bundle"]["step2"]["scores"][0] = float("nan")
        m["score_bundle"]["branches"] = {}
        packet = d.build_attempt_packet(m, self.manifest)
        self.assertFalse(packet["eligible"])
        self.assertIn("STEP2_SCORES_INVALID", packet["eligibility_reasons"][0])


    def test_row3_nonfinite_is_packetized_ineligible(self):
        m = material(self.manifest, 0)
        branch = next(iter(m["score_bundle"]["branches"]))
        m["score_bundle"]["branches"][branch]["row3_scores"][0] = float("inf")
        packet = d.build_attempt_packet(m, self.manifest)
        self.assertFalse(packet["eligible"])
        self.assertEqual(packet["eligibility_reasons"], ["ROW3_SCORES_INVALID"])
        self.assertIsNone(packet["constructibility"])

    def test_launcher_has_no_direct_science_execute_mode(self):
        proc=subprocess.run([str(ROOT/'launch_successor_feature_constructibility_v1.sh'),'execute'],cwd=ROOT,text=True,capture_output=True)
        self.assertNotEqual(proc.returncode,0)
        self.assertIn('invalid choice', proc.stderr)

    def test_unknown_future_field_rejected_by_exact_schema(self):
        m = material(self.manifest, 0)
        m["future_observation"] = "forbidden"
        with self.assertRaisesRegex(d.DriverContractError, "ATTEMPT_MATERIAL_SCHEMA_MISMATCH"):
            d.build_attempt_packet(m, self.manifest)
        m = material(self.manifest, 0)
        m["prefix"]["actual_A4"] = "forbidden"
        with self.assertRaisesRegex(d.DriverContractError, "PREFIX_SCHEMA_MISMATCH"):
            d.build_attempt_packet(m, self.manifest)

    def test_terminal_gate_12_of_16_and_11_of_16(self):
        twelve=[]; eleven=[]
        for i in range(16):
            twelve.append(d.build_attempt_packet(material(self.manifest,i,eligible=i<12),self.manifest))
            eleven.append(d.build_attempt_packet(material(self.manifest,i,eligible=i<11),self.manifest))
        s12=d.terminal_summary(twelve,self.manifest); s11=d.terminal_summary(eleven,self.manifest)
        self.assertEqual(s12["eligible_count"],12); self.assertEqual(s12["verdict"],d.PASS_LABEL)
        self.assertEqual(s11["eligible_count"],11); self.assertEqual(s11["verdict"],d.FAIL_LABEL)

    def test_packet_validation_is_key_order_independent_after_canonical_json(self):
        packet=d.build_attempt_packet(material(self.manifest,0,eligible=False),self.manifest)
        reloaded=json.loads(d.canonical_json_bytes(packet))
        self.assertEqual(d.validate_packet(reloaded,self.manifest)["packet_sha256"],packet["packet_sha256"])

    def test_terminal_refuses_incomplete_duplicate_and_tamper(self):
        packets=[d.build_attempt_packet(material(self.manifest,i,eligible=False),self.manifest) for i in range(16)]
        with self.assertRaisesRegex(d.DriverContractError,"EXACTLY_16"):
            d.terminal_summary(packets[:-1],self.manifest)
        dup=packets[:-1]+[packets[0]]
        with self.assertRaisesRegex(d.DriverContractError,"DUPLICATE_PACKET_INDEX"):
            d.terminal_summary(dup,self.manifest)
        bad=copy.deepcopy(packets); bad[0]["eligibility_reasons"]=["tampered"]
        with self.assertRaisesRegex(d.DriverContractError,"PACKET_SHA256_MISMATCH"):
            d.terminal_summary(bad,self.manifest)

    def test_launcher_preflight_only_reads_authority(self):
        out=subprocess.check_output([str(ROOT/'launch_successor_feature_constructibility_v1.sh'),'preflight'],cwd=ROOT,text=True)
        obj=json.loads(out)
        self.assertEqual(obj["manifest_sha256"],self.manifest["manifest_sha256"])
        self.assertEqual(obj["scientific_result"],"NOT_ASSESSED")


if __name__ == "__main__":
    unittest.main()
