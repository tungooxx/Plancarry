# PSB-SYM-1 — isolated per-arm native public bridge, A4 engineering verification

**Date:** 2026-10-10  
**Scope:** Prospective symbolic TextWorld 1.7.0 **engineering only**. Not BIND-v0.3 G0 and not agent/model authorization.

## Origin and expected invariant

A4's [prior independent audit](PSB_SYM1_A4_INDEPENDENT_NATIVE_RENDERER_CLONE_AUDIT_20261010.md) proved `TextWorldEnv.copy()` leaves soft-shared `Game` and `Inform7Game` references; a controlled rename of A's room label changed B's public render with no B action. The new isolated bridge loads the *same SHA-pinned* fixture into separate `TextWorldEnv` objects instead of calling `copy()`, while the narrow public output is enforced by a fixed room-name/command whitelist.

## Changes

- `research/psb_sym1_isolated_public_bridge.py`: SHA-pinned source file validation, fresh independent native `TextWorldEnv.load` for each arm, no shared `_game`/`_inform7`/`_game_progression`, explicit public renderer, exact command string check, constant status enums on invalid input/engine errors, no native exceptions in public output.
- `tests/test_psb_sym1_isolated_public_bridge.py`: nine CPU-only regressions on the exact 17,590-byte prospective fixture SHA256 `40e0654afa677d45b173552ee77c5c38dd862df9cddbfb79b4deb4783a2b3f67`; tests verify alias blocking, private oracle field omission, invalid commands, mutated room labels, unchanged native winning routes and terminal behavior.
- Original `research/psb_sym1_textworld_native_copy_preflight.py` and frozen JSON fixture remain unchanged on this branch, so previous A1 baseline remains reproducible and this bridge is an opt-in engineering proposal.

## Reproduced execution evidence

| CPU job | Outcome | Notes |
| --- | --- | --- |
| `local_58d6d654c2fc467a` | PASS, exit 0 | Prior A4 direct source/fixture clone audit. Normal native routes win. |
| `local_7b0e8aa896cf4c43` | PASS, exit 0 | Prior A4 controlled shared-reference renderer-leak reproduction. |
| `local_67bed6332ee146ee` | **FAILED as expected development iteration** | Test suite fixture SHA `setUpClass` used an instance assertion API on class object, zero tests run. Corrected test harness; this is not counted as a pass. |
| `local_bacb2cf9f0204de5` | **9/9 PASS, exit 0** | Current pinned bridge and tests downloaded from branch commit `f15cc569bd0bf1e391f97bf1ecf6be14d06ffed6`; exact fixture downloaded from commit `307ea0c0f10fb18223ae448d99a221d41660eba2`. CPU TextWorld 1.7.0 isolated environment. |

Passing 9 tests: distinct Game/Inform7/progression/state allocations; unchanged common-prefix/two winning paths with scores `[1,1]` and 4 moves each; a malicious A room-name mutation cannot alter B render; A renderer rejects its own forged label; metadata walkthrough route sentinel absent from public observation; raw `env.state` privileged fields omitted from public result; invalid or non-menu command returns only `INVALID_ACTION`; terminal state rejects further actions; altered or renamed frozen fixture fails closed.

## Explicit limitations

- The bridge is **not a sandbox against arbitrary Python execution**. The trusted host still has access to private `_env`, facts, quest, game metadata, and native logic. Only pure JSON-serializable return values from `observe()/act()` may cross an eventual model tool boundary. No model tool endpoint or LLM has been connected.
- The fixed room ID/name and command allowlist are intentionally **single-fixture specific**. These must not be silently generalized to other games. The test does not certify general symbolic TextWorld snapshots or ALFWorld PDDL state/RNG.
- `TextWorldEnv.load` independent instances solve observed *soft-copy Game aliasing* on the pinned fixture. They do not independently attest identical RNG state for all possible backends.
- Both manually specified routes win but do **not** establish model-owned plan competence or policy binding advantage against direct reminders.
- A separate scientific design with prospective cohort, privacy leak threat model, fair comparators, statistical assumptions and independent review is still necessary before any inference.

**Result:** `ISOLATED_NATIVE_PUBLIC_BRIDGE_STRUCTURAL_ONLY`, `scientific_gate=NOT_AUTHORIZED`. BIND-v0.3 remains `NO_GO_FOR_G1_UNDER_CURRENT_G0_EVIDENCE`.

**No paid GPU/API, model calls, ALFWorld TRAIN, confirmation access or paper work.**
