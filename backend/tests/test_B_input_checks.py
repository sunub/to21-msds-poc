"""실행·채점 전 입력 검사 시험: 원본 찾기, 쪽 글자 줄번호, 평가 문서 빠짐. 모델을 부르지 않는다."""
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from msds.common import manifest, paths
from msds.extract.inputs import pages_problems

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROW = {"doc_id": "T21-X50", "source_file": "가상 원본.pdf"}


def write_page(pages: Path, doc: str, name: str, text: str):
    (pages / doc).mkdir(parents=True, exist_ok=True)
    (pages / doc / name).write_text(text, encoding="utf-8")


# ── 원본 찾기 ──

def test_raw_pdf_found_in_subfolder(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "RAW", tmp_path)
    pdf = tmp_path / "받은 폴더" / "가상 원본.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"x")
    assert manifest.raw_pdf(ROW) == pdf


def test_raw_pdf_prefers_top_level_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "RAW", tmp_path)
    (tmp_path / "가" ).mkdir()
    (tmp_path / "가" / "가상 원본.pdf").write_bytes(b"x")
    (tmp_path / "가상 원본.pdf").write_bytes(b"x")
    assert manifest.raw_pdf(ROW) == tmp_path / "가상 원본.pdf"


def test_raw_pdf_missing_still_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "RAW", tmp_path)
    with pytest.raises(FileNotFoundError, match="T21-X50"):
        manifest.raw_pdf(ROW)


# ── 쪽 글자 ──

def test_numbered_pages_pass_and_blank_page_is_allowed(tmp_path):
    write_page(tmp_path, "T21-X01", "p001.txt", "L001 글\nL002 글\n")
    write_page(tmp_path, "T21-X01", "p002.txt", "\n")                 # 로고만 있는 빈 쪽
    assert pages_problems(["T21-X01"], tmp_path) == []


def test_missing_folder_and_unnumbered_pages_are_reported(tmp_path):
    write_page(tmp_path, "T21-X02", "p001.txt", "L001 글\n")
    write_page(tmp_path, "T21-X02", "p002.txt", "번호 없는 글\n")       # 한 쪽만 달라도 잡는다
    write_page(tmp_path, "T21-X03", "p001.txt", "\n")                 # 글이 한 줄도 없다
    assert pages_problems(["T21-X02", "T21-X03", "T21-X04"], tmp_path) == [
        "T21-X02: 줄번호 없는 쪽 글자", "T21-X03: 줄번호 없는 쪽 글자", "T21-X04: 쪽 글자 파일 없음"]


def test_run_sections_stops_before_running(tmp_path):
    if not paths.MANIFEST.exists():
        pytest.skip("data/manifest.csv 없음 (저장소 밖 자료, D-47)")
    write_page(tmp_path, "T21-S016", "p001.txt", "번호 없는 글\n")
    done = subprocess.run([sys.executable, str(SCRIPTS / "run_sections.py"), "--model", "없는태그", "--docs", "T21-S016",
                           "--pages-dir", str(tmp_path)], capture_output=True, text=True)
    assert done.returncode == 2 and "줄번호" in done.stderr


# ── 평가 문서 빠짐 ──

@pytest.fixture
def score(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("score")


def test_eval_gaps_ignores_excluded_doc(score):
    keep = {"T21-025", "T21-002", "T21-050"}
    assert score.eval_gaps(keep, ["T21-025"], []) == []                # 25번은 평균에 넣지 않는다 (ADR-0005)
    assert score.eval_gaps(keep, ["T21-050"], ["T21-025"]) == ["T21-050"]
    assert score.eval_gaps(keep, [], ["T21-002"]) == ["T21-002"]


def test_score_refuses_example25_with_eval_purpose(tmp_path):
    done = subprocess.run([sys.executable, str(SCRIPTS / "score.py"), "--pred", str(tmp_path), "--title", "시험",
                           "--purpose", "평가", "--gold-example25"], capture_output=True, text=True)
    assert done.returncode == 2 and "ADR-0005" in done.stderr
