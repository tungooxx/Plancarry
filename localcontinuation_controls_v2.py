#!/usr/bin/env python3
from __future__ import annotations

import collections
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import replay_residual_natural_packet_producer_v2_1 as v21
import replay_residual_sanity_protocol_v1 as sp

SLOT_TOKENS = 128
MAX_SEMANTIC_CONTENT_TOKENS = 96
PAST_ACTION_PREFIX_TOKENS = 40
# Frozen prospectively at implementation from the already tokenizer-audited
# Qwen3 newline ID present in the v0.2 token-native constants.
PAST_ACTION_SEPARATOR_IDS = (198,)
NEUTRAL_FILLER_PRIMITIVE_TEXT = " neutral context remains unchanged."
NEUTRAL_FILLER_PRIMITIVE_IDS = (20628, 2266, 8458, 34857, 13)
NEUTRAL_FILLER_IDS = (20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458, 34857, 13, 20628, 2266, 8458)
NEUTRAL_FILLER_IDS_SHA256 = "557e30342fe6309165f388724a14895474db6d7ef82e4a3679c4459f4f7ae287"
NEUTRAL_FILLER_PRIMITIVE_TEXT_UTF8_SHA256 = "4916bbd15671511ba355d30e8320b245e9315dc622eeb795e9792215e4d4b002"
PAST_ACTION_SEPARATOR_IDS_SHA256 = "840d60afcf8aeb607ff32e9b4fba7e3132722c2148136c5f4e4816fec59f4ff3"

SCIENCE_CONDITIONS = (
    "PLAN_PRESENT",
    "NEUTRAL_FILLER",
    "PLAN_BLOCK_DERANGED",
    "UNRELATED_PLAN",
    "PAST_ACTIONS_ONLY",
    "NEXT_ACTION_PRESERVED_LATE_NULL",
)

CAUSAL_ARMS = (
    "ACTIVE_PLAN_RESIDUAL",
    "NO_PATCH",
    "ZERO_ADD",
    "SELF_REPLACE",
    "RANDOM_EQ_NORM",
    "NEXT_ACTION_PRESERVED_LATE_NULL",
    "UNRELATED_PLAN",
    "PLAN_BLOCK_DERANGED",
    "PAST_ACTIONS_ONLY",
    "VISIBLE_TEXT_PLAN",
)

SPECIFICITY_MAX_CONTROLS = (
    "RANDOM_EQ_NORM",
    "NEXT_ACTION_PRESERVED_LATE_NULL",
    "UNRELATED_PLAN",
    "PLAN_BLOCK_DERANGED",
    "PAST_ACTIONS_ONLY",
)

class V2ControlError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _ids(values: Sequence[int]) -> list[int]:
    return [int(x) for x in values]


def verify_neutral_filler_ids(filler_ids: Sequence[int]) -> list[int]:
    vals = _ids(filler_ids)
    if len(vals) != SLOT_TOKENS:
        raise V2ControlError(f"NEUTRAL_FILLER_LENGTH:{len(vals)}")
    got = sha_json(vals)
    if got != NEUTRAL_FILLER_IDS_SHA256:
        raise V2ControlError(f"NEUTRAL_FILLER_SHA256:{got}")
    return vals


def _make_slot_ids_unchecked(content_ids: Sequence[int], filler_ids: Sequence[int]) -> list[int]:
    content = _ids(content_ids)
    filler = _ids(filler_ids)
    if len(filler) != SLOT_TOKENS:
        raise V2ControlError("FILLER_MUST_HAVE_128_IDS")
    if len(content) > MAX_SEMANTIC_CONTENT_TOKENS:
        raise V2ControlError(f"CONTENT_GT96:{len(content)}")
    out = content + filler[: SLOT_TOKENS - len(content)]
    if len(out) != SLOT_TOKENS or out[: len(content)] != content:
        raise V2ControlError("EXACT128_SLOT_POSTCONDITION")
    return out


def make_slot_ids(content_ids: Sequence[int], neutral_filler_ids: Sequence[int]) -> list[int]:
    return _make_slot_ids_unchecked(content_ids, verify_neutral_filler_ids(neutral_filler_ids))


def balanced_block_rotate(interior_ids: Sequence[int]) -> tuple[list[int], dict[str, Any]]:
    x = _ids(interior_ids)
    n = len(x)
    if n < 2:
        raise V2ControlError("INTERIOR_TOO_SHORT")
    k = 4 if n >= 8 else 2
    q, r = divmod(n, k)
    sizes = [q + (1 if i < r else 0) for i in range(k)]
    blocks: list[list[int]] = []
    j = 0
    for size in sizes:
        blocks.append(x[j : j + size])
        j += size
    order = list(range(1, k)) + [0]
    out = [token for block_index in order for token in blocks[block_index]]
    return out, {"method": "BALANCED_BLOCK_LEFT_ROTATE", "offset": None, "order": order, "sizes": sizes}


def strong_interior_derangement(interior_ids: Sequence[int]) -> tuple[list[int], dict[str, Any]]:
    x = _ids(interior_ids)
    n = len(x)
    if n < 2:
        raise V2ControlError("INTERIOR_TOO_SHORT")
    if len(set(x)) < 2:
        raise V2ControlError("INTERIOR_ALL_EQUAL")
    primary, meta = balanced_block_rotate(x)
    if primary != x and primary[-1] != x[-1]:
        return primary, meta
    for offset in range(1, n):
        candidate = x[offset:] + x[:offset]
        if candidate != x and candidate[-1] != x[-1]:
            return candidate, {
                "method": "SMALLEST_VALID_LEFT_ROTATION",
                "offset": offset,
                "order": None,
                "sizes": None,
            }
    raise V2ControlError("NO_VALID_DERANGEMENT")


def plan_block_deranged(
    tagged_plan_ids: Sequence[int], open_tag_ids: Sequence[int], close_tag_ids: Sequence[int]
) -> tuple[list[int], dict[str, Any]]:
    ids = _ids(tagged_plan_ids)
    op = _ids(open_tag_ids)
    cl = _ids(close_tag_ids)
    if not op or not cl:
        raise V2ControlError("EMPTY_TAG_SPAN")
    if ids[: len(op)] != op or ids[-len(cl) :] != cl:
        raise V2ControlError("TAG_SPAN_MISMATCH")
    if len(ids) < len(op) + len(cl) + 2:
        raise V2ControlError("INTERIOR_TOO_SHORT")
    interior = ids[len(op) : len(ids) - len(cl)]
    transformed, meta = strong_interior_derangement(interior)
    out = op + transformed + cl
    if out[: len(op)] != op or out[-len(cl) :] != cl:
        raise V2ControlError("TAG_SPAN_MOVED")
    if len(out) != len(ids) or collections.Counter(out) != collections.Counter(ids):
        raise V2ControlError("TOKEN_MULTISET_OR_COUNT_CHANGED")
    if transformed == interior:
        raise V2ControlError("DERANGEMENT_VALUE_IDENTICAL")
    if transformed[-1] == interior[-1]:
        raise V2ControlError("RIGHTMOST_INTERIOR_UNCHANGED")
    meta = dict(meta)
    meta.update(
        {
            "open_tag_len": len(op),
            "close_tag_len": len(cl),
            "interior_len": len(interior),
            "source_ids_sha256": sha_json(ids),
            "deranged_ids_sha256": sha_json(out),
        }
    )
    return out, meta


def past_actions_only_content(action1_ids: Sequence[int], action2_ids: Sequence[int]) -> list[int]:
    out = _ids(action1_ids)[:PAST_ACTION_PREFIX_TOKENS] + list(PAST_ACTION_SEPARATOR_IDS) + _ids(action2_ids)[:PAST_ACTION_PREFIX_TOKENS]
    if len(out) > MAX_SEMANTIC_CONTENT_TOKENS:
        raise V2ControlError(f"PAST_ACTIONS_ONLY_GT96:{len(out)}")
    # The frozen rule is 40 + 1 + 40 = 81 maximum.
    if len(out) > 81:
        raise V2ControlError(f"PAST_ACTIONS_ONLY_GT81:{len(out)}")
    return out


def next_action_preserved_content(action3_ids: Sequence[int]) -> list[int]:
    out = _ids(action3_ids)
    if len(out) > MAX_SEMANTIC_CONTENT_TOKENS:
        raise V2ControlError(f"ACTION3_GT96_STAGE1_INELIGIBLE:{len(out)}")
    return out


def _encode(tokenizer: Any, text: str) -> list[int]:
    return [int(x) for x in tokenizer.encode(str(text), add_special_tokens=False)]


def _tokenize_plan_once_with_offsets(tokenizer: Any, plan_text: str) -> tuple[list[int], list[tuple[int, int]]]:
    try:
        encoded = tokenizer(
            str(plan_text),
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
    except Exception as exc:
        raise V2ControlError(f"PLAN_OFFSET_TOKENIZATION_FAILED:{type(exc).__name__}:{exc}") from exc
    try:
        ids = [int(x) for x in encoded["input_ids"]]
        offsets = [(int(a), int(b)) for a, b in encoded["offset_mapping"]]
    except Exception as exc:
        raise V2ControlError(f"PLAN_OFFSET_TOKENIZATION_MALFORMED:{type(exc).__name__}:{exc}") from exc
    if len(ids) != len(offsets):
        raise V2ControlError("PLAN_IDS_OFFSETS_LENGTH_MISMATCH")
    return ids, offsets


def _plan_literal_spans(plan_text: str) -> tuple[int, int]:
    match = re.fullmatch(r"(<PLAN>)(.*?)(</PLAN>)", str(plan_text), re.IGNORECASE | re.DOTALL)
    if match is None:
        raise V2ControlError("PLAN_FULLMATCH_FAILED")
    return int(match.end(1)), int(match.start(3))


def derange_mutable_positions(
    source_ids: Sequence[int], mutable_positions: Sequence[int]
) -> tuple[list[int], dict[str, Any]]:
    ids = _ids(source_ids)
    mutable = [int(x) for x in mutable_positions]
    if mutable != sorted(set(mutable)):
        raise V2ControlError("MUTABLE_POSITIONS_NOT_SORTED_UNIQUE")
    if any(i < 0 or i >= len(ids) for i in mutable):
        raise V2ControlError("MUTABLE_POSITION_OUT_OF_RANGE")
    if len(mutable) < 2:
        raise V2ControlError("MUTABLE_INTERIOR_TOO_SHORT")
    values = [ids[i] for i in mutable]
    transformed, meta = strong_interior_derangement(values)
    out = list(ids)
    for i, value in zip(mutable, transformed):
        out[i] = int(value)
    frozen = [i for i in range(len(ids)) if i not in set(mutable)]
    if len(out) != len(ids) or collections.Counter(out) != collections.Counter(ids):
        raise V2ControlError("TOKEN_MULTISET_OR_COUNT_CHANGED")
    if any(out[i] != ids[i] for i in frozen):
        raise V2ControlError("FROZEN_BOUNDARY_TOKEN_MOVED")
    if transformed == values:
        raise V2ControlError("DERANGEMENT_VALUE_IDENTICAL")
    if transformed[-1] == values[-1]:
        raise V2ControlError("RIGHTMOST_MUTABLE_UNCHANGED")
    result_meta = dict(meta)
    result_meta.update(
        {
            "mutable_positions": mutable,
            "mutable_count": len(mutable),
            "frozen_positions": frozen,
            "source_ids_sha256": sha_json(ids),
            "deranged_ids_sha256": sha_json(out),
            "mutable_source_ids_sha256": sha_json(values),
            "mutable_deranged_ids_sha256": sha_json(transformed),
        }
    )
    return out, result_meta


def materialize_plan_tokens(tokenizer: Any, plan_text: str) -> dict[str, Any]:
    open_end, close_start = _plan_literal_spans(plan_text)
    ids, offsets = _tokenize_plan_once_with_offsets(tokenizer, plan_text)
    if len(ids) > MAX_SEMANTIC_CONTENT_TOKENS:
        raise V2ControlError(f"PLAN_PRESENT_GT96:{len(ids)}")
    mutable = [
        i
        for i, (start, end) in enumerate(offsets)
        if end > start and start >= open_end and end <= close_start
    ]
    if len(mutable) < 2:
        raise V2ControlError(f"PLAN_MUTABLE_POSITIONS_LT2:{len(mutable)}")
    mutable_values = [ids[i] for i in mutable]
    if len(set(mutable_values)) < 2:
        raise V2ControlError("PLAN_MUTABLE_VALUES_ALL_EQUAL")
    deranged, meta = derange_mutable_positions(ids, mutable)
    frozen = [i for i in range(len(ids)) if i not in set(mutable)]
    return {
        "plan_token_ids": ids,
        "plan_offsets": [[a, b] for a, b in offsets],
        "plan_mutable_positions": mutable,
        "plan_frozen_positions": frozen,
        "plan_token_ids_sha256": sha_json(ids),
        "plan_offsets_sha256": sha_json([[a, b] for a, b in offsets]),
        "plan_mutable_positions_sha256": sha_json(mutable),
        "plan_deranged_ids": deranged,
        "plan_deranged_ids_sha256": sha_json(deranged),
        "plan_open_end_char": open_end,
        "plan_close_start_char": close_start,
        "derangement": meta,
        "materialization": "ONE_ACCEPTED_PLAN_TOKENIZATION_WITH_OFFSETS_PRE_E",
    }


def validate_plan_materialization_stored(plan_text: str, materialization: Mapping[str, Any]) -> None:
    open_end, close_start = _plan_literal_spans(plan_text)
    ids = _ids(materialization.get("plan_token_ids", []))
    offsets = [tuple(int(v) for v in pair) for pair in materialization.get("plan_offsets", [])]
    mutable = [int(x) for x in materialization.get("plan_mutable_positions", [])]
    frozen = [int(x) for x in materialization.get("plan_frozen_positions", [])]
    deranged = _ids(materialization.get("plan_deranged_ids", []))
    if len(ids) > MAX_SEMANTIC_CONTENT_TOKENS or len(ids) != len(offsets):
        raise V2ControlError("STORED_PLAN_IDS_OFFSETS_INVALID")
    expected_mutable = [
        i for i, (start, end) in enumerate(offsets)
        if end > start and start >= open_end and end <= close_start
    ]
    if mutable != expected_mutable:
        raise V2ControlError("STORED_PLAN_MUTABLE_POSITIONS_MISMATCH")
    expected_frozen = [i for i in range(len(ids)) if i not in set(mutable)]
    if frozen != expected_frozen:
        raise V2ControlError("STORED_PLAN_FROZEN_POSITIONS_MISMATCH")
    if len(mutable) < 2 or len({ids[i] for i in mutable}) < 2:
        raise V2ControlError("STORED_PLAN_MUTABLE_UNCONSTRUCTIBLE")
    rebuilt, meta = derange_mutable_positions(ids, mutable)
    if deranged != rebuilt:
        raise V2ControlError("STORED_PLAN_DERANGEMENT_MISMATCH")
    checks = {
        "plan_token_ids_sha256": sha_json(ids),
        "plan_offsets_sha256": sha_json([[a, b] for a, b in offsets]),
        "plan_mutable_positions_sha256": sha_json(mutable),
        "plan_deranged_ids_sha256": sha_json(deranged),
    }
    for key, expected in checks.items():
        if materialization.get(key) != expected:
            raise V2ControlError(f"STORED_PLAN_HASH_MISMATCH:{key}")
    if int(materialization.get("plan_open_end_char", -1)) != open_end or int(materialization.get("plan_close_start_char", -1)) != close_start:
        raise V2ControlError("STORED_PLAN_CHAR_BOUNDARY_MISMATCH")
    if materialization.get("derangement", {}).get("deranged_ids_sha256") != meta["deranged_ids_sha256"]:
        raise V2ControlError("STORED_PLAN_DERANGEMENT_META_MISMATCH")


def validate_stage1_materialization_provenance(
    provenance: Mapping[str, Any], plan_text: str, actions: Sequence[Mapping[str, Any]]
) -> None:
    if len(actions) < 3:
        raise V2ControlError("REFERENCE_ACTION_COUNT_LT3_FOR_CONTROLS")
    plan = provenance.get("plan")
    action_data = provenance.get("actions")
    if not isinstance(plan, Mapping) or not isinstance(action_data, Mapping):
        raise V2ControlError("STORED_STAGE1_MATERIALIZATION_MISSING")
    validate_plan_materialization_stored(plan_text, plan)
    for step in (1, 2, 3):
        ids = _ids(action_data.get(f"action{step}_ids", []))
        if action_data.get(f"action{step}_command") != str(actions[step - 1].get("command", "")):
            raise V2ControlError(f"STORED_ACTION{step}_COMMAND_MISMATCH")
        if action_data.get(f"action{step}_ids_sha256") != sha_json(ids):
            raise V2ControlError(f"STORED_ACTION{step}_HASH_MISMATCH")
        if int(action_data.get(f"action{step}_token_count", -1)) != len(ids):
            raise V2ControlError(f"STORED_ACTION{step}_COUNT_MISMATCH")
    next_action_preserved_content(_ids(action_data.get("action3_ids", [])))
    past_actions_only_content(
        _ids(action_data.get("action1_ids", [])),
        _ids(action_data.get("action2_ids", [])),
    )


def frozen_tag_ids(tokenizer: Any) -> tuple[list[int], list[int]]:
    op = _encode(tokenizer, "<PLAN>")
    cl = _encode(tokenizer, "</PLAN>")
    if not op or not cl:
        raise V2ControlError("EMPTY_FROZEN_PLAN_TAG_IDS")
    return op, cl


def stage1_constructibility_guard(
    tokenizer: Any,
    plan_text: str,
    actions: Sequence[Mapping[str, Any]],
    open_tag_ids: Sequence[int] | None = None,
    close_tag_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    if len(actions) < 3:
        raise V2ControlError("REFERENCE_ACTION_COUNT_LT3_FOR_CONTROLS")
    plan = materialize_plan_tokens(tokenizer, plan_text)
    action_rows: dict[str, Any] = {}
    for step in (1, 2, 3):
        command = str(actions[step - 1].get("command", ""))
        ids = _encode(tokenizer, command)
        action_rows[f"action{step}_command"] = command
        action_rows[f"action{step}_ids"] = ids
        action_rows[f"action{step}_token_count"] = len(ids)
        action_rows[f"action{step}_ids_sha256"] = sha_json(ids)
    next_action_preserved_content(action_rows["action3_ids"])
    past_actions_only_content(action_rows["action1_ids"], action_rows["action2_ids"])
    result = {
        "plan": plan,
        "actions": action_rows,
        "past_action_separator_ids": list(PAST_ACTION_SEPARATOR_IDS),
        "past_action_separator_ids_sha256": sha_json(list(PAST_ACTION_SEPARATOR_IDS)),
        "neutral_filler_ids_sha256": NEUTRAL_FILLER_IDS_SHA256,
        "semantic_ids_frozen_pre_E": True,
    }
    validate_stage1_materialization_provenance(result, plan_text, actions)
    return result

def build_semantic_slots(
    packet: Mapping[str, Any],
    unrelated_packet: Mapping[str, Any],
    neutral_filler_ids: Sequence[int] = NEUTRAL_FILLER_IDS,
) -> tuple[dict[str, list[int]], dict[str, Any]]:
    filler = verify_neutral_filler_ids(neutral_filler_ids)
    source_prov = packet.get("v2_control_constructibility_provenance")
    donor_prov = unrelated_packet.get("v2_control_constructibility_provenance")
    if not isinstance(source_prov, Mapping) or not isinstance(donor_prov, Mapping):
        raise V2ControlError("STAGE2_REQUIRES_STORED_STAGE1_MATERIALIZATION")
    validate_stage1_materialization_provenance(
        source_prov,
        str(packet.get("plan_text", "")),
        list(packet.get("actions", [])),
    )
    validate_stage1_materialization_provenance(
        donor_prov,
        str(unrelated_packet.get("plan_text", "")),
        list(unrelated_packet.get("actions", [])),
    )
    source_plan = source_prov["plan"]
    source_actions = source_prov["actions"]
    donor_plan = donor_prov["plan"]
    contents = {
        "PLAN_PRESENT": _ids(source_plan["plan_token_ids"]),
        "NEUTRAL_FILLER": [],
        "PLAN_BLOCK_DERANGED": _ids(source_plan["plan_deranged_ids"]),
        "UNRELATED_PLAN": _ids(donor_plan["plan_token_ids"]),
        "PAST_ACTIONS_ONLY": past_actions_only_content(
            _ids(source_actions["action1_ids"]), _ids(source_actions["action2_ids"])
        ),
        "NEXT_ACTION_PRESERVED_LATE_NULL": next_action_preserved_content(
            _ids(source_actions["action3_ids"])
        ),
    }
    if any(len(v) > MAX_SEMANTIC_CONTENT_TOKENS for v in contents.values()):
        raise V2ControlError("STORED_SEMANTIC_CONTENT_GT96")
    slots = {name: _make_slot_ids_unchecked(contents[name], filler) for name in SCIENCE_CONDITIONS}
    if set(slots) != set(SCIENCE_CONDITIONS) or any(len(v) != SLOT_TOKENS for v in slots.values()):
        raise V2ControlError("SEMANTIC_SLOT_SET_OR_LENGTH")
    meta = {
        "condition_names": list(SCIENCE_CONDITIONS),
        "semantic_content_ids_sha256_by_condition": {k: sha_json(contents[k]) for k in SCIENCE_CONDITIONS},
        "semantic_content_token_count_by_condition": {k: len(contents[k]) for k in SCIENCE_CONDITIONS},
        "slot_ids_sha256_by_condition": {k: sha_json(slots[k]) for k in SCIENCE_CONDITIONS},
        "neutral_filler_ids_sha256": sha_json(filler),
        "past_action_separator_ids": list(PAST_ACTION_SEPARATOR_IDS),
        "past_action_separator_ids_sha256": sha_json(list(PAST_ACTION_SEPARATOR_IDS)),
        "plan_block_derangement": dict(source_plan["derangement"]),
        "source_plan_token_ids_sha256": source_plan["plan_token_ids_sha256"],
        "source_action_ids_sha256": {
            f"action{i}": source_actions[f"action{i}_ids_sha256"] for i in (1, 2, 3)
        },
        "unrelated_plan_token_ids_sha256": donor_plan["plan_token_ids_sha256"],
        "semantic_materialization": "STORED_STAGE1_IDS_ONLY_NO_SEMANTIC_DECODE_RETOKENIZE",
    }
    return slots, meta

def build_replay_ids(
    tokenizer: Any,
    packet: Mapping[str, Any],
    slot_ids: Sequence[int],
    anchor_cycle: int,
) -> tuple[list[int], dict[str, Any]]:
    slot = _ids(slot_ids)
    if len(slot) != SLOT_TOKENS:
        raise V2ControlError(f"SLOT_NOT_128:{len(slot)}")
    if anchor_cycle not in (1, 2):
        raise V2ControlError("ANCHOR_MUST_BE_T1_OR_T2")
    # Intentionally reuse only the reviewed textual prefix/suffix renderers.
    # The semantic slot itself is never decoded or jointly re-tokenized.
    prefix_ids = _encode(tokenizer, sp.replay_prefix(dict(packet)))
    suffix_ids = _encode(tokenizer, sp.replay_suffix(dict(packet), anchor_cycle))
    replay = prefix_ids + slot + suffix_ids
    provenance = {
        "anchor_cycle": int(anchor_cycle),
        "prefix_token_count": len(prefix_ids),
        "slot_token_count": SLOT_TOKENS,
        "suffix_token_count": len(suffix_ids),
        "full_token_count": len(replay),
        "slot_start_index": len(prefix_ids),
        "slot_end_index_exclusive": len(prefix_ids) + SLOT_TOKENS,
        "suffix_start_index": len(prefix_ids) + SLOT_TOKENS,
        "prefix_ids_sha256": sha_json(prefix_ids),
        "slot_ids_sha256": sha_json(slot),
        "suffix_ids_sha256": sha_json(suffix_ids),
        "full_ids_sha256": sha_json(replay),
        "serialization": "DIRECT_PREFIX_IDS_PLUS_EXACT128_SLOT_IDS_PLUS_SUFFIX_IDS_NO_SLOT_DECODE_RETOKENIZE",
    }
    return replay, provenance


def assert_condition_invariant_replay_geometry(provenance_by_condition: Mapping[str, Mapping[str, Any]]) -> None:
    if not provenance_by_condition:
        raise V2ControlError("NO_REPLAY_PROVENANCE")
    keys = ("prefix_token_count", "slot_token_count", "suffix_token_count", "full_token_count", "slot_start_index", "slot_end_index_exclusive", "suffix_start_index", "prefix_ids_sha256", "suffix_ids_sha256")
    rows = list(provenance_by_condition.values())
    baseline = tuple(rows[0].get(k) for k in keys)
    for row in rows[1:]:
        if tuple(row.get(k) for k in keys) != baseline:
            raise V2ControlError("CONDITION_REPLAY_GEOMETRY_DRIFT")


def intervention_controls_from_arms() -> list[str]:
    return [x for x in CAUSAL_ARMS if x != "ACTIVE_PLAN_RESIDUAL"]
