# PlanCarry BIND-v0.2 — A3 independent cross-manifest consistency challenge
**Date:** 2026-10-10 (Asia/Seoul)  
**Classification:** STATIC_PROVENANCE_CHALLENGE / ENGINEERING_ONLY / **NO SCIENCE AUTHORITY**  
**Project:** PlanCarry: LLM Plan-State Persistence  
**Frozen design:** `fd92e3a6-6013-4eb3-9566-20bbb5900456`, design SHA `aeba093973233c894c72889b3637407a689e59bd2ecddaea41fcf0fb42d7f769`  
**Peer synthesis:** `d4fa3379-9f95-438b-8929-19fab7ca4407` = `REVISE_BEFORE_TEST`  
**Constraint:** No model, simulator, GPU, paid API, new source rollout or confirmation was used. This note is **not** an additional peer-hidden attack vote or an execution release.

## Exact Git blobs inspected

All files were read from `tungooxx/Plancarry` at `a2/bind-g0-full-input-integrity-20261010`.

| File under `results/design/` | Git blob SHA-1 | Paths |
|---|---|---:|
| `gdaa_train_candidate_manifest_v1.json` | `1e6765fae3a1ff02d7125424965fdc7fee83b9f0` | 90 |
| `gdaa_train_candidate_manifest_disjoint_v1.json` | `7f3744748c7a11aa22c9145cfe86abb49e04aeea` | 90 |
| `gdaa_train_candidate_manifest_fresh_v2.json` | `bc781248597c47199f5c51a8d68b5ea60a86e29b` | 90 |
| `latent_ab_pilot_manifest_v2.json` | `f0a3786d62efe7e3adeaa9ce7181a5827f4d60b4` | 40 |

Independent exact string-set checks (same `game.tw-pddl` absolute-path notation in all four inputs):
- `|V1 ∩ DISJOINT| = 71`, `|V1 ∩ FRESH| = |DISJOINT ∩ FRESH| = 0`.
- All 40 PILOT paths are outside all three GDAA manifests.
- `|V1 ∪ DISJOINT ∪ FRESH| = 199`; including PILOT gives **239** distinct paths.
- All three GDAA arrays are lexicographically sorted, and the first 71 entries of DISJOINT are **exactly** the V1 entries surviving DISJOINT. Its final 19 entries are strictly after V1's last lexicographic path.
- Thus exactly **19** paths in the original V1 first-90 are missing from the first-90 DISJOINT, with 19 later lexicographic replacements.

## Contradictory historical-exclusion arithmetic

The DISJOINT metadata explicitly describes its 90 entries as the first lexicographic candidates **after excluding the frozen Binding-v1 180-candidate pool**, identified by `d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee`, from a 790-path TRAIN universe. FRESH metadata says it uses the **same** frozen Binding-180 exclusion and additionally excludes the entire DISJOINT 90 list.

**Conditional deduction:** If V1, DISJOINT and FRESH actually represent the same immutable 790-path universe with those literal exclusion semantics, then:
1. The 19 removed V1 paths are the *only* paths of V1 lying in Binding-180. (The first-90 lexicographic prefix retains every non-excluded original V1 path.)
2. DISJOINT and FRESH contain no Binding-180 paths, by their stated exclusion rule.
3. Therefore `|Binding180 ∩ (V1 ∪ DISJOINT ∪ FRESH)| = 19`; the corresponding union is `180 + 199 - 19 = 360`.

However `latent_ab_pilot_manifest_v2.json` declares **Binding=180**, **GDAA union=199**, **their exclusion union=332**. By inclusion-exclusion, this asserts `180 + 199 - 332 = 47` Binding/GDAA overlaps, not 19.

> **Discrepancy:** the same historical relationship is described as **19** overlaps by the sorted-first-90 selection/exclusion metadata and **47** by PILOT's reported union size — a **28-path inconsistency**.

This is a contradiction among *declared historical provenance contracts*. It does **not** prove which manifest is wrong, that any particular candidate leaked, that a particular run executed, or that G1 is scientifically false. At least one assumed claim (same source universe, same binding exclusion bytes, lexicographic first-90 procedure, or PILOT union metadata) needs revalidation against authenticated raw source.

The A2 reconciliation `research/BIND_v02_ACTUAL_TRAIN_EXPOSURE_RECONCILIATION.md` faithfully reports PILOT's implied 47 and upper-bound 418, but does not resolve the conflicting disjoint/fresh selection semantics. **Do not promote either upper bound as a proven fresh supply.** If the 19-overlap interpretation and all further declared exclusions were verified, the analogous unselected-path arithmetic would be `790 - (360 + 40) = 390`, *not* 418; neither number proves untouched availability, complete historical consumption, or bilateral A/B source competence.

## Mandatory resolution before G1

1. Recover the exact **Binding-180** candidate path list associated with the frozen `d6e289b...` checksum *and the algorithm/input revision used to compute it*. Authenticate the original 790-path source inventory and split, and compare exact bytes, normalized paths, family IDs and source content SHA-256 — not merely manifest labels.
2. Reproduce `V1`, `DISJOINT` and `FRESH` selection from the **same frozen 790 entries** with the actual exclusion set; identify whether the lists were regenerated against different universes/ordering, whether source hash claims refer to different Binding pools, or whether PILOT's 332 union was computed from another selection.
3. Recompute all set unions from authenticated raw lists and reconstruct **historical actual execution exposure**, separate from manifest selection. Keep off-repo checkpoints and inspected but not executed paths in the custody ledger.
4. **Until reconciled**, set the G1 prior-population/custody gate to `BLOCKED_SOURCE_PROVENANCE`; do not sample a fresh 32 from the supposed 418 (or 390), launch model/source calls, or use confirmation. Fixing arithmetic alone is **not** independent non-consumption attestation.

## Reproduction

Use `research/bind_v02_manifest_consistency_a3.py` on these four local JSON files in order (V1, DISJOINT, FRESH, PILOT). The script produces a JSON report with the arithmetic and a conditional conflict flag. It never returns a science-authorizing PASS.

**A3 conclusion:** `UNRESOLVED_PROVENANCE_CONFLICT`, not a negative experimental result.
