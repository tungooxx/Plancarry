from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence

from cpds_v5_predictive_recurrence_v1 import BASE_MODEL_ID, BASE_MODEL_REVISION, REALIZATION, canonical_bytes

SEAL_SCHEMA = 'PLANCARRY_CPDS_V5_V4_RESERVED_STRUCTURAL_KEY_HASH_SEAL_V1'
CHECKPOINT_SCHEMA = 'PLANCARRY_CPDS_V5_DETERMINISTIC_CHECKPOINT_V1'
TRAIN_MANIFEST_SCHEMA = 'PLANCARRY_CPDS_V5_TRAIN_FREEZE_V1'


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def load_reserved_v4_hash_seal(path: str | Path | None, recipe: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if path is None:
        raise ValueError('V4_RESERVED_HASH_SEAL_REQUIRED')
    cfg = recipe.get('provenance', {}).get('v4_reserved_structural_key_hash_seal')
    if not isinstance(cfg, dict):
        raise ValueError('RECIPE_RESERVED_HASH_SEAL_BINDING')
    p = Path(path)
    actual_sha = sha256_file(p)
    if actual_sha != cfg.get('file_sha256'):
        raise ValueError('V4_RESERVED_HASH_SEAL_SHA')
    d = json.loads(p.read_text(encoding='utf-8'))
    if d.get('schema') != SEAL_SCHEMA or cfg.get('schema') != SEAL_SCHEMA:
        raise ValueError('V4_RESERVED_HASH_SEAL_SCHEMA')
    hashes = d.get('structural_family_key_sha256s')
    if not isinstance(hashes, list) or hashes != sorted(set(hashes)) or len(hashes) != int(cfg.get('count', -1)) or len(hashes) != 66:
        raise ValueError('V4_RESERVED_HASH_SEAL_CONTENT')
    if not all(_is_sha256(x) for x in hashes):
        raise ValueError('V4_RESERVED_HASH_SEAL_HASH_FORMAT')
    sm = d.get('source_manifests')
    if not isinstance(sm, dict):
        raise ValueError('V4_RESERVED_HASH_SEAL_SOURCE')
    if sm.get('development', {}).get('manifest_sha256') != cfg.get('development_manifest_sha256'):
        raise ValueError('V4_RESERVED_HASH_SEAL_DEV_MANIFEST')
    if sm.get('confirmation', {}).get('manifest_sha256') != cfg.get('confirmation_manifest_sha256'):
        raise ValueError('V4_RESERVED_HASH_SEAL_CONF_MANIFEST')
    return d, actual_sha


def build_train_provenance(packets: Sequence[Mapping[str, Any]], reserved_v4_hash_seal_sha256: str) -> dict[str, Any]:
    if not packets or not _is_sha256(reserved_v4_hash_seal_sha256):
        raise ValueError('TRAIN_PROVENANCE_INPUT')
    graph_ids = sorted(str(p['source_graph_id']) for p in packets)
    structural = sorted(str(p['structural_key_sha256']) for p in packets)
    if len(graph_ids) != len(set(graph_ids)) or len(structural) != len(set(structural)):
        raise ValueError('TRAIN_PROVENANCE_DUPLICATE')
    if not all(_is_sha256(x) for x in structural):
        raise ValueError('TRAIN_PROVENANCE_STRUCTURAL_HASH')
    return {'partition':'TRAIN','packet_count':len(packets),'source_graph_ids_sha256':_sha256_canonical(graph_ids),'structural_key_sha256s_sha256':_sha256_canonical(structural),'reserved_v4_hash_seal_sha256':reserved_v4_hash_seal_sha256}


def read_checkpoint_header(path: str | Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    if not _is_sha256(expected_sha256):
        raise ValueError('CHECKPOINT_EXPECTED_SHA')
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('CHECKPOINT_SHA')
    magic = b'CPDSV5CKPT1\n'
    if not raw.startswith(magic) or len(raw) < len(magic) + 8:
        raise ValueError('CHECKPOINT_MAGIC')
    off = len(magic)
    hlen = struct.unpack('<Q', raw[off:off+8])[0]; off += 8
    if hlen <= 0 or off + hlen > len(raw):
        raise ValueError('CHECKPOINT_HEADER_LENGTH')
    hb = raw[off:off+hlen]
    try:
        header = json.loads(hb)
    except Exception as e:
        raise ValueError('CHECKPOINT_HEADER_JSON') from e
    if header.get('schema') != CHECKPOINT_SCHEMA or header.get('realization') != REALIZATION:
        raise ValueError('CHECKPOINT_IDENTITY')
    if header.get('base_model_id') != BASE_MODEL_ID or header.get('base_model_revision') != BASE_MODEL_REVISION:
        raise ValueError('CHECKPOINT_BASE_MODEL')
    return header, hashlib.sha256(hb).hexdigest()


def validate_calibration_checkpoint_binding(*, checkpoint_path: str | Path, checkpoint_sha256: str, recipe_sha256: str, reserved_v4_hash_seal_sha256: str, train_manifest_path: str | Path, train_manifest_sha256: str) -> dict[str, Any]:
    if not all(_is_sha256(x) for x in (checkpoint_sha256, recipe_sha256, reserved_v4_hash_seal_sha256, train_manifest_sha256)):
        raise ValueError('CALIBRATION_PROVENANCE_SHA_FORMAT')
    mp = Path(train_manifest_path)
    if sha256_file(mp) != train_manifest_sha256:
        raise ValueError('TRAIN_MANIFEST_SHA')
    manifest = json.loads(mp.read_text(encoding='utf-8'))
    if manifest.get('schema') != TRAIN_MANIFEST_SCHEMA or manifest.get('scientific_result') != 'NOT_ASSESSED_TRAIN_ONLY':
        raise ValueError('TRAIN_MANIFEST_IDENTITY')
    if manifest.get('checkpoint_sha256') != checkpoint_sha256:
        raise ValueError('TRAIN_MANIFEST_CHECKPOINT_SHA')
    if manifest.get('recipe_sha256') != recipe_sha256:
        raise ValueError('TRAIN_MANIFEST_RECIPE_SHA')
    if manifest.get('reserved_v4_hash_seal_sha256') != reserved_v4_hash_seal_sha256:
        raise ValueError('TRAIN_MANIFEST_RESERVED_SEAL_SHA')
    header, header_sha = read_checkpoint_header(checkpoint_path, checkpoint_sha256)
    if manifest.get('checkpoint_header_sha256') != header_sha:
        raise ValueError('TRAIN_MANIFEST_CHECKPOINT_HEADER_SHA')
    if header.get('recipe_sha256') != recipe_sha256:
        raise ValueError('CHECKPOINT_RECIPE_SHA')
    train_prov = manifest.get('train_provenance')
    if not isinstance(train_prov, dict) or header.get('provenance') != train_prov:
        raise ValueError('TRAIN_MANIFEST_CHECKPOINT_PROVENANCE')
    if train_prov.get('partition') != 'TRAIN' or int(train_prov.get('packet_count', 0)) <= 0:
        raise ValueError('TRAIN_PROVENANCE_PARTITION')
    if train_prov.get('reserved_v4_hash_seal_sha256') != reserved_v4_hash_seal_sha256:
        raise ValueError('CHECKPOINT_RESERVED_SEAL_SHA')
    for key in ('source_graph_ids_sha256','structural_key_sha256s_sha256'):
        if not _is_sha256(train_prov.get(key)):
            raise ValueError('TRAIN_SOURCE_PROVENANCE_SHA')
    return {'train_manifest_sha256':train_manifest_sha256,'checkpoint_header_sha256':header_sha,'train_provenance':train_prov}
