# PlanLatch v7.20 execution checkout

This checkout is frozen for execution. No further design/fidelity/review loop is part of the run path.

Canonical Git ref:
- branch: `planlatch-v7.20-exec`
- immutable tag: `planlatch-v7.20-exec-v1`

On a fresh CUDA-13-capable Vast host:

```bash
git clone --branch planlatch-v7.20-exec-v1 --single-branch https://github.com/tungooxx/Plancarry.git
cd Plancarry
./run_v720.sh
```

The runner verifies all frozen v7.20 science files, the committed exact36 input, the full Python package freeze, exact core wheel hashes, exact Qwen revision/file hashes, CUDA availability, and the 36/576 frame before running the real model.

The selected environment rows and final `root.json` are already materialized, so ALFWorld/TextWorld is not required on the GPU host.

Frozen execution input:
- universe: `2bbd5228e125a6e3aaf3a7b41b7f0c44f194323bc6ba84880253cfff91056d26`
- fixed36 receipt: `816185dbb1d966057a56d2994afc678ead6acdf8571b56a02616f240fc92a734`
- portable root: `79c3794975964e6a201458c4baa51028cca936d9c209c2f14c491de0668a0d2f`
- frame: `25991201dd708282801bef9473c209b17a64c7988e8205ebdee4e021153382af`
- partitions: FIT12 / PILOT8 / SUPPORT12 / CROSS_REALIZATION4

The deterministic fixed36 receipt replaces only the rejected future-beacon/server-authority wrapper. It does not change the PlanLatch MLP-latch mechanism, model, source/relay estimands, G1-G20, or frame.
