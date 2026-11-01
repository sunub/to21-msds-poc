"""C-1: 최종 페이지 텍스트에서 법정 16개 항목 경계 파일을 만든다."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .layout import section_headings

_LINE = re.compile(r"^\s*L(\d+)\s+(.*)$")
_TOC_MIN = 8
_NEW_MSDS_MIN_FOUND = 3

SEMANTIC_TYPES = {
    1: "identification", 2: "hazard", 3: "components", 4: "first_aid",
    5: "fire_fighting", 6: "accidental_release", 7: "handling_storage",
    8: "exposure_controls", 9: "physical_chemical_properties",
    10: "stability_reactivity", 11: "toxicology", 12: "ecology",
    13: "disposal", 14: "transport", 15: "regulatory", 16: "other_information",
}


@dataclass(frozen=True)
class PageLine:
    page: int
    number: int
    text: str

    @property
    def ref(self) -> str:
        return f"p{self.page}:L{self.number}"


@dataclass(frozen=True)
class Heading:
    offset: int
    section: int
    text: str


def _compact(text: str) -> str:
    return re.sub(r"[\s·ㆍ.\-_/]+", "", text).casefold()


def heading_semantic(section: int, title: str) -> str:
    """제목 내용으로 의미를 판별한다. 구양식의 2·3항은 번호와 의미가 다르다."""
    compact = _compact(title)
    if section in (2, 3):
        if any(word in compact for word in ("구성성분", "성분의명칭", "composition", "ingredient")):
            return "components"
        if any(word in compact for word in ("유해", "위험", "hazard")):
            return "hazard"
    return SEMANTIC_TYPES[section]


def document_format(group: dict[int, Heading]) -> str:
    """2·3항의 실제 의미가 현재 법정 순서와 반대면 구양식으로 판정한다."""
    second = group.get(2)
    third = group.get(3)
    if ((second and heading_semantic(2, second.text) == "components")
            or (third and heading_semantic(3, third.text) == "hazard")):
        return "legacy"
    return "current"


def load_lines(pages_dir: Path) -> list[PageLine]:
    """pNNN.txt를 B와 같은 pN:LN 좌표 목록으로 읽는다."""
    lines: list[PageLine] = []
    for path in sorted(pages_dir.glob("p[0-9][0-9][0-9].txt")):
        page = int(path.stem[1:])
        for fallback, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _LINE.match(raw)
            number, text = (int(match.group(1)), match.group(2)) if match else (fallback, raw)
            lines.append(PageLine(page, number, text))
    return lines


def _page_candidates(lines: list[PageLine], after: int) -> tuple[list[tuple[int, int, str]], int]:
    """한 쪽을 layout.section_headings로 판독해 (쪽 안 위치, 항, 제목)를 돌려준다."""
    items = [
        {"text": line.text, "box": [0.0, float(i * 20), float(max(1, len(line.text))), float(i * 20 + 10)]}
        for i, line in enumerate(lines)
    ]
    found = []
    for y, section, title in section_headings(items, after=after):
        index = max(0, min(len(lines) - 1, round(y / 20)))
        found.append((index, section, title))
    return found, (found[-1][1] if found else after)


def find_headings(lines: list[PageLine]) -> list[Heading]:
    """항 제목 후보를 찾고 목차와 반복 머리글을 제외한다."""
    offsets_by_page: dict[int, list[int]] = {}
    for offset, line in enumerate(lines):
        offsets_by_page.setdefault(line.page, []).append(offset)

    candidates: list[Heading] = []
    after = 0
    for page in sorted(offsets_by_page):
        offsets = offsets_by_page[page]
        page_lines = [lines[i] for i in offsets]
        found, after = _page_candidates(page_lines, after)
        candidates.extend(Heading(offsets[i], section, title) for i, section, title in found)

    # 목차는 항 제목이 한 줄씩 길게 연속되는 쪽이다. 실제 본문은 제목 사이에 내용 줄이 있다.
    toc_pages: set[int] = set()
    for page in offsets_by_page:
        positions = sorted(lines[h.offset].number for h in candidates if lines[h.offset].page == page)
        longest = run = 0
        previous = None
        for position in positions:
            run = run + 1 if previous is not None and position == previous + 1 else 1
            longest = max(longest, run)
            previous = position
        if longest >= _TOC_MIN:
            toc_pages.add(page)

    # 같은 제목이 세 쪽 이상에서 각 쪽 상단에 반복되면 항 제목이 아니라 머리글이다.
    top_pages: dict[str, list[int]] = {}
    for heading in candidates:
        line = lines[heading.offset]
        if line.number <= 5 and line.page not in toc_pages:
            top_pages.setdefault(heading.text, []).append(line.page)
    repeated = set()
    for title, pages in top_pages.items():
        pages = sorted(set(pages))
        run = longest = 0
        previous = None
        for page in pages:
            run = run + 1 if previous is not None and page == previous + 1 else 1
            longest = max(longest, run)
            previous = page
        if longest >= 3:
            repeated.add(title)
    return [h for h in candidates if lines[h.offset].page not in toc_pages and h.text not in repeated]


def build_contract(doc_id: str, lines: list[PageLine], source: str | None = None) -> dict[str, Any]:
    """layout 제목 후보를 B 입력과 같은 data/sections 형식으로 변환한다."""
    if not lines:
        return {"doc_id": doc_id, "source": source, "msds": [],
                "stats": {"found": 0, "msds": 0, "complete": 0, "missing": []}}
    headings = find_headings(lines)
    groups: list[dict[int, Heading]] = [{}]
    for heading in headings:
        current = groups[-1]
        if heading.section == 1 and len(current) >= _NEW_MSDS_MIN_FOUND:
            groups.append({1: heading})
        elif heading.section not in current and (not current or heading.section > max(current)):
            current[heading.section] = heading
    groups = [group for group in groups if group] or [{}]

    begins = [0] + [group[1].offset for group in groups[1:]]
    msds = []
    missing_report = []
    for index, group in enumerate(groups):
        format_name = document_format(group)
        document_end = begins[index + 1] - 1 if index + 1 < len(begins) else len(lines) - 1
        found = sorted(group.items(), key=lambda item: item[1].offset)
        sections: dict[str, dict[str, Any]] = {}
        for position, (number, heading) in enumerate(found):
            end = found[position + 1][1].offset - 1 if position + 1 < len(found) else document_end
            sections[str(number)] = {
                "start": lines[heading.offset].ref,
                "end": lines[max(heading.offset, end)].ref,
                "method": "legacy_title" if format_name == "legacy" else "title",
                "semantic_type": heading_semantic(number, heading.text),
            }
        missing = [number for number in range(1, 17) if str(number) not in sections]
        for number in missing:
            sections[str(number)] = {
                "start": None,
                "end": None,
                "method": "failed",
                "semantic_type": SEMANTIC_TYPES[number],
            }
        start_page = 1 if index == 0 else lines[begins[index]].page
        if index + 1 < len(begins):
            next_page = lines[begins[index + 1]].page
            end_page = max(start_page, next_page - 1)
        else:
            end_page = lines[-1].page
        msds.append({
            "pages": [start_page, end_page],
            "format": format_name,
            "sections": {str(number): sections[str(number)] for number in range(1, 17)},
        })
        missing_report.append({"msds_index": index + 1, "sections": missing})

    complete = sum(not item["sections"] for item in missing_report)
    return {
        "doc_id": doc_id,
        "source": source,
        "msds": msds,
        "stats": {
            "found": sum(16 - len(item["sections"]) for item in missing_report),
            "msds": len(msds),
            "complete": complete,
            "missing": missing_report,
        },
    }


def extract_sections(doc_id: str, pages_dir: Path) -> dict[str, Any]:
    source_dir = pages_dir.resolve()
    try:
        source = str(source_dir.relative_to(Path(__file__).resolve().parents[4]))
    except ValueError:
        source = str(source_dir)
    return build_contract(doc_id, load_lines(source_dir), source)
