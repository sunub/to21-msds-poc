#!/bin/bash
# 글자 추출 API(version17)와 GPU 워커를 함께 띄운다. 8020 서버가 이 API로 PDF를 보내게 하려면
# 8020을 띄우기 전에 MSDS_EXTRACTION_API_URL=http://127.0.0.1:8000 을 설정한다 (service/preprocess_v17.py).
# 비밀번호는 deploy/htodb/.env에서 읽어 명령 줄에 남기지 않는다. 작업 DB는 서비스 DB(msds_service)와 별도다.
#
#   backend/scripts/serve_extraction_api.sh                    API 8000 + 워커(gpu:0), 작업 DB msds_extraction
#   MSDS_OCR_DEVICE=cpu backend/scripts/serve_extraction_api.sh   GPU 없이 (느리다)
#   MSDS_EXTRACTION_PORT=8001 MSDS_JOBS_DB=<DB 이름> ...          포트, 작업 DB 바꾸기
# API와 워커는 같은 DB와 같은 파일 경로(data/pages/api, data/extraction_api)를 써야 한다.
set -euo pipefail

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(dirname "$BACKEND")"
DB_ENV="$ROOT/deploy/htodb/.env"
[ -f "$DB_ENV" ] || {
  echo "$DB_ENV 가 없습니다. deploy/htodb/TEAM_SETUP.md를 보고 만들어 주세요." >&2
  exit 1
}

set -a
# shellcheck disable=SC1090
. "$DB_ENV"
set +a

export PGPASSWORD="$HTODB_PG_PASSWORD"
export MSDS_JOBS_DATABASE_URL="host=127.0.0.1 port=${HTODB_PG_PORT:-5433} dbname=${MSDS_JOBS_DB:-msds_extraction} user=kdb"

cd "$BACKEND"
.venv/bin/uvicorn --app-dir src msds.api.extraction_app:app --host 127.0.0.1 --port "${MSDS_EXTRACTION_PORT:-8000}" &
api=$!
args=(--ocr-device "${MSDS_OCR_DEVICE:-gpu:0}")
[ "${MSDS_USE_DOCLING:-1}" = "0" ] && args+=(--no-docling)
PYTHONPATH=src .venv/bin/python -m msds.preprocess.jobs "${args[@]}" &
worker=$!

trap 'kill "$api" "$worker" 2>/dev/null || true' EXIT INT TERM
wait -n "$api" "$worker"   # 둘 중 하나라도 끝나면 나머지도 내린다
