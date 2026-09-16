#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import localcontinuation_controls_v2 as controls
import localcontinuation_packet_builder_v1 as v1pb
import replay_residual_natural_packet_producer_v2_1 as v21
import replay_residual_sanity_protocol_v1 as sp

FINAL_PREREG_REL = Path("results/design/plancarry_localcontinuation_v2_final_prereg_v1_20260824.json")
FINAL_PREREG_SHA256 = "73aa5277b7fb20bcaebd5963e82cd62553b60b0a1bb975e8e223e0e4c1e8a716"
CONTROL_CONTRACT_REL = Path("results/design/plancarry_localcontinuation_v2_constructible_control_contract_v1_20260824.json")
CONTROL_CONTRACT_SHA256 = "8511bf400e5032920440485ca8d1d32b64299082f386663b2d0d23cb8f6dbf8c"
FINAL_REVIEW_REL = Path("results/design/plancarry_localcontinuation_v2_token_freeze_post_guard_repair_independent_review_a4_20260824.json")
FINAL_REVIEW_SHA256 = "05c16eeb150f40ccc93edee81ce1b98be483c303382c33fcbce96e07aa9e1de6"
STATIC_AUDIT_REL = Path("results/design/plancarry_localcontinuation_v2_final_prereg_static_audit_v1_20260824.json")
STATIC_AUDIT_SHA256 = "e246cd9f33443c6a5a1fb2917b0066c6ee2a9c1a6bdc79be5b140c2f0c048f51"
MATERIALIZATION_AUDIT_REL = Path("results/design/plancarry_localcontinuation_v2_token_materialization_repair_a2_20260824.json")
MATERIALIZATION_AUDIT_SHA256 = "64c1c5cdf701b51a322f0a60b4df1bb0e68b133884224faaa6653d69fa3046da"
TOKEN_TEST_REL = Path("results/design/test_plancarry_localcontinuation_v2_token_materialization_v1.py")
TOKEN_TEST_SHA256 = "38fc49adc4a50cadd26c3f97b664e6c6664e2df6327cf651b6d7587bb07cdcdd"
POPULATION_REL = Path("results/design/plancarry_localcontinuation_v2_fresh_population_v1_20260824.json")
POPULATION_SHA256 = "59a4d79bceff17700411753828fe58b36826cc723557fd0b171a367c352d1b18"
CONTROLS_SHA256 = "c93bc0b76110a88eb54dfc0b0d2ea63f13b515140b68e927c12da2f495ec0367"
V1_PACKET_BUILDER_SHA256 = "116c213d27af987e782e463bc0317d8d443e95bf1ba571dbba0386d63d109128"
V1_VALIDATOR_SHA256 = "93390667e19302087f6b3d1a583f00ee4b97232443a4955aa2f1ca2a773fcbda"
V1_PHASE_RUNNER_SHA256 = "81a55589f68e1b8d53110ad64eceacb7cfc52a0838166b5241b34fb7fb11783d"
V1_PROTOCOL_SHA256 = "9af0d247e8bb9cb5e17d11727008d827dab0c088d5c28142726be20cd2d883ef"
V1_SESSION_SHA256 = "585e44ec5cd2395be0804b865de85ac36c5db79117cf4061566cf16a9749e3b6"
V21_PRODUCER_SHA256 = "bb05eb8b3b02f15d32f768212730712f2f0a04062729a57ca4993be2031dec55"
ALFWORLD_RUNTIME_SHA256 = "53e550f70711a3779409c565ecbd3e2fd971751a03633dad3566d5569a6fb3c6"
TEXTWORLD_COMPAT_SHA256 = "cee3c3818b5856507179dd9f5c5c819260d1cd51c746faa012c612f79bf2fc83"

PHASE_RANGES = {
    "development": tuple(range(0, 32)),
    "confirmation": tuple(range(32, 52)),
    "reserve_replication": tuple(range(52, 64)),
}
PHASE_LABEL = {"development": "development", "confirmation": "confirmation", "reserve_replication": "reserve"}
MIN_STAGE2 = {"development": 16, "confirmation": 15, "reserve_replication": 10}
REFERENCE_ACTIONS_REQUIRED = 5
CUT_AFTER_ACTION = 2
PACKET_CONTRACT = "PLANCARRY_LOCALCONTINUATION_REFERENCE_PACKET_V2"

class V2PacketError(RuntimeError):
    pass


def sha_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_json(value: Any) -> str:
    return controls.sha_json(value)


def verify_bindings(root: str | Path = ".") -> None:
    root = Path(root)
    required = {
        root / FINAL_PREREG_REL: FINAL_PREREG_SHA256,
        root / CONTROL_CONTRACT_REL: CONTROL_CONTRACT_SHA256,
        root / FINAL_REVIEW_REL: FINAL_REVIEW_SHA256,
        root / STATIC_AUDIT_REL: STATIC_AUDIT_SHA256,
        root / MATERIALIZATION_AUDIT_REL: MATERIALIZATION_AUDIT_SHA256,
        root / TOKEN_TEST_REL: TOKEN_TEST_SHA256,
        root / POPULATION_REL: POPULATION_SHA256,
        root / "localcontinuation_controls_v2.py": CONTROLS_SHA256,
        root / "localcontinuation_packet_builder_v1.py": V1_PACKET_BUILDER_SHA256,
        root / "localcontinuation_validator_v1.py": V1_VALIDATOR_SHA256,
        root / "localcontinuation_phase_runner_v1.py": V1_PHASE_RUNNER_SHA256,
        root / "replay_residual_sanity_protocol_v1.py": V1_PROTOCOL_SHA256,
        root / "replay_residual_t1_session_runtime_v1.py": V1_SESSION_SHA256,
        root / "replay_residual_natural_packet_producer_v2_1.py": V21_PRODUCER_SHA256,
        root / "alfworld_runtime.py": ALFWORLD_RUNTIME_SHA256,
        root / "textworld_py313_compat.py": TEXTWORLD_COMPAT_SHA256,
    }
    for path, expected in required.items():
        if not path.is_file():
            raise V2PacketError(f"FROZEN_BINDING_MISSING:{path}")
        got = sha_file(path)
        if got != expected:
            raise V2PacketError(f"FROZEN_BINDING_DRIFT:{path}:{got}:{expected}")


def family_from_game_path(game_path: str) -> str:
    return v1pb.family_from_game_path(game_path)


def _selected_rows(root: str | Path = ".") -> list[dict[str, Any]]:
    verify_bindings(root)
    data = json.loads((Path(root) / POPULATION_REL).read_text())
    rows = [dict(x) for x in data["selected"]]
    if [int(x["frozen_index"]) for x in rows] != list(range(64)):
        raise V2PacketError("POPULATION_INDEX_DRIFT")
    if len({str(x["game_path"]) for x in rows}) != 64:
        raise V2PacketError("POPULATION_DUPLICATE_PATH")
    for row in rows:
        row["family"] = family_from_game_path(str(row["game_path"]))
    return rows


def load_population_phase(phase: str, root: str | Path = ".") -> list[dict[str, Any]]:
    if phase not in PHASE_RANGES:
        raise V2PacketError(f"UNKNOWN_PHASE:{phase}")
    by_index = {int(x["frozen_index"]): x for x in _selected_rows(root)}
    rows = [dict(by_index[i]) for i in PHASE_RANGES[phase]]
    if any(str(row["phase"]) != PHASE_LABEL[phase] for row in rows):
        raise V2PacketError("POPULATION_PHASE_LABEL_DRIFT")
    return rows


def local_stage1_eligibility_v2(
    tokenizer: Any,
    plan_text: str,
    actions: Sequence[Mapping[str, Any]],
    runtime_errors: Sequence[Any],
    open_tag_ids: Sequence[int] | None = None,
    close_tag_ids: Sequence[int] | None = None,
) -> tuple[bool, list[str], dict[str, Any] | None]:
    base_ok, reasons = v1pb.local_stage1_eligibility(bool(plan_text), actions, runtime_errors)
    reasons = list(reasons)
    guard: dict[str, Any] | None = None
    if base_ok:
        try:
            guard = controls.stage1_constructibility_guard(
                tokenizer,
                str(plan_text),
                actions,
                open_tag_ids,
                close_tag_ids,
            )
        except Exception as exc:
            reasons.append(f"V2_CONTROL_CONSTRUCTIBILITY_FAILED:{type(exc).__name__}:{exc}")
    return (not reasons), reasons, guard


def stored_stage1_eligibility_v2(packet: Mapping[str, Any]) -> tuple[bool, list[str]]:
    plan_text = str(packet.get("plan_text", ""))
    actions = list(packet.get("actions", []))
    runtime_errors = list(packet.get("stage1_runtime_errors", []))
    base_ok, reasons = v1pb.local_stage1_eligibility(bool(plan_text), actions, runtime_errors)
    reasons = list(reasons)
    if base_ok:
        try:
            controls.validate_stage1_materialization_provenance(
                packet.get("v2_control_constructibility_provenance", {}),
                plan_text,
                actions,
            )
        except Exception as exc:
            reasons.append(f"V2_STORED_MATERIALIZATION_INVALID:{type(exc).__name__}:{exc}")
    return (not reasons), reasons

def _base(row: Mapping[str, Any], provenance: Mapping[str, Any], phase: str) -> dict[str, Any]:
    packet = v21._packet_base(row, provenance)
    packet.update(
        {
            "localcontinuation_packet_contract": PACKET_CONTRACT,
            "phase": phase,
            "final_prereg_sha256": FINAL_PREREG_SHA256,
            "control_contract_sha256": CONTROL_CONTRACT_SHA256,
            "final_review_sha256": FINAL_REVIEW_SHA256,
            "static_audit_sha256": STATIC_AUDIT_SHA256,
            "materialization_audit_sha256": MATERIALIZATION_AUDIT_SHA256,
            "token_materialization_test_sha256": TOKEN_TEST_SHA256,
            "population_manifest_sha256": POPULATION_SHA256,
            "v2_controls_source_sha256": CONTROLS_SHA256,
            "v1_packet_builder_source_sha256": V1_PACKET_BUILDER_SHA256,
            "v1_phase_runner_source_sha256": V1_PHASE_RUNNER_SHA256,
            "v1_protocol_source_sha256": V1_PROTOCOL_SHA256,
            "v1_session_source_sha256": V1_SESSION_SHA256,
            "producer_source_sha256": V21_PRODUCER_SHA256,
            "task_success_required": False,
            "reference_action_count_required": REFERENCE_ACTIONS_REQUIRED,
            "cut_after_action": CUT_AFTER_ACTION,
            "stage1_runtime_errors": [],
            "v2_control_constructibility_provenance": None,
        }
    )
    return packet


def produce_stage1_attempt(
    row: Mapping[str, Any],
    phase: str,
    tokenizer: Any,
    model_provenance: Mapping[str, Any],
    runtime_factory: Callable[[str], Any],
    planner_fn: Callable[[str, str], Any],
    command_score_fn: Callable[[Sequence[int], Sequence[int]], float],
    open_tag_ids: Sequence[int],
    close_tag_ids: Sequence[int],
) -> dict[str, Any]:
    if int(row["frozen_index"]) not in PHASE_RANGES[phase]:
        raise V2PacketError("ROW_OUTSIDE_PHASE")
    packet = _base(row, model_provenance, phase)
    runtime = None
    errors: list[str] = []
    planner = None
    try:
        runtime = runtime_factory(str(row["game_path"]))
        packet["initial_observation"] = str(runtime.observation)
        packet["task_instruction"] = v21.extract_task_instruction(packet["initial_observation"])
        planner = planner_fn(packet["task_instruction"], packet["initial_observation"])
        accepted, count = v21.accept_plan_new_ids(tokenizer, planner.new_ids)
        if accepted != planner.plan_text or count != planner.complete_block_token_count:
            raise RuntimeError("PLANNER_RESULT_ACCEPTANCE_MISMATCH")
        packet["plan_text"] = planner.plan_text
        packet["plan_provenance"] = v21.plan_provenance(tokenizer, planner)
        packet["prompt_provenance"] = v21.prompt_provenance_for_planner(planner)
        for step in range(1, v21.ACTION_BUDGET + 1):
            if bool(runtime.done) or bool(runtime.won):
                break
            commands = sorted(str(x) for x in runtime.admissible_commands)
            choice = v21.choose_admissible_command(
                tokenizer,
                packet["task_instruction"],
                planner.plan_text,
                packet["actions"],
                str(runtime.observation),
                commands,
                command_score_fn,
            )
            was_admissible = choice.command in commands
            if not was_admissible:
                raise RuntimeError("CHOICE_NOT_CURRENT_ADMISSIBLE_COMMAND")
            pre_state = str(runtime.hash())
            record = runtime.step(choice.command)
            action = v21.action_row(step, choice, pre_state, record, commands)
            action["accepted"] = record.error is None
            action["was_admissible"] = bool(was_admissible)
            packet["actions"].append(action)
            if record.error:
                errors.append(str(record.error))
                break
        packet["success"] = bool(getattr(runtime, "won", False))
    except Exception as exc:
        errors.append(f"{type(exc).__name__}:{exc}")
        if not packet.get("plan_provenance"):
            packet["plan_provenance"] = v21.plan_provenance(tokenizer, planner)
    finally:
        if runtime is not None:
            try:
                runtime.close()
            except Exception:
                pass
    packet["stage1_runtime_errors"] = list(errors)
    eligible, reasons, guard = local_stage1_eligibility_v2(
        tokenizer,
        str(packet.get("plan_text", "")),
        packet.get("actions", []),
        errors,
        open_tag_ids,
        close_tag_ids,
    )
    packet["trajectory_eligible"] = bool(eligible)
    packet["qualification_stage1_reasons"] = reasons
    packet["v2_control_constructibility_provenance"] = guard
    packet["qualified"] = False
    packet["qualification_stage2_reasons"] = ["STAGE2_NOT_RUN"]
    packet["trajectory_sha256"] = sp.trajectory_digest(packet)
    return packet


def _packet_binding_requirements() -> dict[str, str]:
    return {
        "localcontinuation_packet_contract": PACKET_CONTRACT,
        "final_prereg_sha256": FINAL_PREREG_SHA256,
        "control_contract_sha256": CONTROL_CONTRACT_SHA256,
        "final_review_sha256": FINAL_REVIEW_SHA256,
        "static_audit_sha256": STATIC_AUDIT_SHA256,
        "materialization_audit_sha256": MATERIALIZATION_AUDIT_SHA256,
        "token_materialization_test_sha256": TOKEN_TEST_SHA256,
        "population_manifest_sha256": POPULATION_SHA256,
        "v2_controls_source_sha256": CONTROLS_SHA256,
        "v1_packet_builder_source_sha256": V1_PACKET_BUILDER_SHA256,
        "v1_phase_runner_source_sha256": V1_PHASE_RUNNER_SHA256,
        "v1_protocol_source_sha256": V1_PROTOCOL_SHA256,
        "v1_session_source_sha256": V1_SESSION_SHA256,
        "producer_source_sha256": V21_PRODUCER_SHA256,
    }


def validate_reference_packet(
    packet: Mapping[str, Any],
    phase: str,
    tokenizer: Any | None = None,
    open_tag_ids: Sequence[int] | None = None,
    close_tag_ids: Sequence[int] | None = None,
    root: str | Path = ".",
) -> None:
    rows = {int(x["frozen_index"]): x for x in load_population_phase(phase, root)}
    idx = int(packet.get("frozen_index", -1))
    if idx not in rows:
        raise V2PacketError("PACKET_PHASE_INDEX_LEAK")
    expected = rows[idx]
    if str(packet.get("game_path")) != str(expected["game_path"]):
        raise V2PacketError("PACKET_MANIFEST_PATH_MISMATCH")
    if str(packet.get("family")) != str(expected["family"]):
        raise V2PacketError("PACKET_MANIFEST_FAMILY_MISMATCH")
    for key, value in _packet_binding_requirements().items():
        if packet.get(key) != value:
            raise V2PacketError(f"PACKET_BINDING_MISMATCH:{key}")
    eligible, reasons = stored_stage1_eligibility_v2(packet)
    if bool(packet.get("trajectory_eligible")) != eligible or list(packet.get("qualification_stage1_reasons", [])) != reasons:
        raise V2PacketError("PACKET_STAGE1_STORED_RECLASSIFICATION_MISMATCH")
    if packet.get("task_success_required") is not False:
        raise V2PacketError("TASK_SUCCESS_MUST_NOT_GATE")
    if packet.get("trajectory_sha256") != sp.trajectory_digest(dict(packet)):
        raise V2PacketError("TRAJECTORY_HASH_MISMATCH")

def apply_stage2_phase(
    tokenizer: Any,
    packets: Sequence[dict[str, Any]],
    phase: str,
    neutral_filler_ids: Sequence[int],
    open_tag_ids: Sequence[int] | None = None,
    close_tag_ids: Sequence[int] | None = None,
    root: str | Path = ".",
) -> list[dict[str, Any]]:
    controls.verify_neutral_filler_ids(neutral_filler_ids)
    expected_indices = list(PHASE_RANGES[phase])
    if [int(p.get("frozen_index", -1)) for p in packets] != expected_indices:
        raise V2PacketError(f"STAGE2_REQUIRES_COMPLETE_PHASE_E:{phase}")
    # No semantic tokenizer call is permitted from this point onward. The
    # tokenizer/open/close arguments are retained only for API compatibility.
    for packet in packets:
        validate_reference_packet(packet, phase, None, None, None, root)
    eligible = v21.frozen_eligible_order(packets)
    e_indices = [int(x["frozen_index"]) for x in eligible]
    e_sha = sha_json(e_indices)
    result = [dict(p) for p in packets]
    by_index = {int(p["frozen_index"]): p for p in result}
    if len(eligible) < 2:
        for packet in result:
            packet["qualified"] = False
            packet["qualification_stage2_reasons"] = ["FROZEN_E_SIZE_LT_2"]
            packet["frozen_E_indices_sha256"] = e_sha
        return result
    for source in eligible:
        packet = by_index[int(source["frozen_index"])]
        packet["frozen_E_indices_sha256"] = e_sha
        donor = v21.unrelated_donor_for(source, eligible)
        if donor is None:
            packet["qualified"] = False
            packet["qualification_stage2_reasons"] = ["NO_DIFFERENT_FAMILY_DONOR_IN_FROZEN_E"]
            continue
        try:
            slots, meta = controls.build_semantic_slots(
                packet,
                donor,
                neutral_filler_ids,
            )
            packet["control_provenance"] = {
                **meta,
                "unrelated_donor_frozen_index": int(donor["frozen_index"]),
                "unrelated_donor_ordering_key": v21.unrelated_ordering_key(donor),
                "anchor_cycle": CUT_AFTER_ACTION,
                "frozen_E_indices": e_indices,
                "frozen_E_indices_sha256": e_sha,
                "control_contract_sha256": CONTROL_CONTRACT_SHA256,
                "controls_source_sha256": CONTROLS_SHA256,
                "stage2_semantic_tokenizer_calls": 0,
            }
            packet["qualified"] = True
            packet["qualification_stage2_reasons"] = []
        except Exception as exc:
            packet["qualified"] = False
            packet["qualification_stage2_reasons"] = [f"CONTROL_CONSTRUCTION_FAILED:{type(exc).__name__}:{exc}"]
    for packet in result:
        packet.setdefault("frozen_E_indices_sha256", e_sha)
        if not packet.get("trajectory_eligible"):
            packet["qualified"] = False
            packet["qualification_stage2_reasons"] = ["NOT_IN_FROZEN_TRAJECTORY_ELIGIBLE_E"]
    return result

def validate_phase_packets(
    packets: Sequence[Mapping[str, Any]],
    phase: str,
    tokenizer: Any,
    open_tag_ids: Sequence[int],
    close_tag_ids: Sequence[int],
    root: str | Path = ".",
) -> dict[str, Any]:
    expected = list(PHASE_RANGES[phase])
    if [int(p.get("frozen_index", -1)) for p in packets] != expected:
        raise V2PacketError("PACKET_SET_INDEX_MISMATCH")
    for packet in packets:
        validate_reference_packet(packet, phase, tokenizer, open_tag_ids, close_tag_ids, root)
    return {
        "phase": phase,
        "attempted_count": len(packets),
        "trajectory_eligible_count": sum(bool(p.get("trajectory_eligible")) for p in packets),
        "stage2_qualified_count": sum(bool(p.get("qualified")) for p in packets),
        "minimum_stage2_qualified": MIN_STAGE2[phase],
    }
