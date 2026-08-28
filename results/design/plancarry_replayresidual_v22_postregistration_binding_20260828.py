#!/usr/bin/env python3
"""Bind the reviewed ReplayResidual V2.2 template to fresh post-review registration IDs.

Engineering/provenance only. This module never calls a model, environment, Research OS,
or reads any science packet/result artifact.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, re, uuid
from pathlib import Path
from typing import Any

TEMPLATE_REL = Path('results/design/plancarry_replayresidual_v22_unified_execution_contract_template_20260828.json')
TEMPLATE_SHA256 = '691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1'
PARENT_SHA256 = '83370fbfc65c4818ada159a0e3c83cf778b88ed02f964bcf7887e5cea3843158'
POLICY_SHA256 = 'c9ee11ccaad981441c1462a60b59b9bd4ffa021b149ac4f0d18df568f4724c70'
POLICY_REVIEW_SHA256 = '7044718fbef271fb86d8243e4345e2970894a66d65326be2c9d292af9214c750'
ATTESTATION_CONTRACT_SHA256 = '40ae9747f675dc136a59ecc6e2c7ae28d4d329860566c542cbf1691d84bbc666'
ATTESTATION_REVIEW_SHA256 = 'a03a4cc7f2d7c83fe8df3112edba5b373bd0d4241d6f20731a373f62adc39765'
REQUIRED_MATERIALIZATION_REVIEW_VERDICT = 'PASS_FOR_REPLAYRESIDUAL_V22_MATERIALIZATION_RECOVERY'
UNBOUND = 'UNBOUND_REQUIRES_POSTREGISTRATION_BINDING'


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(p: Path) -> str:
    return sha256_bytes(p.read_bytes())

def canonical_bytes(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def canonical_no_self_hash(obj: dict[str, Any]) -> str:
    x = copy.deepcopy(obj)
    x.pop('canonical_object_sha256_without_self_field', None)
    return sha256_bytes(canonical_bytes(x))

def _uuid(s: str, label: str) -> str:
    try: return str(uuid.UUID(s))
    except Exception as e: raise ValueError(f'{label}_MUST_BE_UUID:{s}') from e

def _sha(s: str, label: str) -> str:
    if not re.fullmatch(r'[0-9a-f]{64}', s): raise ValueError(f'{label}_MUST_BE_LOWER_HEX_SHA256')
    return s

def load_template(root: Path) -> dict[str, Any]:
    p = root / TEMPLATE_REL
    if sha256_file(p) != TEMPLATE_SHA256: raise RuntimeError('V22_TEMPLATE_SHA256_MISMATCH')
    x = json.loads(p.read_text(encoding='utf-8'))
    if x.get('canonical_object_sha256_without_self_field') != canonical_no_self_hash(x):
        raise RuntimeError('V22_TEMPLATE_CANONICAL_SELF_HASH_MISMATCH')
    t = x.get('technical_successor_v2_2', {})
    if t.get('parent_v2_1_contract', {}).get('sha256') != PARENT_SHA256: raise RuntimeError('PARENT_CONTRACT_BINDING_MISMATCH')
    if t.get('successor_policy', {}).get('sha256') != POLICY_SHA256 or t.get('successor_policy', {}).get('independent_review_sha256') != POLICY_REVIEW_SHA256:
        raise RuntimeError('SUCCESSOR_POLICY_BINDING_MISMATCH')
    if t.get('execution_attestation', {}).get('contract_sha256') != ATTESTATION_CONTRACT_SHA256 or t.get('execution_attestation', {}).get('independent_review_sha256') != ATTESTATION_REVIEW_SHA256:
        raise RuntimeError('ATTESTATION_BINDING_MISMATCH')
    if t.get('registration_binding', {}).get('successor_experiment_id') != UNBOUND or t.get('registration_binding', {}).get('successor_prediction_id') != UNBOUND:
        raise RuntimeError('TEMPLATE_ALREADY_BOUND')
    return x

def bind_contract(root: Path, experiment_id: str, prediction_id: str, review_work_item_id: str, review_sha256: str, review_verdict: str) -> dict[str, Any]:
    if review_verdict != REQUIRED_MATERIALIZATION_REVIEW_VERDICT:
        raise RuntimeError('MATERIALIZATION_REVIEW_NOT_EXACT_PASS')
    experiment_id = _uuid(experiment_id, 'EXPERIMENT_ID')
    prediction_id = _uuid(prediction_id, 'PREDICTION_ID')
    review_work_item_id = _uuid(review_work_item_id, 'REVIEW_WORK_ITEM_ID')
    review_sha256 = _sha(review_sha256, 'REVIEW_SHA256')
    template = load_template(root)
    x = copy.deepcopy(template)
    x['kind'] = 'PLANCARRY_REPLAY_RESIDUAL_UNIFIED_EXECUTION_CONTRACT_V2_2_TECHNICAL_SUCCESSOR_BOUND'
    t = x['technical_successor_v2_2']
    t['status'] = 'BOUND_POSTREGISTRATION_PRE_EXECUTION'
    rb = t['registration_binding']
    rb['successor_experiment_id'] = experiment_id
    rb['successor_prediction_id'] = prediction_id
    rb['materialization_review_work_item_id'] = review_work_item_id
    rb['materialization_review_sha256'] = review_sha256
    rb['materialization_review_verdict'] = review_verdict
    rb['template_sha256'] = TEMPLATE_SHA256
    x['canonical_object_sha256_without_self_field'] = canonical_no_self_hash(x)
    validate_bound(x, template)
    return x

def validate_bound(x: dict[str, Any], template: dict[str, Any] | None = None) -> dict[str, str]:
    if x.get('kind') != 'PLANCARRY_REPLAY_RESIDUAL_UNIFIED_EXECUTION_CONTRACT_V2_2_TECHNICAL_SUCCESSOR_BOUND': raise RuntimeError('BOUND_KIND_MISMATCH')
    if x.get('canonical_object_sha256_without_self_field') != canonical_no_self_hash(x): raise RuntimeError('BOUND_CANONICAL_SELF_HASH_MISMATCH')
    t = x.get('technical_successor_v2_2', {})
    if t.get('status') != 'BOUND_POSTREGISTRATION_PRE_EXECUTION' or t.get('scientific_variables_changed') != []: raise RuntimeError('BOUND_STATUS_OR_SCIENCE_DRIFT')
    if t.get('parent_v2_1_contract', {}).get('sha256') != PARENT_SHA256: raise RuntimeError('BOUND_PARENT_MISMATCH')
    if t.get('execution_attestation', {}).get('contract_sha256') != ATTESTATION_CONTRACT_SHA256 or t.get('execution_attestation', {}).get('independent_review_sha256') != ATTESTATION_REVIEW_SHA256: raise RuntimeError('BOUND_ATTESTATION_MISMATCH')
    rb = t.get('registration_binding', {})
    exp = _uuid(str(rb.get('successor_experiment_id','')), 'EXPERIMENT_ID')
    pred = _uuid(str(rb.get('successor_prediction_id','')), 'PREDICTION_ID')
    _uuid(str(rb.get('materialization_review_work_item_id','')), 'REVIEW_WORK_ITEM_ID')
    _sha(str(rb.get('materialization_review_sha256','')), 'REVIEW_SHA256')
    if rb.get('materialization_review_verdict') != REQUIRED_MATERIALIZATION_REVIEW_VERDICT: raise RuntimeError('BOUND_REVIEW_NOT_PASS')
    if rb.get('template_sha256') != TEMPLATE_SHA256: raise RuntimeError('BOUND_TEMPLATE_SHA_MISMATCH')
    if t.get('output_binding',{}).get('old_v2_1_packet_or_result_contents_may_be_successor_input') is not False: raise RuntimeError('OLD_SCIENCE_INPUT_GUARD_MISSING')
    if template is not None:
        expected=copy.deepcopy(template)
        expected['kind']='PLANCARRY_REPLAY_RESIDUAL_UNIFIED_EXECUTION_CONTRACT_V2_2_TECHNICAL_SUCCESSOR_BOUND'
        et=expected['technical_successor_v2_2']; et['status']='BOUND_POSTREGISTRATION_PRE_EXECUTION'
        erb=et['registration_binding']
        for key in ('successor_experiment_id','successor_prediction_id','materialization_review_work_item_id','materialization_review_sha256','materialization_review_verdict','template_sha256'):
            erb[key]=rb[key]
        expected['canonical_object_sha256_without_self_field']=canonical_no_self_hash(expected)
        if expected != x: raise RuntimeError('BOUND_CONTRACT_DRIFT_OUTSIDE_POSTREGISTRATION_FIELDS')
    return {'experiment_id':exp,'prediction_id':pred,'materialization_review_sha256':str(rb['materialization_review_sha256'])}

def main() -> int:
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest='cmd',required=True)
    b=sub.add_parser('bind')
    b.add_argument('--root',default='.')
    b.add_argument('--experiment-id',required=True); b.add_argument('--prediction-id',required=True)
    b.add_argument('--materialization-review-work-item-id',required=True); b.add_argument('--materialization-review-sha256',required=True)
    b.add_argument('--materialization-review-verdict',required=True); b.add_argument('--output',required=True)
    v=sub.add_parser('validate-bound'); v.add_argument('--input',required=True); v.add_argument('--root',default='.')
    args=ap.parse_args()
    if args.cmd=='bind':
        root=Path(args.root).resolve(); out=Path(args.output)
        if out.exists(): raise RuntimeError('BOUND_OUTPUT_EXISTS_REFUSE_OVERWRITE')
        obj=bind_contract(root,args.experiment_id,args.prediction_id,args.materialization_review_work_item_id,args.materialization_review_sha256,args.materialization_review_verdict)
        out.parent.mkdir(parents=True,exist_ok=True)
        payload=json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False)+'\n'
        out.write_text(payload,encoding='utf-8')
        print(json.dumps({'status':'BOUND_PRE_EXECUTION','output':str(out),'sha256':sha256_file(out),'experiment_id':args.experiment_id,'prediction_id':args.prediction_id},sort_keys=True))
        return 0
    obj=json.loads(Path(args.input).read_text(encoding='utf-8')); info=validate_bound(obj, load_template(Path(args.root).resolve()))
    print(json.dumps({'status':'BOUND_VALID',**info},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
