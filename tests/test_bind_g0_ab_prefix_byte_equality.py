"""BIND G0 toy-only full-state and byte-exact trace regression."""
import base64
import copy
import hashlib
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from bind_g0_ab_prefix_byte_equality import SCHEMA, structural_audit

def enc(x):
    return base64.b64encode(x).decode()

def sha(x):
    return hashlib.sha256(x.encode()).hexdigest()

def state(tag="S0", rng="R0", observation=b"room", cmds=(b"go to desk",b"look")):
    return {"full_hidden_state_b64":enc(tag.encode()),
            "rng_state_b64":enc(rng.encode()),
            "observation_b64":enc(observation),
            "ordered_commands":[enc(x) for x in cmds],
            "score_b64":enc(b"0"),"done_b64":enc(b"0")}

def step(n,action,bstate):
    return {"prefix_step":n,"actual_action_b64":enc(action),"after":bstate}

def fixture():
    steps=[step(0,b"RESET",state()),step(1,b"look",state("S1","R1",b"desk ahead"))]
    return {"schema":SCHEMA,"phase":"PRE_G1_SYNTHETIC_TOY",
      "source":{key:sha(key) for key in ("game_sha256","goal_sha256","simulator_sha256","renderer_sha256","tokenizer_sha256")},
      "backend":{"backend_kind":"SYNTHETIC_TOY","backend_revision_sha256":sha("toy"),
          "full_state_export_provenance":"TOY_ONLY_NOT_REAL_ATTESTATION",
          "rng_export_provenance":"TOY_ONLY_NOT_REAL_ATTESTATION"},
      "pair":"synthetic-01",
      "A":{"independent_instance_id":"toy-A","steps":steps},
      "B":{"independent_instance_id":"toy-B","steps":copy.deepcopy(steps)}}

class TraceTests(unittest.TestCase):
    def reject(self,data,field):
        got=structural_audit(data)
        self.assertEqual("MISMATCHED_SYNTHETIC_PREFIX",got["status"])
        self.assertIn(field,got["failures"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_exact_identity_is_toy_only_no_g0_pass(self):
        got=structural_audit(fixture())
        self.assertEqual("MATCHED_SYNTHETIC_PREFIX_ONLY",got["status"])
        self.assertNotEqual("PASS",got["status"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_action_order_is_not_sorted(self):
        d=fixture()
        d["B"]["steps"][0]["after"]["ordered_commands"].reverse()
        self.reject(d,"step_0.ordered_commands")

    def test_rng_difference_is_detected(self):
        d=fixture()
        d["B"]["steps"][0]["after"]["rng_state_b64"]=enc(b"RNG drift")
        self.reject(d,"step_0.rng_state_b64")

    def test_hidden_state_difference_is_detected(self):
        d=fixture()
        d["B"]["steps"][1]["after"]["full_hidden_state_b64"]=enc(b"secret drift")
        self.reject(d,"step_1.full_hidden_state_b64")

    def test_observation_difference_is_detected(self):
        d=fixture()
        d["B"]["steps"][1]["after"]["observation_b64"]=enc(b"desk behind")
        self.reject(d,"step_1.observation_b64")

    def test_different_first_actual_action_is_rejected(self):
        d=fixture()
        d["B"]["steps"][1]["actual_action_b64"]=enc(b"go to desk")
        self.reject(d,"step_1.actual_action")

    def test_unbalanced_prefix_is_invalid(self):
        d=fixture()
        d["B"]["steps"].pop()
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_same_instance_is_invalid(self):
        d=fixture()
        d["B"]["independent_instance_id"]="toy-A"
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_missing_full_state_is_invalid(self):
        d=fixture()
        del d["A"]["steps"][0]["after"]["full_hidden_state_b64"]
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_fake_real_backend_claim_is_invalid(self):
        d=fixture()
        d["backend"]["backend_kind"]="ALFWORLD_REAL"
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_fake_preapproved_backend_provenance_is_invalid(self):
        d=fixture()
        d["backend"]["rng_export_provenance"]="INDEPENDENTLY_APPROVED"
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_bool_prefix_index_is_invalid(self):
        d=fixture()
        d["A"]["steps"][1]["prefix_step"]=True
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_noncanonical_base64_is_invalid(self):
        d=fixture()
        d["B"]["steps"][0]["after"]["rng_state_b64"]="***"
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_empty_command_menu_is_invalid(self):
        d=fixture()
        d["A"]["steps"][0]["after"]["ordered_commands"]=[]
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_same_action_but_different_returned_bytes_is_rejected(self):
        d=fixture()
        d["B"]["steps"][1]["after"]["observation_b64"]=enc(b"desk ahead\n")
        self.reject(d,"step_1.observation_b64")

    def test_duplicate_menu_action_invalid(self):
        d=fixture()
        x=d["B"]["steps"][0]["after"]["ordered_commands"]
        x.append(x[0])
        with self.assertRaises(ValueError):
            structural_audit(d)

    def test_two_sides_same_illegal_action_must_not_match(self):
        d=fixture()
        for side in ("A","B"):
            d[side]["steps"][1]["actual_action_b64"]=enc(b"teleport into a future state")
        got=structural_audit(d)
        self.assertEqual("MISMATCHED_SYNTHETIC_PREFIX",got["status"])
        self.assertIn("step_1.A.action_not_admissible",got["failures"])
        self.assertIn("step_1.B.action_not_admissible",got["failures"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_one_side_menu_lacks_shared_action(self):
        d=fixture()
        d["B"]["steps"][0]["after"]["ordered_commands"]=[enc(b"go to desk")]
        got=structural_audit(d)
        self.assertEqual("MISMATCHED_SYNTHETIC_PREFIX",got["status"])
        self.assertIn("step_0.ordered_commands",got["failures"])
        self.assertIn("step_1.B.action_not_admissible",got["failures"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_shared_information_action_remains_legal(self):
        d=fixture()
        got=structural_audit(d)
        self.assertEqual("MATCHED_SYNTHETIC_PREFIX_ONLY",got["status"])
        self.assertEqual([],got["failures"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_both_sides_cannot_act_after_terminal_reset(self):
        d=fixture()
        for side in ("A","B"):
            d[side]["steps"][0]["after"]["done_b64"]=enc(b"1")
        got=structural_audit(d)
        self.assertEqual("MISMATCHED_SYNTHETIC_PREFIX",got["status"])
        self.assertIn("step_1.A.action_after_terminal",got["failures"])
        self.assertIn("step_1.B.action_after_terminal",got["failures"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_only_one_side_cannot_act_after_terminal(self):
        d=fixture()
        d["B"]["steps"][0]["after"]["done_b64"]=enc(b"1")
        got=structural_audit(d)
        self.assertEqual("MISMATCHED_SYNTHETIC_PREFIX",got["status"])
        self.assertIn("step_0.done_b64",got["failures"])
        self.assertIn("step_1.B.action_after_terminal",got["failures"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_final_step_may_terminate(self):
        d=fixture()
        for side in ("A","B"):
            d[side]["steps"][1]["after"]["done_b64"]=enc(b"1")
        got=structural_audit(d)
        self.assertEqual("MATCHED_SYNTHETIC_PREFIX_ONLY",got["status"])
        self.assertEqual("NOT_AUTHORIZED",got["scientific_gate"])

    def test_noncanonical_terminal_marker_invalid(self):
        d=fixture()
        for side in ("A","B"):
            d[side]["steps"][0]["after"]["done_b64"]=enc(b"FALSE")
        with self.assertRaises(ValueError):
            structural_audit(d)


if __name__=="__main__":
    unittest.main()
