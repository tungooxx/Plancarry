from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cpds_development_driver_v1 as dev
import cpds_development_runtime_v1 as v4rt
import cpds_v5_packet_validator_v1 as validator
import cpds_v5_predictive_recurrence_v1 as v5rt

ROOT = Path(__file__).resolve().parent
DEFAULT_ALFWORLD_DATA = Path("/opt/gpu-lab/envs/plancarry-alfworld-data")
EXPECTED_PACKAGES = {
    "alfworld": "0.4.2", "numpy": "2.5.2", "textworld": "1.7.0",
    "tokenizers": "0.21.1", "torch": "2.13.0", "transformers": "4.51.3",
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _feature_list(value: Any, label: str) -> list[float]:
    if hasattr(value, "detach"):
        value = value.detach().float().cpu().tolist()
    elif hasattr(value, "tolist"):
        value = value.tolist()
    out = [float(x) for x in value]
    validator._vector(out, label)
    return out


def _strict_surface_resolver(env: Any) -> Callable[[str], str]:
    """Production-only real ALFWorld symbolic resolver; deliberately has no identity fallback."""
    try:
        demangler_wrapper = env.env.batch_env.envs[0]._wrapped_env._wrapped_env
        infos = demangler_wrapper._entity_infos
    except (AttributeError, IndexError, TypeError) as exc:
        raise RuntimeError("PACKET_REAL_DEMANGLER_UNAVAILABLE") from exc
    if not isinstance(infos, Mapping) or not infos:
        raise RuntimeError("PACKET_REAL_DEMANGLER_INFOS")
    Demangler = importlib.import_module("alfworld.agents.utils.misc").Demangler
    demangler = Demangler(game_infos=infos, shuffle=False)
    id_by_casefold: dict[str, str] = {}
    for info in infos.values():
        entity_id = str(info.id)
        key = entity_id.casefold()
        _require(key not in id_by_casefold or id_by_casefold[key] == entity_id, "PACKET_SYMBOLIC_CASEFOLD_COLLISION")
        id_by_casefold[key] = entity_id

    def demangle_object(symbolic_object_id: str) -> str:
        runtime_id = id_by_casefold.get(str(symbolic_object_id).casefold())
        _require(runtime_id is not None, "PACKET_SYMBOLIC_OBJECT_NOT_IN_GAME")
        surface = str(demangler.demangle_alfred_name(runtime_id))
        _require(bool(surface), "PACKET_SYMBOLIC_DEMANGLE_EMPTY")
        return surface

    return lambda command: dev._translate_symbolic_action(str(command), demangle_object)


def _surface(env: Any, resolver: Callable[[str], str], symbolic: str, code: str) -> str:
    surface = str(resolver(str(symbolic)))
    candidates = [str(x) for x in env.admissible_commands]
    _require(surface in candidates, code)
    return surface


def _site(tokenizer: Any, model: Any, goal: str, observation: str, candidates: Sequence[str], target_surface: str) -> dict[str, Any]:
    actions = sorted(str(x) for x in candidates)
    _require(bool(actions) and len(actions) == len(set(actions)), "PACKET_SITE_CANDIDATES")
    _require(target_surface in actions and actions.count(target_surface) == 1, "PACKET_SITE_TARGET")
    prompt = v4rt.render_policy_prompt(goal, observation, actions)
    scores: list[float] = []
    features: list[list[float]] = []
    for action in actions:
        scores.append(float(v5rt.teacher_forced_whole_action_score(model, tokenizer, prompt, action)))
        features.append(_feature_list(v5rt.native_hidden_feature(model, tokenizer, v5rt.canonical_action_payload(action)), "ACTION"))
    return {
        "prompt": prompt,
        "observation": observation,
        "candidate_actions": actions,
        "base_scores": scores,
        "action_features": features,
        "target_index": actions.index(target_surface),
        "target_surface_command": target_surface,
    }


def runtime_fingerprint() -> str:
    attestation: dict[str, Any] = {
        "python": ".".join(map(str, sys.version_info[:3])),
        "packages": {},
        "model_id": validator.BASE_MODEL_ID,
        "model_revision": validator.BASE_MODEL_REVISION,
        "bound_code_sha256": validator.BOUND_CODE_SHA256,
        "packet_contract_sha256": validator.CONTRACT_SHA256,
    }
    _require(attestation["python"] == "3.13.15", "PACKET_PYTHON_VERSION")
    for name, expected in EXPECTED_PACKAGES.items():
        actual = importlib.metadata.version(name)
        normalized = actual.split("+")[0]
        _require(normalized == expected, "PACKET_PACKAGE_VERSION:" + name + ":" + actual)
        attestation["packages"][name] = actual
    return validator.sha_obj(attestation)


def _game_file(row: Mapping[str, Any], alfworld_data: Path) -> Path:
    p = alfworld_data / "json_2.1.1" / "train" / str(row["source_graph_id"]) / "game.tw-pddl"
    _require(p.is_file(), "PACKET_GAME_FILE_MISSING")
    _require(validator.sha_file(p) == row["game_tw_pddl_sha256"], "PACKET_GAME_FILE_SHA")
    return p


def _positive_packet(
    row: Mapping[str, Any], tokenizer: Any, model: Any, runtime_factory: Callable[[str], Any],
    runtime_fp: str, alfworld_data: Path, *, resolver_factory: Callable[[Any], Callable[[str], str]] = _strict_surface_resolver,
) -> dict[str, Any]:
    """Build one positive packet. Public production path uses the strict real resolver by default."""
    game = _game_file(row, alfworld_data)
    env = runtime_factory(str(game))
    try:
        resolver = resolver_factory(env)
        reset_obs = str(env.observation)
        reset_candidates = sorted(str(x) for x in env.admissible_commands)
        immediate_surface = _surface(env, resolver, str(row["immediate_symbolic_command"]), "PACKET_IMMEDIATE_NOT_ADMISSIBLE")
        reset_prompt = v4rt.render_policy_prompt(str(row["goal_canonical"]), reset_obs, reset_candidates)
        pre_reset_hidden = _feature_list(v5rt.native_hidden_feature(model, tokenizer, reset_prompt.encode("utf-8")), "PRE_RESET")

        immediate = env.step(immediate_surface)
        _require(getattr(immediate, "error", None) is None, "PACKET_IMMEDIATE_STEP_ERROR")

        common1_symbolic = str(row["update_symbolic_commands"][0])
        common1_surface = _surface(env, resolver, common1_symbolic, "PACKET_COMMON1_NOT_ADMISSIBLE")
        rec1 = env.step(common1_surface)
        _require(getattr(rec1, "error", None) is None, "PACKET_COMMON1_STEP_ERROR")
        obs1 = str(rec1.observation)
        h1 = _feature_list(v5rt.native_hidden_feature(model, tokenizer, v5rt.canonical_transition_payload(common1_symbolic, obs1)), "TRANSITION1")
        common2_symbolic = str(row["update_symbolic_commands"][1])
        common2_surface = _surface(env, resolver, common2_symbolic, "PACKET_COMMON2_TARGET_NOT_ADMISSIBLE")
        site0 = _site(tokenizer, model, str(row["goal_canonical"]), str(env.observation), env.admissible_commands, common2_surface)

        rec2 = env.step(common2_surface)
        _require(getattr(rec2, "error", None) is None, "PACKET_COMMON2_STEP_ERROR")
        obs2 = str(rec2.observation)
        h2 = _feature_list(v5rt.native_hidden_feature(model, tokenizer, v5rt.canonical_transition_payload(common2_symbolic, obs2)), "TRANSITION2")
        continuation_symbolic = str(row["continuation_symbolic_command"])
        continuation_surface = _surface(env, resolver, continuation_symbolic, "PACKET_CONTINUATION_TARGET_NOT_ADMISSIBLE")
        site1 = _site(tokenizer, model, str(row["goal_canonical"]), str(env.observation), env.admissible_commands, continuation_surface)

        continuation = env.step(continuation_surface)
        _require(getattr(continuation, "error", None) is None, "PACKET_CONTINUATION_STEP_ERROR")
        continuation_hidden = _feature_list(
            v5rt.native_hidden_feature(model, tokenizer, v5rt.canonical_transition_payload(continuation_symbolic, str(continuation.observation))),
            "CONTINUATION_TRANSITION",
        )
        updates = [
            {
                "symbolic_command": common1_symbolic,
                "surface_command": common1_surface,
                "transition_hidden": h1,
                "prediction_site": site0,
                "next_transition_hidden": h2,
            },
            {
                "symbolic_command": common2_symbolic,
                "surface_command": common2_surface,
                "transition_hidden": h2,
                "prediction_site": site1,
                "next_transition_hidden": continuation_hidden,
            },
        ]
        packet: dict[str, Any] = {
            "schema": validator.PACKET_SCHEMA,
            "base_model_id": validator.BASE_MODEL_ID,
            "base_model_revision": validator.BASE_MODEL_REVISION,
            "source_graph_id": row["source_graph_id"],
            "structural_key_sha256": row["structural_key_sha256"],
            "partition": row["partition"],
            "packet_id": row["packet_id"],
            "pre_reset_hidden": pre_reset_hidden,
            "updates": updates,
            "final_prediction_site": copy.deepcopy(site1),
            "producer_provenance": {
                "packet_construction_contract_sha256": validator.CONTRACT_SHA256,
                "behavior_manifest_sha256": validator.BEHAVIOR_SHA256,
                "source_authority_seal": validator.SOURCE_AUTHORITY_SEAL,
                "candidate_census_sha256": validator.CENSUS_SHA256,
                "v4_reserved_seal_sha256": validator.RESERVED_FILE_SHA256,
                "game_tw_pddl_sha256": row["game_tw_pddl_sha256"],
                "runtime_fingerprint": runtime_fp,
                "model_snapshot_revision": validator.BASE_MODEL_REVISION,
                "packet_binding_commit": "4c4de54e16f697e9aa12b3b7fa8b07f6ee80da34",
                "continuation_symbolic_command": continuation_symbolic,
                "continuation_surface_command": continuation_surface,
                "producer_code_sha256": validator.sha_file(__file__),
            },
        }
        return packet
    finally:
        env.close()


def inject_contrastive_negatives(positive_packets: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_graph = {str(p["source_graph_id"]): copy.deepcopy(dict(p)) for p in positive_packets}
    row_by_graph = {str(r["source_graph_id"]): r for r in rows}
    _require(set(by_graph) == set(row_by_graph), "PACKET_POSITIVE_SOURCE_SET")
    out: list[dict[str, Any]] = []
    for gid in sorted(by_graph):
        packet = by_graph[gid]
        row = row_by_graph[gid]
        donor0, donor1 = [str(x) for x in row["negative_donor_source_graph_ids"]]
        _require(donor0 != gid and donor1 != gid and donor0 != donor1, "PACKET_DONOR_IDENTITY")
        _require(donor0 in by_graph and donor1 in by_graph, "PACKET_DONOR_MISSING")
        _require(by_graph[donor0]["partition"] == packet["partition"] == by_graph[donor1]["partition"], "PACKET_DONOR_PARTITION")
        packet["updates"][0]["negative_transition_hidden"] = copy.deepcopy(by_graph[donor0]["updates"][1]["transition_hidden"])
        packet["updates"][0]["negative_donor_source_graph_id"] = donor0
        packet["updates"][1]["negative_transition_hidden"] = copy.deepcopy(by_graph[donor1]["updates"][1]["next_transition_hidden"])
        packet["updates"][1]["negative_donor_source_graph_id"] = donor1
        packet["packet_sha256"] = validator.sha_obj(packet)
        out.append(packet)
    return out


def build_partition(
    partition: str, tokenizer: Any, model: Any, runtime_factory: Callable[[str], Any], runtime_fp: str,
    *, alfworld_data: str | Path = DEFAULT_ALFWORLD_DATA,
) -> list[dict[str, Any]]:
    behavior, _ = validator.load_frozen_authority()
    rows = [r for r in behavior["rows"] if r["partition"] == partition]
    expected = 1504 if partition == "TRAIN" else 423 if partition == "CALIBRATION" else None
    _require(expected is not None and len(rows) == expected, "PACKET_PARTITION")
    positives = [_positive_packet(r, tokenizer, model, runtime_factory, runtime_fp, Path(alfworld_data)) for r in rows]
    packets = inject_contrastive_negatives(positives, rows)
    validator.validate_partition_packets(packets, partition)
    return packets


def write_partition_atomic(packets: Sequence[Mapping[str, Any]], partition: str, output_dir: str | Path) -> dict[str, Any]:
    target = Path(output_dir)
    _require(not target.exists(), "PACKET_OUTPUT_ALREADY_EXISTS")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=target.name + ".tmp.", dir=str(target.parent)))
    try:
        for packet in packets:
            path = tmp / (str(packet["packet_id"]) + ".json")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb", closefd=False) as f:
                    f.write(validator.canonical_bytes(packet)); f.flush(); os.fsync(f.fileno())
            finally:
                os.close(fd)
        validation = validator.validate_packet_dir(tmp, partition)
        os.replace(tmp, target)
        dfd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try: os.fsync(dfd)
        finally: os.close(dfd)
        return validation
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _write_canonical_exclusive(path: Path, obj: Mapping[str, Any]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(validator.canonical_bytes(obj)); f.flush(); os.fsync(f.fileno())
    finally:
        os.close(fd)


def build_partition_atomic(
    partition: str, tokenizer: Any, model: Any, runtime_factory: Callable[[str], Any], runtime_fp: str,
    output_dir: str | Path, *, alfworld_data: str | Path = DEFAULT_ALFWORLD_DATA,
) -> dict[str, Any]:
    """Disk-backed two-pass build; target appears only after complete validation."""
    target = Path(output_dir)
    _require(not target.exists(), "PACKET_OUTPUT_ALREADY_EXISTS")
    behavior, _ = validator.load_frozen_authority()
    rows = [r for r in behavior["rows"] if r["partition"] == partition]
    expected = 1504 if partition == "TRAIN" else 423 if partition == "CALIBRATION" else None
    _require(expected is not None and len(rows) == expected, "PACKET_PARTITION")
    row_by_graph = {str(r["source_graph_id"]): r for r in rows}
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=target.name + ".stage.", dir=str(target.parent)))
    positive_dir = stage / "positive"; final_dir = stage / "final"
    positive_dir.mkdir(); final_dir.mkdir()
    try:
        # Pass 1: materialize positives only. No donor feature is read yet.
        for row in rows:
            packet = _positive_packet(row, tokenizer, model, runtime_factory, runtime_fp, Path(alfworld_data))
            _write_canonical_exclusive(positive_dir / (str(row["packet_id"]) + ".json"), packet)
        # Pass 2: inject exact frozen donor features by source identity, one focal packet at a time.
        packet_id_by_graph = {g: str(r["packet_id"]) for g, r in row_by_graph.items()}
        def read_positive(gid: str) -> dict[str, Any]:
            return json.loads((positive_dir / (packet_id_by_graph[gid] + ".json")).read_text(encoding="utf-8"))
        for gid in sorted(row_by_graph):
            row = row_by_graph[gid]; packet = read_positive(gid)
            donor0, donor1 = [str(x) for x in row["negative_donor_source_graph_ids"]]
            _require(donor0 != gid and donor1 != gid and donor0 != donor1, "PACKET_DONOR_IDENTITY")
            _require(donor0 in row_by_graph and donor1 in row_by_graph, "PACKET_DONOR_MISSING")
            _require(row_by_graph[donor0]["partition"] == partition == row_by_graph[donor1]["partition"], "PACKET_DONOR_PARTITION")
            p0 = read_positive(donor0); p1 = read_positive(donor1)
            packet["updates"][0]["negative_transition_hidden"] = copy.deepcopy(p0["updates"][1]["transition_hidden"])
            packet["updates"][0]["negative_donor_source_graph_id"] = donor0
            packet["updates"][1]["negative_transition_hidden"] = copy.deepcopy(p1["updates"][1]["next_transition_hidden"])
            packet["updates"][1]["negative_donor_source_graph_id"] = donor1
            packet["packet_sha256"] = validator.sha_obj(packet)
            _write_canonical_exclusive(final_dir / (str(packet["packet_id"]) + ".json"), packet)
        validation = validator.validate_packet_dir(final_dir, partition)
        shutil.rmtree(positive_dir)
        os.replace(final_dir, target)
        shutil.rmtree(stage, ignore_errors=True)
        dfd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try: os.fsync(dfd)
        finally: os.close(dfd)
        return validation
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise

def _runtime_factory(game_file: str):
    from alfworld_runtime import AlfRuntime
    return AlfRuntime(game_file, max_steps=12)


def main() -> None:
    parser = argparse.ArgumentParser(description="Produce exact frozen CPDS V5 TRAIN/CALIBRATION feature packets.")
    parser.add_argument("--partition", required=True, choices=("TRAIN", "CALIBRATION"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hf-cache", required=True)
    parser.add_argument("--alfworld-data", default=str(DEFAULT_ALFWORLD_DATA))
    args = parser.parse_args()
    validator.load_frozen_authority()  # before model/environment access
    fp = runtime_fingerprint()
    tokenizer, model = v5rt.load_frozen_qwen(args.hf_cache, device="cuda")
    result = build_partition_atomic(args.partition, tokenizer, model, _runtime_factory, fp, args.output_dir, alfworld_data=args.alfworld_data)
    print(json.dumps({"status": "PACKET_BUILD_COMPLETE", "runtime_fingerprint": fp, **result}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
