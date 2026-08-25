import math
from types import SimpleNamespace
import torch
import planunique_science_driver_v1 as P

class _ToyModel:
    def __init__(self):
        self.anchor=torch.nn.Parameter(torch.tensor(0.0))
        self.vocab=23
        self.calls=[]
    def parameters(self):
        yield self.anchor
    def __call__(self,input_ids,logits_to_keep=0):
        # Deterministic row-local logits: selected-row computation is mathematically exact.
        x=input_ids.to(torch.float32)
        pos=torch.arange(x.shape[1],device=x.device,dtype=torch.float32)[None,:]
        h=(x*0.03125+pos*0.0078125)[:,:,None]
        w=torch.arange(self.vocab,device=x.device,dtype=torch.float32)[None,None,:]
        all_logits=(h*(w+1.0)+0.125*w).to(torch.bfloat16)
        if isinstance(logits_to_keep,int):
            selected=all_logits if logits_to_keep==0 else all_logits[:,-logits_to_keep:,:]
        else:
            selected=all_logits[:,logits_to_keep,:]
        self.calls.append((tuple(input_ids.shape),logits_to_keep,tuple(selected.shape)))
        return SimpleNamespace(logits=selected)

def _reference(model,p,s):
    full=torch.tensor([list(p)+list(s)],dtype=torch.long)
    with torch.inference_mode():
        logits=model(input_ids=full,logits_to_keep=0).logits.float()
        logp=torch.log_softmax(logits,dim=-1)
        vals=[logp[0,len(p)+j-1,int(t)] for j,t in enumerate(s)]
        return float(torch.stack(vals).mean().item())

def test_vram_bounded_suffix_score_exact_reference_and_geometry():
    p=[3,5,7,11,13,17,19];s=[2,4,6]
    a=_reference(_ToyModel(),p,s)
    m=_ToyModel();b=P._suffix_mean_logprob_vram_bounded(m,p,s)
    assert a==b
    shape,keep,selected=m.calls[-1]
    assert shape==(1,len(p)+len(s))
    assert keep.tolist()==list(range(len(p)-1,len(p)+len(s)-1))
    assert selected==(1,len(s),m.vocab)

def test_vram_bounded_suffix_score_single_token():
    p=[1,2,3];s=[5]
    a=_reference(_ToyModel(),p,s);m=_ToyModel();b=P._suffix_mean_logprob_vram_bounded(m,p,s)
    assert a==b and math.isfinite(b)
    assert m.calls[-1][1].tolist()==[len(p)-1]

def test_vram_bounded_suffix_score_rejects_empty():
    m=_ToyModel()
    for p,s in [([], [1]),([1],[])]:
        try:P._suffix_mean_logprob_vram_bounded(m,p,s);assert False
        except RuntimeError as e:assert str(e)=='EMPTY_PREFIX_OR_SUFFIX'
