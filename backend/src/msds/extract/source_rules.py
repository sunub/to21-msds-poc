"""원문 줄로 확인하는 고침 (B, ADR-029).

펼친 TO21 msds 항목을 문서의 원문 줄과 맞춰 본다. 원문 글자로 확인되는 값만 고친다.
expand.to_to21이 MSDS마다 expand_msds 뒤, A의 apply_conventions 앞에 부른다.
규칙은 글의 꼴로만 정한다. 문서 번호로 나누지 않는다.
- H·P 코드: 문서 글에 그 종류의 코드 꼴이 하나도 없으면 모델이 쓴 코드를 비운다. 문장은 둔다.
  2항 그림(이미지 입력)에서만 읽은 코드를 지우지 않으려고, 글에 코드가 전혀 없는 문서만 고친다.
- 개정 횟수: '개정 횟수 … : N' 줄로 meta.revision_no를 정한다. 'N-N'이면 비운다.
- 메타 값 없음: meta의 글자 칸이 자료없음·해당없음·미기재(공백 무시)이면 비운다.
- 전화번호: 연락처가 원문에 그대로 없고, 숫자가 같은 원문 조각이 있으면 그 조각으로 바꾼다.
"""
from __future__ import annotations

import re

from msds.extract.inputs import Line

_NO_VALUE = ("자료없음", "해당없음", "미기재")      # 값 없는 칸 (expand._NO_VALUE와 같다)
# 앞뒤가 다른 영문·숫자가 아닌 코드 꼴. H코드는 TO21 접미 문자(H360FD, H361d)까지 코드로 본다.
_CODE_FORMS = {
    "h_statements": ("H", re.compile(r"(?<![A-Za-z0-9])(?:EU)?H\d{3}[A-Za-z]{0,2}(?![A-Za-z0-9])")),
    "p_statements": ("P", re.compile(r"(?<![A-Za-z0-9])P\d{3}(?![A-Za-z0-9])")),
}
_REVISION = re.compile(r"개정\s*횟수[^:：]*[:：](?P<value>.*)$")
_REVISION_NO = re.compile(r"(\d+)\s*회?")
_REVISION_PAIR = re.compile(r"\d+\s*-\s*\d+")
_PHONE_GAP = r"[\s\-()]*"     # 전화번호 숫자 사이에 올 수 있는 글자
_PHONE_MIN = 7                # 원문 조각의 최소 글자 수


def _clear_codes(item: dict, text: str) -> list[str]:
    changes = []
    for key, (label, form) in _CODE_FORMS.items():
        rows = [s for s in item["hazard"][key] if s.get("code") is not None]
        if rows and not form.search(text):
            for s in rows:
                s["code"] = None
            changes.append(f"{label} 코드 {len(rows)}개 비움: 문서 글에 {label} 코드 꼴이 없음")
    return changes


def _revision_no(item: dict, lines: list[Line]) -> list[str]:
    line, m = next(((l, m) for l in lines if (m := _REVISION.search(l.text))), (None, None))
    if m is None:
        return []
    value = m["value"].split(",")[0].strip()
    if n := _REVISION_NO.fullmatch(value):
        new = int(n.group(1))
    elif _REVISION_PAIR.fullmatch(value):
        new = None
    else:
        return []
    old = item["meta"]["revision_no"]
    if old == new:
        return []
    item["meta"]["revision_no"] = new
    return [f"meta.revision_no {old!r} → {new!r} ({line.id})"]


def _meta_no_value(item: dict) -> list[str]:
    changes = []
    for k, v in item["meta"].items():
        if isinstance(v, str) and re.sub(r"\s+", "", v) in _NO_VALUE:
            item["meta"][k] = None
            changes.append(f"meta.{k} {v!r} → None")
    return changes


def _phone_fragment(value: str, lines: list[Line]) -> str | None:
    """숫자만 남기면 value와 같은 원문 조각(숫자로 시작·끝나고 사이에 숫자·'-'·공백·괄호만, 7자 이상)."""
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    form = re.compile(r"(?<!\d)" + _PHONE_GAP.join(digits) + r"(?!\d)")
    for line in lines:
        for m in form.finditer(line.text):
            if len(m.group(0).strip()) >= _PHONE_MIN:
                return m.group(0).strip()
    return None


def _phones(item: dict, lines: list[Line], text: str) -> list[str]:
    changes = []
    for company in item["companies"]:
        for c in company.get("contacts") or []:
            value = c.get("value")
            if not isinstance(value, str) or value in text:
                continue
            if (frag := _phone_fragment(value, lines)) is not None:
                c["value"] = frag
                changes.append(f"연락처 {value!r} → {frag!r}")
    return changes


def apply_source_rules(item: dict, lines: list[Line]) -> list[str]:
    """펼친 TO21 msds 항목 하나를 원문 줄로 확인해 바로 고친다. 고친 내용(사람이 읽는 한 줄씩)을 돌려준다.
    lines는 문서 전체 줄이다."""
    text = "\n".join(l.text for l in lines)
    return (_clear_codes(item, text) + _revision_no(item, lines) + _meta_no_value(item)
            + _phones(item, lines, text))
