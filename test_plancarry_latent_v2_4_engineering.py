import copy
import hashlib
import json
import math
import shutil
from pathlib import Path

import pytest

import plancarry_latent_v2_4_runner as r
import plancarry_latent_v2_4_validator as v

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def exact_model_info(device_name="NVIDIA GeForce GTX 1650"):
    return {
        "mode": "real",
        "model_id": r.EXPECTED_MODEL_ID,
        "model_revision_requested": r.EXPECTED_MODEL_REVISION,
        "model_commit_resolved": r.EXPECTED_MODEL_REVISION,
        "device": "cuda:0",
        "device_name": device_name,
        "dtype": "torch.float16",
        "transformers_version": r.EXPECTED_TRANSFORMERS,
        "tokenizers_version": r.EXPECTED_TOKENIZERS,
        "quantization": "NONE",
        "num_layers": 28,
        "hidden_size": 1536,
        "torch_version": "2.6.0+cu124",
    }


def test_held_fixed_hashes_unchanged():
    assert sha("plancarry_latent_v2_2_runner.py") == "f5e61aef3c204afc075530eb4bb06797e28d899b09ff1aaf04c27e1b887faf46"
    assert sha("plancarry_latent_v2_2_validator.py") == "d2e7422fa34fb6f048919899d0898caa434ddde51fe02d2fb1dc3d48f9c4b077"
    assert sha("whitebox_bridge.py") == "f1a505ad22ae50f61eff563ff8ce6cce7ae9bd2f08a91bc051b411d3b5029eb2"
    assert sha("whitebox_client.py") == "65e4d52651cd7f1a4fa1f1e9f9ece338228448cb417461ed9316be53bf2396c7"


def test_frozen_bundle_and_tokenizer_audit_pass():
    bundle = v.require_frozen_bundle(ROOT)
    v.validate_prereg_template_contract(bundle["prereg"])
    audit = bundle["tokenizer_audit"]
    assert audit["all_pass"] is True
    assert all(audit["checks"].values())
    assert audit["model_inference"] is False
    assert audit["scientific_result"] == "NOT_ASSESSED"


def test_bundle_hash_failure_is_fail_closed(tmp_path):
    rels = [
        "results/design/plancarry_latent_v2_4_prereg_immutable_20260819T1624Z.json",
        "results/design/plancarry_latent_v2_matched_pair_manifest.json",
        "results/design/plancarry_latent_v2_2_unrelated_donor_map.json",
        "results/design/plancarry_latent_v2_4_independent_review.json",
        "results/design/plancarry_latent_v2_4_static_newline_repair_audit.json",
        "results/design/plancarry_latent_v2_4_exact_template_tokenizer_audit.json",
    ]
    for rel in rels:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    p = tmp_path / rels[0]
    p.write_bytes(p.read_bytes() + b"\n")
    with pytest.raises(Exception):
        v.require_frozen_bundle(tmp_path)


def test_template_literal_backslash_n_is_rejected():
    prereg = copy.deepcopy(v.require_frozen_bundle(ROOT)["prereg"])
    prereg["pair_variable"]["reset_template"] = prereg["pair_variable"]["reset_template"].replace("\n", "\\n")
    with pytest.raises(ValueError, match="LITERAL_BACKSLASH_N"):
        v.validate_prereg_template_contract(prereg)


def test_donor_map_is_discovery_to_confirmation_bijection():
    bundle = v.require_frozen_bundle(ROOT)
    v.validate_donor_map(bundle["manifest"], bundle["donor_map"])
    rows = bundle["donor_map"]["mapping"]
    recipients = [int(x["confirmation_pair_index"]) for x in rows]
    donors = [int(x["discovery_donor_pair_index"]) for x in rows]
    assert recipients == list(range(20, 40))
    assert sorted(donors) == list(range(20))
    assert set(recipients).isdisjoint(donors)


def test_frozen_math_zero_direction_rademacher_sign_holm():
    direction, norm = v.normalized_contrast([1.0, 2.0], [1.0, 2.0 + 1e-10])
    assert norm <= 1e-8
    assert direction == [0.0, 0.0]
    x = v.rademacher_direction("confirmation", 20, 6, 1536)
    y = v.rademacher_direction("confirmation", 20, 6, 1536)
    assert x == y
    assert abs(sum(z*z for z in x) - 1.0) < 1e-12
    assert v.exact_sign_tail(20) == pytest.approx(2**-20)
    assert v.exact_sign_tail(19) == pytest.approx(21 * 2**-20)
    raw = {n: 0.01 for n in v.PRIMARY_TEST_NAMES}
    adj = v.holm_adjust(raw)
    assert set(adj) == set(v.PRIMARY_TEST_NAMES)
    assert max(adj.values()) == pytest.approx(0.04)


def test_bridge_provenance_accepts_only_frozen_gtx1650_contract():
    r.validate_bridge_info(exact_model_info())
    with pytest.raises(RuntimeError, match="device_name"):
        r.validate_bridge_info(exact_model_info("NVIDIA GeForce RTX 3050"))
    bad = exact_model_info(); bad["model_commit_resolved"] = "wrong"
    with pytest.raises(RuntimeError, match="revision_resolved"):
        r.validate_bridge_info(bad)


def test_independent_all40_audit_and_paircontext_newline_contract():
    audit_path = ROOT / "results/design/plancarry_latent_v2_4_partial_runner_disconnect_audit.json"
    assert hashlib.sha256(audit_path.read_bytes()).hexdigest() == "5d140efb4b5a0d20b00bcb17577b8f9c48199334e7a4f1b025e66ced10c83fd3"
    audit = json.loads(audit_path.read_text())
    assert audit["runner_sha256"] == "19ce73cacdcbec50319959529c1c8a6fef9604bc080094d66578ebf0621e2d4e"
    assert audit["validator_sha256"] == "e57783fdf83365561c122f5ba8f0dc9ba827b6e36a1af43ef85c36a1beb3c5d9"
    assert audit["checks"]["all_40_environment_replay_and_serialization"] is True
    assert audit["checks"]["all_40_actual_newline_no_literal_backslash_n"] is True
    assert audit["model_outcomes_seen"] is False
    ctx = r.PairContext(
        pair_index=0, family="synthetic", delayed_divergence=False,
        reset_block="RESET\n<STATE_END>\n",
        active_a="A\n<STATE_END>\n", active_b="B\n<STATE_END>\n",
        archived_a="AA\n<STATE_END>\n", archived_b="BB\n<STATE_END>\n",
        command_a="go to a", command_b="go to b", option_orientation_bit=0,
    )
    assert ctx.scoring_prompt == "RESET\n<STATE_END>\nACTION:"
    assert ctx.source_scoring_prompt("active_a") == "A\n<STATE_END>\nACTION:"
    assert ctx.suffixes == [" go to a", " go to b"]
    with pytest.raises(RuntimeError, match="LITERAL_BACKSLASH_N"):
        r.PairContext(0,"bad",False,"RESET\\n<STATE_END>\n","A\n<STATE_END>\n","B\n<STATE_END>\n","AA\n<STATE_END>\n","BB\n<STATE_END>\n","a","b",0)


def test_confirmation_selection_barrier_fails_before_bridge_call(tmp_path):
    class NeverCall:
        calls = 0
        def model_info(self):
            self.calls += 1
            raise AssertionError("bridge must not be called before selection verification")
    client = NeverCall()
    with pytest.raises(Exception):
        r.run_confirmation(client, tmp_path / "missing-selection.json", "0"*64, tmp_path / "out.json")
    assert client.calls == 0


def test_confirmation_decision_requires_exact_all20_and_frozen_guards():
    rows = [{
        "pair_index": 20 + i,
        "cpse_active": 0.20,
        "cpse_archived": 0.00,
        "cpse_random": 0.00,
        "cpse_unrelated": 0.00,
        "delta_a": 0.10,
        "delta_b": 0.10,
    } for i in range(20)]
    d = v.confirmation_decision(rows, overall_competent=20, delayed_competent=13)
    assert d["status"] == "SUPPORTED_T1"
    d2 = v.confirmation_decision(rows, overall_competent=15, delayed_competent=13)
    assert d2["status"] == "INCONCLUSIVE_MODEL_EXPRESSIVITY"
    with pytest.raises(Exception):
        v.confirmation_decision(rows[:19], overall_competent=19, delayed_competent=13)
