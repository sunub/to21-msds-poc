#!/bin/bash
# Pod 안에서 돈다. vLLM 서버를 띄운다. 키는 /workspace/vllm_api_key 에서 읽는다.
# 사용: [MAX_MODEL_LEN=.. MAX_NUM_SEQS=.. GPU_UTIL=.. BATCH_INVARIANT=0|1 PREFIX_CACHING=0|1] serve_vllm.sh <모델 이름>
# 값은 pod_up.py가 configs/models.yaml 태그의 server 설정으로 넘긴다. 없으면 A100 80GB에서 쓰던 값이다.
MODEL="$1"
export HF_HOME=/workspace/hf
export VLLM_USE_DEEP_GEMM=0  # Pod에 DeepGEMM JIT에 필요한 nvcc>=12.9가 없다
# FlashInfer 샘플러는 미리 만든 커널이 없는 GPU(11/3 A6000 sm_86)에서 켤 때 ninja·nvcc로 JIT 빌드하다 멈춘다.
# PyTorch 샘플러를 쓴다. temperature 0(가장 확률 높은 토큰)에서는 고르는 값이 같다
export VLLM_USE_FLASHINFER_SAMPLER=0
export PATH=/workspace/venv/bin:$PATH   # 다른 JIT 단계가 venv의 ninja를 찾도록
export VLLM_API_KEY=$(cat /workspace/vllm_api_key)
EXTRA=()
# 결정적 모드: 같은 입력이면 함께 처리되는 요청 수와 순서에 상관없이 같은 출력 (vLLM batch invariance, 베타)
[ "${BATCH_INVARIANT:-0}" = "1" ] && export VLLM_BATCH_INVARIANT=1
[ "${PREFIX_CACHING:-1}" = "0" ] && EXTRA+=(--no-enable-prefix-caching)
exec /workspace/venv/bin/vllm serve "$MODEL" --trust-remote-code \
  --host 0.0.0.0 --port 8000 --api-key "$VLLM_API_KEY" \
  --max-model-len "${MAX_MODEL_LEN:-40960}" --max-num-seqs "${MAX_NUM_SEQS:-64}" \
  --gpu-memory-utilization "${GPU_UTIL:-0.85}" \
  --limit-mm-per-prompt "{\"image\": 2}" \
  --structured-outputs-config "{\"backend\": \"xgrammar\", \"disable_any_whitespace\": true}" \
  "${EXTRA[@]}"
