# ReplayResidual causal estimands and identification boundary — V1 (pre-outcome)

**Status:** frozen before any terminal ReplayResidual representation-sanity or T1 result. This note defines what the preregistered stages can identify; it does not add or alter any scientific variable.

## 1. Scope and notation
For frozen family `f`, let `S_f` denote the cloned reset snapshot (world-state hash, current observation, admissible actions, task instruction, reset serialization). Let `a` denote a preregistered intervention arm. Let `Y_f^LPA(a)`, `Y_f^TS(a)`, and `Y_f^VA(a)` denote later-plan agreement, task success, and valid-action rate under that arm, using the same reset snapshot and ordinary persistent KV/session dynamics.

The primary LPA endpoint deliberately excludes the first post-reset action. If the uninterrupted reference actions are `a1..am`, `m>=2`, then

`LPA = (1/(m-1)) * sum_{j=2..m} I[rollout action_j == reference action_j AND pre-action world-state hash == reference hash_j]`.

Divergence, termination, or missing actions score zero at unmatched positions. Thus immediate next-action copying cannot contribute to the primary endpoint.

## 2. Representation sanity is not the causal T1 estimand
The representation-sanity stage asks whether the residual induced by replaying the model's own plan is temporally stable and plan-selective across t1/t2 relative to every frozen replay control. Its family aggregate margin, control gaps, and retrieval top-1 are **representation-feasibility/selectivity estimands only**. A sanity PASS licenses causal engineering; it does not establish causal sufficiency, persistence, task benefit, checkpointability, compactness, or generality.

## 3. Primary T1 paired interventional estimands
At the single globally selected development operating point `(layer*, alpha*)`, the active arm injects exactly once at the reset-prefix last-token site and the hook is removed permanently. All later actions and observations extend the same KV/session.

For each untouched confirmation family:

`d_no_patch(f) = Y_f^LPA(ACTIVE_PLAN_RESIDUAL) - Y_f^LPA(NO_PATCH)`.

Let the frozen specificity-control set be

`C_spec = {RANDOM_EQ_NORM, NEXT_ACTION_PRESERVED_LATE_NULL, UNRELATED_PLAN, SHUFFLED_PLAN, GENERIC_HISTORY}`.

Then

`d_specificity(f) = Y_f^LPA(ACTIVE_PLAN_RESIDUAL) - max_{c in C_spec} Y_f^LPA(c)`.

The max-control rule is prospective and family-matched. A positive `d_specificity` means the plan residual beats the strongest tested matched alternative for that family; it is not a decomposition proving that every other latent nuisance is absent.

Task-level supporting contrasts are also frozen: ACTIVE TaskSuccess, ACTIVE−NO_PATCH TaskSuccess, ACTIVE−max(RANDOM_EQ_NORM, NEXT_ACTION_PRESERVED_LATE_NULL, UNRELATED_PLAN) TaskSuccess, and ACTIVE valid-action rate relative to NO_PATCH.

## 4. Confirmation inference
The inference unit is the frozen family. Confirmation uses exactly source indices 32..51 (`n=20`), no replacement and no confirmation tuning. If the natural-trajectory gate reaches at least 16/20, **all 20 remain in primary denominators**; unqualified/unconstructible families receive zero LPA and non-positive pairwise differences and cannot count as sign successes.

Two co-primary exact one-sided Binomial/sign tests are frozen: `d_no_patch > 0` and `d_specificity > 0`, with zero/non-positive treated as failure. Holm step-down controls FWER at 0.05 across exactly those two tests. Statistical significance alone is insufficient: all preregistered effect, TaskSuccess, positive-family-fraction, and valid-action guards must also pass.

The sign/binomial calibration additionally presumes family units are sufficiently independent/exchangeable for that test. Because the cohort itself is prospectively fixed rather than sampled to represent every task/model/environment, a PASS is strongest as evidence on the preregistered cohort and protocol; broader generality requires the separate frozen replication stages.

## 5. Identification assumptions / engineering validity conditions
The paired intervention has a causal interpretation only while the following hold:

1. **Reset-state equality:** every arm starts from the exact cloned environment snapshot; world-state hash, observation, admissible actions, instruction, and reset serialization match.
2. **Single intervention:** the activation hook fires exactly once on the reset-prefix forward, then is permanently removed; no hidden reinjection or reset-prefix rebuild occurs.
3. **Persistent session:** committed action and observation tokens extend the same KV/session after reset.
4. **Exact token/trajectory semantics:** intervention and action scoring use the frozen exact token IDs/serialization; candidate scoring does not mutate the live cache.
5. **Matched intervention geometry:** nonzero residual/random controls are norm matched to the active residual before the common alpha; `RANDOM_EQ_NORM` tests generic activation-energy explanations.
6. **No cross-arm interference:** executing one cloned arm does not alter the potential outcome of another arm for the same family; families do not interfere with one another for inference.
7. **Prospective selection:** no outcome-dependent family replacement/filtering, control deletion, layer/site/scale selection, threshold relaxation, prompt/filler rescue, or model/benchmark switching occurs after outcomes.
8. **Endpoint fidelity:** first action is excluded from LPA and world-state hashes are checked, so route changes cannot masquerade as restoration of the original active plan.

Violation of these conditions is technical invalidity, not evidence for or against the scientific mechanism.

## 6. What the frozen controls falsify
- `NEXT_ACTION_PRESERVED_LATE_NULL`: strongest direct falsifier of the immediate-next-action / execution-boundary alternative; it preserves the first reference action while destroying later plan structure.
- `RANDOM_EQ_NORM`: tests generic activation magnitude/energy.
- `UNRELATED_PLAN`: tests plan-like content not belonging to the episode/family.
- `SHUFFLED_PLAN`: tests lexical content with destroyed plan order/structure.
- `GENERIC_HISTORY`: tests generic transcript/history information.
- `NO_PATCH`: identifies benefit over ordinary reset behavior.
- `ZERO_ADD` and `SELF_REPLACE`: engineering/plumbing sentinels, not primary specificity controls.
- `VISIBLE_TEXT_PLAN`: positive descriptive ceiling, not a matched hidden-state control.

No finite control set proves the absence of all alternative latent variables; the claim is specificity relative to these prospectively frozen alternatives.

## 7. Claim identified by a positive T1
If every frozen statistical and effect guard passes, the supported claim is:

> Under the preregistered Qwen3/ALFWorld reset protocol and ordinary persistent KV/session dynamics, a model-own episode-specific plan residual injected exactly once at reset is causally sufficient to improve first-action-excluded continuation of the original active plan, beyond the tested matched no-patch and plan-specificity controls.

This is a **causal sufficiency** claim for the tested intervention. It is not a necessity claim: the experiment does not show that removing the model's endogenous plan representation necessarily destroys continuation. It is not by itself a mediation claim, an independent-memory-substrate claim, or a claim of model/task/environment generality.

## 8. Conditional KV-mediation estimands
Only after prospectively supported primary T1, the frozen KV secondary uses the same primary families and operating point. For cache arm `X` and semantic condition `c`, let `Delta_X(c)=Y_X(c)-Y_D`, where `D` is the matched full-clean restore. With `C={NEXT_ACTION_PRESERVED_LATE_NULL, UNRELATED_PLAN, EQUAL_NORM_RANDOM}`:

- `TOTAL = Delta_A(PLAN) - max_{c in C} Delta_A(c)`
- `PROPAGATED = Delta_B(PLAN) - max_{c in C} Delta_B(c)`
- `DIRECT = Delta_C(PLAN) - max_{c in C} Delta_C(c)`

Controls are maximized **within the same cache arm** and never pooled. The exact one-sided family sign/binomial tests use Holm FWER 0.05 across TOTAL/PROPAGATED/DIRECT, with median >0 effect guards. TOTAL must pass before PROPAGATED or DIRECT can support localization.

This secondary can localize the supported effect within ordinary KV/session dynamics (reset-prefix/direct versus first-cycle propagated KV). It cannot establish a distinct non-KV persistent substrate. If TOTAL fails, localized positives do not count as mechanistic support.

## 9. External validity is separate from identification
Untouched replication, same-model cross-task `valid_unseen`, and distinct-model replication answer generalization questions. They import the frozen primary operating point with zero retuning and remain separate tables/estimands. They cannot rescue a null or invalid primary T1, and their outcomes are never pooled into primary confirmation significance.

## 10. Explicit non-claims
ReplayResidual does not claim first latent memory, first hidden-state transport, first activation steering, first state continuity, or first KV restoration. Even a positive complete evidence chain does not establish universal plan representations, causal necessity, a non-KV memory substrate, or unrestricted cross-model/environment generality.
