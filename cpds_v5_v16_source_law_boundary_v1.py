"""CPDS V5 V16 PRE_SCIENCE source-law trust boundary.

This module is deliberately narrower than the V15 authority proof module.
It separates two things that V15 accidentally conflated:

1. deterministic facts that code can prove about the one-shot source-to-S6
   transducer and its provenance bytes; and
2. the prospectively frozen scientific source-law assumption about the Linux
   kernel RNG, which serialized caller-owned bytes cannot prove after the fact.

No model, tokenizer, environment, TRAIN, CALIBRATION, DEVELOPMENT or
CONFIRMATION execution is performed here.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import os
import pathlib
import posix as _posix
import sys
from typing import Any, Iterable, Mapping, Sequence

import cpds_v5_v15_authority_proof_v1 as v15

# Source authority deliberately does not live in writable module-global
# "frozen" object aliases.  The production boundary instead checks structural
# properties of CPython's C-bound posix.getrandom object plus canonical module
# registry identity immediately before acquisition.  This is an engineering
# same-process binding guard, not randomness-origin proof and not resistance to
# arbitrary hostile rewrite of the entire interpreter (including sys.modules or
# builtins).

ROOT = pathlib.Path(__file__).resolve().parent
DESIGN_ID = "faee370b-d0e6-4305-b3d8-da57dede7cab"
DESIGN_SEMANTIC_HASH = "58c2c1f2169789a9d42bfbb941f54c9b4392e29e0370af806bc9d2a9a4497429"
DESIGN_ATTACK_SYNTHESIS_ID = "477fd4dd-d316-4693-b9be-db481133c061"
SOURCE_LAW_ASSUMPTION_ID = "d34d0cf0-6405-4feb-bba0-4c4820211144"
SOURCE_AUTHORITY_ID = "CPDS_V16_LINUX_KERNEL_GETRANDOM_FLAGS0_AUTHORITY_V1"
SOURCE_PRIMITIVE_ID = "LINUX_OS_GETRANDOM_FLAGS0"
SOURCE_REQUEST_BYTES = v15.DEVELOPMENT_N * v15.BOUND_SOURCE_WORDS_PER_FAMILY * 2
SOURCE_PARTITION_ID = "CPDS_V16_33_ORDERED_DISJOINT_BLOCKS_X8_UINT16_BE_V1"
SOURCE_TO_ASSIGNMENT_TRANSDUCER_ID = "CPDS_V16_FIRST_ACCEPTED_REJECT_GE_65520_FACTORADIC_S6_V1"
SOURCE_LAW_CLAIM = "EXACT_PRODUCT_UNIFORM_S6_POWER_33_CONDITIONAL_ON_FROZEN_SOURCE_LAW_ASSUMPTION"
RECEIPT_ROLE = "PROVENANCE_AND_INTEGRITY_ONLY_NOT_RANDOMNESS_ORIGIN_PROOF"
PROVENANCE_SCHEMA = "CPDS_V5_V16_SOURCE_PROVENANCE_V1"
TRANSDUCER_PROOF_SCHEMA = "CPDS_V5_V16_DETERMINISTIC_TRANSDUCER_PROOF_V1"
ASSIGNMENT_BUNDLE_SCHEMA = "CPDS_V5_V16_PRODUCTION_ASSIGNMENT_BUNDLE_V1"
RELEASE_PROOF_SCHEMA = "CPDS_V5_V16_RELEASE_CONDITIONAL_LAW_PROOF_V1"

# These component identities and the aggregate implementation identity are
# prospectively frozen literals from the exact reviewed successor bytes.
# Production authority never re-mints itself from current mutable function objects.
FROZEN_PRIMITIVE_ATTESTATION_SHA256 = "39f65118fb7f258a6a67ffc5f610f470ead05057f5897fab95748af9cec067fe"
FROZEN_ONE_SHOT_SOURCE_CALL_SHA256 = "ab376b946d7670a3bf897da41c45b8100eef1d1f34ef1242aeb9ff0bf489b1e7"
FROZEN_V16_TRANSDUCER_SHA256 = "015e99ef43beb686f3f41d078efae347c9fbe8bf2f1389b8b03fdd35fa7d39c1"
FROZEN_V15_PARTITION_SHA256 = "d12ce8825c00c6366fb9fb72ee550e26169b8231b8d81e34839fd4c5359281b9"
FROZEN_V15_FIRST_ACCEPTED_SHA256 = "3cf25fe00a1a7e91cba7d454870de8fe750e89f53cfe3ff3b8eeb0072c749411"
FROZEN_V15_FACTORADIC_SHA256 = "462b038d230b121db5ca6ecdf0e0f8c0136685d3876fd1576e16e48807c1d865"
FROZEN_SOURCE_HASH_HELPER_SHA256 = "6f51a422f39418be33083497cb763611413faf3d19660ae8e5d79813df8f41b2"
FROZEN_BINDING_VERIFIER_SHA256 = "d5eb6f28154906a6d90093c30ac7f7d576935a53c6d5e8009e8dbf52f3a01e20"
FROZEN_PRODUCTION_ENTRYPOINT_SHA256 = "3901f048d367d6254adf8192723c9fbb0f93c46a20eca6473f44bb6c27276c25"
FROZEN_PRODUCTION_SOURCE_IMPLEMENTATION_SHA256 = "1ee84c398ee5ecd38c19c5dd3c07457fe47de9c41da10c4b2416a05c2ce4b369"



def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _sha_obj(obj: Any) -> str:
    return v15.sha_obj(obj)


def _source_hash(fn: Any) -> str:
    return hashlib.sha256(inspect.getsource(fn).encode("utf-8")).hexdigest()


def source_law_assumption() -> dict[str, Any]:
    """Return the frozen V16 source model; this is an assumption, not evidence."""
    d = {
        "schema": "CPDS_V5_V16_SOURCE_LAW_ASSUMPTION_V1",
        "assumption_id": SOURCE_LAW_ASSUMPTION_ID,
        "scientific_design_id": DESIGN_ID,
        "design_semantic_hash": DESIGN_SEMANTIC_HASH,
        "authority_id": SOURCE_AUTHORITY_ID,
        "source_primitive_id": SOURCE_PRIMITIVE_ID,
        "platform": "linux",
        "python_binding": "os.getrandom",
        "flags": 0,
        "logical_invocation_count": 1,
        "bytes_requested": SOURCE_REQUEST_BYTES,
        "word_interpretation": "UINT16_BIG_ENDIAN",
        "word_count": v15.DEVELOPMENT_N * v15.BOUND_SOURCE_WORDS_PER_FAMILY,
        "source_word_law_assumed": "EXACT_UNIFORM_UINT16_GIVEN_COMPLETE_PRIOR_HISTORY_WITH_REQUIRED_CROSS_BLOCK_INDEPENDENCE",
        "randomization_claim": SOURCE_LAW_CLAIM,
        "mechanically_proven_by_serialized_receipt": False,
        "unconditional_kernel_randomness_claim": False,
        "external_randomness_origin_authentication_claim": False,
    }
    d["assumption_sha256"] = _sha_obj(d)
    return d


def verify_source_law_assumption_declaration(assumption: Mapping[str, Any]) -> str:
    expected = source_law_assumption()
    _require(dict(assumption) == expected, "V16_SOURCE_LAW_ASSUMPTION_DRIFT")
    return expected["assumption_sha256"]


def _production_source_primitive_attestation() -> dict[str, Any]:
    # inspect.isbuiltin and writable module-global object aliases are not
    # authority.  Require the canonical interpreter module identities, then
    # require os.getrandom and posix.getrandom to be the *same* CPython
    # builtin-function object, C-bound to the canonical posix module.  A Python
    # function can spoof __name__/__module__ strings but cannot satisfy this
    # builtin type + __self__ ownership relation.
    _require(sys.platform.startswith("linux"), "V16_SOURCE_PLATFORM")
    _require(sys.modules.get("os") is os, "V16_SOURCE_OS_MODULE_BINDING_DRIFT")
    _require(sys.modules.get("posix") is _posix, "V16_SOURCE_POSIX_MODULE_BINDING_DRIFT")
    fn = getattr(os, "getrandom", None)
    posix_fn = getattr(_posix, "getrandom", None)
    builtin_function_type = type([].append)
    _require(type(fn) is builtin_function_type and type(posix_fn) is builtin_function_type, "V16_SOURCE_PRIMITIVE_NOT_CPYTHON_BUILTIN")
    _require(fn is posix_fn, "V16_SOURCE_PRIMITIVE_RELATION_DRIFT")
    _require(getattr(fn, "__self__", None) is _posix and getattr(posix_fn, "__self__", None) is _posix, "V16_SOURCE_PRIMITIVE_OWNER_DRIFT")
    _require(getattr(fn, "__name__", "") == "getrandom" and getattr(fn, "__module__", "") == "posix", "V16_SOURCE_PRIMITIVE_METADATA_DRIFT")
    return {
        "primitive_id": SOURCE_PRIMITIVE_ID,
        "python_binding": "os.getrandom",
        "python_binding_module": "posix",
        "runtime_identity_relation": "OS_GETRANDOM_IS_POSIX_GETRANDOM_IS_CPYTHON_POSIX_BOUND_BUILTIN",
        "flags": 0,
        "bytes_requested": SOURCE_REQUEST_BYTES,
        "attestation_scope": "RUNTIME_BINDING_ONLY_NOT_RANDOMNESS_ORIGIN_PROOF",
    }


def _invoke_production_source_once() -> bytes:
    """The sole production entropy acquisition primitive. No injectable arguments."""
    # Re-check the exact prospectively frozen source-use identities inside the
    # acquisition boundary.  A replaced helper cannot self-authorize by causing
    # production_source_authority() to mint a new matching implementation hash.
    _require(_source_hash(_invoke_production_source_once) == FROZEN_ONE_SHOT_SOURCE_CALL_SHA256, "V16_FROZEN_SOURCE_CALL_DRIFT")
    _require(_source_hash(_production_source_primitive_attestation) == FROZEN_PRIMITIVE_ATTESTATION_SHA256, "V16_FROZEN_SOURCE_ATTESTATION_DRIFT")
    _production_source_primitive_attestation()
    raw = os.getrandom(SOURCE_REQUEST_BYTES, 0)
    _require(type(raw) is bytes and len(raw) == SOURCE_REQUEST_BYTES, "V16_SOURCE_SHORT_READ_FAIL_CLOSED")
    return raw


def production_source_implementation_sha256() -> str:
    # Never derive authority from live mutable helpers.  This literal identifies
    # the exact prospectively reviewed component set.
    return FROZEN_PRODUCTION_SOURCE_IMPLEMENTATION_SHA256


def verify_frozen_production_source_bindings() -> dict[str, str]:
    """Fail closed if a source/transducer alias differs from the frozen V16 bytes."""
    observed = {
        "source_hash_helper": _source_hash(_source_hash),
        "binding_verifier": _source_hash(verify_frozen_production_source_bindings),
        "production_entrypoint": _source_hash(produce_development_assignment_bundle),
        "primitive_attestation": _source_hash(_production_source_primitive_attestation),
        "one_shot_source_call": _source_hash(_invoke_production_source_once),
        "v16_transducer": _source_hash(deterministic_transducer_proof_from_raw),
        "v15_partition": _source_hash(v15._partition_invocation_bytes),
        "v15_first_accepted": _source_hash(v15.first_accepted_assignment),
        "v15_factoradic": _source_hash(v15.factoradic_unrank_s6),
    }
    expected = {
        "source_hash_helper": FROZEN_SOURCE_HASH_HELPER_SHA256,
        "binding_verifier": FROZEN_BINDING_VERIFIER_SHA256,
        "production_entrypoint": FROZEN_PRODUCTION_ENTRYPOINT_SHA256,
        "primitive_attestation": FROZEN_PRIMITIVE_ATTESTATION_SHA256,
        "one_shot_source_call": FROZEN_ONE_SHOT_SOURCE_CALL_SHA256,
        "v16_transducer": FROZEN_V16_TRANSDUCER_SHA256,
        "v15_partition": FROZEN_V15_PARTITION_SHA256,
        "v15_first_accepted": FROZEN_V15_FIRST_ACCEPTED_SHA256,
        "v15_factoradic": FROZEN_V15_FACTORADIC_SHA256,
    }
    _require(observed == expected, "V16_FROZEN_SOURCE_COMPONENT_DRIFT")
    observed_aggregate = _sha_obj({
        "domain": "CPDS_V16_FROZEN_PRODUCTION_SOURCE_IMPLEMENTATION_V3",
        "components": observed,
    })
    _require(observed_aggregate == FROZEN_PRODUCTION_SOURCE_IMPLEMENTATION_SHA256, "V16_FROZEN_SOURCE_IMPLEMENTATION_DRIFT")
    _production_source_primitive_attestation()
    return observed


def production_source_authority() -> dict[str, Any]:
    d = {
        "schema": "CPDS_V5_V16_SOURCE_AUTHORITY_V1",
        "authority_id": SOURCE_AUTHORITY_ID,
        "implementation_sha256": production_source_implementation_sha256(),
        "source_primitive_id": SOURCE_PRIMITIVE_ID,
        "source_contract_sha256": v15.exact_uint16_source_contract()["contract_sha256"],
        "source_law_assumption_sha256": source_law_assumption()["assumption_sha256"],
        "partition_id": SOURCE_PARTITION_ID,
        "transducer_id": SOURCE_TO_ASSIGNMENT_TRANSDUCER_ID,
        "one_shot": True,
        "source_shopping": False,
        "fresh_entropy_on_retry": False,
    }
    d["authority_sha256"] = _sha_obj(d)
    return d


def derive_invocation_id(*, consumed_family_id: str, context_root: str) -> str:
    authority_hash = production_source_authority()["authority_sha256"]
    _require(type(consumed_family_id) is str and bool(consumed_family_id), "V16_CONSUMED_FAMILY_ID")
    _require(v15._is_sha256(context_root), "V16_CONTEXT_ROOT")
    return _sha_obj({
        "domain": "CPDS_V5_V16_SINGLE_PRODUCTION_ENTROPY_INVOCATION_V1",
        "authority_sha256": authority_hash,
        "consumed_family_id": consumed_family_id,
        "context_root": context_root,
    })


def deterministic_transducer_proof_from_raw(*, raw: bytes, family_ids: Sequence[str]) -> dict[str, Any]:
    """Prove only deterministic transformation/counting facts for supplied bytes."""
    streams = v15._partition_invocation_bytes(raw, family_ids)
    assignments: list[dict[str, Any]] = []
    for i, fid in enumerate(family_ids):
        perm, consumed = v15.first_accepted_assignment(streams[fid])
        assignments.append({
            "family_index": i,
            "family_id": fid,
            "arm_permutation": list(perm),
            "consumed_word_count": len(consumed),
            "consumed_words_sha256": _sha_obj(list(consumed)),
            "block_words_sha256": _sha_obj(list(streams[fid])),
        })
    proof = {
        "schema": TRANSDUCER_PROOF_SCHEMA,
        "proof_scope": "DETERMINISTIC_TRANSFORM_ONLY_DOES_NOT_PROVE_SOURCE_LAW_OR_RANDOMNESS_ORIGIN",
        "family_ids": list(family_ids),
        "raw_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_byte_count": len(raw),
        "partition_id": SOURCE_PARTITION_ID,
        "words_per_family": v15.BOUND_SOURCE_WORDS_PER_FAMILY,
        "transducer_id": SOURCE_TO_ASSIGNMENT_TRANSDUCER_ID,
        "sampler_count_proof": v15.exact_sampler_count_proof(),
        "fixed_block_conditional_rank_count_proof": v15.fixed_block_conditional_rank_count_proof(),
        "assignments": assignments,
        "source_law_assumption_sha256": source_law_assumption()["assumption_sha256"],
        "randomization_claim_scope": SOURCE_LAW_CLAIM,
    }
    proof["proof_sha256"] = _sha_obj(proof)
    return proof


def verify_deterministic_transducer_proof(proof: Mapping[str, Any], *, raw: bytes, family_ids: Sequence[str]) -> str:
    expected = deterministic_transducer_proof_from_raw(raw=raw, family_ids=family_ids)
    _require(dict(proof) == expected, "V16_DETERMINISTIC_TRANSDUCER_PROOF_DRIFT")
    counts = expected["sampler_count_proof"]
    _require(counts == {"accepted": 65520, "rejected": 16, "per_rank_preimages": 91, "rank_count": 720}, "V16_SAMPLER_COUNTS")
    block = expected["fixed_block_conditional_rank_count_proof"]
    _require(block["words_per_family"] == 8 and block["rank_count"] == 720 and block["conditional_rank_law_given_success"] == "EXACT_UNIFORM_S6", "V16_FIXED_BLOCK_COUNTS")
    _require(block["successful_blocks_per_rank"] * 720 == block["successful_blocks"], "V16_FIXED_BLOCK_EQUAL_RANK_COUNT")
    return expected["proof_sha256"]


def _build_provenance_receipt(*, raw: bytes, family_ids: Sequence[str], consumed_family_id: str, context_root: str, invocation_id: str) -> dict[str, Any]:
    """Build an audit record. It is intentionally not a randomness-origin credential."""
    receipt = {
        "schema": PROVENANCE_SCHEMA,
        "role": RECEIPT_ROLE,
        "scientific_design_id": DESIGN_ID,
        "design_semantic_hash": DESIGN_SEMANTIC_HASH,
        "authority": production_source_authority(),
        "source_primitive_attestation": _production_source_primitive_attestation(),
        "source_law_assumption_sha256": source_law_assumption()["assumption_sha256"],
        "randomness_origin_established": False,
        "source_law_established_by_receipt": False,
        "consumed_family_id": consumed_family_id,
        "context_root": context_root,
        "invocation_id": invocation_id,
        "family_ids": list(family_ids),
        "raw_bytes_hex": raw.hex(),
        "raw_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_byte_count": len(raw),
        "partition_id": SOURCE_PARTITION_ID,
        "transducer_id": SOURCE_TO_ASSIGNMENT_TRANSDUCER_ID,
    }
    receipt["receipt_sha256"] = _sha_obj(receipt)
    return receipt


def verify_provenance_receipt_integrity(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Check integrity only; never convert serialized bytes into source-law evidence."""
    d = copy.deepcopy(dict(receipt))
    claimed = d.pop("receipt_sha256", None)
    _require(v15._is_sha256(claimed) and _sha_obj(d) == claimed, "V16_RECEIPT_SELF_HASH")
    required = {
        "schema","role","scientific_design_id","design_semantic_hash","authority","source_primitive_attestation",
        "source_law_assumption_sha256","randomness_origin_established","source_law_established_by_receipt",
        "consumed_family_id","context_root","invocation_id","family_ids","raw_bytes_hex","raw_bytes_sha256",
        "raw_byte_count","partition_id","transducer_id"
    }
    _require(set(d) == required and d["schema"] == PROVENANCE_SCHEMA and d["role"] == RECEIPT_ROLE, "V16_RECEIPT_FIELDS")
    _require(d["scientific_design_id"] == DESIGN_ID and d["design_semantic_hash"] == DESIGN_SEMANTIC_HASH, "V16_RECEIPT_DESIGN")
    _require(d["authority"] == production_source_authority(), "V16_RECEIPT_AUTHORITY")
    _require(d["source_primitive_attestation"] == _production_source_primitive_attestation(), "V16_RECEIPT_RUNTIME_BINDING")
    _require(d["source_law_assumption_sha256"] == source_law_assumption()["assumption_sha256"], "V16_RECEIPT_SOURCE_ASSUMPTION")
    _require(d["randomness_origin_established"] is False and d["source_law_established_by_receipt"] is False, "V16_RECEIPT_OVERCLAIM")
    _require(d["partition_id"] == SOURCE_PARTITION_ID and d["transducer_id"] == SOURCE_TO_ASSIGNMENT_TRANSDUCER_ID, "V16_RECEIPT_TRANSFORM")
    try:
        raw = bytes.fromhex(d["raw_bytes_hex"])
    except (TypeError, ValueError):
        raise ValueError("V16_RECEIPT_RAW_HEX")
    _require(len(raw) == SOURCE_REQUEST_BYTES == d["raw_byte_count"], "V16_RECEIPT_RAW_LENGTH")
    _require(hashlib.sha256(raw).hexdigest() == d["raw_bytes_sha256"], "V16_RECEIPT_RAW_HASH")
    _require(len(d["family_ids"]) == v15.DEVELOPMENT_N and len(set(d["family_ids"])) == v15.DEVELOPMENT_N, "V16_RECEIPT_FAMILIES")
    _require(d["invocation_id"] == derive_invocation_id(consumed_family_id=d["consumed_family_id"], context_root=d["context_root"]), "V16_RECEIPT_INVOCATION")
    return {
        "integrity": "PASS",
        "receipt_sha256": claimed,
        "randomness_origin": "NOT_ESTABLISHED_BY_SERIALIZED_RECEIPT",
        "source_law": "NOT_ESTABLISHED_BY_SERIALIZED_RECEIPT",
        "scientific_randomization_validity": "CONDITIONAL_ON_SEPARATELY_FROZEN_SOURCE_LAW_ASSUMPTION",
    }


def produce_development_assignment_bundle(*, family_ids: Sequence[str], consumed_family_id: str, context_root: str, invocation_id: str) -> dict[str, Any]:
    """Scientific production randomization entry point. Entropy is not injectable."""
    verify_source_law_assumption_declaration(source_law_assumption())
    _require(len(family_ids) == v15.DEVELOPMENT_N and len(set(family_ids)) == v15.DEVELOPMENT_N, "V16_FAMILY_IDS")
    _require(all(type(fid) is str and fid for fid in family_ids), "V16_FAMILY_ID_TYPE")
    _require(v15._is_sha256(context_root), "V16_CONTEXT_ROOT")
    _require(invocation_id == derive_invocation_id(consumed_family_id=consumed_family_id, context_root=context_root), "V16_INVOCATION_ID")
    # Authority-critical source acquisition is owned directly by this exact
    # production entrypoint.  It does not delegate scientific source bytes to
    # the caller-mutable verifier/helper pair.  Use direct stdlib hashing here
    # rather than _source_hash so replacing _source_hash cannot bless a forged
    # source helper.  These checks are implementation integrity, not proof of
    # the scientific source-law assumption.
    direct_observed = {
        "source_hash_helper": hashlib.sha256(inspect.getsource(_source_hash).encode("utf-8")).hexdigest(),
        "binding_verifier": hashlib.sha256(inspect.getsource(verify_frozen_production_source_bindings).encode("utf-8")).hexdigest(),
        "production_entrypoint": hashlib.sha256(inspect.getsource(produce_development_assignment_bundle).encode("utf-8")).hexdigest(),
        "primitive_attestation": hashlib.sha256(inspect.getsource(_production_source_primitive_attestation).encode("utf-8")).hexdigest(),
        "one_shot_source_call": hashlib.sha256(inspect.getsource(_invoke_production_source_once).encode("utf-8")).hexdigest(),
        "v16_transducer": hashlib.sha256(inspect.getsource(deterministic_transducer_proof_from_raw).encode("utf-8")).hexdigest(),
        "v15_partition": hashlib.sha256(inspect.getsource(v15._partition_invocation_bytes).encode("utf-8")).hexdigest(),
        "v15_first_accepted": hashlib.sha256(inspect.getsource(v15.first_accepted_assignment).encode("utf-8")).hexdigest(),
        "v15_factoradic": hashlib.sha256(inspect.getsource(v15.factoradic_unrank_s6).encode("utf-8")).hexdigest(),
    }
    direct_expected = {
        "source_hash_helper": FROZEN_SOURCE_HASH_HELPER_SHA256,
        "binding_verifier": FROZEN_BINDING_VERIFIER_SHA256,
        "production_entrypoint": FROZEN_PRODUCTION_ENTRYPOINT_SHA256,
        "primitive_attestation": FROZEN_PRIMITIVE_ATTESTATION_SHA256,
        "one_shot_source_call": FROZEN_ONE_SHOT_SOURCE_CALL_SHA256,
        "v16_transducer": FROZEN_V16_TRANSDUCER_SHA256,
        "v15_partition": FROZEN_V15_PARTITION_SHA256,
        "v15_first_accepted": FROZEN_V15_FIRST_ACCEPTED_SHA256,
        "v15_factoradic": FROZEN_V15_FACTORADIC_SHA256,
    }
    _require(direct_observed == direct_expected, "V16_PRODUCTION_INLINE_BINDING_DRIFT")
    _production_source_primitive_attestation()
    raw = os.getrandom(SOURCE_REQUEST_BYTES, 0)
    _require(type(raw) is bytes and len(raw) == SOURCE_REQUEST_BYTES, "V16_SOURCE_SHORT_READ_FAIL_CLOSED")
    # If any block has no accepted word, deterministic_transducer_proof_from_raw raises.
    # The already-consumed one-shot realization is not retried or redrawn.
    transducer_proof = deterministic_transducer_proof_from_raw(raw=raw, family_ids=family_ids)
    receipt = _build_provenance_receipt(raw=raw, family_ids=family_ids, consumed_family_id=consumed_family_id, context_root=context_root, invocation_id=invocation_id)
    receipt_status = verify_provenance_receipt_integrity(receipt)
    _require(receipt_status["randomness_origin"] == "NOT_ESTABLISHED_BY_SERIALIZED_RECEIPT", "V16_RECEIPT_SCOPE")
    bundle = {
        "schema": ASSIGNMENT_BUNDLE_SCHEMA,
        "scientific_design_id": DESIGN_ID,
        "design_semantic_hash": DESIGN_SEMANTIC_HASH,
        "source_law_assumption": source_law_assumption(),
        "source_law_assumption_sha256": source_law_assumption()["assumption_sha256"],
        "randomization_claim_scope": SOURCE_LAW_CLAIM,
        "randomness_origin_claim": "NOT_ESTABLISHED_POST_HOC",
        "source_authority": production_source_authority(),
        "consumed_family_id": consumed_family_id,
        "context_root": context_root,
        "invocation_id": invocation_id,
        "family_ids": list(family_ids),
        "assignments": copy.deepcopy(transducer_proof["assignments"]),
        "deterministic_transducer_proof": transducer_proof,
        "provenance_receipt": receipt,
        "one_shot_source_consumed": True,
        "fresh_entropy_on_retry": False,
        "source_shopping": False,
    }
    bundle["bundle_sha256"] = _sha_obj(bundle)
    return bundle


def verify_assignment_bundle_structure(bundle: Mapping[str, Any]) -> dict[str, Any]:
    d = copy.deepcopy(dict(bundle))
    claimed = d.pop("bundle_sha256", None)
    _require(v15._is_sha256(claimed) and _sha_obj(d) == claimed, "V16_BUNDLE_SELF_HASH")
    required = {
        "schema","scientific_design_id","design_semantic_hash","source_law_assumption","source_law_assumption_sha256",
        "randomization_claim_scope","randomness_origin_claim","source_authority","consumed_family_id","context_root",
        "invocation_id","family_ids","assignments","deterministic_transducer_proof","provenance_receipt",
        "one_shot_source_consumed","fresh_entropy_on_retry","source_shopping"
    }
    _require(set(d) == required and d["schema"] == ASSIGNMENT_BUNDLE_SCHEMA, "V16_BUNDLE_FIELDS")
    _require(d["scientific_design_id"] == DESIGN_ID and d["design_semantic_hash"] == DESIGN_SEMANTIC_HASH, "V16_BUNDLE_DESIGN")
    assumption_hash = verify_source_law_assumption_declaration(d["source_law_assumption"])
    _require(d["source_law_assumption_sha256"] == assumption_hash, "V16_BUNDLE_ASSUMPTION")
    _require(d["randomization_claim_scope"] == SOURCE_LAW_CLAIM and d["randomness_origin_claim"] == "NOT_ESTABLISHED_POST_HOC", "V16_BUNDLE_CLAIM_SCOPE")
    _require(d["source_authority"] == production_source_authority(), "V16_BUNDLE_AUTHORITY")
    _require(d["invocation_id"] == derive_invocation_id(consumed_family_id=d["consumed_family_id"], context_root=d["context_root"]), "V16_BUNDLE_INVOCATION")
    _require(d["one_shot_source_consumed"] is True and d["fresh_entropy_on_retry"] is False and d["source_shopping"] is False, "V16_BUNDLE_ONE_SHOT")
    receipt_status = verify_provenance_receipt_integrity(d["provenance_receipt"])
    raw = bytes.fromhex(d["provenance_receipt"]["raw_bytes_hex"])
    proof_hash = verify_deterministic_transducer_proof(d["deterministic_transducer_proof"], raw=raw, family_ids=d["family_ids"])
    _require(d["assignments"] == d["deterministic_transducer_proof"]["assignments"], "V16_BUNDLE_ASSIGNMENTS")
    return {
        "bundle_integrity": "PASS",
        "bundle_sha256": claimed,
        "deterministic_transducer_proof_sha256": proof_hash,
        "receipt_integrity": receipt_status["integrity"],
        "randomness_origin": "NOT_ESTABLISHED_BY_SERIALIZED_BUNDLE",
        "source_law_status": "PROSPECTIVELY_FROZEN_ASSUMPTION_NOT_POST_HOC_PROOF",
        "scientific_randomization_validity": "EXACT_ONLY_CONDITIONAL_ON_SOURCE_LAW_ASSUMPTION",
    }


def retry_same_assignment_bundle(existing_bundle: Mapping[str, Any], *, consumed_family_id: str, context_root: str, invocation_id: str) -> dict[str, Any]:
    """Retry may only reuse the exact already-realized bundle; it obtains no entropy."""
    status = verify_assignment_bundle_structure(existing_bundle)
    _require(existing_bundle["consumed_family_id"] == consumed_family_id, "V16_RETRY_FAMILY_SWITCH")
    _require(existing_bundle["context_root"] == context_root, "V16_RETRY_CONTEXT_SWITCH")
    _require(existing_bundle["invocation_id"] == invocation_id, "V16_RETRY_INVOCATION_SWITCH")
    out = copy.deepcopy(dict(existing_bundle))
    _require(out["bundle_sha256"] == status["bundle_sha256"], "V16_RETRY_BUNDLE_SWITCH")
    return out


def make_release_conditional_law_proof(*, event_name: str, depends_on: Iterable[str], context_root: str, assignment_bundle: Mapping[str, Any], release_event_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bundle_status = verify_assignment_bundle_structure(assignment_bundle)
    _require(type(event_name) is str and bool(event_name), "V16_RELEASE_EVENT")
    _require(context_root == assignment_bundle["context_root"], "V16_RELEASE_CONTEXT")
    deps = sorted(v15._nfc(x) for x in depends_on)
    proof = {
        "schema": RELEASE_PROOF_SCHEMA,
        "event_name": event_name,
        "depends_on": deps,
        "context_root": context_root,
        "assignment_bundle_sha256": bundle_status["bundle_sha256"],
        "release_event_history": copy.deepcopy(list(release_event_history)),
        "release_event_history_sha256": _sha_obj(list(release_event_history)),
        "source_law_assumption_sha256": assignment_bundle["source_law_assumption_sha256"],
        "preserved_law": SOURCE_LAW_CLAIM,
        "claim_scope": "CONDITIONAL_ON_FROZEN_SOURCE_LAW_ASSUMPTION_AND_FULL_RELEASE_INFORMATION",
        "receipt_used_as_randomness_origin_proof": False,
        "verifier_sha256": _source_hash(verify_release_conditional_law_proof),
    }
    proof["proof_sha256"] = _sha_obj(proof)
    return proof


def verify_release_conditional_law_proof(proof: Mapping[str, Any], *, event_name: str, depends_on: Iterable[str], context_root: str, assignment_bundle: Mapping[str, Any], release_event_history: Sequence[Mapping[str, Any]]) -> str:
    d = copy.deepcopy(dict(proof))
    claimed = d.pop("proof_sha256", None)
    _require(v15._is_sha256(claimed) and _sha_obj(d) == claimed, "V16_RELEASE_PROOF_SELF_HASH")
    required = {"schema","event_name","depends_on","context_root","assignment_bundle_sha256","release_event_history","release_event_history_sha256","source_law_assumption_sha256","preserved_law","claim_scope","receipt_used_as_randomness_origin_proof","verifier_sha256"}
    _require(set(d) == required and d["schema"] == RELEASE_PROOF_SCHEMA, "V16_RELEASE_PROOF_FIELDS")
    status = verify_assignment_bundle_structure(assignment_bundle)
    _require(d["event_name"] == event_name and d["depends_on"] == sorted(v15._nfc(x) for x in depends_on), "V16_RELEASE_PROOF_EVENT")
    _require(d["context_root"] == context_root == assignment_bundle["context_root"], "V16_RELEASE_PROOF_CONTEXT")
    _require(d["assignment_bundle_sha256"] == status["bundle_sha256"], "V16_RELEASE_PROOF_BUNDLE")
    _require(d["release_event_history"] == list(release_event_history) and d["release_event_history_sha256"] == _sha_obj(list(release_event_history)), "V16_RELEASE_PROOF_HISTORY")
    _require(d["source_law_assumption_sha256"] == assignment_bundle["source_law_assumption_sha256"], "V16_RELEASE_PROOF_ASSUMPTION")
    _require(d["preserved_law"] == SOURCE_LAW_CLAIM and d["claim_scope"] == "CONDITIONAL_ON_FROZEN_SOURCE_LAW_ASSUMPTION_AND_FULL_RELEASE_INFORMATION", "V16_RELEASE_PROOF_LAW")
    _require(d["receipt_used_as_randomness_origin_proof"] is False, "V16_RELEASE_RECEIPT_OVERCLAIM")
    _require(d["verifier_sha256"] == _source_hash(verify_release_conditional_law_proof), "V16_RELEASE_PROOF_VERIFIER")
    return str(claimed)


def verify_production_noninjectability() -> dict[str, Any]:
    """Static proof that scientific source acquisition has no caller entropy channel."""
    primitive_attestation = _production_source_primitive_attestation()
    source_sig = inspect.signature(_invoke_production_source_once)
    producer_sig = inspect.signature(produce_development_assignment_bundle)
    retry_sig = inspect.signature(retry_same_assignment_bundle)
    _require(len(source_sig.parameters) == 0, "V16_SOURCE_INJECTION_PARAMETER")
    forbidden = {"raw","bytes","raw_bytes","words","family_streams","receipt","source_reader","rng","entropy"}
    producer_names = {name.lower() for name in producer_sig.parameters}
    _require(not (producer_names & forbidden), "V16_PRODUCTION_ENTROPY_INJECTION_PARAMETER")

    source_tree = ast.parse(inspect.getsource(_invoke_production_source_once))
    getrandom_calls = [n for n in ast.walk(source_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "os" and n.func.attr == "getrandom"]
    _require(len(getrandom_calls) == 1, "V16_SOURCE_CALL_COUNT")
    call = getrandom_calls[0]
    _require(len(call.args) == 2 and isinstance(call.args[0], ast.Name) and call.args[0].id == "SOURCE_REQUEST_BYTES" and isinstance(call.args[1], ast.Constant) and call.args[1].value == 0, "V16_SOURCE_CALL_BINDING")

    producer_tree = ast.parse(inspect.getsource(produce_development_assignment_bundle))
    producer_helper_calls = [n for n in ast.walk(producer_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_invoke_production_source_once"]
    _require(len(producer_helper_calls) == 0, "V16_PRODUCTION_DELEGATED_SOURCE_CALL")
    producer_getrandom_calls = [n for n in ast.walk(producer_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "os" and n.func.attr == "getrandom"]
    _require(len(producer_getrandom_calls) == 1, "V16_PRODUCTION_SOURCE_CALL_COUNT")
    producer_call = producer_getrandom_calls[0]
    _require(len(producer_call.args) == 2 and isinstance(producer_call.args[0], ast.Name) and producer_call.args[0].id == "SOURCE_REQUEST_BYTES" and isinstance(producer_call.args[1], ast.Constant) and producer_call.args[1].value == 0, "V16_PRODUCTION_SOURCE_CALL_BINDING")
    names = {n.attr for n in ast.walk(producer_tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(producer_tree) if isinstance(n, ast.Name)}
    _require("verify_source_invocation_evidence" not in names and "build_entropy_realization_proof" not in names, "V16_OLD_RECEIPT_PROOF_PATH")

    retry_tree = ast.parse(inspect.getsource(retry_same_assignment_bundle))
    retry_source_calls = [n for n in ast.walk(retry_tree) if isinstance(n, ast.Call) and ((isinstance(n.func, ast.Name) and n.func.id == "_invoke_production_source_once") or (isinstance(n.func, ast.Attribute) and n.func.attr == "getrandom"))]
    _require(len(retry_source_calls) == 0, "V16_RETRY_FRESH_ENTROPY")
    _require("raw" not in {name.lower() for name in retry_sig.parameters}, "V16_RETRY_ENTROPY_INJECTION")
    return {
        "production_source_parameters": [],
        "producer_parameters": list(producer_sig.parameters),
        "source_getrandom_call_count": 1,
        "source_request_bytes": SOURCE_REQUEST_BYTES,
        "source_flags": 0,
        "producer_source_call_count": 1,
        "producer_delegated_helper_call_count": 0,
        "retry_source_call_count": 0,
        "caller_entropy_in_production": False,
        "receipt_substitution_in_production": False,
        "source_primitive_runtime_identity_relation": primitive_attestation["runtime_identity_relation"],
    }


def verify_inherited_v15_controls(root: pathlib.Path = ROOT) -> dict[str, Any]:
    protected = v15.verify_protected_science(root)
    sutva = v15.verify_production_slot_sutva_binding(root)
    _require(protected["confirmation_status"] == "HARD_SEALED_NO_RUNTIME_ROUTE", "V16_CONFIRMATION_SEAL")
    _require(protected["future_program_authority"] == "NONE", "V16_FUTURE_ALPHA")
    return {
        "protected_science": protected,
        "production_slot_sutva": sutva,
        "registry_interpretation_contract_sha256": v15.registry_interpretation_contract_hash(),
        "finite_program_authority": "INHERITED_V15_ONE_CONSUMED_33_PLUS_33",
        "same_verdict_monitor_noninterference": True,
        "historical_unsupported_exposure": "UNKNOWN",
    }


def static_preflight(root: pathlib.Path = ROOT) -> dict[str, Any]:
    inherited = verify_inherited_v15_controls(root)
    noninjectable = verify_production_noninjectability()
    frozen_bindings = verify_frozen_production_source_bindings()
    sampler = v15.exact_sampler_count_proof()
    block = v15.fixed_block_conditional_rank_count_proof()
    _require(sampler == {"accepted": 65520, "rejected": 16, "per_rank_preimages": 91, "rank_count": 720}, "V16_STATIC_COUNTS")
    return {
        "schema": "CPDS_V5_V16_PRE_SCIENCE_STATIC_PREFLIGHT_V1",
        "scientific_design_id": DESIGN_ID,
        "design_semantic_hash": DESIGN_SEMANTIC_HASH,
        "design_attack_synthesis_id": DESIGN_ATTACK_SYNTHESIS_ID,
        "scientific_result": "NOT_ASSESSED_PRE_SCIENCE_ONLY",
        "scientific_variable_drift": False,
        "source_law_assumption": source_law_assumption(),
        "randomization_claim_scope": SOURCE_LAW_CLAIM,
        "receipt_semantics": RECEIPT_ROLE,
        "production_noninjectability": noninjectable,
        "frozen_production_source_bindings": frozen_bindings,
        "frozen_production_source_implementation_sha256": FROZEN_PRODUCTION_SOURCE_IMPLEMENTATION_SHA256,
        "sampler_count_proof": sampler,
        "fixed_block_conditional_rank_count_proof": block,
        "inherited_v15_controls": inherited,
        "model_calls": 0,
        "environment_calls": 0,
        "train_calls": 0,
        "calibration_calls": 0,
        "development_calls": 0,
        "confirmation_calls": 0,
    }
