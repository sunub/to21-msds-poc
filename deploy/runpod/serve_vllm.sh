#!/bin/bash
# Pod 안에서 돈다. vLLM 서버를 띄운다. 키는 /workspace/vllm_api_key 에서 읽는다.
# 사용: serve_vllm.sh <모델 이름>
MODEL="$1"
export HF_HOME=/workspace/hf
export VLLM_USE_DEEP_GEMM=0  # Pod에 DeepGEMM JIT에 필요한 nvcc>=12.9가 없다
export VLLM_API_KEY=$(cat /workspace/vllm_api_key)
exec /workspace/venv/bin/vllm serve "$MODEL" --trust-remote-code \
  --host 0.0.0.0 --port 8000 --api-key "$VLLM_API_KEY" \
  --max-model-len 40960 --max-num-seqs 64 --gpu-memory-utilization 0.85 \
  --limit-mm-per-prompt "{\"image\": 2}" \
  --structured-outputs-config "{\"backend\": \"xgrammar\", \"disable_any_whitespace\": true}"
