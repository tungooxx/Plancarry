from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

PARTITION_SCHEMA = "PLANCARRY_CPDS_V5_TRAIN_CALIBRATION_PARTITION_V1"
TRAIN_BUCKETS = frozenset(range(8))
CALIBRATION_BUCKETS = frozenset((8, 9))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def partition_bucket(source_graph_id: str) -> int:
    if not source_graph_id:
        raise ValueError("SOURCE_GRAPH_ID")
    return int(_sha("CPDS_V5_PARTITION_V1\0" + source_graph_id)[:16], 16) % 10


def partition_name(source_graph_id: str) -> str:
    b = partition_bucket(source_graph_id)
    if b in TRAIN_BUCKETS:
        return "TRAIN"
    if b in CALIBRATION_BUCKETS:
        return "CALIBRATION"
    raise AssertionError


def validate_blind_reserved_overlap(candidate_structural_key_hashes: Iterable[str], reserved_v4_hashes: Iterable[str]) -> None:
    c = set(candidate_structural_key_hashes); r = set(reserved_v4_hashes)
    if any(len(x) != 64 for x in c | r):
        raise ValueError("STRUCTURAL_KEY_HASH")
    overlap = c & r
    if overlap:
        # Fail closed without returning the overlapping sealed identities.
        raise ValueError(f"V4_RESERVED_STRUCTURAL_KEY_OVERLAP_COUNT:{len(overlap)}")


def validate_source_graph_disjoint(train_graphs: Iterable[str], calibration_graphs: Iterable[str]) -> None:
    t = set(train_graphs); c = set(calibration_graphs)
    if not t or not c:
        raise ValueError("EMPTY_PARTITION")
    if t & c:
        raise ValueError("SOURCE_GRAPH_PARTITION_OVERLAP")
    for g in t:
        if partition_name(g) != "TRAIN":
            raise ValueError("TRAIN_BUCKET_MISMATCH")
    for g in c:
        if partition_name(g) != "CALIBRATION":
            raise ValueError("CALIBRATION_BUCKET_MISMATCH")


def deterministic_donor_index(target_graph_id: str, operator_id: str, candidates: Sequence[Mapping[str, str]]) -> int:
    eligible = []
    for i, row in enumerate(candidates):
        if row.get("source_graph_id") == target_graph_id:
            continue
        if row.get("operator_id") != operator_id:
            continue
        rid = row.get("record_id")
        if not rid:
            raise ValueError("DONOR_RECORD_ID")
        eligible.append((_sha("CPDS_V5_DONOR_V1\0" + target_graph_id + "\0" + operator_id + "\0" + rid), i))
    if not eligible:
        raise ValueError("NO_IN_DISTRIBUTION_DONOR")
    eligible.sort()
    return eligible[0][1]

_DONOR_Z0_FORBIDDEN_KEYS = frozenset({
    "branch_A", "branch_B", "branch_A_equivalence_class", "branch_B_equivalence_class",
    "evaluator_label", "outcome", "correctness", "endpoint", "score",
})


def deterministic_z0_donor_index(
    target_structural_id: str,
    target_source_graph_id: str,
    phase: str,
    candidates: Sequence[Mapping[str, str]],
) -> int:
    """Reviewed V5 donor-z0 selector: structure-only, phase-local, different graph."""
    if not target_structural_id or not target_source_graph_id or phase not in ("CALIBRATION", "DEVELOPMENT", "CONFIRMATION"):
        raise ValueError("DONOR_Z0_TARGET_IDENTITY")
    eligible = []
    for i, row in enumerate(candidates):
        if _DONOR_Z0_FORBIDDEN_KEYS & set(row):
            raise ValueError("DONOR_Z0_OUTCOME_OR_EVALUATOR_FIELD_FORBIDDEN")
        donor_graph = row.get("source_graph_id")
        donor_structural_id = row.get("structural_id")
        donor_phase = row.get("phase")
        if not donor_graph or not donor_structural_id or not donor_phase:
            raise ValueError("DONOR_Z0_CANDIDATE_IDENTITY")
        if donor_phase != phase or donor_graph == target_source_graph_id:
            continue
        key = _sha("CPDS_V5_DONOR_Z0_V1|" + target_structural_id + "|" + donor_structural_id)
        eligible.append((key, donor_structural_id, i))
    if not eligible:
        raise ValueError("NO_PHASE_LOCAL_DIFFERENT_GRAPH_Z0_DONOR")
    eligible.sort()
    return eligible[0][2]
