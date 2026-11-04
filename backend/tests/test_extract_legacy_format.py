"""구양식(2항 구성성분 · 3항 유해·위험성) 문서는 추출에서 2·3항 구간을 맞바꿔 읽는다.

항 분할(preprocess.section_contract)이 정한 format을 추출 입력(extract.inputs)이 읽는지 본다.
글은 직접 만든 가짜 MSDS이고 모델 서버·실제 문서를 쓰지 않는다.
"""
import json

from msds.extract import inputs
from msds.preprocess.section_contract import Heading, document_format, extract_sections

DOC = "T21-LEGACY"

LEGACY = """L1 물질안전보건자료 (MSDS)
L2 1. 화학 제품과 제조회사 정보
L3 제품명 시험물질
L4 2. 구성 성분의 명칭 및 함유량
L5 화학물질명 | CAS No. | 함유량 (%)
L6 Polyamide 6 | 25038-54-4 | 99
L7 3. 유해 위험성
L8 눈에 대한 영향 자극을 줄 수 있음
L9 4. 응급 조치 요령
L10 눈에 들어가면 물로 씻는다
"""

CURRENT = """L1 물질안전보건자료 (MSDS)
L2 1. 화학제품과 회사에 관한 정보
L3 제품명 시험물질
L4 2. 유해성·위험성
L5 눈에 대한 영향 자극을 줄 수 있음
L6 3. 구성성분의 명칭 및 함유량
L7 화학물질명 | CAS No. | 함유량 (%)
L8 Polyamide 6 | 25038-54-4 | 99
L9 4. 응급조치 요령
L10 눈에 들어가면 물로 씻는다
"""


def load(tmp_path, text):
    pages = tmp_path / "pages"
    (pages / DOC).mkdir(parents=True)
    (pages / DOC / "p001.txt").write_text(text, encoding="utf-8")
    sections = tmp_path / "sections"
    sections.mkdir()
    split = extract_sections(DOC, pages / DOC)
    (sections / f"{DOC}.json").write_text(json.dumps(split), encoding="utf-8")
    return split, inputs.load_document(DOC, pages, sections, tmp_path / "codes")


def texts(doc, no):
    return [l.text for l in inputs.section_lines(doc, 0, no, with_preamble=False)]


def test_legacy_document_is_split_as_legacy_and_sections_are_swapped(tmp_path):
    split, doc = load(tmp_path, LEGACY)
    assert split["msds"][0]["format"] == "legacy"
    hazard, components = texts(doc, 2), texts(doc, 3)
    # 추출의 2항(유해성)에는 원문 3항(유해 위험성), 3항(성분)에는 원문 2항(구성 성분)이 간다
    assert any("눈에 대한 영향" in t for t in hazard) and not any("Polyamide" in t for t in hazard)
    assert any("Polyamide 6" in t for t in components) and not any("눈에 대한 영향" in t for t in components)
    # 줄 id는 원문 그대로다
    assert [l.id for l in inputs.section_lines(doc, 0, 2, with_preamble=False)] == ["p1:L7", "p1:L8"]
    assert any("서로 바꿔 읽었습니다" in w for w in doc.warnings)


def test_current_document_is_untouched(tmp_path):
    split, doc = load(tmp_path, CURRENT)
    assert split["msds"][0]["format"] == "current"
    assert any("눈에 대한 영향" in t for t in texts(doc, 2))
    assert any("Polyamide 6" in t for t in texts(doc, 3))
    assert not any("서로 바꿔" in w for w in doc.warnings)


def test_other_sections_are_not_affected_by_the_swap(tmp_path):
    _, legacy = load(tmp_path / "a", LEGACY)
    _, current = load(tmp_path / "b", CURRENT)
    assert texts(legacy, 1) == ["1. 화학 제품과 제조회사 정보", "제품명 시험물질"]
    assert texts(legacy, 4) == ["4. 응급 조치 요령", "눈에 들어가면 물로 씻는다"]
    assert texts(current, 1) == ["1. 화학제품과 회사에 관한 정보", "제품명 시험물질"]
    assert texts(current, 4) == ["4. 응급조치 요령", "눈에 들어가면 물로 씻는다"]


def test_document_format_reads_only_the_titles():
    h = lambda section, text: Heading(0, section, text)
    # 현행: 2항 유해성, 3항 성분
    assert document_format({2: h(2, "유해성·위험성"), 3: h(3, "구성성분의 명칭 및 함유량")}) == "current"
    # 구양식: 2항 성분, 3항 유해성
    assert document_format({2: h(2, "구성 성분의 명칭 및 함유량"), 3: h(3, "유해 위험성")}) == "legacy"
    # 영문 제목도 같다
    assert document_format({2: h(2, "Composition"), 3: h(3, "Hazards identification")}) == "legacy"
    # 한계: 제목에 기준 단어가 없으면 구양식이어도 현행으로 본다 (제목이 깨진 경우 등)
    assert document_format({2: h(2, "성분"), 3: h(3, "ㅇㅇ")}) == "current"
