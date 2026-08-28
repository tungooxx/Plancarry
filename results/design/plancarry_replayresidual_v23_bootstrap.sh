#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${PLANCARRY_V23_VENV:-/workspace/GPU-Lab/venvs/plancarry-v23}"
DATA="${PLANCARRY_ALFWORLD_STORE:-/opt/gpu-lab/envs/plancarry-alfworld-data}"
if [ ! -x "$VENV/bin/python" ]; then python3 -m venv "$VENV"; fi
export PATH="$VENV/bin:$PATH"
python -m pip install -U pip wheel setuptools
python -m pip install 'torch==2.13.0' 'transformers==4.51.3' 'tokenizers==0.21.1'
python -m pip install -r "$ROOT/requirements_replayresidual_v21_alfworld_py313.txt"
mkdir -p "$DATA" /opt/gpu-lab/data
python "$ROOT/alfworld_text_setup.py" --data-dir "$DATA"
if [ ! -e /opt/gpu-lab/data/plancarry-alfworld ]; then ln -s "$DATA" /opt/gpu-lab/data/plancarry-alfworld; fi
python -c "import torch,transformers,tokenizers; assert torch.__version__=='2.13.0+cu130',torch.__version__; assert transformers.__version__=='4.51.3'; assert tokenizers.__version__=='0.21.1'; print('V23_BOOTSTRAP_PASS',torch.__version__,transformers.__version__,tokenizers.__version__)"
