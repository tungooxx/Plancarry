import copy, json, unittest
from pathlib import Path
from cpds_graphfork_contract_validator_v1 import structural_family_key as v1_structural_family_key
from cpds_graphfork_contract_validator_v2 import (
    generate_certificate, generator_identity, source_snapshot_identity, structural_family_key,
    validate_contract_files, validate_generator_spec,
)
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'results'/'design'
SPEC=json.loads((D/'plancarry_cpds_graphfork_generator_spec_v2_20260829.json').read_text())

def family(): return {'source_graph_id':'g1','goal_canonical':'put object','reset_observation_canonical':'room','allowed_pre_reset_history_canonical':['look','go north'],'immediate_next_command_canonical':'open door','common_prefix_transition_keys':['t1','t2'],'branch_A_equivalence_class':['a1','a2'],'branch_B_equivalence_class':['b1'],'divergence_depth_after_immediate':2}
def witness(): return {'source_graph_id':'g1','initial_state_id':'s0','reset_state_id':'sr','pre_reset_steps':[{'transition_key':'p1','command':'look','from_state_id':'s0','to_state_id':'s1'},{'transition_key':'p2','command':'go north','from_state_id':'s1','to_state_id':'sr'}],'immediate_step':{'transition_key':'imm','command':'open door','from_state_id':'sr','to_state_id':'s2'},'common_prefix_steps':[{'transition_key':'t1','command':'take','from_state_id':'s2','to_state_id':'s3'},{'transition_key':'t2','command':'move','from_state_id':'s3','to_state_id':'s4'}],'branch_A_equivalence_class':['a1','a2'],'branch_B_equivalence_class':['b1'],'divergence_depth_after_immediate':2}
def snapshot(f=None,w=None):
    s={'snapshot_id':'snap','static_graph_replayability_witnesses':[w or witness()],'families':[f or family()]}; s['snapshot_sha256']=source_snapshot_identity(s); return s
class T(unittest.TestCase):
 def cert(self,f=None,w=None,s=None):
    s=s or snapshot(f,w); return generate_certificate(f or family(),SPEC,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1',s,s['snapshot_sha256'])
 def test_contract_spec_and_valid_certificate(self):
    self.assertTrue(validate_generator_spec(SPEC)); self.assertEqual(SPEC['generator_identity_sha256'],generator_identity(SPEC)); self.assertTrue(validate_contract_files(D/'plancarry_cpds_graphfork_constructibility_contract_v2_20260829.json',D/'plancarry_cpds_graphfork_generator_spec_v2_20260829.json')); self.assertEqual(self.cert()['source_admission'],'STATIC_GRAPH_REPLAYABILITY_ONLY')
 def test_v1_structural_key_continuity(self):
    old=family(); old['local_source_competence_preoutcome']=True; self.assertEqual(v1_structural_family_key(old),structural_family_key(family()))
 def test_old_behavioral_field_is_rejected(self):
    f=family(); f['local_source_competence_preoutcome']=True; s=snapshot(); s['families']=[f]; s['snapshot_sha256']=source_snapshot_identity(s)
    with self.assertRaises(ValueError): generate_certificate(f,SPEC,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1',s,s['snapshot_sha256'])
 def test_missing_or_duplicate_witness_rejected(self):
    for ws in [[],[witness(),copy.deepcopy(witness())]]:
      s=snapshot(); s['static_graph_replayability_witnesses']=ws; s['snapshot_sha256']=source_snapshot_identity(s)
      with self.assertRaises(ValueError): generate_certificate(family(),SPEC,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1',s,s['snapshot_sha256'])
 def test_history_and_state_chain_tamper_rejected(self):
    muts=[]
    w=witness(); w['pre_reset_steps'][0]['command']='inventory'; muts.append(w)
    w=witness(); w['pre_reset_steps'][1]['from_state_id']='wrong'; muts.append(w)
    w=witness(); w['reset_state_id']='wrong'; muts.append(w)
    for w in muts:
      with self.assertRaises(ValueError): self.cert(w=w)
 def test_immediate_and_common_legality_tamper_rejected(self):
    muts=[]
    w=witness(); w['immediate_step']['command']='close door'; muts.append(w)
    w=witness(); w['immediate_step']['from_state_id']='wrong'; muts.append(w)
    w=witness(); w['common_prefix_steps'][0]['transition_key']='other'; muts.append(w)
    w=witness(); w['common_prefix_steps'][1]['from_state_id']='wrong'; muts.append(w)
    for w in muts:
      with self.assertRaises(ValueError): self.cert(w=w)
 def test_branch_and_divergence_tamper_rejected(self):
    muts=[]
    w=witness(); w['branch_A_equivalence_class']=['other']; muts.append(w)
    w=witness(); w['divergence_depth_after_immediate']=3; muts.append(w)
    for w in muts:
      with self.assertRaises(ValueError): self.cert(w=w)
 def test_forbidden_future_outcome_fields_rejected_recursively(self):
    for key in ['whole_task_success','future_oracle_trajectory','teacher_plan','local_source_competence_preoutcome','per_family_model_evaluability']:
      w=witness(); w['common_prefix_steps'][0][key]=True; s=snapshot(w=w)
      with self.assertRaises(ValueError): generate_certificate(family(),SPEC,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1',s,s['snapshot_sha256'])
 def test_external_snapshot_seal_and_membership_rejected(self):
    s=snapshot()
    with self.assertRaises(ValueError): generate_certificate(family(),SPEC,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1',s,'0'*64)
    original_seal=s['snapshot_sha256']; tampered=copy.deepcopy(s); tampered['static_graph_replayability_witnesses'][0]['pre_reset_steps'][0]['command']='inventory'; tampered['snapshot_sha256']=source_snapshot_identity(tampered)
    with self.assertRaises(ValueError): generate_certificate(family(),SPEC,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1',tampered,original_seal)
    other=family(); other['goal_canonical']='different';
    with self.assertRaises(ValueError): generate_certificate(other,SPEC,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1',s,s['snapshot_sha256'])
 def test_contract_preserves_causal_core_and_makes_model_guard_whole_split_only(self):
    c=json.loads((D/'plancarry_cpds_graphfork_constructibility_contract_v2_20260829.json').read_text()); v1=json.loads((D/'plancarry_cpds_graphfork_constructibility_contract_v1_20260829.json').read_text())
    self.assertEqual(c['arms'],v1['arms']); self.assertEqual(c['primary_probe'],v1['primary_probe']); self.assertEqual(c['matching_invariants'],v1['matching_invariants']); self.assertEqual(c['machine_validation_rules'],v1['machine_validation_rules'])
    rep=c['graph_family_generator']['source_admission_semantic_repair']; self.assertIn('WHOLE_SPLIT_ONLY_NONFILTERING',rep['later_model_evaluability_guard']); self.assertNotIn('local_source_competence_pre_outcome',c['eligibility_and_guards']['eligibility_allowed'])
if __name__=='__main__': unittest.main()
