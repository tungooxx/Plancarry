# PSB-SYM-1 — A4 independent native clone and public-renderer audit

**Date:** 2026-10-10  
**Reviewer:** PlanCarry LLM A4, independent engineering review  
**Verdict:** **BACKEND_FEASIBLE_STRUCTURAL_ONLY**, with **confirmed shared-reference renderer-contamination risk if any controller mutates the shared Game object**.  
**Science authority:** `NOT_AUTHORIZED`. No new scientific BIND-v0.3 G0 PASS, PSB-SYM-1 accepted ScientificDesign, or LLM source competence claim.

## Reproduction, pinned inputs

- Frozen game `research/fixtures/psb_sym1_prospective_frozen_game.json`, size **17,590 bytes**, SHA-256 **`40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67`**, retrieved from GitHub at fixture commit `307ea0c0f10fb18223ae448d99a221d41660eba2`.
- Runner `research/psb_sym1_textworld_native_copy_preflight.py` pinned to commit `407bcaa5bfa6adfb0caba43d8a2e6d9fa04ffcdc`.
- Backend: official `TextWorld 1.7.0` symbolic `textworld.envs.tw.TextWorldEnv` imported from A1's isolated CPU Python virtualenv; no PDDL or ALFWorld TRAIN.
- **A4 independent CPU job `local_58d6d654c2fc467a`, exit 0**: fetched independently from the two immutable URLs, rehashed fixture, ran `native_preflight`, then built **two additional fresh independent copies** from the fixture. It was not a transcription of A1's JSON report.
- **A4 negative-control CPU job `local_7b0e8aa896cf4c43`, exit 0**: independently re-fetched pinned inputs, isolated copies, checked action-only changes, induced an explicit shared-reference mutation and tested public rendering/hidden-route suppression.
- Both jobs: **zero model calls, zero GPU, no paid API, no ALFWorld TRAIN, no confirmation**.

## Checks and observed outcomes

| Test | Verified result | What it establishes |
| --- | --- | --- |
| Exact fixture bytes match precommitted hash | PASS | Prevents replay against a silently regenerated game in these runs |
| Same reset, `go east` then `look` | PASS | Identical native captured progression/public rendering at the shared prefix |
| A fork `go north`, `go east`; B fork `go east`, `go north` | PASS | Both mechanically reach public goal, **score 1**, **4 total actions** per arm |
| Separate `GameProgression` objects | PASS | `a._game_progression is not b._game_progression` |
| Normal A native `go east` changes B captured projection | NEGATIVE, as desired | B projection stayed unchanged under native update |
| `a._game is b._game` | **TRUE** | Underlying `Game` remains shared |
| `a._inform7 is b._inform7` | **TRUE** | Renderer-side helper remains shared |
| `a._game_progression.valid_actions is b._game_progression.valid_actions` immediately after copy | **TRUE** | Shared list reference at copy time; upstream `GameProgression.update()` replaces the list on native action |
| Directly set `a._game.infos['r_0'].name` to `A4_SPOOFED_ROOM` | **REPRODUCIBLE PEER RENDER CHANGE** | `render_public(b)` prints `Current room: A4_SPOOFED_ROOM`, despite B not moving |
| Restore original shared room name | PASS | B renderer returns to `Current room: foyer` |
| Add sentinel `SECRET_ROUTE_DO_NOT_SHOW` to shared `a._game.metadata['walkthrough']` | PASS for narrow renderer | The sentinel was **absent** from `render_public(b)` |
| Inspect native `env.state` keys | **PRIVILEGED DATA EXISTS** | `game`, `facts`, `_facts`, `_winning_policy`, `_game_progression`, `_valid_actions`, `_valid_commands` are present; these must not become model-facing tools or prompt fields |

Public renderer emitted by original fixture at reset:

```text
Goal: Reach the vault.
Current room: foyer
Available actions (in native order):
- go east
- inventory
- look
```

After a **deliberate privileged mutation** of the shared room-name lookup in A, *without any B action*, that same renderer emitted `Current room: A4_SPOOFED_ROOM`. This is **not** spontaneous leakage observed under ordinary `step()`; it demonstrates that clone independence is only qualified by *no writes to soft-shared game/renderer data*.

## Upstream mechanism and security boundary

In pinned [`microsoft/TextWorld` tag `1.7.0`, `textworld/envs/tw.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/envs/tw.py) (GitHub blob `8532f5733b7106299bff0b1d8731860ec68a4ab7`), `TextWorldEnv.copy()` assigns **references** `env._game = self._game`, `env._inform7 = self._inform7`, and copies its `GameProgression`. The method explicitly warns that the first two objects are soft copies.

In [`textworld/generator/game.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/generator/game.py) (blob `281be003a36902f022ca5f302d5bbc714a4ad992`), `GameProgression.copy()` deep-copies the logical `State` while initially assigning `gp._valid_actions = self._valid_actions`; a normal `update(action)` replaces `_valid_actions` rather than mutating that shared list in place. This explains why original native route steps showed independent progression in the checked fixture.

The tested `render_public(env)` accesses the public objective, the player-room position extracted from privileged progression facts, **room-name metadata from shared `env._game.infos`**, and native ordered legal-command list. It emits only goal, current room, and ordered commands. This is a **narrow whitelist projection**, not generic safe serialization of `env.state`. Private quests, solver-policy graphs, original game world, and native facts remain accessible to trusted engineering code. Any model tool that exposes `env.state`, `Game`, `GameProgression`, `_winning_policy`, `policy_commands`, `facts`, native debugger contents, or exception payloads could defeat the planned blind-source separation.

## Interpretation and required next gates

**Confirmed limited feasibility:** For this pinned single symbolic game and *ordinary tested native `step` calls*, the two forks follow a common public prefix and independently reach the same goal without observed cross-step corruption.

**Not established:**

1. Full native-state and RNG equivalence for arbitrary TextWorld games, let alone ALFWorld's distinct **PDDL** backend; this game is deterministic-looking symbolic `TextWorldEnv`, not PDDL.
2. Independence if controller-level code writes shared `Game` or `Inform7Game` objects; adversarial test demonstrates a real renderer-contamination pathway under such writes.
3. Confidentiality for any model-facing interface that returns the full `env.state` dictionary; our whitelist renderer is narrower and no agent-facing runtime is currently wired.
4. Competent **model-authored** bilateral plans, naturally valid fork cohorts, confirmation separation, sampling/power, and strong fair `DIRECT_REMINDER` null. Both winning routes are manually specified mechanical paths on **one** frozen fixture.
5. The historical TRAIN consumption ledger and complete ALFWorld PDDL full-state/RNG attestation required by the **terminal frozen BIND-v0.3**. A new prospective symbolic estimand does not retroactively rescue that design.

Before any PSB-SYM-1 model or scientific execution approval: (i) freeze an agent/tool boundary that returns **only** whitelist renderer bytes and legal-action responses; do not reveal internal `GameState`; (ii) freeze room-name mapping from a trusted immutable fixture or separate the soft-shared `Game/Inform7Game` objects, and test branch-adversarial mutation rejection; (iii) include blind sanitizer tests for metadata, walkthrough, quest, policy, graph, and exceptions, not merely a positive sample; (iv) independently review any new **ScientificDesign** for prospectively generated symbolic tasks and its fair direct-reminder null, cohort, statistical power and permission gates; (v) keep BIND-v0.3 **NO_GO_FOR_G1_UNDER_CURRENT_G0_EVIDENCE** until original G0 prerequisites are actually attested.

## Review decision

**`BACKEND_FEASIBLE_STRUCTURAL_ONLY`** is the narrow warranted verdict. Mechanical clone, prefix, routes and public renderer have been independently reproduced on the pinned fixture; **the renderer data lineage is not isolated from arbitrary writes to shared `Game` metadata**, and the existence of oracle-bearing native keys makes model-facing interface whitelisting mandatory. A1's current single-fixture preflight can be retained as an engineering feasibility result; it must not be promoted into a blind-agent or causal experiment without the specified corrections and independent scientific design gate.

**Independent review WorkItem:** `d6090712-5cc6-4f3c-a853-f56311d8c3cf`. **No science review quorum claim.**
