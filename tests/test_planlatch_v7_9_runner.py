import dataclasses
import hashlib
import json
from pathlib import Path
import pytest
import planlatch_v7_9_protocol as p
import planlatch_v7_9_runner as r


def make_tasks(n=36):
    rows=[]
    for i in range(n):
        rows.append(r.BaseTaskMetadata(
            task_id=f"train-task-{i:03d}", m0=f"m0-{i%3}", cross_realization_tag=f"real-{i:03d}",
            split="train", never_consumed=True,
            dependency_keys={
                "base_task_identity":f"train-task-{i:03d}",
                "relation_template_group_id":f"rel-{i:03d}",
                "source_template_instance_family_id":f"src-{i:03d}",
                "paired_rng_ancestor_id":f"rng-{i:03d}",
                "generation_seed_family_id":f"seed-{i:03d}",
                "constructor_randomization_table_id":f"ctor-{i:03d}",
                "cache_namespace_parent_id":f"cache-{i:03d}",
                "source_data_origin_family_id":f"origin-{i:03d}",
            }))
    return rows


def test_protocol_bytes_are_fidelity_confirmed_identity():
    assert r.protocol_byte_identity()
    assert r.sha256_file("planlatch_v7_9_protocol.py") == r.PROTOCOL_SHA256


def test_frame_is_whole_block_complete_and_pre_response_only():
    frame=r.compile_pre_response_frame(make_tasks())
    assert len(frame.block_ids)==36
    assert list(frame.partition_by_block.values()).count("FIT")==12
    assert list(frame.partition_by_block.values()).count("PILOT")==8
    assert list(frame.partition_by_block.values()).count("SUPPORT")==12
    assert list(frame.partition_by_block.values()).count("CROSS_REALIZATION")==4
    assert r.verify_complete_cells(frame)
    assert len(frame.cells)==36*16
    assert all(c.u==(c.a,c.h,c.m0) for c in frame.cells)


def test_dependency_closure_keeps_linked_tasks_in_one_block():
    tasks=make_tasks(37)
    a=tasks[0]
    b=tasks[-1]
    keys=dict(b.dependency_keys); keys["paired_rng_ancestor_id"]=a.dependency_keys["paired_rng_ancestor_id"]
    tasks[-1]=dataclasses.replace(b,dependency_keys=keys)
    frame=r.compile_pre_response_frame(tasks)
    cells0={c.block_id for c in frame.cells if c.task_id==a.task_id}
    cellsb={c.block_id for c in frame.cells if c.task_id==tasks[-1].task_id}
    assert cells0==cellsb


def test_probe_bank_and_candidate_universe_are_semantic_blind_hash_derivations():
    bank1=r.derive_opaque_probe_bank(1000,{0,1,2}); bank2=r.derive_opaque_probe_bank(1000,{0,1,2})
    assert bank1==bank2 and len(bank1.token_ids)==r.OPAQUE_PROBE_COUNT
    assert not ({0,1,2}&set(bank1.token_ids))
    coords=r.derive_candidate_channels([32]*16)
    assert len(coords)==r.CANDIDATE_CHANNEL_COUNT and len(set(coords))==r.CANDIDATE_CHANNEL_COUNT


def test_global_involution_lossless_orbit_and_q():
    vals=(0.25,-1.5,2.0,0.0)
    t=r.serialize_t(vals); gt=r.apply_g(t)
    assert r.apply_g(gt)==t
    rec=r.canonicalize_response(vals)
    assert rec.c1==r.apply_g(rec.c0)
    assert len(rec.o_star)==2*len(vals)
    assert rec.j_singleton is False and rec.q in (0,1)
    singleton=r.canonicalize_response((0.0,0.0))
    assert singleton.j_singleton and singleton.q is None


def test_decoder_freeze_is_synthetic_only_and_passes_positive_negative_canaries():
    cfg,audit=r.freeze_decoder_config()
    assert cfg.family==r.DECODER_FAMILY
    selected=[x for x in audit["attempts"] if x["passed"]]
    assert selected
    m=selected[0]["metrics"]
    assert m["positive_ba_gain"]>=0.25 and m["positive_log_gain"]>=0.20
    assert m["factorized_abs_log_gain"]<=0.01 and m["factorized_abs_ba_gain"]<=0.02


def test_phi_is_label_bit_blind_and_weights_are_post_phi():
    cfg,_=r.freeze_decoder_config()
    o=[(-1.0,0.2),(1.0,0.2),(-0.5,-0.2),(0.5,-0.2)]
    labels=["p","q","p","q"]; q=[0,1,1,0]
    a=r.fit_source_models(o,q,labels,(0,0,"m0"),cfg)
    b=r.fit_source_models(o,[1-x for x in q],list(reversed(labels)),(0,0,"m0"),cfg)
    assert a.phi.serialized_bytes()==b.phi.serialized_bytes()


def test_placebo_scoring_uses_p_mix_one_record_functional():
    cfg,_=r.freeze_decoder_config()
    o=[(-2.0,0.0)]*10+[(2.0,0.0)]*10
    labels=["p"]*10+["q"]*10; q=[i%2 for i in range(20)]
    models=r.fit_source_models(o,q,labels,(0,0,"m0"),cfg)
    out=r.score_source_record(models,o[0],q[0],labels[0])
    assert {"full_label","placebo_label","full_log","placebo_log","delta_log"} <= set(out)
    assert set(out["full_probabilities"])==set(p.LABEL_ORDER)
    assert set(out["placebo_mix"])==set(p.LABEL_ORDER)
    assert out["placebo_label"] == p.hard_label(out["placebo_mix"])


def test_payload_bank_is_fit_only_anonymous_and_distinct():
    rows=[]
    for i in range(40):
        rows.append(r.ActuatorCandidateEvidence(i//8,i,p.ALLOWED_GAINS[i%2],float(40-i),float(i),"FIT",f"fit-{i}"))
    cp,cq,audit=r.construct_payload_bank_fit_only(rows)
    assert audit["fit_only"] and cp.triples!=cq.triples
    selected=r.select_anonymous_payload("p",cp,cq)
    assert set(selected)=={"version","triples","checksum"}
    text=r.stable_json(selected)
    assert "C_p" not in text and "C_q" not in text and '"name"' not in text


def test_reset_envelope_has_no_donor_decoder_semantic_fields():
    env=r.build_reset_applier_envelope(None,"a"*64,"b"*64)
    text=r.stable_json(env)
    for forbidden in ("o_star","decoder_score","predicted_s","donor_hidden","past_key_values","C_p","C_q"):
        assert forbidden not in text
    assert env["arm"]=="NO_CODEWORD"


def test_runtime_freeze_is_deterministic_and_non_scientific(tmp_path):
    a,audit_a=r.synthetic_runtime_freeze(); b,audit_b=r.synthetic_runtime_freeze()
    assert a==b and audit_a==audit_b
    assert a.protocol_sha256==r.PROTOCOL_SHA256
    assert a.model_revision==r.MODEL_REVISION and a.task_split=="train"


def _h(name):
    return hashlib.sha256(name.encode()).hexdigest()


def make_pre_source_manifest():
    freeze,_=r.synthetic_runtime_freeze()
    return {
        "phase":"PRE_SOURCE",
        "design_id":r.DESIGN_ID,"semantic_hash":r.SEMANTIC_HASH,"runtime_freeze_hash":freeze.freeze_hash,
        "model_id":r.MODEL_ID,"model_revision":r.MODEL_REVISION,"model_dtype":r.MODEL_DTYPE,
        "quantization":r.MODEL_QUANTIZATION,"task_split":"train","never_consumed_train_inventory":True,
        "frame_hash":_h("frame"),"dependency_hash":_h("dependency"),"probe_bank_hash":_h("probe"),
        "candidate_channel_hash":_h("channels"),"decoder_config_hash":freeze.decoder["config_hash"],
        "task_inventory_hash":_h("inventory"),"freshness_attestation_hash":_h("freshness"),
        "model_parameter_hash":_h("model-params"),
    }


def make_post_fit_manifest(pre):
    pre_binding=r.verify_pre_source_manifest(pre,Path('/tmp')/'v79-manifest-hash-probe-not-created')
    return {
        "phase":"POST_FIT_HELDOUT","design_id":r.DESIGN_ID,"semantic_hash":r.SEMANTIC_HASH,
        "pre_source_manifest_hash":pre_binding.manifest_hash,"pre_source":pre,
        "fit_only_complete":True,"heldout_partitions_unread_before_freeze":True,
        "source_model_bytes_hash":_h("source-model"),"decoder_bytes_hash":_h("decoder-bytes"),
        "phi_bytes_hash":_h("phi-bytes"),"transformed_o_star_hash":_h("o-star"),
        "payload_bank_hash":_h("payload"),"visible_context_manifest_hash":_h("visible"),
        "endpoint_manifest_hash":_h("endpoints"),"reset_attestation_hash":_h("reset"),
        "model_parameter_hash":pre["model_parameter_hash"],
    }


def test_real_execution_manifest_is_staged_fail_closed_and_fresh_namespace(tmp_path):
    pre=make_pre_source_manifest(); out=tmp_path/"fresh.json"
    assert r.verify_frozen_real_manifest(pre,out)
    # PRE_SOURCE deliberately does not and must not require FIT-derived hashes.
    for forbidden in ("source_model_bytes_hash","payload_bank_hash","reset_attestation_hash"):
        assert forbidden not in pre
    post=make_post_fit_manifest(pre)
    assert r.verify_frozen_real_manifest(post,out)
    occupied=tmp_path/"occupied.json"; occupied.write_text("occupied")
    with pytest.raises(r.RuntimeViolation): r.verify_frozen_real_manifest(pre,occupied)
    bad=dict(pre); bad["model_revision"]="wrong"
    with pytest.raises(r.RuntimeViolation): r.verify_frozen_real_manifest(bad,tmp_path/"other.json")
    bad_post=dict(post); bad_post["heldout_partitions_unread_before_freeze"]=False
    with pytest.raises(r.RuntimeViolation): r.verify_frozen_real_manifest(bad_post,tmp_path/"other2.json")
    changed_model=dict(post); changed_model["model_parameter_hash"]=_h("changed-model")
    with pytest.raises(r.RuntimeViolation): r.verify_frozen_real_manifest(changed_model,tmp_path/"other3.json")
    legacy={k:v for k,v in pre.items() if k!="phase"}
    with pytest.raises(r.RuntimeViolation): r.verify_frozen_real_manifest(legacy,tmp_path/"legacy.json")


def test_cli_canary_output_never_claims_science(tmp_path):
    path=tmp_path/"freeze.json"
    assert r.main(["--synthetic-canaries","--output",str(path)])==0
    data=json.loads(path.read_text())
    assert data["scientific_execution_performed"] is False
    assert data["model_or_environment_loaded"] is False
    assert data["kind"].endswith("NOT_SCIENTIFIC_EVIDENCE")


def test_allow_real_execution_intentionally_blocked_pre_release():
    with pytest.raises(r.RuntimeViolation): r.main(["--allow-real-execution"])


def test_frame_rejects_nontrain_or_consumed_tasks_and_cross_realization_must_be_distinct():
    tasks=make_tasks()
    with pytest.raises(r.RuntimeViolation):
        r.BaseTaskMetadata(task_id="x",m0="m",dependency_keys={"base_task_identity":"x"},cross_realization_tag="r",split="valid_seen",never_consumed=True)
    with pytest.raises(r.RuntimeViolation):
        r.BaseTaskMetadata(task_id="x",m0="m",dependency_keys={"base_task_identity":"x"},cross_realization_tag="r",split="train",never_consumed=False)
    # 32 fixed groups + four groups that all advertise the same concrete realization is invalid.
    rows=[dataclasses.replace(x,cross_realization_tag="same") for x in make_tasks(36)]
    with pytest.raises(r.RuntimeViolation): r.compile_pre_response_frame(rows)


def test_payload_bank_rejects_nonfit_provenance():
    rows=[r.ActuatorCandidateEvidence(i//8,i,p.ALLOWED_GAINS[i%2],40-i,i,source_partition="FIT",source_record_hash=f"fit-{i}") for i in range(40)]
    r.construct_payload_bank_fit_only(rows)
    rows[0]=dataclasses.replace(rows[0],source_partition="PILOT")
    with pytest.raises(r.RuntimeViolation): r.construct_payload_bank_fit_only(rows)


def make_source_gate_report():
    canary_names=("positive","conditional_placebo","factorized_negative","label_permutation_preprocessing_invariance",
        "decoder_relative_common_transform_null","collapsed_symmetric_null_objective_equivalence","placebo_metric_reduction",
        "incompatible_nuisance_router","singleton_zero","off_support_toggle_boundary")
    return {
        "frame_frozen_pre_T":True,"complete_cell_schedule":True,"response_derived_replacement":False,
        "only_U_external_router":True,"forbidden_paths_unreachable":True,
        "j_distribution_reported":True,"standardized_realized_j0_scope":True,"j1_member_contribution_zero":True,
        "uniform_preprocessing_weights":True,"label_permutation_invariant":True,
        "full_placebo_transformed_o_star_hash_equal":True,"bit_path_block_separable":True,
        "canaries":{k:True for k in canary_names},"two_class_j0_constructible":True,
        "support_blocks":[{"delta_b":0.03,"ba_increment":0.06} for _ in range(12)],
        "pilot_blocks":[{"delta_b":0.02,"full_ba":0.85} for _ in range(8)],
        "constructible_u_deltas":[0.01,0.02,0.03],"u_only_baseline_cannot_explain":True,
        "sham_specificity_pass":True,"all_selection_actual_supported_q":True,
        "off_support_used_for_evidence_or_selection":False,
    }


def make_relay_gate_report():
    triples=[[i//8,i,p.ALLOWED_GAINS[i%2]] for i in range(p.PAYLOAD_K)]
    payload=p.make_payload_manifest(tuple(p.PayloadTriple(*x) for x in triples)).serialized_payload()
    return {
        "bank_fit_only":True,"bank_identical_budget":True,"bank_structurally_distinct":True,
        "bank_independent_of_later_information":True,"applied_payload":payload,
        "payload_sole_donor_object_after_reset":True,"donor_state_unreachable":True,
        "model_parameter_checksum_unchanged":True,"clean_cache_visible_context_identical":True,
        "selection_is_f_U_phiO_Q_actual_support":True,"payload_frozen_before_evaluator_unseal":True,
        "all_arm_scores_frozen_before_labels":True,
        "cp_vs_no_pilot":[0.06]*8,"cq_vs_no_pilot":[0.06]*8,"cp_vs_cq_directional_pilot":[0.06]*8,
        "direction_survives_true_s_stratification":True,
        "selected_payload_by_class":{
            "p":{"block_count":4,"record_count":12,"block_shifts":[0.05,0.05,0.05,0.05]},
            "q":{"block_count":4,"record_count":12,"block_shifts":[0.05,0.05,0.05,0.05]},
        },
        "cross_realization":[{"cp_correct":True,"cq_correct":True,"selected_correct":True} for _ in range(4)],
        "endpoint_no_systematic_reversal":True,"valid_action_worse_blocks":1,
    }


def test_g1_g20_pass_report_has_exact_twenty_gates():
    out=r.evaluate_g1_g20(make_source_gate_report(),make_relay_gate_report())
    assert out["all_passed"] and not out["failures"]
    assert len(out["gates"])==20
    assert set(k.split("_")[0] for k in out["gates"])=={f"G{i}" for i in range(1,21)}
    assert out["interpretation"].startswith("mechanical gate evaluation only")


def test_source_gate_threshold_boundaries_fail_closed():
    x=make_source_gate_report()
    # 9/12 positive fails G7 even though median effect remains positive.
    for i in range(3): x["support_blocks"][i]["delta_b"]=-0.001
    x["support_blocks"][3]["delta_b"]=-0.001
    out=r.evaluate_source_gates(x)
    assert not out["gates"]["G7_fixed_support_replication"]
    x=make_source_gate_report(); x["pilot_blocks"][0]["delta_b"]=-0.01; x["pilot_blocks"][1]["delta_b"]=-0.01
    assert not r.evaluate_source_gates(x)["gates"]["G9_pilot_replication"]
    x=make_source_gate_report(); x["canaries"]["off_support_toggle_boundary"]=False
    assert not r.evaluate_source_gates(x)["gates"]["G5_canaries"]


def test_relay_gate_threshold_and_reset_boundaries_fail_closed():
    x=make_relay_gate_report(); x["cp_vs_no_pilot"]=[0.06]*5+[0.0]*3
    assert not r.evaluate_relay_gates(x)["gates"]["G17_bidirectional_payload_efficacy"]
    x=make_relay_gate_report(); x["selected_payload_by_class"]["q"]["record_count"]=11
    assert not r.evaluate_relay_gates(x)["gates"]["G19_selected_payload_relay"]
    x=make_relay_gate_report(); x["cross_realization"][0]["selected_correct"]=False; x["cross_realization"][1]["selected_correct"]=False
    assert not r.evaluate_relay_gates(x)["gates"]["G20_cross_realization"]
    x=make_relay_gate_report(); x["donor_state_unreachable"]=False
    assert not r.evaluate_relay_gates(x)["gates"]["G15_reset_provenance"]


def test_runtime_freeze_commits_staged_execution_boundary():
    freeze,_=r.synthetic_runtime_freeze()
    assert set(freeze.staged_execution_contract)=={"PRE_SOURCE","POST_FIT_HELDOUT"}
    assert "before donor response" in freeze.staged_execution_contract["PRE_SOURCE"]
    assert "FIT only" in freeze.staged_execution_contract["POST_FIT_HELDOUT"]


def test_preflight_runs_every_named_v79_canary_before_real_access():
    freeze,audit=r.synthetic_runtime_freeze()
    c=audit["protocol_checks"]["protocol_canaries"]
    expected={"positive","conditional_placebo","factorized_negative","J_selection_boundary","placebo_metric_reduction",
        "off_support_toggle_boundary","incompatible_nuisance_router","orbit_redundant_chart_boundary",
        "decoder_relative_common_transform_null","label_permutation_preprocessing_invariance",
        "collapsed_symmetric_null_objective_equivalence","singleton_zero"}
    assert set(c)==expected and all(v["passed"] for v in c.values())
    assert c["collapsed_symmetric_null_objective_equivalence"]["max_parameter_or_prediction_abs_diff"] <= r.DECODER_TOLERANCE


def test_g14_rejects_payload_checksum_tamper():
    x=make_relay_gate_report(); x["applied_payload"]=dict(x["applied_payload"]); x["applied_payload"]["checksum"]="0"*64
    assert not r.evaluate_relay_gates(x)["gates"]["G14_payload_purity"]
