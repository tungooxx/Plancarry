import copy, importlib, json, math, os, pathlib, tempfile, unittest
from unittest import mock

import cpds_development_driver_v1 as d
import cpds_development_runtime_v1 as r

ROOT=pathlib.Path(__file__).resolve().parents[1]

class TestCPDSDevelopmentDriverV1(unittest.TestCase):
    def test_01_import_has_no_science_packages(self):
        # The modules may exist in the process from other tests; source is the stable check.
        txt=(ROOT/'cpds_development_driver_v1.py').read_text()
        head=txt.split('def _runtime_factory_default',1)[0]
        self.assertNotIn('import torch',head); self.assertNotIn('import textworld',head); self.assertNotIn('import alfworld',head)

    def test_02_exact_semantics_hash(self):
        self.assertEqual(r.sha_file(d.SEMANTICS_PATH),d.SEMANTICS_SHA256)
        o=json.loads(d.SEMANTICS_PATH.read_text())
        x=copy.deepcopy(o); x.pop('canonical_object_sha256_without_self_field',None); self.assertEqual(__import__('hashlib').sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest(),d.SEMANTICS_SELF_SHA256)

    def test_03_actual_33_two_transition_and_assignments(self):
        a=d._authorities(); fs=a['source']['families']
        self.assertEqual(len(fs),33); self.assertTrue(all(len(x['common_prefix_transition_keys'])==2 for x in fs))
        self.assertEqual(len(a['assignment_by_key']),33)

    def test_04_family_secret_split(self):
        f=d._authorities()['source']['families'][0]
        c,e=d._split_family(f)
        self.assertTrue(set(c).isdisjoint(d.EVALUATOR_KEYS))
        self.assertEqual(set(e),set(d.EVALUATOR_KEYS))

    def _vec(self,i):
        x=[0.0]*2048; x[i]=1.0; return x

    def test_05_arm_prefix_orders_and_static_scratch(self):
        z=self._vec(0); x1=self._vec(1); x2=self._vec(2); feats={'k1':x1,'k2':x2}; af={'a':self._vec(3)}; base={'a':-1.0}
        _,p1=d._arm_map_at_site('TRANSITION_PERMUTED','POST_TRANSITION_1',base,af,z,feats,['k1'])
        _,p2=d._arm_map_at_site('TRANSITION_PERMUTED','BRANCH_POINT',base,af,z,feats,['k1','k2'])
        self.assertEqual(p1['transition_order'],['k1']); self.assertEqual(p2['transition_order'],['k2','k1'])
        one,e1=d._arm_map_at_site('STATIC_ONESHOT','BRANCH_POINT',base,af,z,feats,['k1','k2'])
        sta,e2=d._arm_map_at_site('STATIC_REPEAT','BRANCH_POINT',base,af,z,feats,['k1','k2'])
        self.assertEqual(one,sta); self.assertEqual(e1['F_calls'],0); self.assertEqual(e2['F_calls'],2)

    def test_06_geometry_rejects_future_preview(self):
        events={a:[] for a in d.EXACT_ARMS}
        for a in d.EXACT_ARMS:
            for site,n in zip(d.SITES,[0,1,2]):
                g=a in d.MATCHED_ARMS or (a=='STATIC_ONESHOT' and site=='BRANCH_POINT')
                f=n if a in d.MATCHED_ARMS else 0
                order=[] if n==0 else (['k1'] if n==1 else ['k1','k2'])
                if a=='TRANSITION_PERMUTED' and n==2: order=['k2','k1']
                events[a].append({'site':site,'arm_id':a,'G_called':g,'F_calls':f,'transition_order':order})
        self.assertEqual(d._validate_geometry(events,['k1','k2'])['matched_G_count'],3)
        bad=copy.deepcopy(events); bad['TRANSITION_PERMUTED'][1]['transition_order']=['k2']
        with self.assertRaises(d.TechnicalInvalid): d._validate_geometry(bad,['k1','k2'])

    def _family_result(self,cs=.1,cp=.1,ci=.01,da=.2,oneshot=-999.0):
        guards={k:True for k in ('assignment_and_provenance','call_geometry_or_arm_matching','branch_blindness','graph_admissibility','immediate_action_invariance','score_completeness','isolation','G_nonforcing')}
        return {'endpoint':{'C':{'static':cs,'permuted':cp,'information':ci,'oneshot':oneshot},'D':{'ALIGNED_RECURSION':da}},'guards':guards}

    def test_07_development_gate_pass_and_ignores_oneshot(self):
        g=d.development_gate([self._family_result() for _ in range(33)])
        self.assertTrue(g['passed']); self.assertFalse(g['C_oneshot_used_as_development_gate'])
        self.assertEqual(g['terminal_label'],'DEVELOPMENT_READINESS_PASS_NOT_SCIENTIFIC_SUPPORT')

    def test_08_development_gate_exact_k22(self):
        xs=[self._family_result(cs=.1 if i<22 else -.1,cp=.1 if i<22 else -.1) for i in range(33)]
        g=d.development_gate(xs); self.assertTrue(g['positive_static_ge_22'] if 'positive_static_ge_22' in g else g['checks']['positive_static_ge_22'])
        xs[21]=self._family_result(cs=-.1,cp=-.1)
        g=d.development_gate(xs); self.assertFalse(g['passed']); self.assertEqual(g['positive_static'],21)

    def test_09_guard_failure_blocks_gate(self):
        xs=[self._family_result() for _ in range(33)]; xs[3]['guards']['isolation']=False
        g=d.development_gate(xs); self.assertFalse(g['passed']); self.assertEqual(g['guard_violations']['isolation'],1)

    def test_10_top_set_exact_ties(self):
        self.assertEqual(d._top_set({'b':1.0,'a':1.0,'c':0.0}),('a','b'))
        self.assertEqual(d._top_set({'a':1.0,'b':math.nextafter(1.0,2.0)}),('b',))

    def test_11_loader_uses_hf_home_hub_and_cuda(self):
        txt=(ROOT/'cpds_development_runtime_v1.py').read_text()
        self.assertIn('pathlib.Path(m["hf_home"])/"hub"',txt)
        self.assertIn('torch.cuda.is_bf16_supported()',txt)
        self.assertIn('model.to(device=torch.device("cuda"),dtype=torch.bfloat16)',txt)

    def test_12_launcher_executes_driver_after_preflight(self):
        txt=(ROOT/'cpds_development_primary_v1.sh').read_text()
        self.assertIn('CPDS_DEVELOPMENT_REQUIRES_RESEARCH_DECISION_BOUND',txt)
        self.assertIn('cpds_development_runtime_v1.py" --preflight',txt)
        self.assertIn('exec "$PY" "$ROOT/cpds_development_driver_v1.py"',txt)
        self.assertNotIn('exit 65',txt)

    def test_13_confirmation_and_planroute_absent_from_driver_routes(self):
        txt=(ROOT/'cpds_development_driver_v1.py').read_text()
        self.assertNotIn('selected_confirmation_source_graph_ids',txt)
        self.assertNotIn('valid_seen',txt)
        self.assertNotIn('PlanRoute(',txt)

    def test_14_output_existing_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            old=d.OUTPUT_DIR
            try:
                d.OUTPUT_DIR=pathlib.Path(td)/'out'; d.OUTPUT_DIR.mkdir()
                with mock.patch.dict(os.environ,{'CPDS_DEVELOPMENT_AUTHORIZATION':'RESEARCH_DECISION_BOUND'}):
                    with self.assertRaises(d.TechnicalInvalid): d.execute_development(model_loader=lambda:None)
            finally: d.OUTPUT_DIR=old

    def test_15_chronological_G_timing_in_source(self):
        import inspect
        src=inspect.getsource(d._execute_family)
        self.assertLess(src.index('score_arms_now("RESET_PREFIX"'),src.index('CARRIER_IMMEDIATE_STEP_ERROR'))
        self.assertLess(src.index('score_arms_now("POST_TRANSITION_1"'),src.index('CARRIER_COMMON2_NOT_ADMISSIBLE'))
        self.assertLess(src.index('transition_features[common_keys[1]]'),src.index('score_arms_now("BRANCH_POINT"'))

    def test_16_authorization_required_before_model_load(self):
        called=[]
        with mock.patch.dict(os.environ,{},clear=True):
            with self.assertRaises(d.TechnicalInvalid): d.execute_development(model_loader=lambda:called.append(1))
        self.assertEqual(called,[])

    def test_17_synthetic_full_family_orchestration(self):
        from types import SimpleNamespace
        a=d._authorities(); family=a['source']['families'][0]
        sk=__import__('cpds_graphfork_contract_validator_v2').structural_family_key(family)
        assignment=a['assignment_by_key'][sk]; witness=a['witness_by_graph'][family['source_graph_id']]
        imm=family['immediate_next_command_canonical']; c1=witness['common_prefix_steps'][0]['command']; c2=witness['common_prefix_steps'][1]['command']
        branches=tuple(sorted(family['branch_A_equivalence_class']+family['branch_B_equivalence_class']+['look']))
        class FakeEnv:
            def __init__(self): self.phase=0; self.observation='reset-observation'; self.admissible_commands=[imm,'look']
            def step(self,cmd):
                expected=[imm,c1,c2][self.phase]
                if cmd!=expected: return SimpleNamespace(error='bad',observation=self.observation)
                self.phase+=1; self.observation=f'obs-{self.phase}'
                self.admissible_commands=([c1,'look'] if self.phase==1 else ([c2,'look'] if self.phase==2 else list(branches)))
                return SimpleNamespace(error=None,observation=self.observation)
            def close(self): pass
        def factory(_): return FakeEnv()
        def vec(i):
            x=[0.0]*2048; x[i]=1.0; return x
        def fake_hidden(_torch,_tok,_model,payload):
            text=payload.decode('utf-8')
            if '"command":"'+c1.replace('\\','\\\\').replace('"','\\"')+'"' in text: return vec(1)
            if '"command":"'+c2.replace('\\','\\\\').replace('"','\\"')+'"' in text: return vec(2)
            return vec(0)
        def fake_site(_torch,_tok,_model,_goal,obs,candidates):
            acts=tuple(sorted(candidates)); base={x:-10.0*i for i,x in enumerate(acts)}
            af={x:vec(3+(i%10)) for i,x in enumerate(acts)}
            return {'prompt':'PROMPT-'+obs,'candidates':acts,'base_scores':base,'action_features':af}
        with tempfile.NamedTemporaryFile() as tf, mock.patch.object(d,'_game_file',lambda _gid:pathlib.Path(tf.name)), mock.patch.object(d,'_score_site',fake_site), mock.patch.object(r,'native_hidden_feature',fake_hidden):
            out=d._execute_family(family,witness,assignment,None,None,None,factory)
        self.assertEqual(out['family_id'],assignment['family_id'])
        self.assertEqual(len(out['slot_records']),6)
        self.assertTrue(out['oneshot_static_branch_maps_equal'])
        self.assertTrue(out['guards']['graph_admissibility'])
        self.assertTrue(out['guards']['call_geometry_or_arm_matching'])
        self.assertIn('static',out['endpoint']['C'])

    def test_18_technical_terminal_has_no_partial_science(self):
        with tempfile.TemporaryDirectory() as td:
            old=d.OUTPUT_DIR
            try:
                d.OUTPUT_DIR=pathlib.Path(td)/'terminal-dir'
                with mock.patch.dict(os.environ,{'CPDS_DEVELOPMENT_AUTHORIZATION':'RESEARCH_DECISION_BOUND'}), mock.patch.object(d,'execute_development',side_effect=d.TechnicalInvalid('X')):
                    self.assertEqual(d.main(),70)
                o=json.loads((d.OUTPUT_DIR/d.TERMINAL_NAME).read_text())
                self.assertEqual(o['scientific_result'],'TECHNICAL_INVALID_ENTIRE_SPLIT_NOT_ASSESSED')
                self.assertFalse(o['partial_scientific_outcomes_exposed'])
                self.assertEqual(o['confirmation_status'],'HARD_SEALED_NO_RUNTIME_ROUTE')
            finally: d.OUTPUT_DIR=old

if __name__=='__main__': unittest.main()
