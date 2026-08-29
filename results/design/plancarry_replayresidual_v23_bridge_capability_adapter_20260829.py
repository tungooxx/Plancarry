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
    # Remove every legacy device-name option and append exactly one disabled
    # occurrence. Any non-empty occurrence is rejected before frozen argparse
    # can apply its normal last-option-wins semantics.
    out=[]
    flag="--expected-device-substring"
    i=0
    while i<len(argv):
        arg=argv[i]
        if arg==flag:
            if i+1>=len(argv) or argv[i+1]!="":
                raise RuntimeError("V23_DEVICE_NAME_ADMISSION_FORBIDDEN")
            i+=2
            continue
        if arg.startswith(flag+"="):
            if arg.split("=",1)[1]!="":
                raise RuntimeError("V23_DEVICE_NAME_ADMISSION_FORBIDDEN")
            i+=1
            continue
        out.append(arg)
        i+=1
    out.extend([flag,""])
    return out

def main()->int:
    sys.argv=[sys.argv[0],*normalized_argv(sys.argv[1:])]
    return frozen.main()

if __name__=="__main__":
    raise SystemExit(main())
