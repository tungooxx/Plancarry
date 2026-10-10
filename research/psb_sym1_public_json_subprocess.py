#!/usr/bin/env python3
"""PSB-SYM-1 native public JSON line worker for an external trusted controller.

Evaluated models must see only serialized public response bytes through this
private stdio process. They must NEVER receive the Python GuardedSymbolicEnv
instance, the game source, hidden facts, Quest objects, oracle, or process
filesystem access. The original native source is SHA-locked by the bridge.

One process owns ONE game. For paired A/B, start two independent OS processes
using the exact same game fixture. This is an IPC boundary, NOT an OS sandbox
when model code has arbitrary host filesystem/process execution rights.

Only engineering preflight. No LLM calls and no scientific G0/G1 authorization.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_INPUT_LINE=2048
MAX_IPC_REQUESTS=64


def reply_status(status: str) -> bytes:
    return json.dumps({"status":status},separators=(",",":"),sort_keys=True).encode("ascii")


def serve(frozen_game: Path) -> int:
    try:
        from psb_sym1_isolated_public_bridge import GuardedSymbolicEnv
        from psb_sym1_isolated_json_dispatch import dispatch_json
        instance=GuardedSymbolicEnv(frozen_game)
    except Exception:
        sys.stdout.buffer.write(reply_status("ENGINE_ERROR")+b"\n")
        sys.stdout.buffer.flush()
        return 2

    count=0
    while True:
        raw=sys.stdin.buffer.readline(MAX_INPUT_LINE+2)
        if not raw:
            return 0
        # Oversized frames must not be split into multiple commands. An
        # oversize frame terminates process after a fixed sanitized reply.
        if len(raw)>MAX_INPUT_LINE+1 or not raw.endswith(b"\n"):
            sys.stdout.buffer.write(reply_status("INVALID_REQUEST")+b"\n")
            sys.stdout.buffer.flush()
            return 2
        if count >= MAX_IPC_REQUESTS:
            # Exactly one response per accepted wire request; do not emit
            # an unsolicited status after the preceding request.
            sys.stdout.buffer.write(reply_status("REQUEST_BUDGET_EXHAUSTED")+b"\n")
            sys.stdout.buffer.flush()
            return 0
        request=raw[:-1]
        try:
            response=dispatch_json(instance,request)
            if b"\n" in response or b"\r" in response:
                response=reply_status("ENGINE_ERROR")
        except Exception:
            response=reply_status("ENGINE_ERROR")
        sys.stdout.buffer.write(response+b"\n")
        sys.stdout.buffer.flush()
        count+=1

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--frozen-game",type=Path,required=True)
    args=p.parse_args()
    return serve(args.frozen_game)


if __name__=="__main__":
    raise SystemExit(main())
