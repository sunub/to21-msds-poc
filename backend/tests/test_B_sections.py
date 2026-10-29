"""extract/sections.py(임시 항목 분할)와 inputs.load_document의 분할 방식 시험.

글은 직접 만든 짧은 가짜 MSDS다 (D-43). 제목 글자는 TO21 동의어 사전에서 실행할 때 읽고 시험에 적지 않는다 (D-47).
"""
import json

from msds.extract import inputs
from msds.extract.inputs import Line
from msds.extract.section_prompts import _dictionary
from msds.extract.sections import find_sections

DOC = "T21-TEST"
TITLES = _dictionary()["sections"]


def t(n: int) -> str:
    """n항 제목: 사전의 첫 변형."""
    return TITLES[str(n)][0]


def make_lines(pages: dict[int, list[str]]) -> list[Line]:
    """쪽마다 L1부터 번호를 붙인 줄 목록."""
    return [Line(f"p{p}:L{i}", p, i, text)
            for p in sorted(pages) for i, text in enumerate(pages[p], start=1)]


def titled(nos, prefix: str = "") -> list[str]:
    """항마다 제목 줄과 내용 줄 하나."""
    out = []
    for n in nos:
        out += [f"{prefix}{n}. {t(n)}", f"가상 내용 {n}"]
    return out


def starts(part: dict) -> dict[int, str]:
    return {int(k): v["start"] for k, v in part["sections"].items() if v.get("method") != "failed"}


# ── find_sections ──────────────────────────────────────

def test_provisional_sixteen_titles():
    lines = make_lines({
        1: ["가상 물질안전보건자료"] + titled(range(1, 9)),
        2: ["8항 이어지는 내용"] + titled(range(9, 17)) + ["끝 줄"],
    })
    out = find_sections(lines, TITLES)
    assert out["stats"] == {"found": 16, "msds": 1}
    assert len(out["msds"]) == 1
    part = out["msds"][0]
    assert part["pages"] == [1, 2]
    secs = part["sections"]
    assert sorted(secs, key=int) == [str(n) for n in range(1, 17)]
    assert all(s["method"] == "provisional" for s in secs.values())
    # 1~7항: 제목 줄부터 다음 제목 바로 앞 줄까지
    for n in range(1, 8):
        assert secs[str(n)] == {"start": f"p1:L{2 * n}", "end": f"p1:L{2 * n + 1}", "method": "provisional"}
    # 8항은 다음 쪽 첫 줄까지 이어진다
    assert (secs["8"]["start"], secs["8"]["end"]) == ("p1:L16", "p2:L1")
    for n in range(9, 16):
        a = 2 * (n - 9) + 2
        assert (secs[str(n)]["start"], secs[str(n)]["end"]) == (f"p2:L{a}", f"p2:L{a + 1}")
    # 마지막 항은 끝 줄까지
    assert (secs["16"]["start"], secs["16"]["end"]) == ("p2:L16", "p2:L18")


def test_provisional_title_split_by_cells_and_number_forms():
    def split(s: str) -> str:
        k = len(s) // 2
        return s[:k] + " | " + s[k:]

    lines = make_lines({1: [
        f"1. {t(1)}", "내용",
        f"2. | {t(2)}", "내용",          # 번호와 제목이 칸으로 나뉨
        f"3) {split(t(3))}", "내용",     # 제목 가운데가 칸으로 나뉨
        f"4항 {t(4)}", "내용",
        f"5 {t(5)}", "내용",
        f"6.{t(6)} | (계속)", "내용",    # 제목 변형으로 시작
    ]})
    out = find_sections(lines, TITLES)
    assert starts(out["msds"][0]) == {n: f"p1:L{2 * n - 1}" for n in range(1, 7)}


def test_provisional_not_a_title():
    lines = make_lines({1: [
        f"1. {t(1)}", "내용",
        f"{t(2)}",                       # 번호 없음
        f"17. {t(2)}",                   # 1~16 밖
        f"3. {t(2)}",                    # 번호와 제목이 맞지 않음
        f"가. {t(3)}",                   # 번호가 숫자가 아님
        f"2. {t(2)}", "내용",
    ]})
    out = find_sections(lines, TITLES)
    assert starts(out["msds"][0]) == {1: "p1:L1", 2: "p1:L7"}


def test_provisional_two_msds():
    lines = make_lines({
        1: titled(range(1, 9)),
        2: titled(range(9, 17)),
        3: titled(range(1, 9)),
        4: titled(range(9, 17)) + ["둘째 건 끝"],
    })
    out = find_sections(lines, TITLES)
    assert out["stats"] == {"found": 32, "msds": 2}
    a, b = out["msds"]
    assert (a["pages"], b["pages"]) == ([1, 2], [3, 4])
    assert (a["sections"]["1"]["start"], b["sections"]["1"]["start"]) == ("p1:L1", "p3:L1")
    # 앞 건의 마지막 항은 다음 건 앞 쪽의 끝 줄까지, 뒤 건은 문서 끝 줄까지
    assert a["sections"]["16"]["end"] == "p2:L16"
    assert b["sections"]["16"]["end"] == "p4:L17"


def test_provisional_repeated_first_title_with_few_found_stays_one():
    lines = make_lines({1: titled([1, 2]) + [f"1. {t(1)}"] + titled(range(3, 17))})
    out = find_sections(lines, TITLES)
    assert out["stats"] == {"found": 16, "msds": 1}
    secs = out["msds"][0]["sections"]
    assert secs["1"]["start"] == "p1:L1"           # 같은 번호가 두 번이면 앞의 것
    assert secs["2"]["end"] == "p1:L5"             # 버린 제목 줄은 앞 항 안에 남는다


def test_provisional_missing_section_failed():
    lines = make_lines({1: titled(range(1, 13)) + titled(range(14, 17))})
    out = find_sections(lines, TITLES)
    secs = out["msds"][0]["sections"]
    assert secs["13"] == {"method": "failed"}
    assert all(secs[str(n)]["method"] == "provisional" for n in range(1, 17) if n != 13)
    assert secs["12"]["end"] == "p1:L24"           # 14항 제목 바로 앞 줄
    assert out["stats"] == {"found": 15, "msds": 1}


def test_provisional_reversed_number_dropped():
    nos = [1, 2, 3, 4, 5, 6, 8, 9]
    lines = make_lines({1: titled(nos) + [f"7. {t(7)}", "내용"] + titled(range(10, 17))})
    out = find_sections(lines, TITLES)
    secs = out["msds"][0]["sections"]
    assert secs["7"] == {"method": "failed"}
    assert (secs["9"]["start"], secs["9"]["end"]) == ("p1:L15", "p1:L18")


def test_provisional_page_header_excluded():
    header = f"1. {t(1)}"                          # 머리글이 제목처럼 보여도
    lines = make_lines({
        1: [header] + titled(range(1, 7)),
        2: [header] + titled(range(7, 12)),
        3: [header] + titled(range(12, 17)),
    })
    out = find_sections(lines, TITLES)
    assert out["stats"] == {"found": 16, "msds": 1}
    part = out["msds"][0]
    assert part["pages"] == [1, 3]
    assert part["sections"]["1"]["start"] == "p1:L2"
    assert not any(s.endswith(":L1") for s in starts(part).values())


def test_provisional_header_on_two_pages_is_kept():
    lines = make_lines({
        1: [f"1. {t(1)}", "내용"],
        2: [f"1. {t(1)}"] + titled(range(2, 17)),
    })
    out = find_sections(lines, TITLES)
    # 셋 이상의 쪽이 아니라 머리글로 보지 않는다. 같은 번호는 앞의 것을 쓴다
    assert out["msds"][0]["sections"]["1"]["start"] == "p1:L1"


def test_provisional_table_of_contents_skipped():
    lines = make_lines({
        1: ["가상 물질안전보건자료", "목차"] + [f"{n}. {t(n)} | {n}" for n in range(1, 17)],
        2: titled(range(1, 9)),
        3: titled(range(9, 17)),
    })
    out = find_sections(lines, TITLES)
    assert out["stats"] == {"found": 16, "msds": 1}
    part = out["msds"][0]
    assert part["pages"] == [1, 3]                 # 첫 건은 1쪽부터
    assert part["sections"]["1"]["start"] == "p2:L1"
    assert all(int(s.split(":")[0][1:]) >= 2 for s in starts(part).values())


def test_provisional_many_titles_with_content_between_kept():
    # 한 쪽에 제목이 9개 넘게 있어도 사이에 내용 줄이 있으면 목차가 아니다
    lines = make_lines({1: titled(range(1, 17))})
    out = find_sections(lines, TITLES)
    assert out["stats"] == {"found": 16, "msds": 1}


def test_provisional_no_titles_and_no_lines():
    out = find_sections(make_lines({1: ["가", "나"], 2: ["다"]}), TITLES)
    assert out["stats"] == {"found": 0, "msds": 1}
    assert all(s == {"method": "failed"} for s in out["msds"][0]["sections"].values())
    assert find_sections([], TITLES) == {"msds": [], "stats": {"found": 0, "msds": 0}}


def test_provisional_deterministic():
    lines = make_lines({1: titled(range(1, 9)), 2: titled(range(9, 17))})
    assert find_sections(lines, TITLES) == find_sections(lines, TITLES)


# ── load_document ──────────────────────────────────────

def write_pages(root, pages: dict[int, list[str]], doc=DOC):
    d = root / doc
    d.mkdir(parents=True)
    for no, texts in pages.items():
        (d / f"p{no:03d}.txt").write_text("".join(f"L{i} {x}\n" for i, x in enumerate(texts, start=1)),
                                          encoding="utf-8")
    return root


def test_provisional_load_document_without_file(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: titled(range(1, 9)), 2: titled(range(9, 17))})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert doc.sections_method == "provisional"
    assert doc.warnings == ["항목 분할 파일 없음: 임시 분할 (찾은 항 16/16, MSDS 1건)"]
    assert len(doc.msds) == 1 and doc.msds[0].pages == (1, 2)
    assert doc.msds[0].sections[3].method == "provisional"
    assert [l.id for l in inputs.section_lines(doc, 0, 3)] == ["p1:L5", "p1:L6"]
    assert not (tmp_path / "sections").exists()    # 임시 분할은 파일로 쓰지 않는다


def test_provisional_load_document_missing_section_falls_back(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: titled(range(1, 13)) + titled(range(14, 17))})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert doc.sections_method == "provisional"
    assert doc.warnings[0] == "항목 분할 파일 없음: 임시 분할 (찾은 항 15/16, MSDS 1건)"
    assert any(w.startswith("13항") for w in doc.warnings[1:])
    assert doc.msds[0].sections[13].method == "fallback"
    assert len(inputs.section_lines(doc, 0, 13)) == 30   # 그 항만 건 전체


def test_provisional_load_document_two_msds(tmp_path):
    pages = write_pages(tmp_path / "pages", {n: titled(range(1, 17)) for n in (1, 2)})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert "MSDS 2건" in doc.warnings[0] and "찾은 항 32/32" in doc.warnings[0]
    assert [m.pages for m in doc.msds] == [(1, 1), (2, 2)]
    assert [l.id for l in inputs.section_lines(doc, 1, 16)] == ["p2:L31", "p2:L32"]


def test_provisional_load_document_no_titles_fallback(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: ["가", "나"]})
    doc = inputs.load_document(DOC, pages, tmp_path / "sections", tmp_path / "codes")
    assert doc.sections_method == "fallback"
    assert doc.warnings == ["항목 분할 파일 없음: 대체 경로"]
    assert all(s.method == "fallback" for s in doc.msds[0].sections.values())


def test_provisional_load_document_file_wins(tmp_path):
    pages = write_pages(tmp_path / "pages", {1: titled(range(1, 17))})
    secs = tmp_path / "sections"
    secs.mkdir()
    (secs / f"{DOC}.json").write_text(json.dumps({"msds": [{"pages": [1, 1], "sections": {
        str(n): {"start": "p1:L1", "end": "p1:L32", "method": "title"} for n in range(1, 17)}}]}),
        encoding="utf-8")
    doc = inputs.load_document(DOC, pages, secs, tmp_path / "codes")
    assert doc.sections_method == "file"
    assert doc.warnings == []
    assert doc.msds[0].sections[5].method == "title"
