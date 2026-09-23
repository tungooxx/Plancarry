"""PlanLatch v7.20 science adapter.

All accepted v7.9 scientific math is reused byte-identically from
planlatch_v7_9_runner/protocol.  Only the pre-response frame/router is replaced
so M0 is provenance-only and science routes on authenticated U*=(A,H,R).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Mapping, Sequence

import planlatch_v7_9_runner as v79
import planlatch_v7_20_controls as ctl

DESIGN_ID = ctl.DESIGN_ID
SEMANTIC_HASH = ctl.SEMANTIC_HASH
RUNNER_VERSION = "planlatch-v7.20-runner-adapter-v1"
PARTITION_COUNTS = v79.PARTITION_COUNTS
CROSS_REALIZATION_MIN = v79.CROSS_REALIZATION_MIN
DEPENDENCY_KEY_TYPES = v79.DEPENDENCY_KEY_TYPES
TASK_SPLIT = v79.TASK_SPLIT

# Exact inherited scientific primitives and constants.
RuntimeViolation = v79.RuntimeViolation
stable_json = v79.stable_json
sha256_json = v79.sha256_json
sha256_file = v79.sha256_file
OpaqueProbeBank = v79.OpaqueProbeBank
derive_opaque_probe_bank = v79.derive_opaque_probe_bank
ChannelCoordinate = v79.ChannelCoordinate
derive_candidate_channels = v79.derive_candidate_channels
serialize_t = v79.serialize_t
deserialize_t = v79.deserialize_t
apply_g = v79.apply_g
OrbitRecord = v79.OrbitRecord
canonicalize_response = v79.canonicalize_response
DecoderConfig = v79.DecoderConfig
LinearDecoder = v79.LinearDecoder
ActuatorCandidateEvidence = v79.ActuatorCandidateEvidence
construct_payload_bank_fit_only = v79.construct_payload_bank_fit_only
select_anonymous_payload = v79.select_anonymous_payload
build_reset_applier_envelope = v79.build_reset_applier_envelope
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
    candidate_universe_receipt_hash: str
    membership_receipt_hash: str
    model_parameter_hash: str
    execution_root_hash: str
    donor_program_hash: str
    washout_hash: str


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
_median = v79._median
evaluate_source_gates = v79.evaluate_source_gates
evaluate_relay_gates = v79.evaluate_relay_gates
evaluate_g1_g20 = v79.evaluate_g1_g20
run_all_protocol_canaries = v79.run_all_protocol_canaries
freeze_decoder_config = v79.freeze_decoder_config
FittedSourceModels = v79.FittedSourceModels
fit_source_models = v79.fit_source_models
score_source_record = v79.score_source_record

# Explicit inherited model-facing constants for exact science compatibility.
MODEL_ID = v79.MODEL_ID
MODEL_REVISION = v79.MODEL_REVISION
MODEL_DTYPE = v79.MODEL_DTYPE
MODEL_QUANTIZATION = v79.MODEL_QUANTIZATION
CANDIDATE_CHANNEL_COUNT = v79.CANDIDATE_CHANNEL_COUNT
DECODER_FAMILY = v79.DECODER_FAMILY
DECODER_TOLERANCE = v79.DECODER_TOLERANCE


@dataclass(frozen=True)
class BaseTaskMetadata:
    """One already-selected exact-body B entry as seen by the science layer.

    canonical identity, membership rank, selection key and receipt metadata are
    intentionally absent.  The binder supplies only an opaque block handle and
    the already-frozen partition.
    """
    opaque_block_handle: str
    m0: str
    r: ctl.CanonicalCoordinate
    partition: str
    split: str

    def __post_init__(self) -> None:
        if not self.opaque_block_handle or not self.m0:
            raise RuntimeViolation("opaque block handle and M0 provenance required")
        if self.partition not in dict(ctl.PARTITION_COUNTS):
            raise RuntimeViolation("invalid frozen partition")
        if self.split != TASK_SPLIT:
            raise RuntimeViolation("PlanLatch v7.20 accepts TRAIN split only")
        if self.r.name != "R" or self.r.producer_id != ctl.CANONICAL_PRODUCERS["R"]:
            raise RuntimeViolation("R must come from frozen canonical repeatable-orientation producer")
        if self.r.tainted_by_content:
            raise RuntimeViolation("R cannot be content/M0/identity tainted")


@dataclass(frozen=True)
class FrameCell:
    block_id: str  # opaque binder-only handle digest; not a science input
    partition: str
    s: str
    a: int
    h: int
    sham: bool
    u: tuple[int, int, int]
    cell_id: str  # binder/provenance only


@dataclass(frozen=True)
class FrameFreeze:
    block_ids: tuple[str, ...]
    partition_by_block: Mapping[str, str]
    cells: tuple[FrameCell, ...]
    frame_hash: str  # science-only hash: invariant to opaque-handle relabel
    binder_hash: str
    m0_provenance_hash: str


def _canonical_coord(name: str, value: int) -> ctl.CanonicalCoordinate:
    producer_id = ctl.CANONICAL_PRODUCERS[name]
    return ctl.CanonicalCoordinate(
        name=name,
        value=value,
        producer_id=producer_id,
        producer_sha256=ctl.sha256_json({"producer_id": producer_id, "version": 1}),
    )


def compile_pre_response_frame(tasks: Sequence[BaseTaskMetadata]) -> FrameFreeze:
    tasks = tuple(tasks)
    if len(tasks) != ctl.TOTAL_SELECTED:
        raise RuntimeViolation(f"v7.20 requires exactly {ctl.TOTAL_SELECTED} bound B entries")
    handles=[t.opaque_block_handle for t in tasks]
    if len(set(handles)) != len(handles):
        raise RuntimeViolation("duplicate opaque block handle")
    counts={name:sum(t.partition==name for t in tasks) for name,_ in ctl.PARTITION_COUNTS}
    if counts != dict(ctl.PARTITION_COUNTS):
        raise RuntimeViolation(f"frozen partition counts mismatch: {counts}")

    # Ordering is independent of canonical identity/rank/receipt metadata.
    # Within a partition, R is a scientific stratifier; equal-R B entries are
    # exchangeable and appear as repeated identical science payloads.
    porder={name:i for i,(name,_) in enumerate(ctl.PARTITION_COUNTS)}
    ordered=sorted(tasks,key=lambda t:(porder[t.partition],t.r.value,ctl.sha256_json({"opaque":t.opaque_block_handle})))
    block_ids=[]
    partition_by_block={}
    cells=[]
    science_rows=[]
    binder_rows=[]
    for t in ordered:
        bid="opaque-B-"+ctl.sha256_json({"handle":t.opaque_block_handle})[:20]
        block_ids.append(bid)
        partition_by_block[bid]=t.partition
        binder_rows.append({"block_id":bid,"partition":t.partition})
        for s_label in ("p","q"):
            for a_bit in (0,1):
                for h_bit in (0,1):
                    for sham in (False,True):
                        a=_canonical_coord("A",a_bit)
                        h=_canonical_coord("H",h_bit)
                        u=ctl.authenticated_u_star(a,h,t.r)
                        science_payload={
                            "partition":t.partition,"s":s_label,"a":a_bit,
                            "h":h_bit,"r":t.r.value,"sham":sham,
                        }
                        cell_id="v720-cell-"+ctl.sha256_json({"binder":bid,**science_payload})[:24]
                        cells.append(FrameCell(bid,t.partition,s_label,a_bit,h_bit,sham,u,cell_id))
                        science_rows.append(science_payload)

    # Science hash excludes all binder/identity/M0/receipt material.
    science_rows.sort(key=ctl.stable_json)
    frame_hash=ctl.sha256_json(science_rows)
    binder_hash=ctl.sha256_json(sorted(binder_rows,key=ctl.stable_json))
    m0_prov=ctl.sha256_json(sorted(
        [{"opaque_block":ctl.sha256_json({"h":t.opaque_block_handle}),"m0_provenance_sha256":ctl.sha256_json({"m0":t.m0})} for t in tasks],
        key=ctl.stable_json,
    ))
    return FrameFreeze(tuple(block_ids),partition_by_block,tuple(cells),frame_hash,binder_hash,m0_prov)


def verify_complete_cells(frame: FrameFreeze) -> bool:
    by_block: dict[str,set[tuple[str,int,int,bool]]] = {}
    for c in frame.cells:
        by_block.setdefault(c.block_id,set()).add((c.s,c.a,c.h,c.sham))
    expected={(s,a,h,sham) for s in ("p","q") for a in (0,1) for h in (0,1) for sham in (False,True)}
    if len(by_block)!=ctl.TOTAL_SELECTED or any(v!=expected for v in by_block.values()):
        raise RuntimeViolation("incomplete exact36 SxAxH+sham schedule")
    return True


@dataclass(frozen=True)
class ExecutionFreeze:
    freeze_hash: str
    factor_contract: Mapping[str, object]
    partition_contract: Mapping[str, object]
    inherited_v79_freeze_hash: str


def synthetic_runtime_freeze() -> tuple[ExecutionFreeze, dict[str, object]]:
    """Metadata-only pre-science freeze; does not execute NumPy/model canaries."""
    inherited_hashes={
        "protocol_sha256": v79.sha256_file("planlatch_v7_9_protocol.py"),
        "runner_sha256": v79.sha256_file("planlatch_v7_9_runner.py"),
        "model_runtime_sha256": v79.sha256_file("planlatch_v7_9_model_runtime.py"),
    }
    inherited_identity=ctl.sha256_json({
        "model_id":MODEL_ID,
        "model_revision":MODEL_REVISION,
        "model_dtype":MODEL_DTYPE,
        "model_quantization":MODEL_QUANTIZATION,
        "files":inherited_hashes,
        "decoder_family":DECODER_FAMILY,
    })
    factor={
        "S":["p","q"],"A":[0,1],"H":[0,1],"R":[0,1],
        "M0":"provenance-only; forbidden from scientific routing",
        "U*":"(A,H,R)","sham":True,"washout":"equal-token-frozen",
    }
    partition={
        "whole_B":True,"FIT":12,"PILOT":8,"SUPPORT":12,"CROSS_REALIZATION":4,
        "response_conditioned_replacement":False,
    }
    payload={
        "version":RUNNER_VERSION,"design_id":DESIGN_ID,"semantic_hash":SEMANTIC_HASH,
        "factor_contract":factor,"partition_contract":partition,
        "inherited_v79_byte_identity":inherited_identity,
        "inherited_v79_files":inherited_hashes,
        "scientific_canaries_required_at_exact_runtime_preflight":True,
    }
    return ExecutionFreeze(ctl.sha256_json(payload),factor,partition,inherited_identity),payload


@dataclass(frozen=True)
class PreSourceManifestBinding:
    manifest_hash: str
    model_parameter_hash: str
    runtime_fingerprint: str
    universe_receipt_hash: str
    implementation_fingerprint: str


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


def _require_sha(manifest: Mapping[str, object], key: str) -> str:
    value=manifest.get(key)
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
        raise RuntimeViolation(f"{key} must be lowercase sha256")
    return value


def _assert_fresh_output(output_path: str | object) -> None:
    from pathlib import Path
    if Path(output_path).exists():
        raise RuntimeViolation("output namespace must be fresh")


def verify_pre_source_manifest(manifest: Mapping[str, object], output_path: str | object) -> PreSourceManifestBinding:
    """v7.20 pre-source freeze: fixed-subject only; no global freshness claim."""
    _assert_fresh_output(output_path)
    required={
        "phase":"PRE_SOURCE",
        "design_id":DESIGN_ID,
        "semantic_hash":SEMANTIC_HASH,
        "task_split":TASK_SPLIT,
        "u_star":"(A,H,R)",
        "m0_scientific_role":"provenance-only",
        "exact36":True,
        "partition_counts":{"FIT":12,"PILOT":8,"SUPPORT":12,"CROSS_REALIZATION":4},
        "response_conditioned_replacement":False,
    }
    for k,v in required.items():
        if manifest.get(k)!=v:
            raise RuntimeViolation(f"v7.20 pre-source manifest mismatch for {k}")
    forbidden=("never_consumed_train_inventory","global_freshness","project_history_unseen","candidate_pool_freshness")
    if any(k in manifest for k in forbidden):
        raise RuntimeViolation("v7.20 manifest must not assert global/project-history freshness")
    hashes={k:_require_sha(manifest,k) for k in (
        "runtime_freeze_hash","frame_hash","binder_hash","decoder_config_hash",
        "task_inventory_hash","model_parameter_hash","execution_root_hash","donor_program_hash",
        "washout_hash","runtime_fingerprint","universe_receipt_hash","implementation_fingerprint",
    )}
    mh=ctl.sha256_json({k:manifest[k] for k in sorted(manifest)})
    return PreSourceManifestBinding(
        mh,hashes["model_parameter_hash"],hashes["runtime_fingerprint"],
        hashes["universe_receipt_hash"],hashes["implementation_fingerprint"]
    )


def verify_post_fit_manifest(manifest: Mapping[str, object], pre_source: PreSourceManifestBinding, output_path: str | object) -> PostFitManifestBinding:
    required={
        "phase":"POST_FIT_HELDOUT",
        "design_id":DESIGN_ID,
        "semantic_hash":SEMANTIC_HASH,
        "pre_source_manifest_hash":pre_source.manifest_hash,
        "fit_only_complete":True,
        "heldout_partitions_unread_before_freeze":True,
    }
    for k,v in required.items():
        if manifest.get(k)!=v:
            raise RuntimeViolation(f"v7.20 post-FIT manifest mismatch for {k}")
    vals={k:_require_sha(manifest,k) for k in (
        "source_model_bytes_hash","decoder_bytes_hash","phi_bytes_hash","transformed_o_star_hash",
        "payload_bank_hash","visible_context_manifest_hash","endpoint_manifest_hash",
        "reset_attestation_hash","model_parameter_hash",
    )}
    if vals["model_parameter_hash"]!=pre_source.model_parameter_hash:
        raise RuntimeViolation("model parameter checksum changed between PRE_SOURCE and POST_FIT_HELDOUT")
    mh=ctl.sha256_json({k:manifest[k] for k in sorted(manifest)})
    return PostFitManifestBinding(
        mh,pre_source.manifest_hash,vals["source_model_bytes_hash"],vals["decoder_bytes_hash"],
        vals["phi_bytes_hash"],vals["transformed_o_star_hash"],vals["payload_bank_hash"],
        vals["visible_context_manifest_hash"],vals["endpoint_manifest_hash"],
        vals["reset_attestation_hash"],vals["model_parameter_hash"]
    )


def verify_frozen_real_manifest(manifest: Mapping[str, object], output_path: str | object) -> bool:
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
    raise RuntimeViolation("v7.20 real manifest phase must be PRE_SOURCE or POST_FIT_HELDOUT")


def protocol_byte_identity(root: str = ".") -> bool:
    return v79.protocol_byte_identity(root)
