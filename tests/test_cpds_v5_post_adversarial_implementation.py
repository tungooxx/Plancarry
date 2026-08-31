from __future__ import annotations

import copy
import hashlib
import json
import math
import unittest
from pathlib import Path

import torch

import cpds_v5_partition_v1 as part
import cpds_v5_predictive_recurrence_v1 as rt
import cpds_v5_train_calibration_v1 as tc
from tests.test_cpds_v5_predictive_recurrence_runtime import packet, v

ROOT = Path(__file__).parents[1]


class T(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(20260830)
        torch.set_num_threads(1)
        self.m = rt.CPDSV5Adapter().eval()

    def test_exact_control_surface(self):
        required = {
            "ZERO_Z0_RECURSION", "DONOR_Z0_RECURSION", "LAST_TRANSITION_ONLY",
            "BAGGED_TRANSITIONS", "STATIC_PREDICTIVE_SHARED_G",
        }
        self.assertTrue(required <= set(rt.ARMS))

    def test_exact_state_encoder_parameter_match_and_shared_g(self):
        rec = sum(p.numel() for n,p in self.m.named_parameters() if n.startswith(("W0.","Wx.","gru.")))
        sta = sum(p.numel() for n,p in self.m.named_parameters() if n.startswith("static_fc"))
        self.assertEqual(rec, 1443328)
        self.assertEqual(sta, 1443072)
        self.assertEqual(rec-sta, 256)
        names = [n for n,_ in self.m.named_parameters()]
        self.assertEqual(names[:10], [
            "W0.weight", "Wx.weight", "gru.weight_ih", "gru.weight_hh", "gru.bias_ih", "gru.bias_hh",
            "Wa.weight", "static_fc1.weight", "static_fc1.bias", "static_fc2.weight",
        ])
        self.assertEqual(sum(n.startswith("Wa.") for n in names), 1)
        self.assertFalse(any("static" in n.lower() and "wa" in n.lower() for n in names))

    def test_zero_z0_does_not_read_target_z0(self):
        xs=[v(1),v(2)]
        poisonous=torch.full((rt.STATE_WIDTH,), float("nan"))
        z=self.m.arm_state("ZERO_Z0_RECURSION", poisonous, xs)
        self.assertTrue(torch.isfinite(z).all())
        self.assertAlmostEqual(float(torch.linalg.vector_norm(z).detach()),1.0,places=5)

    def test_donor_z0_changes_only_initial_state(self):
        xs=[v(1),v(2),v(3)]
        z_target=self.m.z0(v(0)); z_donor=self.m.z0(v(7))
        poisonous=torch.full((rt.STATE_WIDTH,), float("nan"))
        got=self.m.arm_state("DONOR_Z0_RECURSION",poisonous,xs,donor_z0=z_donor)
        expected=self.m.fold(z_donor,xs)
        self.assertTrue(torch.equal(got,expected))
        self.assertFalse(torch.equal(got,self.m.fold(z_target,xs)))

    def test_last_transition_has_no_transition_to_transition_path(self):
        z0=self.m.z0(v(0)); b=v(9)
        a=self.m.last_transition_only(z0,[v(1),b])
        c=self.m.last_transition_only(z0,[v(5),b])
        self.assertTrue(torch.equal(a,c))
        self.assertTrue(torch.equal(a,self.m.step(z0,b)))

    def test_bagged_transition_state_is_exactly_permutation_invariant(self):
        z0=self.m.z0(v(0)); xs=[v(1),v(2),v(3)]
        a=self.m.bagged_transitions(z0,xs)
        b=self.m.bagged_transitions(z0,[xs[2],xs[0],xs[1]])
        self.assertTrue(torch.equal(a,b))

    def test_static_predictive_uses_pre_reset_only_and_same_g(self):
        z0=self.m.z0(v(0)); h=v(4); xs=[v(1),v(2)]
        poisonous=torch.full((rt.STATE_WIDTH,), float("nan"))
        a=self.m.arm_state("STATIC_PREDICTIVE_SHARED_G",poisonous,xs,h_pre_reset=h)
        b=self.m.arm_state("STATIC_PREDICTIVE_SHARED_G",poisonous,[v(8),v(9)],h_pre_reset=h)
        self.assertTrue(torch.equal(a,b))
        acts=torch.stack([v(10),v(11),v(12)])
        self.assertTrue(torch.equal(self.m.g_delta(a,acts), self.m.g_delta(self.m.static_state(h),acts)))

    def test_structure_only_donor_selection_is_order_stable_by_identity(self):
        rows=[
            {"source_graph_id":"g0","structural_id":"s0","phase":"CALIBRATION"},
            {"source_graph_id":"g1","structural_id":"s1","phase":"CALIBRATION"},
            {"source_graph_id":"g2","structural_id":"s2","phase":"CALIBRATION"},
        ]
        i=part.deterministic_z0_donor_index("s0","g0","CALIBRATION",rows)
        selected=rows[i]["structural_id"]
        rev=list(reversed(rows)); j=part.deterministic_z0_donor_index("s0","g0","CALIBRATION",rev)
        self.assertEqual(selected,rev[j]["structural_id"])
        self.assertNotEqual(rows[i]["source_graph_id"],"g0")
        bad=copy.deepcopy(rows); bad[1]["outcome"]="win"
        with self.assertRaisesRegex(ValueError,"OUTCOME_OR_EVALUATOR"):
            part.deterministic_z0_donor_index("s0","g0","CALIBRATION",bad)


    def test_calibration_donor_map_is_frozen_from_structure_only_and_order_stable(self):
        gs=[]
        for i in range(1000):
            g=f"cal-map-{i}"
            if part.partition_name(g)=="CALIBRATION": gs.append(g)
            if len(gs)==3: break
        ps=[packet(g,"CALIBRATION") for g in gs]
        a=tc.calibration_donor_z0_map(ps)
        b=tc.calibration_donor_z0_map(list(reversed(ps)))
        self.assertEqual(a,b)
        for target,donor in a.items():
            self.assertNotEqual(next(p["source_graph_id"] for p in ps if p["packet_id"]==target), next(p["source_graph_id"] for p in ps if p["packet_id"]==donor))

    def test_recipe_and_scientific_hash_are_exactly_bound(self):
        self.assertEqual(rt.sha256_file(tc.RECIPE_PATH),tc.REVIEWED_RECIPE_SHA256)
        d=tc.load_reviewed_contract()
        self.assertEqual(d["scientific_spec_hash"],tc.REVIEWED_SCIENTIFIC_SPEC_HASH)
        cfg=tc.load_recipe()["training"]
        self.assertEqual((cfg["seed"],cfg["epochs"],cfg["batch_sequences"]),(20260830,32,8))

    def test_packet_order_is_hash_frozen_not_input_order_or_epoch_random(self):
        p1=packet("g-a","TRAIN"); p2=packet("g-b","TRAIN")
        # packet_order_key itself is independent of list order and exactly binds graph, packet id, seed.
        expected=hashlib.sha256((p1["source_graph_id"]+p1["packet_id"]+"20260830").encode()).hexdigest()
        self.assertEqual(tc.packet_order_key(p1,20260830),expected)
        ordered1=sorted([p1,p2],key=lambda p:(tc.packet_order_key(p,20260830),p["packet_id"]))
        ordered2=sorted([p2,p1],key=lambda p:(tc.packet_order_key(p,20260830),p["packet_id"]))
        self.assertEqual([p["packet_id"] for p in ordered1],[p["packet_id"] for p in ordered2])

    def test_joint_loss_is_exact_equal_weight(self):
        p=packet("g-joint","TRAIN")
        sec=0.25
        rec=tc._branch_sequence_loss(self.m,p,sec,static=False)
        sta=tc._branch_sequence_loss(self.m,p,sec,static=True)
        joint=tc.sequence_training_loss(self.m,p,sec)
        self.assertTrue(torch.equal(joint,0.5*rec+0.5*sta))

    def test_calibration_includes_every_post_attack_null_and_never_authorizes_development(self):
        gs=[]
        for i in range(1000):
            g=f"cal-post-{i}"
            if part.partition_name(g)=="CALIBRATION": gs.append(g)
            if len(gs)==2: break
        ps=[packet(g,"CALIBRATION") for g in gs]
        out=tc.calibration_gate(self.m,ps)
        required={"STATIC_REPEAT","TRANSITION_PERMUTED","ZERO_Z0_RECURSION","DONOR_Z0_RECURSION","LAST_TRANSITION_ONLY","BAGGED_TRANSITIONS","STATIC_PREDICTIVE_SHARED_G","ALIGNED_RECURSION"}
        self.assertEqual(set(out["median_predictive_loss"]),required)
        self.assertFalse(out["v5_development_authorized"])
        self.assertEqual(out["confirmation_status"],"HARD_SEALED_NO_RUNTIME_ROUTE")
        self.assertFalse(out["checks"]["calibration_model_selection"])

    def test_reviewed_design_blobs_unchanged(self):
        expected={
            "results/design/plancarry_cpds_v5_post_adversarial_design_repair_a1_20260831.json":"936c7681b61b29956a0094b95c8d6498c5192d5b55cf73eeb643041cdd3327d2",
            "results/design/plancarry_cpds_v5_post_adversarial_semantic_diff_a1_20260831.json":"bc1d5732bf70d6868edf3ff13e85380b7e9ed2928fec14e65029f2c216ba1570",
            "results/design/plancarry_cpds_v5_post_adversarial_identity_binding_a1_20260831.json":"88e029654dc1bace5f14fb75ac348677d879f8d52586e3ef9aee8943e030f3f7",
            "tests/test_cpds_v5_post_adversarial_design_repair.py":"d4442304adedf0b3cf4b8bb94bc5ba42200991e353ed02ea23954b97c0763cb2",
        }
        for rel,h in expected.items(): self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(),h,rel)


if __name__ == "__main__": unittest.main()
