# HTODB 로컬 PostgreSQL 설정 가이드

이 문서는 Windows의 WSL2에서 이 저장소의 HTODB 데이터와 추출·판정 테이블을 Docker PostgreSQL에 준비하고 DBeaver로 확인하는 방법을 설명합니다. 명령은 별도 안내가 없으면 **저장소 루트** `~/to21-msds-poc`에서 실행합니다.

완료되면 `kdb` 데이터베이스에 `htodb`의 지식DB 원본 16개 테이블, `htodb_map`의 매핑 테이블, `extract`의 추출 테이블 5개, `judge`의 판정 테이블 6개가 준비됩니다. 두 적재 스키마에는 각각 적재 이력을 기록하는 `load_log`도 생성됩니다. `to21_erd_control.migration_history`에는 서비스 테이블 생성 이력이 기록됩니다. 지식DB를 같은 내용으로 채우려면 팀원이 **같은 버전의 HTODB ZIP과 명세서**를 받아야 합니다. 추출·판정 테이블은 구조만 만들어지므로 다른 사람의 PDF, 작업과 결과 데이터는 복사되지 않습니다.

전달받은 ZIP의 ERD와 설정 자료는 참고용이며, 실행에는 백엔드 코드를 포함한 전체 프로젝트가 필요합니다. 기존 ERD 구축 문서에 나온 `.env.erd`와 `55433`은 해당 문서의 별도 구축 예시입니다. 이 가이드의 HTODB 연결은 `deploy/htodb/.env`와 각자 설정한 포트를 사용합니다.

## 준비물

- 프로젝트 저장소와 WSL2에서 사용할 수 있는 Docker Desktop, Docker Compose. Docker Desktop을 켜고 해당 WSL 배포판의 Docker 통합을 활성화합니다.
- Python 3.11 또는 3.12와 `uv`.
- TO21에서 별도로 받은 `HTODB.zip`과 명세서 `TO21_MSDS_추출명세서_v0.6.xlsx`. ZIP과 명세서는 이 저장소에서 제공하지 않습니다. 명세서는 `to21/v0.6/`에 원래 이름으로 둡니다. 자세한 내용은 `to21/README.md`를 확인하세요.
- DBeaver (DB를 화면에서 확인할 때 사용).

원본 ZIP, MDF 사본, `.env`, 비밀번호는 Git이나 공유 ZIP에 올리지 않습니다. 기존 데이터를 보존하려면 `docker compose down -v`로 볼륨을 삭제하지 마세요.

### 프로젝트 버전 준비

이 문서와 A1·A2·B2 SQL이 모두 포함된 버전을 사용합니다. 아직 `main`에 반영되기 전이라면 팀에서 공유한 `db/htodb-setup` 브랜치를 받아 사용합니다. 새로 받는 예시입니다. 저장소 접근 권한이 필요합니다.

```bash
cd ~
git clone --branch db/htodb-setup https://github.com/sunub/to21-msds-poc.git
cd to21-msds-poc
```

이미 프로젝트가 있다면 로컬 작업을 먼저 확인하고 팀 안내에 따라 해당 브랜치로 전환하세요. 브랜치 전환으로 작업 중인 파일을 덮어쓰지 마세요. SQL이 머지된 이후에는 팀이 안내한 최신 버전을 사용합니다. SQL 파일을 찾을 수 없다는 오류가 나면 아래 파일이 있는지 확인합니다.

```bash
ls backend/migrations/a1_0001_extract_jobs.sql \
  backend/migrations/a2_0002_extract_results_reviews_artifacts.sql \
  backend/migrations/a2_0003_extract_handoff.sql \
  backend/migrations/b2_0004_judge_runs_versions.sql \
  backend/migrations/b2_0005_judge_explanations_reviews.sql \
  backend/migrations/b2_0006_judge_snapshots_artifacts.sql \
  backend/migrations/0007_service_grants.sql \
  backend/scripts/apply_erd_migrations.py
```

## 1. Windows에서 원본 ZIP 복사

Windows 다운로드 폴더에 ZIP이 있다면 WSL에서는 `/mnt/c/Users/<Windows 사용자명>/Downloads/HTODB.zip` 경로입니다. 다음에서 `Admin`을 실제 Windows 사용자명으로 바꾸세요.

파일 위치나 Windows 사용자명을 모를 때는 다음과 같이 확인할 수 있습니다.

```bash
find ~ -type f -iname '*htodb*.zip' 2>/dev/null
ls /mnt/c/Users
```

```bash
cd ~/to21-msds-poc
mkdir -p ~/.local/share/to21-htodb/source
cp "/mnt/c/Users/Admin/Downloads/HTODB.zip" ~/.local/share/to21-htodb/source/
ls -lh ~/.local/share/to21-htodb/source/HTODB.zip
```

`cp`는 원본을 남기고 복사합니다. 파일이 다른 위치에 있다면 원본 경로를 바꾸세요. `HTODB_MDF_DIR`은 원본 ZIP이 아니라 적재 중 압축을 풀 **별도 폴더**입니다.

TO21 명세서도 팀에서 별도로 받아 `to21/v0.6/TO21_MSDS_추출명세서_v0.6.xlsx`에 둡니다. 예를 들어 Windows 다운로드 폴더에 있다면 사용자명과 파일 위치를 바꾸어 복사합니다.

```bash
mkdir -p to21/v0.6
cp '/mnt/c/Users/Admin/Downloads/TO21_MSDS_추출명세서_v0.6.xlsx' to21/v0.6/
ls -lh to21/v0.6/TO21_MSDS_추출명세서_v0.6.xlsx
```

이 명세서는 HTODB 매핑 적재에 필요합니다. 실제 PDF 추출과 검증에는 스키마·동의어사전·검증기 등 다른 TO21 자료도 별도로 필요합니다. 필요한 파일은 [TO21 자료 안내](../../to21/README.md)를 확인하세요.

## 2. 백엔드 의존성 설치

```bash
cd ~/to21-msds-poc/backend
uv sync
cd ..
```

WSL 내부에서 실행해 Linux용 `backend/.venv`를 준비합니다. 적재에는 개발 의존성인 `pymssql`도 필요하므로 기본 개발 그룹을 제외하지 마세요.

## 3. 환경 설정

루트의 `.env`가 아닌 `deploy/htodb/.env`를 사용합니다. 파일이 아직 없으면 예시를 복사합니다. `-n`은 이미 있는 설정을 덮어쓰지 않습니다.

```bash
cp -n deploy/htodb/.env.example deploy/htodb/.env
nano deploy/htodb/.env
```

아래 항목을 각자의 값으로 채웁니다. 예시의 `<...>`를 실제 값으로 바꾸고 꺾쇠는 넣지 마세요.

```env
HTODB_PG_PASSWORD='<직접 정한 PostgreSQL 비밀번호>'
HTODB_READER_PASSWORD='<직접 정한 읽기 전용 계정 비밀번호>'
HTODB_MSSQL_SA_PASSWORD='<직접 정한 SQL Server 비밀번호>'
HTODB_MDF_DIR='/home/<WSL 사용자명>/.local/share/to21-htodb/mdf'
HTODB_PG_PORT=5433
HTODB_MSSQL_PORT=14330
```

- WSL 사용자명은 `whoami`로 확인할 수 있습니다. 예를 들어 사용자명이 `aiuser`라면 MDF 경로는 `/home/aiuser/.local/share/to21-htodb/mdf`입니다. ZIP 파일명이 아닌 저장소 밖의 **절대 폴더 경로**를 적습니다. 스크립트가 폴더를 만들고 ZIP을 풉니다.
- `setup.sh`는 이 파일을 셸에서 읽으므로 비밀번호는 작은따옴표로 감싸고 비밀번호 안에는 작은따옴표를 쓰지 마세요. SQL Server 비밀번호는 대문자·소문자·숫자·기호를 포함한 8자 이상으로 정합니다. 공유된 비밀번호가 아니라 각자 새로 설정하는 값입니다.
- PostgreSQL만 띄워도 Compose가 SQL Server 설정을 읽으므로 `HTODB_PG_PASSWORD`와 `HTODB_MSSQL_SA_PASSWORD`가 모두 필요합니다. 적재 스크립트는 이 둘에 더해 `HTODB_READER_PASSWORD`와 `HTODB_MDF_DIR`도 요구합니다.
- `HTODB_PG_PORT` 기본값은 `5433`입니다. 이미 사용 중이면 `5434` 등 비어 있는 포트로 변경하세요. `HTODB_MSSQL_PORT`도 충돌하면 다른 빈 포트로 변경합니다.
- `nano`에서 **Ctrl+O → Enter**로 저장하고 **Ctrl+X**로 나갑니다. 각 줄에는 변수명을 한 번만 적으세요.

`.env`가 아예 없으면 `setup.sh`가 필요한 값을 자동 생성하지만, 위처럼 파일을 직접 만든 경우 빈 값을 자동으로 채우지 않습니다. 기존 `.env`를 삭제하거나 비밀번호를 임의로 덮어쓰지 마세요.

## 4. 포트 확인 및 PostgreSQL 실행

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml up -d pg
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml ps
```

`port is already allocated`가 나오면 다른 프로그램이 해당 포트를 사용 중입니다. 기존 컨테이너를 중지하기 전에 확인하고, 보통은 `.env`의 `HTODB_PG_PORT`를 빈 포트로 바꾼 뒤 다시 실행하면 됩니다. 호스트 포트가 `5434`여도 컨테이너 내부 포트는 `5432`입니다.

Docker 컨테이너가 아닌 프로그램이 포트를 사용 중인지 확인하려면 예를 들어 `sudo ss -ltnp | grep ':5433'`을 사용합니다.

## 5. HTODB 원본 데이터 적재

```bash
deploy/htodb/setup.sh ~/.local/share/to21-htodb/source/HTODB.zip
```

ZIP을 다른 위치에 뒀다면 그 실제 경로를 지정합니다. 스크립트는 임시 SQL Server를 띄워 원본을 읽고 `kdb` DB에 옮깁니다. 이후 각 테이블의 행 수와 해시를 검증하고, 명세서의 매핑 시트를 적재한 뒤 SQL Server를 중지합니다. 최초 실행에는 이미지 다운로드가 필요합니다.

완료 메시지에서 16개 원본 테이블과 매핑 적재 결과를 확인하세요. 원본 ZIP 버전에 따라 행 수와 해시는 다를 수 있습니다. **적재와 재적재는 `htodb`와 `htodb_map` 스키마를 `DROP SCHEMA ... CASCADE`로 삭제한 뒤 재생성**하므로 그 안에 직접 만든 객체나 의존 객체가 있다면 실행 전 보존 여부를 확인하세요. `extract`와 `judge`가 같은 DB에 존재할 수 있으며, 적재 스크립트는 이 두 스키마를 직접 재생성하지 않습니다.

현재 팀에서 확인한 원본 버전은 `htodb-94f8b6ff7f24`, 매핑 버전은 `map13-e934f60e5e39`입니다. 같은 데이터가 필요한 경우 완료 메시지의 두 값을 비교하세요. 값이 다르면 전달받은 원본 ZIP과 명세서의 버전을 팀에 확인합니다.

## 6. 추출·판정 테이블과 적용 이력 만들기

앞 단계는 `htodb`와 `htodb_map`을 채웁니다. 다음 마이그레이션 실행기는 `extract`·`judge` 테이블과 `to21_erd_control.migration_history`를 만들고, SQL 적용 이력 및 서비스 역할 권한을 기록합니다. **신규 DB를 대상으로 실행**하세요. 이미 수동으로 만든 테이블이 있고 적용 이력이 없거나 기존 구조가 다르면 실행기가 멈춥니다. 기존 테이블을 삭제하거나 이력을 임의로 만들지 말고 팀에 확인하세요.

먼저 현재 테이블을 확인합니다. 목록이 비어 있는 신규 DB라면 다음 단계로 진행합니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -v ON_ERROR_STOP=1 -U kdb -d kdb \
  -c "SELECT schemaname, tablename FROM pg_catalog.pg_tables WHERE schemaname IN ('extract', 'judge', 'to21_erd_control') ORDER BY schemaname, tablename;"
```

추출·판정 서비스용 DB 역할을 준비합니다. 아래 역할은 로그인할 수 없는 권한 그룹입니다. 이미 같은 이름의 역할이 있으면 변경하지 않으며, 실행기가 권한이 적절한지 검사합니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -v ON_ERROR_STOP=1 -U kdb -d kdb <<'SQL'
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'to21_extract') THEN
    CREATE ROLE to21_extract NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'to21_judge') THEN
    CREATE ROLE to21_judge NOLOGIN NOINHERIT;
  END IF;
END
$roles$;
SQL
```

이제 실행기를 실행합니다. 비밀번호는 `.env`에서 읽으며 명령줄에 직접 입력하지 않습니다. 괄호 안 환경변수는 명령이 끝나면 현재 셸에 남지 않습니다.

```bash
(
  set -a
  . ./deploy/htodb/.env
  set +a
  export PGPASSWORD="$HTODB_PG_PASSWORD"
  export TO21_ERD_DATABASE_URL="host=127.0.0.1 port=${HTODB_PG_PORT:-5433} dbname=kdb user=kdb"
  backend/.venv/bin/python backend/scripts/apply_erd_migrations.py \
    --extract-role to21_extract --judge-role to21_judge
)
```

실행기는 A1 → A2 → B2 테이블 SQL 여섯 개와 권한 SQL `0007`을 순서대로 적용합니다. 각 단계는 별도 트랜잭션으로 기록되므로 중간에 실패하면 메시지를 확인하고 같은 명령으로 다시 실행합니다. 기록된 파일의 내용이나 DB 구조가 달라진 경우는 자동으로 바꾸지 않고 중단합니다. 역할은 서비스 계정이 사용할 권한 그룹이며, 이 단계만으로 로그인 계정이 추가되거나 API 설정이 바뀌지는 않습니다.

완료 후에는 다음을 확인합니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -U kdb -d kdb -c '\dt extract.*'
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -U kdb -d kdb -c '\dt judge.*'
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -U kdb -d kdb -c 'SELECT name FROM to21_erd_control.migration_history ORDER BY name;'
```

`extract` 테이블 5개, `judge` 테이블 6개와 적용 이력 7건을 확인합니다. 추출·판정 테이블은 빈 구조입니다. 다른 팀원의 PDF와 추출 결과는 복사되지 않으며, `judge` 테이블이 있다고 판정 API가 완성된 것은 아닙니다.

이 브랜치는 DB 구축 파일만 포함합니다. 추출 API 및 판정 기능은 별도 작업이며, 해당 코드가 머지된 후 팀의 실행 안내를 따릅니다.

## 7. DBeaver에서 연결

DBeaver에서 **새 연결 → PostgreSQL**을 선택하고 다음을 입력합니다.

| 항목 | 값 |
| --- | --- |
| Host | `localhost` 또는 `127.0.0.1` |
| Port | `.env`의 `HTODB_PG_PORT` 값 (기본 `5433`, 충돌 시 설정한 값) |
| Database | `kdb` |
| Username | `kdb` |
| Password | `.env`의 `HTODB_PG_PASSWORD` 값 |

**Test Connection**을 누르고 처음에 드라이버 다운로드를 요청하면 설치한 뒤 **Finish**를 누릅니다. 왼쪽에서 `kdb → Schemas`를 우클릭해 **Refresh**하고 `htodb`, `htodb_map`, `extract`, `judge`, `to21_erd_control`의 **Tables**를 각각 펼칩니다.

터미널에서 확인할 수도 있습니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec pg psql -U kdb -d kdb
```

`kdb=#` 프롬프트에서 아래를 입력합니다. `\q`는 psql 종료 명령입니다.

```sql
SELECT version();
\dt htodb.*
\dt htodb_map.*
\dt extract.*
\dt judge.*
\dt to21_erd_control.*
\q
```

조회 API를 사용하려면 적재 후 다음을 실행하고 `http://127.0.0.1:8010/docs`를 엽니다. API는 `kdb_reader`와 `HTODB_READER_PASSWORD`를 사용합니다.

```bash
cd ~/to21-msds-poc/backend
.venv/bin/uvicorn --app-dir src msds.api.htodb_app:app --port 8010
```

## 자주 발생하는 오류

- **`required variable ... is missing a value`**: `deploy/htodb/.env`에 해당 변수를 채우고 저장하세요. 실행할 때 `--env-file deploy/htodb/.env`로 파일을 명시할 수 있습니다.
- **`HTODB_MDF_DIR는 저장소 밖 절대 경로여야 함: HTODB_MDF_DIR=/...`**: 값에 `HTODB_MDF_DIR=`를 중복해서 적었는지 확인합니다. `HTODB_MDF_DIR='/home/사용자명/.../mdf'` 형태로 한 번만 씁니다.
- **DBeaver `password authentication failed`**: 포트와 DB가 맞는지, `HTODB_PG_PASSWORD`를 입력했는지 확인합니다. 기존 데이터 볼륨이 있으면 `.env` 수정만으로 이미 초기화된 PostgreSQL 비밀번호는 바뀌지 않습니다. 비밀번호 초기화를 위해 볼륨을 지우지 마세요. 적재 스크립트는 실행 시 DB 계정 비밀번호를 `.env` 값으로 맞춥니다.
- **`htodb` 스키마가 안 보임**: DBeaver에서 Schemas를 새로고침합니다. PostgreSQL 실행만으로 원본 데이터가 적재되지는 않으므로 적재 완료 메시지를 확인하세요.
- **포트 확인**: `docker port to21-htodb-pg-1` 또는 `docker ps --format 'table {{.Names}}\t{{.Ports}}'`를 사용합니다. DBeaver와 API에는 호스트 포트를 입력합니다.

추가 설명은 `deploy/htodb/README.md`를 참고하세요.

기존 DB의 `kdb` 비밀번호만 현재 `.env` 값으로 맞추려면 적재를 다시 실행하는 대신 아래처럼 접속합니다. 이 작업은 해당 계정의 비밀번호를 변경하므로 다른 연결에도 영향을 줍니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec pg psql -U kdb -d kdb
```

`kdb=#`에서 `\password kdb`를 입력하고 `.env`의 `HTODB_PG_PASSWORD` 값을 두 번 입력한 뒤 `\q`로 종료합니다. 입력한 비밀번호는 화면에 표시되지 않습니다.
