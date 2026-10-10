# PlanCarry PSB-SYM-1 — A4 bounded JSON action-horizon patch for draft PR #10

**Date:** 2026-10-10  
**Role:** A4 engineering reviewer, independent negative reproduction and minimal follow-up patch  
**Science:** `NOT_AUTHORIZED`; no model, G0/G1/G2/G3, ALFWorld TRAIN or confirmation touched.

## Independent issue reproduction

PR #10 head `71d230c51e87855dbd11b4a7b33cc897a09767bf`, stacked on isolated public bridge PR #7, whitelists JSON `observe` and `act`, but has no finite **valid-action horizon**. A4 independently retrieved original SHA-locked TextWorld 1.7.0 symbolic fixture `40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67`.

**CPU job `local_871e4613c2ce4a8d`**, exit 0: sending 24 valid `{"command":"act","action":"look"}` requests all returned `status="OK"`, `done=false`, `score=0`. Native `_moves=24`, no budget cap. A/B comparisons that later permit unconstrained calls can have uncontrolled or unequal episode length even when native branch-copy isolation is correct. A secondary API issue: the helper `dispatch(instance,{"command":[]})` raised `TypeError`; `dispatch_json()` caught it, so it did **not** expose a JSON remote traceback.

## Engineering-only patch (stacked draft)

Branch `research/psb-sym1-action-budget-a4-20261010`, based **exactly on PR #10 head** `71d230c51e87855dbd11b4a7b33cc897a09767bf`.

- `research/psb_sym1_isolated_json_dispatch.py`: introduce `MAX_EPISODE_ACTIONS=12`; use trusted native `_moves` to enforce the same finite limit on each separate environment. On the twelfth valid action, return `done=true`; subsequent valid `act` requests return `{"status":"TERMINAL"}`. Invalid action requests do not consume native moves. Never send `_moves` itself to agent. Check direct helper `command` type before set membership; malformed command now produces `INVALID_REQUEST` instead of a raw `TypeError`.
- `tests/test_psb_sym1_isolated_json_dispatch.py`: four new native tests for 12 `look` requests, independent A/B turn caps, 12 `inventory` requests, strict `done=true/score=0` timeout, malformed nonstring command handling and untouched normal 4-action winner.

**Important:** `12` is an **engineering-only conservative fixture-specific proposed default**, not a preregistered scientific horizon; A1 must decide and freeze per-arm equal budget with the future independently reviewed PSB ScientificDesign before any LLM inference. For this specific single-score-one fixture, `done=true,score=0` denotes budget exhaustion **not goal success**; never equate `done` with positive goal outcome. The four-field protocol is preserved; no extra hidden state appears.

## Native CPU verification

**GPU-LAB job `local_42e363973db64498`, exit 0**: independent re-download of the exact patched source/tests at git commit `cc5aa183bddbede41b456af04da1bb1ca5c3ca60`, upstream isolated public bridge at PR #7 commit `8cf24e14501156e55ccd0ebbf7e3c268231dfe47`, and frozen fixture at immutable commit `307ea0c0f10fb18223ae448d99a221d41660eba2`. Native **TextWorld 1.7.0** result **14/14 tests PASS** (10 previous native JSON regressions plus 4 budget/schema regressions); fixture SHA-256 independently verified unchanged.

Limitations: no process sandbox / production model API, source controlled by trusted host, no independent native RNG certificate, no full ALFWorld PDDL clone, no strong direct-reminder matched hypothesis test or model-owned plans. Original BIND-v0.3 remains `NO_GO_FOR_G1_UNDER_CURRENT_G0_EVIDENCE`; PSB-SYM-1 remains a distinct prospective design awaiting independent review.

**Merge ordering:** PR #7 (fresh-load isolated native bridge) → PR #10 (serialized JSON gateway) → this bounded-turn draft; independently review and preregister an appropriate cap before scientific execution.
