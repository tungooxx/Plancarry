import dataclasses
import hashlib
import pytest

import planlatch_v7_20_controls as c


def h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


def universe(n=40):
    return [
        c.UniverseCandidate(f"id-{i:03d}", h(f"body-{i}"), ())
        for i in range(n)
    ]


def fp(tag="base"):
    return c.ClaimFamilyFingerprint(h("estimand-"+tag), h("universe-"+tag), h("gates-"+tag), h("claim-"+tag))


def runtime(tag="x"):
    return c.RuntimeFingerprint(
        h("container-"+tag), h("tree-"+tag), h("model-"+tag), h("tok-"+tag),
        "host-"+tag, "gpu-uuid-"+tag, "gpu-model", "driver", "cuda", "fw", "bfloat16",
        h("flags-"+tag), h("env-"+tag),
    )


def test_universe_eq_alias_collapse_and_unknown_fail_closed():
    xs = universe(38)
    # Exact mirror of id-000 must not get a second ticket.
    xs.append(c.UniverseCandidate("mirror-000", xs[0].exact_body_sha256, ("renamed-000",)))
    xs.append(c.UniverseCandidate("unknown-stuffed", None, ("unknown-alias",)))
    r = c.build_universe_receipt(xs)
    assert len(r.canonical_entries) == 38
    assert "unknown-stuffed" in r.excluded_unknowns and "unknown-alias" in r.excluded_unknowns
    canonical_for_body0 = r.canonical_entries[r.canonical_body_hashes.index(xs[0].exact_body_sha256)]
    aliases = set(r.collapsed_aliases[canonical_for_body0])
    assert {"id-000", "mirror-000", "renamed-000"} - {canonical_for_body0} <= aliases


def test_duplicate_identity_rejected():
    xs = universe(2)
    xs.append(c.UniverseCandidate("id-000", h("different")))
    with pytest.raises(c.ControlViolation):
        c.build_universe_receipt(xs)


def test_registration_consumes_immediately_and_redraw_fails():
    led = c.TestOnlyAttemptLedger()
    assert led.register_consumed(fp()) == c.AttemptState.CONSUMED_WAITING_BEACON
    with pytest.raises(c.ControlViolation):
        led.register_consumed(fp("again"))
    with pytest.raises(c.ControlViolation):
        led.assert_same_family_nonconfirmatory(fp())
    led.finalize(c.AttemptState.TERMINAL_NONEXECUTION)
    with pytest.raises(c.ControlViolation):
        led.register_consumed(fp("retry"))


def test_live_authority_surface_is_disabled():
    led = c.TestOnlyAttemptLedger(test_only=False)
    with pytest.raises(c.ControlViolation):
        led.register_consumed(fp())


def test_offline_one_shot_receipt_exact36_counts_and_tamper_rejects():
    u = c.build_universe_receipt(universe(50))
    b = c.OfflineBeaconRecord("test-chain", 7, h("rand"), h("proof"), True)
    r = c.derive_offline_test_receipt(
        family_fingerprint=fp(), executable_freeze_hash=h("exe"),
        runtime_fingerprint=runtime().sha256, universe=u, beacon=b,
    )
    expected_selection_key = hashlib.sha256(
        (
            "PlanLatch-v7.18"
            + fp().sha256
            + c.SEMANTIC_HASH
            + h("exe")
            + runtime().sha256
            + u.ordered_universe_hash
            + h("rand")
        ).encode("utf-8")
    ).hexdigest()
    assert r.selection_key == expected_selection_key
    assert len(r.selected_identities) == 36
    assert c.verify_receipt_immutable(r)
    assert {k: list(r.partition_by_identity.values()).count(k) for k, _ in c.PARTITION_COUNTS} == dict(c.PARTITION_COUNTS)
    bad_map = dict(r.partition_by_identity)
    first = r.selected_identities[0]
    bad_map[first] = "PILOT"
    bad = dataclasses.replace(r, partition_by_identity=bad_map)
    with pytest.raises(c.ControlViolation):
        c.verify_receipt_immutable(bad)


def test_exact_runtime_substitution_rejected():
    x = runtime("a")
    assert c.require_exact_runtime(x, x)
    with pytest.raises(c.ControlViolation):
        c.require_exact_runtime(x, runtime("b"))


def cert(**kw):
    base = dict(
        name="phi", implementation_sha256=h("phi"), input_effects=(c.Effect.CONTENT_DATA,),
        output_effect=c.Effect.SCIENCE_DATA, frozen_formula_id="v79_phi",
        recursively_verified=True,
    )
    base.update(kw)
    return c.OperatorCertificate(**base)


def test_whole_program_effect_positive_and_opaque_nested_control_reject():
    assert c.verify_whole_program_effects([cert()])
    with pytest.raises(c.ControlViolation):
        c.verify_whole_program_effects([cert(name="opaque", opaque_or_native=True, recursively_verified=False)])
    with pytest.raises(c.ControlViolation):
        c.verify_whole_program_effects([cert(name="nested", hidden_control_effect=True)])


def test_compute_both_and_mask_and_soft_gating_reject():
    for name in ("hard-mask", "soft-gate"):
        with pytest.raises(c.ControlViolation):
            c.verify_whole_program_effects([cert(name=name, content_selects_alternative_family=True)])


def coord(name, value, *, tainted=False, producer=None):
    pid = producer or c.CANONICAL_PRODUCERS[name]
    return c.CanonicalCoordinate(name, value, pid, c.sha256_json({"producer_id": pid, "version": 1}), tainted)


def test_authenticated_ustar_and_laundering_reject():
    assert c.authenticated_u_star(coord("A",1),coord("H",0),coord("R",1)) == (1,0,1)
    with pytest.raises(c.ControlViolation):
        coord("R", 1, tainted=True)
    fake = coord("R",1,producer="body-hash-derived-R")
    with pytest.raises(c.ControlViolation):
        c.authenticated_u_star(coord("A",1),coord("H",0),fake)


def test_opaque_handle_equality_only():
    a=c.OpaqueHandle.from_test_token("same")
    b=c.OpaqueHandle.from_test_token("same")
    assert a == b
    with pytest.raises(TypeError): hash(a)
    with pytest.raises(TypeError): a < b


def test_total_report_never_suppresses_fields():
    out = c.total_report_schema({"terminal_state":"FAIL","source_report":{"x":1}})
    assert set(out) == set(c.MANDATORY_REPORT_FIELDS)
    assert out["source_report"] == {"x":1}
    assert out["relay_report"]["value"] is None
    out2 = c.gate_status_only_report({"terminal_state":"FAIL"}, {"G1":False,"G2":True})
    assert set(out2) == set(c.MANDATORY_REPORT_FIELDS)
    assert out2["g1_g20"]["status"] == {"G1":False,"G2":True}


def test_explicit_forbidden_selector_source_matrix():
    assert c.verify_scientific_selector_sources(("A","H","R"))
    for source in sorted(c.FORBIDDEN_SELECTOR_SOURCES):
        with pytest.raises(c.ControlViolation):
            c.verify_scientific_selector_sources(("A",source))
