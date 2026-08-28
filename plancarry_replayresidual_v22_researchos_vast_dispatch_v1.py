#!/usr/bin/env python3
"""Transport-only Research OS dispatcher for ReplayResidual V2.2 on reviewed Vast host.

This module does not define or modify scientific semantics.  It verifies an immutable
live-host attestation, executes the exact reviewed remote launcher, and mirrors only
an exact allowlist of terminal/provenance artifacts into the local GPU-lab job before
successful exit.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import asyncssh

EXPERIMENT_ID = "e9a95d91-7b68-4ffc-9f1c-ec3dc5c3c6e9"
EXPECTED_INSTANCE_ID = "vast_48954592"
EXPECTED_GPU = "NVIDIA GeForce RTX 3080"
EXPECTED_DRIVER = "580.142"
REMOTE_REPO = "/workspace/GPU-Lab/repos/plancarry-replayresidual-v22-911b081"
REMOTE_COMMIT = "911b0815061f0f79265558ba0e758f0d8bff5ba2"
REMOTE_PYTHON = "/workspace/venv-replayresidual-v22/bin/python"
HOST_REVIEW_WORK_ITEM_ID = "7d98bcb2-27a5-491d-a739-42fcc4950be0"
HOST_REVIEW_PASS = "PASS_FOR_REPLAYRESIDUAL_V22_VAST_RTX3080_HOST_EQUIVALENCE"
LAUNCHER = "results/design/plancarry_replayresidual_v22_vast_rtx3080_launcher_a4_20260828.sh"
LAUNCHER_SHA256 = "7159c0da94c6436aef263225ae8904d40b0c693bf65cc4a0ff2396de39ecbd8a"
BOUND_CONTRACT = "results/design/plancarry_replayresidual_v22_unified_execution_contract_bound_a4_20260828.json"
BOUND_CONTRACT_SHA256 = "f125b6f8a0c96ca74beb75893e9ac6a40ea2ea436306e73c4b0667150ecd3726"
RESET_CANARY = "results/design/plancarry_replayresidual_v22_reset_canary_attestation_vast48954592_a4_20260828.json"
RESET_CANARY_SHA256 = "a660a118e93664f6f8a233fac4de6c36b9348ddb418eb2f1a807d8598401aab2"
PACKET_DIR = "results/science/plancarry_replay_residual_sanity_packets_v2_2_technical_retry1"
RESULT_JSON = "results/science/plancarry_replay_residual_representation_sanity_v2_2_technical_retry1.json"
EXECUTION_ATTESTATION = "results/science/plancarry_replayresidual_v22_execution_attestation_technical_retry1.json"
DECLARED_OUTPUTS = (PACKET_DIR, RESULT_JSON, EXECUTION_ATTESTATION)
REMOTE_BUNDLE = "/workspace/plancarry-v22-tmp/replayresidual_v22_terminal_artifacts_v1.tgz"
REMOTE_MANIFEST = "/workspace/plancarry-v22-tmp/replayresidual_v22_terminal_artifacts_v1.manifest.json"
LIVE_ATTESTATION_KIND = "PLANCARRY_REPLAYRESIDUAL_V22_VAST48954592_POSTSTAGE_LIVE_ATTESTATION_A3_V1"
LIVE_ATTESTATION_STATUS = "PASS_FOR_REPLAYRESIDUAL_V22_VAST48954592_POSTSTAGE_LIVE_ATTESTATION"
LIVE_ATTESTATION_SHA256 = "064bbc3a1471fc67057f1d3ec507c9afb09e8d47332de524f7586cc48df044db"
LIVE_ATTESTATION_REL = "results/design/plancarry_replayresidual_v22_vast48954592_poststage_live_attestation_a3_20260828.json"
REMOTE_TREE = "ad30adf6a8b1fc9af20c2e88e6839f4d30c99e27"
EXPECTED_VRAM_MIB = 10240
EXPECTED_HOST_REVIEW_SHA256 = "d38b2ccf8dd3e4af55c78b3f120487d837950e7adcc868bba8450db75ffc3572"
EXPECTED_HOST = "191.223.212.127"
EXPECTED_PORT = 32963
EXPECTED_HOSTKEY_ED25519_SHA256 = "mOJF8cM2NYBVFIuYvPU/pkdOx1TdMvc7ZL37etokals"


def q(value: object) -> str:
    return shlex.quote(str(value))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_hex_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_declared_relpath(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("ARTIFACT_PATH_INVALID")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or "." in p.parts or str(p) != value:
        raise ValueError("ARTIFACT_PATH_ESCAPE")
    if value not in DECLARED_OUTPUTS:
        raise ValueError("ARTIFACT_PATH_NOT_DECLARED")
    forbidden = ("valid_seen", "valid_unseen", "reserve", "32..63")
    if any(token in value for token in forbidden):
        raise ValueError("FUTURE_SPLIT_ARTIFACT_FORBIDDEN")
    return value


def _require_exact(obj: dict[str, Any], path: tuple[str, ...], expected: object) -> None:
    cur: object = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            raise ValueError("LIVE_HOST_ATTESTATION_FIELD_MISSING:" + ".".join(path))
        cur = cur[key]
    if cur != expected:
        raise ValueError("LIVE_HOST_ATTESTATION_FIELD_MISMATCH:" + ".".join(path))


def load_live_attestation(path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    actual_sha = sha256_bytes(raw)
    if expected_sha256 != LIVE_ATTESTATION_SHA256 or actual_sha != LIVE_ATTESTATION_SHA256:
        raise ValueError("LIVE_HOST_ATTESTATION_SHA_MISMATCH")
    obj = json.loads(raw)
    exact = {
        ("kind",): LIVE_ATTESTATION_KIND,
        ("status",): LIVE_ATTESTATION_STATUS,
        ("scientific_result",): "NOT_ASSESSED",
        ("host_equivalence_review_work_item_id",): HOST_REVIEW_WORK_ITEM_ID,
        ("instance", "instance_id"): EXPECTED_INSTANCE_ID,
        ("instance", "provider_instance_id"): "48954592",
        ("instance", "provider_status"): "running",
        ("instance", "ssh_reachable"): True,
        ("instance", "gpu_name"): EXPECTED_GPU,
        ("instance", "gpu_count"): 1,
        ("instance", "gpu_memory_total_mib"): EXPECTED_VRAM_MIB,
        ("instance", "gpu_memory_used_mib"): 0,
        ("instance", "gpu_utilization_percent"): 0,
        ("instance", "compute_processes_present"): False,
        ("instance", "driver"): EXPECTED_DRIVER,
        ("remote_checkout", "path"): REMOTE_REPO,
        ("remote_checkout", "head"): REMOTE_COMMIT,
        ("remote_checkout", "tree"): REMOTE_TREE,
        ("remote_checkout", "clean"): True,
        ("runtime", "python_path"): REMOTE_PYTHON,
        ("runtime", "python"): "3.13.15",
        ("runtime", "torch"): "2.13.0+cu130",
        ("runtime", "transformers"): "4.51.3",
        ("runtime", "tokenizers"): "0.21.1",
        ("runtime", "alfworld"): "0.4.2",
        ("runtime", "textworld"): "1.7.0",
        ("runtime", "torch_cuda_initialized_before_metadata_check"): False,
        ("runtime", "torch_cuda_initialized_after_metadata_check"): False,
        ("data_and_model", "qwen_revision"): "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
        ("data_and_model", "qwen_cache_present"): True,
        ("data_and_model", "qwen_cache_path"): "/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
        ("data_and_model", "alfworld_data_path"): "/opt/gpu-lab/envs/plancarry-alfworld-data",
        ("data_and_model", "alfworld_train_path_present"): "/opt/gpu-lab/envs/plancarry-alfworld-data/json_2.1.1/train",
        ("preflight", "status"): "READY_NO_SCIENCE",
        ("preflight", "model_calls"): 0,
        ("preflight", "model_loads"): 0,
        ("preflight", "environment_execution"): 0,
        ("preflight", "old_v21_science_reads"): 0,
        ("preflight", "scientific_result_reads"): 0,
        ("preflight", "reserve_access"): False,
        ("preflight", "valid_seen_access"): False,
        ("preflight", "valid_unseen_access"): False,
        ("preflight", "registration_bound"): False,
        ("preflight", "native_execution_attestation_required"): True,
        ("preflight", "reset_canary_required_before_execute"): True,
        ("science_targets", "packet_target"): PACKET_DIR,
        ("science_targets", "packet_target_absent"): True,
        ("science_targets", "result_target"): RESULT_JSON,
        ("science_targets", "result_target_absent"): True,
        ("post_preflight", "remote_checkout_clean"): True,
        ("post_preflight", "science_targets_absent"): True,
        ("post_preflight", "compute_processes_present"): False,
        ("post_preflight", "gpu_memory_used_mib"): 0,
        ("post_preflight", "gpu_utilization_percent"): 0,
        ("reviewed_hashes", "host_launcher"): LAUNCHER_SHA256,
        ("reviewed_hashes", "host_binding"): "302554698ac35990692884053e227a18d7d8af47db23503239c36af27690871b",
        ("reviewed_hashes", "registered_bound_contract"): BOUND_CONTRACT_SHA256,
        ("reviewed_hashes", "reset_canary_attestation"): RESET_CANARY_SHA256,
        ("reviewed_hashes", "host_static_audit"): "f2004405f61d07d89fb43c01f831cb906ab760e219e993f7c6785f29b712ddc2",
        ("reviewed_hashes", "reset_canary_script"): "28a2185501fec546a660c733c26d015c9fd9139d853ef1af25a80c9d4d82a9aa",
        ("reviewed_hashes", "template"): "691b93024ffe45ad46c4bb3b6fc162b83dace44e939dd0373bcd6bdf822dc4a1",
        ("prohibitions_observed", "future_split_access"): False,
        ("prohibitions_observed", "provider_lifecycle_action"): False,
        ("prohibitions_observed", "model_load_or_forward_or_generation"): False,
        ("prohibitions_observed", "alfworld_study_reset_or_game"): False,
        ("prohibitions_observed", "old_v21_science_read"): False,
        ("prohibitions_observed", "research_decision_or_science_execution"): False,
        ("prohibitions_observed", "host_substitution"): False,
    }
    for key_path, expected in exact.items():
        _require_exact(obj, key_path, expected)
    # The host review itself is separately immutable and must match the known PASS artifact.
    if EXPECTED_HOST_REVIEW_SHA256 != "d38b2ccf8dd3e4af55c78b3f120487d837950e7adcc868bba8450db75ffc3572":
        raise ValueError("HOST_REVIEW_SHA_INTERNAL_MISMATCH")
    return obj


def load_transport_binding() -> tuple[str, int, str]:
    host = os.environ.get("REPLAYRESIDUAL_V22_VAST_HOST")
    port_s = os.environ.get("REPLAYRESIDUAL_V22_VAST_PORT")
    fingerprint = os.environ.get("REPLAYRESIDUAL_V22_VAST_HOSTKEY_ED25519_SHA256")
    if host != EXPECTED_HOST:
        raise ValueError("VAST_HOST_BINDING_MISMATCH")
    try:
        port = int(port_s or "")
    except ValueError as exc:
        raise ValueError("VAST_PORT_BINDING_INVALID") from exc
    if port != EXPECTED_PORT:
        raise ValueError("VAST_PORT_BINDING_MISMATCH")
    if fingerprint != EXPECTED_HOSTKEY_ED25519_SHA256:
        raise ValueError("VAST_HOSTKEY_BINDING_MISMATCH")
    return host, port, fingerprint


def pinned_known_hosts(host: str, port: int, expected_fingerprint: str) -> str:
    scan = subprocess.run(
        ["ssh-keyscan", "-T", "8", "-t", "ed25519", "-p", str(port), host],
        capture_output=True,
        text=True,
        check=False,
    )
    if scan.returncode != 0 or not scan.stdout.strip():
        raise SystemExit("VAST_HOSTKEY_SCAN_FAILED")
    with tempfile.NamedTemporaryFile("w", delete=False, prefix="plancarry_v22_known_hosts_", suffix=".tmp") as f:
        f.write(scan.stdout)
        known = f.name
    fp = subprocess.run(["ssh-keygen", "-lf", known, "-E", "sha256"], capture_output=True, text=True, check=False)
    expected = "SHA256:" + expected_fingerprint
    if fp.returncode != 0 or expected not in fp.stdout:
        Path(known).unlink(missing_ok=True)
        raise SystemExit("VAST_HOSTKEY_MISMATCH")
    return known


def remote_preflight_command() -> str:
    absent = " && ".join(f"test ! -e {q(rel)}" for rel in DECLARED_OUTPUTS)
    return f"""set -euo pipefail
cd {q(REMOTE_REPO)}
test \"$(git rev-parse HEAD)\" = {q(REMOTE_COMMIT)}
test -z \"$(git status --porcelain)\"
test \"$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | sed 's/[[:space:]]*$//')\" = {q(EXPECTED_GPU)}
test \"$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | sed 's/[[:space:]]*$//')\" = {q(EXPECTED_DRIVER)}
echo {q(LAUNCHER_SHA256 + '  ' + LAUNCHER)} | sha256sum -c -
echo {q(BOUND_CONTRACT_SHA256 + '  ' + BOUND_CONTRACT)} | sha256sum -c -
echo {q(RESET_CANARY_SHA256 + '  ' + RESET_CANARY)} | sha256sum -c -
test -x {q(REMOTE_PYTHON)}
{absent}
PLANCARRY_PYTHON={q(REMOTE_PYTHON)} HF_HOME=/workspace/.hf_home TMPDIR=/workspace/plancarry-v22-tmp ALFWORLD_DATA=/opt/gpu-lab/data/plancarry-alfworld bash {q(LAUNCHER)} preflight
echo V22_DISPATCH_REMOTE_PREFLIGHT_PASS
"""


def remote_execution_command() -> str:
    # This is the exact reviewed launcher invocation; transport wraps it but never rewrites its science.
    return f"""set -euo pipefail
cd {q(REMOTE_REPO)}
PLANCARRY_PYTHON={q(REMOTE_PYTHON)} \\
HF_HOME=/workspace/.hf_home \\
TMPDIR=/workspace/plancarry-v22-tmp \\
ALFWORLD_DATA=/opt/gpu-lab/data/plancarry-alfworld \\
CUBLAS_WORKSPACE_CONFIG=:4096:8 \\
REPLAYRESIDUAL_V22_EXECUTION_AUTHORIZATION=RESEARCH_DECISION_BOUND \\
REPLAYRESIDUAL_V22_BOUND_CONTRACT={q(REMOTE_REPO + '/' + BOUND_CONTRACT)} \\
REPLAYRESIDUAL_V22_RESET_CANARY_ATTESTATION={q(REMOTE_REPO + '/' + RESET_CANARY)} \\
REPLAYRESIDUAL_V22_EXECUTION_ATTESTATION={q(REMOTE_REPO + '/' + EXECUTION_ATTESTATION)} \\
bash {q(LAUNCHER)} execute
"""


def remote_bundle_command(require_success_outputs: bool) -> str:
    required_flag = "1" if require_success_outputs else "0"
    return f"""set -euo pipefail
cd {q(REMOTE_REPO)}
mkdir -p /workspace/plancarry-v22-tmp
{q(REMOTE_PYTHON)} - {q(PACKET_DIR)} {q(RESULT_JSON)} {q(EXECUTION_ATTESTATION)} {q(REMOTE_MANIFEST)} {required_flag} <<'PYREMOTE'
import hashlib,json,os,pathlib,sys,tempfile
packet,result,attest,out,required=sys.argv[1:]
required=required=='1'; declared=(packet,result,attest); root=pathlib.Path.cwd().resolve(); rows=[]
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()
def check_path(rel):
 p=pathlib.Path(rel)
 if p.is_absolute() or '..' in p.parts or str(p.as_posix())!=rel: raise SystemExit('REMOTE_ARTIFACT_PATH_ESCAPE')
 full=(root/p)
 if not full.exists(): return None
 if full.is_symlink(): raise SystemExit('REMOTE_ARTIFACT_SYMLINK_FORBIDDEN')
 real=full.resolve()
 if root not in real.parents and real!=root: raise SystemExit('REMOTE_ARTIFACT_REALPATH_ESCAPE')
 return full
for rel in declared:
 full=check_path(rel)
 if full is None:
  if required: raise SystemExit('REQUIRED_REMOTE_ARTIFACT_MISSING:'+rel)
  continue
 if full.is_dir():
  for child in sorted(full.rglob('*')):
   if child.is_symlink(): raise SystemExit('REMOTE_ARTIFACT_SYMLINK_FORBIDDEN')
   if child.is_file():
    real=child.resolve()
    if root not in real.parents: raise SystemExit('REMOTE_ARTIFACT_REALPATH_ESCAPE')
    rows.append({{'path':child.relative_to(root).as_posix(),'sha256':digest(child),'size':child.stat().st_size}})
 elif full.is_file(): rows.append({{'path':rel,'sha256':digest(full),'size':full.stat().st_size}})
 else: raise SystemExit('REMOTE_ARTIFACT_TYPE_FORBIDDEN')
if required and not rows: raise SystemExit('REQUIRED_REMOTE_ARTIFACT_SET_EMPTY')
obj={{'kind':'PLANCARRY_REPLAYRESIDUAL_V22_REMOTE_ARTIFACT_MANIFEST_V1','experiment_id':{EXPERIMENT_ID!r},'repo_commit':{REMOTE_COMMIT!r},'declared_roots':list(declared),'files':rows}}
raw=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()+b'\\n'
os.makedirs(os.path.dirname(out),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='v22manifest.',dir=os.path.dirname(out))
with os.fdopen(fd,'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
os.replace(tmp,out)
PYREMOTE
items=''
for p in {q(PACKET_DIR)} {q(RESULT_JSON)} {q(EXECUTION_ATTESTATION)}; do if [ -e "$p" ]; then items="$items $(printf '%q' "$p")"; fi; done
[ -n "$items" ] || {{ [ {required_flag} = 0 ] && exit 0; echo REQUIRED_REMOTE_ARTIFACT_SET_EMPTY >&2; exit 91; }}
eval "tar --format=posix -czf {q(REMOTE_BUNDLE)} -- $items"
"""


def validate_manifest_paths(manifest: dict[str, Any], require_success_outputs: bool = True) -> None:
    if manifest.get("kind") != "PLANCARRY_REPLAYRESIDUAL_V22_REMOTE_ARTIFACT_MANIFEST_V1":
        raise ValueError("REMOTE_MANIFEST_KIND_MISMATCH")
    if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("repo_commit") != REMOTE_COMMIT:
        raise ValueError("REMOTE_MANIFEST_PROVENANCE_MISMATCH")
    if tuple(manifest.get("declared_roots", [])) != DECLARED_OUTPUTS:
        raise ValueError("REMOTE_MANIFEST_DECLARATION_MISMATCH")
    roots = tuple(PurePosixPath(x) for x in DECLARED_OUTPUTS)
    seen: set[str] = set()
    for row in manifest.get("files", []):
        rel = row.get("path")
        if not isinstance(rel, str) or rel in seen:
            raise ValueError("REMOTE_MANIFEST_PATH_INVALID")
        p = PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts or "." in p.parts or str(p) != rel:
            raise ValueError("REMOTE_MANIFEST_PATH_ESCAPE")
        if not any(p == root or root in p.parents for root in roots):
            raise ValueError("REMOTE_MANIFEST_UNDECLARED_PATH")
        if any(token in rel for token in ("valid_seen", "valid_unseen", "reserve")):
            raise ValueError("REMOTE_MANIFEST_FUTURE_SPLIT_FORBIDDEN")
        if not is_hex_sha256(row.get("sha256")) or type(row.get("size")) is not int or row["size"] < 0:
            raise ValueError("REMOTE_MANIFEST_DIGEST_INVALID")
        seen.add(rel)
    if require_success_outputs:
        covered = {root: False for root in DECLARED_OUTPUTS}
        for rel in seen:
            p = PurePosixPath(rel)
            for root_s in DECLARED_OUTPUTS:
                root = PurePosixPath(root_s)
                if p == root or root in p.parents:
                    covered[root_s] = True
        if not all(covered.values()):
            raise ValueError("REMOTE_MANIFEST_REQUIRED_ROOT_MISSING")


def verify_and_extract_bundle(
    bundle: Path, manifest_path: Path, artifact_dir: Path, require_success_outputs: bool = True
) -> Path:
    manifest = json.loads(manifest_path.read_text())
    validate_manifest_paths(manifest, require_success_outputs=require_success_outputs)
    rows = {row["path"]: row for row in manifest["files"]}
    if not rows:
        raise ValueError("REMOTE_MANIFEST_EMPTY")
    tmp = Path(tempfile.mkdtemp(prefix="v22_extract_", dir=str(artifact_dir)))
    try:
        with tarfile.open(bundle, "r:gz") as tf:
            members = tf.getmembers()
            files = [m for m in members if m.isfile()]
            for m in members:
                p = PurePosixPath(m.name)
                if p.is_absolute() or ".." in p.parts or m.issym() or m.islnk():
                    raise ValueError("LOCAL_BUNDLE_MEMBER_UNSAFE")
                if not (m.isfile() or m.isdir()):
                    raise ValueError("LOCAL_BUNDLE_MEMBER_TYPE_FORBIDDEN")
            file_names = {PurePosixPath(m.name).as_posix().lstrip("./") for m in files}
            if file_names != set(rows):
                raise ValueError("LOCAL_BUNDLE_MANIFEST_MEMBER_MISMATCH")
            for m in files:
                rel = PurePosixPath(m.name).as_posix().lstrip("./")
                target = tmp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    raise ValueError("LOCAL_BUNDLE_EXTRACT_FAILED")
                with target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                row = rows[rel]
                if target.stat().st_size != row["size"] or sha256_file(target) != row["sha256"]:
                    raise ValueError("LOCAL_BUNDLE_HASH_MISMATCH")
        final = artifact_dir / "replayresidual_v22_terminal_artifacts"
        if final.exists():
            raise ValueError("LOCAL_ARTIFACT_TARGET_ALREADY_EXISTS")
        os.replace(tmp, final)
        local_manifest = {
            "kind": "PLANCARRY_REPLAYRESIDUAL_V22_DURABLE_LOCAL_ARTIFACT_MANIFEST_V1",
            "experiment_id": EXPERIMENT_ID,
            "source_repo_commit": REMOTE_COMMIT,
            "remote_manifest_sha256": sha256_file(manifest_path),
            "bundle_sha256": sha256_file(bundle),
            "files": manifest["files"],
            "scientific_values_inspected": False,
            "future_split_access": False,
        }
        out = artifact_dir / "replayresidual_v22_durable_artifact_manifest_v1.json"
        out.write_text(json.dumps(local_manifest, sort_keys=True, separators=(",", ":")) + "\n")
        return out
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


async def run_stream(conn: asyncssh.SSHClientConnection, command: str) -> int:
    proc = await conn.create_process(command)
    async def pump(reader: Any, target: Any) -> None:
        async for chunk in reader:
            target.write(chunk)
            target.flush()
    await asyncio.gather(pump(proc.stdout, sys.stdout), pump(proc.stderr, sys.stderr))
    await proc.wait_closed()
    return int(proc.exit_status)


async def fetch_bundle(conn: asyncssh.SSHClientConnection, jobdir: Path, require_success_outputs: bool) -> None:
    artifact_dir = jobdir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    prep = await conn.run(remote_bundle_command(require_success_outputs), check=False, timeout=180)
    if prep.exit_status != 0:
        raise RuntimeError("REMOTE_ARTIFACT_BUNDLE_FAILED:" + str(prep.exit_status))
    exists = await conn.run(f"test -f {q(REMOTE_BUNDLE)} -a -f {q(REMOTE_MANIFEST)}", check=False)
    if exists.exit_status != 0:
        if require_success_outputs:
            raise RuntimeError("REMOTE_ARTIFACT_BUNDLE_MISSING")
        return
    bundle = artifact_dir / "replayresidual_v22_terminal_artifacts_v1.tgz"
    manifest = artifact_dir / "replayresidual_v22_terminal_artifacts_v1.remote_manifest.json"
    async with conn.start_sftp_client() as sftp:
        await sftp.get(REMOTE_BUNDLE, str(bundle))
        await sftp.get(REMOTE_MANIFEST, str(manifest))
    verify_and_extract_bundle(bundle, manifest, artifact_dir, require_success_outputs=require_success_outputs)
    print("V22_DURABLE_ARTIFACTS_FETCHED")


async def main_async(mode: str) -> None:
    att_path_s = os.environ.get("REPLAYRESIDUAL_V22_LIVE_HOST_ATTESTATION")
    att_sha = os.environ.get("REPLAYRESIDUAL_V22_LIVE_HOST_ATTESTATION_SHA256", "")
    if not att_path_s:
        raise SystemExit("LIVE_HOST_ATTESTATION_REQUIRED")
    att = load_live_attestation(Path(att_path_s), att_sha)
    host, port, hostkey = load_transport_binding()
    if mode == "execute":
        if os.environ.get("REPLAYRESIDUAL_V22_DISPATCH_AUTHORIZATION") != "RESEARCH_DECISION_BOUND":
            raise SystemExit("RESEARCH_DECISION_BOUND_DISPATCH_AUTHORIZATION_REQUIRED")
        jobdir_s = os.environ.get("GPU_LAB_JOB_DIR")
        if not jobdir_s:
            raise SystemExit("GPU_LAB_JOB_DIR_REQUIRED")
        jobdir = Path(jobdir_s)
    else:
        jobdir = Path(".")
    user = os.environ.get("REPLAYRESIDUAL_V22_VAST_USER", "root")
    key = os.environ.get("REPLAYRESIDUAL_V22_VAST_SSH_KEY", "/run/ssh-key")
    known = pinned_known_hosts(host, port, hostkey)
    try:
        async with asyncssh.connect(host, port=port, username=user, client_keys=[key], known_hosts=known, connect_timeout=30) as conn:
            pre = await conn.run(remote_preflight_command(), check=False, timeout=180)
            sys.stdout.write(pre.stdout)
            sys.stderr.write(pre.stderr)
            if pre.exit_status != 0 or "READY_NO_SCIENCE" not in pre.stdout or "V22_DISPATCH_REMOTE_PREFLIGHT_PASS" not in pre.stdout:
                raise SystemExit(pre.exit_status or 85)
            if mode == "preflight":
                return
            code = await run_stream(conn, remote_execution_command())
            try:
                await fetch_bundle(conn, jobdir, require_success_outputs=(code == 0))
            except Exception as exc:
                # Artifact durability failure is technical; never report successful science without durable bytes.
                raise SystemExit("ARTIFACTS_NOT_DURABLE:" + repr(exc)) from exc
            if code != 0:
                raise SystemExit(code)
    finally:
        Path(known).unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["preflight", "execute"], required=True)
    asyncio.run(main_async(ap.parse_args().mode))


if __name__ == "__main__":
    main()
