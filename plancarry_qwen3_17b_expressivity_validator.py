from pathlib import Path
import ast,hashlib,json,re
DESIGN=Path('results/design/plancarry_qwen3_17b_expressivity_recovery_design_v1.json')
MANIFEST=Path('results/design/plancarry_qwen3_17b_expressivity_recovery_manifest_v1.json')
EXPECTED={'design':'51e3f81671eddb306af3d15d4c34ba8b1301543e2efe2fce8ad0d514d0b5ec81','manifest':'bff529503ac72371102e8689be0ecf92b367b1fe039d6e62444c00b54a27d8b5'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate_static():
    src=Path('plancarry_qwen3_17b_expressivity_runner.py').read_text(); tree=ast.parse(src)
    calls={n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,(ast.Attribute,ast.Name))}
    names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
    funcs={n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    forbidden_calls={'patch_score','capture'}
    forbidden_funcs={'run_confirmation','run_discovery','control_cpse','patched_q'}
    return {'design_sha':sha(DESIGN)==EXPECTED['design'],'manifest_sha':sha(MANIFEST)==EXPECTED['manifest'],'compile':True,
      'no_forbidden_execution_symbols':not (calls & forbidden_calls) and not (funcs & forbidden_funcs) and 'EXPECTED_LAYERS' not in names,'overwrite_refusal':'OUTPUT_EXISTS_REFUSING_OVERWRITE' in src,
      'thresholds_fixed':'ma>=0.10 and mb<=-0.10' in src and "count>=PASS_MIN" in src,
      'leading_space_suffix_semantics': bool(re.search(r"return\s*\[\s*['\"] ['\"]\s*\+\s*self\.command_a\s*,\s*['\"] ['\"]\s*\+\s*self\.command_b\s*\]", src)),
      'qwen3_bound':"Qwen/Qwen3-1.7B" in src and '70d244cc86ccca08cf5af4e1e306ecf908b1ad5e' in src}
if __name__=='__main__':
    r=validate_static(); print(json.dumps(r,indent=2,sort_keys=True)); raise SystemExit(0 if all(r.values()) else 2)
