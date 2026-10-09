# PlanCarry — historical Binding-v1 vs Latent Pilot-v2: execution-level evidence audit

**Status:** `SOURCE_HISTORY_PARTIAL` · **No G0/G1/G2/G3 authority.** Code and log evidence recovered through Research OS historical ExperimentRun, original GPU_LAB job metadata (read-only SQLite), historical command sources and frozen GitHub source manifests. All present investigations use CPU/static read-only operations, no model inference.

## Distinguish three different kinds of exposure

1. **Candidate-selection membership:** exact old Binding-180 cohort recovered with historical preregistered SHA256 `d6e289b04ae1bfea0a8210f2cb643f91699a4e48a6e46cd84721310cc8f946ee`. The 40-game pilot v2 set contains **11** of those 180.
2. **ALFWorld environment access:** the recorded Python command for `local_7bd88fb99ccd406e` (`latent-pilot-pair-freeze`, exit 0 on 2026-08-19) explicitly loops over **all 40 pilot candidates**, creates `AlfRuntime(game,max_steps=8)`, reads admissible commands and replays legal X→Y/Y→X navigation paths. Thus **all 11 overlapping candidates were environment-inspected in this job**, and **9 of them became frozen route pairs** among the first 32. The separate `latent-pair-semantic-audit` job inspected the first 5 frozen pairs at environment level. This is **not a language-model run**.
3. **Model inference:** Research OS canonical `ExperimentRun` **`43f2e3f6-15d4-45a0-b277-93541e1ea026`** for original Binding v1 (`local_a2debb765575fe69f652f204`, initiated 2026-08-21 23:47 UTC) is **FAILED, exit1**, due to `httpx.ConnectError [Errno 111] Connection refused` in `client.chat.completions.create` on the *first attempted qualification request*. Canonical scientific inspection recorded **`NOT_ASSESSED`**, `INVALID_TECHNICAL_MODEL_ENDPOINT_UNAVAILABLE`, `ZERO` science information gain. Stdout size was **0 bytes**, stderr **6635 bytes**. Source code `alfworld_binding_runner.py` enters `aq.run_game` for candidate index1; `alfworld_qualify.py` initializes `AlfRuntime` and calls model before any action. Therefore first Binding source game was environment-opened, but **no successful model response** and **no recorded model-chosen action** in that run.

The first Binding game is `pick_and_place_simple-Lettuce-None-CounterTop-25/trial_T20190907_000052_389529`; it is **not in the 40-game pilot**. So these two documented jobs do **not** establish a single common game with duplicated runtime or model treatment.

## Original bug mechanism is proven by the job command itself

The recovered command source for `local_75aa27a0ede54111` (`latent-pilot-manifest-v2-freeze`) computes the Binding exclusion cohort as:

```python
binding=sorted(all_games,key=lambda p: hashlib.sha256((binding_salt+p).encode()).hexdigest())[:180]
```

The actual preregistered Binding runner instead uses `SHA256(binding_salt + "\n" + p)`. Replaying the missing-newline exclusion reproduces **all 40 pilot candidates in exact order**, reports the historical union **332**, and gives zero overlap against the **wrong** exclusion set. The true Binding-180 has GDAA overlap **19** (union **360**) and pilot overlap **11**. This is a **historical source-selection exclusion bug**, not proof of intentional tampering or duplicated LLM inference.

## Bounded retrospective search scope

- Read-only GPU Lab metadata DB: searched **12,495** jobs with start timestamps within **2026-08-17 to 2026-08-31**, filtering original binding runner / pilot manifest / named latent jobs; one documented actual execution of `alfworld_binding_runner.py` was identified, and it failed at first model request
- Original August job directories are no longer accessible under `/data/local-jobs`; canonical Research OS persists the run traceback and artifact sizes, but not a complete successful old Binding result
- Pilot v2 manifest and 32-pair route-freeze steps are backed by completed recorded commands. There is no confirmed pilot v2 **model** inference in the inspected explicit manifest-referencing commands. This does **not** establish a global negative over all remote, off-repo or differently named jobs

## Scientific boundary

**Precise findings:** 11 overlapping selected game paths; all 11 pilot environment-inspected; 9 frozen as route pair candidates; original Binding run failed before first model response, at a different initial game. **Confirmed repeated inference events: none identified**, with **incomplete global historical provenance**.

The new v0.3 design has an independent G0 historical inventory and G1 bilateral fresh TRAIN source gate. The above pilot history must be excluded or explicitly categorized in custody. Do **not** retroactively swap samples in the old pilot or extrapolate invalidity to every historical result. New-model science remains unauthorized until independent peer reviews and G0 pass.

**Machine-readable per-game evidence:** `research/BINDING180_PILOT_11_HISTORICAL_RUN_EXPOSURE_MATRIX_20261010.json` (each game with original Binding selection index, pilot index and frozen-route membership).
