"""Deterministic C-role preprocessing for MSDS page artifacts.

This module deliberately does not call an LLM.  It consumes the 200-DPI
images and PDF/PaddleOCR text produced by version2 and creates traceable
section, code and row artifacts for the downstream JSON extractor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


_ENGLISH_SECTION_TITLES = {
    1: "identification",
    2: "hazards identification",
    3: "composition/information on ingredients",
    4: "first-aid measures",
    5: "fire-fighting measures",
    6: "accidental release measures",
    7: "handling and storage",
    8: "exposure controls/personal protection",
    9: "physical and chemical properties",
    10: "stability and reactivity",
    11: "toxicological information",
    12: "ecological information",
    13: "disposal considerations",
    14: "transport information",
    15: "regulatory information",
    16: "other information",
}

_SYNONYMS_PATH = Path(__file__).resolve().parents[4] / "to21" / "v0.6" / "TO21_MSDS_동의어사전_v0.6.json"


def _load_section_titles() -> dict[int, tuple[str, ...]]:
    """Build the per-section title variants from the TO21 v0.6 synonym dictionary.

    The dictionary's own note says comparisons must ignore whitespace,
    punctuation and middle dots, which is what caused model-side mismatches
    on table headers that only differ by spacing (e.g. "CAS 번호" vs
    "CAS번호"). We fall back to a single hardcoded Korean/English title per
    section if the dictionary cannot be loaded, so detection degrades rather
    than breaking outright.
    """
    titles: dict[int, tuple[str, ...]] = {}
    try:
        data = json.loads(_SYNONYMS_PATH.read_text(encoding="utf-8"))
        for key, variants in data.get("sections", {}).items():
            titles[int(key)] = tuple(variants) + (_ENGLISH_SECTION_TITLES.get(int(key), ""),)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        pass
    for number, english in _ENGLISH_SECTION_TITLES.items():
        if number not in titles:
            titles[number] = (english,)
    return titles


SECTION_TITLES = _load_section_titles()

_HEADER = re.compile(r"^\s*(?:제\s*)?(1[0-6]|[1-9])\s*[.．、):：-]\s*(.+?)\s*$", re.I)
_EN_HEADER = re.compile(r"^\s*(?:section\s*)?(1[0-6]|[1-9])\s*[.．、):：-]?\s+(.+?)\s*$", re.I)
_TOC_PAGE = re.compile(r"(?:\.{2,}|…{2,}|\s{3,})\s*\d+\s*$")

_H_CODE = re.compile(r"(?<![A-Z0-9])H\s*(\d{3})(?!\d)", re.I)
_P_CODE = re.compile(r"(?<![A-Z0-9])P\s*(\d{3})(?!\d)", re.I)
_CAS = re.compile(r"(?<!\d)(\d{2,7}-\d{2}-\d)(?!\d)")
_UN = re.compile(r"(?<![A-Z0-9])UN\s*[-:]?\s*(\d{4})(?!\d)", re.I)


def _compact(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", value.casefold())


def _title_matches(number: int, title: str) -> bool:
    compact = _compact(title)
    return any(_compact(candidate) in compact or compact in _compact(candidate)
               for candidate in SECTION_TITLES[number])


def detect_section_header(line: str) -> int | None:
    """Return a statutory section number, rejecting likely TOC entries."""
    if _TOC_PAGE.search(line):
        return None
    match = _HEADER.match(line) or _EN_HEADER.match(line)
    if not match:
        return None
    number = int(match.group(1))
    return number if _title_matches(number, match.group(2)) else None


@dataclass
class Section:
    document_index: int
    number: int
    title_line: str
    start_page: int
    end_page: int
    lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_index": self.document_index,
            "section": self.number,
            "title": self.title_line,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "text": "\n".join(self.lines).strip(),
        }


def split_sections(pages: list[tuple[int, str]]) -> tuple[list[Section], list[dict[str, Any]]]:
    """Split pages into sections and detect a new MSDS when numbering restarts."""
    sections: list[Section] = []
    events: list[dict[str, Any]] = []
    current: Section | None = None
    document_index = 1
    seen: set[int] = set()

    for page, text in pages:
        for line_no, raw in enumerate(text.splitlines(), start=1):
            line = raw.rstrip()
            number = detect_section_header(line)
            if number is not None:
                # A repeated section 1 after later sections is a strong multi-MSDS signal.
                if number == 1 and seen and max(seen) >= 8:
                    document_index += 1
                    seen = set()
                    events.append({
                        "type": "new_msds",
                        "document_index": document_index,
                        "page": page,
                        "line": line_no,
                        "evidence": line,
                    })
                if current is not None:
                    sections.append(current)
                current = Section(document_index, number, line, page, page, [line])
                seen.add(number)
                continue
            if current is not None:
                current.lines.append(line)
                current.end_page = page
    if current is not None:
        sections.append(current)
    return sections, events


def extract_codes(pages: list[tuple[int, str]], context_radius: int = 1) -> list[dict[str, Any]]:
    """Extract codes with page, line and nearby source evidence."""
    patterns = (("H", _H_CODE), ("P", _P_CODE), ("CAS", _CAS), ("UN", _UN))
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for page, text in pages:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            for kind, pattern in patterns:
                for match in pattern.finditer(line):
                    raw = match.group(1)
                    value = f"{kind}{raw}" if kind in {"H", "P"} else (f"UN {raw}" if kind == "UN" else raw)
                    key = (kind, value, page, index + 1)
                    if key in seen:
                        continue
                    seen.add(key)
                    start = max(0, index - context_radius)
                    end = min(len(lines), index + context_radius + 1)
                    found.append({
                        "type": kind,
                        "value": value,
                        "page": page,
                        "line": index + 1,
                        "source_line": line,
                        "context": "\n".join(lines[start:end]),
                    })
    return found


def group_rows(page_json: dict[str, Any], y_tolerance: float = 12.0) -> list[dict[str, Any]]:
    """Group coordinate entries into rows; retain every source item for audit."""
    entries = [entry for entry in page_json.get("entries", []) if entry.get("text") and entry.get("bbox")]
    entries.sort(key=lambda item: ((item["bbox"][1] + item["bbox"][3]) / 2, item["bbox"][0]))
    rows: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for entry in entries:
        center = (entry["bbox"][1] + entry["bbox"][3]) / 2
        if not rows or abs(center - centers[-1]) > y_tolerance:
            rows.append([entry])
            centers.append(center)
        else:
            rows[-1].append(entry)
            centers[-1] = sum((e["bbox"][1] + e["bbox"][3]) / 2 for e in rows[-1]) / len(rows[-1])
    output = []
    for row_index, row in enumerate(rows, start=1):
        row.sort(key=lambda item: item["bbox"][0])
        output.append({
            "row": row_index,
            "text": " | ".join(item["text"].strip() for item in row),
            "cells": row,
        })
    return output


def load_pages(input_dir: Path) -> list[tuple[int, str]]:
    pages = []
    for path in sorted(input_dir.glob("p[0-9][0-9][0-9].txt")):
        pages.append((int(path.stem[1:]), path.read_text(encoding="utf-8")))
    return pages


def diagnostics(sections: list[Section], expected_msds: int | None = None) -> dict[str, Any]:
    document_ids = sorted({section.document_index for section in sections})
    detected_msds = len(document_ids)
    by_document: list[dict[str, Any]] = []
    for index in document_ids:
        numbers = [section.number for section in sections if section.document_index == index]
        unique = sorted(set(numbers))
        missing = [number for number in range(1, 17) if number not in unique]
        duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
        out_of_order = any(right < left for left, right in zip(numbers, numbers[1:]))
        by_document.append({
            "document_index": index,
            "detected_sections": numbers,
            "missing_sections": missing,
            "duplicate_sections": duplicates,
            "out_of_order": out_of_order,
            "passed": not missing and not duplicates and not out_of_order,
        })
    return {
        "detected_msds_count": detected_msds,
        "expected_msds_count": expected_msds,
        "msds_count_matches": expected_msds is None or detected_msds == expected_msds,
        "documents": by_document,
        "passed": bool(by_document)
        and all(item["passed"] for item in by_document)
        and (expected_msds is None or detected_msds == expected_msds),
    }


def process_document(input_dir: Path, output_dir: Path, expected_msds: int | None = None) -> dict[str, Any]:
    pages = load_pages(input_dir)
    if not pages:
        raise ValueError(f"페이지 TXT를 찾을 수 없습니다: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    sections, boundaries = split_sections(pages)
    codes = extract_codes(pages)
    rows: dict[str, list[dict[str, Any]]] = {}
    for page, _ in pages:
        detail_path = input_dir / f"p{page:03d}.json"
        if detail_path.exists():
            rows[f"p{page:03d}"] = group_rows(json.loads(detail_path.read_text(encoding="utf-8")))
    checks = diagnostics(sections, expected_msds)
    result = {
        "input": str(input_dir),
        "page_count": len(pages),
        "method": "version2 PDF text + PaddleOCR; deterministic post-processing; no LLM",
        "boundaries": boundaries,
        "sections": [section.as_dict() for section in sections],
        "codes": codes,
        "diagnostics": checks,
    }
    (output_dir / "sections.json").write_text(json.dumps(result["sections"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "codes.json").write_text(json.dumps(codes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "table_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "diagnostics.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_report(output_dir / "report.md", input_dir.name, result, rows)
    return result


def _write_report(path: Path, doc_id: str, result: dict[str, Any], rows: dict[str, Any]) -> None:
    checks = result["diagnostics"]
    counts: dict[str, int] = {kind: 0 for kind in ("H", "P", "CAS", "UN")}
    for item in result["codes"]:
        counts[item["type"]] += 1
    lines = [
        f"# {doc_id} C 전처리 결과\n\n",
        "- 입력 방식: 200 DPI 이미지 + PDF 텍스트/PaddleOCR\n",
        "- LLM/VLM: 사용 안 함\n",
        f"- 페이지: {result['page_count']}\n",
        f"- 탐지 MSDS: {checks['detected_msds_count']} / 기대 {checks['expected_msds_count']}\n",
        f"- 분할 판정: {'통과' if checks['passed'] else '검토 필요'}\n",
        f"- 코드: H {counts['H']} / P {counts['P']} / CAS {counts['CAS']} / UN {counts['UN']}\n",
        f"- 좌표 행 묶기: {len(rows)}페이지\n\n",
        "## 문서별 16항 점검\n\n",
        "| MSDS | 탐지 항목 | 누락 | 중복 | 순서 오류 | 판정 |\n",
        "|---:|---|---|---|---|---|\n",
    ]
    for item in checks["documents"]:
        lines.append(
            f"| {item['document_index']} | {', '.join(map(str, item['detected_sections']))} | "
            f"{', '.join(map(str, item['missing_sections'])) or '-'} | "
            f"{', '.join(map(str, item['duplicate_sections'])) or '-'} | "
            f"{'예' if item['out_of_order'] else '아니오'} | {'통과' if item['passed'] else '검토 필요'} |\n"
        )
    lines.extend(["\n## 생성 파일\n\n", "- `sections.json`: 항목별 원문과 페이지 범위\n", "- `codes.json`: 코드와 원문 근거\n", "- `table_rows.json`: 좌표 기반 `|` 행 묶기\n", "- `diagnostics.json`: 누락·중복·순서·다중 MSDS 검사\n", "- `result.json`: 전체 통합 결과\n"])
    path.write_text("".join(lines), encoding="utf-8")
