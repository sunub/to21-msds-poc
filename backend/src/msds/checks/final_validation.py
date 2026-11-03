"""최종 추출 검사 결과를 손상 없이 요약하고 검수할 항목에 연결한다.

TO21 검증기는 JSON 스키마 검사와 별도다. 그 오류나 실행 예외를 무시한 채
`schema_errors == []`만으로 추출 결과를 통과로 판단하지 않는다.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any

from msds.service.review import SECTION_OF_ROOT, SECTIONS
from msds.checks.validator import run_to21_validator
from msds.common.schema import validate_to21

_FIELD = re.compile(r"^msds\[(\d+)\]\.([A-Za-z_][A-Za-z_0-9]*)(?:\[(\d+)\])?(?:\.|$)")
_ITEM_CODE = re.compile(r"^S(\d+)_")


def _list(obj: dict, name: str, *, required: bool = False) -> list:
    if name not in obj:
        if required:
            raise ValueError(f"검사 결과에 {name}이 없습니다")
        return []
    value = obj[name]
    if not isinstance(value, list):
        raise ValueError(f"검사 결과의 {name}은 배열이어야 합니다")
    return value


def _location(doc: dict, field: Any) -> tuple[int, int] | None:
    """명시된 필드·행의 항만 찾는다. 메시지 문구를 보고 추측하지 않는다."""
    if not isinstance(field, str) or not (match := _FIELD.match(field)):
        return None
    msds_index, root, row_index = match.groups()
    msds_index = int(msds_index)
    docs = doc.get("msds")
    if not isinstance(docs, list) or msds_index >= len(docs) or not isinstance(docs[msds_index], dict):
        return None
    section = SECTION_OF_ROOT.get(root)
    if root in ("extras", "narratives") and row_index is not None:
        rows = docs[msds_index].get(root)
        index = int(row_index)
        if not isinstance(rows, list) or index >= len(rows) or not isinstance(rows[index], dict):
            return None
        row = rows[index]
        if root == "extras":
            section = row.get("section_no")
        else:
            code = row.get("item_code")
            item = _ITEM_CODE.match(code) if isinstance(code, str) else None
            section = int(item.group(1)) if item else None
    if isinstance(section, bool) or not isinstance(section, int) or not 1 <= section <= 16:
        return None
    return msds_index, section


def summarize_checks(doc: dict, checks: dict) -> dict:
    """기존 추출 결과를 그대로 두고 최종 검증 요약을 계산한다.

    `status`는 `passed`, `needs_review`, `invalid` 중 하나다. 스키마 오류,
    TO21 오류·예외, 또는 실패 항목이 하나라도 있으면 `invalid`이다.
    각 MSDS에서 9개 추출 항의 검사 기록이 완전하지 않으면 `invalid`다.
    공식 검증 결과나 스키마 검사 기록이 없으면 통과로 간주하지 않고 예외를 낸다.
    `unmapped_findings`는 항을 확정할 근거가 없는 공식 검증 결과다.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("msds"), list):
        raise ValueError("추출 문서의 msds 배열이 없습니다")
    if not isinstance(checks, dict):
        raise ValueError("검사 결과는 객체여야 합니다")
    schema_errors = _list(checks, "schema_errors", required=True)
    validator = _list(checks, "to21_validator", required=True)
    sections = _list(checks, "sections")
    existing_review = _list(checks, "needs_review")

    review: set[tuple[int, int]] = set()
    for row in existing_review:
        if (isinstance(row, dict) and isinstance(row.get("msds_index"), int)
                and not isinstance(row.get("msds_index"), bool) and row["msds_index"] >= 0
                and isinstance(row.get("section"), int) and not isinstance(row.get("section"), bool)
                and 1 <= row["section"] <= 16):
            review.add((row["msds_index"], row["section"]))
        else:
            raise ValueError("검수 필요 항목의 문서 번호 또는 항 번호가 잘못됐습니다")

    expected = {(index, section) for index in range(len(doc["msds"])) for section in SECTIONS}
    seen: set[tuple[int, int]] = set()
    invalid_section_records = 0
    failed_sections = []
    for row in sections:
        if not isinstance(row, dict) or not isinstance(row.get("ok"), bool):
            raise ValueError("항목별 검사에 유효한 성공 여부가 없습니다")
        index, section = row.get("msds_index"), row.get("section")
        if (isinstance(index, bool) or not isinstance(index, int) or index < 0
                or isinstance(section, bool) or not isinstance(section, int)
                or (index, section) not in expected or (index, section) in seen):
            invalid_section_records += 1
            continue
        seen.add((index, section))
        if not row["ok"]:
            failed_sections.append({"msds_index": index, "section": section})
            review.add((index, section))

    levels: Counter[str] = Counter()
    unmapped: list[dict] = []
    for finding in validator:
        if not isinstance(finding, dict):
            raise ValueError("공식 검증 결과의 각 항목은 객체여야 합니다")
        level = finding.get("level")
        # 낯선 결과나 실행 예외는 오류 없이 통과한 것으로 취급하지 않는다.
        category = level if level in ("오류", "경고") else "예외"
        levels[category] += 1
        location = _location(doc, finding.get("field"))
        if location is None:
            unmapped.append({"level": level, "rule": finding.get("rule"), "field": finding.get("field")})
        else:
            review.add(location)

    errors = len(schema_errors) + levels["오류"] + levels["예외"] + len(failed_sections)
    missing_sections = expected - seen
    invalid_msds = not doc["msds"] or any(not isinstance(item, dict) for item in doc["msds"])
    if errors or invalid_msds or invalid_section_records or missing_sections:
        status = "invalid"
    elif levels["경고"] or review:
        status = "needs_review"
    else:
        status = "passed"
    return {
        "status": status,
        "schema_errors": len(schema_errors),
        "validator_errors": levels["오류"],
        "validator_warnings": levels["경고"],
        "validator_exceptions": levels["예외"],
        "failed_sections": failed_sections,
        "missing_sections": [{"msds_index": i, "section": no} for i, no in sorted(missing_sections)],
        "invalid_section_records": invalid_section_records,
        "invalid_msds": invalid_msds,
        "needs_review": [{"msds_index": i, "section": no} for i, no in sorted(review)],
        "unmapped_findings": unmapped,
    }


def validate_document(doc: dict, checks: dict, *, schema_validator=None, semantic_validator=None) -> tuple[dict, dict]:
    """현재 추출값을 다시 검사하고 (새 검사 기록, 요약)을 돌려준다.

    검수에서 값이 수정되었다면 기존 validator 결과를 재사용하지 않고 이 함수를
    수정분을 반영한 문서에 호출한다. 원본 문서와 이전 검사 기록은 변경하지 않는다.
    검사기 예외와 잘못된 반환값은 통과가 아니라 오류로 기록한다.
    기존 항별 검사 및 검수 필요 정보는 명시적 재검수 전까지 보존한다.
    """
    if not isinstance(checks, dict):
        raise ValueError("검사 결과는 객체여야 합니다")
    result = copy.deepcopy(checks)
    schema_validator = schema_validator or validate_to21
    semantic_validator = semantic_validator or run_to21_validator
    try:
        schema_errors = schema_validator(copy.deepcopy(doc))
        if not isinstance(schema_errors, list):
            raise TypeError("스키마 검사 결과는 배열이어야 합니다")
        result["schema_errors"] = schema_errors
    except Exception as exc:
        result["schema_errors"] = [f"스키마 검사 실행 실패: {type(exc).__name__}"]
    try:
        findings = semantic_validator(copy.deepcopy(doc))
        if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
            raise TypeError("공식 검증 결과가 올바르지 않습니다")
        result["to21_validator"] = findings
    except Exception as exc:
        result["to21_validator"] = [{"level": "예외", "rule": None, "field": None,
                                      "message": f"검증기 실행 실패: {type(exc).__name__}"}]
    summary = summarize_checks(doc, result)
    result["needs_review"] = copy.deepcopy(summary["needs_review"])
    return result, summary
