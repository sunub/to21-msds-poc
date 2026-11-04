#!/bin/bash
# 학습 환경 준비 (RunPod Pod 안, /workspace/to21에서). 11/04 F
#   bash finetune/pod_setup.sh
# 학습 가상환경 /workspace/venv-train을 만들고 finetune/requirements.txt를 깐 뒤 CPU 시험(11개)을 돌린다.
# torch는 uv가 Pod의 CUDA 드라이버에 맞는 판을 고른다(--torch-backend=auto, 팀 vLLM 설치와 같은 방식).
# 평가용 vLLM은 따로 deploy/runpod/setup_vllm.sh로 /workspace/venv에 깐다(vLLM이 자기 torch 판을 깐다).
set -e
export HF_HOME=/workspace/hf                  # 모델은 영구 디스크(/workspace)에 받는다
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; }
export PATH=$HOME/.local/bin:$PATH
[ -x /workspace/venv-train/bin/python ] || uv venv /workspace/venv-train --python 3.12
. /workspace/venv-train/bin/activate
uv pip install --no-cache torch --torch-backend=auto
uv pip install --no-cache -r finetune/requirements.txt
python -c "import torch, transformers, peft; print('torch', torch.__version__, 'cuda', torch.version.cuda, '| transformers', transformers.__version__, '| peft', peft.__version__)"
python -m pytest finetune/tests -q
nvidia-smi --query-gpu=index,name,memory.total --format=csv
df -h /workspace | tail -1
echo "준비 끝. 새 터미널마다: source /workspace/venv-train/bin/activate && export HF_HOME=/workspace/hf"
