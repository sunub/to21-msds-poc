"""기준선 실행기 run_baseline.py의 --skip-done (역할 B, ADR-006).

모델 서버를 부르지 않는다. 실행 폴더는 tmp_path로 바꾸고 extract_document는 가짜로 바꾼다.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_baseline  # noqa: E402
from msds.extract.prompt_builder import PROMPT_VERSION  # noqa: E402

RUN = "test_baseline_qwen38"


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(run_baseline, "run_dir", lambda run_name: tmp_path)
    return tmp_path


def write_output(run: Path, doc_id: str, doc: dict) -> None:
    p = run / "outputs" / f"{doc_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"doc": doc, "msds": []}, ensure_ascii=False), encoding="utf-8")


def engine_doc(version: str) -> dict:
    return {"extraction": {"engine": f"Qwen/Qwen3.8-27B-FP8 (baseline, prompt {version})",
                           "extracted_at": "2026-10-26T10:00:00+09:00"}}


def test_no_output_is_not_done(run):
    assert run_baseline.done_with_current_prompt(RUN, "T21-S016") is False


def test_same_prompt_version_is_done(run):
    write_output(run, "T21-S016", engine_doc(PROMPT_VERSION))
    assert run_baseline.done_with_current_prompt(RUN, "T21-S016") is True


def test_other_prompt_version_is_not_done(run):
    write_output(run, "T21-S016", engine_doc(PROMPT_VERSION + "x"))
    assert run_baseline.done_with_current_prompt(RUN, "T21-S016") is False


@pytest.mark.parametrize("data", [
    {"msds": []},                                    # doc 없음
    {"doc": {}, "msds": []},                         # extraction 없음
    {"doc": {"extraction": {}}, "msds": []},         # engine 없음
])
def test_missing_engine_is_not_done(run, data):
    p = run / "outputs" / "T21-S016.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    assert run_baseline.done_with_current_prompt(RUN, "T21-S016") is False


@pytest.fixture
def calls(run, monkeypatch):
    """extract_document 호출을 기록만 한다. T21-S016은 이미 끝난 문서로 둔다."""
    called = []

    def fake_extract(doc_id, model_tag, mode, run_name, bundle_ids=None):
        called.append(doc_id)
        return {"doc_id": doc_id}

    monkeypatch.setattr(run_baseline, "extract_document", fake_extract)
    monkeypatch.setattr(run_baseline, "save_run_config", lambda *a, **k: None)
    write_output(run, "T21-S016", engine_doc(PROMPT_VERSION))
    return called


DOCS = ["--docs", "T21-S016", "T21-M013", "--run-name", RUN]


def test_skip_done_skips_finished_doc(calls, capsys):
    run_baseline.main(DOCS + ["--skip-done"])
    assert calls == ["T21-M013"]
    out = capsys.readouterr().out
    assert f"[건너뜀] T21-S016: 같은 프롬프트({PROMPT_VERSION}) 결과가 있음" in out
    assert f"기록: runs/{RUN}/log.jsonl" in out


def test_skip_done_with_bundles_runs_all(calls):
    run_baseline.main(DOCS + ["--skip-done", "--bundles", "b1"])
    assert sorted(calls) == ["T21-M013", "T21-S016"]


def test_without_skip_done_runs_all(calls):
    run_baseline.main(DOCS)
    assert sorted(calls) == ["T21-M013", "T21-S016"]
