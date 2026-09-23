from pathlib import Path
import tempfile

import pytest

import planlatch_v7_20_effect_manifest as e


def scan(src: str) -> bool:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "poison.py"
        p.write_text(src)
        return e.static_fail_closed_scan(p)


def rejected(src: str) -> None:
    with pytest.raises(e.EffectManifestViolation):
        scan(src)


def test_exact_audited_manifest_passes():
    m = e.verify_default_manifest()
    assert m["certification_mode"].startswith("EXACT_BYTE_SEMANTIC_WHITELIST")
    assert len(m["operators"]) == 11
    assert m["unknown_opaque_native_callbacks"] == "FAIL_CLOSED"


def test_safe_unknown_fixed_numeric_dataflow_passes():
    assert scan("def f(x, y):\n    z = x * 2.0 + y\n    return z\n")


@pytest.mark.parametrize("src", [
    # A2 direct hidden branch.
    "def f(o, bank0, bank1):\n    if o[0] > 0:\n        return bank1\n    return bank0\n",
    # A2 branchless soft gate.
    "def f(o, y0, y1, sigmoid):\n    w = sigmoid(o)\n    return w*y1 + (1-w)*y0\n",
    # Hard mask / compute-both-and-select.
    "def f(o, y0, y1):\n    w = o > 0\n    return w*y1 + (1-w)*y0\n",
    # A2 content-derived RNG seed.
    "def f(o, random):\n    random.seed(o)\n    return 1\n",
    # A2 content-keyed cache.
    "def f(o, cache):\n    return cache[o]\n",
    # A2 content-dependent early exit.
    "def f(o):\n    if o:\n        return 0\n    return 1\n",
    # argmax/top-k module selection.
    "def f(o, modules, argmax):\n    return modules[argmax(o)]\n",
    "def f(o, topk):\n    return topk(o, 1)\n",
    # fallback path.
    "def f(o, fallback):\n    return fallback(o)\n",
    # dynamic threshold/payload/aggregation/report family lookup.
    "def f(i, thresholds):\n    return thresholds[i]\n",
    "def f(i, payloads):\n    return payloads[i]\n",
    "def f(i, aggregators):\n    return aggregators[i]\n",
    "def f(i, reports):\n    return reports[i]\n",
    # dynamic shape/scheduling surface.
    "def f(n):\n    return [0] * n\n",
    "def f(o, schedule):\n    return schedule(o)\n",
])
def test_direct_source_poisons_fail_closed(src):
    rejected(src)


def test_reflection_dynamic_native_fail_closed():
    for src in (
        "def f(x):\n    return eval(x)\n",
        "import importlib\ndef f():\n    return importlib.import_module('x')\n",
        "import ctypes\ndef f():\n    return 1\n",
        "def f(g):\n    return g.__code__\n",
    ):
        rejected(src)


def test_exact_whitelist_byte_drift_fails(tmp_path):
    for rel in e.EXACT_AUDITED_FILE_HASHES:
        src=e.ROOT/rel
        dst=tmp_path/rel
        dst.write_bytes(src.read_bytes())
    victim=tmp_path/"planlatch_v7_20_controls.py"
    victim.write_bytes(victim.read_bytes()+b"\n# byte drift poison\n")
    with pytest.raises(e.EffectManifestViolation):
        e.verify_exact_audited_files(tmp_path)
