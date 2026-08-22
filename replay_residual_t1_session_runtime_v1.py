"""Pre-outcome exact-token persistent-session runtime for ReplayResidual T1.

Engineering utility only.  It contains no ALFWorld population access, no T1
statistics, and no scientific decision logic.  The core contract is:
  * caller supplies exact token IDs (never text to be jointly retokenized),
  * optional residual intervention fires exactly once on the reset-prefix
    forward and its hook is then permanently removed,
  * later committed action/observation token IDs extend the SAME KV cache,
  * candidate scoring clones the cache and therefore cannot mutate the live
    session,
  * suffix scores are arithmetic-mean FP32 token log probabilities with
    deterministic lexical command tie-break.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from replay_residual_kv_mediation_v1 import cache_layers, rebuild_like

T1_PREREG_SHA256 = "77a7d9c9ee597551da8e8ef0b8a2c79038990968e3f62735ff90ed8c9c7d55e2"
GAP_MATRIX_SHA256 = "8cd22aff1d89b7a54eaa07b833dc75ecc1286f6938e39ee72256dd9705cba895"
V21_CONTRACT_SHA256 = "83370fbfc65c4818ada159a0e3c83cf778b88ed02f964bcf7887e5cea3843158"
ENGINEERING_EQUIV_ATOL = 1e-6


class SessionContractError(RuntimeError):
    pass


def _torch():
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SessionContractError("torch is required") from exc
    return torch


def canonical_json_sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def token_ids_sha256(ids: Sequence[int]) -> str:
    return canonical_json_sha256([int(x) for x in ids])


def vector_sha256_fp32(vector: Any) -> str:
    torch = _torch()
    t = torch.as_tensor(vector, dtype=torch.float32).detach().contiguous().cpu()
    payload = t.view(torch.uint8).numpy().tobytes()
    h = hashlib.sha256()
    h.update(str(tuple(t.shape)).encode())
    h.update(payload)
    return h.hexdigest()


def _tensor_bytes(t: Any) -> bytes:
    torch = _torch()
    x = t.detach().contiguous().cpu()
    return x.view(torch.uint8).numpy().tobytes()


def cache_digest(cache: Any) -> str:
    h = hashlib.sha256()
    for idx, (key, value) in enumerate(cache_layers(cache)):
        for tag, tensor in (("k", key), ("v", value)):
            h.update(f"{idx}:{tag}:{tuple(tensor.shape)}:{tensor.dtype}".encode())
            h.update(_tensor_bytes(tensor))
    return h.hexdigest()


def cache_seq_len(cache: Any) -> int:
    layers = cache_layers(cache)
    n = int(layers[0][0].shape[-2])
    if n <= 0:
        raise SessionContractError("cache sequence length must be positive")
    for key, value in layers:
        if int(key.shape[-2]) != n or int(value.shape[-2]) != n:
            raise SessionContractError("cache layer sequence-length mismatch")
    return n


def clone_cache(cache: Any) -> Any:
    layers = tuple((k.detach().clone(), v.detach().clone()) for k, v in cache_layers(cache))
    return rebuild_like(cache, layers)


def _layer_stack(model: Any) -> Any:
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    if hasattr(model, "layers"):
        return model.layers
    raise SessionContractError("model must expose .model.layers or .layers")


def _model_device(model: Any) -> Any:
    try:
        return next(model.parameters()).device
    except Exception as exc:
        raise SessionContractError("cannot infer model device") from exc


def _hidden_from_output(output: Any) -> tuple[Any, tuple[Any, ...] | None]:
    if isinstance(output, tuple):
        if not output:
            raise SessionContractError("empty layer output tuple")
        return output[0], tuple(output[1:])
    return output, None


def _rebuild_output(hidden: Any, tail: tuple[Any, ...] | None) -> Any:
    return (hidden, *tail) if tail is not None else hidden


def capture_activation_ids(model: Any, prefix_ids: Sequence[int], layer: int, token_index: int = -1) -> Any:
    """Capture one activation from exact caller-supplied IDs without intervention."""
    torch = _torch()
    ids = [int(x) for x in prefix_ids]
    if not ids:
        raise SessionContractError("prefix_ids must be nonempty")
    layers = _layer_stack(model)
    if layer < 0 or layer >= len(layers):
        raise SessionContractError("layer outside model")
    resolved = token_index if token_index >= 0 else len(ids) + token_index
    if resolved < 0 or resolved >= len(ids):
        raise SessionContractError("token_index outside prefix")
    captured: dict[str, Any] = {}
    calls = 0

    def hook(_module: Any, _inp: Any, output: Any) -> Any:
        nonlocal calls
        calls += 1
        hidden, _tail = _hidden_from_output(output)
        captured["vector"] = hidden[:, resolved, :].detach().clone()
        return output

    handle = layers[layer].register_forward_hook(hook)
    device = _model_device(model)
    input_ids = torch.tensor([ids], dtype=torch.long, device=device)
    mask = torch.ones_like(input_ids)
    try:
        with torch.inference_mode():
            model(input_ids=input_ids, attention_mask=mask, use_cache=False)
    finally:
        handle.remove()
    if calls != 1 or "vector" not in captured:
        raise SessionContractError(f"capture hook count must equal 1, got {calls}")
    return captured["vector"][0]


@dataclass(frozen=True)
class CandidateScore:
    command: str
    suffix_token_ids_sha256: str
    token_count: int
    logprob_sum: float
    mean_logprob: float


class PersistentTokenSession:
    """One exact-token causal session with immutable reset-prefix provenance."""

    def __init__(
        self,
        model: Any,
        reset_prefix_ids: Sequence[int],
        *,
        layer: int,
        vector: Any | None,
        mode: str = "add",
        scale: float = 1.0,
    ) -> None:
        torch = _torch()
        ids = [int(x) for x in reset_prefix_ids]
        if not ids:
            raise SessionContractError("reset_prefix_ids must be nonempty")
        if mode not in {"add", "replace"}:
            raise SessionContractError("mode must be add or replace")
        if not math.isfinite(float(scale)):
            raise SessionContractError("scale must be finite")
        layers = _layer_stack(model)
        if layer < 0 or layer >= len(layers):
            raise SessionContractError("layer outside model")
        self.model = model
        self.layers = layers
        self.device = _model_device(model)
        self.layer = int(layer)
        self.mode = mode
        self.scale = float(scale)
        self.reset_prefix_ids = tuple(ids)
        self.reset_prefix_sha256 = token_ids_sha256(ids)
        self.hook_count = 0
        self.closed = False
        self.append_events: list[dict[str, Any]] = []
        self.vector_sha256 = None if vector is None else vector_sha256_fp32(vector)
        patch_vec = None
        if vector is not None:
            patch_vec = torch.as_tensor(vector, device=self.device)
            if patch_vec.ndim != 1:
                patch_vec = patch_vec.reshape(-1)
        handle = None
        if patch_vec is not None:
            expected_hidden = int(getattr(getattr(model, "config", None), "hidden_size", patch_vec.numel()))
            if int(patch_vec.numel()) != expected_hidden:
                raise SessionContractError(f"vector dim mismatch expected={expected_hidden} got={int(patch_vec.numel())}")

            def hook(_module: Any, _inp: Any, output: Any) -> Any:
                self.hook_count += 1
                hidden, tail = _hidden_from_output(output)
                vec = patch_vec.to(dtype=hidden.dtype, device=hidden.device)
                modified = hidden.clone()
                if self.mode == "add":
                    modified[:, -1, :] = modified[:, -1, :] + self.scale * vec
                else:
                    modified[:, -1, :] = self.scale * vec
                return _rebuild_output(modified, tail)

            handle = layers[layer].register_forward_hook(hook)
        input_ids = torch.tensor([ids], dtype=torch.long, device=self.device)
        attention_mask = torch.ones_like(input_ids)
        try:
            with torch.inference_mode():
                out = model(input_ids=input_ids, attention_mask=attention_mask, use_cache=True)
        finally:
            if handle is not None:
                handle.remove()
        expected_hooks = 0 if patch_vec is None else 1
        if self.hook_count != expected_hooks:
            raise SessionContractError(f"reset hook count mismatch expected={expected_hooks} got={self.hook_count}")
        if not hasattr(out, "past_key_values") or out.past_key_values is None:
            raise SessionContractError("model did not return past_key_values")
        self.past_key_values = out.past_key_values
        self.next_logits = out.logits[:, -1, :].float().detach()
        self.context_len = len(ids)
        if cache_seq_len(self.past_key_values) != self.context_len:
            raise SessionContractError("initial cache length does not equal exact reset prefix length")
        self.initial_cache_sha256 = cache_digest(self.past_key_values)
        self.session_id_hash = canonical_json_sha256({
            "reset_prefix_sha256": self.reset_prefix_sha256,
            "layer": self.layer,
            "mode": self.mode,
            "scale": self.scale,
            "vector_sha256": self.vector_sha256,
            "initial_cache_sha256": self.initial_cache_sha256,
            "t1_prereg_sha256": T1_PREREG_SHA256,
        })

    def _assert_open(self) -> None:
        if self.closed:
            raise SessionContractError("session is closed")

    def provenance(self) -> dict[str, Any]:
        return {
            "t1_prereg_sha256": T1_PREREG_SHA256,
            "gap_matrix_sha256": GAP_MATRIX_SHA256,
            "v2_1_contract_sha256": V21_CONTRACT_SHA256,
            "reset_prefix_sha256": self.reset_prefix_sha256,
            "layer": self.layer,
            "mode": self.mode,
            "scale": self.scale,
            "injected_vector_sha256": self.vector_sha256,
            "hook_count": self.hook_count,
            "session_id_hash": self.session_id_hash,
            "context_len": self.context_len,
            "cache_sha256": cache_digest(self.past_key_values),
            "append_event_count": len(self.append_events),
        }

    def _step_model(self, token_id: int, past: Any, context_len: int) -> tuple[Any, Any]:
        torch = _torch()
        step = torch.tensor([[int(token_id)]], dtype=torch.long, device=self.device)
        mask = torch.ones((1, int(context_len) + 1), dtype=torch.long, device=self.device)
        with torch.inference_mode():
            out = self.model(input_ids=step, attention_mask=mask, past_key_values=past, use_cache=True)
        return out.past_key_values, out.logits[:, -1, :].float().detach()

    def score_suffix_ids(self, suffix_ids: Sequence[int]) -> tuple[float, int]:
        """Score exact suffix IDs without mutating the live session cache."""
        torch = _torch()
        self._assert_open()
        ids = [int(x) for x in suffix_ids]
        if not ids:
            raise SessionContractError("candidate suffix must be nonempty")
        before = cache_digest(self.past_key_values)
        local_past = clone_cache(self.past_key_values)
        local_logits = self.next_logits.detach().clone()
        local_len = int(self.context_len)
        total = 0.0
        for j, token_id in enumerate(ids):
            lp = torch.log_softmax(local_logits.float(), dim=-1)
            total += float(lp[0, token_id].item())
            if j + 1 < len(ids):
                local_past, local_logits = self._step_model(token_id, local_past, local_len)
                local_len += 1
        after = cache_digest(self.past_key_values)
        if before != after or cache_seq_len(self.past_key_values) != self.context_len:
            raise SessionContractError("candidate scoring mutated live KV session")
        return total, len(ids)

    def score_candidates(self, suffix_ids_by_command: Mapping[str, Sequence[int]]) -> tuple[str, dict[str, CandidateScore]]:
        self._assert_open()
        if not suffix_ids_by_command:
            raise SessionContractError("candidate map must be nonempty")
        rows: dict[str, CandidateScore] = {}
        for command in sorted(str(x) for x in suffix_ids_by_command):
            ids = [int(x) for x in suffix_ids_by_command[command]]
            total, n = self.score_suffix_ids(ids)
            rows[command] = CandidateScore(command, token_ids_sha256(ids), n, total, total / n)
        best = sorted(rows.values(), key=lambda r: (-r.mean_logprob, r.command))[0]
        return best.command, rows

    def append_ids(self, ids: Sequence[int], *, event: str) -> dict[str, Any]:
        """Commit exact IDs to the live session, carrying the same cache forward."""
        torch = _torch()
        self._assert_open()
        seq = [int(x) for x in ids]
        if not seq:
            raise SessionContractError("append sequence must be nonempty")
        start_len = self.context_len
        total = 0.0
        for token_id in seq:
            lp = torch.log_softmax(self.next_logits.float(), dim=-1)
            total += float(lp[0, token_id].item())
            self.past_key_values, self.next_logits = self._step_model(token_id, self.past_key_values, self.context_len)
            self.context_len += 1
        if cache_seq_len(self.past_key_values) != self.context_len:
            raise SessionContractError("live KV length drift after append")
        if self.vector_sha256 is not None and self.hook_count != 1:
            raise SessionContractError("intervention hook fired after reset prefix")
        row = {
            "event": str(event),
            "token_ids_sha256": token_ids_sha256(seq),
            "token_count": len(seq),
            "mean_logprob": total / len(seq),
            "context_len_before": start_len,
            "context_len_after": self.context_len,
            "cache_sha256_after": cache_digest(self.past_key_values),
            "hook_count": self.hook_count,
        }
        self.append_events.append(row)
        return row

    def choose_and_commit(self, suffix_ids_by_command: Mapping[str, Sequence[int]], *, event: str = "ACTION") -> tuple[str, dict[str, CandidateScore], dict[str, Any]]:
        command, scores = self.score_candidates(suffix_ids_by_command)
        committed = self.append_ids(suffix_ids_by_command[command], event=event)
        return command, scores, committed

    def close(self) -> dict[str, Any]:
        self._assert_open()
        self.closed = True
        return self.provenance()
