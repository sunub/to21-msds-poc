"""version13 출력 폴더의 meta.json (ocr_batch_version13.write_meta).

전처리(render.preprocess)의 meta와 같은 방식이다: 쪽마다 최종 글(text_source, text_file)과
데이터 표(tables: file, section, box). 경로는 모두 문서 폴더 기준이라 폴더만 넘겨받아도 표 md를 찾는다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ocr_batch_version13 as v13  # noqa: E402
from msds.preprocess import render  # noqa: E402

OCR_SCALE = 200 / 72   # PaddleOCR 조각은 200dpi 쪽 이미지 좌표


def _one_table(page, scale):
    """선으로 그린 2행 3열 표 하나 (pt 좌표: x 72~372, y 72~112). layout.page_tables 대신 쓴다."""
    xs, ys = (72, 172, 272, 372), (72, 92, 112)
    return [[[[xs[c] * scale, ys[r] * scale, xs[c + 1] * scale, ys[r + 1] * scale] for c in range(3)] for r in range(2)]]


def _it(text, x, y, s=1.0):
    return {"text": text, "box": [x * s, y * s, (x + 8 * len(text)) * s, (y + 10) * s]}


def _table_items(s=1.0):
    return [_it("물질명", 80, 76, s), _it("CAS No.", 180, 76, s), _it("UN No.", 280, 76, s),
            _it("질소", 80, 96, s), _it("7727-37-9", 180, 96, s), _it("1977", 280, 96, s)]


def test_write_meta_records_final_text_and_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "page_tables", _one_table)
    monkeypatch.setattr(render, "judge_states", lambda doc: (["정상", "글꼴깨짐"], "혼합"))
    out = tmp_path / "T21-X"
    out.mkdir()
    for n in (1, 2):
        (out / f"p{n:03d}.txt").write_text("L001 글\n", encoding="utf-8")
    (out / "tables").mkdir()
    (out / "tables" / "p009_t1.md").write_text("예전 실행의 표", encoding="utf-8")

    pages = [{"items": [_it("3. 구성성분의 명칭 및 함유량", 40, 50)] + _table_items(), "scale": 1.0, "mode": "pdf_xycut"},
             {"items": _table_items(OCR_SCALE), "scale": OCR_SCALE, "mode": "paddle_full_page"}]
    meta = v13.write_meta(out, "T21-X", "S_질소.pdf", "version13", [None, None], pages)

    assert json.loads((out / "meta.json").read_text(encoding="utf-8")) == meta
    assert {k: meta[k] for k in ("doc_id", "version", "source_file", "page_count", "dpi", "text_layer")} == {
        "doc_id": "T21-X", "version": "version13", "source_file": "S_질소.pdf", "page_count": 2, "dpi": 200,
        "text_layer": "혼합"}
    box = [72.0, 72.0, 372.0, 112.0]
    sec = "3. 구성성분의 명칭 및 함유량"
    assert meta["pages"] == [
        {"page": 1, "state": "정상", "text_source": "텍스트층", "text_file": "p001.txt",
         "tables": [{"file": "tables/p001_t1.md", "section": sec, "box": box}], "frames": 0},
        {"page": 2, "state": "글꼴깨짐", "text_source": "OCR", "text_file": "p002.txt",   # OCR 좌표도 pt로 바꿔 적는다
         "tables": [{"file": "tables/p002_t1.md", "section": sec, "box": box}], "frames": 0}]
    for p in meta["pages"]:                      # 모든 경로는 문서 폴더 기준으로 실제 파일을 가리킨다
        assert (out / p["text_file"]).exists()
        for t in p["tables"]:
            assert (out / t["file"]).read_text(encoding="utf-8").startswith("| 물질명 | CAS No. | UN No. |")
    assert not (out / "tables" / "p009_t1.md").exists()   # 예전 실행의 표가 남지 않는다
