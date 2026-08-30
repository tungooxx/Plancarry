#!/usr/bin/env python3
"""Exact CPDS V4 DEVELOPMENT execution driver.

This module is import-safe: it has no top-level torch/transformers/ALFWorld/TextWorld
imports and performs no scientific execution on import. The CLI is reachable only from
the ResearchDecision-bound ``development`` launcher path.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import pathlib
import inspect
import importlib
import re
import shutil
import sys
from typing import Any, Callable, Mapping, Sequence

import cpds_development_runtime_v1 as rt
import cpds_graphfork_contract_validator_v2 as gv2

ROOT = pathlib.Path(__file__).resolve().parent
D = ROOT / "results" / "design"
SEMANTICS_PATH = D / "plancarry_cpds_actual_family_execution_semantics_v1_20260830.json"
SOURCE_PATH = D / "plancarry_cpds_actual_development_source_snapshot_v2_20260829.json"
GENERATOR_PATH = D / "plancarry_cpds_actual_development_generator_manifest_v3_20260829.json"
BUNDLE_PATH = D / "plancarry_cpds_actual_33x2_durable_v1" / "two_split_assignment_bundle.json"
V4_PATH = D / "plancarry_cpds_v4_branch_preference_endpoint_contract_a2_20260830.json"
SEMANTICS_SHA256 = "4cbb409141a90a8cae1ae1f5d7ba63ab9b04e1cfd1d06ec584027e97fb7a97fb"
SEMANTICS_SELF_SHA256 = "770a29e1c60ff483837b018c5987e6f7dab156e615950911803a02ee2be0d550"
EXACT_ARMS = rt.EXACT_ARMS
MATCHED_ARMS = ("STATIC_REPEAT", "ALIGNED_RECURSION", "TRANSITION_PERMUTED", "MATCHED_INFORMATION")
SITES = ("RESET_PREFIX", "POST_TRANSITION_1", "BRANCH_POINT")
CARRIER_KEYS = (
    "source_graph_id", "goal_canonical", "reset_observation_canonical",
    "allowed_pre_reset_history_canonical", "immediate_next_command_canonical",
    "common_prefix_transition_keys", "divergence_depth_after_immediate",
)
EVALUATOR_KEYS = ("branch_A_equivalence_class", "branch_B_equivalence_class")
OUTPUT_DIR = ROOT / "outputs" / "cpds_v4_development_v1"
TERMINAL_NAME = "terminal.json"


class TechnicalInvalid(RuntimeError):
    """Whole-split technical/validity invalidity; never scientific evidence."""


def _canon(obj: Any) -> bytes:
    return rt.canonical_bytes(obj)


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def _load(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise TechnicalInvalid(code)


def _split_family(family: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(set(family) == set(CARRIER_KEYS) | set(EVALUATOR_KEYS), "FAMILY_RUNTIME_SCHEMA")
    carrier = {k: copy.deepcopy(family[k]) for k in CARRIER_KEYS}
    evaluator = {k: copy.deepcopy(family[k]) for k in EVALUATOR_KEYS}
    _require(not (set(carrier) & set(EVALUATOR_KEYS)), "BRANCH_SECRET_IN_CARRIER")
    return carrier, evaluator


def _authorities() -> dict[str, Any]:
    # Runtime authority validates corrected V4/recurrent/assignment transitive hashes.
    rt.verify_frozen_authorities()
    _require(rt.sha_file(SEMANTICS_PATH) == SEMANTICS_SHA256, "SEMANTICS_FILE_SHA")
    sem = _load(SEMANTICS_PATH)
    _require(sem.get("canonical_object_sha256_without_self_field") == SEMANTICS_SELF_SHA256, "SEMANTICS_DECLARED_SELF_SHA")
    sem_payload=copy.deepcopy(sem); sem_payload.pop("canonical_object_sha256_without_self_field",None)
    sem_self=hashlib.sha256(json.dumps(sem_payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")).hexdigest()
    _require(sem_self == SEMANTICS_SELF_SHA256, "SEMANTICS_SELF_SHA")
    _require(sem.get("scientific_result") == "NOT_ASSESSED", "SEMANTICS_SCOPE")
    _require(sem.get("preserved_science", {}).get("confirmation") == "HARD_SEALED_NO_RUNTIME_ROUTE", "CONFIRMATION_NOT_SEALED")
    _require(sem.get("preserved_science", {}).get("development_C_oneshot_guard") is False, "DEVELOPMENT_ONESHOT_GATE_DRIFT")
    source = _load(SOURCE_PATH)
    generator = _load(GENERATOR_PATH)
    bundle = _load(BUNDLE_PATH)
    v4 = _load(V4_PATH)
    families = source.get("families")
    witnesses = source.get("static_graph_replayability_witnesses")
    _require(isinstance(families, list) and len(families) == 33, "DEVELOPMENT_FAMILY_COUNT")
    _require(isinstance(witnesses, list) and len(witnesses) == 33, "DEVELOPMENT_WITNESS_COUNT")
    _require(all(len(f.get("common_prefix_transition_keys", [])) == 2 for f in families), "ACTUAL_FAMILY_NOT_TWO_TRANSITIONS")
    skeys = [gv2.structural_family_key(f) for f in families]
    _require(skeys == generator.get("structural_family_key_sha256s"), "GENERATOR_SOURCE_ORDER")
    certs = generator.get("certificates")
    _require(isinstance(certs, list) and len(certs) == 33, "GENERATOR_CERT_COUNT")
    _require([c.get("structural_family_key_sha256") for c in certs] == skeys, "GENERATOR_CERT_ORDER")
    assignments = bundle.get("development_assignment_manifest", {}).get("records")
    _require(isinstance(assignments, list) and len(assignments) == 33, "ASSIGNMENT_COUNT")
    amap = {r.get("structural_family_key_sha256"): r for r in assignments}
    _require(set(amap) == set(skeys), "ASSIGNMENT_STRUCTURAL_KEYS")
    certmap = {c["structural_family_key_sha256"]: c for c in certs}
    wmap = {w["source_graph_id"]: w for w in witnesses}
    _require(len(wmap) == 33, "WITNESS_GRAPH_IDS")
    for f, sk in zip(families, skeys, strict=True):
        gv2.validate_static_replayability(f, wmap[f["source_graph_id"]])
        a = amap[sk]; c = certmap[sk]
        _require(a.get("family_id") == c.get("family_id"), "ASSIGNMENT_FAMILY_ID")
        _require(a.get("split_namespace") == "CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1", "ASSIGNMENT_NAMESPACE")
        _require(a.get("generated_before_any_development_arm_outcome") is True, "ASSIGNMENT_POSTOUTCOME")
        perm = a.get("arm_permutation")
        _require(isinstance(perm, list) and len(perm) == 6 and set(perm) == set(EXACT_ARMS), "ASSIGNMENT_ARM_PERMUTATION")
    dr = v4.get("development_rule", {})
    _require(dr.get("positive_static_min") == 22 and dr.get("positive_permuted_min") == 22, "DEVELOPMENT_K_DRIFT")
    _require(float(dr.get("median_C_static_nats_min")) == 0.05 and float(dr.get("median_C_permuted_nats_min")) == 0.05, "DEVELOPMENT_EFFECT_DRIFT")
    _require(dr.get("median_C_information_gt0") is True and dr.get("median_D_aligned_gt0") is True, "DEVELOPMENT_GUARD_DRIFT")
    _require("median_C_oneshot_gt0" not in dr, "DEVELOPMENT_ONESHOT_GATE_PRESENT")
    return {"semantics": sem, "source": source, "generator": generator, "bundle": bundle, "v4": v4, "assignment_by_key": amap, "certificate_by_key": certmap, "witness_by_graph": wmap}


def _game_file(source_graph_id: str) -> pathlib.Path:
    root = pathlib.Path(os.environ.get("ALFWORLD_DATA", "/opt/gpu-lab/envs/plancarry-alfworld-data"))
    p = root / "json_2.1.1" / "train" / source_graph_id / "game.tw-pddl"
    _require(p.is_file(), "DEVELOPMENT_GAME_FILE_MISSING")
    return p


_SYMBOLIC_ACTION_RE = re.compile(r"^(GotoLocation|examineReceptacle)\(([^()]*)\)$")


def _translate_symbolic_action(command: str, demangle_object: Callable[[str], str]) -> str:
    """Translate the frozen graph action identity to ALFWorld's surface command.

    The actual33 source snapshots are static-PDDL graph authorities. AlfRuntime uses
    AlfredDemangler(shuffle=False), so its admissible-command strings are surface text.
    This bridge changes only the environment/model-facing spelling; the caller retains
    the original symbolic command for transition identity and F payloads.
    """
    symbolic = str(command)
    match = _SYMBOLIC_ACTION_RE.fullmatch(symbolic)
    _require(match is not None, "SYMBOLIC_ACTION_SYNTAX")
    op, body = match.group(1), match.group(2)
    args = body.split(",")
    expected_arity = 4 if op == "GotoLocation" else 2
    _require(len(args) == expected_arity and args[0] == "agent1", "SYMBOLIC_ACTION_ARITY")
    object_name = str(demangle_object(args[-1]))
    _require(bool(object_name), "SYMBOLIC_OBJECT_DEMANGLE_EMPTY")
    if op == "GotoLocation":
        return f"go to {object_name}"
    if op == "examineReceptacle":
        return f"examine {object_name}"
    raise TechnicalInvalid("SYMBOLIC_ACTION_OPERATOR")


def _build_symbolic_surface_resolver(env: Any) -> Callable[[str], str]:
    """Return a deterministic symbolic->surface resolver for one exact AlfRuntime game.

    Synthetic test runtimes intentionally use symbolic actions directly and do not expose
    TextWorld wrapper internals; identity resolution keeps those no-science fixtures valid.
    The real AlfRuntime path fails closed on case-fold collisions or missing entity IDs.
    """
    try:
        demangler_wrapper = env.env.batch_env.envs[0]._wrapped_env._wrapped_env
        infos = demangler_wrapper._entity_infos
    except (AttributeError, IndexError, TypeError):
        return lambda command: str(command)

    Demangler = importlib.import_module("alfworld.agents.utils.misc").Demangler
    demangler = Demangler(game_infos=infos, shuffle=False)
    id_by_casefold: dict[str, str] = {}
    for info in infos.values():
        entity_id = str(info.id)
        key = entity_id.casefold()
        _require(key not in id_by_casefold or id_by_casefold[key] == entity_id, "SYMBOLIC_OBJECT_CASEFOLD_COLLISION")
        id_by_casefold[key] = entity_id

    def demangle_object(symbolic_object_id: str) -> str:
        runtime_id = id_by_casefold.get(str(symbolic_object_id).casefold())
        _require(runtime_id is not None, "SYMBOLIC_OBJECT_NOT_IN_GAME")
        return str(demangler.demangle_alfred_name(runtime_id))

    return lambda command: _translate_symbolic_action(str(command), demangle_object)


def _runtime_surface_command(env: Any, resolver: Callable[[str], str], symbolic: str, code: str) -> str:
    surface = str(resolver(str(symbolic)))
    _require(surface in env.admissible_commands, code)
    return surface


def _top_set(scores: Mapping[str, float]) -> tuple[str, ...]:
    _require(bool(scores), "EMPTY_SCORE_MAP")
    vals = {str(k): float(v) for k, v in scores.items()}
    _require(all(math.isfinite(v) for v in vals.values()), "NONFINITE_SCORE")
    m = max(vals.values())
    return tuple(sorted(k for k, v in vals.items() if v == m))


def _score_site(torch: Any, tokenizer: Any, model: Any, goal: str, observation: str, candidates: Sequence[str]) -> dict[str, Any]:
    actions = tuple(sorted(str(x) for x in candidates))
    _require(bool(actions) and len(actions) == len(set(actions)), "SITE_CANDIDATE_SET")
    prompt = rt.render_policy_prompt(goal, observation, actions)
    base_scores: dict[str, float] = {}
    action_features: dict[str, list[float]] = {}
    for action in actions:
        base_scores[action] = rt.teacher_forced_whole_action_score(torch, tokenizer, model, prompt, action)
        action_features[action] = rt.native_hidden_feature(torch, tokenizer, model, rt.canonical_action_payload(action))
    return {"prompt": prompt, "candidates": actions, "base_scores": base_scores, "action_features": action_features}


def _arm_map_at_site(
    arm_id: str,
    site: str,
    base_scores: Mapping[str, float],
    action_features: Mapping[str, Sequence[float]],
    z0: Sequence[float],
    transition_features: Mapping[str, Sequence[float]],
    observed_keys: Sequence[str],
) -> tuple[dict[str, float], dict[str, Any]]:
    _require(site in SITES, "SITE")
    keys = list(observed_keys)
    # One-shot intentionally has no reset/post-transition G exposure.
    if arm_id == "NO_CARRY" or (arm_id == "STATIC_ONESHOT" and site != "BRANCH_POINT"):
        return ({a: float(base_scores[a]) for a in base_scores}, {"site": site, "arm_id": arm_id, "G_called": False, "F_calls": 0, "transition_order": []})
    if arm_id == "STATIC_ONESHOT":
        order: list[str] = []
    elif arm_id == "TRANSITION_PERMUTED" and len(keys) == 2:
        order = [keys[1], keys[0]]
    else:
        order = list(keys)
    if arm_id == "STATIC_REPEAT":
        # Exact matched scratch recurrence budget. Result is deliberately discarded and
        # cannot reach G/endpoint; exposed state remains z0.
        if order:
            _ = rt.fold(z0, [transition_features[k] for k in order])
        adjusted = rt.adjust_score_map(arm_id, base_scores, z0, transition_features, order, action_features)
        f_calls = len(order)
    else:
        adjusted = rt.adjust_score_map(arm_id, base_scores, z0, transition_features, order, action_features)
        f_calls = len(order) if arm_id in ("ALIGNED_RECURSION", "TRANSITION_PERMUTED", "MATCHED_INFORMATION") else 0
    return adjusted, {"site": site, "arm_id": arm_id, "G_called": True, "F_calls": f_calls, "transition_order": list(order)}


def _validate_geometry(events: Mapping[str, Sequence[Mapping[str, Any]]], common_keys: Sequence[str]) -> dict[str, Any]:
    expected_f = [0, 1, 2]
    for arm in MATCHED_ARMS:
        rows = list(events.get(arm, ()))
        _require([r.get("site") for r in rows] == list(SITES), "MATCHED_G_SITES:" + arm)
        _require([bool(r.get("G_called")) for r in rows] == [True, True, True], "MATCHED_G_COUNT:" + arm)
        _require([int(r.get("F_calls", -1)) for r in rows] == expected_f, "MATCHED_F_BUDGET:" + arm)
    one = list(events.get("STATIC_ONESHOT", ()))
    _require([r.get("site") for r in one] == list(SITES), "ONESHOT_EVENT_SITES")
    _require([bool(r.get("G_called")) for r in one] == [False, False, True], "ONESHOT_EXPOSURE_COUNT")
    _require([int(r.get("F_calls", -1)) for r in one] == [0, 0, 0], "ONESHOT_F_CALL")
    no = list(events.get("NO_CARRY", ()))
    _require(all(not bool(r.get("G_called")) and int(r.get("F_calls", -1)) == 0 for r in no), "NOCARRY_INTERFACE")
    _require(list(events["ALIGNED_RECURSION"][1]["transition_order"]) == [common_keys[0]], "ALIGNED_PREFIX1")
    _require(list(events["ALIGNED_RECURSION"][2]["transition_order"]) == list(common_keys), "ALIGNED_PREFIX2")
    _require(list(events["TRANSITION_PERMUTED"][1]["transition_order"]) == [common_keys[0]], "PERMUTED_FUTURE_PREVIEW")
    _require(list(events["TRANSITION_PERMUTED"][2]["transition_order"]) == [common_keys[1], common_keys[0]], "PERMUTED_FINAL_ORDER")
    return {"matched_sites": list(SITES), "matched_F_budget": expected_f, "matched_G_count": 3, "oneshot_G_count": 1, "permuted_no_future_preview": True}


def _atomic_terminal(obj: Mapping[str, Any]) -> pathlib.Path:
    _require(not OUTPUT_DIR.exists(), "OUTPUT_ALREADY_EXISTS")
    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    stage = OUTPUT_DIR.parent / ("." + OUTPUT_DIR.name + ".stage-" + str(os.getpid()))
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    p = stage / TERMINAL_NAME
    data = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    with p.open("xb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(stage, OUTPUT_DIR)
    dfd = os.open(str(OUTPUT_DIR.parent), os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return OUTPUT_DIR / TERMINAL_NAME


def _median33(values: Sequence[float]) -> float:
    _require(len(values) == 33, "MEDIAN_DENOMINATOR")
    xs = sorted(float(x) for x in values)
    _require(all(math.isfinite(x) for x in xs), "MEDIAN_NONFINITE")
    return xs[16]


def development_gate(family_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _require(len(family_results) == 33, "DEVELOPMENT_RESULT_COUNT")
    cs = [float(x["endpoint"]["C"]["static"]) for x in family_results]
    cp = [float(x["endpoint"]["C"]["permuted"]) for x in family_results]
    ci = [float(x["endpoint"]["C"]["information"]) for x in family_results]
    da = [float(x["endpoint"]["D"]["ALIGNED_RECURSION"]) for x in family_results]
    positive_static = sum(x > 0.0 for x in cs)
    positive_permuted = sum(x > 0.0 for x in cp)
    med_static = _median33(cs); med_permuted = _median33(cp); med_info = _median33(ci); med_da = _median33(da)
    guard_names = (
        "assignment_and_provenance", "call_geometry_or_arm_matching", "branch_blindness",
        "graph_admissibility", "immediate_action_invariance", "score_completeness",
        "isolation", "G_nonforcing",
    )
    violations = {g: sum(not bool(x["guards"].get(g, False)) for x in family_results) for g in guard_names}
    checks = {
        "positive_static_ge_22": positive_static >= 22,
        "positive_permuted_ge_22": positive_permuted >= 22,
        "median_C_static_ge_0_05": med_static >= 0.05,
        "median_C_permuted_ge_0_05": med_permuted >= 0.05,
        "median_C_information_gt_0": med_info > 0.0,
        "median_D_ALIGNED_gt_0": med_da > 0.0,
        "zero_validity_isolation_provenance_randomization_violations": all(v == 0 for v in violations.values()),
    }
    passed = all(checks.values())
    return {
        "role": "FUTILITY_READINESS_ONLY_NOT_SUPPORT",
        "n": 33, "k_positive_required": 22,
        "positive_static": positive_static, "positive_permuted": positive_permuted,
        "median_C_static": med_static, "median_C_permuted": med_permuted,
        "median_C_information": med_info, "median_D_ALIGNED": med_da,
        "guard_violations": violations, "checks": checks,
        "C_oneshot_used_as_development_gate": False,
        "passed": passed,
        "terminal_label": "DEVELOPMENT_READINESS_PASS_NOT_SCIENTIFIC_SUPPORT" if passed else "DEVELOPMENT_FUTILITY_STOP_CONFIRMATION_REMAINS_SEALED",
    }


def _runtime_factory_default(game_file: str):
    from alfworld_runtime import AlfRuntime
    return AlfRuntime(game_file, max_steps=12)


def _slot_replay_guard(runtime_factory: Callable[[str], Any], game_file: pathlib.Path, family: Mapping[str, Any], witness: Mapping[str, Any], expected_branch_candidates: Sequence[str]) -> dict[str, Any]:
    env = runtime_factory(str(game_file))
    try:
        resolve_surface = _build_symbolic_surface_resolver(env)
        for cmd in family["allowed_pre_reset_history_canonical"]:
            surface = _runtime_surface_command(env, resolve_surface, cmd, "PRE_RESET_HISTORY_NOT_ADMISSIBLE")
            rec = env.step(surface); _require(rec.error is None, "PRE_RESET_HISTORY_STEP_ERROR")
        reset_candidates = tuple(sorted(str(x) for x in env.admissible_commands))
        immediate_surface = _runtime_surface_command(env, resolve_surface, family["immediate_next_command_canonical"], "IMMEDIATE_NOT_ADMISSIBLE")
        rec = env.step(immediate_surface); _require(rec.error is None, "IMMEDIATE_STEP_ERROR")
        for step in witness["common_prefix_steps"]:
            surface = _runtime_surface_command(env, resolve_surface, step["command"], "COMMON_NOT_ADMISSIBLE")
            rec = env.step(surface); _require(rec.error is None, "COMMON_STEP_ERROR")
        branch = tuple(sorted(str(x) for x in env.admissible_commands))
        _require(branch == tuple(expected_branch_candidates), "BRANCH_CANDIDATE_REPLAY_MISMATCH")
        return {"reset_candidate_sha256": _sha_obj(list(reset_candidates)), "branch_candidate_sha256": _sha_obj(list(branch)), "replay_steps": len(family["allowed_pre_reset_history_canonical"]) + 3}
    finally:
        env.close()


def _execute_family(
    family: Mapping[str, Any], witness: Mapping[str, Any], assignment: Mapping[str, Any],
    torch: Any, tokenizer: Any, model: Any, runtime_factory: Callable[[str], Any],
) -> dict[str, Any]:
    carrier, evaluator_secret = _split_family(family)
    common_steps = witness["common_prefix_steps"]
    common_keys = list(carrier["common_prefix_transition_keys"])
    _require([x["transition_key"] for x in common_steps] == common_keys, "WITNESS_COMMON_KEYS")
    game = _game_file(carrier["source_graph_id"])
    arm_order = list(assignment["arm_permutation"])

    events: dict[str, list[dict[str, Any]]] = {a: [] for a in EXACT_ARMS}
    reset_maps: dict[str, dict[str, float]] = {}
    branch_maps_by_arm: dict[str, dict[str, float]] = {}
    diagnostic_hashes: dict[str, dict[str, str]] = {a: {} for a in EXACT_ARMS}
    transition_features: dict[str, list[float]] = {}

    def score_arms_now(site: str, site_packet: Mapping[str, Any], observed: Sequence[str]) -> None:
        # Called at the actual chronological site. Only the causally observed feature subset
        # is passed into the arm adapter; future transition features do not yet exist here.
        visible_features = {k: transition_features[k] for k in observed}
        for arm in arm_order:
            amap, event = _arm_map_at_site(
                arm, site, site_packet["base_scores"], site_packet["action_features"], z0,
                visible_features, observed,
            )
            events[arm].append(event)
            diagnostic_hashes[arm][site] = _sha_obj(amap)
            if site == "RESET_PREFIX": reset_maps[arm] = amap
            if site == "BRANCH_POINT": branch_maps_by_arm[arm] = amap

    # One branch-blind carrier trace constructs immutable model inputs causally and calls
    # G at each frozen site before any later transition is observed/featurized.
    env = runtime_factory(str(game))
    try:
        resolve_surface = _build_symbolic_surface_resolver(env)
        for cmd in carrier["allowed_pre_reset_history_canonical"]:
            surface = _runtime_surface_command(env, resolve_surface, cmd, "CARRIER_HISTORY_NOT_ADMISSIBLE")
            rec = env.step(surface); _require(rec.error is None, "CARRIER_HISTORY_STEP_ERROR")
        reset_obs = str(env.observation); reset_candidates = tuple(sorted(str(x) for x in env.admissible_commands))
        immediate_surface = _runtime_surface_command(env, resolve_surface, carrier["immediate_next_command_canonical"], "CARRIER_IMMEDIATE_NOT_ADMISSIBLE")
        reset_site = _score_site(torch, tokenizer, model, carrier["goal_canonical"], reset_obs, reset_candidates)
        z0 = rt.native_hidden_feature(torch, tokenizer, model, reset_site["prompt"].encode("utf-8"))
        score_arms_now("RESET_PREFIX", reset_site, [])

        imm = env.step(immediate_surface); _require(imm.error is None, "CARRIER_IMMEDIATE_STEP_ERROR")
        step1 = common_steps[0]
        step1_surface = _runtime_surface_command(env, resolve_surface, step1["command"], "CARRIER_COMMON1_NOT_ADMISSIBLE")
        r1 = env.step(step1_surface); _require(r1.error is None, "CARRIER_COMMON1_STEP_ERROR")
        transition_features[common_keys[0]] = rt.native_hidden_feature(
            torch, tokenizer, model, rt.canonical_transition_payload(step1["command"], str(r1.observation))
        )
        post1_candidates = tuple(sorted(str(x) for x in env.admissible_commands))
        post1_site = _score_site(torch, tokenizer, model, carrier["goal_canonical"], str(env.observation), post1_candidates)
        score_arms_now("POST_TRANSITION_1", post1_site, [common_keys[0]])

        step2 = common_steps[1]
        step2_surface = _runtime_surface_command(env, resolve_surface, step2["command"], "CARRIER_COMMON2_NOT_ADMISSIBLE")
        r2 = env.step(step2_surface); _require(r2.error is None, "CARRIER_COMMON2_STEP_ERROR")
        transition_features[common_keys[1]] = rt.native_hidden_feature(
            torch, tokenizer, model, rt.canonical_transition_payload(step2["command"], str(r2.observation))
        )
        branch_candidates = tuple(sorted(str(x) for x in env.admissible_commands))
        branch_site = _score_site(torch, tokenizer, model, carrier["goal_canonical"], str(env.observation), branch_candidates)
        score_arms_now("BRANCH_POINT", branch_site, list(common_keys))
    finally:
        env.close()

    geometry = _validate_geometry(events, common_keys)
    _require(set(reset_maps) == set(EXACT_ARMS) and set(branch_maps_by_arm) == set(EXACT_ARMS), "ARM_SCORE_MAP_COVERAGE")
    _require(_canon(branch_maps_by_arm["STATIC_ONESHOT"]) == _canon(branch_maps_by_arm["STATIC_REPEAT"]), "ONESHOT_STATIC_RELATION")

    # Each randomized physical slot gets an independent environment replay. G is a pure,
    # nonexecuting score transform; all carrier inputs used above are immutable/sealed.
    slot_records = []
    for slot_index, arm in enumerate(arm_order):
        slot_guard = _slot_replay_guard(runtime_factory, game, carrier, witness, branch_candidates)
        slot_records.append({"slot_index": slot_index, "arm_id": arm, "slot_guard": slot_guard})

    base_top = _top_set(reset_maps["NO_CARRY"])
    immediate_invariance = all(_top_set(reset_maps[a]) == base_top for a in EXACT_ARMS)

    ordered_maps = {a: copy.deepcopy(branch_maps_by_arm[a]) for a in EXACT_ARMS}
    candidate_keys = set(branch_candidates)
    score_complete = all(set(m) == candidate_keys and all(math.isfinite(float(v)) for v in m.values()) for m in ordered_maps.values())
    _require(score_complete, "BRANCH_SCORE_COMPLETENESS")
    seal_bytes = _canon(ordered_maps)
    seal_sha = hashlib.sha256(seal_bytes).hexdigest()
    # Canonical serialization sorts object keys for the content seal. V4 evaluation,
    # however, requires the explicitly frozen EXACT_ARMS insertion order. Preserve that
    # order in a deep-copied sealed view rather than round-tripping through sorted JSON.
    sealed_maps = {a: copy.deepcopy(ordered_maps[a]) for a in EXACT_ARMS}

    # Evaluator-only A/B classes are first consumed after score-map seal. Their frozen
    # identities remain symbolic PDDL; only now translate them to the exact surface-action
    # keys used by the sealed policy score maps.
    branch_A_symbolic = list(evaluator_secret["branch_A_equivalence_class"])
    branch_B_symbolic = list(evaluator_secret["branch_B_equivalence_class"])
    branch_A = [resolve_surface(x) for x in branch_A_symbolic]
    branch_B = [resolve_surface(x) for x in branch_B_symbolic]
    _require(len(branch_A) == len(set(branch_A)) and len(branch_B) == len(set(branch_B)), "BRANCH_SURFACE_MAPPING_NOT_INJECTIVE")
    graph_admissible = set(branch_A) <= candidate_keys and set(branch_B) <= candidate_keys and bool(branch_A) and bool(branch_B) and not (set(branch_A) & set(branch_B))
    _require(graph_admissible, "BRANCH_GRAPH_ADMISSIBILITY")
    endpoint = rt.v4_endpoint_from_sealed_scores(sealed_maps, branch_A, branch_B)

    assignment_ok = (
        assignment.get("structural_family_key_sha256") == gv2.structural_family_key(family)
        and assignment.get("split_namespace") == "CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1"
        and list(assignment.get("arm_permutation", [])) == [x["arm_id"] for x in slot_records]
        and set(assignment.get("arm_permutation", [])) == set(EXACT_ARMS)
    )
    branch_blind = set(carrier).isdisjoint(EVALUATOR_KEYS)
    isolation = len({x["slot_index"] for x in slot_records}) == 6 and len(slot_records) == 6
    gsrc = inspect.getsource(rt.G_delta) + inspect.getsource(rt.adjust_score_map)
    g_nonforcing = all(token not in gsrc for token in ('.step(', 'execute_environment_action', 'force_one_action', 'mask_policy_to_single_action', 'mutate_environment'))
    guards = {
        "assignment_and_provenance": assignment_ok,
        "call_geometry_or_arm_matching": geometry["matched_G_count"] == 3 and geometry["oneshot_G_count"] == 1,
        "branch_blindness": branch_blind,
        "graph_admissibility": graph_admissible,
        "immediate_action_invariance": immediate_invariance,
        "score_completeness": score_complete,
        "isolation": isolation,
        "G_nonforcing": g_nonforcing,
    }
    return {
        "family_id": assignment["family_id"],
        "structural_family_key_sha256": assignment["structural_family_key_sha256"],
        "source_graph_id": carrier["source_graph_id"],
        "assignment_index": assignment["assignment_index"],
        "arm_permutation": list(assignment["arm_permutation"]),
        "score_map_seal_sha256": seal_sha,
        "sealed_branch_score_maps": sealed_maps,
        "diagnostic_score_map_sha256": diagnostic_hashes,
        "branch_A_equivalence_class": branch_A_symbolic,
        "branch_B_equivalence_class": branch_B_symbolic,
        "endpoint": endpoint,
        "guards": guards,
        "geometry": geometry,
        "slot_records": slot_records,
        "oneshot_static_branch_maps_equal": True,
    }

def execute_development(
    *, runtime_factory: Callable[[str], Any] | None = None,
    model_loader: Callable[[], tuple[Any, Any, Any]] | None = None,
) -> dict[str, Any]:
    _require(os.environ.get("CPDS_DEVELOPMENT_AUTHORIZATION") == "RESEARCH_DECISION_BOUND", "RESEARCH_DECISION_AUTHORIZATION")
    _require(not OUTPUT_DIR.exists(), "OUTPUT_ALREADY_EXISTS")
    auth = _authorities()
    source = auth["source"]
    runtime_factory = runtime_factory or _runtime_factory_default
    model_loader = model_loader or rt._load_model_runtime
    torch, tokenizer, model = model_loader()
    results = []
    for family in source["families"]:
        sk = gv2.structural_family_key(family)
        assignment = auth["assignment_by_key"][sk]
        witness = auth["witness_by_graph"][family["source_graph_id"]]
        results.append(_execute_family(family, witness, assignment, torch, tokenizer, model, runtime_factory))
    gate = development_gate(results)
    terminal = {
        "schema": "PLANCARRY_CPDS_V4_DEVELOPMENT_TERMINAL_V1",
        "phase": "DEVELOPMENT_ONLY",
        "scientific_result": gate["terminal_label"],
        "experiment_id": auth["semantics"]["experiment_id"],
        "prediction_id": auth["semantics"]["prediction_id"],
        "hypothesis_id": auth["semantics"]["hypothesis_id"],
        "runtime_git_commit": rt._git("rev-parse", "HEAD"),
        "runtime_git_tree": rt._git("rev-parse", "HEAD^{tree}"),
        "execution_semantics_sha256": SEMANTICS_SHA256,
        "development_family_count": len(results),
        "family_results": results,
        "development_gate": gate,
        "confirmation_status": "HARD_SEALED_NO_RUNTIME_ROUTE",
        "replacement_resampling_redraw": False,
        "planroute": "USER_NOOP_RETIRED",
    }
    terminal["terminal_sha256"] = _sha_obj(terminal)
    p = _atomic_terminal(terminal)
    print(json.dumps({"status": gate["terminal_label"], "terminal_path": str(p), "terminal_sha256": terminal["terminal_sha256"]}, sort_keys=True))
    return terminal


def main() -> int:
    try:
        execute_development()
    except TechnicalInvalid as exc:
        # No partial family endpoints are written. For a genuinely ResearchDecision-bound
        # attempt, persist one deterministic technical terminal only when the output path
        # was absent. Unauthorized/manual invocations never create an artifact.
        technical={
            "schema":"PLANCARRY_CPDS_V4_DEVELOPMENT_TECHNICAL_TERMINAL_V1",
            "phase":"DEVELOPMENT_ONLY",
            "scientific_result":"TECHNICAL_INVALID_ENTIRE_SPLIT_NOT_ASSESSED",
            "error":str(exc),
            "partial_scientific_outcomes_exposed":False,
            "confirmation_status":"HARD_SEALED_NO_RUNTIME_ROUTE",
            "planroute":"USER_NOOP_RETIRED",
        }
        technical["terminal_sha256"]=_sha_obj(technical)
        if os.environ.get("CPDS_DEVELOPMENT_AUTHORIZATION")=="RESEARCH_DECISION_BOUND" and not OUTPUT_DIR.exists():
            try: _atomic_terminal(technical)
            except TechnicalInvalid: pass
        print(json.dumps({"status":technical["scientific_result"],"error":str(exc),"confirmation_status":technical["confirmation_status"]},sort_keys=True),file=sys.stderr)
        return 70
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
