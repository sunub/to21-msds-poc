#!/usr/bin/env bash
# TO21 지식DB(HTODB)를 로컬 PostgreSQL에 한 번에 적재한다. 여러 번 실행해도 된다.
#
#   deploy/htodb/setup.sh <HTODB.zip>            최초 적재. 다시 실행하면 같은 데이터로 다시 맞춰 적재
#   deploy/htodb/setup.sh --fresh <HTODB.zip>    SQL Server 쪽 사본을 강제로 새로 풂 (새 zip은 해시로 알아서 감지함)
#
# 필요: docker compose, backend/.venv (cd backend && uv sync), to21/v0.6/ 의 명세서 xlsx
# Windows는 WSL2 안에서 실행한다. 데이터·zip·mdf는 저장소에 두지 않는다(D-47).
# .env가 없으면 무작위 비밀번호로 만든다(git 제외). 비밀번호는 명령줄에 넣지 않고 환경 변수로만 넘긴다.
set -euo pipefail
unset CDPATH

FRESH=0 ZIP=""
for a in "$@"; do
  case "$a" in
    --fresh) FRESH=1 ;;
    -*) echo "알 수 없는 옵션: $a" >&2; exit 2 ;;
    *) [[ -z "$ZIP" ]] || { echo "zip은 하나만 주세요" >&2; exit 2; }; ZIP="$a" ;;
  esac
done
[[ -n "$ZIP" && -f "$ZIP" ]] || { echo "사용법: $0 [--fresh] <HTODB.zip 경로>" >&2; exit 2; }
ZIP="$(cd "$(dirname "$ZIP")" && pwd)/$(basename "$ZIP")"

HERE="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$(cd "$HERE/../../backend" && pwd)"
PY="$BACKEND/.venv/bin/python"
cd "$HERE"

say() { printf '\n== %s\n' "$*"; }

if [[ ! -x "$PY" ]]; then
  [[ -e "$BACKEND/.venv/Scripts/python.exe" ]] && echo "Windows용 venv임 → WSL2 안에서 venv를 만들고 실행하세요" >&2
  echo "backend/.venv 가 없음 → cd backend && uv sync" >&2
  exit 2
fi
"$PY" -c "import pymssql, psycopg, openpyxl" 2>/dev/null \
  || { echo "적재 패키지 없음 → cd backend && uv sync" >&2; exit 2; }
# 서버를 띄우기 전에 명세서부터 확인(없으면 받는 방법을 알려 주고 멈춤)
PYTHONPATH="$BACKEND/src" "$PY" -c "from msds.common.paths import to21_file; to21_file('spec')"

if [[ ! -f .env ]]; then
  say ".env 만들기 (무작위 비밀번호)"
  "$PY" - <<'EOF'
import os, secrets
data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
base = os.path.join(data, "to21-htodb")
os.makedirs(base, mode=0o700, exist_ok=True)
os.chmod(base, 0o700)   # 기업 DB 사본이 있는 곳: 다른 사용자는 못 들어오게
tok = lambda: secrets.token_urlsafe(18)
lines = {"HTODB_PG_PASSWORD": tok(), "HTODB_READER_PASSWORD": tok(), "HTODB_MSSQL_SA_PASSWORD": "Aa1!" + tok(),
         "HTODB_MDF_DIR": os.path.join(base, "mdf"), "HTODB_PG_PORT": "5433", "HTODB_MSSQL_PORT": "14330"}
fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write("".join(f"{k}='{v}'\n" for k, v in lines.items()))
EOF
fi
set -a; . ./.env; set +a
for k in HTODB_PG_PASSWORD HTODB_READER_PASSWORD HTODB_MSSQL_SA_PASSWORD HTODB_MDF_DIR; do
  [[ -n "${!k:-}" ]] || { echo ".env에 $k 값이 없음 (견본: .env.example, 또는 .env를 지우고 다시 실행)" >&2; exit 2; }
done
[[ "$HTODB_MDF_DIR" == /* ]] || { echo "HTODB_MDF_DIR는 저장소 밖 절대 경로여야 함: $HTODB_MDF_DIR" >&2; exit 2; }

export SQLCMDPASSWORD="$HTODB_MSSQL_SA_PASSWORD"
sqlcmd() { docker compose exec -T -e SQLCMDPASSWORD mssql /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -b -h -1 -W "$@"; }
# 실패하면 SQL Server 메시지를 보여 주고 멈춘다(성공 때 나오는 긴 업그레이드 메시지는 숨김)
sqlrun() { local out; out="$(sqlcmd -Q "$1" 2>&1)" || { echo "$out" >&2; echo "SQL Server 명령 실패: $1" >&2; exit 1; }; }
psql_admin() { docker compose exec -T -e HTODB_PG_PASSWORD -e HTODB_READER_PASSWORD pg psql -v ON_ERROR_STOP=1 -U kdb -d kdb -q "$@"; }

say "PostgreSQL + SQL Server 띄우기 (첫 실행은 SQL Server 이미지 약 1.5GB 내려받기)"
mkdir -p "$HTODB_MDF_DIR"
trap 'docker compose stop mssql >/dev/null 2>&1 || true' EXIT   # 중간에 실패해도 SQL Server는 끈다
docker compose --profile export up -d
for i in $(seq 1 90); do
  docker compose exec -T pg pg_isready -U kdb -d kdb >/dev/null 2>&1 && sqlcmd -Q "SELECT 1" >/dev/null 2>&1 && break
  [[ $i == 90 ]] && { echo "서버가 3분 안에 뜨지 않음 → docker compose logs 확인" >&2; exit 1; }
  sleep 2
done

# 연결된 사본이 지금 zip에서 나온 것인지 확인. 다르거나(새 버전) 파일이 없으면 다시 풀어 연결한다.
ZIP_SHA="$("$PY" -c "import hashlib,sys; h=hashlib.sha256(); f=open(sys.argv[1],'rb'); [h.update(b) for b in iter(lambda: f.read(1<<20), b'')]; print(h.hexdigest())" "$ZIP")"
MARK="$HTODB_MDF_DIR/source.sha256"
attached="$(sqlcmd -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name='HTODB'")"
same_source=0
[[ -f "$MARK" && -f "$HTODB_MDF_DIR/HTODB.mdf" && "$(cat "$MARK")" == "$ZIP_SHA" ]] && same_source=1
if [[ "$attached" == 1 && ( "$FRESH" == 1 || "$same_source" == 0 ) ]]; then
  say "기존 HTODB 사본 내리기 ($([[ $FRESH == 1 ]] && echo '--fresh' || echo '다른 zip 또는 사본 파일 없음'))"
  # 연결했던 사본만 내린다(받은 zip은 그대로). 막 뜬 직후엔 DB가 열리는 중이라 실패할 수 있어 몇 번 다시 시도
  # 사본 파일이 없으면 DROP이 경고와 함께 실패 코드를 내기도 해서, 결과는 DB가 실제로 없어졌는지로 판단한다
  for i in $(seq 1 30); do
    sqlcmd -Q "IF DB_ID('HTODB') IS NOT NULL DROP DATABASE HTODB" >/dev/null 2>&1 || true
    [[ "$(sqlcmd -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name='HTODB'")" == 0 ]] && break
    [[ $i == 30 ]] && sqlrun "DROP DATABASE HTODB"
    sleep 2
  done
  attached=0
fi
if [[ "$attached" != 1 ]]; then
  say "HTODB.zip 풀기 → $HTODB_MDF_DIR"
  rm -f "$HTODB_MDF_DIR/HTODB.mdf" "$HTODB_MDF_DIR/HTODB_log.ldf" "$MARK"
  "$PY" -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2], members=['HTODB.mdf', 'HTODB_log.ldf'])" "$ZIP" "$HTODB_MDF_DIR"
  chmod a+rwx "$HTODB_MDF_DIR"; chmod a+rw "$HTODB_MDF_DIR/HTODB.mdf" "$HTODB_MDF_DIR/HTODB_log.ldf"   # SQL Server 컨테이너 사용자용
  say "SQL Server에 사본 연결"
  sqlrun "CREATE DATABASE HTODB ON (FILENAME='/var/opt/mssql/attach/HTODB.mdf'),(FILENAME='/var/opt/mssql/attach/HTODB_log.ldf') FOR ATTACH;"
  echo "$ZIP_SHA" > "$MARK"
fi
# SQL Server는 뜬 뒤에 사용자 DB를 따로 늦게 연다(sys.databases는 그 전에도 ONLINE으로 보임).
# 적재 스크립트처럼 HTODB를 직접 지정해 로그인이 될 때까지 기다린다.
for i in $(seq 1 90); do
  sqlcmd -d HTODB -Q "SELECT 1" >/dev/null 2>&1 && break
  [[ $i == 90 ]] && { echo "HTODB가 3분 안에 열리지 않음 → docker compose logs mssql 확인, 또는 --fresh로 다시 실행" >&2; exit 1; }
  sleep 2
done
sqlrun "ALTER DATABASE HTODB SET READ_ONLY WITH ROLLBACK IMMEDIATE;"   # DB가 열린 뒤에 매번 다시 건다(멱등)

say "계정 맞추기: 적재 계정 kdb, 조회 계정 kdb_reader (쓰기 권한 없음)"
# .env를 새로 만들었어도 기존 볼륨의 비밀번호와 어긋나지 않게 매번 .env 값으로 다시 맞춘다
printf "%s\n" \
  '\getenv admin_pw HTODB_PG_PASSWORD' \
  '\getenv reader_pw HTODB_READER_PASSWORD' \
  "ALTER ROLE kdb PASSWORD :'admin_pw';" \
  "SELECT 'CREATE ROLE kdb_reader LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kdb_reader') \\gexec" \
  "ALTER ROLE kdb_reader PASSWORD :'reader_pw';" \
  "GRANT pg_read_all_data TO kdb_reader;" \
  "ALTER ROLE kdb_reader SET default_transaction_read_only = on;" \
  | psql_admin >/dev/null

say "적재 (원본과 행 수·값 해시가 같아야 커밋)"
"$PY" "$BACKEND/scripts/load_htodb.py" --source "$ZIP"
"$PY" "$BACKEND/scripts/load_htodb_map.py"

say "완료 (SQL Server는 끔. 적재 뒤에는 PostgreSQL만 있으면 됨)"
echo "PostgreSQL: 127.0.0.1:${HTODB_PG_PORT:-5433} (컴퓨터를 다시 켜도 Docker가 켜지면 자동으로 뜸)"
echo "조회 API:  cd backend && .venv/bin/uvicorn --app-dir src msds.api.htodb_app:app --port 8010   → http://127.0.0.1:8010/docs"
