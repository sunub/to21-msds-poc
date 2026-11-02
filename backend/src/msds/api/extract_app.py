"""PDF 추출 서비스 API: 올리기 → 전처리 → 항목 나누기 → 항별 모델 추출 → 정리·검증, 진행 조회.

실행: cd backend && .venv/bin/uvicorn --app-dir src msds.api.extract_app:app --port 8020  (문서: /docs)
모델은 MSDS_SERVICE_MODEL(configs/models.yaml 태그, 기본 qwen36_35b_runpod)이고 접속 정보는 .env에서 읽는다.
frontend/out(정적 빌드)이 있으면 같은 주소의 / 에서 화면을 낸다. 개발 서버(next dev)는 CORS로 붙는다.

진행의 기본 단위는 항목(MSDS 건 × 1~16항)이다 (service.progress). 화면은 GET /api/documents/{id}를 1~2초마다 부른다.

POST /api/documents?filename=&as_of=      본문이 PDF 바이트 그대로(application/pdf). 202와 진행 상태
GET  /api/documents?status=all|active|done|failed   목록(항별 목록 없이 개수만)과 상태별 개수
GET  /api/documents/{id}                   진행 상태 전체(단계, 전처리 쪽 수, 항별 상태, 경고)
GET  /api/documents/{id}/pages/{n}/image   쪽 이미지 (전처리 뒤)
GET  /api/documents/{id}/pages/{n}/lines   줄 번호 붙은 쪽 글 (근거 줄 p2:L23과 같은 번호)
GET  /api/documents/{id}/result            끝난 뒤 TO21 JSON과 사람이 볼 항. 끝나기 전에는 409
POST /api/documents/{id}/retry             실패·멈춘 문서를 처음부터 다시
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from msds.checks.validator import load_to21_module
from msds.common import paths
from msds.extract.inputs import read_page_lines
from msds.service import pipeline, progress, regenerated, review
from msds.service.store import DocumentStore, now_kst
from msds.service.worker import Worker

MAX_PDF_BYTES = 50 * 1024 * 1024
CORS_ENV = "MSDS_CORS_ORIGINS"
DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3101,http://127.0.0.1:3101"
FRONTEND_OUT = paths.ROOT / "frontend" / "out"
_DATE = r"^\d{4}-\d{2}-\d{2}$"
_ACTIVE = ("queued", "running")
_FAILED = ("failed", "interrupted")


class FieldReview(BaseModel):
    msds_index: int = Field(ge=0)
    path: str = Field(min_length=1, max_length=300)
    action: Literal["confirm", "edit", "reset"]
    value: str | None = None
    reviewer: str = Field(min_length=1, max_length=40, pattern=r"\S")

    @model_validator(mode="after")
    def edit_needs_value(self):
        if self.action == "edit" and self.value is None:
            raise ValueError("수정에는 value가 필요합니다")
        return self


class SectionReview(BaseModel):
    msds_index: int = Field(ge=0)
    section: int = Field(ge=1, le=16)
    confirmed: bool
    reviewer: str = Field(min_length=1, max_length=40, pattern=r"\S")


def load_regen():
    """TO21 제공 재생성 스크립트. 저장소에 없으니(D-47) 부를 때 읽는다."""
    return load_to21_module("regen")


def create_app(store: DocumentStore | None = None, worker=None, pages_dir: Path | None = None,
               static_dir: Path | None = FRONTEND_OUT) -> FastAPI:
    """store·worker를 주지 않으면 켤 때 data/service와 실제 파이프라인 작업자를 만든다."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        st = app.state.store = store or DocumentStore(pipeline.service_root(), taken_dirs=[paths.PAGES])
        wk = app.state.worker = worker or Worker(st, pipeline.process)
        wk.start()
        for doc_id in st.recover():
            wk.submit(doc_id)
        yield
        wk.stop(timeout=1)

    app = FastAPI(title="TO21 MSDS 추출 API", lifespan=lifespan)
    pages_root = Path(pages_dir) if pages_dir else None
    app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"],
                       allow_origins=[o.strip() for o in os.environ.get(CORS_ENV, DEFAULT_CORS).split(",") if o.strip()])

    def get_state(request: Request, doc_id: str) -> dict:
        state = request.app.state.store.get(doc_id)
        if state is None:
            raise HTTPException(404, f"없는 문서: {doc_id}")
        return state

    @app.get("/api/health")
    def health():
        return {"ok": True, "model_tag": pipeline.model_tag()}

    @app.post("/api/documents", status_code=202)
    async def upload(request: Request, filename: str = Query(min_length=1, max_length=255),
                     as_of: str | None = Query(None, pattern=_DATE)):
        name = Path(filename.replace("\\", "/")).name
        if not name.lower().endswith(".pdf"):
            raise HTTPException(400, "PDF 파일만 올릴 수 있습니다")
        if int(request.headers.get("content-length") or 0) > MAX_PDF_BYTES:
            raise HTTPException(413, f"파일이 너무 큽니다 (최대 {MAX_PDF_BYTES // 1024 // 1024}MB)")
        body = await request.body()
        if len(body) > MAX_PDF_BYTES:
            raise HTTPException(413, f"파일이 너무 큽니다 (최대 {MAX_PDF_BYTES // 1024 // 1024}MB)")
        if not body.startswith(b"%PDF-"):
            raise HTTPException(400, "PDF 파일이 아닙니다")
        state = request.app.state.store.create(body, name, as_of, pipeline.model_tag())
        request.app.state.worker.submit(state["id"])
        return progress.view(state)

    @app.get("/api/documents")
    def list_documents(request: Request, status: Literal["all", "active", "done", "failed"] = "all"):
        states = request.app.state.store.list()
        groups = {"all": states,
                  "active": [s for s in states if s["status"] in _ACTIVE],
                  "done": [s for s in states if s["status"] == "done"],
                  "failed": [s for s in states if s["status"] in _FAILED]}
        return {"items": [progress.summary_view(s) for s in groups[status]],
                "counts": {k: len(v) for k, v in groups.items()}}

    @app.get("/api/documents/{doc_id}")
    def detail(request: Request, doc_id: str):
        return progress.view(get_state(request, doc_id))

    @app.get("/api/documents/{doc_id}/pages/{page}/image")
    def page_image(request: Request, doc_id: str, page: int = PathParam(ge=1)):
        get_state(request, doc_id)
        path = (pages_root or paths.PAGES) / doc_id / f"p{page:03d}.png"
        if not path.is_file():
            raise HTTPException(404, "쪽 이미지가 아직 없습니다")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/documents/{doc_id}/pages/{page}/lines")
    def page_lines(request: Request, doc_id: str, page: int = PathParam(ge=1)):
        get_state(request, doc_id)
        try:
            lines = [l for l in read_page_lines(doc_id, pages_root or paths.PAGES) if l.page == page]
        except FileNotFoundError:
            lines = []
        if not lines:
            raise HTTPException(404, "쪽 글이 아직 없습니다")
        return {"page": page, "lines": [{"id": l.id, "no": l.no, "text": l.text} for l in lines]}

    @app.get("/api/documents/{doc_id}/result")
    def result(request: Request, doc_id: str):
        state = get_state(request, doc_id)
        if state["status"] != "done":
            raise HTTPException(409, "추출이 끝나지 않았습니다")
        out, checks = pipeline.result_paths(request.app.state.store, doc_id)
        if not out.is_file():
            raise HTTPException(404, "결과 파일이 없습니다")
        chk = json.loads(checks.read_text(encoding="utf-8")) if checks.is_file() else {}
        return {"to21": json.loads(out.read_text(encoding="utf-8")),
                "needs_review": chk.get("needs_review", []), "warnings": chk.get("warnings", []),
                "schema_errors": chk.get("schema_errors", []), "to21_validator": chk.get("to21_validator", [])}

    @app.get("/api/documents/{doc_id}/sections/{msds_index}/{section}")
    def section_result(request: Request, doc_id: str, msds_index: int = PathParam(ge=0),
                       section: int = PathParam(ge=1, le=16)):
        """끝난 항의 값(펼치기 전 중간 형식). 문서가 끝나기 전에도 준다. 모델 응답 원문과 사용량은 내보내지 않는다."""
        state = get_state(request, doc_id)
        item = next((s for s in state["sections"] if (s["msds_index"], s["section"]) == (msds_index, section)), None)
        if item is None:
            raise HTTPException(404, f"없는 항: MSDS {msds_index} {section}항")
        # 상태부터 본다: 다시 돌리는 중이면 이전 실행의 파일이 남아 있다
        if item["status"] not in ("done", "failed"):
            raise HTTPException(409, "이 항은 아직 끝나지 않았습니다")
        path = pipeline.section_raw_path(request.app.state.store, doc_id, msds_index, section)
        if not path.is_file():
            raise HTTPException(404, "항 결과 파일이 없습니다")
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {**item, "errors": raw.get("errors", []), "check_problems": raw.get("check_problems", []),
                "parsed": raw.get("parsed") if raw.get("ok") else None}

    @app.get("/api/documents/{doc_id}/regenerated")
    def regenerated_msds(request: Request, doc_id: str):
        """끝난 문서의 재생성 MSDS. 모델을 부르지 않고 결과 파일로 그때그때 만든다."""
        state = get_state(request, doc_id)
        if state["status"] != "done":
            raise HTTPException(409, "추출이 끝나지 않았습니다")
        out, checks = pipeline.result_paths(request.app.state.store, doc_id)
        if not out.is_file():
            raise HTTPException(404, "결과 파일이 없습니다")
        doc = review.apply_edits(json.loads(out.read_text(encoding="utf-8")), request.app.state.store.load_review(doc_id))
        try:
            parts = regenerated.regenerate_sections(doc, load_regen())
        except Exception as e:   # TO21 제공 스크립트가 어떤 입력에서 터질지 여기서 알 수 없다
            raise HTTPException(500, f"재생성하지 못했습니다: {type(e).__name__}: {str(e)[:300]}") from e
        chk = json.loads(checks.read_text(encoding="utf-8")) if checks.is_file() else {}
        flagged = {(r["msds_index"], r["section"]) for r in chk.get("needs_review", [])}
        status = {(s["msds_index"], s["section"]): s["status"] for s in state["sections"]}
        return {"msds": [{**m, "sections": [{"section": s["section"], "title": s["title"],
                                             "status": status.get((m["msds_index"], s["section"]), "failed"),
                                             "needs_review": (m["msds_index"], s["section"]) in flagged,
                                             "lines": s["lines"]} for s in m["sections"]]} for m in parts]}

    def review_inputs(request: Request, doc_id: str) -> tuple[dict, dict, dict]:
        """(진행 상태, 추출 결과, 검사 결과). 끝나기 전이면 409, 결과 파일이 없으면 404."""
        state = get_state(request, doc_id)
        if state["status"] != "done":
            raise HTTPException(409, "추출이 끝나지 않았습니다")
        out, checks = pipeline.result_paths(request.app.state.store, doc_id)
        if not out.is_file():
            raise HTTPException(404, "결과 파일이 없습니다")
        chk = json.loads(checks.read_text(encoding="utf-8")) if checks.is_file() else {}
        return state, json.loads(out.read_text(encoding="utf-8")), chk

    @app.get("/api/documents/{doc_id}/review")
    def review_view(request: Request, doc_id: str):
        """2.2 추출값 확인: 항별 칸, 근거, 검사 문제, 검수 기록."""
        state, doc, chk = review_inputs(request, doc_id)
        return review.build_view(doc, chk, state["sections"], request.app.state.store.load_review(doc_id))

    @app.put("/api/documents/{doc_id}/review/fields")
    def review_field(request: Request, doc_id: str, body: FieldReview):
        """칸 하나 확인·수정·되돌림. 원래 값, 근거, 검토자, 시각을 함께 남긴다. 추출 결과 파일은 고치지 않는다."""
        state, doc, chk = review_inputs(request, doc_id)
        try:
            record = request.app.state.store.update_review(doc_id, lambda r: review.set_field(
                r, doc, body.msds_index, body.path, body.action, body.value, body.reviewer.strip(), now_kst()))
        except KeyError:
            raise HTTPException(404, f"없는 칸: {body.path}") from None
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        return review.build_view(doc, chk, state["sections"], record)

    @app.put("/api/documents/{doc_id}/review/sections")
    def review_section(request: Request, doc_id: str, body: SectionReview):
        """항 하나 확인 완료·취소."""
        state, doc, chk = review_inputs(request, doc_id)
        if body.msds_index >= len(doc["msds"]):
            raise HTTPException(404, f"없는 MSDS: {body.msds_index}")
        record = request.app.state.store.update_review(doc_id, lambda r: review.set_section(
            r, body.msds_index, body.section, body.confirmed, body.reviewer.strip(), now_kst()))
        return review.build_view(doc, chk, state["sections"], record)

    @app.post("/api/documents/{doc_id}/retry", status_code=202)
    def retry(request: Request, doc_id: str):
        state = get_state(request, doc_id)
        next_state = request.app.state.store.requeue(doc_id)
        if next_state is None:
            raise HTTPException(409, f"다시 돌릴 수 없는 문서입니다 (지금: {state['status']})")
        request.app.state.worker.submit(doc_id)
        return progress.view(next_state)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


app = create_app()
