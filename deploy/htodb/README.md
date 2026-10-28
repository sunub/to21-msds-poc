# TO21 지식DB(HTODB) 로컬 적재와 조회 API

TO21이 준 HTODB(SQL Server mdf, 16개 테이블)를 로컬 PostgreSQL에 **값을 바꾸지 않고** 옮기고, 명세서 v0.6의 13_TO21DB매핑 시트(추출 코드 ↔ HTODB 코드)를 셀 값 그대로 함께 넣는다. 조회 API는 원본 값을 그대로 돌려줄 뿐 해석·판정은 하지 않는다.

- 데이터·zip·mdf는 저장소에 올리지 않는다(D-47). 각자 받은 파일로 적재한다.
- 바꾸는 것은 테이블·컬럼 이름 소문자화뿐. PK·NOT NULL·길이·소수 자릿수는 원본과 같다.
- 적재는 한 트랜잭션이고, 테이블마다 원본 SQL Server와 행 수·값 해시가 같아야 커밋한다. 번역표는 다시 읽은 값이 시트와 셀 단위로 같아야 커밋한다.
- API는 쓰기 권한 없는 계정 `kdb_reader`(`pg_read_all_data`만) + 읽기 전용 세션으로 붙는다.

## 적재 (최초 1회, 새 버전을 받으면 다시)

```bash
cd deploy/htodb
cp .env.example .env            # 값 채우기. HTODB_MDF_DIR = HTODB.zip을 풀 폴더(저장소 밖 절대 경로)
set -a; . ./.env; set +a
mkdir -p "$HTODB_MDF_DIR" && python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" <HTODB.zip> "$HTODB_MDF_DIR"
chmod -R a+rwX "$HTODB_MDF_DIR"    # SQL Server 컨테이너 사용자가 열 수 있게
docker compose --profile export up -d
# SQL Server가 다 뜬 뒤(수십 초) mdf 사본 연결 + 읽기 전용
docker compose exec -T mssql /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$HTODB_MSSQL_SA_PASSWORD" -b -Q "
CREATE DATABASE HTODB ON (FILENAME='/var/opt/mssql/attach/HTODB.mdf'),(FILENAME='/var/opt/mssql/attach/HTODB_log.ldf') FOR ATTACH;
ALTER DATABASE HTODB SET READ_ONLY WITH ROLLBACK IMMEDIATE;"
# 조회 계정
printf "CREATE ROLE kdb_reader LOGIN PASSWORD :'pw';\nGRANT pg_read_all_data TO kdb_reader;\nALTER ROLE kdb_reader SET default_transaction_read_only = on;\n" \
  | docker compose exec -T pg psql -v ON_ERROR_STOP=1 -U kdb -d kdb -v pw="$HTODB_READER_PASSWORD"

cd ../../backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/load_htodb.py --source <HTODB.zip>
.venv/bin/python scripts/load_htodb_map.py         # to21/v0.6/의 명세서 xlsx를 읽음
docker compose -f ../deploy/htodb/compose.yaml stop mssql   # 적재 뒤에는 pg만 있으면 됨
```

## 조회 API

```bash
cd backend
.venv/bin/uvicorn --app-dir src msds.api.htodb_app:app --port 8010   # 서버 실행(계속 떠 있음). 문서: http://127.0.0.1:8010/docs
```

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_D_htodb_mapping.py tests/test_D_htodb_api.py   # DB가 없으면 API 시험은 건너뜀
```

| 경로 | 돌려주는 것 |
|---|---|
| `GET /health` | knowledge_version(원본 zip 해시), map_version(명세서 xlsx 해시) |
| `GET /chemicals?cas=` / `?ke=` / `?un=` | 물질 원본 행. 키 비교는 13_TO21DB매핑 A묶음 규칙(CAS는 R02 표기 맞춤). DB 값은 그대로 |
| `GET /chemicals/{chem_id}` 와 `/classifications` `/toxicity` `/physical-properties` `/regulations` `/exposure-limits` | 그 물질의 원본 행 + 행이 쓰는 코드의 기준정보 사전(`codes`). 분류는 두 출처 모두 |
| `GET /codes/ghs-class/{code}` `/codes/h/{code}` `/codes/div/{code}` `/codes/property/{code}` `/codes/regulate-item/{code}` | 코드 기준정보 |
| `GET /mapping/hazard?class_code=&category=&route_form=&effect=`, `/mapping/{pictogram,signal-word,property,endpoint,regulation}/{code}` | 추출 코드 → HTODB 코드(근거 시트 행 번호·셀 원문 포함) |
| `POST /lookup` (추출 JSON) | JSON 안 코드마다 번역 결과 + HTODB 원본. 성분 CAS로 한 물질이 찾아지면 그 물질 세부정보도 붙임. 형식이 틀리면 422와 틀린 경로 |

- numeric은 소수 자릿수를 지키려고 문자열로 돌려준다.
- 시트에 대응이 없으면 `mapping`은 빈 목록(추측하지 않음). 시트가 route_form·effect로 나누는 분류는 JSON에 그 값이 없으면 고르지 않는다. 11·12항 endpoint는 시트에 적힌 후보 DIV_CODE를 모두 돌려준다.
- 시트 셀에서 나눠 읽는 곳은 ' · '로 묶은 추출 코드와 '/'로 줄여 쓴 DIV_CODE뿐. 괄호로 시작하는 자리표시 행은 번역 대상에서 뺀다.
