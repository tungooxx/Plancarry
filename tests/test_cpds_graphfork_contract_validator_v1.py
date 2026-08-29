import copy, json, pathlib, unittest
from cpds_graphfork_contract_validator_v1 import *
ROOT=pathlib.Path(__file__).resolve().parents[1]
D=ROOT/'results'/'design'
CONTRACT=D/'plancarry_cpds_graphfork_constructibility_contract_v1_20260829.json'
CASES=D/'plancarry_cpds_graphfork_adversarial_cases_v1_20260829.json'
SPEC=D/'plancarry_cpds_graphfork_generator_spec_v1_20260829.json'

def sample_family(tag='x'):
    return {'source_graph_id':'g-'+tag,'goal_canonical':'put object','reset_observation_canonical':'room','allowed_pre_reset_history_canonical':['look'],'immediate_next_command_canonical':'open door','common_prefix_transition_keys':['t1','t2'],'branch_A_equivalence_class':['a1','a2'],'branch_B_equivalence_class':['b1'],'divergence_depth_after_immediate':2,'local_source_competence_preoutcome':True}

class TestCPDSGraphForkContract(unittest.TestCase):
    def test_contract_and_all_adversarial_fixtures(self):
        out=validate_contract_files(CONTRACT,CASES,SPEC)
        self.assertTrue(out['all_passed']); self.assertEqual(out['rules'],16); self.assertGreaterEqual(out['fixtures'],29)
    def test_generator_identity_and_canonical_family_identity(self):
        spec=json.loads(SPEC.read_text()); self.assertEqual(generator_identity(spec),spec['generator_identity_sha256'])
        f=sample_family(); rev={k:f[k] for k in reversed(list(f))}
        a=generate_certificate(f,spec,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1','0'*64)
        b=generate_certificate(rev,spec,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1','0'*64)
        self.assertEqual(a,b)
        tam=copy.deepcopy(spec); tam['algorithm_version']=2
        self.assertNotEqual(generator_identity(tam),spec['generator_identity_sha256'])
    def test_generator_rejects_branch_overlap_and_forbidden_outcome_field(self):
        spec=json.loads(SPEC.read_text()); f=sample_family(); f['branch_B_equivalence_class']=['a1']
        with self.assertRaisesRegex(ValueError,'BRANCH_OVERLAP'): generate_certificate(f,spec,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1','0'*64)
        f=sample_family(); f['whole_task_success']=True
        with self.assertRaisesRegex(ValueError,'FAMILY_SCHEMA'): generate_certificate(f,spec,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1','0'*64)
    def test_confirmation_cannot_be_reordered_development_or_structural_overlap(self):
        spec=json.loads(SPEC.read_text()); f=sample_family()
        dev=generate_certificates([f],spec,'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1','0'*64)
        conf=generate_certificates([f],spec,'CPDS_CONFIRMATION_GRAPH_FAMILIES_V1','1'*64)
        with self.assertRaisesRegex(ValueError,'STRUCTURAL_FAMILY_OVERLAP'): validate_disjoint(dev,conf)
        f2=sample_family('y'); conf2=generate_certificates([f2],spec,'CPDS_CONFIRMATION_GRAPH_FAMILIES_V1','1'*64)
        self.assertTrue(validate_disjoint(dev,conf2))

if __name__=='__main__': unittest.main()
