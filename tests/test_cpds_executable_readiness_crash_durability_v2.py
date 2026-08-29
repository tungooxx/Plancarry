import copy
import hashlib
import inspect
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cpds_executable_readiness_v1 as m
import cpds_graphfork_constructibility_v1 as gf


def family(tag):
    return {
        "source_graph_id":"graph-"+tag,"goal_canonical":"goal-"+tag,
        "reset_observation_canonical":"reset-"+tag,"allowed_pre_reset_history_canonical":["look-"+tag],
        "immediate_next_command_canonical":"open-"+tag,
        "common_prefix_transition_keys":[tag+"-t1",tag+"-t2",tag+"-t3"],
        "branch_A_equivalence_class":[tag+"-A"],"branch_B_equivalence_class":[tag+"-B"],
        "divergence_depth_after_immediate":2,"local_source_competence_preoutcome":True,
    }


def split(prefix, namespace):
    fs=[family(f"{prefix}{i:02d}") for i in range(33)]
    snap=gf.seal_source_snapshot(prefix+"-source",fs); ss=snap["snapshot_sha256"]
    man=gf.build_generator_run_manifest(snap,namespace,ss)
    return snap,ss,man,man["manifest_sha256"]


def word_factory(base):
    def factory(fid):
        # Force one rejection for a stable subset, then an accepted exact-u16 word.
        accepted=(int(fid[:12],16)+base)%720
        if int(fid[-2:],16)%5==0:
            return iter([65535,accepted])
        return iter([accepted])
    return factory


class TestCPDSCrashDurabilityV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev=split("durdev",m.DEVELOPMENT_NAMESPACE)
        cls.conf=split("durconf",m.CONFIRMATION_NAMESPACE)
        cls.code_sha=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()

    def args(self, td, devf=None, conff=None, nonce=b"N"*32):
        ds,dss,dm,dms=self.dev; cs,css,cm,cms=self.conf
        return dict(
            transaction_path=Path(td)/"assignment.tx.json", bundle_path=Path(td)/"bundle.json",
            development_snapshot=ds, development_source_sha256=dss,
            development_generator_manifest=dm, development_generator_manifest_sha256=dms,
            confirmation_snapshot=cs, confirmation_source_sha256=css,
            confirmation_generator_manifest=cm, confirmation_generator_manifest_sha256=cms,
            development_test_word_source_factory=devf or word_factory(3),
            confirmation_test_word_source_factory=conff or word_factory(7),
            development_arm_outcomes_opened=False, test_transaction_nonce=nonce,
            generator_code_sha256=self.code_sha,
        )

    def binding(self):
        return m._durable_binding(self.dev[1],self.dev[3],self.conf[1],self.conf[3],self.code_sha)

    def test_01_contract_and_audit_freeze_literal_v3_rng(self):
        self.assertTrue(m.validate_contract())
        c=json.loads(m.CONTRACT_PATH.read_text()); a=json.loads(m.AUDIT_PATH.read_text())
        self.assertEqual(c["v3_assignment"]["rng"],"OS_CSPRNG_16BIT_WORDS_DURABLY_JOURNALED_BEFORE_THRESHOLD_OR_ACCEPTANCE_USE")
        self.assertFalse(c["crash_durability"]["hmac_or_prf_assignment_expansion"])
        self.assertTrue(all(a["checks"].values())); self.assertTrue(all(v==0 for v in a["prohibited_actions_observed"].values()))

    def test_02_production_freeze_has_no_rng_seed_word_injection(self):
        sig=inspect.signature(m.freeze_two_split_bundle_durable)
        forbidden={"word_source_factory","test_transaction_nonce","master_entropy","seed","rng","_test_only_master_entropy","generator_code_sha256"}
        self.assertFalse(forbidden & set(sig.parameters))
        self.assertIn("test_only",m.freeze_two_split_bundle_durable_test_only.__name__)
        self.assertFalse(hasattr(m,"DURABLE_DERIVATION_ID"))

    def test_03_transaction_is_create_once_canonical_and_corruption_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"tx.json"; b=self.binding()
            t1=m.ensure_durable_transaction_test_only(p,b,b"A"*32)
            t2=m.ensure_durable_transaction_test_only(p,b,b"B"*32)
            self.assertEqual(t1,t2); self.assertEqual(t2["transaction_nonce_hex"],(b"A"*32).hex())
            raw=p.read_bytes(); self.assertEqual(raw,m._canonical_bytes(t1))
            p.write_bytes(raw[:19])
            with self.assertRaisesRegex(ValueError,"CORRUPT"):
                m.ensure_durable_transaction_test_only(p,b,b"C"*32)
            self.assertEqual(p.read_bytes(),raw[:19])

    def test_04_raw_word_is_journaled_before_use_and_restart_reuses_winner(self):
        with tempfile.TemporaryDirectory() as td:
            txp=Path(td)/"tx.json"; tx=m.ensure_durable_transaction_test_only(txp,self.binding(),b"D"*32)
            fid=self.dev[2]["family_ids"][0]
            g=m.durable_u16_words_test_only(txp,tx,m.DEVELOPMENT_NAMESPACE,fid,iter([65535,17]))
            self.assertEqual(next(g),65535); self.assertEqual(next(g),17)
            # Fresh conflicting supplier cannot replace already journaled words.
            g2=m.durable_u16_words_test_only(txp,tx,m.DEVELOPMENT_NAMESPACE,fid,iter([111,222]))
            self.assertEqual(next(g2),65535); self.assertEqual(next(g2),17)
            paths=[m._draw_path(txp,tx,m.DEVELOPMENT_NAMESPACE,fid,i) for i in (0,1)]
            self.assertTrue(all(p.exists() for p in paths))
            self.assertEqual(json.loads(paths[0].read_text())["rng_source"],"OS_CSPRNG_16BIT_WORDS")

    def test_05_old_crash_restart_redraw_attack_now_reproduces_identical_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            kw=self.args(td,word_factory(11),word_factory(17),b"E"*32)
            b1,h1,t1=m.freeze_two_split_bundle_durable_test_only(**kw)
            # Simulate final directory-entry loss after all accepted raw draws were durable.
            Path(kw["bundle_path"]).unlink()
            kw2=self.args(td,word_factory(211),word_factory(317),b"Z"*32)
            b2,h2,t2=m.freeze_two_split_bundle_durable_test_only(**kw2)
            self.assertEqual(t1,t2); self.assertEqual(b1,b2); self.assertEqual(h1,h2)
            self.assertEqual(b1["development_assignment_manifest"]["records"],b2["development_assignment_manifest"]["records"])
            self.assertEqual(b1["confirmation_assignment_manifest"]["records"],b2["confirmation_assignment_manifest"]["records"])

    def test_06_mid_generation_restart_reuses_existing_draws_and_finishes_once(self):
        with tempfile.TemporaryDirectory() as td:
            kw=self.args(td,word_factory(23),word_factory(29),b"F"*32)
            tx=m.ensure_durable_transaction_test_only(kw["transaction_path"],self.binding(),b"F"*32)
            fid=self.dev[2]["family_ids"][0]
            stream=m.durable_u16_words_test_only(kw["transaction_path"],tx,m.DEVELOPMENT_NAMESPACE,fid,word_factory(23)(fid))
            first=next(stream)
            b,h,_=m.freeze_two_split_bundle_durable_test_only(**kw)
            self.assertEqual(b["development_assignment_manifest"]["records"][0]["draw_words_u16_in_order"][0],first)
            self.assertTrue(Path(kw["bundle_path"]).exists()); self.assertEqual(h,hashlib.sha256(Path(kw["bundle_path"]).read_bytes()).hexdigest())

    def test_07_existing_final_bundle_with_missing_journal_fails_closed_no_regeneration(self):
        with tempfile.TemporaryDirectory() as td:
            kw=self.args(td,word_factory(31),word_factory(37),b"G"*32)
            b,_,tx=m.freeze_two_split_bundle_durable_test_only(**kw)
            rec=b["development_assignment_manifest"]["records"][0]
            victim=m._draw_path(kw["transaction_path"],tx,m.DEVELOPMENT_NAMESPACE,rec["family_id"],0)
            victim.unlink()
            with self.assertRaisesRegex(ValueError,"DURABLE_FILE_READ_FAILED|JOURNAL|No such file|DURABLE"):
                m.freeze_two_split_bundle_durable_test_only(**self.args(td,word_factory(401),word_factory(409),b"H"*32))
            self.assertFalse(victim.exists(),"existing final bundle must not trigger draw regeneration")

    def test_08_corrupt_draw_fails_closed_and_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            txp=Path(td)/"tx.json"; tx=m.ensure_durable_transaction_test_only(txp,self.binding(),b"I"*32)
            fid=self.dev[2]["family_ids"][0]
            g=m.durable_u16_words_test_only(txp,tx,m.DEVELOPMENT_NAMESPACE,fid,iter([17])); self.assertEqual(next(g),17)
            p=m._draw_path(txp,tx,m.DEVELOPMENT_NAMESPACE,fid,0); p.write_bytes(b'{bad')
            g2=m.durable_u16_words_test_only(txp,tx,m.DEVELOPMENT_NAMESPACE,fid,iter([19]))
            with self.assertRaisesRegex(ValueError,"CORRUPT"):
                next(g2)
            self.assertEqual(p.read_bytes(),b'{bad')

    def test_09_file_and_parent_directory_fsync_are_both_called(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"probe.json"; calls=[]; real=os.fsync
            def spy(fd):
                calls.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
                return real(fd)
            with mock.patch.object(m.os,"fsync",side_effect=spy):
                m._create_regular_file_once_durable(p,b'{}\n',"EXISTS")
            self.assertIn("file",calls); self.assertIn("dir",calls)
            self.assertLess(calls.index("file"),calls.index("dir"))

    def test_10_ambiguous_directory_fsync_error_leaves_state_never_unlinks(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"probe.json"; real=os.fsync; seen_file=False
            def fail_dir(fd):
                nonlocal seen_file
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError("simulated dir fsync failure")
                seen_file=True; return real(fd)
            with mock.patch.object(m.os,"fsync",side_effect=fail_dir):
                with self.assertRaises(OSError): m._create_regular_file_once_durable(p,b'{}\n',"EXISTS")
            self.assertTrue(seen_file); self.assertTrue(p.exists(),"ambiguous state must be left for recovery/fail-closed, not unlinked")
            with self.assertRaisesRegex(ValueError,"EXISTS"):
                m._create_regular_file_once_durable(p,b'{"different":1}\n',"EXISTS")

    def test_11_extra_journal_after_accepted_word_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            kw=self.args(td,word_factory(43),word_factory(47),b"J"*32)
            b,_,tx=m.freeze_two_split_bundle_durable_test_only(**kw)
            rec=b["development_assignment_manifest"]["records"][0]
            extra_counter=len(rec["draw_words_u16_in_order"])
            p=m._draw_path(kw["transaction_path"],tx,m.DEVELOPMENT_NAMESPACE,rec["family_id"],extra_counter)
            dr=m.build_draw_record_test_only(tx,m.DEVELOPMENT_NAMESPACE,rec["family_id"],extra_counter,12)
            m._create_regular_file_once_durable(p,m._canonical_bytes(dr),"EXISTS")
            with self.assertRaisesRegex(ValueError,"REDRAW_AFTER_ACCEPTANCE|FILE_SET"):
                m.validate_draw_journal_against_bundle(kw["transaction_path"],tx,b)

    def test_12_parent_must_preexist_and_transaction_bundle_same_parent(self):
        with tempfile.TemporaryDirectory() as td:
            missing=Path(td)/"missing"/"tx.json"
            with self.assertRaisesRegex(ValueError,"PARENT_DIRECTORY"):
                m.ensure_durable_transaction_test_only(missing,self.binding(),b"K"*32)
            other=Path(td)/"other"; other.mkdir()
            kw=self.args(td,word_factory(53),word_factory(59),b"K"*32); kw["bundle_path"]=other/"bundle.json"
            with self.assertRaisesRegex(ValueError,"SAME_PREEXISTING_DIRECTORY"):
                m.freeze_two_split_bundle_durable_test_only(**kw)

    def test_13_production_restart_after_lost_bundle_uses_zero_new_randomness(self):
        with tempfile.TemporaryDirectory() as td:
            ds,dss,dm,dms=self.dev; cs,css,cm,cms=self.conf
            txp=Path(td)/"prod.tx.json"; bp=Path(td)/"prod.bundle.json"
            calls=[]
            def first_entropy(n):
                calls.append(n)
                if n==m.TRANSACTION_NONCE_BYTES:
                    return b"P"*n
                if n==2:
                    return (17).to_bytes(2,"big")
                raise AssertionError(n)
            with mock.patch.object(m.os,"urandom",side_effect=first_entropy):
                b1,h1,t1=m.freeze_two_split_bundle_durable(
                    txp,bp,ds,dss,dm,dms,cs,css,cm,cms,development_arm_outcomes_opened=False
                )
            self.assertEqual(calls[0],m.TRANSACTION_NONCE_BYTES)
            self.assertEqual(calls.count(2),66)
            self.assertEqual(t1["assignment_randomness_source"],"OS_CSPRNG_16BIT_WORDS_DURABLY_JOURNALED_BEFORE_USE")
            bp.unlink()  # simulate final directory-entry loss; transaction+raw-word journal remain durable
            with mock.patch.object(m.os,"urandom",side_effect=AssertionError("restart must not redraw")):
                b2,h2,t2=m.freeze_two_split_bundle_durable(
                    txp,bp,ds,dss,dm,dms,cs,css,cm,cms,development_arm_outcomes_opened=False
                )
            self.assertEqual(t1,t2); self.assertEqual(b1,b2); self.assertEqual(h1,h2)

if __name__=='__main__': unittest.main()
