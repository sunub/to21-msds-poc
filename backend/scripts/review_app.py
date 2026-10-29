"""검수 화면 (역할 A, D-36). 사용법: python scripts/review_app.py --doc T21-M013

왼쪽에 쪽 사진, 오른쪽에 그 쪽에서 나온 칸을 띄우고, 고른 결과를 검수표(data/review/<문서>.xlsx)의
검수 칸에 바로 적는다. 원본 기록은 검수표이고 이 화면은 엑셀 대신 쓰는 입력 도구라 열 형식은 그대로다.
내 컴퓨터(127.0.0.1)에서만 열린다. 쪽 사진은 TO21 자료라 밖으로 보내지 않는다 (D-47).
"""
import argparse
import json
import os
import platform
import re
import subprocess
import unicodedata
import webbrowser
from datetime import datetime
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import openpyxl
import pymupdf
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

import _common  # noqa: F401
from msds.common import paths
from msds.common.align import generic
from msds.common.jsonpath import from_cell, to_cell
from msds.common.priority import priority_of
from msds.common.schema import msds_item_schema
from msds.review.build_gold import _KEY_PATH, _ROW_PATH, _branch, _excel_value, _resolve, _schema_at
from msds.review.make_sheet import flat_doc, label_of
from msds.review.sheet_spec import COLUMNS, SHEET_INFO, SHEET_MAIN

HUMAN = COLUMNS[COLUMNS.index("검수 결과"):]          # 사람이 쓰는 열만 고친다
INFO_EDIT = ("검수 시작", "검수 끝", "검수자", "교차 확인자")
NEED_SOURCE = ("수정", "누락 추가")                       # 수정값, 수정 원문 조각, 수정 쪽을 함께 적는다 (계획서 13.2)


def _cell(v):
    return v if isinstance(v, str) else to_cell(_excel_value(v))


def _clean(v):
    s = ILLEGAL_CHARACTERS_RE.sub("", str(v or "")).strip()
    return s or None


class Sheet:
    """검수표 하나. 고칠 때마다 저장하고, 그사이 엑셀에서 파일이 바뀌었으면 다시 읽은 뒤 고친다.
    줄은 엑셀 행 번호가 아니라 '경로'로 찾는다(엑셀에서 정렬해도 안전)."""

    def __init__(self, doc_id: str):
        self.doc_id, self.path = doc_id, paths.review_sheet_path(doc_id)
        self.load()

    def load(self):
        self.wb = openpyxl.load_workbook(self.path)
        self.mtime = os.stat(self.path).st_mtime_ns
        self.col = {str(c.value): c.column for c in self.wb[SHEET_MAIN][1] if c.value}
        missing = [c for c in COLUMNS if c not in self.col]
        if missing:
            raise SystemExit(f"{self.path}: 검수표 열이 없음 {missing}")
        ws = self.wb[SHEET_MAIN]
        self.tags = [t for t in ("GPT", "Claude")       # 실버가 있는 모델만 채택할 수 있다
                     if any(ws.cell(r, self.col[f"{t} 값"]).value not in (None, "") for r in range(2, ws.max_row + 1))]
        self.results = {"수정", "삭제", "누락 추가", *(f"{t} 채택" for t in self.tags)}

    def fresh(self) -> bool:
        if os.stat(self.path).st_mtime_ns != self.mtime:
            self.load()
            return True
        return False

    def rows(self) -> list[dict]:
        ws, out = self.wb[SHEET_MAIN], []
        for r in range(2, ws.max_row + 1):
            row = {c: _cell(ws.cell(r, self.col[c]).value) for c in COLUMNS}
            if any(row.values()):
                out.append(row)
        return out

    def info(self) -> dict:
        return {str(a.value): _cell(b.value) for a, b in self.wb[SHEET_INFO].iter_rows(max_col=2)
                if a.value is not None}

    def _find(self, path: str) -> int | None:
        ws, c = self.wb[SHEET_MAIN], self.col["경로"]
        return next((r for r in range(2, ws.max_row + 1) if str(ws.cell(r, c).value or "").strip() == path), None)

    def _check(self, values) -> dict:
        """하나라도 틀리면 아무것도 고치지 않도록 쓰기 전에 모두 검사한다."""
        if not isinstance(values, dict):
            raise ValueError("values는 {열: 값} 형태여야 함")
        bad = [k for k in values if k not in HUMAN]
        if bad:
            raise ValueError(f"고칠 수 없는 열: {bad}")
        res = _clean(values.get("검수 결과"))
        if res and res not in self.results:
            raise ValueError(f"검수 결과는 {sorted(self.results)} 중 하나여야 함: {res}")
        if res in NEED_SOURCE and not all(_clean(values.get(k)) for k in ("수정값", "수정 원문 조각", "수정 쪽")):
            raise ValueError("수정과 누락 추가는 값, 원문 조각, 쪽을 모두 적어야 합니다")
        return values

    def _put(self, r: int, values: dict):
        ws = self.wb[SHEET_MAIN]
        for k, v in values.items():
            c = ws.cell(r, self.col[k])
            c.value = _clean(v)
            if k == "수정 쪽" and c.value and c.value.isdecimal():
                c.value = int(c.value)
            elif isinstance(c.value, str) and c.value.startswith("="):   # 수식이 되지 않게
                c.data_type = "s"

    def _stamp_start(self):
        ws = self.wb[SHEET_INFO]
        for a, b in ws.iter_rows(max_col=2):
            if a.value == "검수 시작" and not b.value:
                b.value = datetime.now().strftime("%Y-%m-%d %H:%M")

    def save_row(self, path: str, values: dict) -> dict:
        return self.save_rows([{"경로": path, "values": values}])[0]

    def save_rows(self, items: list) -> list[dict]:
        """여러 줄을 한 번에 저장한다(묶음 '전부 맞음'). 하나라도 틀리면 아무것도 고치지 않는다."""
        if not isinstance(items, list) or not items:
            raise ValueError("items는 [{경로, values}] 목록이어야 함")
        todo = []
        for it in items:
            path = str(it["경로"]).strip()
            r = self._find(path)
            if r is None:
                raise ValueError(f"검수표에 없는 경로: {path}")
            todo.append((r, _texted(path, self._check(it["values"]))))
        for r, values in todo:
            self._put(r, values)
        if any(v.get("검수 결과") for _, v in todo):
            self._stamp_start()
        self._save()
        return [{c: _cell(self.wb[SHEET_MAIN].cell(r, self.col[c]).value) for c in COLUMNS} for r, _ in todo]

    def add_row(self, values: dict) -> dict:
        """누락 추가: 두 모델이 모두 빠뜨린 칸을 새 줄로 넣는다."""
        if not isinstance(values, dict):
            raise ValueError("values는 {열: 값} 형태여야 함")
        values = dict(values)
        path = str(values.pop("경로", "") or "").strip()
        m = _ROW_PATH.fullmatch(path)
        if not m or not _KEY_PATH.fullmatch(m.group(2)):
            raise ValueError("경로 형식이 맞지 않음 (msds[0].이름[k=키].이름 …). 비슷한 줄의 경로를 본떠 고쳐 주세요")
        if _schema_at(generic(m.group(2))) is None:
            raise ValueError(f"TO21 스키마에 없는 칸입니다: {generic(m.group(2))}. 끝 이름을 비슷한 줄과 맞춰 주세요")
        if self._find(path):
            raise ValueError("이미 있는 칸입니다. 그 줄에서 '수정'을 고르세요")
        values = _texted(path, self._check({**values, "검수 결과": "누락 추가"}))
        ws = self.wb[SHEET_MAIN]
        r = ws.max_row + 1
        ws.cell(r, self.col["경로"]).value = path
        ws.cell(r, self.col["칸 이름"]).value = label_of(m.group(2))
        ws.cell(r, self.col["우선순위"]).value = priority_of(m.group(2))   # 1순위면 교차 확인 대상
        self._put(r, values)
        ws.auto_filter.ref = ws.dimensions         # 새 줄도 엑셀 필터에 들어가게
        self._stamp_start()
        self._save()
        return {c: _cell(ws.cell(r, self.col[c]).value) for c in COLUMNS}

    def remove_added(self, path: str):
        """사람이 넣은 누락 추가 줄을 지운다. 비워 두기만 하면 골드셋에 값이 빈 항목이 생긴다."""
        r = self._find(path)
        ws = self.wb[SHEET_MAIN]
        if r is None or ws.cell(r, self.col["일치"]).value not in (None, ""):
            raise ValueError("사람이 넣은 누락 추가 줄만 지울 수 있습니다")
        ws.delete_rows(r)
        ws.auto_filter.ref = ws.dimensions
        self._save()

    def cross_done(self, name: str) -> int:
        """교차 확인 반영 (역할 A 가이드 4.6): 검수 담당이 의견을 반영한 뒤 1순위 줄에 교차 확인 담당 이름을 적는다."""
        name = _clean(name)
        if not name:
            raise ValueError("교차 확인 담당 이름을 적어 주세요")
        ws, n = self.wb[SHEET_MAIN], 0
        left = sum(1 for r in range(2, ws.max_row + 1) if str(ws.cell(r, self.col["우선순위"]).value) == "1"
                   and not ws.cell(r, self.col["검수 결과"]).value)
        if left:                          # 가이드 4.6: 1순위를 끝낸 뒤 교차 확인
            raise ValueError(f"1순위 {left}줄이 아직 미검수입니다. 1순위를 모두 끝낸 뒤 반영해 주세요")
        for r in range(2, ws.max_row + 1):
            if str(ws.cell(r, self.col["우선순위"]).value) == "1":
                ws.cell(r, self.col["교차 확인자"]).value = name
                n += 1
        self.save_info("교차 확인자", name)
        return n

    def save_info(self, key: str, value: str):
        if key not in INFO_EDIT:
            raise ValueError(f"고칠 수 없는 문서 정보: {key}")
        ws = self.wb[SHEET_INFO]
        cell = next((b for a, b in ws.iter_rows(max_col=2) if a.value == key), None)
        if cell is None:
            ws.append([key, None])
            cell = ws.cell(ws.max_row, 2)
        cell.value = _clean(value)
        self._save()

    def excel_open(self) -> bool:
        """엑셀이 이 파일을 열면 같은 폴더에 '~$파일이름' 잠금 파일이 생긴다(윈도우, 맥 모두).
        맥 엑셀은 파일을 잠그지 않아 그대로 저장하면 나중에 엑셀이 덮어쓰므로 미리 막는다."""
        n = self.path.name
        return any((self.path.parent / f"~${x}").exists() for x in (n, n[2:]))

    def _save(self):
        if self.excel_open():
            self.load()       # 저장 못 한 변경은 버리고 파일 상태로 되돌린다
            raise PermissionError(f"엑셀에서 이 검수표가 열려 있습니다. 엑셀을 닫고 다시 눌러 주세요. 엑셀을 닫았는데도 계속 뜨면 같은 폴더의 '~${self.path.name}' 파일을 지우세요")
        try:
            self.wb.save(self.path)
        except PermissionError:
            self.load()       # 저장 못 한 변경은 버리고 파일 상태로 되돌린다
            raise PermissionError("엑셀에서 이 검수표가 열려 있어 저장하지 못했습니다. 엑셀을 닫고 다시 눌러 주세요")
        self.mtime = os.stat(self.path).st_mtime_ns


def open_chrome(url: str):
    """크롬으로 연다(이 화면은 크롬 기준). 크롬이 없으면 기본 브라우저."""
    system = platform.system()
    if system == "Darwin":
        cmd = ["open", "-a", "Google Chrome", url]
    elif system == "Windows":
        cmd = ["cmd", "/c", "start", "", "chrome", url]
    elif "microsoft" in platform.release().lower():      # WSL: 윈도우 쪽 크롬
        cmd = ["cmd.exe", "/c", "start", "", "chrome", url]
    else:
        cmd = ["google-chrome", url]
    try:
        if subprocess.run(cmd, capture_output=True, timeout=15).returncode == 0:
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    webbrowser.open(url)


def _texted(path: str, values: dict) -> dict:
    """스키마상 글자만 받는 칸에 12345처럼 숫자로 읽히는 수정값을 적으면 골드셋에서 숫자가 되어
    스키마 오류가 나므로 따옴표로 감싼다 ("12345")."""
    v, m = values.get("수정값"), _ROW_PATH.fullmatch(path)
    if v in (None, "") or not m or not isinstance(from_cell(str(v)), (int, float, bool)):
        return values
    s = _schema_at(generic(m.group(2))) or {}
    types = {t for x in [s, *s.get("anyOf", [])] for t in ([x["type"]] if isinstance(x.get("type"), str) else x.get("type") or [])}
    if "string" in types and not types & {"number", "integer", "boolean"}:
        return {**values, "수정값": json.dumps(str(v).strip(), ensure_ascii=False)}
    return values


def _use_repo_data():
    """main의 paths.py는 ROOT를 backend/로 잡아 저장소 최상위 data/, to21/을 못 찾는다(#1에서 고침).
    그때까지 이 화면만 최상위를 쓰게 한다. ponytail: #1이 합쳐지면 이 함수를 지운다."""
    top = paths.ROOT.parent
    if paths.REVIEW.exists() or not (top / "data" / "review").exists():
        return
    for name in ("DATA", "RAW", "PAGES", "SILVER", "REVIEW", "GOLD", "MANIFEST", "RUNS", "TO21"):
        setattr(paths, name, top / getattr(paths, name).relative_to(paths.ROOT))


@lru_cache(maxsize=None)
def field_order(gpath: str) -> list[int]:
    """번호를 지운 경로의 칸마다 스키마 안 순서 번호. 스키마는 MSDS 문서 순서라, 카드 안 칸을 문서에서 읽는 순서로 놓는 데 쓴다."""
    s, out = msds_item_schema(), []
    for name, arr in re.findall(r"([^.\[\]]+)|(\[\])", gpath.removeprefix("msds[].")):
        if arr:
            s = (_branch(s, "array") or {}).get("items")
        else:
            props = (_branch(s, "object") or {}).get("properties") or {}
            out.append(list(props).index(name) if name in props else 999)
            s = props.get(name)
        if s is None:
            break
        s = _resolve(s)
    return out


@lru_cache(maxsize=None)
def silver_rank(doc_id: str) -> dict[str, int]:
    """칸 경로마다 실버 JSON 안 순서. 모델은 목록을 문서에 적힌 순서로 내므로, 순번 칸이 없는 목록(8항 노출기준 등)도 문서 순서로 놓을 수 있다."""
    rank = {}
    for t in ("claude", "gpt"):
        f = paths.silver_path(t, doc_id)
        if f.exists():
            for p in flat_doc(json.loads(f.read_text(encoding="utf-8"))):
                rank.setdefault(p, len(rank))
    return rank


def page_count(doc_id: str) -> int:
    return len(list(paths.page_dir(doc_id).glob("p*.png")))


_DASH = str.maketrans("‐‑‒–—―−", "-------")    # 글자층의 en dash 등과 조각의 '-'를 같게 본다


def _norm(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", s or "").lower().translate(_DASH) if not ch.isspace() and ch != "|")


class Locator:
    """고른 칸이 쪽 사진의 어디인지 찾는다. 원본 PDF 글자층에서 값과 원문 조각을 찾아
    사진 크기에 대한 비율(0~1) 상자로 돌려준다. 글자층이 깨졌거나 순서가 섞여 못 찾으면 빈 목록."""

    def __init__(self, doc_id: str):
        self.doc, self.ok, self.cache = None, set(), {}
        meta_path = paths.page_meta(doc_id)
        if not meta_path.exists():        # preprocess.py의 meta.json이 없으면(version2만 복사했을 때 등) 상자 없이 연다
            print(f"위치 상자 없이 엽니다: {meta_path} 없음")
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pdf = paths.RAW / meta["source_file"]
        self.doc = pymupdf.open(pdf) if pdf.exists() else None
        self.ok = {p["page"] for p in meta["pages"] if p["state"] == "정상"}

    def _chars(self, no: int):
        if no not in self.cache:
            page, out = self.doc[no - 1], []
            for b in page.get_text("rawdict")["blocks"]:
                for line in b.get("lines", []):
                    for span in line["spans"]:
                        for c in span["chars"]:
                            out += [(ch, c["bbox"]) for ch in _norm(c["c"])]
            self.cache[no] = ("".join(ch for ch, _ in out), [bb for _, bb in out], page)
        return self.cache[no]

    def locate(self, no: int, value: str, snippet: str) -> dict:
        if not self.doc or no not in self.ok or not 1 <= no <= len(self.doc):
            return {"value": [], "area": [], "many": 0}
        text, boxes, page = self._chars(no)
        center = lambda s: ((boxes[s][0] + boxes[s][2]) / 2, (boxes[s][1] + boxes[s][3]) / 2)
        dist = lambda s, a: abs(center(s)[0] - a[0]) / 3 + abs(center(s)[1] - a[1])   # 같은 줄을 더 가깝게 본다
        near = page.rect.height / 4

        def hits(s):
            n = _norm(s)
            return [(m.start(), len(n)) for m in re.finditer(re.escape(n), text)] if len(n) >= 2 else []

        def same(a, b):         # 같은 줄인가 (글자 높이의 절반 안)
            return abs(center(a)[1] - center(b)[1]) < (boxes[a][3] - boxes[a][1]) * 0.6

        def pick(tokens, anchor, one_line=True):
            """토큰들이 가장 많이 함께 나오는 자리를 고른다. 같은 점수면 기준점에 가까운 자리.
            one_line이면 그 줄에 있는 토큰만 쓴다(표 칸, 값). 아니면 그 자리 근처(쪽 높이 1/4 안)까지."""
            found = [h for h in (hits(t) for t in tokens) if h]
            if one_line:          # 줄을 넘어 이어 붙은 자리(윗줄 끝 + 아랫줄 처음)는 버린다
                found = [h for h in ([x for x in h if all(same(i, x[0]) for i in range(x[0], x[0] + x[1]))] for h in found) if h]
            if not found or (anchor is None and len(found) == 1 and len(found[0]) > 1):   # 한 토큰이 여러 번 나오면 어디인지 모른다
                return [], anchor
            close = same if one_line else (lambda x, c: dist(x, center(c)) < near)
            band = lambda x, c: abs(center(x)[1] - center(c)[1]) <= 2.5 * (boxes[c][3] - boxes[c][1])   # 같은 단락쯤(줄 간격 2.5배 안)
            score = lambda c: (sum(any(same(x, c) for x, _ in h) for h in found),          # 같은 줄에 함께 있는 토큰 수가 먼저
                               0 if one_line else sum(any(band(x, c) for x, _ in h) for h in found),   # 그다음 같은 단락에 함께 있는 토큰 수
                               sum(any(close(x, c) for x, _ in h) for h in found), -dist(c, anchor) if anchor else 0)
            cands = [s for h in found for s, _ in h if anchor is None or dist(s, anchor) < near]
            if not cands:
                return [], anchor
            best = max(cands, key=score)
            far = (lambda c, b: not same(c, b)) if one_line else \
                (lambda c, b: abs(center(c)[1] - center(b)[1]) > 2.5 * (boxes[b][3] - boxes[b][1]))   # 여러 줄이면 다른 단락
            if anchor is None and any(score(c) == score(best) and far(c, best) for c in cands):
                return [], anchor     # 점수가 같은 자리가 다른 줄에도 있으면 어디인지 모른다(엉뚱한 곳보다 안 그리는 게 낫다)
            out = [min((x for x in h if close(x[0], best)), key=lambda x: (not same(x[0], best), dist(x[0], center(best))))
                   for h in found if any(close(x[0], best) for x in h)]      # 같은 줄에 있으면 그 자리를 먼저
            if not one_line:      # 여러 줄 덩어리: 고른 줄에서 줄 간격 2.5배 안으로 이어지는 줄만 (다른 단락에 붙지 않게)
                lh, lo, hi, keep = boxes[best][3] - boxes[best][1], center(best)[1], center(best)[1], []
                for x in sorted(out, key=lambda x: abs(center(x[0])[1] - center(best)[1])):
                    y = center(x[0])[1]
                    if lo - 2.5 * lh <= y <= hi + 2.5 * lh:
                        keep.append(x)
                        lo, hi = min(lo, y), max(hi, y)
                out = keep
            return out, center(best)

        whole, area, anchor = hits(snippet), [], None
        if len(whole) == 1:
            area, anchor = whole, center(whole[0][0])
        elif whole:               # 조각 전체가 쪽에 여러 번 나오면 어느 것인지 몰라 후보를 모두 칠하고 몇 곳인지 알린다
            area = whole
        else:
            parts = [p for p in re.split(r"\s*\|\s*|\n", snippet or "") if len(_norm(p)) >= 2]
            area, anchor = pick(parts, None)
            if not area:          # 여러 줄 덩어리(회사 정보 등)는 낱말로 찾는다
                area, anchor = pick([t for t in (w.rstrip(".,;:") for w in re.split(r"\s+", snippet or "")) if len(_norm(t)) >= 2], None, one_line=False)
                # 낱말 끝 마침표는 뗀다: 글자층에서 마침표가 떨어져 있으면 '받으시오.'가 앞 단락 줄에서만 맞는다
        vh = hits(value)
        if anchor is not None and vh:       # 원문 조각 상자와 같은 줄에 있는 자리를 먼저, 없으면 가장 가까운 자리
            m = min(vh, key=lambda x: (not any(same(x[0], s) for s, _ in area), dist(x[0], anchor)))
            val = [m] if dist(m[0], anchor) < near else []
        elif whole:               # 후보가 여러 곳이면 값도 후보 줄마다 있는 자리를 모두
            val = [x for x in vh if any(same(x[0], s) for s, _ in area)]
        else:
            val = vh if len(vh) == 1 else []
        if not val:
            val, _ = pick([t for t in re.split(r"\s+", value or "") if len(_norm(t)) >= 2], anchor)
        W, H = page.rect.width, page.rect.height

        def rects(spans):
            out = []
            for s, n in spans:
                line = None
                for i in range(s, s + n):
                    r = pymupdf.Rect(boxes[i]) * page.rotation_matrix   # 글자 좌표는 회전 전 기준, 사진은 회전 후
                    if line is not None and abs(r.y0 - line.y0) < r.height / 2 and r.x0 >= line.x0 - 1:
                        line |= r
                    else:
                        if line is not None:
                            out.append(line)
                        line = r
                out.append(line)
            return [[round(r.x0 / W, 4), round(r.y0 / H, 4), round(r.width / W, 4), round(r.height / H, 4)] for r in out]

        return {"value": rects(val), "area": rects(area), "many": len(whole)}


def _plain(v) -> str:
    """검수표 칸 글자 → 찾을 글자. '"54588"'처럼 따옴표로 감싼 글자 값은 따옴표를 뗀다."""
    v = from_cell(str(v)) if v not in (None, "") else ""
    if isinstance(v, dict):               # Q 객체 등은 원문(raw, text)으로만 찾는다
        return str(v.get("raw") or v.get("text") or "")
    return "" if isinstance(v, list) else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def make_handler(sheet: Sheet, readonly: bool, locator: Locator):
    def locate(query: str) -> dict:
        sheet.fresh()                     # 엑셀에서 고친 직후에도 지금 값으로 찾는다
        q = parse_qs(query)
        no, want = int(q["page"][0]), set(q.get("path", []))
        out = {"value": [], "area": [], "many": 0}
        for r in sheet.rows():
            if r["경로"] in want:
                t = next((t for t in ("Claude", "GPT") if r[f"{t} 값"] != ""), "Claude")
                edited = r["수정값"] != "" and r["검수 결과"] in NEED_SOURCE
                got = locator.locate(no, _plain(r["수정값"] if edited else r[f"{t} 값"]),
                                     r["수정 원문 조각"] if edited else r[f"{t} 원문 조각"])
                for k in ("value", "area"):
                    out[k] += [b for b in got.get(k, []) if b not in out[k]]
                out["many"] = max(out["many"], got.get("many", 0))
        return out

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # 요청마다 찍히는 줄은 끈다
            pass

        def _local(self) -> bool:
            """다른 웹페이지가 이 화면을 대신 부르지 못하게(DNS 재바인딩) 주소가 내 컴퓨터일 때만 받는다."""
            port = self.server.server_port
            if self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return True
            self._send(403, b"forbidden", "text/plain")
            return False

        def _send(self, code: int, body: bytes, ctype: str, cache: bool = False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            if not self._local():
                return
            if self.path == "/":
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if self.path == "/api/state":
                reloaded = sheet.fresh()
                rows = sheet.rows()
                return self._json(200, {"doc": sheet.doc_id, "file": str(sheet.path), "info": sheet.info(),
                                        "rank": silver_rank(sheet.doc_id),
                                        "rows": rows, "order": {r["경로"]: field_order(generic(r["경로"])) for r in rows}, "pages": page_count(sheet.doc_id), "reloaded": reloaded,
                                        "excel_open": sheet.excel_open(), "readonly": readonly})
            u = urlsplit(self.path)
            if u.path == "/api/locate":
                try:
                    return self._json(200, locate(u.query))
                except (KeyError, ValueError, IndexError) as e:
                    return self._json(400, {"error": str(e)})
            m = re.fullmatch(r"/page/(\d+)\.png", self.path)
            if m and (p := paths.page_png(sheet.doc_id, int(m.group(1)))).exists():
                return self._send(200, p.read_bytes(), "image/png", cache=True)
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self._local():
                return
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):   # 다른 사이트의 폼 전송 차단
                return self._json(415, {"error": "JSON만 받습니다"})
            if readonly:
                return self._json(403, {"error": "교차 확인 화면은 검수표를 고치지 않습니다 (역할 A 가이드 4.6)"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                reloaded = sheet.fresh()
                if self.path == "/api/save":
                    out = {"row": sheet.save_row(str(body["경로"]).strip(), body["values"])}
                elif self.path == "/api/save_many":
                    out = {"rows": sheet.save_rows(body["items"])}
                elif self.path == "/api/add":
                    out = {"row": sheet.add_row(body["values"])}
                elif self.path == "/api/remove":
                    sheet.remove_added(str(body["경로"]).strip())
                    out = {}
                elif self.path == "/api/cross":
                    out = {"count": sheet.cross_done(body["name"]), "rows": sheet.rows()}
                elif self.path == "/api/info":
                    sheet.save_info(body["key"], body["value"])
                    out = {"info": sheet.info()}
                else:
                    return self._json(404, {"error": "없는 주소"})
                self._json(200, {**out, "reloaded": reloaded})
            except PermissionError as e:
                self._json(409, {"error": str(e)})
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                sheet.load()                  # 반쯤 바뀐 메모리 상태를 버리고 파일 상태로 되돌린다
                self._json(400, {"error": str(e)})

    return Handler


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>검수 화면</title>
<style>
:root { --bg:#f4f5f7; --panel:#fff; --ink:#1b2430; --muted:#5d6877; --line:#dde2e8; --accent:#e8630a;
  --ok:#1f8a4c; --okbg:#e3f4ea; --warn:#b7791f; --warnbg:#fbf1dc; --bad:#c53030; --badbg:#fde8e8; --chip:#eef1f4; }
@media (prefers-color-scheme: dark) { :root { --bg:#12161c; --panel:#1b2129; --ink:#e6eaef; --muted:#9aa5b2; --line:#2c3540;
  --accent:#ff8a3d; --ok:#5fd08f; --okbg:#17321f; --warn:#f0b85a; --warnbg:#3a2e14; --bad:#ff7a7a; --badbg:#3d1c1c; --chip:#232b35; } }
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { background: var(--bg); color: var(--ink); font: 14px/1.5 "Pretendard", "Noto Sans KR", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  -webkit-font-smoothing: antialiased;
  word-break: keep-all; overflow-wrap: anywhere; display: grid; grid-template-rows: auto 1fr; }
button, input, textarea, select { font: inherit; color: inherit; }
button { border: 1px solid var(--line); background: var(--panel); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
button:hover { border-color: var(--accent); }
button.on { background: var(--accent); border-color: var(--accent); color: #fff; }
input, textarea { border: 1px solid var(--line); background: var(--bg); border-radius: 6px; padding: 5px 8px; width: 100%; }
header { background: var(--panel); border-bottom: 1px solid var(--line); padding: 8px 14px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
header h1 { font-size: 1rem; margin: 0; }
.grp { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.lbl { color: var(--muted); font-size: .8rem; }
#me { width: 9em; }
#q { width: 12em; }
.bar { width: 160px; height: 8px; background: var(--chip); border-radius: 4px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--ok); }
#saved { font-size: .8rem; color: var(--muted); }
main { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(360px, 1fr); min-height: 0; }
#left { display: grid; grid-template-rows: auto 1fr; min-height: 0; border-right: 1px solid var(--line); }
#pager { display: flex; gap: 4px; flex-wrap: wrap; padding: 8px 10px; background: var(--panel); border-bottom: 1px solid var(--line); }
#pager button { min-width: 2.6em; padding: 2px 6px; font-variant-numeric: tabular-nums; }
#pager button small { color: var(--muted); margin-left: 2px; }
#pager button.on small { color: #fff; }
#pager button.clear { border-color: var(--ok); }
#view { overflow: auto; padding: 10px; scrollbar-gutter: stable; overscroll-behavior: contain; }
#view .pgw { position: relative; margin: 0 auto; }
#view img { display: block; width: 100%; box-shadow: 0 1px 4px rgba(0,0,0,.25); background: #fff; }
.hl { position: absolute; pointer-events: none; border-radius: 2px; }
.hl.area { background: rgba(255, 214, 0, .28); outline: 1px solid rgba(214, 160, 0, .55); }
.hl.value { background: rgba(232, 99, 10, .22); outline: 2px solid #e8630a; outline-offset: 1px; }
#right { overflow: auto; padding: 10px 12px 40px; min-height: 0; scrollbar-gutter: stable; overscroll-behavior: contain; }
.none { color: var(--muted); padding: 30px; text-align: center; }
.card { content-visibility: auto; contain-intrinsic-size: auto 220px; background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--line); border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }
.card.p1 { border-left-color: var(--bad); } .card.p2 { border-left-color: var(--warn); }
.card.done { opacity: .62; } .card.done:hover { opacity: 1; }
.card h3 { font-size: .95rem; margin: 0 0 2px; display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
.path { font-size: .72rem; color: var(--muted); font-family: ui-monospace, Consolas, monospace; }
.tag { font-size: .72rem; padding: 0 7px; border-radius: 99px; background: var(--chip); color: var(--muted); white-space: nowrap; }
.tag.bad { background: var(--badbg); color: var(--bad); } .tag.ok { background: var(--okbg); color: var(--ok); } .tag.warn { background: var(--warnbg); color: var(--warn); }
.val { font-size: 1.05rem; font-weight: 700; margin: 6px 0 2px; white-space: pre-wrap; }
.val small { font-weight: 400; color: var(--muted); font-size: .75rem; margin-right: 6px; }
.src { font-size: .85rem; color: var(--muted); border-left: 3px solid var(--line); padding-left: 8px; margin: 4px 0; white-space: pre-wrap;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; cursor: zoom-in; }
.src.full { display: block; cursor: zoom-out; }
.card h3 { cursor: pointer; }
.card h3 b { font-weight: 600; color: var(--muted); }
.ln { border-top: 1px dashed var(--line); padding: 6px 4px 6px 6px; margin: 0 -4px; border-radius: 6px; cursor: pointer; }
.ln:first-of-type { border-top: 0; }
.ln.sel { background: rgba(232, 99, 10, .08); }
.ln.done .lt { opacity: .62; }
.lt { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.fn { font-size: .8rem; color: var(--muted); min-width: 5.5em; }
.v { font-weight: 700; white-space: pre-wrap; }
.v small { font-weight: 400; color: var(--muted); }
.acts.sm button { padding: 1px 8px; font-size: .82rem; }
.card > .acts { border-top: 1px solid var(--line); padding-top: 8px; }
details { font-size: .82rem; color: var(--muted); margin: 4px 0; }
.acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.res { font-weight: 700; color: var(--ok); }
.ed { display: grid; gap: 6px; margin-top: 8px; padding: 8px; background: var(--bg); border-radius: 6px; }
.ed label { font-size: .78rem; color: var(--muted); }
.memo { font-size: .82rem; color: var(--warn); margin-top: 4px; }
#toast { position: fixed; bottom: 14px; left: 50%; transform: translateX(-50%); padding: 8px 14px; border-radius: 8px; background: var(--ink); color: var(--bg); display: none; max-width: 90vw; z-index: 9; }
#toast.err { background: var(--bad); color: #fff; }
.help { font-size: .8rem; color: var(--muted); }
@media (max-width: 900px) { main { grid-template-columns: 1fr; grid-template-rows: 55vh auto; } }
</style></head><body>
<header>
  <h1 id="title">검수 화면</h1>
  <div class="grp"><span class="lbl">내 이름</span><input id="me" placeholder="이름 (필수)"></div>
  <span id="modelbl" class="tag"></span>
  <div class="grp" id="prio"><span class="lbl">우선순위</span><button data-p="1" class="on" title="D-36: 1순위부터">1</button><button data-p="2">2</button><button data-p="3">3</button></div>
  <div class="grp" id="stat"><span class="lbl">보기</span><button data-s="todo" class="on">남은 칸</button><button data-s="all">전체</button></div>
  <input id="q" placeholder="찾기 (칸 이름, 값)">
  <div class="grp"><div class="bar"><i id="barfill"></i></div><span id="prog" class="lbl"></span></div>
  <div class="grp"><button id="crossbtn" title="디스코드의 교차 확인 의견을 반영한 뒤 누름">교차 확인 반영</button><button id="endbtn">검수 끝 시각 적기</button><span id="saved"></span></div>
</header>
<main>
  <section id="left"><div id="pager"></div><div id="view"></div></section>
  <section id="right"></section>
</main>
<div id="toast"></div>
<script>
const $ = s => document.querySelector(s);
const MAC = /Mac/i.test(navigator.userAgentData?.platform || navigator.platform), MOD = MAC ? "⌘" : "Ctrl";
const CHROMIUM = !!navigator.userAgentData?.brands?.some(b => /Chrom/.test(b.brand));
const h = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let S = {rows: [], info: {}, pages: 0}, page = 1, mode = "검수", prio = new Set([1]), show = "todo", q = "", open = null, zoom = 100;
let tags = [];
const store = (k, v) => { try { v === undefined ? 0 : localStorage.setItem(k, v); return localStorage.getItem(k); } catch { return null; } };
$("#me").value = store("review.me") || "";
$("#me").onchange = e => store("review.me", e.target.value.trim());

function pagesOf(r) {
  const s = r["Claude 쪽"] || r["GPT 쪽"] || r["수정 쪽"] || "";
  const ns = (String(s).match(/\d+/g) || []).map(Number).filter(n => n >= 1 && n <= S.pages);
  return ns.length ? [...new Set(ns)] : [0];
}
const inMode = r => mode === "검수" || String(r["우선순위"]) === "1";
const isDone = r => mode === "검수" && !!r["검수 결과"];
const visible = r => inMode(r) && prio.has(Number(r["우선순위"]) || 3) && (show === "all" || !isDone(r))
  && (!q || [r["칸 이름"], r["경로"], ...tags.map(t => r[t + " 값"]), r["수정값"]].join(" ").toLowerCase().includes(q));

async function api(url, body) {
  const res = await fetch(url, body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {});
  const j = await res.json();
  if (!res.ok) throw new Error(j.error || res.status);
  if (j.reloaded && body) { toast("엑셀에서 바뀐 내용을 다시 읽었습니다"); await load(); }
  return j;
}
function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = err ? "err" : ""; t.style.display = "block";
  clearTimeout(toast.t); toast.t = setTimeout(() => t.style.display = "none", err ? 7000 : 2500);
}
async function load() {
  S = await api("/api/state");
  tags = ["GPT", "Claude"].filter(t => S.rows.some(r => r[t + " 값"] !== ""));
  mode = S.readonly ? "교차" : "검수";
  $("#modelbl").textContent = S.readonly ? "교차 확인 (보기 전용)" : "검수";
  for (const id of ["#crossbtn", "#endbtn"]) $(id).hidden = S.readonly;
  $("#title").textContent = "검수 화면 " + S.doc;
  if (S.excel_open) toast("엑셀에서 이 검수표가 열려 있습니다. 엑셀을 닫아야 저장됩니다", true);
  document.title = "검수 " + S.doc;
  render();
}
function render() { renderPager(); renderView(); renderCards(); renderProg(); }

function renderProg() {
  const own = r => r["일치"] !== "";      // 진행률은 스크립트가 만든 줄 기준 (누락 추가 줄 제외)
  const base = S.rows.filter(r => inMode(r) && own(r)), done = base.filter(isDone).length;
  const by = n => { const x = S.rows.filter(r => own(r) && String(r["우선순위"]) === n); return `${n}순위 ${x.filter(r => !!r["검수 결과"]).length}/${x.length}`; };
  $("#prog").textContent = mode === "검수" ? `검수 ${done} / ${base.length} (${by("1")}, ${by("2")}, ${by("3")})` : `1순위 ${base.length}줄`;
  $("#barfill").style.width = (base.length ? 100 * done / base.length : 0) + "%";
}
function renderPager() {
  const cnt = {};
  for (const r of S.rows) if (visible(r)) for (const p of pagesOf(r)) cnt[p] = (cnt[p] || 0) + 1;
  const list = [...Array(S.pages).keys()].map(i => i + 1);
  if (S.rows.some(r => pagesOf(r)[0] === 0)) list.push(0);
  $("#pager").innerHTML = `<button id="prev" title="이전 쪽 (←)">◀</button>` + list.map(p =>
    `<button data-pg="${p}" class="${p === page ? "on" : ""} ${cnt[p] ? "" : "clear"}">${p || "쪽 없음"}${cnt[p] ? `<small>${cnt[p]}</small>` : ""}</button>`).join("")
    + `<button id="next" title="다음 쪽 (→)">▶</button><span class="grp" style="margin-left:auto"><button id="zo">−</button><button id="zf">맞춤</button><button id="zi">+</button></span>`;
}
function renderView() {
  const v = $("#view"), w = v.querySelector(".pgw");
  if (page && w && Number(w.dataset.pg) === page) { w.style.width = zoom + "%"; return; }   // 확대만 바뀌면 사진을 다시 그리지 않는다
  v.innerHTML = page ? `<div class="pgw" data-pg="${page}" style="width:${zoom}%"><img src="/page/${page}.png" alt="${page}쪽" decoding="async"><div id="hls"></div></div>`
    : noPage();
}
// 쪽 번호가 없는 칸: 대부분 '문서에 이런 표기가 없다'는 판단이라 가리킬 쪽이 없다. 같은 항이 있는 쪽으로 가는 단추를 준다
function noPage() {
  const sec = r => (String(r["칸 이름"]).match(/^\d+항/) || [""])[0];
  const secs = [...new Set(S.rows.filter(r => visible(r) && pagesOf(r)[0] === 0).map(sec).filter(Boolean))];
  const jump = secs.map(x => {
    const ps = [...new Set(S.rows.filter(r => sec(r) === x).flatMap(pagesOf).filter(Boolean))].sort((a, b) => a - b);
    return ps.length ? `<p>${x}이 있는 쪽: ${ps.map(p => `<button data-go="${p}">${p}쪽</button>`).join(" ")}</p>` : "";
  }).join("");
  return `<div class="none"><p>여기 칸들은 모델이 쪽 번호를 적지 않은 칸입니다. 대부분 "문서에 이런 표기가 없다"는 판단이라 가리킬 쪽이 없습니다.
    예를 들어 "유해성분 미함유 표기: false"는 문서에 "유해성분 없음"이라는 표기가 없다는 뜻입니다.</p>
    <p>확인하는 법: 아래 쪽을 열어 그 표기가 정말 없는지 보고, 없으면 '맞음'입니다. 있으면 '수정'으로 값과 쪽을 적어 주세요.</p>${jump}</div>`;
}
$("#view").addEventListener("click", e => { const b = e.target.closest("button[data-go]"); if (b) go(Number(b.dataset.go)); });
// 고른 칸(또는 묶음)이 사진의 어디인지 표시한다. 노란 상자 = 원문 조각, 주황 테두리 = 값
let sel = [], selSeq = 0;
async function highlight(paths) {
  sel = paths; const seq = ++selSeq;
  document.querySelectorAll(".ln, .card").forEach(el => el.classList.remove("sel"));
  for (const p of paths) document.querySelector(`.ln[data-p="${CSS.escape(p)}"]`)?.classList.add("sel");
  const box = $("#hls"); if (!box || !page || !paths.length) return box && (box.innerHTML = "");
  const qs = new URLSearchParams([["page", page], ...paths.map(p => ["path", p])]);
  let j; try { j = await api("/api/locate?" + qs); } catch { return; }
  if (seq !== selSeq) return;                          // 그사이 다른 칸을 골랐으면 버린다
  const div = (k, [x, y, w, hh]) => `<div class="hl ${k}" style="left:${x*100}%;top:${y*100}%;width:${w*100}%;height:${hh*100}%"></div>`;
  box.innerHTML = j.area.map(b => div("area", b)).join("") + j.value.map(b => div("value", b)).join("");
  const first = box.querySelector(".value") || box.querySelector(".area");
  if (first) first.scrollIntoView({block: "center", inline: "nearest", behavior: "smooth"});
  if (j.many > 1) toast(`같은 문장이 이 쪽에 ${j.many}곳 있어 모두 노랗게 칠했습니다. 카드 제목을 보고 맞는 곳을 확인해 주세요`);
  else if (!first) toast("사진에서 위치를 찾지 못했습니다 (글자층이 없거나 순서가 섞인 쪽). 사진에서 직접 찾아 주세요");
}
// 같은 대상(분류 하나, 회사 하나, 성분 하나)의 칸은 카드 한 장으로 묶어 보여 준다. 저장은 지금처럼 칸마다 한 줄
function gkey(p) {
  let g = p.slice(0, p.lastIndexOf("]") + 1);
  if (/^msds\[\d+\]$/.test(g)) g = p.split(".").slice(0, 2).join(".");
  return g;
}
const parts = name => { const m = String(name).match(/^(.*?) · (.*?)(?: \((.*)\))?$/); return m ? {sec: m[1], fn: m[2], key: m[3] || ""} : {sec: name, fn: "", key: ""}; };
// '"54588"'처럼 글자로 저장한 값은 따옴표 없이 보여 준다
const plain = v => { const s = String(v ?? ""); if (/^".*"$/s.test(s)) { try { return JSON.parse(s); } catch {} } return s; };
const GHS = {GHS01: "폭발성 폭탄", GHS02: "불꽃", GHS03: "원 위의 불꽃", GHS04: "가스 실린더", GHS05: "부식성",
  GHS06: "해골과 X자형 뼈", GHS07: "감탄부호", GHS08: "건강 유해성", GHS09: "환경"};
// 순번(seq), 대상 성분(comp_ref)은 원문 글자가 아니라 줄끼리 잇는 번호라 숫자 대신 뜻을 보여 준다
function compName(p, v, t) {
  if (v === "MIX") return "제품 전체";
  const m = p.match(/^msds\[\d+\]/)[0];
  const c = S.rows.find(x => x["경로"].startsWith(m + ".components[") && x["경로"].endsWith("].seq") && plain(x[t + " 값"]) === v);   // 모델마다 성분 번호가 다를 수 있어 같은 모델 값으로 찾는다
  const k = c && c["경로"].match(/\[k=([^\]]*)\]/);
  return k ? `${v}번 성분 (${k[1]})` : `${v}번 성분`;
}
function meaning(r, v, t) {
  const p = r["경로"];
  if (p.endsWith(".comp_ref")) return compName(p, v, t);
  if (p.endsWith(".parent_seq")) return compName(p, v, t) + "의 하위 성분";
  if (p.endsWith(".seq")) return p.includes(".components[") ? `성분표 ${v}번째 줄` : `${v}번째`;
  if (p.includes(".extras[") && p.endsWith(".page")) return v + "쪽";
  if (p.includes(".extras[") && p.endsWith(".section_no")) return v + "항";
  return "";
}
// Q(숫자와 단위), COND(측정 조건), STMT(서술 한 줄)는 JSON 대신 읽기 쉬운 글로 보여 준다. 검수표에는 JSON 그대로 저장된다
const OPS = {">=": "≥", ">": ">", "<=": "≤", "<": "<", "=": "="};
function condText(c) {
  const L = [["temp", "온도", "temp_unit"], ["pressure", "압력", "pressure_unit"], ["method", "방법"], ["reference", "기준"], ["conc_value", "농도", "conc_unit"]];
  return L.filter(([k]) => c[k] != null).map(([k, n, u]) => `${n} ${c[k]}${u && c[u] ? " " + c[u] : ""}`).join(", ");
}
function fmt(s) {
  s = String(s ?? "");
  if (!/^[{[]/.test(s)) return h(s);
  let o; try { o = JSON.parse(s); } catch { return h(s); }
  if (Array.isArray(o)) return o.every(x => typeof x !== "object") ? h(o.join("; ")) : h(s);
  if ("status" in o && "raw" in o) {
    const b = (op, x) => (op != null || x != null) && (OPS[op] ?? op ?? "") + (x ?? ""), lim = [b(o.lower_op, o.lower), b(o.upper_op, o.upper)].filter(Boolean);
    const d = [o.value != null && `숫자 ${o.approx ? "약 " : ""}${o.value}`, lim.length && `범위 ${o.approx ? "약 " : ""}${lim.join(" ~ ")}`,
      o.unit && `단위 ${o.unit}`, o.status && `상태 ${o.status}`, o.note && `괄호 설명 "${o.note}"`].filter(Boolean).join(", ");
    return `${h(o.raw ?? "")} <small>→ ${h(d)}</small>`;
  }
  if ("temp" in o && "method" in o) return h(condText(o) || "조건 없음");
  if ("seq" in o && "text" in o && "value" in o) {
    const ex = [o.text && o.text !== o.value && `원문 줄: ${o.text}`, o.refs && `성분 ${o.refs}`,
      o.cond && `조건 ${o.cond.raw ?? condText(o.cond)}`, o.std_code && `표준문구 ${o.std_code}`].filter(Boolean).join(", ");
    return `${o.key ? h(o.key) + ": " : ""}${h(o.value)}${ex ? ` <small>${h(ex)}</small>` : ""}`;
  }
  return h(s);
}
const mainTag = r => tags.find(t => t === "Claude" && r[t + " 값"] !== "") || tags.find(t => r[t + " 값"] !== "");
const srcOf = r => { const t = mainTag(r); return t ? r[t + " 원문 조각"] : ""; };
function srcBox(s, pg) { return s ? `<div class="src" title="눌러서 펼치기">${h(s)}${pg ? ` <span class="lbl">(${h(pg)}쪽)</span>` : ""}</div>` : ""; }
function line(r, i, shared) {
  const res = r["검수 결과"], {fn} = parts(r["칸 이름"]);
  let html = `<div class="ln ${isDone(r) ? "done" : ""}" data-i="${i}" data-p="${h(r["경로"])}">
    <div class="lt"><span class="fn">${h(fn || r["칸 이름"])}</span>`;
  for (const t of tags) if (r[t + " 값"] !== "") {
    const v = plain(r[t + " 값"]);
    html += `<span class="v">${tags.length > 1 ? `<small>${t} </small>` : ""}${meaning(r, v, t) ? h(meaning(r, v, t)) : fmt(v)}${GHS[v] ? ` <small>${GHS[v]}</small>` : ""}</span>`;
  }
  html += `${r["검증기"] ? `<span class="tag bad">${h(r["검증기"])}</span>` : ""}</div>`;
  for (const t of tags) if (r[t + " 원문 조각"] && r[t + " 원문 조각"] !== shared) html += srcBox(r[t + " 원문 조각"], r[t + " 쪽"]);
  if (r["설명"] || r["적용 규칙"]) html += `<details><summary>모델 설명</summary>${h(r["적용 규칙"])} ${h(r["설명"])}</details>`;
  if (res) html += `<div><span class="res">✔ ${h(res)}</span>${res === "수정" || res === "누락 추가" ? ` → <b>${fmt(plain(r["수정값"]))}</b> <span class="lbl">${h(r["수정 원문 조각"])} ${r["수정 쪽"] ? "(" + h(r["수정 쪽"]) + "쪽)" : ""}</span>` : ""}
    <span class="lbl">${h(r["검수자"])}</span></div>`;
  if (r["교차 확인자"]) html += `<div class="lbl">교차 확인: ${h(r["교차 확인자"])}</div>`;
  if (r["메모"]) html += `<div class="memo">메모: ${h(r["메모"])}</div>`;
  html += `<div class="acts sm">`;
  if (mode === "교차") return html + `<button data-a="opinion">의견 남기기</button></div>` + (open && open.i === i ? editor(r, "opinion") : "") + `</div>`;
  for (const t of tags) if (r[t + " 값"] !== "") html += `<button data-a="adopt" data-t="${t}" class="${res === t + " 채택" ? "on" : ""}">맞음${tags.length > 1 ? ` (${t})` : ""}</button>`;
  html += `<button data-a="edit" class="${res === "수정" ? "on" : ""}">수정</button><button data-a="del" class="${res === "삭제" ? "on" : ""}">삭제</button>
    <button data-a="memo">메모</button>${res ? `<button data-a="undo">${r["일치"] === "" ? "이 줄 지우기" : "되돌리기"}</button>` : ""}</div>`;
  if (open && open.i === i) html += editor(r, open.kind);
  return html + `</div>`;
}
function card(key, items) {
  const rs = items.map(([r]) => r), pr = Math.min(...rs.map(r => Number(r["우선순위"]) || 3));
  const {sec, key: k} = parts(rs[0]["칸 이름"]);
  const srcs = new Set(rs.map(srcOf)), shared = srcs.size === 1 && rs.length > 1 ? [...srcs][0] : null;
  const todo = rs.filter(r => !r["검수 결과"] && mainTag(r)).length;
  let html = `<div class="card p${pr} ${rs.every(isDone) ? "done" : ""}" data-g="${h(key)}">
    <h3><span class="tag">${pr}순위</span>${h(sec)}${k ? ` <b>${h(k)}</b>` : ""}</h3>`;
  if (shared) html += srcBox(shared, rs[0][mainTag(rs[0]) + " 쪽"]);
  html += items.map(([r, i]) => line(r, i, shared)).join("");
  if (mode === "교차") return html + `</div>`;
  return html + `<div class="acts">${todo > 1 ? `<button data-a="adopt_all">전부 맞음 (${todo}칸)</button>` : ""}
    <button data-a="add" title="이 묶음과 같은 종류인데 모델이 빠뜨린 항목">빠진 항목 추가</button>
    <span class="path" title="${h(key)}">${h(key.length > 60 ? key.slice(0, 60) + "…" : key)}</span></div>
    ${open && open.g === key ? editor(rs[0], "add") : ""}</div>`;
}
function editor(r, kind) {
  const t = tags.includes("Claude") ? "Claude" : tags[0];
  const pv = v => { const p = plain(v); return /^-?[\d.,]+$|^(true|false|null)$/.test(p) ? v : p; };   // 숫자로 읽힐 글자만 따옴표를 남긴다
  if (kind === "edit") return `<div class="ed"><label>수정값 (원문 그대로. 숫자는 숫자만, 글자로 남길 숫자는 "01"처럼 따옴표)</label>
    <textarea id="e_val" rows="2">${h(pv(r["수정값"] || r[t + " 값"]))}</textarea>
    <label>수정 원문 조각 (필수. 값이 적힌 원문 줄 그대로. 값을 고쳤으면 이 줄도 그 값이 적힌 줄로 맞추기)</label><textarea id="e_src" rows="2">${h(r["수정 원문 조각"] || r[t + " 원문 조각"])}</textarea>
    <label>수정 쪽 (필수)</label><input id="e_pg" value="${h(r["수정 쪽"] || page || "")}">
    <label>메모 (선택)</label><input id="e_memo" value="${h(r["메모"])}">
    <div class="acts"><button class="on" data-a="save_edit">저장 (${MOD}+Enter)</button><button data-a="close">닫기</button></div></div>`;
  if (kind === "del") return `<div class="ed"><label>삭제 이유 (필수. 예: 원문에 없는 값)</label><input id="e_memo" value="${h(r["메모"])}">
    <div class="acts"><button class="on" data-a="save_del">삭제로 저장</button><button data-a="close">닫기</button></div></div>`;
  if (kind === "opinion") return `<div class="ed"><label>의견 (무엇이 왜 틀렸는지, 맞는 값)</label><textarea id="e_val" rows="3"></textarea>
    <div class="acts"><button class="on" data-a="copy_op">의견 복사 (디스코드에 붙여 넣기)</button><button data-a="close">닫기</button></div></div>`;
  if (kind === "memo") return `<div class="ed"><label>메모</label><input id="e_memo" value="${h(r["메모"])}">
    <div class="acts"><button class="on" data-a="save_memo">메모 저장</button><button data-a="close">닫기</button></div></div>`;
  if (kind === "add") return `<div class="ed"><p class="help">모델이 함께 빠뜨린 항목을 새 줄로 넣습니다. 아래 경로는 이 칸의 경로를 본뜬 것이니, [k=…] 안의 키(예: CAS 번호)와 끝 이름을 원문에 맞게 고쳐 주세요.</p>
    <label>경로</label><input id="e_path" value="${h(r["경로"])}">
    <label>값</label><textarea id="e_val" rows="2"></textarea>
    <label>원문 조각</label><textarea id="e_src" rows="2"></textarea>
    <label>쪽</label><input id="e_pg" value="${h(page || "")}">
    <label>메모 (선택)</label><input id="e_memo">
    <div class="acts"><button class="on" data-a="save_add">누락 추가로 저장</button><button data-a="close">닫기</button></div></div>`;
  return "";
}
function renderCards() {
  const list = S.rows.map((r, i) => [r, i]).filter(([r]) => visible(r) && pagesOf(r).includes(page));
  groups = new Map();
  RANK = new Map();     // 목록 항목 경로(…[k=…])마다 그 안 칸 가운데 가장 앞선 실버 순서
  for (const [p, n] of Object.entries(S.rank || {}))
    for (const m of p.matchAll(/\]/g)) { const k = p.slice(0, m.index + 1); if (!(RANK.get(k) <= n)) RANK.set(k, n); }
  for (const it of list) { const k = gkey(it[0]["경로"]); groups.has(k) ? groups.get(k).push(it) : groups.set(k, [it]); }
  for (const items of groups.values()) items.sort(([a], [b]) => byDoc(a["경로"], b["경로"]));
  const hint = mode === "교차" ? "보기 전용입니다. 1순위 줄을 원문과 대조하고, 의견이 있으면 '의견 남기기'로 복사해 디스코드의 문서별 스레드에 붙여 넣으세요. 검수표는 검수 담당이 고칩니다 (역할 A 가이드 4.6)." :
    "칸을 누르면 왼쪽 사진에 위치가 표시됩니다(노란 상자 = 원문 조각, 주황 테두리 = 값). 맞으면 '맞음', 틀리면 '수정', 원문에 없는 값이면 '삭제'. 누르면 바로 검수표에 저장됩니다. 칸 순서는 문서에 적힌 순서입니다. '1번째', '7번 성분 (CAS)' 같은 칸은 원문 글자가 아니라 줄끼리 잇는 번호라, 카드 제목과 맞으면 '맞음'입니다.";
  $("#right").innerHTML = `<p class="help">${hint}</p>` + (list.length ? [...groups].map(([k, it]) => [k, it, cardKey(k, it)]).sort(cardCmp).map(([k, items]) => card(k, items)).join("")
    : `<p class="none">${page ? page + "쪽에" : "여기에"} ${show === "todo" ? "남은 칸이 없습니다 ✔" : "칸이 없습니다"}</p>`);
  for (const p of sel) document.querySelector(`.ln[data-p="${CSS.escape(p)}"]`)?.classList.add("sel");
  if (open) { const el = $("#e_val") || $("#e_memo"); if (el) el.focus(); }
}
let groups = new Map();
// 카드 안 칸은 문서에서 읽는 순서(스키마 순서)로. 검수표 줄 순서는 '문제 있는 줄 먼저'라 카드 안에서는 뒤섞여 보인다
function byDoc(a, b) {
  const x = S.order?.[a] || [999], y = S.order?.[b] || [999];
  for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (x[i] ?? -1) - (y[i] ?? -1); if (d) return d; }
  return a.localeCompare(b, "ko", {numeric: true});
}
// 카드끼리도 문서 순서로: 경로의 칸마다 [스키마 순서 번호, 그 목록 항목의 실버 순서]를 이어 붙인 목록을 앞에서부터 비교한다.
// 실버 순서는 화면에 보이는 줄이 아니라 전체 실버에서 오므로, 줄을 '맞음'으로 저장해 숨어도 자리가 그대로
let RANK = new Map();
function cardKey(k, it) {
  const o = S.order?.[it[0][0]["경로"]] || [999], pre = k.match(/^msds\[\d+\]\.?/)?.[0] || "", body = k.slice(pre.length), out = [Number(pre.match(/\d+/)?.[0] ?? 0)];   // 다중 MSDS는 건 번호부터
  [...body.matchAll(/([^.[\]]+)(\[[^\]]*\])?/g)].forEach((m, i) => {
    out.push(o[i] ?? 999);
    if (m[2]) out.push(RANK.get(pre + body.slice(0, m.index + m[0].length)) ?? m[2]);   // 목록 항목: 실버에 적힌 순서(문서 순서). 없으면(누락 추가) [k=…] 글자로 끝에
  });
  return out;
}
// 없음 < 숫자 < 글자 순. 숫자끼리는 크기, 글자끼리는 숫자를 숫자로 읽어 비교
const cmp1 = (a, b) => a === b ? 0 : a === undefined ? -1 : b === undefined ? 1 : typeof a !== typeof b ? (typeof a === "number" ? -1 : 1)
  : typeof a === "number" ? a - b : a.localeCompare(b, "ko", {numeric: true});
function cardCmp([ka, , x], [kb, , y]) {
  for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = cmp1(x[i], y[i]); if (d) return d; }
  return ka.localeCompare(kb, "ko", {numeric: true});
}
function needName() {
  const me = $("#me").value.trim();
  if (!me) { toast("먼저 위쪽 '내 이름'을 적어 주세요", true); $("#me").focus(); }
  return me;
}
async function save(r, values, msg) {
  try {
    const j = await api("/api/save", {"경로": r["경로"], values});
    const idx = S.rows.findIndex(x => x["경로"] === r["경로"]);
    if (idx >= 0) S.rows[idx] = j.row;
    open = null; $("#saved").textContent = "저장됨 " + new Date().toLocaleTimeString("ko-KR");
    if (msg) toast(msg);
    render();
  } catch (e) { toast(e.message, true); }
}
async function saveMany(items, msg) {
  if (!items.length) return;
  try {
    const j = await api("/api/save_many", {items});
    for (const row of j.rows) { const idx = S.rows.findIndex(x => x["경로"] === row["경로"]); if (idx >= 0) S.rows[idx] = row; }
    open = null; $("#saved").textContent = "저장됨 " + new Date().toLocaleTimeString("ko-KR");
    toast(msg); render();
  } catch (e) { toast(e.message, true); }
}
const who = me => ({"검수자": me});
$("#right").addEventListener("click", async e => {
  const src = e.target.closest(".src"); if (src) return src.classList.toggle("full");
  const b = e.target.closest("button[data-a]"), ln = e.target.closest(".ln"), cd = e.target.closest(".card");
  if (!e.target.closest(".ed, button, summary")) {      // 칸이나 묶음 제목을 누르면 사진에 위치 표시
    if (ln) return highlight([ln.dataset.p]);
    if (cd) return highlight((groups.get(cd.dataset.g) || []).map(([r]) => r["경로"]));
  }
  if (!b) return;
  const g = cd.dataset.g, a = b.dataset.a;
  if (!ln) {                                            // 묶음 단추
    const items = groups.get(g) || [];
    if (a === "add") { open = open && open.g === g ? null : {g, kind: "add"}; return renderCards(); }
    if (a === "adopt_all") {
      const me = needName(); if (!me) return;
      const todo = items.map(([r]) => r).filter(r => !r["검수 결과"] && mainTag(r));
      return saveMany(todo.map(r => ({"경로": r["경로"], values: {"검수 결과": mainTag(r) + " 채택", ...who(me)}})), `${todo.length}칸을 맞음으로 저장했습니다`);
    }
  }
  const i = ln ? Number(ln.dataset.i) : -1, r = ln ? S.rows[i] : null;      // 묶음 편집기(빠진 항목 추가)는 줄 밖에 있다
  if (ln && (ln.dataset.p !== sel[0] || sel.length !== 1)) highlight([ln.dataset.p]);
  if (["edit", "del", "memo", "add", "opinion"].includes(a)) { open = open && open.i === i && open.kind === a ? null : {i, kind: a}; return renderCards(); }
  if (a === "close") { open = null; return renderCards(); }
  if (a === "copy_op") {
    const v = $("#e_val").value.trim(); if (!v) return toast("의견을 적어 주세요", true);
    const text = `[${S.doc}] ${r["경로"]}\n칸: ${r["칸 이름"]}\n의견: ${v}`;
    try { await navigator.clipboard.writeText(text); open = null; renderCards(); toast("복사했습니다. 디스코드 문서별 스레드에 붙여 넣으세요"); }
    catch { toast("복사하지 못했습니다. 의견 칸 글을 직접 복사해 주세요", true); }
    return;
  }
  const me = needName(); if (!me) return;
  if (a === "adopt") return save(r, {"검수 결과": b.dataset.t + " 채택", ...who(me)});
  if (a === "undo" && r["일치"] === "") {        // 누락 추가 줄은 비우지 않고 줄째 지운다
    if (!confirm("이 누락 추가 줄을 지울까요?")) return;
    try { await api("/api/remove", {"경로": r["경로"]}); S.rows = S.rows.filter(x => x["경로"] !== r["경로"]); open = null; toast("누락 추가 줄을 지웠습니다"); render(); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (a === "undo") return save(r, {"검수 결과": "", "수정값": "", "수정 원문 조각": "", "수정 쪽": ""}, "미검수로 되돌렸습니다");
  if (a === "save_edit") {
    const v = $("#e_val").value.trim();
    if (!v) return toast("수정값을 적어 주세요. 원문에 없는 값이면 '삭제'를 고릅니다", true);
    if (!$("#e_src").value.trim() || !$("#e_pg").value.trim()) return toast("수정 원문 조각과 수정 쪽도 적어 주세요", true);
    return save(r, {"검수 결과": "수정", "수정값": v, "수정 원문 조각": $("#e_src").value, "수정 쪽": $("#e_pg").value, "메모": $("#e_memo").value, ...who(me)});
  }
  if (a === "save_del") {
    const m = $("#e_memo").value.trim();
    if (!m) return toast("삭제 이유를 메모에 적어 주세요", true);
    return save(r, {"검수 결과": "삭제", "메모": m, ...who(me)});
  }
  if (a === "save_memo") return save(r, {"메모": $("#e_memo").value}, "메모를 저장했습니다");
  if (a === "save_add") {
    try {
      const j = await api("/api/add", {values: {"경로": $("#e_path").value, "수정값": $("#e_val").value, "수정 원문 조각": $("#e_src").value,
        "수정 쪽": $("#e_pg").value, "메모": $("#e_memo").value, "검수자": me}});
      S.rows.push(j.row); open = null; toast("누락 추가 줄을 넣었습니다"); render();
    } catch (err) { toast(err.message, true); }
  }
});
$("#right").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { const b = $(".ed button.on"); if (b) b.click(); } });
function go(p) { page = p; open = null; sel = []; selSeq++; render(); $("#view").scrollTop = 0; $("#right").scrollTop = 0; }
$("#pager").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  const list = [...document.querySelectorAll("#pager [data-pg]")].map(x => Number(x.dataset.pg)), k = list.indexOf(page);
  if (b.dataset.pg !== undefined) return go(Number(b.dataset.pg));
  if (b.id === "prev" && k > 0) return go(list[k - 1]);
  if (b.id === "next" && k < list.length - 1) return go(list[k + 1]);
  if (b.id === "zi") zoom = Math.min(300, zoom + 20); if (b.id === "zo") zoom = Math.max(40, zoom - 20); if (b.id === "zf") zoom = 100;
  renderView();
});
document.addEventListener("keydown", e => {
  if (e.target.closest("input, textarea")) return;
  if (e.key === "ArrowLeft") $("#prev").click();
  if (e.key === "ArrowRight") $("#next").click();
});
$("#crossbtn").onclick = async () => {
  const name = prompt("교차 확인 담당 이름 (디스코드 의견을 모두 반영한 뒤 누르세요). 1순위 줄의 '교차 확인자' 칸에 적습니다.");
  if (!name || !name.trim()) return;
  try { const j = await api("/api/cross", {name: name.trim()}); S.rows = j.rows; render(); toast(`1순위 ${j.count}줄에 교차 확인자 '${name.trim()}'을 적었습니다`); }
  catch (e) { toast(e.message, true); }
};
document.querySelectorAll("[data-p]").forEach(b => b.onclick = () => {
  const p = Number(b.dataset.p); prio.has(p) ? prio.delete(p) : prio.add(p); b.classList.toggle("on", prio.has(p)); render(); });
document.querySelectorAll("[data-s]").forEach(b => b.onclick = () => {
  show = b.dataset.s; document.querySelectorAll("[data-s]").forEach(x => x.classList.toggle("on", x === b)); render(); });
$("#q").oninput = e => { q = e.target.value.trim().toLowerCase(); render(); };
$("#endbtn").onclick = async () => {
  if (!needName()) return;
  try { await api("/api/info", {key: "검수 끝", value: new Date().toLocaleString("sv-SE").slice(0, 16)}); toast("검수 끝 시각을 문서 정보에 적었습니다"); }
  catch (e) { toast(e.message, true); }
};
// 맥 트랙패드 핀치(크롬은 Ctrl+휠로 보냄)와 Ctrl/⌘+휠은 쪽 사진만 확대한다
$("#view").addEventListener("wheel", e => {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault(); zoom = Math.min(300, Math.max(40, zoom - e.deltaY * 0.4)); renderView();
}, {passive: false});
if (!CHROMIUM) toast("이 화면은 크롬 기준으로 만들었습니다. 크롬에서 열어 주세요", true);
load().catch(e => toast("불러오지 못했습니다: " + e.message, true));
</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="검수 화면: 쪽 사진을 보며 검수표에 바로 적는다")
    ap.add_argument("--doc", required=True, help="문서 번호 (예: T21-M013)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--cross", action="store_true", help="교차 확인용: 보기만 하고 의견을 복사해 디스코드에 남김 (검수표는 안 고침)")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    a = ap.parse_args()
    _use_repo_data()
    sheet = Sheet(a.doc)
    if not page_count(a.doc):
        raise SystemExit(f"{paths.page_dir(a.doc)}에 쪽 사진이 없습니다. C의 OCR 결과(data/pages/version2/{a.doc}/)를 이 폴더에 복사하세요")
    handler = make_handler(sheet, a.cross, Locator(a.doc))
    try:
        server = HTTPServer(("127.0.0.1", a.port), handler)
    except OSError:                       # 포트가 이미 쓰이면 빈 포트로
        server = HTTPServer(("127.0.0.1", 0), handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"검수 화면: {url}  (검수표 {sheet.path})")
    print("이 창을 닫거나 Ctrl+C를 누르면 끝납니다. 쓰는 동안 같은 검수표를 엑셀에서 열지 마세요.")
    if not a.no_browser:
        open_chrome(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
