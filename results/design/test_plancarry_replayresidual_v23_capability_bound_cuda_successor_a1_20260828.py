import hashlib, importlib.util, json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
CONTRACT=ROOT/'results/design/plancarry_replayresidual_v23_capability_bound_cuda_successor_contract_a1_20260828.json'
SOURCE=ROOT/'results/design/plancarry_replayresidual_v22_unified_execution_contract_bound_a4_20260828.json'
VALIDATOR=ROOT/'replayresidual_v23_capability_validator_a1.py'
SCIENCE=['authoritative_sources','canonical_hashing','conflict_resolution','executor','observable_input_contract','packet_schema','planner','population','qualification','replay_conditions','sanity_binding','trajectory']

def cbytes(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(v): return hashlib.sha256(cbytes(v)).hexdigest()
def load_validator():
    s=importlib.util.spec_from_file_location('capv',VALIDATOR); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def base_attestation(name='Anything CUDA'):
    return {
      'actual_gpu_name':name,'actual_gpu_uuid_if_available':'GPU-test','driver_version':'test','cuda_runtime':'13.0','compute_capability':'8.x',
      'total_vram_mib':10240,'driver_free_vram_before_canary_mib':9000,'peak_reserved_mib':3500,'post_canary_reserved_mib':3400,
      'repeat_reserved_span_mib':0,'bf16_supported':True,'oom_events':0,'runtime_fingerprint':'test','cuda_available':True,'repeat_count':3,
      'capture_layers':[7,14,21,27],'hook_count_by_layer':[1,1,1,1],
      'model_id':'Qwen/Qwen3-1.7B','revision':'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e','dtype':'bfloat16','quantization':'NONE','offload':'NONE',
      'torch':'2.13.0+cu130','transformers':'4.51.3','tokenizers':'0.21.1'
    }

def test_science_sections_exact_from_v22():
    c=json.loads(CONTRACT.read_text()); s=json.loads(SOURCE.read_text())
    assert c['scientific_protocol_variables_changed']==[] and c['estimand_changed'] is False
    for k in SCIENCE:
        assert c[k]==s[k]
        assert c['scientific_protocol_inheritance']['section_sha256'][k]==sha(s[k])

def test_no_exact_gpu_name_lock_or_provider_lock():
    c=json.loads(CONTRACT.read_text()); v=load_validator()
    assert 'device_name_required' not in c['model_runtime']
    assert c['execution_capability_admission']['gpu_name_whitelist'] is None
    assert c['execution_capability_admission']['gpu_name_blacklist'] is None
    assert c['execution_capability_admission']['provider_or_instance_whitelist'] is None
    assert v.validate_contract(c)==[]

def test_gpu_name_does_not_change_admission():
    c=json.loads(CONTRACT.read_text()); v=load_validator()
    for name in ['NVIDIA GeForce RTX 3080','NVIDIA GeForce RTX 4090','Future CUDA GPU X']:
        assert v.validate_attestation(c,base_attestation(name))==[]

def test_measured_4gb_case_fails_headroom_not_name():
    c=json.loads(CONTRACT.read_text()); v=load_validator(); a=base_attestation('NVIDIA GeForce RTX 3050 Laptop GPU')
    a.update({'total_vram_mib':4095.5,'driver_free_vram_before_canary_mib':3301.4,'peak_reserved_mib':3412.0})
    e=v.validate_attestation(c,a)
    assert 'TOTAL_VRAM_HEADROOM_LT_REQUIRED' in e
    assert 'LIVE_FREE_VRAM_HEADROOM_LT_REQUIRED' in e
    assert all('NAME' not in x for x in e)

def test_capability_failure_is_fail_closed():
    c=json.loads(CONTRACT.read_text()); v=load_validator(); a=base_attestation()
    a['bf16_supported']=False; a['oom_events']=1
    e=v.validate_attestation(c,a)
    assert 'BF16_UNSUPPORTED' in e and 'CANARY_OOM' in e

def test_canonical_self_hash():
    c=json.loads(CONTRACT.read_text()); expected=c.pop('canonical_object_sha256_without_self_field')
    assert sha(c)==expected


def test_contract_self_hash_and_canary_fields_fail_closed():
    c=json.loads(CONTRACT.read_text()); v=load_validator()
    assert v.validate_contract(c)==[]
    bad=json.loads(CONTRACT.read_text())
    bad['canonical_object_sha256_without_self_field']='0'*64
    assert 'CONTRACT_SELF_HASH_MISMATCH' in v.validate_contract(bad)
    for path,value,label in [
        (['execution_capability_admission','exact_model_stress_canary','study_packet_access'], True, 'CANARY_CONTRACT_MISMATCH:study_packet_access'),
        (['execution_capability_admission','exact_model_stress_canary','future_split_access'], True, 'CANARY_CONTRACT_MISMATCH:future_split_access'),
        (['execution_capability_admission','exact_model_stress_canary','environment_execution'], 1, 'CANARY_CONTRACT_MISMATCH:environment_execution'),
        (['execution_capability_admission','exact_model_stress_canary','prefix_token_count'], 64, 'CANARY_CONTRACT_MISMATCH:prefix_token_count'),
        (['execution_capability_admission','exact_model_stress_canary','teacher_forced_suffix_token_count'], 64, 'CANARY_CONTRACT_MISMATCH:teacher_forced_suffix_token_count'),
        (['execution_capability_admission','exact_model_stress_canary','hook_count_per_layer'], 2, 'CANARY_CONTRACT_MISMATCH:hook_count_per_layer'),
        (['execution_capability_admission','exact_model_stress_canary','dtype'], 'float16', 'CANARY_CONTRACT_MISMATCH:dtype'),
        (['execution_capability_admission','exact_model_stress_canary','quantization'], 'INT8', 'CANARY_CONTRACT_MISMATCH:quantization'),
        (['execution_capability_admission','exact_model_stress_canary','offload'], 'CPU', 'CANARY_CONTRACT_MISMATCH:offload'),
        (['execution_capability_admission','exact_model_stress_canary','revision'], 'wrong', 'CANARY_CONTRACT_MISMATCH:revision'),
    ]:
        b=json.loads(CONTRACT.read_text())
        d=b
        for k in path[:-1]: d=d[k]
        d[path[-1]]=value
        assert label in v.validate_contract(b)

def test_required_actual_fields_cover_validator_inputs():
    c=json.loads(CONTRACT.read_text())
    required=set(c['runtime_attestation']['required_actual_fields'])
    expected={
      'actual_gpu_name','actual_gpu_uuid_if_available','driver_version','cuda_runtime','compute_capability',
      'total_vram_mib','driver_free_vram_before_canary_mib','peak_reserved_mib','post_canary_reserved_mib',
      'repeat_reserved_span_mib','bf16_supported','oom_events','runtime_fingerprint','cuda_available','repeat_count',
      'capture_layers','hook_count_by_layer','model_id','revision','dtype','quantization','offload','torch','transformers','tokenizers'
    }
    assert expected <= required
    v=load_validator(); a=base_attestation(); a.pop('transformers')
    assert 'MISSING_ATTESTATION:transformers' in v.validate_attestation(c,a)
