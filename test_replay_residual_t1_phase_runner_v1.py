import json
import tempfile
import unittest
from pathlib import Path

import replay_residual_t1_phase_runner_v1 as r


def sha(ch):
    return (ch * 64)[:64]


def arm(fam, lpa, ts, valid, hook, norm_guard=True):
    return {
        "lpa": lpa,
        "task_success": ts,
        "valid_action_rate": valid,
        "hook_count": hook,
        "vector_norm_guard_passed": norm_guard,
        "reset_prefix_sha256": fam["reset_prefix_sha256"],
        "reset_world_state_sha256": fam["reset_world_state_sha256"],
        "reset_serialization_sha256": fam["reset_serialization_sha256"],
        "task_instruction_sha256": fam["task_instruction_sha256"],
        "reset_observation_sha256": fam["reset_observation_sha256"],
        "admissible_actions_sha256": fam["admissible_actions_sha256"],
        "world_state_match_enforced": True,
        "lpa_excludes_first_action": True,
    }


def base_family(idx, qualified=True):
    row = {"index": idx, "qualified": qualified}
    if qualified:
        row.update({
            "reset_prefix_sha256": sha("a"),
            "reset_world_state_sha256": sha("b"),
            "reset_serialization_sha256": sha("c"),
            "task_instruction_sha256": sha("1"),
            "reset_observation_sha256": sha("2"),
            "admissible_actions_sha256": sha("3"),
            "reference_world_state_sequence_sha256": sha("d"),
            "reference_remaining_action_count": 4,
            "primary_endpoint": r.PRIMARY_ENDPOINT,
            "lpa_excludes_first_action": True,
            "world_state_match_enforced": True,
            "engineering_sentinels": {"zero_add_no_patch_maxabs": 0.0, "self_replace_no_patch_maxabs": 0.0},
        })
    return row


def metric_for(fam, active=0.8, nopatch=0.2, ctrl=0.3, active_ts=1.0):
    arms = {
        r.ACTIVE: arm(fam, active, active_ts, 0.9, 1),
        r.NO_PATCH: arm(fam, nopatch, 0.0, 0.9, 0, False),
    }
    for c in r.SPECIFICITY_CONTROLS:
        arms[c] = arm(fam, ctrl, 0.0, 0.9, 1)
    return {"active_raw_residual_l2": 1.0, "arms": arms}


def common_payload(phase):
    return {
        "phase": phase,
        "sanity_status": r.SANITY_REQUIRED,
        "t1_prereg_sha256": r.T1_PREREG_SHA256,
        "gap_matrix_sha256": r.GAP_MATRIX_SHA256,
        "v2_1_contract_sha256": r.V2_1_CONTRACT_SHA256,
        "session_runtime_sha256": r.SESSION_RUNTIME_SHA256,
        "phase_runner_sha256": r.self_sha256(),
        "source_anchor": r.SOURCE_ANCHOR,
        "target_site": r.TARGET_SITE,
    }


def dev_payload(q=32, best=(14, 0.5)):
    p = common_payload("T1_DEVELOPMENT")
    fams = [base_family(i, i < q) for i in r.DEVELOPMENT_INDICES]
    p["families"] = fams
    qualified = [f for f in fams if f["qualified"]]
    p["vector_sha256_by_family_layer"] = {str(f["index"]): {str(l): sha("e") for l in r.LAYERS} for f in qualified}
    grids = {}
    for l in r.LAYERS:
        for a in r.ALPHAS:
            # Best margin at requested point; elsewhere equal lower margin. Task success drives tie only.
            is_best = (l, a) == best
            active = 0.85 if is_best else 0.65
            ctrl = 0.25
            grids[r.grid_key(l, a)] = {str(f["index"]): metric_for(f, active=active, ctrl=ctrl, active_ts=1.0 if is_best else 0.5) for f in qualified}
    p["grid_results"] = grids
    return p


def confirmation_payload(seal_sha, selected_layer, selected_alpha, q=20, strong=True):
    p = common_payload("T1_CONFIRMATION")
    p.update({"development_seal_sha256": seal_sha, "selected_layer": selected_layer, "selected_alpha": selected_alpha})
    fams = []
    for pos, idx in enumerate(r.CONFIRMATION_INDICES):
        fam = base_family(idx, pos < q)
        if fam["qualified"]:
            m = metric_for(fam, active=0.8 if strong else 0.31, nopatch=0.2 if strong else 0.30, ctrl=0.3 if strong else 0.30, active_ts=1.0 if strong else 0.4)
            fam["active_raw_residual_l2"] = m["active_raw_residual_l2"]
            fam["arms"] = m["arms"]
        fams.append(fam)
    p["families"] = fams
    return p


class TestT1PhaseRunner(unittest.TestCase):
    def test_sign_p_and_holm(self):
        self.assertAlmostEqual(r.exact_one_sided_sign_p(10, 12), 0.019287109375)
        h = r.holm_two({"d_no_patch": 0.01, "d_specificity": 0.04})
        self.assertTrue(h["both_pass"])
        self.assertFalse(r.holm_two({"d_no_patch": 0.06, "d_specificity": 0.001})["both_pass"])

    def test_dev_gate_inconclusive_no_seal(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"seal.json"
            out = r.select_development(dev_payload(q=15), path)
            self.assertEqual(out["status"], "INCONCLUSIVE_T1_DEVELOPMENT_EXPRESSIVITY")
            self.assertFalse(path.exists())

    def test_development_selection_and_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"seal.json"
            out=r.select_development(dev_payload(best=(14,0.5)),path)
            self.assertEqual((out["selected_layer"],out["selected_alpha"]),(14,0.5))
            self.assertEqual(out["qualified_count"],32)
            self.assertTrue(path.exists())
            self.assertTrue(r.validate_t1_phase_artifact(json.loads(path.read_text())))
            with self.assertRaises(r.T1PhaseContractError): r.select_development(dev_payload(),path)

    def test_tie_break_lower_alpha_then_earlier_layer(self):
        p=dev_payload()
        # Force identical metric everywhere, so alpha then layer decide.
        qualified=[f for f in p["families"] if f["qualified"]]
        p["grid_results"]={r.grid_key(l,a):{str(f["index"]):metric_for(f,active=.7,ctrl=.3,active_ts=.5) for f in qualified} for l in r.LAYERS for a in r.ALPHAS}
        with tempfile.TemporaryDirectory() as td:
            out=r.select_development(p,Path(td)/"s")
            self.assertEqual((out["selected_layer"],out["selected_alpha"]),(7,0.25))

    def _seal(self, td):
        path=Path(td)/"seal.json"; out=r.select_development(dev_payload(best=(14,.5)),path)
        return path,out["seal_file_sha256"],out

    def test_confirmation_phase_seal_validated_before_input_read(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,_=self._seal(td)
            bad_input=Path(td)/"confirmation.json"; bad_input.write_text("NOT JSON")
            with self.assertRaisesRegex(r.T1PhaseContractError,"seal sha mismatch"):
                r.run_confirmation_file(bad_input,seal,sha("f"),Path(td)/"out.json")

    def test_confirmation_all20_supported_with_four_unqualified(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            inp=Path(td)/"c.json"; outp=Path(td)/"o.json"
            inp.write_text(json.dumps(confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=16,strong=True)))
            out=r.run_confirmation_file(inp,seal,seal_sha,outp)
            self.assertEqual(out["status"],r.SUPPORTED_PRIMARY)
            self.assertEqual(out["denominator"],20)
            self.assertEqual(out["qualified_count"],16)
            self.assertEqual(out["positive_counts"],{"d_no_patch":16,"d_specificity":16})
            self.assertTrue(out["holm"]["both_pass"]); self.assertTrue(out["all_effect_guards_pass"])

    def test_confirmation_gate_inconclusive(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            payload=confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=15,strong=True)
            got=r.evaluate_confirmation(payload,json.loads(seal.read_text()),seal_sha)
            self.assertEqual(got["status"],"INCONCLUSIVE_T1_CONFIRMATION_EXPRESSIVITY")
            self.assertEqual(got["denominator"],20)

    def test_confirmation_null_when_effects_weak(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            got=r.evaluate_confirmation(confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=20,strong=False),json.loads(seal.read_text()),seal_sha)
            self.assertEqual(got["status"],"REFUTED_REPLAY_RESIDUAL_T1")

    def test_reset_hash_and_hook_guards(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            p=confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=20,strong=True)
            p["families"][0]["arms"][r.ACTIVE]["reset_world_state_sha256"]=sha("f")
            with self.assertRaisesRegex(r.T1PhaseContractError,"reset provenance mismatch"):
                r.evaluate_confirmation(p,json.loads(seal.read_text()),seal_sha)
            p=confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=20,strong=True)
            p["families"][0]["arms"][r.ACTIVE]["hook_count"]=2
            with self.assertRaisesRegex(r.T1PhaseContractError,"hook_count"):
                r.evaluate_confirmation(p,json.loads(seal.read_text()),seal_sha)

    def test_partial_confirmation_population_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            p=confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"]); p["families"].pop()
            with self.assertRaisesRegex(r.T1PhaseContractError,"family index set mismatch"):
                r.evaluate_confirmation(p,json.loads(seal.read_text()),seal_sha)

    def test_confirmation_output_overwrite_refused_before_read(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            inp=Path(td)/"bad.json"; inp.write_text("NOT JSON")
            out=Path(td)/"out.json"; out.write_text("existing")
            with self.assertRaisesRegex(r.T1PhaseContractError,"refuse existing output"):
                r.run_confirmation_file(inp,seal,seal_sha,out)

    def test_operating_point_drift_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            p=confirmation_payload(seal_sha,7,s["selected_alpha"])
            with self.assertRaisesRegex(r.T1PhaseContractError,"layer differs"):
                r.evaluate_confirmation(p,json.loads(seal.read_text()),seal_sha)

    def test_zero_norm_cannot_be_positive_comparison(self):
        fam=base_family(32,True); m=metric_for(fam,active=.9,nopatch=.1,ctrl=.2); fam["arms"]=m["arms"]; fam["active_raw_residual_l2"]=0.0
        vals=r._confirmation_family_values(fam)
        self.assertLessEqual(vals["d_no_patch"],0.0); self.assertLessEqual(vals["d_specificity"],0.0)

    def test_t1r_lock(self):
        for status in ["REFUTED_REPLAY_RESIDUAL_T1","INCONCLUSIVE_T1_CONFIRMATION_EXPRESSIVITY","TECHNICAL_INVALID"]:
            with self.assertRaises(r.T1PhaseContractError): r.assert_t1r_unlocked(status)
        r.assert_t1r_unlocked(r.SUPPORTED_PRIMARY)

    def test_provenance_drift_rejected(self):
        p=dev_payload(); p["t1_prereg_sha256"]=sha("f")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(r.T1PhaseContractError,"prereg hash drift"):
                r.select_development(p,Path(td)/"s")


    def test_extra_development_arm_rejected(self):
        p=dev_payload(q=16)
        key=next(iter(p["grid_results"]))
        fam_idx=next(iter(p["grid_results"][key]))
        p["grid_results"][key][fam_idx]["arms"]["EXTRA_NOT_PREREGISTERED"] = dict(p["grid_results"][key][fam_idx]["arms"][r.NO_PATCH])
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(r.T1PhaseContractError,"arm set must equal"):
                r.select_development(p,Path(td)/"s")

    def test_extra_confirmation_arm_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            p=confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=20,strong=True)
            p["families"][0]["arms"]["EXTRA_NOT_PREREGISTERED"] = dict(p["families"][0]["arms"][r.NO_PATCH])
            with self.assertRaisesRegex(r.T1PhaseContractError,"arm set must equal"):
                r.evaluate_confirmation(p,json.loads(seal.read_text()),seal_sha)

    def test_development_artifact_internal_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            seal,_,_=self._seal(td)
            obj=json.loads(seal.read_text())
            obj["qualified_count"] -= 1
            with self.assertRaisesRegex(r.T1PhaseContractError,"qualified_count drift"):
                r.validate_t1_phase_artifact(obj)
            obj=json.loads(seal.read_text())
            obj["all_grid_aggregates"][r.grid_key(7,.25)]["active_task_success_rate"] = 0.123
            with self.assertRaisesRegex(r.T1PhaseContractError,"aggregate sha drift"):
                r.validate_t1_phase_artifact(obj)
            obj=json.loads(seal.read_text())
            obj["selected_vector_sha256_by_family"].pop(next(iter(obj["selected_vector_sha256_by_family"])))
            with self.assertRaisesRegex(r.T1PhaseContractError,"vector family map drift"):
                r.validate_t1_phase_artifact(obj)

    def test_confirmation_artifact_recomputes_statistics_and_status(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            obj=r.evaluate_confirmation(confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=20,strong=True),json.loads(seal.read_text()),seal_sha)
            self.assertTrue(r.validate_t1_phase_artifact(obj))
            bad=json.loads(json.dumps(obj)); bad["positive_counts"]["d_no_patch"] -= 1
            with self.assertRaisesRegex(r.T1PhaseContractError,"positive-count drift"):
                r.validate_t1_phase_artifact(bad)
            bad=json.loads(json.dumps(obj)); bad["effect_guards"]["mean_d_no_patch_ge_0_15"] = False
            with self.assertRaisesRegex(r.T1PhaseContractError,"effect-guard drift"):
                r.validate_t1_phase_artifact(bad)
            bad=json.loads(json.dumps(obj)); bad["status"]="REFUTED_REPLAY_RESIDUAL_T1"
            with self.assertRaisesRegex(r.T1PhaseContractError,"final status inconsistent"):
                r.validate_t1_phase_artifact(bad)

    def test_inconclusive_confirmation_artifact_gate_consistency(self):
        with tempfile.TemporaryDirectory() as td:
            seal,seal_sha,s=self._seal(td)
            obj=r.evaluate_confirmation(confirmation_payload(seal_sha,s["selected_layer"],s["selected_alpha"],q=15,strong=True),json.loads(seal.read_text()),seal_sha)
            self.assertTrue(r.validate_t1_phase_artifact(obj))
            bad=dict(obj); bad["qualified_count"]=16
            with self.assertRaisesRegex(r.T1PhaseContractError,"contradicts"):
                r.validate_t1_phase_artifact(bad)


if __name__ == '__main__':
    unittest.main()
