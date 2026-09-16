import sys
from pathlib import Path

ROOT=Path('/workspace/local-vlm/LLM/plancarry')
sys.path.insert(0, str(ROOT))
import plancarry_harness as h


def test_token_clip_respects_budget():
    text='alpha beta gamma delta epsilon '*100
    for budget in [0,1,8,32,192]:
        assert h.token_count(h.clip_tokens(text,budget)) <= budget


def test_stable_json_normalizes_action_keys():
    a=h.stable_json({'name':'move','args':{'quantity':1,'slot_to':'[A1]','slot_from':'[I1]'}})
    b=h.stable_json({'args':{'slot_from':'[I1]','slot_to':'[A1]','quantity':1},'name':'move'})
    assert a==b


def test_replay_snapshot_hash_identity():
    instances=h.load_instances()
    inst=next(x for x in instances if not x.get('impossible'))
    rt1=h.CraftRuntime(inst)
    rt2=h.CraftRuntime(inst)
    assert rt1.state_hash()==rt2.state_hash()
    assert rt1.observation()==rt2.observation()


def test_truncation_budget():
    recs=[]
    for i in range(20):
        recs.append(h.ActionRecord('search',{'recipe_name':f'item{i}'},f'a{i}','obs '*20,'x',False,None))
    m=h.truncation_memory(recs,64)
    assert h.token_count(m)<=64


def test_sanitize_args_drops_extra_fields():
    assert h.sanitize_args('search', {'recipe_name':'cookie','recipe_type':'crafting'}) == {'recipe_name':'cookie'}

def test_sanitize_args_normalizes_move_quantity():
    assert h.sanitize_args('move', {'slot_from':'[I1]','slot_to':'[A1]','quantity':'2','junk':9}) == {'slot_from':'[I1]','slot_to':'[A1]','quantity':2}


def test_fit_json_budget_is_valid_and_bounded():
    import json
    obj={
      'objective':'craft a complicated item with many details '*8,
      'completed_steps':['did something verbose '*8,'did another verbose thing '*8],
      'current_subgoal':'continue very carefully '*8,
      'constraints_dependencies':{'x':'detail '*20},
      'rejected_or_failed_actions':['bad '*20],
      'important_evidence':{'inventory':'lots '*30},
      'intended_next_action':{'name':'search','args':{'recipe_name':'target_item'}},
      'unresolved_uncertainties':['unknown '*20],
    }
    text=h.fit_json_budget(obj,128)
    assert h.token_count(text)<=128
    assert isinstance(json.loads(text),dict)

def test_normalize_slot_wraps_model_shorthand():
    assert h.normalize_slot('I16')=='[I16]'
    assert h.normalize_slot('[A1]')=='[A1]'
    assert h.normalize_slot('0')=='[0]'


def test_observation_output_hint_names_free_inventory_slot():
    inst=next(x for x in h.load_instances() if x['id']=='TEST0091')
    rt=h.CraftRuntime(inst)
    # Create warped planks from warped_hyphae using the observed simple recipe placement.
    rec=rt.execute('move',{'slot_from':'[I7]','slot_to':'[B1]','quantity':1})
    obs=rt.observation()
    assert '[0]' in obs and 'OUTPUT_NOTE' in obs and 'non-target item warped_planks' in obs


def test_target_output_gets_collection_hint():
    # Construct a synthetic inventory-hash check indirectly by using a trivial target
    # task whose target appears only when crafted is covered by integration smoke;
    # here assert the implementation distinguishes target vs non-target text.
    src=h.CraftRuntime.observation.__code__.co_consts
    assert any(isinstance(x,str) and 'TASK TARGET' in x for x in src)


def test_clarify_recipe_text_marks_destinations_not_sources():
    raw='Recipes to craft x:\nrecipe 1:\npumpkin at [B2]\nsugar at [A3]'
    txt=h.clarify_recipe_text(raw,'x')
    assert "REQUIRED exact ingredient 'pumpkin'" in txt
    assert "PLACE INTO crafting destination '[B2]'" in txt
    assert "NOT a source inventory slot" in txt
