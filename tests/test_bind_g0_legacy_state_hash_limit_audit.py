"""Read-only, synthetic controls for legacy ALFWorld state-hash insufficiency."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from bind_g0_legacy_state_hash_limit_audit import audit_source, load_original_functions

SYNTHETIC_SOURCE = '''
from typing import Any
def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
def _facts(info: dict[str, Any]) -> list[str]:
    facts=info.get("facts")
    if facts is None: return []
    if isinstance(facts,(list,tuple)) and len(facts)==1 and isinstance(facts[0],(list,tuple,set)):
        facts=facts[0]
    return sorted(str(x) for x in facts)
def _commands(info: dict[str, Any]) -> list[str]:
    x=info.get("admissible_commands",[])
    if isinstance(x,(list,tuple)) and len(x)==1 and isinstance(x[0],(list,tuple)):
        x=x[0]
    return list(x)
def state_hash(game_file: str, observation: str, info: dict[str,Any], score: float, done: bool) -> str:
    payload={
        "game_file":str(Path(game_file).absolute()),
        "observation":observation,
        "admissible_commands":sorted(_commands(info)),
        "facts":_facts(info),
        "score":float(score),
        "done":bool(done),
    }
    return hashlib.sha256(stable_json(payload).encode()).hexdigest()
class AlfRuntime:
    def hash(self): pass
    def step(self, command): pass
    def close(self): pass
'''


class LegacyProxyTests(unittest.TestCase):
    def test_all_synthetic_hash_probes_are_explicit(self):
        result = audit_source(SYNTHETIC_SOURCE)
        probe = result["synthetic_probe"]
        self.assertTrue(probe["action_menu_order_changed"])
        self.assertTrue(probe["hash_unchanged_when_action_order_reversed"])
        self.assertTrue(probe["hash_unchanged_when_omitted_rng_field_changed"])
        self.assertTrue(probe["hash_unchanged_when_omitted_private_field_changed"])

    def test_no_implicit_pass(self):
        result = audit_source(SYNTHETIC_SOURCE)
        self.assertEqual("NOT_AUTHORIZED", result["scientific_gate"])
        self.assertTrue(result["verdict"].startswith("BLOCKED_"))

    def test_no_full_snapshot_api_in_source(self):
        result = audit_source(SYNTHETIC_SOURCE)
        self.assertFalse(result["full_state_named_method_present"])

    def test_action_order_sort_expression_detected(self):
        result = audit_source(SYNTHETIC_SOURCE)
        self.assertTrue(result["state_hash_sorts_action_menu_in_source"])

    def test_unmodified_original_hash_code_reused(self):
        f, methods, snippet = load_original_functions(SYNTHETIC_SOURCE)
        self.assertIn("hash", methods)
        self.assertIn("sorted(_commands(info))", snippet)
        self.assertEqual(
            f["state_hash"]("/tmp/demo", "room",
                            {"facts": ["f1"], "admissible_commands": ["a", "b"]},
                            0, False),
            f["state_hash"]("/tmp/demo", "room",
                            {"facts": ["f1"], "admissible_commands": ["b", "a"]},
                            0, False),
        )

    def test_missing_runtime_function_fails_closed(self):
        with self.assertRaises(ValueError):
            audit_source(SYNTHETIC_SOURCE.replace("def state_hash(", "def missing_hash("))

    def test_missing_runtime_class_fails_closed(self):
        with self.assertRaises(ValueError):
            audit_source(SYNTHETIC_SOURCE.replace("class AlfRuntime:", "class MissingRuntime:"))

    def test_empty_source_fails_closed(self):
        with self.assertRaises(ValueError):
            audit_source("")


if __name__ == "__main__":
    unittest.main()
