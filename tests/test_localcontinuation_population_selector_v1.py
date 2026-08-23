from __future__ import annotations

import ast
import json
import random
import tempfile
import unittest
from pathlib import Path

import localcontinuation_population_selector_v1 as s


def path(i: int) -> str:
    return f"json_2.1.1/train/pick_and_place_simple-apple-None-countertop-{i}/trial_T{i:04d}/game.tw-pddl"


class SelectorTests(unittest.TestCase):
    def test_exact_split_exposure_exclusion_and_determinism(self) -> None:
        inventory = [path(i) for i in range(100)]
        exposed = inventory[:10]
        a = s.select_population(inventory, exposed)
        b = s.select_population(list(reversed(inventory)), list(reversed(exposed)))
        self.assertEqual(s.canonical_json_bytes(a), s.canonical_json_bytes(b))
        self.assertEqual(a["selected_n"], 64)
        rows = a["selected"]
        self.assertEqual(sum(r["phase"] == "development" for r in rows), 32)
        self.assertEqual(sum(r["phase"] == "confirmation" for r in rows), 20)
        self.assertEqual(sum(r["phase"] == "reserve" for r in rows), 12)
        selected = {r["game_path"] for r in rows}
        self.assertEqual(len(selected), 64)
        self.assertFalse(selected & set(exposed))
        self.assertEqual(a["exposed_selected_overlap"], 0)

    def test_rank_rule_exact(self) -> None:
        inventory = [path(i) for i in range(70)]
        result = s.select_population(inventory, [])
        expected = sorted(inventory, key=lambda p: (s.sha256_text(s.SALT + p), p))[:64]
        self.assertEqual([r["game_path"] for r in result["selected"]], expected)

    def test_load_json_and_newline_equivalent(self) -> None:
        values = [path(i) for i in range(70)]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            jp = td / "x.json"
            lp = td / "x.txt"
            jp.write_text(json.dumps(values), encoding="utf-8")
            lp.write_text("\n".join(values) + "\n", encoding="utf-8")
            self.assertEqual(s.load_path_list(str(jp), label="inventory"), values)
            self.assertEqual(s.load_path_list(str(lp), label="inventory"), values)

    def test_duplicate_inventory_fails(self) -> None:
        values = [path(i) for i in range(70)]
        with self.assertRaisesRegex(s.SelectionError, "DUPLICATE_INVENTORY_PATH"):
            s.select_population(values + [values[0]], [])

    def test_duplicate_exposed_fails(self) -> None:
        values = [path(i) for i in range(70)]
        with self.assertRaisesRegex(s.SelectionError, "DUPLICATE_EXPOSED_PATH"):
            s.select_population(values, [values[0], values[0]])

    def test_exposed_must_belong_to_inventory(self) -> None:
        values = [path(i) for i in range(70)]
        with self.assertRaisesRegex(s.SelectionError, "EXPOSED_PATH_NOT_IN_INVENTORY"):
            s.select_population(values, [path(999)])

    def test_bad_paths_fail_closed(self) -> None:
        bad = [
            "/json_2.1.1/train/pick_and_place_simple-a/trial_T/game.tw-pddl",
            "C:/json_2.1.1/train/pick_and_place_simple-a/trial_T/game.tw-pddl",
            "json_2.1.1/train/../pick_and_place_simple-a/trial_T/game.tw-pddl",
            "json_2.1.1/valid_seen/pick_and_place_simple-a/trial_T/game.tw-pddl",
            "json_2.1.1/train/pick_two_obj_and_place-a/trial_T/game.tw-pddl",
            "json_2.1.1/train/pick_and_place_simple-a/trial_T/game.json",
            "json_2.1.1//train/pick_and_place_simple-a/trial_T/game.tw-pddl",
        ]
        for candidate in bad:
            with self.subTest(candidate=candidate):
                with self.assertRaises(s.SelectionError):
                    s.normalize_game_path(candidate)

    def test_backslashes_only_normalization(self) -> None:
        candidate = path(1)
        self.assertEqual(s.normalize_game_path(candidate.replace("/", "\\")), candidate)

    def test_insufficient_unexposed_fails(self) -> None:
        values = [path(i) for i in range(70)]
        with self.assertRaisesRegex(s.SelectionError, "INSUFFICIENT_UNEXPOSED_PATHS:63<64"):
            s.select_population(values, values[:7])

    def test_cli_refuses_existing_output_and_is_byte_stable(self) -> None:
        inventory = [path(i) for i in range(80)]
        exposed = inventory[:10]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inv = td / "inventory.json"
            exp = td / "exposed.json"
            inv.write_text(json.dumps(inventory), encoding="utf-8")
            exp.write_text(json.dumps(exposed), encoding="utf-8")
            expected = s.canonical_json_bytes(s.select_population(inventory, exposed))
            self.assertEqual(expected, s.canonical_json_bytes(s.select_population(list(reversed(inventory)), exposed)))

    def test_static_forbidden_imports_and_discovery_calls_absent(self) -> None:
        source_path = Path(s.__file__)
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_import_roots = {"alfworld", "transformers", "torch", "subprocess", "requests", "urllib", "socket"}
        imported = set()
        called_attrs = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called_attrs.add(node.func.attr)
        self.assertFalse(imported & forbidden_import_roots)
        self.assertFalse({"glob", "rglob", "iterdir", "listdir", "walk"} & called_attrs)
        self.assertNotIn("/opt/gpu-lab/data", source)


if __name__ == "__main__":
    unittest.main()
