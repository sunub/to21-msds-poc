# HTODB 로컬 PostgreSQL 설정 가이드

이 문서는 Windows의 WSL2에서 이 저장소의 HTODB를 Docker PostgreSQL에 적재하고 DBeaver로 조회하는 방법을 설명합니다. 명령은 별도 안내가 없으면 **저장소 루트** `~/to21-msds-poc`에서 실행합니다.

전달받은 ZIP의 ERD와 설정 자료는 참고용이며, 실행에는 백엔드 코드를 포함한 전체 프로젝트가 필요합니다. 기존 ERD 구축 문서에 나온 `.env.erd`와 `55433`은 해당 문서의 별도 구축 예시입니다. 이 가이드의 HTODB 연결은 `deploy/htodb/.env`와 각자 설정한 포트를 사용합니다.

## 준비물

- 프로젝트 저장소와 WSL2에서 사용할 수 있는 Docker Desktop, Docker Compose. Docker Desktop을 켜고 해당 WSL 배포판의 Docker 통합을 활성화합니다.
- Python 3.11 또는 3.12와 `uv`.
- TO21에서 별도로 받은 `HTODB.zip`과 명세서 `TO21_MSDS_추출명세서_v0.6.xlsx`. ZIP과 명세서는 이 저장소에서 제공하지 않습니다. 명세서는 `to21/v0.6/`에 원래 이름으로 둡니다. 자세한 내용은 `to21/README.md`를 확인하세요.
- DBeaver (DB를 화면에서 확인할 때 사용).

원본 ZIP, MDF 사본, `.env`, 비밀번호는 Git이나 공유 ZIP에 올리지 않습니다. 기존 데이터를 보존하려면 `docker compose down -v`로 볼륨을 삭제하지 마세요.

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

## 6. 추출·판정 테이블 만들기

이 단계는 **새 DB에서 최초 한 번** 실행합니다. 앞 단계의 HTODB 적재는 `htodb`와 `htodb_map`을 채우지만, 다음 `extract`와 `judge` 서비스 테이블은 만들지 않습니다. A1·A2와 B2 테이블 생성 SQL이 포함된 프로젝트 버전이 필요합니다.

먼저 기존 테이블을 확인합니다. 아래 목록에 `extract.jobs`, `extract.results`, `extract.reviews`, `extract.artifacts`, `extract.handoff` 또는 `judge` 테이블이 이미 보인다면 SQL을 다시 실행하지 말고 팀에 구조와 적용 이력을 확인하세요. 기존 DB를 삭제하지 않습니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -v ON_ERROR_STOP=1 -U kdb -d kdb \
  -c "SELECT schemaname, tablename FROM pg_catalog.pg_tables WHERE schemaname IN ('extract', 'judge') ORDER BY schemaname, tablename;"
```

목록이 비어 있는 신규 DB에서는 먼저 스키마를 준비합니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -v ON_ERROR_STOP=1 -U kdb -d kdb \
  -c 'CREATE SCHEMA IF NOT EXISTS extract; CREATE SCHEMA IF NOT EXISTS judge;'
```

다음 SQL을 **표시된 순서대로 한 번만** 적용합니다. 오류가 나면 이후 파일 실행을 중단합니다. 이미 성공한 SQL은 유지되므로 원인을 확인한 뒤 남은 파일만 적용하세요.

```bash
for migration in \
  backend/migrations/a1_0001_extract_jobs.sql \
  backend/migrations/a2_0002_extract_results_reviews_artifacts.sql \
  backend/migrations/a2_0003_extract_handoff.sql \
  backend/migrations/b2_0004_judge_runs_versions.sql \
  backend/migrations/b2_0005_judge_explanations_reviews.sql \
  backend/migrations/b2_0006_judge_snapshots_artifacts.sql; do
  echo "적용: $migration"
  docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
    psql -v ON_ERROR_STOP=1 -U kdb -d kdb < "$migration" || break
done
```

완료 후에는 다음을 확인합니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -U kdb -d kdb -c '\dt extract.*'
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec -T pg \
  psql -U kdb -d kdb -c '\dt judge.*'
```

`extract`에서 `jobs`, `results`, `reviews`, `artifacts`, `handoff`, `judge`에서 `runs`, `versions`, `explanations`, `reviews`, `snapshots`, `artifacts`가 보이면 됩니다. 이는 빈 서비스 테이블을 만드는 절차입니다. 다른 팀원이 처리한 PDF와 추출 결과는 복사되지 않으며, `judge` 테이블이 있다고 판정 API가 완성된 것은 아닙니다.

추출 API를 DB 대기열 모드로 실행하는 방법은 [A1 실행 안내](../../docs/A1_작업_흐름_실행.md), 추출 결과 저장과 전달은 [A2 연결 안내](../../docs/A2_단일_PDF_연결.md)를 확인합니다. B2 판정 테이블만 따로 준비할 때는 [B2 안내](../../docs/B2_판정_테이블_준비.md)를 참고하세요.

## 7. DBeaver에서 연결

DBeaver에서 **새 연결 → PostgreSQL**을 선택하고 다음을 입력합니다.

| 항목 | 값 |
| --- | --- |
| Host | `localhost` 또는 `127.0.0.1` |
| Port | `.env`의 `HTODB_PG_PORT` 값 (기본 `5433`, 충돌 시 설정한 값) |
| Database | `kdb` |
| Username | `kdb` |
| Password | `.env`의 `HTODB_PG_PASSWORD` 값 |

**Test Connection**을 누르고 처음에 드라이버 다운로드를 요청하면 설치한 뒤 **Finish**를 누릅니다. 왼쪽에서 `kdb → Schemas`를 우클릭해 **Refresh**하고 `htodb → Tables`, `htodb_map → Tables`를 펼칩니다. `extract`, `judge` 등은 별도의 서비스용 스키마이며 환경에 따라 같은 DB에 이미 존재할 수 있습니다.

터미널에서 확인할 수도 있습니다.

```bash
docker compose --env-file deploy/htodb/.env -f deploy/htodb/compose.yaml exec pg psql -U kdb -d kdb
```

`kdb=#` 프롬프트에서 아래를 입력합니다. `\q`는 psql 종료 명령입니다.

```sql
SELECT version();
\dt htodb.*
\dt htodb_map.*
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
