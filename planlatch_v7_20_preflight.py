"""Stdlib-only deterministic PRE_SCIENCE preflight for PlanLatch v7.20.

This intentionally does not execute model/decoder science.  NumPy-dependent
inherited decoder canaries remain a separate runtime preflight obligation.
"""
from __future__ import annotations
import dataclasses
import hashlib
import importlib.util
import json
from pathlib import Path

import planlatch_v7_20_controls as ctl
import planlatch_v7_20_effect_manifest as eff
import planlatch_v7_20_runner as runner

ROOT=Path(__file__).resolve().parent
FILES=(
    "planlatch_v7_9_protocol.py",
    "planlatch_v7_9_runner.py",
    "planlatch_v7_9_model_runtime.py",
    "planlatch_v7_9_execution_driver.py",
    "planlatch_v7_20_controls.py",
    "planlatch_v7_20_runner.py",
    "planlatch_v7_20_execution_driver.py",
    "planlatch_v7_20_effect_manifest.py",
    "planlatch_v7_20_preflight.py",
    "planlatch_v7_20_manifest_builder.py",
    "tests/run_planlatch_v7_20_checks.py",
    "tests/test_planlatch_v7_20_controls.py",
    "tests/test_planlatch_v7_20_runner.py",
    "tests/test_planlatch_v7_20_execution_driver.py",
    "tests/test_planlatch_v7_20_manifests.py",
    "tests/test_planlatch_v7_20_effect_manifest.py",
    "tests/test_planlatch_v7_9_protocol.py",
    "tests/test_planlatch_v7_9_runner.py",
    "tests/test_planlatch_v7_9_execution_driver.py",
    "tests/test_planlatch_v7_9_model_runtime.py",
    "v720_test_requirements.txt",
)

def sha_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda:fh.read(1<<20),b""): h.update(chunk)
    return h.hexdigest()

def tree_fingerprint()->str:
    return ctl.sha256_json({name:sha_file(ROOT/name) for name in sorted(FILES)})

def run()->dict:
    effect=eff.verify_default_manifest()
    # Control/router compile is stdlib-only and must not import model runtimes.
    assert runner.DESIGN_ID==ctl.DESIGN_ID
    assert runner.SEMANTIC_HASH==ctl.SEMANTIC_HASH
    assert runner.fit_source_models.__module__=="planlatch_v7_9_runner"
    assert runner.score_source_record.__module__=="planlatch_v7_9_runner"
    assert runner.construct_payload_bank_fit_only.__module__=="planlatch_v7_9_runner"
    numpy_available=importlib.util.find_spec("numpy") is not None
    pytest_available=importlib.util.find_spec("pytest") is not None
    return {
        "design_id":ctl.DESIGN_ID,
        "semantic_hash":ctl.SEMANTIC_HASH,
        "implementation_fingerprint":tree_fingerprint(),
        "files":{name:sha_file(ROOT/name) for name in sorted(FILES)},
        "effect_manifest_operator_count":len(effect["operators"]),
        "effect_manifest_status":"PASS",
        "unknown_opaque_native_callbacks":"FAIL_CLOSED",
        "extensional_content_selection":"FORBIDDEN",
        "scientific_execution_performed":False,
        "live_membership_draw":False,
        "live_authority_consumed":False,
        "selected_body_access":False,
        "numpy_available":numpy_available,
        "pytest_available":pytest_available,
        "inherited_decoder_runtime_preflight":"READY" if numpy_available else "BLOCKED_MISSING_NUMPY_ENVIRONMENT",
    }

if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,separators=(",",":")))
