import dataclasses
import hashlib
import json
import subprocess
import unittest

import action_matched_grounded_v2_constructibility as g

BASE = "1d27ffa6c7826b2cb9cef58342b20a2e7aa25362"
OLD = "8d9ae9a2ee108becae26b3b9e1445ecd77209475"
DESIGN = "results/design/"
POP = DESIGN + "plancarry_action_matched_grounded_v2_fresh_population_20260825.json"
INVENTORY = DESIGN + "plancarry_localcontinuation_canonical_inventory_v1_20260823.json"


def git_json(commit, path):
    return json.loads(subprocess.check_output(["git", "show", f"{commit}:{path}"]))


def extract_paths(o):
    if isinstance(o, list):
        if all(isinstance(x, str) for x in o):
            return list(o)
        return [x["game_path"] for x in o if isinstance(x, dict) and isinstance(x.get("game_path"), str)]
    if isinstance(o, dict):
        for key in ("selected", "paths", "inventory", "games", "game_paths"):
            if key in o:
                out = extract_paths(o[key])
                if out:
                    return out
    return []


class PopulationTests(unittest.TestCase):
    def test_exact_reviewed_population_reconstruction(self):
        pop = git_json(BASE, POP)
        inv = extract_paths(git_json(BASE, INVENTORY))
        source_sets = []
        for src in pop["exclusion_sources"]:
            commit = OLD if src["name"] == "actionmatched_v1_selected" else BASE
            source = git_json(commit, DESIGN + src["file"])
            paths = extract_paths(source)
            self.assertEqual(len(set(map(g.normalize_game_path, paths))), src["exact_paths"])
            source_sets.append(paths)
        union = g.build_normalized_exclusion_union(source_sets)
        self.assertEqual(len(inv), 790)
        self.assertEqual(len(union), 593)
        self.assertEqual(g.canonical_json_sha256(list(union)), "16840e99b5b04cd3f18b2ae4ccf51752b2d698f2422ebf2ed5a90aa18fe1bfe3")
        selected, spare = g.deterministic_fresh_selection(inv, union)
        manifest_selected = tuple(x["game_path"] for x in pop["paths"])
        self.assertEqual(selected, manifest_selected)
        self.assertEqual(len(selected), 160)
        self.assertEqual(len(spare), 37)
        self.assertFalse(set(selected) & set(union))
        self.assertTrue(all(g.population_rank_sha256(x["game_path"]) == x["rank_sha256"] for x in pop["paths"]))
        bits = [g.orientation_bit(p) for p in selected]
        self.assertEqual((bits.count(0), bits.count(1)), (79, 81))

    def test_contaminated_selected_rejected(self):
        with self.assertRaises(g.ConstructibilityError):
            g.assert_selected_population_clean(["a/trial_1"], ["json_2.1.1/train/a/trial_1/game.tw-pddl"])


class PairTests(unittest.TestCase):
    def kwargs(self):
        game_path = "pick_and_place_simple-test/trial_T1"
        bit = g.orientation_bit(game_path)
        a4, b4 = (("rank1", "rank2") if bit == 0 else ("rank2", "rank1"))
        return dict(
            game_path=game_path,
            pre_cut_actions=["pre1", "pre2"],
            pre_cut_actions_model_own_nontrivial=True,
            cut_admissibles=["a3-low", "a3-high"],
            cut_scores={"a3-low": -2.0, "a3-high": -1.0},
            post_action3_admissibles=["rank2", "rank3", "rank1"],
            post_action3_scores={"rank1": 0.9, "rank2": 0.7, "rank3": 0.1},
            branch_a_admissibles=["A5", "Ax"],
            branch_a_scores={"A5": 0.5, "Ax": 0.2},
            branch_b_admissibles=["B5", "Bx"],
            branch_b_scores={"B5": 0.6, "Bx": 0.1},
            cut_state_hash="cut",
            post_action3_state_hash="post3",
            branch_a_state_hash="a4state",
            branch_b_state_hash="b4state",
            common_observation3="obs3",
            branch_a_observation="obsa",
            branch_b_observation="obsb",
            executed_shared_action3="a3-high",
            branch_a_action4_executed=a4,
            branch_b_action4_executed=b4,
        )

    def test_top2_before_orientation_and_branch_local_a5(self):
        p = g.construct_grounded_pair(**self.kwargs())
        self.assertEqual((p.unordered_rank1, p.unordered_rank2), ("rank1", "rank2"))
        bit = g.orientation_bit(p.game_path)
        self.assertEqual(p.orientation_bit, bit)
        self.assertEqual((p.action4_a, p.action4_b), ("rank1", "rank2") if bit == 0 else ("rank2", "rank1"))
        self.assertEqual((p.action5_a, p.action5_b), ("A5", "B5"))
        self.assertEqual(p.shared_action3, "a3-high")
        self.assertTrue(p.science_execution_forbidden)

    def test_lexical_tie_break(self):
        k = self.kwargs()
        k["post_action3_scores"] = {"rank1": 0.7, "rank2": 0.7, "rank3": 0.1}
        p = g.construct_grounded_pair(**k)
        self.assertEqual((p.unordered_rank1, p.unordered_rank2), ("rank1", "rank2"))

    def test_score_gap_filter_rejected(self):
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**self.kwargs(), score_gap_filter=0.2)

    def test_activation_outcome_rejected(self):
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**self.kwargs(), activation_outcomes={"effect": 1.0})

    def test_pair_retry_rejected(self):
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**self.kwargs(), pair_retry_count=1)

    def test_stale_admissibles_rejected(self):
        k = self.kwargs()
        k["branch_a_scores"] = {"A5": 0.5}
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)

    def test_a5_equals_b5_rejected(self):
        k = self.kwargs()
        k["branch_b_admissibles"] = ["A5", "Bx"]
        k["branch_b_scores"] = {"A5": 0.8, "Bx": 0.1}
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)

    def test_missing_provenance_rejected(self):
        k = self.kwargs(); k["post_action3_state_hash"] = ""
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)


    def test_exactly_two_pre_cut_actions_required(self):
        k = self.kwargs(); k["pre_cut_actions"] = ["pre1"]
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)
        k = self.kwargs(); k["pre_cut_actions"] = ["pre1", "pre2", "pre3"]
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)

    def test_blank_pre_cut_action_rejected(self):
        k = self.kwargs(); k["pre_cut_actions"] = ["pre1", " "]
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)

    def test_pre_cut_model_own_attestation_required(self):
        k = self.kwargs(); k["pre_cut_actions_model_own_nontrivial"] = False
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)

    def test_executed_shared_a3_mismatch_rejected(self):
        k = self.kwargs(); k["executed_shared_action3"] = "wrong-a3"
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)

    def test_branch_a4_execution_mismatch_rejected(self):
        k = self.kwargs(); k["branch_a_action4_executed"] = "wrong-a4"
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)
        k = self.kwargs(); k["branch_b_action4_executed"] = "wrong-b4"
        with self.assertRaises(g.ConstructibilityError):
            g.construct_grounded_pair(**k)

    def test_tampered_orientation_rejected(self):
        p = g.construct_grounded_pair(**self.kwargs())
        bad = dataclasses.replace(p, orientation_bit=1-p.orientation_bit)
        with self.assertRaises(g.ConstructibilityError):
            g.validate_grounded_pair(bad)

    def test_tampered_top2_rejected(self):
        p = g.construct_grounded_pair(**self.kwargs())
        bad = dataclasses.replace(p, unordered_rank1="rank3")
        with self.assertRaises(g.ConstructibilityError):
            g.validate_grounded_pair(bad)


class FailClosedScopeTests(unittest.TestCase):
    def test_science_guard(self):
        self.assertTrue(g.SCIENCE_EXECUTION_FORBIDDEN)
        self.assertGreaterEqual(len(g.UNRESOLVED_SCIENCE_AUTHORITY), 7)
        with self.assertRaisesRegex(RuntimeError, "SCIENCE_EXECUTION_FORBIDDEN"):
            g.refuse_science_execution()

    def test_control_concepts_are_placeholders_not_formulas(self):
        self.assertEqual(g.CONTROL_CONCEPTS, ("NEXT_DIVERGENT_ACTION_ONLY", "FUTURE_ACTION_SEQUENCE_ONLY"))
        self.assertEqual(g.CONTROL_CONCEPT_ALIASES["IMMEDIATE_ACTION_IDENTITY_ONLY"], "NEXT_DIVERGENT_ACTION_ONLY")
        self.assertEqual(g.CONTROL_CONCEPT_ALIASES["FUTURE_ACTION_SEQUENCE_ONLY"], "FUTURE_ACTION_SEQUENCE_ONLY")
        self.assertFalse(hasattr(g, "run_science"))
        self.assertFalse(hasattr(g, "execute_experiment"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
