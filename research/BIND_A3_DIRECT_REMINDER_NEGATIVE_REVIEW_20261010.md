# PlanCarry — A3 independent engineering review: strongest DIRECT_REMINDER parity

**Date:** 2026-10-10  
**WorkItem:** `27124e6b-e9b9-41d7-8144-1797d6b5b843`  
**Source:** `tungooxx/Plancarry`, original baseline commit `ded3fc3c0f9d9c2a093c6ca1cb145eb7b0de6726`  
**Disposition:** `CODE_REPAIR_REQUESTED`, **scientific gate `NOT_AUTHORIZED`**  
**Review role:** A3 engineering critic; this document is NOT a peer-hidden BIND-v0.3 design attack or replacement for G0/G1 source authority.

## 1. Bounded independent reproductions

GPU-Lab CPU job `local_aeed6baee14c4b05` checked out the exact original source commit, and independently ran `python -m unittest discover -s tests -p test_bind_strong_direct_reminder_matched_control.py -v`: **10/10 PASS**, exit code 0. Three extra negative probes were accepted by `check_shape`:

| Probe | Original preflight | Interpretation |
| --- | --- | --- |
| Unverified source plan was called **“model-authored”** inside both message frames despite `model_owned_plan_attested=False` | ACCEPTED | Prompt overstates source authorship. Semantic parity of two arms does not cure lack of provenance |
| Two divergent A/B plans had distinct `plan_id` but identical `source_record_sha256` | ACCEPTED | Source-history consistency not checked; SHA **syntax** is not authenticity |
| Same artificial earlier action `teleport to vault` was placed into the shared prefix and both future paths | ACCEPTED | Current shape checker has no source-time native menu/observation receipt; cannot infer whether earlier actions were legal |

These are **schema/representation attacks**, not demonstrations of real-world data leakage, successful model exploitation, or bias in measured BIND results (no model result exists here).

## 2. Repair and verification

A3 branched from the exact author baseline and proposed [PR #11](https://github.com/tungooxx/Plancarry/pull/11), `a3/bind-strong-null-provenance-guard-20261010`:

1. Both equally privileged prompt frames now describe the supplied sequence as **proposed, not independently attested** rather than unconditionally model-authored.
2. Reject A/B divergent complete source histories with identical record digest. This checks consistency only, *not* historical source attestation.
3. Report prompt UTF-8 byte length and delta while retaining `tokenizer_realized_costs_matched=False` and `science_gate=NOT_AUTHORIZED`.
4. Three new zero-model regression tests.

Pinned independent CPU verification job `local_f0f14f4b08484111`, commit `7e88bc0294f73ed4412c934f77436477475d803b`: **13/13 tests PASS**, `compileall` PASS, exit code 0. For the test fixture, both directions yield **BIND 906 UTF-8 bytes** and **DIRECT_REMINDER 884 UTF-8 bytes** (BIND +22 bytes). Do **not** equate UTF-8 byte sizes to model-token budgets or equal model attention. Only the frozen original model/tokenizer and full prompt/call ledger could establish realized resource comparability.

## 3. Original ALFWorld PDDL evidence assessed separately

The original original 790 TRAIN source archive checksum remains `5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`; selected frozen Binding180 digest remains `d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee`.

In prior real CPU native TextWorld 1.7.0/FastDownward preflight, **11 previously environmentally inspected** BIND180/Pilot40 overlap games passed real PDDL common-prefix and distinct legal movement fork checks (first-class native atoms, facts, ordered menu and feedback; protected report SHA256 `9dfe1a45d827965bd4b40a96f47ef6d4bbc679f660704ad8dac9bf251e3b46bb`). Subsequent independent two-process 11-game native prefix replay also passed; strict guard verifies actual native Atom/fact changes, not feedback-only differences. Original strong-null integration records **11 cases × 2 directions = 22 serialized frames**, CPU job `local_97b6b14731644767`, output digest `bfec7073106abf1be172558f922e8687356843b6fa312a2f54d5530f103ad514` (prior A1 execution, **not rerun by A3**).

This shows meaningful **environmental structural feasibility** of matched public prefixes on originally inspected data. It does **not** prove full hidden simulator RNG/save-state equivalence, the original full run-level model use history, or 32 independent competent bilateral model-owned successful plans. This first-generation integration used **mechanically chosen source plans** and a task-family filename descriptor, not the official goal. That descriptor defect is now superseded by the later source-authenticated original-public-grammar task integration below. The strong-null experiment with an actual LLM remains unrun.

### 2026-10-10 A3 evidence addendum: original task-goal provenance repaired

A1 subsequently created `research/bind_alfworld_original_public_task.py` (source byte SHA256 `cf3f14af6cf800bf7bc8353c89f8b9655333d7d0b241d7d3bb8ac08c73c85030`), parsing the publicly referenced `grammar.intro #task#` → public `grammar.task.rhs` from original `game.tw-pddl` JSON, without using filenames or exposing privileged walkthrough. A1's 790-game original-source report `research/BIND_ORIGINAL_PUBLIC_TASK_790_AUDIT_NATIVE_11X22_20261010.json` records **790 parsed, 280 unique public task sentences** and an updated original real PDDL 11×22 preview report SHA256 `fd99fac1d2ed3a1df6cef45ff4e76a3c57b0bcf9adf554f46c7aa04a0660ca27`. The 790-game result is **A1's prior audit**, not independently rerun here by A3.

A3 independently read the exact 11-case report from the existing GPU-Lab workspace and reopened only the **same 11 previously environmentally inspected original games** (no model calls, no new cohort). Every game was resolved by its archived `game_sha256` among candidate `trial_*/game.tw-pddl` files; task-family name alone is unsafe because **10 of 11 families have more than one trial**. For each resolved original file, A3 independently ran the public parser and compared five archived fields to source bytes: task string, task SHA256, game SHA256, provenance identifier, and the public-intro indicator: **55/55 field checks PASS** over **11/11 exact games**, with 11 distinct public sentences. CPU job `local_f2ca7fc4c0424079` exited 0. The earlier direct family-path lookup and first-trial assumption failed safely, and was corrected to unique exact game-SHA matching; no prior failed assumption is treated as a PASS. This establishes task-to-source byte linkage on the 11-case preview, **not** global historical freshness, full native RNG equivalence, model-generated plan competence, treatment-token parity, or BIND causal effect.

The archived revised 11-case preview still declares `model_calls=0`, `model_owned_plans_generated=false`, `full_native_rng_state_certificate=false` and `scientific_gate=NOT_AUTHORIZED`.

## 4. Remaining essential controls

- Attach independent, complete historical request/response and episode/seed consumption custody to frozen original TRAIN identities. A SHA string supplied by a renderer is insufficient.
- Pin official model-visible task goal and source-plan origin; do not derive goal from filename label or present mechanical proxy as model-authored.
- Require immutable ordered legal-command and actual action/observation receipts for *each historical prefix step*; never compare an old earlier action against the current fork menu.
- Freeze the strongest DIRECT_REMINDER's instruction priority, message role, placement and semantic atom scope against BIND, and measure model-specific token/call/latency/storage parity using the actual pinned model/tokenizer before treatment.
- Protect reciprocal A→B/B→A ITT denominator, legal alternate routes, and terminal task success independently of donor-route matching.
- Keep original G0 decision `NO_GO_FOR_G1_UNDER_CURRENT_EVIDENCE` and independent scientific design batch separate; no G1/G2/G3 or confirmation authority follows from this code review.

**Resources used by A3:** existing repository source, GitHub read/write, free local CPU only. No new model inference, GPU, paid API, new original TRAIN game openings or confirmation.
