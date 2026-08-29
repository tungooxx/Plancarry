from __future__ import annotations

import binascii
import hashlib
import json
import struct
import zlib
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

SCHEMA = "PLANCARRY_CPDS_ALFWORLD_STATIC_SOURCE_AUTHORITY_V1"
AUTHORIZED_PREFIX = ("json_2.1.1", "train")
REQUIRED_STATIC_GRAPH_FILES = ("game.tw-pddl", "initial_state.pddl", "traj_data.json")
FORBIDDEN_SPLIT_PARTS = frozenset({"valid_seen", "valid_unseen", "valid_train"})
FORBIDDEN_PROVENANCE_KEYS = frozenset({
    "behavioral_source_competence", "future_expert_trajectory", "future_oracle_trajectory",
    "future_success", "local_source_competence_preoutcome", "model_source_competence",
    "outcome_selected", "per_family_model_evaluability", "post_reset_arm_score",
    "post_reset_carrier_behavior", "realized_future_observations", "replacement_reason",
    "teacher_plan", "whole_task_success",
})


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _forbidden_key_scan(obj, where="$"):
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if k in FORBIDDEN_PROVENANCE_KEYS:
                raise ValueError(f"FORBIDDEN_PROVENANCE_KEY:{where}.{k}")
            _forbidden_key_scan(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _forbidden_key_scan(v, f"{where}[{i}]")


def train_relative_path(member_name: str) -> str:
    parts = PurePosixPath(member_name).parts
    if len(parts) < 3 or tuple(parts[:2]) != AUTHORIZED_PREFIX:
        raise ValueError("NOT_AUTHORIZED_TRAIN_MEMBER")
    if any(p in FORBIDDEN_SPLIT_PARTS for p in parts):
        raise ValueError("FORBIDDEN_SPLIT_MEMBER")
    rel = PurePosixPath(*parts[2:]).as_posix()
    if not rel or rel.startswith("../") or rel.startswith("/"):
        raise ValueError("BAD_TRAIN_RELATIVE_PATH")
    return rel


def validate_layout_asset(obj: Mapping) -> None:
    a = obj["asset"]
    entries = [e for e in obj["entries"] if not e["name"].endswith("/")]
    cd0, cd1 = a["central_directory_range"]
    e0, e1 = a["eocd_range"]
    if cd1 + 1 != e0 or e1 + 1 != a["size"]:
        raise ValueError("METADATA_GEOMETRY")
    if len(a["train_spans"]) < 1:
        raise ValueError("NO_TRAIN_SPAN")
    by_off = sorted(entries, key=lambda x: x["header_offset"])
    if len({e["header_offset"] for e in by_off}) != len(by_off):
        raise ValueError("DUPLICATE_HEADER_OFFSET")
    forbidden = []
    train_count = 0
    for e in by_off:
        if not (0 <= e["header_offset"] < e["record_end_exclusive"] <= cd0):
            raise ValueError("LOCAL_RECORD_GEOMETRY")
        try:
            train_relative_path(e["name"])
            auth = True
        except ValueError:
            auth = False
        if bool(e.get("authorized_train", False)) != auth:
            raise ValueError("AUTHORIZATION_CLASSIFICATION_DRIFT")
        if auth:
            train_count += 1
        else:
            forbidden.append((e["header_offset"], e["record_end_exclusive"]))
    if train_count != a["train_entry_count"]:
        raise ValueError("TRAIN_COUNT")
    for s, t, _n in a["train_spans"]:
        if not (0 <= s < t <= cd0):
            raise ValueError("TRAIN_SPAN_GEOMETRY")
        for fs, ft in forbidden:
            if max(s, fs) < min(t, ft):
                raise ValueError("TRAIN_SPAN_OVERLAPS_FORBIDDEN")


def validate_train_span_access(layout: Sequence[Mapping], access: Sequence[Mapping]) -> None:
    by_id = {x["asset"]["id"]: x for x in layout}
    if len(by_id) != len(layout) or len(access) != len(layout):
        raise ValueError("ACCESS_CARDINALITY")
    seen = set()
    for rec in access:
        aid = rec["asset_id"]
        if aid in seen or aid not in by_id:
            raise ValueError("ACCESS_IDENTITY")
        seen.add(aid)
        obj = by_id[aid]
        validate_layout_asset(obj)
        spans = obj["asset"]["train_spans"]
        if len(spans) != 1:
            raise ValueError("ACCESS_EXPECTED_ONE_SPAN")
        s, t, _ = spans[0]
        if rec["range_start"] != s or rec["range_end_inclusive"] != t - 1:
            raise ValueError("ACCESS_RANGE_DRIFT")
        if rec["bytes"] != t - s:
            raise ValueError("ACCESS_SIZE_DRIFT")
        if rec.get("forbidden_overlap_count") != 0:
            raise ValueError("ACCESS_FORBIDDEN_OVERLAP")
        if rec["etag"] != obj["asset"]["etag"]:
            raise ValueError("ACCESS_ETAG_DRIFT")
        if not isinstance(rec["sha256"], str) or len(rec["sha256"]) != 64:
            raise ValueError("ACCESS_SHA_FORMAT")


def _decode_member(segment: bytes, span_start: int, entry: Mapping) -> tuple[bytes, str]:
    off = entry["header_offset"] - span_start
    if off < 0 or off + 30 > len(segment):
        raise ValueError("LOCAL_HEADER_OUTSIDE_SPAN")
    vals = struct.unpack_from("<4s5H3L2H", segment, off)
    sig, vneed, flag, comp, mt, md, crc_local, csize_local, usize_local, nlen, xlen = vals
    if sig != b"PK\x03\x04":
        raise ValueError("LOCAL_HEADER_SIGNATURE")
    name_b = segment[off + 30: off + 30 + nlen]
    enc = "utf-8" if (flag & 0x800) else "cp437"
    name = name_b.decode(enc)
    if name != entry["name"]:
        raise ValueError("LOCAL_CENTRAL_NAME_MISMATCH")
    data_start = off + 30 + nlen + xlen
    csize = int(entry["compress_size"])
    if data_start + csize > len(segment):
        raise ValueError("COMPRESSED_BODY_OUTSIDE_SPAN")
    compressed = segment[data_start:data_start + csize]
    if int(entry["compress_type"]) == 0:
        raw = compressed
    elif int(entry["compress_type"]) == 8:
        raw = zlib.decompress(compressed, -15)
    else:
        raise ValueError("UNSUPPORTED_COMPRESSION")
    if len(raw) != int(entry["file_size"]):
        raise ValueError("UNCOMPRESSED_SIZE")
    if (binascii.crc32(raw) & 0xffffffff) != int(entry["crc32"], 16):
        raise ValueError("CRC32_MISMATCH")
    # When bit 3 is clear, local sizes/CRC must match too. With descriptors, central directory is authority.
    if not (flag & 0x8):
        if csize_local != csize or usize_local != len(raw) or crc_local != (binascii.crc32(raw) & 0xffffffff):
            raise ValueError("LOCAL_CENTRAL_SIZE_CRC_MISMATCH")
    return raw, name


def build_official_train_manifest(layout: Sequence[Mapping], access: Sequence[Mapping], segment_dir: Path, local_train_root: Path):
    validate_train_span_access(layout, access)
    access_by_id = {x["asset_id"]: x for x in access}
    records = []
    source_paths = set()
    for obj in sorted(layout, key=lambda x: x["asset"]["id"]):
        a = obj["asset"]
        aid = a["id"]
        rec = access_by_id[aid]
        seg_path = segment_dir / (a["name"] + ".train-span.bin")
        if not seg_path.is_file() or seg_path.stat().st_size != rec["bytes"] or sha256_file(seg_path) != rec["sha256"]:
            raise ValueError("TRAIN_SPAN_FILE_BINDING")
        segment = seg_path.read_bytes()
        s, t, _ = a["train_spans"][0]
        for e in sorted((x for x in obj["entries"] if x.get("authorized_train", False) and not x["name"].endswith("/")), key=lambda x: x["name"]):
            raw, name = _decode_member(segment, s, e)
            rel = train_relative_path(name)
            if rel in source_paths:
                raise ValueError("DUPLICATE_TRAIN_RELATIVE_PATH")
            source_paths.add(rel)
            lp = local_train_root / rel
            if not lp.is_file():
                raise ValueError("LOCAL_TRAIN_FILE_MISSING:" + rel)
            local_sha = sha256_file(lp)
            raw_sha = sha256_bytes(raw)
            if lp.stat().st_size != len(raw) or local_sha != raw_sha:
                raise ValueError("LOCAL_TRAIN_BYTE_MISMATCH:" + rel)
            records.append({
                "relative_path": rel,
                "byte_size": len(raw),
                "sha256": raw_sha,
                "source_asset_id": aid,
                "source_asset_name": a["name"],
                "source_member_name": name,
                "source_member_crc32": e["crc32"],
                "source_member_compress_size": e["compress_size"],
                "source_member_compress_type": e["compress_type"],
            })
    local_paths = {p.relative_to(local_train_root).as_posix() for p in local_train_root.rglob("*") if p.is_file()}
    if local_paths != source_paths:
        missing = sorted(source_paths - local_paths)[:10]
        extra = sorted(local_paths - source_paths)[:10]
        raise ValueError(f"LOCAL_TRAIN_TREE_SET_MISMATCH missing={missing} extra={extra}")
    records.sort(key=lambda x: x["relative_path"])
    if len({x["relative_path"] for x in records}) != len(records):
        raise ValueError("DUPLICATE_MANIFEST_PATH")
    return records


def complete_static_graph_units(records: Sequence[Mapping]):
    by_dir = {}
    for r in records:
        p = PurePosixPath(r["relative_path"])
        by_dir.setdefault(p.parent.as_posix(), set()).add(p.name)
    units = [d for d, names in by_dir.items() if set(REQUIRED_STATIC_GRAPH_FILES).issubset(names)]
    return sorted(units)


def build_authority_artifact(*, publisher_assets, package_provenance, layout, access, records, source_admission_refs):
    _forbidden_key_scan({"publisher_assets": publisher_assets, "package_provenance": package_provenance, "source_admission_refs": source_admission_refs})
    units = complete_static_graph_units(records)
    manifest_sha = sha256_bytes(canonical_bytes(records))
    units_sha = sha256_bytes(canonical_bytes(units))
    core = {
        "schema": SCHEMA,
        "scope": "OFFICIAL_ALFWORLD_TRAIN_STATIC_BYTES_ONLY",
        "source_admission_semantics": "STATIC_GRAPH_REPLAYABILITY_ONLY",
        "heldout_body_access": False,
        "whole_archive_body_access": False,
        "archive_level_sha256": None,
        "archive_level_sha256_reason": "INTENTIONALLY_NOT_COMPUTED_NO_FUTURE_SPLIT_ACCESS",
        "publisher_assets": publisher_assets,
        "package_provenance": package_provenance,
        "transport": {
            "metadata_only": "HEAD + exact EOCD last-22-byte range + exact central-directory range",
            "body_only": "exact coalesced local-record intervals whose member paths are under json_2.1.1/train/",
            "non_train_local_record_intervals": "FORBIDDEN",
            "range_server_requirement": "HTTP_206_WITH_EXACT_CONTENT_RANGE",
            "access_log": access,
        },
        "canonicalization": {
            "encoding": "UTF-8",
            "json": "sort_keys=True,separators=(comma,colon),ensure_ascii=False,newline_terminated=True",
            "file_order": "lexicographic relative_path",
            "relative_root": "json_2.1.1/train",
            "file_record_fields": ["relative_path", "byte_size", "sha256", "source_asset_id", "source_asset_name", "source_member_name", "source_member_crc32", "source_member_compress_size", "source_member_compress_type"],
        },
        "train_file_count": len(records),
        "train_file_manifest_sha256": manifest_sha,
        "static_graph_unit_rule": "trial relative directory containing all of game.tw-pddl, initial_state.pddl, traj_data.json; structural completeness only, no model/outcome admission",
        "static_graph_unit_count": len(units),
        "static_graph_unit_manifest_sha256": units_sha,
        "source_admission_refs": source_admission_refs,
        "future_snapshot_binding": {
            "envelope_schema": "PLANCARRY_CPDS_SOURCE_SNAPSHOT_PROVENANCE_ENVELOPE_V1",
            "required_fields": ["official_static_source_authority_sha256", "source_snapshot_sha256"],
            "rule": "future V2 replayability snapshot/witness bundle must be externally paired with this exact source-authority seal before certificate use; this source-authority freeze does not itself generate/select/sample families",
        },
        "scientific_result": "NOT_ASSESSED_PRE_SCIENCE_SOURCE_AUTHORITY_ONLY",
        "forbidden_actions_confirmed": ["NO_33X2_FAMILY_SELECTION", "NO_ASSIGNMENT_RANDOMNESS", "NO_MODEL", "NO_TOKENIZER", "NO_ENVIRONMENT_EXECUTION", "NO_GPU_PROVIDER", "NO_EXPERIMENT", "NO_PREDICTION", "NO_DECISION", "NO_ARM_OUTCOMES"],
    }
    _forbidden_key_scan(core)
    seal = sha256_bytes(canonical_bytes(core))
    return {**core, "official_static_source_authority_sha256": seal}, units


def verify_authority_artifact(artifact: Mapping, records: Sequence[Mapping], units: Sequence[str]) -> None:
    if artifact.get("schema") != SCHEMA:
        raise ValueError("AUTHORITY_SCHEMA")
    if artifact.get("source_admission_semantics") != "STATIC_GRAPH_REPLAYABILITY_ONLY":
        raise ValueError("SOURCE_ADMISSION_SEMANTICS")
    if artifact.get("heldout_body_access") is not False or artifact.get("whole_archive_body_access") is not False:
        raise ValueError("BODY_ACCESS_SCOPE")
    if artifact.get("archive_level_sha256") is not None:
        raise ValueError("WHOLE_ARCHIVE_HASH_FORBIDDEN")
    if artifact.get("train_file_manifest_sha256") != sha256_bytes(canonical_bytes(list(records))):
        raise ValueError("TRAIN_MANIFEST_SHA")
    if artifact.get("static_graph_unit_manifest_sha256") != sha256_bytes(canonical_bytes(list(units))):
        raise ValueError("UNIT_MANIFEST_SHA")
    if artifact.get("train_file_count") != len(records) or artifact.get("static_graph_unit_count") != len(units):
        raise ValueError("COUNT_BINDING")
    _forbidden_key_scan(artifact)
    x = dict(artifact); seal = x.pop("official_static_source_authority_sha256", None)
    if seal != sha256_bytes(canonical_bytes(x)):
        raise ValueError("SOURCE_AUTHORITY_SEAL")


def build_snapshot_provenance_envelope(source_authority_sha256: str, source_snapshot_sha256: str):
    for x in (source_authority_sha256, source_snapshot_sha256):
        if not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x):
            raise ValueError("SHA256_FORMAT")
    return {
        "schema": "PLANCARRY_CPDS_SOURCE_SNAPSHOT_PROVENANCE_ENVELOPE_V1",
        "official_static_source_authority_sha256": source_authority_sha256,
        "source_snapshot_sha256": source_snapshot_sha256,
    }
