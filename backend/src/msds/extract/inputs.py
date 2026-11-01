"""C의 전처리 결과를 읽어 줄 번호 붙은 줄 목록과 MSDS별 항목 구간을 만든다 (B).

C의 항목 분할 파일이 없으면 제목으로 임시 분할을 만든다(sections.py, ADR-019). 제목을 하나도 못 찾거나
코드 추출 파일이 없으면 대체 경로로 간다(ADR-006).
어느 항에도 속하지 않는 1항 제목 앞 줄(문서 머리)은 읽을 때 계산해 모든 항 호출에 붙인다(ADR-020).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from msds.common.paths import DATA, PAGES

_LINE_NO = re.compile(r"^L(\d+) (.*)$")
_PAGE_FILE = re.compile(r"^p(\d+)\.txt$")
SECTION_NOS = range(1, 17)
PREAMBLE_MAX = 40     # 문서 머리로 붙이는 줄 수 상한. 목차·표지는 길어도 값이 적다


@dataclass(frozen=True)
class Line:
    id: str      # "p2:L23"
    page: int
    no: int      # 23
    text: str


@dataclass
class SectionSpan:
    start: str | None
    end: str | None
    method: str          # "title" | "synonym" | "provisional" | "failed" | "fallback"


@dataclass
class MsdsPart:
    index: int                       # 0부터
    pages: tuple[int, int]           # 시작·끝 쪽 (끝 포함)
    sections: dict[int, SectionSpan]  # 1~16 모두 들어 있다
    preamble: tuple[str, str] | None = None   # 문서 머리의 첫 줄·끝 줄 id. 없으면 None


@dataclass
class DocumentInput:
    doc_id: str
    lines: list[Line]
    msds: list[MsdsPart]
    codes: dict | None
    warnings: list[str]
    sections_method: str             # "file" | "provisional"(B 임시 분할) | "fallback"(문서 전체)


def read_page_lines(doc_id: str, pages_dir: Path = PAGES) -> list[Line]:
    doc_dir = pages_dir / doc_id
    files = []
    if doc_dir.is_dir():
        for p in doc_dir.iterdir():
            m = _PAGE_FILE.match(p.name)
            if m:
                files.append((int(m.group(1)), p))
    if not files:
        raise FileNotFoundError(f"{doc_id}: 쪽 글자 파일(pNNN.txt)이 없습니다: {doc_dir}")

    lines: list[Line] = []
    for page, path in sorted(files):
        seq = 0
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            seq += 1
            m = _LINE_NO.match(raw)
            no, text = (int(m.group(1)), m.group(2)) if m else (seq, raw)
            lines.append(Line(f"p{page}:L{no}", page, no, text.rstrip()))
    return lines


def _fallback_sections() -> dict[int, SectionSpan]:
    return {n: SectionSpan(None, None, "fallback") for n in SECTION_NOS}


def _preamble(index: int, first_page: int, sections: dict[int, SectionSpan], lines: list[Line],
              pos: dict[str, int]) -> tuple[str, str] | None:
    """건의 첫 줄부터 그 건에서 가장 앞에 있는 항 구간 start 바로 앞 줄까지(최대 PREAMBLE_MAX줄).
    건의 첫 줄은 첫 건이면 문서 첫 줄, 다음 건이면 그 건 첫 쪽의 첫 줄이다."""
    starts = [pos[s.start] for s in sections.values() if s.method != "fallback"]
    begin = 0 if index == 0 else next((i for i, l in enumerate(lines) if l.page >= first_page), None)
    if not starts or begin is None or min(starts) <= begin:
        return None
    end = min(min(starts) - 1, begin + PREAMBLE_MAX - 1)
    return lines[begin].id, lines[end].id


def _build_part(index: int, entry: dict, lines: list[Line], pos: dict[str, int], warnings: list[str]) -> MsdsPart:
    first, last = entry["pages"]
    raw = entry.get("sections") or {}
    sections = {}
    for n in SECTION_NOS:
        span = raw.get(str(n))
        reason = None
        if not span:
            reason = "항목 없음"
        elif span.get("method") == "failed":
            reason = "분할 실패(failed)"
        else:
            start, end = span.get("start"), span.get("end")
            missing = [x for x in (start, end) if x not in pos]
            if missing:
                reason = f"없는 줄 번호: {', '.join(str(x) for x in missing)}"
            elif pos[start] > pos[end]:
                reason = f"시작({start})이 끝({end})보다 뒤"
        if reason:
            warnings.append(f"{n}항: {reason}, 대체 경로 (MSDS {index})")
            sections[n] = SectionSpan(None, None, "fallback")
        else:
            sections[n] = SectionSpan(span["start"], span["end"], span.get("method", "title"))
    return MsdsPart(index, (first, last), sections, _preamble(index, first, sections, lines, pos))


def load_document(doc_id: str, pages_dir: Path = PAGES, sections_dir: Path = DATA / "sections",
                  codes_dir: Path = DATA / "codes") -> DocumentInput:
    lines = read_page_lines(doc_id, pages_dir)
    pos = {l.id: i for i, l in enumerate(lines)}
    warnings: list[str] = []

    sections_path = sections_dir / f"{doc_id}.json"
    if sections_path.exists():
        data = json.loads(sections_path.read_text(encoding="utf-8"))
        method = "file"
    else:
        # section_prompts와 sections가 이 모듈을 import하므로 여기서 부른다
        from msds.extract.section_prompts import _dictionary
        from msds.extract.sections import find_sections

        data = find_sections(lines, _dictionary()["sections"])
        found, count = data["stats"]["found"], data["stats"]["msds"]
        method = "provisional" if found else "fallback"
        if found:
            warnings.append(f"항목 분할 파일 없음: 임시 분할 (찾은 항 {found}/{16 * count}, MSDS {count}건)")
    if method == "fallback":
        warnings.append("항목 분할 파일 없음: 대체 경로")
        msds = [MsdsPart(0, (lines[0].page, lines[-1].page), _fallback_sections())]
    else:
        msds = [_build_part(i, e, lines, pos, warnings) for i, e in enumerate(data["msds"])]

    codes_path = codes_dir / f"{doc_id}.json"
    codes = json.loads(codes_path.read_text(encoding="utf-8")) if codes_path.exists() else None
    return DocumentInput(doc_id, lines, msds, codes, warnings, method)


def section_lines(doc: DocumentInput, msds_index: int, section_no: int, with_preamble: bool = True) -> list[Line]:
    """그 항 호출에 보내는 줄. fallback 항은 건의 쪽 전체, 아니면 문서 머리 + 항 구간(겹치면 한 번만, 문서 순서).
    with_preamble=False면 항 구간만 (2항 쪽 이미지 고르기)."""
    part = doc.msds[msds_index]
    span = part.sections[section_no]
    if span.method == "fallback":
        first, last = part.pages
        return [l for l in doc.lines if first <= l.page <= last]
    pos = {l.id: i for i, l in enumerate(doc.lines)}
    keep = set(range(pos[span.start], pos[span.end] + 1))
    if with_preamble and part.preamble:
        a, b = part.preamble
        keep |= set(range(pos[a], pos[b] + 1))
    return [doc.lines[i] for i in sorted(keep)]


_EDGE = 2      # 쪽 위·아래에서 머리글·바닥글을 찾는 줄 수
_PAGE_NO = re.compile(r"^\s*(?:-\s*)?\d{1,3}\s*(?:/\s*\d{1,3})?\s*(?:-\s*)?$|^\s*(?:page|쪽)\s*\d+(?:\s*(?:of|/)\s*\d+)?\s*$",
                      re.IGNORECASE)
def page_noise(lines: list[Line]) -> set[str]:
    """쪽 머리글·바닥글·쪽 번호 줄의 id. 쪽 위·아래 _EDGE줄 가운데 같은 자리(위·아래에서 몇 번째)에 같은 글(숫자는
    무시)이 절반 이상 쪽(3쪽 이상 문서)에 되풀이되거나, 쪽 번호 모양인 줄이다. 쪽을 넘는 목록의 데이터 줄은 같은 글이라도
    자리가 쪽마다 달라 잡히지 않는다."""
    by_page: dict[int, list[Line]] = {}
    for l in lines:
        by_page.setdefault(l.page, []).append(l)
    if len(by_page) < 3:
        return set()
    edges = [(("top", i), l) for ls in by_page.values() for i, l in enumerate(ls[:_EDGE])]
    edges += [(("bottom", i), l) for ls in by_page.values() for i, l in enumerate(reversed(ls[-_EDGE:]))]
    key = lambda at, l: (at, re.sub(r"[\d\s]+", "", l.text))
    pages_of: dict[tuple, set[int]] = {}
    for at, l in edges:
        if key(at, l)[1]:
            pages_of.setdefault(key(at, l), set()).add(l.page)
    repeated = {k for k, p in pages_of.items() if len(p) >= max(3, (len(by_page) + 1) // 2)}
    return {l.id for at, l in edges if key(at, l) in repeated or _PAGE_NO.match(l.text)}


def model_lines(doc: DocumentInput, msds_index: int, section_no: int) -> list[Line]:
    """모델에 보내는 줄: section_lines에서 항 구간의 쪽 머리글·바닥글·쪽 번호를 뺀다. 문서 머리와 줄 번호는 그대로 둔다.
    항 제목 줄은 남긴다. 문서 머리와 항 본문의 경계라, 빼면 모델이 문서 머리의 표기를 가져오거나 제목 바로 뒤 행을
    빠뜨렸다(11/01 실행, 3·8·11·12·15항)."""
    drop = page_noise(doc.lines) & {l.id for l in section_lines(doc, msds_index, section_no, with_preamble=False)}
    return [l for l in section_lines(doc, msds_index, section_no) if l.id not in drop]


_MARK = re.compile(r"^(\s*)([●○ο■□◆◇▶▷※]|[-–]|[·•ㆍ∙]|[가-하]\s*[.)]|\(?\d{1,2}\)|[①-⑳]|\d{1,2}\.(?!\d))\s*")


def line_parents(lines: list[Line]) -> dict[str, list[Line]]:
    """글머리 기호가 있는 줄마다 부모 줄 목록(가까운 것부터). 기호(들여쓰기 포함)마다 처음 나온 깊이를 기억한다.
    처음 보는 기호는 앞 줄의 자식이고('○ 발암성' > '- 성분' > '· IARC'), 다시 나온 기호는 그 깊이로 돌아가 형제가 된다
    ('● 법령 A' 아래 '- 성분' 목록 뒤의 '● 법령 B'). 맨 위 깊이로 돌아가면(다음 항 제목 등) 기억을 지운다.
    기호가 없는 줄은 넣지 않는다."""
    out: dict[str, list[Line]] = {}
    stack: list[tuple[int, Line]] = []
    depth: dict[tuple[int, str], int] = {}
    for l in lines:
        m = _MARK.match(l.text)
        if not m:
            continue
        indent = len(m[1].expandtabs(4))
        key = (indent, _mark_kind(m[2]))
        if key in depth:
            del stack[depth[key]:]
        while stack and stack[-1][0] > indent:
            stack.pop()
        if not stack:
            depth.clear()
        depth[key] = len(stack)
        out[l.id] = [s[1] for s in reversed(stack)]
        stack.append((indent, l))
    return out


def _mark_kind(mark: str) -> str:
    """같은 종류 기호를 한 이름으로: '가.'·'나.' → '가.', '1)'·'(2)' → '1)', '3.' → '1.', '①' → '①'."""
    m = re.sub(r"\s", "", mark)
    for pat, kind in ((r"[가-하][.)]", "가."), (r"\(?\d{1,2}\)", "1)"), (r"\d{1,2}\.", "1."), (r"[①-⑳]", "①")):
        if re.fullmatch(pat, m):
            return kind
    return m[:1]


def render_lines(lines: list[Line]) -> str:
    return "\n".join(f"{l.id} {l.text}" for l in lines)


def line_index(lines: list[Line]) -> dict[str, Line]:
    return {l.id: l for l in lines}
