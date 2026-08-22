import json
from pathlib import Path

import alfworld_gdaa_cohort_runner as r


def _arm(success=False, gdaa=False, rpa=False, prompt=100):
    return {
        "success": success, "gdaa": gdaa, "reference_progress_agreement": rpa,
        "prefix_reversal_count": 0, "consecutive_repeat_count": 0,
        "invalid_model_turns": 0, "usage_total": {"total_tokens": 10},
        "first_call_prompt_tokens": prompt,
    }


def _episode(arms):
    return {
        "arms": arms, "all_guards_pass": True,
        "memory_generation_usage": {
            "generic_summary": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            "plancarry": {"compiler": "deterministic_prefix_only", "model_tokens": 0},
        },
    }


def test_frozen_candidate_manifest_is_exact_and_unique():
    games = r.candidate_games()
    assert len(games) == 90
    assert len(set(games)) == 90
    m = json.loads(r.MANIFEST_PATH.read_text())
    assert r.manifest_payload_sha256(m) == r.EXPECTED_MANIFEST_SHA256
    assert m["manifest_sha256"] == r.EXPECTED_MANIFEST_SHA256
    assert games == m["candidates"]


def test_aggregate_keeps_success_gdaa_rpa_separate_and_counts_divergence():
    names = ["observation_only", "tail_truncation", "generic_summary", "plancarry"]
    e1 = _episode({n: _arm(False, False, False, 100) for n in names})
    e1["arms"]["plancarry"] = _arm(True, True, False, 111)
    e2 = _episode({n: _arm(True, True, True, 120) for n in names})
    a = r.aggregate([e1, e2], scanned_count=2, eligible_found=2)
    assert a["measurement_status"] == "INCONCLUSIVE_INSUFFICIENT_ELIGIBLE_COHORT"
    assert a["metrics"]["plancarry"]["successes"] == 2
    assert a["metrics"]["plancarry"]["gdaa_count"] == 2
    assert a["metrics"]["plancarry"]["rpa_count"] == 1
    assert a["metrics"]["plancarry"]["successful_gdaa1_rpa0_count"] == 1
    assert a["natural_successful_gdaa1_rpa0_count_all_arms"] >= 1
    assert a["generic_summary_preprocessing_usage_total"] == {
        "prompt_tokens": 14, "completion_tokens": 6, "total_tokens": 20
    }


def test_complete_synthetic_cohort_measured_only_not_scientifically_assessed():
    names = ["observation_only", "tail_truncation", "generic_summary", "plancarry"]
    episodes = []
    for i in range(8):
        arms = {n: _arm(True, True, True, 100+i) for n in names}
        if i == 0:
            arms["plancarry"] = _arm(True, True, False, 101)
        episodes.append(_episode(arms))
    a = r.aggregate(episodes, scanned_count=12, eligible_found=8)
    assert a["measurement_status"] == "MEASURED_AWAITING_SCIENTIFIC_ASSESSMENT"
    assert a["scientific_result"] == "NOT_ASSESSED"
    assert a["all_gdaa_defined"] is True


def test_undefined_gdaa_invalidates_complete_cohort():
    names = ["observation_only", "tail_truncation", "generic_summary", "plancarry"]
    episodes = []
    for _ in range(8):
        episodes.append(_episode({n: _arm(True, True, False) for n in names}))
    episodes[3]["arms"]["generic_summary"]["gdaa"] = None
    a = r.aggregate(episodes, scanned_count=8, eligible_found=8)
    assert a["measurement_status"] == "INVALID_GUARD_FAILURE"
    assert a["all_gdaa_defined"] is False


def test_runner_does_not_reference_valid_unseen_or_old_v3_output():
    source = Path(r.__file__).read_text()
    assert 'SPLIT = "train"' in source
    assert 'valid_seen' not in source
    assert 'alfworld_cohort_v3.json' not in source


def test_disjoint_v3_binding_pool_is_reproduced_and_overlap_is_zero():
    assert r.EXPERIMENT_ID == "bd09ff0f-5cc6-4846-a486-65e9c858200e"
    assert r.EXPECTED_MANIFEST_SHA256 == "5beaeb849cc6abbee4397c1f8d5021700e272b799e356a2d77d47f920af4d418"
    assert r.EXPECTED_BINDING_POOL_SHA256 == "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee"
    isolation = r.validate_candidate_isolation()
    assert isolation["train_population_count"] == 790
    assert isolation["binding_candidate_count"] == 180
    assert isolation["binding_pool_sha256"] == r.EXPECTED_BINDING_POOL_SHA256
    assert isolation["disjoint_source_pool_count"] == 610
    assert isolation["gdaa_candidate_count"] == 90
    assert isolation["cross_manifest_overlap_count"] == 0
    assert set(r.candidate_games()).isdisjoint(set(r.binding_candidate_games()))


def test_runner_is_not_bound_to_superseded_overlapping_gdaa_v2():
    source = Path(r.__file__).read_text()
    assert "f35b6470-0968-4256-b62e-4387fe3017ba" not in source
    assert "7dbaff3bb3513c52458683cff7c7df17e9e387108492f7930e4c07601f62e874" not in source
    assert "gdaa_train_candidate_manifest_v1.json" not in source
    assert "gdaa_train_candidate_manifest_disjoint_v1.json" in source
