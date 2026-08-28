import copy, json, tempfile, unittest
from pathlib import Path
import replay_residual_t1_direct_override_causal_dev_v1 as d

INNER={
 'kind':'PLANCARRY_REPLAY_RESIDUAL_T1_DEVELOPMENT_SELECTION_V1','status':'FROZEN_T1_DEVELOPMENT_SELECTION',
 't1_prereg_sha256':d.T1_PREREG_SHA,'gap_matrix_sha256':d.GAP_SHA,'v2_1_contract_sha256':d.V21_SHA,
 'session_runtime_sha256':d.SESSION_SHA,'phase_runner_sha256':d.PHASE_SHA,'development_indices':list(range(32)),
 'qualified_indices':list(range(16)),'qualified_count':16,'development_payload_sha256':'1'*64,
 'source_anchor':'SOURCE_T2_LAST_TOKEN','target_site':'RESET_PREFIX_LAST_TOKEN_SAME_LAYER',
 'selection_rule':'max median specificity margin; tie ACTIVE TaskSuccess, lower alpha, earlier layer',
 'selected_layer':14,'selected_alpha':0.5,'selected_vector_sha256_by_family':{str(i):('a'*64) for i in range(16)},
 'selected_vector_map_sha256':'b'*64,'all_grid_aggregates':{'L14_A0.5':{'x':1}},'all_grid_aggregates_sha256':'c'*64,
 'confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY'
}
PAYLOAD={
 'sanity_status':'PASS_REPLAY_RESIDUAL_SANITY','prereg_compliance':{
  'status':d.OVERRIDE_STATUS,'original_sanity_pass_observed':False,'original_prereg_activation_gate_satisfied':False},
 'driver_sha256':'d'*64
}
class FakePhase:
 def select_development(self,payload,path):
  raw=d.pretty_json_bytes(INNER); Path(path).write_bytes(raw)
  return dict(INNER,seal_file_sha256=d.sha_bytes(raw))

class TestOverrideProvenance(unittest.TestCase):
 def test_write_validate_and_cleanup(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; private=d._override_inner_selection_path(pub)
   out=d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   self.assertTrue(pub.is_file()); self.assertFalse(private.exists())
   got=d.load_validate_override_development_seal(pub,out['seal_file_sha256'])
   self.assertEqual(got['kind'],d.OVERRIDE_SELECTION_KIND)
   self.assertEqual(got['prereg_compliance']['status'],d.OVERRIDE_STATUS)
   self.assertFalse(got['prereg_compliance']['original_sanity_pass_observed'])
   self.assertFalse(got['prereg_compliance']['original_prereg_activation_gate_satisfied'])
   self.assertTrue(got['user_directed_sanity_gate_override'])
   self.assertFalse(got['original_sanity_pass_observed']); self.assertFalse(got['original_prereg_activation_gate_satisfied'])
   self.assertEqual(got['selected_layer'],INNER['selected_layer']); self.assertEqual(got['selected_alpha'],INNER['selected_alpha'])
   self.assertEqual(got['selected_vector_sha256_by_family'],INNER['selected_vector_sha256_by_family'])
 def test_reject_plain_canonical_seal(self):
  with self.assertRaisesRegex(RuntimeError,'KIND_OR_STATUS'):
   d.validate_override_development_seal_obj(INNER)
 def test_reject_missing_override(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; out=d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   obj=json.loads(pub.read_text()); obj['prereg_compliance']['status']='PREREG_COMPLIANT'
   with self.assertRaisesRegex(RuntimeError,'PREREG_COMPLIANCE'):
    d.validate_override_development_seal_obj(obj)
 def test_reject_false_original_sanity_flags(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   obj=json.loads(pub.read_text()); obj['prereg_compliance']['original_sanity_pass_observed']=True
   with self.assertRaisesRegex(RuntimeError,'ORIGINAL_SANITY'):
    d.validate_override_development_seal_obj(obj)
 def test_reject_top_level_override_tamper(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   obj=json.loads(pub.read_text()); obj['user_directed_sanity_gate_override']=False
   with self.assertRaisesRegex(RuntimeError,'TOP_LEVEL_PROVENANCE'):
    d.validate_override_development_seal_obj(obj)
 def test_reject_protocol_hash_tamper(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   obj=json.loads(pub.read_text()); obj['t1_prereg_sha256']='0'*64
   with self.assertRaisesRegex(RuntimeError,'PROTOCOL_PROVENANCE'):
    d.validate_override_development_seal_obj(obj)
 def test_reject_inner_tamper(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   obj=json.loads(pub.read_text()); obj['phase_selection']['selected_alpha']=1.0; obj['selected_alpha']=1.0
   with self.assertRaisesRegex(RuntimeError,'INNER_SELECTION_HASH'):
    d.validate_override_development_seal_obj(obj)
 def test_reject_mirror_tamper_even_if_rehashed(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   obj=json.loads(pub.read_text()); obj['selected_layer']=21
   with self.assertRaisesRegex(RuntimeError,'MIRROR_MISMATCH'):
    d.validate_override_development_seal_obj(obj)
 def test_refuse_preexisting_private(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; private=d._override_inner_selection_path(pub); private.write_text('stale')
   with self.assertRaisesRegex(RuntimeError,'REFUSE_EXISTING_PRIVATE'):
    d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   self.assertTrue(private.exists())
 def test_public_file_hash_binding(self):
  with tempfile.TemporaryDirectory() as td:
   pub=Path(td)/'selection.json'; out=d.write_override_development_selection(PAYLOAD,FakePhase(),pub)
   with self.assertRaisesRegex(RuntimeError,'FILE_HASH_MISMATCH'):
    d.load_validate_override_development_seal(pub,'0'*64)
   d.load_validate_override_development_seal(pub,out['seal_file_sha256'])

if __name__=='__main__': unittest.main()
