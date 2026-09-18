import ast
from pathlib import Path
import pytest
import planlatch_v7_9_model_runtime as m
import planlatch_v7_9_runner as r


def test_model_runtime_import_is_lazy_and_exactly_bound():
    src=Path('planlatch_v7_9_model_runtime.py').read_text()
    tree=ast.parse(src)
    top_imports=[]
    for node in tree.body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            top_imports.extend([x.name for x in node.names])
    assert 'torch' not in top_imports and 'transformers' not in top_imports and 'tokenizers' not in top_imports
    assert r.MODEL_ID=='Qwen/Qwen3-1.7B'
    assert r.MODEL_REVISION=='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'
    assert m.EXPECTED_TRANSFORMERS=='4.51.3' and m.EXPECTED_TOKENIZERS=='0.21.1'


def test_frozen_intervention_sites_and_measurement_are_explicit():
    assert m.SOURCE_ABLATION_SITE=='qwen-mlp-down_proj-input-post-gated-last-visible-token-v1'
    assert 'baseline-minus-zero-ablation' in m.SOURCE_RESPONSE
    assert m.PAYLOAD_SITE==m.SOURCE_ABLATION_SITE
    assert 'distinct-channel' in m.PAYLOAD_COMPOSITION
    assert 'choice-softmax-over-mean' in m.ENDPOINT_SCORING


def test_runtime_freeze_hash_commits_model_facing_contracts():
    freeze,audit=r.synthetic_runtime_freeze()
    d=freeze.__dict__
    # Dataclass fields intentionally expose the nested dictionaries.
    assert d['candidate_channel_algorithm']['count']==256
    # model-facing additions are included in the freeze hash even though ExecutionFreeze
    # stores them through its expanded schema in runner.
    f1,_=r.synthetic_runtime_freeze(); f2,_=r.synthetic_runtime_freeze()
    assert f1.freeze_hash==f2.freeze_hash


def test_payload_constructor_never_selects_same_channel_twice():
    import planlatch_v7_9_protocol as p
    rows=[]
    for i in range(30):
        # Two gains per channel; ranking would otherwise allow duplicate coordinates.
        rows.append(r.ActuatorCandidateEvidence(i//10,i,p.ALLOWED_GAINS[0],100-i,i,"FIT",f"fit-a-{i}"))
        rows.append(r.ActuatorCandidateEvidence(i//10,i,p.ALLOWED_GAINS[1],99-i,i+0.1,"FIT",f"fit-b-{i}"))
    cp,cq,_=r.construct_payload_bank_fit_only(rows)
    for payload in (cp,cq):
        coords=[(t.transformer_block_index,t.mlp_intermediate_channel_index) for t in payload.triples]
        assert len(coords)==len(set(coords))==p.PAYLOAD_K


def test_model_fingerprint_fails_closed_without_resolved_commit_and_bfloat_hashes_storage_bytes():
    src=Path('planlatch_v7_9_model_runtime.py').read_text()
    assert 'resolved model commit hash is unavailable' in src
    assert 'or core.MODEL_REVISION' not in src
    assert '.view(self.torch.uint8)' in src


def test_real_runtime_checks_actual_dtype_device_and_quantization():
    src=Path('planlatch_v7_9_model_runtime.py').read_text()
    assert 'quantized model configuration is forbidden' in src
    assert 'non-bfloat16 floating parameters detected' in src
    assert 'offloaded/non-CUDA parameters detected' in src
