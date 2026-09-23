#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="${PLANLATCH_ENV:-/opt/planlatch-v720-py312}"
WHEELS="${PLANLATCH_WHEELHOUSE:-$ROOT/.runtime-wheels}"
MODEL="${PLANLATCH_MODEL_DIR:-$ROOT/.qwen3-1.7b-70d244}"
mkdir -p "$ROOT" "$WHEELS" "$MODEL"
export PLANLATCH_MODEL_DIR="$MODEL"
export HF_HOME="${HF_HOME:-$ROOT/.hf-planlatch-v720}"

apt-get update
apt-get install -y --no-install-recommends python3.12 python3.12-venv python3-pip ca-certificates curl git
python3.12 -m venv "$ENV"
"$ENV/bin/python" -m pip install --upgrade 'pip==25.0.1'

"$ENV/bin/python" -m pip download --no-deps --only-binary=:all: -d "$WHEELS"   numpy==2.3.3 transformers==4.51.3 tokenizers==0.21.1
"$ENV/bin/python" -m pip download --no-deps --only-binary=:all:   --index-url https://download.pytorch.org/whl/cu130 -d "$WHEELS" 'torch==2.13.0+cu130'

verify_one() {
  local pat="$1" expected="$2"
  local f
  f=$(compgen -G "$WHEELS/$pat" | head -n1 || true)
  test -n "$f"
  test "$(sha256sum "$f" | awk '{print $1}')" = "$expected"
}
verify_one 'numpy-2.3.3-*.whl' d9192da52b9745f7f0766531dcfa978b7763916f158bb63bdb8a1eca0068ab20
verify_one 'tokenizers-0.21.1-*.whl' 2dd9a0061e403546f7377df940e866c3e678d7d4e9643d0461ea442b4f89e61a
verify_one 'torch-2.13.0+cu130-*.whl' 8db7338e6895c3d4bd89a02ff4209507d1f0cf2ffeb3b898538b5a07d1ea8c1e
verify_one 'transformers-4.51.3-*.whl' fd3279633ceb2b777013234bbf0b4f5c2d23c4626b05497691f00cfda55e8a83

NP=$(compgen -G "$WHEELS/numpy-2.3.3-*.whl" | head -n1)
TK=$(compgen -G "$WHEELS/tokenizers-0.21.1-*.whl" | head -n1)
TR=$(compgen -G "$WHEELS/transformers-4.51.3-*.whl" | head -n1)
TO=$(compgen -G "$WHEELS/torch-2.13.0+cu130-*.whl" | head -n1)

"$ENV/bin/python" -m pip install --no-deps "$NP" "$TK" "$TR"
"$ENV/bin/python" -m pip install --no-deps "$TO"
"$ENV/bin/python" -m pip install --extra-index-url https://download.pytorch.org/whl/cu130 -r "$ROOT/execution_assets/exact_py312_deps.txt"
"$ENV/bin/python" -m pip check

"$ENV/bin/python" - <<'PY'
import importlib.metadata as m, sys
exp={'torch':'2.13.0+cu130','transformers':'4.51.3','tokenizers':'0.21.1','numpy':'2.3.3','huggingface-hub':'0.36.2'}
assert sys.version_info[:2]==(3,12), sys.version
for k,v in exp.items():
    assert m.version(k)==v,(k,m.version(k),v)
print("CORE_RUNTIME_VERSIONS_PASS")
PY

"$ENV/bin/python" - <<'PY'
import os
from huggingface_hub import snapshot_download
root=snapshot_download(
    repo_id='Qwen/Qwen3-1.7B',
    revision='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e',
    cache_dir=os.environ['HF_HOME'],
)
print("MODEL_SNAPSHOT_DOWNLOADED",root)
PY

"$ENV/bin/python" - <<'PYHASH'
from pathlib import Path
import hashlib, os
from huggingface_hub import snapshot_download
root=Path(snapshot_download(
    repo_id='Qwen/Qwen3-1.7B',
    revision='70d244cc86ccca08cf5af4e1e306ecf908b1ad5e',
    cache_dir=os.environ['HF_HOME'],
))
expected={
'config.json':'1ddb5b89ebc90dcb417a45c213d818577e65976454d29385c8f6140771d95197',
'generation_config.json':'2325da0f15bb848e018c5ae071b7943332e9f871d6b60e2ed22ca97d4cb993d2',
'merges.txt':'8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5',
'model-00001-of-00002.safetensors':'169ad53ec313c3a34b06c0809216e4fc072cce444a5d4ff2b59690d064130ed5',
'model-00002-of-00002.safetensors':'912becff8d60672aa8628ef08c05898d9adf17c2ad4ae3caf99b065622fdeff9',
'model.safetensors.index.json':'0d660e94b165eb912669a5249dff44b83188c4777a07ddb9611fb78d91b0578d',
'tokenizer.json':'aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4',
'tokenizer_config.json':'d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101',
'vocab.json':'ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910',
}
for name,want in expected.items():
    got=hashlib.sha256((root/name).read_bytes()).hexdigest()
    assert got==want,(name,got,want)
print("MODEL_HASHES_PASS")
PYHASH

nvidia-smi --query-gpu=uuid,name,vbios_version,driver_version --format=csv,noheader,nounits
"$ENV/bin/python" - <<'PY'
import torch
print("torch",torch.__version__,"cuda",torch.version.cuda,"cuda_available",torch.cuda.is_available())
assert torch.__version__=='2.13.0+cu130'
assert torch.version.cuda=='13.0'
assert torch.cuda.is_available()
PY

"$ENV/bin/python" -m pip freeze --all | sort > "$ENV/.planlatch_v720_freeze.actual"
sort "$ROOT/execution_assets/exact_py312_pip_freeze.txt" > "$ENV/.planlatch_v720_freeze.expected"
diff -u "$ENV/.planlatch_v720_freeze.expected" "$ENV/.planlatch_v720_freeze.actual"
touch "$ENV/.planlatch_v720_ready"
echo RUNTIME_BOOTSTRAP_PASS
