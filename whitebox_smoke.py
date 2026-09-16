import os, json, hashlib, argparse, math
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--model', default='Qwen/Qwen2.5-0.5B-Instruct')
    ap.add_argument('--cache-dir', default='.hf_cache')
    ap.add_argument('--out', default='results/engineering/whitebox_smoke.json')
    args=ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    torch.manual_seed(0)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(0)
    tokenizer=AutoTokenizer.from_pretrained(args.model, cache_dir=args.cache_dir)
    model=AutoModelForCausalLM.from_pretrained(args.model, cache_dir=args.cache_dir, torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32)
    device='cuda' if torch.cuda.is_available() else 'cpu'
    model=model.to(device).eval()
    if torch.cuda.is_available(): torch.cuda.reset_peak_memory_stats()
    messages=[{'role':'user','content':'Reply with exactly one word: ready'}]
    text=tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    batch=tokenizer(text, return_tensors='pt').to(device)
    with torch.no_grad():
        g1=model.generate(**batch, max_new_tokens=4, do_sample=False, use_cache=True)
        g2=model.generate(**batch, max_new_tokens=4, do_sample=False, use_cache=True)
        out=model(**batch, output_hidden_states=True, use_cache=False)
    deterministic=bool(torch.equal(g1,g2))
    hidden_shapes=[list(x.shape) for x in out.hidden_states]
    base_logits=out.logits[:, -1, :].detach().float()
    layers=model.model.layers
    layer_idx=len(layers)//2

    def run_hook(scale):
        gen=torch.Generator(device=device); gen.manual_seed(1234)
        def hook(module, inp, output):
            if isinstance(output, tuple):
                h=output[0]
                rest=output[1:]
            else:
                h=output; rest=None
            h2=h.clone()
            if scale != 0.0:
                v=torch.randn(h2.shape[-1], generator=gen, device=h2.device, dtype=torch.float32)
                v=v/(v.norm()+1e-8)
                # magnitude relative to last-token residual norm, bounded engineering sensitivity test only
                mag=h2[:, -1, :].float().norm(dim=-1, keepdim=True).mean() * scale
                h2[:, -1, :]=h2[:, -1, :] + (v.to(h2.dtype)*mag.to(h2.dtype))
            return (h2, *rest) if rest is not None else h2
        handle=layers[layer_idx].register_forward_hook(hook)
        try:
            with torch.no_grad(): r=model(**batch, use_cache=False)
            return r.logits[:, -1, :].detach().float()
        finally:
            handle.remove()
    noop=run_hook(0.0)
    pert=run_hook(0.05)
    result={
      'kind':'WHITEBOX_ENGINEERING_SMOKE','scientific_result':'NOT_ASSESSED',
      'model_id':args.model,'model_commit':getattr(model.config,'_commit_hash',None),
      'transformers_version':__import__('transformers').__version__,'torch_version':torch.__version__,
      'device':device,'gpu_name':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
      'parameter_count':sum(p.numel() for p in model.parameters()),
      'dtype':str(next(model.parameters()).dtype),'num_transformer_layers':len(layers),
      'hidden_state_count':len(out.hidden_states),'hidden_shapes':hidden_shapes,
      'deterministic_generation':deterministic,
      'decoded_generation':tokenizer.decode(g1[0][batch.input_ids.shape[1]:], skip_special_tokens=True),
      'noop_logit_maxabs_delta':float((noop-base_logits).abs().max().item()),
      'perturb_logit_maxabs_delta':float((pert-base_logits).abs().max().item()),
      'perturb_logit_l2_delta':float((pert-base_logits).norm().item()),
      'hook_layer_index':layer_idx,
      'peak_gpu_allocated_bytes':int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else 0,
      'gpu_free_total_bytes_after':list(torch.cuda.mem_get_info()) if torch.cuda.is_available() else None,
      'valid_unseen_consumed':False
    }
    with open(args.out,'w') as f: json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
