import os, json, argparse, torch
from transformers import AutoTokenizer, AutoModelForCausalLM

ap=argparse.ArgumentParser()
ap.add_argument('--model',default='Qwen/Qwen2.5-0.5B-Instruct')
ap.add_argument('--cache-dir',default='.hf_cache')
ap.add_argument('--out',default='results/engineering/latent_transplant_smoke.json')
args=ap.parse_args()
os.makedirs(os.path.dirname(args.out),exist_ok=True)
torch.manual_seed(0)
device='cuda' if torch.cuda.is_available() else 'cpu'
tok=AutoTokenizer.from_pretrained(args.model,cache_dir=args.cache_dir)
model=AutoModelForCausalLM.from_pretrained(args.model,cache_dir=args.cache_dir,torch_dtype=torch.float16 if device=='cuda' else torch.float32).to(device).eval()
layers=model.model.layers
layer_ids=sorted(set([len(layers)//4,len(layers)//2,3*len(layers)//4]))

def enc(text): return tok(text,return_tensors='pt').to(device)
def hs_last(text):
    b=enc(text)
    with torch.no_grad(): o=model(**b,output_hidden_states=True,use_cache=False)
    return [h[0,-1,:].detach().clone() for h in o.hidden_states], b

preA='Plan commitment: move the held object to shelf 1. Preserve this commitment through an interruption.'
preB='Plan commitment: move the held object to shelf 2. Preserve this commitment through an interruption.'
reset='After interruption, the visible world state is identical. You hold the object. Choose the next destination: shelf 1 or shelf 2. Answer only: shelf 1 or shelf 2.'
hA,_=hs_last(preA); hB,_=hs_last(preB)
rb=enc(reset)
with torch.no_grad(): base=model(**rb,use_cache=False).logits[0,-1,:].float()
ids1=tok.encode(' shelf 1',add_special_tokens=False); ids2=tok.encode(' shelf 2',add_special_tokens=False)
# first token may be shared; score full string by teacher-forced logprob for a stronger plumbing diagnostic

def seq_logprob(prompt, suffix, patch=None):
    full=tok(prompt+suffix,return_tensors='pt').to(device)
    p_len=tok(prompt,return_tensors='pt').input_ids.shape[1]
    handles=[]
    if patch:
      li, vec, mode=patch
      def hook(m,inp,out):
        if isinstance(out,tuple): h,*rest=out
        else: h=out; rest=None
        h2=h.clone()
        pos=min(p_len-1,h2.shape[1]-1)
        if mode=='replace': h2[:,pos,:]=vec.to(h2.dtype)
        elif mode=='add': h2[:,pos,:]=h2[:,pos,:]+vec.to(h2.dtype)
        return (h2,*rest) if rest is not None else h2
      handles.append(layers[li].register_forward_hook(hook))
    try:
      with torch.no_grad(): logits=model(**full,use_cache=False).logits.float()
    finally:
      for h in handles:h.remove()
    labels=full.input_ids[0,p_len:]
    lp=0.0
    for j,tid in enumerate(labels):
      pos=p_len+j-1
      lp+=torch.log_softmax(logits[0,pos,:],dim=-1)[tid].item()
    return lp

rows=[]
for li in layer_ids:
    # hidden_states index li+1 is layer li output
    va=hA[li+1]; vb=hB[li+1]
    for label,vec in [('A_full',va),('B_full',vb),('AminusB',va-vb),('BminusA',vb-va)]:
      mode='replace' if label.endswith('full') else 'add'
      l1=seq_logprob(reset,' shelf 1',(li,vec,mode)); l2=seq_logprob(reset,' shelf 2',(li,vec,mode))
      rows.append({'layer':li,'patch':label,'mode':mode,'logp_shelf1':l1,'logp_shelf2':l2,'margin_1_minus_2':l1-l2})
base1=seq_logprob(reset,' shelf 1'); base2=seq_logprob(reset,' shelf 2')
res={'kind':'LATENT_TRANSPLANT_ENGINEERING_SMOKE','scientific_result':'NOT_ASSESSED','model_id':args.model,'model_commit':getattr(model.config,'_commit_hash',None),'layers_tested':layer_ids,'baseline':{'logp_shelf1':base1,'logp_shelf2':base2,'margin_1_minus_2':base1-base2},'patches':rows,'note':'Toy prompt only validates capture/injection/transplant plumbing; not scientific evidence and not a novelty claim.','valid_unseen_consumed':False}
with open(args.out,'w') as f:json.dump(res,f,indent=2)
print(json.dumps(res,indent=2))
