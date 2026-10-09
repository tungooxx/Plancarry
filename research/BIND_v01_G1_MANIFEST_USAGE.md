# BIND-v0.1 — G1 offline manifest linter

**Research-only engineering contract.** This is not G1 scientific execution and does not authorize training, inference, ALFWorld access, independent-review bypass, or confirmation access. The frozen design remains NOT_ACCEPTED_FOR_TEST until formal Research OS synthesis.

Files:
- research/bind_g1_manifest.py — standard-library JSON structural validator; no model/API/GPU dependencies.
- tests/test_bind_g1_manifest.py — eleven entirely synthetic tests.
- research/BIND_v01_PREEXECUTION_AUDIT.md — source audit and safety boundaries.

Run from repository root using Python 3.10+:

    python -m unittest discover -s tests -p test_bind_g1_manifest.py -v
    python research/bind_g1_manifest.py /path/to/frozen_manifest.json

Exit code 2 means structural invalidity. Exit code 0 never means the scientific result is valid.

## Frozen manifest format

JSON schema name is plancarry.bind.g1.v0.1 and phase is FROZEN_MANIFEST. Required pinned keys: exact model_revision, candidate_order_rule, evaluator_version, evaluator_sha256 (64 lowercase hex), source_protocol_sha256 (64 lowercase hex), confirmation_touched=false, binding_model_calls=0.

The candidates array must contain **exactly 32** distinct precommitted items in original order. Each item needs candidate_id, split=train, game_sha256 (64 lowercase hex), source_family_id, consumption_audit={status:VERIFIED_UNUSED,evidence_id:independent-proof-reference}, and qualification=null.

The frozen digest is computed in Python via digest(_immutable(manifest)); write it to frozen_sha256 and commit the frozen JSON before any source-model calls. This audit does not itself authenticate the independent provenance reference or the hashes against disk files.

After *independently authorized* source qualification, set phase=SOURCE_AUDIT, preserve the frozen SHA and original candidate ordering, and fill qualification for **all 32** attempts. Allowed statuses are ELIGIBLE, INELIGIBLE, TECHNICAL_FAILURE. Failed candidates require a reason. Eligible pairs require source_a, source_b, and source_evaluator_attestation.evidence_id.

Each source contains:
- reset: state_hash (SHA256), goal, observation, ordered admissible_commands.
- trajectory: at least two entries of {action, admissible_before}. The first action must be shared between A/B, later actions must differ, and every action must appear in the ordered admissible list valid for that time.
- won=true, invalid_model_turns=0, branch_label (different between A/B), and trace_sha256.
- Both sources must share identical reset hash, goal, observation, and ordered commands.

Do not include binding-result or post-treatment outcomes in source qualification. Do not replace ineligible subjects after seeing intervention results.

## Verdicts and limits

- FROZEN_MANIFEST_STRUCTURAL_ONLY: 32-item manifest structurally frozen; not authenticated science.
- G1_STRUCTURAL_THRESHOLD_ONLY_REQUIRES_INDEPENDENT_REVIEW: 16+ structurally eligible pairs, **not a scientific G1 PASS**.
- G1_STOP_BELOW_SOURCE_THRESHOLD: fewer than 16 eligible from a complete technically clean 32 attempts.
- TECHNICAL_BLOCKER_NOT_SCIENTIFIC_FAIL: technical failures, never count as scientific refutations or use to redraw an inspected cohort.
- INVALID_PREEXECUTION_CONTRACT: missing fields, compromised identities, mismatched ordered action sets, frozen SHA drift, or other guard errors.

This validator cannot establish that A/B branches represent *genuinely different goal-consistent plans*, that original records were unused, that source traces are authentic, or that there is no private answer leakage. It cannot evaluate practical binding advantages, CI, confirmatory statistical power or third-party reviewer independence.

Research OS peer-hidden batch 861f57bb-e003-411d-83c9-f1d90db4941c still requires three independent reviewers and synthesis before a model/GPU run. The G1 threshold is a screening rule, not publication-grade evidence. The original BIND-v0.1 thresholds for G2/G3 remain frozen and subject to pre-execution reviewer acceptance. No paid compute should be started.
