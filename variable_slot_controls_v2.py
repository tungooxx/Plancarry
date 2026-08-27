#!/usr/bin/env python3
"""Pure token-ID controls for the pre-science ReplayResidual VariableSlot v2 diagnostic.

SCIENCE_EXECUTION_FORBIDDEN. This module performs no tokenization, decoding,
model calls, environment access, packet reads, or study-family selection. It
only checks whether exact-length token-ID controls can be constructed without
weakening the prospective semantic nulls.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Iterable, Sequence

RULE_VERSION = "REPLAYRESIDUAL_VARIABLE_SLOT_CONTROLS_V2"
MIN_SLOT_LENGTH = 8
ORDER_BLOCK_COUNT = 4
SCIENCE_EXECUTION_FORBIDDEN = True


class VariableSlotContractError(RuntimeError):
    """Fail-closed static constructibility error."""


def _ids(values: Iterable[int], *, label: str, allow_empty: bool = False) -> tuple[int, ...]:
    out = tuple(values)
    if not allow_empty and not out:
        raise VariableSlotContractError(f"{label}_EMPTY")
    for value in out:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise VariableSlotContractError(f"{label}_INVALID_TOKEN_ID")
    return out


@dataclass(frozen=True)
class FrozenTokenContract:
    """Token-ID constants that must be frozen before any future science."""

    neutral_cycle_ids: tuple[int, ...]
    action_wrapper_prefix_ids: tuple[int, ...]
    action_wrapper_suffix_ids: tuple[int, ...]
    contract_name: str = "UNBOUND_PROSPECTIVE_TOKEN_CONTRACT"

    def __post_init__(self) -> None:
        object.__setattr__(self, "neutral_cycle_ids", _ids(self.neutral_cycle_ids, label="NEUTRAL_CYCLE"))
        object.__setattr__(self, "action_wrapper_prefix_ids", _ids(self.action_wrapper_prefix_ids, label="ACTION_PREFIX", allow_empty=True))
        object.__setattr__(self, "action_wrapper_suffix_ids", _ids(self.action_wrapper_suffix_ids, label="ACTION_SUFFIX", allow_empty=True))
        if not isinstance(self.contract_name, str) or not self.contract_name:
            raise VariableSlotContractError("CONTRACT_NAME_REQUIRED")


# Synthetic-only IDs for CPU property tests. Not a Qwen tokenizer binding.
SYNTHETIC_TEST_CONTRACT = FrozenTokenContract(
    neutral_cycle_ids=(31, 37, 41, 43, 47),
    action_wrapper_prefix_ids=(101, 103),
    action_wrapper_suffix_ids=(107,),
    contract_name="SYNTHETIC_INTEGER_IDS_ONLY_V2",
)


def _cycle_fill(length: int, cycle: Sequence[int], *, offset: int = 0) -> tuple[int, ...]:
    if length < 0:
        raise VariableSlotContractError("NEGATIVE_FILL_LENGTH")
    frozen_cycle = _ids(cycle, label="FILL_CYCLE")
    return tuple(frozen_cycle[(offset + index) % len(frozen_cycle)] for index in range(length))


def _split_four(plan: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    n = len(plan)
    if n < MIN_SLOT_LENGTH:
        raise VariableSlotContractError(f"SLOT_TOO_SHORT:{n}<{MIN_SLOT_LENGTH}")
    quotient, remainder = divmod(n, ORDER_BLOCK_COUNT)
    sizes = tuple(quotient + (1 if index < remainder else 0) for index in range(ORDER_BLOCK_COUNT))
    if any(size <= 0 for size in sizes):
        raise VariableSlotContractError("ORDER_BLOCK_EMPTY")
    blocks: list[tuple[int, ...]] = []
    cursor = 0
    for size in sizes:
        blocks.append(plan[cursor : cursor + size])
        cursor += size
    if cursor != n:
        raise VariableSlotContractError("ORDER_BLOCK_PARTITION_MISMATCH")
    return tuple(blocks)


def _derangement_orders() -> tuple[tuple[int, ...], ...]:
    """All four-block derangements in lexicographic order."""
    return tuple(
        order
        for order in permutations(range(ORDER_BLOCK_COUNT))
        if all(source_index != output_index for output_index, source_index in enumerate(order))
        and order.index(ORDER_BLOCK_COUNT - 1) != ORDER_BLOCK_COUNT - 1
    )


DERANGEMENT_ORDERS = _derangement_orders()


def build_order_null(plan_ids: Sequence[int]) -> tuple[tuple[int, ...], dict]:
    """Return the first deterministic block derangement that changes token values.

    Four contiguous blocks cover the entire plan. Candidate output block orders
    are searched in lexicographic order. Every source block must move to a new
    output block index, the original final block must move away from final, and
    the emitted token sequence itself must differ from PLAN. If the token
    sequence is invariant under every allowed block derangement, the control is
    prospectively unconstructible and fails closed.
    """
    plan = _ids(plan_ids, label="PLAN")
    blocks = _split_four(plan)
    chosen: tuple[int, ...] | None = None
    output: tuple[int, ...] | None = None
    candidates_checked = 0
    for order in DERANGEMENT_ORDERS:
        candidates_checked += 1
        candidate = tuple(token for source in order for token in blocks[source])
        if candidate != plan:
            chosen, output = order, candidate
            break
    if chosen is None or output is None:
        raise VariableSlotContractError("ORDER_NULL_VALUE_DERANGEMENT_UNCONSTRUCTIBLE")
    if len(output) != len(plan) or sorted(output) != sorted(plan):
        raise VariableSlotContractError("ORDER_MULTISET_POSTCONDITION_FAILED")
    if output == plan:
        raise VariableSlotContractError("ORDER_VALUE_NONIDENTITY_POSTCONDITION_FAILED")
    if any(source == out for out, source in enumerate(chosen)):
        raise VariableSlotContractError("ORDER_BLOCK_DERANGEMENT_POSTCONDITION_FAILED")
    final_source_output_index = chosen.index(ORDER_BLOCK_COUNT - 1)
    if final_source_output_index == ORDER_BLOCK_COUNT - 1:
        raise VariableSlotContractError("FINAL_SOURCE_BLOCK_NOT_MOVED")
    return output, {
        "rule": "LEXICOGRAPHIC_SEARCH_OVER_FOUR_CONTIGUOUS_BLOCK_DERANGEMENTS",
        "block_count": ORDER_BLOCK_COUNT,
        "source_block_sizes": [len(block) for block in blocks],
        "output_source_block_order": list(chosen),
        "candidate_orders_checked": candidates_checked,
        "candidate_order_count": len(DERANGEMENT_ORDERS),
        "all_block_indices_deranged": True,
        "original_final_block_output_index": final_source_output_index,
        "token_multiset_preserved": True,
        "value_level_nonidentity": True,
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
    """Build exact-L ACTION_ONLY and wrapper-matched neutral using action3 only."""
    if length < MIN_SLOT_LENGTH:
        raise VariableSlotContractError(f"SLOT_TOO_SHORT:{length}<{MIN_SLOT_LENGTH}")
    action3 = _ids(action3_ids, label="ACTION3")
    prefix = contract.action_wrapper_prefix_ids
    suffix = contract.action_wrapper_suffix_ids
    content_length = len(prefix) + len(action3) + len(suffix)
    if content_length > length:
        raise VariableSlotContractError(f"ACTION_ONLY_CONTENT_EXCEEDS_SLOT:{content_length}>{length}")
    neutral_action = _cycle_fill(len(action3), contract.neutral_cycle_ids, offset=len(prefix))
    filler_length = length - content_length
    filler = _cycle_fill(
        filler_length,
        contract.neutral_cycle_ids,
        offset=len(prefix) + len(action3) + len(suffix),
    )
    action_only = prefix + action3 + suffix + filler
    wrapper_neutral = prefix + neutral_action + suffix + filler
    if len(action_only) != length or len(wrapper_neutral) != length:
        raise VariableSlotContractError("ACTION_ONLY_LENGTH_POSTCONDITION_FAILED")
    return action_only, wrapper_neutral, {
        "rule": "FIXED_WRAPPER_EXACT_ACTION3_THEN_NEUTRAL_CYCLE",
        "depends_on": ["slot_length_L", "reference_action3_ids", "frozen_wrapper_ids", "frozen_neutral_cycle_ids"],
        "forbidden_inputs": ["plan_ids", "reference_action4_ids", "reference_action5_ids", "future_observations"],
        "action3_token_count": len(action3),
        "wrapper_prefix_token_count": len(prefix),
        "wrapper_suffix_token_count": len(suffix),
        "filler_token_count": filler_length,
        "truncation": False,
    }


def build_control_payloads(
    plan_ids: Sequence[int],
    action3_ids: Sequence[int],
    contract: FrozenTokenContract,
) -> dict:
    plan = _ids(plan_ids, label="PLAN")
    length = len(plan)
    if length < MIN_SLOT_LENGTH:
        raise VariableSlotContractError(f"SLOT_TOO_SHORT:{length}<{MIN_SLOT_LENGTH}")
    neutral = build_neutral(length, contract)
    order_null, order_provenance = build_order_null(plan)
    action_only, action_only_neutral, action_provenance = build_action_only_pair(length, action3_ids, contract)
    controls = {
        "PLAN_PRESENT": plan,
        "NEUTRAL_L": neutral,
        "ORDER_NULL": order_null,
        "ACTION_ONLY_NULL": action_only,
        "ACTION_ONLY_NEUTRAL": action_only_neutral,
    }
    if any(len(value) != length for value in controls.values()):
        raise VariableSlotContractError("VARIABLE_SLOT_LENGTH_POSTCONDITION_FAILED")
    if controls["ORDER_NULL"] == controls["PLAN_PRESENT"]:
        raise VariableSlotContractError("ORDER_VALUE_NONIDENTITY_POSTCONDITION_FAILED")
    anchor = length - 1
    return {
        "rule_version": RULE_VERSION,
        "science_execution_forbidden": SCIENCE_EXECUTION_FORBIDDEN,
        "contract_name": contract.contract_name,
        "slot_length_L": length,
        "source_anchor_offset": anchor,
        "source_anchor_offsets": {name: anchor for name in controls},
        "no_tokenizer_decode_reencode": True,
        "controls": controls,
        "order_null_provenance": order_provenance,
        "action_only_provenance": action_provenance,
    }


__all__ = [
    "RULE_VERSION",
    "MIN_SLOT_LENGTH",
    "ORDER_BLOCK_COUNT",
    "SCIENCE_EXECUTION_FORBIDDEN",
    "DERANGEMENT_ORDERS",
    "VariableSlotContractError",
    "FrozenTokenContract",
    "SYNTHETIC_TEST_CONTRACT",
    "build_neutral",
    "build_order_null",
    "build_action_only_pair",
    "build_control_payloads",
]
