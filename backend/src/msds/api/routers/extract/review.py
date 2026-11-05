"""2.2 추출값 확인(검수): 항별 칸·근거·검사 문제 보기, 칸 확인·수정·되돌림, 항 확인 완료.

검수 기록은 저장소에 따로 남기고 추출 결과 파일은 고치지 않는다.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from msds.api.routers.extract.deps import done_result
from msds.api.routers.extract.storage import republish
from msds.service import review
from msds.service.store import now_kst

router = APIRouter(tags=["review"])


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
    section: int
    confirmed: bool
    reviewer: str = Field(min_length=1, max_length=40, pattern=r"\S")

    @field_validator("section")
    @classmethod
    def in_extract_sections(cls, v: int) -> int:
        if v not in review.SECTIONS:
            raise ValueError(
                f"추출 대상 항이 아닙니다: {v} (대상: {', '.join(map(str, review.SECTIONS))})"
            )
        return v


@router.get("/api/documents/{doc_id}/review")
def review_view(request: Request, doc_id: str):
    """2.2 추출값 확인: 항별 칸, 근거, 검사 문제, 검수 기록."""
    state, doc, chk = done_result(request, doc_id)
    return review.build_view(
        doc, chk, state["sections"], request.app.state.store.load_review(doc_id)
    )


@router.put("/api/documents/{doc_id}/review/fields")
def review_field(request: Request, doc_id: str, body: FieldReview):
    """칸 하나 확인·수정·되돌림. 원래 값, 근거, 검토자, 시각을 함께 남긴다. 추출 결과 파일은 고치지 않는다."""
    state, doc, chk = done_result(request, doc_id)
    try:
        record = request.app.state.store.update_review(
            doc_id,
            lambda r: review.set_field(
                r,
                doc,
                body.msds_index,
                body.path,
                body.action,
                body.value,
                body.reviewer.strip(),
                now_kst(),
            ),
        )
    except KeyError:
        raise HTTPException(404, f"없는 칸: {body.path}") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    republish(request, doc_id, "values_reviewed" if body.action == "confirm" else "value_edited")
    return review.build_view(doc, chk, state["sections"], record)


@router.put("/api/documents/{doc_id}/review/sections")
def review_section(request: Request, doc_id: str, body: SectionReview):
    """항 하나 확인 완료·취소."""
    state, doc, chk = done_result(request, doc_id)
    if body.msds_index >= len(doc["msds"]):
        raise HTTPException(404, f"없는 MSDS: {body.msds_index}")
    record = request.app.state.store.update_review(
        doc_id,
        lambda r: review.set_section(
            r,
            body.msds_index,
            body.section,
            body.confirmed,
            body.reviewer.strip(),
            now_kst(),
        ),
    )
    republish(request, doc_id, "values_reviewed")
    return review.build_view(doc, chk, state["sections"], record)
