import unittest

from replay_residual_kv_mediation_v1 import (
    ARM_A, ARM_B, ARM_C, ARM_D, ARM_E, CacheContractError,
    arm_matched_selective_contrasts, build_cache_arms, cache_layers,
    compose_cache, identity_guard, partition_cache, rebuild_like,
)


class FakeTensor:
    dtype = "float32"
    device = "cpu"

    def __init__(self, rows):
        self.rows = tuple(tuple(float(x) for x in row) for row in rows)
        width = len(self.rows[0]) if self.rows else 0
        if any(len(row) != width for row in self.rows):
            raise ValueError("ragged")
        self.shape = (1, len(self.rows), width)

    def __getitem__(self, key):
        if not isinstance(key, tuple) or len(key) < 2:
            raise TypeError(key)
        seq = key[-2]
        if not isinstance(seq, slice):
            raise TypeError(key)
        return FakeTensor(self.rows[seq])

    def __repr__(self):
        return f"FakeTensor({self.rows!r})"


class FakeDynamicCache:
    def __init__(self):
        self.key_cache = []
        self.value_cache = []
        self._seen_tokens = 0


def fake_concat(tensors, dim):
    if dim != -2:
        raise AssertionError(dim)
    rows = []
    for tensor in tensors:
        rows.extend(tensor.rows)
    return FakeTensor(rows)


def fake_diff(a, b):
    if a.shape != b.shape:
        return float("inf")
    if not a.rows:
        return 0.0
    return max(abs(x-y) for ra, rb in zip(a.rows, b.rows) for x, y in zip(ra, rb))


def make_legacy(offset):
    layers = []
    for layer in range(2):
        key = FakeTensor([[offset + 100*layer + 10*i + j for j in range(3)] for i in range(5)])
        val = FakeTensor([[offset + 1000 + 100*layer + 10*i + j for j in range(3)] for i in range(5)])
        layers.append((key, val))
    return tuple(layers)


def make_dynamic(offset):
    obj = FakeDynamicCache()
    for key, val in make_legacy(offset):
        obj.key_cache.append(key)
        obj.value_cache.append(val)
    obj._seen_tokens = 5
    return obj


class KVMediationTests(unittest.TestCase):
    def assert_cache_rows_equal(self, a, b):
        la, lb = cache_layers(a), cache_layers(b)
        self.assertEqual(len(la), len(lb))
        for (ak,av),(bk,bv) in zip(la,lb):
            self.assertEqual(ak.rows,bk.rows)
            self.assertEqual(av.rows,bv.rows)

    def test_partition_and_legacy_recompose_exact(self):
        cache = make_legacy(0)
        part = partition_cache(cache, 3)
        self.assertEqual(part.prefix_len, 3)
        self.assertEqual(part.total_len, 5)
        rebuilt = compose_cache(cache, cache, 3, concat_fn=fake_concat)
        self.assert_cache_rows_equal(cache, rebuilt)

    def test_dynamic_like_rebuild_preserves_class_and_geometry(self):
        cache = make_dynamic(0)
        rebuilt = compose_cache(cache, cache, 2, concat_fn=fake_concat)
        self.assertIsInstance(rebuilt, FakeDynamicCache)
        self.assertEqual(rebuilt._seen_tokens, 5)
        self.assert_cache_rows_equal(cache, rebuilt)

    def test_exact_A_to_E_arms(self):
        condition, clean = make_legacy(10000), make_legacy(0)
        arms = build_cache_arms(condition, clean, 2, concat_fn=fake_concat)
        self.assertEqual(set(arms), {ARM_A,ARM_B,ARM_C,ARM_D,ARM_E})
        self.assert_cache_rows_equal(arms[ARM_A], condition)
        self.assert_cache_rows_equal(arms[ARM_E], condition)
        self.assert_cache_rows_equal(arms[ARM_D], clean)
        # B: clean prefix, condition cycle. C: condition prefix, clean cycle.
        for (bk,bv),(ck,cv),(condk,condv),(cleank,cleanv) in zip(
            cache_layers(arms[ARM_B]), cache_layers(arms[ARM_C]), cache_layers(condition), cache_layers(clean)
        ):
            self.assertEqual(bk.rows[:2], cleank.rows[:2]); self.assertEqual(bk.rows[2:], condk.rows[2:])
            self.assertEqual(bv.rows[:2], cleanv.rows[:2]); self.assertEqual(bv.rows[2:], condv.rows[2:])
            self.assertEqual(ck.rows[:2], condk.rows[:2]); self.assertEqual(ck.rows[2:], cleank.rows[2:])
            self.assertEqual(cv.rows[:2], condv.rows[:2]); self.assertEqual(cv.rows[2:], cleanv.rows[2:])

    def test_identity_guards_are_bit_exact_on_cache_content(self):
        condition, clean = make_dynamic(10000), make_dynamic(0)
        arms = build_cache_arms(condition, clean, 2, concat_fn=fake_concat)
        guard = identity_guard(condition, clean, arms, tensor_diff_fn=fake_diff)
        self.assertEqual(guard, {
            'sham_E_vs_A_max_abs':0.0,
            'persist_A_vs_condition_max_abs':0.0,
            'full_restore_D_vs_clean_max_abs':0.0,
        })

    def test_arm_matched_contrasts(self):
        scores = {
            ARM_D: 1.0,
            ARM_A: {'PLAN':5.0,'NEXT_ACTION_PRESERVED_LATE_NULL':3.0,'UNRELATED_PLAN':2.0,'EQUAL_NORM_RANDOM':1.5},
            ARM_B: {'PLAN':4.0,'NEXT_ACTION_PRESERVED_LATE_NULL':1.5,'UNRELATED_PLAN':2.5,'EQUAL_NORM_RANDOM':2.0},
            ARM_C: {'PLAN':3.5,'NEXT_ACTION_PRESERVED_LATE_NULL':2.0,'UNRELATED_PLAN':1.0,'EQUAL_NORM_RANDOM':1.5},
        }
        out = arm_matched_selective_contrasts(scores)
        self.assertAlmostEqual(out['TOTAL'],2.0)
        self.assertAlmostEqual(out['PROPAGATED'],1.5)
        self.assertAlmostEqual(out['DIRECT'],1.5)
        self.assertAlmostEqual(out['TOTAL_max_control_delta'],2.0)
        self.assertAlmostEqual(out['PROPAGATED_max_control_delta'],1.5)
        self.assertAlmostEqual(out['DIRECT_max_control_delta'],1.0)

    def test_rejects_missing_or_pooled_controls(self):
        base={ARM_D:0.0,ARM_A:{},ARM_B:{},ARM_C:{}}
        for arm in (ARM_A,ARM_B,ARM_C):
            base[arm]={'PLAN':1.0,'NEXT_ACTION_PRESERVED_LATE_NULL':0.0,'UNRELATED_PLAN':0.0,'EQUAL_NORM_RANDOM':0.0}
        bad={k:(dict(v) if isinstance(v,dict) else v) for k,v in base.items()}
        del bad[ARM_B]['UNRELATED_PLAN']
        with self.assertRaises(CacheContractError):
            arm_matched_selective_contrasts(bad)
        pooled=dict(base)
        pooled[ARM_A]=dict(base[ARM_A]); pooled[ARM_A]['POOLED_CONTROL']=0.0
        with self.assertRaises(CacheContractError):
            arm_matched_selective_contrasts(pooled)

    def test_geometry_mismatch_fails_closed(self):
        condition = make_legacy(0)
        bad = list(make_legacy(100))
        bad[0] = (FakeTensor([[1,2,3]]*4), bad[0][1])
        with self.assertRaises(CacheContractError):
            build_cache_arms(condition, tuple(bad), 2, concat_fn=fake_concat)


if __name__ == '__main__':
    unittest.main(verbosity=2)
