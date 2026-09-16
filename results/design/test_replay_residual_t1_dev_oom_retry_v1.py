from __future__ import annotations

from types import SimpleNamespace
import importlib
import torch

import replay_residual_natural_packet_producer_v2_1 as p
m = importlib.import_module('replay_residual_t1_direct_override_dev_v1_2_oom_retry')


class Dummy(torch.nn.Module):
    def __init__(self, logits):
        super().__init__()
        self.anchor = torch.nn.Parameter(torch.zeros(()), requires_grad=False)
        self._logits = logits
    def forward(self, input_ids):
        return SimpleNamespace(logits=self._logits[:, : input_ids.shape[1], :])


def test_score_equivalence():
    torch.manual_seed(1234)
    for plen, slen, vocab in [(3, 1, 17), (9, 4, 31), (17, 6, 47)]:
        total = plen + slen
        logits = torch.randn(1, total, vocab, dtype=torch.float32).to(torch.bfloat16)
        model = Dummy(logits)
        prefix = list(range(1, plen + 1))
        suffix = [int((i * 7 + 3) % vocab) for i in range(slen)]
        legacy = p.torch_suffix_mean_logprob(model, prefix, suffix)
        bounded = m.vram_bounded_suffix_mean_logprob(model, prefix, suffix)
        assert legacy == bounded, (plen, slen, legacy, bounded)


def test_same_index_retry():
    calls = []
    old = m._ORIG_ATTEMPT
    try:
        def fake(row, *_args):
            calls.append(int(row['frozen_index']))
            if len(calls) == 1:
                return {'qualification_stage1_reasons':['INVALID_COMMAND_OR_EXECUTION_ERROR','OutOfMemoryError:CUDA out of memory.']}
            return {'qualification_stage1_reasons':[], 'frozen_index':int(row['frozen_index'])}
        m._ORIG_ATTEMPT = fake
        got = m.retrying_stage1_attempt({'frozen_index':7}, None, {}, None, None, None)
        assert calls == [7, 7], calls
        assert got['frozen_index'] == 7
    finally:
        m._ORIG_ATTEMPT = old


def test_retry_exhaustion():
    calls = []
    old = m._ORIG_ATTEMPT
    try:
        def fake(row, *_args):
            calls.append(int(row['frozen_index']))
            return {'qualification_stage1_reasons':['OutOfMemoryError:CUDA out of memory.']}
        m._ORIG_ATTEMPT = fake
        try:
            m.retrying_stage1_attempt({'frozen_index':11}, None, {}, None, None, None)
        except RuntimeError as exc:
            assert str(exc) == 'TECHNICAL_OOM_RETRY_EXHAUSTED:index=11:retries=3'
        else:
            raise AssertionError('expected exhaustion')
        assert calls == [11,11,11,11], calls
    finally:
        m._ORIG_ATTEMPT = old


if __name__ == '__main__':
    test_score_equivalence()
    test_same_index_retry()
    test_retry_exhaustion()
    print('PASS: scorer equivalence + same-index OOM retry + exhaustion')
