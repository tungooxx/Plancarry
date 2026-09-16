#!/usr/bin/env python3
"""Independent deterministic validator for ReplayResidual V2.1 packet sets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from replay_residual_sanity_protocol_v1 import CONDITIONS, DEV_INDICES, PLAN_SLOT_TOKENS, build_condition_slots, canonical_json_bytes, development_manifest, trajectory_digest
from replay_residual_natural_packet_producer_v2_1 import (
    ACTION_BUDGET, ANCHOR_CYCLE, CONTRACT_REL, CONTRACT_SHA256, EXPECTED_DEVICE_NAME, EXPECTED_MODEL_PROVENANCE,
    FINAL_TARGET_REL, MIN_FINAL_QUALIFIED, PACKET_CONTRACT_VERSION, PROTOCOL_SHA256,
    REQUIRED_ACTION_FIELDS, REQUIRED_PACKET_FIELDS, REVIEW_REL, REVIEW_SHA256,
    packet_filename, sha256_bytes, sha256_file, sha256_json, sha256_text,
    unrelated_donor_for, unrelated_ordering_key, validate_model_provenance, verify_frozen_bindings,
)

FORBIDDEN_CAUSAL_KEYS = {"capture", "patch", "patch_score", "inject", "injection", "selected_layer", "selected_scale", "t1_effect", "valid_seen", "valid_unseen"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_keys(value: Any):
    if isinstance(value, Mapping):
        for k, v in value.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_keys(v)


def validate_packet(packet: dict[str, Any], tokenizer: Any | None = None) -> None:
    missing = [k for k in REQUIRED_PACKET_FIELDS if k not in packet]
    if missing:
        raise RuntimeError("PACKET_REQUIRED_FIELDS_MISSING:" + ",".join(missing))
    idx = int(packet["frozen_index"])
    if idx not in DEV_INDICES:
        raise RuntimeError(f"SEALED_OR_INVALID_PACKET_INDEX:{idx}")
    if packet["packet_contract_version"] != PACKET_CONTRACT_VERSION or packet["producer_contract_sha256"] != CONTRACT_SHA256:
        raise RuntimeError("PACKET_CONTRACT_BINDING_MISMATCH")
    if packet["game_path_sha256"] != sha256_text(str(packet["game_path"])):
        raise RuntimeError("GAME_PATH_HASH_MISMATCH")
    validate_model_provenance(packet["model_provenance"])
    if int(packet.get("interruption_after", -1)) != ANCHOR_CYCLE:
        raise RuntimeError("INTERRUPTION_AFTER_MISMATCH")
    actions = packet.get("actions")
    if not isinstance(actions, list) or len(actions) > ACTION_BUDGET:
        raise RuntimeError("ACTION_LIST_OR_BUDGET_INVALID")
    for i, row in enumerate(actions, 1):
        missing_action = [k for k in REQUIRED_ACTION_FIELDS if k not in row]
        if missing_action:
            raise RuntimeError("ACTION_REQUIRED_FIELDS_MISSING:" + ",".join(missing_action))
        if int(row["step"]) != i:
            raise RuntimeError("ACTION_STEP_SEQUENCE_MISMATCH")
        commands = row["admissible_commands"]
        if commands != sorted(commands) or row["command"] not in commands:
            raise RuntimeError("ACTION_ADMISSIBLE_COMMAND_BINDING_MISMATCH")
        if row["admissible_commands_sha256"] != sha256_json(commands):
            raise RuntimeError("ADMISSIBLE_COMMAND_HASH_MISMATCH")
        if set(row["candidate_suffix_token_ids_sha256_by_command"]) != set(commands):
            raise RuntimeError("CANDIDATE_SUFFIX_HASH_COMMAND_SET_MISMATCH")
    if packet["trajectory_sha256"] != trajectory_digest(packet):
        raise RuntimeError("TRAJECTORY_HASH_MISMATCH")
    if bool(packet["qualified"]) and not bool(packet["trajectory_eligible"]):
        raise RuntimeError("QUALIFIED_PACKET_NOT_TRAJECTORY_ELIGIBLE")
    keys = {k.lower() for k in _walk_keys(packet)}
    if keys & FORBIDDEN_CAUSAL_KEYS:
        raise RuntimeError("CAUSAL_PATH_FIELD_FORBIDDEN:" + ",".join(sorted(keys & FORBIDDEN_CAUSAL_KEYS)))
    cp = packet["control_provenance"]
    if cp.get("condition_names") != list(CONDITIONS) or int(cp.get("anchor_cycle", -1)) != ANCHOR_CYCLE:
        raise RuntimeError("CONTROL_PROVENANCE_BINDING_MISMATCH")
    if cp.get("control_builder_source_sha256") != PROTOCOL_SHA256:
        raise RuntimeError("CONTROL_BUILDER_HASH_MISMATCH")
    if bool(packet["qualified"]):
        if set(cp.get("condition_slot_token_ids_sha256_by_condition", {})) != set(CONDITIONS):
            raise RuntimeError("QUALIFIED_PACKET_MISSING_SEVEN_CONTROL_HASHES")
        if tokenizer is not None:
            # Donor text is checked at directory scope; here ensure local plan is valid via slot construction later.
            plan_ids = tokenizer.encode(str(packet["plan_text"]), add_special_tokens=False)
            if len(plan_ids) > 96:
                raise RuntimeError("QUALIFIED_PLAN_EXCEEDS_96_COMPLETE_BLOCK_TOKENS")


def validate_packet_directory(directory: Path, tokenizer: Any | None = None, root: Path | None = None) -> dict[str, Any]:
    directory = Path(directory)
    root = Path(root) if root is not None else Path.cwd()
    verify_frozen_bindings(root)
    if not directory.is_dir():
        raise RuntimeError("PACKET_DIRECTORY_MISSING")
    expected_names = {packet_filename(i) for i in DEV_INDICES} | {"manifest.json", "provenance.json"}
    actual_names = {p.name for p in directory.iterdir() if p.is_file()}
    if actual_names != expected_names:
        raise RuntimeError("PACKET_DIRECTORY_FILE_SET_MISMATCH")
    manifest_path = directory / "manifest.json"
    manifest = _load(manifest_path)
    provenance = _load(directory / "provenance.json")
    if manifest.get("producer_contract_sha256") != CONTRACT_SHA256 or manifest.get("indices") != list(DEV_INDICES):
        raise RuntimeError("MANIFEST_CONTRACT_OR_INDEX_MISMATCH")
    if int(manifest.get("attempted_count", -1)) != 32 or not bool(manifest.get("no_replacement")):
        raise RuntimeError("MANIFEST_ALL32_NO_REPLACEMENT_MISMATCH")
    if int(manifest.get("minimum_final_qualified", -1)) != MIN_FINAL_QUALIFIED or int(manifest.get("anchor_cycle", -1)) != ANCHOR_CYCLE:
        raise RuntimeError("MANIFEST_QUALIFICATION_OR_ANCHOR_MISMATCH")
    if manifest.get("experiment_id") != "fbfeb9e9-4850-46c7-ad13-326cbe8da380" or manifest.get("prediction_id") != "d3208f84-ad00-47e3-ad77-c6a320e08c2d":
        raise RuntimeError("MANIFEST_SUCCESSOR_IDENTITY_MISMATCH")
    packet_names = {packet_filename(i) for i in DEV_INDICES}
    if set(manifest.get("packet_sha256_by_filename", {})) != packet_names:
        raise RuntimeError("MANIFEST_PACKET_HASH_KEYSET_MISMATCH")
    if provenance.get("contract_sha256") != CONTRACT_SHA256 or provenance.get("review_sha256") != REVIEW_SHA256 or provenance.get("protocol_sha256") != PROTOCOL_SHA256:
        raise RuntimeError("AGGREGATE_PROVENANCE_MISMATCH")
    if provenance.get("packet_manifest_sha256") != sha256_file(manifest_path):
        raise RuntimeError("AGGREGATE_MANIFEST_HASH_MISMATCH")
    if int(provenance.get("model_calls_during_engineering", -1)) != 0 or int(provenance.get("environment_execution_during_engineering", -1)) != 0 or provenance.get("scientific_outcomes_accessed_during_engineering") is not False:
        raise RuntimeError("ENGINEERING_ISOLATION_PROVENANCE_MISMATCH")
    dev_rows = development_manifest(root)
    row_by_index = {int(r["frozen_index"]): r for r in dev_rows}
    packets = []
    for idx in DEV_INDICES:
        path = directory / packet_filename(idx)
        expected_hash = manifest["packet_sha256_by_filename"].get(path.name)
        if expected_hash != sha256_file(path):
            raise RuntimeError(f"PACKET_FILE_HASH_MISMATCH:{idx}")
        packet = _load(path)
        if int(packet["frozen_index"]) != idx:
            raise RuntimeError("PACKET_FILENAME_INDEX_MISMATCH")
        frozen_row = row_by_index[idx]
        if packet.get("family") != frozen_row.get("family") or packet.get("game_path") != frozen_row.get("game_path"):
            raise RuntimeError("PACKET_FROZEN_COHORT_IDENTITY_MISMATCH")
        validate_packet(packet, tokenizer)
        packets.append(packet)
    eligible_order = sorted((p for p in packets if p["trajectory_eligible"]), key=unrelated_ordering_key)
    for p in packets:
        cp = p["control_provenance"]
        if p["trajectory_eligible"] and len(eligible_order) >= 2:
            donor = unrelated_donor_for(p, eligible_order)
            if donor is None:
                if p["qualified"]:
                    raise RuntimeError("QUALIFIED_WITHOUT_DIFFERENT_FAMILY_DONOR")
                continue
            if cp.get("unrelated_donor_frozen_index") != int(donor["frozen_index"]):
                raise RuntimeError("UNRELATED_DONOR_INDEX_MISMATCH")
            if cp.get("unrelated_donor_ordering_key") != unrelated_ordering_key(donor):
                raise RuntimeError("UNRELATED_DONOR_ORDERING_KEY_MISMATCH")
            if p["qualified"] and tokenizer is not None:
                slots = build_condition_slots(tokenizer, p, str(donor["plan_text"]), anchor_cycle=ANCHOR_CYCLE)
                hashes = {name: sha256_json(list(slots[name])) for name in CONDITIONS}
                if hashes != cp["condition_slot_token_ids_sha256_by_condition"]:
                    raise RuntimeError("CONTROL_SLOT_HASH_MISMATCH")
                if any(len(v) != PLAN_SLOT_TOKENS for v in slots.values()):
                    raise RuntimeError("CONTROL_SLOT_LENGTH_MISMATCH")
        else:
            if p["qualified"]:
                raise RuntimeError("QUALIFIED_OUTSIDE_VALID_FROZEN_E")
    q = sum(bool(p["qualified"]) for p in packets)
    e = sum(bool(p["trajectory_eligible"]) for p in packets)
    if manifest.get("final_qualified_count") != q or manifest.get("trajectory_eligible_count") != e:
        raise RuntimeError("MANIFEST_COUNT_MISMATCH")
    expected_label = None if q >= MIN_FINAL_QUALIFIED else "INCONCLUSIVE_INSUFFICIENT_NATURAL_TRAJECTORIES"
    if manifest.get("below_minimum_label") != expected_label:
        raise RuntimeError("MINIMUM_QUALIFICATION_LABEL_MISMATCH")
    return {"attempted": 32, "trajectory_eligible": e, "qualified": q, "below_minimum_label": expected_label}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    result = validate_packet_directory(Path(args.directory), tokenizer=None, root=Path(args.root).resolve())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
