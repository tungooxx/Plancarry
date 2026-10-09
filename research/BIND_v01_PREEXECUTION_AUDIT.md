# PlanCarry BIND-v0.1 — PRE-EXECUTION REVIEW (2026-10-09)

**Status:** engineering/source audit only; **NOT scientific evidence, NOT approval for model/GPU execution**.  
**Research OS:** AgendaItem `5a119eb4-7823-4fbf-830e-2af951756413`, ScientificDesign `6c360b62-3ee3-4cf8-bcb3-26682b0db6aa` (frozen, `NOT_ACCEPTED_FOR_TEST`), peer-hidden independent attack batch `861f57bb-e003-411d-83c9-f1d90db4941c`.  
**Primary question:** Once a source model can act on two distinct A/B later plans, can a *nonexecuting* state-to-policy interface make a correct stored commitment causally affect *later* behavior after a real reset, beyond strongest equally provisioned memory/retrieval alternatives?

This document is a **design audit**, not a protocol amendment. Reviewer acceptance and new frozen version are necessary before any science run. Preserve prior Decision-Quotient/PlanFrame/PlanLatch failures; never rename/retune a failed mechanism.

## Source-code inspection (GitHub main)

- `alfworld_binding_runner.py` (blob `174378c6a61a9a4b0d982fa925c054d5f1ae90bb`), lines 48–56: `BINDING_WRAPPER` explicitly instructs the model to **execute `intended_next_action` as its first non-information action**. This tests first-action compliance, not same-first-action / later-branch A↔B transfer. Do **not** reuse this arm as BIND-v0.1's treatment. Its `iaa`, `gdaa`, `rpa` outcomes and fixed `pick_and_place_simple` pool are not BIND-v0.1 primary endpoints.
- `alfworld_binding_runner.py` lines 65–79, 390–425: fixed hashed selection from `train/pick_and_place_simple`, expected TRAIN population **790** and legacy scan cap **180**, with cohort hashes/salts from August 2026. **Not a newly untouched population by assertion**. Inventory exact historical game files/episodes consumed in all earlier development, review, and pilot outputs before freezing any new 32 candidates; identify a demonstrably unconsumed prospective source or stop G1.
- `alfworld_binding_runner.py` lines 203–246: eligibility requires previously observed success, a specific intended-next-action and direct goal-progress admissibility. No bilateral competence or fixed-first-action/differing-later-branch criterion is present.
- `alfworld_cohort_runner.py` and `alfworld_runtime.py`: deterministic replay and all-arm state identity support reuse after *new* admissibility guards and source-pair validator. `state_hash` sorts admissible command names; tool calls select **list indices**. Compare **ordered** command list in addition to state hash, and record full list before each paired call. Two identical set/hash values alone do not ensure matching index-to-command mapping.
- `alfworld_qualify.py` makes model calls through OpenAI-compatible Ollama interface; source competence requires actual newly executed A/B behaviors, **not** merely evaluator-defined labels or strings.

## Mandatory preflight blockers (independent review targets)

1. **Constructibility / task legitimacy.** Same reset world state, task objective and *naturally shared* immediate action, but later A/B procedural alternatives must be both feasible and distinguishable. In classic `pick_and_place_simple`, only one goal destination may be legal or goal-consistent; do not fabricate an opposite "plan" whose outcome violates the task. Pilot constructibility without using held-out data and without selecting only favorable post-reset outcomes.
2. **Avoid post-treatment selection.** The qualified subset may be chosen using **pre-treatment** bilateral source competence, not BIND success. If BIND changes the shared first action, do not drop the trial; record first-action deviation as treatment behavior, and score later-branch estimand with a frozen intention-to-treat rule. Dropping it would induce selection bias.
3. **No actuator laundering.** BIND is a context/interface manipulation only. It may not supply a forced action, action masking/filtering/reranking, hidden future, privileged expert plan, direct `choose_action(index)` intervention, or extra calls. Preserve complete ordered publicly admissible action set. Guard native prompt tokens, bytes, calls, elapsed time and evidence access.
4. **Strong null parity.** PASSIVE, binding-content NOOP, equivalent flat JSON, high-quality summary, best available query-adaptive retrieval, action-only and identity-destroying shuffled plan are required. Retrieval's persistent store/index construction and query-time byte/call/latency cost must be explicitly accounted; do not weaken it to a fixed static extract.
5. **Actual continuation metric.** Primary endpoint is **first-action-excluded later branch choice under full action competition**, not `intended_next_action` adherence, first-command GDAA, rank/logit or faithful playback of one arbitrary uninterrupted route. Record terminal task success separately; count other valid goal-achieving routes as valid success.
6. **Provenance.** Freeze model revision, API/tool formatting, decoding, dataset+game hashes, ordered action sets, first 32 attempted population order, independent evaluator, arm ordering and statistical rules **before observing results**. A reused `train` path is insufficient to prove noncontamination.

## Three user-authorized stopping gates

| Gate | Development decision rule in frozen v0.1 | Interpretation |
| --- | --- | --- |
| **G1 SOURCE** | First **32** verifiably unused TRAIN A/B attempted pairs, at least **16** bilateral-competent genuine later-branch pairs | Feasibility only; no treatment success claim |
| **G2 CAUSAL** | Both A→B and B→A at least **+20 percentage points** donor-specific later-branch improvement over strongest identity-destroying matched control, with terminal success loss at most **10 pp** | Development-screen only; matched uncertainty must be reported |
| **G3 BASELINE** | Untouched independent confirmation at least **+10 pp** against best information-/token-/call-/latency-matched memory/retrieval baseline; terminal success loss at most **5 pp** | Do not claim publication-grade confirmation if power/CI or baseline validity is inadequate |

**Power warning:** at `n=16` paired binary cases, a net **4/16 = 25 pp** advantage may come from four treatment-only wins and zero losses. A *two-sided exact paired discordance test* then has **p = 0.125**, so crossing +20 pp does not establish a confident effect. Similarly two net gains yield **12.5 pp**, with p=0.5 in the zero-loss extreme. Predefine confirmatory sample size/power, confidence interval and clinically/practically meaningful estimand *independently* before G3. An exploratory gate may reject a weak method; it cannot certify top-tier evidence.

## Proposed zero-compute reviewer order

1. **Necessity attacker**: can any pre-reset commitment satisfy the same-first-action later-different-goal contrast on genuine tasks under public information? Is source competence feasible without postselection?
2. **Causal-identifiability attacker**: are paired interventions equivalent in task goal, memory facts, instruction tokens, API privileges, admissible actions, first-action handling and storage access? Can instruction-following alone account for effect?
3. **Degenerate-solution attacker**: could a matched flat text instruction, query retrieval, repeated direct prompt, future-blind code, goal-reconstruction or tool-call artifact reproduce all observed changes? Do any outcomes select on the treatment?
4. **Planner synthesis**: freeze any design revision **before data use**; only if accepted for test, authorize a **new** G1 TRAIN population/provenance and executable technical tests, with zero paid compute.

## Reuse decision

**Reusable as engineering starting points:** `alfworld_runtime.py` deterministic replay + observable commands, `alfworld_qualify.py` open-model runner, `alfworld_cohort_runner.py` budget accounting/replay guards, `gdaa_evaluator.py` route-independent *secondary* metric, paired statistical helper functions. These are not BIND-v0.1 scientific validators as-is.

**Must be replaced/adapted after review:** legacy BINDING_WRAPPER; eligibility; first-action IAA/GDAA/RPA primary endpoints; candidate-split manifest; bilateral A/B source builder; reciprocal swap+identity-destroying matched controls; nonexecuting instruction and ordered-command fidelity audit; independent confirmation gate.

**Current authorized action:** request three **different** reviewers through Research OS planner A1. Reviewer-independent attacks are NOT satisfied by this document or by the design author's self-review. No G1 model calls, GPU jobs, or paid APIs were initiated.
