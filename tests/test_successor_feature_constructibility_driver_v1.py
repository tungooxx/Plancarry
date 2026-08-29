from __future__ import annotations

import copy
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import successor_feature_constructibility_driver_v1 as d
import successor_feature_constructibility_validator_v1 as validator
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


def scores_for(prefix, game_path, separated=True, step2_scores=None):
    obs = prefix["observable"]
    snapshot = lb.render_snapshot_utf8(obs["task_instruction"], obs["history"], obs["current_observation"], obs["admissible_commands"])
    a3 = prefix["shared_action_a3"]
    if step2_scores is None:
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
    return {"step2": {"prompt_sha256": h(p2), "scores": list(step2_scores)}, "branches": branches}


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


def cohort(manifest, eligible_count=0, separated=True):
    return [material(manifest, i, eligible=i < eligible_count, separated=separated) for i in range(16)]


def seal(manifest, materials):
    mm = d.build_attempt_material_manifest(materials, manifest)
    return mm, mm["material_manifest_sha256"]


def packets_for(manifest, materials, mm, mmsha):
    return [d.build_attempt_packet(m, manifest, mm, mmsha) for m in materials]


def write_json(path: Path, value, *, canonical=True):
    if canonical:
        path.write_bytes(d.canonical_json_bytes(value) + b"\n")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


class DriverRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = d.build_manifest(ROOT)

    def test_bound_module_is_candidate_worktree(self):
        self.assertEqual(Path(d.__file__).resolve(), (ROOT / "successor_feature_constructibility_driver_v1.py").resolve())

    def test_authority_and_manifest_are_deterministic(self):
        a = d.build_manifest(ROOT); b = d.build_manifest(ROOT)
        self.assertEqual(a, b); self.assertEqual(a["fixed_indices"], list(range(16)))
        self.assertEqual(len(a["paths"]), 16); self.assertNotIn("device_name", json.dumps(a))

    def test_authority_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in [d.PREREG_REL, d.POPULATION_REL, d.LABEL_BINDING_REL, d.ACTION_PRIMITIVE_REL, d.RUNTIME_PRIMITIVE_REL, d.SF_HELPER_REL, d.LABEL_HELPER_REL]:
                (root / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT / rel, root / rel)
            with (root / d.PREREG_REL).open("ab") as f: f.write(b" ")
            with self.assertRaisesRegex(d.DriverContractError, "AUTHORITY_SHA256_MISMATCH"):
                d.verify_authority(root)

    def test_strict_index_rejects_bool_and_locked_splits(self):
        for bad in [True, False, -1, 16, 32, 36, 37, 1.0, "1"]:
            with self.assertRaises(sf.ContractError): d.strict_constructibility_index(bad)
        self.assertEqual(d.strict_constructibility_index(0), 0); self.assertEqual(d.strict_constructibility_index(15), 15)

    def test_json_object_key_order_is_nonsemantic_for_material(self):
        mats = cohort(self.manifest, 0)
        sorted_mats = [json.loads(d.canonical_json_bytes(x)) for x in mats]
        mm1, sha1 = seal(self.manifest, mats); mm2, sha2 = seal(self.manifest, sorted_mats)
        self.assertEqual(sha1, sha2); self.assertEqual(mm1, mm2)
        p1 = packets_for(self.manifest, mats, mm1, sha1)[0]
        p2 = packets_for(self.manifest, sorted_mats, mm2, sha2)[0]
        self.assertEqual(p1, p2)

    def test_material_manifest_requires_exact16_unique_fixed_indices(self):
        mats = cohort(self.manifest, 0)
        with self.assertRaisesRegex(d.DriverContractError, "EXACTLY_16"):
            d.build_attempt_material_manifest(mats[:-1], self.manifest)
        dup = mats[:-1] + [copy.deepcopy(mats[0])]
        with self.assertRaisesRegex(d.DriverContractError, "DUPLICATE_ATTEMPT_MATERIAL_INDEX"):
            d.build_attempt_material_manifest(dup, self.manifest)

    def test_external_material_manifest_seal_is_required(self):
        mats = cohort(self.manifest, 0); mm, sha = seal(self.manifest, mats)
        with self.assertRaisesRegex(d.DriverContractError, "EXTERNAL_SEAL_MISMATCH"):
            d.validate_attempt_material_manifest(mm, self.manifest, "0" * 64)
        self.assertEqual(d.validate_attempt_material_manifest(mm, self.manifest, sha)["material_manifest_sha256"], sha)

    def test_prefix_failure_emits_packet_bound_to_material(self):
        mats = cohort(self.manifest, 0); mm, sha = seal(self.manifest, mats)
        p = d.build_attempt_packet(mats[0], self.manifest, mm, sha)
        self.assertFalse(p["eligible"]); self.assertEqual(p["eligibility_reasons"], ["PREFIX_RUNTIME_ERROR"])
        self.assertEqual(p["attempt_material_sha256"], d.attempt_material_sha256(mats[0])); self.assertIsNone(p["constructibility"])
        self.assertEqual(d.validate_packet(p, mats[0], self.manifest, mm, sha), p)

    def test_whole_task_or_future_prefix_reason_is_forbidden(self):
        mats = cohort(self.manifest, 0); mats[0]["prefix"]["reasons"] = ["NOT_WON_WITHIN_ACTION_BUDGET"]
        mm, sha = seal(self.manifest, mats)
        with self.assertRaisesRegex(d.DriverContractError, "FORBIDDEN_OUTCOME_OR_FUTURE_CONCEPT"):
            d.build_attempt_packet(mats[0], self.manifest, mm, sha)

    def test_eligible_packet_carriers_and_future_distance(self):
        mats = cohort(self.manifest, 1); mm, sha = seal(self.manifest, mats)
        p = d.build_attempt_packet(mats[0], self.manifest, mm, sha)
        self.assertTrue(p["eligible"]); c = p["constructibility"]; self.assertGreaterEqual(c["future_distance"], 0.5)
        for branch in c["branches"].values():
            self.assertEqual(len(branch["carrier"].encode("ascii")), 52)
            rows = sf.parse_carrier(branch["carrier"]); self.assertEqual([sum(r) for r in rows], [255,255,255,255])

    def test_identical_future_rows_fail_even_with_distinct_row2(self):
        mats = cohort(self.manifest, 1, separated=False); mm, sha = seal(self.manifest, mats)
        p = d.build_attempt_packet(mats[0], self.manifest, mm, sha)
        self.assertFalse(p["eligible"]); self.assertEqual(p["eligibility_reasons"], ["FUTURE_DISTANCE_BELOW_0_50"])
        self.assertEqual(p["constructibility"]["future_distance"], 0.0)

    def test_step2_prompt_hash_tamper_fails(self):
        mats = cohort(self.manifest, 1); mats[0]["score_bundle"]["step2"]["prompt_sha256"] = "0" * 64
        mm, sha = seal(self.manifest, mats)
        with self.assertRaisesRegex(d.DriverContractError, "STEP2_PROMPT_SHA256_MISMATCH"):
            d.build_attempt_packet(mats[0], self.manifest, mm, sha)

    def test_runner_up_threshold_below_at_above(self):
        below = [math.log(.505)] + [math.log(.099)] * 5
        at = [math.log(.5)] + [math.log(.1)] * 5
        above = [math.log(.495)] + [math.log(.101)] * 5
        with self.assertRaisesRegex(sf.ContractError, "BELOW_0_10"): sf.branch_labels_if_plausible(below)
        self.assertEqual(len(sf.branch_labels_if_plausible(at)), 2)
        self.assertEqual(len(sf.branch_labels_if_plausible(above)), 2)

    def test_nonfinite_step2_and_rows_packetize_ineligible(self):
        for field in ["step2", "row3", "row4"]:
            mats = cohort(self.manifest, 1)
            if field == "step2":
                mats[0]["score_bundle"]["step2"]["scores"][0] = float("nan"); mats[0]["score_bundle"]["branches"] = {}
            else:
                branch = next(iter(mats[0]["score_bundle"]["branches"]))
                mats[0]["score_bundle"]["branches"][branch][f"{field}_scores"][0] = float("inf")
            mm, sha = seal(self.manifest, mats)
            p = d.build_attempt_packet(mats[0], self.manifest, mm, sha)
            self.assertFalse(p["eligible"]); self.assertIsNone(p["constructibility"])

    def test_unknown_future_field_rejected_by_exact_schema(self):
        mats = cohort(self.manifest, 1); mats[0]["future_observation"] = "forbidden"
        with self.assertRaisesRegex(d.DriverContractError, "ATTEMPT_MATERIAL_SCHEMA_MISMATCH"):
            seal(self.manifest, mats)
        mats = cohort(self.manifest, 1); mats[0]["prefix"]["actual_A4"] = "forbidden"; mm, sha = seal(self.manifest, mats)
        with self.assertRaisesRegex(d.DriverContractError, "PREFIX_SCHEMA_MISMATCH"):
            d.build_attempt_packet(mats[0], self.manifest, mm, sha)

    def test_terminal_gate_12_of_16_and_11_of_16_from_sealed_material(self):
        for n, verdict in [(12, d.PASS_LABEL), (11, d.FAIL_LABEL)]:
            mats = cohort(self.manifest, n); mm, sha = seal(self.manifest, mats); packets = packets_for(self.manifest, mats, mm, sha)
            s = d.terminal_summary(packets, mats, mm, sha, self.manifest)
            self.assertEqual(s["eligible_count"], n); self.assertEqual(s["verdict"], verdict)

    def test_packet_json_key_order_is_nonsemantic(self):
        mats = cohort(self.manifest, 0); mm, sha = seal(self.manifest, mats)
        p = d.build_attempt_packet(mats[0], self.manifest, mm, sha); reloaded = json.loads(d.canonical_json_bytes(p))
        self.assertEqual(d.validate_packet(reloaded, mats[0], self.manifest, mm, sha), p)

    def test_exact_a2_packet_forgery_is_rejected_even_after_rehash(self):
        mats = cohort(self.manifest, 0); mm, sha = seal(self.manifest, mats); packets = packets_for(self.manifest, mats, mm, sha)
        baseline = d.terminal_summary(packets, mats, mm, sha, self.manifest)
        self.assertEqual(baseline["eligible_count"], 0)
        forged = copy.deepcopy(packets)
        for i in range(12):
            forged[i]["eligible"] = True; forged[i]["eligibility_reasons"] = []
            payload = {k: v for k, v in forged[i].items() if k != "packet_sha256"}
            forged[i]["packet_sha256"] = d.canonical_sha256(payload)
        with self.assertRaisesRegex(d.DriverContractError, "PACKET_DOES_NOT_MATCH_SEALED_MATERIAL_RECOMPUTATION"):
            d.terminal_summary(forged, mats, mm, sha, self.manifest)

    def test_material_tamper_after_seal_is_rejected(self):
        mats = cohort(self.manifest, 0); mm, sha = seal(self.manifest, mats); packets = packets_for(self.manifest, mats, mm, sha)
        tampered = copy.deepcopy(mats); tampered[0]["prefix"]["reasons"] = ["DIFFERENT_RUNTIME_ERROR"]
        with self.assertRaisesRegex(d.DriverContractError, "ATTEMPT_MATERIAL_SHA256_MISMATCH"):
            d.terminal_summary(packets, tampered, mm, sha, self.manifest)

    def test_joint_packet_and_material_tamper_cannot_bypass_unchanged_external_seal(self):
        mats = cohort(self.manifest, 0); mm, sha = seal(self.manifest, mats); packets = packets_for(self.manifest, mats, mm, sha)
        tampered_mats = copy.deepcopy(mats); tampered_mats[0]["prefix"]["reasons"] = ["DIFFERENT_RUNTIME_ERROR"]
        forged_packets = copy.deepcopy(packets); forged_packets[0]["eligibility_reasons"] = ["DIFFERENT_RUNTIME_ERROR"]
        payload = {k:v for k,v in forged_packets[0].items() if k != "packet_sha256"}; forged_packets[0]["packet_sha256"] = d.canonical_sha256(payload)
        with self.assertRaisesRegex(d.DriverContractError, "ATTEMPT_MATERIAL_SHA256_MISMATCH"):
            d.terminal_summary(forged_packets, tampered_mats, mm, sha, self.manifest)

    def test_nested_packet_tamper_is_recomputed_from_material(self):
        mats = cohort(self.manifest, 12); mm, sha = seal(self.manifest, mats); packets = packets_for(self.manifest, mats, mm, sha)
        forged = copy.deepcopy(packets); forged[0]["constructibility"]["future_distance"] = 999.0
        payload = {k:v for k,v in forged[0].items() if k != "packet_sha256"}; forged[0]["packet_sha256"] = d.canonical_sha256(payload)
        with self.assertRaisesRegex(d.DriverContractError, "PACKET_DOES_NOT_MATCH_SEALED_MATERIAL_RECOMPUTATION"):
            d.terminal_summary(forged, mats, mm, sha, self.manifest)

    def test_terminal_refuses_incomplete_duplicate_packets_and_materials(self):
        mats = cohort(self.manifest, 0); mm, sha = seal(self.manifest, mats); packets = packets_for(self.manifest, mats, mm, sha)
        with self.assertRaisesRegex(d.DriverContractError, "16_PACKETS"):
            d.terminal_summary(packets[:-1], mats, mm, sha, self.manifest)
        with self.assertRaisesRegex(d.DriverContractError, "16_MATERIALS"):
            d.terminal_summary(packets, mats[:-1], mm, sha, self.manifest)
        dup_packets = packets[:-1] + [packets[0]]
        with self.assertRaisesRegex(d.DriverContractError, "DUPLICATE_PACKET_INDEX"):
            d.terminal_summary(dup_packets, mats, mm, sha, self.manifest)

    def test_launcher_has_no_direct_science_execute_mode(self):
        proc = subprocess.run([str(ROOT/'launch_successor_feature_constructibility_v1.sh'),'execute'],cwd=ROOT,text=True,capture_output=True)
        self.assertNotEqual(proc.returncode,0); self.assertIn('invalid choice', proc.stderr)

    def test_launcher_preflight_only_reads_authority(self):
        out = subprocess.check_output([str(ROOT/'launch_successor_feature_constructibility_v1.sh'),'preflight'],cwd=ROOT,text=True)
        obj = json.loads(out); self.assertEqual(obj["manifest_sha256"], self.manifest["manifest_sha256"]); self.assertEqual(obj["scientific_result"],"NOT_ASSESSED")

    def test_cli_fixed16_seal_packetize_summarize_and_forge_rejection(self):
        mats = cohort(self.manifest, 12)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); md=td/'materials'; pd=td/'packets'; md.mkdir(); pd.mkdir()
            for i,m in enumerate(mats): write_json(md/f'attempt_{i:02d}.json', m, canonical=(i%2==0))
            mm_path=td/'material_manifest.json'; mm=validator.seal_materials(ROOT,md,mm_path); sha=mm['material_manifest_sha256']
            for i in range(16): validator.build_packet(ROOT,md/f'attempt_{i:02d}.json',mm_path,sha,pd/f'attempt_{i:02d}.json')
            out=td/'summary.json'; s=validator.summarize(ROOT,pd,md,mm_path,sha,out)
            self.assertEqual(s['eligible_count'],12); self.assertEqual(s['verdict'],d.PASS_LABEL)
            forged=json.loads((pd/'attempt_12.json').read_text()); forged['eligible']=True; forged['eligibility_reasons']=[]
            forged['packet_sha256']=d.canonical_sha256({k:v for k,v in forged.items() if k!='packet_sha256'})
            write_json(pd/'attempt_12.json',forged)
            with self.assertRaisesRegex(d.DriverContractError,'PACKET_DOES_NOT_MATCH_SEALED_MATERIAL_RECOMPUTATION'):
                validator.summarize(ROOT,pd,md,mm_path,sha,td/'forged_summary.json')

    def test_cli_rejects_material_extra_json_and_external_seal_drift(self):
        mats = cohort(self.manifest, 0)
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); md=td/'materials'; md.mkdir()
            for i,m in enumerate(mats): write_json(md/f'attempt_{i:02d}.json',m)
            write_json(md/'extra.json',{})
            with self.assertRaisesRegex(d.DriverContractError,'MATERIAL_DIRECTORY_HAS_EXTRA_JSON'):
                validator.seal_materials(ROOT,md,td/'mm.json')
            (md/'extra.json').unlink(); mm=validator.seal_materials(ROOT,md,td/'mm.json')
            with self.assertRaisesRegex(d.DriverContractError,'EXTERNAL_SEAL_MISMATCH'):
                validator.build_packet(ROOT,md/'attempt_00.json',td/'mm.json','0'*64,td/'p.json')


if __name__ == "__main__":
    unittest.main()
