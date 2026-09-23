#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
ENV="${PLANLATCH_ENV:-/opt/planlatch-v720-py312}"
OUT="${PLANLATCH_OUTPUT:-results/science/planlatch_v7_20_exact36_v1}"
export PLANLATCH_ENV="$ENV"
export PLANLATCH_OUTPUT="$OUT"
export PLANLATCH_WHEELHOUSE="${PLANLATCH_WHEELHOUSE:-$ROOT/.runtime-wheels}"
export HF_HOME="${HF_HOME:-$ROOT/.hf-planlatch-v720}"
export PYTHONHASHSEED=0
export TOKENIZERS_PARALLELISM=false
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

die() { echo "PlanLatch v7.20: $*" >&2; exit 2; }

# Verify immutable science bytes and committed exact36 input before model/runtime work.
test "$(sha256sum V720_IMPLEMENTATION_MANIFEST.json | awk '{print $1}')" = d4cf9e095f34f6f2cb3aa87db8a721828fa45e5249117481018e1291c7f0be82 || die "implementation manifest mismatch"
python3 - <<'PY'
from pathlib import Path
import hashlib,json
m=json.loads(Path('V720_IMPLEMENTATION_MANIFEST.json').read_text())
for rel,want in m['files'].items():
    p=Path(rel)
    if not p.is_file(): raise SystemExit(f'missing frozen file: {rel}')
    got=hashlib.sha256(p.read_bytes()).hexdigest()
    if got!=want: raise SystemExit(f'frozen file hash mismatch: {rel} {got} != {want}')
checks={
 'results/design/planlatch_v7_20_train_input/root.json':'79c3794975964e6a201458c4baa51028cca936d9c209c2f14c491de0668a0d2f',
 'results/design/planlatch_v7_20_execution_fixed36_v1/membership_receipt.json':'41cadd45b57967097e195dded6b831f4d915aa84c4574abdac2f0a7ec0e7b75c',
 'results/design/planlatch_v7_20_execution_fixed36_v1/precomputed_selected_rows.json':'9e3b8db6f2aead894ad195729e784387cdc85b32675e26322273dc35244e1740',
 'execution_assets/planlatch_v720_runtime_lock_v4.json':'9fe4f5c568418eb5b126bffe386a4e0d52e0048ad5d5a80042a51bee10fdd2ad',
 'execution_assets/collector_v2/reserved_host_attest.py':'4875e59397f60d250ca2c8c6803dde4a92802d36b4387ccab0532ac1edb5d0d7',
}
for rel,want in checks.items():
    p=Path(rel); got=hashlib.sha256(p.read_bytes()).hexdigest()
    if got!=want: raise SystemExit(f'execution asset hash mismatch: {rel} {got} != {want}')
print('FROZEN_EXECUTION_BYTES_PASS')
PY

if [ ! -f "$ENV/.planlatch_v720_ready" ]; then
  bash execution_assets/bootstrap_runtime.sh
fi

# Recheck exact runtime state even when reusing a prepared environment.
"$ENV/bin/python" -m pip freeze --all | sort > "$ENV/.planlatch_v720_freeze.actual"
sort execution_assets/exact_py312_pip_freeze.txt > "$ENV/.planlatch_v720_freeze.expected"
diff -u "$ENV/.planlatch_v720_freeze.expected" "$ENV/.planlatch_v720_freeze.actual"
"$ENV/bin/python" -m pip check

"$ENV/bin/python" - <<'PY'
import torch
import planlatch_v7_20_execution_driver as d
import planlatch_v7_20_runner as core
root=d.load_root_input('results/design/planlatch_v7_20_train_input/root.json')
frame=core.compile_pre_response_frame(root.tasks)
core.verify_complete_cells(frame)
counts={p:list(frame.partition_by_block.values()).count(p) for p in ('FIT','PILOT','SUPPORT','CROSS_REALIZATION')}
assert len(frame.block_ids)==36 and len(frame.cells)==576
assert counts=={'FIT':12,'PILOT':8,'SUPPORT':12,'CROSS_REALIZATION':4},counts
assert frame.frame_hash=='25991201dd708282801bef9473c209b17a64c7988e8205ebdee4e021153382af',frame.frame_hash
assert torch.__version__=='2.13.0+cu130',torch.__version__
assert torch.version.cuda=='13.0',torch.version.cuda
assert torch.cuda.is_available(),'CUDA unavailable'
print('EXECUTION_PREFLIGHT_PASS',torch.cuda.get_device_name(0),counts)
PY

[ ! -e "$OUT" ] || die "output namespace already exists: $OUT"

"$ENV/bin/python" - <<'PY'
import os
from planlatch_v7_20_execution_driver import load_root_input,run_pipeline
from planlatch_v7_9_model_runtime import RealQwenRuntime
root=load_root_input('results/design/planlatch_v7_20_train_input/root.json')
backend=RealQwenRuntime(device='cuda')
run_pipeline(root,backend,os.environ['PLANLATCH_OUTPUT'],synthetic=False)
PY
