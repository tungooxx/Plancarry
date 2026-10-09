# PlanCarry BIND-v0.2 G1: source custody / prior-consumption static triage

**Science state:** `NOT_ACCEPTED_FOR_TEST`; exact design `fd92e3a6-6013-4eb3-9566-20bbb5900456`, semantic SHA256 `aeba093973233c894c72889b3637407a689e59bd2ecddaea41fcf0fb42d7f769`; independent-batch `7a1fbacc-0c7c-4a02-b90a-19fad81d3cae` and synthesis `d4fa3379-9f95-438b-8929-19fab7ca4407` = `REVISE_BEFORE_TEST`. **No experiment, rollout, GPU, paid API or confirmation authorized.**

## Verified repo observations; evidence gaps

- Existing `alfworld_binding_runner.py` reads `train/pick_and_place_simple`, expects **790** candidates, scans at most **180**, and tests a fixed `intended_next_action` instruction with first-action IAA/GDAA/RPA. These are historical constants in source, **not a verified list of all historically used game identities**, nor bilateral A/B later-fork evidence.
- Old `alfworld_cohort_runner.py` previously uses `valid_seen`. It cannot be relabeled TRAIN or used to certify fresh BIND cases.
- GitHub `results/` on the inspected branch exposes only `design/`; no audited all-run per-game consumption inventory or new model-generated successful bilateral A/B traces was present in the inspected repository tree. Evidence may exist elsewhere; absence from this branch is not proof it never existed.
- `research/bind_g1_manifest.py` allows `frozen_sha256=None` during `FROZEN_MANIFEST`; the new offline gate rejects that case. This script does not alter the legacy linter or claim a cryptographically authenticated source ledger.

## Tool interface and deliberately fail-closed outcome

```bash
python -m unittest discover -s tests -p test_bind_source_custody_gate.py -v
python research/bind_source_custody_gate.py frozen_g1_manifest.json historical_uses.json
```

The first input follows the existing `plancarry.bind.g1.v0.1` frozen pre-source manifest with exactly **32** ordered TRAIN candidate IDs, game SHA-256, source family IDs, and frozen SHA of the old linter's immutable identity. The second input uses schema `plancarry.bind.prior-consumption.v0.2`, with immutable dataset/inventory-hash metadata, declared historical coverage and run-level source SHA lists. The tool matches **content SHA-256** across known uses, including reused content with a different split/path, checks empty/duplicate/invalid records, candidate substitutions and source-audit leakage.

Possible verdicts: `INVALID_AUDIT_INPUT` (exit 2), `BLOCKED_KNOWN_CONSUMPTION` (exit 3), and `BLOCKED_FRESHNESS_UNATTESTED` (exit 3). **There is intentionally no PASS or zero exit code.** Claiming historical inventory completeness or writing `VERIFIED_UNUSED` is not enough. Positive attestation requires a separate independent authoritative inventory/custody mechanism with immutable source provenance and actual pre-usage verification; this tool does not implement that mechanism or verify external signatures.

## What is required before G1 can become scientific work

1. Identify *every* previously inspected source episode across all historical project checkpoints/artifacts, including all task families/seeds/splits, with immutable run and dataset provenance. Audit any declared exclusion source and gaps. A GitHub code scan alone is not complete usage inventory.
2. An independent verifier must authenticate historical inventory completeness **and** the exact first 32 game bytes/identities *before* source-model calls; supply a separately verifiable authority rather than self-authored evidence IDs.
3. Prove distinct, goal-consistent, model-owned A/B plans from the exact same reset/goal/ordered command list and same naturally occurring first action. Full authentic source trajectories and independent goal evaluator needed; reference-route mimicry is not synonymous with task utility.
4. If any prerequisite is missing, use `BLOCKED_SOURCE_PROVENANCE` or `BLOCKED_SOURCE_FEASIBILITY`; do **not** reinterpret technical non-execution as a negative scientific effect. Never sample replacements after outcomes or unseal confirmation.

**This artifact is a reproducible engineering triage, not evidence for G1 success and not approval to execute a revised scientific design.**
