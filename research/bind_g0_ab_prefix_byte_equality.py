#!/usr/bin/env python3
"""BIND-v0.3 G0 prospective A/B reset-prefix evidence checker, synthetic-only.

Compares BYTES, not the legacy sorted-command hash. This is not a simulator
clone API or a proof that bytes from any real backend represent all hidden
state or RNG. An independent backend-authority attestation is still mandatory.
No model, TRAIN episode, G1, G2, or confirmation is authorized.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "plancarry.bind.g0.ab-prefix-byte-equality.v0.1"
SHA_FIELDS = ("game_sha256", "goal_sha256", "simulator_sha256",
              "renderer_sha256", "tokenizer_sha256")
SNAP_FIELDS = ("full_hidden_state_b64", "rng_state_b64",
               "observation_b64", "ordered_commands", "score_b64",
               "done_b64")
TRACE_TOP = {"schema", "phase", "source", "pair", "backend", "A", "B"}
BACKEND_KEYS = {"backend_kind", "backend_revision_sha256",
                "full_state_export_provenance", "rng_export_provenance"}
SIDE_KEYS = {"independent_instance_id", "steps"}
STEP_KEYS = {"prefix_step", "actual_action_b64", "after"}
DECISION_KEYS = {"phase", "authoritative_full_state_export", "authoritative_rng_export",
                 "backend_independently_attested", "all_actions_byte_exact",
                 "confirmation_untouched", "source_model_calls"}


def bytes_field(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("Required base64 bytes missing")
    try:
        data = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeError, binascii.Error, ValueError) as e:
        raise ValueError("Invalid base64 bytes") from e
    if not data:
        raise ValueError("Encoded empty bytes are not accepted")
    # Require unique canonical wire bytes. Python accepts alternate Base64
    # spellings differing only in unused padding bits unless checked here.
    if base64.b64encode(data).decode("ascii") != value:
        raise ValueError("Noncanonical base64 bytes")
    return data


def sha_ok(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(x in "0123456789abcdef" for x in value)


def snapshot(snap: Any) -> dict[str, Any]:
    if not isinstance(snap, dict) or set(snap) != set(SNAP_FIELDS):
        raise ValueError("Snapshot must supply every exact full-state and public field")
    cmds = snap["ordered_commands"]
    if not isinstance(cmds, list) or not all(isinstance(x, str) and x for x in cmds):
        raise ValueError("Ordered command array invalid")
    # Do NOT sort: bytewise order and distinctions between strings matter.
    if len(set(cmds)) != len(cmds):
        raise ValueError("Duplicate commands cannot form a trusted menu")
    result = {k: bytes_field(snap[k]) for k in SNAP_FIELDS if k != "ordered_commands"}
    decoded_commands = [bytes_field(x) for x in cmds]
    # Enforce uniqueness on the actual command byte strings, not merely their
    # encoded representation, which is a weaker invariant.
    if len(set(decoded_commands)) != len(decoded_commands):
        raise ValueError("Duplicate decoded command bytes cannot form a trusted menu")
    result["ordered_commands"] = decoded_commands
    # Terminal marker has a strict canonical byte encoding in synthetic
    # traces. Arbitrary non-empty marker bytes cannot masquerade as False.
    if result["done_b64"] not in (b"0", b"1"):
        raise ValueError("Terminal marker must be exact ASCII 0 or 1")
    # A completed episode may have no remaining admissible actions. An empty
    # menu on a nonterminal state is an invalid pre-action witness. The
    # existing step validator still forbids any action after done == b"1".
    if not decoded_commands and result["done_b64"] != b"1":
        raise ValueError("Nonterminal snapshot cannot have an empty command menu")
    return result


def mismatch(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return [key for key in SNAP_FIELDS if left[key] != right[key]]


def structural_audit(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != TRACE_TOP:
        raise ValueError("Wrong complete A/B evidence schema")
    if record["schema"] != SCHEMA or record["phase"] != "PRE_G1_SYNTHETIC_TOY":
        raise ValueError("Only synthetic pre-G1 work allowed")
    src = record["source"]
    if not isinstance(src, dict) or set(src) != set(SHA_FIELDS) or not all(sha_ok(x) for x in src.values()):
        raise ValueError("All five original source identity hashes required")
    be = record["backend"]
    if not isinstance(be, dict) or set(be) != BACKEND_KEYS or be["backend_kind"] != "SYNTHETIC_TOY":
        raise ValueError("Only synthetic toy backend accepted in this checker")
    if not sha_ok(be["backend_revision_sha256"]):
        raise ValueError("Backend hash missing")
    for k in ("full_state_export_provenance", "rng_export_provenance"):
        if be.get(k) != "TOY_ONLY_NOT_REAL_ATTESTATION":
            raise ValueError("Cannot self-certify real backend source state")
    left, right = record["A"], record["B"]
    for side in (left, right):
        if not isinstance(side, dict) or set(side) != SIDE_KEYS:
            raise ValueError("Incomplete side")
        if not isinstance(side["independent_instance_id"], str) or not side["independent_instance_id"]:
            raise ValueError("Missing independent backend instance")
        if not isinstance(side["steps"], list) or not side["steps"]:
            raise ValueError("Empty trace")
    if left["independent_instance_id"] == right["independent_instance_id"]:
        raise ValueError("A and B cannot reference the same instance")
    if len(left["steps"]) != len(right["steps"]):
        raise ValueError("Unbalanced common prefix step counts")
    if len(left["steps"]) < 2:
        raise ValueError("Must include initial step and >=1 common prefix action")
    failures = []
    # Preserve exact ordered legal-action menus for each previous snapshot.
    # Byte-identical transitions are insufficient if both sides replay the
    # same impossible action. This is a NECESSARY toy lint, never a full-state
    # authority certificate.
    previous_a = previous_b = None
    step_n = len(left["steps"])
    for i in range(step_n):
        a = left["steps"][i]
        b = right["steps"][i]
        if not isinstance(a, dict) or not isinstance(b, dict) or set(a) != STEP_KEYS or set(b) != STEP_KEYS:
            raise ValueError("Invalid step fields")
        if type(a["prefix_step"]) is not int or type(b["prefix_step"]) is not int or a["prefix_step"] != i or b["prefix_step"] != i:
            raise ValueError("Nonconsecutive common-prefix index")
        aa = bytes_field(a["actual_action_b64"])
        bb = bytes_field(b["actual_action_b64"])
        if i == 0:
            if aa != b"RESET" or bb != b"RESET":
                raise ValueError("First step must be RESET evidence")
        else:
            if aa != bb:
                failures.append(f"step_{i}.actual_action")
            if previous_a is None or previous_b is None:
                raise ValueError("Missing previous snapshots for action validation")
            if previous_a["done_b64"] == b"1":
                failures.append(f"step_{i}.A.action_after_terminal")
            if previous_b["done_b64"] == b"1":
                failures.append(f"step_{i}.B.action_after_terminal")
            if aa not in previous_a["ordered_commands"]:
                failures.append(f"step_{i}.A.action_not_admissible")
            if bb not in previous_b["ordered_commands"]:
                failures.append(f"step_{i}.B.action_not_admissible")
        sa, sb = snapshot(a["after"]), snapshot(b["after"])
        failures.extend(f"step_{i}.{x}" for x in mismatch(sa, sb))
        previous_a, previous_b = sa, sb
    if not failures:
        status = "MATCHED_SYNTHETIC_PREFIX_ONLY"
    else:
        status = "MISMATCHED_SYNTHETIC_PREFIX"
    return {"status": status, "scientific_gate": "NOT_AUTHORIZED",
            "verified_prefix_steps": step_n,
            "failures": failures,
            "schema": SCHEMA,
            "scope": "Toy trace checks representation byte equality only. Neither full backend state authority, live PDDL snapshot completeness, nor actual independent consumption provenance is proven.",
            "blocking_gate": "BLOCKED_INDEPENDENT_FULL_STATE_AND_HISTORICAL_USAGE_ATTESTATION"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = structural_audit(json.loads(args.trace.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as err:
        result = {"status": "INVALID_TRACE", "scientific_gate": "NOT_AUTHORIZED",
                  "blocking_gate": "BLOCKED_INVALID_EVIDENCE", "error": str(err)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "MATCHED_SYNTHETIC_PREFIX_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
