#!/usr/bin/env python3
from __future__ import annotations

import gc
import json
from typing import Any, Mapping, Sequence

import torch

import replay_residual_natural_packet_producer_v2_1 as p
import replay_residual_t1_direct_override_dev_v1_1 as base

MAX_OOM_RETRIES = 3
_ORIG_ATTEMPT = p.produce_stage1_attempt


def vram_bounded_suffix_mean_logprob(model: Any, prefix_ids: Sequence[int], suffix_ids: Sequence[int]) -> float:
    """Exact frozen FP32 suffix logprob, selecting suffix prediction rows before FP32 expansion."""
    pids = [int(x) for x in prefix_ids]
    sids = [int(x) for x in suffix_ids]
    if not pids or not sids:
        raise RuntimeError("EMPTY_PREFIX_OR_SUFFIX")
    device = next(model.parameters()).device
    full = torch.tensor([pids + sids], dtype=torch.long, device=device)
    with torch.inference_mode():
        logits = model(input_ids=full).logits
        # Frozen scorer uses rows absolute-1 for each suffix token. Select only those
        # rows in BF16 first, then perform the same FP32 conversion/log_softmax.
        row_ids = torch.arange(len(pids) - 1, len(pids) + len(sids) - 1, device=logits.device)
        suffix_logits_fp32 = logits[0].index_select(0, row_ids).float()
        logp = torch.log_softmax(suffix_logits_fp32, dim=-1)
        token_ids = torch.tensor(sids, dtype=torch.long, device=logp.device)
        vals = logp.gather(1, token_ids.unsqueeze(1)).squeeze(1)
        score = vals.mean()
    value = float(score.detach().cpu().item())
    if not p.math.isfinite(value):
        raise RuntimeError("NONFINITE_CANDIDATE_SCORE")
    return value


def packet_has_cuda_oom(packet: Mapping[str, Any]) -> bool:
    reasons = packet.get("qualification_stage1_reasons") or []
    text = "\n".join(str(x) for x in reasons).lower()
    markers = (
        "outofmemoryerror",
        "cuda out of memory",
        "memory allocation failed with oom",
        "cuda error: out of memory",
    )
    return any(marker in text for marker in markers)


def cleanup_cuda() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        try:
            torch.cuda.synchronize()
        except Exception:
            pass


def retrying_stage1_attempt(
    row: Mapping[str, Any],
    tokenizer: Any,
    model_provenance: Mapping[str, Any],
    runtime_factory: Any,
    planner_fn: Any,
    command_score_fn: Any,
) -> dict[str, Any]:
    frozen_index = int(row["frozen_index"])
    for retry_no in range(MAX_OOM_RETRIES + 1):
        packet = _ORIG_ATTEMPT(
            row, tokenizer, model_provenance, runtime_factory, planner_fn, command_score_fn
        )
        if not packet_has_cuda_oom(packet):
            cleanup_cuda()
            return packet
        if retry_no >= MAX_OOM_RETRIES:
            del packet
            cleanup_cuda()
            raise RuntimeError(
                f"TECHNICAL_OOM_RETRY_EXHAUSTED:index={frozen_index}:retries={MAX_OOM_RETRIES}"
            )
        # The producer already closed the per-family runtime in finally. The partial
        # packet is intentionally discarded and never enters stage2 or publication.
        del packet
        cleanup_cuda()
        print(
            json.dumps(
                {
                    "technical_event": "CUDA_OOM_RETRY_SAME_INDEX",
                    "frozen_index": frozen_index,
                    "retry": retry_no + 1,
                    "max_retries": MAX_OOM_RETRIES,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    raise AssertionError("unreachable")


def main() -> int:
    # Monkeypatch only execution plumbing. Frozen source files remain unchanged.
    p.torch_suffix_mean_logprob = vram_bounded_suffix_mean_logprob
    p.produce_stage1_attempt = retrying_stage1_attempt
    return int(base.main())


if __name__ == "__main__":
    raise SystemExit(main())
