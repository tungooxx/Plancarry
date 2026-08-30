import ast,copy,json,math,pathlib,unittest
import cpds_development_runtime_v1 as m

class TestCPDSDevelopmentRuntime(unittest.TestCase):
 def test_contract_and_authority_static(self):
  c=m.load_contract(); self.assertEqual(c['scientific_result'],'NOT_ASSESSED'); self.assertTrue(m.verify_frozen_authorities())
  self.assertEqual(c['confirmation_seal']['status'],'HARD_SEALED'); self.assertFalse(c['confirmation_seal']['runtime_route_present'])
 def test_no_top_level_science_imports(self):
  t=ast.parse(pathlib.Path(m.__file__).read_text()); mods=[]
  for n in t.body:
   if isinstance(n,ast.Import): mods.extend(a.name.split('.')[0] for a in n.names)
   if isinstance(n,ast.ImportFrom) and n.module: mods.append(n.module.split('.')[0])
  self.assertTrue({'torch','transformers','alfworld','textworld'}.isdisjoint(mods))
 def test_prompt_exact_and_branch_blind(self):
  p=m.render_policy_prompt('put mug','room',['z','a']); self.assertEqual(p,'TASK\nput mug\nCURRENT OBSERVATION\nroom\nADMISSIBLE COMMANDS\na\nz\n<STATE_END>\nACTION:')
  self.assertNotIn('branch',p.lower()); self.assertNotIn('correct',p.lower())
 def test_serialization_exact(self):
  self.assertEqual(m.canonical_action_payload('open door'),b'{"action":"open door"}')
  self.assertEqual(m.canonical_transition_payload('open','room'),b'{"command":"open","observation":"room"}')
 def test_endpoint_ab_swap_invariant(self):
  maps={g:{'a1':-1.0,'a2':-2.0,'b1':-3.0} for g in m.EXACT_ARMS}; maps['ALIGNED_RECURSION']={'a1':0.5,'a2':-2.0,'b1':-3.0}; maps['STATIC_REPEAT']={'a1':-0.5,'a2':-2.0,'b1':-3.0}; maps['TRANSITION_PERMUTED']={'a1':-0.25,'a2':-2.0,'b1':-3.0}
  x=m.v4_endpoint_from_sealed_scores(maps,['a1','a2'],['b1']); y=m.v4_endpoint_from_sealed_scores(maps,['b1'],['a1','a2'])
  for g in m.EXACT_ARMS: self.assertAlmostEqual(x['R'][g],-y['R'][g],places=12); self.assertAlmostEqual(x['D'][g],y['D'][g],places=12)
  for k in x['C']: self.assertAlmostEqual(x['C'][k],y['C'][k],places=12)
  self.assertEqual(x['correctness_semantics'],'UNDEFINED_AND_FORBIDDEN')
 def test_endpoint_requires_complete_sealed_maps(self):
  maps={g:{'a':0.0,'b':0.0} for g in m.EXACT_ARMS}; bad=dict(maps); bad.pop('NO_CARRY'); self.assertRaisesRegex(ValueError,'SEALED_ARM_ORDER',m.v4_endpoint_from_sealed_scores,bad,['a'],['b'])
  self.assertRaisesRegex(ValueError,'BRANCH_CLASSES',m.v4_endpoint_from_sealed_scores,maps,['a'],['a'])
 def test_recurrence_arm_semantics(self):
  z=[0.0]*2048;z[0]=1.0;x1=[0.0]*2048;x1[0]=1.0;x2=[0.0]*2048;x2[1]=1.0; q={'a':z}; base={'a':0.0}; feats={'t1':x1,'t2':x2}
  aligned=m.adjust_score_map('ALIGNED_RECURSION',base,z,feats,['t1','t2'],q)
  perm=m.adjust_score_map('TRANSITION_PERMUTED',base,z,feats,['t2','t1'],q)
  self.assertTrue(math.isfinite(aligned['a']) and math.isfinite(perm['a'])); self.assertNotEqual(aligned,perm)
  self.assertEqual(m.adjust_score_map('NO_CARRY',base,z,feats,['t1','t2'],q),base)
 def test_duplicate_transition_order_fails(self):
  z=[0.0]*2048;z[0]=1.0; q={'a':z}; self.assertRaisesRegex(ValueError,'TRANSITION_ORDER',m.adjust_score_map,'ALIGNED_RECURSION',{'a':0.0},z,{'t':z},['t','t'],q)
 def test_contract_tamper_fails(self):
  c=m.load_contract(); c['branch_blind_endpoint']['correctness_semantics']='CORRECT_BRANCH_A'; c['contract_sha256']=m.self_hash(c,'contract_sha256'); self.assertRaisesRegex(ValueError,'BRANCH_BLINDNESS',m.validate_contract,c)
  c=m.load_contract(); c['authority']['source_authority_seal']='0'*64; c['contract_sha256']=m.self_hash(c,'contract_sha256'); self.assertRaisesRegex(ValueError,'AUTHORITY_BINDING',m.validate_contract,c)
 def test_confirmation_not_read_by_data_preflight_source(self):
  src=pathlib.Path(m.__file__).read_text(); node=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name=='verify_development_data'); text=ast.get_source_segment(src,node)
  self.assertIn('selected_development_source_graph_ids',text); self.assertNotIn('selected_confirmation_source_graph_ids',text)
 def test_common_score_offset_invariance_and_zero_tie(self):
  maps={g:{'a':-2.0,'b':-2.0} for g in m.EXACT_ARMS}; maps['ALIGNED_RECURSION']={'a':-1.0,'b':-2.0}
  x=m.v4_endpoint_from_sealed_scores(maps,['a'],['b'])
  shifted={g:{a:v+17.25 for a,v in sm.items()} for g,sm in maps.items()}; y=m.v4_endpoint_from_sealed_scores(shifted,['a'],['b'])
  for g in m.EXACT_ARMS: self.assertAlmostEqual(x['R'][g],y['R'][g],places=12); self.assertAlmostEqual(x['D'][g],y['D'][g],places=12)
  tie={g:{'a':0.0,'b':0.0} for g in m.EXACT_ARMS}; z=m.v4_endpoint_from_sealed_scores(tie,['a'],['b']); self.assertEqual(z['C']['static'],0.0); self.assertEqual(z['C']['permuted'],0.0)
 def test_model_cache_quick_binding_and_dev_data_only(self):
  got=m.verify_model_cache(full_weight_hash=False); self.assertGreaterEqual(len(got),9)
  d=m.verify_development_data(); self.assertEqual(d['development_files_verified'],33); self.assertEqual(d['confirmation_files_opened'],0)
 def test_decision_handoff_exact_and_confirmation_absent(self):
  c=m.load_contract(); h=c['decision_handoff']; self.assertEqual(h['command'],'bash cpds_development_primary_v1.sh development'); self.assertEqual(h['working_directory'],'/workspace/local-vlm/LLM/plancarry-cpds-development'); self.assertIsNone(h['python_env']); self.assertEqual(h['environment']['CPDS_DEVELOPMENT_AUTHORIZATION'],'RESEARCH_DECISION_BOUND'); self.assertFalse(c['confirmation_seal']['runtime_route_present'])
 def test_static_audit_self_hash_and_zero_actions(self):
  a=json.loads(pathlib.Path('results/design/plancarry_cpds_development_runtime_static_audit_a5_20260830.json').read_text()); got=a.pop('audit_sha256'); self.assertEqual(got,m.sha_bytes(m.canonical_bytes(a))); self.assertTrue(all(v==0 for v in a['prohibited_actions_observed'].values())); self.assertFalse(a['implementation_guards']['confirmation_runtime_route_present'])
 def test_launcher_development_fails_without_decision(self):
  s=pathlib.Path('cpds_development_primary_v1.sh').read_text(); self.assertIn('RESEARCH_DECISION_BOUND',s); self.assertIn('SEPARATE_REVIEWED_EXECUTION_WORKITEM',s)

if __name__=='__main__': unittest.main()
