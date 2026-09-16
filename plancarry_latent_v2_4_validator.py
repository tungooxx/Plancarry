#!/usr/bin/env python3
"""Pure validation/statistics helpers for frozen PlanCarry-Latent v2.4.

This module contains no model calls and never assesses scientific truth from
engineering tests. It mechanically enforces the preregistered hashes,
independence map, exact sign tests, Holm correction, and confirmation decision
rules of Experiment e436f81c-e31f-43e9-8fef-f3e3c2c6e250.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any, Iterable

PREREG_SHA256 = "e6fb83177173044cf0c77a2868a4bd16ad8f166318cbd522ccc856c0ca87cbe0"
MANIFEST_SHA256 = "285d85b10171fcec0a80cc2960a79ae3349472e3b38935b6e97ec10deeaf0feb"
DONOR_MAP_SHA256 = "a2e342e35dd719d14a15a8559b23d545bb51b695405025c3d5964e7290f101f5"
REVIEW_SHA256 = "fe3df8f0c72bc16307cdc9f009eeb377d60257a97d7d5904817be3f4687a1a54"
STATIC_AUDIT_SHA256 = "70cf5e2da8c1b9aa84fcc0a1b26e951df50aeac3086c90181270a1c1da66a24a"
TOKENIZER_AUDIT_SHA256 = "343513b6f707291dc8513d7adebc177789a1f1013c00361c24fac6d99709d16f"
EXPECTED_CONFIRMATION_INDICES = list(range(20, 40))
EXPECTED_DISCOVERY_INDICES = list(range(20))
PRIMARY_TEST_NAMES = [
    "active_gt_zero",
    "active_gt_archived",
    "active_gt_random",
    "active_gt_unrelated",
]


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require_file_hash(path: str | Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"FROZEN_HASH_MISMATCH {path}: {actual} != {expected}")


def require_frozen_bundle(root: str | Path = ".") -> dict[str, Any]:
    root = Path(root)
    paths = {
        "prereg": root / "results/design/plancarry_latent_v2_4_prereg_immutable_20260819T1624Z.json",
        "manifest": root / "results/design/plancarry_latent_v2_matched_pair_manifest.json",
        "donor_map": root / "results/design/plancarry_latent_v2_2_unrelated_donor_map.json",
        "review": root / "results/design/plancarry_latent_v2_4_independent_review.json",
        "static_audit": root / "results/design/plancarry_latent_v2_4_static_newline_repair_audit.json",
        "tokenizer_audit": root / "results/design/plancarry_latent_v2_4_exact_template_tokenizer_audit.json",
    }
    expected = {
        "prereg": PREREG_SHA256,
        "manifest": MANIFEST_SHA256,
        "donor_map": DONOR_MAP_SHA256,
        "review": REVIEW_SHA256,
        "static_audit": STATIC_AUDIT_SHA256,
        "tokenizer_audit": TOKENIZER_AUDIT_SHA256,
    }
    for key, path in paths.items():
        require_file_hash(path, expected[key])
    bundle = {key: load_json(path) for key, path in paths.items()}
    validate_donor_map(bundle["manifest"], bundle["donor_map"])
    prereg = bundle["prereg"]
    validate_prereg_template_contract(prereg)
    if prereg.get("scientific_result") != "NOT_ASSESSED":
        raise ValueError("PREREG_SCIENTIFIC_RESULT_NOT_UNASSESSED")
    if prereg.get("artifact_integrity", {}).get("scientific_outcomes_seen") is not False:
        raise ValueError("PREREG_OUTCOMES_ALREADY_SEEN")
    review = bundle["review"]
    if (review.get("verdict") != "PASS_FOR_V24_ENGINEERING" or
            review.get("scientific_outcomes_seen") is not False or
            review.get("model_inference_executed") is not False or
            review.get("material_findings") != []):
        raise ValueError("INDEPENDENT_REVIEW_NOT_PASS_FOR_V24_ENGINEERING")
    static_audit = bundle["static_audit"]
    if static_audit.get("all_pass") is not True or static_audit.get("model_scientific_outcomes_seen") is not False:
        raise ValueError("V24_STATIC_NEWLINE_AUDIT_NOT_PASS")
    tokenizer_audit = bundle["tokenizer_audit"]
    if (tokenizer_audit.get("all_pass") is not True or tokenizer_audit.get("model_inference") is not False or
            tokenizer_audit.get("scientific_result") != "NOT_ASSESSED"):
        raise ValueError("V24_TOKENIZER_AUDIT_NOT_PASS")
    return bundle



def validate_prereg_template_contract(prereg: dict[str, Any]) -> None:
    """Fail closed on the exact executable v2.4 newline/scoring contract."""
    try:
        pair = prereg["pair_variable"]
        scoring = prereg["action_scoring"]
        fields = {
            "reset_template": pair["reset_template"],
            "source_active_template": pair["source_active_template"],
            "source_archived_template": pair["source_archived_template"],
            "reset_block": scoring["reset_block"],
        }
    except Exception as exc:
        raise ValueError("V24_TEMPLATE_FIELDS_MISSING") from exc
    for name, text in fields.items():
        if not isinstance(text, str):
            raise ValueError(f"V24_TEMPLATE_NOT_STRING {name}")
        if "\\n" in text:
            raise ValueError(f"V24_LITERAL_BACKSLASH_N_FORBIDDEN {name}")
        if not text.endswith("<STATE_END>\n") or text.endswith("<STATE_END>\n\n"):
            raise ValueError(f"V24_TERMINAL_NEWLINE_CONTRACT_FAILED {name}")
    if pair["reset_template"] != scoring["reset_block"]:
        raise ValueError("V24_RESET_TEMPLATE_DIVERGENCE")
    if scoring.get("scoring_prompt") != "{RESET_BLOCK}ACTION:":
        raise ValueError("V24_SCORING_PROMPT_CONTRACT_FAILED")
    if scoring.get("candidate_suffix_serialization") != " {EXACT_ADMISSIBLE_COMMAND}":
        raise ValueError("V24_CANDIDATE_SUFFIX_CONTRACT_FAILED")


def _pair_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("selected_pairs")
    if not isinstance(rows, list) or len(rows) != 40:
        raise ValueError("MANIFEST_PAIR_COUNT_MISMATCH")
    return rows


def validate_donor_map(manifest: dict[str, Any], donor_map: dict[str, Any]) -> None:
    if donor_map.get("model_outcomes_seen") is not False:
        raise ValueError("DONOR_MAP_NOT_PROSPECTIVE")
    rows = donor_map.get("mapping")
    if not isinstance(rows, list) or len(rows) != 20:
        raise ValueError("DONOR_MAP_COUNT_MISMATCH")
    recipients = [int(r["confirmation_pair_index"]) for r in rows]
    donors = [int(r["discovery_donor_pair_index"]) for r in rows]
    if recipients != EXPECTED_CONFIRMATION_INDICES:
        raise ValueError("DONOR_RECIPIENT_INDICES_MISMATCH")
    if sorted(donors) != EXPECTED_DISCOVERY_INDICES or len(set(donors)) != 20:
        raise ValueError("DONOR_DISCOVERY_BIJECTION_MISMATCH")
    pairs = {int(r["frozen_pair_index"]): r for r in _pair_rows(manifest)}
    base = donor_map.get("base_string")
    if not isinstance(base, str) or not base:
        raise ValueError("DONOR_BASE_STRING_MISSING")
    expected_discovery = sorted(
        [(i, pairs[i]["family"]) for i in EXPECTED_DISCOVERY_INDICES],
        key=lambda x: (
            hashlib.sha256((base + "|donor|" + str(x[0]) + "|" + x[1]).encode("utf-8")).hexdigest(),
            x[0],
        ),
    )
    expected_confirmation = [(i, pairs[i]["family"]) for i in EXPECTED_CONFIRMATION_INDICES]
    for row, (ci, cf), (di, df) in zip(rows, expected_confirmation, expected_discovery):
        digest = hashlib.sha256((base + "|donor|" + str(di) + "|" + df).encode("utf-8")).hexdigest()
        expected = (ci, cf, di, df, digest)
        actual = (
            int(row["confirmation_pair_index"]), row["confirmation_family"],
            int(row["discovery_donor_pair_index"]), row["discovery_donor_family"],
            row["donor_sort_sha256"],
        )
        if actual != expected:
            raise ValueError(f"DONOR_MAP_ALGORITHM_MISMATCH expected={expected!r} actual={actual!r}")


def option_orientation_bit(pair_index: int) -> int:
    s = f"{MANIFEST_SHA256}|{pair_index}|option_orientation_v1"
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[0:2], 16) % 2


def rademacher_direction(split: str, pair_index: int, layer_0based: int, dimension: int) -> list[float]:
    if dimension <= 0:
        raise ValueError("dimension must be positive")
    base = f"{MANIFEST_SHA256}|{split}|{pair_index}|{layer_0based}|random_control_v2_1"
    inv = 1.0 / math.sqrt(dimension)
    out: list[float] = []
    for j in range(dimension):
        digest = hashlib.sha256((base + "|" + str(j)).encode("utf-8")).digest()
        out.append(inv if digest[0] % 2 == 0 else -inv)
    return out


def l2(xs: Iterable[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in xs))


def f32(x: float) -> float:
    """Round a scalar to IEEE-754 binary32 for preregistered FP32 contrast math."""
    return struct.unpack("!f", struct.pack("!f", float(x)))[0]

def l2_f32(xs: Iterable[float]) -> float:
    acc = f32(0.0)
    for x in xs:
        xx = f32(x)
        acc = f32(acc + f32(xx * xx))
    return f32(math.sqrt(acc))

def normalized_contrast(a: list[float], b: list[float], epsilon: float = 1e-8) -> tuple[list[float], float]:
    if len(a) != len(b) or not a:
        raise ValueError("VECTOR_DIM_MISMATCH")
    delta = [f32(f32(x) - f32(y)) for x, y in zip(a, b)]
    norm = l2_f32(delta)
    if norm <= epsilon:
        return [0.0] * len(delta), norm
    return [f32(x / norm) for x in delta], norm


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def mean_lp(score_row: dict[str, Any]) -> float:
    n = int(score_row["token_count"])
    if n <= 0:
        raise ValueError("EMPTY_COMMAND_SUFFIX")
    return float(score_row["logprob_sum"]) / n


def q_a(score_response: dict[str, Any]) -> tuple[float, float, float]:
    rows = score_response.get("scores")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("EXPECTED_TWO_COMMAND_SCORES")
    a, b = mean_lp(rows[0]), mean_lp(rows[1])
    margin = a - b
    return sigmoid(margin), margin, a - b


def exact_sign_tail(k: int, n: int = 20) -> float:
    if n != 20:
        raise ValueError("V2_4_PRIMARY_N_MUST_BE_20")
    if k < 0 or k > n:
        raise ValueError("INVALID_SUCCESS_COUNT")
    return sum(math.comb(n, j) for j in range(k, n + 1)) * (0.5 ** n)


def holm_adjust(raw_p: dict[str, float]) -> dict[str, float]:
    if set(raw_p) != set(PRIMARY_TEST_NAMES):
        raise ValueError("PRIMARY_TEST_SET_MISMATCH")
    ordered = sorted(raw_p.items(), key=lambda kv: (kv[1], kv[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    m = len(ordered)
    for rank, (name, p) in enumerate(ordered):
        candidate = min(1.0, (m - rank) * float(p))
        running = max(running, candidate)
        adjusted[name] = running
    return adjusted


def primary_test_statistics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if len(rows) != 20:
        raise ValueError("CONFIRMATION_PRIMARY_REQUIRES_EXACTLY_20_ROWS")
    indices = [int(r["pair_index"]) for r in rows]
    if sorted(indices) != EXPECTED_CONFIRMATION_INDICES or len(set(indices)) != 20:
        raise ValueError("CONFIRMATION_POPULATION_MISMATCH")
    xs = {
        "active_gt_zero": [float(r["cpse_active"]) for r in rows],
        "active_gt_archived": [float(r["cpse_active"]) - float(r["cpse_archived"]) for r in rows],
        "active_gt_random": [float(r["cpse_active"]) - float(r["cpse_random"]) for r in rows],
        "active_gt_unrelated": [float(r["cpse_active"]) - float(r["cpse_unrelated"]) for r in rows],
    }
    raw: dict[str, float] = {}
    out: dict[str, dict[str, Any]] = {}
    for name in PRIMARY_TEST_NAMES:
        k = sum(1 for x in xs[name] if x > 0.0)  # exact zero is frozen failure
        p = exact_sign_tail(k)
        raw[name] = p
        out[name] = {"k_positive": k, "n": 20, "raw_p": p}
    adj = holm_adjust(raw)
    for name in PRIMARY_TEST_NAMES:
        out[name]["holm_adjusted_p"] = adj[name]
    return out


def confirmation_decision(rows: list[dict[str, Any]], overall_competent: int, delayed_competent: int) -> dict[str, Any]:
    if overall_competent < 16 or delayed_competent < 8:
        return {
            "status": "INCONCLUSIVE_MODEL_EXPRESSIVITY",
            "overall_competent": overall_competent,
            "delayed_competent": delayed_competent,
            "primary_inference": None,
        }
    tests = primary_test_statistics(rows)
    mean_active = sum(float(r["cpse_active"]) for r in rows) / 20.0
    positive_fraction = sum(1 for r in rows if float(r["cpse_active"]) > 0.0) / 20.0
    bidirectional_fraction = sum(
        1 for r in rows if float(r["delta_a"]) > 0.0 and float(r["delta_b"]) > 0.0
    ) / 20.0
    control_means = {
        c: sum(float(r["cpse_active"]) - float(r[c]) for r in rows) / 20.0
        for c in ["cpse_archived", "cpse_random", "cpse_unrelated"]
    }
    all_p = all(tests[name]["holm_adjusted_p"] <= 0.05 for name in PRIMARY_TEST_NAMES)
    active_guards = mean_active >= 0.10 and positive_fraction >= 0.70 and bidirectional_fraction >= 0.60
    specificity_p = all(tests[name]["holm_adjusted_p"] <= 0.05 for name in ["active_gt_archived", "active_gt_random", "active_gt_unrelated"])
    specificity_guards = all(v >= 0.05 for v in control_means.values())
    active_core = tests["active_gt_zero"]["holm_adjusted_p"] <= 0.05 and active_guards
    if active_core and specificity_p and specificity_guards:
        status = "SUPPORTED_T1"
    elif active_core and not (specificity_p and specificity_guards):
        status = "INCONCLUSIVE_NONSPECIFIC_ACTIVATION_EFFECT"
    else:
        status = "NOT_SUPPORTED_WEAKENED_SINGLE_SITE_CONTRAST"
    return {
        "status": status,
        "overall_competent": overall_competent,
        "delayed_competent": delayed_competent,
        "primary_inference": tests,
        "effect_guards": {
            "mean_cpse_active": mean_active,
            "positive_pair_fraction": positive_fraction,
            "bidirectional_pair_fraction": bidirectional_fraction,
            "mean_active_minus_controls": control_means,
            "all_holm_p_le_0_05": all_p,
            "active_guards_pass": active_guards,
            "specificity_p_pass": specificity_p,
            "specificity_guards_pass": specificity_guards,
        },
        "claim_scope": "T1 causal active-plan signal only",
    }


def verify_selection_artifact(path: str | Path, expected_sha256: str) -> dict[str, Any]:
    require_file_hash(path, expected_sha256)
    obj = load_json(path)
    if obj.get("kind") != "PLANCARRY_LATENT_V2_4_DISCOVERY_SELECTION":
        raise ValueError("SELECTION_KIND_MISMATCH")
    if obj.get("scientific_result") != "NOT_ASSESSED_DISCOVERY_SELECTION_ONLY":
        raise ValueError("SELECTION_SCIENTIFIC_SCOPE_MISMATCH")
    refs = obj.get("frozen_refs", {})
    required_refs = {
        "prereg_sha256": PREREG_SHA256,
        "manifest_sha256": MANIFEST_SHA256,
        "donor_map_sha256": DONOR_MAP_SHA256,
        "independent_review_sha256": REVIEW_SHA256,
        "static_audit_sha256": STATIC_AUDIT_SHA256,
        "tokenizer_audit_sha256": TOKENIZER_AUDIT_SHA256,
    }
    if any(refs.get(k) != expected for k, expected in required_refs.items()):
        raise ValueError("SELECTION_FROZEN_REFS_MISMATCH")
    if int(obj.get("selected_layer")) not in [6, 13, 20, 27]:
        raise ValueError("SELECTION_LAYER_OUTSIDE_FROZEN_GRID")
    if float(obj.get("selected_alpha")) not in [0.05, 0.1, 0.2]:
        raise ValueError("SELECTION_ALPHA_OUTSIDE_FROZEN_GRID")
    dirs = obj.get("discovery_active_directions")
    if not isinstance(dirs, dict) or sorted(map(int, dirs.keys())) != EXPECTED_DISCOVERY_INDICES:
        raise ValueError("SELECTION_DONOR_DIRECTIONS_INCOMPLETE")
    if obj.get("confirmation_requests_made") not in (False, 0):
        raise ValueError("SELECTION_CREATED_AFTER_CONFIRMATION_ACCESS")
    return obj


if __name__ == "__main__":
    bundle = require_frozen_bundle(Path(__file__).resolve().parent)
    print(json.dumps({
        "ok": True,
        "prereg_sha256": PREREG_SHA256,
        "manifest_sha256": MANIFEST_SHA256,
        "donor_map_sha256": DONOR_MAP_SHA256,
        "pair_count": len(bundle["manifest"]["selected_pairs"]),
        "scientific_result": "NOT_ASSESSED",
    }, sort_keys=True))
