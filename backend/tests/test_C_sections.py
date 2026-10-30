from pathlib import Path
from unittest import SkipTest

from msds.preprocess.section_contract import PageLine, build_contract, extract_sections


ROOT = Path(__file__).resolve().parents[2]


def lines(pages: dict[int, list[str]]) -> list[PageLine]:
    return [PageLine(page, number, text)
            for page in sorted(pages)
            for number, text in enumerate(pages[page], start=1)]


def title(number: int) -> str:
    words = {
        1: "화학제품과 회사에 관한 정보", 2: "유해성·위험성", 3: "구성성분의 명칭 및 함유량",
        4: "응급조치 요령", 5: "폭발·화재 시 대처방법", 6: "누출 사고 시 대처방법",
        7: "취급 및 저장방법", 8: "노출방지 및 개인보호구", 9: "물리화학적 특성",
        10: "안정성 및 반응성", 11: "독성에 관한 정보", 12: "환경에 미치는 영향",
        13: "폐기시 주의사항", 14: "운송에 필요한 정보", 15: "법적 규제현황", 16: "그 밖의 참고사항",
    }
    return f"{number}. {words[number]}"


def document(section_numbers=range(1, 17)) -> list[str]:
    return [value for number in section_numbers for value in (title(number), f"{number}항 내용")]


def test_builds_b_compatible_sixteen_section_contract():
    result = build_contract("T21-X", lines({1: ["표지"] + document(range(1, 9)), 2: document(range(9, 17)) + ["끝"]}))
    assert result["stats"] == {"found": 16, "msds": 1, "complete": 1, "missing": [{"msds_index": 1, "sections": []}]}
    part = result["msds"][0]
    assert part["pages"] == [1, 2]
    assert part["format"] == "current"
    assert part["sections"]["1"] == {
        "start": "p1:L2", "end": "p1:L3", "method": "title", "semantic_type": "identification"
    }
    assert part["sections"]["8"]["end"] == "p1:L17"
    assert part["sections"]["16"]["end"] == "p2:L17"


def test_marks_missing_section_as_failed():
    result = build_contract("T21-X", lines({1: document([1, 2, 4])}))
    assert result["msds"][0]["sections"]["3"] == {
        "start": None, "end": None, "method": "failed", "semantic_type": "components"
    }
    assert 3 in result["stats"]["missing"][0]["sections"]


def test_splits_multiple_msds_when_section_one_restarts():
    result = build_contract("T21-X", lines({1: document(range(1, 9)), 2: document(range(9, 17)),
                                             3: document(range(1, 9)), 4: document(range(9, 17))}))
    assert result["stats"]["msds"] == 2
    assert result["msds"][0]["pages"] == [1, 2]
    assert result["msds"][1]["pages"] == [3, 4]
    assert result["msds"][1]["sections"]["1"]["start"] == "p3:L1"


def test_skips_consecutive_table_of_contents_titles():
    toc = [title(number) for number in range(1, 17)]
    result = build_contract("T21-X", lines({1: toc, 2: document(range(1, 9)), 3: document(range(9, 17))}))
    assert result["stats"]["msds"] == 1
    assert result["msds"][0]["sections"]["1"]["start"] == "p2:L1"


def test_accepts_repeated_ocr_punctuation_and_english_title():
    result = build_contract("T21-X", lines({1: [
        "13. . 폐기시 주의사항", "내용",
        "14. Transport information", "내용",
        "15. Regulatory information", "내용",
        "16. Other information", "내용",
    ]}))
    sections = result["msds"][0]["sections"]
    assert sections["13"]["start"] == "p1:L1"
    assert sections["14"]["start"] == "p1:L3"
    assert sections["15"]["start"] == "p1:L5"
    assert sections["16"]["start"] == "p1:L7"


def test_detects_legacy_format_and_preserves_original_section_numbers():
    result = build_contract("T21-OLD", lines({1: [
        "1. 화학 제품과 제조회사 정보", "내용",
        "2. 구성 성분의 명칭 및 함유량", "성분 내용",
        "3. 유해 위험성", "유해성 내용",
        "4. 응급조치 요령", "내용",
        "16. 기타 정보", "내용",
    ]}))
    part = result["msds"][0]
    assert part["format"] == "legacy"
    assert part["sections"]["2"] == {
        "start": "p1:L3", "end": "p1:L4", "method": "legacy_title", "semantic_type": "components"
    }
    assert part["sections"]["3"] == {
        "start": "p1:L5", "end": "p1:L6", "method": "legacy_title", "semantic_type": "hazard"
    }
    assert part["sections"]["16"]["semantic_type"] == "other_information"


def test_same_first_title_on_nonconsecutive_pages_starts_new_msds():
    pages = {
        1: document(range(1, 17)),
        3: document(range(1, 17)),
        5: document(range(1, 17)),
    }
    result = build_contract("T21-X", lines(pages))
    assert result["stats"]["msds"] == 3
    assert [part["sections"]["1"]["start"] for part in result["msds"]] == ["p1:L1", "p3:L1", "p5:L1"]


def test_development_ten_have_all_sixteen_sections():
    """현재 C 전처리 실데이터에서 개발용 M/S 10건의 16항 경계를 확인한다."""
    pages_root = ROOT / "data" / "pages" / "version14"
    doc_ids = [
        "T21-M001", "T21-M002", "T21-M004", "T21-M005", "T21-M013",
        "T21-S001", "T21-S003", "T21-S013", "T21-S014", "T21-S016",
    ]
    if any(not (pages_root / doc_id).is_dir() for doc_id in doc_ids):
        raise SkipTest("로컬 version14 개발용 10건 전처리 결과가 없음")
    results = {doc_id: extract_sections(doc_id, pages_root / doc_id) for doc_id in doc_ids}
    assert {doc_id: result["stats"]["missing"] for doc_id, result in results.items()
            if result["stats"]["complete"] != 1} == {}
