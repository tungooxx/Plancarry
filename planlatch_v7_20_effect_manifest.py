"""Machine-derived/fail-closed whole-program effect certification for PlanLatch v7.20.

Scientific operators are accepted only when the exact implementation bytes match
an audited semantic whitelist.  Unknown source is checked by a deliberately
conservative AST verifier and fails closed on scientific control/selection
surfaces.  No caller-supplied effect boolean is treated as evidence.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Mapping

import planlatch_v7_20_controls as ctl

ROOT = Path(__file__).resolve().parent

# Full-module byte identities are the certification root.  These are the exact
# reviewed scientific/control modules.  Any helper/call-graph drift changes the
# module hash and invalidates the certificate.
EXACT_AUDITED_FILE_HASHES = {
    "planlatch_v7_9_protocol.py": "e10db7c0b1552ca56e297ae0b8effe8e05988aad1be5e77ee9c42c534bc8222a",
    "planlatch_v7_9_runner.py": "5e185c990e0f994485ac2d5d0434430d7c8723a09b6eb505a68ec5b41e5ed200",
    "planlatch_v7_9_model_runtime.py": "d042978a0fc31e2d9c3124695d80854e8d9580d40a2c2393666d4798fca0ec01",
    "planlatch_v7_9_execution_driver.py": "23f39c4615f2f8de7b9bf3094090db7df0a7297309a3de68d272563c37281505",
    "planlatch_v7_20_controls.py": "06e7c8da9294c9e677fa421d9219ee36fa84ae01e2dd128eb978ce089d889173",
    "planlatch_v7_20_runner.py": "b728c83a92c976f5ed341c1084ac21bc667c11cd6be99507b052611c2aea58f9",
    "planlatch_v7_20_execution_driver.py": "f19a27ad8dc7d216c47a634588e60affd965357bc1b733c5d2a8da34b6b3a18b",
}

# Operator -> exact audited module + frozen formula.  Certificate truth is
# derived from the exact module hash match below, never injected by a caller.
SCIENCE_CERTIFICATES = (
    ("phi", "planlatch_v7_9_protocol.py", "v79_phi"),
    ("full_decoder", "planlatch_v7_9_runner.py", "v79_full_decoder"),
    ("placebo_decoder", "planlatch_v7_9_runner.py", "v79_placebo_decoder"),
    ("p_mix", "planlatch_v7_9_protocol.py", "v79_p_mix"),
    ("source_scoring", "planlatch_v7_9_runner.py", "v79_source_scoring"),
    ("payload_bank", "planlatch_v7_9_runner.py", "v79_payload_bank_fit_only"),
    ("payload_select", "planlatch_v7_9_protocol.py", "v79_observed_support_payload_select"),
    ("relay_scoring", "planlatch_v7_9_execution_driver.py", "v79_relay_scoring"),
    ("g1_g20", "planlatch_v7_9_runner.py", "v79_g1_g20_terminal"),
    ("u_star", "planlatch_v7_20_runner.py", "v720_u_star_router"),
    ("total_report", "planlatch_v7_20_controls.py", "v720_total_report"),
)

FORBIDDEN_CALL_NAMES = {
    "eval", "exec", "compile", "__import__", "getattr", "setattr", "delattr",
}
FORBIDDEN_IMPORT_ROOTS = {
    "ctypes", "cffi", "importlib", "subprocess", "multiprocessing",
}
FORBIDDEN_ATTRS = {
    "__subclasses__", "__globals__", "__code__", "__closure__", "__dict__",
}
# Unknown/unwhitelisted scientific source is intentionally much more
# restrictive than ordinary Python.  These calls can select scientific
# families, hidden state, RNG/cache identity, scheduling or fallback paths.
SUSPICIOUS_CALL_TOKENS = {
    "random", "rand", "randint", "randn", "seed", "choice", "shuffle",
    "argmax", "argmin", "topk", "top_k", "sort", "sorted",
    "cache", "memo", "lru_cache", "fallback", "retry", "schedule",
    "threshold", "payload", "aggregate", "aggregation", "report",
    "select", "dispatch", "lookup", "route", "router", "mask", "gate",
}
SAFE_UNKNOWN_CALLS = {"abs", "int", "float", "bool"}


class EffectManifestViolation(ValueError):
    pass


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts = [f.attr]
        v = f.value
        while isinstance(v, ast.Attribute):
            parts.append(v.attr)
            v = v.value
        if isinstance(v, ast.Name):
            parts.append(v.id)
        return ".".join(reversed(parts))
    return "<dynamic-call>"


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _looks_like_branchless_family_blend(node: ast.BinOp) -> bool:
    # Detect w*f0 + (1-w)*f1 and analogous hard/soft arithmetic selectors,
    # even when the selector was computed on a previous line.
    if not isinstance(node.op, (ast.Add, ast.Sub)):
        return False
    mults = [n for n in ast.walk(node) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult)]
    return len(mults) >= 2 and len(_names(node)) >= 3


def static_fail_closed_scan(path: Path) -> bool:
    """Conservative verifier for *unapproved* source.

    Exact audited scientific modules are certified by byte identity elsewhere.
    Unknown source must be simple fixed numeric dataflow.  Control flow,
    data-dependent indexing, opaque calls, family blends, cache/RNG/scheduling
    and fallback surfaces fail closed.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [x.name.split(".")[0] for x in node.names]
            elif node.module:
                names = [node.module.split(".")[0]]
            bad = set(names) & FORBIDDEN_IMPORT_ROOTS
            if bad:
                raise EffectManifestViolation(
                    f"forbidden dynamic/native import in {path.name}: {sorted(bad)}"
                )

        if isinstance(node, ast.Call):
            name = _call_name(node)
            leaf = name.split(".")[-1]
            if leaf in FORBIDDEN_CALL_NAMES:
                raise EffectManifestViolation(f"forbidden reflective call {name} in {path.name}")
            if leaf not in SAFE_UNKNOWN_CALLS:
                low = name.lower()
                if any(tok in low for tok in SUSPICIOUS_CALL_TOKENS):
                    raise EffectManifestViolation(
                        f"scientific selection/RNG/cache/scheduling call rejected: {name}"
                    )
                # Unknown calls are opaque by default; fail closed.
                raise EffectManifestViolation(f"unverified call in unknown scientific source: {name}")

        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            raise EffectManifestViolation(
                f"forbidden reflective attribute {node.attr} in {path.name}"
            )

        if isinstance(node, (
            ast.If, ast.IfExp, ast.While, ast.For, ast.AsyncFor, ast.Match,
            ast.Try, ast.With, ast.AsyncWith, ast.BoolOp, ast.Break, ast.Continue,
            ast.Yield, ast.YieldFrom, ast.Await, ast.Lambda,
            ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
        )):
            raise EffectManifestViolation(
                f"unknown scientific control/topology node rejected: {type(node).__name__}"
            )

        if isinstance(node, ast.Compare):
            # Comparisons in unknown scientific source can become hard masks or
            # branch predicates.  Approved formulae use exact-byte certification.
            raise EffectManifestViolation("comparison/mask in unknown scientific source rejected")

        if isinstance(node, ast.Subscript):
            # Dynamic scientific indexing/lookup is not admitted outside exact
            # audited formulae.
            if not isinstance(node.slice, ast.Constant):
                raise EffectManifestViolation("dynamic scientific indexing rejected")

        if isinstance(node, ast.BinOp) and _looks_like_branchless_family_blend(node):
            raise EffectManifestViolation("branchless scientific family blend rejected")

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            # Dynamic shape/list repetition such as [0] * n is a topology path.
            vals = (node.left, node.right)
            if any(isinstance(v, (ast.List, ast.Tuple, ast.Set, ast.Dict)) for v in vals) and any(
                isinstance(v, ast.Name) for v in vals
            ):
                raise EffectManifestViolation("dynamic scientific shape construction rejected")

    return True


def verify_exact_audited_files(root: Path = ROOT) -> Mapping[str, str]:
    observed = {}
    for rel, expected in EXACT_AUDITED_FILE_HASHES.items():
        got = sha_file(root / rel)
        observed[rel] = got
        if got != expected:
            raise EffectManifestViolation(
                f"exact semantic whitelist byte drift: {rel} expected={expected} got={got}"
            )
    return observed


def build_operator_certificates(root: Path = ROOT) -> tuple[ctl.OperatorCertificate, ...]:
    observed = verify_exact_audited_files(root)
    out = []
    for name, rel, formula in SCIENCE_CERTIFICATES:
        digest = observed[rel]
        # These booleans are derived *only* after exact whitelist verification.
        # There is no API accepting caller-provided scientific effect truth.
        out.append(
            ctl.OperatorCertificate(
                name=name,
                implementation_sha256=digest,
                input_effects=(ctl.Effect.CONTENT_DATA, ctl.Effect.SCIENCE_DATA),
                output_effect=(
                    ctl.Effect.TERMINAL_DECISION
                    if formula == "v79_g1_g20_terminal"
                    else ctl.Effect.SCIENCE_DATA
                ),
                frozen_formula_id=formula,
                recursively_verified=True,
                opaque_or_native=False,
                content_selects_alternative_family=False,
                hidden_control_effect=False,
            )
        )
    return tuple(out)


def verify_default_manifest(root: Path = ROOT) -> Mapping[str, object]:
    certs = build_operator_certificates(root)
    ctl.verify_whole_program_effects(certs)
    return {
        "version": "planlatch-v7.20-effect-manifest-v2",
        "design_id": ctl.DESIGN_ID,
        "semantic_hash": ctl.SEMANTIC_HASH,
        "certification_mode": "EXACT_BYTE_SEMANTIC_WHITELIST_PLUS_FAIL_CLOSED_UNKNOWN_AST",
        "exact_audited_file_hashes": dict(EXACT_AUDITED_FILE_HASHES),
        "operators": [
            {
                "name": x.name,
                "implementation_sha256": x.implementation_sha256,
                "formula": x.frozen_formula_id,
                "recursively_verified": x.recursively_verified,
                "certificate_basis": "EXACT_AUDITED_MODULE_BYTES",
            }
            for x in certs
        ],
        "unknown_opaque_native_callbacks": "FAIL_CLOSED",
        "unknown_source_control_flow": "FAIL_CLOSED",
        "dynamic_scientific_indexing": "FAIL_CLOSED",
        "extensional_content_selection": "FORBIDDEN",
        "production_numeric_dependency_certificate": {
            "status": "PENDING_EXACT_RUNTIME_FREEZE",
            "required": ["numpy exact bytes/version", "python runtime exact bytes/version"],
        },
    }
