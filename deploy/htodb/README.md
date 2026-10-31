# TO21 지식DB(HTODB) 로컬 적재와 조회 API

TO21이 준 HTODB(SQL Server mdf, 16개 테이블)를 로컬 PostgreSQL에 **값을 바꾸지 않고** 옮기고, 명세서 v0.6의 13_TO21DB매핑 시트(추출 코드 ↔ HTODB 코드)를 셀 값 그대로 함께 넣는다. 조회 API는 기본적으로 원본 값을 그대로 돌려주며, 독성·물성 조회에서 `parsed=true`를 주면 원본 행 옆에 판정 입력용 파싱 결과를 별도로 붙인다.

- 데이터·zip·mdf는 저장소에 올리지 않는다(D-47). 각자 받은 파일로 적재한다.
- 바꾸는 것은 테이블·컬럼 이름 소문자화뿐. PK·NOT NULL·길이·소수 자릿수는 원본과 같다.
- 적재는 한 트랜잭션이고, 테이블마다 원본 SQL Server와 행 수·값 해시가 같아야 커밋한다. 번역표는 다시 읽은 값이 시트와 셀 단위로 같아야 커밋한다.
- API는 쓰기 권한 없는 계정 `kdb_reader`(`pg_read_all_data`만) + 읽기 전용 세션으로 붙는다.

## 처음 한 번: 적재

준비: Docker(compose), `backend/.venv`(`cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`), `to21/v0.6/`의 명세서 xlsx, TO21에서 받은 HTODB.zip.
Windows는 WSL2 안에서 실행한다. Apple Silicon Mac은 Docker Desktop의 Rosetta 사용을 켠다(SQL Server 이미지가 amd64 전용).

```bash
deploy/htodb/setup.sh <HTODB.zip 경로>     # 1분 안팎(첫 실행은 SQL Server 이미지 약 1.5GB 내려받기). 여러 번 실행해도 됨
deploy/htodb/setup.sh --fresh <HTODB.zip>  # SQL Server 쪽 사본을 강제로 새로 풀 때(새 버전 zip은 해시로 알아서 다시 풂)
```

스크립트가 하는 일: `.env`가 없으면 무작위 비밀번호로 만듦(git 제외, mdf 사본은 `~/.local/share/to21-htodb/mdf`, 폴더 권한 700) → PostgreSQL·SQL Server 띄움 → zip을 풀어 SQL Server에 사본을 읽기 전용으로 연결(이미 같은 zip의 사본이 연결돼 있으면 건너뜀) → 적재 계정·조회 계정 `kdb_reader` 비밀번호를 `.env`에 맞춤 → `scripts/load_htodb.py`·`scripts/load_htodb_map.py` 적재 → SQL Server 끔(중간에 실패해도 끔).
PostgreSQL은 `restart: unless-stopped`라 컴퓨터를 다시 켜도 Docker가 켜지면 자동으로 뜬다(다시 적재할 필요 없음). 수동으로 켜려면 `docker compose -f deploy/htodb/compose.yaml up -d pg`.
처음 상태로 지우려면 `docker compose -f deploy/htodb/compose.yaml --profile export down -v` 후 `deploy/htodb/.env`와 mdf 폴더를 지운다.

## 조회 API

```bash
cd backend
.venv/bin/uvicorn --app-dir src msds.api.htodb_app:app --port 8010   # 서버 실행(계속 떠 있음). 문서: http://127.0.0.1:8010/docs
```

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_D_htodb_mapping.py tests/test_D_htodb_api.py
```

- DB에 못 붙으면 API 시험은 건너뛰지 않고, 이 문서를 가리키는 안내와 함께 실패한다(전체 시험을 돌릴 때도 같다).
- 지식DB 없이 다른 시험만 돌릴 때는 일부러 끈다: `HTODB_SKIP=1 .venv/bin/python -m pytest -q`. 결과에 건너뛴 이유가 `HTODB_SKIP=1`로 남는다.
- DB는 붙는데 시험할 행이 없으면 적재가 덜 된 것으로 보고 실패한다. `setup.sh`로 다시 적재한다.

| 경로 | 돌려주는 것 |
|---|---|
| `GET /health` | knowledge_version(원본 zip 해시), map_version(명세서 xlsx 해시) |
| `GET /chemicals?cas=` / `?ke=` / `?un=` | 물질 원본 행. 키 비교는 13_TO21DB매핑 A묶음 규칙(CAS는 R02 표기 맞춤). DB 값은 그대로 |
| `GET /chemicals/{chem_id}` 와 `/classifications` `/toxicity` `/physical-properties` `/regulations` `/exposure-limits` | 그 물질의 원본 행 + 행이 쓰는 코드의 기준정보 사전(`codes`). 분류는 두 출처 모두. `/toxicity`와 `/physical-properties`는 `parsed=true`일 때 원본 순서와 같은 파싱 결과 목록(`parsed`)을 추가 |
| `GET /codes/ghs-class/{code}` `/codes/h/{code}` `/codes/div/{code}` `/codes/property/{code}` `/codes/regulate-item/{code}` | 코드 기준정보 |
| `GET /mapping/hazard?class_code=&category=&route_form=&effect=`, `/mapping/{pictogram,signal-word,property,endpoint,regulation}/{code}` | 추출 코드 → HTODB 코드(근거 시트 행 번호·셀 원문 포함) |
| `POST /lookup` (추출 JSON) | JSON 안 코드마다 번역 결과 + HTODB 원본. 성분 CAS로 한 물질이 찾아지면 그 물질 세부정보도 붙임. 형식이 틀리면 422와 틀린 경로 |

- numeric은 소수 자릿수를 지키려고 문자열로 돌려준다.
- 시트에 대응이 없으면 `mapping`은 빈 목록(추측하지 않음). 시트가 route_form·effect로 나누는 분류는 JSON에 그 값이 없으면 고르지 않는다. 11·12항 endpoint는 시트에 적힌 후보 DIV_CODE를 모두 돌려준다.
- 시트 셀에서 나눠 읽는 곳은 ' · '로 묶은 추출 코드와 '/'로 줄여 쓴 DIV_CODE뿐. 괄호로 시작하는 자리표시 행은 번역 대상에서 뺀다.
