import dataclasses
import hashlib

import planlatch_v7_9_protocol as p
import planlatch_v7_9_runner as v79
import planlatch_v7_20_controls as c
import planlatch_v7_20_runner as r


def coord_r(bit):
    pid=c.CANONICAL_PRODUCERS["R"]
    return c.CanonicalCoordinate("R",bit,pid,c.sha256_json({"producer_id":pid,"version":1}))


def part(i):
    return "FIT" if i<12 else "PILOT" if i<20 else "SUPPORT" if i<32 else "CROSS_REALIZATION"

def task(i, *, m0=None, rbit=None, handle=None):
    return r.BaseTaskMetadata(
        handle or f"opaque-{i:03d}", m0 if m0 is not None else f"unique-m0-{i:03d}",
        coord_r((i%2) if rbit is None else rbit), part(i), "train",
    )


def test_exact36_and_u_star_has_all_8_strata_each_partition():
    f=r.compile_pre_response_frame([task(i) for i in range(36)])
    assert len(f.block_ids)==36
    assert list(f.partition_by_block.values()).count("FIT")==12
    assert list(f.partition_by_block.values()).count("PILOT")==8
    assert list(f.partition_by_block.values()).count("SUPPORT")==12
    assert list(f.partition_by_block.values()).count("CROSS_REALIZATION")==4
    assert r.verify_complete_cells(f)
    for part in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION"):
        us={x.u for x in f.cells if x.partition==part and not x.sham}
        assert us == {(a,h,rr) for a in (0,1) for h in (0,1) for rr in (0,1)}


def test_m0_change_cannot_change_science_router_or_frame_hash():
    xs=[task(i) for i in range(36)]
    a=r.compile_pre_response_frame(xs)
    ys=[dataclasses.replace(t,m0="completely-different-"+str(i)) for i,t in enumerate(xs)]
    b=r.compile_pre_response_frame(ys)
    assert [x.u for x in a.cells] == [x.u for x in b.cells]
    assert a.frame_hash == b.frame_hash
    assert a.m0_provenance_hash != b.m0_provenance_hash


def test_r_changes_router_but_requires_canonical_producer():
    xs=[task(i) for i in range(36)]
    a=r.compile_pre_response_frame(xs)
    ys=list(xs); ys[0]=dataclasses.replace(ys[0],r=coord_r(1-xs[0].r.value))
    b=r.compile_pre_response_frame(ys)
    assert a.frame_hash != b.frame_hash
    assert a.frame_hash != b.frame_hash


def test_no_never_consumed_freshness_claim_in_v720_task_contract():
    fields={f.name for f in dataclasses.fields(r.BaseTaskMetadata)}
    assert "opaque_block_handle" in fields and "partition" in fields
    assert "task_id" not in fields and "never_consumed" not in fields


def test_inherited_science_primitive_identity():
    assert r.fit_source_models is v79.fit_source_models
    assert r.score_source_record is v79.score_source_record
    assert r.construct_payload_bank_fit_only is v79.construct_payload_bank_fit_only
    assert r.evaluate_g1_g20 is v79.evaluate_g1_g20
    assert r.protocol_byte_identity(".")


def test_v720_runtime_freeze_declares_only_ustar_and_no_m0_router():
    fr,payload=r.synthetic_runtime_freeze()
    assert payload["factor_contract"]["U*"]=="(A,H,R)"
    assert "provenance-only" in payload["factor_contract"]["M0"]
    assert payload["partition_contract"]["FIT"]==12
    assert payload["partition_contract"]["PILOT"]==8
    assert payload["partition_contract"]["SUPPORT"]==12
    assert payload["partition_contract"]["CROSS_REALIZATION"]==4
    assert payload["partition_contract"]["response_conditioned_replacement"] is False
    assert len(fr.freeze_hash)==64


def test_opaque_handle_relabel_does_not_change_science_frame_hash():
    xs=[task(i) for i in range(36)]
    a=r.compile_pre_response_frame(xs)
    ys=[dataclasses.replace(t,opaque_block_handle=f"RELABEL-{i:03d}") for i,t in enumerate(xs)]
    b=r.compile_pre_response_frame(ys)
    assert a.frame_hash==b.frame_hash
    assert a.binder_hash!=b.binder_hash
    assert [sorted({x.u for x in a.cells if x.partition==p}) for p in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION")] == [sorted({x.u for x in b.cells if x.partition==p}) for p in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION")]
