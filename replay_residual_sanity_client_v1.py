#!/usr/bin/env python3
"""Capture-only HTTP client for ReplayResidual representation sanity.

The API surface is intentionally smaller than the general white-box client.
Only health, model metadata, scoring, and activation capture exist here.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_ALLOWED_GET = frozenset({"/health", "/model_info"})
_ALLOWED_POST = frozenset({"/score_sequences", "/capture"})


class CaptureOnlyClient:
    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        if not token:
            raise ValueError("token must be non-empty")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = float(timeout)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = _ALLOWED_GET if method == "GET" else _ALLOWED_POST if method == "POST" else frozenset()
        if path not in allowed:
            raise RuntimeError(f"CAPTURE_ONLY_ENDPOINT_FORBIDDEN:{method}:{path}")
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
            raise RuntimeError(f"BRIDGE_HTTP_{exc.code}:{raw}") from exc
        if not body.get("ok") or not isinstance(body.get("result"), dict):
            raise RuntimeError(f"BRIDGE_PROTOCOL_ERROR:{body}")
        return body["result"]

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def model_info(self) -> dict[str, Any]:
        return self._request("GET", "/model_info")

    def score_sequences(self, prompt: str, suffixes: list[str]) -> dict[str, Any]:
        return self._request("POST", "/score_sequences", {"prompt": prompt, "suffixes": suffixes})

    def capture(self, text: str, layer: int, token_index: int = -1) -> dict[str, Any]:
        return self._request("POST", "/capture", {"text": text, "layer": int(layer), "token_index": int(token_index)})
