import json
import unittest

import cpds_development_driver_v1 as d


def _dm(obj: str) -> str:
    return {
        "Cabinet_bar__plus_00_dot_99": "cabinet 7",
        "Shelf_bar__minus_01_dot_20": "shelf 2",
    }[obj]


class TestCPDSSymbolicSurfaceBridgeV1(unittest.TestCase):
    def test_exact_supported_operator_translation(self):
        self.assertEqual(
            d._translate_symbolic_action(
                "GotoLocation(agent1,loc_a,loc_b,Cabinet_bar__plus_00_dot_99)", _dm
            ),
            "go to cabinet 7",
        )
        self.assertEqual(
            d._translate_symbolic_action(
                "examineReceptacle(agent1,Shelf_bar__minus_01_dot_20)", _dm
            ),
            "examine shelf 2",
        )

    def test_unknown_or_malformed_symbolic_action_fails_closed(self):
        with self.assertRaises(d.TechnicalInvalid):
            d._translate_symbolic_action("PickupObject(agent1,x)", lambda _: "x 1")
        with self.assertRaises(d.TechnicalInvalid):
            d._translate_symbolic_action("GotoLocation(agent2,a,b,c)", lambda _: "c 1")

    def test_frozen_development_33_uses_only_bridge_operators(self):
        source = json.loads(d.SOURCE_PATH.read_text(encoding="utf-8"))
        wmap = {w["source_graph_id"]: w for w in source["static_graph_replayability_witnesses"]}
        ops = set(); count = 0
        for family in source["families"]:
            witness = wmap[family["source_graph_id"]]
            commands = (
                list(family["allowed_pre_reset_history_canonical"])
                + [family["immediate_next_command_canonical"]]
                + [x["command"] for x in witness["common_prefix_steps"]]
                + list(family["branch_A_equivalence_class"])
                + list(family["branch_B_equivalence_class"])
            )
            for command in commands:
                match = d._SYMBOLIC_ACTION_RE.fullmatch(command)
                self.assertIsNotNone(match)
                ops.add(match.group(1)); count += 1
        self.assertEqual(len(source["families"]), 33)
        self.assertEqual(ops, {"GotoLocation", "examineReceptacle"})
        self.assertEqual(count, 165)


if __name__ == "__main__":
    unittest.main()
