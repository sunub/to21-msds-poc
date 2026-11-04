"""PostgreSQL 결과 보관: 끝난 결과를 검증해 저장, 저장된 결과 조회, 판정(B)용 전달 만들기.

파일 저장소로 띄운 앱에서는 모두 409다.
"""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from msds.api.routers.extract.deps import get_state, result_paths
from msds.checks.final_validation import summarize_checks, validate_document
from msds.service.handoff import extraction_date, publish_handoff
from msds.service.results import ResultNotReady, ResultStore

router = APIRouter(tags=["storage"])


def postgres_store(request: Request, what: str):
    """PostgreSQL 작업 저장소. 파일 저장소로 띄웠으면 409."""
    store = request.app.state.store
    if not hasattr(store, "dsn") or not hasattr(store, "schema"):
        raise HTTPException(409, f"PostgreSQL 작업에서만 {what}")
    return store


@router.post("/api/documents/{doc_id}/results/persist")
def persist_completed_result(request: Request, doc_id: str):
    """Persist a previously completed, currently published PostgreSQL attempt."""
    state = get_state(request, doc_id)
    store = postgres_store(request, "결과를 저장할 수 있습니다")
    token = state.get("_active_token")
    if state["status"] != "done" or not token:
        raise HTTPException(409, "완료된 현재 추출 결과가 없습니다")
    out, checks = result_paths(request, doc_id)
    if not out.is_file() or not checks.is_file():
        raise HTTPException(409, "추출 결과 또는 검사 기록이 없습니다")
    doc = json.loads(out.read_text(encoding="utf-8"))
    chk = json.loads(checks.read_text(encoding="utf-8"))
    try:
        validation = summarize_checks(doc, chk)
        verified, _ = validate_document(doc, chk)
        if (
            verified["schema_errors"] != chk["schema_errors"]
            or verified["to21_validator"] != chk["to21_validator"]
        ):
            raise HTTPException(
                409, "추출 결과와 검사 기록이 현재 검증 결과와 일치하지 않습니다"
            )
    except ValueError as exc:
        raise HTTPException(409, f"검사 기록을 확인할 수 없습니다: {exc}") from exc
    result_store = ResultStore(store.dsn, schema=store.schema)
    try:
        result_store.get_active(doc_id)
    except ResultNotReady:
        # Prefer the actual extracted_at in the result. A prior saved
        # snapshot keeps its existing provenance on repeated requests.
        extracted_at = (doc.get("doc", {}).get("extraction") or {}).get("extracted_at")
    else:
        extracted_at = None
    try:
        saved = result_store.save_completed(
            doc_id, token, doc, chk, extracted_at=extracted_at
        )
    except ValueError as exc:
        raise HTTPException(409, f"추출 시각을 확인할 수 없습니다: {exc}") from exc
    return {"job_id": doc_id, "validation": validation, **saved}


@router.get("/api/documents/{doc_id}/results/stored")
def stored_result(request: Request, doc_id: str):
    """Read the active extraction and verification snapshot from PostgreSQL."""
    get_state(request, doc_id)
    store = postgres_store(request, "저장된 결과를 조회할 수 있습니다")
    saved = ResultStore(store.dsn, schema=store.schema).get_active(doc_id)
    return {
        "job_id": doc_id,
        "to21": saved["extraction"],
        "checks": saved["checks"],
        "validation": summarize_checks(saved["extraction"], saved["checks"]),
        "extraction_sha256": saved["extraction_sha256"],
        "checks_sha256": saved["checks_sha256"],
    }


def _publish(store, doc_id: str, reason: str) -> dict:
    """저장된 결과를 실제 추출 날짜로 판정에 넘긴다."""
    saved = ResultStore(store.dsn, schema=store.schema).get_active(doc_id)
    doc = saved.get("extraction") or {}
    actual = (doc.get("doc", {}).get("extraction") or {}).get("extracted_at")
    return publish_handoff(
        store, doc_id, as_of=extraction_date(actual), reason=reason, schema=store.schema
    )


class ToJudgment(BaseModel):
    reviewer: str = Field(min_length=1, max_length=40, pattern=r"\S")


@router.post("/api/documents/{doc_id}/to-judgment", status_code=201)
def to_judgment(request: Request, doc_id: str, body: ToJudgment):
    """추출값 확인을 마치고 판정으로 넘긴다 (넘김②, reason=values_reviewed)."""
    get_state(request, doc_id)
    store = postgres_store(request, "판정용 전달을 만들 수 있습니다")
    payload = _publish(store, doc_id, "values_reviewed")
    return {"job_id": doc_id, "handoff_seq": payload["handoff_seq"]}


@router.post("/api/documents/{doc_id}/handoffs", status_code=201)
def create_handoff(request: Request, doc_id: str):
    """Publish the extraction snapshot using its actual extraction date."""
    get_state(request, doc_id)
    store = postgres_store(request, "판정용 전달을 만들 수 있습니다")
    payload = _publish(store, doc_id, "extraction_done")
    return {
        "job_id": doc_id,
        "handoff_seq": payload["handoff_seq"],
        "as_of": payload["as_of"],
        "extraction_sha256": payload["extraction_sha256"],
        "validator": payload["checks"]["validator"],
    }
