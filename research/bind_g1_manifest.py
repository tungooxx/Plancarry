#!/usr/bin/env python3
"""Offline structural auditor for PlanCarry BIND-v0.1 G1.

Pre-execution engineering tool only. It never calls models or ALFWorld and cannot
certify that a source record is independent, that a branch is scientifically
valid, or that a study may execute. Independent review is still required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "plancarry.bind.g1.v0.1"
N_CANDIDATES = 32
MIN_SOURCE_COMPETENT = 16
SHA = re.compile(r"^[0-9a-f]{64}$")
BLOCKED_OUTPUT_KEYS = {"binding_result", "post_treatment", "treatment_success", "g2_result"}


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _immutable(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": manifest.get("schema"),
        "pinned": manifest.get("pinned"),
        "candidate_order": [
            {key: c.get(key) for key in ("candidate_id", "split", "game_sha256", "source_family_id", "consumption_audit")}
            for c in manifest.get("candidates", []) if isinstance(c, dict)
        ],
    }


def _sha_check(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        errors.append(f"{field}: expected 64-character lowercase SHA256")


def _check_source(source: Any, label: str, errors: list[str]) -> None:
    if not isinstance(source, dict):
        errors.append(f"{label}: missing source record")
        return
    reset = source.get("reset")
    if not isinstance(reset, dict):
        errors.append(f"{label}.reset: missing")
        return
    _sha_check(reset.get("state_hash"), f"{label}.reset.state_hash", errors)
    for name in ("goal", "observation"):
        if not isinstance(reset.get(name), str) or not reset[name].strip():
            errors.append(f"{label}.reset.{name}: missing")
    commands = reset.get("admissible_commands")
    if not isinstance(commands, list) or not commands or not all(isinstance(c, str) for c in commands):
        errors.append(f"{label}.reset.admissible_commands: invalid ordered list")
        commands = []
    elif len(commands) != len(set(commands)):
        errors.append(f"{label}.reset.admissible_commands: duplicate command")
    trace = source.get("trajectory")
    if not isinstance(trace, list) or len(trace) < 2:
        errors.append(f"{label}.trajectory: need first action and later action(s)")
        return
    for i, step in enumerate(trace):
        if not isinstance(step, dict):
            errors.append(f"{label}.trajectory[{i}]: must be object")
            continue
        legal = step.get("admissible_before")
        chosen = step.get("action")
        if not isinstance(legal, list) or not legal or not all(isinstance(c, str) for c in legal):
            errors.append(f"{label}.trajectory[{i}].admissible_before: missing full ordered commands")
        elif chosen not in legal:
            errors.append(f"{label}.trajectory[{i}]: selected action absent from admissible list")
        if i == 0 and legal != commands:
            errors.append(f"{label}.trajectory[0]: ordered commands differ from reset")
    if source.get("won") is not True or source.get("invalid_model_turns") != 0:
        errors.append(f"{label}: requires verified source success and zero invalid model turns")
    if not isinstance(source.get("branch_label"), str) or not source["branch_label"].strip():
        errors.append(f"{label}.branch_label: missing precommitted identity")
    _sha_check(source.get("trace_sha256"), f"{label}.trace_sha256", errors)


def _check_pair(c: dict[str, Any], i: int, errors: list[str]) -> None:
    q = c.get("qualification")
    name = f"candidate[{i}]"
    if not isinstance(q, dict):
        errors.append(f"{name}: source-audit qualification missing")
        return
    if BLOCKED_OUTPUT_KEYS & set(q):
        errors.append(f"{name}: post-treatment result in source qualification")
    status = q.get("status")
    if status not in ("ELIGIBLE", "INELIGIBLE", "TECHNICAL_FAILURE"):
        errors.append(f"{name}: invalid status")
        return
    if status != "ELIGIBLE":
        if not isinstance(q.get("reason"), str) or not q["reason"].strip():
            errors.append(f"{name}: failure/ineligibility requires recorded reason")
        return
    a, b = q.get("source_a"), q.get("source_b")
    _check_source(a, name + ".A", errors)
    _check_source(b, name + ".B", errors)
    if not isinstance(a, dict) or not isinstance(b, dict):
        return
    ra, rb = a.get("reset"), b.get("reset")
    if isinstance(ra, dict) and isinstance(rb, dict):
        for key in ("state_hash", "goal", "observation", "admissible_commands"):
            if ra.get(key) != rb.get(key):
                errors.append(f"{name}: reset {key} differs between A/B")
    ta, tb = a.get("trajectory"), b.get("trajectory")
    if isinstance(ta, list) and isinstance(tb, list) and ta and tb and isinstance(ta[0], dict) and isinstance(tb[0], dict):
        if ta[0].get("action") != tb[0].get("action"):
            errors.append(f"{name}: first action differs between A/B")
        later_a = [x.get("action") for x in ta[1:] if isinstance(x, dict)]
        later_b = [x.get("action") for x in tb[1:] if isinstance(x, dict)]
        if later_a == later_b:
            errors.append(f"{name}: A/B later action traces identical")
    if a.get("branch_label") == b.get("branch_label"):
        errors.append(f"{name}: A/B branch labels identical")
    proof = q.get("source_evaluator_attestation")
    if not isinstance(proof, dict) or not isinstance(proof.get("evidence_id"), str) or not proof["evidence_id"].strip():
        errors.append(f"{name}: missing independent source evaluator attestation reference")


def audit(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append("schema mismatch")
    phase = manifest.get("phase")
    if phase not in ("FROZEN_MANIFEST", "SOURCE_AUDIT"):
        errors.append("phase must be FROZEN_MANIFEST or SOURCE_AUDIT")
    pinned = manifest.get("pinned")
    if not isinstance(pinned, dict):
        errors.append("pinned protocol missing")
        pinned = {}
    for key in ("model_revision", "candidate_order_rule", "evaluator_version"):
        if not isinstance(pinned.get(key), str) or not pinned[key].strip():
            errors.append(f"pinned.{key}: missing")
    for key in ("evaluator_sha256", "source_protocol_sha256"):
        _sha_check(pinned.get(key), f"pinned.{key}", errors)
    if pinned.get("confirmation_touched") is not False:
        errors.append("confirmation must be explicitly untouched")
    if pinned.get("binding_model_calls") != 0:
        errors.append("G1 manifest must contain zero binding-treatment model calls")
    cs = manifest.get("candidates")
    if not isinstance(cs, list) or len(cs) != N_CANDIDATES:
        errors.append(f"candidates: require exactly {N_CANDIDATES} precommitted attempts")
        cs = cs if isinstance(cs, list) else []
    ids, games = set(), set()
    for i, c in enumerate(cs):
        if not isinstance(c, dict):
            errors.append(f"candidate[{i}]: not an object")
            continue
        cid = c.get("candidate_id")
        if not isinstance(cid, str) or not cid.strip() or cid in ids:
            errors.append(f"candidate[{i}]: invalid or duplicate candidate_id")
        ids.add(cid)
        if c.get("split") != "train":
            errors.append(f"candidate[{i}]: TRAIN split only")
        h = c.get("game_sha256")
        _sha_check(h, f"candidate[{i}].game_sha256", errors)
        if h in games:
            errors.append(f"candidate[{i}]: repeated game hash")
        games.add(h)
        if not isinstance(c.get("source_family_id"), str) or not c["source_family_id"].strip():
            errors.append(f"candidate[{i}]: missing source family id")
        pr = c.get("consumption_audit")
        if not isinstance(pr, dict) or pr.get("status") != "VERIFIED_UNUSED" or not pr.get("evidence_id"):
            errors.append(f"candidate[{i}]: independent consumed-cohort exclusion proof required")
        if phase == "FROZEN_MANIFEST" and c.get("qualification") is not None:
            errors.append(f"candidate[{i}]: pre-registration cannot include outcome/qualification")
        if phase == "SOURCE_AUDIT":
            _check_pair(c, i, errors)
    frozen_sha = digest(_immutable(manifest))
    if phase == "SOURCE_AUDIT" and manifest.get("frozen_sha256") != frozen_sha:
        errors.append("frozen_sha256: immutable candidate/protocol definition drift")
    if phase == "FROZEN_MANIFEST" and manifest.get("frozen_sha256") != frozen_sha:
        errors.append("frozen_sha256 missing or does not match pre-registration")
    counts = {k: 0 for k in ("ELIGIBLE", "INELIGIBLE", "TECHNICAL_FAILURE")}
    if phase == "SOURCE_AUDIT":
        for c in cs:
            if isinstance(c, dict) and isinstance(c.get("qualification"), dict):
                status = c["qualification"].get("status")
                if status in counts:
                    counts[status] += 1
    if errors:
        verdict = "INVALID_PREEXECUTION_CONTRACT"
    elif phase == "FROZEN_MANIFEST":
        verdict = "FROZEN_MANIFEST_STRUCTURAL_ONLY"
    elif counts["TECHNICAL_FAILURE"]:
        verdict = "TECHNICAL_BLOCKER_NOT_SCIENTIFIC_FAIL"
    elif counts["ELIGIBLE"] >= MIN_SOURCE_COMPETENT:
        verdict = "G1_STRUCTURAL_THRESHOLD_ONLY_REQUIRES_INDEPENDENT_REVIEW"
    else:
        verdict = "G1_STOP_BELOW_SOURCE_THRESHOLD"
    return {"verdict": verdict, "errors": errors, "candidate_count": len(cs), "counts": counts,
            "computed_frozen_sha256": frozen_sha,
            "limits": "Structural linter only; cannot authenticate external evidence, evaluate task legitimacy, establish novelty or authorize an experiment."}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    args = p.parse_args()
    report = audit(json.loads(args.manifest.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
