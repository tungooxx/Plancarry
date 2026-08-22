import sys,os
os.environ['ALFWORLD_DATA']='/opt/gpu-lab/data/plancarry-alfworld'
sys.path.insert(0,'/workspace/local-vlm/LLM/plancarry')
import alfworld_runtime as a

def first_game():
    gs=a.game_files('valid_seen')
    assert gs
    return gs[0]

def test_game_discovery():
    assert len(a.game_files('valid_seen'))==140
    assert len(a.game_files('valid_unseen'))==134

def test_reset_is_deterministic_and_facts_hidden_from_model_surface():
    g=first_game(); x=a.AlfRuntime(g); y=a.AlfRuntime(g)
    try:
        assert x.hash()==y.hash()
        assert x.observation==y.observation
        assert sorted(x.admissible_commands)==sorted(y.admissible_commands)
        assert len(a._facts(x.info))>0
    finally: x.close(); y.close()

def test_look_replay_hash_identity():
    g=first_game(); rt=a.AlfRuntime(g)
    try:
        cmd='look' if 'look' in rt.admissible_commands else rt.admissible_commands[0]
        rec=rt.step(cmd); expected=rt.hash()
    finally: rt.close()
    rr=a.replay(g,[rec])
    try: assert rr.hash()==expected
    finally: rr.close()

def test_invalid_command_is_non_state_changing():
    g=first_game(); rt=a.AlfRuntime(g)
    try:
        h=rt.hash(); rec=rt.step('__not_an_alfworld_command__')
        assert rec.error and rt.hash()==h and not rec.done
    finally: rt.close()

def test_reset4_qualification_replay_hash_matches_record():
    import json
    qf='/workspace/local-vlm/LLM/plancarry/results/alfworld_qualifications_v1/pick_and_place_simple-Book-None-SideTable-329__trial_T20190908_050633_745514.json'
    d=json.load(open(qf)); recs=[a.AlfActionRecord(**x) for x in d['actions'][:4]]
    rr=a.replay(d['game_file'],recs)
    try: assert rr.hash()==d['actions'][3]['state_hash']
    finally: rr.close()


def test_persistent_alias_restores_missing_bound_path(tmp_path):
    bound=tmp_path/'bound'
    bound.mkdir()
    persistent=tmp_path/'persistent'
    (persistent/'json_2.1.1').mkdir(parents=True)
    resolved=a.ensure_alfworld_data_alias(bound,persistent)
    assert resolved==bound
    assert bound.is_symlink()
    assert (bound/'json_2.1.1').is_dir()


def test_valid_explicit_data_root_is_not_overridden(tmp_path):
    bound=tmp_path/'bound'
    (bound/'json_2.1.1').mkdir(parents=True)
    persistent=tmp_path/'persistent'
    (persistent/'json_2.1.1').mkdir(parents=True)
    resolved=a.ensure_alfworld_data_alias(bound,persistent)
    assert resolved==bound
    assert not bound.is_symlink()


def test_nonempty_invalid_bound_path_fails_closed(tmp_path):
    import pytest
    bound=tmp_path/'bound'; bound.mkdir(); (bound/'unexpected').write_text('x')
    persistent=tmp_path/'persistent'; (persistent/'json_2.1.1').mkdir(parents=True)
    with pytest.raises(RuntimeError):
        a.ensure_alfworld_data_alias(bound,persistent)
