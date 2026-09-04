#!/usr/bin/env python3
"""CPDS V5 V15 finite-program authority/proof layer.

PRE_SCIENCE only.  This module is import-safe and stdlib-only.  It never loads a
model/tokenizer, opens ALFWorld, consumes scientific outcomes, or authorizes an
experiment.  It implements the accepted V15 control invariants so a later,
separately authorized DEVELOPMENT run can be bound to one non-rerollable finite
program.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import math
import pathlib
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

ROOT = pathlib.Path(__file__).resolve().parent

SCHEMA = "PLANCARRY_CPDS_V5_V15_AUTHORITY_PROOF_V1"
DESIGN_ID = "8d5b89f9-1107-46ac-bbdb-630fa8dc14cf"
DESIGN_SEMANTIC_HASH = "c706942d4512d8e5a54cda67bdb247aae40e3a6afea6893aebd6cc5e47c36cbc"
DESIGN_ATTACK_SYNTHESIS_ID = "37886fda-b639-46df-99e1-a994941ad8c5"
BASE_COMMIT = "ccc831c69cbb76304ad88790be9b2056c636bb25"
BASE_TREE = "35f69a4b99d9021577bf76c21e219074a6753b6d"
PROTECTED_V5_SCIENCE_HASH = "3a730d7fca46ae1c9736d3546588fb08143212f0ba52e580f70b7ba450a189b2"
CHECKPOINT_SHA256 = "ab1a638a89db005b1346750c20ce8c1e7ea81cc3d1556af562a59fae8af503f9"
CALIBRATION_SHA256 = "5a511226e807987a5ea8e458f3d66eb4fb712afc86cf37aa95b066257b341eaa"
PACKET_CONTRACT_SHA256 = "0e388caa2e03bd4eb3186764851f1d04108df28cdf2acacb12a1af307764155b"
TRAINING_RECIPE_FILE_SHA256 = "861537f18959bcff736e7cbe30fdf07e128c7621ed5fb4e3522d598f77acab8c"
DEVELOPMENT_DRIVER_SHA256 = "6daf31543e63eb7aca2ae67c1f83577b6af8c2b08c1f1fdd0e70d532b2ddae02"
DEVELOPMENT_RUNTIME_SHA256 = "2d4933c75c69ecccb9495d10cc3568e9906bf57ca485b175956b290f74cd0da5"
PACKET_PRODUCER_SHA256 = "b7ecc835a481648cddb22e2cfba57514fd5b8240a651d4b0b86f0d1fd8a35d73"
PACKET_VALIDATOR_SHA256 = "446ed137758bd84d66bba8252ea1a5964497a52921cc5ffa427ddb0e9cbe2e8c"

DEVELOPMENT_N = 33
CONFIRMATION_N = 33
K_POSITIVE_REQUIRED = 22
CONFIRMATION_STATUS = "HARD_SEALED_NO_RUNTIME_ROUTE"
FUTURE_PROGRAM_AUTHORITY = "NONE"
EXACT_ARMS = (
    "NO_CARRY",
    "STATIC_ONESHOT",
    "STATIC_REPEAT",
    "ALIGNED_RECURSION",
    "TRANSITION_PERMUTED",
    "MATCHED_INFORMATION",
)

UINT16_SPACE = 1 << 16
PERMUTATION_COUNT = math.factorial(len(EXACT_ARMS))  # 720
UINT16_ACCEPT_LIMIT = (UINT16_SPACE // PERMUTATION_COUNT) * PERMUTATION_COUNT  # 65520
UINT16_REJECT_COUNT = UINT16_SPACE - UINT16_ACCEPT_LIMIT  # 16

PROTECTED_FILE_SHA256 = {
    "cpds_v5_packet_producer_v1.py": PACKET_PRODUCER_SHA256,
    "cpds_v5_packet_validator_v1.py": PACKET_VALIDATOR_SHA256,
    "cpds_v5_partition_v1.py": "0e9a007b6e8911a8432c385fbf0f6ba9ccc834467360a427c1c5c1e17a955439",
    "cpds_v5_predictive_recurrence_v1.py": "3a5a190de95c43d8bd4578f056e279c6217d53815a07527974eca5fe1d2f85c5",
    "cpds_v5_provenance_v1.py": "46341de616e5cf8b488eaa3726155cdcd00163e0dfc4a45d0669c4851b65ca8c",
    "cpds_development_runtime_v1.py": DEVELOPMENT_RUNTIME_SHA256,
    "cpds_development_driver_v1.py": DEVELOPMENT_DRIVER_SHA256,
    "results/design/plancarry_cpds_v5_training_recipe_a1_20260830.json": TRAINING_RECIPE_FILE_SHA256,
}

REGISTRY_SCHEMA = "PLANCARRY_CPDS_V5_V15_CANDIDATE_REGISTRY_V1"
REGISTRY_CONTRACT_SCHEMA = "PLANCARRY_CPDS_V5_V15_REGISTRY_INTERPRETATION_CONTRACT_V1"
REGISTRY_FIELDS = (
    "candidate_id",
    "source_graph_id",
    "structural_key_sha256",
    "static_descriptor_sha256",
    "phase_eligibility",
)
REGISTRY_PHASES = ("DEVELOPMENT", "CONFIRMATION")
REGISTRY_FIELD_TYPES = {field: "string" for field in REGISTRY_FIELDS}

SOURCE_CONTRACT_SCHEMA = "PLANCARRY_CPDS_V5_V15_UINT16_SOURCE_CONTRACT_V1"
RANDOMIZATION_CONTEXT_SCHEMA = "PLANCARRY_CPDS_V5_V15_RANDOMIZATION_CONTEXT_V1"
TRANSCRIPT_SCHEMA = "PLANCARRY_CPDS_V5_V15_ENTROPY_TRANSCRIPT_V1"
MONITOR_RELEASE_SCHEMA = "PLANCARRY_CPDS_V5_V15_MONITOR_RELEASE_V1"
PROGRAM_LEDGER_SCHEMA = "PLANCARRY_CPDS_V5_V15_PROGRAM_CONSUMPTION_LEDGER_V2"
PROGRAM_LEDGER_AUTHORITY_ID = "CPDS_V15_GLOBAL_NON_EQUIVOCATING_PROGRAM_LEDGER_V1"
ENTROPY_REALIZATION_PROOF_SCHEMA = "PLANCARRY_CPDS_V5_V15_ENTROPY_REALIZATION_PROOF_V2"
CONDITIONAL_LAW_PROOF_SCHEMA = "PLANCARRY_CPDS_V5_V15_CONDITIONAL_LAW_PROOF_V2"
BOUND_INVOCATION_SELECTOR_ID = "CONTEXT_DERIVED_SINGLE_INVOCATION_V1"
BOUND_INVOCATION_DERIVATION_ID = "SHA256_AUTHORITY_FAMILY_CONTEXT_V1"
BOUND_STREAM_PARTITION_SELECTOR_ID = "EXACT_FAMILY_ID_NAMESPACE_V1"
BOUND_TRANSDUCER_ID = "REJECT_GE_65520_THEN_FACTORADIC_UNRANK_S6_V1"

RANDOMIZATION_ANCESTOR_FIELDS = frozenset(
    {
        "assignment",
        "assignment_index",
        "arm_permutation",
        "entropy_word",
        "entropy_prefix",
        "rejection_history",
        "source_metadata",
        "source_latency",
        "source_health",
        "source_invocation",
        "transducer_state",
        "scientific_outcome",
    }
)


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sha_file(path: str | pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _nfc(value: str) -> str:
    _require(isinstance(value, str) and value != "", "REGISTRY_STRING")
    return unicodedata.normalize("NFC", value)


def _normalize_registry_entry(entry: Mapping[str, Any]) -> dict[str, str]:
    _require(isinstance(entry, Mapping) and set(entry) == set(REGISTRY_FIELDS), "REGISTRY_ENTRY_FIELDS")
    for key in REGISTRY_FIELDS:
        _require(type(entry[key]) is str, "REGISTRY_FIELD_TYPE:" + key)
    out = {k: _nfc(entry[k]) for k in REGISTRY_FIELDS}
    _require(_is_sha256(out["structural_key_sha256"]), "REGISTRY_STRUCTURAL_SHA")
    _require(_is_sha256(out["static_descriptor_sha256"]), "REGISTRY_DESCRIPTOR_SHA")
    _require(out["phase_eligibility"] in REGISTRY_PHASES, "REGISTRY_PHASE")
    return out


def canonical_registry(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [_normalize_registry_entry(x) for x in entries]
    rows.sort(key=lambda x: (x["candidate_id"], x["source_graph_id"], x["structural_key_sha256"]))
    _require(bool(rows), "REGISTRY_EMPTY")
    _require(len({r["candidate_id"] for r in rows}) == len(rows), "REGISTRY_CANDIDATE_DUPLICATE")
    _require(len({r["structural_key_sha256"] for r in rows}) == len(rows), "REGISTRY_STRUCTURAL_DUPLICATE")
    return {"schema": REGISTRY_SCHEMA, "entries": rows}


def registry_bytes(entries: Sequence[Mapping[str, Any]]) -> bytes:
    return canonical_bytes(canonical_registry(entries))


def registry_content_root(entries: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(registry_bytes(entries)).hexdigest()


def _source_hash(fn: Any) -> str:
    return hashlib.sha256(inspect.getsource(fn).encode("utf-8")).hexdigest()


def registry_interpretation_contract() -> dict[str, Any]:
    # The contract binds extensional semantics *and* the three independently named
    # interpreter entry points.  A compatibility parser cannot silently replace one.
    return {
        "schema": REGISTRY_CONTRACT_SCHEMA,
        "registry_schema": REGISTRY_SCHEMA,
        "encoding": "UTF-8",
        "unicode_normalization": "NFC",
        "serializer": "JSON_SORT_KEYS_COMPACT_ALLOW_NAN_FALSE_TRAILING_LF",
        "ordering": ["candidate_id", "source_graph_id", "structural_key_sha256"],
        "exact_fields": list(REGISTRY_FIELDS),
        "exact_field_types": dict(REGISTRY_FIELD_TYPES),
        "phase_values": list(REGISTRY_PHASES),
        "equivalence_adjudicator": "EXACT_NORMALIZED_RECORD_V1_NO_COMPATIBILITY_FALLBACK",
        "monitor_interpreter_sha256": _source_hash(monitor_interpret_registry),
        "selector_interpreter_sha256": _source_hash(selector_interpret_registry),
        "manifest_interpreter_sha256": _source_hash(manifest_interpret_registry),
    }


def registry_interpretation_contract_hash() -> str:
    return sha_obj(registry_interpretation_contract())


def _decode_registry_raw(raw: bytes) -> Any:
    _require(isinstance(raw, bytes) and raw, "REGISTRY_RAW")
    try:
        text = raw.decode("utf-8")
        return json.loads(text)
    except Exception as exc:
        raise ValueError("REGISTRY_PARSE") from exc


def monitor_interpret_registry(raw: bytes, expected_contract_hash: str) -> tuple[tuple[str, str, str, str, str], ...]:
    _require(expected_contract_hash == registry_interpretation_contract_hash(), "REGISTRY_CONTRACT_HASH")
    obj = _decode_registry_raw(raw)
    _require(isinstance(obj, Mapping) and obj.get("schema") == REGISTRY_SCHEMA and set(obj) == {"schema", "entries"}, "REGISTRY_ENVELOPE")
    canon = canonical_registry(obj["entries"])
    _require(raw == canonical_bytes(canon), "REGISTRY_NONCANONICAL_BYTES")
    return tuple(tuple(row[k] for k in REGISTRY_FIELDS) for row in canon["entries"])


def selector_interpret_registry(raw: bytes, expected_contract_hash: str) -> tuple[tuple[str, str, str, str, str], ...]:
    _require(expected_contract_hash == registry_interpretation_contract_hash(), "REGISTRY_CONTRACT_HASH")
    parsed = _decode_registry_raw(raw)
    _require(type(parsed) is dict and sorted(parsed.keys()) == ["entries", "schema"] and parsed["schema"] == REGISTRY_SCHEMA, "REGISTRY_ENVELOPE")
    rows = [_normalize_registry_entry(dict(x)) for x in parsed["entries"]]
    rows = sorted(rows, key=lambda r: (r["candidate_id"], r["source_graph_id"], r["structural_key_sha256"]))
    _require(len(rows) > 0 and len({r["candidate_id"] for r in rows}) == len(rows), "REGISTRY_CANDIDATE_DUPLICATE")
    _require(len({r["structural_key_sha256"] for r in rows}) == len(rows), "REGISTRY_STRUCTURAL_DUPLICATE")
    canon = {"schema": REGISTRY_SCHEMA, "entries": rows}
    _require(raw == canonical_bytes(canon), "REGISTRY_NONCANONICAL_BYTES")
    return tuple((r["candidate_id"], r["source_graph_id"], r["structural_key_sha256"], r["static_descriptor_sha256"], r["phase_eligibility"]) for r in rows)


def manifest_interpret_registry(raw: bytes, expected_contract_hash: str) -> tuple[tuple[str, str, str, str, str], ...]:
    _require(expected_contract_hash == registry_interpretation_contract_hash(), "REGISTRY_CONTRACT_HASH")
    obj = _decode_registry_raw(raw)
    _require(isinstance(obj, dict) and obj.get("schema") == REGISTRY_SCHEMA, "REGISTRY_ENVELOPE")
    entries = obj.get("entries")
    _require(isinstance(entries, list), "REGISTRY_ENTRIES")
    indexed: dict[str, dict[str, str]] = {}
    for raw_entry in entries:
        row = _normalize_registry_entry(raw_entry)
        _require(row["candidate_id"] not in indexed, "REGISTRY_CANDIDATE_DUPLICATE")
        indexed[row["candidate_id"]] = row
    rows = sorted(indexed.values(), key=lambda r: (r["candidate_id"], r["source_graph_id"], r["structural_key_sha256"]))
    _require(len({r["structural_key_sha256"] for r in rows}) == len(rows), "REGISTRY_STRUCTURAL_DUPLICATE")
    canon = {"schema": REGISTRY_SCHEMA, "entries": rows}
    _require(raw == canonical_bytes(canon), "REGISTRY_NONCANONICAL_BYTES")
    return tuple(tuple(r[k] for k in REGISTRY_FIELDS) for r in rows)


def verify_cross_interpreter_equivalence(raw: bytes, expected_contract_hash: str) -> tuple[tuple[str, str, str, str, str], ...]:
    a = monitor_interpret_registry(raw, expected_contract_hash)
    b = selector_interpret_registry(raw, expected_contract_hash)
    c = manifest_interpret_registry(raw, expected_contract_hash)
    _require(a == b == c, "REGISTRY_INTERPRETER_DIVERGENCE")
    return a


def verify_registry_root_binding(*, monitor_root: str, selector_root: str, manifest_root: str, monitor_contract_hash: str, selector_contract_hash: str, manifest_contract_hash: str) -> None:
    _require(_is_sha256(monitor_root) and monitor_root == selector_root == manifest_root, "REGISTRY_ROOT_IDENTITY")
    expected = registry_interpretation_contract_hash()
    _require(monitor_contract_hash == selector_contract_hash == manifest_contract_hash == expected, "REGISTRY_CONTRACT_IDENTITY")


def _bound_uint16_stream_implementation(words: Sequence[int]) -> tuple[int, ...]:
    # Executable source-side interface bound by exact source hash.  It is deliberately
    # identity-only: the external entropy authority supplies the raw iid uint16 stream;
    # this implementation may neither inspect another family nor transform/select words.
    out: list[int] = []
    for word in words:
        _require(type(word) is int and 0 <= word < UINT16_SPACE, "UINT16_WORD")
        out.append(word)
    return tuple(out)


def bound_entropy_implementation_sha256() -> str:
    return _source_hash(_bound_uint16_stream_implementation)


def bound_entropy_implementation_id() -> str:
    return sha_obj({"domain": "CPDS_V15_BOUND_UINT16_SOURCE_IMPLEMENTATION_V2", "source_sha256": bound_entropy_implementation_sha256()})


@dataclass(frozen=True)
class EntropySourceAuthority:
    authority_id: str
    implementation_id: str
    source_contract_hash: str
    invocation_selector_id: str
    invocation_identity_derivation_id: str
    stream_partition_selector_id: str
    source_to_assignment_transducer_id: str

    def canonical(self) -> dict[str, str]:
        d = {
            "authority_id": _nfc(self.authority_id),
            "implementation_id": _nfc(self.implementation_id),
            "source_contract_hash": self.source_contract_hash,
            "invocation_selector_id": _nfc(self.invocation_selector_id),
            "invocation_identity_derivation_id": _nfc(self.invocation_identity_derivation_id),
            "stream_partition_selector_id": _nfc(self.stream_partition_selector_id),
            "source_to_assignment_transducer_id": _nfc(self.source_to_assignment_transducer_id),
        }
        _require(_is_sha256(d["source_contract_hash"]), "SOURCE_CONTRACT_HASH")
        _require(d["implementation_id"] == bound_entropy_implementation_id(), "SOURCE_IMPLEMENTATION_UNBOUND")
        _require(d["invocation_selector_id"] == BOUND_INVOCATION_SELECTOR_ID, "SOURCE_INVOCATION_SELECTOR_UNBOUND")
        _require(d["invocation_identity_derivation_id"] == BOUND_INVOCATION_DERIVATION_ID, "SOURCE_INVOCATION_DERIVATION_UNBOUND")
        _require(d["stream_partition_selector_id"] == BOUND_STREAM_PARTITION_SELECTOR_ID, "SOURCE_STREAM_PARTITION_UNBOUND")
        _require(d["source_to_assignment_transducer_id"] == BOUND_TRANSDUCER_ID, "SOURCE_TRANSDUCER_UNBOUND")
        return d

    @property
    def authority_hash(self) -> str:
        return sha_obj(self.canonical())


def bound_entropy_source_authority(authority_id: str = "CPDS_V15_ENTROPY_AUTHORITY") -> EntropySourceAuthority:
    return EntropySourceAuthority(
        authority_id=authority_id,
        implementation_id=bound_entropy_implementation_id(),
        source_contract_hash=exact_uint16_source_contract()["contract_sha256"],
        invocation_selector_id=BOUND_INVOCATION_SELECTOR_ID,
        invocation_identity_derivation_id=BOUND_INVOCATION_DERIVATION_ID,
        stream_partition_selector_id=BOUND_STREAM_PARTITION_SELECTOR_ID,
        source_to_assignment_transducer_id=BOUND_TRANSDUCER_ID,
    )


def exact_uint16_source_contract() -> dict[str, Any]:
    contract = {
        "schema": SOURCE_CONTRACT_SCHEMA,
        "word_width_bits": 16,
        "word_domain": [0, UINT16_SPACE - 1],
        "conditional_uniformity": "EACH_NEXT_WORD_EXACT_UNIFORM_UINT16_GIVEN_COMPLETE_PRIOR_HISTORY",
        "family_stream_independence": "MUTUALLY_INDEPENDENT_ACROSS_EXACT_33_FAMILY_STREAMS",
        "source_switching_after_binding": False,
        "fresh_invocation_on_retry": False,
        "availability_latency_preview_selection": False,
        "transducer": "REJECT_GE_65520_THEN_FACTORADIC_UNRANK_S6_V1",
    }
    contract["contract_sha256"] = sha_obj(contract)
    return contract


def validate_source_contract(contract: Mapping[str, Any]) -> str:
    d = copy.deepcopy(dict(contract))
    expected = d.pop("contract_sha256", None)
    _require(_is_sha256(expected) and sha_obj(d) == expected, "SOURCE_CONTRACT_SELF_HASH")
    _require(d == {k: v for k, v in exact_uint16_source_contract().items() if k != "contract_sha256"}, "SOURCE_CONTRACT_SEMANTICS")
    return str(expected)


def verify_preobservation_binding(authority: EntropySourceAuthority, *, observed_source_facts: Sequence[str]) -> str:
    _require(len(observed_source_facts) == 0, "SOURCE_OBSERVED_BEFORE_BINDING")
    canonical = authority.canonical()
    _require(canonical["source_contract_hash"] == exact_uint16_source_contract()["contract_sha256"], "SOURCE_CONTRACT_AUTHORITY_BINDING")
    return authority.authority_hash


def factoradic_unrank_s6(rank: int) -> tuple[str, ...]:
    _require(isinstance(rank, int) and 0 <= rank < PERMUTATION_COUNT, "PERMUTATION_RANK")
    choices = list(EXACT_ARMS)
    out: list[str] = []
    r = rank
    for remaining in range(len(EXACT_ARMS), 0, -1):
        f = math.factorial(remaining - 1)
        idx, r = divmod(r, f)
        out.append(choices.pop(idx))
    _require(r == 0 and len(out) == len(EXACT_ARMS) and set(out) == set(EXACT_ARMS), "PERMUTATION_UNRANK")
    return tuple(out)


def uint16_to_rank(word: int) -> int | None:
    _require(isinstance(word, int) and 0 <= word < UINT16_SPACE, "UINT16_WORD")
    if word >= UINT16_ACCEPT_LIMIT:
        return None
    return word % PERMUTATION_COUNT


def exact_sampler_count_proof() -> dict[str, Any]:
    counts = [0] * PERMUTATION_COUNT
    rejected = 0
    for word in range(UINT16_SPACE):
        rank = uint16_to_rank(word)
        if rank is None:
            rejected += 1
        else:
            counts[rank] += 1
    _require(rejected == UINT16_REJECT_COUNT, "SAMPLER_REJECT_COUNT")
    _require(set(counts) == {UINT16_SPACE // PERMUTATION_COUNT}, "SAMPLER_RANK_COUNTS")
    return {"accepted": UINT16_ACCEPT_LIMIT, "rejected": rejected, "per_rank_preimages": counts[0], "rank_count": len(counts)}


def first_accepted_assignment(words: Sequence[int]) -> tuple[tuple[str, ...], tuple[int, ...]]:
    prefix: list[int] = []
    for word in words:
        _require(isinstance(word, int) and 0 <= word < UINT16_SPACE, "UINT16_WORD")
        prefix.append(word)
        rank = uint16_to_rank(word)
        if rank is not None:
            return factoradic_unrank_s6(rank), tuple(prefix)
    raise ValueError("ENTROPY_PREFIX_NO_ACCEPTED_WORD")


def build_entropy_realization_proof(*, family_ids: Sequence[str], family_stream_words: Mapping[str, Sequence[int]], source_contract: Mapping[str, Any], authority: EntropySourceAuthority, consumed_family_id: str, context_root: str, invocation_id: str) -> dict[str, Any]:
    validate_source_contract(source_contract)
    authority_hash = verify_preobservation_binding(authority, observed_source_facts=[])
    _require(_is_sha256(context_root), "ENTROPY_CONTEXT_ROOT")
    _require(invocation_id == derive_invocation_id(authority_hash=authority_hash, consumed_family_id=consumed_family_id, context_root=context_root), "ENTROPY_INVOCATION_ID")
    _require(len(family_ids) == DEVELOPMENT_N and len(set(family_ids)) == DEVELOPMENT_N, "RANDOMIZATION_FAMILY_IDS")
    _require(set(family_stream_words) == set(family_ids), "RANDOMIZATION_STREAM_SET")
    canonical_streams: list[dict[str, Any]] = []
    full_stream_hashes: list[str] = []
    for fid in family_ids:
        words = _bound_uint16_stream_implementation(family_stream_words[fid])
        _require(bool(words), "ENTROPY_STREAM_EMPTY")
        stream_hash = sha_obj(list(words))
        full_stream_hashes.append(stream_hash)
        canonical_streams.append({
            "family_id": _nfc(fid),
            "stream_namespace_id": sha_obj({"domain": "CPDS_V15_FAMILY_STREAM_NAMESPACE_V2", "invocation_id": invocation_id, "family_id": fid}),
            "words": list(words),
            "stream_sha256": stream_hash,
        })
    # Conservative deterministic anti-dependence witness: a maximally coupled repeated
    # concrete stream is inadmissible even though accidental finite collisions can occur
    # under the ideal law.  The exact law itself is bound to the audited source primitive
    # and disjoint family namespaces below, not inferred from marginal declarations.
    _require(len(set(full_stream_hashes)) == DEVELOPMENT_N, "ENTROPY_STREAM_DEPENDENCE_WITNESS")
    proof = {
        "schema": ENTROPY_REALIZATION_PROOF_SCHEMA,
        "authority": authority.canonical(),
        "authority_hash": authority_hash,
        "source_implementation_sha256": bound_entropy_implementation_sha256(),
        "source_contract_hash": validate_source_contract(source_contract),
        "consumed_family_id": _nfc(consumed_family_id),
        "context_root": context_root,
        "invocation_id": invocation_id,
        "family_ids": [_nfc(x) for x in family_ids],
        "family_streams": canonical_streams,
        "stream_partition_rule": "DISJOINT_EXACT_FAMILY_ID_NAMESPACE_V2",
        "conditional_word_law": "EXACT_UNIFORM_UINT16_GIVEN_COMPLETE_PRIOR_REJECTION_HISTORY",
        "cross_family_law": "PRODUCT_INDEPENDENT_EXACT_33_STREAM_NAMESPACES",
        "transducer_id": BOUND_TRANSDUCER_ID,
        "sampler_count_proof": exact_sampler_count_proof(),
        "verifier_sha256": _source_hash(verify_entropy_realization_proof),
    }
    proof["proof_sha256"] = sha_obj(proof)
    return proof


def verify_entropy_realization_proof(proof: Mapping[str, Any]) -> str:
    d = copy.deepcopy(dict(proof))
    claimed = d.pop("proof_sha256", None)
    _require(_is_sha256(claimed) and sha_obj(d) == claimed, "ENTROPY_REALIZATION_PROOF_SELF_HASH")
    required = {"schema","authority","authority_hash","source_implementation_sha256","source_contract_hash","consumed_family_id","context_root","invocation_id","family_ids","family_streams","stream_partition_rule","conditional_word_law","cross_family_law","transducer_id","sampler_count_proof","verifier_sha256"}
    _require(set(d) == required and d["schema"] == ENTROPY_REALIZATION_PROOF_SCHEMA, "ENTROPY_REALIZATION_PROOF_FIELDS")
    a = d["authority"]
    _require(isinstance(a, Mapping), "ENTROPY_REALIZATION_AUTHORITY")
    authority = EntropySourceAuthority(**dict(a))
    _require(authority.authority_hash == d["authority_hash"], "ENTROPY_REALIZATION_AUTHORITY_HASH")
    _require(d["source_implementation_sha256"] == bound_entropy_implementation_sha256(), "ENTROPY_REALIZATION_IMPLEMENTATION")
    _require(d["source_contract_hash"] == exact_uint16_source_contract()["contract_sha256"], "ENTROPY_REALIZATION_SOURCE_CONTRACT")
    _require(d["invocation_id"] == derive_invocation_id(authority_hash=d["authority_hash"], consumed_family_id=d["consumed_family_id"], context_root=d["context_root"]), "ENTROPY_REALIZATION_INVOCATION")
    _require(d["verifier_sha256"] == _source_hash(verify_entropy_realization_proof), "ENTROPY_REALIZATION_VERIFIER")
    _require(d["stream_partition_rule"] == "DISJOINT_EXACT_FAMILY_ID_NAMESPACE_V2", "ENTROPY_REALIZATION_PARTITION_RULE")
    _require(d["conditional_word_law"] == "EXACT_UNIFORM_UINT16_GIVEN_COMPLETE_PRIOR_REJECTION_HISTORY", "ENTROPY_REALIZATION_CONDITIONAL_LAW")
    _require(d["cross_family_law"] == "PRODUCT_INDEPENDENT_EXACT_33_STREAM_NAMESPACES", "ENTROPY_REALIZATION_CROSS_FAMILY_LAW")
    _require(d["transducer_id"] == BOUND_TRANSDUCER_ID and d["sampler_count_proof"] == exact_sampler_count_proof(), "ENTROPY_REALIZATION_TRANSDUCER")
    family_ids = d["family_ids"]
    streams = d["family_streams"]
    _require(isinstance(family_ids, list) and len(family_ids) == DEVELOPMENT_N and len(set(family_ids)) == DEVELOPMENT_N, "ENTROPY_REALIZATION_FAMILIES")
    _require(isinstance(streams, list) and len(streams) == DEVELOPMENT_N, "ENTROPY_REALIZATION_STREAMS")
    seen_ids, seen_hashes, seen_namespaces = set(), set(), set()
    for row in streams:
        _require(isinstance(row, Mapping) and set(row) == {"family_id","stream_namespace_id","words","stream_sha256"}, "ENTROPY_REALIZATION_STREAM_FIELDS")
        fid = row["family_id"]
        _require(type(fid) is str and fid in family_ids and fid not in seen_ids, "ENTROPY_REALIZATION_STREAM_FAMILY")
        words = _bound_uint16_stream_implementation(row["words"])
        expected_hash = sha_obj(list(words))
        expected_ns = sha_obj({"domain": "CPDS_V15_FAMILY_STREAM_NAMESPACE_V2", "invocation_id": d["invocation_id"], "family_id": fid})
        _require(row["stream_sha256"] == expected_hash, "ENTROPY_REALIZATION_STREAM_HASH")
        _require(row["stream_namespace_id"] == expected_ns, "ENTROPY_REALIZATION_STREAM_NAMESPACE")
        seen_ids.add(fid); seen_hashes.add(expected_hash); seen_namespaces.add(expected_ns)
    _require(seen_ids == set(family_ids) and len(seen_namespaces) == DEVELOPMENT_N, "ENTROPY_REALIZATION_STREAM_COVERAGE")
    _require(len(seen_hashes) == DEVELOPMENT_N, "ENTROPY_STREAM_DEPENDENCE_WITNESS")
    return str(claimed)


def build_assignment_vector(*, family_ids: Sequence[str], family_stream_words: Mapping[str, Sequence[int]], source_contract: Mapping[str, Any], authority: EntropySourceAuthority, consumed_family_id: str, context_root: str, invocation_id: str) -> tuple[dict[str, Any], ...]:
    proof = build_entropy_realization_proof(family_ids=family_ids, family_stream_words=family_stream_words, source_contract=source_contract, authority=authority, consumed_family_id=consumed_family_id, context_root=context_root, invocation_id=invocation_id)
    proof_hash = verify_entropy_realization_proof(proof)
    out: list[dict[str, Any]] = []
    for i, fid in enumerate(family_ids):
        perm, consumed = first_accepted_assignment(family_stream_words[fid])
        out.append({"family_index": i, "family_id": fid, "arm_permutation": list(perm), "consumed_word_count": len(consumed), "consumed_words_sha256": sha_obj(list(consumed)), "entropy_realization_proof_sha256": proof_hash})
    return tuple(out)


def randomization_context_root(context: Mapping[str, Any]) -> str:
    required = {
        "schema",
        "consumed_family_id",
        "registry_content_root",
        "registry_interpretation_contract_hash",
        "development_family_ids",
        "donor_maps_sha256",
        "family_states_sha256",
        "execution_descriptors_sha256",
        "arm_semantics_sha256",
        "evaluator_bytes_sha256",
        "nonassignment_nuisance_sha256",
        "release_admission_contract_sha256",
        "entropy_authority_hash",
        "source_contract_hash",
        "source_to_assignment_transducer_id",
    }
    _require(set(context) == required and context["schema"] == RANDOMIZATION_CONTEXT_SCHEMA, "RANDOMIZATION_CONTEXT_FIELDS")
    _require(len(context["development_family_ids"]) == DEVELOPMENT_N and len(set(context["development_family_ids"])) == DEVELOPMENT_N, "RANDOMIZATION_CONTEXT_FAMILIES")
    for key in required - {"schema", "consumed_family_id", "development_family_ids", "source_to_assignment_transducer_id"}:
        _require(_is_sha256(context[key]), "RANDOMIZATION_CONTEXT_HASH:" + key)
    _require(context["registry_interpretation_contract_hash"] == registry_interpretation_contract_hash(), "RANDOMIZATION_REGISTRY_CONTRACT")
    _require(context["source_contract_hash"] == exact_uint16_source_contract()["contract_sha256"], "RANDOMIZATION_SOURCE_CONTRACT")
    return sha_obj(dict(context))


def derive_invocation_id(*, authority_hash: str, consumed_family_id: str, context_root: str) -> str:
    _require(_is_sha256(authority_hash) and _is_sha256(context_root), "INVOCATION_BINDING_HASH")
    return sha_obj({"domain": "CPDS_V15_ENTROPY_INVOCATION_V1", "authority_hash": authority_hash, "consumed_family_id": consumed_family_id, "context_root": context_root})


@dataclass(frozen=True)
class EntropyTranscript:
    authority_hash: str
    context_root: str
    invocation_id: str
    words: tuple[int, ...] = ()

    def append(self, word: int) -> "EntropyTranscript":
        _require(isinstance(word, int) and 0 <= word < UINT16_SPACE, "UINT16_WORD")
        return replace(self, words=self.words + (word,))

    def canonical(self) -> dict[str, Any]:
        _require(_is_sha256(self.authority_hash) and _is_sha256(self.context_root) and _is_sha256(self.invocation_id), "TRANSCRIPT_BINDING")
        return {"schema": TRANSCRIPT_SCHEMA, "authority_hash": self.authority_hash, "context_root": self.context_root, "invocation_id": self.invocation_id, "words": list(self.words)}

    @property
    def transcript_hash(self) -> str:
        return sha_obj(self.canonical())


def resume_same_transcript(existing: EntropyTranscript, *, authority_hash: str, context_root: str, invocation_id: str, replayed_prefix: Sequence[int]) -> EntropyTranscript:
    _require(existing.authority_hash == authority_hash, "RETRY_AUTHORITY_SWITCH")
    _require(existing.context_root == context_root, "RETRY_CONTEXT_SWITCH")
    _require(existing.invocation_id == invocation_id, "RETRY_INVOCATION_SWITCH")
    _require(tuple(replayed_prefix) == existing.words, "RETRY_TRANSCRIPT_PREFIX_MISMATCH")
    return existing


@dataclass(frozen=True)
class FiniteProgramAuthority:
    consumed_family_fingerprint: str
    consumption_record_hash: str
    current_program_n_development: int = DEVELOPMENT_N
    current_program_n_confirmation: int = CONFIRMATION_N

    def validate(self) -> None:
        _require(_is_sha256(self.consumed_family_fingerprint), "FAMILY_FINGERPRINT")
        _require(_is_sha256(self.consumption_record_hash), "FAMILY_CONSUMPTION_RECORD")
        _require(self.current_program_n_development == DEVELOPMENT_N and self.current_program_n_confirmation == CONFIRMATION_N, "FINITE_PROGRAM_SIZE")


def canonical_consumption_ledger_record(*, equivalence_defining_fields: Mapping[str, Any]) -> dict[str, Any]:
    required = {"checkpoint", "calibration", "estimand", "candidate_cohort_question", "arms_controls", "endpoints", "decision_statistics", "thresholds", "no_rescue", "population_definition"}
    _require(set(equivalence_defining_fields) == required, "EQUIVALENCE_FIELDS")
    fingerprint = sha_obj(dict(equivalence_defining_fields))
    record = {
        "schema": PROGRAM_LEDGER_SCHEMA,
        "ledger_authority_id": PROGRAM_LEDGER_AUTHORITY_ID,
        "family_fingerprint": fingerprint,
        "ledger_record_id": sha_obj({"domain": "CPDS_V15_SINGLE_CONSUMPTION_LEDGER_RECORD_V2", "ledger_authority_id": PROGRAM_LEDGER_AUTHORITY_ID, "family_fingerprint": fingerprint}),
        "one_use_ordinal": 1,
        "state": "CONSUMED",
        "development_n": DEVELOPMENT_N,
        "confirmation_n": CONFIRMATION_N,
    }
    record["record_sha256"] = sha_obj(record)
    return record


def verify_consumption_ledger_record(record: Mapping[str, Any], *, equivalence_defining_fields: Mapping[str, Any]) -> str:
    expected = canonical_consumption_ledger_record(equivalence_defining_fields=equivalence_defining_fields)
    _require(dict(record) == expected, "PROGRAM_LEDGER_NON_EQUIVOCATION_OR_ONE_USE")
    return expected["record_sha256"]


def consume_current_program(*, equivalence_defining_fields: Mapping[str, Any], ledger_record: Mapping[str, Any]) -> FiniteProgramAuthority:
    record_hash = verify_consumption_ledger_record(ledger_record, equivalence_defining_fields=equivalence_defining_fields)
    fingerprint = sha_obj(dict(equivalence_defining_fields))
    return FiniteProgramAuthority(fingerprint, record_hash)


def validate_same_consumed_program(authority: FiniteProgramAuthority, *, equivalence_defining_fields: Mapping[str, Any]) -> None:
    authority.validate()
    _require(sha_obj(dict(equivalence_defining_fields)) == authority.consumed_family_fingerprint, "CURRENT_PROGRAM_MUTATION_OR_ALIAS_RESET")


def assess_future_study(*, requests_authority_from_v15: bool, conditions_on_v15_status: bool, separate_authority_frozen_before_earliest_conditioned_v15_status: bool) -> str:
    if requests_authority_from_v15:
        raise ValueError("V15_FUTURE_PROGRAM_AUTHORITY_NONE")
    if conditions_on_v15_status and not separate_authority_frozen_before_earliest_conditioned_v15_status:
        raise ValueError("POST_STATUS_SUCCESSOR_RULE_INVALID")
    return "SEPARATE_SCIENCE_NO_V15_ALPHA_OR_EVIDENCE"


def conditional_law_verifier_sha256() -> str:
    return _source_hash(verify_conditional_law_proof)


def make_conditional_law_proof(*, event_name: str, depends_on: Iterable[str], context_root: str, transcript: EntropyTranscript, entropy_realization_proof: Mapping[str, Any], release_event_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entropy_proof_hash = verify_entropy_realization_proof(entropy_realization_proof)
    deps = tuple(sorted(_nfc(x) for x in depends_on))
    _require(bool(event_name) and _is_sha256(context_root), "CONDITIONAL_LAW_BINDING")
    _require(transcript.context_root == context_root, "CONDITIONAL_LAW_TRANSCRIPT_CONTEXT")
    _require(transcript.authority_hash == entropy_realization_proof["authority_hash"], "CONDITIONAL_LAW_TRANSCRIPT_AUTHORITY")
    _require(transcript.invocation_id == entropy_realization_proof["invocation_id"], "CONDITIONAL_LAW_TRANSCRIPT_INVOCATION")
    proof = {
        "schema": CONDITIONAL_LAW_PROOF_SCHEMA,
        "event_name": _nfc(event_name),
        "depends_on": list(deps),
        "context_root": context_root,
        "transcript": transcript.canonical(),
        "transcript_hash": transcript.transcript_hash,
        "entropy_realization_proof": copy.deepcopy(dict(entropy_realization_proof)),
        "entropy_realization_proof_hash": entropy_proof_hash,
        "release_event_history": copy.deepcopy(list(release_event_history)),
        "release_event_history_sha256": sha_obj(list(release_event_history)),
        "preserved_law": "EXACT_CONDITIONAL_PRODUCT_UNIFORM_S6_POWER_33",
        "verifier_sha256": conditional_law_verifier_sha256(),
    }
    proof["proof_sha256"] = sha_obj(proof)
    return proof


def verify_conditional_law_proof(proof: Mapping[str, Any], *, event_name: str, depends_on: Iterable[str], context_root: str, transcript: EntropyTranscript, release_event_history: Sequence[Mapping[str, Any]]) -> str:
    d = copy.deepcopy(dict(proof))
    claimed = d.pop("proof_sha256", None)
    _require(_is_sha256(claimed) and sha_obj(d) == claimed, "CONDITIONAL_LAW_PROOF_SELF_HASH")
    required = {"schema","event_name","depends_on","context_root","transcript","transcript_hash","entropy_realization_proof","entropy_realization_proof_hash","release_event_history","release_event_history_sha256","preserved_law","verifier_sha256"}
    _require(set(d) == required and d["schema"] == CONDITIONAL_LAW_PROOF_SCHEMA, "CONDITIONAL_LAW_PROOF_FIELDS")
    deps = sorted(_nfc(x) for x in depends_on)
    _require(d["event_name"] == event_name and d["depends_on"] == deps, "CONDITIONAL_LAW_EVENT_BINDING")
    _require(d["context_root"] == context_root == transcript.context_root, "CONDITIONAL_LAW_CONTEXT_BINDING")
    _require(d["transcript"] == transcript.canonical() and d["transcript_hash"] == transcript.transcript_hash, "CONDITIONAL_LAW_TRANSCRIPT_BINDING")
    _require(d["release_event_history"] == list(release_event_history) and d["release_event_history_sha256"] == sha_obj(list(release_event_history)), "CONDITIONAL_LAW_HISTORY_BINDING")
    entropy_hash = verify_entropy_realization_proof(d["entropy_realization_proof"])
    _require(d["entropy_realization_proof_hash"] == entropy_hash, "CONDITIONAL_LAW_ENTROPY_PROOF_BINDING")
    _require(d["entropy_realization_proof"]["context_root"] == context_root, "CONDITIONAL_LAW_ENTROPY_CONTEXT")
    _require(d["entropy_realization_proof"]["authority_hash"] == transcript.authority_hash and d["entropy_realization_proof"]["invocation_id"] == transcript.invocation_id, "CONDITIONAL_LAW_ENTROPY_TRANSCRIPT")
    _require(d["preserved_law"] == "EXACT_CONDITIONAL_PRODUCT_UNIFORM_S6_POWER_33", "CONDITIONAL_LAW_RESULT")
    _require(d["verifier_sha256"] == conditional_law_verifier_sha256(), "CONDITIONAL_LAW_VERIFIER_BINDING")
    return str(claimed)


def validate_release_event(*, event_name: str, depends_on: Iterable[str], fixed_before_entropy: bool, conditional_law_proof: Mapping[str, Any] | None = None, context_root: str | None = None, transcript: EntropyTranscript | None = None, release_event_history: Sequence[Mapping[str, Any]] = ()) -> str:
    deps = frozenset(_nfc(x) for x in depends_on)
    _require(bool(event_name), "RELEASE_EVENT_NAME")
    if fixed_before_entropy:
        _require(not (deps & RANDOMIZATION_ANCESTOR_FIELDS), "PREENTROPY_EVENT_RANDOMIZATION_DEPENDENCY")
        _require(conditional_law_proof is None, "PREENTROPY_PROOF_UNEXPECTED")
        return "PRE_ENTROPY_FIXED"
    _require(conditional_law_proof is not None and context_root is not None and transcript is not None, "POSTENTROPY_FULL_HISTORY_LAW_PROOF_REQUIRED")
    verify_conditional_law_proof(conditional_law_proof, event_name=event_name, depends_on=deps, context_root=context_root, transcript=transcript, release_event_history=release_event_history)
    return "POST_ENTROPY_CONDITIONAL_LAW_PROVED"


def monitor_visible_release(verdict: str, *, hidden_witness: Any = None, hidden_authenticator: Any = None) -> bytes:
    # hidden_* are deliberately ignored.  They are accepted only so tests/reviewers can
    # vary hidden state and prove the design-visible bytes are same-verdict invariant.
    _require(verdict in {"PASS", "FAIL"}, "MONITOR_VERDICT")
    return canonical_bytes({"schema": MONITOR_RELEASE_SCHEMA, "verdict": verdict})


def verify_production_slot_sutva_binding(root: pathlib.Path = ROOT) -> dict[str, Any]:
    driver = root / "cpds_development_driver_v1.py"
    _require(driver.is_file() and sha_file(driver) == DEVELOPMENT_DRIVER_SHA256, "PRODUCTION_DRIVER_DRIFT")
    tree = ast.parse(driver.read_text(encoding="utf-8"))
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    _require("_slot_replay_guard" in funcs and "_execute_family" in funcs, "PRODUCTION_SUTVA_SYMBOLS")
    slot_src = ast.get_source_segment(driver.read_text(encoding="utf-8"), funcs["_slot_replay_guard"]) or ""
    fam_src = ast.get_source_segment(driver.read_text(encoding="utf-8"), funcs["_execute_family"]) or ""
    _require("runtime_factory(str(game_file))" in slot_src and "env.close()" in slot_src, "PRODUCTION_SLOT_FRESH_RUNTIME_CLOSE")
    _require("for slot_index, arm in enumerate(arm_order):" in fam_src, "PRODUCTION_SLOT_LOOP")
    _require("_slot_replay_guard(runtime_factory, game, carrier, witness, branch_candidates)" in fam_src, "PRODUCTION_SLOT_GUARD_CALL")
    _require("slot_records.append" in fam_src, "PRODUCTION_SLOT_RECORD")
    return {"driver_sha256": DEVELOPMENT_DRIVER_SHA256, "fresh_runtime_per_slot": True, "close_per_slot": True, "slot_loop_bound_to_assignment_order": True}


def verify_protected_science(root: pathlib.Path = ROOT) -> dict[str, Any]:
    for rel, expected in PROTECTED_FILE_SHA256.items():
        p = root / rel
        _require(p.is_file() and sha_file(p) == expected, "PROTECTED_FILE_DRIFT:" + rel)
    # Import-safe constants only: these modules have no model/tokenizer/environment side effects.
    import cpds_development_runtime_v1 as rt
    import cpds_v5_packet_validator_v1 as validator
    _require(tuple(rt.EXACT_ARMS) == EXACT_ARMS, "PROTECTED_ARMS_DRIFT")
    _require(validator.PROTECTED_SPEC_SHA256 == PROTECTED_V5_SCIENCE_HASH, "PROTECTED_SCIENCE_HASH_DRIFT")
    _require(validator.CONTRACT_SHA256 == PACKET_CONTRACT_SHA256, "PACKET_CONTRACT_DRIFT")
    return {
        "protected_file_count": len(PROTECTED_FILE_SHA256),
        "protected_v5_science_hash": PROTECTED_V5_SCIENCE_HASH,
        "packet_contract_sha256": PACKET_CONTRACT_SHA256,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "calibration_sha256": CALIBRATION_SHA256,
        "development_n": DEVELOPMENT_N,
        "confirmation_n": CONFIRMATION_N,
        "k_positive_required": K_POSITIVE_REQUIRED,
        "confirmation_status": CONFIRMATION_STATUS,
        "future_program_authority": FUTURE_PROGRAM_AUTHORITY,
    }


def static_preflight(root: pathlib.Path = ROOT) -> dict[str, Any]:
    protected = verify_protected_science(root)
    sutva = verify_production_slot_sutva_binding(root)
    sampler = exact_sampler_count_proof()
    registry_contract = registry_interpretation_contract()
    source_contract = exact_uint16_source_contract()
    return {
        "schema": SCHEMA,
        "scientific_design_id": DESIGN_ID,
        "design_semantic_hash": DESIGN_SEMANTIC_HASH,
        "scientific_result": "NOT_ASSESSED_PRE_SCIENCE_ONLY",
        "scientific_variable_drift": False,
        "protected_science": protected,
        "production_sutva_binding": sutva,
        "registry_interpretation_contract_hash": sha_obj(registry_contract),
        "source_contract_sha256": source_contract["contract_sha256"],
        "entropy_source_implementation_sha256": bound_entropy_implementation_sha256(),
        "conditional_law_verifier_sha256": conditional_law_verifier_sha256(),
        "program_consumption_ledger_schema": PROGRAM_LEDGER_SCHEMA,
        "uint16_sampler_proof": sampler,
        "execution_counters": {
            "model_loads": 0,
            "tokenizer_loads": 0,
            "model_forwards": 0,
            "environment_execution": 0,
            "train": 0,
            "calibration_fitting": 0,
            "development": 0,
            "confirmation": 0,
            "provider_lifecycle": 0,
            "research_decisions": 0,
            "scientific_outcomes_opened": 0,
        },
    }


if __name__ == "__main__":
    print(json.dumps(static_preflight(), sort_keys=True, separators=(",", ":")))
