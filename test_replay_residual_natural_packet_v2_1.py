from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import replay_residual_natural_packet_producer_v2_1 as p
import replay_residual_natural_packet_validator_v2_1 as v
from replay_residual_sanity_protocol_v1 import CONDITIONS, development_manifest, canonical_json_bytes

ROOT = Path(__file__).resolve().parent


class FakeTokenizer:
    eos_token_id = 0
    def __init__(self):
        self.chunk_to_id = {}
        self.id_to_chunk = {}
        self.next_id = 10
        self.chat_calls = []
        self.decode_calls = []
    def _chunks(self, text):
        text = str(text)
        return [text[i:i+4] for i in range(0, len(text), 4)]
    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        out=[]
        for chunk in self._chunks(text):
            if chunk not in self.chunk_to_id:
                i=self.next_id; self.next_id += 1
                self.chunk_to_id[chunk]=i; self.id_to_chunk[i]=chunk
            out.append(self.chunk_to_id[chunk])
        return out
    def decode(self, ids, skip_special_tokens=False, clean_up_tokenization_spaces=False):
        self.decode_calls.append((bool(skip_special_tokens), bool(clean_up_tokenization_spaces)))
        return ''.join(self.id_to_chunk[int(i)] for i in ids if int(i) != self.eos_token_id)
    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, enable_thinking=False):
        self.chat_calls.append((copy.deepcopy(messages), tokenize, add_generation_prompt, enable_thinking))
        assert tokenize is True and add_generation_prompt is True and enable_thinking is False
        text=''.join(f"<{m['role']}>{m['content']}" for m in messages) + '<assistant>'
        return self.encode(text, add_special_tokens=False)


class FakeRuntime:
    def __init__(self, game_path):
        self.game_path=game_path
        self.observation='Header\nYour task is to: put the item away.\nRoom.'
        self.done=False; self.won=False; self.n=0; self.closed=False
    @property
    def admissible_commands(self):
        return ['move', 'look']
    def hash(self):
        return f'h{self.n}'
    def step(self, command):
        if command not in self.admissible_commands:
            return SimpleNamespace(command=command, observation=self.observation, done=self.done, won=self.won, state_hash=self.hash(), error='INVALID')
        self.n += 1
        self.observation=f'o{self.n}'
        self.won = self.n >= 4
        self.done = self.won
        return SimpleNamespace(command=command, observation=self.observation, done=self.done, won=self.won, state_hash=self.hash(), error=None)
    def close(self):
        self.closed=True


def planner_for(tok):
    plan='<PLAN>move item. finish task.</PLAN>'
    ids=tok.encode(plan, add_special_tokens=False)
    def fn(task, obs):
        prefix,user=p.planner_prefix_ids(tok,task,obs)
        return p.PlannerResult(plan, len(ids), tuple(ids), tuple(prefix), user)
    return fn


def scorer_for(tok):
    def score(prefix, suffix):
        cmd=tok.decode(suffix, skip_special_tokens=False, clean_up_tokenization_spaces=False).strip()
        return {'move': 0.0, 'look': -1.0}.get(cmd, -2.0)
    return score


def build_packets(tok):
    rows=development_manifest(ROOT)
    prov=p.derive_model_provenance(p.EXPECTED_DEVICE_NAME)
    return p.all32_attempts(rows, tok, prov, FakeRuntime, planner_for(tok), scorer_for(tok))


def rewrite_manifest_hash(directory: Path, filename: str):
    manifest=json.loads((directory/'manifest.json').read_text())
    manifest['packet_sha256_by_filename'][filename]=p.sha256_file(directory/filename)
    (directory/'manifest.json').write_bytes(canonical_json_bytes(manifest))
    provenance=json.loads((directory/'provenance.json').read_text())
    provenance['packet_manifest_sha256']=p.sha256_file(directory/'manifest.json')
    (directory/'provenance.json').write_bytes(canonical_json_bytes(provenance))


class V21PacketTests(unittest.TestCase):
    def test_binding_and_exact_device(self):
        p.verify_frozen_bindings(ROOT)
        prov=p.derive_model_provenance(p.EXPECTED_DEVICE_NAME)
        p.validate_model_provenance(prov)
        bad=dict(prov); bad['device_name']='NVIDIA GeForce RTX 3050'
        with self.assertRaisesRegex(RuntimeError,'MODEL_DEVICE_NAME_MISMATCH'):
            p.validate_model_provenance(bad)

    def test_task_extraction_uses_last_occurrence(self):
        obs='Your task is to: wrong.\nnoise\nYour task is to: right!\n'
        self.assertEqual(p.extract_task_instruction(obs),'right!')

    def test_planner_acceptance_and_template_contract(self):
        tok=FakeTokenizer(); plan='<PLAN>a. b.</PLAN>'; ids=tok.encode(plan, add_special_tokens=False)
        out,n=p.accept_plan_new_ids(tok,ids)
        self.assertEqual(out,plan); self.assertEqual(n,len(ids))
        self.assertEqual(tok.decode_calls[-1],(True,False))
        p.planner_prefix_ids(tok,'task','obs')
        _, tokenize, add_prompt, thinking=tok.chat_calls[-1]
        self.assertEqual((tokenize,add_prompt,thinking),(True,True,False))
        for bad in ['prefix <PLAN>a.</PLAN>', '<PLAN><think>x</think></PLAN>', '<PLAN>a</PLAN> trailing']:
            with self.assertRaises(RuntimeError):
                p.accept_plan_new_ids(tok,tok.encode(bad,add_special_tokens=False))

    def test_executor_suffix_scoring_and_lexical_tie(self):
        tok=FakeTokenizer()
        user,prefix,suffixes,commands=p.executor_prefix_and_suffixes(tok,'t','<PLAN>a. b.</PLAN>',[],'o',['zeta','alpha'])
        self.assertTrue(user.endswith('ACTION:'))
        self.assertEqual(commands,['alpha','zeta'])
        self.assertEqual(tok.decode(suffixes['alpha']).strip(),'alpha')
        choice=p.choose_admissible_command(tok,'t','<PLAN>a. b.</PLAN>',[],'o',['zeta','alpha'],lambda a,b:0.0)
        self.assertEqual(choice.command,'alpha')

    def test_stage1_nontrivial_case_sensitive_and_guards(self):
        acts=[{'command':'move','error':None},{'command':'take','error':None},{'command':'Look','error':None},{'command':'put','error':None}]
        ok,reasons=p.stage1_eligibility(True,True,acts,[])
        self.assertTrue(ok,reasons)
        acts[0]={'command':'look','error':None}
        ok,reasons=p.stage1_eligibility(True,True,acts,[])
        self.assertFalse(ok); self.assertIn('FIRST_TWO_ACTIONS_NOT_BOTH_NONTRIVIAL',reasons)

    def test_all32_two_stage_and_controls(self):
        tok=FakeTokenizer(); packets=build_packets(tok)
        self.assertEqual([x['frozen_index'] for x in packets],list(range(32)))
        self.assertEqual(sum(x['trajectory_eligible'] for x in packets),32)
        self.assertEqual(sum(x['qualified'] for x in packets),32)
        eligible=p.frozen_eligible_order(packets)
        for x in packets:
            donor=p.unrelated_donor_for(x,eligible)
            self.assertIsNotNone(donor)
            self.assertNotEqual(donor['family'],x['family'])
            self.assertEqual(x['control_provenance']['unrelated_donor_frozen_index'],donor['frozen_index'])
            self.assertEqual(set(x['control_provenance']['condition_slot_token_ids_sha256_by_condition']),set(CONDITIONS))

    def test_E_lt_2_forces_no_qualification(self):
        tok=FakeTokenizer(); packets=build_packets(tok)
        for i,x in enumerate(packets):
            x['trajectory_eligible'] = i == 0
        out=p.apply_stage2(tok,packets)
        self.assertEqual(sum(x['qualified'] for x in out),0)
        self.assertTrue(all(x['qualification_stage2_reasons']==['FROZEN_E_SIZE_LT_2'] for x in out))

    def test_atomic_publish_full_validator_and_refuse_overwrite(self):
        tok=FakeTokenizer(); packets=build_packets(tok)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            final,manifest=p.atomic_publish_packet_set(root,packets,Path('final'),v.validate_packet_directory,tok)
            self.assertTrue(final.is_dir())
            self.assertEqual(manifest['attempted_count'],32)
            self.assertEqual(v.validate_packet_directory(final,tok,ROOT)['qualified'],32)
            self.assertFalse(any('.inprogress' in x.name for x in root.iterdir()))
            with self.assertRaises(FileExistsError):
                p.atomic_publish_packet_set(root,packets,Path('final'),v.validate_packet_directory,tok)

    def test_validator_rejects_cohort_identity_and_manifest_hash_tamper(self):
        tok=FakeTokenizer(); packets=build_packets(tok)
        with tempfile.TemporaryDirectory() as td:
            final,_=p.atomic_publish_packet_set(Path(td),packets,Path('final'),v.validate_packet_directory,tok)
            q=final/p.packet_filename(0)
            obj=json.loads(q.read_text()); obj['family']='wrong-family'; q.write_bytes(canonical_json_bytes(obj))
            rewrite_manifest_hash(final,q.name)
            with self.assertRaisesRegex(RuntimeError,'PACKET_FROZEN_COHORT_IDENTITY_MISMATCH'):
                v.validate_packet_directory(final,tok,ROOT)
        with tempfile.TemporaryDirectory() as td:
            final,_=p.atomic_publish_packet_set(Path(td),packets,Path('final'),v.validate_packet_directory,tok)
            m=json.loads((final/'manifest.json').read_text()); m['anchor_cycle']=99; (final/'manifest.json').write_bytes(canonical_json_bytes(m))
            with self.assertRaisesRegex(RuntimeError,'MANIFEST_QUALIFICATION_OR_ANCHOR_MISMATCH'):
                v.validate_packet_directory(final,tok,ROOT)

    def test_validator_rejects_causal_and_wrong_model_fields(self):
        tok=FakeTokenizer(); packet=build_packets(tok)[0]
        bad=copy.deepcopy(packet); bad['capture']={'x':1}
        with self.assertRaisesRegex(RuntimeError,'CAUSAL_PATH_FIELD_FORBIDDEN'):
            v.validate_packet(bad,tok)
        bad=copy.deepcopy(packet); bad['model_provenance']['revision']='wrong'
        with self.assertRaisesRegex(RuntimeError,'MODEL_PROVENANCE_MISMATCH'):
            v.validate_packet(bad,tok)


if __name__=='__main__':
    unittest.main(verbosity=2)
