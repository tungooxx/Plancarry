#!/usr/bin/env python3
"""Pure token-ID control construction for prospective ReplayResidual VariableSlot.

Engineering-only helper. It performs no tokenization, decoding, model calls, or
environment access. Production science must prospectively freeze the token-ID
contract before any study-family execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

RULE_VERSION = "REPLAYRESIDUAL_VARIABLE_SLOT_CONTROLS_V1"
MIN_SLOT_LENGTH = 8
ORDER_BLOCK_COUNT = 4


class VariableSlotContractError(RuntimeError):
    pass


def _ids(values: Iterable[int], *, label: str, allow_empty: bool = False) -> tuple[int, ...]:
    out = tuple(values)
    if not allow_empty and not out:
        raise VariableSlotContractError(f"{label}_EMPTY")
    for x in out:
        if isinstance(x, bool) or not isinstance(x, int) or x < 0:
            raise VariableSlotContractError(f"{label}_INVALID_TOKEN_ID")
    return out


@dataclass(frozen=True)
class FrozenTokenContract:
    """Prospectively frozen token-ID constants, never learned from study outcomes."""

    neutral_cycle_ids: tuple[int, ...]
    action_wrapper_prefix_ids: tuple[int, ...]
    action_wrapper_suffix_ids: tuple[int, ...]
    contract_name: str = "UNBOUND_PROSPECTIVE_TOKEN_CONTRACT"

    def __post_init__(self) -> None:
        object.__setattr__(self, "neutral_cycle_ids", _ids(self.neutral_cycle_ids, label="NEUTRAL_CYCLE"))
        object.__setattr__(self, "action_wrapper_prefix_ids", _ids(self.action_wrapper_prefix_ids, label="ACTION_PREFIX", allow_empty=True))
        object.__setattr__(self, "action_wrapper_suffix_ids", _ids(self.action_wrapper_suffix_ids, label="ACTION_SUFFIX", allow_empty=True))
        if not self.contract_name or not isinstance(self.contract_name, str):
            raise VariableSlotContractError("CONTRACT_NAME_REQUIRED")


# Synthetic-only constants used by the CPU property suite. These are not a
# scientific Qwen tokenizer binding and MUST NOT be used for model execution.
SYNTHETIC_TEST_CONTRACT = FrozenTokenContract(
    neutral_cycle_ids=(31, 37, 41, 43, 47),
    action_wrapper_prefix_ids=(101, 103),
    action_wrapper_suffix_ids=(107,),
    contract_name="SYNTHETIC_INTEGER_IDS_ONLY_V1",
)


def _cycle_fill(length: int, cycle: Sequence[int], *, offset: int = 0) -> tuple[int, ...]:
    if length < 0:
        raise VariableSlotContractError("NEGATIVE_FILL_LENGTH")
    c = _ids(cycle, label="FILL_CYCLE")
    return tuple(c[(offset + i) % len(c)] for i in range(length))


def _split_four(ids: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    n = len(ids)
    if n < MIN_SLOT_LENGTH:
        raise VariableSlotContractError(f"SLOT_TOO_SHORT:{n}<{MIN_SLOT_LENGTH}")
    q, r = divmod(n, ORDER_BLOCK_COUNT)
    sizes = tuple(q + (1 if i < r else 0) for i in range(ORDER_BLOCK_COUNT))
    if any(s <= 0 for s in sizes):
        raise VariableSlotContractError("ORDER_BLOCK_EMPTY")
    blocks = []
    pos = 0
    for size in sizes:
        blocks.append(ids[pos : pos + size])
        pos += size
    if pos != n:
        raise VariableSlotContractError("ORDER_BLOCK_PARTITION_MISMATCH")
    return tuple(blocks)


def build_order_null(plan_ids: Sequence[int]) -> tuple[tuple[int, ...], dict]:
    """Derange four contiguous full-plan blocks by one cyclic left rotation.

    The source-block order is [1,2,3,0], so every block moves to a different
    block index and the original final block (3) cannot remain final.
    """
    plan = _ids(plan_ids, label="PLAN")
    blocks = _split_four(plan)
    source_block_order = (1, 2, 3, 0)
    if any(src == out for out, src in enumerate(source_block_order)):
        raise VariableSlotContractError("ORDER_DERANGEMENT_POSTCONDITION_FAILED")
    out = tuple(tok for src in source_block_order for tok in blocks[src])
    if len(out) != len(plan) or sorted(out) != sorted(plan):
        raise VariableSlotContractError("ORDER_MULTISET_POSTCONDITION_FAILED")
    if out == plan:
        raise VariableSlotContractError("ORDER_NULL_IDENTICAL_TO_PLAN")
    final_source_block_output_index = source_block_order.index(ORDER_BLOCK_COUNT - 1)
    if final_source_block_output_index == ORDER_BLOCK_COUNT - 1:
        raise VariableSlotContractError("FINAL_SOURCE_BLOCK_NOT_MOVED")
    return out, {
        "rule": "FOUR_CONTIGUOUS_BLOCK_LEFT_ROTATION_BY_ONE",
        "block_count": ORDER_BLOCK_COUNT,
        "source_block_sizes": [len(x) for x in blocks],
        "output_source_block_order": list(source_block_order),
        "all_block_indices_deranged": True,
        "original_final_block_output_index": final_source_block_output_index,
        "token_multiset_preserved": True,
    }


def build_neutral(length: int, contract: FrozenTokenContract) -> tuple[int, ...]:
    if length < MIN_SLOT_LENGTH:
        raise VariableSlotContractError(f"SLOT_TOO_SHORT:{length}<{MIN_SLOT_LENGTH}")
    return _cycle_fill(length, contract.neutral_cycle_ids)


def build_action_only_pair(
    length: int,
    action3_ids: Sequence[int],
    contract: FrozenTokenContract,
) -> tuple[tuple[int, ...], tuple[int, ...], dict]:
    """Construct ACTION_ONLY and wrapper-matched neutral at exact length L.

    Inputs deliberately exclude plan IDs and all later reference actions.
    """
    if length < MIN_SLOT_LENGTH:
        raise VariableSlotContractError(f"SLOT_TOO_SHORT:{length}<{MIN_SLOT_LENGTH}")
    action3 = _ids(action3_ids, label="ACTION3")
    prefix = contract.action_wrapper_prefix_ids
    suffix = contract.action_wrapper_suffix_ids
    base = len(prefix) + len(action3) + len(suffix)
    if base > length:
        raise VariableSlotContractError(f"ACTION_ONLY_CONTENT_EXCEEDS_SLOT:{base}>{length}")
    neutral_action = _cycle_fill(len(action3), contract.neutral_cycle_ids, offset=len(prefix))
    fill_len = length - base
    fill = _cycle_fill(fill_len, contract.neutral_cycle_ids, offset=len(prefix) + len(action3) + len(suffix))
    action_only = prefix + action3 + suffix + fill
    wrapper_neutral = prefix + neutral_action + suffix + fill
    if len(action_only) != length or len(wrapper_neutral) != length:
        raise VariableSlotContractError("ACTION_ONLY_LENGTH_POSTCONDITION_FAILED")
    if action_only == wrapper_neutral:
        raise VariableSlotContractError("ACTION_ONLY_PAIR_IDENTICAL")
    return action_only, wrapper_neutral, {
        "rule": "FIXED_WRAPPER_ACTION3_THEN_NEUTRAL_CYCLE",
        "depends_on": ["slot_length_L", "reference_action3_ids", "frozen_wrapper_ids", "frozen_neutral_cycle_ids"],
        "forbidden_inputs": ["plan_ids", "reference_action4_ids", "reference_action5_ids", "future_observations"],
        "action3_token_count": len(action3),
        "wrapper_prefix_token_count": len(prefix),
        "wrapper_suffix_token_count": len(suffix),
        "filler_token_count": fill_len,
    }


def build_control_payloads(
    plan_ids: Sequence[int],
    action3_ids: Sequence[int],
    contract: FrozenTokenContract,
) -> dict:
    L = len(plan_ids)
    if L < MIN_SLOT_LENGTH:
        raise VariableSlotContractError(f"SLOT_TOO_SHORT:{L}<{MIN_SLOT_LENGTH}")
    plan = _ids(plan_ids, label="PLAN")
    neutral = build_neutral(L, contract)
    if neutral == plan:
        raise VariableSlotContractError("ACTIVE_PAIR_IDENTICAL")
    order_null, order_provenance = build_order_null(plan)
    if order_null == neutral:
        raise VariableSlotContractError("ORDER_NULL_NEUTRAL_IDENTICAL")
    action_only, action_only_neutral, action_provenance = build_action_only_pair(L, action3_ids, contract)
    controls = {
        "PLAN_PRESENT": plan,
        "NEUTRAL_L": neutral,
        "ORDER_NULL": order_null,
        "ACTION_ONLY_NULL": action_only,
        "ACTION_ONLY_NEUTRAL": action_only_neutral,
    }
    if any(len(v) != L for v in controls.values()):
        raise VariableSlotContractError("VARIABLE_SLOT_LENGTH_POSTCONDITION_FAILED")
    anchor = L - 1
    return {
        "rule_version": RULE_VERSION,
        "contract_name": contract.contract_name,
        "slot_length_L": L,
        "source_anchor_offset": anchor,
        "source_anchor_offsets": {k: anchor for k in controls},
        "no_tokenizer_decode_reencode": True,
        "controls": controls,
        "order_null_provenance": order_provenance,
        "action_only_provenance": action_provenance,
    }


__all__ = [
    "RULE_VERSION",
    "MIN_SLOT_LENGTH",
    "ORDER_BLOCK_COUNT",
    "VariableSlotContractError",
    "FrozenTokenContract",
    "SYNTHETIC_TEST_CONTRACT",
    "build_neutral",
    "build_order_null",
    "build_action_only_pair",
    "build_control_payloads",
]
