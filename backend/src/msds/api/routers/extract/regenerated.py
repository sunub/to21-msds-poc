"""재생성 MSDS. 모델을 부르지 않고 결과 파일로 그때그때 만든다. source=reviewed면 검수 수정을 반영한다."""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from msds.api.routers.extract.deps import done_result
from msds.checks.validator import load_to21_module
from msds.service import regenerated, review

logger = logging.getLogger(__name__)
router = APIRouter(tags=["regenerated"])


def load_regen():
    """TO21 제공 재생성 스크립트. 저장소에 없으니(D-47) 부를 때 읽는다."""
    return load_to21_module("regen")


@router.get("/api/documents/{doc_id}/regenerated")
def regenerated_msds(
    request: Request,
    doc_id: str,
    source: Literal["reviewed", "original"] = Query("reviewed"),
):
    """끝난 문서의 재생성 MSDS. 모델을 부르지 않고 결과 파일로 그때그때 만든다."""
    state, doc, chk = done_result(request, doc_id)
    if source == "reviewed":
        doc = review.apply_edits(doc, request.app.state.store.load_review(doc_id))
    try:
        parts = regenerated.regenerate_sections(doc, load_regen())
    except (
        Exception
    ) as e:  # TO21 제공 스크립트가 어떤 입력에서 터질지 여기서 알 수 없다
        logger.exception("재생성 실패: %s", doc_id)
        raise HTTPException(
            500,
            "재생성하지 못했습니다. 추출값 중 재생성 스크립트가 처리하지 못한 값이 있습니다. "
            "다시 불러와도 같으면 개발 담당에게 아래 내용을 알려 주세요. "
            f"(문서 {doc_id}, {type(e).__name__}: {str(e)[:300]})",
        ) from e
    flagged = {(r["msds_index"], r["section"]) for r in chk.get("needs_review", [])}
    status = {(s["msds_index"], s["section"]): s["status"] for s in state["sections"]}
    return {
        "msds": [
            {
                **m,
                "sections": [
                    {
                        "section": s["section"],
                        "title": s["title"],
                        "status": status.get((m["msds_index"], s["section"]), "failed"),
                        "needs_review": (m["msds_index"], s["section"]) in flagged,
                        "lines": s["lines"],
                    }
                    for s in m["sections"]
                ],
            }
            for m in parts
        ]
    }
