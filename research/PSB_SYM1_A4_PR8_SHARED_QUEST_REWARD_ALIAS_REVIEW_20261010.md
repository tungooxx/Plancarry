# A4 independent blocker — PR #8 TextWorld quest reward A/B alias

**Date:** 2026-10-10  
**Role:** PlanCarry LLM A4, supporting engineering critic  
**Verdict:** `BLOCKED_REVIEW_FOR_PAIRED_SCIENTIFIC_OUTCOMES` until PR #8's `controller_copy` fully isolates mutable native `Game`/quest reward, not merely room names.  
**Science:** `NOT_AUTHORIZED`. This is not a model attack, no evidence of a BIND effect, and not a review vote for old frozen BIND-v0.3.

## Pinned inputs and independent execution

- Draft [PR #8](https://github.com/tungooxx/Plancarry/pull/8) head `a761062c5bb2e64d1c863a8106aeab53fd1e1d61`, includes `research/psb_sym1_blind_public_tool_gateway.py`. Stacked draft [PR #6](https://github.com/tungooxx/Plancarry/pull/6) exact head `088b91a217647550d0f01b6e7e10094a541f8e5a`.
- Exact native TextWorld 1.7.0 symbolic JSON fixture at original pinned commit `307ea0c0f10fb18223ae448d99a221d41660eba2`, SHA-256 `40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67`.
- **Independent GPU-LAB CPU run `local_10963984e2bd4733`, exit 0**, re-downloaded source and fixture from original pinned GitHub commits; no model or TRAIN.

## Critical negative test

```python
a = BlindSymbolicGateway(frozen_fixture)
b = a.controller_copy()
assert a._env._game is b._env._game
assert a._env._game.quests[0] is b._env._game_progression.quest_progressions[0].quest
# A and B execute the ordinary legal commands 'go east' and 'go north'
# to reach gallery; B's public room/menu is not changed by this probe.
a._env._game.quests[0].reward = 9  # original fixture reward is 1
# Each arm completes by ordinary native legal 'go east'.
assert agent_tool_dispatch(b, {'command':'act','action':'go east'})['score'] == 9
```

Observed both A and B terminal `done=true` and `score=9`, although only A's *privileged controller object* was deliberately mutated. The room-name sanitizer introduced by PR #6 did not detect the mutation. Native game/quest references remained shared between the A and B copies.

**Threat boundary:** The malicious `a._env._game...` operation requires trusted Python controller access; an evaluated LLM provided only the JSON-only `observe/act` entry point does not gain that power from this experiment. The vulnerability matters because the scientific experiment's **outcome isolation** could silently fail if any controller policy/transformation mutates shared `Game` or `Quest` objects; a room-only whitelist does not certify score independence.

## Matched independent-load control

Draft [PR #7](https://github.com/tungooxx/Plancarry/pull/7) uses independent `TextWorldEnv.load()` for each arm rather than `TextWorldEnv.copy()`. A4 added `test_mutating_a_shared_quest_reward_cannot_influence_b_score` at commit `628b948a24d7ebbac93fbcded939ee794618f758`; **10/10 native TextWorld 1.7.0 regression tests PASS** in independent CPU job `local_ef5639b1ff9b4686` (exit 0). After identical deliberate A quest reward change, A's terminal score is **9**, B's remains **1**. This is a concrete fix pattern, not proof that the draft PR #7 already meets every future agent/science requirement.

## Required remedy before PR #8 merge or model science

1. Make `controller_copy` duplicate the **entire mutable graph** of Game/Inform7/Quest/native progression, or reset independently from the SHA-locked fixture and replay the same authorized action prefix into each separately loaded instance. Prove both arms share exact current public/native state at the fork, but **no writable game/quest instances**.
2. Add A→B score/quest mutation negative regression beside existing room alias tests; check valid native actions, trajectory, score and terminal equivalence after unmutated prefix.
3. Keep `agent_tool_dispatch`'s strict whitelist and avoid any direct Python `gateway._env` exposure to evaluated model. This JSON adapter does not itself implement an OS sandbox.
4. Keep PR #6/#7/#8 in draft independent of frozen BIND-v0.3 design until code-owner review; never infer `G0_CERTIFIED` or `G1_AUTHORIZED` from these engineering tests.

**Review location:** [PR #8 issue comment](https://github.com/tungooxx/Plancarry/pull/8#issuecomment-6095709273). Formal `REQUEST_CHANGES` failed due GitHub self-review restriction for the connected identity, so the issue comment documents the substantive blocker and must not be misrepresented as an approved GitHub review.

**No model inference, paid GPU/API, ALFWorld TRAIN, confirmation data or paper work.**
