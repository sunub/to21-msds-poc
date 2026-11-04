"""PDF 추출 서비스 API: 올리기 → 전처리 → 항목 나누기 → 항별 모델 추출 → 정리·검증, 진행 조회.

실행: cd backend && .venv/bin/uvicorn --app-dir src msds.api.extract_app:app --port 8020  (문서: /docs)
모델은 MSDS_SERVICE_MODEL(configs/models.yaml 태그, 기본 qwen36_35b_runpod)이고 접속 정보는 .env에서 읽는다.
frontend/out(정적 빌드)이 있으면 같은 주소의 / 에서 화면을 낸다. 개발 서버(next dev)는 CORS로 붙는다.

진행의 기본 단위는 항목(MSDS 건 × 추출 대상 9개 항: 1·2·3·8·9·11·12·14·15)이다 (service.progress). 화면은 GET /api/documents/{id}를 1~2초마다 부른다.

POST /api/documents?filename=&as_of=      본문이 PDF 바이트 그대로(application/pdf). 202와 진행 상태
GET  /api/documents?status=all|active|done|failed   목록(항별 목록 없이 개수만)과 상태별 개수
GET  /api/documents/{id}                   진행 상태 전체(단계, 전처리 쪽 수, 항별 상태, 경고)
GET  /api/documents/{id}/pdf               올린 원본 PDF (화면에서 직접 그린다)
GET  /api/documents/{id}/pages/{n}/image   쪽 이미지 (전처리 뒤)
GET  /api/documents/{id}/pages/{n}/lines   줄 번호 붙은 쪽 글 (근거 줄 p2:L23과 같은 번호)
GET  /api/documents/{id}/result            끝난 뒤 TO21 JSON과 사람이 볼 항. 끝나기 전에는 409
POST /api/documents/{id}/retry             실패·멈춘 문서를 처음부터 다시
POST /api/documents/{id}/to-judgment       추출값 확인을 마치고 판정으로 넘김 (본문 {reviewer}, 응답 {job_id, handoff_seq})

이 파일은 앱 조립(저장소·작업자 수명, 오류 응답, CORS, 라우터 붙이기, 화면 정적 파일)만 한다.
경로별 코드는 msds/api/routers/extract/ 아래 의미별 파일에 있다 (목록은 routers/extract/__init__.py).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from msds.api import judge_app
from msds.api.routers.extract import ROUTERS
from msds.common import paths
from msds.service import pipeline
from msds.service.handoff import HandoffNotReady
from msds.service.jobs import ReviewNotReady
from msds.service.results import ResultConflict, ResultNotReady, ResultStore
from msds.service.store import DocumentStore
from msds.service.worker import Worker

CORS_ENV = "MSDS_CORS_ORIGINS"
DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3101,http://127.0.0.1:3101"
FRONTEND_OUT = paths.ROOT / "frontend" / "out"
JUDGE_EMBED_ENV = "MSDS_JUDGE_IN_EXTRACT_APP"


def create_app(
    store: DocumentStore | None = None,
    worker=None,
    pages_dir: Path | None = None,
    static_dir: Path | None = FRONTEND_OUT,
) -> FastAPI:
    """store·worker를 주지 않으면 켤 때 data/service와 실제 파이프라인 작업자를 만든다."""
    judge_embedded = os.environ.get(JUDGE_EMBED_ENV) == "1"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db_url = os.environ.get("MSDS_SERVICE_DATABASE_URL")
        if store is not None:
            st = store
        elif db_url:
            from msds.service.jobs import PostgresJobStore

            st = PostgresJobStore(
                db_url, pipeline.service_root(), taken_dirs=(paths.PAGES,)
            )
        else:
            st = DocumentStore(pipeline.service_root(), taken_dirs=[paths.PAGES])
        app.state.store = st
        if worker is not None:
            wk = worker
        elif db_url and store is None:
            from msds.service.worker import PostgresWorker

            wk = PostgresWorker(
                st,
                result_store=ResultStore(st.dsn, schema=st.schema),
                preprocess_workers=int(os.environ.get("MSDS_PREPROCESS_WORKERS", "1")),
                extract_workers=int(os.environ.get("MSDS_EXTRACT_WORKERS", "1")),
            )
        else:
            wk = Worker(st, pipeline.process)
        app.state.worker = wk
        wk.start()
        try:
            if judge_embedded:
                judge_app.attach(app)
            if not (db_url and store is None and worker is None):
                for doc_id in st.recover():
                    wk.submit(doc_id)
            yield
        finally:
            if judge_embedded and hasattr(app.state, "judge_workers"):
                judge_app.detach(app)
            wk.stop(timeout=1)

    app = FastAPI(title="TO21 MSDS 추출 API", lifespan=lifespan)
    app.state.pages_root = (
        Path(pages_dir) if pages_dir else None
    )  # 파일 저장소일 때 쪽 이미지·글 폴더 (routers.extract.deps)

    @app.exception_handler(ReviewNotReady)
    async def review_not_ready(request: Request, exc: ReviewNotReady):
        return JSONResponse(
            status_code=409,
            content={"detail": "작업이 다시 실행되어 이전 결과를 검수할 수 없습니다"},
        )

    @app.exception_handler(ResultNotReady)
    @app.exception_handler(ResultConflict)
    @app.exception_handler(HandoffNotReady)
    async def result_conflict(request: Request, exc: Exception):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=judge_app.CORS_EXPOSE,
        allow_origins=[
            o.strip()
            for o in os.environ.get(CORS_ENV, DEFAULT_CORS).split(",")
            if o.strip()
        ],
    )

    for router in ROUTERS:
        app.include_router(router)
    if judge_embedded:
        app.include_router(judge_app.router)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


app = create_app()
