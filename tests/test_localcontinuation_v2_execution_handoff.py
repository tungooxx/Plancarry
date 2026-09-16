from __future__ import annotations

import ast
import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import localcontinuation_controls_v2 as controls
import localcontinuation_packet_builder_v2 as pb
import localcontinuation_phase_runner_v2 as phase
import localcontinuation_science_driver_v2 as driver

ROOT = Path(__file__).resolve().parents[1]


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        return list(str(text).encode("utf-8"))

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        assert add_special_tokens is False and return_offsets_mapping is True
        value = str(text)
        return {"input_ids": list(value.encode("utf-8")), "offset_mapping": [(i, i + 1) for i in range(len(value))]}


def synthetic_packet(row, tokenizer, label):
    packet = pb._base(row, {"synthetic": True}, "development")
    packet["task_instruction"] = "synthetic task"
    packet["initial_observation"] = "synthetic room"
    packet["plan_text"] = f"<PLAN>abc{label}</PLAN>"
    packet["actions"] = []
    for step in range(1, 6):
        command = f"move object{step}"
        packet["actions"].append(
            {
                "step": step,
                "command": command,
                "observation": f"obs{step}",
                "admissible_commands": [command, "look"],
                "accepted": True,
                "was_admissible": True,
                "error": None,
            }
        )
    packet["stage1_runtime_errors"] = []
    opening, closing = controls.frozen_tag_ids(tokenizer)
    ok, reasons, guard = pb.local_stage1_eligibility_v2(tokenizer, packet["plan_text"], packet["actions"], [], opening, closing)
    assert ok, reasons
    packet["trajectory_eligible"] = True
    packet["qualification_stage1_reasons"] = []
    packet["v2_control_constructibility_provenance"] = guard
    packet["qualified"] = True
    packet["qualification_stage2_reasons"] = []
    return packet


class TestLocalContinuationV2ExecutionHandoff(unittest.TestCase):
    def test_arm_and_grid_authority_match_v2(self):
        self.assertEqual(phase.SPEC, tuple(controls.SPECIFICITY_MAX_CONTROLS))
        self.assertEqual(phase.ACTIVE, "ACTIVE_PLAN_RESIDUAL")
        self.assertEqual(phase.NO_PATCH, "NO_PATCH")
        self.assertEqual(phase.LAYERS, (7, 14, 21, 27))
        self.assertEqual(phase.ALPHAS, (0.25, 0.5, 1.0))
        self.assertNotIn("SHUFFLED_PLAN", phase.SPEC)
        self.assertNotIn("GENERIC_HISTORY", phase.SPEC)
        self.assertIn("PLAN_BLOCK_DERANGED", phase.SPEC)
        self.assertIn("PAST_ACTIONS_ONLY", phase.SPEC)

    def test_cli_is_development_only(self):
        parser = driver.build_arg_parser()
        action = next(a for a in parser._actions if a.dest == "phase")
        self.assertEqual(tuple(action.choices), ("preflight", "development"))
        self.assertFalse(hasattr(phase, "CONF"))
        self.assertFalse(hasattr(phase, "RESERVE"))
        self.assertTrue(all("confirmation" not in str(path).lower() and "reserve" not in str(path).lower() for path in driver.OUTPUT_PATHS))

    def test_safe_v1_reuse_does_not_call_v1_orchestration(self):
        tree = ast.parse((ROOT / "localcontinuation_science_driver_v2.py").read_text())
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "runtime_v1":
                called.add(node.func.attr)
        self.assertTrue(called.issubset(set(driver._SAFE_V1_REUSE)), called)
        self.assertTrue(called.isdisjoint(set(driver._FORBIDDEN_V1_ORCHESTRATION)), called)

    def test_source_replay_uses_stored_v2_ids_and_exact128_geometry(self):
        tokenizer = FakeTokenizer()
        rows = pb.load_population_phase("development", ROOT)
        source = synthetic_packet(rows[0], tokenizer, 0)
        donor = synthetic_packet(rows[1], tokenizer, 1)
        source["control_provenance"] = {"unrelated_donor_frozen_index": 1}
        ids, meta = driver.source_replay_ids_v2(tokenizer, source, donor)
        self.assertEqual(set(ids), set(controls.SCIENCE_CONDITIONS))
        self.assertEqual(meta["stage2_semantic_tokenizer_calls"], 0)
        replay_rows = list(meta["replay"].values())
        self.assertTrue(all(row["slot_token_count"] == 128 for row in replay_rows))
        geometry = {
            (row["slot_start_index"], row["slot_end_index_exclusive"], row["suffix_start_index"], row["full_token_count"])
            for row in replay_rows
        }
        self.assertEqual(len(geometry), 1)
        self.assertEqual(meta["semantic"]["semantic_materialization"], "STORED_STAGE1_IDS_ONLY_NO_SEMANTIC_DECODE_RETOKENIZE")

    def test_preflight_cannot_load_model_or_open_environment(self):
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        driver_sha = driver.sha_file(ROOT / "localcontinuation_science_driver_v2.py")
        phase_sha = driver.sha_file(ROOT / "localcontinuation_phase_runner_v2.py")
        fake_tokenizer = FakeTokenizer()
        fake_report = {
            "model_id": driver.MODEL_ID,
            "revision": driver.MODEL_REVISION,
            "transformers_version": driver.TRANSFORMERS_VERSION,
            "tokenizers_version": driver.TOKENIZERS_VERSION,
            "neutral_filler_primitive_ids": list(controls.NEUTRAL_FILLER_PRIMITIVE_IDS),
            "neutral_filler_stream_sha256": controls.NEUTRAL_FILLER_IDS_SHA256,
            "past_action_separator_ids": list(controls.PAST_ACTION_SEPARATOR_IDS),
            "opening_tag_ids_sha256": "0" * 64,
            "closing_tag_ids_sha256": "1" * 64,
            "model_forward_calls": 0,
            "model_loaded": False,
        }
        with mock.patch.object(driver, "verify_tokenizer_only", return_value=(fake_tokenizer, fake_report)), \
             mock.patch.object(driver.runtime_v1, "load_runtime", side_effect=AssertionError("MODEL_LOAD_FORBIDDEN")) as load_model, \
             mock.patch.object(driver.runtime_v1, "runtime_factory", side_effect=AssertionError("ALFWORLD_FORBIDDEN")) as runtime_factory:
            stream = io.StringIO()
            with redirect_stdout(stream):
                rc = driver.main(
                    [
                        "--phase", "preflight",
                        "--expected-git-commit", head,
                        "--expected-driver-sha256", driver_sha,
                        "--expected-phase-sha256", phase_sha,
                    ]
                )
            self.assertEqual(rc, 0)
            load_model.assert_not_called()
            runtime_factory.assert_not_called()
            payload = json.loads(stream.getvalue().strip())["LOCALCONTINUATION_V2_PREFLIGHT"]
            self.assertEqual(payload["development_indices"], list(range(32)))
            self.assertEqual(payload["model_calls"], 0)
            self.assertEqual(payload["environment_execution"], 0)
            self.assertFalse(payload["confirmation_accessed"])
            self.assertFalse(payload["reserve_accessed"])
            self.assertFalse(payload["valid_seen_accessed"])
            self.assertFalse(payload["valid_unseen_accessed"])

    def test_v2_phase_split_flags_fail_closed(self):
        payload = {
            "phase": "LOCALCONTINUATION_DEVELOPMENT_V2",
            "families": [{"index": i, "qualified": False} for i in range(32)],
            "grid_results": {},
            "execution_provenance": {"synthetic": True},
            "confirmation_accessed": True,
            "reserve_accessed": False,
            "valid_seen_accessed": False,
            "valid_unseen_accessed": False,
            **phase.binding_payload(),
        }
        payload["execution_provenance_sha256"] = phase.sha_json(payload["execution_provenance"])
        with self.assertRaisesRegex(phase.LocalContinuationContractError, "split isolation"):
            phase.select_development(payload)

    def test_v2_selector_preserves_frozen_threshold_and_tiebreak(self):
        hex_a = "a" * 64
        hex_b = "b" * 64
        hex_c = "c" * 64
        grids = {}
        for layer in phase.LAYERS:
            for alpha in phase.ALPHAS:
                rows = {}
                for idx in range(32):
                    arms = {}
                    for arm in phase.ALL_DEVELOPMENT_ARMS:
                        is_no_patch = arm == phase.NO_PATCH
                        arms[arm] = {
                            "arm_name": arm,
                            "selected_layer": layer,
                            "selected_alpha": alpha,
                            "active_residual_sha256": hex_a,
                            "injected_vector_sha256": None if is_no_patch else hex_b,
                            "reset_snapshot_sha256": hex_c,
                            "reset_prefix_sha256": hex_b,
                            "hook_count": 0 if is_no_patch else 1,
                            "session_id_hash": hex_a,
                            "msa2": 0.5 if is_no_patch else (1.0 if arm == phase.ACTIVE else 0.0),
                            "reference_action_margin_family": 0.25,
                        }
                    rows[str(idx)] = {
                        "arms": arms,
                        "active_raw_residual_l2": 1.0,
                        "active_residual_sha256": hex_a,
                        "reset_snapshot_sha256": hex_c,
                    }
                grids[phase.grid_key(layer, alpha)] = rows
        payload = {
            "phase": "LOCALCONTINUATION_DEVELOPMENT_V2",
            "families": [{"index": i, "qualified": True} for i in range(32)],
            "grid_results": grids,
            "execution_provenance": {"synthetic": True},
            "confirmation_accessed": False,
            "reserve_accessed": False,
            "valid_seen_accessed": False,
            "valid_unseen_accessed": False,
            **phase.binding_payload(),
        }
        payload["execution_provenance_sha256"] = phase.sha_json(payload["execution_provenance"])
        result = phase.select_development(payload)
        self.assertEqual(result["status"], "FROZEN_LOCALCONTINUATION_V2_DEVELOPMENT_SELECTION")
        self.assertEqual((result["selected_layer"], result["selected_alpha"]), (7, 0.25))
        self.assertEqual(result["qualified_count"], 32)
        self.assertFalse(result["confirmation_accessed"])
        self.assertFalse(result["reserve_accessed"])

    def test_no_consumed_v1_population_path_in_v2_driver(self):
        text = (ROOT / "localcontinuation_science_driver_v2.py").read_text()
        self.assertNotIn("plancarry_replayresidual_localcontinuation_dev_packets_v1", text)
        self.assertNotIn("plancarry_replayresidual_localcontinuation_confirmation_packets_v1", text)
        self.assertIn("plancarry_localcontinuation_v2_development_packets", text)

    def test_v2_phase_below_gate_never_accepts_grid(self):
        payload = {
            "phase": "LOCALCONTINUATION_DEVELOPMENT_V2",
            "families": [{"index": i, "qualified": i < 15} for i in range(32)],
            "grid_results": {"unexpected": {}},
            "execution_provenance": {"synthetic": True},
            "confirmation_accessed": False,
            "reserve_accessed": False,
            "valid_seen_accessed": False,
            "valid_unseen_accessed": False,
            **phase.binding_payload(),
        }
        payload["execution_provenance_sha256"] = phase.sha_json(payload["execution_provenance"])
        with self.assertRaisesRegex(phase.LocalContinuationContractError, "grid forbidden"):
            phase.select_development(payload)


if __name__ == "__main__":
    unittest.main()
