from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from cpds_v5_partition_v1 import partition_name

ROOT = Path(__file__).resolve().parent
DESIGN = ROOT / "results" / "design"
BEHAVIOR_PATH = DESIGN / "plancarry_cpds_v5_packet_behavior_manifest_a1_20260901.json"
CONTRACT_PATH = DESIGN / "plancarry_cpds_v5_packet_construction_binding_a1_20260901.json"
CENSUS_PATH = DESIGN / "plancarry_cpds_actual_33x2_candidate_census_v1_20260829.json"
SOURCE_AUTHORITY_PATH = DESIGN / "plancarry_cpds_alfworld_static_source_authority_v1_20260829.json"
STATIC_UNITS_PATH = DESIGN / "plancarry_cpds_alfworld_static_graph_units_v1_20260829.json"
RESERVED_PATH = DESIGN / "plancarry_cpds_v5_v4_reserved_structural_key_hash_seal_a3_20260830.json"
RECIPE_PATH = DESIGN / "plancarry_cpds_v5_training_recipe_a1_20260830.json"
V4_RUNTIME_PATH = DESIGN / "plancarry_cpds_development_runtime_contract_v1_20260830.json"

PACKET_SCHEMA = "PLANCARRY_CPDS_V5_PRECOMPUTED_FEATURE_SEQUENCE_V1"
BASE_MODEL_ID = "Qwen/Qwen3-1.7B"
BASE_MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
NATIVE_WIDTH = 2048
BEHAVIOR_FILE_SHA256 = "d107d8d846fc82f002bd2f698f66029f4e1afcf9aae6a78e9755331040bf42cc"
BEHAVIOR_SHA256 = "ad2f6972552ffae34847d4d551626d041cf65f24db4ebbcae3470a8f9eeb80bb"
CONTRACT_FILE_SHA256 = "12260e9ebcdaa8b2b9af157695319cac41989d136e22f345c2cc6307b6d3e666"
CONTRACT_SHA256 = "0e388caa2e03bd4eb3186764851f1d04108df28cdf2acacb12a1af307764155b"
CENSUS_FILE_SHA256 = "c40cda82d565e0bcd789cbf4204805a4efbcf462a7f83f46e648bc64e0790fb9"
CENSUS_SHA256 = "690dabf4f199cb34e3cb58f6487191ed36e15d2f8dbbf6c919da23fe870d16f7"
SOURCE_AUTHORITY_FILE_SHA256 = "c7f1bf6418c235d3805f653d3cef0907369ef82eff274c27a4ca787061eabce8"
SOURCE_AUTHORITY_SEAL = "a2ca2421f0c4405c403d09ca7f9e78066f57a1c2ee931600bbbc249ddff8810f"
STATIC_UNITS_FILE_SHA256 = "c2ad460d533552fe26e810241a05b22b8fbe3cae749169d282c120f286d6b092"
RESERVED_FILE_SHA256 = "e2d6cecb4a13ff27cd5f2e76fd6d1e021fa27cf1e1d582aeb1808b2f40f075e2"
RECIPE_FILE_SHA256 = "861537f18959bcff736e7cbe30fdf07e128c7621ed5fb4e3522d598f77acab8c"
V4_RUNTIME_FILE_SHA256 = "3dd4d52676b26e7c7e4fc4394cb0b16378b3560aa4711f574ce8ee1d2385ddaa"
PROTECTED_SPEC_SHA256 = "3a730d7fca46ae1c9736d3546588fb08143212f0ba52e580f70b7ba450a189b2"
TRACE_VERSION = "IMMEDIATE_EXCLUDED_COMMON1_COMMON2_EXAMINE_STAGING2_V1"
PACKET_ID_DOMAIN = "CPDS_V5_PACKET_ID_V1"
FORBIDDEN_KEYS = {
    "branch_A", "branch_B", "branch_A_equivalence_class", "branch_B_equivalence_class",
    "evaluator_label", "outcome", "correctness", "endpoint",
}
BOUND_CODE_SHA256 = {
    "alfworld_runtime.py": "53e550f70711a3779409c565ecbd3e2fd971751a03633dad3566d5569a6fb3c6",
    "cpds_actual_33x2_freeze_v1.py": "4429d8a91688e6a4754f66a2cc976a25f560d1da38de6e20a6e43a6dc81030d6",
    "cpds_development_driver_v1.py": "6daf31543e63eb7aca2ae67c1f83577b6af8c2b08c1f1fdd0e70d532b2ddae02",
    "cpds_development_runtime_v1.py": "2d4933c75c69ecccb9495d10cc3568e9906bf57ca485b175956b290f74cd0da5",
    "cpds_v5_partition_v1.py": "0e9a007b6e8911a8432c385fbf0f6ba9ccc834467360a427c1c5c1e17a955439",
    "cpds_v5_predictive_recurrence_v1.py": "3a5a190de95c43d8bd4578f056e279c6217d53815a07527974eca5fe1d2f85c5",
    "cpds_v5_train_calibration_v1.py": "96132d7da8e7f75b7d8aaf8557c636d0ef167c47c4194462551fd30fc5ca1068",
}


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sha_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def self_hash(obj: Mapping[str, Any], field: str) -> str:
    x = copy.deepcopy(dict(obj))
    expected = str(x.pop(field))
    actual = sha_obj(x)
    if actual != expected:
        raise ValueError(f"SELF_HASH:{field}")
    return actual


def packet_id(partition: str, source_graph_id: str, structural_key_sha256: str) -> str:
    return sha_obj({
        "domain": PACKET_ID_DOMAIN,
        "trace_version": TRACE_VERSION,
        "partition": partition,
        "source_graph_id": source_graph_id,
        "structural_key_sha256": structural_key_sha256,
    })


def _walk_keys(obj: Any) -> set[str]:
    if isinstance(obj, Mapping):
        out = {str(k) for k in obj.keys()}
        for v in obj.values():
            out |= _walk_keys(v)
        return out
    if isinstance(obj, (list, tuple)):
        out: set[str] = set()
        for v in obj:
            out |= _walk_keys(v)
        return out
    return set()


def _require_no_forbidden_fields(obj: Any) -> None:
    bad = FORBIDDEN_KEYS & _walk_keys(obj)
    if bad:
        raise ValueError("EVALUATOR_OR_OUTCOME_FIELD_FORBIDDEN:" + ",".join(sorted(bad)))


def _vector(x: Any, label: str) -> list[float]:
    if not isinstance(x, list) or len(x) != NATIVE_WIDTH:
        raise ValueError(label + "_WIDTH")
    vals = [float(v) for v in x]
    if any(not math.isfinite(v) for v in vals):
        raise ValueError(label + "_NONFINITE")
    ss = math.fsum(v * v for v in vals)
    if not math.isfinite(ss) or abs(math.sqrt(ss) - 1.0) > 5e-5:
        raise ValueError(label + "_UNIT_NORM")
    return vals


def _site(site: Any, expected_prompt: str | None, label: str) -> dict[str, Any]:
    if not isinstance(site, Mapping):
        raise ValueError(label + "_TYPE")
    d = dict(site)
    required = {"prompt", "observation", "candidate_actions", "base_scores", "action_features", "target_index", "target_surface_command"}
    if not required <= set(d):
        raise ValueError(label + "_FIELDS")
    actions = d["candidate_actions"]
    if not isinstance(actions, list) or not actions or actions != sorted(actions) or len(actions) != len(set(actions)) or any(not isinstance(a, str) or not a for a in actions):
        raise ValueError(label + "_CANDIDATES")
    scores = d["base_scores"]
    features = d["action_features"]
    if not isinstance(scores, list) or len(scores) != len(actions) or any(not math.isfinite(float(v)) for v in scores):
        raise ValueError(label + "_SCORES")
    if not isinstance(features, list) or len(features) != len(actions):
        raise ValueError(label + "_ACTION_FEATURES")
    for i, vec in enumerate(features):
        _vector(vec, f"{label}_ACTION_{i}")
    target = int(d["target_index"])
    if target < 0 or target >= len(actions):
        raise ValueError(label + "_TARGET_INDEX")
    target_surface = d["target_surface_command"]
    if not isinstance(target_surface, str) or actions[target] != target_surface or actions.count(target_surface) != 1:
        raise ValueError(label + "_TARGET_GEOMETRY")
    if not isinstance(d["observation"], str) or not d["observation"]:
        raise ValueError(label + "_OBSERVATION")
    if not isinstance(d["prompt"], str) or not d["prompt"]:
        raise ValueError(label + "_PROMPT")
    if expected_prompt is not None and d["prompt"] != expected_prompt:
        raise ValueError(label + "_PROMPT_MISMATCH")
    return d


def render_policy_prompt(task_text: str, observation: str, candidate_actions: Sequence[str]) -> str:
    if not isinstance(task_text, str) or not task_text or not isinstance(observation, str) or not observation:
        raise ValueError("PROMPT_INPUT")
    actions = tuple(candidate_actions)
    if not actions or len(actions) != len(set(actions)) or any(not isinstance(x, str) or not x for x in actions):
        raise ValueError("CANDIDATE_SET")
    return "TASK\n" + task_text + "\nCURRENT OBSERVATION\n" + observation + "\nADMISSIBLE COMMANDS\n" + "\n".join(sorted(actions)) + "\n<STATE_END>\nACTION:"


def load_frozen_authority() -> tuple[dict[str, Any], dict[str, Any]]:
    expected_files = {
        BEHAVIOR_PATH: BEHAVIOR_FILE_SHA256,
        CONTRACT_PATH: CONTRACT_FILE_SHA256,
        CENSUS_PATH: CENSUS_FILE_SHA256,
        SOURCE_AUTHORITY_PATH: SOURCE_AUTHORITY_FILE_SHA256,
        STATIC_UNITS_PATH: STATIC_UNITS_FILE_SHA256,
        RESERVED_PATH: RESERVED_FILE_SHA256,
        RECIPE_PATH: RECIPE_FILE_SHA256,
        V4_RUNTIME_PATH: V4_RUNTIME_FILE_SHA256,
    }
    for path, expected in expected_files.items():
        if not path.is_file() or sha_file(path) != expected:
            raise ValueError("FROZEN_AUTHORITY_FILE:" + path.name)
    for rel, expected in BOUND_CODE_SHA256.items():
        path = ROOT / rel
        if not path.is_file() or sha_file(path) != expected:
            raise ValueError("BOUND_CODE_DRIFT:" + rel)
    behavior = json.loads(BEHAVIOR_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if self_hash(behavior, "manifest_sha256") != BEHAVIOR_SHA256:
        raise ValueError("BEHAVIOR_SHA")
    if self_hash(contract, "contract_sha256") != CONTRACT_SHA256:
        raise ValueError("CONTRACT_SHA")
    if contract["authority"]["protected_scientific_spec_hash"] != PROTECTED_SPEC_SHA256:
        raise ValueError("SCIENTIFIC_SPEC_DRIFT")
    if contract["authority"]["source_authority_seal"] != SOURCE_AUTHORITY_SEAL:
        raise ValueError("SOURCE_AUTHORITY_SEAL")
    if contract["authority"]["candidate_census_sha256"] != CENSUS_SHA256:
        raise ValueError("CENSUS_SHA")
    rows = behavior.get("rows")
    if not isinstance(rows, list) or len(rows) != 1927:
        raise ValueError("BEHAVIOR_ROWS")
    reserved = set(json.loads(RESERVED_PATH.read_text(encoding="utf-8"))["structural_family_key_sha256s"])
    if len(reserved) != 66:
        raise ValueError("V4_RESERVED_COUNT")
    seen_graph: set[str] = set()
    seen_packet: set[str] = set()
    for row in rows:
        _require_no_forbidden_fields(row)
        gid = str(row["source_graph_id"]); part = str(row["partition"]); sk = str(row["structural_key_sha256"])
        if gid in seen_graph or str(row["packet_id"]) in seen_packet:
            raise ValueError("BEHAVIOR_DUPLICATE")
        seen_graph.add(gid); seen_packet.add(str(row["packet_id"]))
        if partition_name(gid) != part or part not in ("TRAIN", "CALIBRATION"):
            raise ValueError("BEHAVIOR_PARTITION")
        if sk in reserved:
            raise ValueError("V4_RESERVED_OVERLAP")
        if str(row["packet_id"]) != packet_id(part, gid, sk):
            raise ValueError("PACKET_ID_BINDING")
        if len(row["update_symbolic_commands"]) != 2 or len(row["primary_target_symbolic_commands"]) != 2 or len(row["negative_donor_source_graph_ids"]) != 2:
            raise ValueError("BEHAVIOR_TRACE_GEOMETRY")
        if row["primary_target_symbolic_commands"][0] != row["update_symbolic_commands"][1] or row["primary_target_symbolic_commands"][1] != row["continuation_symbolic_command"]:
            raise ValueError("BEHAVIOR_TARGET_BINDING")
    for part, n, expected_sha in (
        ("TRAIN", 1504, "68080f7bbc7f67a4614dd003496aaab929f66093c8a9ddc41489efc1ca85163b"),
        ("CALIBRATION", 423, "e9bbabd85d489e0dd81459e0cd2b59ae5547f8589a3625044ef236b20ab6a175"),
    ):
        ids = sorted(str(r["source_graph_id"]) for r in rows if r["partition"] == part)
        if len(ids) != n or sha_obj(ids) != expected_sha:
            raise ValueError("PARTITION_BINDING:" + part)
    return behavior, contract


def _packet_self_hash(packet: Mapping[str, Any]) -> str:
    x = copy.deepcopy(dict(packet))
    expected = str(x.pop("packet_sha256"))
    actual = sha_obj(x)
    if expected != actual:
        raise ValueError("PACKET_SELF_HASH")
    return actual


def validate_packet(packet: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    d = copy.deepcopy(dict(packet))
    _require_no_forbidden_fields(d)
    if d.get("schema") != PACKET_SCHEMA:
        raise ValueError("PACKET_SCHEMA")
    if d.get("base_model_id") != BASE_MODEL_ID or d.get("base_model_revision") != BASE_MODEL_REVISION:
        raise ValueError("BASE_MODEL_IDENTITY")
    for key in ("source_graph_id", "structural_key_sha256", "partition", "packet_id"):
        if d.get(key) != row.get(key):
            raise ValueError("ROW_BINDING:" + key)
    if partition_name(str(d["source_graph_id"])) != d["partition"]:
        raise ValueError("PACKET_PARTITION")
    if d["packet_id"] != packet_id(d["partition"], d["source_graph_id"], d["structural_key_sha256"]):
        raise ValueError("PACKET_ID")
    _packet_self_hash(d)
    _vector(d.get("pre_reset_hidden"), "PRE_RESET")
    updates = d.get("updates")
    if not isinstance(updates, list) or len(updates) != 2:
        raise ValueError("UPDATES_EXACTLY_TWO")
    provenance = d.get("producer_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("PRODUCER_PROVENANCE")
    expected_prov = {
        "packet_construction_contract_sha256": CONTRACT_SHA256,
        "behavior_manifest_sha256": BEHAVIOR_SHA256,
        "source_authority_seal": SOURCE_AUTHORITY_SEAL,
        "candidate_census_sha256": CENSUS_SHA256,
        "v4_reserved_seal_sha256": RESERVED_FILE_SHA256,
        "game_tw_pddl_sha256": row["game_tw_pddl_sha256"],
        "model_snapshot_revision": BASE_MODEL_REVISION,
    }
    for key, expected in expected_prov.items():
        if provenance.get(key) != expected:
            raise ValueError("PROVENANCE:" + key)
    runtime_fp = provenance.get("runtime_fingerprint")
    if not isinstance(runtime_fp, str) or len(runtime_fp) != 64 or any(c not in "0123456789abcdef" for c in runtime_fp):
        raise ValueError("RUNTIME_FINGERPRINT")
    continuation_surface = provenance.get("continuation_surface_command")
    if not isinstance(continuation_surface, str) or not continuation_surface:
        raise ValueError("CONTINUATION_SURFACE")
    sites: list[dict[str, Any]] = []
    for i, upd in enumerate(updates):
        if not isinstance(upd, Mapping):
            raise ValueError("UPDATE_TYPE")
        if upd.get("symbolic_command") != row["update_symbolic_commands"][i]:
            raise ValueError(f"UPDATE_{i}_SYMBOLIC")
        if not isinstance(upd.get("surface_command"), str) or not upd["surface_command"]:
            raise ValueError(f"UPDATE_{i}_SURFACE")
        _vector(upd.get("transition_hidden"), f"UPDATE_{i}_TRANSITION")
        _vector(upd.get("next_transition_hidden"), f"UPDATE_{i}_NEXT")
        _vector(upd.get("negative_transition_hidden"), f"UPDATE_{i}_NEGATIVE")
        if upd.get("negative_donor_source_graph_id") != row["negative_donor_source_graph_ids"][i]:
            raise ValueError(f"UPDATE_{i}_DONOR")
        site0 = upd.get("prediction_site")
        if not isinstance(site0, Mapping):
            raise ValueError(f"UPDATE_{i}_SITE")
        expected_prompt = render_policy_prompt(str(row["goal_canonical"]), str(site0.get("observation", "")), site0.get("candidate_actions", []))
        sites.append(_site(site0, expected_prompt, f"UPDATE_{i}_SITE"))
    if updates[0]["next_transition_hidden"] != updates[1]["transition_hidden"]:
        raise ValueError("UPDATE0_POSITIVE_NOT_COMMON2")
    if sites[0]["target_surface_command"] != updates[1]["surface_command"]:
        raise ValueError("UPDATE0_TARGET_NOT_COMMON2_SURFACE")
    if sites[1]["target_surface_command"] != continuation_surface:
        raise ValueError("UPDATE1_TARGET_NOT_CONTINUATION_SURFACE")
    if d.get("final_prediction_site") != updates[1]["prediction_site"]:
        raise ValueError("FINAL_PREDICTION_SITE")
    return d


def validate_partition_packets(packets: Sequence[Mapping[str, Any]], partition: str) -> dict[str, Any]:
    behavior, _ = load_frozen_authority()
    rows = [r for r in behavior["rows"] if r["partition"] == partition]
    expected_n = 1504 if partition == "TRAIN" else 423 if partition == "CALIBRATION" else None
    if expected_n is None:
        raise ValueError("PARTITION")
    if len(packets) != expected_n or len(rows) != expected_n:
        raise ValueError("PARTITION_PACKET_COUNT")
    by_graph = {str(p["source_graph_id"]): p for p in packets}
    if len(by_graph) != expected_n or set(by_graph) != {str(r["source_graph_id"]) for r in rows}:
        raise ValueError("PARTITION_SOURCE_SET")
    row_by_graph = {str(r["source_graph_id"]): r for r in rows}
    validated = {gid: validate_packet(by_graph[gid], row_by_graph[gid]) for gid in sorted(by_graph)}
    for gid, packet in validated.items():
        row = row_by_graph[gid]
        donor0, donor1 = row["negative_donor_source_graph_ids"]
        p0 = validated[str(donor0)]; p1 = validated[str(donor1)]
        if packet["updates"][0]["negative_transition_hidden"] != p0["updates"][1]["transition_hidden"]:
            raise ValueError("DONOR0_FEATURE_BINDING")
        if packet["updates"][1]["negative_transition_hidden"] != p1["updates"][1]["next_transition_hidden"]:
            raise ValueError("DONOR1_FEATURE_BINDING")
    ids_sha = sha_obj(sorted(validated))
    expected_sha = "68080f7bbc7f67a4614dd003496aaab929f66093c8a9ddc41489efc1ca85163b" if partition == "TRAIN" else "e9bbabd85d489e0dd81459e0cd2b59ae5547f8589a3625044ef236b20ab6a175"
    if ids_sha != expected_sha:
        raise ValueError("PARTITION_SOURCE_SHA")
    return {"partition": partition, "packet_count": expected_n, "source_graph_ids_sha256": ids_sha, "status": "VALIDATED_EXACT_FROZEN_PARTITION"}


def validate_packet_dir(packet_dir: str | Path, partition: str) -> dict[str, Any]:
    # Streaming validation: at most the focal packet plus its two donors are resident.
    root = Path(packet_dir)
    if not root.is_dir():
        raise ValueError("PACKET_DIR")
    behavior, _ = load_frozen_authority()
    rows = [r for r in behavior["rows"] if r["partition"] == partition]
    expected_n = 1504 if partition == "TRAIN" else 423 if partition == "CALIBRATION" else None
    if expected_n is None or len(rows) != expected_n:
        raise ValueError("PARTITION")
    row_by_graph = {str(r["source_graph_id"]): r for r in rows}
    packet_id_by_graph = {g: str(r["packet_id"]) for g, r in row_by_graph.items()}
    expected_names = {pid + ".json" for pid in packet_id_by_graph.values()}
    paths = sorted(root.glob("*.json"))
    if len(paths) != expected_n or {p.name for p in paths} != expected_names:
        raise ValueError("PARTITION_PACKET_FILES")

    def read_graph(gid: str) -> dict[str, Any]:
        path = root / (packet_id_by_graph[gid] + ".json")
        raw = path.read_bytes()
        packet = json.loads(raw)
        if path.name != str(packet.get("packet_id")) + ".json":
            raise ValueError("PACKET_FILENAME")
        if raw != canonical_bytes(packet):
            raise ValueError("PACKET_NONCANONICAL_BYTES")
        return validate_packet(packet, row_by_graph[gid])

    for gid in sorted(row_by_graph):
        packet = read_graph(gid)
        donor0, donor1 = [str(x) for x in row_by_graph[gid]["negative_donor_source_graph_ids"]]
        p0 = read_graph(donor0); p1 = read_graph(donor1)
        if packet["updates"][0]["negative_transition_hidden"] != p0["updates"][1]["transition_hidden"]:
            raise ValueError("DONOR0_FEATURE_BINDING")
        if packet["updates"][1]["negative_transition_hidden"] != p1["updates"][1]["next_transition_hidden"]:
            raise ValueError("DONOR1_FEATURE_BINDING")
    ids_sha = sha_obj(sorted(row_by_graph))
    expected_sha = "68080f7bbc7f67a4614dd003496aaab929f66093c8a9ddc41489efc1ca85163b" if partition == "TRAIN" else "e9bbabd85d489e0dd81459e0cd2b59ae5547f8589a3625044ef236b20ab6a175"
    if ids_sha != expected_sha:
        raise ValueError("PARTITION_SOURCE_SHA")
    return {"partition": partition, "packet_count": expected_n, "source_graph_ids_sha256": ids_sha, "status": "VALIDATED_EXACT_FROZEN_PARTITION"}
