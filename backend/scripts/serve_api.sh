#!/bin/bash
# 추출과 판정을 한 앱으로 8020에 띄운다. 화면도 이 주소 하나만 부른다 (docs/A1_작업_흐름_실행.md).
# 비밀번호는 deploy/htodb/.env에서 읽어 명령 줄에 남기지 않는다.
#
#   backend/scripts/serve_api.sh            기본 DB(msds_service), 포트 8020
#   MSDS_API_PORT=8030 backend/scripts/serve_api.sh
#   MSDS_API_RELOAD=1 backend/scripts/serve_api.sh    코드 수정 때 다시 읽기 (돌던 작업은 끊긴다)
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
: "${JUDGE_PG_PASSWORD:?JUDGE_PG_PASSWORD가 없습니다. scripts/b2_migrate.py --database <DB>를 먼저 실행해 주세요}"

DB_NAME="${MSDS_SERVICE_DB:-msds_service}"
# 이 값들은 .env에 두지 않는다. .env는 시험과 다른 스크립트도 읽어, 넣으면 그쪽까지 DB·판정 모드가 된다
export PGPASSWORD="$HTODB_PG_PASSWORD"
export MSDS_SERVICE_DATABASE_URL="host=127.0.0.1 port=${HTODB_PG_PORT:-5433} dbname=$DB_NAME user=kdb"
export MSDS_JUDGE_IN_EXTRACT_APP=1
export JUDGE_PG_DATABASE="$DB_NAME"
export MSDS_PREPROCESS_WORKERS="${MSDS_PREPROCESS_WORKERS:-1}"
export MSDS_EXTRACT_WORKERS="${MSDS_EXTRACT_WORKERS:-1}"
export MSDS_MODEL_MAX_INFLIGHT="${MSDS_MODEL_MAX_INFLIGHT:-8}" # 48GB 서버의 max_num_seqs. 같은 컴퓨터의 다른 프로세스와 값이 같아야 한다

# 판정 설명도 추출과 같은 모델 서버를 쓴다. 기본값(80GB 태그)으로 48GB 서버를 부르지 않게 맞춘다
if [ -z "${MSDS_EXPLAIN_MODEL:-}" ] && [ -f "$ROOT/.env" ]; then
  tag="$(sed -n 's/^MSDS_SERVICE_MODEL=//p' "$ROOT/.env" | tail -1)"
  [ -n "$tag" ] && export MSDS_EXPLAIN_MODEL="$tag"
fi

cd "$BACKEND"
args=(--app-dir src msds.api.extract_app:app --host 127.0.0.1 --port "${MSDS_API_PORT:-8020}")
[ "${MSDS_API_RELOAD:-0}" = "1" ] && args+=(--reload)
exec .venv/bin/uvicorn "${args[@]}"
