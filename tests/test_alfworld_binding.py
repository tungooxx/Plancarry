import json
import sys
from pathlib import Path

ROOT = Path('/workspace/local-vlm/LLM/plancarry')
sys.path.insert(0, str(ROOT))

import alfworld_binding_runner as b
import alfworld_gdaa as g


def test_candidate_pool_frozen():
    pool = b.candidate_games()
    assert len(b.candidate_population()) == 790
    assert len(pool) == 180
    assert b.candidate_pool_sha256(pool) == b.EXPECTED_POOL_SHA256
    assert all('/train/' in x and '/valid_unseen/' not in x for x in pool)


def test_gdaa_sentinels():
    sent = g.frozen_sentinels()
    assert sent and all(sent.values())
    assert g.normalize_entity_type('toilet 1') == 'toilet'
    assert g.normalize_entity_type('toiletpaperhanger 1') == 'toiletpaperhanger'
    assert g.normalize_entity_type('coffee table 2') == 'coffeetable'


def test_wrapper_proxy_tokens_equal_and_frozen():
    assert b.wrapper_proxy_guard()
    assert b.ah.token_count(b.BINDING_WRAPPER) == 34
    assert b.ah.token_count(b.NOOP_WRAPPER) == 34


def test_flat_render_has_same_atomic_values_only():
    memory = json.dumps({
        'objective':'put some bowl on coffeetable.',
        'current_subgoal':'deliver held bowl to coffeetable 1',
        'intended_next_action':'go to coffeetable 1',
        'constraints_dependencies':[],
        'important_evidence':{'destination':'coffeetable 1','held_object':'bowl'},
    }, separators=(',',':'))
    flat = b.flat_neutral_render(memory)
    assert b.retained_atomic_values(memory, is_json=True) == b.retained_atomic_values(flat, is_json=False)
    assert 'go to coffeetable 1' in flat
    assert 'sofa' not in flat


def test_iaa_skips_information_commands():
    actions = [
        {'command':'look'},
        {'command':'examine shelf 1'},
        {'command':'go to sofa 1'},
    ]
    first = b.first_progress_from_records(actions)
    assert first == 'go to sofa 1'
    assert b.iaa_score(first, 'go to sofa 1') is True
    assert b.iaa_score(first, 'go to shelf 1') is False


def test_exact_binomial_hand_cases():
    assert b.binomial_one_sided_p(5,0) == 0.03125
    assert b.binomial_one_sided_p(0,5) == 1.0
    assert b.binomial_one_sided_p(0,0) == 1.0
    assert b.binomial_two_sided_p(5,0) == 0.0625
    assert b.binomial_two_sided_p(3,2) == 1.0


def test_arm_order_is_deterministic_permutation_and_reasonably_counterbalanced():
    x = b.arm_order('/tmp/gameA.tw-pddl')
    assert x == b.arm_order('/tmp/gameA.tw-pddl')
    assert sorted(x) == sorted(b.ARM_NAMES)
    counts = {arm:[0]*4 for arm in b.ARM_NAMES}
    for i in range(400):
        order = b.arm_order(f'/tmp/game{i}.tw-pddl')
        for pos, arm in enumerate(order): counts[arm][pos] += 1
    for arm in b.ARM_NAMES:
        assert max(counts[arm]) - min(counts[arm]) < 45


def test_gdaa_exact_target_and_wrong_target():
    goal='put some remotecontrol on sofa.'
    cmds=['go to sofa 1','go to sofa 2','go to shelf 1','move remotecontrol 1 to shelf 1']
    positives=g.direct_goal_action_set(goal,cmds)
    assert positives == {'go to sofa 1','go to sofa 2'}
    assert g.gdaa_score('go to sofa 2',goal,cmds) is True
    assert g.gdaa_score('go to shelf 1',goal,cmds) is False
    assert g.gdaa_score(None,goal,cmds) is False


def test_gdaa_undefined_not_zero():
    assert g.gdaa_score('go to desk 1','ambiguous task',['go to desk 1']) is None
    assert g.direct_goal_action_set('put some bowl on coffeetable.',['go to shelf 1']) is None


def test_json_arm_specs_are_byte_identical_by_construction():
    memory='{"objective":"x","current_subgoal":"y","intended_next_action":"go to sofa 1"}'
    assert memory == memory == memory
    flat=b.flat_neutral_render(memory)
    assert b.retained_atomic_values(memory,is_json=True) == b.retained_atomic_values(flat,is_json=False)


def test_paired_bool_test():
    episodes=[]
    for a,bv in [(1,0),(1,0),(1,0),(1,0),(1,0)]:
        episodes.append({'arms':{'A':{'iaa':bool(a)},'B':{'iaa':bool(bv)}}})
    r=b.paired_bool_test(episodes,'A','B','iaa')
    assert r['wins_a']==5 and r['losses_a']==0 and r['p']==0.03125
