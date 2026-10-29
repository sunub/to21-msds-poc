"""C의 항목 분할 파일이 없을 때 쪽 글자에서 법정 16개 항목 제목을 찾아 임시 분할을 만든다 (B, ADR-019).

결과는 data/sections/<doc_id>.json과 같은 형식이고 메모리에서만 쓴다. 그 폴더는 C의 자리라 파일로 쓰지 않는다.
제목 변형은 TO21 동의어 사전의 "sections"를 실행할 때 받는다 (D-47). 영문 제목은 찾지 않는다.
"""
from __future__ import annotations

import re
from collections import Counter

from msds.extract.inputs import SECTION_NOS, Line

_NUMBERED = re.compile(r"^\s*(\d{1,2})(?!\d)\s*(?:[.)]|항)?\s*(.*)$")
_NOISE = re.compile(r"[\W_ㆍ]")   # 공백·구두점·가운뎃점. ' | ' 칸 구분도 여기서 빠진다
HEADER_MIN_PAGES = 3              # 쪽 첫 줄이 이만큼의 쪽에서 같으면 머리글
TOC_RUN = 8                       # 한 쪽에서 제목 후보가 이보다 많이 연달아 나오면 목차
NEW_MSDS_MIN_FOUND = 3            # 1항 제목이 다시 나올 때 앞에서 찾은 항이 이만큼 있으면 새 건


def _norm(text: str) -> str:
    return _NOISE.sub("", text)


def _title_no(text: str, variants: dict[int, list[str]]) -> int | None:
    """번호와 제목이 한 줄에 있으면 그 항 번호. 제목은 그 번호의 변형과 같거나 변형으로 시작해야 한다."""
    m = _NUMBERED.match(text)
    if not m:
        return None
    no, rest = int(m.group(1)), _norm(m.group(2))
    if no not in variants or not rest:
        return None
    return no if any(rest.startswith(v) for v in variants[no]) else None


def _candidates(lines: list[Line], variants: dict[int, list[str]]) -> list[tuple[int, int]]:
    """(줄 위치, 항 번호) 목록. 쪽 머리글과 목차 쪽은 뺀다."""
    first_of_page: dict[int, int] = {}
    for i, l in enumerate(lines):
        first_of_page.setdefault(l.page, i)
    repeated = Counter(lines[i].text for i in first_of_page.values())
    headers = {i for i in first_of_page.values() if repeated[lines[i].text] >= HEADER_MIN_PAGES}

    cands = [(i, no) for i, l in enumerate(lines)
             if i not in headers and (no := _title_no(l.text, variants)) is not None]

    toc_pages: set[int] = set()
    run = 0
    for k, (i, _) in enumerate(cands):
        prev = cands[k - 1][0] if k else None
        run = run + 1 if prev == i - 1 and lines[prev].page == lines[i].page else 1
        if run > TOC_RUN:
            toc_pages.add(lines[i].page)
    return [(i, no) for i, no in cands if lines[i].page not in toc_pages]


def _group(cands: list[tuple[int, int]]) -> list[dict[int, int]]:
    """MSDS 건마다 {항 번호: 제목 줄 위치}. 같은 번호나 순서가 뒤집힌 번호는 뒤의 것을 버린다."""
    groups: list[dict[int, int]] = [{}]
    for i, no in cands:
        cur = groups[-1]
        if no == 1 and len(cur) >= NEW_MSDS_MIN_FOUND:
            groups.append({1: i})
        elif not cur or no > max(cur):
            cur[no] = i
    return groups


def find_sections(lines: list[Line], titles: dict[str, list[str]]) -> dict:
    """쪽 글자에서 항목 제목 줄을 찾아 data/sections 형식의 dict를 돌려준다.
    titles는 TO21 동의어 사전의 "sections" (항 번호 문자열 → 제목 변형 목록).
    반환: {"msds": [{"pages": [첫 쪽, 끝 쪽],
                    "sections": {"1": {"start": "p1:L5", "end": "p2:L40", "method": "provisional"}, ...}}],
           "stats": {"found": 찾은 항 수(모든 건 합), "msds": 건 수}}
    못 찾은 항은 {"method": "failed"}다.
    """
    if not lines:
        return {"msds": [], "stats": {"found": 0, "msds": 0}}
    variants = {int(k): [_norm(v) for v in vs if _norm(v)] for k, vs in titles.items()}
    groups = _group(_candidates(lines, variants))

    # 건의 시작 줄: 첫 건은 문서 첫 줄, 다음 건부터는 그 1항 제목 줄
    begins = [0] + [g[1] for g in groups[1:]]
    msds = []
    for k, found in enumerate(groups):
        first_page = lines[begins[k]].page
        if k + 1 < len(groups):
            nxt = begins[k + 1]
            last_page = max(first_page, lines[nxt].page - 1)
            last = max(i for i in range(nxt) if lines[i].page <= last_page)
        else:
            last_page, last = lines[-1].page, len(lines) - 1

        order = sorted(found.items(), key=lambda x: x[1])
        sections = {}
        for j, (no, i) in enumerate(order):
            end = order[j + 1][1] - 1 if j + 1 < len(order) else max(i, last)
            sections[no] = {"start": lines[i].id, "end": lines[end].id, "method": "provisional"}
        msds.append({"pages": [first_page, last_page],
                     "sections": {str(n): sections.get(n, {"method": "failed"}) for n in SECTION_NOS}})
    return {"msds": msds, "stats": {"found": sum(len(g) for g in groups), "msds": len(groups)}}
