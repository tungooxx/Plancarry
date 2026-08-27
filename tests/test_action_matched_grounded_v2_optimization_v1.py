#!/usr/bin/env python3
from __future__ import annotations
import types
import unittest
import hashlib
from pathlib import Path

import torch
import torch.nn as nn

import replay_residual_t1_session_runtime_v1 as legacy
import action_matched_grounded_v2_optimization_v1 as opt
import action_matched_grounded_v2_optimized_runtime_v1 as rt


class ToyStepModel(nn.Module):
    def __init__(self, vocab: int = 17):
        super().__init__()
        self.anchor = nn.Parameter(torch.tensor(0.0))
        self.vocab = vocab
        self.calls = 0

    def forward(self, input_ids, attention_mask=None, past_key_values=None, use_cache=True):
        self.calls += 1
        assert past_key_values is not None
        k, v = past_key_values[0]
        tok = input_ids[:, 0].float().view(-1, 1, 1, 1)
        nk = torch.cat([k, tok], dim=-2)
        nv = torch.cat([v, tok * 0.5 + 1.0], dim=-2)
        context = nk.sum(dim=-2).reshape(input_ids.shape[0], 1, 1)
        basis = torch.linspace(-0.7, 0.9, self.vocab).reshape(1, 1, self.vocab)
        logits = basis + context * torch.linspace(0.03, -0.02, self.vocab).reshape(1, 1, self.vocab)
        return types.SimpleNamespace(past_key_values=((nk, nv),), logits=logits)


def make_scoring_session():
    s = opt.OptimizedPersistentTokenSession.__new__(opt.OptimizedPersistentTokenSession)
    s.model = ToyStepModel()
    s.device = torch.device('cpu')
    s.closed = False
    s.context_len = 3
    k = torch.tensor([[[[1.0], [2.0], [3.0]]]])
    v = torch.tensor([[[[0.5], [1.0], [1.5]]]])
    s.past_key_values = ((k.clone(), v.clone()),)
    s.next_logits = torch.linspace(-0.5, 0.8, s.model.vocab).reshape(1, -1)
    return s


class AddLayer(nn.Module):
    def __init__(self, bias: float):
        super().__init__()
        self.bias = bias
    def forward(self, x):
        return x + self.bias


class Backbone(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.ModuleList([AddLayer(0.25), AddLayer(-0.5), AddLayer(1.0), AddLayer(0.75)])


class ToyCaptureModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(32, 5)
        with torch.no_grad():
            vals = torch.arange(32 * 5, dtype=torch.float32).reshape(32, 5) / 100.0
            self.embed.weight.copy_(vals)
        self.model = Backbone()
        self.calls = 0
    def forward(self, input_ids, attention_mask=None, use_cache=False):
        self.calls += 1
        h = self.embed(input_ids)
        for layer in self.model.layers:
            h = layer(h)
        return types.SimpleNamespace(logits=torch.zeros((*h.shape[:2], 32)), past_key_values=None)


class GroundedOptimizationTests(unittest.TestCase):
    def test_batched_candidate_scores_match_legacy_variable_lengths(self):
        s = make_scoring_session()
        candidates = {'zeta':[2], 'alpha':[4,5,6], 'mid':[3,7], 'long':[8,1,9,4]}
        before = legacy.cache_digest(s.past_key_values)
        best_old, old = s.score_candidates_legacy(candidates)
        mid = legacy.cache_digest(s.past_key_values)
        best_new, new = s.score_candidates(candidates)
        after = legacy.cache_digest(s.past_key_values)
        self.assertEqual(before, mid)
        self.assertEqual(mid, after)
        self.assertEqual(best_old, best_new)
        for name in sorted(candidates):
            self.assertEqual(old[name].token_count, new[name].token_count)
            self.assertEqual(old[name].suffix_token_ids_sha256, new[name].suffix_token_ids_sha256)
            self.assertAlmostEqual(old[name].logprob_sum, new[name].logprob_sum, places=7)
            self.assertAlmostEqual(old[name].mean_logprob, new[name].mean_logprob, places=7)


    def test_batched_candidate_chunking_and_lexical_tie(self):
        s = make_scoring_session()
        candidates = {f"cmd_{i:02d}":[(i % 10)+1, ((i+3) % 10)+1, ((i+5) % 10)+1] for i in range(19)}
        candidates['aaa_tie']=[2,3]
        candidates['zzz_tie']=[2,3]
        best_old, old = s.score_candidates_legacy(candidates)
        best_new, new = s.score_candidates(candidates)
        self.assertEqual(best_old, best_new)
        self.assertEqual(set(old), set(new))
        for name in old:
            self.assertAlmostEqual(old[name].logprob_sum, new[name].logprob_sum, places=7)
            self.assertAlmostEqual(old[name].mean_logprob, new[name].mean_logprob, places=7)
        # Identical-score command names must preserve lexical tie ordering.
        pair={'zzz':[2,3], 'aaa':[2,3]}
        old_best,_=s.score_candidates_legacy(pair); new_best,_=s.score_candidates(pair)
        self.assertEqual(old_best, 'aaa'); self.assertEqual(new_best, 'aaa')

    def test_dynamic_cache_batch_replication_preserves_geometry(self):
        from transformers.cache_utils import DynamicCache
        c=DynamicCache()
        c.key_cache=[torch.arange(12,dtype=torch.float32).reshape(1,2,3,2)]
        c.value_cache=[torch.arange(12,24,dtype=torch.float32).reshape(1,2,3,2)]
        c._seen_tokens=3
        r=opt.repeat_cache_batch(c,4)
        self.assertIsInstance(r, DynamicCache)
        self.assertEqual(tuple(r.key_cache[0].shape),(4,2,3,2))
        self.assertEqual(tuple(r.value_cache[0].shape),(4,2,3,2))
        self.assertEqual(r._seen_tokens,3)
        for i in range(4):
            self.assertTrue(torch.equal(r.key_cache[0][i], c.key_cache[0][0]))
            self.assertTrue(torch.equal(r.value_cache[0][i], c.value_cache[0][0]))

    def test_empty_candidate_fails_closed(self):
        s=make_scoring_session()
        with self.assertRaises(legacy.SessionContractError):
            s.score_candidates({'a':[],'b':[2]})

    def test_batched_candidate_scoring_fail_closed_on_non_batch1_cache(self):
        s = make_scoring_session()
        k, v = s.past_key_values[0]
        s.past_key_values = ((k.repeat(2,1,1,1), v.repeat(2,1,1,1)),)
        with self.assertRaises(legacy.SessionContractError):
            s.score_candidates({'a':[1], 'b':[2]})

    def test_multi_layer_capture_matches_repeated_single_layer(self):
        model = ToyCaptureModel()
        ids = [2,5,7,11]
        layers = [0,1,2,3]
        old = {layer: legacy.capture_activation_ids(model, ids, layer, -1) for layer in layers}
        new = opt.capture_activation_ids_multi(model, ids, layers, -1)
        for layer in layers:
            self.assertTrue(torch.equal(old[layer], new[layer]))

    def test_multi_layer_pair_residual_matches_legacy(self):
        model = ToyCaptureModel()
        A, B, layers = [1,3,5,7], [1,3,6,7], [0,1,2,3]
        old = {layer: rt.capture_pair_residual(model, A, B, layer) for layer in layers}
        new = rt.capture_pair_residuals(model, A, B, layers)
        for layer in layers:
            self.assertTrue(torch.equal(old[layer], new[layer]))


    def test_batching_reduces_model_forward_count(self):
        s = make_scoring_session()
        candidates = {'zeta':[2], 'alpha':[4,5,6], 'mid':[3,7], 'long':[8,1,9,4]}
        s.model.calls = 0
        s.score_candidates_legacy(candidates)
        legacy_calls = s.model.calls
        s.model.calls = 0
        s.score_candidates(candidates)
        batched_calls = s.model.calls
        self.assertEqual(legacy_calls, 6)
        self.assertEqual(batched_calls, 3)
        self.assertLess(batched_calls, legacy_calls)

    def test_multi_layer_capture_reduces_forward_count(self):
        model = ToyCaptureModel()
        ids, layers = [2,5,7,11], [0,1,2,3]
        model.calls = 0
        for layer in layers:
            legacy.capture_activation_ids(model, ids, layer, -1)
        legacy_calls = model.calls
        model.calls = 0
        opt.capture_activation_ids_multi(model, ids, layers, -1)
        multi_calls = model.calls
        self.assertEqual(legacy_calls, 4)
        self.assertEqual(multi_calls, 1)

    def test_original_frozen_runtime_unchanged(self):
        expected={
          'replay_residual_t1_session_runtime_v1.py':'585e44ec5cd2395be0804b865de85ac36c5db79117cf4061566cf16a9749e3b6',
          'action_matched_grounded_v2_runtime_v1.py':'6600d4cf8310f9e43c35e8842df990ad9a0100f820e564ae1ea152f816cc7427',
          'action_matched_grounded_v2_science_driver_v1.py':'b0286859cb9e6c74d0668ab4b81b8646afc5d96c44228b69ec3e03cec98a8f76',
          'action_matched_grounded_v2_primary_v1.sh':'701818356546d09a54f23decf644675a97378ea70889cd2e8c92c550c1d6ee22',
        }
        for name,want in expected.items():
            self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(),want)
        self.assertNotEqual(rt.PersistentTokenSession, legacy.PersistentTokenSession)


if __name__ == '__main__':
    unittest.main()
