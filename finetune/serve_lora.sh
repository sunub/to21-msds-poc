#!/bin/bash
# 학습한 LoRA를 붙여 vLLM을 띄운다 (평가용, RunPod Pod 안에서 /workspace/to21 기준). 11/04 F
#   bash finetune/serve_lora.sh <원본 모델> <adapter 폴더>
#   예: bash finetune/serve_lora.sh Qwen/Qwen3.6-35B-A3B-FP8 finetune/out/to21_lora_qwen36_35b_a3b_v1/adapter
# 한 서버가 두 이름을 받는다: <원본 모델>(학습 전)과 to21-ft(학습 후). 같은 서버·같은 정밀도로 전후를 비교한다.
# 설정은 팀 서버(deploy/runpod/serve_vllm.sh)와 같다(vLLM 0.32.0, 공백 금지 구조화 출력 ADR-017, 이미지 2장). LoRA만 더한다.
# 먼저: bash deploy/runpod/setup_vllm.sh <원본 모델>   (vLLM을 /workspace/venv에 깔고 원본을 받는다. 처음 한 번 15~25분)
# 바꿀 수 있는 값(환경변수): HOST(127.0.0.1. PC에서는 ssh 터널로 붙는다) PORT(8000) TP(GPU 수) MAX_MODEL_LEN(49152)
#   MAX_NUM_SEQS(16) GPU_UTIL(0.90) MM_LIMIT('{"image": 2}', 글 전용 모델(Qwen3-30B-A3B)은 MM_LIMIT= 으로 비운다) NAME(to21-ft)
# 키: /workspace/vllm_api_key (없으면 새로 만든다). PC .env의 FT_VLLM_API_KEY에 같은 값을 둔다. 채팅·노션·저장소에 적지 않는다.
set -e
MODEL="$1"; ADAPTER="$2"; NAME="${NAME:-to21-ft}"
if [ -z "$MODEL" ] || [ ! -f "$ADAPTER/adapter_config.json" ]; then
  echo "사용: bash finetune/serve_lora.sh <원본 모델> <adapter 폴더(adapter_config.json이 있는 곳)>"; exit 1
fi
RANK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['r'])" "$ADAPTER/adapter_config.json")
WS="${WORKSPACE:-/workspace}"                # Pod의 영구 디스크
export HF_HOME=$WS/hf
export VLLM_USE_DEEP_GEMM=0                    # 팀 서버와 같은 이유(serve_vllm.sh)
export VLLM_USE_FLASHINFER_SAMPLER=0
export PATH=$WS/venv/bin:$PATH
if [ ! -s "$WS/vllm_api_key" ]; then
  (umask 077; python3 -c "import secrets; print(secrets.token_urlsafe(24))" > "$WS/vllm_api_key")
  echo "새 vLLM 키를 $WS/vllm_api_key에 만들었습니다(값은 cat으로 보고 PC .env에만 둔다)"
fi
export VLLM_API_KEY=$(cat "$WS/vllm_api_key")   # vLLM은 이 환경변수로 키를 받는다. 인자로 넘기지 않아 ps에 키가 보이지 않는다
TP="${TP:-$(nvidia-smi -L | wc -l)}"
DEFAULT_MM='{"image": 2}'
MM_LIMIT="${MM_LIMIT-$DEFAULT_MM}"            # 없으면 이미지 2장, 빈 값이면 넣지 않는다(글 전용 모델)
MM=()
[ -n "$MM_LIMIT" ] && MM=(--limit-mm-per-prompt "$MM_LIMIT")
echo "vLLM: $MODEL + LoRA $NAME(r=$RANK, $ADAPTER), GPU $TP장, ${HOST:-127.0.0.1}:${PORT:-8000}"
exec "$WS/venv/bin/vllm" serve "$MODEL" --trust-remote-code \
  --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" \
  --tensor-parallel-size "$TP" \
  --max-model-len "${MAX_MODEL_LEN:-49152}" --max-num-seqs "${MAX_NUM_SEQS:-16}" \
  --gpu-memory-utilization "${GPU_UTIL:-0.90}" \
  "${MM[@]}" \
  --structured-outputs-config '{"backend": "xgrammar", "disable_any_whitespace": true}' \
  --enable-lora --max-lora-rank "$RANK" --max-loras 1 --lora-modules "$NAME=$ADAPTER"
