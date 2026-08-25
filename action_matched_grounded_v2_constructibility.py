"""Zero-science constructibility/provenance helpers for ActionMatched Grounded-v2.

This module is deliberately NOT a science runtime.  It contains no model or
ALFWorld imports and refuses science execution.  Full endpoint/statistical,
token/control-serialization, and plan-realization authority remains unresolved
until a later prospective freeze and independent review.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

ORIENTATION_NAMESPACE = "PlanCarry|ACTION_MATCHED_GROUNDED_V2|ORIENT|"
POPULATION_SALT = "PlanCarry|ACTION_MATCHED_GROUNDED_V2|FRESH160|20260825"
SCIENCE_EXECUTION_FORBIDDEN = True
CONTROL_CONCEPTS = (
    "NEXT_DIVERGENT_ACTION_ONLY",
    "FUTURE_ACTION_SEQUENCE_ONLY",
)
CONTROL_CONCEPT_ALIASES = {
    "IMMEDIATE_ACTION_IDENTITY_ONLY": "NEXT_DIVERGENT_ACTION_ONLY",
    "FUTURE_ACTION_SEQUENCE_ONLY": "FUTURE_ACTION_SEQUENCE_ONLY",
}
# These are intentionally unresolved in this constructibility-only prototype.
UNRESOLVED_SCIENCE_AUTHORITY = (
    "H4_H5_exact_endpoint_tests",
    "Holm_FWER_and_exact_effect_competence_thresholds",
    "orientation_robust_semantic_nuisance_scoring",
    "exact_token_and_control_serialization",
    "development_selection_tie_break",
    "exact_plan_realization_prompt_chat_template_parser_failure_behavior",
    "exact_control_formulas_norm_sign_and_endpoints",
)


class ConstructibilityError(ValueError):
    """Prospective geometry/provenance failure; never a scientific outcome."""


def refuse_science_execution() -> None:
    raise RuntimeError(
        "SCIENCE_EXECUTION_FORBIDDEN: Grounded-v2 constructibility prototype is "
        "not science-ready; unresolved authority=" + ",".join(UNRESOLVED_SCIENCE_AUTHORITY)
    )


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def normalize_game_path(path: str) -> str:
    """Normalize reviewed ALFWorld path forms to canonical ``family/trial``."""
    if not isinstance(path, str) or not path.strip():
        raise ConstructibilityError("game_path must be nonempty string")
    p = path.strip().replace("\\", "/")
    prefix = "json_2.1.1/train/"
    if p.startswith(prefix):
        p = p[len(prefix) :]
    suffix = "/game.tw-pddl"
    if p.endswith(suffix):
        p = p[: -len(suffix)]
    p = p.strip("/")
    if not p or "/trial_" not in p:
        raise ConstructibilityError(f"not canonical ALFWorld family/trial path: {path!r}")
    return p


def orientation_bit(game_path: str) -> int:
    p = normalize_game_path(game_path)
    return hashlib.sha256((ORIENTATION_NAMESPACE + p).encode()).digest()[0] & 1


def population_rank_sha256(game_path: str, salt: str = POPULATION_SALT) -> str:
    p = normalize_game_path(game_path)
    return hashlib.sha256((salt + "|" + p).encode()).hexdigest()


def build_normalized_exclusion_union(path_sets: Iterable[Iterable[str]]) -> tuple[str, ...]:
    union = {normalize_game_path(p) for group in path_sets for p in group}
    return tuple(sorted(union))


def deterministic_fresh_selection(
    inventory_paths: Iterable[str],
    exclusion_paths: Iterable[str],
    *,
    selected_n: int = 160,
    salt: str = POPULATION_SALT,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    inventory = {normalize_game_path(p) for p in inventory_paths}
    excluded = {normalize_game_path(p) for p in exclusion_paths}
    fresh = sorted(inventory - excluded)
    ranked = sorted(fresh, key=lambda p: (population_rank_sha256(p, salt), p))
    if len(ranked) < selected_n:
        raise ConstructibilityError(f"fresh capacity {len(ranked)} < selected_n {selected_n}")
    return tuple(ranked[:selected_n]), tuple(ranked[selected_n:])


def _check_scores(admissibles: Sequence[str], scores: Mapping[str, float], label: str) -> tuple[str, ...]:
    actions = tuple(admissibles)
    if len(actions) != len(set(actions)):
        raise ConstructibilityError(f"{label}: duplicate admissible command")
    if set(actions) != set(scores):
        raise ConstructibilityError(f"{label}: stale/incomplete score map vs admissibles")
    if not actions:
        raise ConstructibilityError(f"{label}: empty admissible set")
    return actions


def frozen_rank(admissibles: Sequence[str], scores: Mapping[str, float], *, label: str) -> tuple[str, ...]:
    actions = _check_scores(admissibles, scores, label)
    # Exact reviewed convention: greedy highest suffix-logprob; lexical tie-break.
    return tuple(sorted(actions, key=lambda a: (-float(scores[a]), a)))


@dataclass(frozen=True)
class GroundedPair:
    game_path: str
    pre_cut_actions: tuple[str, str]
    pre_cut_actions_model_own_nontrivial: bool
    shared_action3: str
    executed_shared_action3: str
    unordered_rank1: str
    unordered_rank2: str
    unordered_rank1_score: float
    unordered_rank2_score: float
    orientation_bit: int
    action4_a: str
    action4_b: str
    branch_a_action4_executed: str
    branch_b_action4_executed: str
    action5_a: str
    action5_b: str
    cut_state_hash: str
    post_action3_state_hash: str
    branch_a_state_hash: str
    branch_b_state_hash: str
    cut_admissibles: tuple[str, ...]
    post_action3_admissibles: tuple[str, ...]
    branch_a_admissibles: tuple[str, ...]
    branch_b_admissibles: tuple[str, ...]
    cut_scores: tuple[tuple[str, float], ...]
    post_action3_scores: tuple[tuple[str, float], ...]
    branch_a_scores: tuple[tuple[str, float], ...]
    branch_b_scores: tuple[tuple[str, float], ...]
    common_observation3_sha256: str
    branch_a_observation_sha256: str
    branch_b_observation_sha256: str
    control_concepts: tuple[str, ...] = CONTROL_CONCEPTS
    science_execution_forbidden: bool = True
    provenance_frozen_before_plan_materialization: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def construct_grounded_pair(
    *,
    game_path: str,
    pre_cut_actions: Sequence[str],
    pre_cut_actions_model_own_nontrivial: bool,
    cut_admissibles: Sequence[str],
    cut_scores: Mapping[str, float],
    post_action3_admissibles: Sequence[str],
    post_action3_scores: Mapping[str, float],
    branch_a_admissibles: Sequence[str],
    branch_a_scores: Mapping[str, float],
    branch_b_admissibles: Sequence[str],
    branch_b_scores: Mapping[str, float],
    cut_state_hash: str,
    post_action3_state_hash: str,
    branch_a_state_hash: str,
    branch_b_state_hash: str,
    common_observation3: str,
    branch_a_observation: str,
    branch_b_observation: str,
    executed_shared_action3: str,
    branch_a_action4_executed: str,
    branch_b_action4_executed: str,
    activation_outcomes: Any = None,
    score_gap_filter: float | None = None,
    pair_retry_count: int = 0,
) -> GroundedPair:
    """Construct only the frozen grounded geometry from pre-causal inputs.

    Caller supplies *actual* admissibles/scores from frozen construction
    provenance.  This helper does not run a model or environment.
    """
    p = normalize_game_path(game_path)
    pre_cut = tuple(pre_cut_actions)
    if len(pre_cut) != 2 or any(not isinstance(a, str) or not a.strip() for a in pre_cut):
        raise ConstructibilityError("exactly two nonempty pre-cut action strings are required")
    if pre_cut_actions_model_own_nontrivial is not True:
        raise ConstructibilityError("pre-cut actions must be attested model-own nontrivial")
    if activation_outcomes is not None:
        raise ConstructibilityError("activation outcomes forbidden during pair construction")
    if score_gap_filter is not None:
        raise ConstructibilityError("score-gap filtering is forbidden")
    if pair_retry_count != 0:
        raise ConstructibilityError("pair retry/replacement is forbidden")
    for name, value in (
        ("cut_state_hash", cut_state_hash),
        ("post_action3_state_hash", post_action3_state_hash),
        ("branch_a_state_hash", branch_a_state_hash),
        ("branch_b_state_hash", branch_b_state_hash),
    ):
        if not isinstance(value, str) or not value:
            raise ConstructibilityError(f"missing provenance: {name}")

    cut_rank = frozen_rank(cut_admissibles, cut_scores, label="cut2")
    shared_a3 = cut_rank[0]
    if executed_shared_action3 != shared_a3:
        raise ConstructibilityError("executed shared A3 does not match frozen greedy A3")

    post_rank = frozen_rank(post_action3_admissibles, post_action3_scores, label="post_action3")
    if len(post_rank) < 2:
        raise ConstructibilityError("post_action3 requires >=2 admissible nontrivial commands")
    # Pair is selected while still unordered. Orientation is applied only after rank1/rank2 freeze.
    rank1, rank2 = post_rank[:2]
    bit = orientation_bit(p)
    a4, b4 = (rank1, rank2) if bit == 0 else (rank2, rank1)
    if branch_a_action4_executed != a4:
        raise ConstructibilityError("branch A state provenance does not match oriented A4")
    if branch_b_action4_executed != b4:
        raise ConstructibilityError("branch B state provenance does not match oriented B4")

    # Branch-local current admissibles, not stale/common admissibles.
    a5_rank = frozen_rank(branch_a_admissibles, branch_a_scores, label="branch_a_after_A4")
    b5_rank = frozen_rank(branch_b_admissibles, branch_b_scores, label="branch_b_after_B4")
    a5, b5 = a5_rank[0], b5_rank[0]
    if a5 == b5:
        raise ConstructibilityError("A5 == B5: family constructibility-ineligible; no retry")

    def pairs(m: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
        return tuple(sorted((str(k), float(v)) for k, v in m.items()))

    def h(text: str) -> str:
        if not isinstance(text, str):
            raise ConstructibilityError("observation provenance must be strings")
        return hashlib.sha256(text.encode()).hexdigest()

    pair = GroundedPair(
        game_path=p,
        pre_cut_actions=(pre_cut[0], pre_cut[1]),
        pre_cut_actions_model_own_nontrivial=True,
        shared_action3=shared_a3,
        executed_shared_action3=executed_shared_action3,
        unordered_rank1=rank1,
        unordered_rank2=rank2,
        unordered_rank1_score=float(post_action3_scores[rank1]),
        unordered_rank2_score=float(post_action3_scores[rank2]),
        orientation_bit=bit,
        action4_a=a4,
        action4_b=b4,
        branch_a_action4_executed=branch_a_action4_executed,
        branch_b_action4_executed=branch_b_action4_executed,
        action5_a=a5,
        action5_b=b5,
        cut_state_hash=cut_state_hash,
        post_action3_state_hash=post_action3_state_hash,
        branch_a_state_hash=branch_a_state_hash,
        branch_b_state_hash=branch_b_state_hash,
        cut_admissibles=tuple(cut_admissibles),
        post_action3_admissibles=tuple(post_action3_admissibles),
        branch_a_admissibles=tuple(branch_a_admissibles),
        branch_b_admissibles=tuple(branch_b_admissibles),
        cut_scores=pairs(cut_scores),
        post_action3_scores=pairs(post_action3_scores),
        branch_a_scores=pairs(branch_a_scores),
        branch_b_scores=pairs(branch_b_scores),
        common_observation3_sha256=h(common_observation3),
        branch_a_observation_sha256=h(branch_a_observation),
        branch_b_observation_sha256=h(branch_b_observation),
    )
    validate_grounded_pair(pair)
    return pair


def validate_grounded_pair(pair: GroundedPair) -> None:
    if len(pair.pre_cut_actions) != 2 or any(not isinstance(a, str) or not a.strip() for a in pair.pre_cut_actions):
        raise ConstructibilityError("exactly two nonempty pre-cut actions must remain frozen")
    if pair.pre_cut_actions_model_own_nontrivial is not True:
        raise ConstructibilityError("pre-cut model-own/nontrivial attestation drifted")
    if pair.executed_shared_action3 != pair.shared_action3:
        raise ConstructibilityError("executed shared A3 provenance mismatch")
    if pair.branch_a_action4_executed != pair.action4_a or pair.branch_b_action4_executed != pair.action4_b:
        raise ConstructibilityError("executed branch A4/B4 provenance mismatch")
    if pair.science_execution_forbidden is not True:
        raise ConstructibilityError("science_execution_forbidden must be true")
    if pair.provenance_frozen_before_plan_materialization is not True:
        raise ConstructibilityError("provenance must freeze before plan materialization")
    if tuple(pair.control_concepts) != CONTROL_CONCEPTS:
        raise ConstructibilityError("control concept placeholders drifted")
    if pair.action5_a == pair.action5_b:
        raise ConstructibilityError("A5/B5 must diverge")
    post_scores = dict(pair.post_action3_scores)
    expected_rank = frozen_rank(pair.post_action3_admissibles, post_scores, label="validate_post_action3")
    if len(expected_rank) < 2 or (pair.unordered_rank1, pair.unordered_rank2) != expected_rank[:2]:
        raise ConstructibilityError("unordered top2 pair does not match frozen rank")
    bit = orientation_bit(pair.game_path)
    expected_ab = (
        (pair.unordered_rank1, pair.unordered_rank2)
        if bit == 0
        else (pair.unordered_rank2, pair.unordered_rank1)
    )
    if pair.orientation_bit != bit or (pair.action4_a, pair.action4_b) != expected_ab:
        raise ConstructibilityError("A/B orientation must be path-hash-only after top2 selection")
    for name, admissibles, scores in (
        ("cut2", pair.cut_admissibles, dict(pair.cut_scores)),
        ("post_action3", pair.post_action3_admissibles, dict(pair.post_action3_scores)),
        ("branch_a", pair.branch_a_admissibles, dict(pair.branch_a_scores)),
        ("branch_b", pair.branch_b_admissibles, dict(pair.branch_b_scores)),
    ):
        _check_scores(admissibles, scores, name)
    if frozen_rank(pair.cut_admissibles, dict(pair.cut_scores), label="validate_cut")[0] != pair.shared_action3:
        raise ConstructibilityError("shared action3 is not frozen greedy argmax")
    if frozen_rank(pair.branch_a_admissibles, dict(pair.branch_a_scores), label="validate_A5")[0] != pair.action5_a:
        raise ConstructibilityError("A5 is not branch-local greedy rank1")
    if frozen_rank(pair.branch_b_admissibles, dict(pair.branch_b_scores), label="validate_B5")[0] != pair.action5_b:
        raise ConstructibilityError("B5 is not branch-local greedy rank1")


def assert_selected_population_clean(selected_paths: Iterable[str], excluded_paths: Iterable[str]) -> None:
    selected = [normalize_game_path(p) for p in selected_paths]
    excluded = {normalize_game_path(p) for p in excluded_paths}
    if len(selected) != len(set(selected)):
        raise ConstructibilityError("selected population contains duplicate paths")
    overlap = sorted(set(selected) & excluded)
    if overlap:
        raise ConstructibilityError(f"selected path exposure detected: {overlap[:3]}")
