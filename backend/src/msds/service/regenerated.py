"""TO21 문서를 MSDS로 다시 만들어 추출 대상 항(EXTRACT_SECTIONS)만 항별 줄 목록으로 나눈다 (서비스 API).

만드는 일은 TO21 제공 재생성 스크립트(regenerate)가 한다. 모델을 부르지 않고, 파일도 쓰지 않는다(메모리 DB).
화면이 항마다 상태를 붙여 그리도록 여기서 항으로 나눈다. 스크립트는 저장소에 올리지 않으므로(D-47) 인자로 받는다.

- 숨김 줄(Alt)은 스크립트의 to_html처럼 뺀다.
- 표준 제목과 원문 제목이 함께 나온 항은 처음 제목으로 합친다.
- 스크립트가 글자로 찍는 None은 값 없음으로 바꾼다.
- 제목(title_raw)이 빈 서술 항목은 표준 제목을 넣어 넘긴다. 스키마는 빈 제목을 허용하지만 스크립트는 글자로 여겨,
  미정의 항목(extras)이 있는 문서에서 TypeError로 멈추고 없는 문서에서는 제목이 None으로 찍힌다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from msds.common import paths
from msds.extract.inputs import EXTRACT_SECTIONS

_HEADING = re.compile(r"^(\d{1,2})\.\s+(.+)$")
_NONE = re.compile(r"\bNone\b")
MISSING = "값 없음"
NO_TITLE = "(항목 제목 없음)"
LAST_SECTION = 16


@lru_cache(maxsize=1)
def _standard_titles() -> dict[str, str]:
    """서술 항목 코드 → 표준 제목(TO21 동의어 사전의 첫 이름). 파일이 없으면 빈 표."""
    path = paths.TO21 / paths.TO21_FILES["dictionary"]
    if not path.is_file():
        return {}
    names = json.loads(path.read_text(encoding="utf-8")).get("narratives", {})
    return {code: titles[0] for code, titles in names.items() if titles}


def _fill_titles(doc: dict) -> dict:
    """빈 서술 항목 제목을 채운 사본. 원본(검수 기록을 반영한 결과)은 고치지 않는다."""
    def filled(row: dict) -> dict:
        if row.get("title_raw"):
            return row
        return {**row, "title_raw": _standard_titles().get(row.get("item_code"), NO_TITLE)}
    return {**doc, "msds": [{**m, "narratives": [filled(r) for r in m["narratives"]]} if m.get("narratives") else m
                            for m in doc["msds"]]}


def _line(text: str) -> dict:
    text = _NONE.sub(MISSING, text)
    if text.startswith("- "):
        return {"kind": "item", "text": text[2:]}
    return {"kind": "head", "text": text}


def _split(lines: list[str]) -> tuple[list[str], list[dict]]:
    """(첫 항 앞의 줄, 항 목록). 지금 항이거나 바로 다음 번호일 때만 제목으로 본다('39. pH 조절제' 같은 값이 있다)."""
    header: list[str] = []
    sections: list[dict] = []
    for text in lines:
        current = sections[-1]["section"] if sections else 0
        m = _HEADING.match(text)
        no = int(m.group(1)) if m else None
        if no is not None and no == current + 1 and no <= LAST_SECTION:
            sections.append({"section": no, "title": m.group(2), "lines": []})
        elif no is not None and no == current:
            continue
        elif sections:
            sections[-1]["lines"].append(_line(text))
        else:
            header.append(_NONE.sub(MISSING, text))
    return header, sections


def regenerate_sections(doc: dict, regen: Any) -> list[dict]:
    """[{msds_index, header, sections: [{section, title, lines: [{kind, text}]}]}]. regen은 재생성 스크립트 모듈."""
    db = regen.to_db(_fill_titles(doc), ":memory:")
    try:
        out = []
        for i in range(len(doc["msds"])):
            lines = [str(x) for x in regen.regenerate(db, i + 1) if not isinstance(x, regen.Alt)]
            header, sections = _split(lines)
            sections = [s for s in sections if s["section"] in EXTRACT_SECTIONS]   # 나머지 항은 추출하지 않아 비어 있다
            out.append({"msds_index": i, "header": header, "sections": sections})
        return out
    finally:
        db.close()
