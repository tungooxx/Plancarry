# PlanCarry PR #2 — two-game reproducible path-hash counterexample (2026-10-10)

**Review verdict:** changes required before this guard can verify the historical frozen Binding-180 pool. **Engineering-only, NOT G0/G1 approval.**

Checked PR #2 **head `73a7f4d4c708690b005524e25afdf7744a40f901`**. Its 12/12 synthetic tests pass, but `research/bind_source_selection_guard.py` accepts only `train/.../game.tw-pddl` relative paths and computes `SHA256(binding_salt + "\\n" + relative_path)`. The historical frozen `alfworld_binding_runner.py` computed `SHA256(binding_salt + "\\n" + ABSOLUTE_PATH)`. The prefix changes the SHA ranking: there is no path-invariant SHA-256 ordering.

## Minimal fixture, extracted from the exact ALFWorld 0.4.2 790-game archive

```text
binding_salt = plancarry-binding-v1-2026-08-18
original_source_root = /opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/

A = train/pick_and_place_simple-Pillow-None-ArmChair-214/trial_T20190909_010401_711637/game.tw-pddl
B = train/pick_and_place_simple-Box-None-ArmChair-217/trial_T20190907_170704_319038/game.tw-pddl

SHA256(salt+"\\n"+A)           = 0027d44316a5688986042b2baac2f0a73f7f8d4a5fa9b01bf21ab30c46bba536
SHA256(salt+"\\n"+B)           = 009df34ef579b4934bf988d3c30ecfe86d7d7c17c4eb11aac591adddb3999b6c
SHA256(salt+"\\n"+root+A)      = 89744aa0d32758601502dbaacd6c380d05199dc6539c5a44d71578dd196987af
SHA256(salt+"\\n"+root+B)      = 532894dfa02368fd1d7b2f8ad71a9c9356cbea924fc0be2f116fc2258ef6fd28

Relative winner A; frozen historical absolute winner B.
```

A two-game `population=[A,B]`, `binding_selected=[B]`, `pilot_selected=[A]`, `binding_count=1` yields `BLOCKED_BINDING_SELECTION_MISMATCH` under the new guard, even though `[B]` is the correct historical absolute-path selection. This is a fully deterministic counterexample requiring no model or simulator.

More importantly, when the exact original 790-game universe and checksum-authenticated Binding180 pool are normalized to relative `train/...` paths, the PR #2 guard reports `BLOCKED_BINDING_SELECTION_MISMATCH`, `binding_selection_matches_correct_delimiter=False`, with **284 paths of symmetric difference** between the guard's selected set and the genuine original Binding180. The actual historical pilot40 has **11** literal overlaps with the true selected Binding180.

**Provenance:** official ALFWorld 0.4.2 `json_2.1.3_tw-pddl.zip` (interior `json_2.1.1`), archive SHA256 `5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`; original Binding180 selected-list SHA256 `d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee`. Independent read-only CPU audit jobs: `local_ca088cd9dd524141` (790 test) and `local_f9f2bf766b934761` (two-game witness), both exit 0.

## Remediation before PR #2 merge

Either (a) persist the exact **canonical historical absolute hashing namespace and dataset root**, build the SHA preimage with the root, while accepting relative paths only as sanitized dataset identifiers; or (b) state clearly the new guard is for a **new** relative-input protocol, not historical Binding-v1 regression, and implement a separate authenticated absolute-input historical checker. Add a test against the checksum-matched original Binding180 with actual overlap **11**, expecting `BLOCKED_SELECTED_COHORT_OVERLAP`, and retain `scientific_gate=NOT_AUTHORIZED`.

A1 attempted an independent GitHub `REQUEST_CHANGES` review on PR #2 but GitHub returned HTTP **422 'Review Can not request changes on your own pull request'** due to shared connected GitHub author identity across workers. A top-level PR comment exists. This finding is reproducible engineering review evidence **but not an independent GitHub approval**.
