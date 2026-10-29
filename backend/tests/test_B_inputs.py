"""extract/inputs.py 시험. 글은 직접 만든 가짜 MSDS이고 모델 서버·실제 문서를 쓰지 않는다."""
import json

import pytest

from msds.extract import inputs
from msds.extract.section_prompts import _dictionary

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
    # p1:L1~L4는 1항 앞이라 문서 머리로 앞에 붙는다 (ADR-020)
    assert [l.id for l in inputs.section_lines(doc, 0, 1)] == [
        "p1:L1", "p1:L2", "p1:L3", "p1:L4", "p1:L5", "p1:L6", "p1:L7", "p2:L1", "p2:L2"]
    assert [l.id for l in inputs.section_lines(doc, 0, 1, with_preamble=False)] == [
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


# ── 문서 머리: 어느 항에도 속하지 않는 1항 제목 앞 줄 (ADR-020) ──

def numbered(texts: list[str]) -> str:
    return "".join(f"L{i} {x}\n" for i, x in enumerate(texts, start=1))


def titled(nos) -> list[str]:
    """항마다 제목 줄과 내용 줄 하나. 제목은 TO21 동의어 사전에서 실행할 때 읽는다 (D-47)."""
    titles = _dictionary()["sections"]
    out = []
    for n in nos:
        out += [f"{n}. {titles[str(n)][0]}", f"가상 내용 {n}"]
    return out


HEAD = ["가상 세정액 C | 0000-00-0 | KE-00000", "제조자 | 가상화학", "UN 0000"]


def test_preamble_lines_before_first_title(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: numbered(HEAD + titled(range(1, 17)))})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert doc.sections_method == "provisional"
    assert doc.msds[0].preamble == ("p1:L1", "p1:L3")
    # 머리 3줄 뒤에 항 구간이 이어진다: 1항 p1:L4~L5, 3항 p1:L8~L9
    assert [l.id for l in inputs.section_lines(doc, 0, 3)] == ["p1:L1", "p1:L2", "p1:L3", "p1:L8", "p1:L9"]
    assert [l.id for l in inputs.section_lines(doc, 0, 1)] == ["p1:L1", "p1:L2", "p1:L3", "p1:L4", "p1:L5"]


def test_preamble_none_when_first_line_is_title(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: numbered(titled(range(1, 17)))})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert doc.msds[0].preamble is None
    assert [l.id for l in inputs.section_lines(doc, 0, 3)] == ["p1:L5", "p1:L6"]


def test_preamble_capped_at_40_lines(tmp_path):
    head = [f"가상 표지 {i}" for i in range(1, 46)]
    pages = write_pages(tmp_path / "pages", {1: numbered(head + titled(range(1, 17)))})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert doc.msds[0].preamble == ("p1:L1", "p1:L40")
    # 1항 제목 p1:L46, 3항 p1:L50~L51. 머리 41~45번째 줄은 어느 호출에도 들어가지 않는다
    assert [l.id for l in inputs.section_lines(doc, 0, 3)] == [f"p1:L{i}" for i in range(1, 41)] + ["p1:L50", "p1:L51"]


@pytest.mark.parametrize("head_len, expected", [(3, ("p1:L1", "p1:L3")), (0, None), (45, ("p1:L1", "p1:L40"))])
def test_preamble_with_sections_file(tmp_path, head_len, expected):
    head = [f"가상 머리 {i}" for i in range(1, head_len + 1)]
    pages = write_pages(tmp_path / "pages", {1: numbered(head + [f"가상 내용 {i}" for i in range(1, 6)])})
    h = head_len
    secs = write_sections(tmp_path / "sections", {"msds": [{"pages": [1, 1], "sections": {
        "1": {"start": f"p1:L{h + 1}", "end": f"p1:L{h + 2}", "method": "title"},
        "3": {"start": f"p1:L{h + 3}", "end": f"p1:L{h + 4}", "method": "title"},
    }}]})
    doc = inputs.load_document(DOC, pages, secs, tmp_path / "codes")
    assert doc.sections_method == "file"
    assert doc.msds[0].preamble == expected
    head_ids = [f"p1:L{i}" for i in range(1, min(h, 40) + 1)]
    assert [l.id for l in inputs.section_lines(doc, 0, 3)] == head_ids + [f"p1:L{h + 3}", f"p1:L{h + 4}"]
    # 분할이 없는 항(fallback)은 지금처럼 건의 쪽 전체
    assert len(inputs.section_lines(doc, 0, 2)) == h + 5


def test_preamble_second_msds_from_its_first_page(tmp_path):
    pages = write_pages(tmp_path / "pages", {
        1: numbered(HEAD + titled(range(1, 17))),
        2: numbered(["가상 세정액 D | 1111-11-1", "UN 1111"] + titled(range(1, 17))),
    })
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert [m.pages for m in doc.msds] == [(1, 1), (2, 2)]
    assert doc.msds[0].preamble == ("p1:L1", "p1:L3")
    assert doc.msds[1].preamble == ("p2:L1", "p2:L2")
    assert [l.id for l in inputs.section_lines(doc, 1, 3)] == ["p2:L1", "p2:L2", "p2:L7", "p2:L8"]


def test_preamble_second_msds_with_sections_file(tmp_path):
    pages = write_pages(tmp_path / "pages", {n: numbered([f"가상 줄 {i}" for i in range(1, 6)]) for n in (1, 2, 3)})
    secs = write_sections(tmp_path / "sections", {"msds": [
        {"pages": [1, 2], "sections": all_sections("p1:L2", "p2:L5")},
        {"pages": [3, 3], "sections": all_sections("p3:L3", "p3:L5")},
    ]})
    doc = inputs.load_document(DOC, pages, secs, tmp_path / "codes")
    assert doc.msds[0].preamble == ("p1:L1", "p1:L1")
    assert doc.msds[1].preamble == ("p3:L1", "p3:L2")     # 2건째는 그 건의 첫 쪽 첫 줄부터
    assert [l.id for l in inputs.section_lines(doc, 1, 7)] == ["p3:L1", "p3:L2", "p3:L3", "p3:L4", "p3:L5"]
