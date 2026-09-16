import json
from types import SimpleNamespace

import gdaa_evaluator as ge
import alfworld_gdaa_v4_runner as r


class FakeRT:
    def __init__(self):
        self.won = False
        self.done = False
        self.score = 0.0
        self.admissible_commands = ["go to shelf 1"]
        self.observation = "obs"
        self.closed = False
    def hash(self): return "reset-hash"
    def close(self): self.closed = True
    def step(self, command):
        raise AssertionError("step should not be called in invalid-turn tests")


def no_tool_msg(content="text"):
    return SimpleNamespace(tool_calls=[], content=content)


def invalid_index_msg(index=99):
    tc = SimpleNamespace(id="tc", function=SimpleNamespace(arguments=json.dumps({"index": index})))
    return SimpleNamespace(tool_calls=[tc], content=None)


def setup_common(monkeypatch, messages):
    rt = FakeRT()
    monkeypatch.setattr(r.ar, "replay", lambda *a, **k: rt)
    monkeypatch.setattr(r.aq, "assistant_dict", lambda msg: {"role":"assistant","content":msg.content,"tool_calls":[]})
    monkeypatch.setattr(r.aq, "surface", lambda text, commands: str(text))
    return rt


def test_v4_constants_and_fresh_isolation():
    assert r.EXPERIMENT_ID == "44f469b8-a9a7-4b07-b2dc-c204e8a2793b"
    assert r.EXPECTED_MANIFEST_SHA256 == "62d700e5d407e71ae1db030cb454e1b78a1c4bd505f24997024de4ecb71f008d"
    iso = r.validate_candidate_isolation()
    assert iso["train_population_count"] == 790
    assert iso["binding_candidate_count"] == 180
    assert iso["prior_v3_candidate_count"] == 90
    assert iso["fresh_source_pool_count"] == 520
    assert iso["gdaa_candidate_count"] == 90
    assert iso["cross_binding_overlap_count"] == 0
    assert iso["cross_v3_manifest_overlap_count"] == 0


def test_no_tool_calls_are_behavioral_and_cap_terminates_arm(monkeypatch):
    setup_common(monkeypatch, [])
    monkeypatch.setattr(r.aq, "call", lambda *a, **k: (no_tool_msg(), {"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}))
    out = r.continue_arm_env_budget(None, r.MODEL, "game", [], [], 8)
    assert out["invalid_model_turns"] == 9
    assert out["invalid_turn_subtype_counts"] == {"NO_TOOL_CALL": 9, "INVALID_INDEX": 0}
    assert out["termination_reason"] == "MODEL_INVALID_TURN_CAP_REACHED"
    assert out["technical_failure"] is None
    assert out["success"] is False
    assert out["actions"] == []


def test_invalid_indices_are_behavioral_and_cap_terminates_arm(monkeypatch):
    setup_common(monkeypatch, [])
    monkeypatch.setattr(r.aq, "call", lambda *a, **k: (invalid_index_msg(), {"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}))
    out = r.continue_arm_env_budget(None, r.MODEL, "game", [], [], 8)
    assert out["invalid_model_turns"] == 9
    assert out["invalid_turn_subtype_counts"] == {"NO_TOOL_CALL": 0, "INVALID_INDEX": 9}
    assert out["termination_reason"] == "MODEL_INVALID_TURN_CAP_REACHED"
    assert out["technical_failure"] is None


def test_model_call_exception_is_true_technical_failure(monkeypatch):
    setup_common(monkeypatch, [])
    def boom(*a, **k): raise RuntimeError("api down")
    monkeypatch.setattr(r.aq, "call", boom)
    out = r.continue_arm_env_budget(None, r.MODEL, "game", [], [], 8)
    assert out["termination_reason"] == "technical_guard_failure"
    assert out["technical_failure"].startswith("MODEL_CALL_EXCEPTION:RuntimeError:")
    assert out["invalid_model_turns"] == 0


def test_defined_reset_with_no_valid_progress_scores_false_not_undefined():
    task = "Your task is to: put some book on shelf.\n"
    assert ge.gdaa_score(task, ["go to shelf 1"], []) is False
