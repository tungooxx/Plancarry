from __future__ import annotations

import copy
import hashlib
import itertools
import pathlib
import tempfile
import unittest
from unittest import mock

import cpds_development_driver_v1 as drv
import cpds_v5_v15_authority_proof_v1 as v15

ROOT = pathlib.Path(__file__).resolve().parents[1]


def h(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def registry_entries(n: int = 4):
    out = []
    for i in range(n):
        out.append(
            {
                "candidate_id": f"cand-{i:02d}",
                "source_graph_id": f"graph-{i:02d}",
                "structural_key_sha256": h(f"struct-{i}"),
                "static_descriptor_sha256": h(f"desc-{i}"),
                "phase_eligibility": "DEVELOPMENT" if i % 2 == 0 else "CONFIRMATION",
            }
        )
    return out


def equivalence_fields():
    return {
        "checkpoint": v15.CHECKPOINT_SHA256,
        "calibration": v15.CALIBRATION_SHA256,
        "estimand": "finite-33x33-cpds-v15",
        "candidate_cohort_question": "exact-frozen-v15",
        "arms_controls": list(v15.EXACT_ARMS),
        "endpoints": "frozen-v5-endpoints",
        "decision_statistics": "frozen-sign-iut",
        "thresholds": {"n": 33, "k": 22},
        "no_rescue": True,
        "population_definition": "exact-33-development-plus-33-confirmation",
    }


class V15AuthorityProof(unittest.TestCase):
    def test_static_preflight_preserves_science_and_executes_nothing(self):
        out = v15.static_preflight(ROOT)
        self.assertEqual(out["scientific_design_id"], v15.DESIGN_ID)
        self.assertEqual(out["design_semantic_hash"], v15.DESIGN_SEMANTIC_HASH)
        self.assertEqual(out["scientific_result"], "NOT_ASSESSED_PRE_SCIENCE_ONLY")
        self.assertFalse(out["scientific_variable_drift"])
        self.assertEqual(out["protected_science"]["development_n"], 33)
        self.assertEqual(out["protected_science"]["confirmation_n"], 33)
        self.assertEqual(out["protected_science"]["k_positive_required"], 22)
        self.assertEqual(out["protected_science"]["confirmation_status"], "HARD_SEALED_NO_RUNTIME_ROUTE")
        self.assertTrue(all(value == 0 for value in out["execution_counters"].values()))

    def test_uint16_rejection_sampler_is_exact_over_all_words(self):
        proof = v15.exact_sampler_count_proof()
        self.assertEqual(proof, {"accepted": 65520, "rejected": 16, "per_rank_preimages": 91, "rank_count": 720})
        seen = {v15.factoradic_unrank_s6(i) for i in range(720)}
        self.assertEqual(len(seen), 720)
        self.assertTrue(all(set(x) == set(v15.EXACT_ARMS) for x in seen))

    def test_source_contract_rejects_marginal_only_or_dependent_streams(self):
        good = v15.exact_uint16_source_contract()
        self.assertEqual(v15.validate_source_contract(good), good["contract_sha256"])
        for key, bad_value in (
            ("conditional_uniformity", "MARGINAL_UNIFORM_ONLY"),
            ("family_stream_independence", "DEPENDENT"),
            ("source_switching_after_binding", True),
            ("fresh_invocation_on_retry", True),
            ("availability_latency_preview_selection", True),
        ):
            bad = copy.deepcopy(good)
            bad[key] = bad_value
            bad.pop("contract_sha256")
            bad["contract_sha256"] = v15.sha_obj(bad)
            with self.assertRaisesRegex(ValueError, "SOURCE_CONTRACT_SEMANTICS"):
                v15.validate_source_contract(bad)

    def test_preobservation_authority_refuses_source_shopping(self):
        sc = v15.exact_uint16_source_contract()
        authority = v15.EntropySourceAuthority("authority-A", "impl-v1", sc["contract_sha256"], "selector-v1", "invocation-derive-v1", "family-stream-v1", "reject65520-factoradic-v1")
        self.assertEqual(v15.verify_preobservation_binding(authority, observed_source_facts=[]), authority.authority_hash)
        for fact in ("availability", "latency", "preview", "health", "candidate-invocation-metadata"):
            with self.assertRaisesRegex(ValueError, "SOURCE_OBSERVED_BEFORE_BINDING"):
                v15.verify_preobservation_binding(authority, observed_source_facts=[fact])

    def test_exact_33_family_assignment_vector_and_rejection_histories(self):
        source = v15.exact_uint16_source_contract()
        families = [f"f{i:02d}" for i in range(33)]
        streams = {}
        for i, fid in enumerate(families):
            # Some streams exercise 0,1,2 rejected 16-bit words before acceptance.
            streams[fid] = [65535] * (i % 3) + [i * 91]
        rows = v15.build_assignment_vector(family_ids=families, family_stream_words=streams, source_contract=source)
        self.assertEqual(len(rows), 33)
        self.assertEqual([x["family_id"] for x in rows], families)
        self.assertTrue(all(set(x["arm_permutation"]) == set(v15.EXACT_ARMS) for x in rows))
        self.assertEqual({x["consumed_word_count"] for x in rows}, {1, 2, 3})

    def test_transcript_retry_cannot_switch_source_context_or_prefix(self):
        authority_hash, context_root = h("authority"), h("context")
        invocation = v15.derive_invocation_id(authority_hash=authority_hash, consumed_family_id="family-consumed", context_root=context_root)
        t = v15.EntropyTranscript(authority_hash, context_root, invocation).append(65535).append(42)
        self.assertIs(v15.resume_same_transcript(t, authority_hash=authority_hash, context_root=context_root, invocation_id=invocation, replayed_prefix=[65535, 42]), t)
        with self.assertRaisesRegex(ValueError, "RETRY_AUTHORITY_SWITCH"):
            v15.resume_same_transcript(t, authority_hash=h("other"), context_root=context_root, invocation_id=invocation, replayed_prefix=t.words)
        with self.assertRaisesRegex(ValueError, "RETRY_CONTEXT_SWITCH"):
            v15.resume_same_transcript(t, authority_hash=authority_hash, context_root=h("other"), invocation_id=invocation, replayed_prefix=t.words)
        with self.assertRaisesRegex(ValueError, "RETRY_INVOCATION_SWITCH"):
            v15.resume_same_transcript(t, authority_hash=authority_hash, context_root=context_root, invocation_id=h("other"), replayed_prefix=t.words)
        with self.assertRaisesRegex(ValueError, "RETRY_TRANSCRIPT_PREFIX_MISMATCH"):
            v15.resume_same_transcript(t, authority_hash=authority_hash, context_root=context_root, invocation_id=invocation, replayed_prefix=[42])

    def test_registry_three_interpreters_agree_over_admissible_grammar(self):
        contract_hash = v15.registry_interpretation_contract_hash()
        base = registry_entries(5)
        # Exhaust ordering, phase and NFC-equivalent spellings without sampling outcomes.
        for reverse, phase0, unicode_form in itertools.product((False, True), v15.REGISTRY_PHASES, ("NFC", "NFD")):
            rows = copy.deepcopy(base)
            rows[0]["phase_eligibility"] = phase0
            label = "café"
            import unicodedata
            rows[0]["source_graph_id"] = unicodedata.normalize(unicode_form, label)
            raw = v15.registry_bytes(list(reversed(rows)) if reverse else rows)
            interpreted = v15.verify_cross_interpreter_equivalence(raw, contract_hash)
            self.assertEqual(len(interpreted), 5)
        with self.assertRaisesRegex(ValueError, "REGISTRY_CONTRACT_HASH"):
            v15.monitor_interpret_registry(v15.registry_bytes(base), h("changed-parser-contract"))

    def test_registry_root_and_contract_are_jointly_identical(self):
        root = v15.registry_content_root(registry_entries())
        contract = v15.registry_interpretation_contract_hash()
        v15.verify_registry_root_binding(monitor_root=root, selector_root=root, manifest_root=root, monitor_contract_hash=contract, selector_contract_hash=contract, manifest_contract_hash=contract)
        with self.assertRaisesRegex(ValueError, "REGISTRY_ROOT_IDENTITY"):
            v15.verify_registry_root_binding(monitor_root=root, selector_root=h("root-b"), manifest_root=root, monitor_contract_hash=contract, selector_contract_hash=contract, manifest_contract_hash=contract)
        with self.assertRaisesRegex(ValueError, "REGISTRY_CONTRACT_IDENTITY"):
            v15.verify_registry_root_binding(monitor_root=root, selector_root=root, manifest_root=root, monitor_contract_hash=contract, selector_contract_hash=h("parser-b"), manifest_contract_hash=contract)

    def test_finite_program_alias_reset_and_future_alpha_are_refused(self):
        fields = equivalence_fields()
        auth = v15.consume_current_program(equivalence_defining_fields=fields, external_consumption_nonce="external-ledger-record-001")
        v15.validate_same_consumed_program(auth, equivalence_defining_fields=fields)
        for field in fields:
            changed = copy.deepcopy(fields)
            changed[field] = "changed" if not isinstance(changed[field], bool) else not changed[field]
            with self.assertRaisesRegex(ValueError, "CURRENT_PROGRAM_MUTATION_OR_ALIAS_RESET"):
                v15.validate_same_consumed_program(auth, equivalence_defining_fields=changed)
        # RequiredDiscriminator 6947acd4: every V15 status cannot mint fresh alpha.
        for status in ("REJECT", "NONREJECT", "INCONCLUSIVE", "TECHNICAL_INVALID", "TIMEOUT", "OOM", "RELEASE_REFUSED"):
            with self.assertRaisesRegex(ValueError, "V15_FUTURE_PROGRAM_AUTHORITY_NONE"):
                v15.assess_future_study(requests_authority_from_v15=True, conditions_on_v15_status=True, separate_authority_frozen_before_earliest_conditioned_v15_status=False)
        # RequiredDiscriminator 788b38ca: genuinely separate status-independent science may exist, but inherits nothing from V15.
        self.assertEqual(v15.assess_future_study(requests_authority_from_v15=False, conditions_on_v15_status=False, separate_authority_frozen_before_earliest_conditioned_v15_status=False), "SEPARATE_SCIENCE_NO_V15_ALPHA_OR_EVIDENCE")
        with self.assertRaisesRegex(ValueError, "POST_STATUS_SUCCESSOR_RULE_INVALID"):
            v15.assess_future_study(requests_authority_from_v15=False, conditions_on_v15_status=True, separate_authority_frozen_before_earliest_conditioned_v15_status=False)
        self.assertEqual(v15.assess_future_study(requests_authority_from_v15=False, conditions_on_v15_status=True, separate_authority_frozen_before_earliest_conditioned_v15_status=True), "SEPARATE_SCIENCE_NO_V15_ALPHA_OR_EVIDENCE")

    def test_release_admission_requires_full_history_conditional_law(self):
        law = h("exact-full-history-law-proof")
        self.assertEqual(v15.validate_release_event(event_name="prebound-admit", depends_on=[], fixed_before_entropy=True, full_history_conditional_law_proof_sha256=None, expected_conditional_law_proof_sha256=law), "PRE_ENTROPY_FIXED")
        with self.assertRaisesRegex(ValueError, "PREENTROPY_EVENT_RANDOMIZATION_DEPENDENCY"):
            v15.validate_release_event(event_name="fake-prebound", depends_on=["source_latency"], fixed_before_entropy=True, full_history_conditional_law_proof_sha256=None, expected_conditional_law_proof_sha256=law)
        for proxy in ("assignment", "rejection_history", "source_metadata", "source_latency", "source_health", "scientific_outcome"):
            with self.assertRaisesRegex(ValueError, "POSTENTROPY_FULL_HISTORY_LAW_PROOF_REQUIRED"):
                v15.validate_release_event(event_name="post-event", depends_on=[proxy], fixed_before_entropy=False, full_history_conditional_law_proof_sha256=None, expected_conditional_law_proof_sha256=law)
            self.assertEqual(v15.validate_release_event(event_name="post-event", depends_on=[proxy], fixed_before_entropy=False, full_history_conditional_law_proof_sha256=law, expected_conditional_law_proof_sha256=law), "POST_ENTROPY_CONDITIONAL_LAW_PROVED")

    def test_same_verdict_monitor_has_byte_identical_design_visible_release(self):
        pass_rows = {v15.monitor_visible_release("PASS", hidden_witness={"secret": i}, hidden_authenticator=h(str(i))) for i in range(64)}
        fail_rows = {v15.monitor_visible_release("FAIL", hidden_witness={"secret": i}, hidden_authenticator=h(str(i))) for i in range(64)}
        self.assertEqual(len(pass_rows), 1)
        self.assertEqual(len(fail_rows), 1)
        self.assertNotEqual(next(iter(pass_rows)), next(iter(fail_rows)))
        self.assertNotIn(b"secret", next(iter(pass_rows)))

    def test_production_driver_binding_and_fresh_slot_replay_fixture(self):
        proof = v15.verify_production_slot_sutva_binding(ROOT)
        self.assertEqual(proof["driver_sha256"], v15.DEVELOPMENT_DRIVER_SHA256)
        self.assertTrue(proof["fresh_runtime_per_slot"])
        family = {"allowed_pre_reset_history_canonical": ["prep"], "immediate_next_command_canonical": "immediate"}
        witness = {"common_prefix_steps": [{"command": "c1"}, {"command": "c2"}]}
        expected = ["branch-a", "branch-b"]
        instances = []

        class Rec:
            error = None

        class Env:
            def __init__(self):
                self.closed = False
                self.i = 0
                self.admissible_commands = ["prep"]
            def step(self, command):
                if self.closed:
                    raise RuntimeError("REUSED_CLOSED_ENV")
                self.i += 1
                if self.i >= 4:
                    self.admissible_commands = list(expected)
                return Rec()
            def close(self):
                self.closed = True

        def fresh_factory(_):
            env = Env(); instances.append(env); return env

        with mock.patch.object(drv, "_build_symbolic_surface_resolver", side_effect=lambda env: (lambda s: s)), mock.patch.object(drv, "_runtime_surface_command", side_effect=lambda env, resolver, symbolic, code: symbolic):
            rows = [drv._slot_replay_guard(fresh_factory, pathlib.Path("synthetic"), family, witness, expected) for _ in range(6)]
        self.assertEqual(len({id(x) for x in instances}), 6)
        self.assertTrue(all(x.closed for x in instances))
        self.assertEqual(rows, [rows[0]] * 6)

        shared = Env()
        def bad_factory(_): return shared
        with mock.patch.object(drv, "_build_symbolic_surface_resolver", side_effect=lambda env: (lambda s: s)), mock.patch.object(drv, "_runtime_surface_command", side_effect=lambda env, resolver, symbolic, code: symbolic):
            drv._slot_replay_guard(bad_factory, pathlib.Path("synthetic"), family, witness, expected)
            with self.assertRaisesRegex(RuntimeError, "REUSED_CLOSED_ENV"):
                drv._slot_replay_guard(bad_factory, pathlib.Path("synthetic"), family, witness, expected)


    def test_frozen_contract_and_static_audit_self_hashes(self):
        import json
        contract_path = ROOT / "results" / "design" / "plancarry_cpds_v5_v15_authority_proof_contract_v1_20260904.json"
        audit_path = ROOT / "results" / "design" / "plancarry_cpds_v5_v15_authority_proof_static_audit_v1_20260904.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        c = copy.deepcopy(contract); expected_c = c.pop("contract_sha256")
        a = copy.deepcopy(audit); expected_a = a.pop("audit_sha256")
        self.assertEqual(expected_c, v15.sha_obj(c))
        self.assertEqual(expected_a, v15.sha_obj(a))
        self.assertEqual(contract["scientific_design_id"], v15.DESIGN_ID)
        self.assertEqual(contract["design_semantic_hash"], v15.DESIGN_SEMANTIC_HASH)
        self.assertEqual(contract["scientific_result"], "NOT_ASSESSED")
        self.assertFalse(contract["scientific_variable_drift"])
        self.assertEqual(set(contract["verification_obligation_ids"]), {
            "6947acd4-13bb-4dcf-9acf-27413f7adc9b",
            "788b38ca-c0ea-49d0-8cca-8fde83375886",
            "a5252d9b-6791-4449-99c4-c042da79a396",
            "f03183db-e73e-4935-b07f-9163a86566be",
        })
        for rel, sha in contract["implementation_files_sha256"].items():
            self.assertEqual(v15.sha_file(ROOT / rel), sha)
        self.assertEqual(audit["contract_file_sha256"], v15.sha_file(contract_path))
        self.assertTrue(all(value == 0 for value in audit["execution_counters"].values()))


if __name__ == "__main__":
    unittest.main()
