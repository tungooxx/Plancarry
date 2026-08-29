"""Pure pre-science orchestration for SuccessorFeature-v2 constructibility.

This module performs no model, tokenizer, environment, accelerator, provider, or
Research OS I/O.  A separately reviewed runtime adapter may later materialize
observable two-action cut records and frozen phase-score vectors.  This driver
validates those records, applies only the already-frozen SuccessorFeature-v2
math, and emits deterministic constructibility packets for fixed indices 0..15.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import successor_feature_constructibility_v2 as sf
import successor_feature_label_binding_v2 as lb

SCHEMA = "SUCCESSOR_FEATURE_CONSTRUCTIBILITY_PACKET_V1"
MANIFEST_SCHEMA = "SUCCESSOR_FEATURE_CONSTRUCTIBILITY_MANIFEST_V1"
SUMMARY_SCHEMA = "SUCCESSOR_FEATURE_CONSTRUCTIBILITY_SUMMARY_V1"
MATERIAL_MANIFEST_SCHEMA = "SUCCESSOR_FEATURE_ATTEMPT_MATERIAL_MANIFEST_V1"
PREREG_REL = Path("results/design/plancarry_successor_feature_constructibility_prereg_v2_20260827.json")
POPULATION_REL = Path("results/design/plancarry_successor_feature_fresh_population_v1_20260827.json")
LABEL_BINDING_REL = Path("results/design/plancarry_successor_feature_label_binding_v2_20260828.json")
ACTION_PRIMITIVE_REL = Path("replay_residual_natural_packet_producer_v2_1.py")
RUNTIME_PRIMITIVE_REL = Path("alfworld_runtime.py")
SF_HELPER_REL = Path("successor_feature_constructibility_v2.py")
LABEL_HELPER_REL = Path("successor_feature_label_binding_v2.py")

PREREG_SHA256 = "e6ef3044d6636e03b4b6a5b7a68b1bda89bc92ba2b2da3c936e9e2a8a07e276f"
POPULATION_SHA256 = "d35271102561040901ead7a663e080242b577c9afd75743f94ad3cce014d24d2"
LABEL_BINDING_FILE_SHA256 = "6a31e850b32486f250f58007a02f86044d4f6d1362a48594c094a50811bb686f"
SUFFIX_TABLE_SHA256 = "84dd917857b955a32accc394d5a090108419741d1481ad49607329acfc6d46c7"
ACTION_PRIMITIVE_SHA256 = "bb05eb8b3b02f15d32f768212730712f2f0a04062729a57ca4993be2031dec55"
RUNTIME_PRIMITIVE_SHA256 = "53e550f70711a3779409c565ecbd3e2fd971751a03633dad3566d5569a6fb3c6"
SF_HELPER_SHA256 = "94fb69bf8b11e2a3812573b07360a3c07a37efc8b607773256856bd72e302401"
LABEL_HELPER_SHA256 = "9f269f3fab4b76600d1148043da1a5f47fc2808d01082765cd1a2581ebd812b0"

MODEL_BINDING = {
    "model_id": lb.MODEL_ID,
    "revision": lb.MODEL_REVISION,
    "dtype": "bfloat16",
    "quantization": False,
    "offload": False,
    "thinking": False,
    "transformers": lb.TRANSFORMERS_VERSION,
    "tokenizers": lb.TOKENIZERS_VERSION,
}
PASS_LABEL = "PASS_SUCCESSOR_FEATURE_CONSTRUCTIBILITY_ONLY"
FAIL_LABEL = "INCONCLUSIVE_SUCCESSOR_FEATURE_CONSTRUCTIBILITY"
PASS_COUNT = 12
FIXED_INDICES = tuple(range(16))
SOURCE_BASE_COMMIT = "7649007ae0779d1583a42c86f1d5dc7f235b52c3"
SUFFIX_PROVENANCE_REVIEW_COMMIT = "3b555fd"

_TOP_KEYS = ("index", "game_path", "rank_sha256", "prefix", "score_bundle")
_PREFIX_KEYS = ("eligible", "reasons", "primitive_bindings", "observable", "shared_action_a3", "shared_action_phase")
_OBSERVABLE_KEYS = ("task_instruction", "history", "current_observation", "admissible_commands")
_PRIMITIVE_KEYS = ("action_primitive_sha256", "runtime_primitive_sha256")
_SCORE_KEYS = ("step2", "branches")
_STEP_KEYS = ("prompt_sha256", "scores")
_BRANCH_KEYS = ("row3_prompt_sha256", "row3_scores", "row4_prompt_sha256", "row4_scores")


class DriverContractError(sf.ContractError):
    """Fail-closed orchestration/provenance violation."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DriverContractError("CANONICAL_JSON_SERIALIZATION_FAILED") from exc


def canonical_sha256(value: object) -> str:
    return _sha256_bytes(canonical_json_bytes(value))


def _exact_keys(value: Mapping[str, object], keys: Sequence[str], error: str) -> None:
    # JSON object member order is not semantic.  Require the exact key set and
    # cardinality, while accepting canonical-sorted or insertion-order encodings.
    if not isinstance(value, Mapping) or len(value) != len(keys) or set(value.keys()) != set(keys):
        raise DriverContractError(error)


def strict_constructibility_index(index: object) -> int:
    if type(index) is not int:
        raise DriverContractError("INDEX_MUST_BE_PYTHON_INT_NONBOOL")
    sf.require_constructibility_index(index)
    return index


def verify_authority(root: str | Path) -> dict[str, object]:
    root = Path(root)
    expected = {
        str(PREREG_REL): PREREG_SHA256,
        str(POPULATION_REL): POPULATION_SHA256,
        str(LABEL_BINDING_REL): LABEL_BINDING_FILE_SHA256,
        str(ACTION_PRIMITIVE_REL): ACTION_PRIMITIVE_SHA256,
        str(RUNTIME_PRIMITIVE_REL): RUNTIME_PRIMITIVE_SHA256,
        str(SF_HELPER_REL): SF_HELPER_SHA256,
        str(LABEL_HELPER_REL): LABEL_HELPER_SHA256,
    }
    actual: dict[str, str] = {}
    for rel, digest in expected.items():
        path = root / rel
        if not path.is_file():
            raise DriverContractError(f"AUTHORITY_FILE_MISSING:{rel}")
        got = _sha256_file(path)
        if got != digest:
            raise DriverContractError(f"AUTHORITY_SHA256_MISMATCH:{rel}")
        actual[rel] = got
    if sf.POPULATION_SHA256 != POPULATION_SHA256:
        raise DriverContractError("POPULATION_CONSTANT_DRIFT")
    if lb.canonical_suffix_table_sha256() != SUFFIX_TABLE_SHA256 or lb.SUFFIX_TABLE_SHA256 != SUFFIX_TABLE_SHA256:
        raise DriverContractError("SUFFIX_TABLE_SHA256_MISMATCH")
    binding = json.loads((root / LABEL_BINDING_REL).read_text(encoding="utf-8"))
    if binding.get("suffix_table_sha256") != SUFFIX_TABLE_SHA256:
        raise DriverContractError("LABEL_BINDING_SUFFIX_TABLE_SHA256_MISMATCH")
    if binding.get("model_binding") != {
        "dtype": "bfloat16", "id": lb.MODEL_ID, "model_forward": False, "model_loaded": False,
        "offload": False, "quantization": False, "revision": lb.MODEL_REVISION, "thinking": False,
        "tokenizer_only_canary": True, "tokenizers": lb.TOKENIZERS_VERSION,
        "transformers": lb.TRANSFORMERS_VERSION,
    }:
        raise DriverContractError("MODEL_BINDING_ARTIFACT_DRIFT")
    return {"files_sha256": actual, "suffix_table_sha256": SUFFIX_TABLE_SHA256, "model_binding": MODEL_BINDING}


def build_manifest(root: str | Path) -> dict[str, object]:
    authority = verify_authority(root)
    rows = sf.load_constructibility_population(Path(root) / POPULATION_REL)
    paths = []
    for expected_index, row in enumerate(rows):
        _exact_keys(row, ("game_path", "index", "phase", "rank_sha256"), "POPULATION_ROW_SCHEMA_DRIFT")
        if row["index"] != expected_index or row["phase"] != "constructibility":
            raise DriverContractError("CONSTRUCTIBILITY_POPULATION_PHASE_DRIFT")
        strict_constructibility_index(row["index"])
        paths.append({"index": row["index"], "game_path": row["game_path"], "rank_sha256": row["rank_sha256"]})
    payload = {
        "schema": MANIFEST_SCHEMA,
        "authority": authority,
        "fixed_indices": list(FIXED_INDICES),
        "paths": paths,
        "no_replacement": True,
        "pass_count": PASS_COUNT,
        "pass_label": PASS_LABEL,
        "fail_label": FAIL_LABEL,
        "runtime_adapter_contract": {
            "action_selection_source_sha256": ACTION_PRIMITIVE_SHA256,
            "environment_runtime_source_sha256": RUNTIME_PRIMITIVE_SHA256,
            "prefix_scope": "exactly two model-own nontrivial actions under action-validity/runtime guards; no whole-task win or post-cut qualification",
            "shared_action_a3": "deterministic reviewed admissible-command scorer at the frozen cut; supplied without stepping the environment",
            "shared_action_phase": "frozen row1_action_phase_mapping_v2 classification supplied by a separately reviewed narrow runtime adapter",
            "whole_task_success_criterion_forbidden": True,
        },
        "source_base_commit": SOURCE_BASE_COMMIT,
        "suffix_provenance_review_commit": SUFFIX_PROVENANCE_REVIEW_COMMIT,
        "scientific_result": "NOT_ASSESSED",
    }
    return {**payload, "manifest_sha256": canonical_sha256(payload)}


def _validate_reason_list(reasons: object, *, eligible: bool) -> list[str]:
    if not isinstance(reasons, list) or any(not isinstance(x, str) or not x for x in reasons):
        raise DriverContractError("PREFIX_REASONS_MUST_BE_NONEMPTY_STRINGS")
    forbidden = ("WON", "SUCCESS", "FUTURE", "POST_CUT", "EXPERT", "ORACLE")
    if any(any(fragment in x.upper() for fragment in forbidden) for x in reasons):
        raise DriverContractError("PREFIX_REASON_USES_FORBIDDEN_OUTCOME_OR_FUTURE_CONCEPT")
    if eligible and reasons:
        raise DriverContractError("ELIGIBLE_PREFIX_MUST_HAVE_NO_REASONS")
    if not eligible and not reasons:
        raise DriverContractError("INELIGIBLE_PREFIX_REQUIRES_REASON")
    return list(reasons)


def _finite_scores(value: object, error: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 6:
        raise DriverContractError(error)
    out = []
    for x in value:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise DriverContractError(error)
        y = float(x)
        if not math.isfinite(y):
            raise DriverContractError(error)
        out.append(y)
    return tuple(out)


def _phase_argmax(scores: Sequence[float]) -> str:
    probs = sf.softmax_float64(scores)
    return sf.PHASE_LABELS[min(range(6), key=lambda i: (-probs[i], i))]


_NONFINITE_TAG = "__successor_feature_nonfinite_float_v1__"


def _freeze_attempt_evidence(value: object) -> object:
    """Convert exact attempt material to deterministic JSON-safe evidence.

    Non-finite score inputs are scientifically ineligible but must still be
    packetizable.  They are represented by a typed sentinel so the validator can
    later reconstruct the exact invalid input and re-run the frozen derivation.
    """
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            label = "nan"
        elif value > 0:
            label = "+inf"
        else:
            label = "-inf"
        return {_NONFINITE_TAG: label}
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise DriverContractError("ATTEMPT_EVIDENCE_KEY_MUST_BE_TEXT")
            out[key] = _freeze_attempt_evidence(child)
        return out
    if isinstance(value, list):
        return [_freeze_attempt_evidence(x) for x in value]
    if isinstance(value, tuple):
        return [_freeze_attempt_evidence(x) for x in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise DriverContractError("ATTEMPT_EVIDENCE_VALUE_UNSUPPORTED")


def attempt_material_sha256(material: Mapping[str, object]) -> str:
    """Hash attempt material through a canonical JSON-safe evidence projection.

    Frozen constructibility semantics classify NaN/Inf score records as
    ineligible rather than as serializer failures.  The external material seal
    therefore hashes a typed non-finite sentinel projection, never permissive
    JSON NaN spellings.
    """
    if not isinstance(material, Mapping):
        raise DriverContractError("ATTEMPT_MATERIAL_MUST_BE_OBJECT")
    frozen = _freeze_attempt_evidence(material)
    if not isinstance(frozen, Mapping):
        raise DriverContractError("ATTEMPT_MATERIAL_EVIDENCE_MUST_BE_OBJECT")
    return canonical_sha256(frozen)


def _validate_material_identity(material: Mapping[str, object], manifest: Mapping[str, object]) -> tuple[int, Mapping[str, object]]:
    _exact_keys(material, _TOP_KEYS, "ATTEMPT_MATERIAL_SCHEMA_MISMATCH")
    index = strict_constructibility_index(material["index"])
    expected = manifest["paths"][index]  # type: ignore[index]
    if material["game_path"] != expected["game_path"] or material["rank_sha256"] != expected["rank_sha256"]:
        raise DriverContractError("FROZEN_PATH_IDENTITY_MISMATCH")
    return index, expected


def build_attempt_material_manifest(
    materials: Sequence[Mapping[str, object]], manifest: Mapping[str, object]
) -> dict[str, object]:
    """Seal exactly the fixed 16 runtime-adapter material records before packetization.

    The returned digest is an external authorization value: packetization and
    summarization require the caller to present this exact digest rather than
    deriving authority from mutable packet/material directories.
    """
    if len(materials) != len(FIXED_INDICES):
        raise DriverContractError("MATERIAL_MANIFEST_REQUIRES_EXACTLY_16_MATERIALS")
    by_index: dict[int, Mapping[str, object]] = {}
    for material in materials:
        if not isinstance(material, Mapping):
            raise DriverContractError("ATTEMPT_MATERIAL_MUST_BE_OBJECT")
        idx, _ = _validate_material_identity(material, manifest)
        if idx in by_index:
            raise DriverContractError("DUPLICATE_ATTEMPT_MATERIAL_INDEX")
        by_index[idx] = material
    if set(by_index) != set(FIXED_INDICES):
        raise DriverContractError("ATTEMPT_MATERIAL_INDEX_SET_MISMATCH")
    entries = []
    for i in FIXED_INDICES:
        expected = manifest["paths"][i]  # type: ignore[index]
        entries.append({
            "index": i,
            "game_path": expected["game_path"],
            "rank_sha256": expected["rank_sha256"],
            "attempt_material_sha256": attempt_material_sha256(by_index[i]),
        })
    payload = {
        "schema": MATERIAL_MANIFEST_SCHEMA,
        "scientific_manifest_sha256": manifest["manifest_sha256"],
        "fixed_indices": list(FIXED_INDICES),
        "entries": entries,
        "seal_contract": "bind material_manifest_sha256 outside mutable material/packet directories before packetization and summary",
        "scientific_result": "NOT_ASSESSED",
    }
    return {**payload, "material_manifest_sha256": canonical_sha256(payload)}


def validate_attempt_material_manifest(
    material_manifest: Mapping[str, object],
    manifest: Mapping[str, object],
    expected_material_manifest_sha256: str,
) -> dict[str, object]:
    keys = (
        "schema", "scientific_manifest_sha256", "fixed_indices", "entries",
        "seal_contract", "scientific_result", "material_manifest_sha256",
    )
    _exact_keys(material_manifest, keys, "MATERIAL_MANIFEST_SCHEMA_MISMATCH")
    if material_manifest["schema"] != MATERIAL_MANIFEST_SCHEMA or material_manifest["scientific_result"] != "NOT_ASSESSED":
        raise DriverContractError("MATERIAL_MANIFEST_AUTHORITY_FIELDS_MISMATCH")
    if material_manifest["scientific_manifest_sha256"] != manifest["manifest_sha256"]:
        raise DriverContractError("MATERIAL_MANIFEST_SCIENTIFIC_MANIFEST_MISMATCH")
    if material_manifest["fixed_indices"] != list(FIXED_INDICES):
        raise DriverContractError("MATERIAL_MANIFEST_FIXED_INDICES_MISMATCH")
    if material_manifest["seal_contract"] != "bind material_manifest_sha256 outside mutable material/packet directories before packetization and summary":
        raise DriverContractError("MATERIAL_MANIFEST_SEAL_CONTRACT_MISMATCH")
    if not isinstance(expected_material_manifest_sha256, str) or len(expected_material_manifest_sha256) != 64:
        raise DriverContractError("EXPECTED_MATERIAL_MANIFEST_SHA256_INVALID")
    if any(c not in "0123456789abcdef" for c in expected_material_manifest_sha256):
        raise DriverContractError("EXPECTED_MATERIAL_MANIFEST_SHA256_INVALID")
    payload = {k: material_manifest[k] for k in keys if k != "material_manifest_sha256"}
    recomputed = canonical_sha256(payload)
    if material_manifest["material_manifest_sha256"] != recomputed:
        raise DriverContractError("MATERIAL_MANIFEST_SELF_SHA256_MISMATCH")
    if recomputed != expected_material_manifest_sha256:
        raise DriverContractError("MATERIAL_MANIFEST_EXTERNAL_SEAL_MISMATCH")
    entries = material_manifest["entries"]
    if not isinstance(entries, list) or len(entries) != len(FIXED_INDICES):
        raise DriverContractError("MATERIAL_MANIFEST_ENTRIES_MISMATCH")
    out_entries = []
    for expected_i, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise DriverContractError("MATERIAL_MANIFEST_ENTRY_MUST_BE_OBJECT")
        _exact_keys(entry, ("index", "game_path", "rank_sha256", "attempt_material_sha256"), "MATERIAL_MANIFEST_ENTRY_SCHEMA_MISMATCH")
        i = strict_constructibility_index(entry["index"])
        if i != expected_i:
            raise DriverContractError("MATERIAL_MANIFEST_ENTRY_ORDER_MISMATCH")
        expected = manifest["paths"][i]  # type: ignore[index]
        if entry["game_path"] != expected["game_path"] or entry["rank_sha256"] != expected["rank_sha256"]:
            raise DriverContractError("MATERIAL_MANIFEST_FROZEN_IDENTITY_MISMATCH")
        digest = entry["attempt_material_sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise DriverContractError("ATTEMPT_MATERIAL_SHA256_INVALID")
        out_entries.append(dict(entry))
    return {**{k: material_manifest[k] for k in keys if k != "entries"}, "entries": out_entries}


def _validate_material_against_seal(
    material: Mapping[str, object],
    manifest: Mapping[str, object],
    material_manifest: Mapping[str, object],
    expected_material_manifest_sha256: str,
) -> tuple[int, Mapping[str, object], str]:
    validated_manifest = validate_attempt_material_manifest(material_manifest, manifest, expected_material_manifest_sha256)
    index, expected = _validate_material_identity(material, manifest)
    material_sha = attempt_material_sha256(material)
    entry = validated_manifest["entries"][index]  # type: ignore[index]
    if entry["attempt_material_sha256"] != material_sha:
        raise DriverContractError("ATTEMPT_MATERIAL_SHA256_MISMATCH")
    return index, expected, material_sha


def build_attempt_packet(
    material: Mapping[str, object],
    manifest: Mapping[str, object],
    material_manifest: Mapping[str, object],
    expected_material_manifest_sha256: str,
) -> dict[str, object]:
    index, expected, material_sha = _validate_material_against_seal(
        material, manifest, material_manifest, expected_material_manifest_sha256
    )
    prefix = material["prefix"]
    if not isinstance(prefix, Mapping):
        raise DriverContractError("PREFIX_MUST_BE_OBJECT")
    _exact_keys(prefix, _PREFIX_KEYS, "PREFIX_SCHEMA_MISMATCH")
    eligible_obj = prefix["eligible"]
    if type(eligible_obj) is not bool:
        raise DriverContractError("PREFIX_ELIGIBLE_MUST_BE_BOOL")
    prefix_eligible = bool(eligible_obj)
    reasons = _validate_reason_list(prefix["reasons"], eligible=prefix_eligible)
    primitives = prefix["primitive_bindings"]
    if not isinstance(primitives, Mapping):
        raise DriverContractError("PRIMITIVE_BINDINGS_MUST_BE_OBJECT")
    _exact_keys(primitives, _PRIMITIVE_KEYS, "PRIMITIVE_BINDINGS_SCHEMA_MISMATCH")
    if primitives["action_primitive_sha256"] != ACTION_PRIMITIVE_SHA256 or primitives["runtime_primitive_sha256"] != RUNTIME_PRIMITIVE_SHA256:
        raise DriverContractError("RUNTIME_PRIMITIVE_BINDING_MISMATCH")

    base = {
        "schema": SCHEMA,
        "manifest_sha256": manifest["manifest_sha256"],
        "attempt_material_manifest_sha256": expected_material_manifest_sha256,
        "attempt_material_sha256": material_sha,
        "index": index,
        "game_path": expected["game_path"],
        "rank_sha256": expected["rank_sha256"],
        "scientific_result": "NOT_ASSESSED",
    }
    if not prefix_eligible:
        if prefix["observable"] is not None or prefix["shared_action_a3"] is not None or prefix["shared_action_phase"] is not None or material["score_bundle"] is not None:
            raise DriverContractError("INELIGIBLE_PREFIX_MUST_NOT_EXPOSE_POST_PREFIX_MATERIAL")
        payload = {**base, "eligible": False, "eligibility_reasons": reasons, "prefix_provenance": {"primitive_bindings": dict(primitives)}, "constructibility": None}
        return {**payload, "packet_sha256": canonical_sha256(payload)}

    observable = prefix["observable"]
    if not isinstance(observable, Mapping):
        raise DriverContractError("ELIGIBLE_PREFIX_REQUIRES_OBSERVABLE_SNAPSHOT")
    _exact_keys(observable, _OBSERVABLE_KEYS, "OBSERVABLE_SCHEMA_MISMATCH")
    hist_obj = observable["history"]
    if not isinstance(hist_obj, list):
        raise DriverContractError("HISTORY_MUST_BE_LIST")
    snapshot = lb.render_snapshot_utf8(
        observable["task_instruction"],  # type: ignore[arg-type]
        hist_obj,  # type: ignore[arg-type]
        observable["current_observation"],  # type: ignore[arg-type]
        observable["admissible_commands"],  # type: ignore[arg-type]
    )
    a3 = prefix["shared_action_a3"]
    if not isinstance(a3, str):
        raise DriverContractError("SHARED_ACTION_A3_MUST_BE_TEXT")
    commands = observable["admissible_commands"]
    if not isinstance(commands, list) or a3 not in commands:
        raise DriverContractError("SHARED_ACTION_A3_NOT_CURRENTLY_ADMISSIBLE")
    phase = prefix["shared_action_phase"]
    if phase not in sf.PHASE_LABELS:
        raise DriverContractError("SHARED_ACTION_PHASE_INVALID")

    score_bundle = material["score_bundle"]
    if not isinstance(score_bundle, Mapping):
        raise DriverContractError("ELIGIBLE_PREFIX_REQUIRES_SCORE_BUNDLE")
    _exact_keys(score_bundle, _SCORE_KEYS, "SCORE_BUNDLE_SCHEMA_MISMATCH")
    step2 = score_bundle["step2"]
    branches_obj = score_bundle["branches"]
    if not isinstance(step2, Mapping) or not isinstance(branches_obj, Mapping):
        raise DriverContractError("SCORE_BUNDLE_CHILD_SCHEMA_MISMATCH")
    _exact_keys(step2, _STEP_KEYS, "STEP2_SCORE_SCHEMA_MISMATCH")
    step2_prompt = lb.render_label_prompt_utf8(snapshot, a3)
    if step2["prompt_sha256"] != _sha256_bytes(step2_prompt.encode("utf-8")):
        raise DriverContractError("STEP2_PROMPT_SHA256_MISMATCH")
    try:
        step2_scores = _finite_scores(step2["scores"], "STEP2_SCORES_INVALID")
        top0, top1 = sf.branch_labels_if_plausible(step2_scores)
    except (sf.ContractError, DriverContractError) as exc:
        if branches_obj:
            raise DriverContractError("INELIGIBLE_STEP2_MUST_NOT_HAVE_BRANCH_SCORES") from exc
        payload = {
            **base,
            "eligible": False,
            "eligibility_reasons": [str(exc)],
            "prefix_provenance": {
                "primitive_bindings": dict(primitives),
                "snapshot_sha256": _sha256_bytes(snapshot.encode("utf-8")),
                "shared_action_a3_sha256": _sha256_bytes(a3.encode("utf-8")),
                "shared_action_phase": phase,
            },
            "constructibility": None,
        }
        return {**payload, "packet_sha256": canonical_sha256(payload)}

    branch_a, branch_b = sf.orient_branches(str(expected["game_path"]), top0, top1)
    if set(branches_obj.keys()) != {branch_a, branch_b} or len(branches_obj) != 2:
        raise DriverContractError("BRANCH_SCORE_LABEL_SET_MISMATCH")
    carriers: dict[str, tuple[tuple[int, ...], ...]] = {}
    branch_detail: dict[str, object] = {}
    for branch in (branch_a, branch_b):
        rec = branches_obj[branch]
        if not isinstance(rec, Mapping):
            raise DriverContractError("BRANCH_SCORE_RECORD_MUST_BE_OBJECT")
        _exact_keys(rec, _BRANCH_KEYS, "BRANCH_SCORE_SCHEMA_MISMATCH")
        row3_prompt = lb.render_label_prompt_utf8(snapshot, a3, [branch])
        if rec["row3_prompt_sha256"] != _sha256_bytes(row3_prompt.encode("utf-8")):
            raise DriverContractError("ROW3_PROMPT_SHA256_MISMATCH")
        try:
            row3_scores = _finite_scores(rec["row3_scores"], "ROW3_SCORES_INVALID")
        except DriverContractError as exc:
            payload = {
                **base, "eligible": False, "eligibility_reasons": [str(exc)],
                "prefix_provenance": {
                    "primitive_bindings": dict(primitives),
                    "snapshot_sha256": _sha256_bytes(snapshot.encode("utf-8")),
                    "shared_action_a3_sha256": _sha256_bytes(a3.encode("utf-8")),
                    "shared_action_phase": phase,
                },
                "constructibility": None,
            }
            return {**payload, "packet_sha256": canonical_sha256(payload)}
        row3_label = _phase_argmax(row3_scores)
        row4_prompt = lb.render_label_prompt_utf8(snapshot, a3, [branch, row3_label])
        if rec["row4_prompt_sha256"] != _sha256_bytes(row4_prompt.encode("utf-8")):
            raise DriverContractError("ROW4_PROMPT_SHA256_MISMATCH")
        try:
            row4_scores = _finite_scores(rec["row4_scores"], "ROW4_SCORES_INVALID")
        except DriverContractError as exc:
            payload = {
                **base, "eligible": False, "eligibility_reasons": [str(exc)],
                "prefix_provenance": {
                    "primitive_bindings": dict(primitives),
                    "snapshot_sha256": _sha256_bytes(snapshot.encode("utf-8")),
                    "shared_action_a3_sha256": _sha256_bytes(a3.encode("utf-8")),
                    "shared_action_phase": phase,
                },
                "constructibility": None,
            }
            return {**payload, "packet_sha256": canonical_sha256(payload)}
        carrier = (
            sf.one_hot_row(str(phase)),
            sf.one_hot_row(branch),
            sf.largest_remainder_uint8(sf.softmax_float64(row3_scores)),
            sf.largest_remainder_uint8(sf.softmax_float64(row4_scores)),
        )
        serial = sf.serialize_carrier(carrier)
        if len(serial.encode("ascii")) != 52:
            raise DriverContractError("CARRIER_SERIALIZATION_LENGTH_DRIFT")
        carriers[branch] = carrier
        branch_detail[branch] = {
            "row3_greedy_phase": row3_label,
            "row3_prompt_sha256": rec["row3_prompt_sha256"],
            "row4_prompt_sha256": rec["row4_prompt_sha256"],
            "carrier": serial,
            "carrier_sha256": _sha256_bytes(serial.encode("ascii")),
        }

    distance = sf.future_distance(carriers[branch_a], carriers[branch_b])
    is_eligible = distance >= sf.FUTURE_DISTANCE_THRESHOLD
    eligibility_reasons = [] if is_eligible else ["FUTURE_DISTANCE_BELOW_0_50"]
    payload = {
        **base,
        "eligible": is_eligible,
        "eligibility_reasons": eligibility_reasons,
        "prefix_provenance": {
            "primitive_bindings": dict(primitives),
            "snapshot_sha256": _sha256_bytes(snapshot.encode("utf-8")),
            "shared_action_a3_sha256": _sha256_bytes(a3.encode("utf-8")),
            "shared_action_phase": phase,
        },
        "constructibility": {
            "step2_prompt_sha256": step2["prompt_sha256"],
            "oriented_branch_labels": [branch_a, branch_b],
            "branches": branch_detail,
            "future_distance": distance,
            "future_distance_threshold": sf.FUTURE_DISTANCE_THRESHOLD,
        },
    }
    return {**payload, "packet_sha256": canonical_sha256(payload)}


def validate_packet(
    packet: Mapping[str, object],
    material: Mapping[str, object],
    manifest: Mapping[str, object],
    material_manifest: Mapping[str, object],
    expected_material_manifest_sha256: str,
) -> dict[str, object]:
    """Rebuild from sealed attempt evidence; never trust packet self-authorship."""
    if not isinstance(packet, Mapping):
        raise DriverContractError("PACKET_MUST_BE_OBJECT")
    expected = build_attempt_packet(
        material, manifest, material_manifest, expected_material_manifest_sha256
    )
    if canonical_json_bytes(packet) != canonical_json_bytes(expected):
        raise DriverContractError("PACKET_DOES_NOT_MATCH_SEALED_MATERIAL_RECOMPUTATION")
    return expected


def terminal_summary(
    packets: Sequence[Mapping[str, object]],
    materials: Sequence[Mapping[str, object]],
    material_manifest: Mapping[str, object],
    expected_material_manifest_sha256: str,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    if len(packets) != len(FIXED_INDICES):
        raise DriverContractError("TERMINAL_SUMMARY_REQUIRES_EXACTLY_16_PACKETS")
    if len(materials) != len(FIXED_INDICES):
        raise DriverContractError("TERMINAL_SUMMARY_REQUIRES_EXACTLY_16_MATERIALS")
    validated_material_manifest = validate_attempt_material_manifest(
        material_manifest, manifest, expected_material_manifest_sha256
    )
    materials_by_index: dict[int, Mapping[str, object]] = {}
    for material in materials:
        if not isinstance(material, Mapping):
            raise DriverContractError("ATTEMPT_MATERIAL_MUST_BE_OBJECT")
        idx, _, material_sha = _validate_material_against_seal(
            material, manifest, validated_material_manifest, expected_material_manifest_sha256
        )
        if idx in materials_by_index:
            raise DriverContractError("DUPLICATE_ATTEMPT_MATERIAL_INDEX")
        # Redundant explicit check makes the authority path auditable here.
        entry = validated_material_manifest["entries"][idx]  # type: ignore[index]
        if entry["attempt_material_sha256"] != material_sha:
            raise DriverContractError("ATTEMPT_MATERIAL_SHA256_MISMATCH")
        materials_by_index[idx] = material
    if set(materials_by_index) != set(FIXED_INDICES):
        raise DriverContractError("ATTEMPT_MATERIAL_INDEX_SET_MISMATCH")

    by_index: dict[int, dict[str, object]] = {}
    for packet in packets:
        if not isinstance(packet, Mapping) or "index" not in packet:
            raise DriverContractError("PACKET_MUST_BE_OBJECT_WITH_INDEX")
        idx = strict_constructibility_index(packet["index"])
        if idx in by_index:
            raise DriverContractError("DUPLICATE_PACKET_INDEX")
        validated = validate_packet(
            packet, materials_by_index[idx], manifest,
            validated_material_manifest, expected_material_manifest_sha256,
        )
        by_index[idx] = validated
    if set(by_index) != set(FIXED_INDICES):
        raise DriverContractError("TERMINAL_PACKET_INDEX_SET_MISMATCH")
    eligible_count = sum(bool(by_index[i]["eligible"]) for i in FIXED_INDICES)
    payload = {
        "schema": SUMMARY_SCHEMA,
        "manifest_sha256": manifest["manifest_sha256"],
        "attempt_material_manifest_sha256": expected_material_manifest_sha256,
        "attempt_material_sha256_by_index": [validated_material_manifest["entries"][i]["attempt_material_sha256"] for i in FIXED_INDICES],  # type: ignore[index]
        "packet_sha256_by_index": [by_index[i]["packet_sha256"] for i in FIXED_INDICES],
        "eligible_count": eligible_count,
        "target_count": 16,
        "pass_count": PASS_COUNT,
        "verdict": PASS_LABEL if eligible_count >= PASS_COUNT else FAIL_LABEL,
        "scientific_result": "NOT_ASSESSED",
    }
    return {**payload, "summary_sha256": canonical_sha256(payload)}
