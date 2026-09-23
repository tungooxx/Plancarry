import json
from pathlib import Path
import planlatch_v7_20_controls as c
import planlatch_v7_20_manifest_builder as b


def test_manifest_builder_is_deterministic_and_pins_v79_bytes(tmp_path):
    root=Path(".")
    a=b.build(root); z=b.build(root)
    assert a==z
    assert a["implementation"]["inherited_v79_science_files"]["planlatch_v7_9_protocol.py"] == "e10db7c0b1552ca56e297ae0b8effe8e05988aad1be5e77ee9c42c534bc8222a"
    assert a["implementation"]["inherited_v79_science_files"]["planlatch_v7_9_runner.py"] == "5e185c990e0f994485ac2d5d0434430d7c8723a09b6eb505a68ec5b41e5ed200"
    assert a["effect"]["whole_program_policy"]["extensional_compute_both_mask_or_soft_gate"]=="FORBIDDEN"
    assert a["effect"]["production_numeric_dependency_certificate"]["status"]=="PENDING_EXACT_RUNTIME_FREEZE"


def test_total_report_schema_manifest_is_total():
    x=b.build(Path("."))["report"]
    assert x["mandatory_fields"]==list(c.MANDATORY_REPORT_FIELDS)
    assert "cannot suppress" in x["gate_policy"]


def test_runtime_template_has_no_host_class_fallback():
    x=b.build(Path("."))["runtime"]
    assert x["status"]=="TEMPLATE_NOT_RESERVED"
    assert x["host_class_fallback"] is False


def test_implementation_tree_binds_fidelity_relevant_bytes():
    import planlatch_v7_20_manifest_builder as mb
    required={
        "planlatch_v7_20_effect_manifest.py",
        "planlatch_v7_20_preflight.py",
        "planlatch_v7_20_manifest_builder.py",
        "planlatch_v7_9_execution_driver.py",
        "tests/test_planlatch_v7_20_effect_manifest.py",
        "tests/run_planlatch_v7_20_checks.py",
    }
    assert required.issubset(set(mb.FILES))
    built=mb.build(Path(__file__).resolve().parents[1])
    assert required.issubset(set(built["implementation"]["files"]))
