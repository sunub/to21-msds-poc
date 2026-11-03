"""B 화면 API: 판정·설명·검토·저장·리포트. 계약: docs/superpowers/specs/contracts/5-api.schema.json

혼자 실행: cd backend && .venv/bin/uvicorn --app-dir src msds.api.judge_app:app --port 8011
추출 API와 한 앱으로: app.include_router(router) + attach(app)
"""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from msds.judge import explain as ex
from msds.judge import reports
from msds.judge.service import NOT_SENT, Conflict, InvalidAction, JudgeService, NotFound
from msds.judge.worker import Workers

JOB_ID = r"^U-\d{8}-\d{3,}$"
FINDING_ID = r"^m\d+/(F2|F2L|F15|F15DG|FPT):[^\s]+$"
MAX_SUMMARY_JOBS = 200
JobId = Annotated[str, Path(pattern=JOB_ID)]


def _no_nul(v):
    # PostgreSQL 글자 칸은 NUL을 받지 못한다. 500이 되지 않게 입력에서 막는다
    if v is not None and "\x00" in v:
        raise ValueError("글자에 NUL 문자가 있습니다")
    return v


Reviewer = Annotated[str, Field(min_length=1, max_length=50, pattern=r"\S"), AfterValidator(_no_nul)]
Comment = Annotated[str | None, Field(max_length=2000), AfterValidator(_no_nul)]
router = APIRouter(prefix="/api/judgments", tags=["judgments"])


class ReviewEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: Annotated[str, Field(pattern=FINDING_ID)]
    action: Literal["불일치 확정", "예외 승인", "확인", "의견", "되돌리기"]
    comment: Comment = None
    reviewer: Reviewer
    seen_version: Annotated[int, Field(ge=1)]
    seen_event_id: Annotated[int | None, Field(ge=1)] = None

    @model_validator(mode="after")
    def _comment_required(self):
        if self.action in ("예외 승인", "의견") and not (self.comment or "").strip():
            raise ValueError(f"{self.action}에는 의견이 필요합니다")
        return self


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer: Reviewer
    seen_version: Annotated[int, Field(ge=1)]
    note: Comment = None


class ReportInclude(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regenerated_msds: bool
    findings_2: bool
    findings_15: bool
    components: bool
    history: bool


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["html", "xlsx", "json", "pdf"]
    snapshot_no: Annotated[int | None, Field(ge=1)] = None
    include: ReportInclude


def _svc(request: Request) -> JudgeService:
    return request.app.state.judge


def _call(fn, *args):
    try:
        return fn(*args)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    except InvalidAction as e:
        raise HTTPException(422, str(e)) from e
    except Conflict as e:
        raise HTTPException(409, {"message": str(e), "latest_version": e.latest, "pending_handoff": e.pending}) from e


@router.get("/summary")
def summary(request: Request, job_ids: str = Query(max_length=8000)):
    ids = [x for x in job_ids.split(",") if x]
    if len(ids) > MAX_SUMMARY_JOBS or any(not re.fullmatch(JOB_ID.strip("^$"), x) for x in ids):
        raise HTTPException(422, f"job_ids 는 작업 번호 {MAX_SUMMARY_JOBS}개까지입니다")
    return _svc(request).summary(ids)


@router.post("/_test/handoffs", status_code=201)
def put_test_handoff(request: Request, body: dict):
    """시험용: A 없이 넘김 기록을 넣는다 (파트 B 설계 6절). MSDS_JUDGE_TEST_API=1 일 때만 있다."""
    if os.environ.get("MSDS_JUDGE_TEST_API") != "1":
        raise HTTPException(404, "Not Found")
    required = ("contract", "job_id", "handoff_seq", "reason", "as_of", "source", "extraction", "extraction_sha256", "checks", "fields_total", "field_status")
    missing = [k for k in required if k not in body]
    seq = body.get("handoff_seq")
    if missing or not isinstance(seq, int) or seq < 1 or not re.fullmatch(JOB_ID.strip("^$"), str(body.get("job_id"))):
        raise HTTPException(422, f"넘김 기록 칸 오류: {missing or 'job_id·handoff_seq'}")
    try:
        _svc(request).put_test_handoff(body)
    except psycopg.errors.UniqueViolation as e:
        raise HTTPException(409, "이미 있는 넘김 번호") from e
    return {"job_id": body["job_id"], "handoff_seq": seq}


@router.get("/{job_id}/status")
def status(request: Request, job_id: JobId):
    return _svc(request).status(job_id)


@router.get("/{job_id}/versions")
def versions(request: Request, job_id: JobId):
    return _call(_svc(request).versions, job_id)


@router.get("/{job_id}/history")
def history(request: Request, job_id: JobId):
    return _svc(request).history(job_id)


@router.get("/{job_id}/save-overview")
def save_overview(request: Request, job_id: JobId):
    return _call(_svc(request).save_overview, job_id)


@router.post("/{job_id}/reviews", status_code=201)
def add_review(request: Request, job_id: JobId, body: ReviewEventRequest):
    comment = body.comment.strip() if body.comment else None
    # 칸을 보내지 않으면 충돌을 검사하지 않고, null 을 보내면 "기록이 없는 것을 봤음"으로 검사한다
    seen = body.seen_event_id if "seen_event_id" in body.model_fields_set else NOT_SENT
    return _call(_svc(request).add_review_event, job_id, body.finding_id, body.action, comment, body.reviewer, body.seen_version, seen)


@router.post("/{job_id}/snapshots", status_code=201)
def save(request: Request, job_id: JobId, body: SaveRequest):
    return _call(_svc(request).save_snapshot, job_id, body.reviewer, body.seen_version, body.note)


@router.post("/{job_id}/reports")
def report(request: Request, job_id: JobId, body: ReportRequest):
    data = _call(_svc(request).report_data, job_id, body.snapshot_no)
    try:
        content = reports.render(data, body.format, body.include.model_dump())
    except reports.ReportError as e:
        raise HTTPException(422, str(e)) from e
    headers = {} if body.format == "html" else {"Content-Disposition": reports.content_disposition(reports.filename(data, body.format))}
    return Response(content, media_type=reports.MEDIA[body.format], headers=headers)


@router.get("/{job_id}")
def view(request: Request, job_id: JobId, version: Annotated[int | None, Query(ge=1)] = None):
    return _call(_svc(request).view, job_id, version)


def attach(app: FastAPI) -> None:
    """이미 있는 앱에 붙일 때 lifespan 에서 부른다. app.state.judge, app.state.judge_workers 를 채운다."""
    service = JudgeService(llm=ex.make_llm())
    workers = Workers(service)
    workers.start()
    app.state.judge, app.state.judge_workers = service, workers


def detach(app: FastAPI) -> None:
    app.state.judge_workers.stop()
    app.state.judge.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    attach(app)
    yield
    detach(app)


app = FastAPI(title="MSDS 판정·저장 API", lifespan=lifespan)
# 단독으로 띄울 때 화면 개발 서버(next dev)가 다른 포트에서 부른다. 값은 extract_app과 같다
app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"],
                   allow_origins=[o.strip() for o in os.environ.get("MSDS_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,"
                                                                     "http://localhost:3101,http://127.0.0.1:3101").split(",") if o.strip()])
app.include_router(router)
