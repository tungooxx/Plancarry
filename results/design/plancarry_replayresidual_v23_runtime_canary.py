#!/usr/bin/env python3
import argparse, json, pathlib, subprocess, sys
import torch, transformers, tokenizers
from transformers import AutoModelForCausalLM
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import replayresidual_v23_capability_validator_a1 as validator
MODEL='Qwen/Qwen3-1.7B'; REV='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'; LAYERS=[7,14,21,27]
def smi(field):
    return subprocess.check_output(['nvidia-smi',f'--query-gpu={field}','--format=csv,noheader,nounits'],text=True).splitlines()[0].strip()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',required=True); args=ap.parse_args(); out=pathlib.Path(args.output)
    if out.exists(): raise SystemExit('REFUSE_EXISTING_CANARY')
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(): raise SystemExit('CUDA_OR_BF16_UNAVAILABLE')
    name=torch.cuda.get_device_name(0); uuid=smi('uuid'); driver=smi('driver_version'); cc='.'.join(map(str,torch.cuda.get_device_capability(0)))
    free_b,total_b=torch.cuda.mem_get_info(); free_mib=free_b/2**20; total_mib=total_b/2**20
    model=AutoModelForCausalLM.from_pretrained(MODEL,revision=REV,torch_dtype=torch.bfloat16,trust_remote_code=False).to('cuda').eval()
    counts={i:0 for i in LAYERS}; handles=[]
    for i in LAYERS:
        handles.append(model.model.layers[i].register_forward_hook(lambda m,inp,out,idx=i: counts.__setitem__(idx,counts[idx]+1)))
    ids=(torch.arange(256,device='cuda',dtype=torch.long)%int(model.config.vocab_size)).unsqueeze(0)
    torch.cuda.reset_peak_memory_stats(); peaks=[]; oom=0
    with torch.inference_mode():
        for _ in range(3):
            try:
                model(input_ids=ids,use_cache=False); torch.cuda.synchronize(); peaks.append(torch.cuda.memory_reserved()/2**20)
            except torch.cuda.OutOfMemoryError:
                oom+=1; torch.cuda.empty_cache()
    for h in handles: h.remove()
    peak=torch.cuda.max_memory_reserved()/2**20; post=torch.cuda.memory_reserved()/2**20; span=(max(peaks)-min(peaks)) if peaks else float('inf')
    a={'actual_gpu_name':name,'actual_gpu_uuid_if_available':uuid,'driver_version':driver,'cuda_runtime':str(torch.version.cuda),'compute_capability':cc,'total_vram_mib':total_mib,'driver_free_vram_before_canary_mib':free_mib,'peak_reserved_mib':peak,'post_canary_reserved_mib':post,'repeat_reserved_span_mib':span,'bf16_supported':bool(torch.cuda.is_bf16_supported()),'oom_events':oom,'cuda_available':True,'repeat_count':3,'capture_layers':LAYERS,'hook_count_by_layer':[1,1,1,1],'hook_invocations_by_layer':[counts[i] for i in LAYERS],'model_id':MODEL,'revision':REV,'dtype':'bfloat16','quantization':'NONE','offload':'NONE','torch':torch.__version__,'transformers':transformers.__version__,'tokenizers':tokenizers.__version__,'study_packet_access':False,'future_split_access':False,'environment_execution':0,'prefix_token_count':128,'teacher_forced_suffix_token_count':128,'hook_count_per_layer':1,'scientific_result':'NOT_ASSESSED_RUNTIME_CANARY_ONLY'}
    a['runtime_fingerprint']=validator.compute_runtime_fingerprint(a)
    contract=json.loads((ROOT/'results/design/plancarry_replayresidual_v23_capability_bound_cuda_successor_contract_a1_20260828.json').read_text())
    errors=validator.validate_attestation(contract,a); a['capability_pass']=not errors; a['validation_errors']=errors; a['headroom_total_mib']=total_mib-peak; a['headroom_live_free_mib']=free_mib-peak
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(a,sort_keys=True,indent=2)+'\n'); print(json.dumps(a,sort_keys=True))
    raise SystemExit(0 if not errors else 2)
if __name__=='__main__': main()
