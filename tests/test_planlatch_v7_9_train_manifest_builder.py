import json
from pathlib import Path

import pytest

import planlatch_v7_9_train_manifest_builder as b
import planlatch_v7_9_runner as core
import planlatch_v7_9_execution_driver as driver


def fake_row():
    return {
        "family":"pick_two_obj_and_place-Book-None-Desk-999",
        "trial":"trial_T000000_0",
        "target_receptacle":"desk 1",
        "object_a":{"object":"book 1","source":"bed 1"},
        "object_b":{"object":"book 2","source":"bed 1"},
        "a_first_divergent_action":"take book 1 from bed 1",
        "b_first_divergent_action":"take book 2 from bed 1",
        "task_text":"Your task is to: put two book in desk.",
        "reset_observation":"You arrive at bed 1.",
        "reset_admissible_commands":["take book 1 from bed 1","take book 2 from bed 1","go to desk 1"],
        "reset_state_hash":"abc123",
        "game_path":"train/pick_two_obj_and_place-Book-None-Desk-999/trial_T000000_0/game.tw-pddl",
    }


def test_train_root_is_exact_train_not_validation_split():
    assert b.TRAIN_ROOT.name == "train"
    assert "valid_train" not in b.TRAIN_ROOT.as_posix()
    assert "valid_seen" not in b.TRAIN_ROOT.as_posix()
    assert "valid_unseen" not in b.TRAIN_ROOT.as_posix()


def test_hidden_constructor_paths_are_byte_identical():
    row=fake_row()
    for sham in (False,True):
        for s in ("p","q"):
            vals={b.render_donor_prompt(row,s,sham,a,h)[0] for a in (0,1) for h in (0,1)}
            assert len(vals)==1


def test_m0_pre_s_and_not_serialized():
    row=fake_row()
    m0,bit=b.m0_for(row)
    assert bit in (0,1)
    p,_=b.render_donor_prompt(row,"p",False,0,0)
    q,_=b.render_donor_prompt(row,"q",False,0,0)
    assert m0 not in p and m0 not in q
    assert f"A=0" not in p and f"H=0" not in p


def test_active_and_sham_order_contracts_and_lexical_symmetry():
    row=fake_row()
    p,_=b.render_donor_prompt(row,"p",False,0,0)
    q,_=b.render_donor_prompt(row,"q",False,1,1)
    sp,_=b.render_donor_prompt(row,"p",True,0,1)
    sq,_=b.render_donor_prompt(row,"q",True,1,0)
    assert p.count("ACTIVE ORDER: A THEN B")==1
    assert q.count("ACTIVE ORDER: B THEN A")==1
    assert "ARCHIVED ORDER:" not in p+q
    assert sp.count("ARCHIVED ORDER: A THEN B")==1 and "ACTIVE ORDER: NONE" in sp
    assert sq.count("ARCHIVED ORDER: B THEN A")==1 and "ACTIVE ORDER: NONE" in sq
    assert b._lex_bag(p)==b._lex_bag(q)
    assert b._lex_bag(sp)==b._lex_bag(sq)
    assert all(x.endswith(b.WASHOUT_SUFFIX) for x in (p,q,sp,sq))


def test_reset_context_has_no_order_semantics():
    text=b.reset_block(fake_row())
    assert "ACTIVE ORDER:" not in text
    assert "ARCHIVED ORDER:" not in text
    assert "<STATE_END>" in text


def test_opaque_endpoint_ids_are_lexical_not_semantic():
    row=fake_row()
    assigned=b.option_assignment(row)
    ep,orient=b.opaque_endpoints(assigned)
    assert list(ep)==["e0","e1"]
    assert list(ep.values())==sorted(ep.values())
    assert sorted(orient.values())==["p","q"]


def test_dependency_keys_are_unique_across_tasks():
    rows=[]
    for i in range(36):
        r=fake_row().copy()
        r["family"]=f"pick_two_obj_and_place-Book-None-Desk-{900+i}"
        r["trial"]=f"trial_T{i:06d}_0"
        r["reset_state_hash"]=f"state-{i}"
        r["game_path"]=f"train/{r['family']}/{r['trial']}/game.tw-pddl"
        rows.append(r)
    tasks,_=b.task_metadata(rows)
    assert len(tasks)==36
    for key in core.DEPENDENCY_KEY_TYPES:
        vals=[t.dependency_keys[key] for t in tasks]
        assert len(set(vals))==36
    frame=core.compile_pre_response_frame(tasks)
    assert len(frame.block_ids)==36
    assert len(frame.cells)==576
    counts={n:sum(frame.partition_by_block[x]==n for x in frame.block_ids) for n in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION")}
    assert counts=={"FIT":12,"PILOT":8,"SUPPORT":12,"CROSS_REALIZATION":4}
    assert core.verify_complete_cells(frame)


def test_exclusion_snapshot_ignores_own_output(tmp_path, monkeypatch):
    root=tmp_path/"results"
    design=root/"design"; science=root/"science"
    design.mkdir(parents=True); science.mkdir(parents=True)
    (design/"old.json").write_text('{"family":"pick_two_obj_and_place-Book-None-Desk-314"}')
    out=design/"planlatch_v7_9_train_input"
    out.mkdir()
    (out/"self.json").write_text('{"family":"pick_two_obj_and_place-CD-None-Safe-317"}')
    monkeypatch.setattr(b,"PROJECT_RESULTS_ROOTS",(design,science))
    snap=b.exclusion_snapshot(out)
    assert "pick_two_obj_and_place-Book-None-Desk-314" in snap["referenced_families"]
    assert "pick_two_obj_and_place-CD-None-Safe-317" not in snap["referenced_families"]


def test_driver_root_kind_and_hashes_are_canonical_constants():
    assert b.KIND==driver.ROOT_KIND
    assert len(b.DONOR_PROGRAM_HASH)==64
    assert len(b.WASHOUT_HASH)==64


def test_source_has_no_model_tokenizer_imports():
    src=Path("planlatch_v7_9_train_manifest_builder.py").read_text()
    forbidden=[
        "import torch","from torch","import transformers","from transformers",
        "AutoModel","AutoTokenizer","RealQwenRuntime","cuda()","device=\"cuda\"",
    ]
    for needle in forbidden:
        assert needle not in src
