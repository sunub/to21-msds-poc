"""묶음 방식 실버·골드 → 항별 중간 형식 정답 시험 (11/03 F, msds.finetune.from_silver).

- 근거 원문 조각으로 줄 번호를 찾는다('…'로 줄인 조각, 표 칸 구분, 여러 줄에 걸친 조각 포함).
- 같은 글이 여러 줄에 있으면 근거 쪽, 표의 앞 행 뒤 순으로 고른다.
- 이 항 호출이 볼 수 없는 값(다른 항에 적힌 값, 근거 글이 없는 행)은 정답에서 빼고, 못 찾은 행이 있으면 그 항을 쓰지 않는다.
뒤쪽 실제 골드 시험은 개발 문서의 쪽 글자(data/pages)와 골드가 있을 때만 돈다(D-47).
"""
import json

import pytest

from msds.common.paths import DATA
from msds.extract.inputs import EXTRACT_SECTIONS, DocumentInput, Line, MsdsPart, SectionSpan, load_document
from msds.finetune.dataset import SilverSet, Student, build_examples
from msds.finetune.from_silver import LineFinder, convert_section, norm, row_values

PAGE1 = ["1. 화학제품과 회사에 관한 정보", "가. 제품명 : 가상 세척제 A", "나. 공급자 : 가상화학 주식회사",
         "다. 긴급 연락처 : 02-123-4567",
         "3. 구성성분의 명칭 및 함유량", "화학물질명 | CAS 번호 | 함유량(%)", "가상물질 갑 | 1234-56-6 | 10 ~ 20",
         "가상물질 을 | 2345-67-7 | 자료없음", "가상물질 병 | 3456-78-8 | 자료없음"]
PAGE2 = ["16. 그 밖의 참고사항", "가. 최초 작성일자 : 2020. 01. 02", "나. 개정 횟수 : 3회"]


def make_doc() -> DocumentInput:
    lines = [Line(f"p1:L{i}", 1, i, t) for i, t in enumerate(PAGE1, 1)] + \
            [Line(f"p2:L{i}", 2, i, t) for i, t in enumerate(PAGE2, 1)]
    spans = {no: SectionSpan(None, None, "failed") for no in range(1, 17)}
    spans[1] = SectionSpan("p1:L1", "p1:L4", "title")
    spans[3] = SectionSpan("p1:L5", "p1:L9", "title")
    spans[16] = SectionSpan("p2:L1", "p2:L3", "title")
    for no in (2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
        spans[no] = SectionSpan("p1:L4", "p1:L4", "title")
    return DocumentInput("T21-X01", lines, [MsdsPart(0, (1, 2), spans)], None, [], "file")


def item() -> dict:
    comps = [{"seq": 1, "name": "가상물질 갑", "cas_no": "1234-56-6", "content": {"raw": "10 ~ 20", "status": "값있음",
                                                                            "lower_op": ">=", "lower": 10, "upper_op": "<=",
                                                                            "upper": 20, "unit": "%", "dp": 0}},
             {"seq": 2, "name": "가상물질 을", "cas_no": "2345-67-7", "content": {"raw": "자료없음", "status": "자료없음"}},
             {"seq": 3, "name": "가상물질 병", "cas_no": "3456-78-8", "content": {"raw": "자료없음", "status": "자료없음"}}]
    ev = [{"field": "product.name", "page": 1, "source_text": "가. 제품명 : 가상 세척제 A"},
          {"field": "meta.first_issue_date", "page": 2, "source_text": "가. 최초 작성일자 : 2020. 01. 02"},
          {"field": "companies[0]", "page": 1, "source_text": "나. 공급자 : 가상화학 주식회사"},
          {"field": "companies[0].contacts[0]", "page": 1, "source_text": "다. 긴급 연락처 : 02-123-4567"},
          {"field": "components[0]", "page": 1, "source_text": "가상물질 갑 | 1234-56-6 | 10 ~ 20"},
          {"field": "components[1]", "page": 1, "source_text": "가상물질 을 | 2345-67-7 | 자료없음"},
          {"field": "components[2]", "page": 1, "source_text": "가상물질 병 | 3456-78-8 | 자료…"}]
    return {"meta": {"first_issue_date": "2020-01-02", "page_start": 1}, "product": {"name": "가상 세척제 A", "uses": []},
            "companies": [{"seq": 1, "role": "공급자", "name": "가상화학 주식회사",
                           "contacts": [{"type": "긴급", "value": "02-123-4567"}]}],
            "composition": {"type": "혼합물", "no_hazardous_component": False}, "components": comps,
            "extras": [], "narratives": [], "evidence": ev}


def test_조각_변형과_여러_줄에_걸친_조각():
    lines = [Line("p1:L1", 1, 1, "가. 제품명 : 가상"), Line("p1:L2", 1, 2, "세척제 A (액상)"), Line("p1:L3", 1, 3, "자료없음"),
             Line("p2:L1", 2, 1, "자료없음")]
    f = LineFinder(lines)
    assert f.find("제품명 : 가상 세척제 A") == 0                      # 두 줄에 걸친 조각은 시작 줄
    assert f.find("제품명 : 가상 … 아무 글") == 0                     # '…' 앞 조각
    assert f.find("자료없음", page=2) == 3 and f.find("자료없음", after=3) == 3 and f.find("자료없음") == 2
    assert f.find("없는 글자들입니다") is None and norm(" a | b : c ") == "abc"


def test_항별_정답으로_되돌리고_다른_항의_값은_뺀다():
    doc = make_doc()
    s1, problems, notes = convert_section(item(), 1, doc, 0)
    assert problems == [] and notes == ["이 항 줄 밖 meta.first_issue_date"]   # 16항에 적힌 작성일은 1항 호출이 못 본다
    assert s1["meta"] == {"lines": {}} and s1["product"] == {"name": "가상 세척제 A", "lines": {"name": "p1:L2"}}
    assert s1["companies"] == [{"role": "공급자", "name": "가상화학 주식회사",
                                "contacts": [{"type": "긴급", "value": "02-123-4567", "line": "p1:L4"}], "line": "p1:L3"}]
    s3, problems, _ = convert_section(item(), 3, doc, 0)
    assert problems == [] and [c["line"] for c in s3["components"]] == ["p1:L7", "p1:L8", "p1:L9"]
    assert s3["components"][0]["content"] == {"raw": "10 ~ 20", "lower_op": ">=", "lower": 10, "upper_op": "<=",
                                              "upper": 20, "unit": "%"}        # QM 칸만(status·dp 뺌)
    assert s3["composition"]["lines"] == {"type": "p1:L5", "no_hazardous_component": "p1:L5"}   # 판단 칸은 항 첫 줄


def test_줄을_못_찾은_행이_있으면_그_항은_쓰지_않는다():
    bad = item()
    bad["components"][1]["name"] = "문서에 없는 물질"
    bad["components"][1]["cas_no"] = "9999-99-9"
    bad["evidence"] = [e for e in bad["evidence"] if e["field"] != "components[1]"]
    bad["components"][1]["content"] = {"raw": "99 %"}
    _, problems, _ = convert_section(bad, 3, make_doc(), 0)
    assert problems == ["줄 못 찾음 components[1]"]


def test_행의_원문_글_후보():
    assert row_values({"name": "갑", "cas_no": "1-2-3", "status": "자료없음", "q": {"raw": "5 %"}, "line": "p1:L1"}) == \
        ["갑", "1-2-3", "5 %"]


DEV = ["T21-M001", "T21-M013", "T21-S001", "T21-S013", "T21-S016"]
has_dev = pytest.mark.skipif(not all((DATA / "pages" / d).is_dir() and (DATA / "gold" / f"{d}.json").is_file() for d in DEV),
                             reason="개발 문서의 쪽 글자 또는 골드가 없습니다")


@has_dev
def test_개발_골드는_대부분_항별_정답이_되고_줄에_값이_있다():
    r = build_examples([SilverSet(DATA / "gold", DATA / "pages", "gold")], Student.from_config(None), allow_held_out=True,
                       only_docs=set(DEV))
    made, tried = sum(r.made.values()), sum(r.tried.values())
    assert tried == 45 and made >= 40, (made, r.drop_samples)                 # 11/03: 44/45
    hit = total = 0
    for d in DEV:
        doc = load_document(d, DATA / "pages", DATA / "sections", DATA / "codes")
        text = {l.id: norm(l.text) for l in doc.lines}
        it = json.loads((DATA / "gold" / f"{d}.json").read_text(encoding="utf-8"))["msds"][0]
        for no in EXTRACT_SECTIONS:
            parsed, problems, _ = convert_section(it, no, doc, 0)
            if problems:
                continue
            for table, rows in parsed.items():
                for row in rows if isinstance(rows, list) and table != "narratives" else []:
                    vals = [norm(v) for v in row_values(row) if len(norm(v)) >= 2]
                    if vals:
                        total += 1
                        hit += any(v in text[row["line"]] for v in vals)
    assert total > 300 and hit / total >= 0.9, (hit, total)                   # 11/03: 412/441 (93%)
