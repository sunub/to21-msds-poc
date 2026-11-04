"""api/extract_app.py 시험. 작업자는 가짜(대기열에 넣은 번호만 기록)이고 모델을 부르지 않는다."""
import json
import threading

import pytest
from fastapi.testclient import TestClient

from msds.api import extract_app
from msds.api.routers.extract import jobs as jobs_router
from msds.api.routers.extract import regenerated as regen_router
from msds.api.routers.extract import storage as storage_router
from msds.service import pipeline
from msds.service.store import DocumentStore
from msds.service.worker import Worker

PDF = b"%PDF-1.7\n% fake\n"


class FakeWorker:
    def __init__(self):
        self.submitted: list[str] = []
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def submit(self, doc_id):
        self.submitted.append(doc_id)

    def stop(self, timeout=None):
        self.stopped = True


@pytest.fixture
def ctx(tmp_path):
    store = DocumentStore(tmp_path / "service")
    worker = FakeWorker()
    app = extract_app.create_app(store=store, worker=worker, pages_dir=tmp_path / "pages")
    with TestClient(app) as client:
        yield client, store, worker, tmp_path


def upload(client, body=PDF, **params):
    params = {"filename": "젯소.pdf", **params}
    return client.post("/api/documents", params=params, content=body, headers={"Content-Type": "application/pdf"})


def test_health(ctx):
    client, *_ = ctx
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["model_tag"] == "qwen36_35b_runpod"


def test_upload_creates_queued_document_and_submits(ctx):
    client, store, worker, _ = ctx
    r = upload(client, as_of="2026-10-31")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["filename"] == "젯소.pdf" and body["as_of"] == "2026-10-31"
    assert body["model_tag"] == "qwen36_35b_runpod" and body["sections"] == []
    assert worker.submitted == [body["id"]]
    assert store.pdf_path(body["id"]).read_bytes() == PDF
    assert "sha256" not in body


@pytest.mark.parametrize("params,body,code", [
    ({}, b"not a pdf", 400),
    ({"as_of": "2026/10/31"}, PDF, 422),
    ({"filename": ""}, PDF, 422),
    ({"filename": "a.txt"}, PDF, 400),
])
def test_upload_rejects_bad_input(ctx, params, body, code):
    client, _, worker, _ = ctx
    assert upload(client, body, **params).status_code == code
    assert worker.submitted == []


def test_upload_too_large(ctx, monkeypatch):
    client, *_ = ctx
    monkeypatch.setattr(jobs_router, "MAX_PDF_BYTES", 10)
    assert upload(client).status_code == 413


def test_filename_keeps_only_base_name(ctx):
    client, *_ = ctx
    assert upload(client, filename="../../etc/젯소.pdf").json()["filename"] == "젯소.pdf"


def test_list_filters_and_counts(ctx):
    client, store, *_ = ctx
    a = upload(client).json()["id"]
    b = upload(client, PDF + b"1").json()["id"]
    c = upload(client, PDF + b"2").json()["id"]
    store.apply(a, {"type": "done", "summary": {}})
    store.apply(b, {"type": "started"})
    store.apply(c, {"type": "failed", "error": "x"})
    r = client.get("/api/documents").json()
    assert [d["id"] for d in r["items"]] == [c, b, a]
    assert r["counts"] == {"all": 3, "active": 1, "done": 1, "failed": 1}
    assert "sections" not in r["items"][0] and "counts" in r["items"][0]
    assert [d["id"] for d in client.get("/api/documents", params={"status": "active"}).json()["items"]] == [b]
    assert [d["id"] for d in client.get("/api/documents", params={"status": "done"}).json()["items"]] == [a]
    assert client.get("/api/documents", params={"status": "nope"}).status_code == 422


def test_detail_has_sections_and_404(ctx):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    store.apply(doc, {"type": "plan", "msds_count": 1, "page_count": 1,
                      "sections": [{"msds_index": 0, "section": 1, "title": "t", "pages": [1]}]})
    r = client.get(f"/api/documents/{doc}").json()
    assert r["sections"][0]["status"] == "queued" and r["counts"]["total"] == 1
    assert client.get("/api/documents/U-20990101-001").status_code == 404


def test_source_pdf_is_served_inline(ctx):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    r = client.get(f"/api/documents/{doc}/pdf")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    store.pdf_path(doc).unlink()
    assert client.get(f"/api/documents/{doc}/pdf").status_code == 404
    assert client.get("/api/documents/U-20990101-001/pdf").status_code == 404


def test_page_image_and_lines(ctx):
    client, _, _, tmp = ctx
    doc = upload(client).json()["id"]
    assert client.get(f"/api/documents/{doc}/pages/1/image").status_code == 404   # 전처리 전
    folder = tmp / "pages" / doc
    folder.mkdir(parents=True)
    (folder / "p001.png").write_bytes(b"\x89PNG fake")
    (folder / "p001.txt").write_text("제품명 : 가상\n\n제조자 : 가상화학\n", encoding="utf-8")
    (folder / "p002.txt").write_text("L7 다음 쪽\n", encoding="utf-8")
    img = client.get(f"/api/documents/{doc}/pages/1/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    lines = client.get(f"/api/documents/{doc}/pages/1/lines").json()
    assert lines == {"page": 1, "lines": [{"id": "p1:L1", "no": 1, "text": "제품명 : 가상"},
                                          {"id": "p1:L2", "no": 2, "text": "제조자 : 가상화학"}]}
    assert client.get(f"/api/documents/{doc}/pages/2/lines").json()["lines"][0]["id"] == "p2:L7"
    assert client.get(f"/api/documents/{doc}/pages/3/lines").status_code == 404
    assert client.get(f"/api/documents/{doc}/pages/0/lines").status_code == 422


def test_result_conflict_until_done_then_returns_to21_and_review(ctx):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    assert client.get(f"/api/documents/{doc}/result").status_code == 409
    out, checks = pipeline.result_paths(store, doc)
    out.parent.mkdir(parents=True)
    checks.parent.mkdir(parents=True)
    out.write_text(json.dumps({"doc": {"doc_id": doc}, "msds": []}), encoding="utf-8")
    checks.write_text(json.dumps({"needs_review": [{"msds_index": 0, "section": 2}], "warnings": ["w"],
                                  "schema_errors": [], "to21_validator": []}), encoding="utf-8")
    store.apply(doc, {"type": "done", "summary": {}})
    r = client.get(f"/api/documents/{doc}/result").json()
    assert r["to21"]["doc"]["doc_id"] == doc
    assert r["needs_review"] == [{"msds_index": 0, "section": 2}] and r["warnings"] == ["w"]


def plan(store, doc):
    store.apply(doc, {"type": "plan", "msds_count": 1, "page_count": 2, "sections": [
        {"msds_index": 0, "section": 1, "title": "회사 정보", "pages": [1]},
        {"msds_index": 0, "section": 2, "title": "유해성", "pages": [1, 2]}]})


def section_done(store, doc, no, ok=True, **raw):
    path = pipeline.section_raw_path(store, doc, 0, no)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ok": ok, "parsed": {"칸": no}, "raw_text": "비공개 응답", "mode": "json_schema",
                                "usage": {"prompt_tokens": 1}, "requests": [{"x": 1}], "errors": ["오류"] * 5,
                                "check_problems": ["문제"], **raw}), encoding="utf-8")
    store.apply(doc, {"type": "section_done", "msds_index": 0, "section": no, "ok": ok, "reextracted": True,
                      "needs_review": not ok, "seconds": 2.5, "errors": ["오류"] * 5})


def test_section_result_available_while_document_is_running(ctx):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    store.apply(doc, {"type": "started"})
    plan(store, doc)
    section_done(store, doc, 1)
    r = client.get(f"/api/documents/{doc}/sections/0/1")
    assert r.status_code == 200
    assert r.json() == {"msds_index": 0, "section": 1, "title": "회사 정보", "pages": [1], "status": "done",
                        "needs_review": False, "reextracted": True, "seconds": 2.5, "errors": ["오류"] * 5,
                        "check_problems": ["문제"], "parsed": {"칸": 1}}
    assert client.get(f"/api/documents/{doc}/result").status_code == 409


def test_section_result_conflict_until_section_ends(ctx):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    plan(store, doc)
    assert client.get(f"/api/documents/{doc}/sections/0/2").status_code == 409
    store.apply(doc, {"type": "section_started", "msds_index": 0, "section": 2})
    assert client.get(f"/api/documents/{doc}/sections/0/2").status_code == 409


def test_section_result_failed_section_has_no_value(ctx):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    plan(store, doc)
    section_done(store, doc, 2, ok=False)
    body = client.get(f"/api/documents/{doc}/sections/0/2").json()
    assert body["status"] == "failed" and body["parsed"] is None and body["needs_review"] is True


@pytest.mark.parametrize("path,code", [("0/3", 404), ("1/1", 404), ("0/17", 422), ("0/0", 422), ("-1/1", 422)])
def test_section_result_bad_address(ctx, path, code):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    plan(store, doc)
    assert client.get(f"/api/documents/{doc}/sections/{path}").status_code == code


def test_section_result_404_for_missing_document_or_file(ctx):
    client, store, *_ = ctx
    assert client.get("/api/documents/U-20990101-001/sections/0/1").status_code == 404
    doc = upload(client).json()["id"]
    plan(store, doc)
    store.apply(doc, {"type": "section_done", "msds_index": 0, "section": 1, "ok": True, "reextracted": False,
                      "needs_review": False, "seconds": 1, "errors": []})
    assert client.get(f"/api/documents/{doc}/sections/0/1").status_code == 404


def test_section_result_old_run_file_is_hidden_after_retry(ctx):
    """다시 돌리면 이전 실행의 파일이 남아 있어도 그 항이 다시 끝나기 전에는 내주지 않는다."""
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    plan(store, doc)
    section_done(store, doc, 1)
    store.apply(doc, {"type": "failed", "error": "x"})
    assert client.post(f"/api/documents/{doc}/retry").status_code == 202
    assert client.get(f"/api/documents/{doc}/sections/0/1").status_code == 404
    plan(store, doc)
    assert client.get(f"/api/documents/{doc}/sections/0/1").status_code == 409


def regen_ctx(store, doc):
    plan(store, doc)
    out, checks = pipeline.result_paths(store, doc)
    out.parent.mkdir(parents=True)
    checks.parent.mkdir(parents=True)
    out.write_text(json.dumps({"doc": {"doc_id": doc}, "msds": [{}]}), encoding="utf-8")
    checks.write_text(json.dumps({"needs_review": [{"msds_index": 0, "section": 2}]}), encoding="utf-8")
    store.apply(doc, {"type": "section_done", "msds_index": 0, "section": 1, "ok": True, "reextracted": False,
                      "needs_review": False, "seconds": 1, "errors": []})
    store.apply(doc, {"type": "section_done", "msds_index": 0, "section": 2, "ok": False, "reextracted": False,
                      "needs_review": False, "seconds": 1, "errors": []})


def test_regenerated_conflict_until_done_then_joins_status_and_final_review(ctx, monkeypatch):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    regen_ctx(store, doc)
    assert client.get(f"/api/documents/{doc}/regenerated").status_code == 409
    store.apply(doc, {"type": "done", "summary": {}})
    monkeypatch.setattr(regen_router, "load_regen", lambda: None)
    monkeypatch.setattr(regen_router.regenerated, "regenerate_sections", lambda d, mod: [
        {"msds_index": 0, "header": ["머리"], "sections": [
            {"section": 1, "title": "회사", "lines": [{"kind": "item", "text": "젯소"}]},
            {"section": 2, "title": "유해성", "lines": []}]}])
    r = client.get(f"/api/documents/{doc}/regenerated")
    assert r.status_code == 200
    assert r.json() == {"msds": [{"msds_index": 0, "header": ["머리"], "sections": [
        {"section": 1, "title": "회사", "status": "done", "needs_review": False,
         "lines": [{"kind": "item", "text": "젯소"}]},
        {"section": 2, "title": "유해성", "status": "failed", "needs_review": True, "lines": []}]}]}


def test_regenerated_can_use_original_or_reviewed_extraction(ctx, monkeypatch):
    client, store, *_ = ctx
    doc_id = upload(client).json()['id']
    regen_ctx(store, doc_id)
    out, _ = pipeline.result_paths(store, doc_id)
    source = {'doc': {'doc_id': doc_id}, 'msds': [{'product': {'name': '원본'}}]}
    out.write_text(json.dumps(source), encoding='utf-8')
    store.apply(doc_id, {'type': 'done', 'summary': {}})
    store.update_review(doc_id, lambda record: regen_router.review.set_field(
        record, source, 0, 'product.name', 'edit', '수정', '검토자', '2026-11-03T12:00:00+09:00'))
    monkeypatch.setattr(regen_router, 'load_regen', lambda: None)
    monkeypatch.setattr(regen_router.regenerated, 'regenerate_sections', lambda doc, mod: [
        {'msds_index': 0, 'header': [], 'sections': [{'section': 1, 'title': '제품',
         'lines': [{'text': doc['msds'][0]['product']['name']}]}]},
    ])
    url = f'/api/documents/{doc_id}/regenerated'
    assert client.get(url, params={'source': 'original'}).json()['msds'][0]['sections'][0]['lines'][0]['text'] == '원본'
    assert client.get(url).json()['msds'][0]['sections'][0]['lines'][0]['text'] == '수정'


def test_regenerated_404_without_result_file_or_document(ctx):
    client, store, *_ = ctx
    assert client.get("/api/documents/U-20990101-001/regenerated").status_code == 404
    doc = upload(client).json()["id"]
    store.apply(doc, {"type": "done", "summary": {}})
    assert client.get(f"/api/documents/{doc}/regenerated").status_code == 404


def test_regenerated_reports_failure_of_provided_script(ctx, monkeypatch):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    regen_ctx(store, doc)
    store.apply(doc, {"type": "done", "summary": {}})

    def boom():
        raise KeyError("product_uses")

    monkeypatch.setattr(regen_router, "load_regen", boom)
    r = client.get(f"/api/documents/{doc}/regenerated")
    detail = r.json()["detail"]
    assert r.status_code == 500 and "재생성하지 못했습니다" in detail and "KeyError" in detail
    assert doc in detail and "개발 담당" in detail                       # 무슨 일인지와 누구에게 무엇을 알릴지


def test_retry_only_failed_or_interrupted(ctx):
    client, store, worker, _ = ctx
    doc = upload(client).json()["id"]
    assert client.post(f"/api/documents/{doc}/retry").status_code == 409   # 대기 중
    store.apply(doc, {"type": "failed", "error": "x"})
    r = client.post(f"/api/documents/{doc}/retry")
    assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["error"] is None
    assert worker.submitted == [doc, doc]


def test_retry_allows_done_document_with_failed_section(ctx):
    client, store, worker, _ = ctx
    doc = upload(client).json()["id"]
    plan(store, doc)
    section_done(store, doc, 1, ok=False)
    section_done(store, doc, 2)
    store.apply(doc, {"type": "done", "summary": {}})
    assert client.get(f"/api/documents/{doc}").json()["can_retry"] is True
    r = client.post(f"/api/documents/{doc}/retry")
    assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["can_retry"] is False
    assert worker.submitted.count(doc) == 2


def test_retry_rejects_done_document_without_failed_section(ctx):
    client, store, *_ = ctx
    doc = upload(client).json()["id"]
    plan(store, doc)
    section_done(store, doc, 1)
    store.apply(doc, {"type": "done", "summary": {}})
    assert client.get(f"/api/documents/{doc}").json()["can_retry"] is False
    assert client.post(f"/api/documents/{doc}/retry").status_code == 409


def test_concurrent_retry_submits_only_once(ctx):
    """두 탭에서 동시에 눌러도 작업은 하나만 들어간다 (모델 비용이 두 번 나가지 않게)."""
    client, store, worker, _ = ctx
    doc = upload(client).json()["id"]
    store.apply(doc, {"type": "failed", "error": "x"})
    worker.submitted.clear()
    n = 16
    barrier = threading.Barrier(n)
    got: list = []

    def go():
        barrier.wait()
        got.append(store.requeue(doc))

    threads = [threading.Thread(target=go) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(g is not None for g in got) == 1


def test_startup_recovers_and_resubmits(tmp_path):
    store = DocumentStore(tmp_path / "service")
    a = store.create(PDF, "a.pdf", None, "m")["id"]
    b = store.create(PDF + b"1", "b.pdf", None, "m")["id"]
    store.apply(a, {"type": "started"})
    worker = FakeWorker()
    with TestClient(extract_app.create_app(store=store, worker=worker, pages_dir=tmp_path / "pages")):
        assert worker.started and worker.submitted == [b]
    assert worker.stopped and store.get(a)["status"] == "interrupted"


def test_real_worker_runs_pipeline_in_background(tmp_path):
    store = DocumentStore(tmp_path / "service")
    done = threading.Event()

    def process(st, doc_id):
        st.apply(doc_id, {"type": "started"})
        st.apply(doc_id, {"type": "done", "summary": {}})
        done.set()

    app = extract_app.create_app(store=store, worker=Worker(store, process), pages_dir=tmp_path / "pages")
    with TestClient(app) as client:
        doc = upload(client).json()["id"]
        assert done.wait(5)
        assert client.get(f"/api/documents/{doc}").json()["status"] == "done"


def test_to_judgment_needs_reviewer(ctx):
    client, *_ = ctx
    doc_id = upload(client).json()["id"]
    assert client.post(f"/api/documents/{doc_id}/to-judgment", json={}).status_code == 422
    assert client.post(f"/api/documents/{doc_id}/to-judgment", json={"reviewer": "  "}).status_code == 422


def test_to_judgment_unknown_document(ctx):
    client, *_ = ctx
    assert client.post("/api/documents/nope/to-judgment", json={"reviewer": "홍길동"}).status_code == 404


def test_to_judgment_requires_postgres_store(ctx):
    client, *_ = ctx
    doc_id = upload(client).json()["id"]
    r = client.post(f"/api/documents/{doc_id}/to-judgment", json={"reviewer": "홍길동"})
    assert r.status_code == 409


def test_to_judgment_publishes_values_reviewed_handoff(ctx, monkeypatch):
    client, store, *_ = ctx
    doc_id = upload(client).json()["id"]
    store.dsn, store.schema = "postgresql://unused", "extract"
    saved = {"extraction": {"doc": {"extraction": {"extracted_at": "2026-11-03T09:00:00+09:00"}}}}
    monkeypatch.setattr(storage_router.ResultStore, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(storage_router.ResultStore, "get_active", lambda self, job_id: saved)
    calls = []

    def publish(store_, job_id, **kwargs):
        calls.append((job_id, kwargs["reason"]))
        return {"handoff_seq": 2, "as_of": kwargs["as_of"]}

    monkeypatch.setattr(storage_router, "publish_handoff", publish)
    r = client.post(f"/api/documents/{doc_id}/to-judgment", json={"reviewer": "홍길동"})
    assert r.status_code == 201 and r.json() == {"job_id": doc_id, "handoff_seq": 2}
    assert calls == [(doc_id, "values_reviewed")]
