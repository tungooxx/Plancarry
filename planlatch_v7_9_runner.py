"""PlanLatch v7.9 pre-science executable instrumentation.

This module is an additive realization of ScientificDesign
c8b8981a-352f-48c0-9bee-08bba6a46f7f.  Importing it never loads a model or
an environment.  Real model access is lazy and requires an exact frozen
execution manifest plus explicit ``--allow-real-execution``.

Scientific outcomes are intentionally not produced by the default CLI.  The
primary purpose of this file before release authority is to freeze and test
all implementation mechanics that are permitted to be chosen before response
inspection.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import planlatch_v7_9_protocol as protocol

DESIGN_ID = protocol.DESIGN_ID
SEMANTIC_HASH = protocol.SEMANTIC_HASH
RUNTIME_VERSION = "planlatch-v7.9-runtime-v1"
MODEL_ID = "Qwen/Qwen3-1.7B"
MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
MODEL_DTYPE = "bfloat16"
MODEL_QUANTIZATION = "NONE"
TASK_SPLIT = "train"
PROTOCOL_SHA256 = "e10db7c0b1552ca56e297ae0b8effe8e05988aad1be5e77ee9c42c534bc8222a"
DEPENDENCY_KEY_TYPES = (
    "base_task_identity",
    "relation_template_group_id",
    "source_template_instance_family_id",
    "paired_rng_ancestor_id",
    "generation_seed_family_id",
    "constructor_randomization_table_id",
    "cache_namespace_parent_id",
    "source_data_origin_family_id",
)
PARTITION_COUNTS = (("FIT", 12), ("PILOT", 8), ("SUPPORT", 12))
CROSS_REALIZATION_MIN = 4
CANDIDATE_CHANNEL_COUNT = 256
OPAQUE_PROBE_COUNT = 8
G_ACTION = "global-sign-involution-minus-I-v1"
T_FLOAT_FORMAT = "ieee754-f32-le"
DECODER_FAMILY = "binary-logistic-fullbatch-gd-v1"
DECODER_CANDIDATES = (
    {"l2": 0.01, "lr": 0.2, "steps": 400},
    {"l2": 0.1, "lr": 0.15, "steps": 500},
    {"l2": 1.0, "lr": 0.1, "steps": 600},
)
DECODER_TOLERANCE = 1e-12

class RuntimeViolation(RuntimeError):
    pass


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def protocol_byte_identity(root: str | Path = ".") -> bool:
    got = sha256_file(Path(root) / "planlatch_v7_9_protocol.py")
    if got != PROTOCOL_SHA256:
        raise RuntimeViolation(f"protocol byte identity mismatch: {got}")
    return True


@dataclass(frozen=True)
class BaseTaskMetadata:
    task_id: str
    m0: str
    dependency_keys: Mapping[str, str | None]
    cross_realization_tag: str
    split: str
    never_consumed: bool

    def __post_init__(self) -> None:
        if not self.task_id or not self.m0 or not self.cross_realization_tag:
            raise RuntimeViolation("task_id, m0 and cross_realization_tag must be frozen pre-response")
        if self.split != TASK_SPLIT:
            raise RuntimeViolation("PlanLatch v7.9 frame accepts TRAIN split only")
        if self.never_consumed is not True:
            raise RuntimeViolation("PlanLatch v7.9 requires fresh never-consumed base task identities")
        unknown = set(self.dependency_keys) - set(DEPENDENCY_KEY_TYPES)
        if unknown:
            raise RuntimeViolation(f"unknown dependency key types: {sorted(unknown)}")
        if "base_task_identity" not in self.dependency_keys:
            raise RuntimeViolation("base_task_identity dependency key is required")
        if str(self.dependency_keys.get("base_task_identity")) != self.task_id:
            raise RuntimeViolation("base_task_identity must equal task_id")


@dataclass(frozen=True)
class FrameCell:
    block_id: str
    task_id: str
    partition: str
    s: str
    a: int
    h: int
    sham: bool
    m0: str
    u: tuple[int, int, str]
    cell_id: str


@dataclass(frozen=True)
class FrameFreeze:
    block_ids: tuple[str, ...]
    partition_by_block: Mapping[str, str]
    cells: tuple[FrameCell, ...]
    frame_hash: str
    dependency_hash: str


def _connected_components(tasks: Sequence[BaseTaskMetadata]) -> list[list[BaseTaskMetadata]]:
    if len({t.task_id for t in tasks}) != len(tasks):
        raise RuntimeViolation("duplicate task_id in pre-response inventory")
    parent = list(range(len(tasks)))
    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    seen: dict[tuple[str, str], int] = {}
    for idx, task in enumerate(tasks):
        for key in DEPENDENCY_KEY_TYPES:
            raw = task.dependency_keys.get(key)
            if raw is None or raw == "":
                continue
            token = (key, str(raw))
            if token in seen:
                union(idx, seen[token])
            else:
                seen[token] = idx
    groups: dict[int, list[BaseTaskMetadata]] = {}
    for i, task in enumerate(tasks):
        groups.setdefault(find(i), []).append(task)
    out = []
    for group in groups.values():
        out.append(sorted(group, key=lambda t: t.task_id))
    out.sort(key=lambda g: sha256_json([t.task_id for t in g]))
    return out


def compile_pre_response_frame(tasks: Sequence[BaseTaskMetadata]) -> FrameFreeze:
    """Freeze whole dependency blocks and complete S×A×H+sham schedules.

    No response-dependent field is accepted by this API.
    """
    groups = _connected_components(tuple(tasks))
    needed = sum(n for _, n in PARTITION_COUNTS) + CROSS_REALIZATION_MIN
    if len(groups) < needed:
        raise RuntimeViolation(f"constructibility fail: need >= {needed} B components, got {len(groups)}")
    # Freeze FIT/PILOT/SUPPORT first from deterministic pre-response B order.
    fixed_n = sum(n for _, n in PARTITION_COUNTS)
    fixed_groups = groups[:fixed_n]
    remaining = groups[fixed_n:]
    cross_groups: list[list[BaseTaskMetadata]] = []
    seen_realizations: set[tuple[str, ...]] = set()
    for group in remaining:
        tags={t.cross_realization_tag for t in group}
        if len(tags)!=1:
            continue
        tag=tuple(sorted(tags))
        if tag in seen_realizations:
            continue
        seen_realizations.add(tag)
        cross_groups.append(group)
        if len(cross_groups) == CROSS_REALIZATION_MIN:
            break
    if len(cross_groups) < CROSS_REALIZATION_MIN:
        raise RuntimeViolation("constructibility fail: need >=4 distinct CROSS_REALIZATION concrete realization groups")
    groups = fixed_groups + cross_groups
    block_ids: list[str] = []
    partition_by_block: dict[str, str] = {}
    cursor = 0
    for name, count in PARTITION_COUNTS:
        for group in groups[cursor:cursor+count]:
            bid = "B-" + sha256_json([t.task_id for t in group])[:16]
            block_ids.append(bid)
            partition_by_block[bid] = name
        cursor += count
    for group in groups[cursor:]:
        bid = "B-" + sha256_json([t.task_id for t in group])[:16]
        block_ids.append(bid)
        partition_by_block[bid] = "CROSS_REALIZATION"
    cells: list[FrameCell] = []
    for group, bid in zip(groups, block_ids):
        partition = partition_by_block[bid]
        for task in group:
            for s in protocol.LABEL_ORDER:
                for a in (0, 1):
                    for h in (0, 1):
                        for sham in (False, True):
                            payload = {
                                "block_id": bid, "task_id": task.task_id, "partition": partition,
                                "s": s, "a": a, "h": h, "sham": sham, "m0": task.m0,
                            }
                            cid = "cell-" + sha256_json(payload)[:20]
                            cells.append(FrameCell(bid, task.task_id, partition, s, a, h, sham, task.m0, (a, h, task.m0), cid))
    dep_payload = [
        {"block_id": bid, "tasks": [t.task_id for t in group],
         "keys": [{k: t.dependency_keys.get(k) for k in DEPENDENCY_KEY_TYPES} for t in group]}
        for group, bid in zip(groups, block_ids)
    ]
    dependency_hash = sha256_json(dep_payload)
    frame_payload = [dataclasses.asdict(c) for c in cells]
    return FrameFreeze(tuple(block_ids), partition_by_block, tuple(cells), sha256_json(frame_payload), dependency_hash)


def verify_complete_cells(frame: FrameFreeze) -> bool:
    by_task: dict[tuple[str, str], set[tuple[str, int, int, bool]]] = {}
    for cell in frame.cells:
        by_task.setdefault((cell.block_id, cell.task_id), set()).add((cell.s, cell.a, cell.h, cell.sham))
    expected = {(s, a, h, sham) for s in protocol.LABEL_ORDER for a in (0,1) for h in (0,1) for sham in (False, True)}
    if not by_task or any(v != expected for v in by_task.values()):
        raise RuntimeViolation("incomplete S×A×H+sham schedule")
    return True


@dataclass(frozen=True)
class OpaqueProbeBank:
    probe_ids: tuple[str, ...]
    token_ids: tuple[int, ...]
    bank_hash: str


def derive_opaque_probe_bank(vocab_size: int, special_token_ids: Iterable[int]) -> OpaqueProbeBank:
    if vocab_size <= OPAQUE_PROBE_COUNT + len(set(special_token_ids)):
        raise RuntimeViolation("vocab too small for opaque probe bank")
    forbidden = {int(x) for x in special_token_ids if x is not None}
    chosen: list[int] = []
    counter = 0
    while len(chosen) < OPAQUE_PROBE_COUNT:
        digest = hashlib.sha256(f"{SEMANTIC_HASH}|{MODEL_REVISION}|opaque-probe|{counter}".encode()).digest()
        tid = int.from_bytes(digest[:8], "big") % vocab_size
        counter += 1
        if tid in forbidden or tid in chosen:
            continue
        chosen.append(tid)
    ids = tuple(f"probe-{i:02d}" for i in range(len(chosen)))
    payload = {"probe_ids": ids, "token_ids": tuple(chosen), "selection":"hash-only-no-token-decoding"}
    return OpaqueProbeBank(ids, tuple(chosen), sha256_json(payload))


@dataclass(frozen=True)
class ChannelCoordinate:
    block: int
    channel: int


def derive_candidate_channels(block_intermediate_sizes: Sequence[int]) -> tuple[ChannelCoordinate, ...]:
    universe: list[tuple[str, ChannelCoordinate]] = []
    for block, width in enumerate(block_intermediate_sizes):
        if width <= 0:
            raise RuntimeViolation("MLP intermediate width must be positive")
        for channel in range(int(width)):
            coord = ChannelCoordinate(block, channel)
            rank = hashlib.sha256(f"{SEMANTIC_HASH}|{MODEL_REVISION}|channel|{block}|{channel}".encode()).hexdigest()
            universe.append((rank, coord))
    universe.sort(key=lambda x: x[0])
    if len(universe) < CANDIDATE_CHANNEL_COUNT:
        raise RuntimeViolation("model has too few MLP channels")
    return tuple(x[1] for x in universe[:CANDIDATE_CHANNEL_COUNT])


def serialize_t(values: Sequence[float]) -> bytes:
    if not values:
        raise RuntimeViolation("T cannot be empty")
    out = bytearray()
    for v in values:
        x = float(v)
        if not math.isfinite(x):
            raise RuntimeViolation("T contains non-finite response")
        # Exact-byte singleton/orbit semantics require one canonical zero encoding.
        # IEEE -0.0 and +0.0 are numerically equal but byte-distinct.
        if x == 0.0:
            x = 0.0
        out.extend(struct.pack("<f", x))
    return bytes(out)


def deserialize_t(blob: bytes) -> tuple[float, ...]:
    if not blob or len(blob) % 4:
        raise RuntimeViolation("invalid T bytes")
    return tuple(x[0] for x in struct.iter_unpack("<f", blob))


def apply_g(t_blob: bytes) -> bytes:
    values = deserialize_t(t_blob)
    return serialize_t(tuple(-x for x in values))


@dataclass(frozen=True)
class OrbitRecord:
    c0: bytes
    c1: bytes
    o_star: tuple[float, ...]
    j_singleton: bool
    q: int | None
    orbit_hash: str


def canonicalize_response(t_values: Sequence[float]) -> OrbitRecord:
    t = serialize_t(t_values)
    gt = apply_g(t)
    singleton = t == gt
    c0 = min(t, gt)
    c1 = apply_g(c0)
    if c1 != max(t, gt):
        raise RuntimeViolation("g/canonicalization inconsistency")
    q = None if singleton else (0 if t == c0 else 1)
    o = deserialize_t(c0) + deserialize_t(c1)
    return OrbitRecord(c0, c1, o, singleton, q, sha256_json({"c0":c0.hex(),"c1":c1.hex()}))


@dataclass(frozen=True)
class DecoderConfig:
    family: str
    l2: float
    lr: float
    steps: int
    config_hash: str


@dataclass(frozen=True)
class LinearDecoder:
    weights: tuple[float, ...]
    bias: float
    config: DecoderConfig

    def p_q(self, features: Sequence[float]) -> tuple[float, float]:
        if len(features) != len(self.weights):
            raise RuntimeViolation("decoder feature width mismatch")
        z = self.bias + sum(w*x for w,x in zip(self.weights, features))
        if z >= 0:
            e = math.exp(-z); pq = 1.0/(1.0+e)
        else:
            e = math.exp(z); pq = e/(1.0+e)
        return (1.0-pq, pq)

    def label(self, features: Sequence[float]) -> str:
        pp, pq = self.p_q(features)
        # Frozen label order p,q means ties select p.
        return "p" if pp >= pq else "q"


def _np():
    try:
        import numpy as np  # type: ignore
    except Exception as exc:
        raise RuntimeViolation(f"numpy unavailable: {exc}") from exc
    return np


def _fit_linear_decoder(x_rows: Sequence[Sequence[float]], labels: Sequence[str], record_weights: Sequence[float], cfg: DecoderConfig) -> LinearDecoder:
    np = _np()
    x = np.asarray(x_rows, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] == 0:
        raise RuntimeViolation("decoder requires nonempty 2D X")
    y = np.asarray([0.0 if s == "p" else 1.0 for s in labels], dtype=np.float64)
    wts = np.asarray(record_weights, dtype=np.float64)
    if len(y) != x.shape[0] or len(wts) != x.shape[0] or np.any(wts <= 0):
        raise RuntimeViolation("decoder row/weight mismatch")
    denom = float(wts.sum())
    beta = np.zeros(x.shape[1], dtype=np.float64)
    bias = 0.0
    for _ in range(cfg.steps):
        z = x @ beta + bias
        z = np.clip(z, -40.0, 40.0)
        p = 1.0 / (1.0 + np.exp(-z))
        err = (p-y) * wts / denom
        gb = float(err.sum())
        gw = x.T @ err + cfg.l2 * beta
        beta -= cfg.lr * gw
        bias -= cfg.lr * gb
    return LinearDecoder(tuple(float(v) for v in beta.tolist()), float(bias), cfg)


def _decoder_features(phi_row: Sequence[float], bit: int) -> tuple[float, ...]:
    return protocol.decoder_input(phi_row, bit)


def _balanced_accuracy(y: Sequence[str], pred: Sequence[str]) -> float:
    recalls=[]
    for label in protocol.LABEL_ORDER:
        idx=[i for i,s in enumerate(y) if s==label]
        if not idx: raise RuntimeViolation("balanced accuracy requires both classes")
        recalls.append(sum(pred[i]==label for i in idx)/len(idx))
    return sum(recalls)/2.0


def _log_score(decoder: LinearDecoder, x: Sequence[float], label: str) -> float:
    pp,pq=decoder.p_q(x); p=pp if label=="p" else pq
    return math.log(max(p, 1e-15))


def _synthetic_decoder_canaries(raw_cfg: Mapping[str, Any]) -> tuple[bool, dict[str, float]]:
    cfg=DecoderConfig(DECODER_FAMILY,float(raw_cfg["l2"]),float(raw_cfg["lr"]),int(raw_cfg["steps"]),sha256_json(raw_cfg))
    # Positive: identical O*, Q=S.
    o=[(0.0,0.0)]*40; y=["p"]*20+["q"]*20; q=[0]*20+[1]*20
    phi=protocol.fit_phi(o); z=protocol.transform_phi(phi,o); weights=protocol.class_balance_weights(y)
    full=_fit_linear_decoder([_decoder_features(r,b) for r,b in zip(z,q)],y,weights,cfg)
    placebo_rows=[]; placebo_y=[]; placebo_w=[]
    for r,s,w in zip(z,y,weights):
        placebo_rows.extend((_decoder_features(r,0),_decoder_features(r,1))); placebo_y.extend((s,s)); placebo_w.extend((0.5*w,0.5*w))
    plc=_fit_linear_decoder(placebo_rows,placebo_y,placebo_w,cfg)
    f_pred=[full.label(_decoder_features(r,b)) for r,b in zip(z,q)]
    p_pred=[protocol.placebo_hard_prediction({"p":plc.p_q(_decoder_features(r,0))[0],"q":plc.p_q(_decoder_features(r,0))[1]}, {"p":plc.p_q(_decoder_features(r,1))[0],"q":plc.p_q(_decoder_features(r,1))[1]}) for r in z]
    ba_gain=_balanced_accuracy(y,f_pred)-_balanced_accuracy(y,p_pred)
    f_ls=sum(_log_score(full,_decoder_features(r,b),s) for r,b,s in zip(z,q,y))/len(y)
    p_ls=sum(0.5*(_log_score(plc,_decoder_features(r,0),s)+_log_score(plc,_decoder_features(r,1),s)) for r,s in zip(z,y))/len(y)
    log_gain=f_ls-p_ls
    # Factorized negative: O* already linearly contains S; bit balanced irrelevant.
    o2=[(-2.0,0.0)]*20+[(2.0,0.0)]*20; y2=y; q2=[i%2 for i in range(40)]
    phi2=protocol.fit_phi(o2); z2=protocol.transform_phi(phi2,o2); w2=protocol.class_balance_weights(y2)
    f2=_fit_linear_decoder([_decoder_features(r,b) for r,b in zip(z2,q2)],y2,w2,cfg)
    pr=[]; py=[]; pw=[]
    for r,s,w in zip(z2,y2,w2): pr += [_decoder_features(r,0),_decoder_features(r,1)]; py += [s,s]; pw += [0.5*w,0.5*w]
    p2=_fit_linear_decoder(pr,py,pw,cfg)
    f2ls=sum(_log_score(f2,_decoder_features(r,b),s) for r,b,s in zip(z2,q2,y2))/40
    p2ls=sum(0.5*(_log_score(p2,_decoder_features(r,0),s)+_log_score(p2,_decoder_features(r,1),s)) for r,s in zip(z2,y2))/40
    f2pred=[f2.label(_decoder_features(r,b)) for r,b in zip(z2,q2)]
    p2pred=[protocol.placebo_hard_prediction({"p":p2.p_q(_decoder_features(r,0))[0],"q":p2.p_q(_decoder_features(r,0))[1]}, {"p":p2.p_q(_decoder_features(r,1))[0],"q":p2.p_q(_decoder_features(r,1))[1]}) for r in z2]
    neg_log=abs(f2ls-p2ls); neg_ba=abs(_balanced_accuracy(y2,f2pred)-_balanced_accuracy(y2,p2pred))
    passed=ba_gain>=0.25 and log_gain>=0.20 and neg_log<=0.01 and neg_ba<=0.02
    return passed,{"positive_ba_gain":ba_gain,"positive_log_gain":log_gain,"factorized_abs_log_gain":neg_log,"factorized_abs_ba_gain":neg_ba}



def _fit_collapsed_placebo_reference(
    transformed_o: Sequence[Sequence[float]], labels: Sequence[str], record_weights: Sequence[float], cfg: DecoderConfig
) -> LinearDecoder:
    """Independent N-original-record reference optimizer for the frozen PLACEBO law."""
    np=_np()
    z=np.asarray(transformed_o,dtype=np.float64)
    if z.ndim!=2 or z.shape[0]==0: raise RuntimeViolation("collapsed PLACEBO reference requires nonempty 2D O*")
    y=np.asarray([0.0 if x=="p" else 1.0 for x in labels],dtype=np.float64)
    rw=np.asarray(record_weights,dtype=np.float64)
    if len(y)!=z.shape[0] or len(rw)!=z.shape[0] or np.any(rw<=0): raise RuntimeViolation("collapsed PLACEBO reference row/weight mismatch")
    x0=np.asarray([_decoder_features(row,0) for row in z],dtype=np.float64)
    x1=np.asarray([_decoder_features(row,1) for row in z],dtype=np.float64)
    denom=float(rw.sum()); beta=np.zeros(x0.shape[1],dtype=np.float64); bias=0.0
    for _ in range(cfg.steps):
        p0=1.0/(1.0+np.exp(-np.clip(x0@beta+bias,-40.0,40.0)))
        p1=1.0/(1.0+np.exp(-np.clip(x1@beta+bias,-40.0,40.0)))
        e0=(p0-y)*rw*(0.5/denom); e1=(p1-y)*rw*(0.5/denom)
        gb=float(e0.sum()+e1.sum())
        gw=x0.T@e0+x1.T@e1+cfg.l2*beta
        beta-=cfg.lr*gw; bias-=cfg.lr*gb
    return LinearDecoder(tuple(float(v) for v in beta.tolist()),float(bias),cfg)


def run_all_protocol_canaries(cfg: DecoderConfig) -> dict[str,Any]:
    """Run every named v7.9 synthetic canary/interpretation guard before real data."""
    out: dict[str,Any]={}
    decoder_ok,dm=_synthetic_decoder_canaries({"l2":cfg.l2,"lr":cfg.lr,"steps":cfg.steps})
    out["positive"]={"passed":dm["positive_ba_gain"]>=0.25 and dm["positive_log_gain"]>=0.20,"metrics":dm}
    out["factorized_negative"]={"passed":dm["factorized_abs_log_gain"]<=0.01 and dm["factorized_abs_ba_gain"]<=0.02,"metrics":dm}

    # Common O* geometry / label permutation invariance.
    o=[(-2.0,0.5),(-1.0,-0.5),(1.0,0.5),(2.0,-0.5)]*4
    labels=["p","q","p","q"]*4; q=[0,1,1,0]*4
    phi_a=protocol.fit_phi(o); tx_a=protocol.transform_phi(phi_a,o)
    labels_perm=list(reversed(labels)); q_flip=[1-x for x in q]
    phi_b=protocol.fit_phi(o); tx_b=protocol.transform_phi(phi_b,o)
    out["label_permutation_preprocessing_invariance"]={"passed":phi_a.serialized_bytes()==phi_b.serialized_bytes() and protocol.transformed_multiset_hash(tx_a)==protocol.transformed_multiset_hash(tx_b)}

    # Conditional-placebo: physical Q changes cannot alter the semantic-null fitted arm.
    m_a=fit_source_models(o,q,labels,(0,0,"canary"),cfg)
    m_b=fit_source_models(o,q_flip,labels,(0,0,"canary"),cfg)
    out["conditional_placebo"]={"passed":m_a.placebo==m_b.placebo and m_a.phi.serialized_bytes()==m_b.phi.serialized_bytes()}

    # Independent collapsed-N-record optimizer vs expanded implementation.
    weights=protocol.class_balance_weights(labels)
    expanded=m_a.placebo
    collapsed=_fit_collapsed_placebo_reference(tx_a,labels,weights,cfg)
    max_w=max(abs(a-b) for a,b in zip(expanded.weights,collapsed.weights)); db=abs(expanded.bias-collapsed.bias)
    pred_diff=max(abs(a-b) for row in tx_a for a,b in zip(expanded.p_q(_decoder_features(row,0)),collapsed.p_q(_decoder_features(row,0))))
    out["collapsed_symmetric_null_objective_equivalence"]={"passed":max(max_w,db,pred_diff)<=DECODER_TOLERANCE,"max_parameter_or_prediction_abs_diff":max(max_w,db,pred_diff)}

    # One-record p_mix reduction and deterministic frozen tie rule.
    p0={"p":0.8,"q":0.2}; p1={"p":0.2,"q":0.8}; mix=protocol.p_mix(p0,p1)
    out["placebo_metric_reduction"]={"passed":mix=={"p":0.5,"q":0.5} and protocol.placebo_hard_prediction(p0,p1)=="p" and abs(protocol.placebo_log_score(-0.2,-0.8)+0.5)<=1e-15}

    # Decoder-relative exact-reference null plus invalid geometry rejection flag.
    out["decoder_relative_common_transform_null"]={"passed":protocol.decoder_relative_null_canary(0.625,0.625,tolerance=DECODER_TOLERANCE,invalid_preprocessing_geometry_changed=True)}

    # Incompatible U-router fixture: Q is only an exogenous U proxy; within-U null remains null.
    router_gains=[]
    for ubit in (0,1):
        ro=[(-1.0,0.0),(1.0,0.0)]*20
        ry=["p","q"]*20 if ubit==0 else ["q","p"]*20
        rq=[ubit]*40
        mm=fit_source_models(ro,rq,ry,(ubit,0,"router"),cfg)
        vals=[score_source_record(mm,row,bit,label)["delta_log"] for row,bit,label in zip(ro,rq,ry)]
        router_gains.append(sum(vals)/len(vals))
    out["incompatible_nuisance_router"]={"passed":max(abs(x) for x in router_gains)<=0.01,"per_u_mean_log_gain":router_gains}

    # J=1 cannot change preprocessing/source statistic.
    base_obs=[protocol.MemberObservation((float(i),float(i*i)),False) for i in range(1,5)]
    plus=base_obs+[protocol.MemberObservation((9999.0,-9999.0),True)]
    j_phi=(protocol.fit_phi_from_members(base_obs).serialized_bytes()==protocol.fit_phi_from_members(plus).serialized_bytes())
    ja=protocol.standardized_j0_delta([-0.1,-0.2,-0.3,-0.4],[-0.2,-0.3,-0.4,-0.5],["p","q","p","q"],[False]*4)
    jb=protocol.standardized_j0_delta([-0.1,-0.2,-0.3,-0.4,999.0],[-0.2,-0.3,-0.4,-0.5,-999.0],["p","q","p","q","p"],[False]*4+[True])
    out["singleton_zero"]={"passed":j_phi and ja==jb}

    # Off-support diagnostic cannot cross the selection boundary.
    triples_p=tuple(protocol.PayloadTriple(i//8,i,protocol.ALLOWED_GAINS[i%2]) for i in range(protocol.PAYLOAD_K))
    triples_q=tuple(protocol.PayloadTriple((i+1)//8,100+i,protocol.ALLOWED_GAINS[(i+1)%2]) for i in range(protocol.PAYLOAD_K))
    cp=protocol.make_payload_manifest(triples_p); cq=protocol.make_payload_manifest(triples_q)
    blocked=False
    try: protocol.select_payload_from_observed_support(protocol.off_support_q_toggle_diagnostic("toggle"),cp,cq,observed_support=True)
    except protocol.ProtocolViolation: blocked=True
    out["off_support_toggle_boundary"]={"passed":blocked and not protocol.off_support_q_toggle_diagnostic("toggle").scientific_use_allowed}

    # Selection-boundary guard: adding arbitrary J=1 observations must not alter member statistic.
    out["J_selection_boundary"]={"passed":ja==jb,"interpretation":"selected-population-only guard; no selection-immunity upgrade"}

    # Redundant-chart boundary: Q=r(O*) can aid a restricted decoder without beyond-O* information.
    ro=[]; ry=[]; rq=[]
    for x in (-2.0,-1.0,1.0,2.0):
        bit=1 if abs(x)>1.5 else 0; lab="q" if bit else "p"
        for _ in range(12): ro.append((x,)); rq.append(bit); ry.append(lab)
    rm=fit_source_models(ro,rq,ry,(0,0,"redundant"),cfg)
    rr=[score_source_record(rm,row,bit,lab) for row,bit,lab in zip(ro,rq,ry)]
    gain=sum(x["delta_log"] for x in rr)/len(rr)
    out["orbit_redundant_chart_boundary"]={"passed":gain>0.05,"mean_decoder_relative_log_gain":gain,"interpretation":"positive gain is compatible with Q being deterministic from O*"}

    if not decoder_ok or not all(bool(v.get("passed")) for v in out.values()):
        failed=[k for k,v in out.items() if not bool(v.get("passed"))]
        raise RuntimeViolation(f"v7.9 protocol canary failure: {failed}")
    return out

def freeze_decoder_config() -> tuple[DecoderConfig, dict[str, Any]]:
    attempts=[]
    for raw in DECODER_CANDIDATES:
        passed,metrics=_synthetic_decoder_canaries(raw)
        attempts.append({"config":raw,"metrics":metrics,"passed":passed})
        if passed:
            cfg=DecoderConfig(DECODER_FAMILY,float(raw["l2"]),float(raw["lr"]),int(raw["steps"]),sha256_json({"family":DECODER_FAMILY,**raw}))
            return cfg,{"attempts":attempts,"selected":dataclasses.asdict(cfg)}
    raise RuntimeViolation("no decoder config passes synthetic protocol canaries")


@dataclass(frozen=True)
class FittedSourceModels:
    phi: protocol.PhiState
    full: LinearDecoder
    placebo: LinearDecoder
    u: tuple[int,int,str]
    model_hash: str


def fit_source_models(o_rows: Sequence[Sequence[float]], q_bits: Sequence[int], labels: Sequence[str], u: tuple[int,int,str], cfg: DecoderConfig) -> FittedSourceModels:
    if not (len(o_rows)==len(q_bits)==len(labels)) or not o_rows:
        raise RuntimeViolation("source FIT length mismatch")
    phi=protocol.fit_phi(o_rows)  # O* only, uniform preprocessing weights.
    transformed=protocol.transform_phi(phi,o_rows)
    weights=protocol.class_balance_weights(labels)  # strictly post-phi.
    full=_fit_linear_decoder([_decoder_features(r,b) for r,b in zip(transformed,q_bits)],labels,weights,cfg)
    pr=[]; py=[]; pw=[]
    for r,s,w in zip(transformed,labels,weights):
        pr += [_decoder_features(r,0),_decoder_features(r,1)]
        py += [s,s]; pw += [0.5*w,0.5*w]
    placebo=_fit_linear_decoder(pr,py,pw,cfg)
    payload={"u":u,"phi":phi.payload(),"full":{"w":full.weights,"b":full.bias},"placebo":{"w":placebo.weights,"b":placebo.bias},"cfg":dataclasses.asdict(cfg)}
    return FittedSourceModels(phi,full,placebo,u,sha256_json(payload))


def score_source_record(models: FittedSourceModels, o_star: Sequence[float], q: int, true_s: str) -> dict[str,Any]:
    z=protocol.transform_phi(models.phi,[o_star])[0]
    full_probs=models.full.p_q(_decoder_features(z,q))
    p0=models.placebo.p_q(_decoder_features(z,0)); p1=models.placebo.p_q(_decoder_features(z,1))
    fp={"p":full_probs[0],"q":full_probs[1]}; d0={"p":p0[0],"q":p0[1]}; d1={"p":p1[0],"q":p1[1]}
    full_label=protocol.hard_label(fp); placebo_label=protocol.placebo_hard_prediction(d0,d1)
    f_log=math.log(max(fp[true_s],1e-15)); p_log=protocol.placebo_log_score(math.log(max(d0[true_s],1e-15)),math.log(max(d1[true_s],1e-15)))
    return {
        "full_label":full_label,"placebo_label":placebo_label,
        "full_log":f_log,"placebo_log":p_log,"delta_log":f_log-p_log,
        "full_probabilities":fp,"placebo_p0":d0,"placebo_p1":d1,
        "placebo_mix":protocol.p_mix(d0,d1),
    }


@dataclass(frozen=True)
class ActuatorCandidateEvidence:
    block: int
    channel: int
    gain: float
    score_toward_p: float
    score_toward_q: float
    source_partition: str
    source_record_hash: str


def construct_payload_bank_fit_only(rows: Sequence[ActuatorCandidateEvidence]) -> tuple[protocol.PayloadManifest, protocol.PayloadManifest, dict[str,Any]]:
    if not rows:
        raise RuntimeViolation("FIT-only actuator evidence required")
    clean=[]
    for r in rows:
        if r.source_partition != "FIT":
            raise RuntimeViolation("payload banks may use FIT-only actuator evidence")
        if not isinstance(r.source_record_hash, str) or not r.source_record_hash:
            raise RuntimeViolation("FIT actuator evidence requires frozen source-record provenance")
        if r.gain not in protocol.ALLOWED_GAINS:
            raise RuntimeViolation("actuator gain outside frozen set")
        if not all(math.isfinite(x) for x in (r.score_toward_p,r.score_toward_q)):
            raise RuntimeViolation("nonfinite actuator evidence")
        clean.append(r)
    def select(field: str) -> tuple[protocol.PayloadTriple,...]:
        ranked=sorted(clean,key=lambda r:(-getattr(r,field),r.block,r.channel,r.gain))
        chosen=[]; seen=set()
        for r in ranked:
            key=(r.block,r.channel)
            if key in seen: continue
            seen.add(key); chosen.append(protocol.PayloadTriple(r.block,r.channel,r.gain))
            if len(chosen)==protocol.PAYLOAD_K: break
        if len(chosen)!=protocol.PAYLOAD_K: raise RuntimeViolation("payload constructibility failure")
        return tuple(chosen)
    cp=protocol.make_payload_manifest(select("score_toward_p")); cq=protocol.make_payload_manifest(select("score_toward_q"))
    if cp.triples==cq.triples: raise RuntimeViolation("payload bank must be structurally distinct")
    audit={"fit_only":True,"candidate_count":len(clean),"payload_p_checksum":cp.checksum,"payload_q_checksum":cq.checksum,"semantic_identity_serialized":False}
    return cp,cq,audit


def select_anonymous_payload(predicted_s: str, payload_for_p: protocol.PayloadManifest, payload_for_q: protocol.PayloadManifest) -> dict[str,Any]:
    selected=protocol.select_payload_from_observed_support(predicted_s,payload_for_p,payload_for_q,observed_support=True)
    data=selected.serialized_payload()
    text=stable_json(data)
    if any(token in text for token in ("C_p","C_q",'"name"','"predicted_s"')):
        raise RuntimeViolation("semantic identity leaked into applied payload")
    return data


def build_reset_applier_envelope(payload: Mapping[str,Any] | None, visible_context_hash: str, endpoint_manifest_hash: str) -> dict[str,Any]:
    if not visible_context_hash or not endpoint_manifest_hash:
        raise RuntimeViolation("arm-invariant visible context and opaque endpoint hashes required")
    arm="NO_CODEWORD" if payload is None else "PAYLOAD"
    body={"runtime_version":RUNTIME_VERSION,"arm":arm,"visible_context_hash":visible_context_hash,"endpoint_manifest_hash":endpoint_manifest_hash,"payload":None if payload is None else dict(payload)}
    # No donor/source/runtime semantic state is accepted by this API.
    return {**body,"envelope_hash":sha256_json(body)}


@dataclass(frozen=True)
class ExecutionFreeze:
    design_id: str
    semantic_hash: str
    runtime_version: str
    model_id: str
    model_revision: str
    model_dtype: str
    quantization: str
    task_split: str
    candidate_channel_algorithm: Mapping[str,Any]
    opaque_probe_algorithm: Mapping[str,Any]
    source_ablation_contract: Mapping[str,Any]
    payload_application_contract: Mapping[str,Any]
    endpoint_scoring_contract: Mapping[str,Any]
    runtime_packages: Mapping[str,Any]
    g_action: str
    t_float_format: str
    decoder: Mapping[str,Any]
    factor_contract: Mapping[str,Any]
    partition_contract: Mapping[str,Any]
    payload_contract: Mapping[str,Any]
    staged_execution_contract: Mapping[str,Any]
    protocol_sha256: str
    freeze_hash: str


def synthetic_runtime_freeze() -> tuple[ExecutionFreeze,dict[str,Any]]:
    protocol_byte_identity()
    cfg,decoder_canary=freeze_decoder_config()
    # Mechanics-only protocol canaries that do not touch real donor data.
    protocol_checks={
        "payload_anonymous_fields":sorted(f.name for f in dataclasses.fields(protocol.PayloadManifest))==["checksum","triples","version"],
        "protocol_canaries":run_all_protocol_canaries(cfg),
    }
    if not protocol_checks["payload_anonymous_fields"]: raise RuntimeViolation(f"protocol canary failure: {protocol_checks}")
    body={
        "design_id":DESIGN_ID,"semantic_hash":SEMANTIC_HASH,"runtime_version":RUNTIME_VERSION,
        "model_id":MODEL_ID,"model_revision":MODEL_REVISION,"model_dtype":MODEL_DTYPE,"quantization":MODEL_QUANTIZATION,"task_split":TASK_SPLIT,
        "candidate_channel_algorithm":{"method":"sha256-rank-over-all-block-intermediate-channels","count":CANDIDATE_CHANNEL_COUNT,"semantic_inputs":False},
        "opaque_probe_algorithm":{"method":"sha256-token-id-selection-without-decoding","count":OPAQUE_PROBE_COUNT,"semantic_inputs":False},
        "source_ablation_contract":{"site":"qwen-mlp-down_proj-input-post-gated-last-visible-token-v1","response":"baseline-minus-zero-ablation-next-token-logprob-over-opaque-probes-v1","tensor_order":"candidate-major/probe-major"},
        "payload_application_contract":{"site":"qwen-mlp-down_proj-input-post-gated-last-visible-token-v1","composition":"one-distinct-channel-per-payload;simultaneous-multiplicative-gain-v1","scope":"last-visible-context-token-only"},
        "endpoint_scoring_contract":{"method":"exact-prefix-suffix-logprob-sum-and-mean;choice-softmax-over-mean-v1","endpoint_ids":"opaque","semantic_orientation":"sealed-until-scores-freeze"},
        "runtime_packages":{"python_major_minor":"3.12","torch":"2.13.0+cu130","transformers":"4.51.3","tokenizers":"0.21.1"},
        "g_action":G_ACTION,"t_float_format":T_FLOAT_FORMAT,
        "decoder":{"family":cfg.family,"l2":cfg.l2,"lr":cfg.lr,"steps":cfg.steps,"config_hash":cfg.config_hash,"selection":"first-candidate-passing-synthetic-canaries-only"},
        "factor_contract":{"S":["p","q"],"A":[0,1],"H":[0,1],"M0":"pre-S exogenous mapping/surface-program id","U":"(A,H,M0)","sham":True,"washout":"equal-token-frozen"},
        "partition_contract":{"whole_B":True,"dependency_key_types":DEPENDENCY_KEY_TYPES,"FIT":12,"PILOT":8,"SUPPORT":12,"CROSS_REALIZATION_min":4,"CROSS_REALIZATION_selected":CROSS_REALIZATION_MIN,"response_conditioned_replacement":False},
        "payload_contract":{"K":protocol.PAYLOAD_K,"gains":protocol.ALLOWED_GAINS,"serialized_fields":["version","triples","checksum"],"bank_construction":"FIT-only"},
        "staged_execution_contract":{"PRE_SOURCE":"frame/probe/channel/decoder-config/fresh-TRAIN freeze before donor response","POST_FIT_HELDOUT":"phi/source-decoder/payload/reset hashes freeze using FIT only before SUPPORT/PILOT/CROSS_REALIZATION"},
        "protocol_sha256":PROTOCOL_SHA256,
    }
    freeze=ExecutionFreeze(**body,freeze_hash=sha256_json(body))
    return freeze,{"decoder_canary":decoder_canary,"protocol_checks":protocol_checks}



@dataclass(frozen=True)
class PreSourceManifestBinding:
    manifest_hash: str
    runtime_freeze_hash: str
    frame_hash: str
    dependency_hash: str
    probe_bank_hash: str
    candidate_channel_hash: str
    decoder_config_hash: str
    task_inventory_hash: str
    freshness_attestation_hash: str
    model_parameter_hash: str


@dataclass(frozen=True)
class PostFitManifestBinding:
    manifest_hash: str
    pre_source_manifest_hash: str
    source_model_bytes_hash: str
    decoder_bytes_hash: str
    phi_bytes_hash: str
    transformed_o_star_hash: str
    payload_bank_hash: str
    visible_context_manifest_hash: str
    endpoint_manifest_hash: str
    reset_attestation_hash: str
    model_parameter_hash: str


def _require_sha256(manifest: Mapping[str,Any], key: str) -> str:
    value=manifest.get(key)
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise RuntimeViolation(f"missing/invalid frozen hash: {key}")
    return value


def _assert_fresh_output(output_path: str | Path) -> None:
    path=Path(output_path)
    if path.exists():
        raise RuntimeViolation("real execution output namespace must be fresh")
    # A namespace under an existing parent is enough for preflight; no file is created here.
    if path.name in ("", ".", ".."):
        raise RuntimeViolation("invalid real execution output namespace")


def verify_pre_source_manifest(manifest: Mapping[str,Any], output_path: str | Path) -> PreSourceManifestBinding:
    """Validate the immutable boundary before the first real donor response is read.

    This stage deliberately cannot require FIT-derived source-model or payload-bank
    bytes.  Requiring those here would make the protocol circular.
    """
    freeze,_=synthetic_runtime_freeze()
    required={
        "phase":"PRE_SOURCE",
        "design_id":DESIGN_ID,"semantic_hash":SEMANTIC_HASH,"runtime_freeze_hash":freeze.freeze_hash,
        "model_id":MODEL_ID,"model_revision":MODEL_REVISION,"model_dtype":MODEL_DTYPE,
        "quantization":MODEL_QUANTIZATION,"task_split":TASK_SPLIT,
    }
    for key,value in required.items():
        if manifest.get(key)!=value:
            raise RuntimeViolation(f"pre-source manifest mismatch for {key}")
    if manifest.get("never_consumed_train_inventory") is not True:
        raise RuntimeViolation("pre-source manifest must attest fresh never-consumed TRAIN inventory")
    values={k:_require_sha256(manifest,k) for k in (
        "frame_hash","dependency_hash","probe_bank_hash","candidate_channel_hash",
        "decoder_config_hash","task_inventory_hash","freshness_attestation_hash","model_parameter_hash")}
    if values["decoder_config_hash"] != str(freeze.decoder["config_hash"]):
        raise RuntimeViolation("decoder config hash differs from synthetic-canary freeze")
    _assert_fresh_output(output_path)
    body={k:manifest[k] for k in sorted(manifest)}
    mh=sha256_json(body)
    return PreSourceManifestBinding(mh,freeze.freeze_hash,values["frame_hash"],values["dependency_hash"],
        values["probe_bank_hash"],values["candidate_channel_hash"],values["decoder_config_hash"],
        values["task_inventory_hash"],values["freshness_attestation_hash"],values["model_parameter_hash"])


def verify_post_fit_manifest(manifest: Mapping[str,Any], pre_source: PreSourceManifestBinding, output_path: str | Path) -> PostFitManifestBinding:
    """Validate the FIT-only freeze before SUPPORT/PILOT/CROSS_REALIZATION access."""
    required={"phase":"POST_FIT_HELDOUT","design_id":DESIGN_ID,"semantic_hash":SEMANTIC_HASH,
              "pre_source_manifest_hash":pre_source.manifest_hash}
    for key,value in required.items():
        if manifest.get(key)!=value:
            raise RuntimeViolation(f"post-FIT manifest mismatch for {key}")
    if manifest.get("fit_only_complete") is not True:
        raise RuntimeViolation("post-FIT freeze must attest FIT-only derivation")
    if manifest.get("heldout_partitions_unread_before_freeze") is not True:
        raise RuntimeViolation("held-out partitions must remain unread until FIT freeze")
    values={k:_require_sha256(manifest,k) for k in (
        "source_model_bytes_hash","decoder_bytes_hash","phi_bytes_hash","transformed_o_star_hash","payload_bank_hash",
        "visible_context_manifest_hash","endpoint_manifest_hash","reset_attestation_hash","model_parameter_hash")}
    if values["model_parameter_hash"] != pre_source.model_parameter_hash:
        raise RuntimeViolation("model parameter checksum changed between PRE_SOURCE and POST_FIT_HELDOUT")
    _assert_fresh_output(output_path)
    mh=sha256_json({k:manifest[k] for k in sorted(manifest)})
    return PostFitManifestBinding(mh,pre_source.manifest_hash,values["source_model_bytes_hash"],
        values["decoder_bytes_hash"],values["phi_bytes_hash"],values["transformed_o_star_hash"],values["payload_bank_hash"],values["visible_context_manifest_hash"],
        values["endpoint_manifest_hash"],values["reset_attestation_hash"],values["model_parameter_hash"])


def verify_frozen_real_manifest(manifest: Mapping[str,Any], output_path: str | Path) -> bool:
    """Compatibility validator: accept only an explicit staged manifest.

    PRE_SOURCE validates what can exist before donor responses. POST_FIT_HELDOUT
    requires an embedded ``pre_source`` manifest and then validates FIT-derived
    hashes before held-out access. No scientific execution occurs here.
    """
    phase=manifest.get("phase")
    if phase=="PRE_SOURCE":
        verify_pre_source_manifest(manifest,output_path)
        return True
    if phase=="POST_FIT_HELDOUT":
        raw=manifest.get("pre_source")
        if not isinstance(raw,Mapping):
            raise RuntimeViolation("POST_FIT_HELDOUT validation requires embedded pre_source manifest")
        pre=verify_pre_source_manifest(raw,output_path)
        verify_post_fit_manifest(manifest,pre,output_path)
        return True
    raise RuntimeViolation("real manifest phase must be PRE_SOURCE or POST_FIT_HELDOUT")


def _median(values: Sequence[float]) -> float:
    xs=sorted(float(x) for x in values)
    if not xs or any(not math.isfinite(x) for x in xs):
        raise RuntimeViolation("gate metric vector must be nonempty finite")
    n=len(xs)
    return xs[n//2] if n%2 else 0.5*(xs[n//2-1]+xs[n//2])


def _exact_bool(value: Any, name: str) -> bool:
    if value is not True and value is not False:
        raise RuntimeViolation(f"{name} must be an explicit boolean attestation")
    return bool(value)


def evaluate_source_gates(report: Mapping[str,Any]) -> dict[str,Any]:
    """Deterministically evaluate v7.9 G1-G12 without adding scientific thresholds."""
    support=list(report.get("support_blocks",()))
    pilot=list(report.get("pilot_blocks",()))
    per_u=[float(x) for x in report.get("constructible_u_deltas",())]
    canaries=report.get("canaries",{})
    if not isinstance(canaries,Mapping): raise RuntimeViolation("canaries must be a mapping")
    required_canaries=("positive","conditional_placebo","factorized_negative","label_permutation_preprocessing_invariance",
        "decoder_relative_common_transform_null","collapsed_symmetric_null_objective_equivalence","placebo_metric_reduction",
        "incompatible_nuisance_router","singleton_zero","off_support_toggle_boundary")
    canary_pass=all(canaries.get(k) is True for k in required_canaries)
    if len(support)!=12: raise RuntimeViolation("G7/G8 require exactly 12 fixed SUPPORT blocks")
    if len(pilot)!=8: raise RuntimeViolation("G9 requires exactly first 8 fixed PILOT blocks")
    sd=[float(x["delta_b"]) for x in support]; sb=[float(x["ba_increment"]) for x in support]
    pd=[float(x["delta_b"]) for x in pilot]; pba=[float(x["full_ba"]) for x in pilot]
    gates={
        "G1_preT_frame": _exact_bool(report.get("frame_frozen_pre_T"),"frame_frozen_pre_T") and _exact_bool(report.get("complete_cell_schedule"),"complete_cell_schedule") and not _exact_bool(report.get("response_derived_replacement"),"response_derived_replacement"),
        "G2_provenance": _exact_bool(report.get("only_U_external_router"),"only_U_external_router") and _exact_bool(report.get("forbidden_paths_unreachable"),"forbidden_paths_unreachable"),
        "G3_J_scope": _exact_bool(report.get("j_distribution_reported"),"j_distribution_reported") and _exact_bool(report.get("standardized_realized_j0_scope"),"standardized_realized_j0_scope") and _exact_bool(report.get("j1_member_contribution_zero"),"j1_member_contribution_zero"),
        "G4_label_blind_common_preprocessing": _exact_bool(report.get("uniform_preprocessing_weights"),"uniform_preprocessing_weights") and _exact_bool(report.get("label_permutation_invariant"),"label_permutation_invariant") and _exact_bool(report.get("full_placebo_transformed_o_star_hash_equal"),"full_placebo_transformed_o_star_hash_equal") and _exact_bool(report.get("bit_path_block_separable"),"bit_path_block_separable"),
        "G5_canaries": canary_pass,
        "G6_constructibility": _exact_bool(report.get("two_class_j0_constructible"),"two_class_j0_constructible"),
        "G7_fixed_support_replication": sum(x>0 for x in sd)>=10,
        "G8_support_size": _median(sd)>=0.02 and _median(sb)>=0.05,
        "G9_pilot_replication": sum(x>0 for x in pd)>=7 and _median(pd)>=0.015 and _median(pba)>=0.80,
        "G10_U_robustness": bool(per_u) and all(x>0 for x in per_u) and _exact_bool(report.get("u_only_baseline_cannot_explain"),"u_only_baseline_cannot_explain"),
        "G11_sham_specificity": _exact_bool(report.get("sham_specificity_pass"),"sham_specificity_pass"),
        "G12_observed_support_only": _exact_bool(report.get("all_selection_actual_supported_q"),"all_selection_actual_supported_q") and not _exact_bool(report.get("off_support_used_for_evidence_or_selection"),"off_support_used_for_evidence_or_selection"),
    }
    return {"gates":gates,"all_passed":all(gates.values()),"failures":[k for k,v in gates.items() if not v],
            "descriptive":{"support_delta_vector":sd,"support_ba_increment_vector":sb,"pilot_delta_vector":pd,"pilot_full_ba_vector":pba,"constructible_u_deltas":per_u}}


def evaluate_relay_gates(report: Mapping[str,Any]) -> dict[str,Any]:
    """Deterministically evaluate v7.9 G13-G20 on already frozen arm summaries."""
    cp=list(report.get("cp_vs_no_pilot",())); cq=list(report.get("cq_vs_no_pilot",()))
    sep=list(report.get("cp_vs_cq_directional_pilot",()))
    if len(cp)!=8 or len(cq)!=8 or len(sep)!=8:
        raise RuntimeViolation("G17/G18 require exactly first 8 fixed PILOT block aggregates")
    cp=[float(x) for x in cp]; cq=[float(x) for x in cq]; sep=[float(x) for x in sep]
    payload=report.get("applied_payload",{})
    if not isinstance(payload,Mapping): raise RuntimeViolation("applied_payload must be a mapping")
    triples=payload.get("triples",())
    payload_fields=set(payload)
    predicted=report.get("selected_payload_by_class",{})
    if not isinstance(predicted,Mapping): raise RuntimeViolation("selected_payload_by_class must be a mapping")
    def class_gate(label: str) -> bool:
        row=predicted.get(label,{})
        if not isinstance(row,Mapping): return False
        vals=[float(x) for x in row.get("block_shifts",())]
        blocks=int(row.get("block_count",0)); records=int(row.get("record_count",0))
        return blocks>=4 and len(vals)==blocks and records>=12 and bool(vals) and _median(vals)>=0.04 and sum(x>0 for x in vals)/len(vals)>=0.75
    cross=list(report.get("cross_realization",()))
    if len(cross)<4: cross_ok=False
    else:
        first4=cross[:4]
        cross_ok=(sum(bool(x.get("cp_correct")) for x in first4)>=3 and sum(bool(x.get("cq_correct")) for x in first4)>=3 and sum(bool(x.get("selected_correct")) for x in first4)>=3 and _exact_bool(report.get("endpoint_no_systematic_reversal"),"endpoint_no_systematic_reversal") and int(report.get("valid_action_worse_blocks",99))<=1)
    payload_valid=False
    if payload_fields=={"version","triples","checksum"} and isinstance(triples,(list,tuple)) and len(triples)==protocol.PAYLOAD_K:
        try:
            parsed=tuple(protocol.PayloadTriple(int(t[0]),int(t[1]),float(t[2])) for t in triples)
            rebuilt=protocol.make_payload_manifest(parsed,version=str(payload.get("version")))
            payload_valid=(rebuilt.checksum==payload.get("checksum"))
        except (TypeError,ValueError,IndexError,protocol.ProtocolViolation):
            payload_valid=False
    gates={
        "G13_bank_integrity": _exact_bool(report.get("bank_fit_only"),"bank_fit_only") and _exact_bool(report.get("bank_identical_budget"),"bank_identical_budget") and _exact_bool(report.get("bank_structurally_distinct"),"bank_structurally_distinct") and _exact_bool(report.get("bank_independent_of_later_information"),"bank_independent_of_later_information"),
        "G14_payload_purity": payload_valid,
        "G15_reset_provenance": _exact_bool(report.get("payload_sole_donor_object_after_reset"),"payload_sole_donor_object_after_reset") and _exact_bool(report.get("donor_state_unreachable"),"donor_state_unreachable") and _exact_bool(report.get("model_parameter_checksum_unchanged"),"model_parameter_checksum_unchanged") and _exact_bool(report.get("clean_cache_visible_context_identical"),"clean_cache_visible_context_identical"),
        "G16_blind_selection": _exact_bool(report.get("selection_is_f_U_phiO_Q_actual_support"),"selection_is_f_U_phiO_Q_actual_support") and _exact_bool(report.get("payload_frozen_before_evaluator_unseal"),"payload_frozen_before_evaluator_unseal") and _exact_bool(report.get("all_arm_scores_frozen_before_labels"),"all_arm_scores_frozen_before_labels"),
        "G17_bidirectional_payload_efficacy": sum(x>0 for x in cp)>=6 and _median([abs(x) for x in cp])>=0.05 and sum(x>0 for x in cq)>=6 and _median([abs(x) for x in cq])>=0.05,
        "G18_payload_identity_directionality": sum(x>0 for x in sep)>=6 and _median([abs(x) for x in sep])>=0.05 and _exact_bool(report.get("direction_survives_true_s_stratification"),"direction_survives_true_s_stratification"),
        "G19_selected_payload_relay": class_gate("p") and class_gate("q"),
        "G20_cross_realization": cross_ok,
    }
    return {"gates":gates,"all_passed":all(gates.values()),"failures":[k for k,v in gates.items() if not v],
            "descriptive":{"cp_vs_no_pilot":cp,"cq_vs_no_pilot":cq,"cp_vs_cq_directional_pilot":sep,"cross_realization_count":len(cross)}}


def evaluate_g1_g20(source_report: Mapping[str,Any], relay_report: Mapping[str,Any]) -> dict[str,Any]:
    source=evaluate_source_gates(source_report); relay=evaluate_relay_gates(relay_report)
    gates={**source["gates"],**relay["gates"]}
    if len(gates)!=20:
        raise RuntimeViolation(f"expected exactly G1-G20, got {len(gates)} gates")
    return {"kind":"PLANLATCH_V7_9_G1_G20_REPORT","gates":gates,"all_passed":all(gates.values()),
            "failures":[k for k,v in gates.items() if not v],"source_descriptive":source["descriptive"],"relay_descriptive":relay["descriptive"],
            "interpretation":"mechanical gate evaluation only; not scientific evidence until produced by an authorized inspected run"}

def _runtime_manifest_dict(freeze: ExecutionFreeze, audits: Mapping[str,Any]) -> dict[str,Any]:
    return {"kind":"PLANLATCH_V7_9_PRE_SCIENCE_RUNTIME_FREEZE_NOT_SCIENTIFIC_EVIDENCE","scientific_execution_performed":False,"model_or_environment_loaded":False,"freeze":dataclasses.asdict(freeze),"audits":dict(audits)}


def main(argv: Sequence[str] | None=None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--synthetic-canaries",action="store_true")
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--output")
    p.add_argument("--validate-real-manifest")
    p.add_argument("--real-output")
    p.add_argument("--allow-real-execution",action="store_true")
    args=p.parse_args(argv)
    if args.synthetic_canaries or args.preflight:
        freeze,audits=synthetic_runtime_freeze(); payload=_runtime_manifest_dict(freeze,audits)
        text=json.dumps(payload,sort_keys=True,indent=2)+"\n"
        if args.output:
            path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
        else: print(text,end="")
        return 0
    if args.validate_real_manifest:
        manifest=json.loads(Path(args.validate_real_manifest).read_text())
        if not args.real_output: raise RuntimeViolation("--real-output required")
        verify_frozen_real_manifest(manifest,args.real_output)
        print(stable_json({"real_manifest_valid":True,"scientific_execution_performed":False}))
        return 0
    if args.allow_real_execution:
        raise RuntimeViolation("real science requires a separately reviewed release candidate and ResearchDecision-bound execution wrapper; this pre-science implementation intentionally fails closed")
    raise RuntimeViolation("choose --synthetic-canaries/--preflight or --validate-real-manifest; real science is not authorized")

if __name__ == "__main__":
    raise SystemExit(main())
