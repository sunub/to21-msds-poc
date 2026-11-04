"""추출 결과 보기: 끝난 문서의 TO21 JSON과 검사 요약, 항별 중간 값(문서가 끝나기 전에도)."""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as PathParam

from msds.api.routers.extract.deps import artifact_paths, done_result, get_state
from msds.checks.final_validation import summarize_checks
from msds.extract.section_runner import raw_path
from msds.service import pipeline

router = APIRouter(tags=["results"])


@router.get("/api/documents/{doc_id}/result")
def result(request: Request, doc_id: str):
    _, doc, chk = done_result(request, doc_id)
    try:
        validation = summarize_checks(doc, chk)
    except ValueError:
        validation = {"status": "unavailable"}
    return {
        "to21": doc,
        "needs_review": validation.get("needs_review", chk.get("needs_review", [])),
        "warnings": chk.get("warnings", []),
        "validation": validation,
        "schema_errors": chk.get("schema_errors", []),
        "to21_validator": chk.get("to21_validator", []),
    }


@router.get("/api/documents/{doc_id}/sections/{msds_index}/{section}")
def section_result(
    request: Request,
    doc_id: str,
    msds_index: int = PathParam(ge=0),
    section: int = PathParam(ge=1, le=16),
):
    """끝난 항의 값(펼치기 전 중간 형식). 문서가 끝나기 전에도 준다. 모델 응답 원문과 사용량은 내보내지 않는다."""
    state = get_state(request, doc_id)
    item = next(
        (
            s
            for s in state["sections"]
            if (s["msds_index"], s["section"]) == (msds_index, section)
        ),
        None,
    )
    if item is None:
        raise HTTPException(404, f"없는 항: MSDS {msds_index} {section}항")
    # 상태부터 본다: 다시 돌리는 중이면 이전 실행의 파일이 남아 있다
    if item["status"] not in ("done", "failed"):
        raise HTTPException(409, "이 항은 아직 끝나지 않았습니다")
    published = artifact_paths(request, doc_id)
    path = (
        raw_path(published["runs_dir"] / doc_id, doc_id, msds_index, section)
        if published
        else pipeline.section_raw_path(
            request.app.state.store, doc_id, msds_index, section
        )
    )
    if not path.is_file():
        raise HTTPException(404, "항 결과 파일이 없습니다")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        **item,
        "errors": raw.get("errors", []),
        "check_problems": raw.get("check_problems", []),
        "parsed": raw.get("parsed") if raw.get("ok") else None,
    }
