#!/usr/bin/env python3
"""Fail-closed PlanLatch v7.20 reserved-host runtime attestation collector.

Host introspection only. It does not load Qwen, tokenizers, ALFWorld data, or
perform any scientific/model execution. Run only on the exact reserved host
before one-shot registration.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import ctypes.util
import hashlib
import importlib
import importlib.metadata as md
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import sysconfig
import zipfile

REQUIRED_FIELDS = (
    "complete_python312_environment_manifest_sha256",
    "container_image_digest",
    "container_image_reference",
    "cpu_flags_sha256",
    "cpu_model",
    "cuda_driver_api_version",
    "cuda_runtime_version",
    "gpu_firmware_vbios",
    "gpu_model",
    "gpu_uuid",
    "nvidia_driver_version",
    "numeric_threading_environment_sha256",
    "numpy_exact_version",
    "numpy_installed_tree_sha256",
    "numpy_linked_native_libraries_manifest_sha256",
    "numpy_runtime_config_sha256",
    "numpy_wheel_archive_sha256",
    "python_exact_version",
    "python_executable_sha256",
    "tokenizers_wheel_archive_sha256",
    "torch_wheel_archive_sha256",
    "transformers_wheel_archive_sha256",
)
FROZEN_REQUIRED_VERSIONS = {
    "torch": "2.13.0+cu130",
    "transformers": "4.51.3",
    "tokenizers": "0.21.1",
}
THREAD_ENV_KEYS = (
    "OMP_NUM_THREADS", "OMP_DYNAMIC",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS", "MKL_DYNAMIC",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
)

class AttestationError(RuntimeError):
    pass

def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def require_env(name: str) -> str:
    v=os.environ.get(name)
    if not v:
        raise AttestationError(f"required orchestrator environment variable missing: {name}")
    return v

def hash_tree(root: Path) -> tuple[str, list[dict[str, object]]]:
    if not root.is_dir():
        raise AttestationError(f"tree missing: {root}")
    rows=[]
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel=p.relative_to(root).as_posix()
        if "__pycache__" in p.parts or rel.endswith((".pyc",".pyo")):
            continue
        rows.append({"path":rel,"size":p.stat().st_size,"sha256":sha256_file(p)})
    if not rows:
        raise AttestationError(f"empty tree: {root}")
    return hashlib.sha256(canonical_bytes(rows)).hexdigest(), rows

def read_wheel_metadata(path: Path) -> tuple[str,str]:
    if not path.is_file() or path.suffix != ".whl":
        raise AttestationError(f"wheel archive missing/not .whl: {path}")
    with zipfile.ZipFile(path) as z:
        metas=sorted(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
        if len(metas)!=1:
            raise AttestationError(f"wheel must have exactly one dist-info/METADATA: {path}")
        text=z.read(metas[0]).decode("utf-8","strict")
    name=version=None
    for line in text.splitlines():
        if line.startswith("Name: ") and name is None: name=line[6:].strip()
        if line.startswith("Version: ") and version is None: version=line[9:].strip()
    if not name or not version:
        raise AttestationError(f"wheel metadata missing Name/Version: {path}")
    return name,version

def normalize_dist_name(s: str) -> str:
    return re.sub(r"[-_.]+","-",s).lower()

def load_wheel_manifest(path: Path) -> tuple[dict[str,Path],str]:
    raw=path.read_bytes()
    obj=json.loads(raw)
    if not isinstance(obj,dict):
        raise AttestationError("wheel manifest must be JSON object")
    needed={"torch","transformers","tokenizers","numpy"}
    if set(obj)!=needed:
        raise AttestationError(f"wheel manifest keys must equal {sorted(needed)}")
    out={}
    for dist,p in obj.items():
        wp=Path(p)
        if not wp.is_absolute():
            wp=(path.parent/wp).resolve()
        installed=md.version(dist)
        wn,wv=read_wheel_metadata(wp)
        if normalize_dist_name(wn)!=normalize_dist_name(dist):
            raise AttestationError(f"wheel Name mismatch for {dist}: {wn}")
        if wv!=installed:
            raise AttestationError(f"wheel Version mismatch for {dist}: wheel={wv} installed={installed}")
        out[dist]=wp
    return out,hashlib.sha256(raw).hexdigest()

def installed_distribution_manifest() -> list[dict[str,object]]:
    rows=[]
    for dist in sorted(md.distributions(), key=lambda d: normalize_dist_name(d.metadata.get("Name") or "")):
        name=dist.metadata.get("Name")
        if not name:
            raise AttestationError("installed distribution without Name metadata")
        version=dist.version
        files=[]
        for f in sorted(dist.files or [], key=lambda x:str(x)):
            sf=str(f)
            if "__pycache__" in sf or sf.endswith((".pyc",".pyo")):
                continue
            p=Path(dist.locate_file(f))
            if not p.is_file():
                raise AttestationError(f"installed distribution file missing: {name} {sf}")
            files.append({"path":sf,"size":p.stat().st_size,"sha256":sha256_file(p)})
        rows.append({"name":name,"version":version,"files":files})
    return rows

def cpu_info() -> tuple[str,str,dict[str,object]]:
    p=Path("/proc/cpuinfo")
    if not p.is_file():
        raise AttestationError("/proc/cpuinfo unavailable")
    model=None; flags=None
    for block in p.read_text(errors="strict").split("\n\n"):
        vals={}
        for line in block.splitlines():
            if ":" in line:
                k,v=line.split(":",1); vals[k.strip()]=v.strip()
        if "model name" in vals or "Processor" in vals:
            model=vals.get("model name") or vals.get("Processor")
            flags=(vals.get("flags") or vals.get("Features") or "").split()
            break
    if not model or not flags:
        raise AttestationError("CPU model/flags unavailable")
    flags_sorted=sorted(set(flags))
    flags_sha=hashlib.sha256(canonical_bytes(flags_sorted)).hexdigest()
    payload={
        "logical_cpu_count":os.cpu_count(),
        "machine":platform.machine(),
        "platform":platform.platform(),
        "thread_env":{k:os.environ.get(k,"<UNSET>") for k in THREAD_ENV_KEYS},
    }
    threading_sha=hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return model,flags_sha,{"sha256":threading_sha,"payload":payload}

def run_checked(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30).strip()
    except Exception as e:
        raise AttestationError(f"command failed {args!r}: {e}") from e

def gpu_info(uuid: str) -> dict[str,str]:
    out=run_checked([
        "nvidia-smi","-i",uuid,
        "--query-gpu=uuid,name,vbios_version,driver_version",
        "--format=csv,noheader,nounits",
    ])
    lines=[x.strip() for x in out.splitlines() if x.strip()]
    if len(lines)!=1:
        raise AttestationError(f"expected exactly one reserved GPU row, got {len(lines)}")
    parts=[x.strip() for x in lines[0].split(",")]
    if len(parts)!=4:
        raise AttestationError(f"unexpected nvidia-smi row: {lines[0]}")
    got_uuid,model,vbios,driver=parts
    if got_uuid!=uuid:
        raise AttestationError(f"reserved GPU UUID mismatch: expected={uuid} got={got_uuid}")
    return {"gpu_uuid":got_uuid,"gpu_model":model,"gpu_firmware_vbios":vbios,"nvidia_driver_version":driver}

def _resolve_cuda_library(libname: str) -> str:
    path=ctypes.util.find_library(libname)
    if path:
        return path
    if libname != "cudart":
        raise AttestationError(f"cannot locate {libname}")
    patterns = (
        "lib/python*/site-packages/nvidia/cu13/lib/libcudart.so*",
        "lib/python*/site-packages/nvidia/cuda_runtime/lib/libcudart.so*",
        "lib64/libcudart.so*",
        "lib/libcudart.so*",
    )
    resolved = {}
    prefix = Path(sys.prefix)
    for pattern in patterns:
        for p in sorted(prefix.glob(pattern)):
            if p.is_file():
                rp = p.resolve()
                resolved[str(rp)] = rp
    if len(resolved) != 1:
        raise AttestationError(
            f"cannot deterministically locate {libname}: resolved_candidates={sorted(resolved)}"
        )
    return str(next(iter(resolved.values())))

def cuda_version(libname: str, init_name: str|None, get_name: str) -> str:
    path=_resolve_cuda_library(libname)
    lib=ctypes.CDLL(path)
    if init_name:
        init=getattr(lib,init_name); init.argtypes=[ctypes.c_uint]; init.restype=ctypes.c_int
        rc=init(0)
        if rc!=0: raise AttestationError(f"{init_name} failed rc={rc}")
    get=getattr(lib,get_name); get.argtypes=[ctypes.POINTER(ctypes.c_int)]; get.restype=ctypes.c_int
    v=ctypes.c_int()
    rc=get(ctypes.byref(v))
    if rc!=0: raise AttestationError(f"{get_name} failed rc={rc}")
    return str(v.value)

def numpy_attestation() -> dict[str,object]:
    np=importlib.import_module("numpy")
    np_root=Path(np.__file__).resolve().parent
    tree_sha,_=hash_tree(np_root)
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):
        np.show_config()
    config_text=buf.getvalue()
    config_sha=hashlib.sha256(config_text.encode()).hexdigest()
    ext_rows=[]; deps={}
    for ext in sorted(np_root.rglob("*.so")):
        ldd=run_checked(["ldd",str(ext)])
        ext_rows.append({"extension":ext.relative_to(np_root).as_posix(),"ldd":ldd})
        for line in ldd.splitlines():
            m=re.search(r"=>\s+(/[^ ]+)\s+",line)
            if not m:
                m=re.match(r"\s*(/[^ ]+)\s+",line)
            if m:
                p=Path(m.group(1))
                if p.is_file():
                    deps[str(p)]={"size":p.stat().st_size,"sha256":sha256_file(p)}
    if not ext_rows:
        raise AttestationError("NumPy native extension set empty")
    native={"extensions":ext_rows,"dependencies":[{"path":k,**deps[k]} for k in sorted(deps)]}
    native_sha=hashlib.sha256(canonical_bytes(native)).hexdigest()
    return {
        "numpy_exact_version":str(np.__version__),
        "numpy_installed_tree_sha256":tree_sha,
        "numpy_runtime_config_sha256":config_sha,
        "numpy_linked_native_libraries_manifest_sha256":native_sha,
        "_numpy_runtime_config_text":config_text,
        "_numpy_native_manifest":native,
    }

def collect(wheel_manifest_path: Path) -> dict[str,object]:
    if sys.version_info[:2]!=(3,12):
        raise AttestationError(f"Python must be 3.12, got {platform.python_version()}")
    for dist,expected in FROZEN_REQUIRED_VERSIONS.items():
        got=md.version(dist)
        if got!=expected:
            raise AttestationError(f"{dist} version mismatch: expected={expected} got={got}")
    wheels,wheel_manifest_sha=load_wheel_manifest(wheel_manifest_path)
    wheel_hashes={k:sha256_file(v) for k,v in wheels.items()}
    model,flags_sha,threading=cpu_info()
    reserved_uuid=require_env("PLANCARRY_RESERVED_GPU_UUID")
    gpu=gpu_info(reserved_uuid)
    image_ref=require_env("PLANCARRY_CONTAINER_IMAGE_REFERENCE")
    image_digest=require_env("PLANCARRY_CONTAINER_IMAGE_DIGEST")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}",image_digest):
        raise AttestationError("PLANCARRY_CONTAINER_IMAGE_DIGEST must be sha256:<64hex>")
    npatt=numpy_attestation()
    pyexe=Path(sys.executable).resolve()
    env_manifest={
        "schema":"planlatch-v720-python312-environment-manifest-v1",
        "python_exact_version":platform.python_version(),
        "python_full_version":sys.version,
        "python_executable":str(pyexe),
        "python_executable_sha256":sha256_file(pyexe),
        "implementation":sys.implementation.name,
        "cache_tag":sys.implementation.cache_tag,
        "soabi":sysconfig.get_config_var("SOABI"),
        "prefix":sys.prefix,
        "base_prefix":sys.base_prefix,
        "wheel_manifest_sha256":wheel_manifest_sha,
        "installed_distributions":installed_distribution_manifest(),
    }
    env_sha=hashlib.sha256(canonical_bytes(env_manifest)).hexdigest()
    fields={
        "complete_python312_environment_manifest_sha256":env_sha,
        "container_image_digest":image_digest,
        "container_image_reference":image_ref,
        "cuda_driver_api_version":cuda_version("cuda","cuInit","cuDriverGetVersion"),
        "cuda_runtime_version":cuda_version("cudart",None,"cudaRuntimeGetVersion"),
        **gpu,
        "python_exact_version":platform.python_version(),
        "python_executable_sha256":sha256_file(pyexe),
        "tokenizers_wheel_archive_sha256":wheel_hashes["tokenizers"],
        "torch_wheel_archive_sha256":wheel_hashes["torch"],
        "transformers_wheel_archive_sha256":wheel_hashes["transformers"],
        "numpy_exact_version":npatt["numpy_exact_version"],
        "numpy_wheel_archive_sha256":wheel_hashes["numpy"],
        "numpy_installed_tree_sha256":npatt["numpy_installed_tree_sha256"],
        "numpy_runtime_config_sha256":npatt["numpy_runtime_config_sha256"],
        "numpy_linked_native_libraries_manifest_sha256":npatt["numpy_linked_native_libraries_manifest_sha256"],
        "cpu_model":model,
        "cpu_flags_sha256":flags_sha,
        "numeric_threading_environment_sha256":threading["sha256"],
    }
    if set(fields)!=set(REQUIRED_FIELDS):
        raise AttestationError(f"field closure mismatch missing={set(REQUIRED_FIELDS)-set(fields)} extra={set(fields)-set(REQUIRED_FIELDS)}")
    if any(v in ("",None,"PENDING_RESERVED_HOST") for v in fields.values()):
        raise AttestationError("attestation contains empty/pending field")
    return {
        "schema":"planlatch-v720-reserved-host-attestation-v2",
        "runtime_lock_v4_file_sha256":"9fe4f5c568418eb5b126bffe386a4e0d52e0048ad5d5a80042a51bee10fdd2ad",
        "binding_sha256":"934c3ece94d0c5871c25307d18caad78401392e8f1a6caeb95dcbdc7e76e8a37",
        "fields":fields,
        "evidence":{
            "wheel_manifest_sha256":wheel_manifest_sha,
            "python_environment_manifest":env_manifest,
            "numeric_threading_environment":threading["payload"],
            "numpy_runtime_config_text":npatt["_numpy_runtime_config_text"],
            "numpy_native_manifest":npatt["_numpy_native_manifest"],
        },
        "scope":{
            "model_loaded":False,
            "task_data_accessed":False,
            "authority_consumed":False,
            "beacon_read":False,
            "membership_drawn":False,
            "scientific_execution_performed":False,
        },
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--wheel-manifest",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    obj=collect(a.wheel_manifest)
    payload_sha=hashlib.sha256(canonical_bytes(obj)).hexdigest()
    wrapped={"attestation":obj,"attestation_sha256":payload_sha}
    a.output.write_text(json.dumps(wrapped,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"attestation_sha256":payload_sha,"output_sha256":sha256_file(a.output)},sort_keys=True))

if __name__=="__main__":
    main()
