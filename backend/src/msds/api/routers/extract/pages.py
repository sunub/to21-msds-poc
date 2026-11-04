"""원본 PDF와 전처리 뒤 쪽 이미지·쪽 글. 화면이 원문을 그리고 근거 줄(p2:L23)을 맞춰 보는 데 쓴다."""

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
