"""A3 zero-model static provenance regression for exact historical GDAA manifests.

Tests use checked-in metadata only, never actual source execution or G1 certification.
Run: python -m unittest tests.test_bind_v02_manifest_consistency_a3 -v
"""
import copy
import json
import unittest
from pathlib import Path

from research.bind_v02_manifest_consistency_a3 import audit

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "gdaa_train_candidate_manifest_v1.json",
    "gdaa_train_candidate_manifest_disjoint_v1.json",
    "gdaa_train_candidate_manifest_fresh_v2.json",
    "latent_ab_pilot_manifest_v2.json",
]


def fixture():
    return [
        json.loads((ROOT / "results" / "design" / name).read_text(encoding="utf-8"))
        for name in FILES
    ]


class HistoricalManifestConsistency(unittest.TestCase):
    def test_pinned_manifest_metadata_yields_conflicting_overlap(self):
        v1, dis, fre, pil = fixture()
        result = audit(v1, dis, fre, pil)
        self.assertEqual(result["verdict"], "UNRESOLVED_PROVENANCE_CONFLICT")
        self.assertEqual(result["scientific_gate"], "NOT_AUTHORIZED")
        self.assertEqual(result["v1_disjoint_intersection"], 71)
        self.assertEqual(result["v1_missing_from_disjoint"], 19)
        self.assertEqual(result["gdaa_union"], 199)
        self.assertEqual(result["four_manifest_union"], 239)
        self.assertEqual(result["binding_gdaa_overlap_inferred_if_metadata_true"], 19)
        self.assertEqual(result["binding_gdaa_overlap_implied_by_pilot_counts"], 47)
        self.assertEqual(result["overlap_discrepancy"], 28)

    def test_hypothetically_fixed_count_still_does_not_authorize(self):
        docs = fixture()
        docs[3]["excluded_union_count"] = 360
        result = audit(*docs)
        self.assertEqual(result["verdict"], "SOURCE_FRESHNESS_UNATTESTED")
        self.assertEqual(result["scientific_gate"], "NOT_AUTHORIZED")

    def test_disjoint_order_must_match_stated_selection(self):
        docs = fixture()
        docs[1]["candidates"] = list(reversed(docs[1]["candidates"]))
        result = audit(*docs)
        self.assertEqual(result["verdict"], "INVALID_AUDIT_INPUT")
        self.assertEqual(result["scientific_gate"], "NOT_AUTHORIZED")

    def test_changed_fresh_binding_exclusion_is_invalid(self):
        docs = fixture()
        docs[2]["ordering"] = docs[2]["ordering"].replace(
            "d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee",
            "0" * 64
        )
        result = audit(*docs)
        self.assertEqual(result["verdict"], "INVALID_AUDIT_INPUT")
        self.assertEqual(result["scientific_gate"], "NOT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
