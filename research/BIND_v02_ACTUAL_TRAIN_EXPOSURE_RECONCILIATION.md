# BIND-v0.2 — prospective G1 feasibility: what the actual historical repo proves

Science authority: **NOT_ACCEPTED_FOR_TEST**, `REVISE_BEFORE_TEST`, synthesis `d4fa3379-9f95-438b-8929-19fab7ca4407`. This report is a *repository-evidence audit*, not an independent custody or source-competence certificate.

## Exact source-manifest reconciliation

The versioned path index `research/bind_v02_known_selected_train_paths.json` (same branch) records all **239** distinct game paths actually listed by these four exact Git blob snapshots:

| TRAIN candidate manifest | Git blob SHA1 | Listed paths |
| --- | --- | ---: |
| `gdaa_train_candidate_manifest_v1.json` | `1e6765fae3a1ff02d7125424965fdc7fee83b9f0` | 90 |
| `gdaa_train_candidate_manifest_disjoint_v1.json` | `7f3744748c7a11aa22c9145cfe86abb49e04aeea` | 90 |
| `gdaa_train_candidate_manifest_fresh_v2.json` | `bc781248597c47199f5c51a8d68b5ea60a86e29b` | 90 |
| `latent_ab_pilot_manifest_v2.json` | `f0a3786d62efe7e3adeaa9ce7181a5827f4d60b4` | 40 |

Programmatic exact path-set comparison over fetched bytes: GDAA v1∩disjoint = **71**, GDAA v1∩fresh = **0**, disjoint∩fresh = **0**, hence GDAA total **199** unique paths. Pilot 40 has no *literal path* overlap with these 199.

The historical Pilot v2 metadata itself asserts TRAIN `pick_and_place_simple` **790** paths, previous Binding selection **180**, previous GDAA selection **199**, combined exclusion union **332**, and then 40 pilot selections. The implied overlap between Binding selection and GDAA selection is **47**, but those 180 Binding **literal path IDs were not recovered in these four files**. Conditional on the metadata being true and Pilot's declared exclusion being respected: 332+40=**372** conservatively excluded *candidate path identities*, leaving at most **418** paths outside these *particular declared exclusions*. **418 is NOT an estimate of untouched, independently fresh, source-model competent or usable G1 pairs.**

The further `plancarry_replay_residual_fresh_cohort_v1_20260821.json` independently declares **246 exposed families**, **160 eligible remaining families** under a different historical family-level scan. A family is not a trial/game-path identity. Do not add these figures to path counts or assume its `sanity/development/sealed reserve` subsets were all model-executed.

## Important route-constructibility distinction

`plancarry_latent_v2_matched_pair_manifest.json` includes environment-only examples of delayed two-object route divergence, such as a shared `go to bed 1` first action followed by distinct object-taking actions with both replay paths marked successful. But its listed example uses `json_2.1.1/valid_train/pick_two_obj_and_place`, not the target frozen `train/pick_and_place_simple` universe; the documented pair traces are **not certified source-model-owned A/B commitments**, and these historical cases are not independently fresh. The structural example is only a feasibility pattern, not a transferable G1 pass.

## Required immutable evidence before G1 source calls

1. **Full actual-consumption inventory:** identify which candidate game paths or families were actually inspected or run in *each* historical project execution, not merely included in manifests. Include off-repo jobs/checkpoints with per-run IDs, exact ALFWorld data revisions and artifact SHA checks. Recovery of Binding-180 path identities is a necessary but not sufficient subtask.
2. **Complete pre-source exclusion ledger:** distinguish manifest-selection, environment-inspected, LLM-queried, and outcome-viewed; conservatively exclude uncertain cases pending authenticated evidence. Normalize paths, families and exact game bytes; identify duplicate bytes even when split/path differs.
3. **Frozen genuinely fresh first 32:** an independent custody reviewer must sign/verify exact game bytes, selected candidate IDs and frozen order, with no outcome-conditioned replacements. No `VERIFIED_UNUSED` strings or non-overlap-only source ledger may authorize execution.
4. **Bilateral source feasibility:** under same reset, exact ordered commands, goal and naturally shared first action, each *source model* must independently produce successful A/B trajectories with a later meaningful choice; neither an oracle route nor a forged pre-written plan substitutes for model competence.
5. **Decision rule:** fewer than 16/32 verified bilateral A/B source pairs => G1 stops after a properly authorized prospectively frozen source study; absence of complete input evidence => `BLOCKED_SOURCE_PROVENANCE` now (NOT empirical hypothesis failure). Do not run G2/G3 or unseal confirmation.

Cross-reference: `research/bind_source_custody_gate.py` is a deliberately *negative-only* static verifier; it cannot issue science PASS. No model, GPU, paid API or confirmation access was used to produce this report.
