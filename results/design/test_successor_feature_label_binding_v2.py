import hashlib
import json
import math
import pathlib
import unittest

import successor_feature_label_binding_v2 as lb
from successor_feature_constructibility_v2 import ContractError, PHASE_LABELS

ROOT = pathlib.Path(__file__).resolve().parents[2]

CANARY = {
    "task_instruction": "Put the red apple in/on the wooden box.",
    "history": [
        ("go to countertop 1", "You arrive at countertop 1.\nA red apple is here."),
        ("take apple 1 from countertop 1", "You pick up apple 1."),
    ],
    "current_observation": "You are at countertop 1 holding apple 1.",
    "admissible_commands": [
        "put apple 1 in/on box 1",
        "go to shelf 1",
        "go to cabinet 1",
    ],
    "shared_action": "go to cabinet 1",
}

class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        i = lb.LABEL_SUFFIXES_UTF8.index(text)
        return list(lb.LABEL_SUFFIX_IDS[i])
    def decode(self, ids, skip_special_tokens=False, clean_up_tokenization_spaces=False):
        ids=tuple(ids)
        i=lb.LABEL_SUFFIX_IDS.index(ids)
        return lb.LABEL_SUFFIXES_UTF8[i]

class LabelBindingTests(unittest.TestCase):
    def snapshot(self, commands=None):
        return lb.render_snapshot_utf8(
            CANARY['task_instruction'], CANARY['history'], CANARY['current_observation'],
            CANARY['admissible_commands'] if commands is None else commands,
        )

    def test_snapshot_exact_canonical_and_sort_invariant(self):
        s=self.snapshot()
        self.assertEqual(s, '{"task_instruction":"Put the red apple in/on the wooden box.","history":[{"action":"go to countertop 1","observation":"You arrive at countertop 1.\\nA red apple is here."},{"action":"take apple 1 from countertop 1","observation":"You pick up apple 1."}],"current_observation":"You are at countertop 1 holding apple 1.","admissible_commands_lex":["go to cabinet 1","go to shelf 1","put apple 1 in/on box 1"]}')
        self.assertEqual(s,self.snapshot(list(reversed(CANARY['admissible_commands']))))
        self.assertEqual(lb.validate_snapshot_utf8(s)['admissible_commands_lex'][0],'go to cabinet 1')

    def test_snapshot_requires_exact_two_cycles_and_nonempty_commands(self):
        with self.assertRaisesRegex(ContractError,'EXACTLY_TWO'):
            lb.render_snapshot_utf8('x',CANARY['history'][:1],'o',['a'])
        with self.assertRaisesRegex(ContractError,'EMPTY'):
            lb.render_snapshot_utf8('x',CANARY['history'],'o',[])

    def test_noncanonical_snapshot_tamper_rejected(self):
        s=self.snapshot()
        obj=json.loads(s)
        tampered=json.dumps(obj,ensure_ascii=False,indent=1)
        with self.assertRaisesRegex(ContractError,'CANONICAL_SERIALIZATION'):
            lb.validate_snapshot_utf8(tampered)

    def test_step2_prompt_exact_preregistered_suffix(self):
        s=self.snapshot(); p=lb.render_label_prompt_utf8(s,CANARY['shared_action'])
        expected=s+'\nSHARED_ACTION: go to cabinet 1\nPredict the procedural phase of the next action after the shared action. Answer with exactly one label:'
        self.assertEqual(p,expected)
        self.assertNotIn('PREDICTED_PHASE_HISTORY',p)

    def test_recursive_prompt_only_predicted_phase_labels(self):
        s=self.snapshot()
        p3=lb.render_label_prompt_utf8(s,CANARY['shared_action'],['CARRY_OR_SEEK_RECEPTACLE'])
        p4=lb.render_label_prompt_utf8(s,CANARY['shared_action'],['CARRY_OR_SEEK_RECEPTACLE','PLACE_OBJECT'])
        self.assertIn('PREDICTED_PHASE_HISTORY_AFTER_SHARED_ACTION_JSON:["CARRY_OR_SEEK_RECEPTACLE"]',p3)
        self.assertIn('PREDICTED_PHASE_HISTORY_AFTER_SHARED_ACTION_JSON:["CARRY_OR_SEEK_RECEPTACLE","PLACE_OBJECT"]',p4)
        for forbidden in ('A4','A5','B4','B5','future_observation','future_admissible'):
            self.assertNotIn(forbidden,p3)
            self.assertNotIn(forbidden,p4)
        with self.assertRaisesRegex(ContractError,'UNKNOWN_LABEL'):
            lb.render_label_prompt_utf8(s,CANARY['shared_action'],['go to cabinet 1'])
        with self.assertRaisesRegex(ContractError,'TOO_LONG'):
            lb.render_label_prompt_utf8(s,CANARY['shared_action'],list(PHASE_LABELS[:3]))

    def test_suffix_id_table_exact(self):
        self.assertEqual(lb.LABEL_SUFFIX_IDS,(
            (46240,13442),(10584,19714,13442),
            (356,76864,19834,3620,71133,2192,21073,74701),
            (81882,13442),(25735,3298,79223,50689),(10065,),
        ))
        lb.verify_tokenizer_binding(FakeTokenizer(),model_id=lb.MODEL_ID,revision=lb.MODEL_REVISION,transformers_version=lb.TRANSFORMERS_VERSION,tokenizers_version=lb.TOKENIZERS_VERSION)


    def test_suffix_table_canonical_serialization_and_hash(self):
        rows=lb.suffix_table_rows()
        expected={
            "schema": lb.SUFFIX_TABLE_SERIALIZATION_SCHEMA,
            "rows": [
                {"label": label, "utf8": utf8, "ids": list(ids)}
                for label, utf8, ids in zip(PHASE_LABELS, lb.LABEL_SUFFIXES_UTF8, lb.LABEL_SUFFIX_IDS)
            ],
        }
        expected_bytes=json.dumps(expected,ensure_ascii=False,separators=(",", ":"),sort_keys=False).encode("utf-8")
        self.assertEqual(lb.canonical_suffix_table_utf8(),expected_bytes)
        self.assertEqual(lb.canonical_suffix_table_sha256(),lb.SUFFIX_TABLE_SHA256)
        audit=json.loads((ROOT/'results/design/plancarry_successor_feature_label_binding_v2_20260828.json').read_text())
        self.assertEqual(audit['suffix_table_sha256'],lb.SUFFIX_TABLE_SHA256)
        self.assertEqual(audit['suffix_table_serialization']['schema'],lb.SUFFIX_TABLE_SERIALIZATION_SCHEMA)

    def test_suffix_table_hash_rejects_order_text_and_id_drift(self):
        rows=lb.suffix_table_rows()
        reversed_rows=list(reversed(rows))
        self.assertNotEqual(lb.canonical_suffix_table_sha256(reversed_rows),lb.SUFFIX_TABLE_SHA256)
        text_rows=[dict(x) for x in rows]
        text_rows[0]=dict(text_rows[0]); text_rows[0]['utf8']=' SEEK_OBJECT_TAMPER'
        self.assertNotEqual(lb.canonical_suffix_table_sha256(text_rows),lb.SUFFIX_TABLE_SHA256)
        id_rows=[dict(x) for x in rows]
        id_rows[0]=dict(id_rows[0]); id_rows[0]['ids']=list(id_rows[0]['ids']); id_rows[0]['ids'][0]+=1
        self.assertNotEqual(lb.canonical_suffix_table_sha256(id_rows),lb.SUFFIX_TABLE_SHA256)

    def test_tokenizer_provenance_mismatch_fails_closed(self):
        for kw,val in [('model_id','wrong'),('revision','wrong'),('transformers_version','0'),('tokenizers_version','0')]:
            args=dict(model_id=lb.MODEL_ID,revision=lb.MODEL_REVISION,transformers_version=lb.TRANSFORMERS_VERSION,tokenizers_version=lb.TOKENIZERS_VERSION)
            args[kw]=val
            with self.assertRaises(ContractError): lb.verify_tokenizer_binding(FakeTokenizer(),**args)

    def test_direct_id_geometry(self):
        p=(11,22,33)
        plans=lb.build_label_scoring_sequences(p)
        self.assertEqual(len(plans),6)
        for x,expected in zip(plans,lb.LABEL_SUFFIX_IDS):
            self.assertEqual(x.prompt_ids,p)
            self.assertEqual(x.suffix_start,len(p))
            self.assertEqual(x.sequence_ids[:len(p)],p)
            self.assertEqual(x.sequence_ids[len(p):],expected)
            self.assertEqual(x.suffix_ids,expected)

    def test_mean_suffix_logprob_index_math(self):
        # sequence [prompt0,prompt1,suffix2,suffix3], vocab4.
        # suffix targets 2 and3 are predicted by logits rows1 and2 respectively.
        seq=(0,1,2,3)
        logits=[
            [9.0,0.0,0.0,0.0],
            [0.0,0.0,2.0,0.0],
            [0.0,0.0,0.0,1.0],
        ]
        def lp(row,t):
            m=max(row); return row[t]-(m+math.log(sum(math.exp(x-m) for x in row)))
        expected=(lp(logits[1],2)+lp(logits[2],3))/2
        self.assertAlmostEqual(lb.mean_suffix_logprob_from_logits(logits,seq,2),expected,places=14)

    def test_mean_suffix_logprob_nonfinite_and_shape_fail_closed(self):
        with self.assertRaisesRegex(ContractError,'INSUFFICIENT'):
            lb.mean_suffix_logprob_from_logits([[0,0]],(0,1,1),1)
        with self.assertRaisesRegex(ContractError,'NONFINITE'):
            lb.mean_suffix_logprob_from_logits([[0,float('nan')]],(0,1),1)

    def test_no_model_or_environment_imports(self):
        src=(ROOT/'successor_feature_label_binding_v2.py').read_text().lower()
        for bad in ('import torch','import transformers','import alfworld','import textworld','from torch','from transformers'):
            self.assertNotIn(bad,src)

if __name__=='__main__': unittest.main()
