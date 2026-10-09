# PlanCarry historical cohort audit: exact Binding-180 recovered; Latent A/B pilot v2 exclusion mismatch

**2026-10-10, read-only engineering/provenance audit. NOT a scientific G0/G1 pass.** No model calls, no GPU, no paid API and no confirmation data accessed.

## Corpus and exact original cohort restoration

The official `alfworld/alfworld` **0.4.2** GitHub asset `json_2.1.3_tw-pddl.zip` (36,507,267 bytes) contains a `json_2.1.1/` tree with **790** `train/pick_and_place_simple-*/trial_*/game.tw-pddl` members. The full ZIP passed `zipfile.testzip()`; archive SHA256 `5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`.

Restoration used exact old code from `alfworld_binding_runner.py`: historical absolute prefix `/opt/gpu-lab/data/plancarry-alfworld/` + ZIP member; order by `SHA256('plancarry-binding-v1-2026-08-18' + '\\n' + absolute_path)`, choose first 180, then digest `SHA256('\\n'.join(180 selected absolute paths) + '\\n')`. Observed digest `d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee`, **exactly equal to the historical frozen EXPECTED_POOL_SHA256**.

The 180 exact ordered paths are persisted in `research/HISTORICAL_BINDING_V1_EXACT_180_SOURCE_SELECTION_20261010.json` (local CPU job `local_b9c9113741e64fb2`). This is an authenticated recreation of *selection from a known public archive*, NOT evidence of 180 actual model executions.

## Independently reproducible historical exclusion error

Compare the exact 180 against four historical immutable candidate manifests on the branch:

| Historical manifest | Candidates | Exact actual Binding-180 overlap |
| --- | ---: | ---: |
| `gdaa_train_candidate_manifest_v1.json` | 90 | 19 |
| `gdaa_train_candidate_manifest_disjoint_v1.json` | 90 | 0 |
| `gdaa_train_candidate_manifest_fresh_v2.json` | 90 | 0 |
| `latent_ab_pilot_manifest_v2.json` | 40 | **11** |

The three GDAA manifests have 199 unique paths (GDAA v1 and disjoint overlap by 71 paths); **Binding-180 ∩ GDAA-199 = 19**, so the true union is **360** candidate paths, NOT the **332** declared by `latent_ab_pilot_manifest_v2.json`. The pilot manifest's historical metadata had `excluded_binding_count=180`, `excluded_gdaa_union_count=199`, `excluded_union_count=332`, implying a false overlap of 47.

A separate offline CPU reconstruction on the entire **same 790-member corpus** reproduced the old pilot **exactly, all 40 paths and their exact order**, using this *different*, incorrect Binding exclusion set:

```python
# Frozen Binding runner actually uses:
correct_binding180 = sorted(population, key=lambda p: sha256(BINDING_SALT + "\n" + p))[:180]
# Legacy pilot's exclusion+selection behavior is reproduced with:
other_binding180 = sorted(population, key=lambda p: sha256(BINDING_SALT + p))[:180]
gdaa_union = set(v1_90) | set(disjoint_90) | set(fresh_90)
pilot_v2_reproduced = sorted(
    (p for p in population if p not in (set(other_binding180) | gdaa_union)),
    key=lambda p: sha256(PILOT_SALT + p)
)[:40]
assert pilot_v2_reproduced == historical_pilot_v2_manifest["candidates"]
```

Under `other_binding180` (without newline): overlap GDAA = **47**, union = **332**, pilot overlap = **0**. Under the actually frozen Binding v1 (with newline): overlap GDAA = **19**, union = **360**, and **11 of 40 pilot paths are part of the previously selected Binding-180**. The evidence establishes the exact selection behavior and reproducibility of the missing-newline mistake; it does not by itself identify which historical script line inserted the mistake or whether the 11 were actually executed by either experiment.

## Correct disposition

- Preserve historical immutable manifests and their scientific measurements; annotate as **cohort exclusion / source-independence violation in selected sets**, not as proof of result manipulation or outcome contamination.
- Mark earlier **47 conditional** and **14 conditional witness** derivations as superseded by the actual checksum-matched cohort: **19 Binding/GDAA overlap**, **11 definite pilot candidate overlaps**.
- **Do not** retroactively replace pilot samples or re-label them as independent; new source custody/G0 must inspect actual run and model-call episode logs.
- Independent G0 provenance, 32 genuinely fresh TRAIN cases and model-owned A/B bilateral feasibility remain unproven. G1/G2/G3 and confirmation stay unauthorized until separate reviews.

The only asserted success is exact reconstruction of the historical **selection list** and its provable overlap mismatch; no science claim is upgraded.
