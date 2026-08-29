#!/usr/bin/env python3
"""V2.3 bridge entrypoint that forbids product-name admission.

The frozen bridge implementation remains unchanged.  This adapter guarantees
that its legacy optional device-substring gate is disabled for V2.3.
"""
from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import whitebox_bridge_prefixstable_proto as frozen

def normalized_argv(argv:list[str])->list[str]:
    out=list(argv)
    flag="--expected-device-substring"
    if flag in out:
        i=out.index(flag)
        if i+1>=len(out) or out[i+1]!="":
            raise RuntimeError("V23_DEVICE_NAME_ADMISSION_FORBIDDEN")
        return out
    out.extend([flag,""])
    return out

def main()->int:
    sys.argv=[sys.argv[0],*normalized_argv(sys.argv[1:])]
    return frozen.main()

if __name__=="__main__":
    raise SystemExit(main())
