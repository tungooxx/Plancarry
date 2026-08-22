#!/usr/bin/env python3
"""Frozen engineering helpers for PlanCarry ReplayResidual sanity v1.1.

This module is protocol plumbing only. It never generates model outcomes and it
contains no causal intervention API. Scientific authority remains the immutable
v1.1 preregistration and cohort artifacts whose hashes are checked below.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Iterable

DESIGN_REL = Path("results/design/plancarry_replay_residual_sanity_prereg_v1_1_20260821.json")
COHORT_REL = Path("results/design/plancarry_replay_residual_fresh_cohort_v1_20260821.json")
UNTOUCHED_REL = Path("results/design/plancarry_replay_residual_untouched_confirmation_freeze_v1_1_20260821.json")
DESIGN_SHA256 = "394222b7da7499899fb742080fa9f939a1f6fd7ce43310440f3ac61231ad135c"
COHORT_SHA256 = "545dff3c31a0b05ec86241aaf2ec4a1de49af8d4426cf2731ebc669b30c39009"
UNTOUCHED_SHA256 = "14a13254be9ff84f455a0bbc44901f6fae9430d2c2676707687987fcf67a35e7"
MODEL_ID = "Qwen/Qwen3-1.7B"
MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
TRANSFORMERS_VERSION = "4.51.3"
TOKENIZERS_VERSION = "0.21.1"
TORCH_VERSION = "2.13.0+cu130"
MODEL_DTYPE = "bfloat16"
LAYERS = (7, 14, 21, 27)
SITE = "residual stream output of frozen transformer block"
PLAN_SLOT_TOKENS = 128
MAX_PLAN_CONTENT_TOKENS = 96
MIN_QUALIFIED = 16
DEV_INDICES = tuple(range(32))
CONDITIONS = (
    "PLAN_PRESENT",
    "NEUTRAL_FILLER",
    "SHUFFLED_PLAN",
    "UNRELATED_PLAN",
    "GENERIC_HISTORY",
    "ALT_NEUTRAL_POSITION",
    "NEXT_ACTION_PRESERVED_LATE_NULL",
)
CONTROL_CONDITIONS = (
    "SHUFFLED_PLAN",
    "UNRELATED_PLAN",
    "GENERIC_HISTORY",
    "ALT_NEUTRAL_POSITION",
    "NEXT_ACTION_PRESERVED_LATE_NULL",
)
REQUIRED_PAYLOAD_FIELDS = (
    "model_id", "model_revision", "transformers_version", "tokenizers_version", "torch_version",
    "family", "game_path_sha256", "trajectory_sha256", "replay_transcript_sha256",
    "plan_block_sha256", "condition", "layer", "site", "token_index", "dtype", "shape",
    "cohort_manifest_sha256", "design_sha256",
)
REASONING_MARKERS = (
    re.compile(r"<\s*/?\s*think\s*>", re.I),
    re.compile(r"<\s*/?\s*analysis\s*>", re.I),
    re.compile(r"(?:^|\n)\s*(?:reasoning|chain[- ]of[- ]thought)\s*:", re.I),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load_authoritative(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    paths = (root / DESIGN_REL, root / COHORT_REL, root / UNTOUCHED_REL)
    expected = (DESIGN_SHA256, COHORT_SHA256, UNTOUCHED_SHA256)
    for p, e in zip(paths, expected):
        got = sha256_file(p)
        if got != e:
            raise RuntimeError(f"AUTHORITATIVE_HASH_MISMATCH:{p}:{got}:{e}")
    design, cohort, untouched = (json.loads(p.read_text(encoding="utf-8")) for p in paths)
    if design["model_runtime"]["id"] != MODEL_ID or design["model_runtime"]["revision"] != MODEL_REVISION:
        raise RuntimeError("MODEL_BINDING_MISMATCH")
    if design["model_runtime"]["dtype"] != MODEL_DTYPE or design["model_runtime"]["quantization"] != "NONE" or design["model_runtime"]["offload"] != "NONE":
        raise RuntimeError("PRECISION_BINDING_MISMATCH")
    if design["model_runtime"]["generation"] != {"enable_thinking": False, "temperature": 0.0}:
        raise RuntimeError("GENERATION_BINDING_MISMATCH")
    if tuple(design["replay_pairing"]["candidate_layers"]) != LAYERS:
        raise RuntimeError("LAYER_BINDING_MISMATCH")
    if design["natural_plan_protocol"]["fixed_plan_block_tokens"] != PLAN_SLOT_TOKENS:
        raise RuntimeError("PLAN_SLOT_BINDING_MISMATCH")
    if design["natural_plan_protocol"]["max_plan_content_tokens"] != MAX_PLAN_CONTENT_TOKENS:
        raise RuntimeError("PLAN_CONTENT_BINDING_MISMATCH")
    if design["cohort"]["minimum_qualified"] != MIN_QUALIFIED:
        raise RuntimeError("QUALIFICATION_BINDING_MISMATCH")
    req = tuple(design["latent_payload_provenance_schema"]["required_fields"])
    if req != REQUIRED_PAYLOAD_FIELDS:
        raise RuntimeError("PAYLOAD_SCHEMA_BINDING_MISMATCH")
    if set(design["replay_conditions"]) != set(CONDITIONS):
        raise RuntimeError("CONDITION_BINDING_MISMATCH")
    return design, cohort, untouched


def development_manifest(root: Path) -> list[dict[str, Any]]:
    _design, cohort, _untouched = load_authoritative(root)
    rows = cohort.get("selected", [])
    if len(rows) != 64 or [int(x["frozen_index"]) for x in rows] != list(range(64)):
        raise RuntimeError("COHORT_POPULATION_BINDING_MISMATCH")
    dev = rows[:32]
    if [int(x["frozen_index"]) for x in dev] != list(DEV_INDICES):
        raise RuntimeError("DEVELOPMENT_INDEX_BINDING_MISMATCH")
    if any(x.get("phase") != "sanity_development_candidate" for x in dev):
        raise RuntimeError("DEVELOPMENT_PHASE_BINDING_MISMATCH")
    return dev


def assert_no_reasoning_trace(text: str) -> None:
    if any(p.search(text or "") for p in REASONING_MARKERS):
        raise RuntimeError("REASONING_TRACE_GUARD_FAILED")


def tok_encode(tokenizer: Any, text: str) -> list[int]:
    ids = tokenizer.encode(text, add_special_tokens=False)
    return [int(x) for x in ids]


def tok_decode(tokenizer: Any, ids: Iterable[int]) -> str:
    vals = [int(x) for x in ids]
    try:
        return tokenizer.decode(vals, skip_special_tokens=False, clean_up_tokenization_spaces=False)
    except TypeError:
        return tokenizer.decode(vals, skip_special_tokens=False)


def exact_token_text(tokenizer: Any, ids: list[int], *, label: str) -> str:
    text = tok_decode(tokenizer, ids)
    roundtrip = tok_encode(tokenizer, text)
    if roundtrip != ids:
        raise RuntimeError(f"TOKENIZER_ROUNDTRIP_FAILED:{label}")
    return text


def _filler_fragments(tag: str) -> tuple[str, ...]:
    primary = {
        "neutral": " neutral context remains unchanged.",
        "alternate": " background record contains no plan instruction.",
        "late": " later procedural details are intentionally unavailable.",
        "history": " observed history only; no future plan is supplied.",
    }[tag]
    # Common short fallbacks make exact-length construction possible without
    # truncating a subword token. All fragments are semantically neutral.
    return (primary, " neutral", " context", " unchanged", " background", " record", " fact", " note", " state", " detail", " item", " x", " .", " :", "\n.", ".")


def make_exact_slot_ids(tokenizer: Any, content: str, *, filler_tag: str = "neutral", max_content_tokens: int | None = MAX_PLAN_CONTENT_TOKENS) -> list[int]:
    assert_no_reasoning_trace(content)
    content_ids = tok_encode(tokenizer, content)
    if max_content_tokens is not None and len(content_ids) > max_content_tokens:
        raise RuntimeError(f"PLAN_CONTENT_TOO_LONG:{len(content_ids)}>{max_content_tokens}")
    # Identical neutral wrappers are part of the preregistered neutral padding.
    # They force the tokenizer boundaries at both sides of the 128-token block
    # to be identical across every replay arm, preventing BPE seam merges from
    # shifting the downstream capture position.
    begin = "Neutral context boundary.\n"
    end = "\nNeutral context boundary end."
    filler = ""
    def render(extra: str = "") -> str:
        body = content
        if body and extra:
            return begin + body + extra + end
        if body:
            return begin + body + end
        return begin + extra.lstrip() + end
    text = render(filler)
    n = len(tok_encode(tokenizer, text))
    if n > PLAN_SLOT_TOKENS:
        raise RuntimeError(f"SLOT_BASE_EXCEEDS_128:{n}")
    fragments = _filler_fragments(filler_tag)
    # Deterministically greedily take the largest legal increment; ties use
    # the fixed fragment order. Re-tokenize the full textual block each step so
    # boundary merges are accounted for exactly rather than assumed additive.
    steps = 0
    while n < PLAN_SLOT_TOKENS:
        gap = PLAN_SLOT_TOKENS - n
        choices = []
        for order, frag in enumerate(fragments):
            cand = render(filler + frag)
            m = len(tok_encode(tokenizer, cand))
            inc = m - n
            if 0 < inc <= gap:
                choices.append((inc, -order, frag, cand, m))
        if not choices:
            raise RuntimeError(f"EXACT_128_NEUTRAL_PADDING_UNCONSTRUCTABLE:remaining={gap}:tag={filler_tag}")
        inc, _negorder, frag, text, n = max(choices)
        filler += frag
        steps += 1
        if steps > 256:
            raise RuntimeError("EXACT_128_PADDING_LOOP_GUARD")
    ids = tok_encode(tokenizer, text)
    if len(ids) != PLAN_SLOT_TOKENS:
        raise RuntimeError("SLOT_LENGTH_POSTCONDITION_FAILED")
    roundtrip = exact_token_text(tokenizer, ids, label="plan_slot")
    if len(tok_encode(tokenizer, roundtrip)) != PLAN_SLOT_TOKENS:
        raise RuntimeError("SLOT_ROUNDTRIP_LENGTH_FAILED")
    if content and content not in roundtrip:
        raise RuntimeError("SLOT_CONTENT_NOT_PRESERVED_VERBATIM")
    return ids

def _plan_inner(plan_text: str) -> tuple[str, str, str]:
    m = re.fullmatch(r"\s*(<PLAN>)(.*?)(</PLAN>)\s*", plan_text, flags=re.I | re.S)
    if not m:
        raise RuntimeError("PLAN_MARKERS_REQUIRED")
    return m.group(1), m.group(2).strip(), m.group(3)


def shuffled_plan(plan_text: str, family: str) -> str:
    op, inner, cl = _plan_inner(plan_text)
    raw = [x.strip() for x in re.split(r"(?:\n+|(?<=[.;])\s+)", inner) if x.strip()]
    if len(raw) < 2:
        raise RuntimeError("PLAN_NEEDS_AT_LEAST_TWO_CLAUSES_FOR_SHUFFLE")
    keyed = []
    for i, clause in enumerate(raw):
        key = hashlib.sha256(f"{family}|shuffle|{i}|{clause}".encode()).hexdigest()
        keyed.append((key, clause))
    perm = [x[1] for x in sorted(keyed)]
    if perm == raw:
        perm = perm[1:] + perm[:1]
    return f"{op}\n" + "\n".join(perm) + f"\n{cl}"


def generic_history_text(packet: dict[str, Any], anchor_cycle: int) -> str:
    parts = ["<PLAN>", "VISIBLE HISTORY FACTS ONLY:", str(packet["initial_observation"]).strip()]
    for i, row in enumerate(packet["actions"][:anchor_cycle], 1):
        parts.append(f"STEP {i} ACTION OBSERVED: {row['command']}")
        parts.append(f"STEP {i} RESULT OBSERVED: {row['observation']}")
    parts.append("</PLAN>")
    return "\n".join(parts)


def next_action_late_null_text(packet: dict[str, Any], anchor_cycle: int) -> str:
    if anchor_cycle >= len(packet["actions"]):
        raise RuntimeError("NO_POST_ANCHOR_ACTION_FOR_LATE_NULL")
    action = str(packet["actions"][anchor_cycle]["command"])
    return f"<PLAN>\nNEXT ACTION: {action}\nLATER PLAN: later procedural commitments are intentionally unavailable.\n</PLAN>"


def build_condition_slots(tokenizer: Any, packet: dict[str, Any], unrelated_plan: str, anchor_cycle: int) -> dict[str, list[int]]:
    plan = str(packet["plan_text"])
    assert_no_reasoning_trace(plan)
    assert_no_reasoning_trace(unrelated_plan)
    slots = {
        "PLAN_PRESENT": make_exact_slot_ids(tokenizer, plan, filler_tag="neutral"),
        "NEUTRAL_FILLER": make_exact_slot_ids(tokenizer, "", filler_tag="neutral", max_content_tokens=None),
        "SHUFFLED_PLAN": make_exact_slot_ids(tokenizer, shuffled_plan(plan, str(packet["family"])), filler_tag="neutral"),
        "UNRELATED_PLAN": make_exact_slot_ids(tokenizer, unrelated_plan, filler_tag="neutral"),
        "GENERIC_HISTORY": make_exact_slot_ids(tokenizer, generic_history_text(packet, anchor_cycle), filler_tag="history", max_content_tokens=MAX_PLAN_CONTENT_TOKENS),
        "ALT_NEUTRAL_POSITION": make_exact_slot_ids(tokenizer, "", filler_tag="alternate", max_content_tokens=None),
        "NEXT_ACTION_PRESERVED_LATE_NULL": make_exact_slot_ids(tokenizer, next_action_late_null_text(packet, anchor_cycle), filler_tag="late", max_content_tokens=MAX_PLAN_CONTENT_TOKENS),
    }
    if set(slots) != set(CONDITIONS) or any(len(v) != PLAN_SLOT_TOKENS for v in slots.values()):
        raise RuntimeError("CONDITION_SLOT_CONSTRUCTION_FAILED")
    return slots


def trajectory_digest(packet: dict[str, Any]) -> str:
    payload = {
        "family": packet["family"],
        "game_path": packet["game_path"],
        "task_instruction": packet["task_instruction"],
        "initial_observation": packet["initial_observation"],
        "actions": packet["actions"],
        "success": packet["success"],
        "interruption_after": packet["interruption_after"],
    }
    return sha256_bytes(canonical_json_bytes(payload))


def validate_episode_packet(packet: dict[str, Any], manifest_row: dict[str, Any], tokenizer: Any) -> None:
    idx = int(packet.get("frozen_index", -1))
    if idx not in DEV_INDICES:
        raise RuntimeError(f"SEALED_OR_INVALID_INDEX:{idx}")
    for key in ("family", "game_path"):
        if packet.get(key) != manifest_row.get(key):
            raise RuntimeError(f"MANIFEST_IDENTITY_MISMATCH:{key}")
    if not bool(packet.get("qualified", False)):
        return
    if not bool(packet.get("success", False)):
        raise RuntimeError("QUALIFIED_PACKET_MUST_BE_SUCCESSFUL")
    actions = packet.get("actions")
    if not isinstance(actions, list) or len(actions) > 12 or len(actions) < 4:
        raise RuntimeError("QUALIFIED_TRAJECTORY_ACTION_COUNT_GUARD")
    cut = int(packet.get("interruption_after", -1))
    if cut < 2 or len(actions) - cut < 2:
        raise RuntimeError("INTERRUPTION_COMPLETED_REMAINING_GUARD")
    plan = str(packet.get("plan_text", ""))
    assert_no_reasoning_trace(plan)
    _plan_inner(plan)
    if len(tok_encode(tokenizer, plan)) > MAX_PLAN_CONTENT_TOKENS:
        raise RuntimeError("QUALIFIED_PLAN_TOO_LONG")
    if any(not isinstance(x, dict) or not str(x.get("command", "")).strip() or "observation" not in x for x in actions):
        raise RuntimeError("ACTION_OBSERVATION_SCHEMA_GUARD")


def replay_prefix(packet: dict[str, Any]) -> str:
    return (
        "TASK\n" + str(packet["task_instruction"]).strip() +
        "\nINITIAL OBSERVATION\n" + str(packet["initial_observation"]).strip() +
        "\nPLAN BLOCK\n"
    )


def replay_suffix(packet: dict[str, Any], anchor_cycle: int) -> str:
    parts = ["\nEND PLAN BLOCK\nREPLAYED TRAJECTORY"]
    for i, row in enumerate(packet["actions"][:anchor_cycle], 1):
        parts.append(f"STEP {i}\nACTION: {row['command']}\nOBSERVATION: {row['observation']}")
    parts.append("<STATE_END>")
    return "\n".join(parts)


def build_replay(tokenizer: Any, packet: dict[str, Any], slot_ids: list[int], anchor_cycle: int) -> tuple[str, list[int]]:
    if anchor_cycle not in (1, 2):
        raise RuntimeError("ANCHOR_MUST_BE_T1_OR_T2")
    # The frozen scientific contract is that the plan block itself is exactly
    # 128 model tokens and every arm has the same downstream token positions.
    # Do not require separately-tokenized segments to concatenate to an
    # identical token-ID sequence: BPE/SentencePiece boundary merges can make
    # that stronger property false without changing either scientific fact.
    slot_text = exact_token_text(tokenizer, list(slot_ids), label=f"slot_t{anchor_cycle}")
    if len(tok_encode(tokenizer, slot_text)) != PLAN_SLOT_TOKENS:
        raise RuntimeError("PLAN_SLOT_NOT_EXACT_128_AFTER_ROUNDTRIP")
    text = replay_prefix(packet) + slot_text + replay_suffix(packet, anchor_cycle)
    ids = tok_encode(tokenizer, text)
    return text, ids


def replay_alignment_signature(tokenizer: Any, packet: dict[str, Any], slot_ids: list[int], anchor_cycle: int) -> tuple[int, int]:
    slot_text = exact_token_text(tokenizer, list(slot_ids), label=f"slot_sig_t{anchor_cycle}")
    prefix_slot = replay_prefix(packet) + slot_text
    full = prefix_slot + replay_suffix(packet, anchor_cycle)
    return len(tok_encode(tokenizer, prefix_slot)), len(tok_encode(tokenizer, full))


def residual(a: list[float], b: list[float]) -> list[float]:
    if len(a) != len(b) or not a:
        raise RuntimeError("VECTOR_SHAPE_MISMATCH")
    return [float(x) - float(y) for x, y in zip(a, b)]


def l2(v: list[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in v))


def unit(v: list[float]) -> list[float]:
    n = l2(v)
    if n <= 1e-8:
        return [0.0 for _ in v]
    return [float(x) / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    ua, ub = unit(a), unit(b)
    if not ua or not ub or l2(ua) <= 1e-12 or l2(ub) <= 1e-12:
        return 0.0
    return sum(x * y for x, y in zip(ua, ub))


def payload_sha256(metadata: dict[str, Any], vector: list[float]) -> str:
    missing = [k for k in REQUIRED_PAYLOAD_FIELDS if k not in metadata]
    if missing:
        raise RuntimeError(f"PAYLOAD_PROVENANCE_MISSING:{','.join(missing)}")
    raw = b"".join(struct.pack("<f", float(x)) for x in vector)
    return sha256_bytes(canonical_json_bytes(metadata) + raw)


def validate_payload(metadata: dict[str, Any], vector: list[float], expected_hash: str) -> None:
    got = payload_sha256(metadata, vector)
    if got != expected_hash:
        raise RuntimeError(f"PAYLOAD_HASH_MISMATCH:{got}:{expected_hash}")


def median(vals: list[float]) -> float:
    if not vals:
        raise RuntimeError("MEDIAN_EMPTY")
    s = sorted(float(x) for x in vals)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
