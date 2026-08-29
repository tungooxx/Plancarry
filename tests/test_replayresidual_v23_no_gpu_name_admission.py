import importlib.util
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
RUNNER=ROOT/'results/design/plancarry_replayresidual_v23_sanity_runner_capability_adapter_20260829.py'
BRIDGE=ROOT/'results/design/plancarry_replayresidual_v23_bridge_capability_adapter_20260829.py'
ADAPTER=ROOT/'results/design/plancarry_replayresidual_v23_registered_packet_adapter_20260828.py'
LAUNCHER=ROOT/'results/design/plancarry_replayresidual_v23_capability_launcher_20260828.sh'
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
class T(unittest.TestCase):
    def test_sanity_runtime_name_invariant(self):
        m=load(RUNNER,'v23runner')
        base={'model_id':'Qwen/Qwen3-1.7B','model_revision_requested':'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e','model_commit_resolved':'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e','dtype':'torch.bfloat16','quantization':'NONE','transformers_version':'4.51.3','tokenizers_version':'0.21.1','torch_version':'2.13.0+cu130'}
        for name in ['Device A','Device B','Future CUDA Device']:
            x=dict(base,device_name=name); m.v23_runtime_check(x)
        with self.assertRaisesRegex(RuntimeError,'MODEL_DEVICE_PROVENANCE_REQUIRED'):
            m.v23_runtime_check(dict(base,device_name=''))
    def test_bridge_forces_name_gate_disabled(self):
        m=load(BRIDGE,'v23bridge')
        self.assertEqual(['--port','8892','--expected-device-substring',''],m.normalized_argv(['--port','8892']))
        self.assertEqual(['--expected-device-substring',''],m.normalized_argv(['--expected-device-substring','']))
        with self.assertRaisesRegex(RuntimeError,'V23_DEVICE_NAME_ADMISSION_FORBIDDEN'):
            m.normalized_argv(['--expected-device-substring','some-device'])
        self.assertEqual(['--port','8892','--expected-device-substring',''],m.normalized_argv(['--expected-device-substring','','--port','8892','--expected-device-substring','']))
        with self.assertRaisesRegex(RuntimeError,'V23_DEVICE_NAME_ADMISSION_FORBIDDEN'):
            m.normalized_argv(['--expected-device-substring','','--expected-device-substring','late-device'])
        with self.assertRaisesRegex(RuntimeError,'V23_DEVICE_NAME_ADMISSION_FORBIDDEN'):
            m.normalized_argv(['--expected-device-substring=late-device'])
        self.assertEqual(['--port','8892','--expected-device-substring',''],m.normalized_argv(['--expected-device-substring=','--port','8892']))
    def test_packet_adapter_has_no_expected_name_rebinding(self):
        src=ADAPTER.read_text()
        self.assertNotIn('frozen.EXPECTED_DEVICE_NAME=',src)
        self.assertIn('install_v23_capability_overrides()',src)
        m=load(ADAPTER,'v23packetadapter')
        m.install_v23_capability_overrides()
        import replay_residual_natural_packet_validator_v2_1 as packet_validator
        self.assertIs(packet_validator.validate_model_provenance,m.v23_validate_model_provenance)
        base=dict(m.frozen.EXPECTED_MODEL_PROVENANCE)
        for name in ['Device A','Device B','Future CUDA Device']:
            m.v23_validate_model_provenance(dict(base,device_name=name))
        with self.assertRaisesRegex(RuntimeError,'MODEL_DEVICE_PROVENANCE_REQUIRED'):
            m.v23_validate_model_provenance(dict(base,device_name=''))
    def test_active_launcher_uses_capability_adapters(self):
        src=LAUNCHER.read_text()
        self.assertIn('"$PY" "$BRIDGE_ADAPTER"',src)
        self.assertIn('"$PY" "$SANITY_ADAPTER"',src)
        self.assertNotIn('"$PY" replay_residual_sanity_runner_v1.py --episode-dir',src)
    def test_v23_adapter_sources_have_no_marketing_name_literals(self):
        for p in [RUNNER,BRIDGE,ADAPTER]:
            src=p.read_text()
            self.assertNotIn('RTX 3050',src)
            self.assertNotIn('RTX 3080',src)
            self.assertNotIn('RTX 4090',src)
            self.assertNotIn('GTX ',src)
if __name__=='__main__': unittest.main()
