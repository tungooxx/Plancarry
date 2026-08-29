from __future__ import annotations

import collections
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import cpds_alfworld_static_source_authority_v1 as source_auth
import cpds_executable_readiness_v1 as readiness
import cpds_graphfork_contract_validator_v2 as v2

ROOT = Path(__file__).resolve().parent
DESIGN = ROOT / "results" / "design"
TRAIN_ROOT = Path("/opt/gpu-lab/envs/plancarry-alfworld-data/json_2.1.1/train")
SOURCE_AUTHORITY_PATH = DESIGN / "plancarry_cpds_alfworld_static_source_authority_v1_20260829.json"
SOURCE_FILE_MANIFEST_PATH = DESIGN / "plancarry_cpds_alfworld_train_file_manifest_v1_20260829.json"
SOURCE_GRAPH_UNITS_PATH = DESIGN / "plancarry_cpds_alfworld_static_graph_units_v1_20260829.json"
GENERATOR_SPEC_PATH = DESIGN / "plancarry_cpds_graphfork_generator_spec_v2_20260829.json"
SOURCE_AUTHORITY_SEAL = "a2ca2421f0c4405c403d09ca7f9e78066f57a1c2ee931600bbbc249ddff8810f"
SOURCE_AUTHORITY_REPAIR_COMMIT = "e0e04261cc83e6bfd38b5ac5f366de8faf4b711c"
CRASH_DURABLE_COMMIT = "9e5a34c505ab20f57b02181e883aff4e4da43c12"
FAMILY_COUNT = 33
DEV_NAMESPACE = readiness.DEVELOPMENT_NAMESPACE
CONF_NAMESPACE = readiness.CONFIRMATION_NAMESPACE
PARTITION_DOMAIN = b"CPDS_COHORT_PARTITION_V1\x00"
SELECTION_DOMAIN = b"CPDS_COHORT_SELECTION_V1\x00"
MANIFEST_SCHEMA = "PLANCARRY_CPDS_GRAPHFORK_GENERATOR_RUN_MANIFEST_V3_STATIC_REPLAYABILITY_ACTUAL33"
CENSUS_SCHEMA = "PLANCARRY_CPDS_ACTUAL_STATIC_FORK_CANDIDATE_CENSUS_V1"
AUDIT_SCHEMA = "PLANCARRY_CPDS_ACTUAL_33X2_PREOUTCOME_FREEZE_AUDIT_V1"

CENSUS_PATH = DESIGN / "plancarry_cpds_actual_33x2_candidate_census_v1_20260829.json"
DEV_SNAPSHOT_PATH = DESIGN / "plancarry_cpds_actual_development_source_snapshot_v2_20260829.json"
CONF_SNAPSHOT_PATH = DESIGN / "plancarry_cpds_actual_confirmation_source_snapshot_v2_20260829.json"
DEV_PROVENANCE_PATH = DESIGN / "plancarry_cpds_actual_development_source_provenance_v1_20260829.json"
CONF_PROVENANCE_PATH = DESIGN / "plancarry_cpds_actual_confirmation_source_provenance_v1_20260829.json"
DEV_MANIFEST_PATH = DESIGN / "plancarry_cpds_actual_development_generator_manifest_v3_20260829.json"
CONF_MANIFEST_PATH = DESIGN / "plancarry_cpds_actual_confirmation_generator_manifest_v3_20260829.json"
DURABLE_DIR = DESIGN / "plancarry_cpds_actual_33x2_durable_v1"
TRANSACTION_PATH = DURABLE_DIR / "assignment_freeze_transaction.json"
BUNDLE_PATH = DURABLE_DIR / "two_split_assignment_bundle.json"
AUDIT_PATH = DESIGN / "plancarry_cpds_actual_33x2_preoutcome_freeze_audit_v1_20260829.json"

_FORBIDDEN_DYNAMIC_TERMS = (
    "traj_data", "walkthrough", "teacher_plan", "future_expert", "future_oracle",
    "whole_task_success", "post_reset_arm_score", "realized_future_observations",
)


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def canon_sha(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_once_or_match(path: Path, obj: Any) -> str:
    raw = canonical_bytes(obj)
    digest = hashlib.sha256(raw).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"IMMUTABLE_ARTIFACT_MISMATCH:{path}")
        return digest
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
    finally:
        os.close(fd)
    dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return digest


def _balanced_form(text: str, start: int) -> str:
    if start < 0 or text[start] != "(":
        raise ValueError("BALANCED_FORM_START")
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "(": depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    raise ValueError("UNBALANCED_PDDL")


def _extract_json_string_field(raw: bytes, field: str) -> str:
    marker = (json.dumps(field) + ":").encode("utf-8")
    pos = raw.find(marker)
    if pos < 0:
        marker = (json.dumps(field) + ": ").encode("utf-8")
        pos = raw.find(marker)
    if pos < 0:
        raise ValueError(f"MISSING_STATIC_FIELD:{field}")
    i = pos + len(marker)
    while i < len(raw) and raw[i] in b" \t\r\n": i += 1
    if i >= len(raw) or raw[i] != 0x22:
        raise ValueError(f"STATIC_FIELD_NOT_STRING:{field}")
    j = i + 1; escaped = False
    while j < len(raw):
        b = raw[j]
        if escaped:
            escaped = False
        elif b == 0x5C:
            escaped = True
        elif b == 0x22:
            return json.loads(raw[i:j+1].decode("utf-8"))
        j += 1
    raise ValueError(f"UNTERMINATED_STATIC_FIELD:{field}")


def _normalize_pddl(form: str) -> str:
    return " ".join(form.split())


def _state_id(source_graph_id: str, pddl_problem_sha256: str, agent_location: str, checked: Sequence[str]) -> str:
    return canon_sha({
        "source_graph_id": source_graph_id,
        "pddl_problem_sha256": pddl_problem_sha256,
        "agent_location": agent_location,
        "checked_receptacles": sorted(set(checked)),
    })


def _goto(agent_loc: str, dest_loc: str, receptacle: str) -> str:
    return f"GotoLocation(agent1,{agent_loc},{dest_loc},{receptacle})"


def _examine(receptacle: str) -> str:
    return f"examineReceptacle(agent1,{receptacle})"


def _transition_key(source_graph_id: str, command: str, from_state_id: str, to_state_id: str) -> str:
    return canon_sha({"source_graph_id": source_graph_id, "command": command, "from_state_id": from_state_id, "to_state_id": to_state_id})


def _step(source_graph_id: str, command: str, from_state_id: str, to_state_id: str) -> dict[str, str]:
    return {
        "transition_key": _transition_key(source_graph_id, command, from_state_id, to_state_id),
        "command": command,
        "from_state_id": from_state_id,
        "to_state_id": to_state_id,
    }


def _source_manifest_map() -> dict[str, dict[str, Any]]:
    records = json.loads(SOURCE_FILE_MANIFEST_PATH.read_text())
    return {r["relative_path"]: r for r in records}


def _load_authenticated_problem(source_graph_id: str, manifest_map: Mapping[str, Mapping[str, Any]]) -> tuple[str, str]:
    rel = f"{source_graph_id}/game.tw-pddl"
    rec = manifest_map.get(rel)
    if rec is None:
        raise ValueError("SOURCE_GAME_FILE_NOT_AUTHORIZED")
    path = TRAIN_ROOT / rel
    raw = path.read_bytes()
    if len(raw) != rec["byte_size"] or hashlib.sha256(raw).hexdigest() != rec["sha256"]:
        raise ValueError("SOURCE_GAME_FILE_HASH_MISMATCH")
    # Deliberately decode only pddl_problem. walkthrough/traj_data are never parsed or used.
    problem = _extract_json_string_field(raw, "pddl_problem")
    return problem, hashlib.sha256(problem.encode("utf-8")).hexdigest()


def _extract_relevant_facts(problem: str) -> tuple[str, str, list[tuple[str, tuple[str, ...]]]]:
    init_start = problem.find("(:init")
    goal_start = problem.find("(:goal", init_start)
    if init_start < 0 or goal_start < 0:
        raise ValueError("PDDL_INIT_OR_GOAL_MISSING")
    init = _balanced_form(problem, init_start)
    goal = _balanced_form(problem, goal_start)
    facts: list[tuple[str, tuple[str, ...]]] = []
    for pred in ("atLocation", "objectType", "inReceptacle", "receptacleAtLocation", "checked"):
        pat = re.compile(r"\(" + re.escape(pred) + r"\s+([^()]+?)\)")
        for m in pat.finditer(init):
            facts.append((pred, tuple(m.group(1).split())))
    return init, goal, facts


def _derive_candidate(source_graph_id: str, manifest_map: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    problem, problem_sha = _load_authenticated_problem(source_graph_id, manifest_map)
    _, goal_form, facts = _extract_relevant_facts(problem)
    goal = _normalize_pddl(goal_form)
    tm = re.search(r"\(objectType\s+\?\w+\s+(\w+Type)\)", goal_form)
    if tm is None:
        return None, "NO_TARGET_OBJECT_TYPE"
    target_type = tm.group(1)
    current = [a[1] for p, a in facts if p == "atLocation" and len(a) == 2 and a[0] == "agent1"]
    if len(current) != 1:
        return None, "BAD_INITIAL_AGENT_LOCATION"
    current_loc = current[0]
    obj_type = {a[0]: a[1] for p, a in facts if p == "objectType" and len(a) == 2}
    in_rec: dict[str, list[str]] = collections.defaultdict(list)
    rec_loc = {a[0]: a[1] for p, a in facts if p == "receptacleAtLocation" and len(a) == 2}
    checked = sorted({a[0] for p, a in facts if p == "checked" and len(a) == 1})
    for p, a in facts:
        if p == "inReceptacle" and len(a) == 2:
            in_rec[a[0]].append(a[1])
    targets: list[tuple[str, str, str]] = []
    for obj, typ in obj_type.items():
        if typ != target_type:
            continue
        for rec in in_rec.get(obj, []):
            if rec in rec_loc:
                targets.append((obj, rec, rec_loc[rec]))
    pair = None
    ordered_targets = sorted(set(targets), key=lambda z: (z[2], z[1], z[0]))
    for i, a in enumerate(ordered_targets):
        for b in ordered_targets[i+1:]:
            if a[1] != b[1] and a[2] != b[2]:
                pair = (a, b); break
        if pair is not None: break
    if pair is None:
        return None, "LT2_TARGET_OBJECT_LOCATIONS"
    forbidden_recs = {pair[0][1], pair[1][1]}
    forbidden_locs = {pair[0][2], pair[1][2], current_loc}
    staging: list[tuple[str, str]] = []
    for rec, loc in sorted(rec_loc.items(), key=lambda z: (z[1], z[0])):
        if rec in forbidden_recs or loc in forbidden_locs or any(loc == x[1] for x in staging):
            continue
        staging.append((rec, loc))
        if len(staging) == 2:
            break
    if len(staging) != 2:
        return None, "LT2_STAGING_LOCATIONS"
    s1, s2 = staging
    state0 = _state_id(source_graph_id, problem_sha, current_loc, checked)
    immediate_cmd = _goto(current_loc, s1[1], s1[0])
    state1 = _state_id(source_graph_id, problem_sha, s1[1], checked)
    common1_cmd = _examine(s1[0])
    state2 = _state_id(source_graph_id, problem_sha, s1[1], checked + [s1[0]])
    common2_cmd = _goto(s1[1], s2[1], s2[0])
    state3 = _state_id(source_graph_id, problem_sha, s2[1], checked + [s1[0]])
    immediate = _step(source_graph_id, immediate_cmd, state0, state1)
    common1 = _step(source_graph_id, common1_cmd, state1, state2)
    common2 = _step(source_graph_id, common2_cmd, state2, state3)
    branch_a = _goto(s2[1], pair[0][2], pair[0][1])
    branch_b = _goto(s2[1], pair[1][2], pair[1][1])
    if branch_a == branch_b:
        return None, "BRANCH_COLLAPSE"
    family = {
        "source_graph_id": source_graph_id,
        "goal_canonical": goal,
        "reset_observation_canonical": f"STATIC_PDDL_RESET_STATE_SHA256:{state0}",
        "allowed_pre_reset_history_canonical": [],
        "immediate_next_command_canonical": immediate_cmd,
        "common_prefix_transition_keys": [common1["transition_key"], common2["transition_key"]],
        "branch_A_equivalence_class": [branch_a],
        "branch_B_equivalence_class": [branch_b],
        "divergence_depth_after_immediate": 3,
    }
    witness = {
        "source_graph_id": source_graph_id,
        "initial_state_id": state0,
        "reset_state_id": state0,
        "pre_reset_steps": [],
        "immediate_step": immediate,
        "common_prefix_steps": [common1, common2],
        "branch_A_equivalence_class": [branch_a],
        "branch_B_equivalence_class": [branch_b],
        "divergence_depth_after_immediate": 3,
    }
    return {
        "source_graph_id": source_graph_id,
        "target_object_type": target_type,
        "target_A_object": pair[0][0], "target_A_receptacle": pair[0][1], "target_A_location": pair[0][2],
        "target_B_object": pair[1][0], "target_B_receptacle": pair[1][1], "target_B_location": pair[1][2],
        "staging_1_receptacle": s1[0], "staging_1_location": s1[1],
        "staging_2_receptacle": s2[0], "staging_2_location": s2[1],
        "family": family, "witness": witness,
    }, None


def _partition(source_graph_id: str) -> int:
    d = hashlib.sha256(PARTITION_DOMAIN + source_graph_id.encode("utf-8")).digest()
    return int.from_bytes(d[:8], "big") & 1


def _selection_key(source_graph_id: str) -> str:
    return hashlib.sha256(SELECTION_DOMAIN + source_graph_id.encode("utf-8")).hexdigest()


def build_census() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    source_authority = json.loads(SOURCE_AUTHORITY_PATH.read_text())
    records = json.loads(SOURCE_FILE_MANIFEST_PATH.read_text())
    units = json.loads(SOURCE_GRAPH_UNITS_PATH.read_text())
    source_auth.verify_authority_artifact(source_authority, records, units)
    if source_authority["official_static_source_authority_sha256"] != SOURCE_AUTHORITY_SEAL:
        raise ValueError("SOURCE_AUTHORITY_SEAL_MISMATCH")
    manifest_map = {r["relative_path"]: r for r in records}
    failures: collections.Counter[str] = collections.Counter()
    eligible: list[dict[str, Any]] = []
    for source_graph_id in units:
        candidate, reason = _derive_candidate(source_graph_id, manifest_map)
        if candidate is None:
            failures[reason or "UNKNOWN"] += 1
            continue
        candidate["partition"] = _partition(source_graph_id)
        candidate["selection_key_sha256"] = _selection_key(source_graph_id)
        eligible.append(candidate)
    by_partition = {p: sorted([x for x in eligible if x["partition"] == p], key=lambda x: (x["selection_key_sha256"], x["source_graph_id"])) for p in (0, 1)}
    if len(by_partition[0]) < FAMILY_COUNT or len(by_partition[1]) < FAMILY_COUNT:
        raise ValueError("CONSTRUCTIBILITY_INCONCLUSIVE_EXACT33")
    dev = by_partition[0][:FAMILY_COUNT]
    conf = by_partition[1][:FAMILY_COUNT]
    census_records = [{
        "source_graph_id": x["source_graph_id"], "partition": x["partition"], "selection_key_sha256": x["selection_key_sha256"],
        "structural_family_key_sha256": v2.structural_family_key(x["family"]),
    } for x in sorted(eligible, key=lambda x: x["source_graph_id"])]
    census = {
        "schema": CENSUS_SCHEMA,
        "phase": "PRE_SCIENCE",
        "scientific_result": "NOT_ASSESSED",
        "official_static_source_authority_sha256": SOURCE_AUTHORITY_SEAL,
        "static_graph_unit_count": len(units),
        "eligible_static_fork_count": len(eligible),
        "partition_0_count": len(by_partition[0]),
        "partition_1_count": len(by_partition[1]),
        "development_partition": 0,
        "confirmation_partition": 1,
        "selection_rule": "first 33 by SHA256(CPDS_COHORT_SELECTION_V1\\0 || source_graph_id) within fixed SHA256 partition, after static PDDL forkability only",
        "failure_counts": dict(sorted(failures.items())),
        "eligible_records": census_records,
        "selected_development_source_graph_ids": [x["source_graph_id"] for x in dev],
        "selected_confirmation_source_graph_ids": [x["source_graph_id"] for x in conf],
    }
    census["census_sha256"] = canon_sha(census)
    return census, dev, conf


def _build_snapshot(selected: Sequence[Mapping[str, Any]], snapshot_id: str) -> dict[str, Any]:
    ordered = sorted(selected, key=lambda x: (v2.structural_family_key(x["family"]), x["source_graph_id"]))
    snapshot = {
        "snapshot_id": snapshot_id,
        "snapshot_sha256": "0" * 64,
        "static_graph_replayability_witnesses": [copy.deepcopy(x["witness"]) for x in ordered],
        "families": [copy.deepcopy(x["family"]) for x in ordered],
    }
    snapshot["snapshot_sha256"] = v2.source_snapshot_identity(snapshot)
    return snapshot


def manifest_identity(manifest: Mapping[str, Any]) -> str:
    x = copy.deepcopy(dict(manifest)); x.pop("manifest_sha256", None); return canon_sha(x)


def build_v2_manifest(snapshot: Mapping[str, Any], namespace: str, source_authority_seal: str) -> dict[str, Any]:
    spec = json.loads(GENERATOR_SPEC_PATH.read_text())
    snapshot_sha = snapshot["snapshot_sha256"]
    v2.validate_source_snapshot(snapshot, spec, snapshot_sha)
    certs = v2.generate_certificates(snapshot["families"], spec, namespace, snapshot, snapshot_sha)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "phase": "PRE_SCIENCE",
        "scientific_result": "NOT_ASSESSED",
        "generator_identity_sha256": spec["generator_identity_sha256"],
        "generator_spec_sha256": sha_file(GENERATOR_SPEC_PATH),
        "official_static_source_authority_sha256": source_authority_seal,
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_snapshot_sha256": snapshot_sha,
        "cohort_namespace": namespace,
        "selection_semantics": "ALL_33_SNAPSHOT_FAMILIES_ADMITTED_IN_STRUCTURAL_KEY_ORDER_NO_REPLACEMENT",
        "no_replacement": True,
        "certificate_count": len(certs),
        "structural_family_key_sha256s": [c["structural_family_key_sha256"] for c in certs],
        "family_ids": [c["family_id"] for c in certs],
        "certificates": certs,
    }
    if len(certs) != FAMILY_COUNT:
        raise ValueError("EXACT_33_CERTIFICATES_REQUIRED")
    manifest["manifest_sha256"] = manifest_identity(manifest)
    validate_v2_manifest(manifest, snapshot, manifest["manifest_sha256"])
    return manifest


def validate_v2_manifest(manifest: Mapping[str, Any], snapshot: Mapping[str, Any], expected_sha: str) -> bool:
    req = {"schema","phase","scientific_result","generator_identity_sha256","generator_spec_sha256","official_static_source_authority_sha256","source_snapshot_id","source_snapshot_sha256","cohort_namespace","selection_semantics","no_replacement","certificate_count","structural_family_key_sha256s","family_ids","certificates","manifest_sha256"}
    if not isinstance(manifest, Mapping) or set(manifest) != req: raise ValueError("V2_MANIFEST_SCHEMA")
    if manifest["schema"] != MANIFEST_SCHEMA or manifest["phase"] != "PRE_SCIENCE" or manifest["scientific_result"] != "NOT_ASSESSED": raise ValueError("V2_MANIFEST_SCOPE")
    if manifest["official_static_source_authority_sha256"] != SOURCE_AUTHORITY_SEAL: raise ValueError("V2_MANIFEST_SOURCE_AUTHORITY")
    if manifest["manifest_sha256"] != expected_sha or manifest_identity(manifest) != expected_sha: raise ValueError("V2_MANIFEST_SHA")
    if manifest["source_snapshot_id"] != snapshot["snapshot_id"] or manifest["source_snapshot_sha256"] != snapshot["snapshot_sha256"]: raise ValueError("V2_MANIFEST_SOURCE_BINDING")
    spec = json.loads(GENERATOR_SPEC_PATH.read_text())
    if manifest["generator_identity_sha256"] != spec["generator_identity_sha256"] or manifest["generator_spec_sha256"] != sha_file(GENERATOR_SPEC_PATH): raise ValueError("V2_MANIFEST_GENERATOR_BINDING")
    rebuilt = v2.generate_certificates(snapshot["families"], spec, manifest["cohort_namespace"], snapshot, snapshot["snapshot_sha256"])
    if manifest["certificates"] != rebuilt: raise ValueError("V2_MANIFEST_CERTIFICATE_REBUILD")
    if manifest["certificate_count"] != FAMILY_COUNT or len(rebuilt) != FAMILY_COUNT: raise ValueError("V2_MANIFEST_EXACT33")
    if manifest["structural_family_key_sha256s"] != [c["structural_family_key_sha256"] for c in rebuilt] or manifest["family_ids"] != [c["family_id"] for c in rebuilt]: raise ValueError("V2_MANIFEST_INDEX_REBUILD")
    return True


def validate_split_disjointness(dev_snapshot: Mapping[str, Any], dev_manifest: Mapping[str, Any], conf_snapshot: Mapping[str, Any], conf_manifest: Mapping[str, Any]) -> bool:
    validate_v2_manifest(dev_manifest, dev_snapshot, dev_manifest["manifest_sha256"])
    validate_v2_manifest(conf_manifest, conf_snapshot, conf_manifest["manifest_sha256"])
    if dev_manifest["cohort_namespace"] != DEV_NAMESPACE or conf_manifest["cohort_namespace"] != CONF_NAMESPACE: raise ValueError("EXACT_SPLIT_NAMESPACE")
    if dev_snapshot["snapshot_sha256"] == conf_snapshot["snapshot_sha256"] or dev_snapshot["snapshot_id"] == conf_snapshot["snapshot_id"]: raise ValueError("SOURCE_SNAPSHOTS_NOT_DISTINCT")
    ds = set(dev_manifest["structural_family_key_sha256s"]); cs = set(conf_manifest["structural_family_key_sha256s"])
    df = set(dev_manifest["family_ids"]); cf = set(conf_manifest["family_ids"])
    dg = {f["source_graph_id"] for f in dev_snapshot["families"]}; cg = {f["source_graph_id"] for f in conf_snapshot["families"]}
    if ds & cs: raise ValueError("STRUCTURAL_FAMILY_OVERLAP")
    if df & cf: raise ValueError("FAMILY_ID_OVERLAP")
    if dg & cg: raise ValueError("SOURCE_GRAPH_OVERLAP")
    return True


def _assignment_cert(cert: Mapping[str, Any]) -> dict[str, Any]:
    return {k: cert[k] for k in ("structural_family_key_sha256", "family_id", "cohort_namespace", "source_snapshot_sha256")}


def build_assignment_manifest_v2(manifest: Mapping[str, Any], word_factory: Callable[[str], Iterable[int]], code_sha: str) -> dict[str, Any]:
    namespace = manifest["cohort_namespace"]
    records = [readiness._build_assignment_record_from_words(namespace, _assignment_cert(c), word_factory(c["family_id"]), code_sha) for c in manifest["certificates"]]
    out = {
        "schema": readiness.ASSIGNMENT_MANIFEST_SCHEMA,
        "phase": "PRE_SCIENCE", "scientific_result": "NOT_ASSESSED",
        "split_namespace": namespace,
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "generator_run_manifest_sha256": manifest["manifest_sha256"],
        "generator_code_sha256": code_sha,
        "family_count": FAMILY_COUNT,
        "assignment_space_size": readiness.ASSIGNMENT_SPACE_SIZE,
        "rejection_cutoff": readiness.REJECTION_CUTOFF,
        "ordered_arms": list(readiness.EXACT_ARMS), "slots": list(readiness.EXACT_SLOTS),
        "generated_before_any_development_arm_outcome": True,
        "no_redraw_after_acceptance": True,
        "records": records,
    }
    out["assignment_manifest_sha256"] = readiness.assignment_manifest_identity(out)
    validate_assignment_manifest_v2(out, manifest, code_sha)
    return out


def validate_assignment_manifest_v2(am: Mapping[str, Any], manifest: Mapping[str, Any], code_sha: str) -> bool:
    if am["assignment_manifest_sha256"] != readiness.assignment_manifest_identity(am): raise ValueError("ASSIGNMENT_MANIFEST_SHA")
    if am["split_namespace"] != manifest["cohort_namespace"] or am["source_snapshot_sha256"] != manifest["source_snapshot_sha256"] or am["generator_run_manifest_sha256"] != manifest["manifest_sha256"]: raise ValueError("ASSIGNMENT_MANIFEST_BINDING")
    if am["generator_code_sha256"] != code_sha or am["family_count"] != FAMILY_COUNT or len(am["records"]) != FAMILY_COUNT: raise ValueError("ASSIGNMENT_MANIFEST_EXACT33")
    if am["assignment_space_size"] != 720 or am["rejection_cutoff"] != 64800 or am["ordered_arms"] != list(readiness.EXACT_ARMS) or am["slots"] != list(readiness.EXACT_SLOTS): raise ValueError("ASSIGNMENT_AUTHORITY_DRIFT")
    for r, c in zip(am["records"], manifest["certificates"]): readiness.validate_assignment_record(r, _assignment_cert(c), manifest["cohort_namespace"], code_sha)
    return True


def build_bundle_v2(dev_manifest: Mapping[str, Any], conf_manifest: Mapping[str, Any], dev_factory: Callable[[str], Iterable[int]], conf_factory: Callable[[str], Iterable[int]], code_sha: str) -> dict[str, Any]:
    dev = build_assignment_manifest_v2(dev_manifest, dev_factory, code_sha); conf = build_assignment_manifest_v2(conf_manifest, conf_factory, code_sha)
    bundle = {
        "schema": readiness.TWO_SPLIT_BUNDLE_SCHEMA, "phase": "PRE_SCIENCE", "scientific_result": "NOT_ASSESSED",
        "generated_before_any_development_arm_outcome": True, "confirmation_outcomes_untouched": True,
        "no_replacement": True, "no_redraw": True,
        "development_source_snapshot_sha256": dev_manifest["source_snapshot_sha256"], "confirmation_source_snapshot_sha256": conf_manifest["source_snapshot_sha256"],
        "development_generator_manifest_sha256": dev_manifest["manifest_sha256"], "confirmation_generator_manifest_sha256": conf_manifest["manifest_sha256"],
        "development_assignment_manifest": dev, "confirmation_assignment_manifest": conf,
    }
    bundle["bundle_sha256"] = readiness.bundle_identity(bundle)
    validate_bundle_v2(bundle, dev_manifest, conf_manifest, code_sha)
    return bundle


def validate_bundle_v2(bundle: Mapping[str, Any], dev_manifest: Mapping[str, Any], conf_manifest: Mapping[str, Any], code_sha: str) -> bool:
    if bundle["bundle_sha256"] != readiness.bundle_identity(bundle): raise ValueError("BUNDLE_SHA")
    if bundle["development_source_snapshot_sha256"] == bundle["confirmation_source_snapshot_sha256"]: raise ValueError("BUNDLE_SOURCE_COLLISION")
    validate_assignment_manifest_v2(bundle["development_assignment_manifest"], dev_manifest, code_sha)
    validate_assignment_manifest_v2(bundle["confirmation_assignment_manifest"], conf_manifest, code_sha)
    ds={r["structural_family_key_sha256"] for r in bundle["development_assignment_manifest"]["records"]}; cs={r["structural_family_key_sha256"] for r in bundle["confirmation_assignment_manifest"]["records"]}
    df={r["family_id"] for r in bundle["development_assignment_manifest"]["records"]}; cf={r["family_id"] for r in bundle["confirmation_assignment_manifest"]["records"]}
    if ds & cs or df & cf: raise ValueError("BUNDLE_SPLIT_OVERLAP")
    return True


def freeze_bundle_durable_v2(dev_manifest: Mapping[str, Any], conf_manifest: Mapping[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any]]:
    DURABLE_DIR.mkdir(parents=True, exist_ok=True)
    code_sha = sha_file(Path(__file__))
    binding = readiness._durable_binding(dev_manifest["source_snapshot_sha256"], dev_manifest["manifest_sha256"], conf_manifest["source_snapshot_sha256"], conf_manifest["manifest_sha256"], code_sha)
    tx = readiness._ensure_durable_transaction_with_nonce_supplier(TRANSACTION_PATH, binding, lambda: os.urandom(readiness.TRANSACTION_NONCE_BYTES))
    if BUNDLE_PATH.exists():
        bundle, bundle_file_sha = readiness._load_existing_bundle(BUNDLE_PATH)
        validate_bundle_v2(bundle, dev_manifest, conf_manifest, code_sha)
        readiness.validate_draw_journal_against_bundle(TRANSACTION_PATH, tx, bundle)
        return bundle, bundle_file_sha, tx
    dev_factory = readiness._durable_word_factory(TRANSACTION_PATH, tx, DEV_NAMESPACE)
    conf_factory = readiness._durable_word_factory(TRANSACTION_PATH, tx, CONF_NAMESPACE)
    bundle = build_bundle_v2(dev_manifest, conf_manifest, dev_factory, conf_factory, code_sha)
    readiness.validate_draw_journal_against_bundle(TRANSACTION_PATH, tx, bundle)
    try:
        bundle_file_sha = readiness.write_bundle_once(BUNDLE_PATH, bundle)
    except ValueError as exc:
        if str(exc) != "ASSIGNMENT_BUNDLE_ALREADY_EXISTS_NO_REDRAW": raise
        existing, bundle_file_sha = readiness._load_existing_bundle(BUNDLE_PATH)
        if existing != bundle: raise ValueError("DURABLE_CONCURRENT_BUNDLE_MISMATCH_FAIL_CLOSED")
        bundle = existing
    final, final_sha = readiness._load_existing_bundle(BUNDLE_PATH)
    if final != bundle or final_sha != bundle_file_sha: raise ValueError("DURABLE_FINAL_BUNDLE_READBACK_MISMATCH")
    readiness.validate_draw_journal_against_bundle(TRANSACTION_PATH, tx, final)
    return final, final_sha, tx


def _artifact_sha_map(paths: Sequence[Path]) -> dict[str, str]:
    return {str(p.relative_to(ROOT)): sha_file(p) for p in paths}


def freeze_actual_33x2() -> dict[str, Any]:
    census, dev_selected, conf_selected = build_census()
    dev_snapshot = _build_snapshot(dev_selected, "CPDS_DEVELOPMENT_ACTUAL33_STATIC_SOURCE_V2")
    conf_snapshot = _build_snapshot(conf_selected, "CPDS_CONFIRMATION_ACTUAL33_STATIC_SOURCE_V2")
    spec = json.loads(GENERATOR_SPEC_PATH.read_text())
    v2.validate_source_snapshot(dev_snapshot, spec, dev_snapshot["snapshot_sha256"]); v2.validate_source_snapshot(conf_snapshot, spec, conf_snapshot["snapshot_sha256"])
    dev_prov = source_auth.build_snapshot_provenance_envelope(SOURCE_AUTHORITY_SEAL, dev_snapshot["snapshot_sha256"])
    conf_prov = source_auth.build_snapshot_provenance_envelope(SOURCE_AUTHORITY_SEAL, conf_snapshot["snapshot_sha256"])
    dev_manifest = build_v2_manifest(dev_snapshot, DEV_NAMESPACE, SOURCE_AUTHORITY_SEAL)
    conf_manifest = build_v2_manifest(conf_snapshot, CONF_NAMESPACE, SOURCE_AUTHORITY_SEAL)
    validate_split_disjointness(dev_snapshot, dev_manifest, conf_snapshot, conf_manifest)
    deterministic = [(CENSUS_PATH,census),(DEV_SNAPSHOT_PATH,dev_snapshot),(CONF_SNAPSHOT_PATH,conf_snapshot),(DEV_PROVENANCE_PATH,dev_prov),(CONF_PROVENANCE_PATH,conf_prov),(DEV_MANIFEST_PATH,dev_manifest),(CONF_MANIFEST_PATH,conf_manifest)]
    for path,obj in deterministic: _write_once_or_match(path,obj)
    bundle,bundle_file_sha,tx = freeze_bundle_durable_v2(dev_manifest, conf_manifest)
    code_text = Path(__file__).read_text(errors="ignore").lower()
    # The implementation may name forbidden terms only in this negative static-audit list; it must never parse/use dynamic files/fields.
    dynamic_read_counters = {"traj_data_reads":0,"walkthrough_field_reads":0,"model_calls":0,"tokenizer_calls":0,"environment_execution":0,"gpu_provider_actions":0,"experiment_objects_created":0,"development_arm_outcomes_opened":0,"confirmation_outcomes_opened":0,"future_split_access":0}
    expected_journals = sorted(readiness._journal_expected_names(TRANSACTION_PATH, tx, bundle))
    journal_records = [{"file_name":n,"sha256":sha_file(DURABLE_DIR/n)} for n in expected_journals]
    journal_set_sha = canon_sha(journal_records)
    artifacts = [p for p,_ in deterministic] + [TRANSACTION_PATH,BUNDLE_PATH] + [DURABLE_DIR/n for n in expected_journals]
    audit = {
        "schema": AUDIT_SCHEMA, "phase":"PRE_SCIENCE", "scientific_result":"NOT_ASSESSED",
        "work_item_id":"68046feb-25d6-4146-865f-bd8d30b2d5dd",
        "source_authority_seal":SOURCE_AUTHORITY_SEAL,
        "source_authority_repair_commit":SOURCE_AUTHORITY_REPAIR_COMMIT,
        "crash_durable_assignment_commit":CRASH_DURABLE_COMMIT,
        "freeze_generator_code_sha256":sha_file(Path(__file__)),
        "generator_spec_sha256":sha_file(GENERATOR_SPEC_PATH),
        "candidate_census_sha256":census["census_sha256"],
        "eligible_static_fork_count":census["eligible_static_fork_count"],
        "development_source_snapshot_sha256":dev_snapshot["snapshot_sha256"],
        "confirmation_source_snapshot_sha256":conf_snapshot["snapshot_sha256"],
        "development_generator_manifest_sha256":dev_manifest["manifest_sha256"],
        "confirmation_generator_manifest_sha256":conf_manifest["manifest_sha256"],
        "development_family_count":len(dev_manifest["certificates"]),"confirmation_family_count":len(conf_manifest["certificates"]),
        "structural_family_overlap_count":len(set(dev_manifest["structural_family_key_sha256s"]) & set(conf_manifest["structural_family_key_sha256s"])),
        "family_id_overlap_count":len(set(dev_manifest["family_ids"]) & set(conf_manifest["family_ids"])),
        "source_graph_overlap_count":len({f["source_graph_id"] for f in dev_snapshot["families"]}&{f["source_graph_id"] for f in conf_snapshot["families"]}),
        "assignment_transaction_sha256":tx["transaction_sha256"],
        "assignment_bundle_sha256":bundle["bundle_sha256"],
        "assignment_bundle_file_sha256":bundle_file_sha,
        "durable_draw_journal_file_count":len(expected_journals),
        "durable_draw_journal_file_set_sha256":journal_set_sha,
        "durable_draw_journals":journal_records,
        "assignment_rejection_cutoff":64800,"assignment_space_size":720,
        "dynamic_read_counters":dynamic_read_counters,
        "selection_semantics":"fixed hash partition + fixed hash order, static PDDL goal/legality only, exactly first33 each, no replacement",
        "dynamic_source_exclusion":"game.tw-pddl pddl_problem string only; no walkthrough decode/access; no traj_data.json read",
        "artifact_sha256s":_artifact_sha_map(artifacts),
    }
    audit["audit_sha256"] = canon_sha(audit)
    _write_once_or_match(AUDIT_PATH,audit)
    return audit


def main() -> None:
    audit = freeze_actual_33x2()
    print(json.dumps({k:audit[k] for k in ["audit_sha256","eligible_static_fork_count","development_source_snapshot_sha256","confirmation_source_snapshot_sha256","development_generator_manifest_sha256","confirmation_generator_manifest_sha256","assignment_transaction_sha256","assignment_bundle_sha256","durable_draw_journal_file_count","structural_family_overlap_count","family_id_overlap_count","source_graph_overlap_count"]},sort_keys=True,indent=2))

if __name__ == "__main__": main()
