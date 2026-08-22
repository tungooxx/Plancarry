#!/usr/bin/env python3
"""Pure validation/statistics helpers for PlanCarry-Latent v2.6 RTX3050 runtime-only supersession of reviewed v2.5 science.

No model calls. Scientific core is content-addressed by authoritative reviewed
frozen-design SHA. Engineering tests never assess scientific truth.
"""
from __future__ import annotations
import hashlib, json, math, struct
from pathlib import Path
from typing import Any, Iterable

EXPERIMENT_ID = "d347c226-139a-4b14-8f25-4329ee08ea37"
PREDICTION_ID = "d09895b5-8a13-43db-a5a4-6084630242f4"
DESIGN_SHA256 = "a704b9b16d8b7ca458065cf49e3d0abc58d03534f6424391349286582d1040d1"
PREREG_SHA256 = DESIGN_SHA256
MANIFEST_SHA256 = "285d85b10171fcec0a80cc2960a79ae3349472e3b38935b6e97ec10deeaf0feb"
DONOR_MAP_SHA256 = "a2e342e35dd719d14a15a8559b23d545bb51b695405025c3d5964e7290f101f5"
REVIEW_SHA256 = "a24ee1d81fca6296d70b75c66c8c6f5180392008a54a78e19d883f1caf30b874"
REGISTRATION_WRAPPER_SHA256 = "2a8f9a98ebde73d7411fb6dffdf1c537996e135c2b9784deaf6d588f5718156f"
REGISTRATION_WRAPPER_AUDIT_SHA256 = "29cb9c7b3f43a29e94a916e1e218d4c2c3d0051d63b5e264c296ef73f4c85a38"
SUPERSESSION_AUDIT_SHA256 = "aea3334b1499fba60c9c817cdef1b8f757849bc554331bd7e63d44d086804900"
DIRECT_VS_CACHE_SHA256 = "99901c8a0e4869c8e1a0dc4fc288a0c0c5d3eab2ca057b9c0300aded26349dc5"
PREFIX_STABLE_BRIDGE_SHA256 = "77e17e01553b5fb5c3d50ee20b6443b4b26d7da4be78ee3104472d17e16322be"
WHITEBOX_CLIENT_SHA256 = "65e4d52651cd7f1a4fa1f1e9f9ece338228448cb417461ed9316be53bf2396c7"
PREFIX_STABLE_ENGINEERING_RESULT_ID = "cb545b98-119b-49fa-a1eb-5b594ce0addc"
PLUMBING_AUDIT_SHA256 = "55e08892920a6d036e4c4f58b6377e786382f11a75da588d87bcc12474f29c54"
V26_RUNTIME_REBIND_SHA256 = "c6b5bbd8019e52d293aeaa761f628c83876f86769dc8355b1fbb11caa854c2f5"
V26_RUNTIME_REBIND_REVIEW_SHA256 = "2c4f0c1857a4e1ec49952af1d73ae614ccdb6718eab6bf0f8194de9b307c6e4e"
V26_REGISTRATION_WRAPPER_SHA256 = REGISTRATION_WRAPPER_SHA256
V26_REGISTRATION_WRAPPER_AUDIT_SHA256 = REGISTRATION_WRAPPER_AUDIT_SHA256
SOURCE_V25_DESIGN_SHA256 = "9dc788dcb3ec1e8646bff5526020df4913315b4f2a61059f67f332137b577b90"
V26_EXPECTED_DEVICE_NAME = "NVIDIA GeForce RTX 3050 Laptop GPU"
V26_EXPECTED_TORCH = "2.13.0+cu130"
EXPECTED_CONFIRMATION_INDICES=list(range(20,40)); EXPECTED_DISCOVERY_INDICES=list(range(20))
PRIMARY_TEST_NAMES=["active_gt_zero","active_gt_archived","active_gt_random","active_gt_unrelated"]

def stable_json(obj: Any)->str:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
def sha256_bytes(data: bytes)->str: return hashlib.sha256(data).hexdigest()
def sha256_file(path: str|Path)->str: return sha256_bytes(Path(path).read_bytes())
def load_json(path: str|Path)->Any: return json.loads(Path(path).read_text(encoding="utf-8"))
def require_file_hash(path: str|Path, expected: str)->None:
    actual=sha256_file(path)
    if actual!=expected: raise ValueError(f"FROZEN_HASH_MISMATCH {path}: {actual} != {expected}")

def require_frozen_bundle(root: str|Path=".")->dict[str,Any]:
    root=Path(root)
    paths={
      "prereg":root/"results/design/plancarry_latent_v2_6_rtx3050_full_design_candidate_v2_20260820T0904Z.json",
      "manifest":root/"results/design/plancarry_latent_v2_matched_pair_manifest.json",
      "donor_map":root/"results/design/plancarry_latent_v2_2_unrelated_donor_map.json",
      "review":root/"results/design/plancarry_latent_v2_6_full_design_independent_review_20260820T1022Z.json",
      "registration_wrapper":root/"results/design/plancarry_latent_v2_6_corrected_registration_wrapper_20260820T1024Z.json",
      "registration_wrapper_audit":root/"results/design/plancarry_latent_v2_6_corrected_registration_wrapper_audit_20260820T1024Z.json",
      "supersession_audit":root/"results/design/plancarry_latent_v2_6_rtx3050_full_design_candidate_v2_diff_audit_20260820T0904Z.json",
      "direct_vs_cache":root/"results/design/plancarry_prefixstable_direct_equivalence_synthetic.json",
      "bridge":root/"whitebox_bridge_prefixstable_proto.py",
      "client":root/"whitebox_client.py",
      "v26_runtime_rebind":root/"results/design/plancarry_latent_v2_6_rtx3050_runtime_rebind_20260820T085141Z.json",
      "v26_runtime_rebind_review":root/"results/design/plancarry_latent_v2_6_rtx3050_independent_rebind_review_20260820T0855Z.json",
      "v26_registration_wrapper":root/"results/design/plancarry_latent_v2_6_corrected_registration_wrapper_20260820T1024Z.json",
      "v26_registration_wrapper_audit":root/"results/design/plancarry_latent_v2_6_corrected_registration_wrapper_audit_20260820T1024Z.json",
      "source_v25_design":root/"results/design/plancarry_latent_v2_5_frozen_design_20260820T0244Z.json",
    }
    expected={"prereg":DESIGN_SHA256,"manifest":MANIFEST_SHA256,"donor_map":DONOR_MAP_SHA256,"review":REVIEW_SHA256,
              "registration_wrapper":REGISTRATION_WRAPPER_SHA256,"registration_wrapper_audit":REGISTRATION_WRAPPER_AUDIT_SHA256,
              "supersession_audit":SUPERSESSION_AUDIT_SHA256,"direct_vs_cache":DIRECT_VS_CACHE_SHA256,
              "bridge":PREFIX_STABLE_BRIDGE_SHA256,"client":WHITEBOX_CLIENT_SHA256,
              "v26_runtime_rebind":V26_RUNTIME_REBIND_SHA256,"v26_runtime_rebind_review":V26_RUNTIME_REBIND_REVIEW_SHA256,
              "v26_registration_wrapper":V26_REGISTRATION_WRAPPER_SHA256,"v26_registration_wrapper_audit":V26_REGISTRATION_WRAPPER_AUDIT_SHA256,
              "source_v25_design":SOURCE_V25_DESIGN_SHA256}
    for k,p in paths.items(): require_file_hash(p,expected[k])
    bundle={k:load_json(p) for k,p in paths.items() if k not in {"bridge","client"}}
    validate_donor_map(bundle["manifest"],bundle["donor_map"])
    prereg=bundle["prereg"]; validate_prereg_template_contract(prereg)
    integ=prereg.get("artifact_integrity",{})
    if prereg.get("scientific_result")!="NOT_ASSESSED" or integ.get("scientific_outcomes_seen") is not False or integ.get("confirmation_accessed") is not False:
        raise ValueError("V26_DESIGN_NOT_PROSPECTIVE_UNASSESSED")
    if integ.get("source_v2_5_design_sha256")!=SOURCE_V25_DESIGN_SHA256 or integ.get("scientific_variables_changed_from_v2_5")!=[]:
        raise ValueError("V26_SCIENTIFIC_INHERITANCE_INVALID")
    if prereg.get("model",{}).get("prefix_stable_bridge_sha256")!=PREFIX_STABLE_BRIDGE_SHA256 or prereg.get("model",{}).get("whitebox_client_sha256")!=WHITEBOX_CLIENT_SHA256:
        raise ValueError("V26_SCORER_PROVENANCE_MISMATCH")
    review=bundle["review"]
    if review.get("verdict")!="PASS_FOR_V26_REGISTRATION" or review.get("scientific_result")!="NOT_ASSESSED" or review.get("candidate_sha256")!=DESIGN_SHA256 or review.get("scientific_variables_changed")!=[] or review.get("unexpected_changed_paths")!=[]:
        raise ValueError("V26_FULL_DESIGN_REVIEW_NOT_PASS")
    sup=bundle["supersession_audit"]
    if sup.get("scientific_variables_changed")!=[] or sup.get("unexpected_changed_paths")!=[]:
        raise ValueError("V26_FULL_DESIGN_DIFF_AUDIT_INVALID")
    diag=bundle["direct_vs_cache"]
    if diag.get("scientific_result")!="NOT_ASSESSED" or diag.get("alfworld_science") is not False:
        raise ValueError("V26_DIRECT_CACHE_DIAGNOSTIC_SCOPE_INVALID")
    if abs(float(diag.get("max_abs_meanlp_delta"))-0.0016210079193115234)>1e-15:
        raise ValueError("V26_DIRECT_CACHE_DIAGNOSTIC_VALUE_MISMATCH")
    wrapper=bundle["registration_wrapper"]
    if wrapper.get("canonical_experiment_id")!=EXPERIMENT_ID or wrapper.get("canonical_prediction_id")!=PREDICTION_ID or wrapper.get("full_design_sha256")!=DESIGN_SHA256 or wrapper.get("full_design_independent_review_sha256")!=REVIEW_SHA256 or wrapper.get("scientific_override_paths")!=[]:
        raise ValueError("V26_CORRECTED_REGISTRATION_WRAPPER_INVALID")
    if "PLANCARRY_LATENT_V2_6_DISCOVERY_SELECTION" not in wrapper.get("confirmation_requires",""):
        raise ValueError("V26_CONFIRMATION_SELECTION_BARRIER_MISSING")
    if wrapper.get("phase_seal",{}).get("confirmation_accessed") is not False or wrapper.get("phase_seal",{}).get("valid_seen_consumed") is not False or wrapper.get("phase_seal",{}).get("valid_unseen_consumed") is not False:
        raise ValueError("V26_CORRECTED_REGISTRATION_NOT_PROSPECTIVE")
    wrapper_audit=bundle["registration_wrapper_audit"]
    if wrapper_audit.get("pass") is not True or wrapper_audit.get("wrapper_sha256")!=REGISTRATION_WRAPPER_SHA256 or wrapper_audit.get("canonical_experiment_id")!=EXPERIMENT_ID or wrapper_audit.get("canonical_prediction_id")!=PREDICTION_ID or wrapper_audit.get("scientific_override_count")!=0 or wrapper_audit.get("v26_discovery_selection_barrier_present") is not True:
        raise ValueError("V26_CORRECTED_REGISTRATION_WRAPPER_AUDIT_INVALID")
    rb=bundle["v26_runtime_rebind"]
    if rb.get("scientific_result")!="NOT_ASSESSED" or rb.get("scientific_inheritance",{}).get("source_design_full_sha256")!=SOURCE_V25_DESIGN_SHA256 or rb.get("scientific_inheritance",{}).get("scientific_override_count")!=0:
        raise ValueError("V26_RUNTIME_REBIND_INVALID")
    if rb.get("runtime_override",{}).get("scientific_override_paths")!=[] or rb.get("runtime_override",{}).get("device_name_exact")!=V26_EXPECTED_DEVICE_NAME:
        raise ValueError("V26_RUNTIME_OVERRIDE_SCOPE_INVALID")
    rev=bundle["v26_runtime_rebind_review"]
    if rev.get("verdict")!="PASS_FOR_V26_RTX3050_ENGINEERING" or rev.get("scientific_result")!="NOT_ASSESSED" or rev.get("failed_count")!=0 or rev.get("scientific_override_count")!=0 or rev.get("source_rebind_sha256")!=V26_RUNTIME_REBIND_SHA256:
        raise ValueError("V26_INDEPENDENT_REBIND_REVIEW_INVALID")
    source=bundle["source_v25_design"]
    if source.get("research_question")!=prereg.get("research_question") or source.get("prediction")!=prereg.get("prediction") or source.get("confirmation_primary")!=prereg.get("confirmation_primary") or source.get("development_selection")!=prereg.get("development_selection") or source.get("intervention_math")!=prereg.get("intervention_math"):
        raise ValueError("V26_SCIENTIFIC_CORE_DRIFT_VS_V25")
    return bundle

def validate_prereg_template_contract(prereg: dict[str, Any]) -> None:
    """Fail closed on the exact executable v2.5 newline/scoring contract."""
    try:
        pair = prereg["pair_variable"]
        scoring = prereg["action_scoring"]
        fields = {
            "reset_template": pair["reset_template"],
            "source_active_template": pair["source_active_template"],
            "source_archived_template": pair["source_archived_template"],
            "reset_block": scoring["reset_block"],
        }
    except Exception as exc:
        raise ValueError("V25_TEMPLATE_FIELDS_MISSING") from exc
    for name, text in fields.items():
        if not isinstance(text, str):
            raise ValueError(f"V25_TEMPLATE_NOT_STRING {name}")
        if "\\n" in text:
            raise ValueError(f"V25_LITERAL_BACKSLASH_N_FORBIDDEN {name}")
        if not text.endswith("<STATE_END>\n") or text.endswith("<STATE_END>\n\n"):
            raise ValueError(f"V25_TERMINAL_NEWLINE_CONTRACT_FAILED {name}")
    if pair["reset_template"] != scoring["reset_block"]:
        raise ValueError("V25_RESET_TEMPLATE_DIVERGENCE")
    if scoring.get("scoring_prompt") != "{RESET_BLOCK}ACTION:":
        raise ValueError("V25_SCORING_PROMPT_CONTRACT_FAILED")
    if scoring.get("candidate_suffix_serialization") != " {EXACT_ADMISSIBLE_COMMAND}":
        raise ValueError("V25_CANDIDATE_SUFFIX_CONTRACT_FAILED")


def _pair_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("selected_pairs")
    if not isinstance(rows, list) or len(rows) != 40:
        raise ValueError("MANIFEST_PAIR_COUNT_MISMATCH")
    return rows


def validate_donor_map(manifest: dict[str, Any], donor_map: dict[str, Any]) -> None:
    if donor_map.get("model_outcomes_seen") is not False:
        raise ValueError("DONOR_MAP_NOT_PROSPECTIVE")
    rows = donor_map.get("mapping")
    if not isinstance(rows, list) or len(rows) != 20:
        raise ValueError("DONOR_MAP_COUNT_MISMATCH")
    recipients = [int(r["confirmation_pair_index"]) for r in rows]
    donors = [int(r["discovery_donor_pair_index"]) for r in rows]
    if recipients != EXPECTED_CONFIRMATION_INDICES:
        raise ValueError("DONOR_RECIPIENT_INDICES_MISMATCH")
    if sorted(donors) != EXPECTED_DISCOVERY_INDICES or len(set(donors)) != 20:
        raise ValueError("DONOR_DISCOVERY_BIJECTION_MISMATCH")
    pairs = {int(r["frozen_pair_index"]): r for r in _pair_rows(manifest)}
    base = donor_map.get("base_string")
    if not isinstance(base, str) or not base:
        raise ValueError("DONOR_BASE_STRING_MISSING")
    expected_discovery = sorted(
        [(i, pairs[i]["family"]) for i in EXPECTED_DISCOVERY_INDICES],
        key=lambda x: (
            hashlib.sha256((base + "|donor|" + str(x[0]) + "|" + x[1]).encode("utf-8")).hexdigest(),
            x[0],
        ),
    )
    expected_confirmation = [(i, pairs[i]["family"]) for i in EXPECTED_CONFIRMATION_INDICES]
    for row, (ci, cf), (di, df) in zip(rows, expected_confirmation, expected_discovery):
        digest = hashlib.sha256((base + "|donor|" + str(di) + "|" + df).encode("utf-8")).hexdigest()
        expected = (ci, cf, di, df, digest)
        actual = (
            int(row["confirmation_pair_index"]), row["confirmation_family"],
            int(row["discovery_donor_pair_index"]), row["discovery_donor_family"],
            row["donor_sort_sha256"],
        )
        if actual != expected:
            raise ValueError(f"DONOR_MAP_ALGORITHM_MISMATCH expected={expected!r} actual={actual!r}")


def option_orientation_bit(pair_index: int) -> int:
    s = f"{MANIFEST_SHA256}|{pair_index}|option_orientation_v1"
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[0:2], 16) % 2


def rademacher_direction(split: str, pair_index: int, layer_0based: int, dimension: int) -> list[float]:
    if dimension <= 0:
        raise ValueError("dimension must be positive")
    base = f"{MANIFEST_SHA256}|{split}|{pair_index}|{layer_0based}|random_control_v2_1"
    inv = 1.0 / math.sqrt(dimension)
    out: list[float] = []
    for j in range(dimension):
        digest = hashlib.sha256((base + "|" + str(j)).encode("utf-8")).digest()
        out.append(inv if digest[0] % 2 == 0 else -inv)
    return out


def l2(xs: Iterable[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in xs))


def f32(x: float) -> float:
    """Round a scalar to IEEE-754 binary32 for preregistered FP32 contrast math."""
    return struct.unpack("!f", struct.pack("!f", float(x)))[0]

def l2_f32(xs: Iterable[float]) -> float:
    acc = f32(0.0)
    for x in xs:
        xx = f32(x)
        acc = f32(acc + f32(xx * xx))
    return f32(math.sqrt(acc))

def normalized_contrast(a: list[float], b: list[float], epsilon: float = 1e-8) -> tuple[list[float], float]:
    if len(a) != len(b) or not a:
        raise ValueError("VECTOR_DIM_MISMATCH")
    delta = [f32(f32(x) - f32(y)) for x, y in zip(a, b)]
    norm = l2_f32(delta)
    if norm <= epsilon:
        return [0.0] * len(delta), norm
    return [f32(x / norm) for x in delta], norm


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def mean_lp(score_row: dict[str, Any]) -> float:
    n = int(score_row["token_count"])
    if n <= 0:
        raise ValueError("EMPTY_COMMAND_SUFFIX")
    return float(score_row["logprob_sum"]) / n


def q_a(score_response: dict[str, Any]) -> tuple[float, float, float]:
    rows = score_response.get("scores")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("EXPECTED_TWO_COMMAND_SCORES")
    a, b = mean_lp(rows[0]), mean_lp(rows[1])
    margin = a - b
    return sigmoid(margin), margin, a - b


def exact_sign_tail(k: int, n: int = 20) -> float:
    if n != 20:
        raise ValueError("V2_5_PRIMARY_N_MUST_BE_20")
    if k < 0 or k > n:
        raise ValueError("INVALID_SUCCESS_COUNT")
    return sum(math.comb(n, j) for j in range(k, n + 1)) * (0.5 ** n)


def holm_adjust(raw_p: dict[str, float]) -> dict[str, float]:
    if set(raw_p) != set(PRIMARY_TEST_NAMES):
        raise ValueError("PRIMARY_TEST_SET_MISMATCH")
    ordered = sorted(raw_p.items(), key=lambda kv: (kv[1], kv[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    m = len(ordered)
    for rank, (name, p) in enumerate(ordered):
        candidate = min(1.0, (m - rank) * float(p))
        running = max(running, candidate)
        adjusted[name] = running
    return adjusted


def primary_test_statistics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if len(rows) != 20:
        raise ValueError("CONFIRMATION_PRIMARY_REQUIRES_EXACTLY_20_ROWS")
    indices = [int(r["pair_index"]) for r in rows]
    if sorted(indices) != EXPECTED_CONFIRMATION_INDICES or len(set(indices)) != 20:
        raise ValueError("CONFIRMATION_POPULATION_MISMATCH")
    xs = {
        "active_gt_zero": [float(r["cpse_active"]) for r in rows],
        "active_gt_archived": [float(r["cpse_active"]) - float(r["cpse_archived"]) for r in rows],
        "active_gt_random": [float(r["cpse_active"]) - float(r["cpse_random"]) for r in rows],
        "active_gt_unrelated": [float(r["cpse_active"]) - float(r["cpse_unrelated"]) for r in rows],
    }
    raw: dict[str, float] = {}
    out: dict[str, dict[str, Any]] = {}
    for name in PRIMARY_TEST_NAMES:
        k = sum(1 for x in xs[name] if x > 0.0)  # exact zero is frozen failure
        p = exact_sign_tail(k)
        raw[name] = p
        out[name] = {"k_positive": k, "n": 20, "raw_p": p}
    adj = holm_adjust(raw)
    for name in PRIMARY_TEST_NAMES:
        out[name]["holm_adjusted_p"] = adj[name]
    return out


def confirmation_decision(rows: list[dict[str, Any]], overall_competent: int, delayed_competent: int) -> dict[str, Any]:
    if overall_competent < 16 or delayed_competent < 8:
        return {
            "status": "INCONCLUSIVE_MODEL_EXPRESSIVITY",
            "overall_competent": overall_competent,
            "delayed_competent": delayed_competent,
            "primary_inference": None,
        }
    tests = primary_test_statistics(rows)
    mean_active = sum(float(r["cpse_active"]) for r in rows) / 20.0
    positive_fraction = sum(1 for r in rows if float(r["cpse_active"]) > 0.0) / 20.0
    bidirectional_fraction = sum(
        1 for r in rows if float(r["delta_a"]) > 0.0 and float(r["delta_b"]) > 0.0
    ) / 20.0
    control_means = {
        c: sum(float(r["cpse_active"]) - float(r[c]) for r in rows) / 20.0
        for c in ["cpse_archived", "cpse_random", "cpse_unrelated"]
    }
    all_p = all(tests[name]["holm_adjusted_p"] <= 0.05 for name in PRIMARY_TEST_NAMES)
    active_guards = mean_active >= 0.10 and positive_fraction >= 0.70 and bidirectional_fraction >= 0.60
    specificity_p = all(tests[name]["holm_adjusted_p"] <= 0.05 for name in ["active_gt_archived", "active_gt_random", "active_gt_unrelated"])
    specificity_guards = all(v >= 0.05 for v in control_means.values())
    active_core = tests["active_gt_zero"]["holm_adjusted_p"] <= 0.05 and active_guards
    if active_core and specificity_p and specificity_guards:
        status = "SUPPORTED_T1"
    elif active_core and not (specificity_p and specificity_guards):
        status = "INCONCLUSIVE_NONSPECIFIC_ACTIVATION_EFFECT"
    else:
        status = "NOT_SUPPORTED_WEAKENED_SINGLE_SITE_CONTRAST"
    return {
        "status": status,
        "overall_competent": overall_competent,
        "delayed_competent": delayed_competent,
        "primary_inference": tests,
        "effect_guards": {
            "mean_cpse_active": mean_active,
            "positive_pair_fraction": positive_fraction,
            "bidirectional_pair_fraction": bidirectional_fraction,
            "mean_active_minus_controls": control_means,
            "all_holm_p_le_0_05": all_p,
            "active_guards_pass": active_guards,
            "specificity_p_pass": specificity_p,
            "specificity_guards_pass": specificity_guards,
        },
        "claim_scope": "T1 causal active-plan signal only",
    }


def verify_selection_artifact(path: str|Path, expected_sha256: str)->dict[str,Any]:
    require_file_hash(path,expected_sha256); obj=load_json(path)
    if obj.get("kind")!="PLANCARRY_LATENT_V2_6_DISCOVERY_SELECTION": raise ValueError("SELECTION_KIND_MISMATCH")
    if obj.get("scientific_result")!="NOT_ASSESSED_DISCOVERY_SELECTION_ONLY": raise ValueError("SELECTION_SCIENTIFIC_SCOPE_MISMATCH")
    refs=obj.get("frozen_refs",{})
    required={"experiment_id":EXPERIMENT_ID,"prediction_id":PREDICTION_ID,"frozen_design_sha256":DESIGN_SHA256,
              "manifest_sha256":MANIFEST_SHA256,"donor_map_sha256":DONOR_MAP_SHA256,"independent_review_sha256":REVIEW_SHA256,
              "registration_wrapper_sha256":REGISTRATION_WRAPPER_SHA256,"registration_wrapper_audit_sha256":REGISTRATION_WRAPPER_AUDIT_SHA256,
              "supersession_audit_sha256":SUPERSESSION_AUDIT_SHA256,"direct_vs_cache_diagnostic_sha256":DIRECT_VS_CACHE_SHA256,
              "prefix_stable_bridge_sha256":PREFIX_STABLE_BRIDGE_SHA256,"whitebox_client_sha256":WHITEBOX_CLIENT_SHA256,
              "prefix_stable_engineering_result_id":PREFIX_STABLE_ENGINEERING_RESULT_ID,
              "v26_runtime_rebind_sha256":V26_RUNTIME_REBIND_SHA256,"v26_runtime_rebind_review_sha256":V26_RUNTIME_REBIND_REVIEW_SHA256,
              "v26_registration_wrapper_sha256":V26_REGISTRATION_WRAPPER_SHA256,"v26_registration_wrapper_audit_sha256":V26_REGISTRATION_WRAPPER_AUDIT_SHA256}
    bad={k:(refs.get(k),v) for k,v in required.items() if refs.get(k)!=v}
    if bad: raise ValueError(f"SELECTION_FROZEN_REFS_MISMATCH {bad}")
    if int(obj.get("selected_layer")) not in [6,13,20,27]: raise ValueError("SELECTION_LAYER_OUTSIDE_FROZEN_GRID")
    if float(obj.get("selected_alpha")) not in [0.05,0.1,0.2]: raise ValueError("SELECTION_ALPHA_OUTSIDE_FROZEN_GRID")
    dirs=obj.get("discovery_active_directions")
    if not isinstance(dirs,dict) or sorted(map(int,dirs.keys()))!=EXPECTED_DISCOVERY_INDICES: raise ValueError("SELECTION_DONOR_DIRECTIONS_INCOMPLETE")
    if obj.get("confirmation_requests_made") not in (False,0): raise ValueError("SELECTION_CREATED_AFTER_CONFIRMATION_ACCESS")
    return obj
