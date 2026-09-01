from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cpds_v5_packet_producer_v1 as producer
import cpds_v5_packet_validator_v1 as validator

ROOT = Path(__file__).resolve().parents[1]


def unit(seed: int = 0):
    x = [0.0] * validator.NATIVE_WIDTH
    x[seed % validator.NATIVE_WIDTH] = 1.0
    return x


def site(goal: str, obs: str, candidates, target, seed=0):
    actions = sorted(candidates)
    return {
        "prompt": validator.render_policy_prompt(goal, obs, actions),
        "observation": obs,
        "candidate_actions": actions,
        "base_scores": [float(-i) for i in range(len(actions))],
        "action_features": [unit(seed + i) for i in range(len(actions))],
        "target_index": actions.index(target),
        "target_surface_command": target,
    }


class PacketProducerValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.behavior, cls.contract = validator.load_frozen_authority()
        cls.row = copy.deepcopy(cls.behavior["rows"][0])

    def sample_packet(self):
        r = self.row
        common1_surface = "examine synthetic common1"
        common2_surface = "go to synthetic common2"
        continuation_surface = "examine synthetic continuation"
        s0 = site(r["goal_canonical"], "obs-after-common1", ["look", common2_surface], common2_surface, 10)
        s1 = site(r["goal_canonical"], "obs-after-common2", ["inventory", continuation_surface], continuation_surface, 20)
        p = {
            "schema": validator.PACKET_SCHEMA,
            "base_model_id": validator.BASE_MODEL_ID,
            "base_model_revision": validator.BASE_MODEL_REVISION,
            "source_graph_id": r["source_graph_id"],
            "structural_key_sha256": r["structural_key_sha256"],
            "partition": r["partition"],
            "packet_id": r["packet_id"],
            "pre_reset_hidden": unit(1),
            "updates": [
                {
                    "symbolic_command": r["update_symbolic_commands"][0],
                    "surface_command": common1_surface,
                    "transition_hidden": unit(2),
                    "prediction_site": s0,
                    "next_transition_hidden": unit(3),
                    "negative_transition_hidden": unit(4),
                    "negative_donor_source_graph_id": r["negative_donor_source_graph_ids"][0],
                },
                {
                    "symbolic_command": r["update_symbolic_commands"][1],
                    "surface_command": common2_surface,
                    "transition_hidden": unit(3),
                    "prediction_site": s1,
                    "next_transition_hidden": unit(5),
                    "negative_transition_hidden": unit(6),
                    "negative_donor_source_graph_id": r["negative_donor_source_graph_ids"][1],
                },
            ],
            "final_prediction_site": copy.deepcopy(s1),
            "producer_provenance": {
                "packet_construction_contract_sha256": validator.CONTRACT_SHA256,
                "behavior_manifest_sha256": validator.BEHAVIOR_SHA256,
                "source_authority_seal": validator.SOURCE_AUTHORITY_SEAL,
                "candidate_census_sha256": validator.CENSUS_SHA256,
                "v4_reserved_seal_sha256": validator.RESERVED_FILE_SHA256,
                "game_tw_pddl_sha256": r["game_tw_pddl_sha256"],
                "runtime_fingerprint": "a" * 64,
                "model_snapshot_revision": validator.BASE_MODEL_REVISION,
                "continuation_symbolic_command": r["continuation_symbolic_command"],
                "continuation_surface_command": continuation_surface,
                "producer_code_sha256": validator.sha_file(producer.__file__),
                "packet_binding_commit": validator.EXPECTED_PACKET_BINDING_COMMIT,
            },
        }
        p["packet_sha256"] = validator.sha_obj(p)
        return p

    def reseal(self, p):
        p.pop("packet_sha256", None)
        p["packet_sha256"] = validator.sha_obj(p)
        return p

    def test_frozen_authority_and_bound_code_are_exact(self):
        self.assertEqual(len(self.behavior["rows"]), 1927)
        self.assertEqual(self.contract["contract_sha256"], validator.CONTRACT_SHA256)
        self.assertEqual(self.contract["source_population"]["TRAIN_count"], 1504)
        self.assertEqual(self.contract["source_population"]["CALIBRATION_count"], 423)
        self.assertEqual(self.contract["source_population"]["DEVELOPMENT_count"], 0)
        self.assertEqual(self.contract["source_population"]["CONFIRMATION_count"], 0)

    def test_implementation_audit_self_hash_and_exact_bytes(self):
        audit_path = ROOT / "results" / "design" / "plancarry_cpds_v5_packet_producer_implementation_audit_a1_20260901.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        x = copy.deepcopy(audit); expected = x.pop("audit_sha256")
        self.assertEqual(expected, validator.sha_obj(x))
        self.assertEqual(audit["scientific_result"], "NOT_ASSESSED")
        self.assertFalse(audit["scientific_variable_drift"])
        self.assertEqual(audit["packet_binding"]["commit"], "4c4de54e16f697e9aa12b3b7fa8b07f6ee80da34")
        self.assertEqual(audit["packet_binding"]["review_result_id"], "0c3fe27e-9762-4526-beb8-3a23fc57323d")
        self.assertEqual(audit["packet_binding"]["review_verdict"], "PASS_FOR_CPDS_V5_PACKET_CONSTRUCTION_BINDING")
        self.assertEqual(audit["implementation_files_sha256"]["cpds_v5_packet_producer_v1.py"], validator.EXPECTED_PRODUCER_CODE_SHA256)
        self.assertEqual(validator.sha_file(ROOT / "cpds_v5_packet_producer_v1.py"), validator.EXPECTED_PRODUCER_CODE_SHA256)
        self.assertEqual(audit["implementation_files_sha256"]["cpds_v5_packet_validator_v1.py"], "446ed137758bd84d66bba8252ea1a5964497a52921cc5ffa427ddb0e9cbe2e8c")
        self.assertEqual(audit["implementation_files_sha256"]["tests/test_cpds_v5_packet_producer_validator.py"], "f15bb63e830b9b37663085dc474add231aee2993e07766c9385b06532fff9df5")
        for rel, sha in audit["unchanged_bound_files_sha256"].items():
            self.assertEqual(validator.sha_file(ROOT / rel), sha)
        self.assertEqual(audit["population"], {"TRAIN":1504,"CALIBRATION":423,"DEVELOPMENT":0,"CONFIRMATION":0})
        self.assertTrue(all(v is False for v in audit["execution_counters"].values()))

    def test_provenance_repair_audit_self_hash_and_exact_successor_bytes(self):
        audit_path = ROOT / "results" / "design" / "plancarry_cpds_v5_packet_provenance_repair_a1_20260901.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        x = copy.deepcopy(audit); expected = x.pop("audit_sha256")
        self.assertEqual(expected, validator.sha_obj(x))
        self.assertEqual(audit["source_release_commit"], "ccc831c69cbb76304ad88790be9b2056c636bb25")
        self.assertEqual(audit["failed_review_result_id"], "30cf9667-30c9-4244-a024-5bd9e2d3318b")
        self.assertEqual(audit["regression_proposal_id"], "3940c1bd-4ab8-4cb8-8e1a-dcbc8db6b68d")
        self.assertFalse(audit["scientific_variable_drift"])
        self.assertEqual(audit["exact_provenance_guards"], {
            "producer_code_sha256": validator.EXPECTED_PRODUCER_CODE_SHA256,
            "packet_binding_commit": validator.EXPECTED_PACKET_BINDING_COMMIT,
        })
        for rel, sha in audit["successor_files_sha256"].items():
            self.assertEqual(validator.sha_file(ROOT / rel), sha)
        self.assertEqual(validator.sha_file(ROOT / "cpds_v5_packet_producer_v1.py"), validator.EXPECTED_PRODUCER_CODE_SHA256)
        self.assertTrue(all(v is False for v in audit["execution_counters"].values()))

    def test_strict_real_demangler_has_no_identity_fallback(self):
        class Fake: pass
        with self.assertRaisesRegex(RuntimeError, "PACKET_REAL_DEMANGLER_UNAVAILABLE"):
            producer._strict_surface_resolver(Fake())
        src = Path(producer.__file__).read_text(encoding="utf-8")
        self.assertNotIn("return lambda command: str(command)", src)

    def test_exact_packet_geometry_validates(self):
        p = self.sample_packet()
        out = validator.validate_packet(p, self.row)
        self.assertEqual(len(out["updates"]), 2)
        self.assertEqual(out["final_prediction_site"], out["updates"][1]["prediction_site"])
        self.assertEqual(out["updates"][0]["next_transition_hidden"], out["updates"][1]["transition_hidden"])

    def test_extra_update_and_future_geometry_fail_closed(self):
        p = self.sample_packet()
        p["updates"].append(copy.deepcopy(p["updates"][1])); self.reseal(p)
        with self.assertRaisesRegex(ValueError, "UPDATES_EXACTLY_TWO"):
            validator.validate_packet(p, self.row)
        p = self.sample_packet(); p["updates"][0]["next_transition_hidden"] = unit(99); self.reseal(p)
        with self.assertRaisesRegex(ValueError, "UPDATE0_POSITIVE_NOT_COMMON2"):
            validator.validate_packet(p, self.row)

    def test_candidate_target_and_prompt_tamper_fail_closed(self):
        p = self.sample_packet(); p["updates"][0]["prediction_site"]["target_index"] = 1 - int(p["updates"][0]["prediction_site"]["target_index"]); self.reseal(p)
        with self.assertRaisesRegex(ValueError, "TARGET_GEOMETRY"):
            validator.validate_packet(p, self.row)
        p = self.sample_packet(); p["updates"][1]["prediction_site"]["prompt"] += "tamper"; self.reseal(p)
        with self.assertRaisesRegex(ValueError, "PROMPT_MISMATCH"):
            validator.validate_packet(p, self.row)

    def test_resealed_producer_provenance_tamper_fails_closed(self):
        p = self.sample_packet(); p["producer_provenance"]["producer_code_sha256"] = "0" * 64; self.reseal(p)
        with self.assertRaisesRegex(ValueError, "PROVENANCE:producer_code_sha256"):
            validator.validate_packet(p, self.row)
        p = self.sample_packet(); p["producer_provenance"]["packet_binding_commit"] = "deadbeef" * 5; self.reseal(p)
        with self.assertRaisesRegex(ValueError, "PROVENANCE:packet_binding_commit"):
            validator.validate_packet(p, self.row)

    def test_recursive_evaluator_outcome_and_nonunit_features_rejected(self):
        p = self.sample_packet(); p["producer_provenance"]["outcome"] = "x"; self.reseal(p)
        with self.assertRaisesRegex(ValueError, "EVALUATOR_OR_OUTCOME_FIELD_FORBIDDEN"):
            validator.validate_packet(p, self.row)
        p = self.sample_packet(); p["pre_reset_hidden"] = [1.0] * validator.NATIVE_WIDTH; self.reseal(p)
        with self.assertRaisesRegex(ValueError, "PRE_RESET_UNIT_NORM"):
            validator.validate_packet(p, self.row)

    def test_contrastive_donor_injection_uses_exact_ordinal_features(self):
        rows = [
            {"source_graph_id":"a","partition":"TRAIN","negative_donor_source_graph_ids":["b","c"]},
            {"source_graph_id":"b","partition":"TRAIN","negative_donor_source_graph_ids":["c","a"]},
            {"source_graph_id":"c","partition":"TRAIN","negative_donor_source_graph_ids":["a","b"]},
        ]
        packets=[]
        for i,g in enumerate("abc"):
            packets.append({"source_graph_id":g,"partition":"TRAIN","updates":[{"transition_hidden":unit(10+i),"next_transition_hidden":unit(20+i)},{"transition_hidden":unit(30+i),"next_transition_hidden":unit(40+i)}]})
        out={p["source_graph_id"]:p for p in producer.inject_contrastive_negatives(packets,rows)}
        self.assertEqual(out["a"]["updates"][0]["negative_transition_hidden"], unit(31))
        self.assertEqual(out["a"]["updates"][1]["negative_transition_hidden"], unit(42))
        self.assertEqual(out["a"]["updates"][0]["negative_donor_source_graph_id"], "b")
        self.assertEqual(out["a"]["updates"][1]["negative_donor_source_graph_id"], "c")

    def test_positive_builder_orders_causal_steps_and_excludes_immediate_feature(self):
        r = copy.deepcopy(self.row)
        # Bypass real game bytes only inside this synthetic no-science unit fixture.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); game=root/"json_2.1.1"/"train"/r["source_graph_id"]/"game.tw-pddl"; game.parent.mkdir(parents=True); game.write_bytes(b"fake")
            r["game_tw_pddl_sha256"] = hashlib.sha256(b"fake").hexdigest()
            surfaces={r["immediate_symbolic_command"]:"immediate",r["update_symbolic_commands"][0]:"common1",r["update_symbolic_commands"][1]:"common2",r["continuation_symbolic_command"]:"continuation"}
            class Rec:
                def __init__(self,obs): self.error=None; self.observation=obs
            class Env:
                def __init__(self,_): self.i=0; self.observation="reset"; self.admissible_commands=["immediate","look"]; self.steps=[]
                def step(self,a):
                    self.steps.append(a); self.i+=1
                    if self.i==1: self.observation="after immediate"; self.admissible_commands=["common1","look"]
                    elif self.i==2: self.observation="after common1"; self.admissible_commands=["common2","look"]
                    elif self.i==3: self.observation="after common2"; self.admissible_commands=["continuation","inventory"]
                    else: self.observation="after continuation"; self.admissible_commands=["look"]
                    return Rec(self.observation)
                def close(self): pass
            calls=[]
            def fake_hidden(model,tok,payload):
                text=payload.decode(); calls.append(text); return unit(len(calls))
            def fake_score(model,tok,prompt,action): return -float(len(action))
            with mock.patch.object(producer.v5rt,"native_hidden_feature",side_effect=fake_hidden), mock.patch.object(producer.v5rt,"teacher_forced_whole_action_score",side_effect=fake_score):
                p=producer._positive_packet(r,object(),object(),Env,"b"*64,root,resolver_factory=lambda env:lambda s:surfaces[s])
            self.assertEqual([u["surface_command"] for u in p["updates"]],["common1","common2"])
            self.assertEqual(len(p["updates"]),2)
            self.assertEqual(p["updates"][0]["next_transition_hidden"],p["updates"][1]["transition_hidden"])
            # One prompt feature + common1 + action features + common2 + action features + continuation.
            transition_payloads=[x for x in calls if x.startswith('{"command"')]
            self.assertEqual(len(transition_payloads),3)
            self.assertNotIn('"command":"'+r["immediate_symbolic_command"]+'"',"\n".join(transition_payloads))
            self.assertIn('"command":"'+r["continuation_symbolic_command"]+'"',"\n".join(transition_payloads))


if __name__ == "__main__": unittest.main()
