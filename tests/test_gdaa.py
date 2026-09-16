import inspect

import gdaa_evaluator as g


def obs(goal: str) -> str:
    return f"You are in a room.\nYour task is to: {goal}\n"


def test_exact_reference_route_is_positive():
    task = obs("put some book on sidetable.")
    cmds = ["go to desk 1", "go to sidetable 1"]
    assert g.gdaa_score(task, cmds, ["go to sidetable 1", "move book 1 to sidetable 1"]) is True


def test_alternate_route_can_be_gdaa_positive_while_exact_rpa_is_false():
    task = obs("put a toiletpaper in toiletpaperhanger.")
    cmds = ["go to sinkbasin 1", "go to toiletpaperhanger 1"]
    actions = ["go to toiletpaperhanger 1", "move toiletpaper 2 to toiletpaperhanger 1"]
    reference_first = "go to sinkbasin 1"
    assert g.first_progress_action(actions) != reference_first
    assert g.gdaa_score(task, cmds, actions) is True


def test_information_detour_is_ignored_before_direct_progress():
    task = obs("put some book on sidetable.")
    cmds = ["go to sidetable 1", "go to desk 1"]
    actions = ["examine book 1", "look", "inventory", "go to sidetable 1"]
    assert g.gdaa_score(task, cmds, actions) is True


def test_wrong_placement_recovery_remains_negative_despite_later_recovery():
    task = obs("put some book on sidetable.")
    cmds = ["move book 1 to desk 1", "go to sidetable 1"]
    actions = [
        "move book 1 to desk 1",
        "take book 1 from desk 1",
        "go to sidetable 1",
        "move book 1 to sidetable 1",
    ]
    # This trajectory could later succeed; GDAA intentionally scores only
    # immediate goal-directed continuation and never sees terminal success.
    assert g.gdaa_score(task, cmds, actions) is False


def test_wrong_route_failure_is_negative():
    task = obs("put some book on sidetable.")
    cmds = ["go to desk 1", "go to sidetable 1"]
    assert g.gdaa_score(task, cmds, ["go to desk 1"]) is False


def test_loop_is_negative():
    task = obs("put some book on sidetable.")
    cmds = ["go to desk 1", "go to sidetable 1"]
    assert g.gdaa_score(task, cmds, ["go to desk 1", "go to desk 1", "go to desk 1"]) is False


def test_toilet_does_not_match_toiletpaperhanger():
    task = obs("put some spraybottle on toilet.")
    cmds = ["go to toiletpaperhanger 1", "go to toilet 1"]
    positive = g.goal_directed_action_set(task, cmds)
    assert positive == frozenset({"go to toilet 1"})
    assert g.gdaa_score(task, cmds, ["go to toiletpaperhanger 1"]) is False


def test_multiple_exact_type_destinations_are_all_positive():
    task = obs("put some book on shelf.")
    cmds = ["go to shelf 1", "go to shelf 2", "go to sidetable 1"]
    positive = g.goal_directed_action_set(task, cmds)
    assert positive == frozenset({"go to shelf 1", "go to shelf 2"})
    assert g.gdaa_score(task, cmds, ["go to shelf 1"]) is True
    assert g.gdaa_score(task, cmds, ["go to shelf 2"]) is True


def test_direct_move_is_positive_when_admissible():
    task = obs("put a toiletpaper in toiletpaperhanger.")
    cmds = ["move toiletpaper 2 to toiletpaperhanger 1", "move toiletpaper 2 to toilet 1"]
    assert g.gdaa_score(task, cmds, ["move toiletpaper 2 to toiletpaperhanger 1"]) is True
    assert g.gdaa_score(task, cmds, ["move toiletpaper 2 to toilet 1"]) is False


def test_spaces_and_instance_numbers_are_normalized_exactly():
    task = obs("put some remote control on side table.")
    cmds = ["go to sidetable 2", "go to sofa 1"]
    assert g.parse_pick_and_place_goal(task) == ("remotecontrol", "sidetable")
    assert g.gdaa_score(task, cmds, ["go to sidetable 2"]) is True


def test_unparseable_goal_is_undefined_not_false():
    assert g.gdaa_score(obs("find the book."), ["go to shelf 1"], ["go to shelf 1"]) is None


def test_empty_exact_target_set_is_undefined_not_false():
    task = obs("put some book on sidetable.")
    assert g.gdaa_score(task, ["go to desk 1"], ["go to desk 1"]) is None


def test_scorer_has_no_success_reward_or_reference_input():
    params = set(inspect.signature(g.gdaa_score).parameters)
    forbidden = {"success", "reward", "won", "reference", "future_suffix", "expert_plan"}
    assert params.isdisjoint(forbidden)
