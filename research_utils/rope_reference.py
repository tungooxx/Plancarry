"""Reference RoPE position remapping for fixed-frequency, half-split rotary keys.
CPU-only geometry invariant; not a model-quality or memory-efficacy test.
The default theta matches Qwen2.5; use the actual model frequency for other architectures.
"""
import torch
def rotate_half(x):
    a,b=x.chunk(2,dim=-1)
    return torch.cat((-b,a),-1)
def rope(x,pos,theta=1_000_000.0,inverse=False):
    assert x.ndim==4 and x.shape[-1]%2==0
    L=x.shape[-1]
    freq=1.0/(theta**(torch.arange(0,L,2,device=x.device,dtype=torch.float32)/L))
    angles=torch.outer(pos.to(device=x.device,dtype=torch.float32),freq)
    phase=torch.cat((angles,angles),dim=-1)[None,None,:,:]
    cos=torch.cos(phase);sin=torch.sin(phase)
    if inverse:sin=-sin
    return x.float()*cos+rotate_half(x.float())*sin
def rotate_untouched_plan_kv(original_rotary_keys, original_source_token_start):
    n=original_rotary_keys.shape[-2]
    before=torch.arange(original_source_token_start,original_source_token_start+n,device=original_rotary_keys.device)
    now=torch.arange(n,device=original_rotary_keys.device)
    original=rope(original_rotary_keys,before,inverse=True)
    remapped=rope(original,now,inverse=False)
    return remapped.to(original_rotary_keys.dtype)
def assert_rope_invariant():
    # This is geometry sanity only, no Qwen task-utility.
    z=torch.Generator(device='cpu');z.manual_seed(20261107)
    x=torch.randn((1,4,19,128),generator=z,dtype=torch.float32)
    y=rope(x,torch.arange(2413,2432))
    back=rope(y,torch.arange(2413,2432),inverse=True)
    assert float((x-back).abs().max())<1e-5
    rew=rotate_untouched_plan_kv(y,2413)
    expected=rope(x,torch.arange(19))
    assert float((rew-expected).abs().max())<1e-5
    return True
