import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import cpds_actual_33x2_freeze_v1 as m
import cpds_executable_readiness_v1 as readiness

class TestActual33x2Freeze(unittest.TestCase):
    def test_partition_and_selection_are_deterministic(self):
        x='unit/example'; self.assertEqual(m._partition(x),m._partition(x)); self.assertEqual(m._selection_key(x),m._selection_key(x)); self.assertEqual(len(m._selection_key(x)),64)
    def test_json_string_field_extract_skips_other_fields(self):
        raw=b'{"pddl_problem":"abc\\ndef","walkthrough":["SECRET"]}'
        self.assertEqual(m._extract_json_string_field(raw,'pddl_problem'),'abc\ndef')
        self.assertNotIn('SECRET',m._extract_json_string_field(raw,'pddl_problem'))
    def test_balanced_goal(self):
        s='x (:goal (and (p a) (q b))) tail'; i=s.index('(:goal'); self.assertEqual(m._balanced_form(s,i),'(:goal (and (p a) (q b)))')
    def test_state_and_transition_determinism(self):
        s0=m._state_id('g','a'*64,'l0',[]); s1=m._state_id('g','a'*64,'l1',[]); st=m._step('g','GotoLocation(agent1,l0,l1,r1)',s0,s1)
        self.assertEqual(st,m._step('g','GotoLocation(agent1,l0,l1,r1)',s0,s1)); self.assertNotEqual(st['from_state_id'],st['to_state_id'])
    def _snapshot(self, namespace, tag):
        fam=[]; wit=[]
        for i in range(33):
            g=f'{tag}-{i}'; s0=hashlib.sha256((g+'0').encode()).hexdigest(); s1=hashlib.sha256((g+'1').encode()).hexdigest(); s2=hashlib.sha256((g+'2').encode()).hexdigest(); s3=hashlib.sha256((g+'3').encode()).hexdigest()
            c0=f'goto-{g}-s1'; c1=f'examine-{g}'; c2=f'goto-{g}-s2'
            k1=m._transition_key(g,c1,s1,s2); k2=m._transition_key(g,c2,s2,s3)
            f={'source_graph_id':g,'goal_canonical':f'goal {g}','reset_observation_canonical':f'state {s0}','allowed_pre_reset_history_canonical':[],'immediate_next_command_canonical':c0,'common_prefix_transition_keys':[k1,k2],'branch_A_equivalence_class':[f'A-{g}'],'branch_B_equivalence_class':[f'B-{g}'],'divergence_depth_after_immediate':3}
            w={'source_graph_id':g,'initial_state_id':s0,'reset_state_id':s0,'pre_reset_steps':[],'immediate_step':m._step(g,c0,s0,s1),'common_prefix_steps':[m._step(g,c1,s1,s2),m._step(g,c2,s2,s3)],'branch_A_equivalence_class':[f'A-{g}'],'branch_B_equivalence_class':[f'B-{g}'],'divergence_depth_after_immediate':3}
            fam.append(f); wit.append(w)
        ss={'snapshot_id':f'snap-{tag}','snapshot_sha256':'0'*64,'static_graph_replayability_witnesses':wit,'families':fam}; ss['snapshot_sha256']=m.v2.source_snapshot_identity(ss); return ss
    def test_v2_manifest_and_disjointness(self):
        d=self._snapshot(readiness.DEVELOPMENT_NAMESPACE,'d'); c=self._snapshot(readiness.CONFIRMATION_NAMESPACE,'c')
        dm=m.build_v2_manifest(d,readiness.DEVELOPMENT_NAMESPACE,m.SOURCE_AUTHORITY_SEAL); cm=m.build_v2_manifest(c,readiness.CONFIRMATION_NAMESPACE,m.SOURCE_AUTHORITY_SEAL)
        self.assertTrue(m.validate_split_disjointness(d,dm,c,cm)); self.assertEqual(dm['certificate_count'],33); self.assertEqual(cm['certificate_count'],33)
    def test_assignment_adapter_exact_authority(self):
        d=self._snapshot(readiness.DEVELOPMENT_NAMESPACE,'d2'); dm=m.build_v2_manifest(d,readiness.DEVELOPMENT_NAMESPACE,m.SOURCE_AUTHORITY_SEAL)
        code='1'*64
        def wf(fid): return iter([0])
        am=m.build_assignment_manifest_v2(dm,wf,code); self.assertTrue(m.validate_assignment_manifest_v2(am,dm,code)); self.assertEqual(len(am['records']),33); self.assertTrue(all(r['assignment_index']==0 for r in am['records']))
    def test_tampered_manifest_fails(self):
        d=self._snapshot(readiness.DEVELOPMENT_NAMESPACE,'d3'); dm=m.build_v2_manifest(d,readiness.DEVELOPMENT_NAMESPACE,m.SOURCE_AUTHORITY_SEAL); bad=copy.deepcopy(dm); bad['family_ids'][0]='0'*64; bad['manifest_sha256']=m.manifest_identity(bad)
        with self.assertRaises(ValueError): m.validate_v2_manifest(bad,d,bad['manifest_sha256'])

if __name__=='__main__': unittest.main()
