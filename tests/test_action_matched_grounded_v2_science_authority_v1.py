from __future__ import annotations
import collections, hashlib, itertools, json, math, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'results/design/plancarry_action_matched_grounded_v2_science_ready_prereg_v1_20260825.json'
D=ROOT/'results/design/plancarry_action_matched_grounded_v2_science_authority_semantic_diff_v1_20260825.json'

def load(p): return json.loads(p.read_text())
def pad(x,L,cycle):
    if len(x)>L: raise ValueError('TRUNCATION_FORBIDDEN')
    return list(x)+[cycle[i%len(cycle)] for i in range(L-len(x))]
def upper_binom_p(n,k): return sum(math.comb(n,j) for j in range(k,n+1))/(2**n)
def holm2(p1,p2):
    a=sorted([p1,p2]); return a[0] <= 0.025 and a[1] <= 0.05

def strong_derange(x):
    x=list(x)
    if len(x)<2 or len(set(x))<2: raise ValueError('UNCONSTRUCTIBLE')
    # Reference fallback guaranteed by the frozen authority: smallest ordinary left rotation
    # that is value-nonidentical and changes the rightmost mutable value.
    for off in range(1,len(x)):
        y=x[off:]+x[:off]
        if y!=x and y[-1]!=x[-1]: return y
    raise ValueError('NO_VALID_DERANGEMENT')

class TestGroundedV2ScienceAuthority(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.p=load(P); cls.d=load(D)
    def test_science_fail_closed_and_lineage(self):
        p=self.p
        self.assertTrue(p['science_execution_forbidden'])
        self.assertEqual(p['scientific_result'],'NOT_ASSESSED_PRE_SCIENCE_DESIGN_ONLY')
        self.assertEqual(p['population']['manifest_sha256'],'49ada50d70257e1106d30a39e69567af5c4892367e8972a09f4ba575029729bc')
        self.assertEqual(p['authority_lineage']['constructibility_implementation_commit'],'94c1560220ee1c50dad7987df41dbc5eb9d0ca71')
        self.assertFalse(self.d['outcome_informed_tuning'])
    def test_model_grid_split_exact(self):
        p=self.p
        self.assertEqual(p['model_runtime']['revision'],'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e')
        self.assertEqual((p['model_runtime']['dtype'],p['model_runtime']['quantization'],p['model_runtime']['offload']),('bfloat16','NONE','NONE'))
        self.assertEqual(p['causal_runtime']['layers'],[7,14,21,27]); self.assertEqual(p['causal_runtime']['alphas'],[0.25,0.5,1.0])
        self.assertEqual(p['population']['development_scan_indices'],[0,63]); self.assertEqual(p['population']['confirmation_scan_indices_locked'],[64,127]); self.assertEqual(p['population']['reserve_indices_locked'],[128,159])
    def test_tokenizer_canary_and_wrapper_ids_exact(self):
        t=self.p['token_serialization']
        self.assertEqual(t['tokenizer_provenance']['chat_template_canary_ids_sha256'],'27b3dd904b257baddf6723ea28c7728629b377dd1ec646f079bfb81666df633a')
        self.assertEqual(t['grounded_wrapper_tokens']['source_end']['ids'],[198,18858,13077,10898,29])
        self.assertEqual(t['grounded_wrapper_tokens']['sep_a4']['ids'],[198,13095,41933,21866,19,510])
        self.assertEqual(t['grounded_wrapper_tokens']['sep_a5']['ids'],[198,13095,41933,21866,20,510])
        self.assertEqual(t['neutral_cycle_ids'],[20628,2266,8458,34857,13])
    def test_source_geometry_same_length_and_strong_sequence_control(self):
        cycle=self.p['token_serialization']['neutral_cycle_ids']
        A3=[1,2]; A4=[3]; B4=[4,5]; A5=[6,7,8]; B5=[9]; PA=[10,11,12,13]; PB=[14,15]
        L3=len(A3); L4=max(map(len,[A4,B4])); L5=max(map(len,[A5,B5])); LP=max(map(len,[PA,PB]))
        activeA=pad(A3,L3,cycle)+pad(A4,L4,cycle)+pad(A5,L5,cycle)+pad(PA,LP,cycle)
        activeB=pad(A3,L3,cycle)+pad(B4,L4,cycle)+pad(B5,L5,cycle)+pad(PB,LP,cycle)
        seqA=pad(A3,L3,cycle)+pad(A4,L4,cycle)+pad(A5,L5,cycle)+pad([],LP,cycle)
        seqB=pad(A3,L3,cycle)+pad(B4,L4,cycle)+pad(B5,L5,cycle)+pad([],LP,cycle)
        nxtA=pad(A3,L3,cycle)+pad(A4,L4,cycle)+pad([],L5,cycle)+pad([],LP,cycle)
        nxtB=pad(A3,L3,cycle)+pad(B4,L4,cycle)+pad([],L5,cycle)+pad([],LP,cycle)
        self.assertEqual(len({len(x) for x in [activeA,activeB,seqA,seqB,nxtA,nxtB]}),1)
        self.assertEqual(seqA[:L3+L4+L5],activeA[:L3+L4+L5]); self.assertEqual(seqB[:L3+L4+L5],activeB[:L3+L4+L5])
        self.assertNotIn(6,nxtA[L3+L4:]); self.assertNotIn(9,nxtB[L3+L4:])
    def test_rationale_derangement_property(self):
        for x in ([1,2],[1,1,2],[1,2,1,2],[2,1,1]):
            y=strong_derange(x); self.assertEqual(collections.Counter(x),collections.Counter(y)); self.assertNotEqual(x,y); self.assertNotEqual(x[-1],y[-1])
        with self.assertRaises(ValueError): strong_derange([1,1,1])
    def test_both_sign_false_pass_guard_and_sequence_in_joint(self):
        # active bidirectional=.20 but the - nuisance is .25: orientation-robust joint must fail.
        bidir=.20; plus=.01; minus=.25; seq=.03
        joint=bidir-max(abs(plus),abs(minus),seq)
        self.assertLess(joint,.05)
        self.assertIn('FUTURE_ACTION_SEQUENCE_ONLY',self.p['controls_and_signs']['semantic_nuisance_controls'])
        self.assertIn('future_action_sequence_only',self.p['endpoints']['A4']['joint_semantic_plan_margin'])
        self.assertIn('future_action_sequence_only5',self.p['endpoints']['A5_B5']['joint_semantic_plan_continuation5'])
    def test_exact_confirmation_thresholds_and_holm(self):
        p15=upper_binom_p(20,15); p14=upper_binom_p(20,14)
        self.assertAlmostEqual(p15,0.020694732666015625)
        self.assertAlmostEqual(p14,0.057659149169921875)
        self.assertTrue(holm2(p15,p15)); self.assertFalse(holm2(p14,p15))
        c=self.p['confirmation']; self.assertIn('0.025',c['multiplicity']); self.assertIn('0.05',c['multiplicity']); self.assertIn('>=15/20 positive',c['effect_guards_each'])
    def test_development_selection_and_no_a5_reselection(self):
        d=self.p['development']
        self.assertIn('maximize median joint_semantic_plan_margin',d['selection'])
        self.assertIn('higher median bidirectional',d['selection']); self.assertIn('lower alpha',d['selection']); self.assertIn('earlier layer',d['selection'])
        self.assertIn('cannot select/reselect',d['same_point_A5_gate'])
    def test_plan_materialization_is_one_shot_and_grounded(self):
        m=self.p['plan_materialization']; self.assertEqual(m['calls_per_branch'],1); self.assertFalse(m['retry_or_repair'])
        self.assertEqual(m['generation']['do_sample'],False); self.assertEqual(m['generation']['temperature_argument'],'OMITTED')
        self.assertIn('ACTION_3 capture exact-string equals frozen A3',m['acceptance'])
        self.assertIn('future observations after cut',m['information_forbidden'])
    def test_control_degenerate_norm_does_not_delete_denominator(self):
        rule=self.p['source_residuals']['norm_matching']
        self.assertIn('retain the family',rule); self.assertIn('do not exclude or replace',rule)
    def test_semantic_diff_declares_structural_adaptations_only(self):
        names={x['field'] for x in self.d['grounded_specific_adaptations']}
        self.assertEqual(names,{'plan materialization','source serialization','FUTURE_ACTION_SEQUENCE_ONLY','FUTURE_TOKEN_DERANGED','selection endpoint name','claim scope'})
        self.assertIn('0.05/15-of-20/Holm thresholds',self.d['explicitly_not_changed'])

if __name__=='__main__': unittest.main()
