# PlanCarry BIND-v0.3 — TextWorld 1.7.0 PDDL full-state cloning feasibility review

**Date:** 2026-10-10  
**Role:** LLM A4, read-only static backend/API review  
**Scope:** Frozen BIND-v0.3 ScientificDesign `80e19e85-2689-45a9-8455-18108070aaf8` (SHA `0fca9c1b177d1f41e0342f6d3748f35cd63cddf1c2dc38c5f3c2897e04716553`), G0 full-state-equivalence prerequisite.  
**Scientific result:** `NOT_ASSESSED`; G0 remains `BLOCKED_STATE_EQUIVALENCE` and `BLOCKED_SOURCE_PROVENANCE`. This record is **not** a G1 execution permit or proof that cloning is mathematically impossible.

## Pinning and direct source facts

All upstream source inspection is pinned to the Microsoft TextWorld **1.7.0** release tag, not merely its moving `main` branch:

| Source | GitHub blob SHA | Relevant fact |
| --- | --- | --- |
| [`textworld/core.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/core.py) | `69ad26ff9ab9b6641ad3421152842c06532c4336` | Abstract `Environment.copy()` and `Wrapper.copy()` raise `NotImplementedError`; `GameState.copy()` deep-copies the **reported GameState**, not the backend engine. |
| [`textworld/envs/pddl/pddl.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/envs/pddl/pddl.py) | `a06b138f8b9b76c8c29bfbba5b9f1af0a24b9bf6` | `PddlEnv(Environment)` implements `load/reset/step` but **does not override `copy()`**, nor expose a public save-state/restore-state method. Therefore the inherited `Environment.copy()` does not clone this PDDL environment. |
| [`textworld/gym/envs/textworld_batch.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/gym/envs/textworld_batch.py) | `75ae563edb44f739a5a8f61e4a2f47f482581599` | The `TextworldBatchGymEnv` adapter used through `textworld.gym.make` exposes `reset/step/close`, with no demonstrated full PDDL state snapshot/clone API. |
| [`textworld/envs/pddl/logic/__init__.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/envs/pddl/logic/__init__.py) | `41c5183572d1aa89e927727fadacf46d333700fc` | `PddlState` mutates Fast Downward native interface via `load_sas`, `load_sas_replan`, `apply_operator`, `get_state`, and `get_applicable_operators`. No authenticated per-instance complete state export/restore is established by these calls. |

The PlanCarry adapter [`alfworld_runtime.py`](https://github.com/tungooxx/Plancarry/blob/research/bind-v02-source-custody-20261010/alfworld_runtime.py) initializes `textworld.gym.register_games(...batch_size=1, asynchronous=False)` and uses the legacy `state_hash`, whose input sorts the public admissible-command list and includes public observations, facts, score and done, but not an authenticated whole native PDDL state/RNG snapshot. This hash cannot alone satisfy G0 full-state authority.

## Evidence boundary

1. **Supported static conclusion:** No public clone/export-and-restore implementation was identified in the inspected TextWorld 1.7.0 PDDL environment, the batch adapter, or the original PlanCarry wrapper. Abstract `Environment.copy()` documentation must **not** be represented as concrete `PddlEnv.copy()` capability.
2. **Not proven:** That independent deterministic reset-and-prefix replay could never create causally equivalent states; that two real ALFWorld environments demonstrably share a native mutable singleton; or that native RNG diverges. `downward_lib` calls raise an **isolation hypothesis to test**, not established interference.
3. **Scope of existing checks:** PlanCarry's `bind_g0_ab_prefix_byte_equality.py` and PR#3/#4 regressions are synthetic toy only and correctly return `scientific_gate=NOT_AUTHORIZED`. Equal bytes furnished by a toy adapter do not prove that bytes capture the full actual TextWorld native state.
4. **Independent blocker:** The historical TRAIN model-consumption ledger is incomplete. Selection records labeled `model_calls=0` certify only those *selection operations*, not the global run history. Non-mention of a family in a bounded record or job-command scan does not certify unused source episodes.

## Minimal admissible decision route

- **Without touching TRAIN/LLM/confirmation:** Inspect the version-pinned native Fast Downward library bindings and use an entirely synthetic PDDL instance, if available, to characterize whether separate PDDL game handles share or isolate native state, including exact observation/action-menu/state/goal/terminal behavior. This is a backend feasibility probe, **not** source science. Prefer isolated operating-system processes when native in-process aliasing is unverified.
- **If an actual independent complete-state/RNG snapshot or a demonstrably equivalent immutable deterministic replay mechanism exists:** Require independent provenance of the implementation, precommitted A/B reset identities, complete ordered action/observation traces, and state-transition receipts at the first meaningful fork. All comparisons must be external to the target LLM.
- **If no authoritative full-state witness or complete global historical TRAIN-consumption ledger exists:** G0 remains `BLOCKED_STATE_EQUIVALENCE` or `BLOCKED_SOURCE_PROVENANCE` **without any model calls**, per frozen terminal BIND-v0.3. No old route pairs, proxy public hashes, task-path aliases, corpus narrowing after outcomes, or v0.4 rescue.

## Decision

**Hold `NOT_ACCEPTED_FOR_TEST`.** The available source code identifies a concrete PDDL API gap; it is not evidence of an empirical BIND effect or an empirical BIND failure. Close the positive claim under the frozen G0 stop conditions if full-state authority and a complete historical model-use ledger cannot independently be established. Any eventual publication should describe the evidentiary identifiability constraint precisely, without claiming an experimentally refuted mechanism.

**Work performed:** GitHub upstream code inspection only. No TRAIN episode loaded, no TextWorld runtime instantiated, no language model, GPU, paid API, or confirmation access.
