"""scripts/repeat_runs.py 시험. 모델을 부르지 않고 가짜 추출기로 실행 폴더를 만든다."""
import importlib
import json
import threading
import time
from pathlib import Path

import pytest

from test_B_compare_models import SCRIPTS

DOC = "T21-X001"


@pytest.fixture
def rr(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("repeat_runs")


def write_run(run: Path, doc: str, sections: dict[int, str], output: dict, tokens: int = 10):
    """raw/<doc>_m0_sNN.json(응답 원문)과 outputs/<doc>.json(펼친 TO21)을 쓴다."""
    (run / "raw").mkdir(parents=True, exist_ok=True)
    (run / "outputs").mkdir(parents=True, exist_ok=True)
    for no, text in sections.items():
        rec = {"doc_id": doc, "msds_index": 0, "section": no, "reextracted": False, "ok": True, "raw_text": text,
               "usage": {"completion_tokens": tokens}, "finish_reason": "stop"}
        (run / "raw" / f"{doc}_m0_s{no:02d}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    (run / "outputs" / f"{doc}.json").write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")


def doc_json(stamp: str, content: str = "20 %") -> dict:
    return {"doc": {"extraction": {"extracted_at": stamp}},
            "msds": [{"components": [{"cas": "7647-01-0", "content": {"raw": content}}]}]}


# ── 비교 ──

def test_identical_runs_are_reported_same_and_timestamp_ignored(rr, tmp_path):
    for i in (1, 2):
        write_run(tmp_path / f"r{i}", DOC, {1: "a", 15: "b"}, doc_json(f"2026-11-03T0{i}:00"))
    res = rr.compare_doc([tmp_path / "r1", tmp_path / "r2"], DOC)
    assert [s["same"] for s in res["sections"]] == [True, True]
    assert res["fields_diff"] == 0                                    # 추출 시각은 회차마다 달라 세지 않는다
    assert res["fields_total"] > 0


def test_different_section_shows_first_difference(rr, tmp_path):
    write_run(tmp_path / "r1", DOC, {1: "a", 15: "OSH | 해당 | 6 개월"}, doc_json("t1"))
    write_run(tmp_path / "r2", DOC, {1: "a", 15: "OSH | 해당 | 6 | 개월"}, doc_json("t2", "20%"))
    res = rr.compare_doc([tmp_path / "r1", tmp_path / "r2"], DOC)
    s15 = next(s for s in res["sections"] if s["section"] == 15)
    assert s15["same"] is False and "6 개월" in s15["first_diff"][0] and "6 | 개월" in s15["first_diff"][1]
    assert res["fields_diff"] == 1
    assert res["diff_examples"][0]["field"] == "msds[0].components[0].content.raw"
    assert res["diff_examples"][0]["values"] == ["20 %", "20%"]


def test_section_missing_in_one_run_counts_as_different(rr, tmp_path):
    write_run(tmp_path / "r1", DOC, {1: "a", 2: "b"}, doc_json("t"))
    write_run(tmp_path / "r2", DOC, {1: "a"}, doc_json("t"))
    res = rr.compare_doc([tmp_path / "r1", tmp_path / "r2"], DOC)
    s2 = next(s for s in res["sections"] if s["section"] == 2)
    assert s2["same"] is False and s2["missing"] == [False, True]


def test_failed_output_is_counted_not_crashing(rr, tmp_path):
    write_run(tmp_path / "r1", DOC, {1: "a"}, doc_json("t"))
    write_run(tmp_path / "r2", DOC, {1: "a"}, doc_json("t"))
    (tmp_path / "r2" / "outputs" / f"{DOC}.json").unlink()            # 문서 실패로 결과가 없는 회차
    res = rr.compare_doc([tmp_path / "r1", tmp_path / "r2"], DOC)
    assert res["outputs_missing"] == [False, True]


# ── 실행 ──

def fake_extract(texts: dict[int, str] | None = None, delay: float = 0.0, log: list | None = None):
    def extract(doc_id, model_tag, run_name, *, max_workers, pages_dir, sections_dir, runs_dir, **kw):
        if log is not None:
            log.append(("start", doc_id, run_name, max_workers, time.monotonic()))
        time.sleep(delay)
        write_run(Path(runs_dir) / run_name, doc_id, texts or {1: "a"}, doc_json(run_name))
        if log is not None:
            log.append(("end", doc_id, run_name, max_workers, time.monotonic()))
        return {"doc_id": doc_id, "seconds": delay, "sections_ok": 1, "sections_failed": 0, "reextracted": 0}
    return extract


def test_run_all_makes_one_folder_per_round_and_passes_concurrency(rr, tmp_path):
    log = []
    plan = rr.Plan(tag="t", docs=["A", "B"], rounds=2, concurrency=8, name="n", parallel_docs=False)
    out = rr.run_all(plan, runs_dir=tmp_path, pages_dir=tmp_path, sections_dir=tmp_path,
                     extract=fake_extract(log=log), save_info=lambda *a, **k: None)
    assert [r.name for r in out.run_dirs] == ["n_r1", "n_r2"]
    assert {e[3] for e in log} == {8}
    starts = [(e[1], e[2]) for e in log if e[0] == "start"]
    assert starts == [("A", "n_r1"), ("B", "n_r1"), ("A", "n_r2"), ("B", "n_r2")]
    assert out.seconds["A"] and len(out.seconds["A"]) == 2


def test_parallel_docs_overlap_in_time(rr, tmp_path):
    # N4: 여러 사용자가 함께 쓰는 상황. 문서 두 건을 동시에 보낸다
    log = []
    plan = rr.Plan(tag="t", docs=["A", "B"], rounds=1, concurrency=4, name="p", parallel_docs=True)
    rr.run_all(plan, runs_dir=tmp_path, pages_dir=tmp_path, sections_dir=tmp_path,
               extract=fake_extract(delay=0.2, log=log), save_info=lambda *a, **k: None)
    start_b = next(e[4] for e in log if e[0] == "start" and e[1] == "B")
    end_a = next(e[4] for e in log if e[0] == "end" and e[1] == "A")
    assert start_b < end_a


def test_extract_error_is_recorded_and_other_docs_continue(rr, tmp_path):
    ok = fake_extract()

    def extract(doc_id, *a, **kw):
        if doc_id == "A":
            raise RuntimeError("서버 응답 없음")
        return ok(doc_id, *a, **kw)
    plan = rr.Plan(tag="t", docs=["A", "B"], rounds=1, concurrency=1, name="e", parallel_docs=False)
    out = rr.run_all(plan, runs_dir=tmp_path, pages_dir=tmp_path, sections_dir=tmp_path, extract=extract,
                     save_info=lambda *a, **k: None)
    assert "서버 응답 없음" in out.errors[("A", "e_r1")]
    assert (tmp_path / "e_r1" / "outputs" / "B.json").is_file()


# ── 보고서 ──

def test_report_lists_sections_and_settings(rr, tmp_path):
    write_run(tmp_path / "n_r1", DOC, {1: "a", 15: "x"}, doc_json("t"))
    write_run(tmp_path / "n_r2", DOC, {1: "a", 15: "y"}, doc_json("t"))
    plan = rr.Plan(tag="qwen36_35b_runpod_48g_det", docs=[DOC], rounds=2, concurrency=8, name="n",
                   parallel_docs=False)
    out = rr.RunOutcome(run_dirs=[tmp_path / "n_r1", tmp_path / "n_r2"], seconds={DOC: [10.0, 12.0]}, errors={})
    path = rr.write_report(plan, out, tmp_path / "report", server={"batch_invariant": True}, gpu="RTX 6000 Ada")
    text = path.read_text(encoding="utf-8")
    assert "qwen36_35b_runpod_48g_det" in text and "batch_invariant" in text and "RTX 6000 Ada" in text
    assert "1/2" in text                                              # 같았던 항 수 / 전체 항 수
    assert "| 15 |" in text and "다름" in text
    result = json.loads((tmp_path / "report" / "repeat.json").read_text(encoding="utf-8"))
    assert result["docs"][DOC]["sections_same"] == 1
