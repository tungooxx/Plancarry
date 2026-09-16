import itertools, json, pathlib, collections
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
    if n<2: raise ValueError('INTERIOR_TOO_SHORT')
    k=4 if n>=8 else 2
    q,r=divmod(n,k); sizes=[q+(1 if i<r else 0) for i in range(k)]
    blocks=[]; j=0
    for z in sizes: blocks.append(ids[j:j+z]); j+=z
    order=list(range(1,k))+[0]
    return [x for b in order for x in blocks[b]],order,sizes

def strong_interior_derangement(interior):
    x=list(interior); n=len(x)
    if n<2: raise ValueError('INTERIOR_TOO_SHORT')
    if len(set(x))<2: raise ValueError('INTERIOR_ALL_EQUAL')
    primary,order,sizes=balanced_block_rotate(x)
    if primary!=x and primary[-1]!=x[-1]:
        return primary,{'method':'BALANCED_BLOCK_LEFT_ROTATE','offset':None,'order':order,'sizes':sizes}
    for k in range(1,n):
        y=x[k:]+x[:k]
        if y!=x and y[-1]!=x[-1]:
            return y,{'method':'SMALLEST_VALID_LEFT_ROTATION','offset':k,'order':None,'sizes':None}
    raise ValueError('NO_VALID_DERANGEMENT')

def plan_block_deranged(tagged_ids, open_tag_ids, close_tag_ids):
    ids=list(tagged_ids); op=list(open_tag_ids); cl=list(close_tag_ids)
    if not op or not cl: raise ValueError('EMPTY_TAG_SPAN')
    if ids[:len(op)]!=op or ids[-len(cl):]!=cl: raise ValueError('TAG_SPAN_MISMATCH')
    if len(ids)<len(op)+len(cl)+2: raise ValueError('INTERIOR_TOO_SHORT')
    interior=ids[len(op):len(ids)-len(cl)]
    y,meta=strong_interior_derangement(interior)
    out=op+y+cl
    assert out[:len(op)]==op and out[-len(cl):]==cl
    assert len(out)==len(ids) and collections.Counter(out)==collections.Counter(ids)
    assert y!=interior and y[-1]!=interior[-1]
    return out,meta

def past_actions_only(a1,a2,sep):
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
    root=pathlib.Path(__file__).resolve().parent
    prereg=json.loads((root/'plancarry_localcontinuation_v2_final_prereg_v1_20260824.json').read_text())
    contract=json.loads((root/'plancarry_localcontinuation_v2_constructible_control_contract_v1_20260824.json').read_text())
    arm='PLAN_BLOCK_DERANGED'; stale='PLAN_TOKEN_PERMUTED'
    controls=prereg['causal_runtime_and_controls']['intervention_controls']
    semantics=prereg['semantic_conditions_v2']
    assert arm in controls and stale not in controls and arm in semantics and stale not in semantics
    assert arm in contract['causal_arms'] and arm in contract['specificity_max_controls']
    assert stale not in contract['causal_arms'] and stale not in contract['specificity_max_controls']
    assert controls==[x for x in contract['causal_arms'] if x!='ACTIVE_PLAN_RESIDUAL']
    assert contract['causal_arms'].count('ACTIVE_PLAN_RESIDUAL')==1

    # Exhaustive ternary interiors length2..10: every non-all-equal sequence is constructible,
    # preserves exact IDs/count, is value-nonidentical, and changes the rightmost interior value.
    op=[7001,7002]; cl=[7003,7004]
    constructible=all_equal=primary=fallback=0
    fallback_example=None
    for n in range(2,11):
        for x in itertools.product(range(3), repeat=n):
            tagged=op+list(x)+cl
            if len(set(x))<2:
                all_equal+=1
                try: plan_block_deranged(tagged,op,cl); raise AssertionError('expected all-equal fail-close')
                except ValueError as e: assert str(e)=='INTERIOR_ALL_EQUAL'
                continue
            y,meta=plan_block_deranged(tagged,op,cl); yi=y[len(op):-len(cl)]
            constructible+=1
            assert y[:len(op)]==op and y[-len(cl):]==cl
            assert len(y)==len(tagged) and collections.Counter(y)==collections.Counter(tagged)
            assert yi!=list(x) and yi[-1]!=x[-1]
            if meta['method']=='BALANCED_BLOCK_LEFT_ROTATE': primary+=1
            else:
                fallback+=1
                if fallback_example is None: fallback_example=(list(x),yi,meta['offset'])
    assert constructible==88542 and all_equal==27 and primary==59046 and fallback==29496
    assert fallback_example is not None

    # Explicit tag mismatch and too-short guards.
    for bad,err in [([1,2,3,4,5],'TAG_SPAN_MISMATCH'),(op+[1]+cl,'INTERIOR_TOO_SHORT')]:
        try: plan_block_deranged(bad,op,cl); raise AssertionError('expected guard')
        except ValueError as e: assert str(e)==err

    # History and exact action3 late-null guards remain unchanged.
    for n1 in [0,1,40,41,96,512]:
      for n2 in [0,1,40,41,96,512]:
        h=past_actions_only(range(n1),range(n2),sep); assert len(h)<=81; assert len(pad_slot(h,filler))==128
    for n in [1,2,32,64,96]:
        a=list(range(n)); assert next_action_only(a)==a and len(pad_slot(a,filler))==128
    try: next_action_only(range(97)); raise AssertionError('expected guard')
    except ValueError as e: assert str(e)=='ACTION3_GT96_STAGE1_INELIGIBLE'

    # Direct ID splice preserves downstream geometry.
    prefix=[1,2,3,4]; suffix=[8,9,10]
    conditions=[pad_slot(list(range(n)),filler) for n in [0,2,17,64,96]]
    rs=[replay_ids(prefix,s,suffix) for s in conditions]
    assert len({len(r) for r in rs})==1
    assert all(r[:len(prefix)]==prefix and r[-len(suffix):]==suffix for r in rs)
    assert all(r[len(prefix)+SLOT:]==suffix for r in rs)
    return {'status':'PASS','checks':11,'constructible_exhaustive':constructible,'all_equal_fail_closed':all_equal,'primary_cases':primary,'fallback_cases':fallback,'model_calls':0,'environment_execution':0}
if __name__=='__main__': print(json.dumps(check(),sort_keys=True))
