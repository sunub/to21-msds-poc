"""원본 PDF와 전처리 뒤 쪽 이미지·쪽 글. 화면이 원문을 그리고 근거 줄(p2:L23)을 맞춰 보는 데 쓴다."""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse

from msds.api.routers.extract.deps import get_state, page_root
from msds.extract.inputs import read_page_lines

router = APIRouter(tags=["pages"])


@router.get("/api/documents/{doc_id}/pdf")
def source_pdf(request: Request, doc_id: str):
    """올린 원본 PDF 그대로. 화면이 원본을 직접 그려 추출값을 맞춰 본다."""
    state = get_state(request, doc_id)
    path = request.app.state.store.pdf_path(doc_id)
    if not path.is_file():
        raise HTTPException(404, "원본 PDF가 없습니다")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=state.get("filename") or "source.pdf",
        content_disposition_type="inline",
    )


@router.get("/api/documents/{doc_id}/pages/{page}/image")
def page_image(request: Request, doc_id: str, page: int = PathParam(ge=1)):
    get_state(request, doc_id)
    path = page_root(request, doc_id) / doc_id / f"p{page:03d}.png"
    if not path.is_file():
        raise HTTPException(404, "쪽 이미지가 아직 없습니다")
    return FileResponse(path, media_type="image/png")


@router.get("/api/documents/{doc_id}/pages/{page}/lines")
def page_lines(request: Request, doc_id: str, page: int = PathParam(ge=1)):
    get_state(request, doc_id)
    try:
        lines = [
            l
            for l in read_page_lines(doc_id, page_root(request, doc_id))
            if l.page == page
        ]
    except FileNotFoundError:
        lines = []
    if not lines:
        raise HTTPException(404, "쪽 글이 아직 없습니다")
    return {
        "page": page,
        "lines": [{"id": l.id, "no": l.no, "text": l.text} for l in lines],
    }


@router.get("/api/documents/{doc_id}/pages/{page}/boxes")
def page_boxes(request: Request, doc_id: str, page: int = PathParam(ge=1)):
    """OCR로 읽은 쪽의 글과 자리. 글꼴이 깨졌거나 스캔한 쪽은 원본 PDF 글자 층으로 근거를 찾을 수 없어 화면이 이 자리를 강조한다.
    box는 쪽 이미지(width×height 픽셀) 기준 [x0, y0, x1, y1]이다. OCR 쪽이 아니거나 기록이 없으면 items가 비어 있다."""
    get_state(request, doc_id)
    folder = page_root(request, doc_id) / doc_id
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        info = next(p for p in meta["pages"] if p.get("page") == page)
        trace = json.loads((folder / "item_trace.json").read_text(encoding="utf-8"))
        raw = next(p for p in trace if p.get("page") == page).get("raw_items") or []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        return {"page": page, "width": None, "height": None, "items": []}
    items = [{"text": i["text"], "box": i["box"]} for i in raw
             if info.get("text_source") == "OCR" and isinstance(i, dict) and i.get("text") and len(i.get("box") or []) == 4]
    return {"page": page, "width": info.get("width"), "height": info.get("height"), "items": items}
