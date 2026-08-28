import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

import plancarry_replayresidual_v22_researchos_vast_dispatch_v1 as d


class V22DispatchTests(unittest.TestCase):
    def live_attestation(self):
        return {
            'kind':d.LIVE_ATTESTATION_KIND,'experiment_id':d.EXPERIMENT_ID,
            'instance_id':d.EXPECTED_INSTANCE_ID,'device_name':d.EXPECTED_GPU,'driver':d.EXPECTED_DRIVER,
            'repo_path':d.REMOTE_REPO,'repo_commit':d.REMOTE_COMMIT,'launcher_path':d.LAUNCHER,
            'launcher_sha256':d.LAUNCHER_SHA256,'host_review_work_item_id':d.HOST_REVIEW_WORK_ITEM_ID,
            'host_review_verdict':d.HOST_REVIEW_PASS,'host_review_sha256':'1'*64,
            'hostkey_ed25519_sha256':'2'*64,'host':'203.0.113.10','port':12345,
            'future_split_access':False,'study_cohort_access':False,'provider_lifecycle_action':'NONE',
            'outputs_absent':True,
        }

    def write_att(self, td, mutate=None):
        x=self.live_attestation()
        if mutate: mutate(x)
        p=Path(td)/'att.json'; p.write_text(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n')
        return p,hashlib.sha256(p.read_bytes()).hexdigest()

    def test_live_attestation_exact(self):
        with tempfile.TemporaryDirectory() as td:
            p,h=self.write_att(td); self.assertEqual(d.load_live_attestation(p,h)['instance_id'],d.EXPECTED_INSTANCE_ID)

    def test_live_attestation_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p,h=self.write_att(td); p.write_text(p.read_text().replace(d.EXPECTED_GPU,'OTHER'))
            with self.assertRaisesRegex(ValueError,'SHA_MISMATCH'): d.load_live_attestation(p,h)

    def test_live_attestation_future_access_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p,h=self.write_att(td,lambda x:x.__setitem__('future_split_access',True))
            with self.assertRaisesRegex(ValueError,'ACCESS_GUARD'): d.load_live_attestation(p,h)

    def test_declared_paths_exact_only(self):
        for p in d.DECLARED_OUTPUTS:self.assertEqual(d.validate_declared_relpath(p),p)
        for p in ['../x','/abs','results/science/valid_unseen/x','results/science/other.json']:
            with self.assertRaises(ValueError):d.validate_declared_relpath(p)

    def test_remote_execution_binding_exact(self):
        cmd=d.remote_execution_command()
        self.assertIn('REPLAYRESIDUAL_V22_EXECUTION_AUTHORIZATION=RESEARCH_DECISION_BOUND',cmd)
        self.assertIn(d.REMOTE_REPO+'/'+d.BOUND_CONTRACT,cmd)
        self.assertIn(d.REMOTE_REPO+'/'+d.RESET_CANARY,cmd)
        self.assertIn(d.REMOTE_REPO+'/'+d.EXECUTION_ATTESTATION,cmd)
        self.assertIn("bash '"+d.LAUNCHER+"' execute" if ' ' in d.LAUNCHER else 'bash '+d.LAUNCHER+' execute',cmd)
        self.assertNotIn('valid_seen',cmd);self.assertNotIn('valid_unseen',cmd);self.assertNotIn('reserve32',cmd)

    def test_preflight_checks_exact_commit_gpu_driver_hashes_and_absence(self):
        cmd=d.remote_preflight_command()
        for needle in [d.REMOTE_COMMIT,d.EXPECTED_GPU,d.EXPECTED_DRIVER,d.LAUNCHER_SHA256,d.BOUND_CONTRACT_SHA256,d.RESET_CANARY_SHA256,'READY_NO_SCIENCE']:
            # READY_NO_SCIENCE is expected in output check by caller, not command literal from launcher output.
            if needle!='READY_NO_SCIENCE':self.assertIn(needle,cmd)
        for rel in d.DECLARED_OUTPUTS:self.assertIn(rel,cmd)

    def make_bundle(self, td, extra=None, symlink=False):
        root=Path(td); src=root/'src'; src.mkdir()
        files={
            d.PACKET_DIR+'/manifest.json':b'packet-manifest\n',
            d.PACKET_DIR+'/packet_000.json':b'packet0\n',
            d.RESULT_JSON:b'result\n',
            d.EXECUTION_ATTESTATION:b'attest\n',
        }
        if extra: files.update(extra)
        rows=[]
        for rel,data in files.items():
            p=src/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            rows.append({'path':rel,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)})
        man={'kind':'PLANCARRY_REPLAYRESIDUAL_V22_REMOTE_ARTIFACT_MANIFEST_V1','experiment_id':d.EXPERIMENT_ID,'repo_commit':d.REMOTE_COMMIT,'declared_roots':list(d.DECLARED_OUTPUTS),'files':rows}
        mp=root/'manifest.json';mp.write_text(json.dumps(man,sort_keys=True,separators=(',',':'))+'\n')
        tp=root/'bundle.tgz'
        with tarfile.open(tp,'w:gz') as tf:
            for rel in files:tf.add(src/rel,arcname=rel,recursive=False)
            if symlink:
                ti=tarfile.TarInfo(d.PACKET_DIR+'/badlink');ti.type=tarfile.SYMTYPE;ti.linkname='../../etc/passwd';tf.addfile(ti)
        return tp,mp,files

    def test_bundle_verification_and_durable_copy(self):
        with tempfile.TemporaryDirectory() as td:
            tp,mp,files=self.make_bundle(td);art=Path(td)/'job/artifacts';art.mkdir(parents=True)
            out=d.verify_and_extract_bundle(tp,mp,art);self.assertTrue(out.is_file())
            for rel,data in files.items():self.assertEqual((art/'replayresidual_v22_terminal_artifacts'/rel).read_bytes(),data)
            # Source can disappear after durable copy.
            tp.unlink();mp.unlink()
            self.assertTrue((art/'replayresidual_v22_terminal_artifacts'/d.RESULT_JSON).is_file())

    def test_success_bundle_requires_all_three_declared_roots(self):
        with tempfile.TemporaryDirectory() as td:
            tp,mp,_=self.make_bundle(td)
            x=json.loads(mp.read_text())
            x['files']=[r for r in x['files'] if r['path']!=d.RESULT_JSON]
            mp.write_text(json.dumps(x))
            art=Path(td)/'a';art.mkdir()
            with self.assertRaisesRegex(ValueError,'REQUIRED_ROOT_MISSING'):
                d.verify_and_extract_bundle(tp,mp,art,require_success_outputs=True)

    def test_failure_bundle_may_preserve_attestation_only(self):
        with tempfile.TemporaryDirectory() as td:
            tp,mp,_=self.make_bundle(td)
            x=json.loads(mp.read_text())
            x['files']=[r for r in x['files'] if r['path']==d.EXECUTION_ATTESTATION]
            mp.write_text(json.dumps(x))
            # Build matching one-file tar.
            src=Path(td)/'src'; only=Path(td)/'only.tgz'
            with tarfile.open(only,'w:gz') as tf: tf.add(src/d.EXECUTION_ATTESTATION,arcname=d.EXECUTION_ATTESTATION,recursive=False)
            art=Path(td)/'a';art.mkdir()
            out=d.verify_and_extract_bundle(only,mp,art,require_success_outputs=False)
            self.assertTrue(out.is_file())

    def test_bundle_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tp,mp,_=self.make_bundle(td,symlink=True);art=Path(td)/'a';art.mkdir()
            with self.assertRaisesRegex(ValueError,'UNSAFE'):d.verify_and_extract_bundle(tp,mp,art)

    def test_manifest_undeclared_future_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            extra={'results/science/valid_unseen/leak.json':b'no'}
            tp,mp,_=self.make_bundle(td,extra=extra);art=Path(td)/'a';art.mkdir()
            with self.assertRaises(ValueError):d.verify_and_extract_bundle(tp,mp,art)

    def test_manifest_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tp,mp,_=self.make_bundle(td);x=json.loads(mp.read_text());x['files'][0]['sha256']='0'*64;mp.write_text(json.dumps(x))
            art=Path(td)/'a';art.mkdir()
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):d.verify_and_extract_bundle(tp,mp,art)

    def test_remote_bundle_exact_allowlist(self):
        cmd=d.remote_bundle_command(True)
        for rel in d.DECLARED_OUTPUTS:self.assertIn(rel,cmd)
        self.assertNotIn('valid_seen',cmd);self.assertNotIn('valid_unseen',cmd)
        self.assertIn('REMOTE_ARTIFACT_SYMLINK_FORBIDDEN',cmd)
        self.assertIn('REQUIRED_REMOTE_ARTIFACT_MISSING',cmd)


if __name__=='__main__':unittest.main()
