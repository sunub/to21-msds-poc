"""쪽마다 최종 글 하나 (meta의 text_source·text_file, render.load_pages, render.match_pages).

S003처럼 글꼴이 깨진 쪽도 OCR이 있으면 OCR 글이 최종 글이고, 원문 대조는 그 글로 한다.
모델 입력은 바꾸지 않는다: 정상이 아닌 쪽은 모델이 이미지만 본다 (client.page_parts).
"""
import json

import pymupdf
import pytest

from msds.checks.source_match import match
from msds.common import paths
from msds.preprocess import render

GARBLED = "Ɒ㫼⮹  jhzGuU  rlGuU\n"
OCR_ITEMS = [{"text": "물질안전보건자료", "score": 1.0, "box": [300, 300, 900, 360]},
             {"text": "질소(NITROGEN) 7727-37-9", "score": 0.99, "box": [300, 400, 1200, 460]}]


@pytest.fixture
def doc(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PAGES", tmp_path)
    d = tmp_path / "T21-X"
    d.mkdir()
    return d


def _blank_page():
    return pymupdf.open().new_page()


def _write_ocr(d, n):
    (d / f"p{n:03d}.ocr.json").write_text(json.dumps({"dpi": 300, "items": OCR_ITEMS}, ensure_ascii=False))


def test_broken_page_with_ocr_records_ocr_as_final_text(doc):
    _write_ocr(doc, 1)
    p = render._pick_source("T21-X", {"page": 1, "state": "글꼴깨짐"}, GARBLED, _blank_page())
    assert p["text_source"] == "OCR" and p["text_file"] == "p001.ocr_input.txt"
    assert "input_source" not in p                       # 모델 입력은 고르지 않는다 (이미지만)
    assert "질소(NITROGEN)" in (doc / "p001.ocr_input.txt").read_text(encoding="utf-8")


def test_broken_page_without_ocr_has_no_final_text(doc):
    p = render._pick_source("T21-X", {"page": 1, "state": "글꼴깨짐"}, GARBLED, _blank_page())
    assert p["text_source"] == "없음" and p["text_file"] is None
    assert not (doc / "p001.ocr_input.txt").exists()


def test_normal_page_final_text_is_text_layer(doc):
    p = render._pick_source("T21-X", {"page": 1, "state": "정상"}, "가. 제품명 벤젠\n", _blank_page())
    assert p["input_source"] == p["text_source"] == "텍스트층"
    assert p["text_file"] == "p001.match.txt"


def _meta(doc, pages):
    (doc / "meta.json").write_text(json.dumps({"doc_id": "T21-X", "pages": pages}, ensure_ascii=False))


def test_load_pages_follows_text_source(doc):
    _meta(doc, [{"page": 1, "state": "글꼴깨짐", "text_source": "OCR", "text_file": "p001.ocr_input.txt"},
                {"page": 2, "state": "글꼴깨짐", "text_source": "없음", "text_file": None},
                {"page": 3, "state": "정상", "input_source": "텍스트층", "text_source": "텍스트층",
                 "text_file": "p003.match.txt"}])
    for n in (1, 2):
        (doc / f"p{n:03d}.txt").write_text(GARBLED, encoding="utf-8")
        (doc / f"p{n:03d}.match.txt").write_text(GARBLED, encoding="utf-8")
    (doc / "p001.ocr_input.txt").write_text("물질안전보건자료\n", encoding="utf-8")
    (doc / "p003.txt").write_text("가. 제품명 벤젠벤젠\n", encoding="utf-8")
    (doc / "p003.match.txt").write_text("가. 제품명 벤젠\n", encoding="utf-8")

    p1, p2, p3 = render.load_pages("T21-X")["pages"]
    assert (p1["source"], p1["match_text"], p1["text"]) == ("OCR", "물질안전보건자료\n", "")   # 깨진 글이 새지 않는다
    assert (p2["source"], p2["match_text"], p2["text"]) == ("없음", "", "")
    assert (p3["source"], p3["text"], p3["match_text"]) == ("텍스트층", "가. 제품명 벤젠벤젠\n", "가. 제품명 벤젠\n")


def test_source_match_uses_final_text_of_broken_page():
    pages = [{"page": 1, "state": "글꼴깨짐", "source": "OCR", "match_text": "질소(NITROGEN) 7727-37-9\n"},
             {"page": 2, "state": "글꼴깨짐", "source": "없음", "match_text": ""}]
    texts, states = render.match_pages(pages)
    assert match("7727-37-9", 1, texts, states)["result"] == "일치"
    assert match("7727-37-9", 2, texts, states)["result"] == "대조불가"


def _one_table(page, scale):
    """선으로 그린 2행 3열 표 하나 (pt 좌표: x 72~372, y 72~112). layout.page_tables 대신 쓴다."""
    xs, ys = (72, 172, 272, 372), (72, 92, 112)
    return [[[[xs[c] * scale, ys[r] * scale, xs[c + 1] * scale, ys[r + 1] * scale] for c in range(3)] for r in range(2)]]


def _ocr_cell(text, x_pt, y_pt):
    s = 300 / 72   # OCR 좌표는 300dpi 픽셀
    return {"text": text, "score": 1.0, "box": [x_pt * s, y_pt * s, (x_pt + 60) * s, (y_pt + 10) * s]}


def test_broken_page_tables_come_from_ocr(doc, monkeypatch):
    """S003 1쪽: 글꼴은 깨졌지만 표 선은 멀쩡하다. 최종 글이 OCR이면 표 칸도 OCR 글로 채운다."""
    monkeypatch.setattr(render, "page_tables", _one_table)
    items = [_ocr_cell("물질명", 80, 76), _ocr_cell("CAS No.", 180, 76), _ocr_cell("UN No.", 280, 76),
             _ocr_cell("질소", 80, 96), _ocr_cell("7727-37-9", 180, 96), _ocr_cell("1977", 280, 96)]
    (doc / "p001.ocr.json").write_text(json.dumps({"dpi": 300, "items": items}, ensure_ascii=False))
    garbled = [{"text": "Ɒ㫼⮹", "box": [80, 76, 140, 86]}]
    p = {"page": 1, "state": "글꼴깨짐", "text_source": "OCR", "text_file": "p001.ocr_input.txt"}
    out, _, _ = render._write_tables("T21-X", p, garbled, None, None, None)
    assert [t["file"] for t in out["tables"]] == ["p001_t1.md"]
    assert (doc / "tables" / "p001_t1.md").read_text(encoding="utf-8") == (
        "| 물질명 | CAS No. | UN No. |\n| --- | --- | --- |\n| 질소 | 7727-37-9 | 1977 |\n")


def test_page_without_final_text_has_no_tables(doc, monkeypatch):
    monkeypatch.setattr(render, "page_tables", _one_table)
    p = {"page": 1, "state": "글꼴깨짐", "text_source": "없음", "text_file": None}
    out, prev, section = render._write_tables("T21-X", p, [], None, None, (3, "3. 구성성분"))
    assert "tables" not in out and prev is None
    assert section == (3, "3. 구성성분")   # 읽을 글이 없는 쪽은 앞 쪽의 항을 그대로 넘긴다


def _line(text, x, y):
    return {"text": text, "box": [x, y, x + 8 * len(text), y + 10]}


def test_table_records_section_heading_and_box(doc, monkeypatch):
    """표마다 meta에 파일 이름, 표 위의 가장 가까운 항 제목, 쪽 안 위치(pt)를 남긴다."""
    monkeypatch.setattr(render, "page_tables", _one_table)
    items = [_line("2. 유해성·위험성", 40, 20), _line("3. 구성성분의 명칭 및 함유량", 40, 50),
             _line("물질명", 80, 76), _line("CAS No.", 180, 76), _line("UN No.", 280, 76),
             _line("질소", 80, 96), _line("7727-37-9", 180, 96), _line("1977", 280, 96),
             _line("4. 응급조치 요령", 40, 130)]
    p = {"page": 2, "state": "정상", "text_source": "텍스트층", "text_file": "p002.match.txt"}
    out, _, section = render._write_tables("T21-X", p, items, None, None, (1, "1. 화학제품과 회사에 관한 정보"))
    assert out["tables"] == [{"file": "p002_t1.md", "section": "3. 구성성분의 명칭 및 함유량",
                              "box": [72.0, 72.0, 372.0, 112.0]}]
    assert section == (4, "4. 응급조치 요령")   # 다음 쪽은 이 쪽의 마지막 항에서 시작한다


def test_table_at_page_top_takes_previous_section(doc, monkeypatch):
    """쪽 맨 위의 표 위에 항 제목이 없으면 앞 쪽에서 넘어온 항이다."""
    monkeypatch.setattr(render, "page_tables", _one_table)
    items = [_line("물질명", 80, 76), _line("CAS No.", 180, 76), _line("UN No.", 280, 76),
             _line("질소", 80, 96), _line("7727-37-9", 180, 96), _line("1977", 280, 96)]
    p = {"page": 3, "state": "정상", "text_source": "텍스트층", "text_file": "p003.match.txt"}
    out, _, _ = render._write_tables("T21-X", p, items, None, None, (3, "3. 구성성분의 명칭 및 함유량"))
    assert out["tables"][0]["section"] == "3. 구성성분의 명칭 및 함유량"


def test_section_headings_follow_msds_numbering():
    """항 제목은 1~16항 번호와 그 항의 낱말이 맞고, 번호가 앞 항보다 커야 한다. 본문의 번호 목록은 항이 아니다."""
    from msds.preprocess.layout import section_headings
    items = [_line("1.화학제품과 회사에 관한 정보", 40, 10), _line("가.제품명", 40, 20),
             _line("3 구성성분의 명칭 및 함유량", 40, 50),          # 점 없는 번호 (M 문서)
             _line("1. 눈에 들어갔을 때", 40, 60),                 # 번호가 줄어든다
             _line("5. 이 물질은 위험하다", 40, 70),               # 5항 낱말(화재)이 없다
             _line("12. 환경에 미치는 영향", 40, 90)]
    assert [(n, t) for _, n, t in section_headings(items)] == [
        (1, "1.화학제품과 회사에 관한 정보"), (3, "3 구성성분의 명칭 및 함유량"), (12, "12. 환경에 미치는 영향")]
    assert [n for _, n, _ in section_headings(items[1:], after=3)] == [12]   # 앞 쪽에서 3항까지 봤다


def test_section_headings_restart_and_formats():
    """목차(S001 1쪽)와 MSDS 여러 건을 이은 문서(039)는 '1. 화학제품…'에서 번호가 다시 시작한다.
    '1: 제목'(045) 꼴도 항이고, '2차 유해/위험'처럼 번호 뒤에 바로 한글이 붙은 줄은 항이 아니다."""
    from msds.preprocess.layout import section_headings
    toc = [_line("1. 화학제품과 회사에 관한 정보", 40, 10), _line("16. 기타 참고사항", 40, 20),
           _line("1. 화학제품과 회사에 관한 정보", 40, 40), _line("3. 구성성분의 명칭 및 함유량", 40, 50)]
    assert [n for _, n, _ in section_headings(toc)] == [1, 16, 1, 3]
    assert [n for _, n, _ in section_headings([_line("1. 화학제품 정보", 40, 10)], after=16)] == [1]
    assert [n for _, n, _ in section_headings([_line("2: 유해성ㆍ위험성", 40, 10)])] == [2]
    assert section_headings([_line("2차 유해/위험 방지 환경 규정을 준수하시오.", 40, 10)]) == []
