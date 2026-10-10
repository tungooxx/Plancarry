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
2. **Not proven:** That independent deterministic reset-and-prefix replay could never create causally equivalent states; that two real ALFWorld environments demonstrably share a native mutable singleton; or that native RNG diverges. `downward_lib` calls involve native state, but inspection of the Fast Downward Python binding subsequently found a **per-call shared-library copy mechanism** that specifically mitigates library-global aliasing; see the correction below. Native interference is **not** established.
3. **Scope of existing checks:** PlanCarry's `bind_g0_ab_prefix_byte_equality.py` and PR#3/#4 regressions are synthetic toy only and correctly return `scientific_gate=NOT_AUTHORIZED`. Equal bytes furnished by a toy adapter do not prove that bytes capture the full actual TextWorld native state.
4. **Independent blocker:** The historical TRAIN model-consumption ledger is incomplete. Selection records labeled `model_calls=0` certify only those *selection operations*, not the global run history. Non-mention of a family in a bounded record or job-command scan does not certify unused source episodes.

## Minimal admissible decision route

- **Without touching TRAIN/LLM/confirmation:** Inspect the version-pinned native Fast Downward library bindings and use an entirely synthetic PDDL instance, if available, to characterize whether separate PDDL game handles share or isolate native state, including exact observation/action-menu/state/goal/terminal behavior. This is a backend feasibility probe, **not** source science. Verify the exact installed binding and per-load native-library isolation first; separate operating-system processes remain the simpler independently isolated audit boundary for any future real-backend replay.
- **If an actual independent complete-state/RNG snapshot or a demonstrably equivalent immutable deterministic replay mechanism exists:** Require independent provenance of the implementation, precommitted A/B reset identities, complete ordered action/observation traces, and state-transition receipts at the first meaningful fork. All comparisons must be external to the target LLM.
- **If no authoritative full-state witness or complete global historical TRAIN-consumption ledger exists:** G0 remains `BLOCKED_STATE_EQUIVALENCE` or `BLOCKED_SOURCE_PROVENANCE` **without any model calls**, per frozen terminal BIND-v0.3. No old route pairs, proxy public hashes, task-path aliases, corpus narrowing after outcomes, or v0.4 rescue.

## 2026-10-10 correction — Fast Downward native library isolation, pinned upstream

The TextWorld v1.7.0 requirement [`requirements-pddl.txt`](https://github.com/microsoft/TextWorld/blob/1.7.0/requirements-pddl.txt) lists `fast-downward-textworld` **without a package version pin**; therefore the following conclusion concerns the inspected upstream source tree, and **does not attest which binary was installed in historical PlanCarry runs**.

Pinned repository: [`MarcCote/downward`, branch `api_for_textworld` at commit `83217906b05391586041a49a9ffadad61b580223`](https://github.com/MarcCote/downward/tree/83217906b05391586041a49a9ffadad61b580223).

- [`src/search/interface.cc`](https://github.com/MarcCote/downward/blob/83217906b05391586041a49a9ffadad61b580223/src/search/interface.cc), blob `37e67b88057a43140b006b0561f8234ae1081734`, declares module-global `StateID state_id`, `StateRegistry* state_registry`, `vector<OperatorID> applicable_ops`, and task/plan buffers. `load_sas()` replaces any previous `state_registry` **within that loaded library instance**. It exports `get_state_id`/`set_state_id`, but these integers are registry-relative and **are not a portable full native-state serialization**.
- [`src/fast_downward/interface.py`](https://github.com/MarcCote/downward/blob/83217906b05391586041a49a9ffadad61b580223/src/fast_downward/interface.py), blob `b9b4cbdde30213297661a04e884e9ecea801f22a`, defines `load_lib()` to **copy `libdownward.so` to a fresh `TemporaryDirectory` and then `cdll.LoadLibrary` that unique copy**. Its own comment identifies avoiding concurrency problems as the intent. Thus independent normal `load_lib()` calls are designed to avoid sharing one native global registry; the C++ globals alone do **not** prove two PDDL instances overwrite each other. The Python binding initializes the common C APIs but does **not** expose a complete authenticated native snapshot/restore API or bind `get_state_id`/`set_state_id` in this inspected version.
- TextWorld [`PddlEnv.__init__`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/envs/pddl/pddl.py) invokes `fast_downward.load_lib()` on environment construction; this is the natural path to separate library copies for independently instantiated PDDL environments. Loaded implementation/binary and runtime behavior remain unverified in our current missing-dependency runner.

**Corrected isolation conclusion:** Under the inspected upstream implementation, separate `PddlEnv` constructors are expected to obtain distinct shared-library images; previous speculation that all same-process PDDL instances necessarily corrupt a single global native state would be **incorrect**. This source finding improves the feasibility assessment for parallel A/B resets, but it does **not** supply the required complete native-state/RNG equivalence witness, registry-independent clone and transition attestation, or historical TRAIN non-consumption authority. Thus `scientific_gate=NOT_AUTHORIZED` and A1's `NO_GO_FOR_G1_UNDER_CURRENT_G0_EVIDENCE` remain unchanged. Do not silently revise frozen BIND-v0.3 thresholds or conduct model/TRAIN calls.

## Decision

**Hold `NOT_ACCEPTED_FOR_TEST`.** The available source code identifies a concrete PDDL API gap; it is not evidence of an empirical BIND effect or an empirical BIND failure. Close the positive claim under the frozen G0 stop conditions if full-state authority and a complete historical model-use ledger cannot independently be established. Any eventual publication should describe the evidentiary identifiability constraint precisely, without claiming an experimentally refuted mechanism.

**Work performed:** GitHub upstream code inspection only. No TRAIN episode loaded, no TextWorld runtime instantiated, no language model, GPU, paid API, or confirmation access.
