from __future__ import annotations
import copy, hashlib, json, tempfile, unittest, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

import action_matched_grounded_v2_phase_runner_v1 as ph
import action_matched_grounded_v2_runtime_v1 as rt
import action_matched_grounded_v2_science_driver_v1 as drv


def a4(active=.20, nuisance=.01, sequence=None):
    sequence=nuisance if sequence is None else sequence
    out={'NO_PATCH':0.0,'ACTIVE':{'+':active,'-':-active},'RANDOM_EQ_NORM':{'+':nuisance,'-':-nuisance},'_validity':{'active_nondegenerate':True}}
    for arm in ph.SEMANTIC:
        x=sequence if arm=='FUTURE_ACTION_SEQUENCE_ONLY' else nuisance
        out[arm]={'+':x,'-':-x}; out['_validity'][arm]=True
    return out


def a5(active=.20,nuisance=.01,sequence=None):
    sequence=nuisance if sequence is None else sequence
    out={'NO_PATCH':{'A':0.0,'B':0.0},'_validity':{'active_nondegenerate':True}}
    out['ACTIVE']={'+':{'A':active,'B':active},'-':{'A':-active,'B':active}}
    for arm in ph.SEMANTIC:
        x=sequence if arm=='FUTURE_ACTION_SEQUENCE_ONLY' else nuisance
        out[arm]={'+':{'A':x,'B':x},'-':{'A':-x,'B':-x}}; out['_validity'][arm]=True
    out['RANDOM_EQ_NORM']={'+':{'A':nuisance,'B':nuisance},'-':{'A':-nuisance,'B':-nuisance}}
    return out


def row(i,active=.20,nuisance=.01,a5active=.20,a5nuis=.01,sequence=None,a5sequence=None):
    return {'index':i,'a4_margins':a4(active,nuisance,sequence),'a5_margins':a5(a5active,a5nuis,a5sequence)}


def dev_payload(grids,inds=None):
    inds=list(range(20)) if inds is None else inds
    return {'phase':'ACTION_MATCHED_GROUNDED_V2_DEVELOPMENT','eligible_indices':inds,'grid_results':grids,
            'confirmation_accessed':False,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,
            **ph.binding_payload()}


class GroundedV2ExecutableTests(unittest.TestCase):
    def test_strong_a4_requires_beating_future_sequence_control(self):
        c=ph.a4_components(a4(active=.20,nuisance=.01,sequence=.18))
        self.assertAlmostEqual(c['joint_future_state_margin'],.19)
        self.assertAlmostEqual(c['joint_semantic_plan_margin'],.02)
        self.assertAlmostEqual(c['future_action_sequence_only_shift'],.18)

    def test_strong_a5_requires_beating_future_sequence_control(self):
        c=ph.a5_components(a5(active=.20,nuisance=.01,sequence=.18))
        self.assertAlmostEqual(c['joint_future_state_continuation5'],.19)
        self.assertAlmostEqual(c['joint_semantic_plan_continuation5'],.02)
        self.assertAlmostEqual(c['future_action_sequence_only5'],.18)

    def test_degenerate_required_control_retains_denominator_and_forces_nonpass(self):
        x=a4(.20,.01); x['_validity']['FUTURE_ACTION_SEQUENCE_ONLY']=False
        c=ph.a4_components(x)
        self.assertFalse(c['specificity_valid']); self.assertLessEqual(c['joint_semantic_plan_margin'],0.0)
        y=a5(.20,.01); y['_validity']['UNRELATED_PAIR_RESIDUAL']=False
        d=ph.a5_components(y)
        self.assertFalse(d['specificity_valid5']); self.assertLessEqual(d['joint_semantic_plan_continuation5'],0.0)
        rows=[{'index':i,'a4_margins':copy.deepcopy(x),'a5_margins':copy.deepcopy(y)} for i in range(20)]
        agg=ph.aggregate_point(rows)
        self.assertEqual(agg['n'],20); self.assertEqual(agg['invalid_specificity_A4'],20); self.assertEqual(agg['invalid_specificity_A5'],20)

    def test_a4_only_selection_then_same_point_a5_no_reselection(self):
        grids={ph.grid_key(L,A):[row(i,.10,.01,.10,.01) for i in range(20)] for L in ph.LAYERS for A in ph.ALPHAS}
        grids[ph.grid_key(14,.5)]=[row(i,.30,.01,.01,.01) for i in range(20)]
        grids[ph.grid_key(21,.5)]=[row(i,.20,.01,.20,.01) for i in range(20)]
        term=ph.select_development(dev_payload(grids))
        self.assertEqual((term['selected_layer'],term['selected_alpha']),(14,.5))
        self.assertEqual(term['status'],'DEVELOPMENT_FUTILITY_STOP')
        self.assertTrue(term['a4_gate_pass']); self.assertFalse(term['a5_gate_pass'])

    def test_confirmation_holm_both_coprimary_and_tamper_fail(self):
        grids={ph.grid_key(L,A):[row(i) for i in range(20)] for L in ph.LAYERS for A in ph.ALPHAS}
        with tempfile.TemporaryDirectory() as td:
            sp=Path(td)/'seal.json'; ph.select_development(dev_payload(grids),sp)
            seal=json.loads(sp.read_text()); ss=ph.canonical_sha(seal)
            cp={'phase':'ACTION_MATCHED_GROUNDED_V2_CONFIRMATION','families':[dict(row(64+i),eligible=True) for i in range(20)],
                'selected_layer':seal['selected_layer'],'selected_alpha':seal['selected_alpha'],'development_seal_sha256':ss,
                'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**ph.binding_payload()}
            res=ph.evaluate_confirmation(cp,seal,ss)
            self.assertTrue(res['strong_semantic_plan_support']); self.assertTrue(res['holm']['all_reject'])
            bad=copy.deepcopy(seal); bad['selected_alpha']=999
            with self.assertRaises(ph.ContractError): ph.evaluate_confirmation(cp,bad,ph.canonical_sha(bad))


    def test_secondary_future_sequence_scope_is_descriptive_and_cannot_rescue(self):
        grids={ph.grid_key(L,A):[row(i) for i in range(20)] for L in ph.LAYERS for A in ph.ALPHAS}
        with tempfile.TemporaryDirectory() as td:
            sp=Path(td)/'seal.json'; ph.select_development(dev_payload(grids),sp); seal=json.loads(sp.read_text()); ss=ph.canonical_sha(seal)
            # Future-state margin=.19 passes descriptive guards; adding the
            # .18 sequence nuisance leaves strong semantic margin=.02.
            fam=[dict(row(64+i,active=.20,nuisance=.01,a5active=.20,a5nuis=.01,sequence=.18,a5sequence=.18),eligible=True) for i in range(20)]
            cp={'phase':'ACTION_MATCHED_GROUNDED_V2_CONFIRMATION','families':fam,'selected_layer':seal['selected_layer'],'selected_alpha':seal['selected_alpha'],'development_seal_sha256':ss,'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**ph.binding_payload()}
            res=ph.evaluate_confirmation(cp,seal,ss)
            self.assertFalse(res['strong_semantic_plan_support'])
            self.assertEqual(res['status'],'NARROWED_FUTURE_ACTION_SEQUENCE_CARRIER_DESCRIPTIVE_ONLY')
            sec=res['secondary_future_action_sequence_scope']
            self.assertTrue(sec['descriptive_only']); self.assertTrue(sec['narrowed_future_action_sequence_carrier'])
            self.assertTrue(sec['effect_guards_pass']['A4']); self.assertTrue(sec['effect_guards_pass']['A5'])
            self.assertTrue(sec['cannot_rescue_or_relabel_strong_semantic_support'])

    def test_confirmation_shortfall_is_inconclusive_not_denominator_shrink(self):
        grids={ph.grid_key(L,A):[row(i) for i in range(20)] for L in ph.LAYERS for A in ph.ALPHAS}
        with tempfile.TemporaryDirectory() as td:
            sp=Path(td)/'seal.json'; ph.select_development(dev_payload(grids),sp); seal=json.loads(sp.read_text()); ss=ph.canonical_sha(seal)
            cp={'phase':'ACTION_MATCHED_GROUNDED_V2_CONFIRMATION','families':[dict(row(64+i),eligible=True) for i in range(19)],
                'selected_layer':seal['selected_layer'],'selected_alpha':seal['selected_alpha'],'development_seal_sha256':ss,
                'reserve_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False,**ph.binding_payload()}
            res=ph.evaluate_confirmation(cp,seal,ss)
            self.assertEqual(res['status'],'INCONCLUSIVE_CONFIRMATION_CONSTRUCTIBILITY'); self.assertEqual(res['eligible_count'],19)

    def test_source_geometry_and_neutralized_controls(self):
        prefix=[101,102]
        actions={'A3':[3,4],'A4':[11,12],'B4':[21,22,23],'A5':[31,32],'B5':[41,42]}
        pa={'input_ids':[51,52,53,54],'deranged_input_ids':[51,53,52,54]}
        pb={'input_ids':[61,62,63],'deranged_input_ids':[62,61,63]}
        active=rt.source_condition_ids(prefix,actions,pa,pb,'ACTIVE')
        seq=rt.source_condition_ids(prefix,actions,pa,pb,'FUTURE_ACTION_SEQUENCE_ONLY')
        nxt=rt.source_condition_ids(prefix,actions,pa,pb,'NEXT_DIVERGENT_ACTION_ONLY')
        der=rt.source_condition_ids(prefix,actions,pa,pb,'FUTURE_TOKEN_DERANGED')
        self.assertEqual(len(active['A_ids']),len(active['B_ids']))
        self.assertEqual(active['source_end_position'],seq['source_end_position']); self.assertEqual(seq['source_end_position'],nxt['source_end_position'])
        self.assertEqual(seq['A_slots']['PLAN'],seq['B_slots']['PLAN']); self.assertEqual(nxt['A_slots']['PLAN'],nxt['B_slots']['PLAN'])
        self.assertEqual(nxt['A_slots']['A5'],nxt['B_slots']['A5'])
        self.assertNotEqual(active['A_slots']['A5'],active['B_slots']['A5'])
        self.assertEqual(der['A_slots']['A3'],active['A_slots']['A3']); self.assertEqual(der['A_slots']['A4'],active['A_slots']['A4']); self.assertEqual(der['A_slots']['A5'],active['A_slots']['A5'])

    def test_plan_parser_requires_exact_frozen_actions(self):
        good='<PLAN>\n<ACTION_3>take soap</ACTION_3>\n<ACTION_4>go north</ACTION_4>\n<ACTION_5>put soap in sink</ACTION_5>\n<RATIONALE>These actions continue the visible task.</RATIONALE>\n</PLAN>'
        p=rt.parse_plan_block(good,('take soap','go north','put soap in sink'))
        self.assertEqual(p['A4'],'go north')
        with self.assertRaises(rt.RuntimeContractError): rt.parse_plan_block(good,('take soap','go south','put soap in sink'))

    def test_exact_tokenizer_canary_wrappers_and_rationale_derangement(self):
        from transformers import AutoTokenizer
        tok=AutoTokenizer.from_pretrained(rt.MODEL_ID,revision=rt.REVISION,local_files_only=True,use_fast=True)
        prov=rt.verify_tokenizer(tok); self.assertEqual(prov['class'],'Qwen2TokenizerFast')
        text='<PLAN>\n<ACTION_3>take soap</ACTION_3>\n<ACTION_4>go north</ACTION_4>\n<ACTION_5>put soap in sink</ACTION_5>\n<RATIONALE>Continue carefully toward the visible target now.</RATIONALE>\n</PLAN>'
        parsed=rt.parse_plan_block(text,('take soap','go north','put soap in sink')); t=rt.tokenize_plan_block(tok,parsed)
        self.assertEqual(len(t['input_ids']),len(t['deranged_input_ids'])); self.assertEqual(sorted(t['input_ids']),sorted(t['deranged_input_ids']))
        mutable=set(t['mutable_rationale_positions'])
        for i,(x,y) in enumerate(zip(t['input_ids'],t['deranged_input_ids'])):
            if i not in mutable: self.assertEqual(x,y)
        self.assertNotEqual([t['input_ids'][i] for i in t['mutable_rationale_positions']], [t['deranged_input_ids'][i] for i in t['mutable_rationale_positions']])

    def test_match_control_norm_degenerate_is_validity_false_not_exception(self):
        import torch
        z=torch.zeros(8); v,ok,n=rt.match_control_norm(z,1.0); self.assertFalse(ok); self.assertEqual(n,0.0); self.assertEqual(float(v.abs().sum()),0.0)
        v,ok,n=rt.match_control_norm(torch.ones(8),0.0); self.assertFalse(ok); self.assertEqual(float(v.abs().sum()),0.0)

    def test_population_loader_binds_paths_schema_and_locked_dev_range(self):
        rows=drv._load_population('development')
        self.assertEqual([x['frozen_index'] for x in rows],list(range(64))); self.assertEqual(len(rows),64)
        self.assertTrue(all('/trial_' in x['game_path'] and not x['game_path'].endswith('game.tw-pddl') for x in rows))
        self.assertEqual(ph.sha_file(rt.POP_REL),ph.POPULATION_SHA256)

    def test_preflight_ready_no_science_and_future_sealed(self):
        x=drv.preflight()
        self.assertEqual(x['status'],'READY_NO_SCIENCE')
        self.assertEqual(x['model_calls'],0); self.assertEqual(x['model_loads'],0); self.assertEqual(x['environment_execution'],0)
        self.assertFalse(x['confirmation_accessed']); self.assertFalse(x['reserve_accessed']); self.assertFalse(x['valid_seen_accessed']); self.assertFalse(x['valid_unseen_accessed'])
        self.assertEqual(x['development_pool_indices'],list(range(64)))

    def test_constructibility_terminal_preserves_reason_diagnostics(self):
        payload=dev_payload({},inds=list(range(3)))
        payload['attempted_count']=6
        payload['ineligibility_reason_counts']={'RuntimeContractError:PLAN_FULLMATCH_REQUIRED':2,'ConstructibilityError:A5_EQUALS_B5':1}
        res=ph.select_development(payload)
        self.assertEqual(res['status'],'INCONCLUSIVE_GROUNDED_PAIR_CONSTRUCTIBILITY')
        self.assertEqual(res['attempted_count'],6)
        self.assertEqual(res['ineligibility_reason_counts'],{'ConstructibilityError:A5_EQUALS_B5':1,'RuntimeContractError:PLAN_FULLMATCH_REQUIRED':2})
        bad=copy.deepcopy(payload); bad['attempted_count']=7
        with self.assertRaises(ph.ContractError): ph.select_development(bad)
        bad=copy.deepcopy(payload); bad.pop('ineligibility_reason_counts')
        with self.assertRaises(ph.ContractError): ph.select_development(bad)

    def test_confirmation_seal_and_refusal_precede_model_load_in_source(self):
        src=Path('action_matched_grounded_v2_science_driver_v1.py').read_text()
        block=src[src.index("if args.phase=='development'"):src.index("print(json.dumps({'ACTION_MATCHED_GROUNDED_V2_TERMINAL'")]
        self.assertLess(block.index('_load_seal'),block.index('load_model'))
        self.assertLess(block.index('_refuse([CONF_PACKET_DIR,CONF_PAYLOAD,CONF_RESULT])'),block.index('load_model'))
        self.assertLess(block.index('am.verify_frozen_design(ROOT)'),block.index('load_model'))

    def test_clone_state_mismatch_is_technical_not_family_ineligibility(self):
        src=Path('action_matched_grounded_v2_science_driver_v1.py').read_text()
        replay=src[src.index('def _replay_to_post_a3'):src.index('def _construct_branch')]
        self.assertIn('POST_A3_CLONE_STATE_MISMATCH',replay)
        produce=src[src.index('def produce_grounded_attempt'):src.index('def _scan_first20')]
        self.assertNotIn('POST_A3_CLONE_STATE_MISMATCH',produce[produce.index('except gc.ConstructibilityError'):])

    def test_launcher_requires_future_exact_binding_for_science(self):
        src=Path('action_matched_grounded_v2_primary_v1.sh').read_text()
        for key in ('ACTION_MATCHED_GROUNDED_V2_EXPECTED_GIT_COMMIT','ACTION_MATCHED_GROUNDED_V2_DRIVER_SHA256','ACTION_MATCHED_GROUNDED_V2_RUNTIME_SHA256','ACTION_MATCHED_GROUNDED_V2_PHASE_SHA256','ACTION_MATCHED_GROUNDED_V2_VALIDATOR_SHA256','ACTION_MATCHED_GROUNDED_V2_SHELL_SHA256'):
            self.assertIn(key,src)
        self.assertIn('RESEARCH_DECISION_BOUND',src)

    def test_no_old_consumed_population_binding_in_new_stack(self):
        joined='\n'.join(Path(p).read_text() for p in ['action_matched_grounded_v2_runtime_v1.py','action_matched_grounded_v2_phase_runner_v1.py','action_matched_grounded_v2_science_driver_v1.py'])
        self.assertNotIn('b4225a3818b1fa757a492670317481081b173192f9129b61cf8370ad52d32bc7',joined)
        self.assertNotIn('plancarry_action_matched_future_plan_population_v1_20260825.json',joined)


if __name__=='__main__': unittest.main()
