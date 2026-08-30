from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import torch

import cpds_v5_predictive_recurrence_v1 as rt
import cpds_v5_train_calibration_v1 as tc
import cpds_v5_provenance_v1 as pv
from cpds_v5_partition_v1 import partition_name
from tests.test_cpds_v5_predictive_recurrence_runtime import packet

class T(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(20260830); torch.set_num_threads(1)
        self.recipe=tc.load_recipe()
        self.seal_path=Path(self.recipe['provenance']['v4_reserved_structural_key_hash_seal']['path'])
        self.seal,self.seal_sha=pv.load_reserved_v4_hash_seal(self.seal_path,self.recipe)

    def _graph(self, part):
        reserved=set(self.seal['structural_family_key_sha256s'])
        for i in range(10000):
            g=f'prov-{part.lower()}-{i}'
            if partition_name(g)==part and hashlib.sha256(g.encode()).hexdigest() not in reserved:
                return g
        raise AssertionError

    def test_reserved_seal_is_exact_v4_33x2_union(self):
        dev=json.loads(Path('results/design/plancarry_cpds_actual_development_generator_manifest_v3_20260829.json').read_text())
        conf=json.loads(Path('results/design/plancarry_cpds_actual_confirmation_generator_manifest_v3_20260829.json').read_text())
        expected=sorted(set(dev['structural_family_key_sha256s'])|set(conf['structural_family_key_sha256s']))
        self.assertEqual(len(expected),66)
        self.assertEqual(self.seal['structural_family_key_sha256s'],expected)
        self.assertEqual(self.recipe['provenance']['v4_reserved_structural_key_hash_seal']['file_sha256'],self.seal_sha)

    def test_reserved_seal_is_mandatory_and_tamper_fails(self):
        g=self._graph('TRAIN')
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); (d/'p.json').write_text(json.dumps(packet(g,'TRAIN')))
            with self.assertRaisesRegex(ValueError,'V4_RESERVED_HASH_SEAL_REQUIRED'):
                tc.load_packet_dir(d,'TRAIN',None,self.recipe)
            self.assertEqual(len(tc.load_packet_dir(d,'TRAIN',self.seal_path,self.recipe)),1)
            bad=d/'bad_seal.json'; payload=json.loads(self.seal_path.read_text()); payload['structural_family_key_sha256s']=payload['structural_family_key_sha256s'][1:]; bad.write_text(json.dumps(payload,sort_keys=True,separators=(',',':'))+'\n')
            with self.assertRaisesRegex(ValueError,'V4_RESERVED_HASH_SEAL_SHA'):
                tc.load_packet_dir(d,'TRAIN',bad,self.recipe)

    def test_checkpoint_calibration_binding_requires_exact_train_source_provenance(self):
        g=self._graph('TRAIN'); p=packet(g,'TRAIN')
        train_prov=pv.build_train_provenance([p],self.seal_sha)
        recipe_sha=hashlib.sha256(tc.RECIPE_PATH.read_bytes()).hexdigest()
        model=rt.CPDSV5Adapter().eval()
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); ck=d/'m.ckpt'
            cki=rt.save_deterministic_checkpoint(ck,model,recipe_sha256=recipe_sha,provenance=train_prov)
            manifest={'schema':pv.TRAIN_MANIFEST_SCHEMA,'scientific_result':'NOT_ASSESSED_TRAIN_ONLY','realization':rt.REALIZATION,'recipe_sha256':recipe_sha,'reserved_v4_hash_seal_sha256':self.seal_sha,'checkpoint_sha256':cki['sha256'],'checkpoint_bytes':cki['bytes'],'checkpoint_header_sha256':cki['header_sha256'],'train_provenance':train_prov,'train':{'seed':20260830},'development_access':False,'confirmation_access':False}
            mp=d/'train.json'; mp.write_bytes(rt.canonical_bytes(manifest)); msha=hashlib.sha256(mp.read_bytes()).hexdigest()
            out=pv.validate_calibration_checkpoint_binding(checkpoint_path=ck,checkpoint_sha256=cki['sha256'],recipe_sha256=recipe_sha,reserved_v4_hash_seal_sha256=self.seal_sha,train_manifest_path=mp,train_manifest_sha256=msha)
            self.assertEqual(out['train_provenance'],train_prov)
            with self.assertRaisesRegex(ValueError,'TRAIN_MANIFEST_SHA'):
                pv.validate_calibration_checkpoint_binding(checkpoint_path=ck,checkpoint_sha256=cki['sha256'],recipe_sha256=recipe_sha,reserved_v4_hash_seal_sha256=self.seal_sha,train_manifest_path=mp,train_manifest_sha256='0'*64)
            bad=dict(manifest); bad['train_provenance']=dict(train_prov); bad['train_provenance']['source_graph_ids_sha256']='1'*64
            bmp=d/'bad_train.json'; bmp.write_bytes(rt.canonical_bytes(bad)); bsha=hashlib.sha256(bmp.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'TRAIN_MANIFEST_CHECKPOINT_PROVENANCE'):
                pv.validate_calibration_checkpoint_binding(checkpoint_path=ck,checkpoint_sha256=cki['sha256'],recipe_sha256=recipe_sha,reserved_v4_hash_seal_sha256=self.seal_sha,train_manifest_path=bmp,train_manifest_sha256=bsha)
            with self.assertRaisesRegex(ValueError,'TRAIN_MANIFEST_RESERVED_SEAL_SHA|CHECKPOINT_RESERVED_SEAL_SHA'):
                pv.validate_calibration_checkpoint_binding(checkpoint_path=ck,checkpoint_sha256=cki['sha256'],recipe_sha256=recipe_sha,reserved_v4_hash_seal_sha256='2'*64,train_manifest_path=mp,train_manifest_sha256=msha)

    def test_cli_requires_seal_and_train_manifest_hash(self):
        src=Path(tc.__file__).read_text()
        self.assertIn('t.add_argument("--reserved-v4-hashes",required=True)',src)
        self.assertIn('c.add_argument("--reserved-v4-hashes",required=True)',src)
        self.assertIn('c.add_argument("--train-manifest",required=True)',src)
        self.assertIn('c.add_argument("--train-manifest-sha256",required=True)',src)

if __name__=='__main__': unittest.main()
