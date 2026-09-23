"""PlanLatch v7.20 membership-blind pre-science control layer.

Engineering-only module.  It deliberately exposes no live beacon reader, no
real confirmatory-authority mutation, no model execution, and no selected-body
reader.  Production activation is a separate post-fidelity transition.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

DESIGN_ID = "2f2edabb-e86c-4d24-8233-87e681270f50"
SEMANTIC_HASH = "d7b7022b8a38e93c884b8a5fce6f01d0ae0007ab5ab52571040faa47b4129263"
FAMILY_KEY = "PLANCARRY_PLANLATCH_SOURCE_RELAY_EXACT36_CONFIRMATORY_FAMILY"
CONTROL_VERSION = "planlatch-v7.20-controls-v1"
COMPARATOR_VERSION = "exact-body-sha256-eq-neq-unknown-v1"
PARTITION_COUNTS = (("FIT", 12), ("PILOT", 8), ("SUPPORT", 12), ("CROSS_REALIZATION", 4))
TOTAL_SELECTED = 36


class ControlViolation(ValueError):
    pass


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(stable_json(value).encode("utf-8"))


def _require_sha(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ControlViolation(f"{name} must be lowercase sha256")
    return value


class EqState(str, Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class UniverseCandidate:
    canonical_identity: str
    exact_body_sha256: str | None
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.canonical_identity:
            raise ControlViolation("canonical_identity required")
        if self.exact_body_sha256 is not None:
            _require_sha(self.exact_body_sha256, "exact_body_sha256")
        if self.canonical_identity in self.aliases:
            raise ControlViolation("canonical identity cannot repeat as alias")
        if len(set(self.aliases)) != len(self.aliases):
            raise ControlViolation("duplicate aliases")


def compare_exact_body(a: UniverseCandidate, b: UniverseCandidate) -> EqState:
    if a.exact_body_sha256 is None or b.exact_body_sha256 is None:
        return EqState.UNKNOWN
    return EqState.EQ if a.exact_body_sha256 == b.exact_body_sha256 else EqState.NEQ


@dataclass(frozen=True)
class UniverseReceipt:
    canonical_entries: tuple[str, ...]
    canonical_body_hashes: tuple[str, ...]
    collapsed_aliases: Mapping[str, tuple[str, ...]]
    excluded_unknowns: tuple[str, ...]
    comparator_version: str
    ordered_universe_hash: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "canonical_entries": list(self.canonical_entries),
            "canonical_body_hashes": list(self.canonical_body_hashes),
            "collapsed_aliases": {k: list(v) for k, v in sorted(self.collapsed_aliases.items())},
            "excluded_unknowns": list(self.excluded_unknowns),
            "comparator_version": self.comparator_version,
            "ordered_universe_hash": self.ordered_universe_hash,
        }


def build_universe_receipt(candidates: Sequence[UniverseCandidate]) -> UniverseReceipt:
    if not candidates:
        raise ControlViolation("candidate universe must be nonempty")
    seen_ids: set[str] = set()
    unknown: list[str] = []
    by_hash: dict[str, list[UniverseCandidate]] = {}
    for c in candidates:
        all_ids = (c.canonical_identity,) + tuple(c.aliases)
        if any(x in seen_ids for x in all_ids):
            raise ControlViolation("identity/alias duplicated across candidate rows")
        seen_ids.update(all_ids)
        if c.exact_body_sha256 is None:
            unknown.extend(all_ids)
            continue
        by_hash.setdefault(c.exact_body_sha256, []).append(c)

    canonical: list[tuple[str, str, tuple[str, ...]]] = []
    for body_hash, rows in sorted(by_hash.items()):
        ids: list[str] = []
        for row in rows:
            ids.extend((row.canonical_identity,) + tuple(row.aliases))
        ids = sorted(set(ids))
        chosen = ids[0]
        aliases = tuple(x for x in ids if x != chosen)
        canonical.append((chosen, body_hash, aliases))
    canonical.sort(key=lambda x: x[0])
    entries = tuple(x[0] for x in canonical)
    body_hashes = tuple(x[1] for x in canonical)
    collapsed = {x[0]: x[2] for x in canonical if x[2]}
    payload = {
        "comparator_version": COMPARATOR_VERSION,
        "entries": [{"id": i, "body_sha256": h} for i, h in zip(entries, body_hashes)],
        "excluded_unknowns": sorted(set(unknown)),
    }
    return UniverseReceipt(
        entries,
        body_hashes,
        collapsed,
        tuple(sorted(set(unknown))),
        COMPARATOR_VERSION,
        sha256_json(payload),
    )


class AttemptState(str, Enum):
    CONSUMED_WAITING_BEACON = "CONSUMED_WAITING_BEACON"
    MEMBERSHIP_RECEIPT = "MEMBERSHIP_RECEIPT"
    RECEIPT_DERIVATION_FAILURE = "RECEIPT_DERIVATION_FAILURE"
    TERMINAL_NONEXECUTION = "TERMINAL_NONEXECUTION"
    EXECUTED_RESULT = "EXECUTED_RESULT"


@dataclass(frozen=True)
class ClaimFamilyFingerprint:
    normalized_estimand_hash: str
    normalized_universe_semantics_hash: str
    normalized_gate_semantics_hash: str
    normalized_claim_scope_hash: str

    def __post_init__(self) -> None:
        _require_sha(self.normalized_estimand_hash, "normalized_estimand_hash")
        _require_sha(self.normalized_universe_semantics_hash, "normalized_universe_semantics_hash")
        _require_sha(self.normalized_gate_semantics_hash, "normalized_gate_semantics_hash")
        _require_sha(self.normalized_claim_scope_hash, "normalized_claim_scope_hash")

    @property
    def sha256(self) -> str:
        return sha256_json(dataclasses.asdict(self))


@dataclass
class TestOnlyAttemptLedger:
    """Offline test oracle for the frozen registration-consumed semantics.

    This is intentionally incapable of mutating Research OS production state.
    """
    family_key: str = FAMILY_KEY
    test_only: bool = True
    state: AttemptState | None = None
    fingerprint_sha256: str | None = None
    receipt_sha256: str | None = None

    def _require_test(self) -> None:
        if self.test_only is not True:
            raise ControlViolation("live authority registration is disabled in pre-science implementation")

    def register_consumed(self, fingerprint: ClaimFamilyFingerprint) -> AttemptState:
        self._require_test()
        if self.state is not None:
            raise ControlViolation("claim-family authority already consumed")
        self.fingerprint_sha256 = fingerprint.sha256
        self.state = AttemptState.CONSUMED_WAITING_BEACON
        return self.state

    def assert_same_family_nonconfirmatory(self, successor: ClaimFamilyFingerprint) -> None:
        self._require_test()
        if self.state is None:
            raise ControlViolation("no consumed ancestor")
        if successor.sha256 == self.fingerprint_sha256:
            raise ControlViolation("equivalent successor is SAME_FAMILY_NONCONFIRMATORY")
        # v7.20 is fail-closed: this local helper has no NEW_FAMILY certificate surface.
        raise ControlViolation("successor family classification is fail-closed before production certificate support")

    def finalize(self, state: AttemptState, receipt_sha256: str | None = None) -> None:
        self._require_test()
        if self.state is None:
            raise ControlViolation("attempt must be consumed at registration first")
        if state == AttemptState.CONSUMED_WAITING_BEACON:
            raise ControlViolation("final state required")
        if receipt_sha256 is not None:
            _require_sha(receipt_sha256, "receipt_sha256")
        self.state = state
        self.receipt_sha256 = receipt_sha256


@dataclass(frozen=True)
class OfflineBeaconRecord:
    chain: str
    round: int
    randomness_sha256: str
    proof_sha256: str
    verified_offline: bool

    def __post_init__(self) -> None:
        if not self.chain or not isinstance(self.round, int) or self.round < 0:
            raise ControlViolation("invalid offline beacon identity")
        _require_sha(self.randomness_sha256, "randomness_sha256")
        _require_sha(self.proof_sha256, "proof_sha256")
        if self.verified_offline is not True:
            raise ControlViolation("offline beacon must be preverified")


@dataclass(frozen=True)
class MembershipReceipt:
    selection_key: str
    selected_identities: tuple[str, ...]
    partition_by_identity: Mapping[str, str]
    universe_hash: str
    receipt_sha256: str

    def payload_without_hash(self) -> Mapping[str, Any]:
        return {
            "selection_key": self.selection_key,
            "selected_identities": list(self.selected_identities),
            "partition_by_identity": dict(sorted(self.partition_by_identity.items())),
            "universe_hash": self.universe_hash,
        }


def derive_offline_test_receipt(
    *,
    family_fingerprint: ClaimFamilyFingerprint,
    executable_freeze_hash: str,
    runtime_fingerprint: str,
    universe: UniverseReceipt,
    beacon: OfflineBeaconRecord,
) -> MembershipReceipt:
    for value, name in (
        (executable_freeze_hash, "executable_freeze_hash"),
        (runtime_fingerprint, "runtime_fingerprint"),
        (universe.ordered_universe_hash, "candidate_universe_hash"),
    ):
        _require_sha(value, name)
    if len(universe.canonical_entries) < TOTAL_SELECTED:
        raise ControlViolation("candidate universe has fewer than 36 canonical exact bodies")
    selection_key = sha256_bytes(
        (
            "PlanLatch-v7.18"
            + family_fingerprint.sha256
            + SEMANTIC_HASH
            + executable_freeze_hash
            + runtime_fingerprint
            + universe.ordered_universe_hash
            + beacon.randomness_sha256
        ).encode("utf-8")
    )
    ranked = sorted(
        universe.canonical_entries,
        key=lambda ident: (sha256_bytes((selection_key + ident).encode("utf-8")), ident),
    )
    selected = tuple(ranked[:TOTAL_SELECTED])
    partition: dict[str, str] = {}
    cursor = 0
    for name, count in PARTITION_COUNTS:
        for ident in selected[cursor:cursor + count]:
            partition[ident] = name
        cursor += count
    body = {
        "selection_key": selection_key,
        "selected_identities": list(selected),
        "partition_by_identity": dict(sorted(partition.items())),
        "universe_hash": universe.ordered_universe_hash,
    }
    return MembershipReceipt(
        selection_key,
        selected,
        partition,
        universe.ordered_universe_hash,
        sha256_json(body),
    )


def verify_receipt_immutable(receipt: MembershipReceipt) -> bool:
    if tuple(receipt.partition_by_identity) and set(receipt.partition_by_identity) != set(receipt.selected_identities):
        raise ControlViolation("partition membership must equal selected membership")
    counts = {name: list(receipt.partition_by_identity.values()).count(name) for name, _ in PARTITION_COUNTS}
    expected = dict(PARTITION_COUNTS)
    if counts != expected:
        raise ControlViolation(f"partition counts mismatch: {counts}")
    if sha256_json(receipt.payload_without_hash()) != receipt.receipt_sha256:
        raise ControlViolation("receipt hash mismatch / reassignment detected")
    return True


@dataclass(frozen=True)
class RuntimeFingerprint:
    container_sha256: str
    code_tree_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    host_id: str
    gpu_device_uuid: str
    gpu_model: str
    driver_version: str
    cuda_runtime: str
    firmware_id: str
    dtype: str
    deterministic_flags_sha256: str
    environment_sha256: str

    def __post_init__(self) -> None:
        _require_sha(self.container_sha256, "container_sha256")
        _require_sha(self.code_tree_sha256, "code_tree_sha256")
        _require_sha(self.model_sha256, "model_sha256")
        _require_sha(self.tokenizer_sha256, "tokenizer_sha256")
        _require_sha(self.deterministic_flags_sha256, "deterministic_flags_sha256")
        _require_sha(self.environment_sha256, "environment_sha256")
        if not all((self.host_id,self.gpu_device_uuid,self.gpu_model,self.driver_version,self.cuda_runtime,self.firmware_id,self.dtype)):
            raise ControlViolation("exact runtime string fields required")

    @property
    def sha256(self) -> str:
        return sha256_json(dataclasses.asdict(self))


def require_exact_runtime(expected: RuntimeFingerprint, observed: RuntimeFingerprint) -> bool:
    if expected != observed:
        raise ControlViolation("exact reserved runtime substitution rejected")
    return True


class Effect(str, Enum):
    CONTROL = "CONTROL"
    CONTENT_DATA = "CONTENT_DATA"
    SCIENCE_DATA = "SCIENCE_DATA"
    TERMINAL_DECISION = "TERMINAL_DECISION"


@dataclass(frozen=True)
class OperatorCertificate:
    name: str
    implementation_sha256: str
    input_effects: tuple[Effect, ...]
    output_effect: Effect
    frozen_formula_id: str
    recursively_verified: bool
    opaque_or_native: bool = False
    content_selects_alternative_family: bool = False
    hidden_control_effect: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.frozen_formula_id:
            raise ControlViolation("operator name/formula required")
        _require_sha(self.implementation_sha256, "implementation_sha256")


APPROVED_FORMULAS = frozenset({
    "v79_phi",
    "v79_full_decoder",
    "v79_placebo_decoder",
    "v79_p_mix",
    "v79_source_scoring",
    "v79_payload_bank_fit_only",
    "v79_observed_support_payload_select",
    "v79_relay_scoring",
    "v79_g1_g20_terminal",
    "v720_u_star_router",
    "v720_fixed_reduction",
    "v720_total_report",
})


def verify_operator_certificate(cert: OperatorCertificate) -> bool:
    if cert.frozen_formula_id not in APPROVED_FORMULAS:
        raise ControlViolation("scientific operator formula is not frozen/approved")
    if cert.opaque_or_native and not cert.recursively_verified:
        raise ControlViolation("opaque/native/callback scientific operator fails closed")
    if not cert.recursively_verified:
        raise ControlViolation("whole-program operator closure incomplete")
    if cert.hidden_control_effect:
        raise ControlViolation("CONTENT_DATA-dependent internal scientific control rejected")
    if cert.content_selects_alternative_family:
        raise ControlViolation("extensional content-dependent scientific selection rejected")
    return True


def verify_whole_program_effects(certs: Sequence[OperatorCertificate]) -> bool:
    if not certs:
        raise ControlViolation("effect manifest must be nonempty")
    names = [c.name for c in certs]
    if len(set(names)) != len(names):
        raise ControlViolation("duplicate effect-manifest operator")
    return all(verify_operator_certificate(c) for c in certs)


@dataclass(frozen=True)
class CanonicalCoordinate:
    name: str
    value: int
    producer_id: str
    producer_sha256: str
    tainted_by_content: bool = False

    def __post_init__(self) -> None:
        if self.name not in {"A", "H", "R"} or self.value not in {0, 1}:
            raise ControlViolation("canonical coordinate must be binary A/H/R")
        if not self.producer_id:
            raise ControlViolation("canonical producer id required")
        _require_sha(self.producer_sha256, "producer_sha256")
        if self.tainted_by_content:
            raise ControlViolation("content/M0/identity-tainted A/H/R cannot route U*")


CANONICAL_PRODUCERS = {
    "A": "planlatch-frozen-factor-A-v1",
    "H": "planlatch-frozen-factor-H-v1",
    "R": "planlatch-repeatable-orientation-R-v1",
}

FORBIDDEN_SELECTOR_SOURCES = frozenset({
    "raw_body", "hash_T", "hash_Ostar", "content_embedding", "set_aggregate",
    "M0", "canonical_identity", "membership_receipt", "membership_rank",
    "selection_key", "selected_set_hash", "opaque_row_handle",
})


def verify_scientific_selector_sources(sources: Sequence[str]) -> bool:
    """Verify sources used to choose a scientific branch/family/parameter path.

    Numeric DATA flow is not checked here; this guard is only for scientific
    selection/routing.  U*'s canonical A/H/R are the sole allowed selectors.
    """
    src=tuple(str(x) for x in sources)
    bad=[x for x in src if x not in {"A","H","R"}]
    if bad:
        raise ControlViolation(f"forbidden scientific selector source(s): {sorted(set(bad))}")
    if not src:
        raise ControlViolation("scientific selector must declare its sources")
    return True


def authenticated_u_star(a: CanonicalCoordinate, h: CanonicalCoordinate, r: CanonicalCoordinate) -> tuple[int, int, int]:
    coords = (a, h, r)
    for c, expected in zip(coords, ("A", "H", "R")):
        if c.name != expected or c.producer_id != CANONICAL_PRODUCERS[expected]:
            raise ControlViolation(f"noncanonical {expected} producer")
    return (a.value, h.value, r.value)


MANDATORY_REPORT_FIELDS = (
    "terminal_state",
    "terminal_reason",
    "source_report",
    "relay_report",
    "g1_g20",
    "heterogeneity",
    "runtime_attestation",
    "universe_receipt_hash",
    "membership_receipt_hash",
    "implementation_fingerprint",
    "claim_scope",
)


def total_report_schema(values: Mapping[str, Any]) -> Mapping[str, Any]:
    out: dict[str, Any] = {}
    for key in MANDATORY_REPORT_FIELDS:
        if key in values:
            out[key] = values[key]
        else:
            out[key] = {"value": None, "reason": "NA_NOT_AVAILABLE_IN_TERMINAL_STATE"}
    if set(out) != set(MANDATORY_REPORT_FIELDS):
        raise ControlViolation("mandatory report schema mismatch")
    return out


def gate_status_only_report(base_values: Mapping[str, Any], gate_status: Mapping[str, bool]) -> Mapping[str, Any]:
    if any(not str(k).startswith("G") for k in gate_status):
        raise ControlViolation("gate status keys must be G*")
    merged = dict(base_values)
    merged["g1_g20"] = {"status": dict(sorted(gate_status.items()))}
    return total_report_schema(merged)


@dataclass(frozen=True)
class OpaqueHandle:
    """Equality-only handle; its raw token is intentionally inaccessible."""
    _token_digest: str = dataclasses.field(repr=False)

    def __post_init__(self) -> None:
        _require_sha(self._token_digest, "_token_digest")

    @classmethod
    def from_test_token(cls, token: str) -> "OpaqueHandle":
        return cls(sha256_bytes(token.encode("utf-8")))

    def __hash__(self) -> int:
        raise TypeError("opaque row handles are not hashable/orderable scientific keys")

    def __lt__(self, other: object) -> bool:
        raise TypeError("opaque row handles are not orderable")
