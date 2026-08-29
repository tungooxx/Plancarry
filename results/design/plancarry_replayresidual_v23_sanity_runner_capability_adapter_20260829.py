#!/usr/bin/env python3
"""V2.3 capability-only adapter for the frozen ReplayResidual sanity runner.

The frozen representation-sanity computation remains in
``replay_residual_sanity_runner_v1``.  This adapter changes only operational
runtime admission: CUDA device marketing name is recorded as provenance but is
never compared to a product-name whitelist/sub-string.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import replay_residual_sanity_runner_v1 as frozen
import replay_residual_sanity_protocol_v1 as p

def v23_runtime_check(info:dict[str,Any])->None:
    if info.get("model_id")!=p.MODEL_ID:
        raise RuntimeError(f"MODEL_ID_MISMATCH:{info.get('model_id')}")
    if info.get("model_revision_requested")!=p.MODEL_REVISION:
        raise RuntimeError(f"MODEL_REVISION_MISMATCH:{info.get('model_revision_requested')}")
    if info.get("model_commit_resolved")!=p.MODEL_REVISION:
        raise RuntimeError(f"MODEL_COMMIT_MISMATCH:{info.get('model_commit_resolved')}")
    device_name=info.get("device_name")
    if not isinstance(device_name,str) or not device_name.strip():
        raise RuntimeError("MODEL_DEVICE_PROVENANCE_REQUIRED")
    if str(info.get("dtype")) not in {"torch.bfloat16","bfloat16"}:
        raise RuntimeError(f"DTYPE_MISMATCH:{info.get('dtype')}")
    if info.get("quantization")!="NONE":
        raise RuntimeError(f"QUANTIZATION_MISMATCH:{info.get('quantization')}")
    expected_versions={
        "transformers_version":p.TRANSFORMERS_VERSION,
        "tokenizers_version":p.TOKENIZERS_VERSION,
        "torch_version":p.TORCH_VERSION,
    }
    for key,expected in expected_versions.items():
        if str(info.get(key))!=expected:
            raise RuntimeError(f"RUNTIME_VERSION_MISMATCH:{key}:{info.get(key)}:{expected}")

def main()->int:
    frozen._runtime_check=v23_runtime_check
    return frozen.main()

if __name__=="__main__":
    raise SystemExit(main())
