#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import localcontinuation_controls_v2 as controls
import localcontinuation_packet_builder_v2 as pb

class V2ValidationError(RuntimeError):
    pass


def validate_packet_set(
    packets: Sequence[Mapping[str, Any]],
    expected_phase: str,
    tokenizer: Any,
    open_tag_ids: Sequence[int],
    close_tag_ids: Sequence[int],
    root: str | Path = ".",
) -> dict[str, Any]:
    try:
        return pb.validate_phase_packets(packets, expected_phase, tokenizer, open_tag_ids, close_tag_ids, root)
    except Exception as exc:
        raise V2ValidationError(f"PACKET_SET_INVALID:{type(exc).__name__}:{exc}") from exc


def validate_stage2_reconstruction(
    packets: Sequence[Mapping[str, Any]],
    phase: str,
    tokenizer: Any,
    neutral_filler_ids: Sequence[int],
    open_tag_ids: Sequence[int],
    close_tag_ids: Sequence[int],
    root: str | Path = ".",
) -> dict[str, Any]:
    source = [dict(x) for x in packets]
    expected = pb.apply_stage2_phase(
        tokenizer,
        source,
        phase,
        neutral_filler_ids,
        open_tag_ids,
        close_tag_ids,
        root,
    )
    if len(expected) != len(packets):
        raise V2ValidationError("STAGE2_RECONSTRUCTION_LENGTH")
    for observed, reconstructed in zip(packets, expected):
        for key in ("qualified", "qualification_stage2_reasons", "frozen_E_indices_sha256", "control_provenance"):
            if observed.get(key) != reconstructed.get(key):
                raise V2ValidationError(f"STAGE2_RECONSTRUCTION_MISMATCH:{observed.get('frozen_index')}:{key}")
    return {
        "phase": phase,
        "packet_count": len(packets),
        "qualified_count": sum(bool(x.get("qualified")) for x in packets),
        "reconstruction": "PASS",
    }


def validate_replay_geometry(provenance_by_condition: Mapping[str, Mapping[str, Any]]) -> None:
    try:
        controls.assert_condition_invariant_replay_geometry(provenance_by_condition)
    except Exception as exc:
        raise V2ValidationError(f"REPLAY_GEOMETRY_INVALID:{type(exc).__name__}:{exc}") from exc


def validate_split_access_flags(payload: Mapping[str, Any], phase: str) -> None:
    if phase == "development":
        forbidden = ("confirmation_accessed", "reserve_accessed", "valid_seen_accessed", "valid_unseen_accessed")
    elif phase == "confirmation":
        forbidden = ("reserve_accessed", "valid_seen_accessed", "valid_unseen_accessed")
    elif phase == "reserve_replication":
        forbidden = ("valid_seen_accessed", "valid_unseen_accessed")
    else:
        raise V2ValidationError("UNKNOWN_PHASE")
    for key in forbidden:
        if payload.get(key) is not False:
            raise V2ValidationError(f"SPLIT_ISOLATION:{phase}:{key}")
