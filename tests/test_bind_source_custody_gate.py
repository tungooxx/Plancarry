import copy
import unittest
from research.bind_source_custody_gate import audit, digest, frozen_candidate_identity


def make_manifest():
    m = {'schema':'plancarry.bind.g1.v0.1','phase':'FROZEN_MANIFEST',
         'pinned': {'evaluator_sha256':'a'*64,'source_protocol_sha256':'b'*64,'confirmation_touched':False,'binding_model_calls':0},
         'candidates':[{'candidate_id':f'c{i:02d}','split':'train','game_sha256':f'{i+1:064x}',
                        'source_family_id':f'family{i:02d}',
                        'consumption_audit':{'status':'VERIFIED_UNUSED','evidence_id':f'claimed-{i}'},
                        'qualification':None} for i in range(32)]}
    m['frozen_sha256']=digest(frozen_candidate_identity(m))
    return m


def make_ledger():
    return {'schema':'plancarry.bind.prior-consumption.v0.2',
            'dataset_manifest_sha256':'c'*64, 'inventory_snapshot_sha256':'d'*64,
            'scope':'ALL_HISTORICAL_PROJECT_USES',
            'records':[{'run_id':'old-train-1','artifact_sha256':'e'*64,'source_split':'train',
                        'inspected_game_sha256':['f'*64]}]}


class ProvenanceTests(unittest.TestCase):
    def test_no_overlap_is_not_certified(self):
        self.assertEqual(audit(make_manifest(),make_ledger())['verdict'],'BLOCKED_FRESHNESS_UNATTESTED')
    def test_prior_train_overlap_rejected(self):
        m,l=make_manifest(),make_ledger()
        l['records'][0]['inspected_game_sha256']=[m['candidates'][3]['game_sha256']]
        r=audit(m,l)
        self.assertEqual(r['verdict'],'BLOCKED_KNOWN_CONSUMPTION')
        self.assertEqual(r['known_overlaps'][0]['candidate_index'],3)
    def test_cross_split_content_reuse_rejected(self):
        m,l=make_manifest(),make_ledger()
        l['records'][0]['source_split']='valid_seen'
        l['records'][0]['inspected_game_sha256']=[m['candidates'][0]['game_sha256']]
        self.assertEqual(audit(m,l)['verdict'],'BLOCKED_KNOWN_CONSUMPTION')
    def test_missing_frozen_sha_fails_closed(self):
        m=make_manifest();m['frozen_sha256']=None
        self.assertEqual(audit(m,make_ledger())['verdict'],'INVALID_AUDIT_INPUT')
    def test_postfreeze_candidate_swap_detected(self):
        m=make_manifest();m['candidates'][0]['game_sha256']='f'*64
        self.assertEqual(audit(m,make_ledger())['verdict'],'INVALID_AUDIT_INPUT')
    def test_treatment_qualification_not_accepted(self):
        m=make_manifest();m['candidates'][0]['qualification']={'status':'ELIGIBLE'}
        self.assertEqual(audit(m,make_ledger())['verdict'],'INVALID_AUDIT_INPUT')
    def test_confirmation_forbidden(self):
        m=make_manifest();m['pinned']['confirmation_touched']=True
        self.assertEqual(audit(m,make_ledger())['verdict'],'INVALID_AUDIT_INPUT')
    def test_missing_history_fails(self):
        l=make_ledger();l['records']=[]
        self.assertEqual(audit(make_manifest(),l)['verdict'],'INVALID_AUDIT_INPUT')
    def test_partial_history_fails(self):
        l=make_ledger();l['scope']='PARTIAL'
        self.assertEqual(audit(make_manifest(),l)['verdict'],'INVALID_AUDIT_INPUT')
    def test_wrong_split_fails(self):
        m=make_manifest();m['candidates'][0]['split']='valid_unseen'
        self.assertEqual(audit(m,make_ledger())['verdict'],'INVALID_AUDIT_INPUT')
    def test_duplicate_game_fails(self):
        m=make_manifest();m['candidates'][0]['game_sha256']=m['candidates'][1]['game_sha256']
        m['frozen_sha256']=digest(frozen_candidate_identity(m))
        self.assertEqual(audit(m,make_ledger())['verdict'],'INVALID_AUDIT_INPUT')
    def test_duplicate_run_id_fails(self):
        l=make_ledger();l['records'].append(copy.deepcopy(l['records'][0]))
        self.assertEqual(audit(make_manifest(),l)['verdict'],'INVALID_AUDIT_INPUT')
    def test_empty_input_fails(self):
        self.assertEqual(audit(None, {})['verdict'],'INVALID_AUDIT_INPUT')

if __name__ == '__main__':
    unittest.main()
