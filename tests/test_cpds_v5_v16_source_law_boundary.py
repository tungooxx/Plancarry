import ast
import copy
import hashlib
import inspect
import unittest
from unittest import mock

import cpds_v5_v15_authority_proof_v1 as v15
import cpds_v5_v16_source_law_boundary_v1 as v16


def families():
    return [f"dev-{i:02d}" for i in range(33)]


def context_root():
    return "a" * 64


def consumed_family_id():
    return "cpds-v16-current-program"


def invocation_id():
    return v16.derive_invocation_id(consumed_family_id=consumed_family_id(), context_root=context_root())


def fabricated_raw_distinct_correlated():
    # 33 blocks, deterministic and pairwise-distinct; not evidence of iid randomness.
    out = bytearray()
    for i in range(33):
        for j in range(8):
            word = (i * 257 + j * 17) % 65520
            out.extend(int(word).to_bytes(2, "big"))
    return bytes(out)


def fabricated_raw_all_zero():
    return b"\x00\x00" * (33 * 8)


def inspectable_fake_source_once():
    return b"\x00" * 528


def inspectable_fake_attestation():
    return {"primitive_id": v16.SOURCE_PRIMITIVE_ID, "python_binding": "fake"}


def inspectable_fake_transducer(*, raw, family_ids):
    return {"schema": "FORGED", "assignments": []}


def inspectable_fake_partition(raw, family_ids):
    return {fid: (0,) * 8 for fid in family_ids}


def inspectable_fake_first_accepted(words):
    return (tuple(v15.EXACT_ARMS), (0,))


def inspectable_fake_factoradic(rank):
    return tuple(v15.EXACT_ARMS)


class V16SourceLawBoundary(unittest.TestCase):
    def test_source_law_is_explicit_assumption_not_receipt_proof(self):
        a = v16.source_law_assumption()
        self.assertEqual(v16.verify_source_law_assumption_declaration(a), a["assumption_sha256"])
        self.assertFalse(a["mechanically_proven_by_serialized_receipt"])
        self.assertFalse(a["unconditional_kernel_randomness_claim"])
        self.assertIn("CONDITIONAL", a["randomization_claim"])

    def test_production_source_is_noninjectable_one_shot(self):
        proof = v16.verify_production_noninjectability()
        self.assertEqual(proof["source_getrandom_call_count"], 1)
        self.assertEqual(proof["source_request_bytes"], 528)
        self.assertEqual(proof["retry_source_call_count"], 0)
        self.assertFalse(proof["caller_entropy_in_production"])
        self.assertFalse(proof["receipt_substitution_in_production"])
        params = set(inspect.signature(v16.produce_development_assignment_bundle).parameters)
        self.assertEqual(params, {"family_ids","consumed_family_id","context_root","invocation_id"})

    def test_builtin_source_attestation_rejects_monkeypatched_source(self):
        with mock.patch.object(v16.os, "getrandom", lambda n, flags=0: b"\x00" * n):
            with self.assertRaisesRegex(ValueError, "V16_SOURCE_NOT_BUILTIN_GETRANDOM"):
                v16._production_source_primitive_attestation()

    def test_frozen_authority_does_not_rehash_mutated_source_helper(self):
        before = v16.production_source_authority()
        iid = invocation_id()
        with mock.patch.object(v16, "_invoke_production_source_once", inspectable_fake_source_once):
            after = v16.production_source_authority()
            self.assertEqual(after, before)
            self.assertEqual(v16.derive_invocation_id(consumed_family_id=consumed_family_id(), context_root=context_root()), iid)
            with self.assertRaisesRegex(ValueError, "V16_FROZEN_SOURCE_COMPONENT_DRIFT"):
                v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=iid)

    def test_mutated_primitive_attestation_cannot_self_authorize(self):
        iid = invocation_id()
        with mock.patch.object(v16, "_production_source_primitive_attestation", inspectable_fake_attestation):
            self.assertEqual(v16.derive_invocation_id(consumed_family_id=consumed_family_id(), context_root=context_root()), iid)
            with self.assertRaisesRegex(ValueError, "V16_FROZEN_SOURCE_COMPONENT_DRIFT"):
                v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=iid)

    def test_mutated_v16_transducer_cannot_self_authorize(self):
        iid = invocation_id()
        with mock.patch.object(v16, "deterministic_transducer_proof_from_raw", inspectable_fake_transducer):
            self.assertEqual(v16.derive_invocation_id(consumed_family_id=consumed_family_id(), context_root=context_root()), iid)
            with self.assertRaisesRegex(ValueError, "V16_FROZEN_SOURCE_COMPONENT_DRIFT"):
                v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=iid)

    def test_mutated_v15_partition_alias_cannot_self_authorize(self):
        iid = invocation_id()
        with mock.patch.object(v15, "_partition_invocation_bytes", inspectable_fake_partition):
            with self.assertRaisesRegex(ValueError, "V16_FROZEN_SOURCE_COMPONENT_DRIFT"):
                v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=iid)

    def test_mutated_v15_first_accepted_alias_cannot_self_authorize(self):
        iid = invocation_id()
        with mock.patch.object(v15, "first_accepted_assignment", inspectable_fake_first_accepted):
            with self.assertRaisesRegex(ValueError, "V16_FROZEN_SOURCE_COMPONENT_DRIFT"):
                v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=iid)

    def test_mutated_v15_factoradic_alias_cannot_self_authorize(self):
        iid = invocation_id()
        with mock.patch.object(v15, "factoradic_unrank_s6", inspectable_fake_factoradic):
            with self.assertRaisesRegex(ValueError, "V16_FROZEN_SOURCE_COMPONENT_DRIFT"):
                v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=iid)

    def test_exact_sampler_and_fixed_block_counting(self):
        p = v15.exact_sampler_count_proof()
        self.assertEqual(p, {"accepted":65520,"rejected":16,"per_rank_preimages":91,"rank_count":720})
        b = v15.fixed_block_conditional_rank_count_proof()
        self.assertEqual(b["words_per_family"], 8)
        self.assertEqual(b["all_rejected_blocks"], 16**8)
        self.assertEqual(b["successful_blocks_per_rank"] * 720, b["successful_blocks"])
        self.assertEqual(b["conditional_rank_law_given_success"], "EXACT_UNIFORM_S6")

    def test_fabricated_distinct_correlated_receipt_is_integrity_only(self):
        raw = fabricated_raw_distinct_correlated()
        r = v16._build_provenance_receipt(raw=raw, family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=invocation_id())
        s = v16.verify_provenance_receipt_integrity(r)
        self.assertEqual(s["integrity"], "PASS")
        self.assertEqual(s["randomness_origin"], "NOT_ESTABLISHED_BY_SERIALIZED_RECEIPT")
        self.assertEqual(s["source_law"], "NOT_ESTABLISHED_BY_SERIALIZED_RECEIPT")
        self.assertIn("CONDITIONAL", s["scientific_randomization_validity"])

    def test_fabricated_all_zero_receipt_is_integrity_only_not_origin_proof(self):
        raw = fabricated_raw_all_zero()
        r = v16._build_provenance_receipt(raw=raw, family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=invocation_id())
        s = v16.verify_provenance_receipt_integrity(r)
        self.assertEqual(s["integrity"], "PASS")
        self.assertEqual(s["randomness_origin"], "NOT_ESTABLISHED_BY_SERIALIZED_RECEIPT")
        # A deterministic transducer proof may be valid for fabricated bytes; its scope is explicit.
        p = v16.deterministic_transducer_proof_from_raw(raw=raw, family_ids=families())
        self.assertIn("DOES_NOT_PROVE_SOURCE_LAW", p["proof_scope"])

    def test_receipt_cannot_overclaim_even_after_rehash(self):
        raw = fabricated_raw_distinct_correlated()
        r = v16._build_provenance_receipt(raw=raw, family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=invocation_id())
        r["randomness_origin_established"] = True
        body = dict(r); body.pop("receipt_sha256")
        r["receipt_sha256"] = v15.sha_obj(body)
        with self.assertRaisesRegex(ValueError, "V16_RECEIPT_OVERCLAIM"):
            v16.verify_provenance_receipt_integrity(r)

    def test_transducer_proof_is_byte_bound_but_source_neutral(self):
        raw = fabricated_raw_distinct_correlated()
        p = v16.deterministic_transducer_proof_from_raw(raw=raw, family_ids=families())
        self.assertEqual(v16.verify_deterministic_transducer_proof(p, raw=raw, family_ids=families()), p["proof_sha256"])
        tampered = bytearray(raw); tampered[-1] ^= 1
        with self.assertRaises(ValueError):
            v16.verify_deterministic_transducer_proof(p, raw=bytes(tampered), family_ids=families())

    def test_all_rejected_block_fails_closed_without_redraw_api(self):
        raw = bytearray(fabricated_raw_distinct_correlated())
        for j in range(8):
            raw[2*j:2*j+2] = (65535).to_bytes(2, "big")
        with self.assertRaisesRegex(ValueError, "ENTROPY_PREFIX_NO_ACCEPTED_WORD"):
            v16.deterministic_transducer_proof_from_raw(raw=bytes(raw), family_ids=families())
        retry_src = inspect.getsource(v16.retry_same_assignment_bundle)
        self.assertNotIn("getrandom", retry_src)
        self.assertNotIn("_invoke_production_source_once", retry_src)

    def test_real_production_bundle_has_conditional_not_origin_claim(self):
        bundle = v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=invocation_id())
        status = v16.verify_assignment_bundle_structure(bundle)
        self.assertEqual(len(bundle["assignments"]), 33)
        self.assertEqual(status["bundle_integrity"], "PASS")
        self.assertEqual(status["randomness_origin"], "NOT_ESTABLISHED_BY_SERIALIZED_BUNDLE")
        self.assertEqual(status["scientific_randomization_validity"], "EXACT_ONLY_CONDITIONAL_ON_SOURCE_LAW_ASSUMPTION")

    def test_retry_reuses_exact_bundle_and_rejects_binding_switches(self):
        bundle = v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=invocation_id())
        same = v16.retry_same_assignment_bundle(bundle, consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=invocation_id())
        self.assertEqual(same, bundle)
        with self.assertRaisesRegex(ValueError, "V16_RETRY_CONTEXT_SWITCH"):
            v16.retry_same_assignment_bundle(bundle, consumed_family_id=consumed_family_id(), context_root="b"*64, invocation_id=invocation_id())

    def test_release_proof_binds_full_history_and_conditional_scope(self):
        bundle = v16.produce_development_assignment_bundle(family_ids=families(), consumed_family_id=consumed_family_id(), context_root=context_root(), invocation_id=invocation_id())
        history = [{"event":"source-latency-class","value":"fixed"},{"event":"admission","value":"release"}]
        p = v16.make_release_conditional_law_proof(event_name="release", depends_on=["source_latency","technical_status"], context_root=context_root(), assignment_bundle=bundle, release_event_history=history)
        self.assertEqual(v16.verify_release_conditional_law_proof(p, event_name="release", depends_on=["technical_status","source_latency"], context_root=context_root(), assignment_bundle=bundle, release_event_history=history), p["proof_sha256"])
        self.assertFalse(p["receipt_used_as_randomness_origin_proof"])
        self.assertIn("CONDITIONAL", p["preserved_law"])
        bad_history = history + [{"event":"late","value":"changed"}]
        with self.assertRaisesRegex(ValueError, "V16_RELEASE_PROOF_HISTORY"):
            v16.verify_release_conditional_law_proof(p, event_name="release", depends_on=["source_latency","technical_status"], context_root=context_root(), assignment_bundle=bundle, release_event_history=bad_history)

    def test_inherited_v15_controls_and_protected_science_unchanged(self):
        inherited = v16.verify_inherited_v15_controls()
        self.assertEqual(inherited["protected_science"]["confirmation_status"], "HARD_SEALED_NO_RUNTIME_ROUTE")
        self.assertEqual(inherited["protected_science"]["future_program_authority"], "NONE")
        self.assertEqual(inherited["production_slot_sutva"]["driver_sha256"], "6daf31543e63eb7aca2ae67c1f83577b6af8c2b08c1f1fdd0e70d532b2ddae02")
        self.assertEqual(inherited["historical_unsupported_exposure"], "UNKNOWN")

    def test_static_preflight_is_pre_science_only(self):
        p = v16.static_preflight()
        self.assertFalse(p["scientific_variable_drift"])
        self.assertEqual(p["scientific_result"], "NOT_ASSESSED_PRE_SCIENCE_ONLY")
        self.assertEqual(p["model_calls"], 0)
        self.assertEqual(p["environment_calls"], 0)
        self.assertEqual(p["development_calls"], 0)
        self.assertEqual(p["confirmation_calls"], 0)
        self.assertEqual(p["receipt_semantics"], v16.RECEIPT_ROLE)
        self.assertEqual(p["frozen_production_source_implementation_sha256"], v16.production_source_implementation_sha256())
        self.assertEqual(p["frozen_production_source_bindings"], v16.verify_frozen_production_source_bindings())

    def test_no_old_receipt_verifier_in_v16_production_entrypoint(self):
        src = inspect.getsource(v16.produce_development_assignment_bundle)
        self.assertNotIn("verify_source_invocation_evidence", src)
        self.assertNotIn("build_entropy_realization_proof", src)
        self.assertNotIn("raw_bytes", str(inspect.signature(v16.produce_development_assignment_bundle)))
        self.assertNotIn("receipt", str(inspect.signature(v16.produce_development_assignment_bundle)))

    def test_v15_baseline_module_remains_unmodified_semantically(self):
        self.assertEqual(hashlib.sha256(__import__("pathlib").Path("cpds_v5_v15_authority_proof_v1.py").read_bytes()).hexdigest(), "960d93b93370d53cb13fcfdef545d45ee9e02260892ec63f563b686b637bc475")


if __name__ == "__main__":
    unittest.main()
