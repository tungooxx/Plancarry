#!/usr/bin/env python3
"""Static/frozen-artifact validator for v2.7 competence-only executable."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNNER=ROOT/'plancarry_latent_v2_7_competence_runner.py'
DESIGN=ROOT/'results/design/plancarry_latent_v2_7_slot_bound_source_lineage_repaired_20260820T1401Z.json'
CONTRACT=ROOT/'results/design/plancarry_latent_v2_7_competence_only_runner_contract.json'
MANIFEST=ROOT/'results/design/plancarry_latent_v2_matched_pair_manifest.json'
EXPECTED={
 'design':'0b25f09d2010358c23838f0e999ce7c7bd41b1e68ce84f4f14aecafafd5bdc51',
 'contract':'b5fb54cac2548508703c54ed5b90f7562fb9952dac13685a00e59a93734999e0',
 'manifest':'285d85b10171fcec0a80cc2960a79ae3349472e3b38935b6e97ec10deeaf0feb',
}

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def validate_static():
 src=RUNNER.read_text(); tree=ast.parse(src)
 calls=set(); funcs=set(); attrs=set()
 for n in ast.walk(tree):
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)): funcs.add(n.name)
  if isinstance(n,ast.Call):
   if isinstance(n.func,ast.Name): calls.add(n.func.id)
   elif isinstance(n.func,ast.Attribute): calls.add(n.func.attr)
  if isinstance(n,ast.Attribute): attrs.add(n.attr)
 design=json.loads(DESIGN.read_text())
 forbidden={'capture','patch_score','run_confirmation','run_discovery','_capture','_patched_q','_control_cpse'}
 checks={
  'design_sha':sha(DESIGN)==EXPECTED['design'],
  'contract_sha':sha(CONTRACT)==EXPECTED['contract'],
  'manifest_sha':sha(MANIFEST)==EXPECTED['manifest'],
  'no_forbidden_execution_symbols':not ((calls|funcs|attrs)&forbidden),
  'no_layer_alpha_constants':'EXPECTED_LAYERS' not in src and 'EXPECTED_ALPHAS' not in src,
  'suffix_exact_leading_space':'return [" " + self.command_a, " " + self.command_b]' in src,
  'suffix_fail_closed':'V27_SUFFIX_LEADING_SPACE_CONTRACT_FAILED' in src,
  'competence_thresholds_fixed':'SOURCE_A_MIN = 0.10' in src and 'SOURCE_B_MAX = -0.10' in src and 'PASS_MIN = 12' in src,
  'development_only':'if idx < 0 or idx >= N' in src and 'pair.get("split") != "discovery"' in src,
  'overwrite_refusal':'REFUSE_EXISTING_OUTPUT' in src,
  'qwen_bound':'Qwen/Qwen2.5-1.5B-Instruct' in src and '989aa7980e4cf806f80c7fef2b1adb7bc71aa306' in src,
  'v27_templates_bound':'PLAN STEPS' in design['pair_variable']['source_active_template'] and 'USE THIS PLAN NOW: YES' in design['pair_variable']['source_active_template'] and 'USE THIS PLAN NOW: NO' in design['pair_variable']['source_archived_template'],
 }
 return checks

if __name__=='__main__':
 r=validate_static(); print(json.dumps(r,indent=2,sort_keys=True)); raise SystemExit(0 if all(r.values()) else 2)
