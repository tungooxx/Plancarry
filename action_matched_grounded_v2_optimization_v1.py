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


class OptimizedPersistentTokenSession(legacy.PersistentTokenSession):
    """Drop-in session: exact batch-1 math, concurrent independent CUDA streams."""

    def score_candidates_legacy(self, suffix_ids_by_command: Mapping[str, Sequence[int]]):
        return super().score_candidates(suffix_ids_by_command)

    def _score_suffix_async(self, ids: Sequence[int], stream: Any):
        """Launch one exact legacy-shaped batch-1 candidate chain on one CUDA stream."""
        torch = legacy._torch()
        seq = [int(x) for x in ids]
        if not seq:
            raise legacy.SessionContractError("candidate suffix must be nonempty")
        with torch.cuda.stream(stream):
            local_past = legacy.clone_cache(self.past_key_values)
            local_logits = self.next_logits.detach().clone()
            local_len = int(self.context_len)
            terms = []
            for j, token_id in enumerate(seq):
                lp = torch.log_softmax(local_logits.float(), dim=-1)
                terms.append(lp[0, token_id])
                if j + 1 < len(seq):
                    local_past, local_logits = self._step_model(token_id, local_past, local_len)
                    local_len += 1
        return terms

    def score_candidates(self, suffix_ids_by_command: Mapping[str, Sequence[int]]):
        """Overlap candidates without changing the legacy batch-size-1 numerical geometry."""
        torch = legacy._torch()
        self._assert_open()
        if not suffix_ids_by_command:
            raise legacy.SessionContractError("candidate map must be nonempty")
        commands = sorted(str(x) for x in suffix_ids_by_command)
        seqs = {c:[int(x) for x in suffix_ids_by_command[c]] for c in commands}
        if any(not ids for ids in seqs.values()):
            raise legacy.SessionContractError("candidate suffix must be nonempty")
        for idx,(key,value) in enumerate(cache_layers(self.past_key_values)):
            if key.ndim < 3 or value.ndim < 3 or int(key.shape[0]) != 1 or int(value.shape[0]) != 1:
                raise legacy.SessionContractError(f"optimized candidate scoring requires batch-1 cache at layer {idx}")
        # CPU and non-CUDA callers retain the byte-for-byte legacy execution path.
        if getattr(self.device, 'type', str(self.device)) != 'cuda' or not torch.cuda.is_available():
            return super().score_candidates(suffix_ids_by_command)
        before = legacy.cache_digest(self.past_key_values)
        rows = {}
        caller_stream = torch.cuda.current_stream(self.device)
        for off in range(0, len(commands), MAX_CANDIDATE_STREAMS):
            chunk = commands[off:off + MAX_CANDIDATE_STREAMS]
            launched = []
            for command in chunk:
                stream = torch.cuda.Stream(device=self.device)
                stream.wait_stream(caller_stream)
                terms = self._score_suffix_async(seqs[command], stream)
                launched.append((command, stream, terms))
            # All candidate chains above were submitted before any synchronization,
            # so the GPU may overlap them while every individual chain stays batch-1.
            for command, stream, terms in launched:
                stream.synchronize()
                ids = seqs[command]
                # Match legacy arithmetic exactly: token scalar -> Python float,
                # then left-to-right Python float addition in token order.
                total = 0.0
                for term in terms:
                    total += float(term.item())
                n = len(ids)
                rows[command] = legacy.CandidateScore(command, legacy.token_ids_sha256(ids), n, total, total / n)
        after = legacy.cache_digest(self.past_key_values)
        if before != after or legacy.cache_seq_len(self.past_key_values) != self.context_len:
            raise legacy.SessionContractError("candidate scoring mutated live KV session")
        best = sorted(rows.values(), key=lambda r: (-r.mean_logprob, r.command))[0]
        return best.command, rows


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
            captured[_layer] = hidden[:, resolved, :].detach().clone()
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
