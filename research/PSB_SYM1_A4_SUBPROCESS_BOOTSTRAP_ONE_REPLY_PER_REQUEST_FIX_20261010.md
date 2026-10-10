# PlanCarry PSB-SYM-1 — A4 subprocess bootstrap framing repair

**Date:** 2026-10-10. **Scope:** Engineering-only, zero model/ALFWorld TRAIN/paid GPU/confirmation, no scientific approval. On canonical research branch `research/bind-v02-source-custody-20261010`; no new PR.

## Issue and independent native reproduction

The Python `psb_sym1_public_json_subprocess.py` worker had a startup path that printed `{"status":"ENGINE_ERROR"}` to stdout **before any incoming JSON line** when `GuardedSymbolicEnv(frozen_game)` failed (e.g. source digest mismatch). Such an unsolicited first line violates the invariant **one reply per received request** and risks shifting controller traces. The worker's previously fixed request-64 edge case correctly avoids this, but the separate bootstrap failure branch did not.

A4 independent CPU negative job `local_85ffb4fbd74f4024` completed exit0 and reported **worker process exit2, unsolicited stdout `{"status":"ENGINE_ERROR"}`, zero requests sent** using a local intentionally wrong game file. This test used the pinned original worker source and no model.

## Minimal fix in canonical branch

- `research/psb_sym1_public_json_subprocess.py`, commit `d6016fdc7bfdfeb38175ba3ee7724637fffc578d`: bootstrap initialization exception now exits with status **2 and no stdout frame**, leaving the external controller responsible for treating premature child EOF/death as a fail-closed startup error. The worker must never claim a successful model-facing response before a corresponding input.
- `tests/test_psb_sym1_public_json_subprocess.py`, commit `e11dbe047e7ab295eb7efd303b2d17454ca902b7`: new integration regression starts the real worker with an intentionally altered `psb_sym1_prospective_frozen_game.json`, sends no request, asserts process exit2 and **zero stdout bytes**.

**Full native regression evidence:** CPU job `local_13130cd93900440b` exit0, **6/6 PASS** in 43.585 s, independently fetched canonical exact code revision `e11dbe047e7ab295eb7efd303b2d17454ca902b7` and original fixed fixture SHA256 `40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67`. Existing tests still pass: two separate OS processes win along two distinct routes after an identical prefix; duplicate-command JSON rejected; both native 12-action timeouts; oversized line rejected without splitting; exactly 64 replies for 64 inputs, then request65 returns a single budget-exhausted response.

## Strict boundary

This repair strengthens line framing only; it is **not** a process sandbox for models allowed arbitrary shell/filesystem access. Trusted controller must fail closed on child startup death/no response; no new implicit handshake or scientific policy. Fixed 12 actions and 64 requests are engineering defaults, not accepted PSB scientific budgets. Frozen BIND-v0.3 remains `NO_GO_FOR_G1_UNDER_CURRENT_G0_EVIDENCE`. No LLM evaluation, no original ALFWorld TRAIN use, no confirmation, no paper.
