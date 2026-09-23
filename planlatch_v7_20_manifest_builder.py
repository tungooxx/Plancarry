"""Deterministic v7.20 implementation-manifest builder; no science execution."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

import planlatch_v7_9_protocol as p79
import planlatch_v7_9_runner as r79
import planlatch_v7_20_controls as ctl
import planlatch_v7_20_effect_manifest as eff
import planlatch_v7_20_runner as r20

FILES = (
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

def stable(v:Any)->str:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)

def sha_bytes(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()

def sha_file(p:Path)->str:
    return sha_bytes(p.read_bytes())


def build(root:Path)->dict[str,Any]:
    files={name:sha_file(root/name) for name in FILES}
    effect=dict(eff.verify_default_manifest(root))
    effect["files"]=files
    effect["whole_program_policy"]={
        "unknown_opaque_native_callback_plugin_reflection_dynamic_import":"FAIL_CLOSED",
        "unknown_source_control_or_selection":"FAIL_CLOSED",
        "extensional_compute_both_mask_or_soft_gate":"FORBIDDEN",
        "Ustar_only_router":"authenticated A,H,R",
        "terminal_gates":"status-only/no-feedback",
    }
    report={
        "version":"planlatch-v7.20-total-report-schema-v1",
        "mandatory_fields":list(ctl.MANDATORY_REPORT_FIELDS),
        "terminal_missing_value":{"value":None,"reason":"NA_NOT_AVAILABLE_IN_TERMINAL_STATE"},
        "gate_policy":"G1-G20 populate status only; cannot suppress fields or select claim variants",
    }
    runtime={
        "version":"planlatch-v7.20-exact-runtime-template-v1",
        "status":"TEMPLATE_NOT_RESERVED",
        "required_fields":[f.name for f in __import__("dataclasses").fields(ctl.RuntimeFingerprint)],
        "host_class_fallback":False,
        "unavailable_after_registration":"TERMINAL_NONEXECUTION_AUTHORITY_REMAINS_CONSUMED",
    }
    implementation={
        "version":"planlatch-v7.20-implementation-manifest-v1",
        "design_id":ctl.DESIGN_ID,
        "semantic_hash":ctl.SEMANTIC_HASH,
        "files":files,
        "inherited_v79_science_files":{k:v for k,v in files.items() if "v7_9" in k},
        "additive_v720_files":{k:v for k,v in files.items() if "v7_20" in k},
        "no_live_membership_draw":True,
        "no_live_authority_consumption":True,
        "no_selected_body_access":True,
        "no_model_science_execution":True,
        "no_paid_gpu":True,
    }
    implementation["tree_sha256"]=sha_bytes(stable(implementation["files"]).encode())
    return {"effect":effect,"report":report,"runtime":runtime,"implementation":implementation}


def main()->None:
    root=Path(__file__).resolve().parent
    built=build(root)
    names={
        "effect":"V720_EFFECT_MANIFEST.json",
        "report":"V720_REPORT_SCHEMA.json",
        "runtime":"V720_RUNTIME_MANIFEST_TEMPLATE.json",
        "implementation":"V720_IMPLEMENTATION_MANIFEST.json",
    }
    for key,name in names.items():
        (root/name).write_text(json.dumps(built[key],sort_keys=True,indent=2)+"\n")
    print(stable({k:sha_file(root/name) for k,name in names.items()}))
    print("tree_sha256",built["implementation"]["tree_sha256"])

if __name__=="__main__":
    main()
