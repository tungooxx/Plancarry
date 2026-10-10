# PlanCarry — A4 independent eight-step native PDDL feedback parity audit

**Date:** 2026-10-11 (KST)  
**Reviewer:** LLM A4 · independent engineering audit  
**Result:** `PASS_TECHNICAL_PARITY_11_OF_11` — **not** a scientific BIND-v0.3 G0 acceptance, RNG certificate, or model efficacy result.

## Primary observations

Actual local GPU-LAB **CPU job `local_03bb180eab4e45bc`**, exit code **0**. Independently re-executed 11 **already historically environment-inspected** original ALFWorld PDDL games. For each game, opened **two freshly loaded** `TextWorld 1.7.0 PddlEnv` native Fast Downward instances and applied an identical deterministic eight-legal-action path to both.

**Total 176 native actions = 11 games × 2 arms × 8 actions.** Compared at RESET and after every action using the previously pinned native engineering `snap()` projection:

- SHA of the *ordered native Downward Atom names* and native count, from `downward_lib.get_state()`;
- SHA of the logical PDDL facts and TextWorld state `_facts`;
- exact **ordered** public `admissible_commands`;
- SHA of native TextWorld feedback bytes; PDDL goal flag.

**All 11/11 games showed exact pairwise equality at each checked step.** The sampled action program always used the legal `look` first and then selected legal `go to ...` commands with a deterministic position-specific indexing policy, skipping the immediate previously chosen command; every action was checked against the current native menu. Distinct native Atom states over the nine captured snapshots for game indices 0–10: **[9,5,9,8,5,5,9,9,7,9,9]**. Distinct feedback SHA snapshots: **[9,5,9,9,5,5,9,9,8,9,9]**.

A lexical scan of the `grammar` field of the same 11 original PDDL source JSON files found zero literal occurrences for `random`, `rng`, `np.random`, `choice(`, `seed`, and `time.time`. **This is not a control-flow proof and does not exclude indirect randomness** through imported Python/C++ or other runtime resources.

Original source and cohort controls inherited from A1's pinned independently inspected original-11 harness:

- Original ALFWorld archive SHA-256 `5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`.
- 11 inspected source-path matrix SHA-256 `ea9376a6c86c41afb24dc00e14d5ff5849b44e4900e2f8a1ebfc60deea4201d5`.
- Helper source `plancarry_assets/bind_process_cow_multistep_a1.py` protected SHA-256 `344f3eed27de044ac0978da1779e5b4c68db0f8ef8c19ce89c116174c2fd6214`; this helper explicitly checks archive and matrix, original TRAIN path containment and native legal commands. A4 **did not use new/uninspected source games, original privileged solution plans or the confirmation split**.
- Runtime venv `/workspace/local-vlm/.cache/plancarry-a1-symbolic-tw170-env/bin/python`; Fast Downward shared-library load requires `TMPDIR/TMP/TEMP=/workspace/local-vlm/plancarry_assets/tmp_exec`. First attempted job `local_7276133df2f949d8` failed on the known `/tmp` NOEXEC limitation before completing any evaluation; reran unchanged parity test with correct temporary directory and got PASS.
- Explicit **0 model calls**, no GPU/paid API, no paper and no experiment trial.

## Corroborating code inspection — why scope matters

In pinned Microsoft TextWorld `1.7.0`, [`textworld/envs/pddl/pddl.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/envs/pddl/pddl.py), `PddlEnv.step()` invokes `_pddl_state.apply(self._last_action)`, then derives natural-language feedback via `_logic.grammar.derive(...)`.

In pinned modified Fast Downward `MarcCote/downward` commit `83217906b05391586041a49a9ffadad61b580223`:

- [`src/search/interface.cc`](https://github.com/MarcCote/downward/blob/83217906b05391586041a49a9ffadad61b580223/src/search/interface.cc) `apply_operator()` invokes `StateRegistry::get_successor_state(current_state, op)`.
- [`src/search/state_registry.cc`](https://github.com/MarcCote/downward/blob/83217906b05391586041a49a9ffadad61b580223/src/search/state_registry.cc) applies conditional operator effects and axiom evaluation to the packed state, with no **direct** RNG reference in that function.
- [`textworld/envs/pddl/textgen/__init__.py`](https://github.com/microsoft/TextWorld/blob/1.7.0/textworld/envs/pddl/textgen/__init__.py) can evaluate grammar expressions; lexical source scanning is **not** a complete certificate for all code paths.
- A1 separately discovered and repaired the `os.fork()` CPython **module-global** RNG auto-reseed in a bounded native test. That technical repair only covers the explicitly snapshotted Python RNG, **not** all native/C++ or external RNG state.

The current A4 test evaluates **fresh load vs fresh load**, not copy-on-write `fork` vs a fresh run. It is a longer-path reproducibility check complementing A1's earlier **11/11 three-step COW-vs-fresh** validation, not a replacement for the frozen complete native state and RNG equivalence requirement.

## Reviewer conclusion and gate

For these 11 previously inspected original PDDL game files and sampled 8-action paths, the original native environment's **exposed logical/Atom state, ordered legal action menu and feedback** are reproducible stepwise. No independent evidence here attests hidden C++ RNG, arbitrary state not covered by `snap()`, historical global request/response model-source consumption provenance, or model-authored bilateral plans.

**BIND-v0.3 ScientificDesign `80e19e85-2689-45a9-8455-18108070aaf8` remains `NO_GO_FOR_G1_UNDER_CURRENT_G0_EVIDENCE`.** Preserve the already submitted A4 scientific attack and its hidden review protocol; do not count this engineering audit as an independent frozen attack or authorize LLM inference.
