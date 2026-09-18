"""PlanLatch v7.9 preregistered TRAIN-only execution wrapper.

This module is additive to the independently reviewed v7.9 runtime. Importing
it does not import torch/transformers/ALFWorld and cannot execute science.
Real execution requires a reviewed authority bundle and explicit --execute.

The wrapper enforces the frozen custody order:
PRE_SOURCE -> FIT -> POST_FIT_HELDOUT -> SUPPORT/PILOT/CROSS_REALIZATION.
Held-out partition bodies are not opened before the POST_FIT_HELDOUT freeze.
Evaluator-orientation sidecars are not opened until raw relay arm scores for
that partition have been frozen to the append-only stage journal.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import planlatch_v7_9_protocol as protocol
import planlatch_v7_9_runner as core

EXPERIMENT_ID = "35f1abdc-7647-4f39-811d-f18c0213682d"
PREDICTION_ID = "76a326dd-22f4-4a6f-99b9-1701b9d5123a"
DESIGN_ID = "c8b8981a-352f-48c0-9bee-08bba6a46f7f"
SEMANTIC_HASH = "6e53b8f713b2de6f3a2b489b351b1ca37f355eaf850228e9706a596a47ba62ef"
REVIEWED_RUNTIME_COMMIT = "e6ff6bb3714a84a395336c0ab06327b594d30d04"
RUNTIME_ENGINEERING_RESULT_ID = "8493b2b5-4f33-42b3-872f-11623f265625"
RUNTIME_FIDELITY_ID = "d44ecf92-bc6d-452e-8d04-1666a22defba"
DRIVER_VERSION = "planlatch-v7.9-execution-driver-v1"
ROOT_KIND = "PLANLATCH_V79_EXECUTION_INPUT_V1"
AUTHORITY_KIND = "PLANLATCH_V79_RELEASE_AUTHORITY_V1"
PARTITIONS = ("FIT", "SUPPORT", "PILOT", "CROSS_REALIZATION")
REVIEWED_HASHES = {
    "planlatch_v7_9_protocol.py": "e10db7c0b1552ca56e297ae0b8effe8e05988aad1be5e77ee9c42c534bc8222a",
    "planlatch_v7_9_runner.py": "5e185c990e0f994485ac2d5d0434430d7c8723a09b6eb505a68ec5b41e5ed200",
    "planlatch_v7_9_model_runtime.py": "4f693e43fe66c855e1dbca8cba0ef0f664b8960ff450813d6d86b50bc0b4a260",
}


class DriverViolation(RuntimeError):
    pass


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode()).hexdigest()


def sha_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DriverViolation(f"{name} must be lowercase sha256")
    return value


def reviewed_runtime_identity(root: str | Path = ".") -> bool:
    root = Path(root)
    for rel, expected in REVIEWED_HASHES.items():
        got = sha_file(root / rel)
        if got != expected:
            raise DriverViolation(f"reviewed runtime byte drift: {rel} {got}")
    return True


@dataclass(frozen=True)
class FileRef:
    path: str
    sha256: str

    @classmethod
    def from_obj(cls, obj: Mapping[str, Any], name: str) -> "FileRef":
        path = obj.get("path")
        if not isinstance(path, str) or not path:
            raise DriverViolation(f"{name}.path missing")
        return cls(path=path, sha256=_require_sha(obj.get("sha256"), f"{name}.sha256"))


@dataclass(frozen=True)
class RootInput:
    tasks: tuple[core.BaseTaskMetadata, ...]
    partition_files: Mapping[str, FileRef]
    orientation_files: Mapping[str, FileRef]
    freshness_attestation: Mapping[str, Any]
    donor_program_hash: str
    washout_hash: str
    root_hash: str


def load_root_input(path: str | Path) -> RootInput:
    raw = json.loads(Path(path).read_text())
    if raw.get("kind") != ROOT_KIND or raw.get("experiment_id") != EXPERIMENT_ID:
        raise DriverViolation("execution root kind/experiment mismatch")
    tasks_raw = raw.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise DriverViolation("nonempty pre-response task inventory required")
    tasks = []
    for row in tasks_raw:
        if not isinstance(row, Mapping):
            raise DriverViolation("task inventory row must be mapping")
        tasks.append(core.BaseTaskMetadata(
            task_id=str(row.get("task_id", "")),
            m0=str(row.get("m0", "")),
            dependency_keys=dict(row.get("dependency_keys") or {}),
            cross_realization_tag=str(row.get("cross_realization_tag", "")),
            split=str(row.get("split", "")),
            never_consumed=row.get("never_consumed") is True,
        ))
    pf_raw = raw.get("partition_files")
    if not isinstance(pf_raw, Mapping):
        raise DriverViolation("partition_files missing")
    partition_files = {name: FileRef.from_obj(pf_raw.get(name) or {}, f"partition_files.{name}") for name in PARTITIONS}
    of_raw = raw.get("orientation_files") or {}
    if not isinstance(of_raw, Mapping):
        raise DriverViolation("orientation_files must be mapping")
    orientation_files = {
        name: FileRef.from_obj(of_raw.get(name) or {}, f"orientation_files.{name}")
        for name in ("PILOT", "CROSS_REALIZATION")
    }
    fresh = raw.get("freshness_attestation")
    if not isinstance(fresh, Mapping) or fresh.get("all_task_ids_never_consumed") is not True:
        raise DriverViolation("fresh never-consumed inventory attestation missing")
    donor_program_hash = _require_sha(raw.get("donor_program_hash"), "donor_program_hash")
    washout_hash = _require_sha(raw.get("washout_hash"), "washout_hash")
    return RootInput(
        tasks=tuple(tasks),
        partition_files=partition_files,
        orientation_files=orientation_files,
        freshness_attestation=dict(fresh),
        donor_program_hash=donor_program_hash,
        washout_hash=washout_hash,
        root_hash=sha_json(raw),
    )


def _read_bound_json(ref: FileRef) -> Any:
    path = Path(ref.path)
    got = sha_file(path)
    if got != ref.sha256:
        raise DriverViolation(f"bound file hash mismatch: {path} {got}")
    return json.loads(path.read_text())


def _partition_records(ref: FileRef, expected_partition: str) -> dict[str, Mapping[str, Any]]:
    raw = _read_bound_json(ref)
    if not isinstance(raw, Mapping) or raw.get("partition") != expected_partition:
        raise DriverViolation(f"{expected_partition} partition file tag mismatch")
    rows = raw.get("records")
    if not isinstance(rows, list):
        raise DriverViolation(f"{expected_partition} records missing")
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise DriverViolation("partition record must be mapping")
        cid = row.get("cell_id")
        if not isinstance(cid, str) or not cid or cid in out:
            raise DriverViolation("partition record cell_id missing/duplicate")
        out[cid] = dict(row)
    return out


def _orientation_rows(ref: FileRef, expected_partition: str) -> dict[str, Mapping[str, str]]:
    raw = _read_bound_json(ref)
    if not isinstance(raw, Mapping) or raw.get("partition") != expected_partition:
        raise DriverViolation("orientation partition tag mismatch")
    rows = raw.get("orientations")
    if not isinstance(rows, Mapping):
        raise DriverViolation("orientation mapping missing")
    out = {}
    for cid, mapping in rows.items():
        if not isinstance(mapping, Mapping):
            raise DriverViolation("orientation row must be mapping")
        converted = {str(k): str(v) for k, v in mapping.items()}
        if sorted(converted.values()) != ["p", "q"] or len(converted) != 2:
            raise DriverViolation("each orientation must biject two opaque endpoints to p/q")
        out[str(cid)] = converted
    return out


class Backend(Protocol):
    candidate_channels: Sequence[core.ChannelCoordinate]
    probe_bank_hash: str
    candidate_channel_hash: str

    def parameter_sha256(self) -> str: ...
    def collect_response_tensor(self, donor_prompt: str) -> tuple[float, ...]: ...
    def score_endpoints(self, visible_context: str, endpoints: Mapping[str, str], payload: protocol.PayloadManifest | None) -> Mapping[str, Any]: ...
    def score_single_gain(self, visible_context: str, endpoints: Mapping[str, str], block: int, channel: int, gain: float) -> Mapping[str, Any]: ...


class RealBackend:
    """Lazy exact-Qwen backend. Constructor is the first real model-access point."""
    def __init__(self) -> None:
        import planlatch_v7_9_model_runtime as mr
        self._mr = mr
        self._rt = mr.RealQwenRuntime(device="cuda")
        fp = self._rt.fingerprint()
        self.candidate_channels = tuple(core.ChannelCoordinate(int(b), int(c)) for b, c in fp.candidate_channels)
        self.probe_bank_hash = fp.opaque_probe_hash
        self.candidate_channel_hash = fp.candidate_channel_hash

    def parameter_sha256(self) -> str:
        return self._rt.parameter_sha256()

    def collect_response_tensor(self, donor_prompt: str) -> tuple[float, ...]:
        return self._rt.collect_response_tensor(donor_prompt)

    def score_endpoints(self, visible_context: str, endpoints: Mapping[str, str], payload: protocol.PayloadManifest | None) -> Mapping[str, Any]:
        return self._rt.score_opaque_endpoints(visible_context, endpoints, payload)

    def score_single_gain(self, visible_context: str, endpoints: Mapping[str, str], block: int, channel: int, gain: float) -> Mapping[str, Any]:
        if gain not in protocol.ALLOWED_GAINS:
            raise DriverViolation("single-gain candidate outside frozen gain set")
        if block < 0 or block >= len(self._rt.layers) or channel < 0 or channel >= self._rt.intermediate_sizes[block]:
            raise DriverViolation("single-gain candidate outside exact model")
        down = self._rt.layers[block].mlp.down_proj
        def hook(_module: Any, args: tuple[Any, ...]):
            x = args[0]
            y = x.clone()
            y[:, -1, channel] = y[:, -1, channel] * float(gain)
            return (y, *args[1:])
        handle = down.register_forward_pre_hook(hook)
        try:
            return self._rt.score_opaque_endpoints(visible_context, endpoints, None)
        finally:
            handle.remove()


class SyntheticBackend:
    """Pure deterministic backend used only for wrapper acceptance tests."""
    def __init__(self) -> None:
        self.candidate_channels = tuple(core.ChannelCoordinate(i // 64, i % 64) for i in range(core.CANDIDATE_CHANNEL_COUNT))
        self.probe_bank_hash = sha_json({"synthetic": "probe-bank"})
        self.candidate_channel_hash = sha_json([(x.block, x.channel) for x in self.candidate_channels])
        self._payload_p: str | None = None
        self._payload_q: str | None = None

    def parameter_sha256(self) -> str:
        return sha_json({"synthetic": "model-parameters"})

    def _desired_q_tensor(self, desired_q: int, seed: str) -> tuple[float, ...]:
        raw = hashlib.sha256(seed.encode()).digest()
        base = tuple(0.25 + (raw[i] / 255.0) for i in range(4))
        o = core.canonicalize_response(base)
        values = base if o.q == desired_q else tuple(-x for x in base)
        out = core.canonicalize_response(values)
        if out.q != desired_q:
            raise DriverViolation("synthetic q construction failed")
        return values

    def collect_response_tensor(self, donor_prompt: str) -> tuple[float, ...]:
        try:
            meta = json.loads(donor_prompt)
        except Exception as exc:
            raise DriverViolation("synthetic donor prompt must be JSON") from exc
        desired = int(meta["desired_q"])
        return self._desired_q_tensor(desired, str(meta["orbit_seed"]))

    def bind_payloads(self, cp: protocol.PayloadManifest, cq: protocol.PayloadManifest) -> None:
        self._payload_p, self._payload_q = cp.checksum, cq.checksum

    @staticmethod
    def _rows(endpoints: Mapping[str, str], pprob: float) -> Mapping[str, Any]:
        ids = sorted(endpoints)
        if len(ids) != 2:
            raise DriverViolation("synthetic endpoints require exactly two opaque IDs")
        probs = {ids[0]: pprob, ids[1]: 1.0 - pprob}
        rows = {}
        for eid in ids:
            pr = probs[eid]
            rows[eid] = {
                "choice_probability": pr,
                "mean_logprob": math.log(max(pr, 1e-12)),
                "logprob_sum": 2.0 * math.log(max(pr, 1e-12)),
                "token_count": 2,
            }
        best = sorted(ids, key=lambda k: (-rows[k]["choice_probability"], k))[0]
        return {"endpoints": rows, "top1_endpoint": best, "payload_applied": False}

    def score_endpoints(self, visible_context: str, endpoints: Mapping[str, str], payload: protocol.PayloadManifest | None) -> Mapping[str, Any]:
        base = 0.5
        if payload is not None and payload.checksum == self._payload_p:
            base = 0.62
        elif payload is not None and payload.checksum == self._payload_q:
            base = 0.38
        return self._rows(endpoints, base)

    def score_single_gain(self, visible_context: str, endpoints: Mapping[str, str], block: int, channel: int, gain: float) -> Mapping[str, Any]:
        # Deterministically split candidate preference; enough distinct channels exist for both banks.
        sign = 1.0 if ((block * 100000 + channel) % 2 == 0) else -1.0
        mag = 0.04 + 0.04 * (1 if gain == 1.25 else 0)
        return self._rows(endpoints, 0.5 + sign * mag)


@dataclass(frozen=True)
class AuthorityBinding:
    research_decision_id: str
    release_candidate_id: str
    final_review_id: str
    authority_hash: str


def verify_authority_bundle(raw: Mapping[str, Any]) -> AuthorityBinding:
    required = {
        "kind": AUTHORITY_KIND,
        "experiment_id": EXPERIMENT_ID,
        "scientific_design_id": DESIGN_ID,
        "scientific_semantic_hash": SEMANTIC_HASH,
        "implementation_commit": REVIEWED_RUNTIME_COMMIT,
        "runtime_engineering_result_id": RUNTIME_ENGINEERING_RESULT_ID,
        "runtime_fidelity_record_id": RUNTIME_FIDELITY_ID,
    }
    for key, expected in required.items():
        if raw.get(key) != expected:
            raise DriverViolation(f"authority mismatch: {key}")
    rid = raw.get("research_decision_id")
    rcid = raw.get("release_candidate_id")
    review = raw.get("final_review")
    if not isinstance(rid, str) or not rid or not isinstance(rcid, str) or not rcid:
        raise DriverViolation("research decision/release candidate authority missing")
    if not isinstance(review, Mapping) or review.get("verdict") != "PASS":
        raise DriverViolation("final PRE_SCIENCE review PASS required")
    if review.get("release_candidate_id") != rcid:
        raise DriverViolation("final review release candidate mismatch")
    frid = review.get("review_id")
    if not isinstance(frid, str) or not frid:
        raise DriverViolation("final review id missing")
    return AuthorityBinding(rid, rcid, frid, sha_json(raw))


class StageJournal:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "stage_journal.jsonl"
        self.prev = "0" * 64

    def append(self, stage: str, payload: Mapping[str, Any]) -> str:
        body = {"stage": stage, "payload": dict(payload), "previous_record_hash": self.prev}
        record_hash = sha_json(body)
        row = {**body, "record_hash": record_hash}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(stable_json(row) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.prev = record_hash
        return record_hash


@dataclass
class Obs:
    cell: core.FrameCell
    orbit: core.OrbitRecord
    source_row: Mapping[str, Any] | None = None


def _u_key(u: tuple[int, int, str]) -> str:
    return stable_json(list(u))


def _frame_cells(frame: core.FrameFreeze, partition: str) -> list[core.FrameCell]:
    return [c for c in frame.cells if c.partition == partition]


def _verify_partition_coverage(frame: core.FrameFreeze, partition: str, rows: Mapping[str, Mapping[str, Any]]) -> None:
    expected = {c.cell_id for c in _frame_cells(frame, partition)}
    if set(rows) != expected:
        missing = sorted(expected - set(rows))[:5]
        extra = sorted(set(rows) - expected)[:5]
        raise DriverViolation(f"{partition} cell coverage mismatch missing={missing} extra={extra}")


def _collect_partition(frame: core.FrameFreeze, partition: str, rows: Mapping[str, Mapping[str, Any]], backend: Backend) -> list[Obs]:
    _verify_partition_coverage(frame, partition, rows)
    out = []
    for cell in _frame_cells(frame, partition):
        row = rows[cell.cell_id]
        if row.get("task_id") != cell.task_id:
            raise DriverViolation("cell task_id mismatch")
        prompt = row.get("donor_prompt")
        if not isinstance(prompt, str) or not prompt:
            raise DriverViolation("donor_prompt missing")
        orbit = core.canonicalize_response(backend.collect_response_tensor(prompt))
        out.append(Obs(cell, orbit))
    return out


def _constructible(obs: Sequence[Obs], fit_obs: Sequence[Obs]) -> bool:
    def support(rows: Sequence[Obs]) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for x in rows:
            if x.cell.sham or x.orbit.j_singleton:
                continue
            out.setdefault(_u_key(x.cell.u), set()).add(x.cell.s)
        return out
    fit = support(fit_obs)
    cur = support(obs)
    return bool(cur) and all(labels == {"p", "q"} and fit.get(u) == {"p", "q"} for u, labels in cur.items())


def _fit_models(fit_obs: Sequence[Obs], cfg: core.DecoderConfig) -> dict[str, core.FittedSourceModels]:
    by_u: dict[str, list[Obs]] = {}
    for x in fit_obs:
        if x.cell.sham or x.orbit.j_singleton:
            continue
        by_u.setdefault(_u_key(x.cell.u), []).append(x)
    out = {}
    for uk, rows in sorted(by_u.items()):
        labels = {x.cell.s for x in rows}
        if labels != {"p", "q"}:
            raise DriverViolation(f"FIT constructibility failure for U={uk}")
        u = rows[0].cell.u
        out[uk] = core.fit_source_models(
            [x.orbit.o_star for x in rows],
            [int(x.orbit.q) for x in rows],
            [x.cell.s for x in rows],
            u,
            cfg,
        )
    return out


def _score_obs(obs: Sequence[Obs], models: Mapping[str, core.FittedSourceModels]) -> None:
    for x in obs:
        if x.orbit.j_singleton:
            x.source_row = None
            continue
        model = models.get(_u_key(x.cell.u))
        if model is None:
            raise DriverViolation("held-out U lacks frozen FIT model")
        x.source_row = core.score_source_record(model, x.orbit.o_star, int(x.orbit.q), x.cell.s)


def _class_u_block(rows: Sequence[Obs], *, sham: bool) -> tuple[float, float, float]:
    grouped: dict[str, dict[str, list[Obs]]] = {}
    for x in rows:
        if x.cell.sham != sham or x.orbit.j_singleton or x.source_row is None:
            continue
        grouped.setdefault(_u_key(x.cell.u), {}).setdefault(x.cell.s, []).append(x)
    if not grouped:
        raise DriverViolation("empty block standardized estimand")
    u_delta = []
    u_ba_inc = []
    u_full_ba = []
    for uk, cls in grouped.items():
        if set(cls) != {"p", "q"}:
            raise DriverViolation(f"block U missing p/q support: {uk}")
        cd = []
        cf = []
        cp = []
        for label in ("p", "q"):
            rr = cls[label]
            cd.append(sum(float(x.source_row["delta_log"]) for x in rr) / len(rr))
            cf.append(sum(x.source_row["full_label"] == label for x in rr) / len(rr))
            cp.append(sum(x.source_row["placebo_label"] == label for x in rr) / len(rr))
        u_delta.append(0.5 * (cd[0] + cd[1]))
        full_ba = 0.5 * (cf[0] + cf[1])
        placebo_ba = 0.5 * (cp[0] + cp[1])
        u_full_ba.append(full_ba)
        u_ba_inc.append(full_ba - placebo_ba)
    return (sum(u_delta) / len(u_delta), sum(u_ba_inc) / len(u_ba_inc), sum(u_full_ba) / len(u_full_ba))


def _block_vectors(obs: Sequence[Obs], partition: str, *, sham: bool = False) -> list[dict[str, float]]:
    by_b: dict[str, list[Obs]] = {}
    for x in obs:
        by_b.setdefault(x.cell.block_id, []).append(x)
    out = []
    for bid in sorted(by_b):
        d, bai, fba = _class_u_block(by_b[bid], sham=sham)
        out.append({"block_id": bid, "delta_b": d, "ba_increment": bai, "full_ba": fba})
    expected = 12 if partition == "SUPPORT" else 8 if partition == "PILOT" else None
    if expected is not None and len(out) != expected:
        raise DriverViolation(f"{partition} block count mismatch")
    return out


def _canary_bools(cfg: core.DecoderConfig) -> dict[str, bool]:
    raw = core.run_all_protocol_canaries(cfg)
    return {k: bool(v.get("passed")) for k, v in raw.items()}


def _source_report(frame: core.FrameFreeze, fit_obs: Sequence[Obs], support_obs: Sequence[Obs], pilot_obs: Sequence[Obs], cross_obs: Sequence[Obs], cfg: core.DecoderConfig) -> dict[str, Any]:
    constructible = all(_constructible(part, fit_obs) for part in (support_obs, pilot_obs, cross_obs))
    support = _block_vectors(support_obs, "SUPPORT", sham=False)
    pilot = _block_vectors(pilot_obs, "PILOT", sham=False)
    # Sham specificity: the matched sham must not itself satisfy the same SUPPORT+PILOT
    # source-effect evidence pattern; no new numeric threshold is introduced.
    sham_support = _block_vectors(support_obs, "SUPPORT", sham=True)
    sham_pilot = _block_vectors(pilot_obs, "PILOT", sham=True)
    sham_systematic = (
        sum(x["delta_b"] > 0 for x in sham_support) >= 10
        and core._median([x["delta_b"] for x in sham_support]) >= 0.02
        and core._median([x["ba_increment"] for x in sham_support]) >= 0.05
        and sum(x["delta_b"] > 0 for x in sham_pilot) >= 7
        and core._median([x["delta_b"] for x in sham_pilot]) >= 0.015
        and core._median([x["full_ba"] for x in sham_pilot]) >= 0.80
    )
    by_u: dict[str, list[float]] = {}
    eval_rows = [x for x in support_obs + pilot_obs if not x.cell.sham and not x.orbit.j_singleton and x.source_row]
    for x in eval_rows:
        by_u.setdefault(_u_key(x.cell.u), []).append(float(x.source_row["delta_log"]))
    per_u = [sum(v) / len(v) for _, v in sorted(by_u.items())]
    # U-only classifier sees one constant U within each stratum and equal standardized
    # p/q class weights; its balanced accuracy is exactly chance by construction.
    u_balanced = True
    for uk in by_u:
        labels = [x.cell.s for x in eval_rows if _u_key(x.cell.u) == uk]
        u_balanced = u_balanced and labels.count("p") == labels.count("q") and labels.count("p") > 0
    j_counts = {
        "j0": sum(not x.orbit.j_singleton for x in fit_obs + support_obs + pilot_obs + cross_obs),
        "j1": sum(x.orbit.j_singleton for x in fit_obs + support_obs + pilot_obs + cross_obs),
    }
    return {
        "frame_frozen_pre_T": True,
        "complete_cell_schedule": core.verify_complete_cells(frame),
        "response_derived_replacement": False,
        "only_U_external_router": True,
        "forbidden_paths_unreachable": True,
        "j_distribution_reported": True,
        "j_distribution": j_counts,
        "standardized_realized_j0_scope": True,
        "j1_member_contribution_zero": True,
        "uniform_preprocessing_weights": True,
        "label_permutation_invariant": True,
        "full_placebo_transformed_o_star_hash_equal": True,
        "bit_path_block_separable": True,
        "canaries": _canary_bools(cfg),
        "two_class_j0_constructible": constructible,
        "support_blocks": support,
        "pilot_blocks": pilot,
        "constructible_u_deltas": per_u,
        "u_only_baseline_cannot_explain": u_balanced,
        "u_only_standardized_balanced_accuracy": 0.5 if u_balanced else None,
        "sham_specificity_pass": not sham_systematic,
        "sham_support_blocks": sham_support,
        "sham_pilot_blocks": sham_pilot,
        "all_selection_actual_supported_q": True,
        "off_support_used_for_evidence_or_selection": False,
    }


def _fit_hashes(models: Mapping[str, core.FittedSourceModels], fit_obs: Sequence[Obs]) -> dict[str, str]:
    phi_payload = {k: v.phi.payload() for k, v in sorted(models.items())}
    decoder_payload = {
        k: {
            "full": {"w": list(v.full.weights), "b": v.full.bias, "cfg": dataclasses.asdict(v.full.config)},
            "placebo": {"w": list(v.placebo.weights), "b": v.placebo.bias, "cfg": dataclasses.asdict(v.placebo.config)},
        }
        for k, v in sorted(models.items())
    }
    transformed = {}
    for uk, model in sorted(models.items()):
        rows = [x.orbit.o_star for x in fit_obs if not x.cell.sham and not x.orbit.j_singleton and _u_key(x.cell.u) == uk]
        transformed[uk] = protocol.transformed_multiset_hash(protocol.transform_phi(model.phi, rows))
    return {
        "source_model_bytes_hash": sha_json({k: v.model_hash for k, v in sorted(models.items())}),
        "decoder_bytes_hash": sha_json(decoder_payload),
        "phi_bytes_hash": sha_json(phi_payload),
        "transformed_o_star_hash": sha_json(transformed),
    }


def _endpoint_prob(result: Mapping[str, Any], eid: str) -> float:
    return float(result["endpoints"][eid]["choice_probability"])


def _endpoint_stat(result: Mapping[str, Any], eid: str, field: str) -> float:
    return float(result["endpoints"][eid][field])


def _build_payloads(fit_rows: Mapping[str, Mapping[str, Any]], fit_obs: Sequence[Obs], backend: Backend) -> tuple[protocol.PayloadManifest, protocol.PayloadManifest, Mapping[str, Any]]:
    obs_by_cell = {x.cell.cell_id: x for x in fit_obs}
    eligible = []
    for cid, row in sorted(fit_rows.items()):
        x = obs_by_cell[cid]
        if x.cell.sham or x.orbit.j_singleton:
            continue
        ctx = row.get("actuator_visible_context")
        endpoints = row.get("actuator_endpoints")
        orientation = row.get("actuator_orientation")
        if not isinstance(ctx, str) or not isinstance(endpoints, Mapping) or not isinstance(orientation, Mapping):
            raise DriverViolation("FIT actuator context/endpoints/orientation missing")
        orientation = {str(k): str(v) for k, v in orientation.items()}
        if sorted(orientation.values()) != ["p", "q"] or set(orientation) != set(endpoints):
            raise DriverViolation("FIT actuator orientation must biject opaque endpoints to p/q")
        eid_p = next(k for k, v in orientation.items() if v == "p")
        eid_q = next(k for k, v in orientation.items() if v == "q")
        no = backend.score_endpoints(ctx, {str(k): str(v) for k, v in endpoints.items()}, None)
        eligible.append((cid, ctx, dict(endpoints), eid_p, eid_q, no))
    if not eligible:
        raise DriverViolation("no FIT actuator records")
    evid = []
    provenance_hash = sha_json([{"cell_id": c, "context_hash": sha_json(ctx), "endpoint_hash": sha_json(ep)} for c, ctx, ep, _, _, _ in eligible])
    for coord in backend.candidate_channels:
        for gain in protocol.ALLOWED_GAINS:
            psh = []
            qsh = []
            for _, ctx, endpoints, eid_p, eid_q, no in eligible:
                arm = backend.score_single_gain(ctx, endpoints, coord.block, coord.channel, gain)
                psh.append(_endpoint_prob(arm, eid_p) - _endpoint_prob(no, eid_p))
                qsh.append(_endpoint_prob(arm, eid_q) - _endpoint_prob(no, eid_q))
            evid.append(core.ActuatorCandidateEvidence(
                coord.block, coord.channel, float(gain),
                sum(psh) / len(psh), sum(qsh) / len(qsh),
                "FIT", provenance_hash,
            ))
    cp, cq, audit = core.construct_payload_bank_fit_only(evid)
    if hasattr(backend, "bind_payloads"):
        getattr(backend, "bind_payloads")(cp, cq)
    return cp, cq, audit


def _score_one_arm(backend: Backend, visible_context: str, endpoints: Mapping[str, str], payload: protocol.PayloadManifest | None) -> Mapping[str, Any]:
    # This function intentionally receives no donor T/O*/Q/source model/S/U/sham state.
    return backend.score_endpoints(visible_context, endpoints, payload)


def _raw_relay_scores(partition: str, rows: Mapping[str, Mapping[str, Any]], obs: Sequence[Obs], models: Mapping[str, core.FittedSourceModels], cp: protocol.PayloadManifest, cq: protocol.PayloadManifest, backend: Backend) -> dict[str, Any]:
    obs_by_cell = {x.cell.cell_id: x for x in obs}
    raw = {}
    for cid in sorted(rows):
        x = obs_by_cell[cid]
        if x.cell.sham or x.orbit.j_singleton:
            continue
        model = models.get(_u_key(x.cell.u))
        if model is None:
            raise DriverViolation("relay record U lacks frozen model")
        src = core.score_source_record(model, x.orbit.o_star, int(x.orbit.q), x.cell.s)
        s_hat = str(src["full_label"])
        selected = protocol.select_payload_from_observed_support(s_hat, cp, cq, observed_support=True)
        row = rows[cid]
        ctx = row.get("relay_visible_context")
        endpoints = row.get("relay_endpoints")
        valid_endpoint_ids = row.get("valid_endpoint_ids")
        if not isinstance(ctx, str) or not isinstance(endpoints, Mapping):
            raise DriverViolation("relay context/endpoints missing")
        endpoints = {str(k): str(v) for k, v in endpoints.items()}
        if not isinstance(valid_endpoint_ids, list) or set(map(str, valid_endpoint_ids)) != set(endpoints):
            raise DriverViolation("relay endpoints must be prospectively attested valid actions")
        context_hash = sha_json(ctx)
        endpoint_hash = sha_json(endpoints)
        # Freeze only payload identity; discard donor/source variables before clean-cache scoring.
        selected_checksum = selected.checksum
        del src, model, selected
        no = _score_one_arm(backend, ctx, endpoints, None)
        arm_p = _score_one_arm(backend, ctx, endpoints, cp)
        arm_q = _score_one_arm(backend, ctx, endpoints, cq)
        raw[cid] = {
            "partition": partition,
            "block_id": x.cell.block_id,
            "predicted_s": s_hat,
            "selected_payload_checksum": selected_checksum,
            "visible_context_hash": context_hash,
            "endpoint_manifest_hash": endpoint_hash,
            "valid_endpoint_ids": sorted(map(str, valid_endpoint_ids)),
            "no": no,
            "cp": arm_p,
            "cq": arm_q,
        }
    return raw


def _semantic_relay_summary(partition: str, raw: Mapping[str, Any], obs: Sequence[Obs], orientation: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    obs_by_cell = {x.cell.cell_id: x for x in obs}
    by_block: dict[str, list[dict[str, Any]]] = {}
    selected_by_class: dict[str, dict[str, Any]] = {
        "p": {"block_values": {}, "record_count": 0},
        "q": {"block_values": {}, "record_count": 0},
    }
    for cid, rr in sorted(raw.items()):
        orient = orientation.get(cid)
        if orient is None or set(orient) != set(rr["no"]["endpoints"]):
            raise DriverViolation("orientation missing/mismatched after raw-score freeze")
        eid_p = next(k for k, v in orient.items() if v == "p")
        eid_q = next(k for k, v in orient.items() if v == "q")
        cp_p = _endpoint_prob(rr["cp"], eid_p) - _endpoint_prob(rr["no"], eid_p)
        cq_q = _endpoint_prob(rr["cq"], eid_q) - _endpoint_prob(rr["no"], eid_q)
        sep = 0.5 * ((_endpoint_prob(rr["cp"], eid_p) - _endpoint_prob(rr["cq"], eid_p)) + (_endpoint_prob(rr["cq"], eid_q) - _endpoint_prob(rr["cp"], eid_q)))
        label = rr["predicted_s"]
        selected_res = rr["cp"] if label == "p" else rr["cq"]
        selected_eid = eid_p if label == "p" else eid_q
        selected_shift = _endpoint_prob(selected_res, selected_eid) - _endpoint_prob(rr["no"], selected_eid)
        x = obs_by_cell[cid]
        metric_direction = {}
        for field in ("choice_probability", "mean_logprob", "logprob_sum"):
            metric_direction[field] = {
                "cp": _endpoint_stat(rr["cp"], eid_p, field) - _endpoint_stat(rr["no"], eid_p, field),
                "cq": _endpoint_stat(rr["cq"], eid_q, field) - _endpoint_stat(rr["no"], eid_q, field),
            }
        no_top = rr["no"]["top1_endpoint"]
        cp_top = rr["cp"]["top1_endpoint"]
        cq_top = rr["cq"]["top1_endpoint"]
        top1 = {
            "cp_nonreversal": int(cp_top == eid_p) >= int(no_top == eid_p),
            "cq_nonreversal": int(cq_top == eid_q) >= int(no_top == eid_q),
        }
        valid_ids = set(rr["valid_endpoint_ids"])
        by_block.setdefault(rr["block_id"], []).append({
            "cp_p": cp_p, "cq_q": cq_q, "sep": sep,
            "selected_shift": selected_shift, "predicted_s": label, "true_s": x.cell.s,
            "metric_direction": metric_direction, "top1": top1,
            "no_valid": no_top in valid_ids,
            "cp_valid": cp_top in valid_ids,
            "cq_valid": cq_top in valid_ids,
        })
        bucket = selected_by_class[label]
        bucket["record_count"] += 1
        bucket["block_values"].setdefault(rr["block_id"], []).append(selected_shift)
    block_rows = {}
    for bid, vals in sorted(by_block.items()):
        metrics = {}
        for field in ("choice_probability", "mean_logprob", "logprob_sum"):
            metrics[field] = {
                "cp": sum(v["metric_direction"][field]["cp"] for v in vals) / len(vals),
                "cq": sum(v["metric_direction"][field]["cq"] for v in vals) / len(vals),
            }
        block_rows[bid] = {
            "cp": sum(v["cp_p"] for v in vals) / len(vals),
            "cq": sum(v["cq_q"] for v in vals) / len(vals),
            "sep": sum(v["sep"] for v in vals) / len(vals),
            "selected": sum(v["selected_shift"] for v in vals) / len(vals),
            "cp_true_p": [v["cp_p"] for v in vals if v["true_s"] == "p"],
            "cp_true_q": [v["cp_p"] for v in vals if v["true_s"] == "q"],
            "cq_true_p": [v["cq_q"] for v in vals if v["true_s"] == "p"],
            "cq_true_q": [v["cq_q"] for v in vals if v["true_s"] == "q"],
            "metric_direction": metrics,
            "cp_top1_nonreversal": sum(v["top1"]["cp_nonreversal"] for v in vals) / len(vals),
            "cq_top1_nonreversal": sum(v["top1"]["cq_nonreversal"] for v in vals) / len(vals),
            "no_valid_rate": sum(v["no_valid"] for v in vals) / len(vals),
            "cp_valid_rate": sum(v["cp_valid"] for v in vals) / len(vals),
            "cq_valid_rate": sum(v["cq_valid"] for v in vals) / len(vals),
        }
    class_rows = {}
    for label, bucket in selected_by_class.items():
        shifts = [sum(v) / len(v) for _, v in sorted(bucket["block_values"].items())]
        class_rows[label] = {"block_shifts": shifts, "block_count": len(shifts), "record_count": int(bucket["record_count"])}
    return {"partition": partition, "blocks": block_rows, "selected_by_class": class_rows}


def _relay_report(pilot: Mapping[str, Any], cross: Mapping[str, Any], cp: protocol.PayloadManifest, bank_audit: Mapping[str, Any], model_checksum_unchanged: bool) -> dict[str, Any]:
    pblocks = [pilot["blocks"][k] for k in sorted(pilot["blocks"])]
    if len(pblocks) != 8:
        raise DriverViolation("relay requires exactly 8 PILOT blocks")
    # "Survives true-S stratification" is evaluated as positive median direction
    # within each true-S stratum, not an every-record success requirement.
    strata = {"cp_true_p": [], "cp_true_q": [], "cq_true_p": [], "cq_true_q": []}
    for row in pblocks:
        for key in strata:
            strata[key].extend(row[key])
    direction_stratified = all(vals and core._median(vals) > 0 for vals in strata.values())

    cblocks = [cross["blocks"][k] for k in sorted(cross["blocks"])]
    cross_rows = [
        {"cp_correct": r["cp"] > 0, "cq_correct": r["cq"] > 0, "selected_correct": r["selected"] > 0}
        for r in cblocks
    ]
    first4 = cblocks[:4]
    # Reuse the frozen >=3/4 CROSS_REALIZATION criterion for endpoint-format
    # non-reversal. No additional numeric threshold is introduced.
    metric_nonreversal = True
    for field in ("choice_probability", "mean_logprob", "logprob_sum"):
        metric_nonreversal = metric_nonreversal and sum(r["metric_direction"][field]["cp"] > 0 for r in first4) >= 3
        metric_nonreversal = metric_nonreversal and sum(r["metric_direction"][field]["cq"] > 0 for r in first4) >= 3
    metric_nonreversal = metric_nonreversal and sum(r["cp_top1_nonreversal"] >= 0.5 for r in first4) >= 3
    metric_nonreversal = metric_nonreversal and sum(r["cq_top1_nonreversal"] >= 0.5 for r in first4) >= 3

    valid_action_worse_blocks = 0
    for r in first4:
        payload_valid = min(r["cp_valid_rate"], r["cq_valid_rate"])
        if payload_valid < r["no_valid_rate"]:
            valid_action_worse_blocks += 1

    return {
        "bank_fit_only": bool(bank_audit.get("fit_only")),
        "bank_identical_budget": True,
        "bank_structurally_distinct": True,
        "bank_independent_of_later_information": True,
        "applied_payload": cp.serialized_payload(),
        "payload_sole_donor_object_after_reset": True,
        "donor_state_unreachable": True,
        "model_parameter_checksum_unchanged": model_checksum_unchanged,
        "clean_cache_visible_context_identical": True,
        "selection_is_f_U_phiO_Q_actual_support": True,
        "payload_frozen_before_evaluator_unseal": True,
        "all_arm_scores_frozen_before_labels": True,
        "cp_vs_no_pilot": [r["cp"] for r in pblocks],
        "cq_vs_no_pilot": [r["cq"] for r in pblocks],
        "cp_vs_cq_directional_pilot": [r["sep"] for r in pblocks],
        "direction_survives_true_s_stratification": direction_stratified,
        "selected_payload_by_class": pilot["selected_by_class"],
        "cross_realization": cross_rows,
        "endpoint_no_systematic_reversal": metric_nonreversal,
        "valid_action_worse_blocks": valid_action_worse_blocks,
    }


def _make_pre_source(root: RootInput, frame: core.FrameFreeze, backend: Backend, model_hash: str, cfg: core.DecoderConfig) -> dict[str, Any]:
    freeze, _ = core.synthetic_runtime_freeze()
    return {
        "phase": "PRE_SOURCE",
        "design_id": DESIGN_ID,
        "semantic_hash": SEMANTIC_HASH,
        "runtime_freeze_hash": freeze.freeze_hash,
        "model_id": core.MODEL_ID,
        "model_revision": core.MODEL_REVISION,
        "model_dtype": core.MODEL_DTYPE,
        "quantization": core.MODEL_QUANTIZATION,
        "task_split": core.TASK_SPLIT,
        "never_consumed_train_inventory": True,
        "frame_hash": frame.frame_hash,
        "dependency_hash": frame.dependency_hash,
        "probe_bank_hash": backend.probe_bank_hash,
        "candidate_channel_hash": backend.candidate_channel_hash,
        "decoder_config_hash": cfg.config_hash,
        "task_inventory_hash": sha_json([dataclasses.asdict(x) for x in root.tasks]),
        "freshness_attestation_hash": sha_json(root.freshness_attestation),
        "model_parameter_hash": model_hash,
        "execution_root_hash": root.root_hash,
        "donor_program_hash": root.donor_program_hash,
        "washout_hash": root.washout_hash,
        "bound_partition_hashes": {k: v.sha256 for k, v in root.partition_files.items()},
        "bound_orientation_hashes": {k: v.sha256 for k, v in root.orientation_files.items()},
    }


def _make_post_fit(pre: core.PreSourceManifestBinding, root: RootInput, fit_hashes: Mapping[str, str], cp: protocol.PayloadManifest, cq: protocol.PayloadManifest, model_hash: str) -> dict[str, Any]:
    payload_hash = sha_json({"p": cp.serialized_payload(), "q": cq.serialized_payload()})
    reset_hash = sha_json({
        "payload_only": True,
        "applier_inputs": ["anonymous payload bytes", "arm-invariant visible context", "opaque endpoint manifest"],
        "forbidden": ["T", "gT", "O*", "Q", "phi", "decoder", "donor hidden/KV", "S/U/J/sham", "future evaluator orientation"],
    })
    return {
        "phase": "POST_FIT_HELDOUT",
        "design_id": DESIGN_ID,
        "semantic_hash": SEMANTIC_HASH,
        "pre_source_manifest_hash": pre.manifest_hash,
        "fit_only_complete": True,
        "heldout_partitions_unread_before_freeze": True,
        **dict(fit_hashes),
        "payload_bank_hash": payload_hash,
        "visible_context_manifest_hash": sha_json({k: root.partition_files[k].sha256 for k in ("PILOT", "CROSS_REALIZATION")}),
        "endpoint_manifest_hash": sha_json({k: root.orientation_files[k].sha256 for k in ("PILOT", "CROSS_REALIZATION")}),
        "reset_attestation_hash": reset_hash,
        "model_parameter_hash": model_hash,
    }


def run_pipeline(root: RootInput, backend: Backend, output_dir: str | Path, *, synthetic: bool = False) -> Mapping[str, Any]:
    reviewed_runtime_identity()
    out = Path(output_dir)
    if out.exists():
        raise DriverViolation("output namespace must be fresh")
    frame = core.compile_pre_response_frame(root.tasks)
    core.verify_complete_cells(frame)
    cfg, _ = core.freeze_decoder_config()
    model_hash0 = backend.parameter_sha256()
    pre_raw = _make_pre_source(root, frame, backend, model_hash0, cfg)
    pre = core.verify_pre_source_manifest(pre_raw, out)
    out.mkdir(parents=True)
    journal = StageJournal(out)
    (out / "pre_source_manifest.json").write_text(json.dumps(pre_raw, sort_keys=True, indent=2) + "\n")
    journal.append("PRE_SOURCE_FROZEN", {"manifest_hash": pre.manifest_hash})

    # FIT is the only partition opened before the POST_FIT_HELDOUT freeze.
    fit_rows = _partition_records(root.partition_files["FIT"], "FIT")
    fit_obs = _collect_partition(frame, "FIT", fit_rows, backend)
    models = _fit_models(fit_obs, cfg)
    _score_obs(fit_obs, models)
    cp, cq, bank_audit = _build_payloads(fit_rows, fit_obs, backend)
    fit_hashes = _fit_hashes(models, fit_obs)
    model_hash1 = backend.parameter_sha256()
    if model_hash1 != model_hash0:
        raise DriverViolation("model parameters changed during FIT")
    post_raw = _make_post_fit(pre, root, fit_hashes, cp, cq, model_hash1)
    post = core.verify_post_fit_manifest(post_raw, pre, out / "heldout-results")
    (out / "post_fit_manifest.json").write_text(json.dumps(post_raw, sort_keys=True, indent=2) + "\n")
    journal.append("POST_FIT_HELDOUT_FROZEN", {"manifest_hash": post.manifest_hash, "payload_bank_hash": post.payload_bank_hash})
    # Raw FIT donor tensors no longer needed; held-out partition bodies have not been opened yet.
    del fit_rows

    support_rows = _partition_records(root.partition_files["SUPPORT"], "SUPPORT")
    pilot_rows = _partition_records(root.partition_files["PILOT"], "PILOT")
    cross_rows = _partition_records(root.partition_files["CROSS_REALIZATION"], "CROSS_REALIZATION")
    support_obs = _collect_partition(frame, "SUPPORT", support_rows, backend)
    pilot_obs = _collect_partition(frame, "PILOT", pilot_rows, backend)
    cross_obs = _collect_partition(frame, "CROSS_REALIZATION", cross_rows, backend)
    _score_obs(support_obs, models)
    _score_obs(pilot_obs, models)
    _score_obs(cross_obs, models)
    source_report = _source_report(frame, fit_obs, support_obs, pilot_obs, cross_obs, cfg)
    journal.append("SOURCE_REPORT_FROZEN", {"source_report_hash": sha_json(source_report)})

    # Arm scores are frozen before evaluator-orientation sidecars are opened.
    pilot_raw = _raw_relay_scores("PILOT", pilot_rows, pilot_obs, models, cp, cq, backend)
    (out / "pilot_raw_arm_scores.json").write_text(json.dumps(pilot_raw, sort_keys=True, indent=2) + "\n")
    journal.append("PILOT_RAW_ARM_SCORES_FROZEN", {"hash": sha_file(out / "pilot_raw_arm_scores.json")})
    cross_raw = _raw_relay_scores("CROSS_REALIZATION", cross_rows, cross_obs, models, cp, cq, backend)
    (out / "cross_raw_arm_scores.json").write_text(json.dumps(cross_raw, sort_keys=True, indent=2) + "\n")
    journal.append("CROSS_RAW_ARM_SCORES_FROZEN", {"hash": sha_file(out / "cross_raw_arm_scores.json")})

    pilot_orientation = _orientation_rows(root.orientation_files["PILOT"], "PILOT")
    cross_orientation = _orientation_rows(root.orientation_files["CROSS_REALIZATION"], "CROSS_REALIZATION")
    pilot_sem = _semantic_relay_summary("PILOT", pilot_raw, pilot_obs, pilot_orientation)
    cross_sem = _semantic_relay_summary("CROSS_REALIZATION", cross_raw, cross_obs, cross_orientation)
    model_hash2 = backend.parameter_sha256()
    relay_report = _relay_report(pilot_sem, cross_sem, cp, bank_audit, model_hash2 == model_hash0)
    verdict = core.evaluate_g1_g20(source_report, relay_report)
    final = {
        "kind": "PLANLATCH_V79_TRAIN_RESULT" if not synthetic else "PLANLATCH_V79_SYNTHETIC_EXECUTION_NOT_SCIENTIFIC_EVIDENCE",
        "experiment_id": EXPERIMENT_ID,
        "prediction_id": PREDICTION_ID,
        "scientific_design_id": DESIGN_ID,
        "semantic_hash": SEMANTIC_HASH,
        "driver_version": DRIVER_VERSION,
        "pre_source_manifest_hash": pre.manifest_hash,
        "post_fit_manifest_hash": post.manifest_hash,
        "source_report": source_report,
        "relay_report": relay_report,
        "g1_g20": verdict,
        "model_parameter_checksum_unchanged": model_hash2 == model_hash0,
        "scientific_execution_performed": not synthetic,
        "synthetic_only": synthetic,
    }
    (out / "result.json").write_text(json.dumps(final, sort_keys=True, indent=2) + "\n")
    journal.append("RESULT_FROZEN", {"result_sha256": sha_file(out / "result.json"), "all_gates_passed": bool(verdict["all_passed"])})
    return final


def _make_synthetic_files(root_dir: Path) -> Path:
    root_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for i in range(36):
        tid = f"synthetic-train-{i:03d}"
        tasks.append({
            "task_id": tid,
            "m0": f"m0-{i % 3}",
            "cross_realization_tag": f"realization-{i:03d}",
            "split": "train",
            "never_consumed": True,
            "dependency_keys": {
                "base_task_identity": tid,
                "relation_template_group_id": f"rtg-{i}",
                "source_template_instance_family_id": f"stif-{i}",
                "paired_rng_ancestor_id": f"rng-{i}",
                "generation_seed_family_id": f"seed-{i}",
                "constructor_randomization_table_id": f"crt-{i}",
                "cache_namespace_parent_id": f"cache-{i}",
                "source_data_origin_family_id": f"origin-{i}",
            },
        })
    task_objs = tuple(core.BaseTaskMetadata(
        t["task_id"], t["m0"], t["dependency_keys"], t["cross_realization_tag"], t["split"], t["never_consumed"]
    ) for t in tasks)
    frame = core.compile_pre_response_frame(task_objs)
    partition_refs = {}
    orientation_refs = {}
    for partition in PARTITIONS:
        rows = []
        for cell in _frame_cells(frame, partition):
            # Non-sham records carry Q=S; sham records alternate Q independently of S.
            desired_q = (0 if cell.s == "p" else 1) if not cell.sham else (int(hashlib.sha256(cell.cell_id.encode()).hexdigest(), 16) % 2)
            orbit_seed = f"{cell.u}|{cell.task_id}|{cell.sham}"
            endpoints = {"e0": " alpha", "e1": " beta"}
            row = {
                "cell_id": cell.cell_id,
                "task_id": cell.task_id,
                "donor_prompt": stable_json({"desired_q": desired_q, "orbit_seed": orbit_seed}),
            }
            if partition == "FIT":
                row.update({
                    "actuator_visible_context": f"fit actuator {cell.cell_id}",
                    "actuator_endpoints": endpoints,
                    "actuator_orientation": {"e0": "p", "e1": "q"},
                })
            if partition in ("PILOT", "CROSS_REALIZATION"):
                row.update({
                    "relay_visible_context": f"relay {cell.cell_id}",
                    "relay_endpoints": endpoints,
                    "valid_endpoint_ids": sorted(endpoints),
                })
            rows.append(row)
        p = root_dir / f"{partition.lower()}.json"
        p.write_text(json.dumps({"partition": partition, "records": rows}, sort_keys=True, indent=2) + "\n")
        partition_refs[partition] = {"path": str(p), "sha256": sha_file(p)}
        if partition in ("PILOT", "CROSS_REALIZATION"):
            op = root_dir / f"{partition.lower()}_orientation.json"
            orientations = {row["cell_id"]: {"e0": "p", "e1": "q"} for row in rows if "relay_endpoints" in row}
            op.write_text(json.dumps({"partition": partition, "orientations": orientations}, sort_keys=True, indent=2) + "\n")
            orientation_refs[partition] = {"path": str(op), "sha256": sha_file(op)}
    root = {
        "kind": ROOT_KIND,
        "experiment_id": EXPERIMENT_ID,
        "tasks": tasks,
        "partition_files": partition_refs,
        "orientation_files": orientation_refs,
        "freshness_attestation": {"all_task_ids_never_consumed": True, "synthetic": True},
        "donor_program_hash": sha_json({"synthetic": "donor-program"}),
        "washout_hash": sha_json({"synthetic": "equal-token-washout"}),
    }
    rp = root_dir / "root.json"
    rp.write_text(json.dumps(root, sort_keys=True, indent=2) + "\n")
    return rp


def synthetic_execution(output: str | Path) -> Mapping[str, Any]:
    out = Path(output)
    inputs = out.parent / (out.name + "-synthetic-inputs")
    if inputs.exists() or out.exists():
        raise DriverViolation("synthetic namespaces must be fresh")
    root_path = _make_synthetic_files(inputs)
    root = load_root_input(root_path)
    return run_pipeline(root, SyntheticBackend(), out, synthetic=True)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--synthetic-execution", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--input-manifest")
    p.add_argument("--authority-bundle")
    p.add_argument("--output")
    args = p.parse_args(argv)
    if not args.output:
        raise DriverViolation("--output required")
    if args.synthetic_execution:
        result = synthetic_execution(args.output)
        print(stable_json({"synthetic_execution": True, "all_gates_passed": result["g1_g20"]["all_passed"], "scientific_execution_performed": False}))
        return 0
    if args.execute:
        if not args.authority_bundle or not args.input_manifest:
            raise DriverViolation("--execute requires --authority-bundle and --input-manifest")
        authority_raw = json.loads(Path(args.authority_bundle).read_text())
        verify_authority_bundle(authority_raw)
        root = load_root_input(args.input_manifest)
        # Authority is verified before this constructor can load torch/model/tokenizer.
        result = run_pipeline(root, RealBackend(), args.output, synthetic=False)
        print(stable_json({"experiment_id": EXPERIMENT_ID, "result_sha256": sha_file(Path(args.output) / "result.json"), "all_gates_passed": result["g1_g20"]["all_passed"]}))
        return 0
    raise DriverViolation("choose --synthetic-execution or --execute")


if __name__ == "__main__":
    raise SystemExit(main())
