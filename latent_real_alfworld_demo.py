import os, json, torch
from transformers import AutoTokenizer, AutoModelForCausalLM
MODEL='Qwen/Qwen2.5-1.5B-Instruct'; OUT='results/engineering/latent_real_alfworld_demo_qwen15b.json'
os.makedirs(os.path.dirname(OUT), exist_ok=True)
torch.manual_seed(20260819)
if torch.cuda.is_available(): torch.cuda.manual_seed_all(20260819)
device='cuda' if torch.cuda.is_available() else 'cpu'; dtype=torch.float16 if device=='cuda' else torch.float32
tok=AutoTokenizer.from_pretrained(MODEL, cache_dir='.hf_cache', local_files_only=True)
model=AutoModelForCausalLM.from_pretrained(MODEL, cache_dir='.hf_cache', torch_dtype=dtype, local_files_only=True).to(device).eval(); layers=model.model.layers
layer_ids=[7,14,21]
shared=("ALFWorld task: Move two books from the bed to the desk. The visible world contains two distinct books on the bed. "
"Book A is the closer book on the left. Book B is the book near the wall, left of the stuffed panda. Both orders are valid and the final task goal is identical. ")
preA=shared+"Active plan before interruption: pick Book A first, put it on the desk, then return for Book B."
preB=shared+"Active plan before interruption: pick Book B first, put it on the desk, then return for Book A."
reset=shared+"The agent was interrupted before picking either book. Resume the active plan. Which book should be picked first? Answer exactly: A or B."

def batch(text): return tok(text, return_tensors='pt').to(device)
def last_hidden(text):
    b=batch(text)
    with torch.no_grad(): o=model(**b, output_hidden_states=True, use_cache=False)
    return [h[0,-1,:].detach().clone() for h in o.hidden_states]
hA=last_hidden(preA); hB=last_hidden(preB); hLA=last_hidden('Option A.'); hLB=last_hidden('Option B.')
rb=batch(reset); p_len=rb.input_ids.shape[1]
def seq_lp(suffix, patch=None):
    full=batch(reset+suffix); handle=None
    if patch is not None:
        li, mode, vec = patch
        def hook(m, inp, out):
            if isinstance(out, tuple): h=out[0]; rest=out[1:]
            else: h=out; rest=None
            h2=h.clone(); pos=min(p_len-1,h2.shape[1]-1)
            if mode=='replace': h2[:,pos,:]=vec.to(h2.dtype)
            elif mode=='add': h2[:,pos,:]=h2[:,pos,:]+vec.to(h2.dtype)
            return (h2,*rest) if rest is not None else h2
        handle=layers[li].register_forward_hook(hook)
    try:
        with torch.no_grad(): logits=model(**full,use_cache=False).logits.float()
    finally:
        if handle: handle.remove()
    labels=full.input_ids[0,p_len:]; lp=0.0
    for j,tid in enumerate(labels): lp += torch.log_softmax(logits[0,p_len+j-1,:],dim=-1)[tid].item()
    return lp
def score(patch=None):
    a=seq_lp(' A',patch); b=seq_lp(' B',patch)
    return {'logp_A':a,'logp_B':b,'margin_B_minus_A':b-a,'choice':'B' if b>a else 'A'}
base=score(); rows=[]
for li in layer_ids:
    va=hA[li+1].float(); vb=hB[li+1].float(); dBA=vb-va; dAB=va-vb; lex=hLB[li+1].float()-hLA[li+1].float()
    g=torch.Generator(device=device); g.manual_seed(1000+li); rnd=torch.randn(dBA.shape,generator=g,device=device,dtype=torch.float32); rnd=rnd/(rnd.norm()+1e-12)*(dBA.norm()+1e-12)
    for name,(mode,vec) in {
      'A_replace':('replace',va),'B_replace':('replace',vb),'A_to_B_add':('add',dBA),'B_to_A_add':('add',dAB),
      'random_plus':('add',rnd),'random_minus':('add',-rnd),'lexical_B_minus_A':('add',lex),'lexical_A_minus_B':('add',-lex)}.items():
        s=score((li,mode,vec)); s.update({'layer':li,'condition':name,'mode':mode,'vector_norm':float(vec.norm().item()),'delta_margin_vs_base':s['margin_B_minus_A']-base['margin_B_minus_A']}); rows.append(s)
base2=score()
result={'kind':'EXPLORATORY_REAL_ALFWORLD_LATENT_TRANSPLANT_DEMO','scientific_result':'NOT_ASSESSED','model_id':MODEL,'model_commit':getattr(model.config,'_commit_hash',None),'task_family':'pick_two_obj_and_place-Book-None-Desk-302','source_task_description':'Move two books from the bed to the desk.','object_A':'closer book on the left','object_B':'book near the wall, left of the stuffed panda','same_reset_prompt_for_all_conditions':True,'layers_tested':layer_ids,'baseline':base,'baseline_repeat':base2,'baseline_deterministic':base==base2,'conditions':rows,'note':'Exploratory demo only; text-induced commitments from a real ALFWorld task family. Not the preregistered paper experiment.','valid_unseen_consumed':False}
with open(OUT,'w') as f: json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
