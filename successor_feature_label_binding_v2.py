"""Prospectively frozen SuccessorFeature-v2 label-scoring binding.

This module is deliberately model/environment agnostic.  It freezes observable
snapshot bytes, recursive predicted-phase prompt bytes, exact label suffix IDs,
and causal-LM suffix-score arithmetic.  It performs no model or environment I/O.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from successor_feature_constructibility_v2 import ContractError, PHASE_LABELS

MODEL_ID = "Qwen/Qwen3-1.7B"
MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
TRANSFORMERS_VERSION = "4.51.3"
TOKENIZERS_VERSION = "0.21.1"

LABEL_SUFFIXES_UTF8 = (
    " SEEK_OBJECT",
    " ACQUIRE_OBJECT",
    " CARRY_OR_SEEK_RECEPTACLE",
    " PLACE_OBJECT",
    " MANIPULATE_CONTAINER",
    " OTHER",
)
LABEL_SUFFIX_IDS = (
    (46240, 13442),
    (10584, 19714, 13442),
    (356, 76864, 19834, 3620, 71133, 2192, 21073, 74701),
    (81882, 13442),
    (25735, 3298, 79223, 50689),
    (10065,),
)
if tuple(" " + x for x in PHASE_LABELS) != LABEL_SUFFIXES_UTF8:
    raise RuntimeError("PHASE_LABEL_SUFFIX_AUTHORITY_MISMATCH")

STEP2_PROMPT_TEMPLATE = (
    "{SNAPSHOT_UTF8}\n"
    "SHARED_ACTION: {A3_UTF8}\n"
    "Predict the procedural phase of the next action after the shared action. "
    "Answer with exactly one label:"
)
RECURSIVE_PROMPT_TEMPLATE = (
    "{SNAPSHOT_UTF8}\n"
    "SHARED_ACTION: {A3_UTF8}\n"
    "PREDICTED_PHASE_HISTORY_AFTER_SHARED_ACTION_JSON:{PHASE_HISTORY_JSON}\n"
    "Predict the procedural phase immediately after the predicted phase history above. "
    "Answer with exactly one label:"
)

@dataclass(frozen=True)
class ScoringSequence:
    label: str
    prompt_ids: tuple[int, ...]
    suffix_ids: tuple[int, ...]
    sequence_ids: tuple[int, ...]
    suffix_start: int


def _require_utf8_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field}_MUST_BE_UTF8_TEXT")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ContractError(f"{field}_INVALID_UTF8") from exc
    return value


def _canonical_json(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ContractError("CANONICAL_JSON_INVALID_UTF8") from exc
    return text


def render_snapshot_utf8(
    task_instruction: str,
    action_observation_history: Sequence[tuple[str, str]],
    current_observation: str,
    admissible_commands: Sequence[str],
) -> str:
    """Canonical observable-only cut snapshot after exactly two actions.

    Raw field contents are preserved byte-semantically by canonical JSON escaping.
    Admissible commands are sorted lexicographically by Python Unicode code-point
    order without deduplication.  No post-cut field exists in this schema.
    """
    task = _require_utf8_text(task_instruction, "TASK_INSTRUCTION")
    current = _require_utf8_text(current_observation, "CURRENT_OBSERVATION")
    if len(action_observation_history) != 2:
        raise ContractError("EXPECTED_EXACTLY_TWO_PRECUT_ACTION_OBSERVATION_CYCLES")
    history: list[dict[str, str]] = []
    for i, pair in enumerate(action_observation_history, start=1):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ContractError(f"HISTORY_{i}_MUST_BE_ACTION_OBSERVATION_PAIR")
        action = _require_utf8_text(pair[0], f"HISTORY_ACTION_{i}")
        obs = _require_utf8_text(pair[1], f"HISTORY_OBSERVATION_{i}")
        history.append({"action": action, "observation": obs})
    commands = [_require_utf8_text(x, "ADMISSIBLE_COMMAND") for x in admissible_commands]
    if not commands:
        raise ContractError("ADMISSIBLE_COMMANDS_EMPTY")
    obj = {
        "task_instruction": task,
        "history": history,
        "current_observation": current,
        "admissible_commands_lex": sorted(commands),
    }
    return _canonical_json(obj)


def validate_snapshot_utf8(snapshot_utf8: str) -> dict:
    text = _require_utf8_text(snapshot_utf8, "SNAPSHOT")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError("SNAPSHOT_NOT_CANONICAL_JSON") from exc
    if not isinstance(obj, dict) or list(obj) != [
        "task_instruction", "history", "current_observation", "admissible_commands_lex"
    ]:
        raise ContractError("SNAPSHOT_SCHEMA_MISMATCH")
    if not isinstance(obj["history"], list) or len(obj["history"]) != 2:
        raise ContractError("SNAPSHOT_HISTORY_MISMATCH")
    rebuilt = render_snapshot_utf8(
        obj["task_instruction"],
        [(x["action"], x["observation"]) for x in obj["history"]],
        obj["current_observation"],
        obj["admissible_commands_lex"],
    )
    if rebuilt != text:
        raise ContractError("SNAPSHOT_NOT_CANONICAL_SERIALIZATION")
    return obj


def render_label_prompt_utf8(
    snapshot_utf8: str,
    shared_action_a3_utf8: str,
    predicted_phase_history: Sequence[str] = (),
) -> str:
    validate_snapshot_utf8(snapshot_utf8)
    a3 = _require_utf8_text(shared_action_a3_utf8, "SHARED_ACTION_A3")
    history = tuple(predicted_phase_history)
    if len(history) > 2:
        raise ContractError("PREDICTED_PHASE_HISTORY_TOO_LONG")
    if any(x not in PHASE_LABELS for x in history):
        raise ContractError("PREDICTED_PHASE_HISTORY_UNKNOWN_LABEL")
    if not history:
        prompt = STEP2_PROMPT_TEMPLATE.format(SNAPSHOT_UTF8=snapshot_utf8, A3_UTF8=a3)
    else:
        prompt = RECURSIVE_PROMPT_TEMPLATE.format(
            SNAPSHOT_UTF8=snapshot_utf8,
            A3_UTF8=a3,
            PHASE_HISTORY_JSON=_canonical_json(list(history)),
        )
    _require_utf8_text(prompt, "RENDERED_PROMPT")
    return prompt


def verify_tokenizer_binding(
    tokenizer: object,
    *,
    model_id: str,
    revision: str,
    transformers_version: str,
    tokenizers_version: str,
) -> None:
    if model_id != MODEL_ID:
        raise ContractError("MODEL_ID_MISMATCH")
    if revision != MODEL_REVISION:
        raise ContractError("MODEL_REVISION_MISMATCH")
    if transformers_version != TRANSFORMERS_VERSION:
        raise ContractError("TRANSFORMERS_VERSION_MISMATCH")
    if tokenizers_version != TOKENIZERS_VERSION:
        raise ContractError("TOKENIZERS_VERSION_MISMATCH")
    encode = getattr(tokenizer, "encode", None)
    decode = getattr(tokenizer, "decode", None)
    if not callable(encode) or not callable(decode):
        raise ContractError("TOKENIZER_API_MISMATCH")
    for text, expected in zip(LABEL_SUFFIXES_UTF8, LABEL_SUFFIX_IDS):
        actual = tuple(int(x) for x in encode(text, add_special_tokens=False))
        if actual != expected:
            raise ContractError("LABEL_SUFFIX_TOKEN_IDS_MISMATCH")
        decoded = decode(list(expected), skip_special_tokens=False, clean_up_tokenization_spaces=False)
        if decoded != text:
            raise ContractError("LABEL_SUFFIX_TOKEN_DECODE_MISMATCH")


def encode_prompt_ids(tokenizer: object, prompt_utf8: str) -> tuple[int, ...]:
    prompt = _require_utf8_text(prompt_utf8, "PROMPT")
    encode = getattr(tokenizer, "encode", None)
    if not callable(encode):
        raise ContractError("TOKENIZER_API_MISMATCH")
    ids = tuple(int(x) for x in encode(prompt, add_special_tokens=False))
    if not ids:
        raise ContractError("EMPTY_PROMPT_TOKEN_IDS")
    if any(x < 0 for x in ids):
        raise ContractError("NEGATIVE_PROMPT_TOKEN_ID")
    return ids


def build_label_scoring_sequences(prompt_ids: Sequence[int]) -> tuple[ScoringSequence, ...]:
    p = tuple(prompt_ids)
    if not p or any(type(x) is not int or x < 0 for x in p):
        raise ContractError("INVALID_PROMPT_TOKEN_IDS")
    out = []
    for label, suffix in zip(PHASE_LABELS, LABEL_SUFFIX_IDS):
        seq = p + suffix
        out.append(ScoringSequence(label, p, suffix, seq, len(p)))
    return tuple(out)


def mean_suffix_logprob_from_logits(
    logits: Sequence[Sequence[float]],
    sequence_ids: Sequence[int],
    suffix_start: int,
) -> float:
    """Arithmetic-mean causal-LM logprob over direct suffix IDs.

    `logits[k]` predicts token at sequence position k+1.  Therefore suffix token
    at absolute position `pos` is scored from logits[pos-1].
    """
    seq = tuple(sequence_ids)
    if type(suffix_start) is not int or suffix_start < 1 or suffix_start >= len(seq):
        raise ContractError("INVALID_SUFFIX_START")
    if len(logits) < len(seq) - 1:
        raise ContractError("INSUFFICIENT_LOGIT_POSITIONS")
    vals: list[float] = []
    for pos in range(suffix_start, len(seq)):
        row = logits[pos - 1]
        target = seq[pos]
        if type(target) is not int or target < 0 or target >= len(row):
            raise ContractError("TARGET_TOKEN_OUTSIDE_LOGIT_VOCAB")
        r = [float(x) for x in row]
        if not r or not all(math.isfinite(x) for x in r):
            raise ContractError("NONFINITE_LOGITS")
        m = max(r)
        logz = m + math.log(math.fsum(math.exp(x - m) for x in r))
        lp = r[target] - logz
        if not math.isfinite(lp):
            raise ContractError("NONFINITE_SUFFIX_LOGPROB")
        vals.append(lp)
    if not vals:
        raise ContractError("EMPTY_SUFFIX")
    return math.fsum(vals) / len(vals)
