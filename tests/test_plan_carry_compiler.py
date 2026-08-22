import json,sys
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import plan_runtime as p
import plan_carry_compiler as c
import plancarry_harness as h

Q='/workspace/local-vlm/LLM/plancarry/results/planqual_TEST0174_v4.json'
def setup(n):
 q=json.load(open(Q)); inst=next(x for x in h.load_instances() if x['id']==q['instance_id']); prefix=[p.PlanActionRecord(**x) for x in q['actions'][:n]]; return inst,prefix

def intended(n):
 inst,prefix=setup(n); return json.loads(c.compile_state(inst,prefix,96))['intended_next_action']

def test_after_parent_failure_search_missing_sugar():
 assert intended(2)=={'tool':'search','args':{'recipe_name':'sugar'}}

def test_after_intermediate_craft_retry_pending_parent():
 assert intended(3)=={'tool':'craft','args':{'recipe_name':'pumpkin_pie','recipe_index':0}}

def test_compiled_state_is_valid_bounded_json():
 inst,prefix=setup(4); text=c.compile_state(inst,prefix,96); assert h.token_count(text)<=96; assert isinstance(json.loads(text),dict)
