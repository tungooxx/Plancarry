import copy
import hashlib
import json
import math
import pathlib
import tempfile
import unittest

import successor_feature_constructibility_v2 as sf

ROOT = pathlib.Path(__file__).resolve().parents[2]
POP = ROOT / 'results/design/plancarry_successor_feature_fresh_population_v1_20260827.json'

class SuccessorFeatureRuntimeV2Tests(unittest.TestCase):
    def sample(self):
        return (
            sf.one_hot_row('SEEK_OBJECT'),
            sf.one_hot_row('ACQUIRE_OBJECT'),
            sf.largest_remainder_uint8([.60,.10,.10,.05,.10,.05]),
            sf.largest_remainder_uint8([.10,.10,.10,.55,.10,.05]),
        )

    def test_quantization_exact_sum_and_tie_order(self):
        for vals in ([1]*6, [0,0,1,0,0,0], [.1,.2,.3,.4,.5,.6], [1e-20,1,2,3,4,5]):
            q=sf.largest_remainder_uint8(vals)
            self.assertEqual(sum(q),255)
            self.assertTrue(all(0<=x<=255 for x in q))
        self.assertEqual(sf.largest_remainder_uint8([1]*6), (43,43,43,42,42,42))

    def test_serialization_exact_52_and_roundtrip(self):
        c=self.sample(); s=sf.serialize_carrier(c)
        self.assertEqual(len(s.encode('ascii')),52)
        self.assertEqual(sf.parse_carrier(s),c)
        self.assertEqual(s[4:],s[4:].lower())

    def test_old_row2_only_counterexample_is_zero_future_distance(self):
        row1=sf.one_hot_row('SEEK_OBJECT')
        a=(row1,sf.one_hot_row('ACQUIRE_OBJECT'),sf.NEUTRAL_ROW,sf.NEUTRAL_ROW)
        b=(row1,sf.one_hot_row('PLACE_OBJECT'),sf.NEUTRAL_ROW,sf.NEUTRAL_ROW)
        self.assertEqual(sf.future_distance(a,b),0.0)
        self.assertFalse(sf.future_separable(a,b))

    def test_future_rows_can_clear_threshold_while_rows12_fixed(self):
        row1=sf.one_hot_row('SEEK_OBJECT'); row2=sf.one_hot_row('ACQUIRE_OBJECT')
        a=(row1,row2,sf.one_hot_row('SEEK_OBJECT'),sf.one_hot_row('SEEK_OBJECT'))
        b=(row1,row2,sf.one_hot_row('PLACE_OBJECT'),sf.one_hot_row('PLACE_OBJECT'))
        self.assertGreater(sf.future_distance(a,b),.50)
        self.assertTrue(sf.future_separable(a,b))

    def test_distance_rejects_gamma_drift(self):
        c=self.sample()
        with self.assertRaisesRegex(sf.ContractError,'GAMMA_DRIFT'):
            sf.future_distance(c,c,gamma=.7)

    def test_branch_plausibility(self):
        # Equal logits => second probability 1/6 >= .10.
        self.assertEqual(sf.branch_labels_if_plausible([0]*6), ('SEEK_OBJECT','ACQUIRE_OBJECT'))
        # One overwhelmingly dominant label makes runner-up < .10.
        with self.assertRaisesRegex(sf.ContractError,'SECOND_BRANCH'):
            sf.branch_labels_if_plausible([20,0,0,0,0,0])
        with self.assertRaisesRegex(sf.ContractError,'FINITE'):
            sf.branch_labels_if_plausible([0,0,float('nan'),0,0,0])

    def test_orientation_deterministic_and_pair_preserving(self):
        x=sf.orient_branches('a/path','SEEK_OBJECT','PLACE_OBJECT')
        y=sf.orient_branches('a/path','SEEK_OBJECT','PLACE_OBJECT')
        self.assertEqual(x,y); self.assertEqual(set(x),{'SEEK_OBJECT','PLACE_OBJECT'})

    def test_controls_preserve_required_rows(self):
        c=self.sample()
        bp=sf.branch_phase_only(c)
        self.assertEqual(bp[:2],c[:2]); self.assertEqual(bp[2:],(sf.NEUTRAL_ROW,sf.NEUTRAL_ROW))
        ts=sf.time_shuffled(c)
        self.assertEqual(ts[:2],c[:2]); self.assertEqual(ts[2],c[3]); self.assertEqual(ts[3],c[2])
        ia=sf.immediate_action_only(c)
        self.assertEqual(ia[0],c[0]); self.assertEqual(ia[1:],(sf.NEUTRAL_ROW,)*3)

    def test_population_exact_and_only_constructibility_exposed(self):
        rows=sf.load_constructibility_population(POP)
        self.assertEqual(len(rows),16)
        self.assertEqual([r['index'] for r in rows],list(range(16)))
        for i in range(16): sf.require_constructibility_index(i)
        for i, msg in [(16,'CAUSAL_DEVELOPMENT_SPLIT_LOCKED'),(31,'CAUSAL_DEVELOPMENT_SPLIT_LOCKED'),(32,'SPARE_SPLIT_LOCKED'),(36,'SPARE_SPLIT_LOCKED')]:
            with self.assertRaisesRegex(sf.ContractError,msg): sf.require_constructibility_index(i)

    def test_population_tamper_fails_closed(self):
        raw=POP.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'pop.json'; p.write_bytes(raw+b' ')
            with self.assertRaisesRegex(sf.ContractError,'SHA256'):
                sf.load_constructibility_population(p)

    def test_invalid_carrier_fail_closed(self):
        c=list(self.sample()); c[0]=(1,2,3,4,5,6)
        with self.assertRaisesRegex(sf.ContractError,'ROW_SUM'):
            sf.serialize_carrier(c)
        with self.assertRaises(sf.ContractError): sf.parse_carrier('SF1:'+'00'*24)

    def test_no_forbidden_imports(self):
        src=(ROOT/'successor_feature_constructibility_v2.py').read_text().lower()
        for bad in ['transformers','torch','alfworld','textworld','tokenizer','cuda']:
            self.assertNotIn('import '+bad,src)

if __name__ == '__main__': unittest.main()
