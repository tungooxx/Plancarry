#!/usr/bin/env python3
"""PSB-SYM-1 trusted-host JSON dispatch atop fully isolated TextWorld instances.

PR #7 dependency: each arm loads source-pinned native Game independently,
not TextWorldEnv.copy. Evaluated LLMs must have access only to serialized
dispatch replies through an external IPC host. This module is NOT a sandbox.
Engineering only; no model calls and no G0/G1 scientific authorization.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from psb_sym1_isolated_public_bridge import (
    GuardedSymbolicEnv, isolated_pair, STATUS_OK,
)

_PUBLIC_KEYS=frozenset({"status","observation","done","score"})
_ACTIONS=frozenset({"observe","act"})
_MAX_REQUEST_BYTES=2048


def _reply(result: Mapping[str,Any]) -> dict[str,Any]:
    """Return independent plain JSON primitives, no internal native objects."""
    if not isinstance(result,dict) or "status" not in result:
        return {"status":"ENGINE_ERROR"}
    if result["status"] != STATUS_OK:
        return {"status":str(result["status"]) if result["status"] in (
            "INVALID_ACTION","GUARD_VIOLATION","ENGINE_ERROR","TERMINAL"
        ) else "ENGINE_ERROR"}
    if set(result)!=_PUBLIC_KEYS or type(result["observation"]) is not str \
       or type(result["done"]) is not bool or type(result["score"]) is not int:
        return {"status":"ENGINE_ERROR"}
    if len(result["observation"])>8192:
        return {"status":"ENGINE_ERROR"}
    return {
        "status":STATUS_OK, "observation":result["observation"],
        "done":result["done"], "score":result["score"],
    }


def dispatch(instance: GuardedSymbolicEnv, request: dict[str,Any]) -> dict[str,Any]:
    """The ONLY agent-facing operation: observe or exact native action.

    Never return native env, attributes, arbitrary exceptions, hidden policy,
    history, game graph, quest, RNG or Python traceback.
    """
    if type(request) is not dict:
        return {"status":"INVALID_REQUEST"}
    cmd=request.get("command")
    if cmd not in _ACTIONS:
        return {"status":"INVALID_REQUEST"}
    if cmd=="observe" and set(request)=={"command"}:
        try:return _reply(instance.observe())
        except Exception:return {"status":"ENGINE_ERROR"}
    if cmd=="act" and set(request)=={"command","action"} and type(request["action"]) is str \
       and len(request["action"])<=256:
        try:return _reply(instance.act(request["action"]))
        except Exception:return {"status":"ENGINE_ERROR"}
    return {"status":"INVALID_REQUEST"}


def dispatch_json(instance: GuardedSymbolicEnv, raw: bytes) -> bytes:
    """Suitable for narrow stdio or IPC framing by a separate trusted host."""
    if type(raw) is not bytes or not 0<len(raw)<=_MAX_REQUEST_BYTES:
        return b'{"status":"INVALID_REQUEST"}'
    try:
        # JSON duplicate object members are ambiguous across parsers and
        # could make the audited command differ from the executed command.
        # Reject duplicates at every nesting depth instead of Python's
        # default last-key-wins semantics.
        def unique_object(pairs):
            record={}
            for key,value in pairs:
                if key in record:
                    raise ValueError("duplicate JSON member")
                record[key]=value
            return record
        def forbid_nonfinite(token):
            raise ValueError("nonfinite JSON token")
        data=json.loads(raw.decode("utf-8"),
                        object_pairs_hook=unique_object,
                        parse_constant=forbid_nonfinite)
        result=dispatch(instance,data)
        return json.dumps(result,sort_keys=True,separators=(",",":"),
                          ensure_ascii=True,allow_nan=False).encode("ascii")
    except (UnicodeError,ValueError,TypeError,OverflowError):
        return b'{"status":"INVALID_REQUEST"}'


def make_isolated_prefix_pair(source: Path, prefix: tuple[str,...]):
    """Trusted controller ONLY. Separate real native Game instances per arm.

    Returns handles to trusted controller; NEVER model-visible.
    """
    if not isinstance(prefix,tuple) or not prefix or len(prefix)>8 \
       or any(type(c) is not str or not c for c in prefix):
        raise ValueError("Invalid frozen prefix")
    a,b=isolated_pair(source)
    for command in prefix:
        after_a=dispatch(a,{"command":"act","action":command})
        after_b=dispatch(b,{"command":"act","action":command})
        if after_a!=after_b or after_a.get("status")!=STATUS_OK:
            raise RuntimeError("Isolated PDDL-independent prefix mismatch")
    # Trusted-only native facts parity confirms no hidden symbolic divergence.
    facts_a=sorted(str(x) for x in a._env._game_progression.state.facts)
    facts_b=sorted(str(x) for x in b._env._game_progression.state.facts)
    if facts_a!=facts_b:
        raise RuntimeError("Isolated native state mismatch")
    return a,b
