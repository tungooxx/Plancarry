#!/usr/bin/env python3
"""Fail-closed BIND-v0.3 G0 candidate-input SHA integrity check.

Checks only pre-source structural identity. Never grants model, simulator,
TRAIN/DEVELOPMENT/CONFIRMATION, or execution authorization. An independent
historical non-consumption and source-competence audit is still required.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "plancarry.bind.g0.frozen-input.v0.3"
# PRE-SOURCE only. source_a/b_request_context_sha256 binds complete,
# already-materialized prospective *input message/request bytes* at G0;
# source_a/b_prompt_sha256 binds respective G0 prompt bytes. No model-
# generated history, future plan, success, or G1 outcome exists here.
# G1 execution must use a separate append-only output ledger. Empty histories
# require the checksum of the actual canonical empty input, never placeholders.
# A valid syntactic hash is NOT content/custody attestation by itself.

SHA256 = re.compile(r"^[a-f0-9]{64}$")
TOP_KEYS = frozenset({"schema", "phase", "pinned", "candidates", "frozen_sha256"})
PIN_HASH_KEYS = frozenset({
    "protocol_sha256", "evaluator_sha256", "tokenizer_sha256",
    "dataset_revision_sha256", "simulator_revision_sha256",
    "tools_renderer_sha256", "historical_usage_inventory_sha256",
})
PIN_KEYS = PIN_HASH_KEYS | frozenset({
    "model_revision", "confirmation_touched", "source_model_calls",
})
CANDIDATE_HASH_KEYS = frozenset({
    "game_sha256", "reset_full_state_sha256", "goal_sha256",
    "ordered_actions_sha256", "source_a_request_context_sha256",
    "source_b_request_context_sha256", "source_a_prompt_sha256",
    "source_b_prompt_sha256",
})
CANDIDATE_KEYS = CANDIDATE_HASH_KEYS | frozenset({
    "candidate_id", "source_family_id", "split", "source_a_seed",
    "source_b_seed", "consumption_audit",
})


def _sha256_ok(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def canonical_bytes(manifest: dict[str, Any]) -> bytes:
    """Commit every nested input value except the digest itself."""
    payload = {k: v for k, v in manifest.items() if k != "frozen_sha256"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def frozen_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def audit(manifest: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {"verdict": "INVALID_AUDIT_INPUT",
                "errors": ["manifest must be a JSON object"],
                "scientific_gate": "NOT_AUTHORIZED"}
    if set(manifest) != TOP_KEYS:
        errors.append("top-level manifest requires exactly the fixed fields")
    if manifest.get("schema") != SCHEMA:
        errors.append("wrong frozen-input schema")
    if manifest.get("phase") != "FROZEN_PRE_SOURCE":
        errors.append("must be FROZEN_PRE_SOURCE before source outputs")
    pin = manifest.get("pinned")
    if not isinstance(pin, dict):
        errors.append("missing pinned context")
        pin = {}
    if set(pin) != PIN_KEYS:
        errors.append("pinned context must have exactly the required fields")
    for key in PIN_HASH_KEYS:
        if not _sha256_ok(pin.get(key)):
            errors.append("missing/invalid pinned." + key)
    if not isinstance(pin.get("model_revision"), str) or not pin["model_revision"]:
        errors.append("missing model_revision")
    if (pin.get("confirmation_touched") is not False or
            type(pin.get("source_model_calls")) is not int or
            pin["source_model_calls"] != 0):
        errors.append("source calls must be zero and confirmation untouched")
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates must be an ordered array")
        candidates = []
    if len(candidates) != 32:
        errors.append("must freeze exactly 32 candidates")
    used_ids: set[str] = set()
    used_games: set[str] = set()
    for idx, c in enumerate(candidates):
        if not isinstance(c, dict):
            errors.append(f"candidate[{idx}] must be a record")
            continue
        if set(c) != CANDIDATE_KEYS:
            errors.append(f"candidate[{idx}] must have exactly required fields")
        cid = c.get("candidate_id")
        if not isinstance(cid, str) or not cid or cid in used_ids:
            errors.append(f"candidate[{idx}] missing/duplicate ID")
        else:
            used_ids.add(cid)
        gh = c.get("game_sha256")
        if not _sha256_ok(gh) or gh in used_games:
            errors.append(f"candidate[{idx}] missing/duplicate game checksum")
        else:
            used_games.add(gh)
        if c.get("split") != "train":
            errors.append(f"candidate[{idx}] non-TRAIN game")
        if not isinstance(c.get("source_family_id"), str) or not c["source_family_id"]:
            errors.append(f"candidate[{idx}] missing source_family_id")
        if c.get("consumption_audit") != "PENDING_INDEPENDENT":
            errors.append(f"candidate[{idx}] cannot self-certify unused source")
        for key in CANDIDATE_HASH_KEYS - {"game_sha256"}:
            if not _sha256_ok(c.get(key)):
                errors.append(f"candidate[{idx}] invalid {key}")
        for key in ("source_a_seed", "source_b_seed"):
            if type(c.get(key)) is not int or not (0 <= c[key] < 2**63):
                errors.append(f"candidate[{idx}] invalid {key}")
        if c.get("source_a_seed") == c.get("source_b_seed"):
            errors.append(f"candidate[{idx}] A/B source seeds not distinct")
    if not _sha256_ok(manifest.get("frozen_sha256")):
        errors.append("missing frozen_sha256")
    else:
        try:
            if manifest["frozen_sha256"] != frozen_digest(manifest):
                errors.append("frozen input mutated after commitment")
        except (ValueError, TypeError):
            errors.append("noncanonical frozen input")
    return {
        "verdict": ("INVALID_AUDIT_INPUT" if errors else
                    "BLOCKED_INDEPENDENT_SOURCE_ATTESTATION"),
        "scientific_gate": "NOT_AUTHORIZED",
        "candidate_count": len(candidates),
        "errors": errors,
        "meaning": ("Internal checksum integrity is insufficient to certify "
                    "historical freshness, full simulator provenance, naturally "
                    "authored source plans or G1 competence. No execution token."),
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen_manifest", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.frozen_manifest.read_text(encoding="utf-8"))
        result = audit(manifest)
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        result = {"verdict": "INVALID_AUDIT_INPUT", "scientific_gate": "NOT_AUTHORIZED",
                  "errors": [str(exc)]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["verdict"] == "INVALID_AUDIT_INPUT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
