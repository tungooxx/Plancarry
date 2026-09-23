# PlanLatch v7.20 GitHub -> Vast execution workflow

Canonical repository:

- HTTPS: `https://github.com/tungooxx/Plancarry.git`
- execution branch: `planlatch-v7.20-exec`
- immutable execution tag: `planlatch-v7.20-exec-v1`

## Fresh Vast host

Clone the immutable execution tag:

```bash
git clone --branch planlatch-v7.20-exec-v1 --single-branch https://github.com/tungooxx/Plancarry.git
cd Plancarry
git rev-parse HEAD
./run_v720.sh
```

The tag is intentionally detached/frozen. Do not switch to `main` before execution.

## Updating the execution branch before a future tag

Only operational packaging changes may be added without changing frozen science. If the branch itself is intentionally updated:

```bash
git clone --branch planlatch-v7.20-exec --single-branch https://github.com/tungooxx/Plancarry.git
cd Plancarry
git pull --ff-only origin planlatch-v7.20-exec
git rev-parse HEAD
```

Scientific execution should use the immutable tag named above unless a later tag is explicitly frozen.

## Runtime behavior

`./run_v720.sh` performs the execution preflight itself. It verifies the frozen v7.20 implementation/manifests, exact36 input, runtime-lock asset, exact Python package freeze, exact core wheel hashes, exact Qwen revision/file hashes, CUDA availability, and the 36-block / 576-cell frame before loading the real model.

The exact36 input is already materialized in Git. ALFWorld/TextWorld is not required on the GPU host.

Do not commit credentials, model caches, runtime wheels, virtual environments, or scientific outputs.
