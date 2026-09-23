from __future__ import annotations
import dataclasses
import hashlib
import json
import math
import traceback

import planlatch_v7_9_protocol as p
import planlatch_v7_9_runner as v79
import planlatch_v7_20_controls as c
import planlatch_v7_20_runner as r

PASSED=[]

def h(x:str)->str: return hashlib.sha256(x.encode()).hexdigest()

def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print("PASS", name)
    except Exception:
        print("FAIL", name)
        traceback.print_exc()
        raise

def raises(exc, fn):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"expected {exc.__name__}")

def universe(n=40):
    return [c.UniverseCandidate(f"id-{i:03d}",h(f"body-{i}"),()) for i in range(n)]

def fp(tag="base"):
    return c.ClaimFamilyFingerprint(h("estimand-"+tag),h("universe-"+tag),h("gates-"+tag),h("claim-"+tag))

def runtime(tag="x"):
    return c.RuntimeFingerprint(
        h("container-"+tag),h("tree-"+tag),h("model-"+tag),h("tok-"+tag),
        "host-"+tag,"gpu-uuid-"+tag,"gpu-model","driver","cuda","fw","bfloat16",
        h("flags-"+tag),h("env-"+tag),
    )

def coord(name,value,tainted=False,producer=None):
    pid=producer or c.CANONICAL_PRODUCERS[name]
    return c.CanonicalCoordinate(name,value,pid,c.sha256_json({"producer_id":pid,"version":1}),tainted)

def part(i):
    return "FIT" if i<12 else "PILOT" if i<20 else "SUPPORT" if i<32 else "CROSS_REALIZATION"

def task(i,m0=None,rbit=None,handle=None):
    return r.BaseTaskMetadata(
        handle or f"opaque-{i:03d}", m0 if m0 is not None else f"unique-m0-{i:03d}",
        coord("R",(i%2) if rbit is None else rbit), part(i), "train",
    )


def t_universe():
    xs=universe(38)
    xs.append(c.UniverseCandidate("mirror-000",xs[0].exact_body_sha256,("renamed-000",)))
    xs.append(c.UniverseCandidate("unknown-stuffed",None,("unknown-alias",)))
    rr=c.build_universe_receipt(xs)
    assert len(rr.canonical_entries)==38
    assert {"unknown-stuffed","unknown-alias"} <= set(rr.excluded_unknowns)
    idx=rr.canonical_body_hashes.index(xs[0].exact_body_sha256)
    canon=rr.canonical_entries[idx]
    assert ({"id-000","mirror-000","renamed-000"}-{canon}) <= set(rr.collapsed_aliases[canon])
    raises(c.ControlViolation,lambda:c.build_universe_receipt([xs[0],c.UniverseCandidate("id-000",h("x"))]))

def t_authority():
    led=c.TestOnlyAttemptLedger()
    assert led.register_consumed(fp())==c.AttemptState.CONSUMED_WAITING_BEACON
    raises(c.ControlViolation,lambda:led.register_consumed(fp("again")))
    raises(c.ControlViolation,lambda:led.assert_same_family_nonconfirmatory(fp()))
    led.finalize(c.AttemptState.TERMINAL_NONEXECUTION)
    raises(c.ControlViolation,lambda:led.register_consumed(fp("retry")))
    raises(c.ControlViolation,lambda:c.TestOnlyAttemptLedger(test_only=False).register_consumed(fp()))

def t_receipt():
    u=c.build_universe_receipt(universe(50))
    b=c.OfflineBeaconRecord("test-chain",7,h("rand"),h("proof"),True)
    rr=c.derive_offline_test_receipt(
        family_fingerprint=fp(),executable_freeze_hash=h("exe"),
        runtime_fingerprint=runtime().sha256,universe=u,beacon=b,
    )
    expected_selection_key=hashlib.sha256(
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
    assert rr.selection_key==expected_selection_key
    assert len(rr.selected_identities)==36
    assert c.verify_receipt_immutable(rr)
    assert {k:list(rr.partition_by_identity.values()).count(k) for k,_ in c.PARTITION_COUNTS}==dict(c.PARTITION_COUNTS)
    bad=dict(rr.partition_by_identity); bad[rr.selected_identities[0]]="PILOT"
    raises(c.ControlViolation,lambda:c.verify_receipt_immutable(dataclasses.replace(rr,partition_by_identity=bad)))

def t_runtime():
    x=runtime("a"); assert c.require_exact_runtime(x,x)
    raises(c.ControlViolation,lambda:c.require_exact_runtime(x,runtime("b")))

def cert(**kw):
    z=dict(name="phi",implementation_sha256=h("phi"),input_effects=(c.Effect.CONTENT_DATA,),
           output_effect=c.Effect.SCIENCE_DATA,frozen_formula_id="v79_phi",recursively_verified=True)
    z.update(kw); return c.OperatorCertificate(**z)

def t_effects():
    assert c.verify_whole_program_effects([cert()])
    raises(c.ControlViolation,lambda:c.verify_whole_program_effects([cert(name="opaque",opaque_or_native=True,recursively_verified=False)]))
    raises(c.ControlViolation,lambda:c.verify_whole_program_effects([cert(name="nested",hidden_control_effect=True)]))
    raises(c.ControlViolation,lambda:c.verify_whole_program_effects([cert(name="hard-mask",content_selects_alternative_family=True)]))
    raises(c.ControlViolation,lambda:c.verify_whole_program_effects([cert(name="soft-gate",content_selects_alternative_family=True)]))

def t_selector_source_matrix():
    assert c.verify_scientific_selector_sources(("A","H","R"))
    for source in sorted(c.FORBIDDEN_SELECTOR_SOURCES):
        raises(c.ControlViolation,lambda source=source:c.verify_scientific_selector_sources(("A",source)))

def t_ustar():
    assert c.authenticated_u_star(coord("A",1),coord("H",0),coord("R",1))==(1,0,1)
    raises(c.ControlViolation,lambda:coord("R",1,True))
    fake=coord("R",1,producer="body-hash-derived-R")
    raises(c.ControlViolation,lambda:c.authenticated_u_star(coord("A",1),coord("H",0),fake))

def t_report_handle():
    out=c.total_report_schema({"terminal_state":"FAIL","source_report":{"x":1}})
    assert set(out)==set(c.MANDATORY_REPORT_FIELDS)
    assert out["relay_report"]["value"] is None
    out2=c.gate_status_only_report({"terminal_state":"FAIL"},{"G1":False,"G2":True})
    assert out2["g1_g20"]["status"]=={"G1":False,"G2":True}
    a=c.OpaqueHandle.from_test_token("same"); b=c.OpaqueHandle.from_test_token("same")
    assert a==b
    raises(TypeError,lambda:hash(a))
    raises(TypeError,lambda:a<b)

def t_frame_router():
    xs=[task(i) for i in range(36)]
    a=r.compile_pre_response_frame(xs)
    assert len(a.block_ids)==36 and r.verify_complete_cells(a)
    counts={k:list(a.partition_by_block.values()).count(k) for k in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION")}
    assert counts=={"FIT":12,"PILOT":8,"SUPPORT":12,"CROSS_REALIZATION":4}
    for part in counts:
        us={x.u for x in a.cells if x.partition==part and not x.sham}
        assert us=={(aa,hh,rr) for aa in (0,1) for hh in (0,1) for rr in (0,1)}
    ys=[dataclasses.replace(t,m0=f"different-{i}") for i,t in enumerate(xs)]
    b=r.compile_pre_response_frame(ys)
    assert [x.u for x in a.cells]==[x.u for x in b.cells]
    assert a.frame_hash==b.frame_hash
    assert a.m0_provenance_hash!=b.m0_provenance_hash
    zs=[dataclasses.replace(t,opaque_block_handle=f"RELABEL-{i:03d}") for i,t in enumerate(xs)]
    z=r.compile_pre_response_frame(zs)
    assert a.frame_hash==z.frame_hash and a.binder_hash!=z.binder_hash
    fields={f.name for f in dataclasses.fields(r.BaseTaskMetadata)}
    assert "task_id" not in fields and "never_consumed" not in fields

def t_inherited_science():
    assert r.fit_source_models is v79.fit_source_models
    assert r.score_source_record is v79.score_source_record
    assert r.construct_payload_bank_fit_only is v79.construct_payload_bank_fit_only
    assert r.evaluate_g1_g20 is v79.evaluate_g1_g20
    assert r.protocol_byte_identity(".")
    assert r.MODEL_ID == v79.MODEL_ID
    assert r.MODEL_REVISION == v79.MODEL_REVISION


def t_actual_fit_heldout_constructibility():
    frame=r.compile_pre_response_frame([task(i) for i in range(36)])
    by_part={}
    for part in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION"):
        by_part[part]={x.u for x in frame.cells if x.partition==part and not x.sham}
    expected={(aa,hh,rr) for aa in (0,1) for hh in (0,1) for rr in (0,1)}
    assert by_part["FIT"]==expected
    assert by_part["PILOT"]==expected
    assert by_part["SUPPORT"]==expected
    assert by_part["CROSS_REALIZATION"]==expected
    # This directly closes the v7.9 failure class: every held-out U* has a FIT stratum.
    assert all(by_part[p] <= by_part["FIT"] for p in ("PILOT","SUPPORT","CROSS_REALIZATION"))


for name,fn in [
    ("universe_uniqueness",t_universe),
    ("registration_consumed_authority",t_authority),
    ("offline_exact36_receipt",t_receipt),
    ("exact_runtime",t_runtime),
    ("whole_program_effects",t_effects),
    ("selector_source_matrix",t_selector_source_matrix),
    ("authenticated_ustar",t_ustar),
    ("total_report_and_opaque_handle",t_report_handle),
    ("frame_router_u_star",t_frame_router),
    ("inherited_science_identity",t_inherited_science),
    ("fit_to_heldout_constructibility",t_actual_fit_heldout_constructibility),
]:
    check(name,fn)

summary={"passed":len(PASSED),"tests":PASSED,"scientific_execution_performed":False,"live_membership_draw":False,"live_authority_consumed":False}
print("PLANCARRY_V720_CHECK_SUMMARY",json.dumps(summary,sort_keys=True,separators=(",",":")))
