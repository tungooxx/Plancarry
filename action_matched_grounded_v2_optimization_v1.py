#!/usr/bin/env python3
"""Engineering-only GPU batching helpers for Grounded ActionMatched-v2.

This module leaves the frozen ReplayResidual persistent-session runtime byte-identical.
It subclasses that runtime only to overlap conditionally-independent batch-size-1
candidate suffix chains on CUDA streams and provides observation-only multi-layer activation capture.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence

import replay_residual_t1_session_runtime_v1 as legacy
from replay_residual_kv_mediation_v1 import cache_layers

ENGINEERING_EQUIV_ATOL = 1e-6
MAX_CANDIDATE_STREAMS = 4


class TechnicalMemoryError(RuntimeError):
    """Engineering-only GPU memory failure; never a scientific ineligibility."""


MINIMUM_FREE_VRAM_MB = 768.0

def _device_index(device: Any) -> int | None:
    idx=getattr(device, "index", None)
    return idx if idx is not None else None

def reset_cuda_peak_memory(device: Any) -> None:
    torch=legacy._torch()
    if getattr(device, "type", str(device)) != "cuda" or not torch.cuda.is_available():
        return
    torch.cuda.synchronize(device)
    torch.cuda.reset_peak_memory_stats(device)

def cuda_memory_snapshot(device: Any) -> dict[str, float | bool]:
    torch=legacy._torch()
    if getattr(device, "type", str(device)) != "cuda" or not torch.cuda.is_available():
        return {"cuda": False, "allocated_mb": 0.0, "reserved_mb": 0.0, "peak_allocated_mb": 0.0, "peak_reserved_mb": 0.0, "free_mb": 0.0, "total_mb": 0.0, "peak_reserved_headroom_mb": 0.0}
    torch.cuda.synchronize(device)
    free_b,total_b=torch.cuda.mem_get_info(device)
    mib=1024.0*1024.0
    peak_reserved=float(torch.cuda.max_memory_reserved(device))/mib
    total=float(total_b)/mib
    return {
      "cuda": True,
      "allocated_mb": float(torch.cuda.memory_allocated(device))/mib,
      "reserved_mb": float(torch.cuda.memory_reserved(device))/mib,
      "peak_allocated_mb": float(torch.cuda.max_memory_allocated(device))/mib,
      "peak_reserved_mb": peak_reserved,
      "free_mb": float(free_b)/mib,
      "total_mb": total,
      "peak_reserved_headroom_mb": total-peak_reserved,
    }

def require_cuda_headroom(device: Any, *, minimum_free_mb: float = MINIMUM_FREE_VRAM_MB) -> dict[str, float | bool]:
    snap=cuda_memory_snapshot(device)
    if not snap["cuda"]:
        return snap
    current=float(snap["free_mb"]); peak_headroom=float(snap["peak_reserved_headroom_mb"]); need=float(minimum_free_mb)
    if current < need or peak_headroom < need:
        raise TechnicalMemoryError(
          f"CUDA_MEMORY_HEADROOM_UNSAFE:free_mb={current:.3f}:peak_reserved_headroom_mb={peak_headroom:.3f}:required_mb={need:.3f}"
        )
    return snap


class OptimizedPersistentTokenSession(legacy.PersistentTokenSession):
    """Memory-safe drop-in session preserving exact legacy candidate arithmetic."""

    def score_candidates_legacy(self, suffix_ids_by_command: Mapping[str, Sequence[int]]):
        return super().score_candidates(suffix_ids_by_command)

    def score_candidates(self, suffix_ids_by_command: Mapping[str, Sequence[int]]):
        # The rejected stream implementation cloned several full KV caches concurrently
        # and exhausted 8 GiB cards. Preserve exact legacy sequential batch-1 geometry,
        # but retain an explicit fail-closed cache-shape guard before delegation.
        self._assert_open()
        if not suffix_ids_by_command:
            raise legacy.SessionContractError("candidate map must be nonempty")
        if any(not [int(x) for x in suffix_ids_by_command[c]] for c in suffix_ids_by_command):
            raise legacy.SessionContractError("candidate suffix must be nonempty")
        for idx,(key,value) in enumerate(cache_layers(self.past_key_values)):
            if key.ndim < 3 or value.ndim < 3 or int(key.shape[0]) != 1 or int(value.shape[0]) != 1:
                raise legacy.SessionContractError(f"optimized candidate scoring requires batch-1 cache at layer {idx}")
        return super().score_candidates(suffix_ids_by_command)

def capture_activation_ids_multi(model: Any, prefix_ids: Sequence[int], layers_requested: Sequence[int], token_index: int = -1) -> dict[int, Any]:
    torch = legacy._torch()
    ids = [int(x) for x in prefix_ids]
    if not ids:
        raise legacy.SessionContractError("prefix_ids must be nonempty")
    stack = legacy._layer_stack(model)
    requested = [int(x) for x in layers_requested]
    if not requested or len(set(requested)) != len(requested):
        raise legacy.SessionContractError("layers_requested must be nonempty and unique")
    if any(layer < 0 or layer >= len(stack) for layer in requested):
        raise legacy.SessionContractError("layer outside model")
    resolved = token_index if token_index >= 0 else len(ids) + token_index
    if resolved < 0 or resolved >= len(ids):
        raise legacy.SessionContractError("token_index outside prefix")
    captured, calls, handles = {}, {layer: 0 for layer in requested}, []
    for layer in requested:
        def hook(_module: Any, _inp: Any, output: Any, *, _layer: int = layer):
            calls[_layer] += 1
            hidden, _tail = legacy._hidden_from_output(output)
            captured[_layer] = hidden[:, resolved, :].detach().float().cpu().clone()
            return output
        handles.append(stack[layer].register_forward_hook(hook))
    device = legacy._model_device(model)
    input_ids = torch.tensor([ids], dtype=torch.long, device=device)
    mask = torch.ones_like(input_ids)
    try:
        with torch.inference_mode():
            model(input_ids=input_ids, attention_mask=mask, use_cache=False)
    finally:
        for handle in handles:
            handle.remove()
    if any(calls[layer] != 1 for layer in requested) or any(layer not in captured for layer in requested):
        raise legacy.SessionContractError(f"multi-layer capture hook counts invalid: {calls}")
    return {layer: captured[layer][0] for layer in requested}
