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
REMOTE_REPO = "/workspace/GPU-Lab/repos/plancarry-replayresidual-v22-rtx3080"
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
LIVE_ATTESTATION_KIND = "PLANCARRY_REPLAYRESIDUAL_V22_LIVE_HOST_ATTESTATION_V1"


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


def load_live_attestation(path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if not is_hex_sha256(expected_sha256) or sha256_bytes(raw) != expected_sha256:
        raise ValueError("LIVE_HOST_ATTESTATION_SHA_MISMATCH")
    obj = json.loads(raw)
    required_exact = {
        "kind": LIVE_ATTESTATION_KIND,
        "experiment_id": EXPERIMENT_ID,
        "instance_id": EXPECTED_INSTANCE_ID,
        "device_name": EXPECTED_GPU,
        "driver": EXPECTED_DRIVER,
        "repo_path": REMOTE_REPO,
        "repo_commit": REMOTE_COMMIT,
        "launcher_path": LAUNCHER,
        "launcher_sha256": LAUNCHER_SHA256,
        "host_review_work_item_id": HOST_REVIEW_WORK_ITEM_ID,
        "host_review_verdict": HOST_REVIEW_PASS,
    }
    for key, expected in required_exact.items():
        if obj.get(key) != expected:
            raise ValueError(f"LIVE_HOST_ATTESTATION_FIELD_MISMATCH:{key}")
    if obj.get("future_split_access") is not False or obj.get("study_cohort_access") is not False:
        raise ValueError("LIVE_HOST_ATTESTATION_ACCESS_GUARD_FAILED")
    if obj.get("provider_lifecycle_action") not in (None, "NONE"):
        raise ValueError("PROVIDER_LIFECYCLE_NOT_ALLOWED")
    if not is_hex_sha256(obj.get("host_review_sha256")):
        raise ValueError("HOST_REVIEW_SHA_REQUIRED")
    if not is_hex_sha256(obj.get("hostkey_ed25519_sha256")):
        raise ValueError("HOSTKEY_SHA_REQUIRED")
    host = obj.get("host")
    port = obj.get("port")
    if not isinstance(host, str) or not host or any(ch.isspace() for ch in host):
        raise ValueError("LIVE_HOST_ENDPOINT_INVALID")
    if type(port) is not int or port <= 0 or port > 65535:
        raise ValueError("LIVE_HOST_PORT_INVALID")
    if obj.get("outputs_absent") is not True:
        raise ValueError("LIVE_HOST_OUTPUT_ABSENCE_NOT_ATTESTED")
    return obj


def pinned_known_hosts(att: dict[str, Any]) -> str:
    host, port = att["host"], att["port"]
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
    expected = "SHA256:" + att["hostkey_ed25519_sha256"]
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
    known = pinned_known_hosts(att)
    try:
        async with asyncssh.connect(att["host"], port=att["port"], username=user, client_keys=[key], known_hosts=known, connect_timeout=30) as conn:
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
