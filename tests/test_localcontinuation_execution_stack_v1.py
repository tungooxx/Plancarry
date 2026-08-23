from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from unittest import mock
import localcontinuation_packet_builder_v1 as pb
import localcontinuation_phase_runner_v1 as p
import localcontinuation_science_driver_v1 as drv

B={'final_prereg_sha256':p.FINAL_PREREG_SHA256,'final_review_sha256':p.FINAL_REVIEW_SHA256,'population_manifest_sha256':p.POPULATION_SHA256,'population_review_sha256':p.POPULATION_REVIEW_SHA256}
H0='0'*64; H1='1'*64; H2='2'*64; H3='3'*64; H4='4'*64; H5='5'*64; H6='6'*64
EP={'schema':'synthetic-localcontinuation-test','driver_sha256':H1,'phase_runner_sha256':H2,'packet_builder_sha256':H3,'validator_sha256':H4,'session_runtime_sha256':H5,'vector_schema':'frozen','control_schema':'frozen','session_schema':'frozen','model_provenance':{'model_id':'synthetic'}}
EPS=p.sha_json(EP)

def arm(name,layer=7,alpha=.25,lca=0.0,msa=0.0,margin=.2,reset=H3):
    hook=0 if name in (p.NO_PATCH,'VISIBLE_TEXT_PLAN') else 1
    x={'arm_name':name,'selected_layer':layer,'selected_alpha':alpha,'active_residual_sha256':H1,'injected_vector_sha256':None if hook==0 else H2,'reset_snapshot_sha256':reset,'reset_prefix_sha256':H4,'hook_count':hook,'session_id_hash':H5,'lca2':lca,'valid_action_rate':1.0,'task_success':0.0,'msa2':msa,'reference_action_margin_family':margin}
    if name=='VISIBLE_TEXT_PLAN':
        x['reset_snapshot_sha256']=H6;x['external_reset_snapshot_sha256']=H3;x['visible_plan_slot_token_ids_sha256']=H0
    return x

def seal():
    return {'kind':'PLANCARRY_LOCALCONTINUATION_DEVELOPMENT_SELECTION_V1','status':'FROZEN_LOCALCONTINUATION_DEVELOPMENT_SELECTION',**B,'development_indices':list(p.DEV),'qualified_indices':list(range(16)),'qualified_count':16,'development_payload_sha256':H0,'execution_provenance':EP,'execution_provenance_sha256':EPS,'selected_point_family_provenance_sha256':H6,'selected_layer':7,'selected_alpha':.25,'selected_grid_key':'7:0.25','confirmation_accessed':False,'scientific_result':'NOT_ASSESSED_DEVELOPMENT_SELECTION_ONLY'}

class T(unittest.TestCase):
    def test_stage1_no_success_gate(self):
        acts=[{'command':f'take x{i} from y','admissible_commands':[f'take x{i} from y'],'error':None,'accepted':True,'was_admissible':True} for i in range(5)]
        ok,r=pb.local_stage1_eligibility(True,acts);self.assertTrue(ok);self.assertEqual(r,[])
        acts[2]['command']='look';self.assertFalse(pb.local_stage1_eligibility(True,acts)[0])

    def test_stage1_admissibility_error(self):
        acts=[{'command':f'take x{i} from y','admissible_commands':[f'take x{i} from y'],'error':None,'accepted':True,'was_admissible':True} for i in range(5)]
        acts[1]['was_admissible']=False;self.assertFalse(pb.local_stage1_eligibility(True,acts)[0])
        acts[1]['was_admissible']=True;acts[3]['error']='bad';acts[3]['accepted']=False;self.assertFalse(pb.local_stage1_eligibility(True,acts)[0])

    def test_stage2_partial_phase_refused(self):
        with self.assertRaisesRegex(Exception,'STAGE2_REQUIRES_COMPLETE_PHASE_E'):pb.apply_stage2_phase(None,[],'development','.')

    def test_population_manifest_identity(self):
        rows=pb.load_population_phase('development','.')
        self.assertEqual([int(x['frozen_index']) for x in rows],list(range(32)))
        self.assertEqual(len({x['game_path'] for x in rows}),32)
        self.assertTrue(all(pb.family_from_game_path(x['game_path'])==x['family'] for x in rows))

    def test_margin_tie_and_singleton(self):
        self.assertAlmostEqual(p.reference_action_margin({'b':-1,'a':-1,'r':-.5},'r'),.5);self.assertEqual(p.top1_command({'b':1,'a':1}),'a')
        with self.assertRaisesRegex(Exception,'TECHNICAL_INVALID_MARGIN_UNDEFINED'):p.reference_action_margin({'r':0},'r')

    def test_msa2_matched_state_fail_closed(self):
        rows=[{'state_match':True,'admissible_match':True,'reference_action':'r','scores':{'r':1,'x':0}},{'state_match':True,'admissible_match':True,'reference_action':'r','scores':{'r':0,'x':1}}]
        self.assertEqual(p.matched_state_msa2(rows),(.5,0.0))
        rows[1]['state_match']=False
        with self.assertRaisesRegex(Exception,'matched-state guard fail'):p.matched_state_msa2(rows)

    def test_lca2_excludes_first_and_requires_state(self):
        ref=[{'command':f'r{i}','pre_state_hash':f's{i}'} for i in range(5)]
        gen=[{'command':'WRONG','pre_state_hash':'bad'},{'command':'r3','pre_state_hash':'s3'},{'command':'r4','pre_state_hash':'s4'}]
        self.assertEqual(p.local_continuation_lca2(ref,gen),1.0);gen[2]['pre_state_hash']='x';self.assertEqual(p.local_continuation_lca2(ref,gen),.5)

    def _dev(self):
        fam=[{'index':i,'qualified':i<16} for i in p.DEV];grids={}
        for l in p.LAYERS:
            for a in p.ALPHAS:
                rows={}
                for i in range(16):
                    aa=arm(p.ACTIVE,l,a,msa=1.0); nn=arm(p.NO_PATCH,l,a,msa=0.0)
                    arms={p.ACTIVE:aa,p.NO_PATCH:nn};arms.update({c:arm(c,l,a,msa=0.0) for c in p.SPEC})
                    rows[str(i)]={'arms':arms,'active_raw_residual_l2':1.0,'active_residual_sha256':H1,'reset_snapshot_sha256':H3}
                grids[p.grid_key(l,a)]=rows
        return {'phase':'LOCALCONTINUATION_DEVELOPMENT','families':fam,'grid_results':grids,'confirmation_accessed':False,'reserve_accessed':False,'execution_provenance':EP,'execution_provenance_sha256':EPS,**B}

    def test_selector_external_seal_hash_and_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'seal.json';out=p.select_development(self._dev(),path)
            self.assertEqual((out['selected_layer'],out['selected_alpha']),(7,.25));self.assertNotIn('seal_file_sha256',json.loads(path.read_text()))
            frozen,sha=p.load_seal(path,out['seal_file_sha256']);self.assertEqual(sha,out['seal_file_sha256']);self.assertEqual(frozen['execution_provenance_sha256'],EPS)

    def test_development_zero_active_cannot_improve_joint_margin(self):
        d=self._dev();row=d['grid_results']['7:0.25']['0'];row['active_raw_residual_l2']=0.0
        out=p.select_development(d)
        self.assertGreaterEqual(out['all_grid_aggregates']['7:0.25']['zero_raw_residual_count'],1)

    def _conf(self,indices,name):
        fs=[]
        for i in indices:
            arms={a:arm(a,lca=0.0) for a in p.ALL_ARMS};arms[p.ACTIVE]=arm(p.ACTIVE,lca=1.0)
            ms={a:arm(a,msa=(1.0 if a==p.ACTIVE else 0.0)) for a in (p.ACTIVE,p.NO_PATCH,*p.SPEC)}
            fs.append({'index':i,'qualified':True,'active_raw_residual_l2':1.0,'active_residual_sha256':H1,'reset_snapshot_sha256':H3,'arms':arms,'matched_state_secondary':ms,'zero_add_no_patch_maxabs':0.0,'self_replace_no_patch_maxabs':0.0})
        return {'phase':name,'families':fs,'selected_layer':7,'selected_alpha':.25,'development_seal_sha256':H6,'execution_provenance':EP,'execution_provenance_sha256':EPS,'reserve_accessed':False if name=='LOCALCONTINUATION_CONFIRMATION' else True,'valid_seen_accessed':False,'valid_unseen_accessed':False,**B}

    def test_confirmation_and_replication_labels(self):
        c=self._conf(p.CONF,'LOCALCONTINUATION_CONFIRMATION');out=p.evaluate_confirmation(c,seal(),H6);self.assertEqual(out['status'],'SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1');self.assertIn('matched_state_MSA2_secondary_qualified',out)
        r=self._conf(p.RESERVE,'LOCALCONTINUATION_REPLICATION');self.assertEqual(p.evaluate_replication(r,seal(),H6,'SUPPORTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1')['status'],'REPLICATED_REPLAYRESIDUAL_LOCALCONTINUATION_T1')
        with self.assertRaises(Exception):p.evaluate_replication(r,seal(),H6,'REFUTED_REPLAYRESIDUAL_LOCALCONTINUATION_T1')

    def test_zero_active_cannot_positive(self):
        c=self._conf(p.CONF,'LOCALCONTINUATION_CONFIRMATION');c['families'][0]['active_raw_residual_l2']=0.0
        out=p.evaluate_confirmation(c,seal(),H6);self.assertEqual(out['positive_counts']['d_no_patch'],19);self.assertEqual(out['zero_raw_residual_count'],1)

    def test_execution_provenance_mismatch_fails(self):
        c=self._conf(p.CONF,'LOCALCONTINUATION_CONFIRMATION');c['execution_provenance']=dict(EP,driver_sha256=H0);c['execution_provenance_sha256']=p.sha_json(c['execution_provenance'])
        with self.assertRaisesRegex(Exception,'execution provenance differs'):p.evaluate_confirmation(c,seal(),H6)

    def test_visible_plan_requires_external_reset_binding(self):
        c=self._conf(p.CONF,'LOCALCONTINUATION_CONFIRMATION');del c['families'][0]['arms']['VISIBLE_TEXT_PLAN']['external_reset_snapshot_sha256']
        with self.assertRaisesRegex(Exception,'visible-plan external reset'):p.evaluate_confirmation(c,seal(),H6)

    def test_seal_checked_before_model_load(self):
        with mock.patch.object(drv,'load_runtime',side_effect=AssertionError('MODEL_LOAD_CALLED')):
            with self.assertRaisesRegex(Exception,'development seal missing|development seal hash mismatch'):
                drv.main(['--phase','confirmation','--development-seal-sha256',H0])

    def test_sign_geometry(self):
        self.assertAlmostEqual(p.exact_one_sided_sign_p(15,20),0.020694732666015625);self.assertAlmostEqual(p.exact_one_sided_sign_p(10,12),0.019287109375)

if __name__=='__main__':unittest.main()
