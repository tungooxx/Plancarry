#!/usr/bin/env python3
"""Bounded authenticated HTTP bridge for PlanCarry white-box LLM operations.

GPU-lab validation MUST use --mock. Real mode is intended for the user-authorized
RTX 3050 host and refuses a mismatched CUDA device name by default.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import platform
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

API_VERSION = "plancarry-whitebox-v1"
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 131072
MAX_SUFFIXES = 64
MAX_VECTOR_DIM = 65536
MAX_ABS_SCALE = 32.0
ALLOWED_POST = {"/score_sequences", "/capture", "/patch_score"}
ALLOWED_GET = {"/health", "/model_info"}


class BridgeError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _require_text(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise BridgeError("INVALID_FIELD", f"{name} must be a string")
    if not allow_empty and not value:
        raise BridgeError("INVALID_FIELD", f"{name} must be non-empty")
    if len(value) > MAX_TEXT_CHARS:
        raise BridgeError("INPUT_TOO_LARGE", f"{name} exceeds {MAX_TEXT_CHARS} characters", 413)
    return value


def _require_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BridgeError("INVALID_FIELD", f"{name} must be an integer")
    return value


def _suffixes(payload: dict[str, Any]) -> list[str]:
    vals = payload.get("suffixes")
    if not isinstance(vals, list) or not vals or len(vals) > MAX_SUFFIXES:
        raise BridgeError("INVALID_FIELD", f"suffixes must be a non-empty list with <= {MAX_SUFFIXES} items")
    return [_require_text(x, f"suffixes[{i}]", allow_empty=False) for i, x in enumerate(vals)]


def _vector(payload: dict[str, Any]) -> list[float]:
    vals = payload.get("vector")
    if not isinstance(vals, list) or not vals or len(vals) > MAX_VECTOR_DIM:
        raise BridgeError("INVALID_FIELD", f"vector must be a non-empty numeric list with <= {MAX_VECTOR_DIM} values")
    out: list[float] = []
    for i, v in enumerate(vals):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise BridgeError("INVALID_FIELD", f"vector[{i}] must be numeric")
        f = float(v)
        if not math.isfinite(f):
            raise BridgeError("INVALID_FIELD", f"vector[{i}] must be finite")
        out.append(f)
    return out


def _scale(payload: dict[str, Any]) -> float:
    v = payload.get("scale", 1.0)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise BridgeError("INVALID_FIELD", "scale must be numeric")
    f = float(v)
    if not math.isfinite(f) or abs(f) > MAX_ABS_SCALE:
        raise BridgeError("INVALID_FIELD", f"abs(scale) must be <= {MAX_ABS_SCALE}")
    return f


class MockBackend:
    mode = "mock"

    def __init__(self) -> None:
        self.hidden_size = 8
        self.layers = 4

    def info(self) -> dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "mode": self.mode,
            "model_id": "mock/no-model",
            "model_revision_requested": "mock",
            "model_commit_resolved": "mock",
            "device": "cpu-mock",
            "device_name": "NO_MODEL_LOADED",
            "dtype": "mock",
            "torch_version": None,
            "transformers_version": None,
            "tokenizers_version": None,
            "quantization": "NONE",
            "python_version": platform.python_version(),
            "num_layers": self.layers,
            "hidden_size": self.hidden_size,
            "parameter_count": 0,
            "scientific_result": "NOT_ASSESSED",
        }

    @staticmethod
    def _seed(text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)

    def score_sequences(self, prompt: str, suffixes: list[str]) -> dict[str, Any]:
        scores = []
        for s in suffixes:
            seed = self._seed(prompt + "\x00" + s)
            score = -float(len(s)) - (seed % 1000) / 100000.0
            scores.append({"suffix": s, "logprob_sum": score, "token_count": max(1, len(s.split()))})
        return {"scores": scores, "backend": "mock"}

    def capture(self, text: str, layer: int, token_index: int) -> dict[str, Any]:
        if layer < 0 or layer >= self.layers:
            raise BridgeError("LAYER_OUT_OF_RANGE", f"layer must be in [0,{self.layers - 1}]")
        seed = self._seed(f"{layer}|{token_index}|{text}")
        vec = [((seed >> ((i % 8) * 8)) & 255) / 127.5 - 1.0 for i in range(self.hidden_size)]
        return {"layer": layer, "token_index_requested": token_index, "token_index_resolved": token_index, "vector": vec, "hidden_size": self.hidden_size, "backend": "mock"}

    def patch_score(self, prompt: str, suffixes: list[str], layer: int, token_index: int, vector: list[float], mode: str, scale: float) -> dict[str, Any]:
        if layer < 0 or layer >= self.layers:
            raise BridgeError("LAYER_OUT_OF_RANGE", f"layer must be in [0,{self.layers - 1}]")
        if len(vector) != self.hidden_size:
            raise BridgeError("VECTOR_DIM_MISMATCH", f"expected vector dim {self.hidden_size}, got {len(vector)}")
        if mode not in {"add", "replace"}:
            raise BridgeError("INVALID_FIELD", "mode must be 'add' or 'replace'")
        base = self.score_sequences(prompt, suffixes)["scores"]
        signed = sum((i + 1) * v for i, v in enumerate(vector)) * scale / 100.0
        out = []
        for idx, row in enumerate(base):
            effect = signed * (1.0 if idx % 2 == 0 else -1.0)
            out.append({**row, "logprob_sum": row["logprob_sum"] + effect})
        return {"scores": out, "layer": layer, "token_index_requested": token_index, "mode": mode, "scale": scale, "patch_vector_sha256": hashlib.sha256(json.dumps(vector, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest(), "patch_vector_l2_input": math.sqrt(sum(v*v for v in vector)), "backend": "mock"}


class RealBackend:
    mode = "real"

    def __init__(self, model_id: str, revision: str, device: str, dtype: str, expected_device_substring: str):
        # Lazy imports are intentional: GPU-lab mock validation must not import/load a model.
        try:
            import torch  # type: ignore
            import transformers  # type: ignore
            import tokenizers  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as exc:
            raise BridgeError("BACKEND_IMPORT_FAILED", f"real backend dependencies unavailable: {type(exc).__name__}: {exc}", 500) from exc

        self.torch = torch
        self.transformers = transformers
        self.tokenizers_version = tokenizers.__version__
        # This bridge never passes a quantization_config/load_in_4bit/load_in_8bit
        # argument. Expose that frozen loader fact explicitly for provenance gates.
        self.quantization = "NONE"
        if device == "cuda":
            if not torch.cuda.is_available():
                raise BridgeError("CUDA_UNAVAILABLE", "CUDA is required in real mode", 500)
            device_name = torch.cuda.get_device_name(0)
            if expected_device_substring and expected_device_substring.lower() not in device_name.lower():
                raise BridgeError(
                    "DEVICE_POLICY",
                    f"refusing real model load: expected CUDA device containing {expected_device_substring!r}, got {device_name!r}",
                    500,
                )
        elif device == "cpu":
            device_name = "CPU_DIAGNOSTIC_ONLY"
        else:
            raise BridgeError("DEVICE_POLICY", "diagnostic bridge requires device cuda or cpu", 500)
        dtype_map = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}
        if dtype not in dtype_map:
            raise BridgeError("INVALID_DTYPE", f"dtype must be one of {sorted(dtype_map)}", 500)
        self.device = torch.device(device)
        self.dtype = dtype_map[dtype]
        self.model_id = model_id
        self.revision = revision
        self.device_name = device_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            revision=revision,
            torch_dtype=self.dtype,
            trust_remote_code=False,
            low_cpu_mem_usage=False,
        ).to(self.device).eval()
        self.layers = self._decoder_layers()
        cfg = self.model.config
        self.hidden_size = int(getattr(cfg, "hidden_size", 0))
        if not self.hidden_size:
            raise BridgeError("MODEL_LAYOUT_UNSUPPORTED", "model config lacks hidden_size", 500)
        self.resolved_commit = str(getattr(cfg, "_commit_hash", None) or revision)
        self.parameter_count = sum(int(p.numel()) for p in self.model.parameters())
        self._lock = threading.Lock()

    def _decoder_layers(self):
        candidates = [
            ("model", "layers"),
            ("transformer", "h"),
            ("gpt_neox", "layers"),
        ]
        for parent_name, child_name in candidates:
            parent = getattr(self.model, parent_name, None)
            layers = getattr(parent, child_name, None) if parent is not None else None
            if layers is not None:
                return layers
        raise BridgeError("MODEL_LAYOUT_UNSUPPORTED", "cannot locate decoder block list", 500)

    def info(self) -> dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "mode": self.mode,
            "model_id": self.model_id,
            "model_revision_requested": self.revision,
            "model_commit_resolved": self.resolved_commit,
            "device": str(self.device),
            "device_name": self.device_name,
            "dtype": str(self.dtype),
            "torch_version": self.torch.__version__,
            "transformers_version": self.transformers.__version__,
            "tokenizers_version": self.tokenizers_version,
            "quantization": self.quantization,
            "python_version": platform.python_version(),
            "num_layers": len(self.layers),
            "hidden_size": self.hidden_size,
            "parameter_count": self.parameter_count,
            "scientific_result": "NOT_ASSESSED",
        }

    def _validate_layer(self, layer: int) -> None:
        if layer < 0 or layer >= len(self.layers):
            raise BridgeError("LAYER_OUT_OF_RANGE", f"layer must be in [0,{len(self.layers)-1}]")

    @staticmethod
    def _hidden_from_output(output):
        if hasattr(output, "shape"):
            return output, None
        if isinstance(output, tuple) and output and hasattr(output[0], "shape"):
            return output[0], ("tuple", output[1:])
        if isinstance(output, list) and output and hasattr(output[0], "shape"):
            return output[0], ("list", output[1:])
        raise BridgeError("MODEL_LAYOUT_UNSUPPORTED", "decoder block output is not a tensor/tuple/list", 500)

    @staticmethod
    def _rebuild_output(hidden, tail):
        if tail is None:
            return hidden
        typ, rest = tail
        if typ == "tuple":
            return (hidden, *rest)
        return [hidden, *rest]

    def _encode(self, text: str):
        batch = self.tokenizer(text, return_tensors="pt", add_special_tokens=True)
        return {k: v.to(self.device) for k, v in batch.items()}

    def _resolve_index(self, idx: int, seq_len: int) -> int:
        resolved = idx if idx >= 0 else seq_len + idx
        if resolved < 0 or resolved >= seq_len:
            raise BridgeError("TOKEN_INDEX_OUT_OF_RANGE", f"token_index {idx} invalid for sequence length {seq_len}")
        return resolved

    def capture(self, text: str, layer: int, token_index: int) -> dict[str, Any]:
        self._validate_layer(layer)
        with self._lock, self.torch.inference_mode():
            batch = self._encode(text)
            seq_len = int(batch["input_ids"].shape[1])
            resolved = self._resolve_index(token_index, seq_len)
            captured: dict[str, Any] = {}

            def hook(_module, _inp, output):
                hidden, _tail = self._hidden_from_output(output)
                captured["vector"] = hidden[0, resolved, :].detach().float().cpu()

            handle = self.layers[layer].register_forward_hook(hook)
            try:
                self.model(**batch, use_cache=True)
            finally:
                handle.remove()
            vec = captured.get("vector")
            if vec is None:
                raise BridgeError("CAPTURE_FAILED", "forward hook did not capture activation", 500)
            return {
                "layer": layer,
                "token_index_requested": token_index,
                "token_index_resolved": resolved,
                "sequence_length": seq_len,
                "hidden_size": self.hidden_size,
                "vector": vec.tolist(),
                "backend": "real",
            }

    def _continuation_ids(self, prompt: str, suffix: str):
        prompt_ids = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=True)["input_ids"][0]
        full_ids = self.tokenizer(prompt + suffix, return_tensors="pt", add_special_tokens=True)["input_ids"][0]
        n = int(prompt_ids.numel())
        if int(full_ids.numel()) <= n or not self.torch.equal(full_ids[:n], prompt_ids):
            raise BridgeError(
                "BOUNDARY_TOKENIZATION_MISMATCH",
                "tokenization of prompt is not an exact prefix of prompt+suffix; freeze a serialization with a stable token boundary",
            )
        return prompt_ids, full_ids

    def _score_one(self, prompt: str, suffix: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
        # Prefix-stable exact teacher forcing: compute the scoring prompt once,
        # optionally patch only that prompt forward, then feed gold continuation
        # tokens sequentially through the returned KV cache. This makes the
        # frozen RESET-boundary representation independent of suffix tensor shape.
        prompt_ids_cpu, full_ids_cpu = self._continuation_ids(prompt, suffix)
        prompt_len = int(prompt_ids_cpu.numel())
        continuation_cpu = full_ids_cpu[prompt_len:]
        if int(continuation_cpu.numel()) <= 0:
            raise BridgeError("EMPTY_CONTINUATION", "suffix must contain at least one token")
        prompt_ids = prompt_ids_cpu.unsqueeze(0).to(self.device)
        attention_mask = self.torch.ones_like(prompt_ids)
        handles = []
        resolved_patch_idx = None
        if patch is not None:
            layer = patch["layer"]
            self._validate_layer(layer)
            resolved_patch_idx = self._resolve_index(patch["token_index"], prompt_len)
            vec = self.torch.tensor(patch["vector"], dtype=self.dtype, device=self.device)
            if int(vec.numel()) != self.hidden_size:
                raise BridgeError("VECTOR_DIM_MISMATCH", f"expected vector dim {self.hidden_size}, got {int(vec.numel())}")
            mode = patch["mode"]
            scale = float(patch["scale"])

            def hook(_module, _inp, output):
                hidden, tail = self._hidden_from_output(output)
                modified = hidden.clone()
                if mode == "add":
                    modified[:, resolved_patch_idx, :] = modified[:, resolved_patch_idx, :] + scale * vec
                else:
                    modified[:, resolved_patch_idx, :] = scale * vec
                return self._rebuild_output(modified, tail)

            handles.append(self.layers[layer].register_forward_hook(hook))
        try:
            with self.torch.inference_mode():
                out = self.model(input_ids=prompt_ids, attention_mask=attention_mask, use_cache=True)
        finally:
            for handle in handles:
                handle.remove()
        past = out.past_key_values
        next_logits = out.logits[:, -1, :].float()
        score = 0.0
        cont = continuation_cpu.tolist()
        with self.torch.inference_mode():
            for j, token_id in enumerate(cont):
                logp = self.torch.log_softmax(next_logits, dim=-1)
                score += float(logp[0, int(token_id)].item())
                if j + 1 < len(cont):
                    step_ids = self.torch.tensor([[int(token_id)]], dtype=prompt_ids.dtype, device=self.device)
                    attention_mask = self.torch.ones((1, prompt_len + j + 1), dtype=prompt_ids.dtype, device=self.device)
                    out = self.model(input_ids=step_ids, attention_mask=attention_mask,
                                     past_key_values=past, use_cache=True)
                    past = out.past_key_values
                    next_logits = out.logits[:, -1, :].float()
        return {"suffix": suffix, "logprob_sum": score, "token_count": len(cont),
                "patch_token_index_resolved": resolved_patch_idx}

    def score_sequences(self, prompt: str, suffixes: list[str]) -> dict[str, Any]:
        with self._lock:
            return {"scores": [self._score_one(prompt, s) for s in suffixes], "backend": "real"}

    def patch_score(self, prompt: str, suffixes: list[str], layer: int, token_index: int, vector: list[float], mode: str, scale: float) -> dict[str, Any]:
        self._validate_layer(layer)
        if len(vector) != self.hidden_size:
            raise BridgeError("VECTOR_DIM_MISMATCH", f"expected vector dim {self.hidden_size}, got {len(vector)}")
        if mode not in {"add", "replace"}:
            raise BridgeError("INVALID_FIELD", "mode must be 'add' or 'replace'")
        patch = {"layer": layer, "token_index": token_index, "vector": vector, "mode": mode, "scale": scale}
        with self._lock:
            rows = [self._score_one(prompt, s, patch=patch) for s in suffixes]
        return {"scores": rows, "layer": layer, "token_index_requested": token_index, "mode": mode, "scale": scale, "patch_vector_sha256": hashlib.sha256(json.dumps(vector, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest(), "patch_vector_l2_input": math.sqrt(sum(v*v for v in vector)), "backend": "real"}


class BridgeApplication:
    def __init__(self, backend: Any, token: str):
        if not token:
            raise ValueError("auth token must be non-empty")
        self.backend = backend
        self.token = token.encode("utf-8")
        self.started_at = time.time()

    def authorized(self, header: str | None) -> bool:
        if not header or not header.startswith("Bearer "):
            return False
        supplied = header[7:].encode("utf-8")
        return hmac.compare_digest(self.token, supplied)

    def get(self, path: str) -> dict[str, Any]:
        if path == "/health":
            info = self.backend.info()
            return {
                "ok": True,
                "api_version": API_VERSION,
                "mode": info["mode"],
                "model_id": info["model_id"],
                "device_name": info["device_name"],
                "uptime_seconds": round(time.time() - self.started_at, 3),
                "scientific_result": "NOT_ASSESSED",
            }
        if path == "/model_info":
            return self.backend.info()
        raise BridgeError("NOT_FOUND", "unknown endpoint", 404)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise BridgeError("INVALID_JSON", "JSON body must be an object")
        if path == "/score_sequences":
            prompt = _require_text(payload.get("prompt"), "prompt")
            suffixes = _suffixes(payload)
            return self.backend.score_sequences(prompt, suffixes)
        if path == "/capture":
            text = _require_text(payload.get("text"), "text")
            layer = _require_int(payload.get("layer"), "layer")
            token_index = _require_int(payload.get("token_index", -1), "token_index")
            return self.backend.capture(text, layer, token_index)
        if path == "/patch_score":
            prompt = _require_text(payload.get("prompt"), "prompt")
            suffixes = _suffixes(payload)
            layer = _require_int(payload.get("layer"), "layer")
            token_index = _require_int(payload.get("token_index", -1), "token_index")
            vector = _vector(payload)
            mode = payload.get("mode", "add")
            if mode not in {"add", "replace"}:
                raise BridgeError("INVALID_FIELD", "mode must be 'add' or 'replace'")
            scale = _scale(payload)
            return self.backend.patch_score(prompt, suffixes, layer, token_index, vector, mode, scale)
        raise BridgeError("NOT_FOUND", "unknown endpoint", 404)


def make_handler(app: BridgeApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PlanCarryWhitebox/1"

        def log_message(self, fmt: str, *args: Any) -> None:
            # Never log Authorization headers or request bodies.
            sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

        def _json(self, status: int, obj: dict[str, Any]) -> None:
            raw = (json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _auth(self) -> bool:
            if app.authorized(self.headers.get("Authorization")):
                return True
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": {"code": "UNAUTHORIZED", "message": "Bearer token required"}})
            return False

        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ALLOWED_GET:
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"code": "NOT_FOUND", "message": "unknown endpoint"}})
                return
            if not self._auth():
                return
            try:
                self._json(HTTPStatus.OK, {"ok": True, "result": app.get(self.path)})
            except BridgeError as exc:
                self._json(exc.status, {"ok": False, "error": {"code": exc.code, "message": exc.message}})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ALLOWED_POST:
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"code": "NOT_FOUND", "message": "unknown endpoint"}})
                return
            if not self._auth():
                return
            length_s = self.headers.get("Content-Length")
            try:
                length = int(length_s or "0")
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "INVALID_LENGTH", "message": "invalid Content-Length"}})
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > MAX_BODY_BYTES else HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "INVALID_LENGTH", "message": f"body must be 1..{MAX_BODY_BYTES} bytes"}})
                return
            try:
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
                result = app.post(self.path, payload)
                self._json(HTTPStatus.OK, {"ok": True, "result": result, "provenance": app.backend.info()})
            except json.JSONDecodeError:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "INVALID_JSON", "message": "body must be valid UTF-8 JSON"}})
            except BridgeError as exc:
                self._json(exc.status, {"ok": False, "error": {"code": exc.code, "message": exc.message}})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}})

    return Handler


def make_server(app: BridgeApplication, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(app))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--mock", action="store_true", help="no-model backend for protocol tests only")
    p.add_argument("--allow-remote", action="store_true", help="required to bind a non-loopback host")
    p.add_argument("--model-id")
    p.add_argument("--revision")
    p.add_argument("--device", default="cuda")
    p.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"])
    p.add_argument("--expected-device-substring", default="RTX 3050")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
        print("Refusing non-loopback bind without --allow-remote", file=sys.stderr)
        return 2
    token = os.environ.get("PLANCARRY_WHITEBOX_TOKEN", "")
    if args.mock:
        token = token or "mock-local-token"
        backend: Any = MockBackend()
    else:
        if not token:
            print("PLANCARRY_WHITEBOX_TOKEN is required in real mode", file=sys.stderr)
            return 2
        if not args.model_id or not args.revision:
            print("--model-id and --revision are required in real mode", file=sys.stderr)
            return 2
        try:
            backend = RealBackend(args.model_id, args.revision, args.device, args.dtype, args.expected_device_substring)
        except BridgeError as exc:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
            return 2
    app = BridgeApplication(backend, token)
    server = make_server(app, args.host, args.port)
    bound_host, bound_port = server.server_address[:2]
    # Token is deliberately never printed.
    print(json.dumps({"event": "bridge_started", "api_version": API_VERSION, "host": bound_host, "port": bound_port, "mode": backend.mode, "model_info": backend.info()}, sort_keys=True), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
