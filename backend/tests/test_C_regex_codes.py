from msds.checks.regex_codes import (
    compare,
    find_codes,
    normalize_cas,
    normalize_h,
    p_type,
    scan_codes,
    valid_cas_checksum,
)
from msds.common.models import ExtractionDoc


def test_v06_normalization_and_checksum():
    assert normalize_h("H 302 + H 332") == "H302+H332"
    assert normalize_h("H361d") == "H361d"
    assert normalize_cas("7664 ‐ 93 ‐ 9") == "7664-93-9"
    assert valid_cas_checksum("7664-93-9") is True
    assert valid_cas_checksum("7664-93-8") is False
    assert p_type("P280") == "예방"
    assert p_type("P501") == "폐기"


def test_find_all_number_plates_and_keep_evidence():
    pages = {1: "\n".join([
        "L001 H 302 + H 332 삼키거나 흡입하면 유해함",
        "L002 H361d ** 태아에 손상을 일으킬 것으로 의심됨",
        "L003 EUH066 반복 노출 시 피부 건조",
        "L004 R36/38 눈과 피부에 자극",
        "L005 P 301 + P 310 즉시 의료기관에 연락",
        "L006 CAS 7664 ‐ 93 ‐ 9",
        "L007 CAS 7664-93-8",
        "L008 UN No. 1830",
    ])}
    found = find_codes(pages)
    assert found == {
        "cas": {"7664-93-9", "7664-93-8"},
        "h": {"H302+H332", "H361d", "EUH066", "R36/38"},
        "p": {"P301+P310"},
        "un": {"1830"},
    }
    details = scan_codes(pages)
    h361 = next(item for item in details["h"] if item["value"] == "H361d")
    assert h361["mark"] == "**"
    assert h361["occurrences"][0]["line"] == "L002"
    bad_cas = next(item for item in details["cas"] if item["value"] == "7664-93-8")
    assert bad_cas["checksum_valid"] is False


def test_duplicate_values_merge_occurrences():
    details = scan_codes({1: "L001 H225\nL002 H225", 2: "L001 H225"})
    assert len(details["h"]) == 1
    assert len(details["h"][0]["occurrences"]) == 3


def test_un_label_and_value_can_be_on_adjacent_lines():
    details = scan_codes({7: "L044 가. 유엔번호(IMDG CODE/IATA DGR)\nL045 - 1830"})
    assert details["un"] == [{
        "value": "1830",
        "occurrences": [{
            "page": "p007", "line": "L045", "raw": "1830", "source_text": "- 1830",
        }],
    }]


def test_compare_reads_v06_p_and_transport_fields():
    doc = {"msds": [{
        "components": [{"cas_no": "7664-93-9"}],
        "hazard": {
            "h_statements": [{"code": "H302+H332"}],
            "p_statements": [{"code": "P280"}],
        },
        "transport": [{"un_no": "1830"}],
    }]}
    found = {"cas": {"7664-93-9"}, "h": {"H302+H332"}, "p": {"P280"}, "un": {"1830"}}
    assert compare(doc, found) == []
    found["h"].add("H225")
    assert compare(doc, found) == [{
        "kind": "h", "source_only": ["H225"], "model_only": [], "review": True,
    }]


def test_common_model_accepts_v06_p_statements_and_transport():
    parsed = ExtractionDoc.model_validate({"msds": [{
        "hazard": {"p_statements": [{"code": "P280", "type": "예방"}]},
        "transport": [{"un_no": "1830"}],
    }]})
    assert parsed.msds[0].hazard.p_statements[0].code == "P280"
    assert parsed.msds[0].transport[0].un_no == "1830"
