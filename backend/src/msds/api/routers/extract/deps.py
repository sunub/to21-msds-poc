"""라우터들이 함께 쓰는 문서 찾기와 산출물 위치.

store·worker·쪽 이미지 폴더는 create_app이 app.state에 넣어 둔다 (store, worker, pages_root).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException, Request

from msds.common import paths
from msds.service import pipeline


def get_state(request: Request, doc_id: str) -> dict:
    """문서 진행 상태. 없으면 404."""
    state = request.app.state.store.get(doc_id)
    if state is None:
        raise HTTPException(404, f"없는 문서: {doc_id}")
    return state


def artifact_paths(request: Request, doc_id: str) -> dict | None:
    """PostgreSQL 작업이면 지금 게시된 시도의 산출물 폴더들. 파일 저장소면 None."""
    store = request.app.state.store
    if not hasattr(store, "artifact_paths"):
        return None
    published = store.artifact_paths(doc_id)
    if published is not None:
        return published
    # Unpublished PostgreSQL attempts must never fall back to old files.
    empty = store.root / ".unpublished"
    return {
        "pages_dir": empty / "pages",
        "sections_dir": empty / "sections",
        "runs_dir": empty / "runs",
    }


def page_root(request: Request, doc_id: str) -> Path:
    published = artifact_paths(request, doc_id)
    return (
        published["pages_dir"]
        if published
        else (request.app.state.pages_root or paths.PAGES)
    )


def result_paths(request: Request, doc_id: str) -> tuple[Path, Path]:
    """(TO21 결과 파일, 검사 기록 파일)."""
    published = artifact_paths(request, doc_id)
    if published:
        run = published["runs_dir"] / doc_id
        return run / "outputs" / f"{doc_id}.json", run / "checks" / f"{doc_id}.json"
    return pipeline.result_paths(request.app.state.store, doc_id)


def done_result(request: Request, doc_id: str) -> tuple[dict, dict, dict]:
    """(진행 상태, 추출 결과, 검사 결과). 끝나기 전이면 409, 결과 파일이 없으면 404. 검사 기록이 없으면 {}."""
    state = get_state(request, doc_id)
    if state["status"] != "done":
        raise HTTPException(409, "추출이 끝나지 않았습니다")
    out, checks = result_paths(request, doc_id)
    if not out.is_file():
        raise HTTPException(404, "결과 파일이 없습니다")
    chk = json.loads(checks.read_text(encoding="utf-8")) if checks.is_file() else {}
    return state, json.loads(out.read_text(encoding="utf-8")), chk
