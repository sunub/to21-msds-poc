#!/bin/bash
# Pod 안에서 돈다. vLLM을 깔고 모델을 받는다. 끝나면 표시 파일을 남겨 다음에는 건너뛴다.
# 사용: setup_vllm.sh <모델 이름>
set -e
MODEL="$1"
export HF_HOME=/workspace/hf
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; }
export PATH=$HOME/.local/bin:$PATH
uv venv /workspace/venv --python 3.12 --clear
. /workspace/venv/bin/activate
uv pip install --no-cache "vllm==0.32.0" --torch-backend=auto
python -c "import vllm; print(\"vllm\", vllm.__version__)"
/workspace/venv/bin/hf download "$MODEL"
touch "/workspace/.vllm_ready_${MODEL//\//_}"
echo "[$(date +%T)] SETUP_DONE"
