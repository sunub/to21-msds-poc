"""작업 접수·목록·상태·재시도 API (A1)."""

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from msds.api.routers.extract.deps import get_state
from msds.service import pipeline, progress

MAX_PDF_BYTES = 50 * 1024 * 1024

_DATE = r"^\d{4}-\d{2}-\d{2}$"
_ACTIVE = ("queued", "running")
_FAILED = ("failed", "interrupted")

router = APIRouter(tags=["documents"])


def queue_fields(request: Request, state: dict) -> dict:
    store = request.app.state.store
    position = eta = None
    if hasattr(store, "queue_info") and state["status"] == "queued":
        info = store.queue_info(
            state["id"], workers=int(os.environ.get("MSDS_EXTRACT_WORKERS", "1"))
        )
        position, eta = info["queue_position"], info.get("estimated_completion_seconds")
    return {
        "queue_position": position,
        "eta_seconds": eta,
        "review_stage": state.get("review_stage"),
    }


@router.post("/api/documents", status_code=202)
async def upload(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
    as_of: str | None = Query(None, pattern=_DATE),
    reuse: bool = True,
):
    name = Path(filename.replace("\\", "/")).name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 올릴 수 있습니다")
    limit = MAX_PDF_BYTES  # 시험이 모듈 값을 바꿔 보므로 부를 때 읽는다
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(413, f"파일이 너무 큽니다 (최대 {limit // 1024 // 1024}MB)")
    body = await request.body()
    if len(body) > limit:
        raise HTTPException(413, f"파일이 너무 큽니다 (최대 {limit // 1024 // 1024}MB)")
    if not body.startswith(b"%PDF-"):
        raise HTTPException(400, "PDF 파일이 아닙니다")
    store = request.app.state.store
    if hasattr(store, "dsn"):
        state = store.create(body, name, as_of, pipeline.model_tag(), reuse=reuse)
    else:
        state = store.create(body, name, as_of, pipeline.model_tag())
    request.app.state.worker.submit(state["id"])
    return {**progress.view(state), **queue_fields(request, state)}


@router.get("/api/documents")
def list_documents(
    request: Request, status: Literal["all", "active", "done", "failed"] = "all"
):
    states = request.app.state.store.list()
    groups = {
        "all": states,
        "active": [s for s in states if s["status"] in _ACTIVE],
        "done": [s for s in states if s["status"] == "done"],
        "failed": [s for s in states if s["status"] in _FAILED],
    }
    return {
        "items": [
            {**progress.summary_view(s), **queue_fields(request, s)}
            for s in groups[status]
        ],
        "counts": {k: len(v) for k, v in groups.items()},
    }


@router.get("/api/documents/{doc_id}")
def detail(request: Request, doc_id: str):
    state = get_state(request, doc_id)
    return {**progress.view(state), **queue_fields(request, state)}


@router.post("/api/documents/{doc_id}/retry", status_code=202)
def retry(request: Request, doc_id: str):
    state = get_state(request, doc_id)
    next_state = request.app.state.store.requeue(doc_id)
    if next_state is None:
        raise HTTPException(
            409, f"다시 돌릴 수 없는 문서입니다 (지금: {state['status']})"
        )
    request.app.state.worker.submit(doc_id)
    return {**progress.view(next_state), **queue_fields(request, next_state)}
