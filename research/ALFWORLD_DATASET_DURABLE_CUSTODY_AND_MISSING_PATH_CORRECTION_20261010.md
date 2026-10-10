# PlanCarry ALFWorld original archive — durable custody / no-more-"lost dataset" correction

**Checked 2026-10-10.** This is a verified *data-retention and reproducibility* record, **not** BIND-v0.3 scientific G0 approval.

## Findings verified on GPU Lab CPU host

The actual ALFWorld public source archive **has NOT been lost**:

- Original local archive at inspection: `/workspace/local-vlm/.cache/plancarry-source-audit/json_2.1.3_tw-pddl_alfworld042.zip`
- SHA-256: `5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`
- Size: `36,507,267` bytes
- Zip metadata: `4,027` `game.tw-pddl` member paths, split counts `train=3,553`, `valid_train=200`, `valid_seen=140`, `valid_unseen=134`.
- `train/pick_and_place_simple-*`: **790** game filenames across **322** family names, matching historical fixed `790` candidate pool. This inspection counted ZIP member **names only**; it neither read game contents nor launched a TRAIN simulator.
- Read-only check job: `local_70d214c05d2540ae`, membership job `local_14f6b60afe394a73`.

What is missing in the **current CPU runner** is only the historical extracted-path/environment convention:
- `/opt/gpu-lab/data/plancarry-alfworld/json_2.1.1/` is not present.
- `/opt/gpu-lab/envs/plancarry-alfworld-py312` and `plancarry-alfworld-py313` are not present.
- These absences **do not establish that the original public dataset was erased**. They also do not prove the precise reason / timing of directory disappearance; a different runner, mount, env lifecycle or cleanup remains a hypothesis until filesystem provisioning logs are recovered.

## Durable copy completed and retrieved

The original archive was explicitly **promoted** into GPU Lab durable SHA-256 artifact storage and independently queried:

- Durable URI: `sha256:5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`
- Canonical reference: `plancarry:alfworld042:original-json_2.1.3_tw-pddl-archive:sha256:5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`
- Artifact role: `ORIGINAL_PUBLIC_DATASET_ARCHIVE`
- Recorded original source job `local_70d214c05d2540ae`
- Durable artifact `get` returned `verified: true`.
- Promotion **does not imply** any Python env or expanded game folder was preserved. Neither the dataset archive itself nor its public filenames certify a complete prior model-inference ledger.

## Recovery contract for any future worker

1. **Do not say “ALFWorld data lost” without checking the durable artifact ID above.** Query `local_protected_artifact_get(sha256)`; if verified, use `local_protected_artifact_restore(sha256, destination)` into a project-owned persistent workspace and verify SHA-256. Never assume `/opt/gpu-lab/...` is mounted in the next runner.
2. Recreate a separately pinned Python environment and install the backend as needed, capturing Python, TextWorld, Fast Downward/ALFWorld versions, source revisions, package hashes and physical runtime roots in the job manifest. Do not equate missing old interpreter with missing dataset.
3. If an experiment is approved, mount/unpack original contents into an explicit deterministic per-project path. Preserve source game bytes and split labels. Hash the exact game files and refuse silent source regeneration.
4. Store run-level `game_sha256`, canonical game family/trial/split, model revision, exact request/response status, source-plan creation and actual actions in immutable durable run artifacts. A failed or never-executed model request must be distinguishable from a successful model response.
5. **Scientific review is a separate issue:** frozen BIND-v0.3 G0 is still `NO_GO_FOR_G1_UNDER_CURRENT_EVIDENCE` because the complete *historical request/response usage ledger* and authenticated *PDDL full-state/RNG equivalence* are not yet proven. Do not treat a re-downloaded or restored archive as evidence that prior games were unused.
6. **ALFWorld itself need not be abandoned.** A proposed new ALFWorld study can use explicitly prospective source selection and new verified logging/clone policy, but because BIND-v0.3 froze a terminal no-rescue requirement, any changed population/state contract must be independently reviewed as a separate design. Switching to an entirely different TextWorld symbolic task was an engineering option, not a requirement caused by disappearance of ALFWorld data.

**Root-cause verdict:** original public ZIP exists and is now durable; previous extracted `/opt` data folder and env are currently absent. Exact cleanup/reprovisioning cause **not proven**. The real recurring engineering problem was reliance on ephemeral/host-specific extraction and interpreter paths without a protected source artifact plus a one-command restore manifest. This custody record fixes the former source-preservation gap but does not manufacture missing historical experiment logs.

**Cost/security:** hash and ZIP filename inspection only; no ALFWorld game content, model calls, TRAIN execution, GPU, paid API or confirmation data.
