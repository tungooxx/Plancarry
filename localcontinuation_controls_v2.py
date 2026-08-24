#!/usr/bin/env python3
from __future__ import annotations

import collections
import hashlib
import json
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
NEUTRAL_FILLER_IDS_SHA256 = "664e74fa68bbc976ce8fcf8603f9cf5cac6a83f6f16bf5d8010622ee455b7470"
NEUTRAL_FILLER_TEXT_SHA256 = "7dee91abb637511cc64f5b6d9e190a736411358f9c5126916fa784d8be62c86a"

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


def frozen_tag_ids(tokenizer: Any) -> tuple[list[int], list[int]]:
    op = _encode(tokenizer, "<PLAN>")
    cl = _encode(tokenizer, "</PLAN>")
    if not op or not cl:
        raise V2ControlError("EMPTY_FROZEN_PLAN_TAG_IDS")
    return op, cl


def stage1_constructibility_guard(
    tokenizer: Any,
    plan_text: str,
    action3_command: str,
    open_tag_ids: Sequence[int],
    close_tag_ids: Sequence[int],
) -> dict[str, Any]:
    plan_ids = _encode(tokenizer, plan_text)
    action3_ids = _encode(tokenizer, action3_command)
    if len(plan_ids) > MAX_SEMANTIC_CONTENT_TOKENS:
        raise V2ControlError(f"PLAN_PRESENT_GT96:{len(plan_ids)}")
    next_action_preserved_content(action3_ids)
    _, meta = plan_block_deranged(plan_ids, open_tag_ids, close_tag_ids)
    return {
        "plan_content_token_count": len(plan_ids),
        "action3_token_count": len(action3_ids),
        "plan_ids_sha256": sha_json(plan_ids),
        "action3_ids_sha256": sha_json(action3_ids),
        "open_tag_ids_sha256": sha_json(_ids(open_tag_ids)),
        "close_tag_ids_sha256": sha_json(_ids(close_tag_ids)),
        "derangement_method": meta["method"],
        "derangement_offset": meta["offset"],
    }


def build_semantic_slots(
    tokenizer: Any,
    packet: Mapping[str, Any],
    unrelated_plan_text: str,
    neutral_filler_ids: Sequence[int],
    open_tag_ids: Sequence[int],
    close_tag_ids: Sequence[int],
) -> tuple[dict[str, list[int]], dict[str, Any]]:
    filler = verify_neutral_filler_ids(neutral_filler_ids)
    actions = list(packet.get("actions", []))
    if len(actions) < 3:
        raise V2ControlError("REFERENCE_ACTION_COUNT_LT3_FOR_CONTROLS")
    plan_ids = _encode(tokenizer, str(packet.get("plan_text", "")))
    unrelated_ids = _encode(tokenizer, str(unrelated_plan_text))
    action1_ids = _encode(tokenizer, str(actions[0].get("command", "")))
    action2_ids = _encode(tokenizer, str(actions[1].get("command", "")))
    action3_ids = _encode(tokenizer, str(actions[2].get("command", "")))
    if len(plan_ids) > MAX_SEMANTIC_CONTENT_TOKENS:
        raise V2ControlError(f"PLAN_PRESENT_GT96:{len(plan_ids)}")
    if len(unrelated_ids) > MAX_SEMANTIC_CONTENT_TOKENS:
        raise V2ControlError(f"UNRELATED_PLAN_GT96:{len(unrelated_ids)}")
    deranged_ids, derangement_meta = plan_block_deranged(plan_ids, open_tag_ids, close_tag_ids)
    contents = {
        "PLAN_PRESENT": plan_ids,
        "NEUTRAL_FILLER": [],
        "PLAN_BLOCK_DERANGED": deranged_ids,
        "UNRELATED_PLAN": unrelated_ids,
        "PAST_ACTIONS_ONLY": past_actions_only_content(action1_ids, action2_ids),
        "NEXT_ACTION_PRESERVED_LATE_NULL": next_action_preserved_content(action3_ids),
    }
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
        "plan_block_derangement": derangement_meta,
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
