#!/usr/bin/env python3
"""PlanCarry-Latent v2.7 source-competence-only runner.

This executable is intentionally incapable of causal intervention or confirmation.
It evaluates only frozen development indices 0..19 under the prospectively frozen
v2.7 slot-bound source representation and unchanged v2.6 action-scoring semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from alfworld_runtime import ACTIVE_DATA_ROOT, AlfRuntime, stable_json as alf_stable_json
from whitebox_client import WhiteboxClient

ROOT = Path(__file__).resolve().parent
DESIGN_PATH = ROOT / "results/design/plancarry_latent_v2_7_slot_bound_source_lineage_repaired_20260820T1401Z.json"
DESIGN_SHA256 = "0b25f09d2010358c23838f0e999ce7c7bd41b1e68ce84f4f14aecafafd5bdc51"
REVIEW_SHA256 = "b3e4fb7f110b22fa1b9eaed10f355af5094f42c92513f404a84da73be4beab2d"
CONTRACT_PATH = ROOT / "results/design/plancarry_latent_v2_7_competence_only_runner_contract.json"
CONTRACT_SHA256 = "b5fb54cac2548508703c54ed5b90f7562fb9952dac13685a00e59a93734999e0"
MANIFEST_PATH = ROOT / "results/design/plancarry_latent_v2_matched_pair_manifest.json"
MANIFEST_SHA256 = "285d85b10171fcec0a80cc2960a79ae3349472e3b38935b6e97ec10deeaf0feb"
EXPECTED_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
EXPECTED_MODEL_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
EXPECTED_DEVICE_NAME = "NVIDIA GeForce RTX 3050 Laptop GPU"
EXPECTED_TRANSFORMERS = "4.46.3"
EXPECTED_TOKENIZERS = "0.20.3"
EXPECTED_TORCH = "2.13.0+cu130"
N = 20
PASS_MIN = 12
SOURCE_A_MIN = 0.10
SOURCE_B_MAX = -0.10


class ClientProtocol(Protocol):
    def model_info(self) -> dict[str, Any]: ...
    def score_sequences(self, prompt: str, suffixes: list[str]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PairContext:
    pair_index: int
    family: str
    delayed_divergence: bool
    reset_block: str
    active_a: str
    active_b: str
    reference_a: str
    reference_b: str
    command_a: str
    command_b: str
    option_orientation_bit: int

    def __post_init__(self) -> None:
        for name, text in [
            ("reset_block", self.reset_block), ("active_a", self.active_a),
            ("active_b", self.active_b), ("reference_a", self.reference_a),
            ("reference_b", self.reference_b),
        ]:
            if "\\n" in text:
                raise RuntimeError(f"V27_LITERAL_BACKSLASH_N_FORBIDDEN {name}")
            if not text.endswith("<STATE_END>\n") or text.endswith("<STATE_END>\n\n"):
                raise RuntimeError(f"V27_TERMINAL_NEWLINE_CONTRACT_FAILED {name}")

    @property
    def suffixes(self) -> list[str]:
        # Frozen corrected-v2.6 token boundary: exactly one leading ASCII space.
        return [" " + self.command_a, " " + self.command_b]

    def source_scoring_prompt(self, which: str) -> str:
        text = {
            "active_a": self.active_a,
            "active_b": self.active_b,
            "reference_a": self.reference_a,
            "reference_b": self.reference_b,
        }[which]
        return text + "ACTION:"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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


def option_orientation_bit(pair_index: int) -> int:
    s = f"{MANIFEST_SHA256}|{pair_index}|option_orientation_v1"
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[0:2], 16) % 2


def load_frozen_bundle() -> tuple[dict[str, Any], dict[str, Any]]:
    expected = [
        (DESIGN_PATH, DESIGN_SHA256, "DESIGN"),
        (CONTRACT_PATH, CONTRACT_SHA256, "CONTRACT"),
        (MANIFEST_PATH, MANIFEST_SHA256, "MANIFEST"),
    ]
    for path, digest, name in expected:
        if not path.exists() or sha256_file(path) != digest:
            raise RuntimeError(f"{name}_HASH_MISMATCH")
    design = json.loads(DESIGN_PATH.read_text())
    manifest = json.loads(MANIFEST_PATH.read_text())
    if design["data"]["manifest_sha256"] != MANIFEST_SHA256:
        raise RuntimeError("DESIGN_MANIFEST_BINDING_MISMATCH")
    if int(design["model_expressivity_gate"]["discovery_min_competent"]) != PASS_MIN:
        raise RuntimeError("PASS_MIN_MISMATCH")
    if design["pair_variable"]["source_active_template"].find("USE THIS PLAN NOW: YES") < 0:
        raise RuntimeError("V27_ACTIVE_TEMPLATE_MISMATCH")
    if design["pair_variable"]["source_archived_template"].find("USE THIS PLAN NOW: NO") < 0:
        raise RuntimeError("V27_REFERENCE_TEMPLATE_MISMATCH")
    return design, manifest


def build_pair_context(pair: dict[str, Any], design: dict[str, Any]) -> PairContext:
    idx = int(pair["frozen_pair_index"])
    if idx < 0 or idx >= N:
        raise RuntimeError("V27_COMPETENCE_ONLY_INDEX_OUT_OF_RANGE")
    if pair.get("split") != "discovery":
        raise RuntimeError(f"V27_DEVELOPMENT_SPLIT_MISMATCH pair={idx}")
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
    pair_cfg = design["pair_variable"]
    reset_block = design["action_scoring"]["reset_block"].format(
        TASK_TEXT=task,
        RESET_OBSERVATION=reset_obs,
        ONE_COMMAND_PER_LINE_LEXICOGRAPHIC="\n".join(sorted_commands),
    )
    pair_reset = pair_cfg["reset_template"].format(
        TASK_TEXT=task,
        RESET_OBSERVATION=reset_obs,
        ONE_COMMAND_PER_LINE_LEXICOGRAPHIC="\n".join(sorted_commands),
    )
    if reset_block != pair_reset:
        raise RuntimeError(f"V27_RESET_TEMPLATE_DIVERGENCE pair={idx}")

    bit = option_orientation_bit(idx)
    if bit == 0:
        oa, ob = pair["object_a"], pair["object_b"]
        command_a, command_b = pair["a_first_divergent_action"], pair["b_first_divergent_action"]
    else:
        oa, ob = pair["object_b"], pair["object_a"]
        command_a, command_b = pair["b_first_divergent_action"], pair["a_first_divergent_action"]
    if command_a not in commands or command_b not in commands or command_a == command_b:
        raise RuntimeError(f"DIVERGENT_COMMAND_GUARD_FAILED pair={idx}")

    ca = _clause(oa, pair["target_receptacle"])
    cb = _clause(ob, pair["target_receptacle"])
    active_tpl = pair_cfg["source_active_template"]
    reference_tpl = pair_cfg["source_archived_template"]
    active_a = active_tpl.format(RESET_BLOCK=reset_block, CLAUSE_A=ca, CLAUSE_B=cb)
    active_b = active_tpl.format(RESET_BLOCK=reset_block, CLAUSE_A=cb, CLAUSE_B=ca)
    reference_a = reference_tpl.format(RESET_BLOCK=reset_block, CLAUSE_A=ca, CLAUSE_B=cb)
    reference_b = reference_tpl.format(RESET_BLOCK=reset_block, CLAUSE_A=cb, CLAUSE_B=ca)
    if _lex_bag(active_a) != _lex_bag(active_b) or _lex_bag(reference_a) != _lex_bag(reference_b):
        raise RuntimeError(f"V27_LEXICAL_MULTISET_GUARD_FAILED pair={idx}")
    return PairContext(idx, pair["family"], bool(pair["delayed_divergence"]), reset_block,
                       active_a, active_b, reference_a, reference_b,
                       command_a, command_b, bit)


def validate_bridge_info(info: dict[str, Any]) -> None:
    checks = {
        "mode": info.get("mode") == "real",
        "model_id": info.get("model_id") == EXPECTED_MODEL_ID,
        "revision_requested": info.get("model_revision_requested") == EXPECTED_MODEL_REVISION,
        "revision_resolved": info.get("model_commit_resolved") == EXPECTED_MODEL_REVISION,
        "device": "cuda" in str(info.get("device", "")).lower(),
        "device_name": str(info.get("device_name", "")) == EXPECTED_DEVICE_NAME,
        "dtype": str(info.get("dtype", "")).lower() in {"torch.float16", "float16", "fp16"},
        "transformers": info.get("transformers_version") == EXPECTED_TRANSFORMERS,
        "tokenizers": info.get("tokenizers_version") == EXPECTED_TOKENIZERS,
        "torch": info.get("torch_version") == EXPECTED_TORCH,
        "quantization": str(info.get("quantization", "")).upper() == "NONE",
        "layers": int(info.get("num_layers", -1)) == 28,
        "hidden_size": int(info.get("hidden_size", -1)) == 1536,
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise RuntimeError(f"V27_BRIDGE_PROVENANCE_GATE_FAILED fields={bad}")


def _mean_lp(row: dict[str, Any]) -> float:
    n = int(row["token_count"])
    if n <= 0:
        raise RuntimeError("EMPTY_SUFFIX_SCORE")
    return float(row["logprob_sum"]) / n


def _score_pair(client: ClientProtocol, prompt: str, suffixes: list[str]) -> tuple[float, float, list[float]]:
    if len(suffixes) != 2 or any(not s.startswith(" ") or s.startswith("  ") for s in suffixes):
        raise RuntimeError("V27_SUFFIX_LEADING_SPACE_CONTRACT_FAILED")
    response = client.score_sequences(prompt, suffixes)
    rows = response.get("scores")
    if not isinstance(rows, list) or len(rows) != 2:
        raise RuntimeError("EXPECTED_TWO_COMMAND_SCORES")
    means = [_mean_lp(rows[0]), _mean_lp(rows[1])]
    margin = means[0] - means[1]
    q = 1.0 / (1.0 + math.exp(-margin))
    return q, margin, means


def source_competence(client: ClientProtocol, ctx: PairContext) -> dict[str, Any]:
    qa, ma, _ = _score_pair(client, ctx.source_scoring_prompt("active_a"), ctx.suffixes)
    qb, mb, _ = _score_pair(client, ctx.source_scoring_prompt("active_b"), ctx.suffixes)
    competent = ma >= SOURCE_A_MIN and mb <= SOURCE_B_MAX
    return {
        "margin_source_a": ma,
        "margin_source_b": mb,
        "q_source_a": qa,
        "q_source_b": qb,
        "competent": competent,
    }


def make_client(base_url: str, token_env: str) -> WhiteboxClient:
    token = os.environ.get(token_env, "")
    if not token:
        raise RuntimeError(f"MISSING_BRIDGE_TOKEN_ENV {token_env}")
    return WhiteboxClient(base_url, token, timeout=None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--token-env", default="PLANCARRY_WHITEBOX_TOKEN")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"REFUSE_EXISTING_OUTPUT {output}")

    design, manifest = load_frozen_bundle()
    rows = {int(r["frozen_pair_index"]): r for r in manifest["selected_pairs"]}
    if set(range(N)) - set(rows):
        raise RuntimeError("V27_DEVELOPMENT_MANIFEST_INCOMPLETE")
    contexts = {idx: build_pair_context(rows[idx], design) for idx in range(N)}
    client = make_client(args.base_url, args.token_env)
    info = client.model_info()
    validate_bridge_info(info)

    competence: dict[str, dict[str, Any]] = {}
    for idx in range(N):
        competence[str(idx)] = source_competence(client, contexts[idx])
        # Deliberately coarse: do not expose partial scientific values.
        print(json.dumps({"phase": "v2.7_source_competence", "completed": idx + 1, "total": N}), flush=True)
    count = sum(1 for x in competence.values() if x["competent"])
    status = "PASS_V27_SOURCE_COMPETENCE" if count >= PASS_MIN else "INCONCLUSIVE_MODEL_EXPRESSIVITY_SOURCE_BINDING"
    result = {
        "kind": "PLANCARRY_LATENT_V2_7_SOURCE_COMPETENCE_RESULT",
        "status": status,
        "scientific_result": "NOT_ASSESSED_T1_COMPETENCE_ONLY",
        "competent_count": count,
        "n": N,
        "required_min": PASS_MIN,
        "competence": competence,
        "model_info": info,
        "frozen_refs": {
            "design_sha256": DESIGN_SHA256,
            "independent_review_sha256": REVIEW_SHA256,
            "competence_contract_sha256": CONTRACT_SHA256,
            "manifest_sha256": MANIFEST_SHA256,
        },
        "causal_interventions_computed": False,
        "layer_alpha_search_computed": False,
        "confirmation_requests_made": False,
        "valid_seen_consumed": False,
        "valid_unseen_consumed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    output.write_bytes(raw)
    print(json.dumps({"output": str(output), "sha256": hashlib.sha256(raw).hexdigest(), "status": status,
                      "competent_count": count, "n": N}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
