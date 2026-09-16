"""Deterministic pre-science realization of the accepted PlanLatch v7.9 contract.

This module is intentionally stdlib-only. It implements protocol mechanics and
fidelity canaries; it performs no model inference and produces no scientific
evidence by itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import inspect
import json
import math
from typing import Iterable, Mapping, Sequence

DESIGN_ID = "c8b8981a-352f-48c0-9bee-08bba6a46f7f"
SEMANTIC_HASH = "6e53b8f713b2de6f3a2b489b351b1ca37f355eaf850228e9706a596a47ba62ef"
DESIGN_ATTACK_SYNTHESIS_ID = "5e3b98db-cd24-41c5-bf32-5c3d6d5bc3f7"
DESIGN_FINALIZATION_GATE_ID = "6cc4139b-1007-4415-bbbc-121efb2f6905"
SOURCE_BASE_COMMIT = "d8a509aa43f430ca0edff802d8cd47dc3ec0f9d2"
PROTOCOL_VERSION = "planlatch-v7.9-prescience-v1"
PHI_ALGORITHM = "uniform-j0-o-star-zscore-multiset-v1"
PHI_EPSILON = 1e-12
PAYLOAD_K = 16
ALLOWED_GAINS = (0.8, 1.25)
LABEL_ORDER = ("p", "q")


class ProtocolViolation(ValueError):
    """Raised when an implementation input violates the frozen v7.9 contract."""


def stable_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_json(obj: object) -> str:
    return hashlib.sha256(stable_json(obj).encode("utf-8")).hexdigest()


def _finite_float(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise ProtocolViolation(f"{name} must be numeric, not bool")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolViolation(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ProtocolViolation(f"{name} must be finite")
    return out


def _row(row: Sequence[object], *, expected_dim: int | None = None) -> tuple[float, ...]:
    if isinstance(row, (str, bytes)):
        raise ProtocolViolation("O* row must be a numeric sequence")
    out = tuple(_finite_float(v, name="O* coordinate") for v in row)
    if not out:
        raise ProtocolViolation("O* row cannot be empty")
    if expected_dim is not None and len(out) != expected_dim:
        raise ProtocolViolation("all O* rows must have the same dimension")
    return out


def _canonical_row_key(row: tuple[float, ...]) -> tuple[str, ...]:
    # Derived only from O* numerical values. No row identity, schedule, label,
    # semantic-arm position, J-mask position, Q/P, or mutable provenance enters.
    return tuple(v.hex() for v in row)


@dataclass(frozen=True)
class PhiState:
    algorithm: str
    count: int
    dimension: int
    means: tuple[float, ...]
    scales: tuple[float, ...]
    preprocessing_weight_rule: str = "uniform-v_i-equals-1"
    input_semantics: str = "unordered-multiset-of-realized-J0-FIT-O-star-only"

    def payload(self) -> dict[str, object]:
        return asdict(self)

    def serialized_bytes(self) -> bytes:
        return stable_json(self.payload()).encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.serialized_bytes()).hexdigest()


def fit_phi(o_star_rows: Sequence[Sequence[object]]) -> PhiState:
    """Fit target/bit/identity-blind phi_U from an unordered multiset of O* rows.

    Deliberately accepts only O* rows. Uniform v_i=1 is internal and immutable.
    Rows are canonicalized by O* values before reduction so schedule/order cannot
    become an implicit channel.
    """
    if not o_star_rows:
        raise ProtocolViolation("phi_U requires at least one realized J=0 FIT O* row")
    first = _row(o_star_rows[0])
    rows = [first]
    rows.extend(_row(r, expected_dim=len(first)) for r in o_star_rows[1:])
    ordered = sorted(rows, key=_canonical_row_key)
    n = len(ordered)
    dim = len(first)
    means = tuple(math.fsum(row[j] for row in ordered) / n for j in range(dim))
    variances = tuple(
        math.fsum((row[j] - means[j]) ** 2 for row in ordered) / n for j in range(dim)
    )
    scales = tuple(math.sqrt(v) if v > PHI_EPSILON * PHI_EPSILON else 1.0 for v in variances)
    return PhiState(
        algorithm=PHI_ALGORITHM,
        count=n,
        dimension=dim,
        means=means,
        scales=scales,
    )


def transform_phi(state: PhiState, o_star_rows: Sequence[Sequence[object]]) -> tuple[tuple[float, ...], ...]:
    out: list[tuple[float, ...]] = []
    for raw in o_star_rows:
        row = _row(raw, expected_dim=state.dimension)
        out.append(tuple((row[j] - state.means[j]) / state.scales[j] for j in range(state.dimension)))
    return tuple(out)


def transformed_multiset_hash(rows: Sequence[Sequence[object]]) -> str:
    canonical = sorted((_row(r) for r in rows), key=_canonical_row_key)
    payload = [[v.hex() for v in row] for row in canonical]
    return sha256_json(payload)


@dataclass(frozen=True)
class MemberObservation:
    """Preprocessing-safe observation: no Q, S, U-cell index, or provenance identity."""

    o_star: tuple[float, ...]
    j_singleton: bool


def realized_j0_rows(observations: Sequence[MemberObservation]) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(obs.o_star) for obs in observations if not obs.j_singleton)


def fit_phi_from_members(observations: Sequence[MemberObservation]) -> PhiState:
    return fit_phi(realized_j0_rows(observations))


def class_balance_weights(labels: Sequence[str], label_order: Sequence[str] = LABEL_ORDER) -> tuple[float, ...]:
    """Create supervised w_i only after phi_U is frozen.

    Each declared class contributes equal total weight. This function is kept
    separate from all preprocessing APIs by construction.
    """
    if not labels:
        raise ProtocolViolation("labels cannot be empty")
    declared = tuple(label_order)
    if len(set(declared)) != len(declared) or not declared:
        raise ProtocolViolation("label order must be non-empty and unique")
    counts = {label: 0 for label in declared}
    for label in labels:
        if label not in counts:
            raise ProtocolViolation(f"unexpected label: {label}")
        counts[label] += 1
    if any(counts[label] == 0 for label in declared):
        raise ProtocolViolation("every declared class requires realized J=0 support")
    class_mass = 1.0 / len(declared)
    return tuple(class_mass / counts[label] for label in labels)


def psi(bit: int) -> float:
    if isinstance(bit, bool):
        bit = int(bit)
    if bit not in (0, 1):
        raise ProtocolViolation("bit must be exactly 0 or 1")
    return float(bit)


def decoder_input(transformed_o_star: Sequence[object], bit: int) -> tuple[float, ...]:
    row = _row(transformed_o_star)
    return row + (psi(bit),)


def weighted_mean(values: Sequence[object], weights: Sequence[object]) -> float:
    if len(values) != len(weights) or not values:
        raise ProtocolViolation("values and weights must be non-empty and aligned")
    pairs = [(_finite_float(w, name="weight"), _finite_float(v, name="value")) for v, w in zip(values, weights)]
    if any(w < 0 for w, _ in pairs):
        raise ProtocolViolation("weights must be non-negative")
    denominator = math.fsum(w for w, _ in pairs)
    if denominator <= 0:
        raise ProtocolViolation("weight denominator must be positive")
    ordered = sorted(pairs, key=lambda item: (item[0].hex(), item[1].hex()))
    return math.fsum(w * v for w, v in ordered) / denominator


def collapsed_placebo_objective(
    loss_pairs: Sequence[Sequence[object]],
    weights: Sequence[object],
    *,
    regularizer: object = 0.0,
    lambda_: object = 0.0,
) -> float:
    if len(loss_pairs) != len(weights) or not loss_pairs:
        raise ProtocolViolation("loss pairs and original-record weights must align")
    expected_losses: list[float] = []
    for pair in loss_pairs:
        if len(pair) != 2:
            raise ProtocolViolation("each original record must have exactly P=0 and P=1 losses")
        l0 = _finite_float(pair[0], name="P=0 loss")
        l1 = _finite_float(pair[1], name="P=1 loss")
        expected_losses.append(0.5 * l0 + 0.5 * l1)
    reg = _finite_float(regularizer, name="regularizer")
    lam = _finite_float(lambda_, name="lambda")
    if lam < 0:
        raise ProtocolViolation("lambda must be non-negative")
    return weighted_mean(expected_losses, weights) + lam * reg


def validate_expanded_placebo_weights(
    original_weights: Sequence[object],
    expanded_weights: Sequence[object],
    denominator: object,
    *,
    tolerance: float = 1e-12,
) -> bool:
    """Require a 2-arm implementation to represent the N-record collapsed law.

    Each expanded arm must carry 0.5*w_i while the scientific denominator stays
    Z=sum_i w_i. A naive two-full-weight/2Z representation is rejected even if
    one scalar loss happens to coincide, because its optimization geometry is
    not the frozen original-record objective.
    """
    ow = tuple(_finite_float(w, name="original weight") for w in original_weights)
    ew = tuple(_finite_float(w, name="expanded weight") for w in expanded_weights)
    if len(ew) != 2 * len(ow):
        raise ProtocolViolation("expanded PLACEBO must have exactly two arms per original record")
    z = math.fsum(ow)
    supplied_z = _finite_float(denominator, name="expanded denominator")
    if not math.isclose(supplied_z, z, rel_tol=0.0, abs_tol=tolerance):
        raise ProtocolViolation("expanded PLACEBO denominator must remain original-record Z")
    expected: list[float] = []
    for w in ow:
        expected.extend((0.5 * w, 0.5 * w))
    if any(not math.isclose(a, b, rel_tol=0.0, abs_tol=tolerance) for a, b in zip(ew, expected)):
        raise ProtocolViolation("each PLACEBO arm must carry exactly half of its original-record weight")
    return True


def placebo_log_score(log_p0: object, log_p1: object) -> float:
    return 0.5 * _finite_float(log_p0, name="log p(P=0)") + 0.5 * _finite_float(log_p1, name="log p(P=1)")


def p_mix(p0: Mapping[str, object], p1: Mapping[str, object]) -> dict[str, float]:
    if set(p0) != set(p1) or not p0:
        raise ProtocolViolation("P=0/P=1 distributions must have identical non-empty labels")
    mixed: dict[str, float] = {}
    for label in sorted(p0):
        a = _finite_float(p0[label], name=f"P=0 probability {label}")
        b = _finite_float(p1[label], name=f"P=1 probability {label}")
        if a < 0 or b < 0:
            raise ProtocolViolation("probabilities must be non-negative")
        mixed[label] = 0.5 * a + 0.5 * b
    total = math.fsum(mixed.values())
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ProtocolViolation("mixed predictive distribution must sum to one")
    return mixed


def hard_label(probabilities: Mapping[str, object], label_order: Sequence[str] = LABEL_ORDER) -> str:
    order = tuple(label_order)
    if set(probabilities) != set(order) or len(set(order)) != len(order):
        raise ProtocolViolation("probability labels must equal the frozen unique label order")
    winner = order[0]
    best = _finite_float(probabilities[winner], name=f"probability {winner}")
    for label in order[1:]:
        value = _finite_float(probabilities[label], name=f"probability {label}")
        if value > best:  # strict > preserves earlier frozen label on a tie
            winner, best = label, value
    return winner


def placebo_hard_prediction(
    p0: Mapping[str, object],
    p1: Mapping[str, object],
    label_order: Sequence[str] = LABEL_ORDER,
) -> str:
    return hard_label(p_mix(p0, p1), label_order)


def standardized_j0_delta(
    full_log_scores: Sequence[object],
    placebo_log_scores: Sequence[object],
    labels: Sequence[str],
    j_singleton: Sequence[bool],
    label_order: Sequence[str] = LABEL_ORDER,
) -> float:
    if not (len(full_log_scores) == len(placebo_log_scores) == len(labels) == len(j_singleton)):
        raise ProtocolViolation("source-statistic arrays must align")
    idx = [i for i, j in enumerate(j_singleton) if not j]
    if not idx:
        raise ProtocolViolation("no realized J=0 records")
    j0_labels = [labels[i] for i in idx]
    weights = class_balance_weights(j0_labels, label_order)
    differences = [
        _finite_float(full_log_scores[i], name="FULL log score")
        - _finite_float(placebo_log_scores[i], name="PLACEBO log score")
        for i in idx
    ]
    return weighted_mean(differences, weights)


def equal_u_block_delta(per_u_deltas: Sequence[object]) -> float:
    if not per_u_deltas:
        raise ProtocolViolation("at least one constructible U is required")
    values = [_finite_float(v, name="per-U delta") for v in per_u_deltas]
    return math.fsum(sorted(values)) / len(values)


@dataclass(frozen=True)
class OffSupportDiagnostic:
    name: str
    value: object
    scientific_use_allowed: bool = False


def off_support_q_toggle_diagnostic(value: object) -> OffSupportDiagnostic:
    return OffSupportDiagnostic(name="Q_TOGGLE_OFF_SUPPORT_DIAGNOSTIC", value=value)


@dataclass(frozen=True, order=True)
class PayloadTriple:
    transformer_block_index: int
    mlp_intermediate_channel_index: int
    gain: float

    def __post_init__(self) -> None:
        if isinstance(self.transformer_block_index, bool) or self.transformer_block_index < 0:
            raise ProtocolViolation("payload block index must be a non-negative integer")
        if isinstance(self.mlp_intermediate_channel_index, bool) or self.mlp_intermediate_channel_index < 0:
            raise ProtocolViolation("payload channel index must be a non-negative integer")
        gain = _finite_float(self.gain, name="payload gain")
        if gain not in ALLOWED_GAINS:
            raise ProtocolViolation(f"payload gain must be one of {ALLOWED_GAINS}")

    def payload(self) -> tuple[int, int, float]:
        return (self.transformer_block_index, self.mlp_intermediate_channel_index, float(self.gain))


@dataclass(frozen=True)
class PayloadManifest:
    """Anonymous payload bytes allowed to cross the reset/application boundary.

    Semantic bank identity is deliberately absent.  The checksum preimage is
    exactly ``{version, triples}``; callers may map a predicted label to one
    of two manifests outside this object, but that mapping is never serialized
    into or authenticated as part of the applied payload.
    """

    version: str
    triples: tuple[PayloadTriple, ...]
    checksum: str

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "triples": [list(t.payload()) for t in self.triples],
        }

    def serialized_payload(self) -> dict[str, object]:
        return {**self.unsigned_payload(), "checksum": self.checksum}


def make_payload_manifest(triples: Iterable[PayloadTriple], *, version: str = PROTOCOL_VERSION) -> PayloadManifest:
    frozen = tuple(triples)
    if len(frozen) != PAYLOAD_K:
        raise ProtocolViolation(f"payload must contain exactly {PAYLOAD_K} triples")
    if len(set(frozen)) != PAYLOAD_K:
        raise ProtocolViolation("payload triples must be unique")
    unsigned = {"version": version, "triples": [list(t.payload()) for t in frozen]}
    return PayloadManifest(version=version, triples=frozen, checksum=sha256_json(unsigned))


def validate_payload_manifest(manifest: PayloadManifest) -> bool:
    rebuilt = make_payload_manifest(manifest.triples, version=manifest.version)
    if rebuilt.checksum != manifest.checksum:
        raise ProtocolViolation("payload checksum mismatch")
    return True


def select_payload_from_observed_support(
    s_hat: str | OffSupportDiagnostic,
    payload_for_p: PayloadManifest,
    payload_for_q: PayloadManifest,
    *,
    observed_support: bool,
) -> PayloadManifest:
    """Select at the bank side, returning only an anonymous payload object."""
    if isinstance(s_hat, OffSupportDiagnostic):
        raise ProtocolViolation("off-support diagnostics cannot select payloads")
    if not observed_support:
        raise ProtocolViolation("payload selection requires actual observed-support Q")
    validate_payload_manifest(payload_for_p)
    validate_payload_manifest(payload_for_q)
    if s_hat == "p":
        return payload_for_p
    if s_hat == "q":
        return payload_for_q
    raise ProtocolViolation("S_hat must be p or q")


def decoder_relative_null_canary(
    full_reference_utility: object,
    placebo_reference_utility: object,
    *,
    tolerance: object,
    invalid_preprocessing_geometry_changed: bool,
) -> bool:
    """Validate the v7.9 decoder-relative-null fixture contract.

    Equality must be guaranteed for the exact frozen decoder/objective by the
    fixture/reference solution. Redundancy alone is intentionally not tested.
    """
    full = _finite_float(full_reference_utility, name="FULL reference utility")
    placebo = _finite_float(placebo_reference_utility, name="PLACEBO reference utility")
    tol = _finite_float(tolerance, name="null tolerance")
    if tol < 0:
        raise ProtocolViolation("null tolerance must be non-negative")
    return abs(full - placebo) <= tol and bool(invalid_preprocessing_geometry_changed)


def _contract_hash(payload: Mapping[str, object]) -> str:
    return sha256_json(dict(payload))


PSI_CONTRACT_HASH = _contract_hash({"version": PROTOCOL_VERSION, "psi": "raw-scalar-bit", "allowed": [0, 1], "block_separable": True})
OBJECTIVE_CONTRACT_HASH = _contract_hash({
    "version": PROTOCOL_VERSION,
    "full": "sum_i w_i*loss(phi(O*_i),Q_i)/Z + lambda*R",
    "placebo": "sum_i w_i*0.5*(loss(phi(O*_i),0)+loss(phi(O*_i),1))/Z + lambda*R",
    "denominator": "Z=sum_i w_i over original records",
})
METRIC_CONTRACT_HASH = _contract_hash({
    "version": PROTOCOL_VERSION,
    "placebo_log_score": "0.5*logp0+0.5*logp1 per original record",
    "placebo_classification": "p_mix=0.5*p0+0.5*p1 then one argmax per original record",
    "tie_rule": list(LABEL_ORDER),
})


def protocol_attestation(phi_state: PhiState | None = None) -> dict[str, object]:
    attestation: dict[str, object] = {
        "protocol_version": PROTOCOL_VERSION,
        "design_id": DESIGN_ID,
        "semantic_hash": SEMANTIC_HASH,
        "design_attack_synthesis_id": DESIGN_ATTACK_SYNTHESIS_ID,
        "design_finalization_gate_id": DESIGN_FINALIZATION_GATE_ID,
        "source_base_commit": SOURCE_BASE_COMMIT,
        "phi_algorithm": PHI_ALGORITHM,
        "phi_api_parameters": list(inspect.signature(fit_phi).parameters),
        "preprocessing_weight_rule": "uniform-v_i-equals-1",
        "row_order_identity_blind": True,
        "j1_member_leverage": "zero",
        "off_support_scientific_use": False,
        "psi_contract_hash": PSI_CONTRACT_HASH,
        "objective_contract_hash": OBJECTIVE_CONTRACT_HASH,
        "metric_contract_hash": METRIC_CONTRACT_HASH,
        "payload_k": PAYLOAD_K,
        "allowed_gains": list(ALLOWED_GAINS),
        "model_or_gpu_execution": False,
    }
    if phi_state is not None:
        attestation["phi_state_hash"] = phi_state.sha256
        attestation["phi_state"] = phi_state.payload()
    attestation["attestation_hash"] = sha256_json(attestation)
    return attestation
