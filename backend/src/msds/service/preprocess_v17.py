"""서비스 전처리: version17 방법(pdf_pipeline.extract_pdf)으로 쪽 이미지와 쪽 글을 만든다.

render.preprocess와 이름·인자·반환(meta)이 같아 service.pipeline.Steps.preprocess 자리에 그대로 들어간다.
결과물은 extract_pdf가 만든 그대로(pNNN.txt, pNNN.png, meta.json)이고 소비하는 쪽은 바꾸지 않는다.
다만 render.load_pages가 읽는 파일 두 가지를 덧붙인다: 출처가 OCR인 쪽의 최종 글 pNNN.ocr_input.txt,
원문 대조용으로 줄 번호(L001 )를 뗀 글 pNNN.match.txt (OCR·텍스트층 쪽 모두).

실행 위치는 둘 중 하나다.
- 기본: 이 프로세스 안에서 extract_pdf를 직접 부른다. 설정은 MSDS_OCR_DEVICE(기본 gpu:0, cpu도 가능), MSDS_USE_DOCLING(0이면 보조 표 분석을 끈다).
- MSDS_EXTRACTION_API_URL을 주면 별도 추출 API(api/extraction_app, 예: http://127.0.0.1:8000)에 PDF를 보내고, 워커가 만든
  결과 폴더를 이 작업의 폴더로 복사한다. 이때 OCR 장치와 Docling 사용은 워커 쪽 설정(--ocr-device, --no-docling)을 따른다.
  API와 이 프로세스는 같은 파일시스템을 봐야 한다(응답의 result_dir를 읽는다). 대기 한도는 MSDS_EXTRACTION_API_TIMEOUT(초, 기본 1800).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from msds.common import paths
from msds.preprocess.render import page_match_txt
from msds.preprocess.source import page_ocr_input

DPI = 200   # v17 기본값 (pdf_pipeline.extract_pdf)
OCR_DEVICE_ENV = "MSDS_OCR_DEVICE"
DOCLING_ENV = "MSDS_USE_DOCLING"
API_URL_ENV = "MSDS_EXTRACTION_API_URL"
API_TIMEOUT_ENV = "MSDS_EXTRACTION_API_TIMEOUT"
API_POLL_SECONDS = 1.0
LINE_NO = re.compile(r"^L\d{3} ", re.MULTILINE)   # page_text가 줄마다 붙이는 줄 번호
PIPELINE = "msds.preprocess.pdf_pipeline"   # pdf_pipeline.PIPELINE. 무거운 모델 라이브러리를 부르지 않으려 여기에 적는다


class ExtractionApiError(RuntimeError):
    """추출 API에 연결하지 못했거나 작업이 끝나지 못했다."""


def _request(req: urllib.request.Request, timeout: float = 30) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ExtractionApiError(f"추출 API가 {exc.code}로 응답했습니다: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ExtractionApiError(f"추출 API에 연결하지 못했습니다 ({req.full_url}): {exc}") from exc


def _multipart(pdf_path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    name = pdf_path.name.replace('"', "%22").replace("\r", "").replace("\n", "")
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n").encode("utf-8")
    body = head + pdf_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def strip_line_numbers(text: str) -> str:
    """모델 입력용 글(L001 …)에서 줄 번호를 뗀다. 원문 대조는 줄 번호가 없는 글로 한다."""
    return LINE_NO.sub("", text)


def _check_destination(out: Path, force: bool) -> None:
    """extract_pdf와 같은 기준: 비어 있지 않은 폴더는 force일 때, 이 파이프라인이 만든 폴더만 교체한다."""
    if not out.exists() or not any(out.iterdir()):
        return
    if not force:
        raise ValueError(f"Output directory is not empty: {out}. Choose a new output directory.")
    try:
        owner = json.loads((out / "config.json").read_text(encoding="utf-8")).get("pipeline")
    except (OSError, ValueError):
        owner = None
    if owner != PIPELINE:
        raise ValueError("--force cannot replace historical outputs or outputs of a different pipeline")


def api_extractor(base_url: str, *, timeout: float | None = None, poll: float = API_POLL_SECONDS,
                  sleep: Callable[[float], None] = time.sleep) -> Callable:
    """extract_pdf와 같은 모양(pdf_path, output_dir, *, doc_id, dpi, force, on_progress, **options)의 함수를 만든다.
    options(ocr_device, use_docling)는 워커 설정을 따르므로 쓰지 않는다."""
    base = base_url.rstrip("/")
    limit = float(timeout if timeout is not None else (os.environ.get(API_TIMEOUT_ENV) or 1800))

    def run(pdf_path, output_dir, *, doc_id, dpi=DPI, force=False, on_progress=None, **options) -> dict:
        out = Path(output_dir)
        _check_destination(out, force)
        body, content_type = _multipart(Path(pdf_path))
        job = _request(urllib.request.Request(f"{base}/api/v1/documents", data=body, method="POST",
                                              headers={"Content-Type": content_type}), timeout=120)
        job_id = job["job_id"]
        deadline = time.monotonic() + limit
        seen = 0
        while True:
            state = _request(urllib.request.Request(f"{base}/api/v1/jobs/{job_id}"))
            total, done = state.get("total_pages"), state.get("completed_pages") or 0
            while on_progress is not None and total and seen < done:
                seen += 1
                on_progress({"stage": "page", "doc_id": doc_id, "page": seen, "completed_pages": seen,
                             "total_pages": total, "page_count": total})
            status = state.get("status")
            if status == "succeeded" and state.get("result_ready"):
                break
            if status in ("failed", "recovery_required"):
                raise ExtractionApiError(f"추출 API 작업이 {status}: {state.get('error') or '원인 없음'} (job {job_id})")
            if time.monotonic() > deadline:
                raise ExtractionApiError(f"추출 API 작업이 {int(limit)}초 안에 끝나지 않았습니다 (job {job_id}, 상태 {status})")
            sleep(poll)
        result = Path(state["result_dir"])
        if not (result / "meta.json").is_file():
            raise ExtractionApiError(f"결과 폴더에 meta.json이 없습니다. 이 컴퓨터에서 볼 수 있는 경로인지 확인하세요: {result}")
        out.parent.mkdir(parents=True, exist_ok=True)
        staging = out.parent / f".{out.name}.api-copy-{uuid.uuid4().hex[:8]}"
        shutil.copytree(result, staging)   # 복사가 끝난 뒤에 이름을 바꿔 게시한다
        if out.exists():
            shutil.rmtree(out)
        staging.rename(out)
        return json.loads((out / "meta.json").read_text(encoding="utf-8"))

    return run


def preprocess_v17(pdf_path: Path, doc_id: str, dpi: int = DPI, force: bool = False,
                   on_page: Callable[[int, int], None] | None = None, *, pages_root: Path | None = None,
                   extractor: Callable | None = None) -> dict:
    """on_page(쪽 번호, 전체 쪽수)는 쪽마다 한 번 부른다. 이미 만든 결과를 그대로 돌려줄 때(force 아님)는 부르지 않는다.
    extractor는 시험에서 extract_pdf를 바꿔 끼우는 자리다."""
    out_dir = paths.page_dir(doc_id) if pages_root is None else Path(pages_root) / doc_id
    meta_path = out_dir / "meta.json"
    if meta_path.exists() and not force:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    # extract_pdf의 force는 자기가 만든 파일만 있는 폴더만 교체한다. 이 모듈이 덧붙인 파일은 먼저 지운다.
    for stale in (*out_dir.glob("p[0-9][0-9][0-9].ocr_input.txt"), *out_dir.glob("p[0-9][0-9][0-9].match.txt")):
        stale.unlink()
    if extractor is None:
        api_url = (os.environ.get(API_URL_ENV) or "").strip()
        if api_url:
            extractor = api_extractor(api_url)
        else:
            from msds.preprocess.pdf_pipeline import extract_pdf as extractor

    def progress(event: dict) -> None:
        if on_page is not None and event.get("stage") == "page":
            on_page(event["page"], event["total_pages"])

    options: dict = {"use_docling": os.environ.get(DOCLING_ENV, "1").strip().lower() not in ("0", "false", "no")}
    device = (os.environ.get(OCR_DEVICE_ENV) or "").strip()
    if device:
        options["ocr_device"] = device
    meta = extractor(pdf_path, out_dir, doc_id=doc_id, dpi=dpi, force=force, on_progress=progress, **options)

    for page in meta.get("pages", []):
        source = page.get("text_source")
        if source not in ("OCR", "텍스트층"):
            continue
        final = (out_dir / page["text_file"]).read_text(encoding="utf-8")
        if source == "OCR":
            page_ocr_input(doc_id, page["page"], pages_root=pages_root).write_text(final, encoding="utf-8")
        page_match_txt(doc_id, page["page"], pages_root=pages_root).write_text(strip_line_numbers(final), encoding="utf-8")
    return meta
