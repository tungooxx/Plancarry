import hashlib, json, pathlib, collections
SLOT=128
MAX_CONTENT=96
PAST_ACTION_TAKE=40

def pad_slot(content, filler):
    content=list(content); filler=list(filler)
    if len(content)>MAX_CONTENT: raise ValueError('CONTENT_GT96')
    if not filler: raise ValueError('EMPTY_FILLER')
    need=SLOT-len(content)
    reps=(need+len(filler)-1)//len(filler)
    return content+(filler*reps)[:need]

def balanced_block_rotate(ids):
    ids=list(ids); n=len(ids)
    if n<2: raise ValueError('TAGGED_PLAN_TOO_SHORT')
    k=4 if n>=8 else 2
    q,r=divmod(n,k); sizes=[q+(1 if i<r else 0) for i in range(k)]
    blocks=[]; j=0
    for z in sizes: blocks.append(ids[j:j+z]); j+=z
    order=list(range(1,k))+[0]
    out=[x for b in order for x in blocks[b]]
    return out,order,sizes

def past_actions_only(a1,a2,sep):
    # Past-only nuisance control: bounded, deterministic, and cannot contain action3+.
    return list(a1)[:PAST_ACTION_TAKE]+list(sep)+list(a2)[:PAST_ACTION_TAKE]

def next_action_only(a3):
    a3=list(a3)
    if len(a3)>MAX_CONTENT: raise ValueError('ACTION3_GT96_STAGE1_INELIGIBLE')
    return a3

def replay_ids(prefix,slot,suffix):
    assert len(slot)==SLOT
    return list(prefix)+list(slot)+list(suffix)

def check():
    filler=list(range(1000,1128)); sep=[9001]
    # Plan-order control is total for every structurally admissible token length >=2.
    for n in range(2,97):
        x=list(range(n)); y,order,sizes=balanced_block_rotate(x)
        assert len(y)==n and collections.Counter(y)==collections.Counter(x)
        assert order!=list(range(len(order))) and sizes and all(z>0 for z in sizes)
        assert len(pad_slot(x,filler))==128 and len(pad_slot(y,filler))==128
    # Repeated-token analogue remains constructible even if value-level sequence is degenerate.
    y,order,_=balanced_block_rotate([7]*17); assert len(y)==17 and order!=[0,1,2,3]
    # History never overflows because each past command is prospectively capped at 40 IDs.
    for n1 in [0,1,40,41,96,512]:
      for n2 in [0,1,40,41,96,512]:
        h=past_actions_only(range(n1),range(n2),sep); assert len(h)<=81; assert len(pad_slot(h,filler))==128
    # Exact immediate-next-action identity is retained whenever the prospective Stage1 <=96 guard passes.
    for n in [1,2,32,64,96]:
        a=list(range(n)); assert next_action_only(a)==a and len(pad_slot(a,filler))==128
    try: next_action_only(range(97)); raise AssertionError('expected guard')
    except ValueError as e: assert str(e)=='ACTION3_GT96_STAGE1_INELIGIBLE'
    # Direct ID splice gives condition-invariant downstream positions and no decode/reencode step.
    prefix=[1,2,3,4]; suffix=[8,9,10]
    conditions=[pad_slot(list(range(n)),filler) for n in [0,2,17,64,96]]
    rs=[replay_ids(prefix,s,suffix) for s in conditions]
    assert len({len(r) for r in rs})==1
    assert all(r[:len(prefix)]==prefix and r[-len(suffix):]==suffix for r in rs)
    assert all(r[len(prefix)+SLOT:]==suffix for r in rs)
    return {'status':'PASS','checks':7,'model_calls':0,'environment_execution':0}
if __name__=='__main__': print(json.dumps(check(),sort_keys=True))
