"""Pure pre-science helpers for PlanCarry SuccessorFeature-v2 constructibility.

No model/tokenizer/environment dependencies are permitted in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Sequence

PHASE_LABELS = (
    "SEEK_OBJECT",
    "ACQUIRE_OBJECT",
    "CARRY_OR_SEEK_RECEPTACLE",
    "PLACE_OBJECT",
    "MANIPULATE_CONTAINER",
    "OTHER",
)
NEUTRAL_ROW = (43, 43, 43, 42, 42, 42)
GAMMA = 0.8
FUTURE_DISTANCE_THRESHOLD = 0.50
SECOND_HIGHEST_PROB_MIN = 0.10
POPULATION_SHA256 = "d35271102561040901ead7a663e080242b577c9afd75743f94ad3cce014d24d2"
CONSTRUCTIBILITY_RANGE = range(0, 16)
CAUSAL_DEVELOPMENT_LOCKED_RANGE = range(16, 32)
SPARE_LOCKED_RANGE = range(32, 37)
SERIAL_PREFIX = "SF1:"
SERIAL_ASCII_BYTES = 52

class ContractError(ValueError):
    """Fail-closed contract violation."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def largest_remainder_uint8(probabilities: Sequence[float]) -> tuple[int, ...]:
    """Quantize six finite nonnegative weights to uint8 counts summing exactly 255.

    Ties in fractional remainder are resolved by frozen phase-label order.
    """
    if len(probabilities) != len(PHASE_LABELS):
        raise ContractError("EXPECTED_SIX_PHASE_PROBABILITIES")
    vals = [float(x) for x in probabilities]
    if not all(math.isfinite(x) and x >= 0.0 for x in vals):
        raise ContractError("NONFINITE_OR_NEGATIVE_PHASE_WEIGHT")
    total = math.fsum(vals)
    if not total > 0.0:
        raise ContractError("ZERO_PHASE_WEIGHT_SUM")
    scaled = [x / total * 255.0 for x in vals]
    floors = [math.floor(x) for x in scaled]
    remaining = 255 - sum(floors)
    order = sorted(range(6), key=lambda i: (-(scaled[i] - floors[i]), i))
    for i in order[:remaining]:
        floors[i] += 1
    out = tuple(int(x) for x in floors)
    if sum(out) != 255 or any(x < 0 or x > 255 for x in out):
        raise AssertionError("QUANTIZATION_INVARIANT_BROKEN")
    return out


def one_hot_row(label: str) -> tuple[int, ...]:
    try:
        idx = PHASE_LABELS.index(label)
    except ValueError as exc:
        raise ContractError("UNKNOWN_PHASE_LABEL") from exc
    return tuple(255 if i == idx else 0 for i in range(6))


def _validate_row(row: Sequence[int]) -> tuple[int, ...]:
    if len(row) != 6:
        raise ContractError("ROW_MUST_HAVE_SIX_VALUES")
    if any(type(x) is not int for x in row):
        raise ContractError("ROW_VALUE_NOT_UINT8_INTEGER")
    vals = tuple(row)
    if any(x < 0 or x > 255 for x in vals):
        raise ContractError("ROW_VALUE_OUT_OF_UINT8_RANGE")
    if sum(vals) != 255:
        raise ContractError("ROW_SUM_MUST_EQUAL_255")
    return vals


def validate_carrier(rows: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    if len(rows) != 4:
        raise ContractError("CARRIER_MUST_HAVE_FOUR_ROWS")
    return tuple(_validate_row(r) for r in rows)


def serialize_carrier(rows: Sequence[Sequence[int]]) -> str:
    carrier = validate_carrier(rows)
    text = SERIAL_PREFIX + "".join(f"{x:02x}" for row in carrier for x in row)
    if len(text.encode("ascii")) != SERIAL_ASCII_BYTES:
        raise AssertionError("SERIALIZATION_LENGTH_INVARIANT_BROKEN")
    return text


def parse_carrier(text: str) -> tuple[tuple[int, ...], ...]:
    try:
        raw = text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ContractError("CARRIER_NOT_ASCII") from exc
    if len(raw) != SERIAL_ASCII_BYTES or not text.startswith(SERIAL_PREFIX):
        raise ContractError("INVALID_SF1_SERIALIZATION")
    hexpart = text[len(SERIAL_PREFIX):]
    if len(hexpart) != 48 or any(c not in "0123456789abcdef" for c in hexpart):
        raise ContractError("INVALID_SF1_HEX")
    vals = [int(hexpart[i:i+2], 16) for i in range(0, 48, 2)]
    rows = [vals[i:i+6] for i in range(0, 24, 6)]
    return validate_carrier(rows)


def _row_l1(a: Sequence[int], b: Sequence[int]) -> float:
    aa, bb = _validate_row(a), _validate_row(b)
    return math.fsum(abs(x - y) / 255.0 for x, y in zip(aa, bb))


def future_distance(carrier_a: Sequence[Sequence[int]], carrier_b: Sequence[Sequence[int]], *, gamma: float = GAMMA) -> float:
    """Frozen v2 constructibility distance: rows 3 and 4 only (1-indexed)."""
    a, b = validate_carrier(carrier_a), validate_carrier(carrier_b)
    if gamma != GAMMA:
        raise ContractError("GAMMA_DRIFT")
    return (gamma ** 2) * _row_l1(a[2], b[2]) + (gamma ** 3) * _row_l1(a[3], b[3])


def future_separable(carrier_a: Sequence[Sequence[int]], carrier_b: Sequence[Sequence[int]]) -> bool:
    return future_distance(carrier_a, carrier_b) >= FUTURE_DISTANCE_THRESHOLD


def softmax_float64(scores: Sequence[float]) -> tuple[float, ...]:
    if len(scores) != 6:
        raise ContractError("EXPECTED_SIX_BRANCH_SCORES")
    vals = [float(x) for x in scores]
    if not all(math.isfinite(x) for x in vals):
        raise ContractError("BRANCH_SCORE_NOT_FINITE")
    m = max(vals)
    expv = [math.exp(x - m) for x in vals]
    z = math.fsum(expv)
    return tuple(x / z for x in expv)


def branch_labels_if_plausible(scores: Sequence[float]) -> tuple[str, str]:
    """Return deterministic top-two labels iff frozen runner-up guard passes."""
    probs = softmax_float64(scores)
    order = sorted(range(6), key=lambda i: (-probs[i], i))
    if probs[order[1]] < SECOND_HIGHEST_PROB_MIN:
        raise ContractError("SECOND_BRANCH_PROBABILITY_BELOW_0_10")
    return PHASE_LABELS[order[0]], PHASE_LABELS[order[1]]


def orient_branches(game_path: str, label0: str, label1: str) -> tuple[str, str]:
    if label0 == label1 or label0 not in PHASE_LABELS or label1 not in PHASE_LABELS:
        raise ContractError("INVALID_BRANCH_LABEL_PAIR")
    digest = hashlib.sha256((game_path + "|SUCCESSOR_FEATURE_BRANCH_ORIENTATION_V1").encode("utf-8")).digest()
    return (label0, label1) if (digest[0] & 1) == 0 else (label1, label0)


def branch_phase_only(rows: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    c = validate_carrier(rows)
    return (c[0], c[1], NEUTRAL_ROW, NEUTRAL_ROW)


def time_shuffled(rows: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    c = validate_carrier(rows)
    return (c[0], c[1], c[3], c[2])


def immediate_action_only(rows: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    c = validate_carrier(rows)
    return (c[0], NEUTRAL_ROW, NEUTRAL_ROW, NEUTRAL_ROW)


def load_constructibility_population(population_path: str | Path) -> tuple[dict, ...]:
    """Return only frozen indices 0..15; any population drift/tamper fails closed."""
    path = Path(population_path)
    if _sha256(path) != POPULATION_SHA256:
        raise ContractError("POPULATION_SHA256_MISMATCH")
    obj = json.loads(path.read_text())
    rows = obj.get("paths")
    if not isinstance(rows, list) or len(rows) != 37:
        raise ContractError("EXPECTED_EXACTLY_37_FROZEN_PATHS")
    by_index = {}
    for rec in rows:
        idx = rec.get("index")
        if not isinstance(idx, int) or idx in by_index:
            raise ContractError("INVALID_OR_DUPLICATE_FROZEN_INDEX")
        by_index[idx] = rec
    if set(by_index) != set(range(37)):
        raise ContractError("FROZEN_INDEX_SET_MISMATCH")
    # Explicitly never expose locked rows through this pre-science API.
    return tuple(dict(by_index[i]) for i in CONSTRUCTIBILITY_RANGE)


def require_constructibility_index(index: int) -> None:
    if index not in CONSTRUCTIBILITY_RANGE:
        if index in CAUSAL_DEVELOPMENT_LOCKED_RANGE:
            raise ContractError("CAUSAL_DEVELOPMENT_SPLIT_LOCKED")
        if index in SPARE_LOCKED_RANGE:
            raise ContractError("SPARE_SPLIT_LOCKED")
        raise ContractError("INDEX_OUTSIDE_FROZEN_POPULATION")
