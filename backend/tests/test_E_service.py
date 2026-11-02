"""msds.service 시험: 진행 상태(progress), 상태 저장소(store), 파이프라인(pipeline).

모델·OCR·저장소의 data/를 쓰지 않는다. 파이프라인은 단계 함수를 가짜로 바꿔 끼워 시험한다.
"""
import json
import threading
from pathlib import Path

import pytest

from msds.service import pipeline, progress
from msds.service.store import DocumentStore

PDF = b"%PDF-1.7\n% fake\n"


def plan_event(sections=((0, 1, [1]), (0, 2, [1, 2]), (0, 3, [2]))) -> dict:
    return {"type": "plan", "msds_count": 1, "page_count": 2,
            "sections": [{"msds_index": m, "section": n, "title": f"제목 {n}", "pages": p} for m, n, p in sections]}


def fresh() -> dict:
    return progress.new_state("U-20261101-001", "a.pdf", "abc", 10, "2026-10-31", "qwen36_35b_runpod",
                              "2026-11-01T10:00:00+09:00")


# ── progress ──────────────────────────────────────────

def test_new_state_is_queued_without_sections():
    v = progress.view(fresh())
    assert v["status"] == "queued" and v["stage"] is None and v["stage_index"] == 0
    assert v["counts"] == {"total": 0, "queued": 0, "running": 0, "done": 0, "failed": 0, "needs_review": 0}


def test_preprocess_pages_update_page_count_and_progress():
    s = fresh()
    for e in ({"type": "started"}, {"type": "page", "page": 1, "total": 3}, {"type": "page", "page": 2, "total": 3}):
        progress.apply_event(s, e)
    v = progress.view(s)
    assert v["status"] == "running" and v["stage"] == "preprocess" and v["stage_index"] == 1
    assert v["page_count"] == 3 and v["preprocess"] == {"done": 2, "total": 3}


def test_preprocess_done_warns_on_untrusted_text_layer():
    s = fresh()
    progress.apply_event(s, {"type": "preprocess_done", "page_count": 2, "text_layer": "글꼴깨짐"})
    assert s["text_layer"] == "글꼴깨짐" and s["preprocess"] == {"done": 2, "total": 2}
    assert any("글꼴깨짐" in w for w in s["warnings"])
    t = fresh()
    progress.apply_event(t, {"type": "preprocess_done", "page_count": 2, "text_layer": "정상"})
    assert t["warnings"] == []


def test_plan_then_section_events_drive_counts():
    s = fresh()
    progress.apply_event(s, {"type": "stage", "stage": "extract"})
    progress.apply_event(s, plan_event())
    progress.apply_event(s, {"type": "section_started", "msds_index": 0, "section": 1})
    progress.apply_event(s, {"type": "section_started", "msds_index": 0, "section": 2})
    progress.apply_event(s, {"type": "section_done", "msds_index": 0, "section": 1, "ok": True,
                             "reextracted": True, "needs_review": False, "seconds": 3.2, "errors": []})
    progress.apply_event(s, {"type": "section_done", "msds_index": 0, "section": 2, "ok": False,
                             "reextracted": False, "needs_review": True, "seconds": 9.0,
                             "errors": ["a", "b", "c", "d", "e"]})
    v = progress.view(s)
    assert v["stage_index"] == 3 and v["msds_count"] == 1
    assert v["counts"] == {"total": 3, "queued": 1, "running": 0, "done": 1, "failed": 1, "needs_review": 1}
    one, two, three = v["sections"]
    assert one["status"] == "done" and one["reextracted"] and one["pages"] == [1] and one["title"] == "제목 1"
    assert two["status"] == "failed" and two["needs_review"] and len(two["errors"]) == progress.ERRORS_KEPT
    assert three["status"] == "queued" and three["seconds"] is None


def test_finalize_done_and_failed():
    s = fresh()
    progress.apply_event(s, {"type": "finalize"})
    assert progress.view(s)["stage_index"] == 4
    progress.apply_event(s, {"type": "done", "summary": {"sections_ok": 16}})
    assert s["status"] == "done" and s["stage"] == "done" and s["summary"] == {"sections_ok": 16}
    t = fresh()
    progress.apply_event(t, {"type": "failed", "error": "ValueError: 깨짐"})
    assert t["status"] == "failed" and t["error"] == "ValueError: 깨짐"


def test_requeue_clears_run_but_keeps_upload():
    s = fresh()
    progress.apply_event(s, plan_event())
    progress.apply_event(s, {"type": "failed", "error": "x"})
    progress.apply_event(s, {"type": "queued"})
    assert s["status"] == "queued" and s["error"] is None and s["sections"] == [] and s["filename"] == "a.pdf"


def test_unknown_event_is_rejected():
    with pytest.raises(ValueError):
        progress.apply_event(fresh(), {"type": "nope"})


# ── store ─────────────────────────────────────────────

def test_create_saves_pdf_and_state(tmp_path):
    st = DocumentStore(tmp_path)
    doc = st.create(PDF, "젯소.pdf", "2026-10-31", "qwen36_35b_runpod", today="20261101")
    assert doc["id"] == "U-20261101-001" and doc["status"] == "queued" and doc["filename"] == "젯소.pdf"
    assert st.pdf_path(doc["id"]).read_bytes() == PDF
    saved = json.loads((tmp_path / doc["id"] / "state.json").read_text(encoding="utf-8"))
    assert saved["sha256"] == doc["sha256"] and saved["size"] == len(PDF)


def test_ids_increase_per_day_and_survive_reload(tmp_path):
    st = DocumentStore(tmp_path)
    a = st.create(PDF, "a.pdf", None, "m", today="20261101")
    b = st.create(PDF + b"x", "b.pdf", None, "m", today="20261101")
    assert (a["id"], b["id"]) == ("U-20261101-001", "U-20261101-002")
    again = DocumentStore(tmp_path)
    assert again.create(PDF, "c.pdf", None, "m", today="20261101")["id"] == "U-20261101-003"
    assert again.create(PDF, "d.pdf", None, "m", today="20261102")["id"] == "U-20261102-001"


def test_same_pdf_records_duplicate_of(tmp_path):
    st = DocumentStore(tmp_path)
    a = st.create(PDF, "a.pdf", None, "m", today="20261101")
    b = st.create(PDF, "a2.pdf", None, "m", today="20261101")
    assert a["duplicate_of"] == [] and b["duplicate_of"] == [a["id"]]


def test_apply_persists_and_list_is_newest_first(tmp_path):
    st = DocumentStore(tmp_path)
    a = st.create(PDF, "a.pdf", None, "m", today="20261101")
    b = st.create(PDF + b"1", "b.pdf", None, "m", today="20261101")
    st.apply(a["id"], {"type": "started"})
    assert DocumentStore(tmp_path).get(a["id"])["status"] == "running"
    assert [d["id"] for d in st.list()] == [b["id"], a["id"]]
    assert st.get("U-없음") is None


def test_apply_is_thread_safe(tmp_path):
    st = DocumentStore(tmp_path)
    doc = st.create(PDF, "a.pdf", None, "m", today="20261101")
    st.apply(doc["id"], plan_event(tuple((0, n, [1]) for n in range(1, 17))))

    def finish(n):
        st.apply(doc["id"], {"type": "section_done", "msds_index": 0, "section": n, "ok": True,
                             "reextracted": False, "needs_review": False, "seconds": 1.0, "errors": []})

    threads = [threading.Thread(target=finish, args=(n,)) for n in range(1, 17)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert progress.view(DocumentStore(tmp_path).get(doc["id"]))["counts"]["done"] == 16


def test_recover_marks_running_interrupted_and_returns_queued(tmp_path):
    st = DocumentStore(tmp_path)
    a = st.create(PDF, "a.pdf", None, "m", today="20261101")
    b = st.create(PDF + b"1", "b.pdf", None, "m", today="20261101")
    st.apply(a["id"], {"type": "started"})
    again = DocumentStore(tmp_path)
    assert again.recover() == [b["id"]]
    assert again.get(a["id"])["status"] == "interrupted"


# ── pipeline ──────────────────────────────────────────

class FakeSteps:
    """단계 함수를 흉내 낸다. 무엇을 어떤 인자로 불렀는지 calls에 남긴다."""

    def __init__(self, fail_at: str | None = None, text_layer: str = "정상"):
        self.calls: list[tuple] = []
        self.fail_at = fail_at
        self.text_layer = text_layer

    def _maybe_fail(self, name):
        if self.fail_at == name:
            raise RuntimeError(f"{name} 실패")

    def preprocess(self, pdf_path, doc_id, force=False, on_page=None):
        self.calls.append(("preprocess", Path(pdf_path).name, doc_id, force))
        for i in (1, 2):
            on_page(i, 2)
        self._maybe_fail("preprocess")
        return {"page_count": 2, "text_layer": self.text_layer}

    def sections(self, doc_id, pages_dir, sections_dir):
        self.calls.append(("sections", doc_id))
        self._maybe_fail("sections")
        return {"found": 16, "msds": 1}

    def save_run_info(self, run, model_tag, pages_dir):
        self.calls.append(("save_run_info", Path(run).name, model_tag))

    def extract(self, doc_id, model_tag, run_name, *, pages_dir, sections_dir, runs_dir, on_event):
        self.calls.append(("extract", doc_id, model_tag, run_name))
        on_event(plan_event())
        for n in (1, 2, 3):
            on_event({"type": "section_started", "msds_index": 0, "section": n})
            on_event({"type": "section_done", "msds_index": 0, "section": n, "ok": True, "reextracted": False,
                      "needs_review": n == 3, "seconds": 1.0, "errors": []})
        self._maybe_fail("extract")
        on_event({"type": "finalize"})
        return {"doc_id": doc_id, "seconds": 3.0, "sections_ok": 3, "sections_failed": 0, "reextracted": 0,
                "schema_errors": 0, "warnings": ["w"]}


@pytest.fixture
def svc(tmp_path):
    st = DocumentStore(tmp_path / "service")
    doc = st.create(PDF, "a.pdf", "2026-10-31", "qwen36_35b_runpod", today="20261101")
    return st, doc["id"]


def run_pipeline(svc, steps):
    st, doc_id = svc
    events = []
    orig = st.apply

    def spy(i, e):
        events.append(e["type"])
        return orig(i, e)

    st.apply = spy
    pipeline.process(st, doc_id, steps=steps, pages_dir=Path("/pages"))
    return st.get(doc_id), events


def test_pipeline_runs_four_stages_in_order(svc):
    steps = FakeSteps()
    state, events = run_pipeline(svc, steps)
    assert [c[0] for c in steps.calls] == ["preprocess", "sections", "save_run_info", "extract"]
    assert steps.calls[0] == ("preprocess", "source.pdf", svc[1], True)
    assert steps.calls[3] == ("extract", svc[1], "qwen36_35b_runpod", svc[1])
    assert events[:3] == ["started", "page", "page"]
    assert events.index("preprocess_done") < events.index("plan") < events.index("finalize") < events.index("done")
    assert state["status"] == "done" and state["stage"] == "done"
    assert state["summary"]["sections_ok"] == 3 and state["warnings"] == ["w"]
    assert progress.view(state)["counts"]["needs_review"] == 1


@pytest.mark.parametrize("where", ["preprocess", "sections", "extract"])
def test_pipeline_failure_is_recorded_not_raised(svc, where):
    state, _ = run_pipeline(svc, FakeSteps(fail_at=where))
    assert state["status"] == "failed" and f"{where} 실패" in state["error"]


def test_pipeline_default_model_is_runpod():
    assert pipeline.DEFAULT_MODEL_TAG == "qwen36_35b_runpod"


def test_write_sections_writes_file_when_headings_found(tmp_path):
    pages = tmp_path / "pages" / "U-1"
    pages.mkdir(parents=True)
    (pages / "p001.txt").write_text("1. 화학제품과 회사에 관한 정보\n제품명 : 가상\n2. 유해성·위험성\n분류 : 해당\n",
                                    encoding="utf-8")
    stats = pipeline.write_sections("U-1", tmp_path / "pages", tmp_path / "sections")
    assert stats["found"] >= 1
    data = json.loads((tmp_path / "sections" / "U-1.json").read_text(encoding="utf-8"))
    assert data["msds"][0]["sections"]["1"]["start"] == "p1:L1"


def test_write_sections_skips_file_without_headings(tmp_path):
    pages = tmp_path / "pages" / "U-2"
    pages.mkdir(parents=True)
    (pages / "p001.txt").write_text("제목 없는 글\n", encoding="utf-8")
    assert pipeline.write_sections("U-2", tmp_path / "pages", tmp_path / "sections")["found"] == 0
    assert not (tmp_path / "sections" / "U-2.json").exists()


def test_ids_skip_names_taken_in_other_folders(tmp_path):
    pages = tmp_path / "pages"
    (pages / "U-20261101-001").mkdir(parents=True)   # 지운 저장소가 남긴 쪽 폴더
    st = DocumentStore(tmp_path / "service", taken_dirs=[pages])
    assert st.create(PDF, "a.pdf", None, "m", today="20261101")["id"] == "U-20261101-002"
