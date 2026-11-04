# PDF 글자 추출 API

PDF 한 건을 접수하고 version17 글자 추출 결과를 공유 폴더에 저장한다. 이 서비스는 모델 호출이나 JSON 구조화 추출을 실행하지 않는다.

## 구조

- `src/msds/api/extraction_app.py`: 업로드와 작업 상태 조회 FastAPI
- `src/msds/preprocess/jobs.py`: PostgreSQL 작업 상태와 별도 워커
- `src/msds/preprocess/pdf_pipeline.py`: 원본 PDF에서 version17 산출물 생성
- `tests/test_extraction_api.py`: API와 워커 검증
- `../data/extraction_api/uploads/`: 업로드한 원본 PDF (기본값)
- `../data/pages/api/<doc_id>/`: 페이지별 TXT, PNG와 기타 산출물 (기본값)

API와 워커에는 같은 PostgreSQL 접속 설정과 파일 저장소가 필요하다. 워커가 DB에 기록된 원본 및 결과의 **동일한 절대 경로**에 접근할 수 있어야 한다. 모델에서도 `pages` 결과 폴더를 볼 수 있도록 공유 저장소를 연결한다.

## 준비와 실행

`requirements.txt` 또는 `pyproject.toml`의 의존성과 기존 version17 추출기의 OCR/표 분석 의존성 및 로컬 모델 파일을 설치한다. OCR 기본 장치는 `gpu:0`이다. 환경에 맞게 장치를 선택한다.

HTODB의 `kdb`와는 **별도의 서비스 PostgreSQL DB**를 사용한다. [HTODB ERD](../docs/HTODB_ERD_API.html)의 `htodb`와 `htodb_map`은 화학물질 기준정보 조회용이며 추출 작업 테이블이 아니다. 글자 추출 작업은 서비스 DB의 `msds_extraction.extraction_jobs`에 저장한다. 이는 별도로 구현한 테이블이고 HTODB ERD에 정의된 테이블이 아니다.

API와 워커 양쪽에 서비스 DB의 쓰기 계정을 설정한다. 다음 둘 중 하나를 사용한다.

1. `MSDS_JOBS_DATABASE_URL`에 PostgreSQL 접속 문자열 설정.
2. `MSDS_JOBS_PG_DATABASE`, `MSDS_JOBS_PG_USER`, `MSDS_JOBS_PG_PASSWORD` 설정. `MSDS_JOBS_PG_HOST`, `MSDS_JOBS_PG_PORT`를 생략하면 `127.0.0.1`, `5432`를 사용한다.

이 설정은 HTODB 주소나 계정을 자동으로 가져오지 않는다. API와 워커는 최초 시작 시 `msds_extraction` 스키마와 `extraction_jobs` 테이블·인덱스를 생성하므로 사용하는 계정에 필요한 생성·쓰기 권한이 있어야 한다. 운영 환경에서 스키마를 미리 만들 경우 계정에 해당 스키마 사용 및 테이블 생성 권한을 부여한다. 비밀번호를 저장소에 기록하지 않는다.

다음 명령은 `backend` 디렉터리 기준이며 두 프로세스를 각각 실행한다.

```bash
# 터미널 1: API
.venv/bin/uvicorn --app-dir src msds.api.extraction_app:app --host 0.0.0.0 --port 8000
```

```bash
# 터미널 2: 워커 (예: CPU 사용)
PYTHONPATH=src .venv/bin/python -m msds.preprocess.jobs --ocr-device cpu
```

Docling 표 보조 분석을 사용하지 않을 경우 워커에 `--no-docling`을 추가한다. API만 실행하면 작업은 접수되지만 워커가 없으므로 `queued` 상태로 대기한다.

기본 경로를 바꾸려면 API에 `MSDS_EXTRACTION_ROOT`(업로드 등 작업 파일), `MSDS_PAGES_ROOT`(모델과 공유할 결과 폴더)를 설정한다. 워커는 PostgreSQL에 저장된 절대 경로를 그대로 사용한다. 업로드 파일의 한도는 기본 50 MiB이다.

## 호출

```bash
curl -X POST http://localhost:8000/api/v1/documents -F 'file=@/path/to/msds.pdf'
```

응답은 HTTP 202와 `job_id`, `doc_id`, `queued` 상태다. 완료를 기다리지 않는다.

```bash
curl http://localhost:8000/api/v1/jobs/<job_id>
```

상태는 `queued`, `running`, `succeeded`, `failed`, `recovery_required` 중 하나이며, `stage`, `completed_pages`, `total_pages`, `error`를 함께 조회한다. 총 페이지를 알기 전에는 `total_pages`가 `null`이다. 페이지 수가 모두 처리돼도 결과 게시가 끝나야 `succeeded`와 `result_ready=true`가 된다.

성공 시 `result_dir`은 API·워커 쪽의 결과 폴더 경로다. 모델이 다른 마운트 경로를 사용한다면 모델 쪽에서 해당 공유 폴더의 경로와 `doc_id`를 맞춰야 한다. 서버의 내부 경로를 원격 서버에서 그대로 사용할 수 있다는 의미가 아니다. 모델은 저장된 `pNNN.txt` 등을 직접 읽는다.

워커가 중단되어 heartbeat가 만료된 작업은 다른 워커가 확인할 때 `recovery_required`로 표시한다. 이 상태는 자동으로 재실행하지 않는다. 기존 결과와 작업 상태를 확인한 뒤 운영자가 복구해야 한다. 접수 도중 DB 커밋 결과가 불명확하면 원본 삭제를 피하므로 작업이 없는 업로드 파일이 남을 수 있다.

상호 작용 문서는 `http://localhost:8000/docs`에서 확인한다.

## PostgreSQL 통합 테스트

테스트용 별도 DB를 준비하고 `MSDS_TEST_DATABASE_URL`을 설정한 뒤 `cd backend && .venv/bin/python -m pytest -q tests/test_extraction_postgres.py`를 실행한다. 테스트는 임의 이름의 임시 스키마를 만들고 종료 시 지우므로 테스트 계정에 스키마 생성 권한이 필요하다. 운영 DB가 아닌 테스트 DB에서 실행한다.
