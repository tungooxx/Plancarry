#!/usr/bin/env python3
"""Fail-closed execution binding for corrected ReplayResidual V2.3.

Engineering/provenance only. No model, environment, provider, or study access.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, pathlib, re
from typing import Any

EXPERIMENT_ID='47972f24-71ca-4001-8a1e-ca3dddb7c621'
PREDICTION_ID='55ab178a-67cb-4d82-a91c-cc9cac14b189'
SUPERSEDED_EXPERIMENT_ID='ab513100-a6c2-40a0-b4e4-d37e60368095'
SUPERSEDED_PREDICTION_ID='cdaf8daa-714f-48ed-81e0-024298de37f0'
BASE_COMMIT='d80fbe2bbceb694c71d2d53c58b0b0d1fc56b567'
BASE_TREE='7d7e3f7fc384d9fd9fe9f8fc0dfe41e370afc490'
CONTRACT_REL=pathlib.Path('results/design/plancarry_replayresidual_v23_capability_bound_cuda_successor_contract_a1_20260828.json')
CONTRACT_SHA256='1289bbf073e4f4c6411a82cdac069ff9fe9094cacb92e4ccb333712d8af4a3bc'
REVIEW_SHA256='9776978d0a1dc2909effbdbb81c48ef2e09686ec1810fe5c1315cd405faded53'
REVIEW_VERDICT='PASS_FOR_REPLAYRESIDUAL_V23_CAPABILITY_BOUND_CUDA_SUCCESSOR_INTEGRITY_REPAIR'
RUNTIME_FINGERPRINT='bdb1e690eb1a2d0f5913d11bcb0b1915b0eaad2c91974acb7b26b2a005b94021'
PACKET_REL='results/science/plancarry_replay_residual_sanity_packets_v2_3_capability_successor1'
RESULT_REL='results/science/plancarry_replay_residual_representation_sanity_v2_3_capability_successor1.json'
VALIDATOR_REL=pathlib.Path('replayresidual_v23_capability_validator_a1.py')
VALIDATOR_SHA256='fea9a313d821902490df3052b6ddcbccdab2cb25e33df3dff622731615b5511e'
# Compatibility aliases consumed by the thin registered-packet adapter.
TEMPLATE_SHA256=CONTRACT_SHA256
POLICY_SHA256=CONTRACT_SHA256
POLICY_REVIEW_SHA256=REVIEW_SHA256
ATTESTATION_CONTRACT_SHA256=CONTRACT_SHA256
ATTESTATION_REVIEW_SHA256=REVIEW_SHA256


def sha256_file(p:pathlib.Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def canonical_bytes(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def load_template(root:pathlib.Path)->dict[str,Any]:
    p=root/CONTRACT_REL
    if sha256_file(p)!=CONTRACT_SHA256: raise RuntimeError('V23_CONTRACT_SHA256_MISMATCH')
    vp=root/VALIDATOR_REL
    if sha256_file(vp)!=VALIDATOR_SHA256: raise RuntimeError('V23_VALIDATOR_SHA256_MISMATCH')
    x=json.loads(p.read_text())
    if x.get('scientific_protocol_variables_changed')!=[] or x.get('estimand_changed') is not False:
        raise RuntimeError('V23_CONTRACT_SCIENCE_DRIFT')
    mr=x.get('model_runtime',{})
    if 'device_name_required' in mr: raise RuntimeError('EXACT_GPU_NAME_LOCK_FORBIDDEN')
    adm=x.get('execution_capability_admission',{})
    if adm.get('gpu_name_whitelist') is not None or adm.get('gpu_name_blacklist') is not None or adm.get('provider_or_instance_whitelist') is not None:
        raise RuntimeError('GPU_OR_PROVIDER_IDENTITY_LOCK_FORBIDDEN')
    return x

def validate_bound(x:dict[str,Any], template:dict[str,Any]|None=None)->dict[str,str]:
    required={
      'kind':'PLANCARRY_REPLAYRESIDUAL_V23_CORRECTED_EXECUTION_BINDING',
      'experiment_id':EXPERIMENT_ID,'prediction_id':PREDICTION_ID,
      'base_commit':BASE_COMMIT,'base_tree':BASE_TREE,
      'contract_sha256':CONTRACT_SHA256,'validator_sha256':VALIDATOR_SHA256,
      'independent_design_review_sha256':REVIEW_SHA256,'independent_design_review_verdict':REVIEW_VERDICT,
      'runtime_fingerprint':RUNTIME_FINGERPRINT,
      'packet_target':PACKET_REL,'result_target':RESULT_REL,
      'scientific_protocol_variables_changed':[],'estimand_changed':False,
      'superseded_registration_execution_forbidden':True,
    }
    for k,v in required.items():
        if x.get(k)!=v: raise RuntimeError(f'V23_BINDING_MISMATCH:{k}')
    if SUPERSEDED_EXPERIMENT_ID in json.dumps({k:v for k,v in x.items() if k!='superseded_registration_ids'}) and SUPERSEDED_EXPERIMENT_ID!=x.get('superseded_registration_ids',{}).get('experiment_id'):
        raise RuntimeError('SUPERSEDED_EXPERIMENT_EXECUTION_REFERENCE')
    s=x.get('superseded_registration_ids',{})
    if s!={'experiment_id':SUPERSEDED_EXPERIMENT_ID,'prediction_id':SUPERSEDED_PREDICTION_ID}:
        raise RuntimeError('SUPERSEDED_REGISTRATION_GUARD_MISMATCH')
    ap=pathlib.Path(str(x.get('capability_attestation_path','')))
    ah=str(x.get('capability_attestation_sha256',''))
    if not re.fullmatch(r'[0-9a-f]{64}',ah): raise RuntimeError('CAPABILITY_ATTESTATION_SHA_INVALID')
    if not ap.is_file() or sha256_file(ap)!=ah: raise RuntimeError('CAPABILITY_ATTESTATION_FILE_OR_SHA_MISMATCH')
    a=json.loads(ap.read_text())
    if a.get('runtime_fingerprint')!=RUNTIME_FINGERPRINT: raise RuntimeError('RUNTIME_FINGERPRINT_MISMATCH')
    if template is None: raise RuntimeError('V23_CONTRACT_REQUIRED')
    # Import the frozen validator only after its byte hash has been checked by load_template.
    import importlib.util
    spec=importlib.util.spec_from_file_location('rr_v23_validator',str(VALIDATOR_REL.resolve()))
    m=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m)
    errors=m.validate_attestation(template,a)
    if errors: raise RuntimeError('CAPABILITY_ATTESTATION_REJECTED:'+','.join(errors))
    return {'experiment_id':EXPERIMENT_ID,'prediction_id':PREDICTION_ID,'runtime_fingerprint':RUNTIME_FINGERPRINT,'capability_attestation_sha256':ah}

def bind(root:pathlib.Path,attestation:pathlib.Path)->dict[str,Any]:
    contract=load_template(root)
    a=attestation.resolve()
    if not a.is_file(): raise RuntimeError('CAPABILITY_ATTESTATION_REQUIRED')
    obj={
      'kind':'PLANCARRY_REPLAYRESIDUAL_V23_CORRECTED_EXECUTION_BINDING',
      'experiment_id':EXPERIMENT_ID,'prediction_id':PREDICTION_ID,
      'base_commit':BASE_COMMIT,'base_tree':BASE_TREE,
      'contract_path':str((root/CONTRACT_REL).resolve()),'contract_sha256':CONTRACT_SHA256,
      'validator_sha256':VALIDATOR_SHA256,
      'independent_design_review_sha256':REVIEW_SHA256,'independent_design_review_verdict':REVIEW_VERDICT,
      'runtime_fingerprint':RUNTIME_FINGERPRINT,
      'capability_attestation_path':str(a),'capability_attestation_sha256':sha256_file(a),
      'packet_target':PACKET_REL,'result_target':RESULT_REL,
      'scientific_protocol_variables_changed':[],'estimand_changed':False,
      'superseded_registration_ids':{'experiment_id':SUPERSEDED_EXPERIMENT_ID,'prediction_id':SUPERSEDED_PREDICTION_ID},
      'superseded_registration_execution_forbidden':True,
      'gpu_name_is_provenance_not_authority':True,'provider_instance_is_provenance_not_scientific_authority':True,
    }
    validate_bound(obj,contract)
    return obj

def main()->int:
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    b=sub.add_parser('bind'); b.add_argument('--root',default='.'); b.add_argument('--attestation',required=True); b.add_argument('--output',required=True)
    v=sub.add_parser('validate-bound'); v.add_argument('--root',default='.'); v.add_argument('--input',required=True)
    args=ap.parse_args(); root=pathlib.Path(args.root).resolve(); contract=load_template(root)
    if args.cmd=='bind':
        out=pathlib.Path(args.output)
        if out.exists(): raise RuntimeError('BOUND_OUTPUT_EXISTS_REFUSE_OVERWRITE')
        obj=bind(root,pathlib.Path(args.attestation)); out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
        print(json.dumps({'status':'BOUND_PRE_EXECUTION','sha256':sha256_file(out),'experiment_id':EXPERIMENT_ID,'prediction_id':PREDICTION_ID,'runtime_fingerprint':RUNTIME_FINGERPRINT},sort_keys=True)); return 0
    obj=json.loads(pathlib.Path(args.input).read_text()); info=validate_bound(obj,contract)
    print(json.dumps({'status':'BOUND_VALID',**info},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
