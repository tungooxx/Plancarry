#!/usr/bin/env python3
"""Frozen PlanCarry-Latent v2.4 discovery/confirmation runner.

Scientific configuration comes from immutable preregistration artifacts.  This
runner is deliberately fail-closed: confirmation cannot run without a caller-
supplied SHA256 for the previously frozen discovery-selection artifact, and
live bridge calls require exact GTX1650/model provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from alfworld_runtime import ACTIVE_DATA_ROOT, AlfRuntime, stable_json as alf_stable_json
from plancarry_latent_v2_4_validator import (
    DONOR_MAP_SHA256,
    MANIFEST_SHA256,
    PREREG_SHA256,
    REVIEW_SHA256,
    STATIC_AUDIT_SHA256,
    TOKENIZER_AUDIT_SHA256,
    confirmation_decision,
    l2,
    load_json,
    normalized_contrast,
    option_orientation_bit,
    q_a,
    rademacher_direction,
    require_frozen_bundle,
    sha256_file,
    stable_json,
    verify_selection_artifact,
)
from whitebox_client import WhiteboxClient

EXPECTED_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
EXPECTED_MODEL_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
EXPECTED_TRANSFORMERS = "4.46.3"
EXPECTED_TOKENIZERS = "0.20.3"
EXPECTED_LAYERS = [6, 13, 20, 27]
EXPECTED_ALPHAS = [0.05, 0.1, 0.2]
DIRECTION_EPS = 1e-8
ROOT = Path(__file__).resolve().parent


class ClientProtocol(Protocol):
    def model_info(self) -> dict[str, Any]: ...
    def score_sequences(self, prompt: str, suffixes: list[str]) -> dict[str, Any]: ...
    def capture(self, text: str, layer: int, token_index: int = -1) -> dict[str, Any]: ...
    def patch_score(self, prompt: str, suffixes: list[str], layer: int, vector: list[float], token_index: int = -1, mode: str = "add", scale: float = 1.0) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PairContext:
    pair_index: int
    family: str
    delayed_divergence: bool
    reset_block: str
    active_a: str
    active_b: str
    archived_a: str
    archived_b: str
    command_a: str
    command_b: str
    option_orientation_bit: int

    def __post_init__(self) -> None:
        for name, text in [("reset_block", self.reset_block), ("active_a", self.active_a),
                           ("active_b", self.active_b), ("archived_a", self.archived_a),
                           ("archived_b", self.archived_b)]:
            if "\\n" in text:
                raise RuntimeError(f"V24_LITERAL_BACKSLASH_N_FORBIDDEN {name}")
            if not text.endswith("<STATE_END>\n") or text.endswith("<STATE_END>\n\n"):
                raise RuntimeError(f"V24_TERMINAL_NEWLINE_CONTRACT_FAILED {name}")

    @property
    def scoring_prompt(self) -> str:
        return self.reset_block + "ACTION:"

    @property
    def suffixes(self) -> list[str]:
        return [" " + self.command_a, " " + self.command_b]

    def source_scoring_prompt(self, which: str) -> str:
        text = {"active_a": self.active_a, "active_b": self.active_b,
                "archived_a": self.archived_a, "archived_b": self.archived_b}[which]
        return text + "ACTION:"


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hjson(obj: Any) -> str:
    return hashlib.sha256(alf_stable_json(obj).encode("utf-8")).hexdigest()


def _task_line(initial_observation: str) -> str:
    rows = [line.strip() for line in initial_observation.splitlines() if line.strip().startswith("Your task is to:")]
    if len(rows) != 1:
        raise RuntimeError(f"TASK_TEXT_EXTRACTION_FAILED count={len(rows)}")
    return rows[0]


def _game_path(pair: dict[str, Any]) -> str:
    p = Path(pair["game_path"])
    if p.is_absolute():
        return str(p)
    return str((ACTIVE_DATA_ROOT / p).resolve())


def _lex_bag(text: str) -> list[str]:
    return sorted(re.findall(r"\w+|[^\w\s]", text.lower(), flags=re.UNICODE))


def _clause(obj: dict[str, Any], target: str) -> str:
    return f'Complete {obj["object"]} from {obj["source"]} into {target}.'


def build_pair_context(pair: dict[str, Any], prereg: dict[str, Any]) -> PairContext:
    idx = int(pair["frozen_pair_index"])
    if idx < 0 or idx >= 40:
        raise RuntimeError("PAIR_INDEX_OUT_OF_RANGE")
    rt = AlfRuntime(_game_path(pair), max_steps=40)
    try:
        initial_observation = rt.observation
        for command in pair["common_prefix_actions"]:
            out = rt.step(command)
            if out.error:
                raise RuntimeError(f"RESET_REPLAY_INVALID_COMMAND pair={idx} {out.error}")
        if rt.hash() != pair["reset_state_hash"]:
            raise RuntimeError(f"RESET_STATE_HASH_MISMATCH pair={idx}")
        if _sha_text(rt.observation) != pair["reset_observation_sha256"]:
            raise RuntimeError(f"RESET_OBSERVATION_HASH_MISMATCH pair={idx}")
        commands = list(rt.admissible_commands)
        if commands != pair["reset_admissible_commands"] or _hjson(commands) != pair["reset_admissible_commands_sha256"]:
            raise RuntimeError(f"RESET_COMMANDS_HASH_MISMATCH pair={idx}")
        task = _task_line(initial_observation)
        reset_obs = rt.observation
    finally:
        rt.close()

    sorted_commands = sorted(commands)
    scoring_cfg = prereg["action_scoring"]
    pair_cfg = prereg["pair_variable"]
    reset_block = scoring_cfg["reset_block"].format(
        TASK_TEXT=task, RESET_OBSERVATION=reset_obs,
        ONE_COMMAND_PER_LINE_LEXICOGRAPHIC="\n".join(sorted_commands),
    )
    pair_reset = pair_cfg["reset_template"].format(
        TASK_TEXT=task, RESET_OBSERVATION=reset_obs,
        ONE_COMMAND_PER_LINE_LEXICOGRAPHIC="\n".join(sorted_commands),
    )
    if reset_block != pair_reset:
        raise RuntimeError(f"V24_RESET_TEMPLATE_DIVERGENCE pair={idx}")
    bit = option_orientation_bit(idx)
    if bit == 0:
        oa, ob = pair["object_a"], pair["object_b"]
        command_a, command_b = pair["a_first_divergent_action"], pair["b_first_divergent_action"]
    else:
        oa, ob = pair["object_b"], pair["object_a"]
        command_a, command_b = pair["b_first_divergent_action"], pair["a_first_divergent_action"]
    if command_a not in commands or command_b not in commands or command_a == command_b:
        raise RuntimeError(f"DIVERGENT_COMMAND_GUARD_FAILED pair={idx}")
    ca, cb = _clause(oa, pair["target_receptacle"]), _clause(ob, pair["target_receptacle"])
    active_a = pair_cfg["source_active_template"].format(RESET_BLOCK=reset_block, CLAUSE_A=ca, CLAUSE_B=cb)
    if active_a.count("ACTIVE ORDER: A THEN B") != 1:
        raise RuntimeError(f"V24_ACTIVE_TEMPLATE_MARKER_GUARD_FAILED pair={idx}")
    active_b = active_a.replace("ACTIVE ORDER: A THEN B", "ACTIVE ORDER: B THEN A", 1)
    archived_a = pair_cfg["source_archived_template"].format(RESET_BLOCK=reset_block, CLAUSE_A=ca, CLAUSE_B=cb)
    if archived_a.count("ARCHIVED ORDER: A THEN B") != 1:
        raise RuntimeError(f"V24_ARCHIVED_TEMPLATE_MARKER_GUARD_FAILED pair={idx}")
    archived_b = archived_a.replace("ARCHIVED ORDER: A THEN B", "ARCHIVED ORDER: B THEN A", 1)
    if _lex_bag(active_a) != _lex_bag(active_b) or _lex_bag(archived_a) != _lex_bag(archived_b):
        raise RuntimeError(f"LEXICAL_MULTISET_GUARD_FAILED pair={idx}")
    return PairContext(idx, pair["family"], bool(pair["delayed_divergence"]), reset_block,
                       active_a, active_b, archived_a, archived_b, command_a, command_b, bit)


def validate_bridge_info(info: dict[str, Any]) -> None:
    checks = {
        "mode": info.get("mode") == "real",
        "model_id": info.get("model_id") == EXPECTED_MODEL_ID,
        "revision_requested": info.get("model_revision_requested") == EXPECTED_MODEL_REVISION,
        "revision_resolved": info.get("model_commit_resolved") == EXPECTED_MODEL_REVISION,
        "device": "cuda" in str(info.get("device", "")).lower(),
        "device_name": "gtx 1650" in str(info.get("device_name", "")).lower(),
        "dtype": str(info.get("dtype", "")).lower() in {"torch.float16", "float16", "fp16"},
        "transformers": info.get("transformers_version") == EXPECTED_TRANSFORMERS,
        "tokenizers": info.get("tokenizers_version") == EXPECTED_TOKENIZERS,
        "quantization": str(info.get("quantization", "")).upper() == "NONE",
        "layers": int(info.get("num_layers", -1)) == 28,
        "hidden_size": int(info.get("hidden_size", -1)) == 1536,
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise RuntimeError(f"BRIDGE_PROVENANCE_GATE_FAILED fields={bad} info={{{', '.join(f'{k}={info.get(k)!r}' for k in bad)}}}")


def _score_pair(client: ClientProtocol, prompt: str, suffixes: list[str]) -> tuple[float, float, list[float]]:
    response = client.score_sequences(prompt, suffixes)
    q, margin, _ = q_a(response)
    rows = response["scores"]
    mean_lps = [float(r["logprob_sum"]) / int(r["token_count"]) for r in rows]
    return q, margin, mean_lps


def _patched_q(client: ClientProtocol, ctx: PairContext, layer: int, token_index: int,
               direction: list[float], scale: float) -> tuple[float, list[float]]:
    response = client.patch_score(ctx.scoring_prompt, ctx.suffixes, layer, direction,
                                  token_index=token_index, mode="add", scale=scale)
    q, _margin, _ = q_a(response)
    rows = response["scores"]
    mean_lps = [float(r["logprob_sum"]) / int(r["token_count"]) for r in rows]
    return q, mean_lps


def _control_cpse(client: ClientProtocol, ctx: PairContext, layer: int, token_index: int,
                  direction: list[float], target_norm: float, alpha: float) -> tuple[float, float, float]:
    scale = alpha * target_norm
    qplus, _ = _patched_q(client, ctx, layer, token_index, direction, +scale)
    qminus, _ = _patched_q(client, ctx, layer, token_index, direction, -scale)
    return qplus - qminus, qplus, qminus


def _capture(client: ClientProtocol, text: str, layer: int) -> dict[str, Any]:
    out = client.capture(text, layer, token_index=-1)
    if int(out.get("token_index_resolved", -2)) != int(out.get("sequence_length", -1)) - 1:
        raise RuntimeError("STATE_END_CAPTURE_INDEX_GUARD_FAILED")
    if int(out.get("hidden_size", -1)) != len(out.get("vector", [])):
        raise RuntimeError("CAPTURE_VECTOR_DIM_GUARD_FAILED")
    return out


def _source_direction(client: ClientProtocol, a: str, b: str, layer: int) -> tuple[list[float], float, int, int]:
    ca, cb = _capture(client, a, layer), _capture(client, b, layer)
    if int(ca["sequence_length"]) != int(cb["sequence_length"]):
        raise RuntimeError("SOURCE_TOKENIZER_LENGTH_GUARD_FAILED")
    d, norm = normalized_contrast(ca["vector"], cb["vector"], DIRECTION_EPS)
    return d, norm, int(ca["sequence_length"]), int(ca["hidden_size"])


def source_competence(client: ClientProtocol, ctx: PairContext) -> dict[str, Any]:
    qa, ma, _ = _score_pair(client, ctx.source_scoring_prompt("active_a"), ctx.suffixes)
    qb, mb, _ = _score_pair(client, ctx.source_scoring_prompt("active_b"), ctx.suffixes)
    competent = ma >= 0.10 and mb <= -0.10
    return {"margin_source_a": ma, "margin_source_b": mb, "q_source_a": qa, "q_source_b": qb, "competent": competent}


def plumbing_guard(client: ClientProtocol, contexts: dict[int, PairContext]) -> dict[str, Any]:
    details = []
    for idx in [0, 1]:
        ctx = contexts[idx]
        for layer in EXPECTED_LAYERS:
            cap = _capture(client, ctx.reset_block, layer)
            patch_index = int(cap["sequence_length"]) - 1
            base = client.score_sequences(ctx.scoring_prompt, ctx.suffixes)
            zero = client.patch_score(ctx.scoring_prompt, ctx.suffixes, layer, cap["vector"],
                                      token_index=patch_index, mode="add", scale=0.0)
            selfp = client.patch_score(ctx.scoring_prompt, ctx.suffixes, layer, cap["vector"],
                                       token_index=patch_index, mode="replace", scale=1.0)
            def means(resp):
                return [float(r["logprob_sum"]) / int(r["token_count"]) for r in resp["scores"]]
            bm, zm, sm = means(base), means(zero), means(selfp)
            zero_max = max(abs(x-y) for x,y in zip(bm, zm))
            self_max = max(abs(x-y) for x,y in zip(bm, sm))
            if zero_max > 1e-6 or self_max > 1e-4:
                raise RuntimeError(f"PLUMBING_GUARD_FAILED pair={idx} layer={layer} zero={zero_max} self={self_max}")
            details.append({"pair_index": idx, "layer": layer, "zero_add_max_abs": zero_max, "self_patch_max_abs": self_max})
    return {"passed": True, "details": details}


def _contexts_for_split(manifest: dict[str, Any], prereg: dict[str, Any], split: str) -> dict[int, PairContext]:
    wanted = range(0,20) if split == "discovery" else range(20,40)
    rows = {int(r["frozen_pair_index"]): r for r in manifest["selected_pairs"]}
    out = {}
    for idx in wanted:
        row = rows[idx]
        if row.get("split") != split:
            raise RuntimeError(f"MANIFEST_SPLIT_MISMATCH pair={idx}")
        out[idx] = build_pair_context(row, prereg)
    return out


def _capture_layer_material(client: ClientProtocol, contexts: dict[int, PairContext], layer: int) -> dict[int, dict[str, Any]]:
    material: dict[int, dict[str, Any]] = {}
    for idx, ctx in contexts.items():
        active, active_norm, active_len, hidden = _source_direction(client, ctx.active_a, ctx.active_b, layer)
        archived, archived_norm, archived_len, hidden2 = _source_direction(client, ctx.archived_a, ctx.archived_b, layer)
        if hidden != hidden2 or active_len != archived_len:
            raise RuntimeError(f"SOURCE_SHAPE_GUARD_FAILED pair={idx} layer={layer}")
        reset = _capture(client, ctx.reset_block, layer)
        material[idx] = {
            "active_direction": active, "active_source_norm": active_norm,
            "archived_direction": archived, "archived_source_norm": archived_norm,
            "reset_vector": reset["vector"], "reset_norm": l2(reset["vector"]),
            "target_patch_index": int(reset["sequence_length"]) - 1,
            "hidden_size": hidden,
        }
    return material


def run_discovery(client: ClientProtocol, output: Path) -> str:
    bundle = require_frozen_bundle(ROOT)
    info = client.model_info(); validate_bridge_info(info)
    contexts = _contexts_for_split(bundle["manifest"], bundle["prereg"], "discovery")
    plumbing = plumbing_guard(client, contexts)
    competence = {idx: source_competence(client, ctx) for idx, ctx in contexts.items()}
    competent_indices = [i for i in range(20) if competence[i]["competent"]]
    if len(competent_indices) < 12:
        result = {"kind":"PLANCARRY_LATENT_V2_4_DISCOVERY", "status":"INCONCLUSIVE_MODEL_EXPRESSIVITY",
                  "competent_count":len(competent_indices), "competence":competence,
                  "frozen_refs":{"prereg_sha256":PREREG_SHA256,"manifest_sha256":MANIFEST_SHA256,"donor_map_sha256":DONOR_MAP_SHA256,
                                 "independent_review_sha256":REVIEW_SHA256,"static_audit_sha256":STATIC_AUDIT_SHA256,
                                 "tokenizer_audit_sha256":TOKENIZER_AUDIT_SHA256},
                  "model_info":info,"plumbing":plumbing,"scientific_result":"NOT_ASSESSED_DISCOVERY_SELECTION_ONLY"}
        output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
        return sha256_file(output)

    layer_material = {layer: _capture_layer_material(client, contexts, layer) for layer in EXPECTED_LAYERS}
    grid_rows=[]
    discovery_indices=list(range(20))
    for layer in EXPECTED_LAYERS:
        mat=layer_material[layer]
        for alpha in EXPECTED_ALPHAS:
            per=[]
            for idx in competent_indices:
                ctx=contexts[idx]; m=mat[idx]; hidden=m["hidden_size"]
                donor=discovery_indices[(discovery_indices.index(idx)+1)%20]
                controls={
                    "active":m["active_direction"],
                    "archived":m["archived_direction"],
                    "random":rademacher_direction("discovery",idx,layer,hidden),
                    "unrelated":mat[donor]["active_direction"],
                }
                row={"pair_index":idx}
                for name,direction in controls.items():
                    cpse,_qp,_qm=_control_cpse(client,ctx,layer,m["target_patch_index"],direction,m["reset_norm"],alpha)
                    row["cpse_"+name]=cpse
                per.append(row)
            means={name:sum(r["cpse_"+name] for r in per)/len(per) for name in ["active","archived","random","unrelated"]}
            selection_score=means["active"]-max(abs(means[x]) for x in ["archived","random","unrelated"])
            grid_rows.append({"layer":layer,"alpha":alpha,"competent_n":len(per),"means":means,"selection_score":selection_score,"per_pair":per})
            print(json.dumps({"phase":"discovery_grid","layer":layer,"alpha":alpha,"completed":True}),flush=True)
    selected=sorted(grid_rows,key=lambda r:(-r["selection_score"],-r["means"]["active"],r["alpha"],r["layer"]))[0]
    sl=int(selected["layer"]); sa=float(selected["alpha"])
    donor_dirs={str(i):{
        "direction":layer_material[sl][i]["active_direction"],
        "source_norm":layer_material[sl][i]["active_source_norm"],
        "family":contexts[i].family,
    } for i in range(20)}
    selection={
        "kind":"PLANCARRY_LATENT_V2_4_DISCOVERY_SELECTION",
        "scientific_result":"NOT_ASSESSED_DISCOVERY_SELECTION_ONLY",
        "confirmation_requests_made":False,
        "frozen_refs":{"prereg_sha256":PREREG_SHA256,"manifest_sha256":MANIFEST_SHA256,
                       "donor_map_sha256":DONOR_MAP_SHA256,"independent_review_sha256":REVIEW_SHA256,
                        "static_audit_sha256":STATIC_AUDIT_SHA256,"tokenizer_audit_sha256":TOKENIZER_AUDIT_SHA256},
        "model_info":info,
        "plumbing":plumbing,
        "competence":competence,
        "competent_indices":competent_indices,
        "selected_layer":sl,"selected_alpha":sa,
        "selection_rule":"higher selection score, then higher mean active, then smaller alpha, then smaller layer",
        "selected_grid_row":selected,
        "grid_aggregate":[{k:v for k,v in r.items() if k!="per_pair"} for r in grid_rows],
        "discovery_active_directions":donor_dirs,
        "claim_scope":"Discovery selection only; no confirmation or hypothesis assessment.",
    }
    output.write_text(json.dumps(selection,indent=2,sort_keys=True,allow_nan=False)+"\n")
    return sha256_file(output)


def run_confirmation(client: ClientProtocol, selection_path: Path, selection_sha256: str, output: Path) -> str:
    bundle=require_frozen_bundle(ROOT)
    selection=verify_selection_artifact(selection_path,selection_sha256)
    info=client.model_info(); validate_bridge_info(info)
    # Exact model/runtime identity must match the discovery selection.
    for key in ["model_id","model_revision_requested","model_commit_resolved","device_name","dtype","transformers_version","tokenizers_version","quantization","hidden_size","num_layers","torch_version"]:
        if selection["model_info"].get(key)!=info.get(key):
            raise RuntimeError(f"DISCOVERY_CONFIRMATION_MODEL_DRIFT field={key}")
    contexts=_contexts_for_split(bundle["manifest"],bundle["prereg"],"confirmation")
    competence={idx:source_competence(client,ctx) for idx,ctx in contexts.items()}
    overall=sum(1 for idx in range(20,40) if competence[idx]["competent"])
    delayed=sum(1 for idx in range(20,40) if contexts[idx].delayed_divergence and competence[idx]["competent"])
    if overall<16 or delayed<8:
        result={"kind":"PLANCARRY_LATENT_V2_4_CONFIRMATION","status":"INCONCLUSIVE_MODEL_EXPRESSIVITY",
                "overall_competent":overall,"delayed_competent":delayed,"competence":competence,
                "selection_sha256":selection_sha256,"model_info":info,"scientific_result":"INCONCLUSIVE_MODEL_EXPRESSIVITY",
                "frozen_refs":{"prereg_sha256":PREREG_SHA256,"manifest_sha256":MANIFEST_SHA256,"donor_map_sha256":DONOR_MAP_SHA256}}
        output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        return sha256_file(output)
    layer=int(selection["selected_layer"]); alpha=float(selection["selected_alpha"])
    material=_capture_layer_material(client,contexts,layer)
    donor_map={int(r["confirmation_pair_index"]):int(r["discovery_donor_pair_index"]) for r in bundle["donor_map"]["mapping"]}
    rows=[]
    for done,idx in enumerate(range(20,40),1):
        ctx=contexts[idx]; m=material[idx]; hidden=m["hidden_size"]
        qbase,_margin,_=_score_pair(client,ctx.scoring_prompt,ctx.suffixes)
        donor_idx=donor_map[idx]
        donor_direction=selection["discovery_active_directions"][str(donor_idx)]["direction"]
        if len(donor_direction)!=hidden:
            raise RuntimeError(f"DONOR_VECTOR_DIM_MISMATCH pair={idx}")
        controls={
            "active":m["active_direction"],"archived":m["archived_direction"],
            "random":rademacher_direction("confirmation",idx,layer,hidden),"unrelated":donor_direction,
        }
        vals={}
        for name,direction in controls.items():
            cpse,qp,qm=_control_cpse(client,ctx,layer,m["target_patch_index"],direction,m["reset_norm"],alpha)
            vals[name]={"cpse":cpse,"q_plus":qp,"q_minus":qm}
        row={
            "pair_index":idx,"family":ctx.family,"delayed_divergence":ctx.delayed_divergence,
            "option_orientation_bit":ctx.option_orientation_bit,"donor_discovery_pair_index":donor_idx,
            "competent":competence[idx]["competent"],"q_no_patch":qbase,
            "cpse_active":vals["active"]["cpse"],"cpse_archived":vals["archived"]["cpse"],
            "cpse_random":vals["random"]["cpse"],"cpse_unrelated":vals["unrelated"]["cpse"],
            "delta_a":vals["active"]["q_plus"]-qbase,
            "delta_b":qbase-vals["active"]["q_minus"],
            "direction_norms":{"active_source":m["active_source_norm"],"archived_source":m["archived_source_norm"],"target_reset":m["reset_norm"]},
        }
        rows.append(row)
        # Coarse progress only: never emit scientific values before final artifact.
        print(json.dumps({"phase":"confirmation","completed":done,"total":20}),flush=True)
    decision=confirmation_decision(rows,overall,delayed)
    result={
        "kind":"PLANCARRY_LATENT_V2_4_CONFIRMATION","status":decision["status"],
        "scientific_result":decision["status"],"selection_sha256":selection_sha256,
        "selected_layer":layer,"selected_alpha":alpha,"model_info":info,
        "frozen_refs":{"prereg_sha256":PREREG_SHA256,"manifest_sha256":MANIFEST_SHA256,
                       "donor_map_sha256":DONOR_MAP_SHA256,"independent_review_sha256":REVIEW_SHA256,
                        "static_audit_sha256":STATIC_AUDIT_SHA256,"tokenizer_audit_sha256":TOKENIZER_AUDIT_SHA256},
        "cohort_expressivity":{"overall_competent":overall,"delayed_competent":delayed},
        "decision":decision,"rows":rows,
        "claim_scope":"T1 causal active-plan signal only; no checkpoint/compactness/persistence/generality/superiority claim.",
    }
    output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n")
    return sha256_file(output)


def make_client(base_url: str, token_env: str) -> WhiteboxClient:
    token=os.environ.get(token_env,"")
    if not token:
        raise RuntimeError(f"MISSING_BRIDGE_TOKEN_ENV {token_env}")
    return WhiteboxClient(base_url,token,timeout=120.0)


def main() -> int:
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="phase",required=True)
    for name in ["discovery","confirmation"]:
        p=sub.add_parser(name)
        p.add_argument("--base-url",default="http://127.0.0.1:8765")
        p.add_argument("--token-env",default="PLANCARRY_WHITEBOX_TOKEN")
        p.add_argument("--output",required=True)
        if name=="confirmation":
            p.add_argument("--selection",required=True)
            p.add_argument("--selection-sha256",required=True)
    args=ap.parse_args()
    client=make_client(args.base_url,args.token_env)
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    if args.phase=="discovery":
        sha=run_discovery(client,out)
    else:
        sha=run_confirmation(client,Path(args.selection),args.selection_sha256,out)
    print(json.dumps({"phase":args.phase,"output":str(out),"sha256":sha,"completed":True}),flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
