"""PRE-SCIENCE CPDS graph-fork constructibility implementation.

This module implements only the reviewed constructibility contract.  It does not
run a model/environment and cannot support or refute the CPDS mechanism.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from cpds_graphfork_contract_validator_v1 import (
    canonical_bytes,
    generate_certificates,
    sha256_bytes,
    structural_family_key,
    validate_disjoint,
    validate_generator_spec,
)

ROOT = Path(__file__).resolve().parent
DESIGN = ROOT / "results" / "design"
SPEC_PATH = DESIGN / "plancarry_cpds_graphfork_generator_spec_v1_20260829.json"
CONTRACT_PATH = DESIGN / "plancarry_cpds_graphfork_constructibility_contract_v1_20260829.json"
CASES_PATH = DESIGN / "plancarry_cpds_graphfork_adversarial_cases_v1_20260829.json"
STATIC_AUDIT_PATH = DESIGN / "plancarry_cpds_graphfork_constructibility_static_audit_v1_20260829.json"
VALIDATOR_PATH = ROOT / "cpds_graphfork_contract_validator_v1.py"
BASE_TEST_PATH = ROOT / "tests" / "test_cpds_graphfork_contract_validator_v1.py"

EXPECTED = {
    SPEC_PATH: "a5075c8285afee23d8c50237a7c9e87c0e97683cb8617a92306415e5f81df430",
    CONTRACT_PATH: "87bce823aea942250a906f189dee5fc72658681df961e7f984c5963924eca4f7",
    CASES_PATH: "dbe60905114a41c6a6c2b6a96d591ca7d844e29d6fb1db7a011b01b91748d9ba",
    STATIC_AUDIT_PATH: "30a075e366b910068e9c5af333a6f7d3182494bea6544ee13fe1202a2bd27ba9",
    VALIDATOR_PATH: "c3f6b9ee38fff7a984449e9608b925a0b9f6c7b1bbd268db9beba148b25cbd20",
    BASE_TEST_PATH: "3cfcc74671b98564c8c68ed131779a1288e9dc4bc8a91c1bcd88914aa04fa74e",
}
EXPECTED_GENERATOR_IDENTITY = "719385fb2afce7bf80dcf9a93da8e55e8c1303c38855db0bfa5965cbae59cc15"
DEVELOPMENT_NAMESPACE = "CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1"
MANIFEST_SCHEMA = "PLANCARRY_CPDS_GRAPHFORK_GENERATOR_RUN_MANIFEST_V2"
PACKET_SCHEMA = "CPDS_GRAPHFORK_CONSTRUCTIBILITY_PACKET_V2"
SUMMARY_SCHEMA = "CPDS_GRAPHFORK_CONSTRUCTIBILITY_SUMMARY_V2"
PRIMARY_ENDPOINT = "FIRST_ACTION_EXCLUDED_ROUTE_TOLERANT_FUTURE_BRANCH_LOGPROB_SHIFT_OVER_GRAPH_DEFINED_ACTION_EQUIVALENCE_CLASSES"
EXACT_ARM_IDS = (
    "NO_CARRY",
    "STATIC_ONESHOT",
    "STATIC_REPEAT",
    "ALIGNED_RECURSION",
    "TRANSITION_PERMUTED",
    "MATCHED_INFORMATION",
)
ALLOWED_CARRIER_PROVENANCE = {
    "MODEL_VISIBLE_PRE_RESET",
    "MODEL_OWN_PRE_RESET_PREDICTION",
    "CONTROL_RANDOMNESS_PRECOMMITTED",
    "RUNTIME_CAUSALLY_OBSERVED",
}
FORBIDDEN_PROVENANCE_MARKERS = {
    "EVALUATOR_SECRET",
    "OUTCOME_ONLY",
    "TEACHER_PLAN",
    "TEACHER",
    "FUTURE_ORACLE",
    "FUTURE_EXPERT",
    "FUTURE_SUCCESS",
    "REALIZED_FUTURE",
    "DIRECT_TARGET",
    "BRANCH_TARGET",
}
BASE_GEOMETRY_FIELDS = (
    "state_capacity_id",
    "representation_budget_id",
    "information_volume_id",
    "serialization_or_numeric_budget_id",
    "base_policy_id",
    "prompt_contract_id",
    "z0_identity_id",
    "F_callable_id",
    "F_parameters_id",
    "G_callable_id",
    "G_exposure_locations",
    "updater_invocation_sites",
    "runtime_call_geometry",
    "update_timing_budget",
    "carrier_provenance_sources",
    "oneshot_G_exposure_location",
    "G_can_execute_action",
    "G_can_force_single_action",
    "G_can_mutate_environment",
)
MATCHED_GEOMETRY_FIELDS = BASE_GEOMETRY_FIELDS


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon_sha(obj: Any) -> str:
    return sha256_bytes(canonical_bytes(obj))


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def verify_reviewed_authority() -> dict[str, str]:
    got: dict[str, str] = {}
    for path, expected in EXPECTED.items():
        actual = sha_file(path)
        got[str(path.relative_to(ROOT))] = actual
        if actual != expected:
            raise ValueError("REVIEWED_AUTHORITY_SHA:" + path.name)
    spec = _load_json(SPEC_PATH)
    validate_generator_spec(spec)
    if spec["generator_identity_sha256"] != EXPECTED_GENERATOR_IDENTITY:
        raise ValueError("GENERATOR_IDENTITY")
    contract = _load_json(CONTRACT_PATH)
    if set(contract["arms"]) != set(EXACT_ARM_IDS):
        raise ValueError("REVIEWED_ARM_SET")
    if contract["primary_probe"]["first_action_in_primary_endpoint"] is not False:
        raise ValueError("REVIEWED_ENDPOINT_FIRST_ACTION")
    if contract["primary_probe"]["primary_endpoint"] != PRIMARY_ENDPOINT:
        raise ValueError("REVIEWED_ENDPOINT_ID")
    return got


def _contains_forbidden_key(obj: Any, forbidden: set[str]) -> bool:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if key in forbidden or _contains_forbidden_key(value, forbidden):
                return True
    elif isinstance(obj, list):
        return any(_contains_forbidden_key(v, forbidden) for v in obj)
    return False


def source_snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(snapshot))
    payload.pop("snapshot_sha256", None)
    return payload


def source_snapshot_identity(snapshot: Mapping[str, Any]) -> str:
    return canon_sha(source_snapshot_payload(snapshot))


def seal_source_snapshot(snapshot_id: str, families: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("SNAPSHOT_ID")
    if not isinstance(families, Sequence) or isinstance(families, (str, bytes)):
        raise ValueError("SNAPSHOT_FAMILIES")
    snapshot = {"snapshot_id": snapshot_id, "families": [copy.deepcopy(dict(f)) for f in families]}
    snapshot["snapshot_sha256"] = source_snapshot_identity(snapshot)
    return snapshot


def _validate_source_schema(snapshot: Mapping[str, Any], expected_source_snapshot_sha256: str) -> list[dict[str, Any]]:
    verify_reviewed_authority()
    if not _is_sha(expected_source_snapshot_sha256):
        raise ValueError("EXTERNAL_SOURCE_SEAL_FORMAT")
    spec = _load_json(SPEC_PATH)
    validate_generator_spec(spec)
    required = set(spec["input_snapshot_schema"]["required_top_level"])
    if not isinstance(snapshot, Mapping) or set(snapshot) != required:
        raise ValueError("SOURCE_SNAPSHOT_SCHEMA")
    forbidden = set(spec["forbidden_input_fields"])
    if _contains_forbidden_key(snapshot, forbidden):
        raise ValueError("FORBIDDEN_SOURCE_FIELD")
    if not isinstance(snapshot["snapshot_id"], str) or not snapshot["snapshot_id"]:
        raise ValueError("SNAPSHOT_ID")
    if not isinstance(snapshot["families"], list):
        raise ValueError("FAMILIES_SCHEMA")
    actual = source_snapshot_identity(snapshot)
    if snapshot["snapshot_sha256"] != actual:
        raise ValueError("SOURCE_SNAPSHOT_SHA256_MISMATCH")
    if expected_source_snapshot_sha256 != actual:
        raise ValueError("EXTERNAL_SOURCE_SEAL_MISMATCH")
    # Schema/admission validation only.  Namespace value here is not authority.
    return generate_certificates(snapshot["families"], spec, "__SCHEMA_ONLY__", actual)


def validate_source_snapshot(snapshot: Mapping[str, Any], expected_source_snapshot_sha256: str) -> bool:
    _validate_source_schema(snapshot, expected_source_snapshot_sha256)
    return True


def _certificate_family_id(structural_key: str, namespace: str, source_sha: str) -> str:
    return canon_sha(
        {
            "generator_identity_sha256": EXPECTED_GENERATOR_IDENTITY,
            "cohort_namespace": namespace,
            "source_snapshot_sha256": source_sha,
            "structural_family_key_sha256": structural_key,
        }
    )


def certificate_identity(cert: Mapping[str, Any]) -> str:
    return canon_sha(dict(cert))


def manifest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(manifest))
    payload.pop("manifest_sha256", None)
    return payload


def manifest_identity(manifest: Mapping[str, Any]) -> str:
    return canon_sha(manifest_payload(manifest))


def build_generator_run_manifest(
    snapshot: Mapping[str, Any], cohort_namespace: str, expected_source_snapshot_sha256: str
) -> dict[str, Any]:
    authority = verify_reviewed_authority()
    _validate_source_schema(snapshot, expected_source_snapshot_sha256)
    if not isinstance(cohort_namespace, str) or not cohort_namespace:
        raise ValueError("COHORT_NAMESPACE")
    spec = _load_json(SPEC_PATH)
    certs = generate_certificates(snapshot["families"], spec, cohort_namespace, expected_source_snapshot_sha256)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "phase": "PRE_SCIENCE_CONSTRUCTIBILITY_ONLY",
        "scientific_result": "NOT_ASSESSED",
        "generator_identity_sha256": EXPECTED_GENERATOR_IDENTITY,
        "generator_spec_sha256": authority[str(SPEC_PATH.relative_to(ROOT))],
        "constructibility_contract_sha256": authority[str(CONTRACT_PATH.relative_to(ROOT))],
        "validator_sha256": authority[str(VALIDATOR_PATH.relative_to(ROOT))],
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_snapshot_sha256": expected_source_snapshot_sha256,
        "cohort_namespace": cohort_namespace,
        "selection_semantics": "ALL_ADMITTED_IN_STRUCTURAL_KEY_ORDER_NO_REPLACEMENT",
        "no_replacement": True,
        "certificate_count": len(certs),
        "structural_family_key_sha256s": [c["structural_family_key_sha256"] for c in certs],
        "family_ids": [c["family_id"] for c in certs],
        "certificate_sha256s": [certificate_identity(c) for c in certs],
        "certificates": certs,
    }
    manifest["manifest_sha256"] = manifest_identity(manifest)
    _validate_manifest_structure(manifest)
    return manifest


def _validate_manifest_structure(manifest: Mapping[str, Any]) -> bool:
    verify_reviewed_authority()
    required = {
        "schema", "phase", "scientific_result", "generator_identity_sha256",
        "generator_spec_sha256", "constructibility_contract_sha256", "validator_sha256",
        "source_snapshot_id", "source_snapshot_sha256", "cohort_namespace",
        "selection_semantics", "no_replacement", "certificate_count",
        "structural_family_key_sha256s", "family_ids", "certificate_sha256s",
        "certificates", "manifest_sha256",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != required:
        raise ValueError("MANIFEST_SCHEMA")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ValueError("MANIFEST_SCHEMA_ID")
    if manifest["phase"] != "PRE_SCIENCE_CONSTRUCTIBILITY_ONLY" or manifest["scientific_result"] != "NOT_ASSESSED":
        raise ValueError("SCIENCE_LABEL_FORBIDDEN")
    if manifest["generator_identity_sha256"] != EXPECTED_GENERATOR_IDENTITY:
        raise ValueError("MANIFEST_GENERATOR_IDENTITY")
    if manifest["generator_spec_sha256"] != EXPECTED[SPEC_PATH] or manifest["constructibility_contract_sha256"] != EXPECTED[CONTRACT_PATH] or manifest["validator_sha256"] != EXPECTED[VALIDATOR_PATH]:
        raise ValueError("MANIFEST_REVIEWED_AUTHORITY")
    if not isinstance(manifest["source_snapshot_id"], str) or not manifest["source_snapshot_id"]:
        raise ValueError("MANIFEST_SOURCE_ID")
    if not _is_sha(manifest["source_snapshot_sha256"]):
        raise ValueError("MANIFEST_SOURCE_SHA")
    if not isinstance(manifest["cohort_namespace"], str) or not manifest["cohort_namespace"]:
        raise ValueError("MANIFEST_NAMESPACE")
    if manifest["selection_semantics"] != "ALL_ADMITTED_IN_STRUCTURAL_KEY_ORDER_NO_REPLACEMENT" or manifest["no_replacement"] is not True:
        raise ValueError("MANIFEST_SELECTION_SEMANTICS")
    certs = manifest["certificates"]
    if not isinstance(certs, list):
        raise ValueError("MANIFEST_CERTIFICATES")
    expected_cert_fields = {"structural_family_key_sha256", "family_id", "cohort_namespace", "source_snapshot_sha256"}
    for cert in certs:
        if not isinstance(cert, dict) or set(cert) != expected_cert_fields:
            raise ValueError("CERTIFICATE_SCHEMA")
        if cert["cohort_namespace"] != manifest["cohort_namespace"] or cert["source_snapshot_sha256"] != manifest["source_snapshot_sha256"]:
            raise ValueError("CERTIFICATE_BINDING")
        expected_fid = _certificate_family_id(cert["structural_family_key_sha256"], manifest["cohort_namespace"], manifest["source_snapshot_sha256"])
        if cert["family_id"] != expected_fid:
            raise ValueError("FAMILY_ID_DERIVATION_MISMATCH")
    structural = [c["structural_family_key_sha256"] for c in certs]
    family_ids = [c["family_id"] for c in certs]
    cert_hashes = [certificate_identity(c) for c in certs]
    if structural != sorted(structural) or len(structural) != len(set(structural)) or len(family_ids) != len(set(family_ids)):
        raise ValueError("CERTIFICATE_ORDER_OR_DUPLICATE")
    if manifest["structural_family_key_sha256s"] != structural or manifest["family_ids"] != family_ids or manifest["certificate_sha256s"] != cert_hashes:
        raise ValueError("CERTIFICATE_LIST_BINDING")
    if type(manifest["certificate_count"]) is not int or manifest["certificate_count"] != len(certs):
        raise ValueError("CERTIFICATE_COUNT_MISMATCH")
    if manifest["manifest_sha256"] != manifest_identity(manifest):
        raise ValueError("MANIFEST_SHA256_MISMATCH")
    return True


def validate_generator_run_manifest(manifest: Mapping[str, Any], expected_manifest_sha256: str) -> bool:
    if not _is_sha(expected_manifest_sha256):
        raise ValueError("EXTERNAL_MANIFEST_SEAL_FORMAT")
    _validate_manifest_structure(manifest)
    actual = manifest_identity(manifest)
    if manifest["manifest_sha256"] != actual or expected_manifest_sha256 != actual:
        raise ValueError("EXTERNAL_MANIFEST_SEAL_MISMATCH")
    return True


def validate_manifest_against_source(
    manifest: Mapping[str, Any], expected_manifest_sha256: str,
    snapshot: Mapping[str, Any], expected_source_snapshot_sha256: str,
) -> bool:
    validate_generator_run_manifest(manifest, expected_manifest_sha256)
    _validate_source_schema(snapshot, expected_source_snapshot_sha256)
    if manifest["source_snapshot_id"] != snapshot["snapshot_id"] or manifest["source_snapshot_sha256"] != expected_source_snapshot_sha256:
        raise ValueError("MANIFEST_SOURCE_BINDING")
    spec = _load_json(SPEC_PATH)
    rebuilt = generate_certificates(snapshot["families"], spec, manifest["cohort_namespace"], expected_source_snapshot_sha256)
    if manifest["certificates"] != rebuilt:
        raise ValueError("CERTIFICATE_REBUILD_MISMATCH")
    if manifest["certificate_sha256s"] != [certificate_identity(c) for c in rebuilt]:
        raise ValueError("CERTIFICATE_HASH_REBUILD_MISMATCH")
    return True


def validate_confirmation_disjointness(
    development_manifest: Mapping[str, Any], confirmation_manifest: Mapping[str, Any],
    development_snapshot: Mapping[str, Any], confirmation_snapshot: Mapping[str, Any],
    expected_development_source_sha256: str, expected_confirmation_source_sha256: str,
    expected_development_manifest_sha256: str, expected_confirmation_manifest_sha256: str,
) -> bool:
    validate_manifest_against_source(development_manifest, expected_development_manifest_sha256, development_snapshot, expected_development_source_sha256)
    validate_manifest_against_source(confirmation_manifest, expected_confirmation_manifest_sha256, confirmation_snapshot, expected_confirmation_source_sha256)
    if development_manifest["cohort_namespace"] != DEVELOPMENT_NAMESPACE:
        raise ValueError("DEVELOPMENT_NAMESPACE_MISMATCH")
    if confirmation_manifest["cohort_namespace"] == DEVELOPMENT_NAMESPACE:
        raise ValueError("COHORT_NAMESPACE_NOT_INDEPENDENT")
    if development_manifest["source_snapshot_sha256"] == confirmation_manifest["source_snapshot_sha256"]:
        raise ValueError("SOURCE_SNAPSHOT_NOT_INDEPENDENT")
    if development_manifest["source_snapshot_id"] == confirmation_manifest["source_snapshot_id"]:
        raise ValueError("SOURCE_SNAPSHOT_ID_NOT_INDEPENDENT")
    validate_disjoint(development_manifest["certificates"], confirmation_manifest["certificates"])
    return True


def validate_geometry(geometry: Mapping[str, Any]) -> bool:
    if not isinstance(geometry, Mapping) or set(geometry) != set(BASE_GEOMETRY_FIELDS):
        raise ValueError("GEOMETRY_SCHEMA")
    scalar_fields = (
        "state_capacity_id", "representation_budget_id", "information_volume_id",
        "serialization_or_numeric_budget_id", "base_policy_id", "prompt_contract_id",
        "z0_identity_id", "F_callable_id", "F_parameters_id", "G_callable_id",
        "update_timing_budget", "oneshot_G_exposure_location",
    )
    for key in scalar_fields:
        if not isinstance(geometry[key], str) or not geometry[key]:
            raise ValueError("GEOMETRY_" + key)
    for key in ("G_exposure_locations", "updater_invocation_sites", "runtime_call_geometry", "carrier_provenance_sources"):
        value = geometry[key]
        if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
            raise ValueError("GEOMETRY_" + key)
        # These lists identify distinct locations, sites, or provenance sources.
        # Repeating an identifier adds no permitted geometry and must fail closed.
        if key != "runtime_call_geometry" and len(set(value)) != len(value):
            raise ValueError("GEOMETRY_DUPLICATE_" + key)
    # Runtime geometry is an ordered event sequence, so non-adjacent event names
    # legitimately recur (for example G_EXPOSURE / UPDATE_SLOT alternation).  A
    # repeated adjacent event is instead a duplicated call slot and is rejected.
    runtime = geometry["runtime_call_geometry"]
    if any(left == right for left, right in zip(runtime, runtime[1:])):
        raise ValueError("GEOMETRY_DUPLICATE_runtime_call_geometry")
    if geometry["oneshot_G_exposure_location"] not in geometry["G_exposure_locations"]:
        raise ValueError("ONESHOT_EXPOSURE_NOT_CONTRACTED")
    if any(bool(geometry[k]) for k in ("G_can_execute_action", "G_can_force_single_action", "G_can_mutate_environment")):
        raise ValueError("G_NONEXECUTING_BOUNDARY")
    sources = set(geometry["carrier_provenance_sources"])
    if not sources <= ALLOWED_CARRIER_PROVENANCE:
        raise ValueError("CARRIER_PROVENANCE_NOT_ALLOWED")
    upper = {s.upper() for s in sources}
    if upper & FORBIDDEN_PROVENANCE_MARKERS:
        raise ValueError("CARRIER_PROVENANCE_LEAK")
    return True


def _family_and_certificate(
    snapshot: Mapping[str, Any], source_seal: str,
    manifest: Mapping[str, Any], manifest_seal: str, family_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_manifest_against_source(manifest, manifest_seal, snapshot, source_seal)
    certs = [c for c in manifest["certificates"] if c["family_id"] == family_id]
    if len(certs) != 1:
        raise ValueError("FAMILY_CERTIFICATE_LOOKUP")
    cert = certs[0]
    families = [f for f in snapshot["families"] if structural_family_key(f) == cert["structural_family_key_sha256"]]
    if len(families) != 1:
        raise ValueError("FAMILY_SOURCE_LOOKUP")
    return copy.deepcopy(families[0]), copy.deepcopy(cert)


def _validate_observed_transition_records(records: Sequence[Mapping[str, Any]], family: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("OBSERVED_TRANSITION_RECORDS_SCHEMA")
    expected_keys = list(family["common_prefix_transition_keys"])
    if len(records) != len(expected_keys):
        raise ValueError("OBSERVED_TRANSITION_COUNT")
    normalized: list[dict[str, Any]] = []
    for i, record in enumerate(records):
        required = {"transition_key", "observed_index", "provenance", "causally_observed"}
        if not isinstance(record, Mapping) or set(record) != required:
            raise ValueError("OBSERVED_TRANSITION_RECORD_SCHEMA")
        if record["transition_key"] != expected_keys[i]:
            raise ValueError("OBSERVED_TRANSITION_SOURCE_BINDING")
        if record["observed_index"] != i:
            raise ValueError("OBSERVED_TRANSITION_INDEX")
        if record["provenance"] != "RUNTIME_CAUSALLY_OBSERVED" or record["causally_observed"] is not True:
            raise ValueError("FUTURE_OR_UNOBSERVED_TRANSITION")
        normalized.append(copy.deepcopy(dict(record)))
    if len({r["transition_key"] for r in normalized}) < 2:
        raise ValueError("PERMUTATION_PREOUTCOME_INELIGIBLE")
    return normalized


def deterministic_nonidentity_permutation(keys: Sequence[str], family_id: str) -> list[str]:
    items = list(keys)
    if len(items) < 2 or len(set(items)) < 2 or not _is_sha(family_id):
        raise ValueError("PERMUTATION_PREOUTCOME_INELIGIBLE")
    n = len(items)
    start = 1 + (int(family_id[:16], 16) % (n - 1))
    for delta in range(n - 1):
        shift = 1 + ((start - 1 + delta) % (n - 1))
        perm = items[shift:] + items[:shift]
        if perm != items and sorted(perm) == sorted(items):
            return perm
    raise ValueError("PERMUTATION_PREOUTCOME_INELIGIBLE")


def _base_arm(arm_id: str, geometry: Mapping[str, Any], state_policy: str, transition_order: Sequence[str], update_operation: str) -> dict[str, Any]:
    arm = {"arm_id": arm_id}
    arm.update(copy.deepcopy(dict(geometry)))
    arm["state_policy"] = state_policy
    arm["transition_order"] = list(transition_order)
    arm["update_operation"] = update_operation
    return arm


def build_arms(observed_keys: Sequence[str], family_id: str, geometry: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_geometry(geometry)
    observed = list(observed_keys)
    permuted = deterministic_nonidentity_permutation(observed, family_id)
    active = _base_arm("ALIGNED_RECURSION", geometry, "CAUSAL_ORDERED_RECURSIVE_STATE", observed, "F_ALIGNED")
    static_repeat = _base_arm("STATIC_REPEAT", geometry, "BYTE_OR_NUMERIC_IDENTICAL_Z0_REPEAT", observed, "NOOP_MATCHED_UPDATE_SLOTS")
    matched_info = _base_arm("MATCHED_INFORMATION", geometry, "TARGET_IDENTITY_DESTROYED_MATCHED_INFORMATION", observed, "CONTROL_MATCHED_UPDATE_SLOTS")
    perm = _base_arm("TRANSITION_PERMUTED", geometry, "SAME_AUTHENTICATED_OBSERVED_TRANSITIONS_PERMUTED", permuted, "F_ALIGNED")
    oneshot = _base_arm("STATIC_ONESHOT", geometry, "FROZEN_Z0_ONESHOT", [], "NO_UPDATE")
    oneshot["G_exposure_locations"] = [geometry["oneshot_G_exposure_location"]]
    oneshot["updater_invocation_sites"] = []
    oneshot["runtime_call_geometry"] = ["STATIC_ONESHOT_G_EXPOSURE_ONLY"]
    oneshot["update_timing_budget"] = "NO_UPDATE"
    no_carry = _base_arm("NO_CARRY", geometry, "NO_CPDS_STATE", [], "NO_UPDATE")
    for key in ("state_capacity_id", "representation_budget_id", "information_volume_id", "serialization_or_numeric_budget_id", "z0_identity_id"):
        no_carry[key] = "NO_STATE"
    no_carry["F_callable_id"] = "NO_F"
    no_carry["F_parameters_id"] = "NO_F"
    no_carry["G_callable_id"] = "NULL_INTERFACE"
    no_carry["G_exposure_locations"] = []
    no_carry["updater_invocation_sites"] = []
    no_carry["runtime_call_geometry"] = ["BASE_POLICY_ONLY"]
    no_carry["update_timing_budget"] = "NO_UPDATE"
    no_carry["carrier_provenance_sources"] = []
    # Reviewed six-arm order is explicit and stable.
    return [no_carry, oneshot, static_repeat, active, perm, matched_info]


def _arm_map(arms: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(arms, list) or len(arms) != len(EXACT_ARM_IDS) or not all(isinstance(a, dict) for a in arms):
        raise ValueError("ARM_LIST_SCHEMA")
    ids = [a.get("arm_id") for a in arms]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_ARM")
    if set(ids) != set(EXACT_ARM_IDS):
        raise ValueError("ARM_SET")
    if ids != list(EXACT_ARM_IDS):
        raise ValueError("ARM_ORDER")
    return {a["arm_id"]: a for a in arms}


def _extract_geometry(arm: Mapping[str, Any], allow_empty: bool = False) -> dict[str, Any]:
    geometry = {k: copy.deepcopy(arm[k]) for k in BASE_GEOMETRY_FIELDS}
    if allow_empty:
        return geometry
    validate_geometry(geometry)
    return geometry


def _validate_arm_semantics(arms: Any, observed_keys: Sequence[str]) -> bool:
    amap = _arm_map(arms)
    active = amap["ALIGNED_RECURSION"]
    static = amap["STATIC_REPEAT"]
    perm = amap["TRANSITION_PERMUTED"]
    matched = amap["MATCHED_INFORMATION"]
    oneshot = amap["STATIC_ONESHOT"]
    no_carry = amap["NO_CARRY"]
    expected_arm_keys = {"arm_id", *BASE_GEOMETRY_FIELDS, "state_policy", "transition_order", "update_operation"}
    for arm in arms:
        if set(arm) != expected_arm_keys:
            raise ValueError("ARM_SCHEMA")
        if any(bool(arm[k]) for k in ("G_can_execute_action", "G_can_force_single_action", "G_can_mutate_environment")):
            raise ValueError("G_NONEXECUTING_BOUNDARY")
    # Active authority.
    validate_geometry(_extract_geometry(active))
    if active["state_policy"] != "CAUSAL_ORDERED_RECURSIVE_STATE" or active["transition_order"] != list(observed_keys) or active["update_operation"] != "F_ALIGNED":
        raise ValueError("ALIGNED_RECURSION_SEMANTICS")
    # Matched comparators must have exact geometry; their control operation cannot silently become F_ALIGNED.
    for label, arm in (("STATIC_REPEAT", static), ("TRANSITION_PERMUTED", perm), ("MATCHED_INFORMATION", matched)):
        for field in MATCHED_GEOMETRY_FIELDS:
            if arm[field] != active[field]:
                raise ValueError(label + "_GEOMETRY_MISMATCH")
    if static["state_policy"] != "BYTE_OR_NUMERIC_IDENTICAL_Z0_REPEAT" or static["transition_order"] != list(observed_keys) or static["update_operation"] != "NOOP_MATCHED_UPDATE_SLOTS":
        raise ValueError("STATIC_REPEAT_SEMANTICS")
    if static["update_operation"] == "F_ALIGNED":
        raise ValueError("STATIC_REPEAT_BECAME_ALIGNED")
    if matched["state_policy"] != "TARGET_IDENTITY_DESTROYED_MATCHED_INFORMATION" or matched["transition_order"] != list(observed_keys) or matched["update_operation"] != "CONTROL_MATCHED_UPDATE_SLOTS":
        raise ValueError("MATCHED_INFORMATION_SEMANTICS")
    if matched["update_operation"] == "F_ALIGNED":
        raise ValueError("MATCHED_INFORMATION_BECAME_ALIGNED")
    if perm["state_policy"] != "SAME_AUTHENTICATED_OBSERVED_TRANSITIONS_PERMUTED" or perm["update_operation"] != "F_ALIGNED":
        raise ValueError("TRANSITION_PERMUTED_SEMANTICS")
    if perm["transition_order"] == list(observed_keys):
        raise ValueError("PERMUTATION_IDENTITY")
    if sorted(perm["transition_order"]) != sorted(observed_keys):
        raise ValueError("PERMUTATION_MULTISET")
    # Aside from the arm label/state-policy and transition order, permuted must be operationally identical to active.
    for field in expected_arm_keys - {"arm_id", "state_policy", "transition_order"}:
        if perm[field] != active[field]:
            raise ValueError("PERMUTED_ONLY_ORDER_DIFFERS")
    # One-shot is deliberately not an exposure-matched comparator.
    if oneshot["state_policy"] != "FROZEN_Z0_ONESHOT" or oneshot["update_operation"] != "NO_UPDATE" or oneshot["transition_order"] != []:
        raise ValueError("STATIC_ONESHOT_SEMANTICS")
    for field in ("state_capacity_id", "representation_budget_id", "information_volume_id", "serialization_or_numeric_budget_id", "base_policy_id", "prompt_contract_id", "z0_identity_id", "G_callable_id"):
        if oneshot[field] != active[field]:
            raise ValueError("STATIC_ONESHOT_STATE_BINDING")
    if oneshot["G_exposure_locations"] != [active["oneshot_G_exposure_location"]] or oneshot["updater_invocation_sites"] != [] or oneshot["runtime_call_geometry"] != ["STATIC_ONESHOT_G_EXPOSURE_ONLY"] or oneshot["update_timing_budget"] != "NO_UPDATE":
        raise ValueError("STATIC_ONESHOT_EXPOSURE")
    # No-carry is a real null, never an exposure-matched comparator.
    if no_carry["state_policy"] != "NO_CPDS_STATE" or no_carry["update_operation"] != "NO_UPDATE" or no_carry["transition_order"] != []:
        raise ValueError("NO_CARRY_SEMANTICS")
    for field in ("state_capacity_id", "representation_budget_id", "information_volume_id", "serialization_or_numeric_budget_id", "z0_identity_id"):
        if no_carry[field] != "NO_STATE":
            raise ValueError("NO_CARRY_STATE_PRESENT")
    if no_carry["F_callable_id"] != "NO_F" or no_carry["F_parameters_id"] != "NO_F" or no_carry["G_callable_id"] != "NULL_INTERFACE" or no_carry["G_exposure_locations"] != [] or no_carry["updater_invocation_sites"] != [] or no_carry["runtime_call_geometry"] != ["BASE_POLICY_ONLY"] or no_carry["carrier_provenance_sources"] != []:
        raise ValueError("NO_CARRY_INTERFACE")
    return True


def packet_payload(packet: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(packet))
    payload.pop("packet_sha256", None)
    return payload


def packet_identity(packet: Mapping[str, Any]) -> str:
    return canon_sha(packet_payload(packet))


def build_constructibility_packet(
    snapshot: Mapping[str, Any], expected_source_snapshot_sha256: str,
    manifest: Mapping[str, Any], expected_manifest_sha256: str,
    family_id: str, observed_transition_records: Sequence[Mapping[str, Any]], geometry: Mapping[str, Any],
) -> dict[str, Any]:
    family, cert = _family_and_certificate(snapshot, expected_source_snapshot_sha256, manifest, expected_manifest_sha256, family_id)
    records = _validate_observed_transition_records(observed_transition_records, family)
    arms = build_arms([r["transition_key"] for r in records], family_id, geometry)
    packet = {
        "schema": PACKET_SCHEMA,
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_snapshot_sha256": expected_source_snapshot_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "certificate_sha256": certificate_identity(cert),
        "family_id": cert["family_id"],
        "structural_family_key_sha256": cert["structural_family_key_sha256"],
        "observed_transition_records": records,
        "eligibility_dependencies": ["graph_certificate_valid", "local_source_competence_preoutcome", "preoutcome_contract_checks"],
        "endpoint": PRIMARY_ENDPOINT,
        "first_action_in_primary_endpoint": False,
        "arms": arms,
        "constructibility_only": True,
        "scientific_result": "NOT_ASSESSED",
        "mechanistic_support_or_refutation_available": False,
    }
    packet["packet_sha256"] = packet_identity(packet)
    validate_constructibility_packet(packet, snapshot, expected_source_snapshot_sha256, manifest, expected_manifest_sha256)
    return packet


def validate_constructibility_packet(
    packet: Mapping[str, Any], snapshot: Mapping[str, Any], expected_source_snapshot_sha256: str,
    manifest: Mapping[str, Any], expected_manifest_sha256: str,
) -> bool:
    required = {
        "schema", "source_snapshot_id", "source_snapshot_sha256", "manifest_sha256",
        "certificate_sha256", "family_id", "structural_family_key_sha256",
        "observed_transition_records", "eligibility_dependencies", "endpoint",
        "first_action_in_primary_endpoint", "arms", "constructibility_only",
        "scientific_result", "mechanistic_support_or_refutation_available", "packet_sha256",
    }
    if not isinstance(packet, Mapping) or set(packet) != required:
        raise ValueError("PACKET_SCHEMA")
    if packet["schema"] != PACKET_SCHEMA:
        raise ValueError("PACKET_SCHEMA_ID")
    if packet["packet_sha256"] != packet_identity(packet):
        raise ValueError("PACKET_SHA")
    if packet["constructibility_only"] is not True or packet["scientific_result"] != "NOT_ASSESSED" or packet["mechanistic_support_or_refutation_available"] is not False:
        raise ValueError("PACKET_SCOPE")
    if packet["eligibility_dependencies"] != ["graph_certificate_valid", "local_source_competence_preoutcome", "preoutcome_contract_checks"]:
        raise ValueError("ELIGIBILITY")
    if packet["endpoint"] != PRIMARY_ENDPOINT or packet["first_action_in_primary_endpoint"] is not False:
        raise ValueError("ENDPOINT")
    if packet["source_snapshot_id"] != snapshot.get("snapshot_id") or packet["source_snapshot_sha256"] != expected_source_snapshot_sha256 or packet["manifest_sha256"] != expected_manifest_sha256:
        raise ValueError("PACKET_EXTERNAL_AUTHORITY_BINDING")
    family, cert = _family_and_certificate(snapshot, expected_source_snapshot_sha256, manifest, expected_manifest_sha256, packet["family_id"])
    if packet["structural_family_key_sha256"] != cert["structural_family_key_sha256"] or packet["certificate_sha256"] != certificate_identity(cert):
        raise ValueError("PACKET_CERTIFICATE_BINDING")
    records = _validate_observed_transition_records(packet["observed_transition_records"], family)
    observed_keys = [r["transition_key"] for r in records]
    _validate_arm_semantics(packet["arms"], observed_keys)
    # Permutation is deterministically derived from authenticated observed records, not caller supplied future material.
    amap = _arm_map(packet["arms"])
    expected_perm = deterministic_nonidentity_permutation(observed_keys, packet["family_id"])
    if amap["TRANSITION_PERMUTED"]["transition_order"] != expected_perm:
        raise ValueError("PERMUTATION_NOT_DETERMINISTIC_FROM_OBSERVED")
    return True


def constructibility_summary(
    packet_authorities: Sequence[Mapping[str, Any]], attempted_count: int, rejections: Sequence[str] | None = None,
) -> dict[str, Any]:
    if type(attempted_count) is not int or attempted_count < 0:
        raise ValueError("ATTEMPTED_COUNT")
    rejections = list(rejections or [])
    packet_hashes: list[str] = []
    for authority in packet_authorities:
        required = {"packet", "snapshot", "source_seal", "manifest", "manifest_seal"}
        if not isinstance(authority, Mapping) or set(authority) != required:
            raise ValueError("SUMMARY_AUTHORITY_SCHEMA")
        validate_constructibility_packet(authority["packet"], authority["snapshot"], authority["source_seal"], authority["manifest"], authority["manifest_seal"])
        packet_hashes.append(authority["packet"]["packet_sha256"])
    if attempted_count < len(packet_authorities) + len(rejections):
        raise ValueError("COUNT_INCONSISTENT")
    label = "PASS_CONSTRUCTIBLE" if attempted_count > 0 and attempted_count == len(packet_authorities) and not rejections else "CONSTRUCTIBILITY_INCONCLUSIVE"
    return {
        "schema": SUMMARY_SCHEMA,
        "label": label,
        "attempted_count": attempted_count,
        "constructible_count": len(packet_authorities),
        "packet_sha256s": packet_hashes,
        "preoutcome_rejections": rejections,
        "scientific_result": "NOT_ASSESSED",
        "mechanistic_support_or_refutation_available": False,
        "model_calls": 0,
        "environment_execution": 0,
        "future_split_access": 0,
    }


def _family(tag: str) -> dict[str, Any]:
    return {
        "source_graph_id": "graph-" + tag,
        "goal_canonical": "goal",
        "reset_observation_canonical": "reset",
        "allowed_pre_reset_history_canonical": ["look"],
        "immediate_next_command_canonical": "open",
        "common_prefix_transition_keys": [tag + "-t1", tag + "-t2", tag + "-t3"],
        "branch_A_equivalence_class": [tag + "-A"],
        "branch_B_equivalence_class": [tag + "-B"],
        "divergence_depth_after_immediate": 2,
        "local_source_competence_preoutcome": True,
    }


def _geometry() -> dict[str, Any]:
    return {
        "state_capacity_id": "UNFROZEN_STATE_CAPACITY",
        "representation_budget_id": "UNFROZEN_REPRESENTATION_BUDGET",
        "information_volume_id": "UNFROZEN_INFORMATION_VOLUME",
        "serialization_or_numeric_budget_id": "UNFROZEN_SERIALIZATION_OR_NUMERIC_BUDGET",
        "base_policy_id": "FROZEN_BASE_POLICY_PLACEHOLDER",
        "prompt_contract_id": "FROZEN_PROMPT_CONTRACT_PLACEHOLDER",
        "z0_identity_id": "PREOUTCOME_Z0_IDENTITY",
        "F_callable_id": "UNFROZEN_F_CALLABLE",
        "F_parameters_id": "UNFROZEN_F_PARAMETERS",
        "G_callable_id": "UNFROZEN_G_CALLABLE",
        "G_exposure_locations": ["RESET_PREFIX", "POST_TRANSITION_1", "POST_TRANSITION_2", "BRANCH_POINT"],
        "updater_invocation_sites": ["AFTER_OBS_1", "AFTER_OBS_2", "AFTER_OBS_3"],
        "runtime_call_geometry": ["G_EXPOSURE", "UPDATE_SLOT", "G_EXPOSURE", "UPDATE_SLOT", "G_EXPOSURE", "UPDATE_SLOT", "G_EXPOSURE"],
        "update_timing_budget": "MATCHED_PRE_BRANCH",
        "carrier_provenance_sources": ["MODEL_VISIBLE_PRE_RESET", "RUNTIME_CAUSALLY_OBSERVED"],
        "oneshot_G_exposure_location": "RESET_PREFIX",
        "G_can_execute_action": False,
        "G_can_force_single_action": False,
        "G_can_mutate_environment": False,
    }


def _records(family: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"transition_key": key, "observed_index": i, "provenance": "RUNTIME_CAUSALLY_OBSERVED", "causally_observed": True}
        for i, key in enumerate(family["common_prefix_transition_keys"])
    ]


def self_test() -> dict[str, Any]:
    verify_reviewed_authority()
    f = _family("self")
    snapshot = seal_source_snapshot("self-source", [f])
    source_seal = snapshot["snapshot_sha256"]
    manifest = build_generator_run_manifest(snapshot, DEVELOPMENT_NAMESPACE, source_seal)
    manifest_seal = manifest["manifest_sha256"]
    packet = build_constructibility_packet(snapshot, source_seal, manifest, manifest_seal, manifest["family_ids"][0], _records(f), _geometry())
    result = constructibility_summary([{"packet": packet, "snapshot": snapshot, "source_seal": source_seal, "manifest": manifest, "manifest_seal": manifest_seal}], 1)
    return {"status": result["label"], "scientific_result": result["scientific_result"], "model_calls": 0, "environment_execution": 0, "future_split_access": 0}


if __name__ == "__main__":
    print(json.dumps(self_test(), sort_keys=True))
