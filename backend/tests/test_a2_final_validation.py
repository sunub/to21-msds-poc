"""최종 TO21 검증 오류가 추출 성공으로 가려지지 않는지 검증한다."""
import copy

import pytest

from msds.checks.final_validation import summarize_checks, validate_document


def test_validator_errors_in_extras_are_mapped_without_changing_source():
    doc = {"msds": [{"extras": [{"section_no": 3}, {"section_no": 12}, {"section_no": 14}]}]}
    checks = {"schema_errors": [], "sections": [{"msds_index": 0, "section": 9, "ok": True}],
              "needs_review": [{"msds_index": 0, "section": 9}],
              "to21_validator": [
                  {"level": "오류", "rule": "V22", "field": "msds[0].extras[0]", "message": "값 없음"},
                  {"level": "오류", "rule": "V22", "field": "msds[0].extras[1]", "message": "값 없음"},
                  {"level": "오류", "rule": "V22", "field": "msds[0].extras[2].title_raw", "message": "제목 없음"},
                  {"level": "경고", "rule": "V14", "field": "msds[0].evidence", "message": "근거 없음"},
              ]}
    before_doc, before_checks = copy.deepcopy(doc), copy.deepcopy(checks)
    result = summarize_checks(doc, checks)
    assert result["status"] == "invalid"
    assert (result["validator_errors"], result["validator_warnings"], result["schema_errors"]) == (3, 1, 0)
    assert result["needs_review"] == [{"msds_index": 0, "section": x} for x in (3, 9, 12, 14)]
    assert result["unmapped_findings"] == [{"level": "경고", "rule": "V14", "field": "msds[0].evidence"}]
    assert doc == before_doc and checks == before_checks


def test_warning_and_unmapped_findings_remain_visible():
    checks = {"schema_errors": [], "to21_validator": [{"level": "경고", "rule": "V14", "field": None}]}
    result = summarize_checks({"msds": [{}]}, checks)
    assert result["status"] == "needs_review"
    assert result["validator_warnings"] == 1
    assert result["unmapped_findings"][0]["field"] is None


@pytest.mark.parametrize("checks", [
    {"schema_errors": ["형식 오류"], "to21_validator": []},
    {"schema_errors": [], "to21_validator": [{"level": "예외", "message": "검증기 실행 실패"}]},
    {"schema_errors": [], "to21_validator": [{"level": "알 수 없음", "field": None}]},
    {"schema_errors": [], "to21_validator": [], "sections": [{"msds_index": 0, "section": 2, "ok": False}]},
])
def test_any_error_exception_or_failed_section_blocks_validation_pass(checks):
    assert summarize_checks({"msds": [{}]}, checks)["status"] == "invalid"


@pytest.mark.parametrize("checks", [
    {},
    {"schema_errors": [], "to21_validator": None},
    {"schema_errors": None, "to21_validator": []},
    {"schema_errors": [], "to21_validator": [], "sections": [{"ok": None}]},
    {"schema_errors": [], "to21_validator": ["잘못된 결과"]},
])
def test_missing_or_malformed_checks_never_appear_valid(checks):
    with pytest.raises(ValueError):
        summarize_checks({"msds": [{}]}, checks)


def test_valid_check_passes_and_canonical_root_maps_to_section():
    doc = {"msds": [{"components": [{"cas_no": "0000-00-0"}]}]}
    checks = {"schema_errors": [], "to21_validator": []}
    assert summarize_checks(doc, checks)["status"] == "passed"
    checks["to21_validator"] = [{"level": "오류", "rule": "V01", "field": "msds[0].components[0].cas_no"}]
    assert summarize_checks(doc, checks)["needs_review"] == [{"msds_index": 0, "section": 3}]


def test_changed_values_are_revalidated_without_mutating_existing_records():
    doc = {"msds": [{"extras": [{"section_no": 12}]}]}
    original_checks = {"schema_errors": ["오래된 오류"], "to21_validator": [],
                       "sections": [{"msds_index": 0, "section": 3, "ok": True}], "needs_review": []}
    before_doc, before_checks = copy.deepcopy(doc), copy.deepcopy(original_checks)
    examined = []

    def validate_schema(value):
        examined.append(value)
        return []

    def validate_semantics(value):
        examined.append(value)
        return [{"level": "오류", "rule": "V22", "field": "msds[0].extras[0]"}]

    checks, summary = validate_document(doc, original_checks, schema_validator=validate_schema,
                                        semantic_validator=validate_semantics)
    assert examined == [doc, doc]
    assert checks["schema_errors"] == [] and summary["status"] == "invalid"
    assert checks["needs_review"] == [{"msds_index": 0, "section": 12}]
    assert doc == before_doc and original_checks == before_checks


def test_validator_exceptions_or_invalid_return_values_do_not_claim_success():
    def raises(_):
        raise RuntimeError("사적인 메시지는 출력하지 않음")

    checks, summary = validate_document({"msds": []}, {}, schema_validator=raises,
                                        semantic_validator=lambda _: None)
    assert summary["status"] == "invalid"
    assert summary["schema_errors"] == 1 and summary["validator_exceptions"] == 1
    assert checks["schema_errors"] == ["스키마 검사 실행 실패: RuntimeError"]
    assert checks["to21_validator"][0]["level"] == "예외"


def test_validators_cannot_change_original_or_each_others_input():
    doc = {"msds": [{"product": {"name": "테스트"}}]}

    def schema(value):
        value["msds"][0]["product"]["name"] = "변경"
        return []

    def semantic(value):
        assert value["msds"][0]["product"]["name"] == "테스트"
        value["msds"].clear()
        return []

    _, summary = validate_document(doc, {}, schema_validator=schema, semantic_validator=semantic)
    assert summary["status"] == "passed"
    assert doc["msds"][0]["product"]["name"] == "테스트"
