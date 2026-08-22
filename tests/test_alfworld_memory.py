import json,sys
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import alfworld_interruption_harness as h
Q='/workspace/local-vlm/LLM/plancarry/results/alfworld_qualifications_v1/pick_and_place_simple-Book-None-SideTable-329__trial_T20190908_050633_745514.json'
def load(): return json.load(open(Q))

def test_plancarry_uses_only_prefix_and_preserves_goal_commitment():
 d=load(); m=json.loads(h.compile_plancarry(d,4,96))
 assert 'book' in m['objective'].lower() and 'sidetable' in m['objective'].lower()
 assert m['intended_next_action']=='go to sidetable 1'
 assert 'book' in m['current_subgoal'].lower()

def test_plancarry_is_valid_json_within_budget():
 d=load(); text=h.compile_plancarry(d,4,96); assert h.token_count(text)<=96; assert isinstance(json.loads(text),dict)

def test_truncation_is_matched_or_under_budget():
 d=load(); text=h.truncated_memory(d,4,96); assert h.token_count(text)<=96

def test_no_future_action_needed_for_reset4_compiler():
 d=load(); short=dict(d); short['actions']=d['actions'][:4]
 assert h.compile_plancarry(d,4,96)==h.compile_plancarry(short,4,96)

def fake(command):
 from alfworld_runtime import AlfActionRecord
 return AlfActionRecord(command,'',0.0,False,False,'h',[],None)

def test_information_commands_do_not_count_as_progress():
 xs=[fake('inventory'),fake('examine book 1'),fake('go to sidetable 1')]
 assert h.first_progress_action(xs)=='go to sidetable 1'

def test_consecutive_loops_not_required_revisits():
 assert h.consecutive_repeat_count([fake('go to sidetable 1'),fake('go to bed 1'),fake('go to sidetable 1')])==0
 assert h.consecutive_repeat_count([fake('examine bed 1'),fake('examine bed 1')])==1

def test_take_then_move_back_is_reversal():
 assert h.prefix_reversal_count([fake('take book 1 from bed 1')],[fake('move book 1 to bed 1')])==1
 assert h.prefix_reversal_count([fake('take book 1 from bed 1')],[fake('go to sidetable 1')])==0
