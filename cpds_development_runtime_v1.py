#!/usr/bin/env python3
"""CPDS V4 development runtime binding and load-free pre-science preflight.

This module deliberately has no top-level torch/transformers/ALFWorld/TextWorld import.
The default CLI is preflight-only. Model-facing helpers import the frozen runtime only
when explicitly called by a later ResearchDecision-bound scientific execution.
"""
from __future__ import annotations
import argparse, copy, hashlib, importlib.metadata, json, math, os, pathlib, subprocess, sys
from typing import Any, Mapping, Sequence

ROOT = pathlib.Path(__file__).resolve().parent
D = ROOT / "results" / "design"
CONTRACT_PATH = D / "plancarry_cpds_development_runtime_contract_v1_20260830.json"
V4_PATH = D / "plancarry_cpds_v4_branch_preference_endpoint_contract_a2_20260830.json"
V4_AUDIT_PATH = D / "plancarry_cpds_v4_branch_preference_endpoint_audit_a2_20260830.json"
RECURRENT_PATH = D / "plancarry_cpds_recurrent_realization_feature_basis_v1_20260829.json"
ACTUAL_AUDIT_PATH = D / "plancarry_cpds_actual_33x2_preoutcome_freeze_audit_v1_20260829.json"
CENSUS_PATH = D / "plancarry_cpds_actual_33x2_candidate_census_v1_20260829.json"
TRAIN_MANIFEST_PATH = D / "plancarry_cpds_alfworld_train_file_manifest_v1_20260829.json"
TRANSACTION_PATH = D / "plancarry_cpds_actual_33x2_durable_v1" / "assignment_freeze_transaction.json"
BUNDLE_PATH = D / "plancarry_cpds_actual_33x2_durable_v1" / "two_split_assignment_bundle.json"

BASE_COMMIT = "e152a8449760bda6cf9f4ea5e215832522479a92"
BASE_TREE = "2c3ad2ff4fbc1097e341d44fe586f3b6ffde4c52"
MODEL_ID = "Qwen/Qwen3-1.7B"
MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
MODEL_CONFIG_SHA256 = "1ddb5b89ebc90dcb417a45c213d818577e65976454d29385c8f6140771d95197"
EXACT_ARMS = ("NO_CARRY","STATIC_ONESHOT","STATIC_REPEAT","ALIGNED_RECURSION","TRANSITION_PERMUTED","MATCHED_INFORMATION")


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_file(p: pathlib.Path) -> str: return sha_bytes(p.read_bytes())
def self_hash(obj: Mapping[str, Any], field: str) -> str:
    x = copy.deepcopy(dict(obj)); x.pop(field, None); return sha_bytes(canonical_bytes(x))
def load_json(p: pathlib.Path) -> dict[str, Any]: return json.loads(p.read_text(encoding="utf-8"))
def _git(*args: str) -> str: return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_contract() -> dict[str, Any]:
    c = load_json(CONTRACT_PATH)
    validate_contract(c)
    return c


def validate_contract(c: Mapping[str, Any]) -> bool:
    req={"schema","phase","scientific_result","authority","model_runtime","development_data_realization","prompt_and_scoring","feature_and_recurrence","branch_blind_endpoint","decision_handoff","confirmation_seal","prohibited_actions","contract_sha256"}
    if not isinstance(c, Mapping) or set(c) != req: raise ValueError("CONTRACT_SCHEMA")
    if c["schema"]!="PLANCARRY_CPDS_V4_DEVELOPMENT_RUNTIME_BINDING_V1" or c["phase"]!="PRE_SCIENCE_DEVELOPMENT_RUNTIME_BINDING_ONLY" or c["scientific_result"]!="NOT_ASSESSED": raise ValueError("CONTRACT_SCOPE")
    if c["contract_sha256"] != self_hash(c,"contract_sha256"): raise ValueError("CONTRACT_SELF_HASH")
    a=c["authority"]
    expected={
      "corrected_v4_commit":BASE_COMMIT,
      "corrected_v4_tree":BASE_TREE,
      "v4_contract_sha256":"d8203d364c2ff0756418910a75d03ac3686492c2236ebc17c2922bf55be901dd",
      "v4_audit_sha256":"1ed4000bcccd77dfa46d66909c57586940fe03e93a74a79a8754810c49ea50e7",
      "actual_33x2_freeze_commit":"e4c1ed318c96f5a2e6ac3e059d5e43dfec14d16a",
      "actual_33x2_audit_sha256":"c7886e16c638cb20351a3e35a33365b7f19917aa8674cfad43a895c4272c656a",
      "recurrent_realization_commit":"30bdce87343a20994dd82cd849fd9ec210f4dc22",
      "recurrent_realization_sha256":"dc50e2a8b1d116cb81602102717e35323ce43d45d0989ca1a3783a8aaa84b772",
      "source_authority_seal":"a2ca2421f0c4405c403d09ca7f9e78066f57a1c2ee931600bbbc249ddff8810f",
      "transaction_sha256":"c00a289a098a99831e50f9d8808608abc6b71d4ef0a53d9d7d834a7cc1f13049",
      "assignment_bundle_sha256":"d01568854cabce0d2a219db3da71cd4c384f6680cf72dba455e21af21d59a002",
    }
    if any(a.get(k)!=v for k,v in expected.items()): raise ValueError("AUTHORITY_BINDING")
    m=c["model_runtime"]
    if (m.get("model_id"),m.get("revision"),m.get("config_sha256"),m.get("forward_dtype"),m.get("hidden_size")) != (MODEL_ID,MODEL_REVISION,MODEL_CONFIG_SHA256,"BF16",2048): raise ValueError("MODEL_BINDING")
    if m.get("quantization")!="NONE" or m.get("offload")!="NONE" or m.get("model_mode")!="EVAL_NO_GRAD": raise ValueError("MODEL_MODE")
    p=c["prompt_and_scoring"]
    if p.get("candidate_suffix") != " {EXACT_ACTION_STRING}" or p.get("whole_action_score") != "SUM_EXACT_SUFFIX_TOKEN_LOGPROBS_FLOAT64": raise ValueError("SCORER_CONTRACT")
    if p.get("generation_allowed") is not False or p.get("chat_template_allowed") is not False or p.get("add_special_tokens") is not False: raise ValueError("SCORER_MODE")
    e=c["branch_blind_endpoint"]
    if e.get("R_g")!="LSE_g(A)-LSE_g(B)" or e.get("D_g")!="abs(R_g-R_NO_CARRY)" or e.get("C_static")!="D_ALIGNED_RECURSION-D_STATIC_REPEAT" or e.get("C_permuted")!="D_ALIGNED_RECURSION-D_TRANSITION_PERMUTED": raise ValueError("V4_ENDPOINT")
    if e.get("correctness_semantics")!="UNDEFINED_AND_FORBIDDEN" or not e.get("seal_score_maps_before_opening_classes"): raise ValueError("BRANCH_BLINDNESS")
    if c["confirmation_seal"] != {"status":"HARD_SEALED","runtime_route_present":False,"outcome_access_allowed":False}: raise ValueError("CONFIRMATION_SEAL")
    if any(v is not False for v in c["prohibited_actions"].values()): raise ValueError("PROHIBITED_ACTION_CONTRACT")
    return True


def _internal_identity(obj: Mapping[str,Any], field: str) -> str:
    x=copy.deepcopy(dict(obj)); x.pop(field,None)
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")).hexdigest()


def verify_frozen_authorities(root: pathlib.Path = ROOT) -> dict[str, Any]:
    c=load_contract(); a=c["authority"]
    checks={
      "v4_contract": sha_file(root/V4_PATH.relative_to(ROOT))==a["v4_contract_sha256"],
      "v4_audit": sha_file(root/V4_AUDIT_PATH.relative_to(ROOT))==a["v4_audit_sha256"],
      "recurrent": sha_file(root/RECURRENT_PATH.relative_to(ROOT))==a["recurrent_realization_sha256"],
      "actual_audit": sha_file(root/ACTUAL_AUDIT_PATH.relative_to(ROOT))==a["actual_33x2_audit_sha256"],
    }
    if not all(checks.values()): raise ValueError("FROZEN_AUTHORITY_FILE_HASH")
    v4=load_json(root/V4_PATH.relative_to(ROOT)); rr=load_json(root/RECURRENT_PATH.relative_to(ROOT)); aa=load_json(root/ACTUAL_AUDIT_PATH.relative_to(ROOT))
    if v4["authority"]["source_authority_seal"]!=a["source_authority_seal"] or v4["authority"]["transaction_sha256"]!=a["transaction_sha256"] or v4["authority"]["assignment_bundle_sha256"]!=a["assignment_bundle_sha256"]: raise ValueError("V4_TRANSITIVE_AUTHORITY")
    fm=rr["frozen_model_basis"]
    if (fm["model_id"],fm["revision"],fm["config_sha256"],fm["model_forward_dtype"],fm["hidden_size"])!=(MODEL_ID,MODEL_REVISION,MODEL_CONFIG_SHA256,"BF16",2048): raise ValueError("RECURRENT_MODEL_AUTHORITY")
    if aa.get("phase")!="PRE_SCIENCE" or aa.get("scientific_result")!="NOT_ASSESSED" or aa.get("source_authority_seal")!=a["source_authority_seal"]: raise ValueError("ACTUAL_FREEZE_SCOPE")
    tx=load_json(root/TRANSACTION_PATH.relative_to(ROOT)); bu=load_json(root/BUNDLE_PATH.relative_to(ROOT))
    if _internal_identity(tx,"transaction_sha256")!=a["transaction_sha256"] or tx.get("transaction_sha256")!=a["transaction_sha256"]: raise ValueError("TRANSACTION_BINDING")
    if _internal_identity(bu,"bundle_sha256")!=a["assignment_bundle_sha256"] or bu.get("bundle_sha256")!=a["assignment_bundle_sha256"]: raise ValueError("BUNDLE_BINDING")
    return checks


def verify_model_cache(full_weight_hash: bool = True) -> dict[str, Any]:
    c=load_contract(); m=c["model_runtime"]; snap=pathlib.Path(m["snapshot_path"])
    if not snap.is_dir() or snap.name != MODEL_REVISION: raise ValueError("MODEL_SNAPSHOT_PATH")
    got={}
    for name,spec in m["snapshot_files"].items():
        p=snap/name
        if not p.exists(): raise ValueError("MODEL_FILE_MISSING:"+name)
        if p.stat().st_size != spec["bytes"]: raise ValueError("MODEL_FILE_SIZE:"+name)
        if (not name.endswith(".safetensors")) or full_weight_hash:
            h=sha_file(p)
            if h!=spec["sha256"]: raise ValueError("MODEL_FILE_SHA:"+name)
            got[name]=h
        else:
            # HF LFS cache symlink target basename is the content SHA-256 for weight blobs.
            target=p.resolve().name
            if target!=spec["sha256"]: raise ValueError("MODEL_WEIGHT_BLOB_ID:"+name)
            got[name]=target
    return got


def verify_runtime_packages() -> dict[str,str]:
    c=load_contract(); m=c["model_runtime"]
    if pathlib.Path(sys.executable).as_posix()!=m["python_executable"]: raise ValueError("PYTHON_EXECUTABLE")
    if sys.version.split()[0]!=m["python_version"]: raise ValueError("PYTHON_VERSION")
    got={}
    for pkg,exp in m["package_versions"].items():
        try: v=importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError as e: raise ValueError("PACKAGE_MISSING:"+pkg) from e
        if v!=exp: raise ValueError("PACKAGE_VERSION:"+pkg)
        got[pkg]=v
    return got


def verify_development_data() -> dict[str, Any]:
    c=load_contract(); d=c["development_data_realization"]; root=pathlib.Path(d["alfworld_data_root"])
    if not root.is_dir(): raise ValueError("ALFWORLD_DATA_ROOT")
    census=load_json(CENSUS_PATH); fm=load_json(TRAIN_MANIFEST_PATH); by={e["relative_path"]:e for e in fm}
    ids=census["selected_development_source_graph_ids"]
    if len(ids)!=33 or ids!=d["selected_development_source_graph_ids"]: raise ValueError("DEVELOPMENT_COHORT_BINDING")
    checked=[]
    train_root=root/"json_2.1.1"/"train"
    for gid in ids:
        rel=gid+"/game.tw-pddl"; e=by.get(rel)
        if not e: raise ValueError("DEVELOPMENT_MANIFEST_ENTRY:"+gid)
        p=train_root/gid/"game.tw-pddl"
        if not p.is_file() or sha_file(p)!=e["sha256"]: raise ValueError("DEVELOPMENT_DATA_SHA:"+gid)
        checked.append(gid)
    # Deliberately no confirmation-selected body read occurs here.
    return {"development_files_verified":len(checked),"confirmation_files_opened":0}


def render_policy_prompt(task_text: str, observation: str, candidate_actions: Sequence[str]) -> str:
    if not isinstance(task_text,str) or not task_text or not isinstance(observation,str) or not observation: raise ValueError("PROMPT_INPUT")
    actions=tuple(candidate_actions)
    if not actions or len(actions)!=len(set(actions)) or any(not isinstance(x,str) or not x for x in actions): raise ValueError("CANDIDATE_SET")
    return "TASK\n"+task_text+"\nCURRENT OBSERVATION\n"+observation+"\nADMISSIBLE COMMANDS\n"+"\n".join(sorted(actions))+"\n<STATE_END>\nACTION:"


def canonical_action_payload(action: str) -> bytes:
    if not isinstance(action,str) or not action: raise ValueError("ACTION")
    return json.dumps({"action":action},sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")

def canonical_transition_payload(command: str, observation: str) -> bytes:
    if not all(isinstance(x,str) and x for x in (command,observation)): raise ValueError("TRANSITION")
    return json.dumps({"command":command,"observation":observation},sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")


def _unit_l2(v: Sequence[float]) -> list[float]:
    if len(v)!=2048: raise ValueError("VECTOR_DIM")
    vals=[float(x) for x in v]
    if any(not math.isfinite(x) for x in vals): raise ValueError("VECTOR_NONFINITE")
    ss=0.0
    for x in vals: ss += x*x
    if not math.isfinite(ss) or ss<=0.0: raise ValueError("VECTOR_NORM")
    n=math.sqrt(ss); return [x/n for x in vals]

def F(z: Sequence[float], x: Sequence[float]) -> list[float]: return _unit_l2([float(a)+float(b) for a,b in zip(z,x,strict=True)])
def P(x: Sequence[float]) -> list[float]:
    if len(x)!=2048: raise ValueError("VECTOR_DIM")
    return [((-1.0 if i%2 else 1.0)*float(x[(i+1)%2048])) for i in range(2048)]
def fold(z0: Sequence[float], xs: Sequence[Sequence[float]]) -> list[float]:
    z=_unit_l2(z0)
    for x in xs: z=F(z,x)
    return z

def G_delta(z: Sequence[float], q: Sequence[float]) -> float:
    a=_unit_l2(z); b=_unit_l2(q); s=0.0
    for x,y in zip(a,b,strict=True): s += x*y
    if not math.isfinite(s): raise ValueError("G_NONFINITE")
    return s


def adjust_score_map(arm_id: str, base_scores: Mapping[str,float], z0: Sequence[float], transition_features_by_key: Mapping[str,Sequence[float]], transition_order: Sequence[str], action_features: Mapping[str,Sequence[float]]) -> dict[str,float]:
    if arm_id not in EXACT_ARMS: raise ValueError("ARM")
    actions=tuple(base_scores)
    if not actions or set(actions)!=set(action_features): raise ValueError("ACTION_FEATURE_SET")
    if any(type(base_scores[a]) not in (int,float) or not math.isfinite(float(base_scores[a])) for a in actions): raise ValueError("BASE_SCORE")
    if arm_id=="NO_CARRY": return {a:float(base_scores[a]) for a in actions}
    keys=tuple(transition_order)
    if len(keys)!=len(set(keys)) or any(k not in transition_features_by_key for k in keys): raise ValueError("TRANSITION_ORDER")
    if arm_id in ("STATIC_ONESHOT","STATIC_REPEAT"):
        z=_unit_l2(z0)
    elif arm_id=="ALIGNED_RECURSION":
        z=fold(z0,[transition_features_by_key[k] for k in keys])
    elif arm_id=="MATCHED_INFORMATION":
        z=fold(z0,[P(transition_features_by_key[k]) for k in keys])
    elif arm_id=="TRANSITION_PERMUTED":
        # Caller may invoke this only after every key in the contracted permutation has already been observed.
        z=fold(z0,[transition_features_by_key[k] for k in keys])
    else: raise AssertionError
    return {a:float(base_scores[a])+G_delta(z,action_features[a]) for a in actions}


def _lse(score_map: Mapping[str,float], actions: Sequence[str]) -> float:
    xs=sorted(actions)
    if not xs or len(xs)!=len(set(xs)): raise ValueError("CLASS_ACTIONS")
    vals=[]
    for a in xs:
        if a not in score_map: raise ValueError("CLASS_SCORE_MISSING")
        v=float(score_map[a])
        if not math.isfinite(v): raise ValueError("CLASS_SCORE_NONFINITE")
        vals.append(v)
    m=max(vals); s=0.0
    for v in vals: s += math.exp(v-m)
    return m+math.log(s)


def v4_endpoint_from_sealed_scores(sealed_score_maps: Mapping[str,Mapping[str,float]], branch_A: Sequence[str], branch_B: Sequence[str]) -> dict[str,Any]:
    if tuple(sealed_score_maps)!=EXACT_ARMS: raise ValueError("SEALED_ARM_ORDER")
    A=tuple(branch_A);B=tuple(branch_B)
    if not A or not B or len(A)!=len(set(A)) or len(B)!=len(set(B)) or set(A)&set(B): raise ValueError("BRANCH_CLASSES")
    # This is the first function in the adapter allowed to consume evaluator-only class membership.
    R={g:_lse(sealed_score_maps[g],A)-_lse(sealed_score_maps[g],B) for g in EXACT_ARMS}
    anchor=R["NO_CARRY"];D={g:abs(R[g]-anchor) for g in EXACT_ARMS}
    C={
      "static":D["ALIGNED_RECURSION"]-D["STATIC_REPEAT"],
      "permuted":D["ALIGNED_RECURSION"]-D["TRANSITION_PERMUTED"],
      "information":D["ALIGNED_RECURSION"]-D["MATCHED_INFORMATION"],
      "oneshot":D["ALIGNED_RECURSION"]-D["STATIC_ONESHOT"],
      "nocarry":D["ALIGNED_RECURSION"],
    }
    vals=list(R.values())+list(D.values())+list(C.values())
    if any(not math.isfinite(x) for x in vals): raise ValueError("ENDPOINT_NONFINITE")
    return {"R":R,"D":D,"C":C,"correctness_semantics":"UNDEFINED_AND_FORBIDDEN"}


def _load_model_runtime():
    """Explicit future-science surface. Never called by preflight/tests."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    c=load_contract(); m=c["model_runtime"]
    tok=AutoTokenizer.from_pretrained(MODEL_ID,revision=MODEL_REVISION,cache_dir=m["hf_home"],local_files_only=True,use_fast=True)
    model=AutoModelForCausalLM.from_pretrained(MODEL_ID,revision=MODEL_REVISION,cache_dir=m["hf_home"],local_files_only=True,torch_dtype=torch.bfloat16)
    model.eval(); model.requires_grad_(False)
    return torch,tok,model


def teacher_forced_whole_action_score(torch, tokenizer, model, prompt: str, action: str) -> float:
    if not isinstance(prompt,str) or not prompt or not isinstance(action,str) or not action: raise ValueError("SCORER_INPUT")
    suffix=" "+action
    pids=tokenizer(prompt,add_special_tokens=False,return_tensors=None)["input_ids"]
    fids=tokenizer(prompt+suffix,add_special_tokens=False,return_tensors=None)["input_ids"]
    if not pids or len(fids)<=len(pids) or fids[:len(pids)]!=pids: raise ValueError("TOKENIZER_PREFIX_GUARD")
    device=next(model.parameters()).device
    ids=torch.tensor([fids],dtype=torch.long,device=device)
    with torch.no_grad(): logits=model(input_ids=ids,use_cache=False).logits[0].double()
    total=0.0
    for j,tok in enumerate(fids[len(pids):]):
        pos=len(pids)+j-1
        lp=torch.log_softmax(logits[pos],dim=-1)[int(tok)]
        v=float(lp.item())
        if not math.isfinite(v): raise ValueError("SCORER_NONFINITE")
        total += v
    if not math.isfinite(total): raise ValueError("SCORER_NONFINITE")
    return total


def native_hidden_feature(torch, tokenizer, model, payload_utf8: bytes) -> list[float]:
    text=payload_utf8.decode("utf-8")
    ids=tokenizer(text,add_special_tokens=False,return_tensors=None)["input_ids"]
    if not ids: raise ValueError("EMPTY_TOKEN_SEQUENCE")
    device=next(model.parameters()).device
    x=torch.tensor([ids],dtype=torch.long,device=device)
    with torch.no_grad(): h=model.model(input_ids=x,use_cache=False).last_hidden_state[0,-1].float().cpu().tolist()
    return _unit_l2(h)


def static_preflight(*, full_weight_hash: bool=True) -> dict[str,Any]:
    verify_frozen_authorities(); packages=verify_runtime_packages(); model_files=verify_model_cache(full_weight_hash=full_weight_hash); data=verify_development_data()
    head=_git("rev-parse","HEAD"); tree=_git("rev-parse","HEAD^{tree}")
    if subprocess.run(["git","merge-base","--is-ancestor",BASE_COMMIT,head],cwd=ROOT).returncode!=0: raise ValueError("CORRECTED_V4_NOT_ANCESTOR")
    if _git("status","--porcelain"): raise ValueError("WORKTREE_NOT_CLEAN")
    return {
      "status":"READY_NO_SCIENCE",
      "phase":"PRE_SCIENCE_DEVELOPMENT_RUNTIME_BINDING_ONLY",
      "scientific_result":"NOT_ASSESSED",
      "git_commit":head,"git_tree":tree,
      "package_versions":packages,"model_files_verified":len(model_files),**data,
      "model_loads":0,"tokenizer_loads":0,"model_forwards":0,"environment_execution":0,"development_outcomes_opened":0,"confirmation_outcomes_opened":0,"future_split_access":0,"gpu_provider_lifecycle":0,"experiment_registrations":0,"prediction_registrations":0,"research_decisions":0,
    }


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--preflight",action="store_true"); ap.add_argument("--quick-model-hash",action="store_true"); args=ap.parse_args()
    if not args.preflight: raise SystemExit("PRE_SCIENCE_ONLY_USE_--preflight")
    print(json.dumps(static_preflight(full_weight_hash=not args.quick_model_hash),sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
