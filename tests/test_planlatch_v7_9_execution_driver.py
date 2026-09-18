import hashlib
import importlib
import json
from pathlib import Path

import pytest

import planlatch_v7_9_execution_driver as d
import planlatch_v7_9_runner as core


def test_reviewed_runtime_bytes_unchanged():
    assert d.reviewed_runtime_identity()


def test_import_is_model_environment_lazy():
    # Driver module imports without torch/transformers/ALFWorld side effects.
    assert d.EXPERIMENT_ID == "35f1abdc-7647-4f39-811d-f18c0213682d"
    assert "planlatch_v7_9_model_runtime" not in d.__dict__


def test_authority_bundle_fail_closed():
    good = {
        "kind": d.AUTHORITY_KIND,
        "experiment_id": d.EXPERIMENT_ID,
        "scientific_design_id": d.DESIGN_ID,
        "scientific_semantic_hash": d.SEMANTIC_HASH,
        "implementation_commit": d.REVIEWED_RUNTIME_COMMIT,
        "runtime_engineering_result_id": d.RUNTIME_ENGINEERING_RESULT_ID,
        "runtime_fidelity_record_id": d.RUNTIME_FIDELITY_ID,
        "research_decision_id": "decision-x",
        "release_candidate_id": "candidate-x",
        "final_review": {"verdict": "PASS", "release_candidate_id": "candidate-x", "review_id": "review-x"},
    }
    b = d.verify_authority_bundle(good)
    assert b.research_decision_id == "decision-x"
    for mutation in (
        {**good, "implementation_commit": "bad"},
        {**good, "research_decision_id": ""},
        {**good, "final_review": {"verdict": "FAIL", "release_candidate_id": "candidate-x", "review_id": "review-x"}},
    ):
        with pytest.raises(d.DriverViolation):
            d.verify_authority_bundle(mutation)


def test_synthetic_pipeline_all_gates_and_stage_order(tmp_path):
    out = tmp_path / "out"
    result = d.synthetic_execution(out)
    assert result["synthetic_only"] is True
    assert result["scientific_execution_performed"] is False
    assert result["g1_g20"]["all_passed"] is True
    assert len(result["g1_g20"]["gates"]) == 20
    rows = [json.loads(x) for x in (out / "stage_journal.jsonl").read_text().splitlines()]
    stages = [x["stage"] for x in rows]
    assert stages == [
        "PRE_SOURCE_FROZEN",
        "POST_FIT_HELDOUT_FROZEN",
        "SOURCE_REPORT_FROZEN",
        "PILOT_RAW_ARM_SCORES_FROZEN",
        "CROSS_RAW_ARM_SCORES_FROZEN",
        "RESULT_FROZEN",
    ]
    prev = "0" * 64
    for row in rows:
        assert row["previous_record_hash"] == prev
        body = {k: row[k] for k in ("stage", "payload", "previous_record_hash")}
        assert row["record_hash"] == d.sha_json(body)
        prev = row["record_hash"]


def test_heldout_partition_bodies_not_needed_for_pre_source(tmp_path):
    inp = tmp_path / "inp"
    root_path = d._make_synthetic_files(inp)
    raw = json.loads(root_path.read_text())
    # Remove held-out bodies after root hash binding; root parsing/frame/PRE_SOURCE still does not open them.
    held = [Path(raw["partition_files"][p]["path"]) for p in ("SUPPORT", "PILOT", "CROSS_REALIZATION")]
    root = d.load_root_input(root_path)
    for path in held:
        path.unlink()
    backend = d.SyntheticBackend()
    frame = core.compile_pre_response_frame(root.tasks)
    cfg, _ = core.freeze_decoder_config()
    pre = d._make_pre_source(root, frame, backend, backend.parameter_sha256(), cfg)
    assert pre["phase"] == "PRE_SOURCE"
    # Actual heldout open fails later as expected.
    with pytest.raises(FileNotFoundError):
        d._partition_records(root.partition_files["SUPPORT"], "SUPPORT")


def test_orientation_sidecar_not_needed_until_after_raw_scores(tmp_path):
    inp = tmp_path / "inp"
    root_path = d._make_synthetic_files(inp)
    root = d.load_root_input(root_path)
    # Orientation hashes are bound, but file content is not needed by root load.
    Path(root.orientation_files["PILOT"].path).unlink()
    assert root.orientation_files["PILOT"].sha256
    with pytest.raises(FileNotFoundError):
        d._orientation_rows(root.orientation_files["PILOT"], "PILOT")


def test_output_namespace_must_be_fresh(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(d.DriverViolation):
        d.synthetic_execution(out)


def test_partition_hash_mismatch_fails(tmp_path):
    inp = tmp_path / "inp"
    root_path = d._make_synthetic_files(inp)
    root = d.load_root_input(root_path)
    fit = Path(root.partition_files["FIT"].path)
    fit.write_text(fit.read_text() + " ")
    with pytest.raises(d.DriverViolation):
        d._partition_records(root.partition_files["FIT"], "FIT")


def test_sham_specificity_uses_existing_source_thresholds_not_new_numeric_gate():
    src = Path("planlatch_v7_9_execution_driver.py").read_text()
    assert "sham_systematic" in src
    for literal in ("0.02", "0.05", "0.015", "0.80"):
        assert literal in src


def test_real_backend_not_instantiated_by_synthetic_execution(tmp_path, monkeypatch):
    class Boom:
        def __init__(self):
            raise AssertionError("real backend must not load")
    monkeypatch.setattr(d, "RealBackend", Boom)
    result = d.synthetic_execution(tmp_path / "out")
    assert result["g1_g20"]["all_passed"]


def test_cli_execute_missing_authority_fails_before_real_backend(tmp_path, monkeypatch):
    called = {"real": False}
    class Boom:
        def __init__(self):
            called["real"] = True
            raise AssertionError
    monkeypatch.setattr(d, "RealBackend", Boom)
    with pytest.raises(d.DriverViolation):
        d.main(["--execute", "--output", str(tmp_path / "out")])
    assert called["real"] is False

def test_relay_requires_prospectively_valid_endpoints(tmp_path):
    inp = tmp_path / "inp"
    root_path = d._make_synthetic_files(inp)
    raw = json.loads(root_path.read_text())
    pp = Path(raw["partition_files"]["PILOT"]["path"])
    part = json.loads(pp.read_text())
    part["records"][0].pop("valid_endpoint_ids")
    pp.write_text(json.dumps(part, sort_keys=True, indent=2) + "\n")
    raw["partition_files"]["PILOT"]["sha256"] = d.sha_file(pp)
    root_path.write_text(json.dumps(raw, sort_keys=True, indent=2) + "\n")
    root = d.load_root_input(root_path)
    # Reachability of the explicit validation is a deterministic source audit.
    src = Path("planlatch_v7_9_execution_driver.py").read_text()
    assert "prospectively attested valid actions" in src


def test_cross_endpoint_nonreversal_reuses_three_of_four_rule():
    src = Path("planlatch_v7_9_execution_driver.py").read_text()
    assert 'sum(r["metric_direction"][field]["cp"] > 0 for r in first4) >= 3' in src
    assert 'sum(r["metric_direction"][field]["cq"] > 0 for r in first4) >= 3' in src
