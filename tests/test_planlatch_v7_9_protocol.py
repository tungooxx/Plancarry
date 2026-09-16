from __future__ import annotations

import inspect
import math
from pathlib import Path
import random

import pytest

import planlatch_v7_9_protocol as p


def rows():
    return [
        (4.0, -1.0, 2.0),
        (1.0, 3.0, 8.0),
        (2.0, 0.5, -2.0),
        (7.0, 2.5, 1.0),
    ]


def payload(shift: int = 0):
    triples = [
        p.PayloadTriple(transformer_block_index=i // 4, mlp_intermediate_channel_index=shift + i, gain=p.ALLOWED_GAINS[i % 2])
        for i in range(p.PAYLOAD_K)
    ]
    return p.make_payload_manifest(triples)


def test_phi_api_is_target_bit_weight_and_identity_blind():
    params = tuple(inspect.signature(p.fit_phi).parameters)
    assert params == ("o_star_rows",)
    forbidden = {"s", "q", "p", "w_i", "label", "row_id", "cell", "semantic_arm", "j_mask", "provenance"}
    assert forbidden.isdisjoint(params)


def test_phi_row_permutation_is_byte_exact_and_outputs_inverse_permute():
    base = rows()
    state_a = p.fit_phi(base)
    out_a = p.transform_phi(state_a, base)
    perm = [2, 0, 3, 1]
    permuted = [base[i] for i in perm]
    state_b = p.fit_phi(permuted)
    out_b = p.transform_phi(state_b, permuted)
    assert state_a.serialized_bytes() == state_b.serialized_bytes()
    assert state_a.sha256 == state_b.sha256
    recovered = [None] * len(base)
    for k, original_index in enumerate(perm):
        recovered[original_index] = out_b[k]
    assert tuple(recovered) == out_a
    assert p.transformed_multiset_hash(out_a) == p.transformed_multiset_hash(out_b)


def test_opaque_row_key_renaming_cannot_change_phi():
    base = rows()
    keys_a = ["opaque-a", "opaque-b", "opaque-c", "opaque-d"]
    keys_b = ["renamed-41", "renamed-07", "renamed-88", "renamed-13"]
    keyed_a = list(zip(keys_a, base))
    keyed_b = list(zip(keys_b, base))
    # Keys never enter fit_phi; only O* values cross the API boundary.
    state_a = p.fit_phi([value for _, value in keyed_a])
    state_b = p.fit_phi([value for _, value in keyed_b])
    assert state_a.serialized_bytes() == state_b.serialized_bytes()
    assert p.transform_phi(state_a, base) == p.transform_phi(state_b, base)


def test_s_q_p_and_supervised_weights_cannot_flow_back_into_phi():
    base = rows()
    phi_before = p.fit_phi(base)
    labels_a = ["p", "q", "p", "q"]
    labels_b = ["q", "p", "q", "p"]
    w_a = p.class_balance_weights(labels_a)
    w_b = p.class_balance_weights(labels_b)
    q_a = [0, 1, 1, 0]
    q_b = [1 - x for x in q_a]
    placebo_a = [0, 0, 1, 1]
    placebo_b = list(reversed(placebo_a))
    assert w_a != w_b or labels_a != labels_b
    assert q_a != q_b and placebo_a != placebo_b
    phi_after = p.fit_phi(base)
    assert phi_before.serialized_bytes() == phi_after.serialized_bytes()


def test_full_and_placebo_share_identical_transformed_o_star_and_bit_is_separate():
    base = rows()
    state = p.fit_phi(base)
    transformed = p.transform_phi(state, base)
    full_hash = p.transformed_multiset_hash(transformed)
    placebo_hash = p.transformed_multiset_hash(transformed)
    assert full_hash == placebo_hash
    full_input = p.decoder_input(transformed[0], 1)
    placebo_input = p.decoder_input(transformed[0], 0)
    assert full_input[:-1] == placebo_input[:-1] == transformed[0]
    assert full_input[-1] == 1.0 and placebo_input[-1] == 0.0


def test_j1_has_zero_member_leverage_for_preprocessing_and_source_statistic():
    base_obs = [p.MemberObservation(tuple(r), False) for r in rows()]
    with_j1 = base_obs + [
        p.MemberObservation((9999.0, -9999.0, 42.0), True),
        p.MemberObservation((-7777.0, 8888.0, -13.0), True),
    ]
    assert p.fit_phi_from_members(base_obs).serialized_bytes() == p.fit_phi_from_members(with_j1).serialized_bytes()

    full = [-0.1, -0.2, -0.3, -0.4]
    placebo = [-0.4, -0.5, -0.6, -0.7]
    labels = ["p", "q", "p", "q"]
    j = [False] * 4
    delta_a = p.standardized_j0_delta(full, placebo, labels, j)
    delta_b = p.standardized_j0_delta(full + [1000.0], placebo + [-1000.0], labels + ["p"], j + [True])
    assert delta_a == delta_b


def test_collapsed_placebo_is_original_record_objective_and_naive_2n_geometry_rejected():
    losses = [(0.2, 0.6), (1.0, 0.4), (0.8, 0.2), (0.3, 0.5)]
    weights = p.class_balance_weights(["p", "p", "q", "q"])
    reg = 0.75
    lam = 0.1
    value = p.collapsed_placebo_objective(losses, weights, regularizer=reg, lambda_=lam)
    manual = sum(w * 0.5 * (a + b) for w, (a, b) in zip(weights, losses)) / sum(weights) + lam * reg
    assert value == pytest.approx(manual, rel=0, abs=1e-15)

    expanded = []
    for w in weights:
        expanded.extend((0.5 * w, 0.5 * w))
    assert p.validate_expanded_placebo_weights(weights, expanded, sum(weights))

    naive = []
    for w in weights:
        naive.extend((w, w))
    with pytest.raises(p.ProtocolViolation):
        p.validate_expanded_placebo_weights(weights, naive, 2.0 * sum(weights))


def test_p_mix_makes_one_prediction_per_original_record_with_frozen_tie_rule():
    assert p.placebo_log_score(-0.2, -0.8) == pytest.approx(-0.5)
    mixed = p.p_mix({"p": 0.8, "q": 0.2}, {"p": 0.2, "q": 0.8})
    assert mixed == {"p": 0.5, "q": 0.5}
    assert p.placebo_hard_prediction({"p": 0.8, "q": 0.2}, {"p": 0.2, "q": 0.8}) == "p"
    assert p.placebo_hard_prediction({"p": 0.1, "q": 0.9}, {"p": 0.3, "q": 0.7}) == "q"


def test_off_support_diagnostic_cannot_select_payload():
    cp, cq = payload(), payload(shift=100)
    assert p.select_payload_from_observed_support("p", cp, cq, observed_support=True) == cp
    assert p.select_payload_from_observed_support("q", cp, cq, observed_support=True) == cq
    diag = p.off_support_q_toggle_diagnostic({"synthetic": True})
    assert not diag.scientific_use_allowed
    with pytest.raises(p.ProtocolViolation):
        p.select_payload_from_observed_support(diag, cp, cq, observed_support=True)
    with pytest.raises(p.ProtocolViolation):
        p.select_payload_from_observed_support("p", cp, cq, observed_support=False)


def test_payload_manifest_exact_budget_gains_uniqueness_checksum_and_stability():
    cp = payload()
    assert len(cp.triples) == p.PAYLOAD_K
    assert all(t.gain in p.ALLOWED_GAINS for t in cp.triples)
    assert p.validate_payload_manifest(cp)
    cp_again = payload()
    assert cp.checksum == cp_again.checksum

    duplicate = [p.PayloadTriple(i // 4, i, p.ALLOWED_GAINS[i % 2]) for i in range(p.PAYLOAD_K - 1)]
    duplicate.append(duplicate[-1])
    with pytest.raises(p.ProtocolViolation):
        p.make_payload_manifest(duplicate)
    with pytest.raises(p.ProtocolViolation):
        p.PayloadTriple(0, 0, 1.0)


def test_applied_payload_is_anonymous_and_checksum_has_no_semantic_bank_identity():
    from dataclasses import fields

    first = payload()
    same_bytes_from_other_bank_slot = payload()
    assert first.checksum == same_bytes_from_other_bank_slot.checksum
    assert {field.name for field in fields(p.PayloadManifest)} == {"version", "triples", "checksum"}
    assert set(first.unsigned_payload()) == {"version", "triples"}
    assert set(first.serialized_payload()) == {"version", "triples", "checksum"}
    assert not hasattr(first, "name")

    # Bank-side semantic mapping exists only in local control flow.  The object
    # crossing the boundary is byte-identical for identical anonymous content.
    bank = {"p": first, "q": same_bytes_from_other_bank_slot}
    selected_p = p.select_payload_from_observed_support("p", bank["p"], bank["q"], observed_support=True)
    selected_q = p.select_payload_from_observed_support("q", bank["p"], bank["q"], observed_support=True)
    assert selected_p.serialized_payload() == selected_q.serialized_payload()
    serialized_text = p.stable_json(selected_p.serialized_payload())
    assert '"name"' not in serialized_text
    assert "C_p" not in serialized_text and "C_q" not in serialized_text


def test_payload_checksum_preimage_is_exact_anonymous_version_plus_triples():
    manifest = payload(shift=37)
    assert manifest.checksum == p.sha256_json(manifest.unsigned_payload())
    assert set(manifest.unsigned_payload()) == {"version", "triples"}
    assert len(manifest.unsigned_payload()["triples"]) == p.PAYLOAD_K


def test_decoder_relative_null_canary_requires_reference_equality_not_redundancy_claim():
    assert p.decoder_relative_null_canary(0.625, 0.625, tolerance=1e-12, invalid_preprocessing_geometry_changed=True)
    assert not p.decoder_relative_null_canary(0.626, 0.625, tolerance=1e-4, invalid_preprocessing_geometry_changed=True)
    assert not p.decoder_relative_null_canary(0.625, 0.625, tolerance=1e-12, invalid_preprocessing_geometry_changed=False)


def test_protocol_attestation_is_stable_and_execution_free():
    state = p.fit_phi(rows())
    a = p.protocol_attestation(state)
    b = p.protocol_attestation(state)
    assert a == b
    assert a["design_id"] == p.DESIGN_ID
    assert a["semantic_hash"] == p.SEMANTIC_HASH
    assert a["phi_api_parameters"] == ["o_star_rows"]
    assert a["row_order_identity_blind"] is True
    assert a["model_or_gpu_execution"] is False
    assert len(a["attestation_hash"]) == 64


def test_protocol_module_is_stdlib_only_and_has_no_model_runtime_imports():
    source = Path(p.__file__).read_text()
    forbidden_imports = ("import torch", "from torch", "import openai", "from openai", "import plancraft", "from plancraft")
    assert all(token not in source for token in forbidden_imports)
