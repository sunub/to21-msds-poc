"""원문의 CAS·H·P·UN 번호판을 찾아 모델 결과와 비교한다 (역할 C, C-5).

정규식은 투표에 넣지 않고 형식 검사로 쓴다. 정규식이 찾은 코드 목록과 모델 결과가 다르면 사람 검토로 보낸다.
TO21 v0.6의 R02(CAS), R05(H/P), R09(UN), R21(H 변형)을 따른다.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-", "－": "-"})
_LINE = re.compile(r"^\s*(L\d{3,})\s+(.*)$")

# 공개 상수는 다른 모듈에서 형식 안내에 재사용할 수 있다.
CAS_PATTERN = r"(?<!\d)\d{2,7}\s*[-‐‑‒–—−－]\s*\d{2}\s*[-‐‑‒–—−－]\s*\d(?!\d)"
H_PATTERN = r"(?<![A-Z0-9])(?:EUH\s*\d{3}|H\s*\d{3}[A-Za-z]{0,2}|R\s*\d{1,2}(?:\s*/\s*\d{1,2})*)(?:\s*\+\s*(?:EUH\s*\d{3}|H\s*\d{3}[A-Za-z]{0,2}))*"
P_PATTERN = r"(?<![A-Z0-9])P\s*\d{3}(?:\s*\+\s*P\s*\d{3})*"
UN_PATTERN = r"(?<![A-Z0-9])(?:UN|유엔)\s*(?:NO\.?|번호)?\s*[:：-]?\s*(\d{4})(?!\d)"

_CAS_RE = re.compile(CAS_PATTERN, re.IGNORECASE)
_H_RE = re.compile(H_PATTERN, re.IGNORECASE)
_P_RE = re.compile(P_PATTERN, re.IGNORECASE)
_UN_RE = re.compile(UN_PATTERN, re.IGNORECASE)
_UN_LABEL_RE = re.compile(r"(?:UN|유엔)\s*(?:NO\.?|번호)", re.IGNORECASE)
_FOUR_DIGITS_RE = re.compile(r"^\s*[-–—:：|]?\s*(\d{4})\s*$")
_MARK_RE = re.compile(r"\s*(\*{1,3})")


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").translate(_DASHES)


def normalize_cas(raw: str) -> str:
    """R02: 공백과 전각 하이픈을 정리한다."""
    return re.sub(r"\s+", "", _nfkc(raw))


def valid_cas_checksum(value: str) -> bool:
    """V01: 마지막 숫자가 앞 숫자의 뒤쪽 가중합 mod 10인지 검사한다."""
    if not re.fullmatch(r"\d{2,7}-\d{2}-\d", value or ""):
        return False
    body, check = value.rsplit("-", 1)
    digits = body.replace("-", "")
    total = sum(int(digit) * weight for weight, digit in enumerate(reversed(digits), start=1))
    return total % 10 == int(check)


def normalize_h(raw: str) -> str:
    """R05/R21: 접두사는 대문자로, 공백은 제거하고 결합은 유지한다."""
    parts = re.split(r"\s*\+\s*", _nfkc(raw).strip())
    normalized = []
    for part in parts:
        part = re.sub(r"\s+", "", part)
        upper = part.upper()
        if upper.startswith("EUH"):
            part = "EUH" + part[3:]
        elif upper.startswith("H"):
            part = "H" + part[1:]
        elif upper.startswith("R"):
            part = "R" + part[1:]
        normalized.append(part)
    return "+".join(normalized)


def normalize_p(raw: str) -> str:
    return "+".join("P" + re.sub(r"\s+", "", part)[1:] for part in re.split(r"\s*\+\s*", _nfkc(raw).strip()))


def p_type(code: str) -> str | None:
    """R05/V08: 첫 P코드의 첫 숫자로 유형을 정한다."""
    return {"1": "일반", "2": "예방", "3": "대응", "4": "저장", "5": "폐기"}.get(code[1:2])


def _system(code: str) -> str:
    if code.startswith("EUH"):
        return "EUH"
    if code.startswith("R"):
        return "R"
    return "GHS"


def _line_parts(page: int, raw_line: str, fallback: int) -> tuple[str, str]:
    match = _LINE.match(raw_line)
    return (match.group(1), match.group(2)) if match else (f"L{fallback:03d}", raw_line)


def scan_codes(page_texts: dict[int, str]) -> dict[str, list[dict[str, Any]]]:
    """번호판과 모든 출현 위치를 찾는다. 같은 정규화 값은 객체 하나로 합친다."""
    grouped: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in ("cas", "h", "p", "un")}

    def add(kind: str, value: str, raw: str, page: int, line: str, source: str, **extra: Any) -> None:
        item = grouped[kind].setdefault(value, {"value": value, **extra, "occurrences": []})
        item["occurrences"].append({"page": f"p{page:03d}", "line": line, "raw": raw, "source_text": source})

    for page in sorted(page_texts):
        raw_lines = page_texts[page].splitlines()
        for number, raw_line in enumerate(raw_lines, start=1):
            line, text = _line_parts(page, raw_line, number)
            normalized_text = _nfkc(text)
            for match in _CAS_RE.finditer(normalized_text):
                raw = match.group(0)
                value = normalize_cas(raw)
                add("cas", value, raw, page, line, text, checksum_valid=valid_cas_checksum(value))
            for match in _H_RE.finditer(normalized_text):
                raw = match.group(0).strip()
                value = normalize_h(raw)
                tail = normalized_text[match.end():]
                mark_match = _MARK_RE.match(tail)
                add("h", value, raw, page, line, text, system=_system(value), mark=mark_match.group(1) if mark_match else None)
            for match in _P_RE.finditer(normalized_text):
                raw = match.group(0).strip()
                value = normalize_p(raw)
                add("p", value, raw, page, line, text, type=p_type(value))
            un_matches = list(_UN_RE.finditer(normalized_text))
            for match in un_matches:
                add("un", match.group(1), match.group(0).strip(), page, line, text)
            # 표·목록에서 라벨과 값이 줄바꿈된 경우: "유엔번호" 다음 줄의 정확한 4자리만 허용한다.
            if not un_matches and _UN_LABEL_RE.search(normalized_text) and number < len(raw_lines):
                next_line, next_text = _line_parts(page, raw_lines[number], number + 1)
                value_match = _FOUR_DIGITS_RE.fullmatch(_nfkc(next_text))
                if value_match:
                    add("un", value_match.group(1), value_match.group(1), page, next_line, next_text)
    return {kind: list(values.values()) for kind, values in grouped.items()}


def find_codes(page_texts: dict[int, str]) -> dict[str, set[str]]:
    """기존 비교 인터페이스: {cas/h/p/un: 정규화 값 집합}."""
    return {kind: {item["value"] for item in items} for kind, items in scan_codes(page_texts).items()}


def _iter_rows(value: Any) -> Iterable[dict]:
    return value if isinstance(value, list) else ()


def model_codes(doc: dict) -> dict[str, set[str]]:
    """TO21 v0.6 결과에서 번호판 필드만 읽는다."""
    out: dict[str, set[str]] = {kind: set() for kind in ("cas", "h", "p", "un")}
    for msds in doc.get("msds") or []:
        for row in _iter_rows(msds.get("components")):
            if row.get("cas_no"):
                out["cas"].add(normalize_cas(str(row["cas_no"])))
        hazard = msds.get("hazard") or {}
        for row in _iter_rows(hazard.get("h_statements")):
            if row.get("code"):
                out["h"].add(normalize_h(str(row["code"])))
        for row in _iter_rows(hazard.get("p_statements")):
            if row.get("code"):
                out["p"].add(normalize_p(str(row["code"])))
        for row in _iter_rows(msds.get("transport")):
            if row.get("un_no"):
                value = re.sub(r"\D", "", _nfkc(str(row["un_no"])))
                if len(value) == 4:
                    out["un"].add(value)
    return out


def compare(doc: dict, found: dict[str, set[str]]) -> list[dict]:
    """모델과 원문의 차이가 있는 종류만 돌려준다."""
    model = model_codes(doc)
    differences = []
    for kind in ("cas", "h", "p", "un"):
        source_values = set(found.get(kind, set()))
        model_values = model[kind]
        source_only = sorted(source_values - model_values)
        model_only = sorted(model_values - source_values)
        if source_only or model_only:
            differences.append({
                "kind": kind,
                "source_only": source_only,
                "model_only": model_only,
                "review": True,
            })
    return differences
