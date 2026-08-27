#!/usr/bin/env python3
"""Engineering-only GPU batching helpers for Grounded ActionMatched-v2.

This module leaves the frozen ReplayResidual persistent-session runtime byte-identical.
It subclasses that runtime only to batch conditionally-independent candidate suffix
scoring and provides observation-only multi-layer activation capture.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence

import replay_residual_t1_session_runtime_v1 as legacy
from replay_residual_kv_mediation_v1 import cache_layers, rebuild_like

ENGINEERING_EQUIV_ATOL = 1e-6
MAX_CANDIDATE_BATCH = 8


def repeat_cache_batch(cache: Any, batch_size: int) -> Any:
    if not isinstance(batch_size, int) or batch_size <= 0:
        raise legacy.SessionContractError("batch_size must be a positive integer")
    layers = []
    for idx, (key, value) in enumerate(cache_layers(cache)):
        if key.ndim < 3 or value.ndim < 3 or int(key.shape[0]) != 1 or int(value.shape[0]) != 1:
            raise legacy.SessionContractError(f"candidate batching requires batch-1 cache at layer {idx}")
        layers.append((key.detach().repeat_interleave(batch_size, dim=0).clone(),
                       value.detach().repeat_interleave(batch_size, dim=0).clone()))
    return rebuild_like(cache, tuple(layers))


class OptimizedPersistentTokenSession(legacy.PersistentTokenSession):
    """Drop-in persistent session with exact candidate-batch scoring."""

    def score_candidates_legacy(self, suffix_ids_by_command: Mapping[str, Sequence[int]]):
        return super().score_candidates(suffix_ids_by_command)

    def _step_model_batch(self, token_ids: Sequence[int], past: Any, context_len: int):
        torch = legacy._torch()
        ids = [int(x) for x in token_ids]
        if not ids:
            raise legacy.SessionContractError("batched token_ids must be nonempty")
        step = torch.tensor(ids, dtype=torch.long, device=self.device).reshape(len(ids), 1)
        mask = torch.ones((len(ids), int(context_len) + 1), dtype=torch.long, device=self.device)
        with torch.inference_mode():
            out = self.model(input_ids=step, attention_mask=mask, past_key_values=past, use_cache=True)
        return out.past_key_values, out.logits[:, -1, :].float().detach()

    def _score_candidate_batch(self, commands: Sequence[str], suffix_ids_by_command: Mapping[str, Sequence[int]]):
        """Score one bounded candidate batch from the identical frozen live cache."""
        torch = legacy._torch()
        names = [str(x) for x in commands]
        seqs = [[int(x) for x in suffix_ids_by_command[c]] for c in names]
        if not names or any(not ids for ids in seqs):
            raise legacy.SessionContractError("candidate suffix must be nonempty")
        local_past = repeat_cache_batch(self.past_key_values, len(names))
        if self.next_logits.ndim != 2 or int(self.next_logits.shape[0]) != 1:
            raise legacy.SessionContractError("candidate batching requires batch-1 next_logits")
        local_logits = self.next_logits.detach().clone().expand(len(names), -1).contiguous()
        local_len = int(self.context_len)
        totals = [0.0 for _ in names]
        max_len = max(len(ids) for ids in seqs)
        for j in range(max_len):
            lp = torch.log_softmax(local_logits.float(), dim=-1)
            for i, ids in enumerate(seqs):
                if j < len(ids):
                    totals[i] += float(lp[i, ids[j]].item())
            if j + 1 < max_len:
                # Rows whose exact candidate already ended are advanced with an
                # arbitrary in-row token only to preserve rectangular batch
                # geometry. Their later logits are never scored or observed and
                # cannot influence any other batch row.
                step_ids = [ids[j] if j < len(ids) else ids[-1] for ids in seqs]
                local_past, local_logits = self._step_model_batch(step_ids, local_past, local_len)
                local_len += 1
        rows = {}
        for command, ids, total in zip(names, seqs, totals):
            n = len(ids)
            rows[command] = legacy.CandidateScore(command, legacy.token_ids_sha256(ids), n, total, total / n)
        return rows

    def score_candidates(self, suffix_ids_by_command: Mapping[str, Sequence[int]]):
        """Semantics-equivalent bounded-batch replacement for legacy scoring."""
        self._assert_open()
        if not suffix_ids_by_command:
            raise legacy.SessionContractError("candidate map must be nonempty")
        commands = sorted(str(x) for x in suffix_ids_by_command)
        if any(not [int(v) for v in suffix_ids_by_command[c]] for c in commands):
            raise legacy.SessionContractError("candidate suffix must be nonempty")
        before = legacy.cache_digest(self.past_key_values)
        rows = {}
        for off in range(0, len(commands), MAX_CANDIDATE_BATCH):
            chunk = commands[off:off + MAX_CANDIDATE_BATCH]
            rows.update(self._score_candidate_batch(chunk, suffix_ids_by_command))
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
