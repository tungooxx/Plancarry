import sys
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import plan_runtime as p
import plancarry_harness as h


def inst(iid):
    return next(x for x in h.load_instances() if x['id']==iid)


def test_real_recipe_search_exposes_dependency():
    text=p.search_recipe('pumpkin_pie')
    assert "pumpkin_pie" in text and 'pumpkin' in text and 'sugar' in text and 'egg' in text


def test_sugar_then_pumpkin_pie_real_plancraft_chain():
    rt=p.PlanRuntime(inst('TEST0174'))
    assert rt.inventory.get('sugar_cane')==1 and rt.inventory.get('sugar',0)==0
    fail=rt.execute('craft',{'recipe_name':'pumpkin_pie','recipe_index':0})
    assert fail.error and not rt.success
    sugar=rt.execute('craft',{'recipe_name':'sugar','recipe_index':0})
    assert sugar.error is None and rt.inventory.get('sugar')==1
    pie=rt.execute('craft',{'recipe_name':'pumpkin_pie','recipe_index':0})
    assert pie.error is None and rt.success and rt.inventory.get('pumpkin_pie')==1


def test_warped_dependency_chain_uses_official_recipe_semantics():
    rt=p.PlanRuntime(inst('TEST0091'))
    a=rt.execute('craft',{'recipe_name':'warped_planks','recipe_index':0})
    assert a.error is None and rt.inventory.get('warped_planks')==4
    b=rt.execute('craft',{'recipe_name':'warped_button','recipe_index':0})
    assert b.error is None and rt.success and rt.inventory.get('warped_button')==1


def test_smelting_recipe_works_from_real_instance():
    rt=p.PlanRuntime(inst('TEST0010'))
    assert rt.inventory.get('cactus')==1
    a=rt.execute('craft',{'recipe_name':'green_dye','recipe_index':0})
    assert a.error is None and rt.inventory.get('green_dye')==1


def test_replay_hash_identity():
    instance=inst('TEST0174'); rt=p.PlanRuntime(instance); recs=[]
    recs.append(rt.execute('search',{'recipe_name':'pumpkin_pie'}))
    recs.append(rt.execute('craft',{'recipe_name':'sugar','recipe_index':0}))
    rr=p.replay(instance,recs)
    assert rr.state_hash()==rt.state_hash()


def test_shaped_recipe_executes_without_grid_motor_control():
    # TEST0102 first requires converting stripped_acacia_log -> acacia_planks,
    # then the official shaped bowl recipe can consume those planks.
    rt=p.PlanRuntime(inst('TEST0102'))
    made=False
    for i,_ in enumerate(p.RECIPES['acacia_planks']):
        rec=rt.execute('craft',{'recipe_name':'acacia_planks','recipe_index':i})
        if rec.error is None:
            made=True; break
    assert made and rt.inventory.get('acacia_planks',0)>=3
    made_bowl=False
    for i,_ in enumerate(p.RECIPES['bowl']):
        rec=rt.execute('craft',{'recipe_name':'bowl','recipe_index':i})
        if rec.error is None:
            made_bowl=True; break
    assert made_bowl and rt.success

def test_failed_pumpkin_pie_reports_only_sugar_missing():
    rt=p.PlanRuntime(inst('TEST0174'))
    rec=rt.execute('craft',{'recipe_name':'pumpkin_pie','recipe_index':0})
    assert 'MISSING_EXACT_PREREQUISITES: sugar x1' in rec.observation
    assert 'pumpkin x1' in rec.observation.split('ALREADY_SATISFIED:')[1].split('\n')[0]
    assert 'egg x1' in rec.observation.split('ALREADY_SATISFIED:')[1].split('\n')[0]


def test_requirement_status_for_smelting_reports_cactus_satisfied():
    rt=p.PlanRuntime(inst('TEST0010'))
    r=p.RECIPES['green_dye'][0]
    sat,miss=p.requirement_status(r,rt.inventory)
    assert not miss and any('cactus' in x for x in sat)
