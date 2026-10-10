# PlanCarry — PSB-SYM-1 prospective symbolic-state feasibility protocol (exploratory proposal)

**Status:** `EXPLORATORY_ENGINEERING_PROPOSAL / NOT_FROZEN / NO_EXECUTION_AUTHORITY`  
**Prepared:** 2026-10-10, A1. **Not** BIND-v0.4, not a replacement sample for BIND-v0.3, and not a paper draft.  
**Lineage distinction:** frozen BIND-v0.3 ScientificDesign `80e19e85-2689-45a9-8455-18108070aaf8` (SHA `0fca9c1b177d1f41e0342f6d3748f35cd63cddf1c2dc38c5f3c2897e04716553`) is **TERMINAL / NO_G1** under its current G0 evidence. This proposal poses a *different*, narrower research estimand.

## One genuinely different question

On **prospectively created, version-pinned TextWorld symbolic games with independently verifiable state copies**, when a model has itself produced two goal-reaching route plans, does a **nonexecuting plan-identity binding presentation** improve *later intention-specific route adherence* compared to a **direct, equally informative, equally salient imperative plan reminder**?

- The new estimand is **symbolic fully observed task policy adherence**, **not** generalization to the historical ALFWorld-TRAIN PDDL corpus or proof of a general memory mechanism.
- Source-plan competence, actual task success, route-independent utility/regret, and donor-specific route adherence are distinct outcomes.
- A well-matched direct reminder with comparable or better effect defeats any **BIND-specific superiority** claim; never relabel this as proof the model cannot maintain plans.
- An environment where all routes are mechanically equivalent can only support a **preference/commitment** claim; never misreport the route preference as greater task reward.

## Backend feasibility reason for investigating this, not PDDL

Microsoft TextWorld release `1.7.0`:
- `textworld/envs/tw.py`, blob `8532f5733b7106299bff0b1d8731860ec68a4ab7`: concrete `TextWorldEnv.copy()` copies `GameState`, `request_infos`, `_prev_state`, `_moves`, and a separate `GameProgression.copy()`; underlying `Game` and `Inform7Game` are **shared references**, explicitly warned as soft copies. That is an available *candidate* clone implementation, not proof of comprehensive state independence.
- `textworld/generator/game.py`, `GameProgression.copy()`: copies state/facts and quest progressions, but reuses `game` and `_valid_actions` references. An external audit must establish these are immutable or not mutated by either rollout.
- Upstream `textworld/envs/tests/test_tw.py::TestTextWorldEnv.test_copy` checks copy both before/after reset and divergence after step.
- Unlike `textworld/envs/pddl/pddl.py` (original ALFWorld route), this symbolic environment implements `copy()`. The symbolic `.json` backend defaults to a placeholder text observation, so **a deterministic agent-visible renderer must be fixed before model use**.
- No native Fast Downward interpreter is required for `TextWorldEnv` symbolic state transitions; no claim is made about the old PDDL backend. Package/runtime availability and exact version/dependencies are preflight-only.

## Mandatory engineering-only G0S feasibility preflight, no model

1. Generate **one brand-new programmatic symbolic `.json` game** from a declared fixed `GameMaker` schema and immutable generator seed. It cannot originate from historical ALFWorld TRAIN. Record source file hash and generator source/tree revision; no use of preexisting VALID/TRAIN seeds or content.
2. `TextWorldEnv(request_infos)` loads that game, resets once, then creates independent A and B via `copy()` **before** any intervention. Record all underlying state facts/progression/quest states, public ordered legal menu, goals, counters and any RNG. Exercise same nonempty public prefix, including available informational commands, requiring byte-exact equality on each step.
3. Verify the **same snapshot was cloned** by changing the private progression in only one copy then verifying the other state and menus remain unchanged; reject if any shared mutable `Game` or `Inform7Game` object changes under stepping, or if quest/score/terminal state leaks across clones.
4. Use two alternate, legal, *mechanically verified* paths from the identical pre-fork state to a shared terminal goal, with the **same first actual action** and earliest divergent public action at index ≥2. Check goal success for each direction under the same frozen horizon and matched budget, no privileged future facts. This is engineering *route availability*, **not model-owned plan competence**.
5. Fix and review one **source-blind natural-language observation renderer** from objective/current directly observable player-reachable facts (not backend hidden facts, winning policy, route labels, or the GameMaker secret), plus exact ordered admissible commands. Both interventions and all controls receive byte-identical environment outputs.
6. The feasibility preflight stops at `BACKEND_FEASIBLE_STRUCTURAL_ONLY` or `BLOCKED_BACKEND_CLONE_OR_RENDERER`. This preflight has **no positive scientific outcome code**.

## New source and scientific gate, only after separate review

- Before ANY prospective source-model call: preregister generator revision and **32 exact ordered seeds/task IDs**, 2 independent one-shot source generation seeds per task, task/goal/renderer/simulator hashes, model/tokenizer/revision, identical backend caps, exact budgets, source plan ownership requirements, and split-resistant train/confirmation boundaries. Source plans **must be model-owned** and are never obtained from an oracle winning route shown to the agent.
- Each task must yield two independently model-authored successful plans for the same goal from identical full state and common actual action-observation prefix; first fork ≥2, no after-the-fact cherry picking. Count all **32** tasks including model failures and API failures. A suggested minimum 16/32 is merely a draft acceptance parameter until independently preregistered; do **not** carry the v0.3 thresholds into a new scientific estimand without power justification.
- For eligible pairs, randomize reciprocal A→B and B→A instructions. Primary comparator is **DIRECT_REMINDER** with the exact same future-plan semantic atoms, stated at comparable instruction priority and salience, matched model/context/token/storage/tool-call/latency budgets. Other preregistered nulls: strong summary, retrieval, identity shuffle, and passive text where informational parity permits.
- Primary estimand: **signed donor-route adherence ITT** at earliest later fork, including early deviations and missing forks in denominator. Report **separate** task goal success/regret, source competence, command legality, invalid turns, length/cost; paired confidence intervals and task-cluster sensitivity. A generic route win is not a goal win.
- Explicit falsification: no superiority over the direct reminder, worse goal success, violation of cost/information parity, inability to obtain valid model-owned source plans, or state-copy/render mismatch. Stop; no scope expansion or replacement.
- Hold untouched confirmation distinct from generator/dev pools. Independently verify leakage resistance, model budget, renderer, and blinded evaluator **before** experimental authority. No training, trial inference, GPU, confirmation, or claims authorized by this document.

## Terminal separation

**BIND-v0.3** remains `NO_GO_FOR_G1_UNDER_CURRENT_G0_EVIDENCE`; none of this work supplies its historical source ledger or PDDL full-state witness. `PSB-SYM-1` is a **separate exploratory methodological proposal**, not scientific design approval, not a workaround for the v0.3 no-rescue clause, and must undergo independent novelty/relevance attack and explicit Research OS authority before a model call.

**No-cost restrictions:** CPU-only dependency/source/API check and static preflight are permitted. Do not import an ALFWorld TRAIN source or run any language model, paid API, GPU, or confirmation set.
