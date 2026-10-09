"""Offline synthetic BIND G0 integrity regression, never a G1 science test."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from bind_g0_frozen_identity_v03 import (
    CANDIDATE_HASH_KEYS, PIN_HASH_KEYS, SCHEMA, audit, frozen_digest,
)


def h(i):
    return f"{i:064x}"


def fixture():
    pinned = {k: h(100 + n) for n, k in enumerate(sorted(PIN_HASH_KEYS))}
    pinned.update(model_revision="test-model@frozen",
                  confirmation_touched=False, source_model_calls=0)
    candidates = []
    for i in range(32):
        c = {k: h(1000 + 32*i + j)
             for j, k in enumerate(sorted(CANDIDATE_HASH_KEYS))}
        c.update(candidate_id=f"test-{i:02d}", source_family_id=f"family-{i}",
                 split="train", source_a_seed=2*i, source_b_seed=2*i+1,
                 consumption_audit="PENDING_INDEPENDENT")
        candidates.append(c)
    m = dict(schema=SCHEMA, phase="FROZEN_PRE_SOURCE", pinned=pinned,
             candidates=candidates)
    m["frozen_sha256"] = frozen_digest(m)
    return m


class IntegrityTests(unittest.TestCase):
    def assert_invalid(self, m):
        result = audit(m)
        self.assertEqual("INVALID_AUDIT_INPUT", result["verdict"])
        self.assertEqual("NOT_AUTHORIZED", result["scientific_gate"])

    def test_complete_manifest_never_grants_scientific_pass(self):
        result = audit(fixture())
        self.assertEqual("BLOCKED_INDEPENDENT_SOURCE_ATTESTATION", result["verdict"])
        self.assertEqual("NOT_AUTHORIZED", result["scientific_gate"])

    def test_seed_mutation_detected(self):
        m = fixture()
        m["candidates"][0]["source_a_seed"] += 100
        self.assert_invalid(m)

    def test_full_state_mutation_detected(self):
        m = fixture()
        m["candidates"][1]["reset_full_state_sha256"] = h(777777)
        self.assert_invalid(m)

    def test_source_prompt_mutation_detected(self):
        m = fixture()
        m["candidates"][0]["source_b_prompt_sha256"] = h(888888)
        self.assert_invalid(m)

    def test_source_history_mutation_detected(self):
        m = fixture()
        m["candidates"][2]["source_a_history_sha256"] = h(888887)
        self.assert_invalid(m)

    def test_action_menu_mutation_detected(self):
        m = fixture()
        m["candidates"][3]["ordered_actions_sha256"] = h(888886)
        self.assert_invalid(m)

    def test_candidate_reorder_detected(self):
        m = fixture()
        m["candidates"][0], m["candidates"][1] = m["candidates"][1], m["candidates"][0]
        self.assert_invalid(m)

    def test_extra_candidate_field_rejected_even_after_rehash(self):
        m = fixture()
        m["candidates"][0]["future_answer"] = "CHEAT"
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_extra_top_level_field_rejected_even_after_rehash(self):
        m = fixture()
        m["source_success"] = True
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_duplicate_game_rejected_even_after_rehash(self):
        m = fixture()
        m["candidates"][1]["game_sha256"] = m["candidates"][0]["game_sha256"]
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_candidate_removed_even_after_rehash(self):
        m = fixture()
        m["candidates"].pop()
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_phase_not_source_frozen_even_after_rehash(self):
        m = fixture()
        m["phase"] = "POST_EVALUATION"
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_source_calls_not_zero_even_after_rehash(self):
        m = fixture()
        m["pinned"]["source_model_calls"] = 1
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_self_attested_unused_even_after_rehash(self):
        m = fixture()
        m["candidates"][0]["consumption_audit"] = "VERIFIED_UNUSED"
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_boolean_seed_rejected(self):
        m = fixture()
        m["candidates"][0]["source_a_seed"] = True
        m["frozen_sha256"] = frozen_digest(m)
        self.assert_invalid(m)

    def test_valid_checksum_does_not_prove_independent_custody(self):
        result = audit(fixture())
        self.assertNotEqual("PASS", result["verdict"])
        self.assertEqual("NOT_AUTHORIZED", result["scientific_gate"])


if __name__ == "__main__":
    unittest.main()
