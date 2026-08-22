#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
MODEL_ID="Qwen/Qwen2.5-1.5B-Instruct"
REVISION="989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
EXPECTED_DEVICE="RTX 3050"
EXPECTED_TRANSFORMERS="4.46.3"
EXPECTED_TOKENIZERS="0.20.3"

def fail(msg: str) -> None:
    print(json.dumps({"ok":False,"error":msg}, sort_keys=True), file=sys.stderr)
    raise SystemExit(2)

def main() -> int:
    if not os.environ.get("PLANCARRY_WHITEBOX_TOKEN", "").strip():
        fail("PLANCARRY_WHITEBOX_TOKEN must be non-empty")
    try:
        import torch, transformers, tokenizers
    except Exception as exc:
        fail(f"dependency import failed: {type(exc).__name__}: {exc}")
    if not torch.cuda.is_available(): fail("torch.cuda.is_available() is false")
    name=torch.cuda.get_device_name(0)
    if EXPECTED_DEVICE.lower() not in name.lower(): fail(f"expected device containing {EXPECTED_DEVICE!r}, got {name!r}")
    if transformers.__version__ != EXPECTED_TRANSFORMERS: fail(f"transformers {transformers.__version__} != {EXPECTED_TRANSFORMERS}")
    if tokenizers.__version__ != EXPECTED_TOKENIZERS: fail(f"tokenizers {tokenizers.__version__} != {EXPECTED_TOKENIZERS}")
    print(json.dumps({"ok":True,"device_name":name,"torch_version":torch.__version__,"transformers_version":transformers.__version__,"tokenizers_version":tokenizers.__version__,"model_id":MODEL_ID,"revision":REVISION,"scientific_result":"NOT_ASSESSED"}, sort_keys=True))
    return 0
if __name__ == '__main__': raise SystemExit(main())
