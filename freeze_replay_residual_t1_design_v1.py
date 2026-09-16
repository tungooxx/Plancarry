#!/usr/bin/env python3
import json,hashlib
from pathlib import Path
MAN=Path('results/design/plancarry_replay_residual_delayed48_manifest_v1.json')
DES=Path('results/design/plancarry_replay_residual_t1_prereg_v1.json')
DON=Path('results/design/plancarry_replay_residual_unrelated_donor_map_v1.json')
AUD=Path('results/design/plancarry_replay_residual_t1_static_audit_v1.json')
def sha_bytes(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def dump(p,obj):
 raw=(json.dumps(obj,indent=2,sort_keys=True)+'\n').encode();p.write_bytes(raw);return hashlib.sha256(raw).hexdigest()
def main():
 if not MAN.exists(): raise SystemExit('MANIFEST_NOT_READY')
 m=json.load(open(MAN)); msh=sha_bytes(MAN)
 if m.get('selected_pair_count')!=48 or m.get('development_n')!=24 or m.get('confirmation_n')!=24: raise RuntimeError('MANIFEST_N')
 if not m.get('all_delayed_divergence') or m.get('min_common_prefix_actions',0)<1: raise RuntimeError('DELAYED_GUARD')
 if m.get('model_calls')!=0 or not m.get('environment_only'): raise RuntimeError('MANIFEST_NOT_ENV_ONLY')
 rows=m['selected_pairs']; dev=rows[:24]
 # deterministic unrelated-plan donor pool is development only; prefer distinct object+receptacle types.
 donor={}
 for r in rows:
  c=[d for d in dev if d['family']!=r['family'] and d['target_object_type']!=r['target_object_type'] and d['target_receptacle_type']!=r['target_receptacle_type']]
  if not c:c=[d for d in dev if d['family']!=r['family']]
  if not c:raise RuntimeError('NO_DONOR')
  c.sort(key=lambda d:sha('plancarry-replay-residual-unrelated-v1|'+r['family']+'|'+d['family']))
  donor[r['family']]=c[0]['family']
 dobj={'kind':'PLANCARRY_REPLAY_RESIDUAL_UNRELATED_DONOR_MAP_V1','scientific_result':'NOT_ASSESSED','model_calls':0,'manifest_sha256':msh,
       'donor_pool':'development indices0..23 only','rule':'hash-min among development families with different target object and receptacle types; fallback any nonself development family; no outcome dependence',
       'confirmation_donors_from_confirmation':False,'mapping':donor}
 dsh=dump(DON,dobj)
 plan_request=(
  'PLAN REQUEST\n'
  'Before acting, choose an order for the two unfinished target objects.\n'
  'CANDIDATE 1: {candidate_1}\nCANDIDATE 2: {candidate_2}\nTARGET RECEPTACLE: {target_receptacle}\n'
  'Output exactly three lines and nothing else:\n'
  'STEP 1: finish <one exact candidate object name> into <exact target receptacle>\n'
  'STEP 2: finish <the other exact candidate object name> into <exact target receptacle>\n'
  'END PLAN\nDo not output reasoning, tool calls, or ACTION.\nPLAN:\n')
 design={
  'kind':'PLANCARRY_REPLAY_RESIDUAL_T1_PREREG_V1','status':'FROZEN_PRE_EXECUTION','scientific_result':'NOT_ASSESSED','model_calls':0,
  'title':'PlanCarry-ReplayResidual: causal active-plan checkpoint from matched replay residual',
  'hypothesis_id':'97c6bd41-b4b9-4722-ac20-6b41e8bd8907','parent_hypothesis_id':'2c4031ca-7269-43af-98dd-225c29e030a9',
  'research_question':'Can the hidden-state residual induced by an agent self-generated explicit plan, measured after identical plan-independent action/observation replay, act as a content-specific one-shot checkpoint that causally swaps resumed plan order and remains behaviorally active beyond the first action after a fresh-context reset?',
  'novelty_boundary':{
    'not_claimed':['replay pairing as a diagnostic','linear plan probes','ordinary activation patching','activation-difference steering / Contrastive Activation Addition','generic latent memory','full KV checkpointing','prompt summaries','mere plan decodability'],
    'claimed_only_if_supported':'paired replay residual is causally sufficient for active plan-order control across interruption, survives a single injection beyond the first action, and later admits compact/minimal checkpointing',
    'closest_prior_boundaries':['Plans Don\'t Persist: replay pairing is diagnostic and calls for length/content controls; probe-gated resurfacing did not recover ALFWorld','Where\'s the Plan?: decodable future-plan information need not be causally used; activation patching establishes causal planning sites in a different task','Instruction/behavior activation-difference steering already computes with-vs-without contrast vectors; subtraction and alpha=1 steering are not novelty here']},
  'model':{'model_id':'Qwen/Qwen3-1.7B','revision':'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e','dtype':'bfloat16','quantization':'NONE','offload':'NONE','device':'NVIDIA GeForce RTX 3050 Laptop GPU','transformers':'4.51.3','tokenizers':'0.21.1','torch':'2.13.0+cu130','num_hidden_layers':28,'hidden_size':2048},
  'data':{'manifest_path':str(MAN),'manifest_sha256':msh,'source_split':'train','task_type':'pick_two_obj_and_place','development_indices':[0,23],'confirmation_indices':[24,47],
          'development_n':24,'confirmation_n':24,'all_delayed_divergence_required':True,'common_plan_independent_prefix_min_actions':1,'confirmation_sealed_until_selection_sha':True,
          'prior_selected_two_object_families_excluded':True,'valid_seen_consumed':False,'valid_unseen_consumed':False,'no_family_replacement':True},
  'candidate_orientation':{'rule':'SHA256(manifest_sha256|frozen_pair_index|replay_residual_candidate_orientation_v1) parity determines whether object_a or object_b is displayed as CANDIDATE 1; no outcome dependence','purpose':'break candidate-position bias'},
  'plan_generation':{'when':'initial state before the common plan-independent prefix','prompt_template':plan_request,'decoding':{'do_sample':False,'temperature':0.0,'max_new_tokens':64,'stop_after_exact_text':'END PLAN'},
    'qualification':{'required_exact_markers':['STEP 1:','STEP 2:','END PLAN'],'forbidden_markers':['<think>','</think>','ACTION:','<STATE_END>'],'step1_rule':'contains exactly one candidate object name and exact target receptacle','step2_rule':'contains the other candidate object name and exact target receptacle','token_count_min':8,'token_count_max':64,'development_min_qualified':16,'confirmation_min_qualified':16,'unqualified_primary_effects':'set to zero/nonpositive; never replace family'},
    'plan_identity':'first object named in STEP 1; both object orders are environment-verified task-valid by manifest'},
  'strict_stripping':{'plan_span_only':True,'neutral_token_text':' .','neutral_token_id':659,'replacement':'repeat token 659 exactly once per generated plan token','roundtrip_audited_lengths':[1,2,3,5,10,20,64,128],
    'required_runtime_guards':['plan-present and stripped full replay token counts equal','all token IDs outside the plan span equal after alignment','final <STATE_END> token site aligns within each paired replay','no reasoning-trace markers in qualified plan']},
  'replay_pairing':{'source_plan_present':'same initial task/observation/admissible context + fixed plan request + exact generated plan + exact common-prefix ACTION/OBSERVATION transcript + checkpoint footer ending <STATE_END>',
    'source_plan_stripped':'identical serialization except generated plan token span is replaced by equal-count neutral token 659','trajectory_identity':'exact same ALFWorld common_prefix_actions and resulting observations in both conditions','checkpoint':'after >=1 plan-independent action/observation cycle and before first divergent object-order action'},
  'residual_definition':{'per_layer':'r_i,l = h_plan_present(i,l,<STATE_END>) - h_plan_stripped(i,l,<STATE_END>)','active_scale':1.0,'scale_search':False,'layers':[6,13,20,27],'zero_norm_eps':1e-8,'zero_norm_behavior':'family unqualified/zero-fail; no replacement'},
  'target_intervention':{'fresh_prompt':'TASK + checkpoint CURRENT OBSERVATION + checkpoint ADMISSIBLE COMMANDS + <STATE_END> + ACTION:; no plan/history visible','patch_site':'token index of final <STATE_END> from fresh reset_block capture, before ACTION tokens','mode':'add','scale':1.0,'single_injection_only':True,'hook_removed_after_prefix_forward':True,'gold_suffix_continues_through_returned_KV_cache':True,'repeated_patch_forbidden':True},
  'controls':{
    'NO_PATCH':'same fresh target prompt, no intervention','ZERO_ADD':'zero vector at exact patch site; technical/scientific null','SELF_PATCH':'replace target <STATE_END> hidden state by its own captured value; technical sentinel only',
    'SWAPPED_PLAN_RESIDUAL':'same generated plan lines swapped STEP1<->STEP2; same lexical content; residual vs equal-token neutral strip; rescale to active residual norm','RANDOM_SAME_NORM':'SHA256-Rademacher vector rescaled to active residual norm',
    'UNRELATED_PLAN_RESIDUAL':'canonical two-line valid plan from deterministic development-only donor map; residual vs its own equal-token neutral strip, rescaled to active norm','GENERIC_HISTORY_RESIDUAL':'deterministic token-length-matched slice of initial observation/history vs neutral strip, rescaled to active norm',
    'VISIBLE_TEXT_PLAN_REPLAY':'fresh-reset system baseline with exact generated plan visible and no latent patch; descriptive upper/system baseline, not a matched causal null'},
  'unrelated_donor_map':{'path':str(DON),'sha256':dsh,'confirmation_donor_pool':'development only'},
  'teacher_forced_mechanistic_readout':{
    'requires_bridge_extension':'return span-specific token logprobs while preserving prefix-stable one-shot patch semantics; no intervention after prefix forward',
    'intended_branch':'manifest branch whose first completed object equals generated STEP1 object','counter_branch':'other environment-verified order',
    'immediate_swap':'At t=0, margin(selected first command minus counter first command) under ACTIVE minus the same margin under SWAPPED_PLAN_RESIDUAL.',
    'later_persistence':'For t=1 and t=2, teacher-force the selected branch prior actions and exact resulting observations identically for every intervention arm, then score only intended action-t tokens. The only patch happened on the original fresh-reset prefix.',
    'family_effects':{'SWAP':'immediate active-vs-swapped margin difference','LATER_vs_control':'mean over t=1,2 of intended-action meanLP(ACTIVE)-meanLP(control)','PERSISTENT_CAUSAL_PLAN_SCORE_vs_control':'min(SWAP, LATER_vs_control)'},
    'later_steps_exclude_first_action':True},
  'development_selection':{'uses':'qualified development families only for selection; qualification is format/token validity, never action-likelihood source competence','qualification_gate':'at least16/24; otherwise INCONCLUSIVE_PLAN_GENERATION and no causal grid/confirmation',
    'layer_score':'minimum of mean SWAP and mean LATER_vs each of NO_PATCH, SWAPPED_PLAN_RESIDUAL, RANDOM_SAME_NORM, UNRELATED_PLAN_RESIDUAL, GENERIC_HISTORY_RESIDUAL','tie_break':['higher layer_score','higher mean SWAP','higher mean LATER_vs_NO_PATCH','smaller layer index'],
    'advance_gate':'best layer_score must be >0; otherwise DEVELOPMENT_NULL_REPLAY_RESIDUAL and confirmation remains sealed','freeze_before_confirmation':['selected layer','all development plan outputs/hashes','development family effects','unrelated donor map SHA','exact runner/runtime hashes']},
  'confirmation_primary':{'population':'all 24 frozen confirmation families; if plan qualification gate passes, unqualified families remain in denominator with zero/nonpositive effects','qualification_gate':'at least16/24; failure => INCONCLUSIVE_PLAN_GENERATION without causal interpretation',
    'primary_signed_effects':['SWAP','LATER_vs_NO_PATCH','LATER_vs_SWAPPED_PLAN_RESIDUAL','LATER_vs_RANDOM_SAME_NORM','LATER_vs_UNRELATED_PLAN_RESIDUAL','LATER_vs_GENERIC_HISTORY_RESIDUAL'],
    'tests':'six exact one-sided sign/binomial tests over all24 families; zeros are non-positive; Holm FWER 0.05','effect_guards':{'mean_SWAP_min_nats_per_token':0.10,'positive_SWAP_fraction_min':0.70,'mean_LATER_vs_NO_PATCH_min_nats_per_token':0.05,'mean_each_other_LATER_contrast_min_nats_per_token':0.03,'positive_PERSISTENT_CAUSAL_PLAN_SCORE_vs_NO_PATCH_fraction_min':0.70},
    'support_rule':'all six Holm-adjusted tests significant and all effect guards pass; otherwise do not claim causal persistent plan checkpoint'},
  'behavioral_rollout_guard':{'required_for_full_T1_claim':True,'persistent_cache_session_required':True,'arms':['ACTIVE','SWAPPED_PLAN_RESIDUAL','NO_PATCH','VISIBLE_TEXT_PLAN_REPLAY'],'temperature':0.0,'max_post_reset_actions':12,'single_injection_only':True,
    'plan_order_endpoint':'identity of the target object first successfully moved into the target receptacle; route-independent with respect to navigation/open detours','directionality_guards':{'active_selected_first_rate_min':0.65,'swapped_counter_first_rate_min':0.65,'bidirectional_family_fraction_min':0.60,'active_minus_swapped_selected_first_rate_min':0.30},
    'task_success_guard':'ACTIVE and SWAPPED each must not be worse than NO_PATCH by more than 2/24 absolute successes; task success is a competence guard, not the causal endpoint because both orders are valid'},
  'plumbing_guards':{'sentinel_families':[0,1],'layers':[6,13,20,27],'ZERO_ADD_max_abs_meanLP_delta':1e-6,'SELF_PATCH_max_abs_meanLP_delta':1e-4,'token_boundary_prefix_stable':True,'output_overwrite_refusal':True},
  'phase_isolation':{'development_before_confirmation':True,'confirmation_requests_before_selection_sha_forbidden':True,'partial_confirmation_inspection_forbidden':True,'valid_seen_forbidden':True,'valid_unseen_forbidden':True,'T1R_forbidden_until_supported_T1':True,'T2_forbidden_until_supported_T1':True},
  'claim_scope':{'success':'T1 evidence that an episode-specific paired replay residual causally controls active plan order across reset and retains influence beyond the first action; no compactness/generalization claim yet','not_yet':['minimal dimension','storage advantage','cross-model','cross-environment','end-to-end memory superiority']},
  'later_tiers':{'T1R':'family-disjoint no-retune replication only after T1 support','T2':'longer forced identical-prefix persistence/decay only after T1 support','T3':'projection/compression dimension sweep + bytes/token accounting only after replicated persistence','G':'second model and second environment only after T3'},
  'kill_conditions':['plan qualification <16/24 at either phase','development best robust layer_score <=0','confirmation Holm/effect guards fail','effect is first-action-only because later persistence tests fail','swapped-plan residual does not directionally counter-control plan order','task competence materially collapses','requires repeated injection','requires post-hoc threshold/layer/scale/family tuning'],
  'prohibited_changes':['reuse consumed v2.6/v2.7/Qwen3 recovery families','relax prior failed source-competence thresholds as rescue','family filtering/replacement after model outcomes','alpha/scale search','synthetic reciprocal source-prompt competence gate','confirmation access before frozen selection','repeated patching','valid_seen/unseen access','interpret development as support']}
 dsha=dump(DES,design)
 checks={
  'manifest_sha_match':sha_bytes(MAN)==msh,'manifest_n48':len(rows)==48,'dev24_conf24':m['development_n']==24 and m['confirmation_n']==24,'zero_overlap':m['development_confirmation_family_overlap']==0,
  'all_delayed':m['all_delayed_divergence'] is True,'common_prefix_ge1':m['min_common_prefix_actions']>=1,'env_only_no_model':m['model_calls']==0 and m['environment_only'] is True,
  'layers_exact':design['residual_definition']['layers']==[6,13,20,27],'alpha_fixed_one':design['residual_definition']['active_scale']==1.0 and design['residual_definition']['scale_search'] is False,
  'strict_strip_token659':design['strict_stripping']['neutral_token_id']==659,'qualification_all24_policy':'all 24' in design['confirmation_primary']['population'],
  'six_exact_sign_tests':'six exact one-sided sign/binomial tests' in design['confirmation_primary']['tests'],'holm': 'Holm FWER 0.05' in design['confirmation_primary']['tests'],
  'zeros_fail':'zeros are non-positive' in design['confirmation_primary']['tests'],'later_excludes_first':design['teacher_forced_mechanistic_readout']['later_steps_exclude_first_action'] is True,
  'single_injection':design['target_intervention']['single_injection_only'] and design['target_intervention']['repeated_patch_forbidden'],'rollout_single_injection':design['behavioral_rollout_guard']['single_injection_only'],
  'donor_dev_only':design['unrelated_donor_map']['confirmation_donor_pool']=='development only','no_confirmation_early':design['phase_isolation']['confirmation_requests_before_selection_sha_forbidden'],
  'no_family_replace':'family filtering/replacement after model outcomes' in design['prohibited_changes'],'t1_only':'minimal dimension' in design['claim_scope']['not_yet']}
 audit={'kind':'PLANCARRY_REPLAY_RESIDUAL_T1_STATIC_AUDIT_V1','scientific_result':'NOT_ASSESSED','model_calls':0,'design_path':str(DES),'design_sha256':dsha,'manifest_sha256':msh,'donor_map_sha256':dsh,'checks':checks,'passed':all(checks.values()),'n_passed':sum(checks.values()),'n_total':len(checks),'confirmation_accessed':False,'valid_seen_accessed':False,'valid_unseen_accessed':False}
 ash=dump(AUD,audit)
 print(json.dumps({'design_path':str(DES),'design_sha256':dsha,'manifest_sha256':msh,'donor_map_sha256':dsh,'audit_sha256':ash,'audit_passed':audit['passed'],'checks':f"{audit['n_passed']}/{audit['n_total']}"},sort_keys=True))
if __name__=='__main__':main()
