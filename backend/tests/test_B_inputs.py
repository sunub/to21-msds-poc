"""extract/inputs.py 시험. 글은 직접 만든 가짜 MSDS이고 모델 서버·실제 문서를 쓰지 않는다."""
import json

import pytest

from msds.extract import inputs

DOC = "T21-TEST"


def write_pages(root, pages: dict[int, str], doc=DOC):
    d = root / doc
    d.mkdir(parents=True)
    for no, text in pages.items():
        (d / f"p{no:03d}.txt").write_text(text, encoding="utf-8")
    return root


def write_sections(root, data, doc=DOC):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{doc}.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def all_sections(start, end, method="title"):
    return {str(n): {"start": start, "end": end, "method": method} for n in range(1, 17)}


def test_line_numbers_mixed_pages(tmp_path):
    pages = write_pages(tmp_path / "pages", {
        1: "L5 가짜물질 안전보건자료\n\nL7 1. 화학제품\n",
        2: "제품명 | 시험액\n\n   \n제조사 | 가상화학\n",
    })
    lines = inputs.read_page_lines(DOC, pages)
    assert [(l.id, l.text) for l in lines] == [
        ("p1:L5", "가짜물질 안전보건자료"),
        ("p1:L7", "1. 화학제품"),
        ("p2:L1", "제품명 | 시험액"),
        ("p2:L2", "제조사 | 가상화학"),
    ]
    assert lines[2].page == 2 and lines[2].no == 1


def test_missing_pages_raise(tmp_path):
    with pytest.raises(FileNotFoundError, match=DOC):
        inputs.read_page_lines(DOC, tmp_path / "pages")
    (tmp_path / "pages" / DOC).mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match=DOC):
        inputs.read_page_lines(DOC, tmp_path / "pages")


def test_no_sections_file_falls_back(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: "가\n나\n", 2: "다\n"})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert len(doc.msds) == 1
    part = doc.msds[0]
    assert part.pages == (1, 2)
    assert sorted(part.sections) == list(range(1, 17))
    assert all(s.method == "fallback" and s.start is None and s.end is None for s in part.sections.values())
    assert doc.warnings == ["항목 분할 파일 없음: 대체 경로"]
    assert doc.codes is None
    assert [l.id for l in inputs.section_lines(doc, 0, 3)] == ["p1:L1", "p1:L2", "p2:L1"]


def test_two_msds_sections_are_separate(tmp_path):
    pages = write_pages(tmp_path / "pages", {n: f"L1 쪽{n}\nL2 내용{n}\n" for n in range(1, 7)})
    secs = write_sections(tmp_path / "sections", {"msds": [
        {"pages": [1, 3], "sections": all_sections("p1:L1", "p3:L2")},
        {"pages": [4, 6], "sections": {**all_sections("p4:L1", "p6:L2"),
                                       "2": {"start": "p5:L1", "end": "p5:L2", "method": "synonym"}}},
    ]})
    doc = inputs.load_document(DOC, pages, secs, tmp_path / "codes")
    assert doc.warnings == []
    assert [l.page for l in inputs.section_lines(doc, 0, 1)] == [1, 1, 2, 2, 3, 3]
    assert [l.page for l in inputs.section_lines(doc, 1, 1)] == [4, 4, 5, 5, 6, 6]
    assert [l.id for l in inputs.section_lines(doc, 1, 2)] == ["p5:L1", "p5:L2"]
    assert doc.msds[1].sections[2].method == "synonym"


def test_span_crosses_pages_in_order(tmp_path):
    pages = write_pages(tmp_path / "pages", {
        1: "\n".join(f"L{i} 줄{i}" for i in range(1, 8)),
        2: "L1 a\nL2 b\nL3 c\n",
    })
    secs = write_sections(tmp_path / "sections", {"msds": [
        {"pages": [1, 2], "sections": {"1": {"start": "p1:L5", "end": "p2:L2", "method": "title"}}},
    ]})
    doc = inputs.load_document(DOC, pages, secs, tmp_path / "codes")
    assert [l.id for l in inputs.section_lines(doc, 0, 1)] == [
        "p1:L5", "p1:L6", "p1:L7", "p2:L1", "p2:L2"]


def test_bad_sections_become_fallback_with_warning(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: "L1 가\nL2 나\nL3 다\n"})
    secs = write_sections(tmp_path / "sections", {"msds": [{"pages": [1, 1], "sections": {
        "1": {"start": "p1:L1", "end": "p1:L2", "method": "title"},
        "2": {"start": "p1:L2", "end": "p1:L99", "method": "title"},   # 없는 줄
        "3": {"start": None, "end": None, "method": "failed"},
        "4": {"start": "p1:L3", "end": "p1:L1", "method": "title"},    # 순서 뒤집힘
    }}]})
    doc = inputs.load_document(DOC, pages, secs, tmp_path / "codes")
    s = doc.msds[0].sections
    assert s[1].method == "title"
    for n in (2, 3, 4, 5, 16):
        assert s[n].method == "fallback" and s[n].start is None
    assert len(doc.warnings) == 15   # 2~16항 각각 하나
    assert any(w.startswith("2항") and "p1:L99" in w for w in doc.warnings)
    assert [l.id for l in inputs.section_lines(doc, 0, 2)] == ["p1:L1", "p1:L2", "p1:L3"]


def test_codes_returned_as_is(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: "L1 가\n"})
    codes_dir = tmp_path / "codes"
    codes_dir.mkdir()
    (codes_dir / f"{DOC}.json").write_text(json.dumps({"h_codes": ["H999"]}), encoding="utf-8")
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", codes_dir)
    assert doc.codes == {"h_codes": ["H999"]}


def test_render_and_index(tmp_path):
    pages = write_pages(tmp_path / "pages", {2: "L23 가짜물질 | 000-00-0\n"})
    lines = inputs.read_page_lines(DOC, pages)
    assert inputs.render_lines(lines) == "p2:L23 가짜물질 | 000-00-0"
    assert inputs.line_index(lines)["p2:L23"].text == "가짜물질 | 000-00-0"


def test_deterministic(tmp_path):
    pages = write_pages(tmp_path / "pages", {n: f"L1 쪽{n}\n" for n in (10, 2, 1)})
    a = inputs.read_page_lines(DOC, pages)
    b = inputs.read_page_lines(DOC, pages)
    assert a == b
    assert [l.page for l in a] == [1, 2, 10]
