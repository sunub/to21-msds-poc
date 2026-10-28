"""extract/nuextract_examples.py 시험. 가짜 문서는 직접 만든 것이다 (D-43). 모델 서버를 부르지 않는다."""
import json
import re

import pytest

from msds.common.schema import validate
from msds.extract import nuextract_examples as nxe
from msds.extract.nuextract import coerce
from msds.extract.section_prompts import build_user
from msds.extract.section_runner import check_section
from msds.extract.section_specs import response_schema

NOS = range(1, 17)
NARRATIVE_ONLY = {4, 5, 6, 7, 10, 13}
VERBATIM_KEYS = ("raw", "name", "text", "item_raw", "comp_name", "comp_cas", "cas_no")
TEXT = {l.id: l.text for l in nxe.FAKE_LINES}
POS = {l.id: i for i, l in enumerate(nxe.FAKE_LINES)}


def output(no: int) -> dict:
    return json.loads(nxe.example(no)["output"])


def line_values(node):
    """line, start, end, lines 안 칸의 값."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("line", "start", "end"):
                yield v
            elif k == "lines" and isinstance(v, dict):
                yield from v.values()
            else:
                yield from line_values(v)
    elif isinstance(node, list):
        for v in node:
            yield from line_values(v)


def rows(node):
    """줄 번호 line이나 start를 가진 행."""
    if isinstance(node, dict):
        if "line" in node or "start" in node:
            yield node
        for v in node.values():
            yield from rows(v)
    elif isinstance(node, list):
        for v in node:
            yield from rows(v)


def lists(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from lists(v)
    elif isinstance(node, list):
        yield node
        for v in node:
            yield from lists(v)


def section_range(no: int) -> range:
    """FAKE_LINES에서 no항 제목 줄부터 다음 항 제목 줄 앞까지의 위치."""
    titles = {int(m.group(1)): i for i, l in enumerate(nxe.FAKE_LINES) if (m := re.match(r"(\d+)\. ", l.text))}
    return range(titles[no], titles.get(no + 1, len(nxe.FAKE_LINES)))


def test_fake_lines_ids():
    ids = [l.id for l in nxe.FAKE_LINES]
    assert len(ids) == len(set(ids))
    for l in nxe.FAKE_LINES:
        assert re.fullmatch(r"p\d+:L\d+", l.id)
        assert l.id == f"p{l.page}:L{l.no}"
        assert l.text.strip()
    assert {l.page for l in nxe.FAKE_LINES} == {1, 2}
    assert 40 <= len(ids) <= 70


def test_fake_lines_have_16_titles_in_order():
    titles = [int(m.group(1)) for l in nxe.FAKE_LINES if (m := re.match(r"(\d+)\. ", l.text))]
    assert titles == list(NOS)


@pytest.mark.parametrize("no", NOS)
def test_example_input_is_real_request_text(no):
    ex = nxe.example(no)
    assert set(ex) == {"input", "output"}
    assert ex["input"] == build_user(no, nxe.FAKE_LINES)[0]["text"]


@pytest.mark.parametrize("no", NOS)
def test_example_output_validates_and_is_stable(no):
    s = response_schema(no)
    out = output(no)
    assert validate(out, s) == []
    assert coerce(out, s) == out
    assert out["extras"] == []


@pytest.mark.parametrize("no", NOS)
def test_coerce_keeps_hand_written_rows(no):
    """형 맞추기가 손으로 쓴 행을 버리지 않는다."""
    assert len(list(rows(output(no)))) == len(list(rows(nxe._VALUES[no])))


@pytest.mark.parametrize("no", NOS)
def test_example_line_ids(no):
    out = output(no)
    assert check_section(out, set(TEXT)) == []
    used = [v for v in line_values(out) if v is not None]
    assert used
    assert all(POS[v] in section_range(no) for v in used), "다른 항의 줄을 썼다"


@pytest.mark.parametrize("no", NOS)
def test_example_row_counts(no):
    out = output(no)
    narratives = out.get("narratives", [])
    if no in NARRATIVE_ONLY:
        assert 1 <= len(narratives) <= 2
        return
    assert len(narratives) == (1 if "narratives" in out else 0)
    tables = {k: v for k, v in out.items() if k not in ("narratives", "extras")}
    assert [v for v in line_values(tables) if v is not None]
    assert all(len(x) <= 3 for x in lists(tables))


@pytest.mark.parametrize("no", NOS)
def test_example_verbatim_text_is_in_its_line(no):
    """원문 그대로 옮긴 글(raw, 이름, 제목)은 그 행이 가리키는 줄에 있다."""
    for row in rows(output(no)):
        text = TEXT[row["line"]] if "line" in row else TEXT[row["start"]]
        if row.get("title_raw") and "start" in row:
            assert row["title_raw"] in text
        for k, v in row.items():
            if k in VERBATIM_KEYS and isinstance(v, str):
                assert v in text, (k, v, text)
            elif isinstance(v, dict) and isinstance(v.get("raw"), str):
                assert v["raw"] in text, (k, v["raw"], text)


def test_section3_component_cas_is_in_its_line():
    comps = output(3)["components"]
    assert comps
    for c in comps:
        assert c["cas_no"] and c["cas_no"] in TEXT[c["line"]]
