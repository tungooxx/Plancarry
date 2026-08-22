#!/usr/bin/env python3
"""Fail-closed localhost sidecar for ReplayResidual representation sanity.

Only model metadata, health, sequence scoring, and activation capture are
forwarded to an already-qualified white-box bridge. Every other route is 404
before upstream dispatch. This avoids a second model copy on a 4 GiB GPU.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MAX_BODY_BYTES = 2 * 1024 * 1024
ALLOWED_GET = frozenset({"/health", "/model_info"})
ALLOWED_POST = frozenset({"/score_sequences", "/capture"})


class CaptureOnlyProxy:
    def __init__(self, upstream: str, upstream_token: str, downstream_token: str):
        if not upstream_token or not downstream_token:
            raise ValueError("both tokens must be non-empty")
        self.upstream = upstream.rstrip("/")
        self.upstream_token = upstream_token
        self.downstream_token = downstream_token.encode()
        self.forward_counts = {"GET": 0, "POST": 0}

    def authorized(self, header: str | None) -> bool:
        if not header or not header.startswith("Bearer "):
            return False
        return hmac.compare_digest(header[7:].encode(), self.downstream_token)

    def forward(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        allowed = ALLOWED_GET if method == "GET" else ALLOWED_POST if method == "POST" else frozenset()
        if path not in allowed:
            raise KeyError(path)
        self.forward_counts[method] += 1
        req = urllib.request.Request(
            self.upstream + path,
            data=body,
            method=method,
            headers={"Authorization": "Bearer " + self.upstream_token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return int(resp.status), resp.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()


def make_handler(proxy: CaptureOnlyProxy):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PlanCarryReplayResidualCaptureOnly/1"
        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))
        def _send(self, status: int, raw: bytes) -> None:
            self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(raw)
        def _error(self, status: int, code: str, message: str) -> None:
            self._send(status, (json.dumps({"ok": False, "error": {"code": code, "message": message}}, separators=(",", ":")) + "\n").encode())
        def _auth(self) -> bool:
            if proxy.authorized(self.headers.get("Authorization")): return True
            self._error(HTTPStatus.UNAUTHORIZED, "UNAUTHORIZED", "Bearer token required"); return False
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ALLOWED_GET:
                self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "unknown endpoint"); return
            if not self._auth(): return
            status, raw = proxy.forward("GET", self.path); self._send(status, raw)
        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ALLOWED_POST:
                self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "unknown endpoint"); return
            if not self._auth(): return
            try: length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "INVALID_LENGTH", "invalid Content-Length"); return
            if length <= 0 or length > MAX_BODY_BYTES:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > MAX_BODY_BYTES else HTTPStatus.BAD_REQUEST, "INVALID_LENGTH", "invalid body length"); return
            body = self.rfile.read(length)
            status, raw = proxy.forward("POST", self.path, body); self._send(status, raw)
    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8893)
    ap.add_argument("--upstream", default="http://127.0.0.1:8892")
    ap.add_argument("--upstream-token-file", required=True)
    ap.add_argument("--downstream-token-env", default="PLANCARRY_REPLAY_SANITY_TOKEN")
    args = ap.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("capture-only sidecar refuses non-loopback bind")
    upstream_token = open(args.upstream_token_file, "r", encoding="utf-8").read().strip()
    downstream_token = os.environ.get(args.downstream_token_env, "")
    proxy = CaptureOnlyProxy(args.upstream, upstream_token, downstream_token)
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(proxy))
    print(json.dumps({"event":"capture_only_sidecar_started","host":args.host,"port":args.port,"upstream":args.upstream,"allowed_get":sorted(ALLOWED_GET),"allowed_post":sorted(ALLOWED_POST),"scientific_result":"NOT_ASSESSED"}, sort_keys=True), flush=True)
    try: srv.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt: pass
    finally: srv.server_close()
    return 0


if __name__ == "__main__": raise SystemExit(main())
