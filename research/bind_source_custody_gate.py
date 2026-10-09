#!/usr/bin/env python3
"""Fail-closed static provenance triage for PlanCarry BIND-v0.2 G1.

This script NEVER certifies independent historical non-consumption. It only
checks pre-registered identities and rejects known reuse / incomplete evidence.
No model, environment, tokenizer, network, or GPU dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = 'plancarry.bind.g1.v0.1'
LEDGER_SCHEMA = 'plancarry.bind.prior-consumption.v0.2'
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
EXPECTED_CANDIDATES = 32


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def frozen_candidate_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    """Match the existing G1 linter's frozen manifest identity exactly."""
    return {
        'schema': manifest.get('schema'),
        'pinned': manifest.get('pinned'),
        'candidate_order': [
            {k: c.get(k) for k in ('candidate_id', 'split', 'game_sha256', 'source_family_id', 'consumption_audit')}
            for c in manifest.get('candidates', []) if isinstance(c, dict)
        ],
    }


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def audit(manifest: Any, ledger: Any) -> dict[str, Any]:
    errors: list[str] = []
    matches: list[dict[str, Any]] = []
    if not isinstance(manifest, dict) or not isinstance(ledger, dict):
        return {'verdict': 'INVALID_AUDIT_INPUT', 'errors': ['Inputs must both be JSON objects'], 'known_overlaps': [], 'candidate_count': 0}
    if manifest.get('schema') != MANIFEST_SCHEMA:
        errors.append('manifest.schema invalid')
    if manifest.get('phase') != 'FROZEN_MANIFEST':
        errors.append('manifest must be frozen PRE-source-evaluation, not SOURCE_AUDIT or post-treatment')
    pin = manifest.get('pinned')
    if not isinstance(pin, dict):
        errors.append('manifest.pinned absent')
        pin = {}
    if pin.get('confirmation_touched') is not False or pin.get('binding_model_calls') != 0:
        errors.append('confirmation and binding-model-call embargo not explicit')
    for k in ('evaluator_sha256', 'source_protocol_sha256'):
        if not _valid_hash(pin.get(k)):
            errors.append('invalid pinned.'+k)
    if ledger.get('schema') != LEDGER_SCHEMA:
        errors.append('ledger.schema invalid')
    for k in ('dataset_manifest_sha256', 'inventory_snapshot_sha256'):
        if not _valid_hash(ledger.get(k)):
            errors.append('missing immutable ledger.'+k)
    if ledger.get('scope') != 'ALL_HISTORICAL_PROJECT_USES':
        errors.append('historical usage inventory is not declared complete')
    candidates = manifest.get('candidates')
    if not isinstance(candidates, list):
        candidates = []
        errors.append('manifest.candidates absent')
    if len(candidates) != EXPECTED_CANDIDATES:
        errors.append('manifest must freeze exactly 32 ordered attempts')
    cid_seen, sha_seen = set(), set()
    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            errors.append(f'candidate[{i}] invalid')
            continue
        cid, h = c.get('candidate_id'), c.get('game_sha256')
        if not isinstance(cid, str) or not cid or cid in cid_seen:
            errors.append(f'candidate[{i}] missing or duplicate ID')
        cid_seen.add(cid)
        if c.get('split') != 'train':
            errors.append(f'candidate[{i}] non-TRAIN source prohibited')
        if not _valid_hash(h) or h in sha_seen:
            errors.append(f'candidate[{i}] invalid or duplicate game SHA')
        sha_seen.add(h)
        if not isinstance(c.get('source_family_id'), str) or not c['source_family_id']:
            errors.append(f'candidate[{i}] missing source family ID')
        if c.get('qualification') is not None:
            errors.append(f'candidate[{i}] qualification must not be present in frozen pre-source manifest')
    if not _valid_hash(manifest.get('frozen_sha256')):
        errors.append('frozen_sha256 MUST be present and valid before any source calls')
    elif manifest['frozen_sha256'] != digest(frozen_candidate_identity(manifest)):
        errors.append('frozen_sha256 drift / candidate substitution')
    records = ledger.get('records')
    if not isinstance(records, list) or not records:
        errors.append('historical ledger requires nonempty run-level evidence records')
        records = []
    consumed: dict[str, set[str]] = {}
    run_seen = set()
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f'ledger.records[{i}] invalid')
            continue
        run_id = rec.get('run_id')
        if not isinstance(run_id, str) or not run_id or run_id in run_seen:
            errors.append(f'ledger.records[{i}] run_id missing/duplicate')
        run_seen.add(run_id)
        if not _valid_hash(rec.get('artifact_sha256')):
            errors.append(f'ledger.records[{i}] artifact_sha256 invalid')
        if rec.get('source_split') not in ('train', 'valid_seen', 'valid_unseen'):
            errors.append(f'ledger.records[{i}] source split invalid')
        hashes = rec.get('inspected_game_sha256')
        if not isinstance(hashes, list):
            errors.append(f'ledger.records[{i}] inspected_game_sha256 not a list')
            continue
        for h in hashes:
            if not _valid_hash(h):
                errors.append(f'ledger.records[{i}] invalid inspected game hash')
                continue
            # A raw-content identity collision matters even if an older split label differs.
            consumed.setdefault(h, set()).add(str(run_id))
    for i, c in enumerate(candidates):
        if isinstance(c, dict) and c.get('game_sha256') in consumed:
            matches.append({'candidate_index': i, 'candidate_id': c.get('candidate_id'),
                            'prior_run_ids': sorted(consumed[c['game_sha256']])})
    if errors:
        verdict = 'INVALID_AUDIT_INPUT'
    elif matches:
        verdict = 'BLOCKED_KNOWN_CONSUMPTION'
    else:
        verdict = 'BLOCKED_FRESHNESS_UNATTESTED'
    return {
        'verdict': verdict,
        'candidate_count': len(candidates),
        'historical_record_count': len(records),
        'known_overlap_count': len(matches),
        'known_overlaps': matches,
        'errors': errors,
        'scientific_gate': 'NOT_AUTHORIZED',
        'meaning': 'No overlap in a submitted ledger is NOT proof of unused identity, completeness, true bilateral competence or independent custody. Even a claimed ALL_HISTORICAL_PROJECT_USES scope and self-reported VERIFIED_UNUSED fields are not independently authenticated.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frozen_manifest', type=Path)
    parser.add_argument('historical_consumption_ledger', type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.frozen_manifest.read_text(encoding='utf-8'))
        ledger = json.loads(args.historical_consumption_ledger.read_text(encoding='utf-8'))
        report = audit(manifest, ledger)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        report = {'verdict': 'INVALID_AUDIT_INPUT', 'errors': [str(exc)], 'scientific_gate': 'NOT_AUTHORIZED'}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report['verdict'] == 'INVALID_AUDIT_INPUT' else 3  # never return an execution-authorizing zero


if __name__ == '__main__':
    raise SystemExit(main())
