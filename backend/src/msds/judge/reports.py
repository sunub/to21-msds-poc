"""리포트 내려받기: html·xlsx·json·pdf. 입력은 JudgeService.report_data 하나다."""
import copy
import html
import io
import json
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import pymupdf
from openpyxl import Workbook
from openpyxl.cell import Cell

from msds.checks.validator import load_to21_module

from .display import finding_display

ALL_INCLUDE = {"regenerated_msds": True, "findings_2": True, "findings_15": True, "components": True, "history": True}
_CSS = """
body{font-family:sans-serif;font-size:10pt;color:#111;overflow-wrap:anywhere}h1{font-size:18pt}h2{font-size:13pt;margin-top:14pt}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #999;padding:3pt;font-size:9pt;text-align:left;vertical-align:top}
th{background-color:#eee}
"""
MEDIA = {"html": "text/html; charset=utf-8", "json": "application/json",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "pdf": "application/pdf"}


def _e(v) -> str:
    return html.escape(_ILLEGAL.sub(" ", "" if v is None else str(v)))


def _product(data: dict) -> str:
    msds = data["handoff"]["extraction"].get("msds") or [{}]
    return str((msds[0].get("product") or {}).get("name") or data["job_id"])


def filename(data: dict, fmt: str) -> str:
    return f"{_product(data)[:80]}_MSDS_검토결과.{fmt}".replace("/", "_").replace("\\", "_")


def content_disposition(name: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(name)}"


_SEVERITY = {"높음": 0, "중간": 1, "낮음": 2}
_VERDICT = {"불일치": 0, "경계": 1, "근거부족": 2, "경고": 3, "일치": 4, "참고": 5, "범위 외": 6}
NEEDS_REVIEW = ("불일치", "경계", "근거부족", "경고")


def _rows(data: dict, section: str):
    """설계서 7장: 리포트는 심각도 순서로 낸다."""
    rows = [(f, r["traces"].get(f["trace_id"])) for r in data["consistency"]["results"] for f in r["findings"] if f["section"] == section]
    rows.sort(key=lambda x: (_VERDICT[x[0]["verdict"]], _SEVERITY.get(x[0]["severity"], 3), x[0]["id"]))
    several = len(data["consistency"]["results"]) > 1
    for f, trace in rows:
        # 한 PDF에 MSDS가 여럿이면 어느 MSDS의 줄인지 밝힌다
        label = f"MSDS {int(f['id'][1:f['id'].index('/')]) + 1} · {f['label']}" if several else f["label"]
        yield {**f, "label": label, "display": finding_display(f, trace)}, data["reviews"].get(f["id"], {})


def _status(f, s):
    status = s.get("status", "미검토")
    if status == "미검토" and f["verdict"] not in NEEDS_REVIEW:
        return "처리 불필요"  # 표지의 미검토 수와 맞춘다
    return status + (" · 다시 확인 필요" if s.get("stale") else "")


def _cell(f, s, comments):
    verdict = f["verdict"] + (f" · {f['severity']}" if f["severity"] else "")
    row = [f.get("law_label") or "", f["label"], f["display"]["component"] or "", f["display"]["msds"], f["display"]["expected"],
           f.get("method") or "", verdict, _status(f, s)]
    return row + ([s.get("comment") or ""] if comments else [])


def _table(data: dict, section: str, comments: bool) -> str:
    head = ["법령", "항목", "성분", "MSDS 기재", "검증 결과", "판정 방법", "판정", "처리"] + (["의견"] if comments else [])
    rows = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in _cell(f, s, comments)) + "</tr>" for f, s in _rows(data, section))
    return "<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + f"</tr>{rows}</table>"


def _review_line(data: dict) -> str:
    c = data["counts"]
    return f"미검토 {c['미검토']}건 · 미검수 칸 {c['미검수 칸']}칸"


def _load_regen():
    return load_to21_module("regen")  # 3.11에서 main() 앞만 읽는 처리는 공용 창구에 있다(B-15)


def _without_empty_titles(value):
    """TO21 스크립트는 빈 title_raw 를 줄 목록에 넣은 채 extras 를 처리하다 멈춘다 (실버 T21-010). 사본에서 빈 글자로 바꾼다."""
    if isinstance(value, dict):
        return {k: "" if k == "title_raw" and v is None else _without_empty_titles(v) for k, v in value.items()}
    return [_without_empty_titles(v) for v in value] if isinstance(value, list) else value


def _regenerated_lines(extraction: dict) -> tuple[list[str], str | None]:
    """TO21 재생성 스크립트 결과. (줄 목록, 오류 이름). 스크립트는 저장소에 올리지 않으므로(D-47) 없거나 실패할 수 있다."""
    try:
        mod = _load_regen()
        doc = _without_empty_titles(copy.deepcopy(extraction))
        with tempfile.TemporaryDirectory() as folder:
            db = mod.to_db(doc, str(Path(folder) / "msds.db"))
            try:
                return [str(x) for i in range(len(doc.get("msds") or [])) for x in mod.regenerate(db, i + 1)], None
            finally:
                db.close()
    except Exception as e:  # 재생성이 안 돼도 판정 표는 내려받을 수 있어야 한다
        return [], type(e).__name__


def _regen_failed(error: str) -> str:
    return f"재생성 MSDS를 만들지 못함 ({error})"


def _cover_lines(data: dict) -> list[str]:
    c, snap = data["consistency"], data["snapshot"]
    counts: dict[str, int] = {}
    for r in c["results"]:
        for k, v in r["summary"].items():
            counts[k] = counts.get(k, 0) + v
    saved = f"저장본 {snap['snapshot_no']} · {snap['saved_by']} · {snap['saved_at']}" if snap else "저장 전 미리 보기"
    return [f"문서 번호 {c['doc_id']} · 작업 {data['job_id']}", f"원본 파일 {data['handoff']['source']['filename']}", saved,
            f"기준일 {c['as_of']} · 판정 버전 {data['version']} · 지식 {c['knowledge']['provider']} / {c['knowledge']['version']}",
            " · ".join(f"{k} {v}" for k, v in counts.items()), _review_line(data)]


def _edited_fields(data: dict) -> list[str]:
    return [s["field"] for s in data["handoff"].get("field_status") or [] if s["status"] == "수정됨"]


_FINDING_SECTIONS = (("findings_2", "2"), ("findings_15", "15"))


def _sections(include: dict) -> list[str]:
    return [sec for key, sec in _FINDING_SECTIONS if include[key]]


def _component_rows(data: dict) -> list[list]:
    rows = []
    for r in data["consistency"]["results"]:
        for c in r["components"]:
            classes = " · ".join(f"{x['class_code']} {x['category']}" for x in c["reference_classes"]) or "없음"
            ate = " · ".join(" ".join(x for x in (a["route"], str(a["value"]), a["unit"], f"({a['step']}단계)" if a["step"] else None) if x)
                             if a["value"] is not None else f"{a['route']} {a['excluded'] or '값 없음'}" for a in c["ate"]) or "없음"
            rows.append([c["name"] or "", c["cas"] or "", (c["content"] or {}).get("raw") or "", classes, ate, c["regulation_hits"], c["reliability"]])
    return rows


_COMPONENT_HEAD = ["성분", "CAS", "함량", "기준 분류", "사용 ATE", "15항 해당", "자료"]


def _html_table(head: list[str], rows: list[list]) -> str:
    cells = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>" for row in rows)
    return "<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + f"</tr>{cells}</table>"


def to_html(data: dict, include: dict = ALL_INCLUDE) -> str:
    body = [f"<h1>{_e(_product(data))} MSDS 검토 결과</h1>" + "".join(f"<p>{_e(x)}</p>" for x in _cover_lines(data))]
    if include["regenerated_msds"]:
        lines, error = _regenerated_lines(data["handoff"]["extraction"])
        shown = [_regen_failed(error)] if error else lines
        body.append("<h2>재생성 MSDS</h2>" + "".join(f"<p>{_e(x)}</p>" for x in shown))
    body += [f"<h2>{sec}항 판정</h2>{_table(data, sec, True)}" for sec in _sections(include)]
    if include["components"]:
        body.append(f"<h2>성분별 요약</h2>{_html_table(_COMPONENT_HEAD, _component_rows(data))}")
    if include["history"]:
        rows = [[x["at"], x["reviewer"], x["finding_id"], x["action"], x["comment"]] for x in data["events"]]
        edited = "".join(f"<li>{_e(x)}</li>" for x in _edited_fields(data))
        body.append(f"<h2>부록: 검토 이력</h2>{_html_table(['시각', '검토자', '대상', '처리', '의견'], rows)}"
                    f"<h2>부록: 수정한 추출값 칸</h2><ul>{edited or '<li>없음</li>'}</ul>")
    return f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>{_e(_product(data))} 검토 결과</title><style>{_CSS}</style></head><body>{''.join(body)}</body></html>"


# ── PDF ──────────────────────────────────────────────────────────────
# Story 조판을 쓰지 않고 줄 배치와 쪽 넘김을 직접 한다. MuPDF html-layout.c 는 줄 끝이 영역 끝에 정확히 닿으면
# avail = page_h - fmodf(y - top, page_h) 를 쪽 한 장으로 계산해 쪽을 넘기지 않고, 뒤 줄을 오류 없이 잃는다 (decisions.md).


class ReportError(RuntimeError):
    """리포트를 온전하게 만들 수 없음."""


_FONT = pymupdf.Font("korea")  # 내장 CJK 글꼴. 폐쇄망에서도 시스템 글꼴이 필요 없다. 굵은 체가 없어 제목은 크기로 구분한다
_MARGIN = 36.0
_PAGE = pymupdf.paper_rect("a4")
_WIDTH = _PAGE.width - 2 * _MARGIN
_TITLE, _HEADING, _ROW_HEAD, _BODY = 16.0, 13.0, 10.5, 9.5
_GAP = 5.0
_PDF_LOCK = threading.Lock()  # PyMuPDF 는 스레드에 안전하지 않은데 화면 API는 요청을 여러 스레드에서 처리한다
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]")
# 글꼴에 없지만 뜻이 같은 글자. 소프트 하이픈은 CAS 번호의 하이픈으로 쓰인 경우가 있어 지우지 않는다
_SAME_MEANING = str.maketrans({"\u00ad": "-", "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2212": "-", "\u00b5": "\u03bc",
                               "\u2219": "\u00b7", "\u22c5": "\u00b7", "\u2206": "\u0394", "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl"})
_SUPERSCRIPT = re.compile("[\u00b2\u00b3\u00b9\u2070\u2074-\u207e]+")
_SUBSCRIPT = re.compile("[\u2080-\u208e]+")
_WORD = re.compile(r"\S+")


@lru_cache(maxsize=8192)
def _drawable(ch: str) -> bool:
    """글꼴에 있다고 나와도 다른 글자로 찍히는 경우가 있어 (U+FFFD → 蓣) 실제로 찍어 다시 읽어 본다."""
    if not _FONT.has_glyph(ord(ch)):
        return False
    if ch.isascii() or "가" <= ch <= "힣":
        return True
    doc = pymupdf.open()
    page = doc.new_page()
    writer = pymupdf.TextWriter(page.rect)
    writer.append((36, 60), ch, font=_FONT, fontsize=10)
    writer.write_text(page)
    same = page.get_text().strip() == ch
    inked = same and min(page.get_pixmap(clip=pymupdf.Rect(30, 40, 60, 70), dpi=144).samples) < 255  # ‾ 처럼 잉크 없이 찍히는 글자
    doc.close()
    return inked


def _has_glyphs(text: str) -> bool:
    return all(_drawable(c) for c in text)


def _script(prefix: str):
    """글꼴에 없는 위첨자는 뜻이 같은 표기로 푼다 (10⁻³ → 10^-3). 있는 첨자(m²)는 그대로 둔다."""
    # NFKC 는 ⁻ 를 글꼴에 없는 − (U+2212)로 풀어 준다
    return lambda m: m[0] if _has_glyphs(m[0]) else prefix + unicodedata.normalize("NFKC", m[0]).replace("\u2212", "-")


def _subscripts(word: str) -> str:
    """아래첨자는 한 낱말 안에서 표기를 통일한다 (C₂H₅OH → C_2H_5OH)."""
    if all(_has_glyphs(run) for run in _SUBSCRIPT.findall(word)):
        return word
    return _SUBSCRIPT.sub(lambda m: "_" + unicodedata.normalize("NFKC", m[0]).replace("\u208b", "-"), word)


def _for_font(value) -> str:
    """글꼴이 찍을 수 있는 글로 고친다. 값의 뜻이 조용히 바뀌지 않게, 찍을 수 없는 글자는 코드값을 보이게 남긴다."""
    text = unicodedata.normalize("NFC", _ILLEGAL.sub(" ", "" if value is None else str(value)))
    text = _INVISIBLE.sub("", text).translate(_SAME_MEANING)
    text = _WORD.sub(lambda m: _subscripts(m[0]), _SUPERSCRIPT.sub(_script("^"), text))
    text = " ".join(text.split())
    return "".join(c if c == " " or _drawable(c) else f"[U+{ord(c):04X}]" for c in text)


_FIT_WINDOW = 300  # 가장 좁은 글자로도 한 줄에 이보다 많이 들어가지 않는다. 아주 긴 글자를 통째로 재면 시간이 제곱으로 는다


def _line_height(size: float) -> float:
    return size * 1.35


def _fit(text: str, size: float, width: float) -> int:
    """폭 안에 들어가는 앞글자 수 (최소 1)."""
    low, high = 1, min(len(text), _FIT_WINDOW)
    while low < high:
        mid = (low + high + 1) // 2
        if _FONT.text_length(text[:mid], fontsize=size) <= width:
            low = mid
        else:
            high = mid - 1
    return low


def _wrap(text: str, size: float, width: float = 0.0) -> list[str]:
    """글자 폭을 재서 줄을 나눈다. 띄어쓰기에서 먼저 나누고, 한 낱말이 폭을 넘으면 낱말을 자른다."""
    width = width or _WIDTH
    lines, line = [], ""
    for word in re.findall(r"\S+\s*", text):
        if _FONT.text_length((line + word).rstrip(), fontsize=size) <= width:
            line += word
            continue
        if line:
            lines.append(line.rstrip())
        # 폭 없는 결합 문자만 이어지면 앞부분만 재서는 넘침을 못 본다
        while len(word) > _FIT_WINDOW or _FONT.text_length(word.rstrip(), fontsize=size) > width:
            n = _fit(word, size, width)
            lines.append(word[:n])
            word = word[n:]
        line = word
    return lines + [line.rstrip()] if line or not lines else lines


@dataclass
class _Block:
    lines: list[tuple[float, str]]  # (글자 크기, 글). 되도록 한 쪽에 함께 둔다
    rule: bool = False  # 아래 구분선
    keep_next: bool = False  # 제목: 다음 내용과 같은 쪽에 둔다

    def wrapped(self) -> list[tuple[float, str]]:
        return [(size, part) for size, text in self.lines for part in _wrap(text, size)]


_CELL_PAD = 3.0
_KEEP_ROOM = 60.0  # 제목 아래 남겨 둘 높이 (표 머리줄과 첫 줄)


@dataclass
class _Table:
    head: list[str]
    widths: list[float]  # 쪽 폭에 대한 비율
    rows: list[list[str]]
    size: float = 8.5

    def cells(self, row: list[str]) -> list[list[str]]:
        return [_wrap(c, self.size, w * _WIDTH - 2 * _CELL_PAD) for c, w in zip(row, self.widths)]

    def height(self, wrapped: list[list[str]]) -> float:
        return max(len(c) for c in wrapped) * _line_height(self.size) + 2 * _CELL_PAD


def _layout(blocks: list) -> "pymupdf.Document":
    doc = pymupdf.open()
    top, bottom = _MARGIN, _PAGE.height - _MARGIN
    page = doc.new_page(width=_PAGE.width, height=_PAGE.height)
    writer, y = pymupdf.TextWriter(page.rect), top

    def next_page():
        nonlocal page, writer, y
        writer.write_text(page)
        page = doc.new_page(width=_PAGE.width, height=_PAGE.height)
        writer, y = pymupdf.TextWriter(page.rect), top

    def draw_row(table: _Table, wrapped: list[list[str]], shade: bool):
        nonlocal y
        height, x = table.height(wrapped), _MARGIN
        for cell, ratio in zip(wrapped, table.widths):
            width = ratio * _WIDTH
            page.draw_rect(pymupdf.Rect(x, y, x + width, y + height), color=(0.75, 0.75, 0.75), fill=(0.93, 0.93, 0.93) if shade else None, width=0.4)
            line_y = y + _CELL_PAD
            for text in cell:
                writer.append((x + _CELL_PAD, line_y + table.size), text, font=_FONT, fontsize=table.size)
                line_y += _line_height(table.size)
            x += width
        y += height

    for block in blocks:
        if isinstance(block, _Table):
            head = block.cells(block.head)
            first = block.height(block.cells(block.rows[0])) if block.rows else 0
            if y + block.height(head) + first > bottom:
                next_page()
            draw_row(block, head, True)
            for row in block.rows:
                wrapped = block.cells(row)
                needed = block.height(wrapped)
                if needed > bottom - top - block.height(head):  # 한 쪽에 안 들어가는 줄은 나눈다
                    tall = [(block.size, " · ".join(row))]
                    for size, text in _Block(tall).wrapped():
                        if y + _line_height(size) > bottom:
                            next_page()
                        writer.append((_MARGIN, y + size), text, font=_FONT, fontsize=size)
                        y += _line_height(size)
                    continue
                if y + needed > bottom:
                    next_page()
                    draw_row(block, head, True)  # 머리줄을 쪽마다 다시 찍는다
                draw_row(block, wrapped, False)
            y += _GAP
            continue
        lines = block.wrapped()
        height = sum(_line_height(size) for size, _ in lines)
        if y > top and y + height + (_KEEP_ROOM if block.keep_next else 0) > bottom and height <= bottom - top:
            next_page()
        for size, text in lines:
            if y + _line_height(size) > bottom + 1e-6:
                next_page()
            writer.append((_MARGIN, y + size), text, font=_FONT, fontsize=size)
            y += _line_height(size)
        y += _GAP
        if block.rule and y < bottom:
            page.draw_line((_MARGIN, y - _GAP / 2), (_MARGIN + _WIDTH, y - _GAP / 2), color=(0.8, 0.8, 0.8), width=0.4)
    writer.write_text(page)
    return doc


def _comparable(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split())


def _first_missing(lines: list[str], pdf_text: str) -> str | None:
    """모든 글이 PDF에 순서대로 있지 않으면 처음 빠진 글. 원인이 무엇이든 글이 빠진 PDF는 내보내지 않는다."""
    if "\x00" in pdf_text:  # 글꼴에 없어 네모로 찍힌 글자
        return "글꼴에 없는 글자"
    flat, at = _comparable(pdf_text), 0
    for line in lines:
        piece = _comparable(line)
        found = flat.find(piece, at)
        if found < 0:
            return line
        at = found + len(piece)
    return None


def _one(size: float, text) -> _Block:
    return _Block([(size, _for_font(text))], keep_next=size == _HEADING)


_FINDING_WIDTHS = [0.27, 0.19, 0.19, 0.13, 0.11, 0.11]
_FINDING_HEAD = ["항목", "MSDS 기재", "검증 결과", "판정 방법", "판정", "처리"]
_COMPONENT_WIDTHS = [0.17, 0.11, 0.08, 0.27, 0.21, 0.08, 0.08]


def _finding_table(data: dict, section: str) -> list:
    """표 한 벌. 의견은 칸이 좁아 그 줄 아래 전체 폭으로 찍으므로 의견이 있으면 표를 끊는다."""
    out, rows = [], []

    def flush():
        nonlocal rows
        if rows:
            out.append(_Table(_FINDING_HEAD, _FINDING_WIDTHS, rows))
            rows = []

    for f, s in _rows(data, section):
        law, label, comp, msds, expected, method, verdict, status, comment = _cell(f, s, True)
        item = " · ".join(x for x in (law, label, comp) if x)
        rows.append([_for_font(x) for x in (item, msds, expected, method, verdict, status)])
        if comment:
            flush()
            out.append(_Block([(_BODY, _for_font(f"의견 {part}")) for part in str(comment).splitlines() if part.strip()], rule=True))
    flush()
    return out


def _pdf_blocks(data: dict, include: dict) -> list:
    blocks = [_one(_TITLE, f"{_product(data)} MSDS 검토 결과")] + [_one(_BODY, x) for x in _cover_lines(data)]
    if include["regenerated_msds"]:
        lines, error = _regenerated_lines(data["handoff"]["extraction"])
        blocks.append(_one(_HEADING, "재생성 MSDS"))
        blocks += [_one(_BODY, x) for x in ([_regen_failed(error)] if error else lines)]
    for sec in _sections(include):
        blocks.append(_one(_HEADING, f"{sec}항 판정"))
        blocks += _finding_table(data, sec)
    if include["components"]:
        blocks.append(_one(_HEADING, "성분별 요약"))
        blocks.append(_Table(_COMPONENT_HEAD, _COMPONENT_WIDTHS, [[_for_font(c) for c in row] for row in _component_rows(data)]))
    if include["history"]:
        blocks.append(_one(_HEADING, "부록: 검토 이력"))
        for x in data["events"]:
            lines = [f"{x['at']} · {x['reviewer']} · {x['finding_id']} · {x['action']}"]
            lines += [f"의견 {part}" for part in str(x["comment"] or "").splitlines() if part.strip()]
            blocks.append(_Block([(_BODY, _for_font(t)) for t in lines], rule=True))
        if not data["events"]:
            blocks.append(_one(_BODY, "없음"))
        blocks.append(_one(_HEADING, "부록: 수정한 추출값 칸"))
        blocks += [_one(_BODY, x) for x in _edited_fields(data) or ["없음"]]
    return blocks


def _expected_lines(blocks: list) -> list[str]:
    out = []
    for block in blocks:
        if isinstance(block, _Table):
            out += block.head
            for row in block.rows:
                out += row
        else:
            out += [line for _, line in block.lines]
    return out


def to_pdf(data: dict, include: dict = ALL_INCLUDE) -> bytes:
    with _PDF_LOCK:
        blocks = _pdf_blocks(data, include)
        doc = _layout(blocks)
        doc.subset_fonts()  # 내장 CJK 글꼴을 통째로 넣으면 쪽 수와 상관없이 1.6MB가 넘는다
        raw = doc.tobytes(garbage=3, deflate=True)
        doc.close()
        text = "".join(page.get_text() for page in pymupdf.open(stream=raw, filetype="pdf"))
        missing = _first_missing(_expected_lines(blocks), text)
    if missing is not None:
        raise ReportError(f"PDF에 글이 빠짐, 리포트를 내보내지 않음: {missing[:80]!r}")
    return raw


_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _safe(ws, v):
    # 추출값이 =로 시작해도 수식으로 실행되지 않게 하고, 엑셀이 거부하는 제어 문자로 파일 전체가 막히지 않게 지운다
    if v is None or isinstance(v, (int, float)):
        return v
    v = _ILLEGAL.sub(" ", str(v))
    if v[:1] not in ("=", "+", "-", "@"):
        return v
    # 글자를 덧붙이면 값이 바뀐다. 문자열 칸으로 쓰고 quotePrefix 로 셀을 고쳐 입력해도 수식이 되지 않게 한다
    cell = Cell(ws, value=v)
    cell.data_type, cell.quotePrefix = "s", True
    return cell


def _append(ws, row):
    ws.append([_safe(ws, x) for x in row])


def to_xlsx(data: dict, include: dict = ALL_INCLUDE) -> bytes:
    wb = Workbook()
    c = data["consistency"]
    ws = wb.active
    ws.title = "요약"  # 설계서 38장: 기준일과 지식 버전을 항상 표시한다
    for row in (("문서 번호", c["doc_id"]), ("작업", data["job_id"]), ("기준일", c["as_of"]), ("판정 버전", data["version"]),
                ("지식", f"{c['knowledge']['provider']} / {c['knowledge']['version']}"), ("규칙표", c["knowledge"]["rules"]),
                ("저장본", (data["snapshot"] or {}).get("snapshot_no") or "저장 전"), ("미검토", data["counts"]["미검토"]),
                ("미검수 칸", data["counts"]["미검수 칸"])):
        _append(ws, row)
    head = ["법령", "항목", "성분", "MSDS 기재", "검증 결과", "판정 방법", "판정", "처리", "의견", "항목 ID"]
    for section in _sections(include):
        ws = wb.create_sheet(f"{section}항 판정")
        ws.append(head)
        for f, s in _rows(data, section):
            _append(ws, _cell(f, s, True) + [f["id"]])
    if include["regenerated_msds"]:
        ws = wb.create_sheet("재생성 MSDS")
        lines, error = _regenerated_lines(data["handoff"]["extraction"])
        for line in [_regen_failed(error)] if error else lines:
            _append(ws, [line])
    if include["components"]:
        ws = wb.create_sheet("성분")
        ws.append(_COMPONENT_HEAD)
        for row in _component_rows(data):
            _append(ws, row)
    if include["history"]:
        ws = wb.create_sheet("검토 이력")
        ws.append(["시각", "검토자", "대상", "처리", "의견"])
        for e in data["events"]:
            _append(ws, [e["at"], e["reviewer"], e["finding_id"], e["action"], e["comment"]])
        ws = wb.create_sheet("수정한 칸")
        for field in _edited_fields(data) or ["없음"]:
            _append(ws, [field])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_json(data: dict) -> bytes:
    return json.dumps({"contract": "report/1", "job_id": data["job_id"], "snapshot": data["snapshot"], "version": data["version"],
                       "extraction": data["handoff"]["extraction"], "field_status": data["handoff"].get("field_status"),
                       "consistency": data["consistency"], "reviews": data["reviews"], "events": data["events"]},
                      ensure_ascii=False, indent=1).encode("utf-8")


def render(data: dict, fmt: str, include: dict | None = None) -> bytes:
    """json 은 저장본 + 추출값 + 판정 + 검토 전체라 include 를 쓰지 않는다 (6-screens 3.1)."""
    include = include or ALL_INCLUDE
    if fmt == "html":
        return to_html(data, include).encode("utf-8")
    if fmt == "pdf":
        return to_pdf(data, include)
    return to_xlsx(data, include) if fmt == "xlsx" else to_json(data)
