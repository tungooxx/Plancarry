import dataclasses
import json
from pathlib import Path
import pytest

import planlatch_v7_20_controls as ctl
import planlatch_v7_20_execution_driver as d
import planlatch_v7_20_runner as core


def test_driver_is_bound_to_v720_and_v79_science_bytes_unchanged():
    assert d.DESIGN_ID == ctl.DESIGN_ID
    assert d.SEMANTIC_HASH == ctl.SEMANTIC_HASH
    assert d.ROOT_KIND == "PLANLATCH_V720_SYNTHETIC_INPUT_V1"
    assert d.reviewed_runtime_identity(".")


def test_local_cli_has_no_real_execution_or_live_authority_surface(tmp_path):
    with pytest.raises(d.DriverViolation):
        d.main(["--output", str(tmp_path/"x")])
    src=Path("planlatch_v7_20_execution_driver.py").read_text()
    for forbidden in ("requests", "urllib.request", "drand", "v21_commitment", "public_beacon_records_bind"):
        assert forbidden not in src


def test_synthetic_pipeline_uses_ustar_and_total_report(tmp_path):
    result=d.synthetic_execution(tmp_path/"out")
    assert result["scientific_execution_performed"] is False
    assert result["synthetic_only"] is True
    assert result["g1_g20"]["all_passed"] is True
    assert len(result["g1_g20"]["gates"]) == 20
    assert len(result["source_report"]["constructible_u_deltas"]) == 8
    assert set(result["mandatory_report"]) == set(ctl.MANDATORY_REPORT_FIELDS)
    assert "no global freshness" in result["mandatory_report"]["claim_scope"]


def test_synthetic_root_has_canonical_R_and_no_never_consumed_claim(tmp_path):
    root_path=d._make_synthetic_files(tmp_path/"input")
    raw=json.loads(root_path.read_text())
    assert "freshness_attestation" not in raw
    assert raw["universe_attestation"]["membership_blind_test_fixture"] is True
    for row in raw["tasks"]:
        assert row["r"] in (0,1)
        assert row["r_producer_id"] == ctl.CANONICAL_PRODUCERS["R"]
        assert "never_consumed" not in row
    root=d.load_root_input(root_path)
    frame=core.compile_pre_response_frame(root.tasks)
    for part in d.PARTITIONS:
        us={x.u for x in frame.cells if x.partition==part and not x.sham}
        assert us == {(a,h,r) for a in (0,1) for h in (0,1) for r in (0,1)}


def test_M0_is_provenance_only_in_loaded_frame(tmp_path):
    root_path=d._make_synthetic_files(tmp_path/"input")
    raw=json.loads(root_path.read_text())
    root1=d.load_root_input(root_path)
    f1=core.compile_pre_response_frame(root1.tasks)
    for i,row in enumerate(raw["tasks"]):
        row["m0"]=f"new-provenance-{i}"
    root_path.write_text(json.dumps(raw,sort_keys=True,indent=2)+"\n")
    root2=d.load_root_input(root_path)
    f2=core.compile_pre_response_frame(root2.tasks)
    assert f1.frame_hash == f2.frame_hash
    assert [x.u for x in f1.cells] == [x.u for x in f2.cells]
    assert f1.m0_provenance_hash != f2.m0_provenance_hash
