"""서비스 전처리를 version17로 바꿔도 모델과 다음 단계가 읽는 결과물 계약이 그대로인지 확인한다.

모델 입력 조립(extract/)은 바꾸지 않았다. 여기서는 v17 산출물이 그 조립부가 읽는 모양(pNNN.txt, pNNN.png,
meta.json, OCR 쪽의 pNNN.ocr_input.txt)과 같은지, 진행 알림과 재실행이 기존처럼 동작하는지 본다.
extract_pdf는 GPU 모델이 필요하므로 같은 모양의 파일을 만드는 가짜로 바꿔 끼운다.
"""
from pathlib import Path

import pytest

from msds.extract.inputs import read_page_lines, render_lines
from msds.extract.section_runner import doc_meta_from_pages
from msds.preprocess.render import load_pages, match_pages
from msds.service import pipeline
from msds.service.preprocess_v17 import DPI, preprocess_v17

TEXTS = {1: "L001 1. 화학제품과 회사에 관한 정보\nL002 제품명 시험물질\n", 2: "L001 2. 유해성·위험성\nL002 H302\n"}


def fake_extract_pdf(calls):
    """extract_pdf와 같은 모양의 폴더(pNNN.txt/png, meta.json)를 만든다. 1쪽은 텍스트층, 2쪽은 OCR로 읽은 쪽."""
    def run(pdf_path, output_dir, *, doc_id, dpi, force, on_progress, **options):
        output = Path(output_dir)
        calls.append({"existing_ocr_input": sorted(p.name for p in output.glob("*.ocr_input.txt")) if output.exists() else [],
                      "dpi": dpi, "force": force, "options": options})
        output.mkdir(parents=True, exist_ok=True)
        pages = []
        for n, text in TEXTS.items():
            (output / f"p{n:03d}.txt").write_text(text, encoding="utf-8")
            (output / f"p{n:03d}.png").write_bytes(b"png")
            pages.append({"page": n, "mode": "paddle_fresh_layout" if n == 2 else "pdf_xycut",
                          "state": "글꼴깨짐" if n == 2 else "정상", "text_file": f"p{n:03d}.txt",
                          "image_file": f"p{n:03d}.png", "text_source": "OCR" if n == 2 else "텍스트층"})
            on_progress({"stage": "page", "doc_id": doc_id, "page": n, "completed_pages": n, "total_pages": 2, "page_count": 2})
        meta = {"doc_id": doc_id, "source_file": "msds.pdf", "page_count": 2, "text_layer": "혼합", "pages": pages}
        (output / "meta.json").write_text(__import__("json").dumps(meta, ensure_ascii=False), encoding="utf-8")
        return meta
    return run


def test_steps_default_is_v17_and_dpi_is_200():
    assert pipeline.Steps().preprocess is preprocess_v17
    assert DPI == 200


def test_output_contract_is_what_model_input_reads(tmp_path):
    calls, seen = [], []
    meta = preprocess_v17(tmp_path / "in.pdf", "D1", force=True, on_page=lambda p, t: seen.append((p, t)),
                          pages_root=tmp_path, extractor=fake_extract_pdf(calls))

    assert seen == [(1, 2), (2, 2)]
    assert meta["page_count"] == 2 and meta["text_layer"] == "혼합"
    assert calls[0]["dpi"] == 200

    # 모델 입력: p<쪽>:L<번호> 글 형식 그대로
    lines = read_page_lines("D1", tmp_path)
    assert render_lines(lines).splitlines() == ["p1:L1 1. 화학제품과 회사에 관한 정보", "p1:L2 제품명 시험물질",
                                                "p2:L1 2. 유해성·위험성", "p2:L2 H302"]
    # 2항에 붙이는 쪽 이미지 경로 규칙
    assert (tmp_path / "D1" / "p002.png").is_file()
    # 문서 정보
    assert doc_meta_from_pages("D1", tmp_path)["pages"] == 2
    assert doc_meta_from_pages("D1", tmp_path)["text_layer"] == "혼합"
    # 넘김의 원문 대조: OCR 쪽의 최종 글은 ocr_input.txt에서 읽는다
    pages = load_pages("D1", pages_root=tmp_path)["pages"]
    texts, states = match_pages(pages)
    assert texts[2] == TEXTS[2] and texts[1] == TEXTS[1]
    assert states == {1: "정상", 2: "정상"}


def test_cached_result_is_returned_without_running(tmp_path):
    calls = []
    run = fake_extract_pdf(calls)
    preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path, extractor=run)
    seen = []
    meta = preprocess_v17(tmp_path / "in.pdf", "D1", force=False, on_page=lambda *a: seen.append(a),
                          pages_root=tmp_path, extractor=run)
    assert len(calls) == 1 and seen == [] and meta["page_count"] == 2


def test_rerun_removes_added_ocr_input_before_extract(tmp_path):
    """extract_pdf의 force는 자기 파일만 있는 폴더만 교체하므로, 덧붙인 ocr_input.txt는 먼저 지워야 한다."""
    calls = []
    run = fake_extract_pdf(calls)
    preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path, extractor=run)
    preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path, extractor=run)
    assert calls[0]["existing_ocr_input"] == []
    assert calls[1]["existing_ocr_input"] == []
    assert (tmp_path / "D1" / "p002.ocr_input.txt").is_file()


def test_env_options(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("MSDS_OCR_DEVICE", "cpu")
    monkeypatch.setenv("MSDS_USE_DOCLING", "0")
    preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path, extractor=fake_extract_pdf(calls))
    assert calls[0]["options"] == {"use_docling": False, "ocr_device": "cpu"}
    monkeypatch.delenv("MSDS_OCR_DEVICE")
    monkeypatch.delenv("MSDS_USE_DOCLING")
    preprocess_v17(tmp_path / "in.pdf", "D2", force=True, pages_root=tmp_path, extractor=fake_extract_pdf(calls))
    assert calls[1]["options"] == {"use_docling": True}


def test_extract_failure_propagates(tmp_path):
    def boom(*a, **k):
        raise ValueError("Cannot open original PDF")
    with pytest.raises(ValueError):
        preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path, extractor=boom)


# ── 추출 API(8000) 경유 ─────────────────────────────────────────────────────────
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from msds.service.preprocess_v17 import ExtractionApiError, PIPELINE, api_extractor


def _make_result(root: Path) -> Path:
    """extract_pdf가 게시한 것과 같은 모양의 결과 폴더."""
    root.mkdir(parents=True)
    pages = []
    for n, text in TEXTS.items():
        (root / f"p{n:03d}.txt").write_text(text, encoding="utf-8")
        (root / f"p{n:03d}.png").write_bytes(b"png")
        pages.append({"page": n, "state": "글꼴깨짐" if n == 2 else "정상", "text_file": f"p{n:03d}.txt",
                      "text_source": "OCR" if n == 2 else "텍스트층"})
    meta = {"pipeline": PIPELINE, "doc_id": "doc_x", "source_file": "msds.pdf", "page_count": 2, "text_layer": "혼합", "pages": pages}
    (root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (root / "config.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return root


class FakeApi:
    """POST /api/v1/documents, GET /api/v1/jobs/{id}만 흉내 낸다. states를 차례로 돌려준다."""

    def __init__(self, states):
        self.states, self.uploads, self.calls = list(states), [], 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                outer.uploads.append((self.path, self.headers.get("Content-Type"), self.rfile.read(int(self.headers["Content-Length"]))))
                self._send(202, {"job_id": "job_1", "doc_id": "doc_x", "status": "queued"})

            def do_GET(self):
                state = outer.states[min(outer.calls, len(outer.states) - 1)]
                outer.calls += 1
                self._send(200, state)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _job(status, done=0, total=2, **extra):
    base = {"job_id": "job_1", "doc_id": "doc_x", "status": status, "stage": None, "completed_pages": done,
            "total_pages": total, "result_ready": False, "result_dir": None, "error": None}
    return {**base, **extra}


def test_api_mode_copies_result_reports_progress_and_adapts_ocr(tmp_path):
    result = _make_result(tmp_path / "api_result")
    api = FakeApi([_job("queued", 0, None), _job("running", 1), _job("running", 2),
                   _job("succeeded", 2, result_ready=True, result_dir=str(result))])
    try:
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.7 test")
        seen = []
        meta = preprocess_v17(pdf, "D1", force=True, on_page=lambda p, t: seen.append((p, t)), pages_root=tmp_path / "pages",
                              extractor=api_extractor(api.url, poll=0, sleep=lambda s: None))
    finally:
        api.close()
    assert seen == [(1, 2), (2, 2)]
    assert meta["page_count"] == 2 and meta["text_layer"] == "혼합"
    assert api.uploads[0][0] == "/api/v1/documents" and b"%PDF-1.7 test" in api.uploads[0][2]
    assert api.uploads[0][1].startswith("multipart/form-data; boundary=")
    out = tmp_path / "pages" / "D1"
    assert (out / "p001.txt").read_text(encoding="utf-8") == TEXTS[1] and (out / "p002.png").is_file()
    assert (out / "p002.ocr_input.txt").read_text(encoding="utf-8") == TEXTS[2]     # OCR 쪽만 덧붙임
    assert not (out / "p001.ocr_input.txt").exists()
    assert (tmp_path / "api_result" / "meta.json").is_file()                          # 원본 결과 폴더는 그대로
    assert [p.name for p in (tmp_path / "pages").iterdir()] == ["D1"]                 # 임시 복사 폴더가 남지 않음


def test_api_mode_selected_by_env(tmp_path, monkeypatch):
    result = _make_result(tmp_path / "api_result")
    api = FakeApi([_job("succeeded", 2, result_ready=True, result_dir=str(result))])
    monkeypatch.setenv("MSDS_EXTRACTION_API_URL", api.url + "/")
    try:
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF")
        meta = preprocess_v17(pdf, "D1", force=True, pages_root=tmp_path / "pages")
    finally:
        api.close()
    assert meta["page_count"] == 2 and api.uploads and (tmp_path / "pages" / "D1" / "p001.txt").is_file()


@pytest.mark.parametrize("status,error", [("failed", "RuntimeError: boom"), ("recovery_required", None)])
def test_api_job_failure_is_raised(tmp_path, status, error):
    api = FakeApi([_job(status, 1, error=error)])
    try:
        (tmp_path / "in.pdf").write_bytes(b"%PDF")
        with pytest.raises(ExtractionApiError, match=status):
            preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path / "pages",
                           extractor=api_extractor(api.url, poll=0, sleep=lambda s: None))
    finally:
        api.close()
    assert not (tmp_path / "pages" / "D1").exists()


def test_api_unreachable_and_timeout(tmp_path):
    (tmp_path / "in.pdf").write_bytes(b"%PDF")
    with pytest.raises(ExtractionApiError, match="연결하지 못했습니다"):
        preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path / "pages",
                       extractor=api_extractor("http://127.0.0.1:9", poll=0, sleep=lambda s: None))
    api = FakeApi([_job("running", 0, None)])
    try:
        with pytest.raises(ExtractionApiError, match="끝나지 않았습니다"):
            preprocess_v17(tmp_path / "in.pdf", "D1", force=True, pages_root=tmp_path / "pages",
                           extractor=api_extractor(api.url, timeout=0.05, poll=0.01))
    finally:
        api.close()


def test_api_mode_refuses_foreign_or_nonempty_destination(tmp_path):
    (tmp_path / "in.pdf").write_bytes(b"%PDF")
    out = tmp_path / "pages" / "D1"
    out.mkdir(parents=True)
    (out / "p001.txt").write_text("옛 전처리 결과", encoding="utf-8")
    run = api_extractor("http://127.0.0.1:9")                         # 연결 전에 막아야 하므로 주소는 상관없다
    with pytest.raises(ValueError, match="not empty"):
        run(tmp_path / "in.pdf", out, doc_id="D1", force=False, on_progress=None)
    with pytest.raises(ValueError, match="historical"):
        run(tmp_path / "in.pdf", out, doc_id="D1", force=True, on_progress=None)
    assert (out / "p001.txt").read_text(encoding="utf-8") == "옛 전처리 결과"      # 지우지 않았다
