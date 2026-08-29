"""PRE-SCIENCE executable/readiness machinery for CPDS.

This module authenticates already-reviewed immutable authority, generates and
validates the prospectively randomized six-arm isolated-slot assignment
manifests, and builds *execution plans* from authenticated constructibility
packets.  It deliberately does not load a model, execute an environment, score
an arm, register an Experiment/Decision, or inspect scientific outcomes.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import subprocess
import stat
import sys
from math import factorial
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

import cpds_graphfork_constructibility_v1 as gf
import cpds_recurrent_realization_contract_validator_v1 as rr

ROOT = Path(__file__).resolve().parent
DESIGN = ROOT / "results" / "design"
CONTRACT_PATH = DESIGN / "plancarry_cpds_executable_implementation_readiness_contract_v2_crash_durable_20260829.json"
AUDIT_PATH = DESIGN / "plancarry_cpds_executable_implementation_readiness_static_audit_v2_crash_durable_20260829.json"

SCHEMA = "PLANCARRY_CPDS_EXECUTABLE_IMPLEMENTATION_READINESS_V2_CRASH_DURABLE"
ASSIGNMENT_MANIFEST_SCHEMA = "PLANCARRY_CPDS_ARM_SLOT_ASSIGNMENT_MANIFEST_V1"
TWO_SPLIT_BUNDLE_SCHEMA = "PLANCARRY_CPDS_TWO_SPLIT_PREOUTCOME_FREEZE_BUNDLE_V1"
RUNTIME_PLAN_SCHEMA = "PLANCARRY_CPDS_ISOLATED_SIX_ARM_RUNTIME_PLAN_V1"
DURABLE_TRANSACTION_SCHEMA = "PLANCARRY_CPDS_ASSIGNMENT_FREEZE_TRANSACTION_V2"
DURABLE_DRAW_RECORD_SCHEMA = "PLANCARRY_CPDS_DURABLE_OS_CSPRNG_U16_DRAW_V1"
TRANSACTION_NONCE_BYTES = 32
EXACT_ARMS = (
    "NO_CARRY",
    "STATIC_ONESHOT",
    "STATIC_REPEAT",
    "ALIGNED_RECURSION",
    "TRANSITION_PERMUTED",
    "MATCHED_INFORMATION",
)
EXACT_SLOTS = tuple(f"SLOT_{i}" for i in range(6))
DEVELOPMENT_NAMESPACE = "CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1"
CONFIRMATION_NAMESPACE = "CPDS_CONFIRMATION_GRAPH_FAMILIES_V1"
ASSIGNMENT_SPACE_SIZE = 720
WORD_SPACE = 65536
REJECTION_CUTOFF = 64800
FAMILY_COUNT = 33
PRIMARY_ENDPOINT = gf.PRIMARY_ENDPOINT
ZERO_TOLERANCE_GUARDS = (
    "leakage_or_provenance_violations",
    "G_force_execute_or_environment_mutation_violations",
    "call_geometry_or_arm_matching_violations",
    "arm_slot_assignment_manifest_violations",
    "cross_slot_or_cross_family_interference_violations",
)

CANDIDATE_COMMIT = "30bdce87343a20994dd82cd849fd9ec210f4dc22"
CANDIDATE_TREE = "5c08e73522855193cbafcf85cf6b33ec777e173d"
CONSTRUCTIBILITY_COMMIT = "c1c6517ff4678c2a9b151f67a1ff4dd6f5aae244"
CONSTRUCTIBILITY_TREE = "0f048dde696aef3bbb531214ace21ed387be1f62"
V3_COMMIT = "df17c5ee3a3d2c6bccd70367886216cd043d40f3"
V3_TREE = "f0cd2ee999838dbfa88c54732a7ee1988f5f2adf"
REVIEW_COMMIT = "dac9dfc848bbf28c18c9515b933b510afd63a292"
REVIEW_TREE = "ec365b59246fff2112a60152e54e4a043f857cd9"

CANDIDATE_FILES = {
    "cpds_recurrent_realization_contract_validator_v1.py": "898bfef39ec60a983936c3499e75b1cadcc0975a5fc274a788a2e24062258629",
    "results/design/plancarry_cpds_recurrent_realization_feature_basis_v1_20260829.json": "dc50e2a8b1d116cb81602102717e35323ce43d45d0989ca1a3783a8aaa84b772",
    "results/design/plancarry_cpds_recurrent_realization_static_audit_v1_20260829.json": "cf93cbd6cd2b5b2217c30b27ca731c75ae749253d819de8026a8fc1831bbb322",
    "tests/test_cpds_recurrent_realization_feature_basis_v1.py": "d5c6db46fa8fbd37b9a485abcd715a27bd3eed5c7fbf206bcfd97f3acee48087",
}
CONSTRUCTIBILITY_FILES = {
    "cpds_graphfork_constructibility_v1.py": "18e719298703bdff9b5c88e5a4c913fa787892fde6f1d0fc049cfeea2aeb5550",
    "tests/test_cpds_graphfork_constructibility_v1.py": "5c027408523e82b7b40719e0e32e2b3c83c2e9fb2b58fa6055e1b746f0dbb44e",
    "cpds_graphfork_contract_validator_v1.py": "c3f6b9ee38fff7a984449e9608b925a0b9f6c7b1bbd268db9beba148b25cbd20",
    "tests/test_cpds_graphfork_contract_validator_v1.py": "3cfcc74671b98564c8c68ed131779a1288e9dc4bc8a91c1bcd88914aa04fa74e",
}
V3_FILES = {
    "results/design/plancarry_cpds_numeric_statistical_decision_contract_v3_20260829.json": "24e393c426edae7d52ff4e30bc8f24559d21f352076a91695458c32e238d0f21",
    "results/design/plancarry_cpds_randomized_arm_slot_inference_spec_v1_20260829.json": "cdcad645a3c30cc92eebd573eeb9b4e6497ea2769db990566b3863850f3649c7",
    "results/design/plancarry_cpds_numeric_statistical_static_audit_v3_20260829.json": "2d3c5e27f1f896c6241d2989d6ebf08bc8cca2b2a782faae85ff9b85181407ba",
    "tests/test_cpds_numeric_statistical_decision_contract_v3.py": "5b67d0abd51dcdd054ad2b37472328319789573671c33c8b07e7d499d8543de8",
}
REVIEW_FILES = {
    "results/design/plancarry_cpds_recurrent_realization_feature_basis_independent_review_a4_20260829.json": "77c7b3adc4ff95b96547494a182064bd41a68683b1020a06ce540a95ed70fcfb",
}

ASSIGNMENT_RECORD_FIELDS = {
    "split_namespace",
    "family_id",
    "structural_family_key_sha256",
    "draw_words_u16_in_order",
    "accepted_word_u16",
    "assignment_index",
    "arm_permutation",
    "generated_before_any_development_arm_outcome",
    "generator_code_sha256",
}


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _canon_sha(obj: Any) -> str:
    return hashlib.sha256(_canonical_bytes(obj)).hexdigest()


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _git(repo_root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(["git", *args], cwd=repo_root, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("GIT_AUTHORITY_UNAVAILABLE") from exc


def _git_commit(repo_root: Path, commit: str) -> str:
    return _git(repo_root, "rev-parse", f"{commit}^{{commit}}").decode().strip()


def _git_tree(repo_root: Path, commit: str) -> str:
    return _git(repo_root, "show", "-s", "--format=%T", commit).decode().strip()


def _git_file_sha(repo_root: Path, commit: str, path: str) -> str:
    return _sha_bytes(_git(repo_root, "show", f"{commit}:{path}"))


def _expected_authority_snapshot() -> dict[str, Any]:
    return {
        "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "files": CANDIDATE_FILES},
        "constructibility": {"commit": CONSTRUCTIBILITY_COMMIT, "tree": CONSTRUCTIBILITY_TREE, "files": CONSTRUCTIBILITY_FILES},
        "v3_statistics": {"commit": V3_COMMIT, "tree": V3_TREE, "files": V3_FILES},
        "independent_review": {"commit": REVIEW_COMMIT, "tree": REVIEW_TREE, "files": REVIEW_FILES},
        "working_files": {**CANDIDATE_FILES, **CONSTRUCTIBILITY_FILES},
    }


def collect_external_authority_snapshot(repo_root: Path | str = ROOT) -> dict[str, Any]:
    repo = Path(repo_root)
    expected = _expected_authority_snapshot()
    out: dict[str, Any] = {}
    for label in ("candidate", "constructibility", "v3_statistics", "independent_review"):
        e = expected[label]
        commit = _git_commit(repo, e["commit"])
        out[label] = {
            "commit": commit,
            "tree": _git_tree(repo, commit),
            "files": {path: _git_file_sha(repo, commit, path) for path in e["files"]},
        }
    out["working_files"] = {}
    for path in expected["working_files"]:
        p = repo / path
        if not p.is_file():
            raise ValueError("WORKING_AUTHORITY_FILE_MISSING:" + path)
        out["working_files"][path] = _sha_file(p)
    return out


def validate_authority_snapshot(snapshot: Mapping[str, Any]) -> bool:
    expected = _expected_authority_snapshot()
    if not isinstance(snapshot, Mapping) or set(snapshot) != set(expected):
        raise ValueError("AUTHORITY_SNAPSHOT_SCHEMA")
    for label in ("candidate", "constructibility", "v3_statistics", "independent_review"):
        got = snapshot[label]
        exp = expected[label]
        if not isinstance(got, Mapping) or set(got) != {"commit", "tree", "files"}:
            raise ValueError("AUTHORITY_RECORD_SCHEMA:" + label)
        if got["commit"] != exp["commit"]:
            raise ValueError("AUTHORITY_COMMIT:" + label)
        if got["tree"] != exp["tree"]:
            raise ValueError("AUTHORITY_TREE:" + label)
        if got["files"] != exp["files"]:
            raise ValueError("AUTHORITY_FILE_SHA:" + label)
    if snapshot["working_files"] != expected["working_files"]:
        raise ValueError("WORKING_AUTHORITY_SHA")
    return True


def verify_external_authorities(repo_root: Path | str = ROOT) -> dict[str, Any]:
    snapshot = collect_external_authority_snapshot(repo_root)
    validate_authority_snapshot(snapshot)
    rr.validate_contract(rr.load_contract())
    gf.verify_reviewed_authority()
    # Cross-check immutable V3 bytes, not a copied working-tree substitute.
    repo = Path(repo_root)
    spec_path = "results/design/plancarry_cpds_randomized_arm_slot_inference_spec_v1_20260829.json"
    spec = json.loads(_git(repo, "show", f"{V3_COMMIT}:{spec_path}"))
    if spec["ordered_arms"] != list(EXACT_ARMS) or spec["assignment_space_size"] != ASSIGNMENT_SPACE_SIZE:
        raise ValueError("V3_ASSIGNMENT_AUTHORITY")
    if spec["assignment_generation"]["rejection_cutoff"] != REJECTION_CUTOFF or spec["assignment_generation"]["word_space"] != WORD_SPACE:
        raise ValueError("V3_RNG_AUTHORITY")
    if spec["slot_contract"]["slots"] != list(EXACT_SLOTS) or spec["slot_count"] != len(EXACT_SLOTS):
        raise ValueError("V3_SLOT_AUTHORITY")
    return snapshot


def validate_contract(contract: Mapping[str, Any] | None = None) -> bool:
    d = copy.deepcopy(dict(contract if contract is not None else json.loads(CONTRACT_PATH.read_text())))
    got = d.pop("canonical_object_sha256_without_self_field", None)
    if got != _canon_sha(d):
        raise ValueError("READINESS_CONTRACT_SELF_HASH")
    if d["schema"] != SCHEMA or d["phase"] != "PRE_SCIENCE_EXECUTABLE_READINESS":
        raise ValueError("READINESS_SCOPE")
    if d["scientific_result"] != "NOT_ASSESSED" or d["science_execution_forbidden"] is not True:
        raise ValueError("READINESS_SCIENCE_LABEL")
    if d["exact_arms"] != list(EXACT_ARMS) or d["exact_slots"] != list(EXACT_SLOTS):
        raise ValueError("READINESS_ARM_SLOT_DRIFT")
    if d["v3_assignment"]["space_size"] != 720 or d["v3_assignment"]["rejection_cutoff"] != 64800:
        raise ValueError("READINESS_RANDOMIZATION_DRIFT")
    if d["v3_assignment"]["rng"] != "OS_CSPRNG_16BIT_WORDS_DURABLY_JOURNALED_BEFORE_THRESHOLD_OR_ACCEPTANCE_USE":
        raise ValueError("READINESS_RANDOMIZATION_SOURCE_DRIFT")
    if d["v3_assignment"]["production_rng_injection"] != "FORBIDDEN":
        raise ValueError("READINESS_PRODUCTION_RNG_INJECTION")
    if d["population"]["development_count"] != FAMILY_COUNT or d["population"]["confirmation_count"] != FAMILY_COUNT:
        raise ValueError("READINESS_POPULATION_DRIFT")
    if d["endpoint"] != PRIMARY_ENDPOINT or d["first_action_excluded"] is not True:
        raise ValueError("READINESS_ENDPOINT_DRIFT")
    if d["authority_bindings"] != _expected_authority_snapshot() | {"working_files_policy": "PROTECTED_BYTES_MUST_EQUAL_FROZEN_PARENT_BYTES"}:
        raise ValueError("READINESS_AUTHORITY_DRIFT")
    reviews = d["canonical_review_bindings"]
    expected_reviews = {
        "constructibility": {"work_item_id": "772625e7-9100-485c-a36e-07a319bd6bfa", "verdict": "PASS_FOR_CPDS_GRAPHFORK_GEOMETRY_DUPLICATE_REPAIR"},
        "v3_statistics": {"work_item_id": "8578d9b8-55f8-445c-933b-b7b8faaed433", "verdict": "PASS_FOR_CPDS_V3_STATISTICAL_REPAIR"},
        "recurrent_realization": {"work_item_id": "8712c3ab-7d8d-4bbb-946d-694270641d6d", "verdict": "PASS_FOR_CPDS_RECURRENT_REALIZATION_FEATURE_BASIS_FREEZE", "review_commit": REVIEW_COMMIT, "review_artifact_sha256": next(iter(REVIEW_FILES.values()))},
    }
    if reviews != expected_reviews:
        raise ValueError("READINESS_REVIEW_BINDING")
    stats = d["v3_statistics_preserved"]
    if stats != {"n_per_split": 33, "positive_each_min": 22, "p_22_of_33": 0.04007165622897446, "joint_power_lower_bound_reference": 0.8025570627867475, "statistical_contract_changed": False}:
        raise ValueError("READINESS_V3_STATISTICS_DRIFT")
    if d["zero_tolerance_guard_counter_schema"] != list(ZERO_TOLERANCE_GUARDS):
        raise ValueError("READINESS_ZERO_GUARD_SCHEMA")
    durability = d["crash_durability"]
    expected_durability = {
        "transaction_schema": DURABLE_TRANSACTION_SCHEMA,
        "draw_record_schema": DURABLE_DRAW_RECORD_SCHEMA,
        "transaction_nonce_bytes": TRANSACTION_NONCE_BYTES,
        "transaction_nonce_role": "DURABLE_IDENTITY_ONLY_NOT_ASSIGNMENT_RANDOMNESS",
        "assignment_randomness_source": "OS_CSPRNG_16BIT_WORDS",
        "write_ahead_rule": "RAW_WORD_FILE_AND_PARENT_DIRECTORY_FSYNC_RETURN_BEFORE_THRESHOLD_OR_ACCEPTANCE_USE",
        "transaction_create": "O_CREAT|O_EXCL; canonical JSON; file fsync then parent-directory fsync; preexisting parent required",
        "draw_create": "one canonical write-once record per transaction/split/family/draw_counter; O_CREAT|O_EXCL; file fsync then parent-directory fsync",
        "bundle_finalize": "O_CREAT|O_EXCL; canonical JSON; file fsync then parent-directory fsync; exact readback required",
        "restart": "reuse exact transaction and all existing draw records; generate only a not-yet-existing next raw draw when no final bundle exists; if final bundle exists every journal record must already exist and match",
        "ambiguous_or_corrupt_state": "FAIL_CLOSED_NO_UNLINK_NO_RESEED_NO_REDRAW",
        "concurrency": "O_EXCL selects one durable record; racing writers must load and use the winner, never their losing random word",
        "existing_bundle_missing_or_extra_journal": "FAIL_CLOSED_NO_REGENERATION",
        "same_parent_requirement": True,
        "parent_directory_fsync_required": True,
        "hmac_or_prf_assignment_expansion": False,
        "reason": "Preserve frozen V3 literal OS_CSPRNG_16BIT_WORDS randomization authority while closing the independently reproduced crash/restart redraw window.",
    }
    if durability != expected_durability:
        raise ValueError("READINESS_CRASH_DURABILITY_DRIFT")
    supersedes = d["supersedes_failed_readiness"]
    if supersedes != {
        "failed_commit": "4ea5080aa85dd1340e526885c402d04d0db361f0",
        "failed_tree": "4ac4515812e5a842842c9407a8c29fb44fdf5911",
        "failed_review_commit": "385ee466b54929805be4ea334a3ad28269f6a6f2",
        "failed_review_artifact_sha256": "ac2309628de815e348266aa2d7af98204831388347d523d1cfd41036e8e70a0b",
        "failed_review_work_item_id": "dd5ae582-732e-457c-b3f8-2410b0d0cf96",
        "verdict": "MATERIAL_REPAIR_REQUIRED",
        "defect_id": "CRASH_RESTART_REDRAW_WINDOW",
        "repair_scope": "ENGINEERING_DURABILITY_PROVENANCE_ONLY_NO_SCIENTIFIC_CHANGE",
    }:
        raise ValueError("READINESS_FAILED_REVIEW_BINDING")
    return True


def factoradic_unrank(index: int, arms: Sequence[str] = EXACT_ARMS) -> tuple[str, ...]:
    if type(index) is not int or not 0 <= index < factorial(len(arms)):
        raise ValueError("ASSIGNMENT_INDEX")
    pool = list(arms)
    if len(pool) != len(set(pool)) or tuple(pool) != EXACT_ARMS:
        raise ValueError("ORDERED_ARM_AUTHORITY")
    out: list[str] = []
    remainder = index
    for r in range(len(pool), 0, -1):
        f = factorial(r - 1)
        q, remainder = divmod(remainder, f)
        out.append(pool.pop(q))
    return tuple(out)


def draw_uniform_assignment_index(words: Iterable[int]) -> tuple[list[int], int, int]:
    seen: list[int] = []
    for word in words:
        if type(word) is not int or not 0 <= word < WORD_SPACE:
            raise ValueError("RNG_WORD_U16")
        seen.append(word)
        if word < REJECTION_CUTOFF:
            return seen, word, word % ASSIGNMENT_SPACE_SIZE
    raise ValueError("RNG_WORD_STREAM_EXHAUSTED_BEFORE_ACCEPT")


def assignment_record_identity(record: Mapping[str, Any]) -> str:
    return _canon_sha(dict(record))


def _build_assignment_record_from_words(
    split_namespace: str,
    certificate: Mapping[str, Any],
    words: Iterable[int],
    generator_code_sha256: str | None = None,
) -> dict[str, Any]:
    if split_namespace not in {DEVELOPMENT_NAMESPACE, CONFIRMATION_NAMESPACE}:
        raise ValueError("SPLIT_NAMESPACE")
    code_sha = generator_code_sha256 or _sha_file(Path(__file__))
    if not _is_sha(code_sha):
        raise ValueError("GENERATOR_CODE_SHA")
    required_cert = {"structural_family_key_sha256", "family_id", "cohort_namespace", "source_snapshot_sha256"}
    if not isinstance(certificate, Mapping) or set(certificate) != required_cert:
        raise ValueError("CERTIFICATE_SCHEMA")
    if certificate["cohort_namespace"] != split_namespace:
        raise ValueError("CERTIFICATE_NAMESPACE")
    draw_words, accepted, index = draw_uniform_assignment_index(words)
    record = {
        "split_namespace": split_namespace,
        "family_id": certificate["family_id"],
        "structural_family_key_sha256": certificate["structural_family_key_sha256"],
        "draw_words_u16_in_order": draw_words,
        "accepted_word_u16": accepted,
        "assignment_index": index,
        "arm_permutation": list(factoradic_unrank(index)),
        "generated_before_any_development_arm_outcome": True,
        "generator_code_sha256": code_sha,
    }
    validate_assignment_record(record, certificate, split_namespace, code_sha)
    return record


def validate_assignment_record(
    record: Mapping[str, Any],
    certificate: Mapping[str, Any],
    split_namespace: str,
    expected_generator_code_sha256: str,
) -> bool:
    if not isinstance(record, Mapping) or set(record) != ASSIGNMENT_RECORD_FIELDS:
        raise ValueError("ASSIGNMENT_RECORD_SCHEMA")
    if record["split_namespace"] != split_namespace or certificate["cohort_namespace"] != split_namespace:
        raise ValueError("ASSIGNMENT_NAMESPACE_BINDING")
    if record["family_id"] != certificate["family_id"] or record["structural_family_key_sha256"] != certificate["structural_family_key_sha256"]:
        raise ValueError("ASSIGNMENT_FAMILY_BINDING")
    if record["generator_code_sha256"] != expected_generator_code_sha256 or not _is_sha(expected_generator_code_sha256):
        raise ValueError("ASSIGNMENT_GENERATOR_CODE_BINDING")
    words = record["draw_words_u16_in_order"]
    if not isinstance(words, list) or not words:
        raise ValueError("ASSIGNMENT_DRAW_LOG")
    if any(type(w) is not int or not 0 <= w < WORD_SPACE for w in words):
        raise ValueError("ASSIGNMENT_DRAW_U16")
    if any(w < REJECTION_CUTOFF for w in words[:-1]):
        raise ValueError("ASSIGNMENT_REDRAW_AFTER_ACCEPT")
    if words[-1] >= REJECTION_CUTOFF:
        raise ValueError("ASSIGNMENT_NO_ACCEPTED_WORD")
    if record["accepted_word_u16"] != words[-1]:
        raise ValueError("ASSIGNMENT_ACCEPTED_WORD_BINDING")
    expected_index = words[-1] % ASSIGNMENT_SPACE_SIZE
    if record["assignment_index"] != expected_index:
        raise ValueError("ASSIGNMENT_INDEX_BINDING")
    if record["arm_permutation"] != list(factoradic_unrank(expected_index)):
        raise ValueError("ASSIGNMENT_PERMUTATION_BINDING")
    if record["generated_before_any_development_arm_outcome"] is not True:
        raise ValueError("ASSIGNMENT_POSTOUTCOME")
    return True


def _manifest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    x = copy.deepcopy(dict(manifest))
    x.pop("assignment_manifest_sha256", None)
    return x


def assignment_manifest_identity(manifest: Mapping[str, Any]) -> str:
    return _canon_sha(_manifest_payload(manifest))


def _build_assignment_manifest_from_word_sources(
    generator_manifest: Mapping[str, Any],
    expected_generator_manifest_sha256: str,
    word_source_factory: Callable[[str], Iterable[int]],
    generator_code_sha256: str | None = None,
) -> dict[str, Any]:
    gf.validate_generator_run_manifest(generator_manifest, expected_generator_manifest_sha256)
    namespace = generator_manifest["cohort_namespace"]
    if namespace not in {DEVELOPMENT_NAMESPACE, CONFIRMATION_NAMESPACE}:
        raise ValueError("ASSIGNMENT_SPLIT_NAMESPACE")
    certs = generator_manifest["certificates"]
    if len(certs) != FAMILY_COUNT:
        raise ValueError("ASSIGNMENT_EXACT_33_REQUIRED")
    code_sha = generator_code_sha256 or _sha_file(Path(__file__))
    if word_source_factory is None:
        raise ValueError("WORD_SOURCE_FACTORY_REQUIRED_INTERNAL")
    records = [_build_assignment_record_from_words(namespace, cert, word_source_factory(cert["family_id"]), code_sha) for cert in certs]
    manifest = {
        "schema": ASSIGNMENT_MANIFEST_SCHEMA,
        "phase": "PRE_SCIENCE",
        "scientific_result": "NOT_ASSESSED",
        "split_namespace": namespace,
        "source_snapshot_sha256": generator_manifest["source_snapshot_sha256"],
        "generator_run_manifest_sha256": expected_generator_manifest_sha256,
        "generator_code_sha256": code_sha,
        "family_count": FAMILY_COUNT,
        "assignment_space_size": ASSIGNMENT_SPACE_SIZE,
        "rejection_cutoff": REJECTION_CUTOFF,
        "ordered_arms": list(EXACT_ARMS),
        "slots": list(EXACT_SLOTS),
        "generated_before_any_development_arm_outcome": True,
        "no_redraw_after_acceptance": True,
        "records": records,
    }
    manifest["assignment_manifest_sha256"] = assignment_manifest_identity(manifest)
    validate_assignment_manifest(manifest, generator_manifest, expected_generator_manifest_sha256, code_sha)
    return manifest


def validate_assignment_manifest(
    manifest: Mapping[str, Any],
    generator_manifest: Mapping[str, Any],
    expected_generator_manifest_sha256: str,
    expected_generator_code_sha256: str,
) -> bool:
    gf.validate_generator_run_manifest(generator_manifest, expected_generator_manifest_sha256)
    required = {
        "schema", "phase", "scientific_result", "split_namespace", "source_snapshot_sha256",
        "generator_run_manifest_sha256", "generator_code_sha256", "family_count",
        "assignment_space_size", "rejection_cutoff", "ordered_arms", "slots",
        "generated_before_any_development_arm_outcome", "no_redraw_after_acceptance",
        "records", "assignment_manifest_sha256",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != required:
        raise ValueError("ASSIGNMENT_MANIFEST_SCHEMA")
    if manifest["schema"] != ASSIGNMENT_MANIFEST_SCHEMA or manifest["phase"] != "PRE_SCIENCE" or manifest["scientific_result"] != "NOT_ASSESSED":
        raise ValueError("ASSIGNMENT_MANIFEST_SCOPE")
    if manifest["split_namespace"] != generator_manifest["cohort_namespace"]:
        raise ValueError("ASSIGNMENT_MANIFEST_NAMESPACE")
    if manifest["source_snapshot_sha256"] != generator_manifest["source_snapshot_sha256"] or manifest["generator_run_manifest_sha256"] != expected_generator_manifest_sha256:
        raise ValueError("ASSIGNMENT_MANIFEST_SOURCE_BINDING")
    if manifest["generator_code_sha256"] != expected_generator_code_sha256:
        raise ValueError("ASSIGNMENT_MANIFEST_CODE_BINDING")
    if manifest["family_count"] != FAMILY_COUNT or len(generator_manifest["certificates"]) != FAMILY_COUNT:
        raise ValueError("ASSIGNMENT_MANIFEST_EXACT_33")
    if manifest["assignment_space_size"] != ASSIGNMENT_SPACE_SIZE or manifest["rejection_cutoff"] != REJECTION_CUTOFF:
        raise ValueError("ASSIGNMENT_MANIFEST_RANDOMIZATION")
    if manifest["ordered_arms"] != list(EXACT_ARMS) or manifest["slots"] != list(EXACT_SLOTS):
        raise ValueError("ASSIGNMENT_MANIFEST_ARM_SLOT")
    if manifest["generated_before_any_development_arm_outcome"] is not True or manifest["no_redraw_after_acceptance"] is not True:
        raise ValueError("ASSIGNMENT_MANIFEST_TIMING")
    records = manifest["records"]
    certs = generator_manifest["certificates"]
    if not isinstance(records, list) or len(records) != FAMILY_COUNT:
        raise ValueError("ASSIGNMENT_RECORD_COUNT")
    for record, cert in zip(records, certs):
        validate_assignment_record(record, cert, manifest["split_namespace"], expected_generator_code_sha256)
    if len({r["family_id"] for r in records}) != FAMILY_COUNT or len({r["structural_family_key_sha256"] for r in records}) != FAMILY_COUNT:
        raise ValueError("ASSIGNMENT_DUPLICATE_FAMILY")
    if manifest["assignment_manifest_sha256"] != assignment_manifest_identity(manifest):
        raise ValueError("ASSIGNMENT_MANIFEST_SHA")
    return True


def _bundle_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    x = copy.deepcopy(dict(bundle))
    x.pop("bundle_sha256", None)
    return x


def bundle_identity(bundle: Mapping[str, Any]) -> str:
    return _canon_sha(_bundle_payload(bundle))


def _freeze_two_split_bundle_from_word_sources(
    development_snapshot: Mapping[str, Any], development_source_sha256: str,
    development_generator_manifest: Mapping[str, Any], development_generator_manifest_sha256: str,
    confirmation_snapshot: Mapping[str, Any], confirmation_source_sha256: str,
    confirmation_generator_manifest: Mapping[str, Any], confirmation_generator_manifest_sha256: str,
    development_word_source_factory: Callable[[str], Iterable[int]] | None = None,
    confirmation_word_source_factory: Callable[[str], Iterable[int]] | None = None,
    *, development_arm_outcomes_opened: bool, existing_bundle: Mapping[str, Any] | None = None,
    generator_code_sha256: str | None = None,
) -> dict[str, Any]:
    if development_arm_outcomes_opened is not False:
        raise ValueError("DEVELOPMENT_OUTCOME_ALREADY_OPEN")
    if existing_bundle is not None:
        raise ValueError("ASSIGNMENT_BUNDLE_ALREADY_FROZEN_NO_REDRAW")
    gf.validate_confirmation_disjointness(
        development_generator_manifest, confirmation_generator_manifest,
        development_snapshot, confirmation_snapshot,
        development_source_sha256, confirmation_source_sha256,
        development_generator_manifest_sha256, confirmation_generator_manifest_sha256,
    )
    if development_generator_manifest["cohort_namespace"] != DEVELOPMENT_NAMESPACE or confirmation_generator_manifest["cohort_namespace"] != CONFIRMATION_NAMESPACE:
        raise ValueError("EXACT_SPLIT_NAMESPACE")
    if len(development_generator_manifest["certificates"]) != FAMILY_COUNT or len(confirmation_generator_manifest["certificates"]) != FAMILY_COUNT:
        raise ValueError("EXACT_33_BOTH_SPLITS")
    code_sha = generator_code_sha256 or _sha_file(Path(__file__))
    if development_word_source_factory is None or confirmation_word_source_factory is None:
        raise ValueError("WORD_SOURCE_FACTORY_REQUIRED_INTERNAL")
    dev = _build_assignment_manifest_from_word_sources(development_generator_manifest, development_generator_manifest_sha256, development_word_source_factory, code_sha)
    conf = _build_assignment_manifest_from_word_sources(confirmation_generator_manifest, confirmation_generator_manifest_sha256, confirmation_word_source_factory, code_sha)
    bundle = {
        "schema": TWO_SPLIT_BUNDLE_SCHEMA,
        "phase": "PRE_SCIENCE",
        "scientific_result": "NOT_ASSESSED",
        "generated_before_any_development_arm_outcome": True,
        "confirmation_outcomes_untouched": True,
        "no_replacement": True,
        "no_redraw": True,
        "development_source_snapshot_sha256": development_source_sha256,
        "confirmation_source_snapshot_sha256": confirmation_source_sha256,
        "development_generator_manifest_sha256": development_generator_manifest_sha256,
        "confirmation_generator_manifest_sha256": confirmation_generator_manifest_sha256,
        "development_assignment_manifest": dev,
        "confirmation_assignment_manifest": conf,
    }
    bundle["bundle_sha256"] = bundle_identity(bundle)
    validate_two_split_bundle(
        bundle,
        development_snapshot, development_generator_manifest, development_generator_manifest_sha256,
        confirmation_snapshot, confirmation_generator_manifest, confirmation_generator_manifest_sha256,
        code_sha,
    )
    return bundle





def build_assignment_record_test_only(
    split_namespace: str, certificate: Mapping[str, Any], words: Iterable[int],
    generator_code_sha256: str | None = None,
) -> dict[str, Any]:
    """Synthetic/adversarial helper only; never a production randomization path."""
    return _build_assignment_record_from_words(split_namespace, certificate, words, generator_code_sha256)


def build_assignment_manifest_test_only(
    generator_manifest: Mapping[str, Any], expected_generator_manifest_sha256: str,
    word_source_factory: Callable[[str], Iterable[int]], generator_code_sha256: str | None = None,
) -> dict[str, Any]:
    """Synthetic/adversarial helper only; production must use durable freeze."""
    return _build_assignment_manifest_from_word_sources(
        generator_manifest, expected_generator_manifest_sha256, word_source_factory, generator_code_sha256
    )


def freeze_two_split_bundle_test_only(
    development_snapshot: Mapping[str, Any], development_source_sha256: str,
    development_generator_manifest: Mapping[str, Any], development_generator_manifest_sha256: str,
    confirmation_snapshot: Mapping[str, Any], confirmation_source_sha256: str,
    confirmation_generator_manifest: Mapping[str, Any], confirmation_generator_manifest_sha256: str,
    development_word_source_factory: Callable[[str], Iterable[int]],
    confirmation_word_source_factory: Callable[[str], Iterable[int]],
    *, development_arm_outcomes_opened: bool, existing_bundle: Mapping[str, Any] | None = None,
    generator_code_sha256: str | None = None,
) -> dict[str, Any]:
    """Explicit test-only in-memory path; production callers cannot inject RNG."""
    return _freeze_two_split_bundle_from_word_sources(
        development_snapshot, development_source_sha256,
        development_generator_manifest, development_generator_manifest_sha256,
        confirmation_snapshot, confirmation_source_sha256,
        confirmation_generator_manifest, confirmation_generator_manifest_sha256,
        development_word_source_factory, confirmation_word_source_factory,
        development_arm_outcomes_opened=development_arm_outcomes_opened,
        existing_bundle=existing_bundle, generator_code_sha256=generator_code_sha256,
    )


def validate_two_split_bundle(
    bundle: Mapping[str, Any],
    development_snapshot: Mapping[str, Any], development_generator_manifest: Mapping[str, Any], development_generator_manifest_sha256: str,
    confirmation_snapshot: Mapping[str, Any], confirmation_generator_manifest: Mapping[str, Any], confirmation_generator_manifest_sha256: str,
    expected_generator_code_sha256: str,
) -> bool:
    required = {
        "schema", "phase", "scientific_result", "generated_before_any_development_arm_outcome",
        "confirmation_outcomes_untouched", "no_replacement", "no_redraw",
        "development_source_snapshot_sha256", "confirmation_source_snapshot_sha256",
        "development_generator_manifest_sha256", "confirmation_generator_manifest_sha256",
        "development_assignment_manifest", "confirmation_assignment_manifest", "bundle_sha256",
    }
    if not isinstance(bundle, Mapping) or set(bundle) != required:
        raise ValueError("TWO_SPLIT_BUNDLE_SCHEMA")
    if bundle["schema"] != TWO_SPLIT_BUNDLE_SCHEMA or bundle["phase"] != "PRE_SCIENCE" or bundle["scientific_result"] != "NOT_ASSESSED":
        raise ValueError("TWO_SPLIT_BUNDLE_SCOPE")
    if not all(bundle[k] is True for k in ("generated_before_any_development_arm_outcome", "confirmation_outcomes_untouched", "no_replacement", "no_redraw")):
        raise ValueError("TWO_SPLIT_TIMING_OR_SELECTION")
    dev_source_sha = bundle["development_source_snapshot_sha256"]
    conf_source_sha = bundle["confirmation_source_snapshot_sha256"]
    if dev_source_sha == conf_source_sha:
        raise ValueError("TWO_SPLIT_SOURCE_NOT_INDEPENDENT")
    gf.validate_confirmation_disjointness(
        development_generator_manifest, confirmation_generator_manifest,
        development_snapshot, confirmation_snapshot,
        dev_source_sha, conf_source_sha,
        development_generator_manifest_sha256, confirmation_generator_manifest_sha256,
    )
    if bundle["development_generator_manifest_sha256"] != development_generator_manifest_sha256 or bundle["confirmation_generator_manifest_sha256"] != confirmation_generator_manifest_sha256:
        raise ValueError("TWO_SPLIT_GENERATOR_MANIFEST_BINDING")
    validate_assignment_manifest(bundle["development_assignment_manifest"], development_generator_manifest, development_generator_manifest_sha256, expected_generator_code_sha256)
    validate_assignment_manifest(bundle["confirmation_assignment_manifest"], confirmation_generator_manifest, confirmation_generator_manifest_sha256, expected_generator_code_sha256)
    dev_records = bundle["development_assignment_manifest"]["records"]
    conf_records = bundle["confirmation_assignment_manifest"]["records"]
    if {r["structural_family_key_sha256"] for r in dev_records} & {r["structural_family_key_sha256"] for r in conf_records}:
        raise ValueError("TWO_SPLIT_STRUCTURAL_OVERLAP")
    if {r["family_id"] for r in dev_records} & {r["family_id"] for r in conf_records}:
        raise ValueError("TWO_SPLIT_FAMILY_OVERLAP")
    if bundle["bundle_sha256"] != bundle_identity(bundle):
        raise ValueError("TWO_SPLIT_BUNDLE_SHA")
    return True




def _open_parent_dir(path: Path) -> tuple[Path, int]:
    if path.name in {"", ".", ".."}:
        raise ValueError("DURABLE_FILE_NAME")
    try:
        parent = path.parent.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("DURABLE_PARENT_DIRECTORY_MUST_PREEXIST") from exc
    if not parent.is_dir():
        raise ValueError("DURABLE_PARENT_DIRECTORY_MUST_PREEXIST")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(parent, flags)
    except OSError as exc:
        raise ValueError("DURABLE_PARENT_DIRECTORY_OPEN_FAILED") from exc
    return parent, fd


def _read_regular_file_at(dir_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError("DURABLE_FILE_READ_FAILED") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ValueError("DURABLE_PATH_NOT_SINGLE_REGULAR_FILE")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _create_regular_file_once_durable(path: Path | str, raw: bytes, exists_error: str) -> str:
    p = Path(path)
    _, dir_fd = _open_parent_dir(p)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        try:
            fd = os.open(p.name, flags, 0o600, dir_fd=dir_fd)
        except FileExistsError as exc:
            raise ValueError(exists_error) from exc
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ValueError("DURABLE_CREATED_PATH_NOT_SINGLE_REGULAR_FILE")
        view = memoryview(raw)
        written = 0
        while written < len(view):
            n = os.write(fd, view[written:])
            if n <= 0:
                raise OSError("short durable write")
            written += n
        os.fsync(fd)
        # Creation is not authoritative until the directory entry is durable.
        os.fsync(dir_fd)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(dir_fd)
    # Deliberately never unlink on error. Ambiguous/partial state is recovered
    # by exact validation or fails closed; it is never replaced with fresh RNG.
    return _sha_bytes(raw)


def _durable_binding(
    development_source_sha256: str, development_generator_manifest_sha256: str,
    confirmation_source_sha256: str, confirmation_generator_manifest_sha256: str,
    generator_code_sha256: str,
) -> dict[str, str]:
    vals = {
        "development_source_snapshot_sha256": development_source_sha256,
        "development_generator_manifest_sha256": development_generator_manifest_sha256,
        "confirmation_source_snapshot_sha256": confirmation_source_sha256,
        "confirmation_generator_manifest_sha256": confirmation_generator_manifest_sha256,
        "generator_code_sha256": generator_code_sha256,
    }
    if any(not _is_sha(v) for v in vals.values()):
        raise ValueError("DURABLE_TRANSACTION_BINDING_SHA")
    return vals


def _transaction_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    x = copy.deepcopy(dict(record))
    x.pop("transaction_sha256", None)
    return x


def transaction_identity(record: Mapping[str, Any]) -> str:
    return _canon_sha(_transaction_payload(record))


def _build_transaction_record(binding: Mapping[str, str], transaction_nonce: bytes) -> dict[str, Any]:
    if not isinstance(transaction_nonce, bytes) or len(transaction_nonce) != TRANSACTION_NONCE_BYTES:
        raise ValueError("TRANSACTION_NONCE_EXACT_32_BYTES")
    record = {
        "schema": DURABLE_TRANSACTION_SCHEMA,
        "phase": "PRE_SCIENCE",
        "scientific_result": "NOT_ASSESSED",
        "assignment_randomness_source": "OS_CSPRNG_16BIT_WORDS_DURABLY_JOURNALED_BEFORE_USE",
        "transaction_nonce_hex": transaction_nonce.hex(),
        "transaction_nonce_role": "DURABLE_IDENTITY_ONLY_NOT_ASSIGNMENT_RANDOMNESS",
        "binding": dict(binding),
        "created_before_any_assignment_draw_use": True,
        "no_reseed_or_redraw": True,
    }
    record["transaction_sha256"] = transaction_identity(record)
    validate_transaction_record(record, binding)
    return record


def build_transaction_record_test_only(binding: Mapping[str, str], transaction_nonce: bytes) -> dict[str, Any]:
    """Explicit test-only deterministic transaction identity constructor."""
    return _build_transaction_record(binding, transaction_nonce)


def validate_transaction_record(record: Mapping[str, Any], expected_binding: Mapping[str, str]) -> bool:
    required = {
        "schema", "phase", "scientific_result", "assignment_randomness_source",
        "transaction_nonce_hex", "transaction_nonce_role", "binding",
        "created_before_any_assignment_draw_use", "no_reseed_or_redraw", "transaction_sha256",
    }
    if not isinstance(record, Mapping) or set(record) != required:
        raise ValueError("DURABLE_TRANSACTION_SCHEMA")
    if record["schema"] != DURABLE_TRANSACTION_SCHEMA or record["phase"] != "PRE_SCIENCE" or record["scientific_result"] != "NOT_ASSESSED":
        raise ValueError("DURABLE_TRANSACTION_SCOPE")
    if record["assignment_randomness_source"] != "OS_CSPRNG_16BIT_WORDS_DURABLY_JOURNALED_BEFORE_USE":
        raise ValueError("DURABLE_TRANSACTION_RNG_SOURCE")
    if record["transaction_nonce_role"] != "DURABLE_IDENTITY_ONLY_NOT_ASSIGNMENT_RANDOMNESS":
        raise ValueError("DURABLE_TRANSACTION_NONCE_ROLE")
    if record["binding"] != dict(expected_binding):
        raise ValueError("DURABLE_TRANSACTION_BINDING")
    h = record["transaction_nonce_hex"]
    if not isinstance(h, str) or len(h) != 2 * TRANSACTION_NONCE_BYTES:
        raise ValueError("DURABLE_TRANSACTION_NONCE")
    try:
        nonce = bytes.fromhex(h)
    except ValueError as exc:
        raise ValueError("DURABLE_TRANSACTION_NONCE") from exc
    if len(nonce) != TRANSACTION_NONCE_BYTES:
        raise ValueError("DURABLE_TRANSACTION_NONCE")
    if record["created_before_any_assignment_draw_use"] is not True or record["no_reseed_or_redraw"] is not True:
        raise ValueError("DURABLE_TRANSACTION_TIMING")
    if record["transaction_sha256"] != transaction_identity(record):
        raise ValueError("DURABLE_TRANSACTION_SHA")
    return True


def _load_canonical_json_regular(path: Path | str, corrupt_error: str) -> dict[str, Any]:
    p = Path(path)
    _, dir_fd = _open_parent_dir(p)
    try:
        raw = _read_regular_file_at(dir_fd, p.name)
    except FileNotFoundError:
        raise
    finally:
        os.close(dir_fd)
    try:
        obj = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(corrupt_error) from exc
    if not isinstance(obj, dict) or raw != _canonical_bytes(obj) + b"\
":
        raise ValueError(corrupt_error)
    return obj


def load_durable_transaction(path: Path | str, expected_binding: Mapping[str, str]) -> dict[str, Any]:
    try:
        record = _load_canonical_json_regular(path, "DURABLE_TRANSACTION_CORRUPT_FAIL_CLOSED")
    except FileNotFoundError as exc:
        raise ValueError("DURABLE_TRANSACTION_MISSING") from exc
    validate_transaction_record(record, expected_binding)
    return record


def _ensure_durable_transaction_with_nonce_supplier(
    path: Path | str, binding: Mapping[str, str], nonce_supplier: Callable[[], bytes],
) -> dict[str, Any]:
    p = Path(path)
    try:
        return load_durable_transaction(p, binding)
    except ValueError as exc:
        if str(exc) != "DURABLE_TRANSACTION_MISSING":
            raise
    nonce = nonce_supplier()
    record = _build_transaction_record(binding, nonce)
    raw = _canonical_bytes(record) + b"\
"
    try:
        _create_regular_file_once_durable(p, raw, "DURABLE_TRANSACTION_ALREADY_EXISTS")
        return record
    except ValueError as exc:
        if str(exc) != "DURABLE_TRANSACTION_ALREADY_EXISTS":
            raise
        return load_durable_transaction(p, binding)


def ensure_durable_transaction(path: Path | str, binding: Mapping[str, str]) -> dict[str, Any]:
    """Production transaction creation; accepts no caller RNG/seed injection."""
    return _ensure_durable_transaction_with_nonce_supplier(path, binding, lambda: os.urandom(TRANSACTION_NONCE_BYTES))


def ensure_durable_transaction_test_only(
    path: Path | str, binding: Mapping[str, str], transaction_nonce: bytes,
) -> dict[str, Any]:
    """Explicit deterministic test helper; transaction nonce is identity only."""
    return _ensure_durable_transaction_with_nonce_supplier(path, binding, lambda: transaction_nonce)


def _draw_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    x = copy.deepcopy(dict(record))
    x.pop("draw_record_sha256", None)
    return x


def draw_record_identity(record: Mapping[str, Any]) -> str:
    return _canon_sha(_draw_payload(record))


def _draw_path(transaction_path: Path | str, transaction: Mapping[str, Any], split_namespace: str, family_id: str, draw_counter: int) -> Path:
    if split_namespace == DEVELOPMENT_NAMESPACE:
        split_tag = "dev"
    elif split_namespace == CONFIRMATION_NAMESPACE:
        split_tag = "conf"
    else:
        raise ValueError("DURABLE_DRAW_NAMESPACE")
    if not _is_sha(family_id) or type(draw_counter) is not int or draw_counter < 0:
        raise ValueError("DURABLE_DRAW_IDENTITY")
    txid = transaction.get("transaction_sha256")
    if not _is_sha(txid):
        raise ValueError("DURABLE_DRAW_TRANSACTION_ID")
    name = f".cpdsdraw-{txid}-{split_tag}-{family_id}-{draw_counter:08d}.json"
    if len(name.encode()) > 240:
        raise ValueError("DURABLE_DRAW_FILENAME_TOO_LONG")
    return Path(transaction_path).parent / name


def _build_draw_record(transaction: Mapping[str, Any], split_namespace: str, family_id: str, draw_counter: int, word_u16: int) -> dict[str, Any]:
    if type(word_u16) is not int or not 0 <= word_u16 < WORD_SPACE:
        raise ValueError("RNG_WORD_U16")
    record = {
        "schema": DURABLE_DRAW_RECORD_SCHEMA,
        "phase": "PRE_SCIENCE",
        "scientific_result": "NOT_ASSESSED",
        "transaction_sha256": transaction["transaction_sha256"],
        "split_namespace": split_namespace,
        "family_id": family_id,
        "draw_counter": draw_counter,
        "word_u16": word_u16,
        "rng_source": "OS_CSPRNG_16BIT_WORDS",
        "durably_persisted_before_threshold_or_acceptance_use": True,
    }
    record["draw_record_sha256"] = draw_record_identity(record)
    validate_draw_record(record, transaction, split_namespace, family_id, draw_counter)
    return record


def build_draw_record_test_only(transaction: Mapping[str, Any], split_namespace: str, family_id: str, draw_counter: int, word_u16: int) -> dict[str, Any]:
    return _build_draw_record(transaction, split_namespace, family_id, draw_counter, word_u16)


def validate_draw_record(record: Mapping[str, Any], transaction: Mapping[str, Any], split_namespace: str, family_id: str, draw_counter: int) -> bool:
    required = {
        "schema", "phase", "scientific_result", "transaction_sha256", "split_namespace",
        "family_id", "draw_counter", "word_u16", "rng_source",
        "durably_persisted_before_threshold_or_acceptance_use", "draw_record_sha256",
    }
    if not isinstance(record, Mapping) or set(record) != required:
        raise ValueError("DURABLE_DRAW_RECORD_SCHEMA")
    if record["schema"] != DURABLE_DRAW_RECORD_SCHEMA or record["phase"] != "PRE_SCIENCE" or record["scientific_result"] != "NOT_ASSESSED":
        raise ValueError("DURABLE_DRAW_SCOPE")
    if record["transaction_sha256"] != transaction["transaction_sha256"] or record["split_namespace"] != split_namespace or record["family_id"] != family_id or record["draw_counter"] != draw_counter:
        raise ValueError("DURABLE_DRAW_BINDING")
    if type(record["word_u16"]) is not int or not 0 <= record["word_u16"] < WORD_SPACE:
        raise ValueError("DURABLE_DRAW_WORD")
    if record["rng_source"] != "OS_CSPRNG_16BIT_WORDS" or record["durably_persisted_before_threshold_or_acceptance_use"] is not True:
        raise ValueError("DURABLE_DRAW_RNG_AUTHORITY")
    if record["draw_record_sha256"] != draw_record_identity(record):
        raise ValueError("DURABLE_DRAW_SHA")
    return True


def _load_durable_draw(path: Path, transaction: Mapping[str, Any], split_namespace: str, family_id: str, draw_counter: int) -> dict[str, Any]:
    try:
        record = _load_canonical_json_regular(path, "DURABLE_DRAW_CORRUPT_FAIL_CLOSED")
    except FileNotFoundError:
        raise
    validate_draw_record(record, transaction, split_namespace, family_id, draw_counter)
    return record


def _get_or_create_durable_draw(
    transaction_path: Path | str, transaction: Mapping[str, Any], split_namespace: str, family_id: str,
    draw_counter: int, word_supplier: Callable[[], int],
) -> int:
    path = _draw_path(transaction_path, transaction, split_namespace, family_id, draw_counter)
    try:
        return _load_durable_draw(path, transaction, split_namespace, family_id, draw_counter)["word_u16"]
    except FileNotFoundError:
        pass
    word = word_supplier()
    record = _build_draw_record(transaction, split_namespace, family_id, draw_counter, word)
    raw = _canonical_bytes(record) + b"\
"
    try:
        _create_regular_file_once_durable(path, raw, "DURABLE_DRAW_ALREADY_EXISTS")
        # Word may be tested/accepted only after file+directory fsync returned.
        return word
    except ValueError as exc:
        if str(exc) != "DURABLE_DRAW_ALREADY_EXISTS":
            raise
        return _load_durable_draw(path, transaction, split_namespace, family_id, draw_counter)["word_u16"]


def durable_os_u16_words(
    transaction_path: Path | str, transaction: Mapping[str, Any], split_namespace: str, family_id: str,
) -> Iterator[int]:
    """Production literal V3 OS-CSPRNG stream, write-ahead journaled per raw u16."""
    counter = 0
    while True:
        yield _get_or_create_durable_draw(
            transaction_path, transaction, split_namespace, family_id, counter,
            lambda: int.from_bytes(os.urandom(2), "big", signed=False),
        )
        counter += 1


def durable_u16_words_test_only(
    transaction_path: Path | str, transaction: Mapping[str, Any], split_namespace: str, family_id: str, words: Iterable[int],
) -> Iterator[int]:
    """Explicit deterministic test helper. Existing journal words always win on restart."""
    source = iter(words)
    counter = 0
    while True:
        def supply() -> int:
            try:
                return next(source)
            except StopIteration as exc:
                raise ValueError("TEST_DURABLE_WORD_STREAM_EXHAUSTED") from exc
        yield _get_or_create_durable_draw(transaction_path, transaction, split_namespace, family_id, counter, supply)
        counter += 1


def _durable_word_factory(transaction_path: Path | str, transaction: Mapping[str, Any], split_namespace: str) -> Callable[[str], Iterable[int]]:
    return lambda family_id: durable_os_u16_words(transaction_path, transaction, split_namespace, family_id)


def _durable_test_word_factory(
    transaction_path: Path | str, transaction: Mapping[str, Any], split_namespace: str, test_factory: Callable[[str], Iterable[int]],
) -> Callable[[str], Iterable[int]]:
    return lambda family_id: durable_u16_words_test_only(transaction_path, transaction, split_namespace, family_id, test_factory(family_id))


def _load_existing_bundle(path: Path | str) -> tuple[dict[str, Any], str]:
    try:
        bundle = _load_canonical_json_regular(path, "DURABLE_EXISTING_BUNDLE_CORRUPT_FAIL_CLOSED")
    except FileNotFoundError as exc:
        raise ValueError("DURABLE_BUNDLE_MISSING") from exc
    raw = _canonical_bytes(bundle) + b"\
"
    return bundle, _sha_bytes(raw)


def _journal_expected_names(transaction_path: Path | str, transaction: Mapping[str, Any], bundle: Mapping[str, Any]) -> set[str]:
    expected: set[str] = set()
    for manifest in (bundle["development_assignment_manifest"], bundle["confirmation_assignment_manifest"]):
        namespace = manifest["split_namespace"]
        for record in manifest["records"]:
            for counter, word in enumerate(record["draw_words_u16_in_order"]):
                path = _draw_path(transaction_path, transaction, namespace, record["family_id"], counter)
                try:
                    draw = _load_durable_draw(path, transaction, namespace, record["family_id"], counter)
                except FileNotFoundError as exc:
                    raise ValueError("DURABLE_JOURNAL_MISSING_FAIL_CLOSED") from exc
                if draw["word_u16"] != word:
                    raise ValueError("DURABLE_JOURNAL_WORD_MISMATCH")
                expected.add(path.name)
            next_path = _draw_path(transaction_path, transaction, namespace, record["family_id"], len(record["draw_words_u16_in_order"]))
            if next_path.exists():
                raise ValueError("DURABLE_JOURNAL_REDRAW_AFTER_ACCEPTANCE")
    return expected


def validate_draw_journal_against_bundle(transaction_path: Path | str, transaction: Mapping[str, Any], bundle: Mapping[str, Any]) -> bool:
    expected = _journal_expected_names(transaction_path, transaction, bundle)
    parent = Path(transaction_path).parent
    prefix = f".cpdsdraw-{transaction['transaction_sha256']}-"
    found = {x.name for x in parent.iterdir() if x.name.startswith(prefix) and x.name.endswith(".json")}
    if found != expected:
        raise ValueError("DURABLE_JOURNAL_FILE_SET_MISMATCH")
    return True


def write_bundle_once(path: Path | str, bundle: Mapping[str, Any]) -> str:
    """Create-once finalization with file fsync + parent-directory fsync; never unlinks on error."""
    raw = _canonical_bytes(bundle) + b"\
"
    return _create_regular_file_once_durable(path, raw, "ASSIGNMENT_BUNDLE_ALREADY_EXISTS_NO_REDRAW")


def _validate_durable_split_inputs(
    development_snapshot: Mapping[str, Any], development_source_sha256: str,
    development_generator_manifest: Mapping[str, Any], development_generator_manifest_sha256: str,
    confirmation_snapshot: Mapping[str, Any], confirmation_source_sha256: str,
    confirmation_generator_manifest: Mapping[str, Any], confirmation_generator_manifest_sha256: str,
) -> None:
    gf.validate_confirmation_disjointness(
        development_generator_manifest, confirmation_generator_manifest,
        development_snapshot, confirmation_snapshot,
        development_source_sha256, confirmation_source_sha256,
        development_generator_manifest_sha256, confirmation_generator_manifest_sha256,
    )
    if development_generator_manifest["cohort_namespace"] != DEVELOPMENT_NAMESPACE or confirmation_generator_manifest["cohort_namespace"] != CONFIRMATION_NAMESPACE:
        raise ValueError("EXACT_SPLIT_NAMESPACE")
    if len(development_generator_manifest["certificates"]) != FAMILY_COUNT or len(confirmation_generator_manifest["certificates"]) != FAMILY_COUNT:
        raise ValueError("EXACT_33_BOTH_SPLITS")


def _freeze_two_split_bundle_durable_impl(
    transaction_path: Path | str, bundle_path: Path | str,
    development_snapshot: Mapping[str, Any], development_source_sha256: str,
    development_generator_manifest: Mapping[str, Any], development_generator_manifest_sha256: str,
    confirmation_snapshot: Mapping[str, Any], confirmation_source_sha256: str,
    confirmation_generator_manifest: Mapping[str, Any], confirmation_generator_manifest_sha256: str,
    *, development_arm_outcomes_opened: bool, generator_code_sha256: str | None,
    transaction_nonce_supplier: Callable[[], bytes],
    development_test_word_source_factory: Callable[[str], Iterable[int]] | None = None,
    confirmation_test_word_source_factory: Callable[[str], Iterable[int]] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if development_arm_outcomes_opened is not False:
        raise ValueError("DEVELOPMENT_OUTCOME_ALREADY_OPEN")
    txp, bp = Path(transaction_path), Path(bundle_path)
    tx_parent, tx_dir_fd = _open_parent_dir(txp)
    os.close(tx_dir_fd)
    bp_parent, bp_dir_fd = _open_parent_dir(bp)
    os.close(bp_dir_fd)
    if txp.name == bp.name or tx_parent != bp_parent:
        raise ValueError("DURABLE_TRANSACTION_AND_BUNDLE_REQUIRE_SAME_PREEXISTING_DIRECTORY")
    _validate_durable_split_inputs(
        development_snapshot, development_source_sha256, development_generator_manifest, development_generator_manifest_sha256,
        confirmation_snapshot, confirmation_source_sha256, confirmation_generator_manifest, confirmation_generator_manifest_sha256,
    )
    code_sha = generator_code_sha256 or _sha_file(Path(__file__))
    binding = _durable_binding(
        development_source_sha256, development_generator_manifest_sha256,
        confirmation_source_sha256, confirmation_generator_manifest_sha256, code_sha,
    )
    tx = _ensure_durable_transaction_with_nonce_supplier(txp, binding, transaction_nonce_supplier)

    # If a final bundle exists, it is authoritative only if its entire raw-word
    # journal is already present and matches. Never generate replacement draws.
    if bp.exists():
        existing, sha = _load_existing_bundle(bp)
        validate_two_split_bundle(
            existing, development_snapshot, development_generator_manifest, development_generator_manifest_sha256,
            confirmation_snapshot, confirmation_generator_manifest, confirmation_generator_manifest_sha256, code_sha,
        )
        validate_draw_journal_against_bundle(txp, tx, existing)
        return existing, sha, tx

    if development_test_word_source_factory is None:
        dev_factory = _durable_word_factory(txp, tx, DEVELOPMENT_NAMESPACE)
        conf_factory = _durable_word_factory(txp, tx, CONFIRMATION_NAMESPACE)
    else:
        if confirmation_test_word_source_factory is None:
            raise ValueError("TEST_DURABLE_BOTH_WORD_FACTORIES_REQUIRED")
        dev_factory = _durable_test_word_factory(txp, tx, DEVELOPMENT_NAMESPACE, development_test_word_source_factory)
        conf_factory = _durable_test_word_factory(txp, tx, CONFIRMATION_NAMESPACE, confirmation_test_word_source_factory)

    bundle = _freeze_two_split_bundle_from_word_sources(
        development_snapshot, development_source_sha256, development_generator_manifest, development_generator_manifest_sha256,
        confirmation_snapshot, confirmation_source_sha256, confirmation_generator_manifest, confirmation_generator_manifest_sha256,
        dev_factory, conf_factory, development_arm_outcomes_opened=False, existing_bundle=None, generator_code_sha256=code_sha,
    )
    validate_draw_journal_against_bundle(txp, tx, bundle)
    try:
        sha = write_bundle_once(bp, bundle)
    except ValueError as exc:
        if str(exc) != "ASSIGNMENT_BUNDLE_ALREADY_EXISTS_NO_REDRAW":
            raise
        existing, sha = _load_existing_bundle(bp)
        if existing != bundle:
            raise ValueError("DURABLE_CONCURRENT_BUNDLE_MISMATCH_FAIL_CLOSED")
        validate_draw_journal_against_bundle(txp, tx, existing)
        bundle = existing
    # Read back exact canonical bytes after durable finalization.
    final, final_sha = _load_existing_bundle(bp)
    if final != bundle or final_sha != sha:
        raise ValueError("DURABLE_FINAL_BUNDLE_READBACK_MISMATCH")
    return final, final_sha, tx


def freeze_two_split_bundle_durable(
    transaction_path: Path | str, bundle_path: Path | str,
    development_snapshot: Mapping[str, Any], development_source_sha256: str,
    development_generator_manifest: Mapping[str, Any], development_generator_manifest_sha256: str,
    confirmation_snapshot: Mapping[str, Any], confirmation_source_sha256: str,
    confirmation_generator_manifest: Mapping[str, Any], confirmation_generator_manifest_sha256: str,
    *, development_arm_outcomes_opened: bool,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Production crash-durable freeze. No RNG/seed/word/code-SHA injection surface exists."""
    return _freeze_two_split_bundle_durable_impl(
        transaction_path, bundle_path,
        development_snapshot, development_source_sha256, development_generator_manifest, development_generator_manifest_sha256,
        confirmation_snapshot, confirmation_source_sha256, confirmation_generator_manifest, confirmation_generator_manifest_sha256,
        development_arm_outcomes_opened=development_arm_outcomes_opened, generator_code_sha256=_sha_file(Path(__file__)),
        transaction_nonce_supplier=lambda: os.urandom(TRANSACTION_NONCE_BYTES),
    )


def freeze_two_split_bundle_durable_test_only(
    transaction_path: Path | str, bundle_path: Path | str,
    development_snapshot: Mapping[str, Any], development_source_sha256: str,
    development_generator_manifest: Mapping[str, Any], development_generator_manifest_sha256: str,
    confirmation_snapshot: Mapping[str, Any], confirmation_source_sha256: str,
    confirmation_generator_manifest: Mapping[str, Any], confirmation_generator_manifest_sha256: str,
    development_test_word_source_factory: Callable[[str], Iterable[int]],
    confirmation_test_word_source_factory: Callable[[str], Iterable[int]],
    *, development_arm_outcomes_opened: bool, test_transaction_nonce: bytes,
    generator_code_sha256: str | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Explicit deterministic crash/adversarial test surface; never production authority."""
    return _freeze_two_split_bundle_durable_impl(
        transaction_path, bundle_path,
        development_snapshot, development_source_sha256, development_generator_manifest, development_generator_manifest_sha256,
        confirmation_snapshot, confirmation_source_sha256, confirmation_generator_manifest, confirmation_generator_manifest_sha256,
        development_arm_outcomes_opened=development_arm_outcomes_opened, generator_code_sha256=generator_code_sha256,
        transaction_nonce_supplier=lambda: test_transaction_nonce,
        development_test_word_source_factory=development_test_word_source_factory,
        confirmation_test_word_source_factory=confirmation_test_word_source_factory,
    )


def validate_candidate_actions(actions: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(actions, Sequence) or isinstance(actions, (str, bytes)):
        raise ValueError("CANDIDATE_SET_SCHEMA")
    out = tuple(actions)
    if not out or len(out) != len(set(out)) or any(not isinstance(a, str) or not a for a in out):
        raise ValueError("CANDIDATE_SET_INVALID")
    return out


def validate_g_score_output(base_actions: Sequence[str], adjusted_rows: Sequence[Mapping[str, Any]]) -> bool:
    base = validate_candidate_actions(base_actions)
    if not isinstance(adjusted_rows, Sequence) or isinstance(adjusted_rows, (str, bytes)) or len(adjusted_rows) != len(base):
        raise ValueError("G_OUTPUT_SCHEMA")
    got: list[str] = []
    for row in adjusted_rows:
        if not isinstance(row, Mapping) or set(row) != {"action", "adjusted_whole_action_logscore"}:
            raise ValueError("G_OUTPUT_ROW_SCHEMA")
        if not isinstance(row["action"], str) or type(row["adjusted_whole_action_logscore"]) not in (int, float) or not math.isfinite(float(row["adjusted_whole_action_logscore"])):
            raise ValueError("G_OUTPUT_ROW_VALUE")
        got.append(row["action"])
    if tuple(got) != base:
        raise ValueError("G_CANDIDATE_SET_MUTATION")
    return True


def _runtime_slot_semantics(arm_id: str) -> dict[str, Any]:
    if arm_id == "NO_CARRY":
        return {"exposed_state_source": "NO_CPDS_STATE", "recurrent_update": "NONE", "transition_transform": "NONE", "scratch_only": False}
    if arm_id == "STATIC_ONESHOT":
        return {"exposed_state_source": "SEALED_Z0_ONESHOT", "recurrent_update": "NONE", "transition_transform": "NONE", "scratch_only": False}
    if arm_id == "STATIC_REPEAT":
        return {"exposed_state_source": "BYTE_OR_NUMERIC_IDENTICAL_SEALED_Z0", "recurrent_update": "CPDS_NATIVE2048_UNIT_SUM_RECURRENCE_V1", "transition_transform": "IDENTITY_AUTHENTICATED_OBSERVED_SCRATCH", "scratch_only": True}
    if arm_id == "ALIGNED_RECURSION":
        return {"exposed_state_source": "CAUSAL_ORDERED_RECURRENT_STATE", "recurrent_update": "CPDS_NATIVE2048_UNIT_SUM_RECURRENCE_V1", "transition_transform": "IDENTITY_AUTHENTICATED_OBSERVED", "scratch_only": False}
    if arm_id == "TRANSITION_PERMUTED":
        return {"exposed_state_source": "PERMUTED_RECURRENT_STATE", "recurrent_update": "CPDS_NATIVE2048_UNIT_SUM_RECURRENCE_V1", "transition_transform": "DETERMINISTIC_NONIDENTITY_ALREADY_OBSERVED_ORDER_ONLY", "scratch_only": False}
    if arm_id == "MATCHED_INFORMATION":
        return {"exposed_state_source": "CONTROL_SCRAMBLED_RECURRENT_STATE", "recurrent_update": "CPDS_NATIVE2048_UNIT_SUM_RECURRENCE_V1", "transition_transform": "FIXED_SIGNED_CYCLIC_P", "scratch_only": False}
    raise ValueError("UNKNOWN_ARM")


def runtime_plan_identity(plan: Mapping[str, Any]) -> str:
    return _canon_sha(dict(plan))


def build_family_runtime_plan(
    packet_authority: Mapping[str, Any], assignment_record: Mapping[str, Any], base_candidate_actions: Sequence[str],
    expected_assignment_generator_code_sha256: str | None = None,
) -> dict[str, Any]:
    required_authority = {"packet", "snapshot", "source_seal", "manifest", "manifest_seal"}
    if not isinstance(packet_authority, Mapping) or set(packet_authority) != required_authority:
        raise ValueError("PACKET_AUTHORITY_SCHEMA")
    packet = packet_authority["packet"]
    gf.validate_constructibility_packet(packet, packet_authority["snapshot"], packet_authority["source_seal"], packet_authority["manifest"], packet_authority["manifest_seal"])
    certs = [c for c in packet_authority["manifest"]["certificates"] if c["family_id"] == packet["family_id"]]
    if len(certs) != 1:
        raise ValueError("RUNTIME_CERTIFICATE_LOOKUP")
    code_sha = expected_assignment_generator_code_sha256 or _sha_file(Path(__file__))
    validate_assignment_record(assignment_record, certs[0], packet_authority["manifest"]["cohort_namespace"], code_sha)
    actions = validate_candidate_actions(base_candidate_actions)
    recurrent_contract = rr.load_contract()
    rr.validate_contract(recurrent_contract)
    arm_map = {a["arm_id"]: a for a in packet["arms"]}
    if tuple(arm_map) != EXACT_ARMS:
        raise ValueError("RUNTIME_PACKET_ARM_ORDER")
    slots: list[dict[str, Any]] = []
    for slot_id, arm_id in zip(EXACT_SLOTS, assignment_record["arm_permutation"]):
        arm = arm_map[arm_id]
        sem = _runtime_slot_semantics(arm_id)
        scope = _canon_sha({"family_id": packet["family_id"], "slot_id": slot_id, "assignment": assignment_record_identity(assignment_record)})
        slots.append({
            "slot_id": slot_id,
            "arm_id": arm_id,
            "isolated_mutable_state_scope_id": scope,
            "sealed_checkpoint_packet_sha256": packet["packet_sha256"],
            "candidate_set_sha256": _canon_sha(list(actions)),
            "candidate_count": len(actions),
            "contract_state_policy": arm["state_policy"],
            "contract_update_operation": arm["update_operation"],
            "transition_order": list(arm["transition_order"]),
            "recurrent_state_id": recurrent_contract["recurrent_state"]["state_id"],
            "adapter_G_id": recurrent_contract["adapter_G"]["G_id"],
            "exposed_state_source": sem["exposed_state_source"],
            "recurrent_update": sem["recurrent_update"],
            "transition_transform": sem["transition_transform"],
            "scratch_only": sem["scratch_only"],
            "scratch_state_reaches_G": False,
            "scratch_state_reaches_endpoint": False,
            "cross_slot_mutable_inputs": [],
            "G_candidate_set_policy": "EXACT_BASE_POLICY_CANDIDATE_SET_NO_ADD_DELETE_FILTER_RELABEL",
            "G_can_execute_action": False,
            "G_can_force_single_action": False,
            "G_can_mutate_environment": False,
            "future_transition_preview_allowed": False,
        })
    plan = {
        "schema": RUNTIME_PLAN_SCHEMA,
        "phase": "PRE_SCIENCE_EXECUTION_PLAN_ONLY",
        "scientific_result": "NOT_ASSESSED",
        "family_id": packet["family_id"],
        "structural_family_key_sha256": packet["structural_family_key_sha256"],
        "source_snapshot_sha256": packet["source_snapshot_sha256"],
        "generator_manifest_sha256": packet["manifest_sha256"],
        "constructibility_packet_sha256": packet["packet_sha256"],
        "assignment_record_sha256": assignment_record_identity(assignment_record),
        "assignment_index": assignment_record["assignment_index"],
        "arm_permutation": list(assignment_record["arm_permutation"]),
        "endpoint": PRIMARY_ENDPOINT,
        "first_action_excluded": True,
        "candidate_set_sha256": _canon_sha(list(actions)),
        "candidate_count": len(actions),
        "slots": slots,
        "model_calls_performed": 0,
        "environment_execution_performed": 0,
        "arm_outcomes_opened": 0,
    }
    validate_family_runtime_plan(plan, packet_authority, assignment_record, actions, code_sha)
    return plan


def validate_family_runtime_plan(
    plan: Mapping[str, Any], packet_authority: Mapping[str, Any], assignment_record: Mapping[str, Any], base_candidate_actions: Sequence[str], expected_assignment_generator_code_sha256: str,
) -> bool:
    packet = packet_authority["packet"]
    gf.validate_constructibility_packet(packet, packet_authority["snapshot"], packet_authority["source_seal"], packet_authority["manifest"], packet_authority["manifest_seal"])
    certs = [c for c in packet_authority["manifest"]["certificates"] if c["family_id"] == packet["family_id"]]
    if len(certs) != 1:
        raise ValueError("RUNTIME_CERTIFICATE_LOOKUP")
    validate_assignment_record(assignment_record, certs[0], packet_authority["manifest"]["cohort_namespace"], expected_assignment_generator_code_sha256)
    actions = validate_candidate_actions(base_candidate_actions)
    required = {
        "schema", "phase", "scientific_result", "family_id", "structural_family_key_sha256",
        "source_snapshot_sha256", "generator_manifest_sha256", "constructibility_packet_sha256",
        "assignment_record_sha256", "assignment_index", "arm_permutation", "endpoint",
        "first_action_excluded", "candidate_set_sha256", "candidate_count", "slots",
        "model_calls_performed", "environment_execution_performed", "arm_outcomes_opened",
    }
    if not isinstance(plan, Mapping) or set(plan) != required:
        raise ValueError("RUNTIME_PLAN_SCHEMA")
    if plan["schema"] != RUNTIME_PLAN_SCHEMA or plan["phase"] != "PRE_SCIENCE_EXECUTION_PLAN_ONLY" or plan["scientific_result"] != "NOT_ASSESSED":
        raise ValueError("RUNTIME_PLAN_SCOPE")
    if any(plan[k] != 0 for k in ("model_calls_performed", "environment_execution_performed", "arm_outcomes_opened")):
        raise ValueError("RUNTIME_PLAN_OUTCOME_ACCESS")
    if plan["family_id"] != packet["family_id"] or plan["structural_family_key_sha256"] != packet["structural_family_key_sha256"]:
        raise ValueError("RUNTIME_PLAN_FAMILY_BINDING")
    if plan["source_snapshot_sha256"] != packet["source_snapshot_sha256"] or plan["generator_manifest_sha256"] != packet["manifest_sha256"] or plan["constructibility_packet_sha256"] != packet["packet_sha256"]:
        raise ValueError("RUNTIME_PLAN_PACKET_BINDING")
    if plan["assignment_record_sha256"] != assignment_record_identity(assignment_record) or plan["assignment_index"] != assignment_record["assignment_index"] or plan["arm_permutation"] != assignment_record["arm_permutation"]:
        raise ValueError("RUNTIME_PLAN_ASSIGNMENT_BINDING")
    if plan["endpoint"] != PRIMARY_ENDPOINT or plan["first_action_excluded"] is not True:
        raise ValueError("RUNTIME_PLAN_ENDPOINT")
    csha = _canon_sha(list(actions))
    if plan["candidate_set_sha256"] != csha or plan["candidate_count"] != len(actions):
        raise ValueError("RUNTIME_PLAN_CANDIDATE_BINDING")
    slots = plan["slots"]
    if not isinstance(slots, list) or len(slots) != 6 or [s.get("slot_id") for s in slots] != list(EXACT_SLOTS) or [s.get("arm_id") for s in slots] != assignment_record["arm_permutation"]:
        raise ValueError("RUNTIME_PLAN_SLOT_ASSIGNMENT")
    scopes = [s.get("isolated_mutable_state_scope_id") for s in slots]
    if len(scopes) != len(set(scopes)) or any(not _is_sha(s) for s in scopes):
        raise ValueError("RUNTIME_PLAN_SLOT_ISOLATION")
    amap = {a["arm_id"]: a for a in packet["arms"]}
    rr_contract = rr.load_contract()
    for slot in slots:
        arm_id = slot["arm_id"]
        arm = amap[arm_id]
        sem = _runtime_slot_semantics(arm_id)
        expected_keys = {
            "slot_id", "arm_id", "isolated_mutable_state_scope_id", "sealed_checkpoint_packet_sha256",
            "candidate_set_sha256", "candidate_count", "contract_state_policy", "contract_update_operation",
            "transition_order", "recurrent_state_id", "adapter_G_id", "exposed_state_source",
            "recurrent_update", "transition_transform", "scratch_only", "scratch_state_reaches_G",
            "scratch_state_reaches_endpoint", "cross_slot_mutable_inputs", "G_candidate_set_policy",
            "G_can_execute_action", "G_can_force_single_action", "G_can_mutate_environment",
            "future_transition_preview_allowed",
        }
        if set(slot) != expected_keys:
            raise ValueError("RUNTIME_SLOT_SCHEMA")
        if slot["sealed_checkpoint_packet_sha256"] != packet["packet_sha256"] or slot["candidate_set_sha256"] != csha or slot["candidate_count"] != len(actions):
            raise ValueError("RUNTIME_SLOT_INPUT_BINDING")
        if slot["contract_state_policy"] != arm["state_policy"] or slot["contract_update_operation"] != arm["update_operation"] or slot["transition_order"] != arm["transition_order"]:
            raise ValueError("RUNTIME_SLOT_ARM_BINDING")
        if slot["recurrent_state_id"] != rr_contract["recurrent_state"]["state_id"] or slot["adapter_G_id"] != rr_contract["adapter_G"]["G_id"]:
            raise ValueError("RUNTIME_SLOT_REALIZATION_BINDING")
        for key in ("exposed_state_source", "recurrent_update", "transition_transform", "scratch_only"):
            if slot[key] != sem[key]:
                raise ValueError("RUNTIME_SLOT_SEMANTICS:" + key)
        if slot["scratch_state_reaches_G"] is not False or slot["scratch_state_reaches_endpoint"] is not False or slot["cross_slot_mutable_inputs"] != []:
            raise ValueError("RUNTIME_SLOT_CARRYOVER")
        if slot["G_candidate_set_policy"] != "EXACT_BASE_POLICY_CANDIDATE_SET_NO_ADD_DELETE_FILTER_RELABEL":
            raise ValueError("RUNTIME_SLOT_CANDIDATE_POLICY")
        if any(slot[k] is not False for k in ("G_can_execute_action", "G_can_force_single_action", "G_can_mutate_environment", "future_transition_preview_allowed")):
            raise ValueError("RUNTIME_SLOT_FORBIDDEN_CAPABILITY")
        if arm_id == "STATIC_REPEAT" and slot["exposed_state_source"] != "BYTE_OR_NUMERIC_IDENTICAL_SEALED_Z0":
            raise ValueError("STATIC_REPEAT_EXPOSURE")
        if arm_id == "TRANSITION_PERMUTED":
            observed = [r["transition_key"] for r in packet["observed_transition_records"]]
            if sorted(slot["transition_order"]) != sorted(observed) or slot["transition_order"] == observed:
                raise ValueError("PERMUTED_ORDER_ONLY")
    return True


def validate_zero_tolerance_guard_counters(counters: Mapping[str, Any]) -> bool:
    if not isinstance(counters, Mapping) or set(counters) != set(ZERO_TOLERANCE_GUARDS):
        raise ValueError("ZERO_TOLERANCE_GUARD_SCHEMA")
    for key in ZERO_TOLERANCE_GUARDS:
        value = counters[key]
        if type(value) is not int or value != 0:
            raise ValueError("ZERO_TOLERANCE_GUARD_VIOLATION:" + key)
    return True


def static_preflight(repo_root: Path | str = ROOT) -> dict[str, Any]:
    validate_contract()
    authority = verify_external_authorities(repo_root)
    audit = json.loads(AUDIT_PATH.read_text())
    if audit["scientific_result"] != "NOT_ASSESSED" or not all(v == 0 for v in audit["prohibited_actions_observed"].values()):
        raise ValueError("READINESS_STATIC_AUDIT")
    return {
        "status": "PASS_PRE_SCIENCE_STATIC_READINESS",
        "scientific_result": "NOT_ASSESSED",
        "python_runtime": sys.version.split()[0],
        "authority_snapshot_sha256": _canon_sha(authority),
        "model_calls": 0,
        "environment_execution": 0,
        "gpu_provider_lifecycle": 0,
        "experiment_or_decision_actions": 0,
        "arm_outcomes_opened": 0,
        "future_split_access": 0,
    }


if __name__ == "__main__":
    print(json.dumps(static_preflight(), sort_keys=True))
