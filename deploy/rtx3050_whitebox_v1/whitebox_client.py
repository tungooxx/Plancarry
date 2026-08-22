#!/usr/bin/env python3
"""Client for the bounded PlanCarry white-box bridge."""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = 120.0


class WhiteboxClient:
    def __init__(self, base_url: str, token: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        if not token:
            raise ValueError("token must be non-empty")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except Exception:
                body = {"ok": False, "error": {"code": "HTTP_ERROR", "message": raw}}
            raise RuntimeError(f"bridge HTTP {exc.code}: {body}") from exc
        if not body.get("ok"):
            raise RuntimeError(f"bridge error: {body.get('error')}")
        return body

    def health(self): return self.request("GET", "/health")
    def model_info(self): return self.request("GET", "/model_info")
    def score_sequences(self, prompt: str, suffixes: list[str]):
        return self.request("POST", "/score_sequences", {"prompt": prompt, "suffixes": suffixes})
    def capture(self, text: str, layer: int, token_index: int = -1):
        return self.request("POST", "/capture", {"text": text, "layer": layer, "token_index": token_index})
    def patch_score(self, prompt: str, suffixes: list[str], layer: int, vector: list[float], token_index: int = -1, mode: str = "add", scale: float = 1.0):
        return self.request("POST", "/patch_score", {"prompt": prompt, "suffixes": suffixes, "layer": layer, "token_index": token_index, "vector": vector, "mode": mode, "scale": scale})


def _load_vector(arg: str) -> list[float]:
    if arg.startswith("@"):
        value = json.load(open(arg[1:], "r", encoding="utf-8"))
    else:
        value = json.loads(arg)
    if isinstance(value, dict) and "vector" in value:
        value = value["vector"]
    if not isinstance(value, list):
        raise ValueError("vector JSON must be a list or object containing vector")
    return [float(x) for x in value]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=os.environ.get("PLANCARRY_WHITEBOX_URL", "http://127.0.0.1:8765"))
    p.add_argument("--token", default=os.environ.get("PLANCARRY_WHITEBOX_TOKEN", ""))
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("model-info")
    s = sub.add_parser("score"); s.add_argument("--prompt", required=True); s.add_argument("--suffix", action="append", required=True)
    c = sub.add_parser("capture"); c.add_argument("--text", required=True); c.add_argument("--layer", type=int, required=True); c.add_argument("--token-index", type=int, default=-1)
    q = sub.add_parser("patch-score"); q.add_argument("--prompt", required=True); q.add_argument("--suffix", action="append", required=True); q.add_argument("--layer", type=int, required=True); q.add_argument("--token-index", type=int, default=-1); q.add_argument("--mode", choices=["add", "replace"], default="add"); q.add_argument("--scale", type=float, default=1.0); q.add_argument("--vector", required=True, help="JSON list, or @file.json")
    args = p.parse_args()
    if not args.token:
        print("PLANCARRY_WHITEBOX_TOKEN/--token is required", file=sys.stderr); return 2
    cli = WhiteboxClient(args.url, args.token, args.timeout)
    if args.cmd == "health": out = cli.health()
    elif args.cmd == "model-info": out = cli.model_info()
    elif args.cmd == "score": out = cli.score_sequences(args.prompt, args.suffix)
    elif args.cmd == "capture": out = cli.capture(args.text, args.layer, args.token_index)
    else: out = cli.patch_score(args.prompt, args.suffix, args.layer, _load_vector(args.vector), args.token_index, args.mode, args.scale)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
