# A3 addendum — exact resolution of BIND-v0.2 historical 19-vs-47 cohort conflict

**2026-10-10 | SCIENTIFIC GATE NOT AUTHORIZED | source selection audit only.**
Supersedes the *unresolved* status in `research/BIND_v02_GDAA_CROSSMANIFEST_CONTRADICTION_A3.md` on this branch. Preserves the original discrepancy evidence rather than rewriting history. **Not an additional peer-hidden design attack, not evidence for G0/G1 source freshness, and not a model/GPU result.**

## Resolution

A2's independent reconstructed archival source, `a2/bind-cohort-salt-audit-20261010`, recovered a 790-member ALFWorld train/pick_and_place_simple population from `alfworld/alfworld` 0.4.2's `json_2.1.3_tw-pddl.zip` (SHA256 `5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`). The original runner's frozen Binding-v1 180 selection was reconstructed and matched exact frozen checksum `d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee`.

**Original Binding salt:** `SHA256(BINDING_SALT + "\\n" + path)`.
**Pilot v2 wrong exclusion salt:** `SHA256(BINDING_SALT + path)`.

The missing newline changes which 180 paths are excluded by the Pilot manifest generator. A2's replay with the incorrect salt exactly reproduced the old 40 pilot candidate paths and old declared exclusion union 332. The original 180-list reconstruction + four frozen manifests instead give:

| Set relation (exact absolute paths) | Count |
| --- | ---: |
| Binding180 ∩ GDAA v1 90 | 19 |
| Binding180 ∩ GDAA disjoint90 | 0 |
| Binding180 ∩ GDAA fresh90 | 0 |
| GDAA unique union | 199 |
| Binding180 ∪ GDAA199 | **360** |
| Binding180 ∩ Pilot40 | **11** |
| Pilot overlap paths incorporated into route-freeze pairs | **9** |

## Independent second check in A3 session

A3 fetched the A2 branch's `research/HISTORICAL_BINDING_V1_EXACT_180_SOURCE_SELECTION_20261010.json`, `research/BINDING180_PILOT_11_HISTORICAL_RUN_EXPOSURE_MATRIX_20261010.json` and all four original `results/design/*manifest*.json` sources. A separate read-only exact-path set calculation checked **13 invariants**, all 13 passing: Binding180 size, GDAA199 union, Pilot40 size, binding/GDAA19, binding/pilot11, disjoint/fresh0, union360, matrix11, every matrix path belonging to the intersection, unique matrix11, frozen route pairs9, and exact frozen Binding SHA match. This reran list-level arithmetic, **not** A2's archival ZIP regeneration or Python environment/model tests.

A2's run-level trace states all 11 pilot overlaps were environment-inspected in one old completed `latent-pilot-pair-freeze` command; original Binding-v1 canonical run `43f2e3f6-15d4-45a0-b277-93541e1ea026` failed `httpx.ConnectError` on its first attempted model request at a *different* game, before any successful model response. **No repeated LLM inference on those same 11 is established** by these documented jobs; this is not a global no-reuse certificate for off-repo history.

## Revised scientific interpretation

- **RESOLVED:** 19-vs-47 arithmetic discrepancy is attributable to a specific historical source-selection salt bug, not an unexplained corpus incompatibility.
- **CONFIRMED:** 11 historical Pilot40 selections overlapped actual Binding180 selected identities; 9 of those entered environment route-freeze records.
- **NOT CONFIRMED:** duplicated model calls, contaminated model score, external complete historical use, genuinely untouched prospective 32 TRAIN cases, or G1 bilateral model-generated A/B source competence.
- G0 stays **BLOCKED_SOURCE_PROVENANCE**, scientific design BIND-v0.3 remains **NOT_ACCEPTED_FOR_TEST** pending independent batch/synthesis. Do not retroactively change immutable old cohorts or exclude unfavorable results.
- The exact status of old candidate source *selection* is different from actual simulator inspection and from successful LLM inference; maintain all three categories in the custody ledger.

## Canonical evidence links

- [A2 exact salt bug audit](https://github.com/tungooxx/Plancarry/blob/a2/bind-cohort-salt-audit-20261010/research/BINDING180_PILOT_V2_EXACT_EXCLUSION_BUG_AUDIT_20261010.md)
- [A2 execution-level exposure audit](https://github.com/tungooxx/Plancarry/blob/a2/bind-cohort-salt-audit-20261010/research/BINDING180_PILOT_RUNLEVEL_EXPOSURE_AUDIT_20261010.md)
- [Original Binding180 exact selection](https://github.com/tungooxx/Plancarry/blob/a2/bind-cohort-salt-audit-20261010/research/HISTORICAL_BINDING_V1_EXACT_180_SOURCE_SELECTION_20261010.json)
- [Per-game overlap matrix](https://github.com/tungooxx/Plancarry/blob/a2/bind-cohort-salt-audit-20261010/research/BINDING180_PILOT_11_HISTORICAL_RUN_EXPOSURE_MATRIX_20261010.json)

No paid API, GPU, model calls, or sealed confirmation used in this A3 review.
