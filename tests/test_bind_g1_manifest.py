"""Synthetic-only tests; these do not run ALFWorld or use study data."""
import copy
import unittest
from research.bind_g1_manifest import audit, digest, _immutable


def src(branch):
    commands = ["look", "take object", "put object in alpha", "put object in beta"]
    second = "put object in " + ("alpha" if branch == "A" else "beta")
    return {"reset": {"state_hash": "b" * 64, "goal": "place an object", "observation": "holding object",
                      "admissible_commands": commands},
            "trajectory": [{"action": "take object", "admissible_before": commands},
                           {"action": second, "admissible_before": commands}],
            "won": True, "invalid_model_turns": 0, "branch_label": branch,
            "trace_sha256": "c" * 64}


def manifest():
    data = {"schema": "plancarry.bind.g1.v0.1", "phase": "FROZEN_MANIFEST",
            "pinned": {"model_revision": "synthetic-model-only", "candidate_order_rule": "hash-sorted-frozen",
                       "evaluator_version": "synthetic", "evaluator_sha256": "a" * 64,
                       "source_protocol_sha256": "d" * 64, "confirmation_touched": False,
                       "binding_model_calls": 0},
            "candidates": [{"candidate_id": f"pair-{i:02d}", "split": "train",
                            "game_sha256": f"{i + 1:064x}", "source_family_id": f"f{i:02d}",
                            "consumption_audit": {"status": "VERIFIED_UNUSED", "evidence_id": f"synthetic-{i}"},
                            "qualification": None} for i in range(32)]}
    data["frozen_sha256"] = digest(_immutable(data))
    return data


def source_audit(data, eligible=16):
    d = copy.deepcopy(data)
    d["phase"] = "SOURCE_AUDIT"
    for i, c in enumerate(d["candidates"]):
        if i < eligible:
            c["qualification"] = {"status": "ELIGIBLE", "source_a": src("A"), "source_b": src("B"),
                                  "source_evaluator_attestation": {"evidence_id": f"synthetic-eval-{i}"}}
        else:
            c["qualification"] = {"status": "INELIGIBLE", "reason": "synthetic non-pair"}
    return d


class G1Test(unittest.TestCase):
    def test_frozen_manifest(self):
        self.assertEqual(audit(manifest())["verdict"], "FROZEN_MANIFEST_STRUCTURAL_ONLY")

    def test_frozen_manifest_rejects_missing_digest(self):
        d = manifest()
        del d["frozen_sha256"]
        result = audit(d)
        self.assertEqual(result["verdict"], "INVALID_PREEXECUTION_CONTRACT")
        self.assertIn("frozen_sha256 missing or does not match pre-registration", result["errors"])

    def test_frozen_manifest_rejects_wrong_digest(self):
        d = manifest()
        d["frozen_sha256"] = "f" * 64
        result = audit(d)
        self.assertEqual(result["verdict"], "INVALID_PREEXECUTION_CONTRACT")
        self.assertIn("frozen_sha256 missing or does not match pre-registration", result["errors"])

    def test_threshold_is_not_scientific_pass(self):
        self.assertEqual(audit(source_audit(manifest()))["verdict"],
                         "G1_STRUCTURAL_THRESHOLD_ONLY_REQUIRES_INDEPENDENT_REVIEW")

    def test_below_threshold_stops(self):
        self.assertEqual(audit(source_audit(manifest(), 15))["verdict"], "G1_STOP_BELOW_SOURCE_THRESHOLD")

    def test_ordered_action_difference_detected_even_if_set_equal(self):
        d = source_audit(manifest())
        c = d["candidates"][0]["qualification"]["source_b"]
        c["reset"]["admissible_commands"].reverse()
        r = audit(d)
        self.assertIn("reset admissible_commands differs", " | ".join(r["errors"]))

    def test_shared_first_action_required(self):
        d = source_audit(manifest())
        d["candidates"][0]["qualification"]["source_b"]["trajectory"][0]["action"] = "look"
        self.assertIn("first action differs", " | ".join(audit(d)["errors"]))

    def test_no_posttreatment_selection(self):
        d = source_audit(manifest())
        d["candidates"][0]["qualification"]["binding_result"] = "success"
        self.assertIn("post-treatment result", " | ".join(audit(d)["errors"]))

    def test_freeze_guards_candidate_replacement(self):
        d = source_audit(manifest())
        d["candidates"][0]["game_sha256"] = "f" * 64
        self.assertIn("immutable candidate/protocol definition drift", " | ".join(audit(d)["errors"]))

    def test_duplicate_game_rejected(self):
        d = manifest()
        d["candidates"][1]["game_sha256"] = d["candidates"][0]["game_sha256"]
        self.assertIn("repeated game hash", " | ".join(audit(d)["errors"]))

    def test_prior_consumption_proof_required(self):
        d = manifest()
        d["candidates"][0]["consumption_audit"] = {"status": "UNKNOWN"}
        self.assertIn("consumed-cohort exclusion proof required", " | ".join(audit(d)["errors"]))

    def test_technical_blocker_not_scientific_failure(self):
        d = source_audit(manifest())
        d["candidates"][17]["qualification"] = {"status": "TECHNICAL_FAILURE", "reason": "synthetic time-out"}
        self.assertEqual(audit(d)["verdict"], "TECHNICAL_BLOCKER_NOT_SCIENTIFIC_FAIL")

    def test_confirmation_must_be_untouched(self):
        d = manifest()
        d["pinned"]["confirmation_touched"] = True
        self.assertIn("confirmation must be explicitly untouched", " | ".join(audit(d)["errors"]))


if __name__ == "__main__":
    unittest.main()
