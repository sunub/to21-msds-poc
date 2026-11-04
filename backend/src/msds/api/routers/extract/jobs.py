"""작업 접수·목록·상태·재시도 API (A1). 목록·상세에는 검수 진행(A2 document_extras·review_stage)도 붙는다."""

import json
import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from msds.api.routers.extract.deps import get_state, result_paths_for
from msds.service import pipeline, progress, review

MAX_PDF_BYTES = 50 * 1024 * 1024

_DATE = r"^\d{4}-\d{2}-\d{2}$"
_ACTIVE = ("queued", "running")
_FAILED = ("failed", "interrupted")

LOG = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


def review_context(request: Request, states: list[dict]) -> dict:
    """[A2] 끝난 문서들의 검수 기록과 판정 넘김 여부를 한 번에 읽는다 (목록 폴링마다 문서당 연결을 열지 않는다)."""
    store = request.app.state.store
    done = [s for s in states if s["status"] == "done"]
    if not done:
        return {"records": {}, "handed": set()}
    ask = getattr(store, "handed_off", None)
    try:
        return {"records": store.review_records(done), "handed": set(ask([s["id"] for s in done])) if ask else set()}
    except Exception:
        # 검수 진행은 덧붙이는 정보다. 읽지 못해도 목록·상세는 보여 준다 (진행 칸만 비고 단계는 '검수 중')
        LOG.exception("검수 진행을 읽지 못했습니다")
        return {"records": {}, "handed": set()}


def review_fields(request: Request, state: dict, ctx: dict) -> dict:
    """[A2] 검수 진행. 끝나지 않았거나 결과 파일이 없으면 document_extras 는 None."""
    record = ctx["records"].get(state["id"])
    if state["status"] != "done" or record is None:  # 목록을 읽는 사이 다시 실행되었으면 기록이 없다
        return {"review_stage": None, "document_extras": None}
    extras = None
    out, checks = result_paths_for(request, state)
    try:
        if out.is_file():
            doc = json.loads(out.read_text(encoding="utf-8"))
            chk = json.loads(checks.read_text(encoding="utf-8")) if checks.is_file() else {}
            extras = review.document_extras(doc, chk, state["sections"], record)
    except (OSError, ValueError, KeyError, TypeError):
        # 결과 파일 하나가 깨져도 목록 전체를 막지 않는다. 그 문서의 결과 화면이 오류를 보여 준다
        LOG.exception("검수 진행을 계산하지 못했습니다: %s", state["id"])
    stage = review.review_stage(state["status"], record, handed_off=state["id"] in ctx["handed"])
    return {"review_stage": stage, "document_extras": extras}


def queue_fields(request: Request, state: dict, ctx: dict | None = None) -> dict:
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
        **review_fields(request, state, ctx if ctx is not None else review_context(request, [state])),
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
    ctx = review_context(request, groups[status])
    return {
        "items": [
            {**progress.summary_view(s), **queue_fields(request, s, ctx)}
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
