"""extract/section_prompts.py 시험. 명세서·동의어 사전은 읽기만 하고, 원문 줄은 직접 만든 가짜 값이다 (D-43)."""
import hashlib
import json
import re
import time

import pytest

from msds.common.paths import to21_file
from msds.extract import section_prompts as sp
from msds.extract.inputs import Line
from msds.extract.rows import ROWS_SECTIONS_DEFAULT, row_tables
from msds.extract.section_specs import load_specs

NOS = range(1, 17)
TARGETS = {no: set(s.targets) for no, s in load_specs().items()}
ALL_KEYS = set().union(*TARGETS.values())


@pytest.fixture(scope="module")
def systems():
    return {no: sp.build_system(no) for no in NOS}


def _part(text: str, title: str) -> str:
    """안내문에서 '## <title>'로 시작하는 부분만 (다음 '## ' 전까지)."""
    m = re.search(rf"^## {re.escape(title)}.*?(?=^## |\Z)", text, re.M | re.S)
    return m.group(0) if m else ""


@pytest.mark.parametrize("no", NOS)
def test_build_system_has_title_and_line_example(systems, no):
    text = systems[no]
    assert f'{no}항 "{load_specs()[no].title}"' in text
    assert "p2:L23" in text


@pytest.mark.parametrize("no", NOS)
def test_field_paths_of_targets_present(systems, no):
    fields = _part(systems[no], "[필드 정의]")
    for key in TARGETS[no]:
        assert re.search(rf"^- `{key}[.\[]", fields, re.M), f"{no}항 필드 정의에 {key} 없음"


@pytest.mark.parametrize("no, path", [
    (1, "companies[].contacts[].value"), (1, "meta.msds_no"), (2, "hazard.classes[].class_code"),
    (3, "components[].cas_no"), (9, "physchem[].prop_code"), (15, "regulations[].item_code"),
    (16, "meta_revision.last_revision_date"), (4, "narratives[].item_code"), (5, "extras[].title_raw"),
])
def test_field_path_examples(systems, no, path):
    assert f"- `{path}`" in systems[no]


@pytest.mark.parametrize("no", NOS)
def test_no_other_section_keys(systems, no):
    for key in ALL_KEYS - TARGETS[no]:
        assert not re.search(rf"`{key}[.\[`]", systems[no]), f"{no}항 안내문에 {key}"


def test_no_transport_in_section_3(systems):
    assert "transport" not in systems[3]


@pytest.mark.parametrize("no", NOS)
def test_code_owned_fields_excluded(systems, no):
    text = systems[no]
    for path in ["hazard.pictograms", "meta.page_start", "meta.page_end", "narratives[].status",
                 "narratives[].statements", "extras[].page", "extras[].section_no", "evidence", "validation"]:
        assert f"`{path}" not in text
    assert not re.search(r"`[\w.\[\]]*\.seq`", text)                    # 순번은 코드가 붙인다
    assert not re.search(r"`[\w.\[\]]*\.comp_ref`", text)               # 이 호출은 comp_name·comp_cas로 쓴다


def test_no_pictogram_table_in_section_2(systems):
    text = systems[2]
    assert "(C2)" not in text
    assert "GHS01" not in text
    assert "### 5-1. 유해성 분류 코드(C1)" in text


@pytest.mark.parametrize("no", NOS)
def test_narrative_codes_only_this_section(systems, no):
    """C3 코드표는 이 항의 줄만. 필드 정의의 예시 값(명세서 '예시(가상)')은 따지지 않는다."""
    text = _part(systems[no], "[코드표]")
    for other, spec in load_specs().items():
        for code in spec.narrative_codes:
            assert (code in text) == (other == no), f"{no}항 안내문의 {code}"


@pytest.mark.parametrize("no, tables", [
    (1, {"C7"}), (2, {"C1", "C3"}), (3, set()), (9, {"C4"}), (11, {"C3", "C5", "C7", "C8"}),
    (15, {"C3", "C6", "C7"}),
])
def test_code_tables_from_field_refs(systems, no, tables):
    found = set(re.findall(r"^### 5-\d\. .*\((C\d)\)$", _part(systems[no], "[코드표]"), re.M))
    assert found == tables


def test_synonyms_only_9_and_15(systems):
    dic = json.loads(to21_file("dictionary").read_text(encoding="utf-8"))
    for no, key in [(9, "physchem"), (15, "regulations")]:
        syn = _part(systems[no], "[동의어]")
        assert f"### {key}" in syn
        code, names = next(iter(dic[key].items()))
        assert f"- {code}: " + " / ".join(names) in syn
    assert "### regulations" not in systems[9]
    assert "### physchem" not in systems[15]
    for no in set(NOS) - {9, 15}:
        assert "[동의어]" not in systems[no]


@pytest.mark.parametrize("no, codes", [
    (1, {"R01", "R12"}), (2, {"R05", "R07", "R21"}), (3, {"R02", "R03", "R04", "R06", "R13", "R19", "R23"}),
    (9, {"R25"}), (15, {"R25"}), (16, {"R01"}),
])
def test_rules_include_guide_rules(systems, no, codes):
    rules = _part(systems[no], "[규칙]")
    for code in codes | {"R15", "R17", "R24"}:
        assert f"- {code} " in rules, f"{no}항 규칙에 {code} 없음"


def test_rules_exclude_comp_ref_rule(systems):
    assert "- R10 " not in systems[8]          # comp_ref는 펼치기가 붙인다


def test_guides_mention_comp_and_narrative_fields(systems):
    for no in (8, 9, 11, 12, 15):
        assert "`comp_name`" in systems[no] and "`comp_cas`" in systems[no]
    for no in (1, 3, 4):
        assert "`comp_name`" not in _part(systems[no], "이 항의 안내")
    for no, spec in load_specs().items():
        has = "`start`" in _part(systems[no], "이 항의 안내")
        assert has == bool(spec.narrative_codes)
    assert "`meta_revision`" in systems[16]


def test_build_user_renders_lines():
    lines = [Line("p1:L1", 1, 1, "가. 제품명 : 가짜 세척제 A"), Line("p1:L2", 1, 2, "나. 용도 : 세척")]
    assert sp.build_user(1, lines) == [
        {"type": "text", "text": "[1항 원문]\np1:L1 가. 제품명 : 가짜 세척제 A\np1:L2 나. 용도 : 세척"}]


def test_build_user_retry_feedback():
    lines = [Line("p3:L7", 3, 7, "가짜 성분 | 000-00-0 | 10~20")]
    out = sp.build_user(3, lines, retry_feedback="components[0].line: p9:L99는 없는 줄")
    assert out == [{"type": "text", "text": "[3항 원문]\np3:L7 가짜 성분 | 000-00-0 | 10~20"
                                             "\n\n[다시 확인할 점]\ncomponents[0].line: p9:L99는 없는 줄"}]


@pytest.mark.parametrize("no", NOS)
def test_prompt_hash_stable(systems, no):
    h = sp.prompt_hash(no)
    assert h == sp.prompt_hash(no)
    assert h == hashlib.sha256(systems[no].encode("utf-8")).hexdigest()[:12]


def test_prompt_hash_differs_by_section():
    assert len({sp.prompt_hash(no) for no in NOS}) == 16


@pytest.mark.parametrize("no", NOS)
def test_value_and_range_are_exclusive(systems, no):
    """value와 lower/upper를 함께 쓰지 않게 한다 (TO21 검증기 V03)."""
    assert "`value`와 `lower`·`upper`는 함께 쓰지 않는다" in systems[no]


def test_version():
    assert sp.SECTION_PROMPT_VERSION == "s5"


@pytest.mark.parametrize("no", NOS)
def test_s4_omit_empty_cells(systems, no):
    """값 없는 칸은 쓰지 않게 한다 (ADR-017)."""
    assert "값이 없는 칸은 쓰지 않는다" in systems[no]
    assert "null로 둔다" not in systems[no]


def test_build_all_under_one_second():
    sp._workbook.cache_clear()
    sp._dictionary.cache_clear()
    t = time.perf_counter()
    for no in NOS:
        sp.build_system(no)
    assert time.perf_counter() - t < 1.0


def test_print_sizes(systems):
    """항별 안내문 글자 수 (실패 조건 아님). 보려면 -s."""
    print("\n항별 안내문 글자 수: " + ", ".join(f"{no}항 {len(systems[no]):,}" for no in NOS))


# ── 행 형식 안내문 (ADR-019) ───────────────────────────

@pytest.fixture(scope="module")
def rows_systems():
    return {no: sp.build_system(no, rows=True) for no in ROWS_SECTIONS_DEFAULT}


def test_rows_version_s5():
    assert sp.SECTION_PROMPT_VERSION == "s5"


@pytest.mark.parametrize("no", ROWS_SECTIONS_DEFAULT)
def test_rows_system_has_table_headers_and_columns(rows_systems, no):
    text = rows_systems[no]
    assert f'{no}항 "{load_specs()[no].title}"' in text
    assert "p2:L23" in text
    fmt = _part(text, "[응답 형식]")
    for name, cols in row_tables(no).items():
        assert f"### {name}\n" + " | ".join(cols) + "\n" in fmt


@pytest.mark.parametrize("no", ROWS_SECTIONS_DEFAULT)
def test_rows_system_replaces_json_rules_only(rows_systems, systems, no):
    """JSON 지시는 빠지고, 이 항의 안내·필드 정의·코드표는 JSON 안내문과 같다."""
    text = rows_systems[no]
    assert "JSON 형식" not in text and "값이 없는 칸은 쓰지 않는다" not in text
    assert "JSON을 쓰지 않는다" in text
    for title in ("이 항의 안내", "[필드 정의]", "[코드표]"):
        assert _part(text, title).strip() == _part(systems[no], title).strip(), title


@pytest.mark.parametrize("no", ROWS_SECTIONS_DEFAULT)
def test_rows_system_only_this_section_tables(rows_systems, no):
    for key in ALL_KEYS - TARGETS[no]:
        assert f"### {key}\n" not in rows_systems[no], f"{no}항 행 안내문에 {key}"


@pytest.mark.parametrize("no", NOS)
def test_rows_false_is_json_prompt(systems, no):
    assert sp.build_system(no, rows=False) == systems[no]
    assert "[응답 형식]" not in systems[no]


@pytest.mark.parametrize("no", ROWS_SECTIONS_DEFAULT)
def test_rows_prompt_hash(rows_systems, no):
    h = sp.prompt_hash(no, rows=True)
    assert h == hashlib.sha256(rows_systems[no].encode("utf-8")).hexdigest()[:12]
    assert h != sp.prompt_hash(no)
