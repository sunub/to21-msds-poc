#!/bin/bash
# Pod 안: vLLM(8000)과 앱(8020)을 켠다. 이미 떠 있으면 건너뛴다. pod_app_setup.sh 다음에 실행한다.
#   bash /workspace/to21/deploy/runpod/demo/pod_start.sh                 # 태그 qwen36_35b_runpod_48g, 원본 모델
#   RESTART_APP=1 bash ...                                               # 코드를 새로 받은 뒤 앱만 다시 켠다
#   TAG=<models.yaml 태그> MODEL=<vllm serve 모델> bash ...               # 다른 모델: 먼저 기존 vLLM을 끈다
# vLLM은 0.0.0.0:8000에 붙지만 Pod는 8080(Apache)·22만 열어 밖에서는 닿지 않는다(2026-11-04 확인).
# 체험 서버(심사위원 여럿)라 동시 추출 3개로 띄운다. 3건 동시 업로드에서 마지막 문서 225초 → 169초 (2026-11-04, L40S).
# 원격 ssh 로 부를 때는 `ssh -n ... 'setsid bash pod_start.sh > /workspace/start.log 2>&1 < /dev/null &'` 처럼 띄운다(아니면 ssh가 안 끝난다).
set -euo pipefail
W=/workspace; APP=$W/to21
TAG="${TAG:-qwen36_35b_runpod_48g}"; MODEL="${MODEL:-Qwen/Qwen3.6-35B-A3B-FP8}"
models() { curl -s -m 3 -H "Authorization: Bearer $(cat $W/vllm_api_key)" http://127.0.0.1:8000/v1/models || true; }

if ! models | grep -q '"id"'; then
  if pgrep -f "[v]llm serve" >/dev/null; then
    echo "vLLM이 이미 뜨는 중이다. 기다린다"
  else
    # 48GB 태그의 server 값(models.yaml). setup_vllm.sh 가 /workspace 에 받아 둔 vLLM 0.32.0 을 쓴다
    cp $APP/deploy/runpod/serve_vllm.sh $W/serve_vllm.sh
    MAX_MODEL_LEN=49152 MAX_NUM_SEQS=8 GPU_UTIL=0.92 setsid bash $W/serve_vllm.sh "$MODEL" > $W/serve_vllm.log 2>&1 < /dev/null &
    echo "vLLM 기동 (모델을 올리는 데 첫 기동 약 7분)"
  fi
  for _ in $(seq 1 90); do models | grep -q '"id"' && break; sleep 10; done
fi
models | grep -q "\"id\":\"$MODEL\"" || { echo "vLLM이 $MODEL 로 떠 있지 않다: $W/serve_vllm.log (다른 모델이면 그 vLLM을 먼저 끈다)" >&2; exit 1; }
grep -E "Maximum concurrency" $W/serve_vllm.log | tail -1 || true

# 앱 설정: 모델 주소·키·태그(키 값은 화면에 내지 않는다)
# 전처리는 예전 방식(legacy). version17(#172 기본값)은 OCR 패키지가 필요한데 체험 서버는 OCR 그룹을 깔지 않아
# 글꼴 깨짐·스캔 PDF가 실패한다. legacy는 그런 쪽을 이미지로 넘긴다. OCR을 깔고 확인한 뒤에만 PREPROCESS= 로 바꾼다
{ echo "RUNPOD_VLLM_BASE_URL=http://127.0.0.1:8000/v1"; echo "RUNPOD_VLLM_API_KEY=$(cat $W/vllm_api_key)"; echo "MSDS_SERVICE_MODEL=$TAG"
  echo "MSDS_PREPROCESS=${PREPROCESS-legacy}"; } > $APP/.env

if [ "${RESTART_APP:-0}" = "1" ] && pgrep -f "[u]vicorn --app-dir src msds.api.extract_app" >/dev/null; then
  kill $(pgrep -f "[u]vicorn --app-dir src msds.api.extract_app")
  for _ in $(seq 1 30); do pgrep -f "[u]vicorn --app-dir src msds.api.extract_app" >/dev/null || break; sleep 1; done
fi
if ! curl -s -m 3 http://127.0.0.1:8020/api/health | grep -q '"ok":true'; then
  ( cd $APP && MSDS_PREPROCESS="${PREPROCESS-legacy}" MSDS_EXTRACT_WORKERS=3 MSDS_PREPROCESS_WORKERS=2 setsid bash backend/scripts/serve_api.sh > $W/app.log 2>&1 < /dev/null & )
  for _ in $(seq 1 30); do curl -s -m 3 http://127.0.0.1:8020/api/health | grep -q '"ok":true' && break; sleep 2; done
fi
HEALTH=$(curl -s -m 3 http://127.0.0.1:8020/api/health || true)
echo "$HEALTH" | grep -q "\"model_tag\":\"$TAG\"" || { echo "앱이 뜨지 않았거나 태그가 다르다: $HEALTH / $W/app.log" >&2; exit 1; }
echo "앱: $HEALTH"
echo "외부 확인: curl -u to21:<비밀번호> -A Mozilla/5.0 https://\$RUNPOD_POD_ID-8080.proxy.runpod.net/api/health"
