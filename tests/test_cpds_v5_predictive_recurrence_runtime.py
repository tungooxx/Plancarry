from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import torch

import cpds_v5_predictive_recurrence_v1 as rt
import cpds_v5_train_calibration_v1 as tc
from cpds_v5_partition_v1 import partition_name, validate_blind_reserved_overlap, validate_source_graph_disjoint


def v(i, n=2048):
    x=torch.zeros(n); x[i % n]=1.0; return x


def site(target=0):
    acts=torch.stack([v(10),v(11),v(12)])
    return {"base_scores":[0.0,0.0,0.0],"action_features":[x.tolist() for x in acts],"target_index":target}


def packet(graph,part):
    return {"schema":tc.PACKET_SCHEMA,"base_model_id":rt.BASE_MODEL_ID,"base_model_revision":rt.BASE_MODEL_REVISION,"source_graph_id":graph,"packet_id":"packet-"+graph,"partition":part,"structural_key_sha256":hashlib.sha256(graph.encode()).hexdigest(),"pre_reset_hidden":v(0).tolist(),"updates":[{"transition_hidden":v(1).tolist(),"prediction_site":site(0),"next_transition_hidden":v(2).tolist(),"negative_transition_hidden":v(3).tolist()},{"transition_hidden":v(2).tolist(),"prediction_site":site(1),"next_transition_hidden":v(4).tolist(),"negative_transition_hidden":v(5).tolist()}],"final_prediction_site":site(1)}


class T(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(20260830); torch.set_num_threads(1)
        self.m=rt.CPDSV5Adapter().eval()

    def test_identity_and_gain(self):
        self.assertEqual(rt.STATE_WIDTH,256); self.assertEqual(rt.G_GAIN,1.0)
        self.assertEqual(rt.BASE_MODEL_REVISION,"70d244cc86ccca08cf5af4e1e306ecf908b1ad5e")

    def test_order_sensitive_and_deterministic(self):
        z0=self.m.z0(v(0)); xs=[v(1),v(2),v(3)]
        a=self.m.fold(z0,xs); b=self.m.fold(z0,[xs[1],xs[2],xs[0]])
        self.assertFalse(torch.equal(a,b)); self.assertGreater(float(torch.max(torch.abs(a-b)).detach()),1e-7)
        self.assertTrue(torch.equal(a,self.m.fold(z0,xs)))

    def test_static_scratch_cannot_change_exposed_state(self):
        z0=self.m.z0(v(0)); xs=[v(1),v(2)]
        z=self.m.arm_state("STATIC_REPEAT",z0,xs)
        self.assertTrue(torch.equal(z,z0))

    def test_permuted_same_multiset_only_order(self):
        z0=self.m.z0(v(0)); xs=[v(1),v(2),v(3)]
        pi=rt.deterministic_nonidentity_permutation("g",3)
        self.assertEqual(sorted(pi),[0,1,2]); self.assertNotEqual(pi,(0,1,2))
        z=self.m.arm_state("TRANSITION_PERMUTED",z0,xs,permuted_order=pi)
        self.assertEqual(tuple(z.shape),(256,))

    def test_g_bounded_and_nonexecuting(self):
        z=self.m.z0(v(0)); acts=torch.stack([v(10),v(11),v(12)])
        d=self.m.g_delta(z,acts)
        self.assertTrue(torch.all(d>=-1.000001)); self.assertTrue(torch.all(d<=1.000001))

    def test_partition_disjoint(self):
        train=[]; cal=[]
        i=0
        while not train or not cal:
            g=f"graph-{i}"; (train if partition_name(g)=="TRAIN" else cal).append(g); i+=1
        validate_source_graph_disjoint(train,cal)

    def test_blind_reserved_overlap_rejects_without_identity(self):
        h=hashlib.sha256(b"x").hexdigest()
        with self.assertRaisesRegex(ValueError,"OVERLAP_COUNT:1") as cm:
            validate_blind_reserved_overlap([h],[h])
        self.assertNotIn(h,str(cm.exception))

    def test_checkpoint_is_byte_deterministic(self):
        recipe_sha=hashlib.sha256(b"recipe").hexdigest()
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a.ckpt"; b=Path(td)/"b.ckpt"
            ha=rt.save_deterministic_checkpoint(a,self.m,recipe_sha256=recipe_sha,provenance={"x":1})
            hb=rt.save_deterministic_checkpoint(b,self.m,recipe_sha256=recipe_sha,provenance={"x":1})
            self.assertEqual(a.read_bytes(),b.read_bytes()); self.assertEqual(ha["sha256"],hb["sha256"])
            m2=rt.CPDSV5Adapter(); rt.load_deterministic_checkpoint(a,m2,expected_sha256=ha["sha256"])
            for k,vv in self.m.state_dict().items(): self.assertTrue(torch.equal(vv,m2.state_dict()[k]))

    def test_calibration_is_predictive_only_and_sealed(self):
        # We only validate schema/guards here; random untrained weights may pass or fail the predictive inequalities.
        g=None
        for i in range(100):
            cand=f"cal-{i}"
            if partition_name(cand)=="CALIBRATION": g=cand; break
        g2=None
        for i in range(101,300):
            cand=f"cal-{i}"
            if partition_name(cand)=="CALIBRATION" and cand != g: g2=cand; break
        p=packet(g,"CALIBRATION"); p2=packet(g2,"CALIBRATION")
        out=tc.calibration_gate(self.m,[p,p2])
        self.assertIn(out["status"],(tc.CALIBRATION_PASS,tc.CALIBRATION_FAIL))
        self.assertFalse(out["v5_development_authorized"])
        self.assertEqual(out["confirmation_status"],"HARD_SEALED_NO_RUNTIME_ROUTE")
        src=Path(tc.__file__).read_text()
        self.assertNotIn("v4_endpoint_from_sealed_scores",src)
        self.assertNotIn("cpds_development_runtime_v1",src)
        bad=json.loads(json.dumps(p)); bad["updates"][0]["prediction_site"]["branch_A"]=["secret"]
        with tempfile.TemporaryDirectory() as td:
            q=Path(td)/"bad.json"; q.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"EVALUATOR_OR_OUTCOME_FIELD_FORBIDDEN"):
                tc._packet(q)



    def test_scorer_surface_preserves_v4_leading_space_and_exact_revision(self):
        src=Path(rt.__file__).read_text()
        self.assertIn('suffix = " " + action',src)
        self.assertIn('revision=BASE_MODEL_REVISION',src)
        self.assertIn('local_files_only=True',src)
        self.assertIn('model.requires_grad_(False)',src)

    def test_tiny_training_is_seed_deterministic(self):
        g=None
        for i in range(100):
            cand=f"train-{i}"
            if partition_name(cand)=="TRAIN": g=cand; break
        p=packet(g,"TRAIN")
        r=json.loads(json.dumps(tc.load_recipe()))
        r["training"]["epochs"]=1; r["training"]["batch_sequences"]=1
        m1,_=tc.train_model([p],r); m2,_=tc.train_model([p],r)
        for k,x in m1.state_dict().items():
            self.assertTrue(torch.equal(x,m2.state_dict()[k]),k)

    def test_recipe_forbids_posthoc_selection(self):
        r=tc.load_recipe(); cfg=r["training"]
        self.assertEqual(cfg["seed"],20260830); self.assertEqual(cfg["epochs"],32)
        self.assertEqual(cfg["early_stopping"],"NONE"); self.assertEqual(cfg["checkpoint_selection"],"FINAL_EPOCH_ONLY")
        self.assertFalse(cfg["calibration_model_selection"]); self.assertEqual(r["adapter"]["G_gain"],1.0)

if __name__=='__main__': unittest.main()
