import copy, importlib.util, json, pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
BIND=ROOT/'results/design/plancarry_replayresidual_v23_execution_binding_20260828.py'
VAL=ROOT/'replayresidual_v23_capability_validator_a1.py'
CONTRACT=ROOT/'results/design/plancarry_replayresidual_v23_capability_bound_cuda_successor_contract_a1_20260828.json'

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
binding=load(BIND,'v23_binding'); validator=load(VAL,'v23_validator')
contract=json.loads(CONTRACT.read_text())

def good_att(name='NVIDIA GeForce RTX 3080'):
    a={
      'actual_gpu_name':name,'actual_gpu_uuid_if_available':'GPU-test','driver_version':'580.142','cuda_runtime':'13.0','compute_capability':'8.6',
      'total_vram_mib':10240.0,'driver_free_vram_before_canary_mib':9876.0,'peak_reserved_mib':3430.0,'post_canary_reserved_mib':3430.0,
      'repeat_reserved_span_mib':0.0,'bf16_supported':True,'oom_events':0,'cuda_available':True,
      'repeat_count':3,'capture_layers':[7,14,21,27],'hook_count_by_layer':[1,1,1,1],
      'model_id':'Qwen/Qwen3-1.7B','revision':'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e','dtype':'bfloat16','quantization':'NONE','offload':'NONE',
      'torch':'2.13.0+cu130','transformers':'4.51.3','tokenizers':'0.21.1'
    }
    a['runtime_fingerprint']=validator.compute_runtime_fingerprint(a)
    return a
class T(unittest.TestCase):
    def test_gpu_name_not_authority(self):
        for name in ['NVIDIA GeForce RTX 3080','NVIDIA GeForce RTX 4090','Future CUDA Device X']:
            self.assertEqual([],validator.validate_attestation(contract,good_att(name)))
    def test_headroom_fail(self):
        a=good_att(); a['total_vram_mib']=4095.5; a['driver_free_vram_before_canary_mib']=3301.4; a['peak_reserved_mib']=3412.0
        e=validator.validate_attestation(contract,a)
        self.assertIn('LIVE_FREE_VRAM_HEADROOM_LT_REQUIRED',e)
    def test_runtime_drift_fail(self):
        a=good_att(); a['torch']='2.12.0'
        self.assertIn('ATTESTED_RUNTIME_MISMATCH:torch',validator.validate_attestation(contract,a))
    def test_missing_required_fail(self):
        a=good_att(); del a['bf16_supported']
        self.assertIn('MISSING_ATTESTATION:bf16_supported',validator.validate_attestation(contract,a))
    def test_binding_corrected_ids_and_wrong_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            ap=pathlib.Path(d)/'att.json'; ap.write_text(json.dumps(good_att()))
            obj=binding.bind(ROOT,ap)
            self.assertEqual(binding.EXPERIMENT_ID,obj['experiment_id'])
            self.assertEqual(binding.PREDICTION_ID,obj['prediction_id'])
            bad=copy.deepcopy(obj); bad['experiment_id']=binding.SUPERSEDED_EXPERIMENT_ID
            with self.assertRaisesRegex(RuntimeError,'V23_BINDING_MISMATCH:experiment_id'):
                binding.validate_bound(bad,contract)
    def test_nonfinite_fail_closed(self):
        for k in ['total_vram_mib','driver_free_vram_before_canary_mib','peak_reserved_mib','post_canary_reserved_mib','repeat_reserved_span_mib']:
            a=good_att(); a[k]=float('nan')
            self.assertIn(f'NONFINITE_OR_NONNUMERIC:{k}',validator.validate_attestation(contract,a))
    def test_runtime_fingerprint_tamper_fail(self):
        a=good_att(); a['driver_version']='0.0'
        self.assertIn('RUNTIME_FINGERPRINT_MISMATCH',validator.validate_attestation(contract,a))
    def test_gpu_uuid_required(self):
        a=good_att(); a['actual_gpu_uuid_if_available']=''; a['runtime_fingerprint']=validator.compute_runtime_fingerprint(a)
        self.assertIn('ACTUAL_GPU_UUID_REQUIRED_FOR_EXECUTION_BINDING',validator.validate_attestation(contract,a))
    def test_frozen_science_hashes(self):
        want={
          'replay_residual_natural_packet_producer_v2_2_technical_successor.py':'d1be7ecbabc1ac3d8d24587a57e53141623b320615400a5acd0d9b7437635ab8',
          'replay_residual_sanity_runner_v1.py':'7a2c45dadb89a6e0736e53638132b69a38792ab83a3915a9d67ef937ce0a1bd3',
          'replay_residual_capture_only_sidecar_v1.py':'9bc1b5976798c37a989fb4aa4a9e91b2d6004f90185713687c8bf13fee35e3aa',
          'whitebox_bridge_prefixstable_proto.py':'d8c5ad9abd3cf45181a07cf8f1f837e7b36d3c47d59e7dc7cc4225f1a5e66404'}
        import hashlib
        for p,h in want.items(): self.assertEqual(h,hashlib.sha256((ROOT/p).read_bytes()).hexdigest())
if __name__=='__main__': unittest.main()
