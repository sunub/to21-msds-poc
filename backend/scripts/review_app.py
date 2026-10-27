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
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

import _common  # noqa: F401
from msds.common import paths
from msds.common.align import generic
from msds.common.jsonpath import from_cell, to_cell
from msds.common.priority import priority_of
from msds.review.build_gold import _KEY_PATH, _ROW_PATH, _excel_value, _schema_at
from msds.review.make_sheet import label_of
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
        r = self._find(path)
        if r is None:
            raise ValueError(f"검수표에 없는 경로: {path}")
        self._put(r, _texted(path, self._check(values)))
        if values.get("검수 결과"):
            self._stamp_start()
        self._save()
        return {c: _cell(self.wb[SHEET_MAIN].cell(r, self.col[c]).value) for c in COLUMNS}

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


def page_count(doc_id: str) -> int:
    return len(list(paths.page_dir(doc_id).glob("p*.png")))


def make_handler(sheet: Sheet, readonly: bool):
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
                return self._json(200, {"doc": sheet.doc_id, "file": str(sheet.path), "info": sheet.info(),
                                        "rows": sheet.rows(), "pages": page_count(sheet.doc_id), "reloaded": reloaded,
                                        "excel_open": sheet.excel_open(), "readonly": readonly})
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
#view img { display: block; margin: 0 auto; box-shadow: 0 1px 4px rgba(0,0,0,.25); background: #fff; }
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
.src { font-size: .85rem; color: var(--muted); border-left: 3px solid var(--line); padding-left: 8px; margin: 4px 0; white-space: pre-wrap; }
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
const SRC_TIP = {"불일치":"기계가 PDF 글자층에서 이 조각을 못 찾음. 지어냈다는 뜻은 아님. 사진에서 직접 확인",
  "일치":"조각의 글자가 그 쪽에 있음. 값이 맞다는 뜻은 아님. 1순위는 값을 직접 확인",
  "대조불가":"글자층이 깨진 쪽이거나 조각이 없음. 사진에서 확인"};
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
  const v = $("#view"), img = v.querySelector("img");
  if (page && img && Number(img.dataset.pg) === page) { img.style.width = zoom + "%"; return; }   // 확대만 바뀌면 사진을 다시 그리지 않는다
  v.innerHTML = page ? `<img data-pg="${page}" src="/page/${page}.png" alt="${page}쪽" decoding="async" style="width:${zoom}%">`
    : `<p class="none">쪽 번호가 없는 칸입니다. 원본 PDF에서 직접 찾아 확인해 주세요.</p>`;
}
function srcTag(r) {
  const s = r["원문 대조"];
  if (!s) return "";
  return `<span class="tag ${s === "일치" ? "ok" : s === "불일치" ? "warn" : ""}" title="${h(SRC_TIP[s] || "")}">원문 대조 ${h(s)}</span>`;
}
function card(r, i) {
  const pr = String(r["우선순위"]), done = isDone(r), res = r["검수 결과"];
  let html = `<div class="card p${h(pr)} ${done ? "done" : ""}" data-i="${i}">
    <h3><span class="tag">${h(pr)}순위</span>${h(r["칸 이름"])} ${srcTag(r)}
      ${r["검증기"] ? `<span class="tag bad">${h(r["검증기"])}</span>` : ""}</h3>
    <div class="path">${h(r["경로"])}</div>`;
  for (const t of tags) if (r[t + " 값"] !== "")
    html += `<div class="val"><small>${t}</small>${h(r[t + " 값"])}</div>${r[t + " 원문 조각"] ? `<div class="src">${h(r[t + " 원문 조각"])} <span class="lbl">(${h(r[t + " 쪽"])}쪽)</span></div>` : ""}`;
  if (r["설명"] || r["적용 규칙"]) html += `<details><summary>모델 설명</summary>${h(r["적용 규칙"])} ${h(r["설명"])}</details>`;
  if (res) html += `<div><span class="res">✔ ${h(res)}</span>${res === "수정" || res === "누락 추가" ? ` → <b>${h(r["수정값"])}</b> <span class="lbl">${h(r["수정 원문 조각"])} ${r["수정 쪽"] ? "(" + h(r["수정 쪽"]) + "쪽)" : ""}</span>` : ""}
    <span class="lbl">${h(r["검수자"])}</span></div>`;
  if (r["교차 확인자"]) html += `<div class="lbl">교차 확인: ${h(r["교차 확인자"])}</div>`;
  if (r["메모"]) html += `<div class="memo">메모: ${h(r["메모"])}</div>`;
  html += `<div class="acts">`;
  if (mode === "교차") return html + `<button data-a="opinion">의견 남기기</button></div>` + (open && open.i === i ? editor(r, "opinion") : "") + `</div>`;
  for (const t of tags) if (r[t + " 값"] !== "") html += `<button data-a="adopt" data-t="${t}" class="${res === t + " 채택" ? "on" : ""}">맞음 (${t} 채택)</button>`;
  html += `<button data-a="edit" class="${res === "수정" ? "on" : ""}">수정</button><button data-a="del" class="${res === "삭제" ? "on" : ""}">삭제</button>
    <button data-a="memo">메모</button><button data-a="add" title="이 칸과 같은 종류인데 모델이 빠뜨린 항목">빠진 항목 추가</button>
    ${res ? `<button data-a="undo">${r["일치"] === "" ? "이 줄 지우기" : "되돌리기"}</button>` : ""}</div>`;
  if (open && open.i === i) html += editor(r, open.kind);
  return html + `</div>`;
}
function editor(r, kind) {
  const t = tags.includes("Claude") ? "Claude" : tags[0];
  if (kind === "edit") return `<div class="ed"><label>수정값 (원문 그대로. 숫자는 숫자만, 글자로 남길 숫자는 "01"처럼 따옴표)</label>
    <textarea id="e_val" rows="2">${h(r["수정값"] || r[t + " 값"])}</textarea>
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
  const hint = mode === "교차" ? "보기 전용입니다. 1순위 줄을 원문과 대조하고, 의견이 있으면 '의견 남기기'로 복사해 디스코드의 문서별 스레드에 붙여 넣으세요. 검수표는 검수 담당이 고칩니다 (역할 A 가이드 4.6)." :
    "사진과 비교해 맞으면 '맞음', 틀리면 '수정', 원문에 없는 값이면 '삭제'를 누릅니다. 누르면 바로 검수표에 저장됩니다.";
  $("#right").innerHTML = `<p class="help">${hint}</p>` + (list.length ? list.map(([r, i]) => card(r, i)).join("")
    : `<p class="none">${page ? page + "쪽에" : "여기에"} ${show === "todo" ? "남은 칸이 없습니다 ✔" : "칸이 없습니다"}</p>`);
  if (open) { const el = $("#e_val") || $("#e_memo"); if (el) el.focus(); }
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
const who = me => ({"검수자": me});
$("#right").addEventListener("click", async e => {
  const b = e.target.closest("button[data-a]"); if (!b) return;
  const i = Number(b.closest(".card").dataset.i), r = S.rows[i], a = b.dataset.a;
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
function go(p) { page = p; open = null; render(); $("#view").scrollTop = 0; $("#right").scrollTop = 0; }
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
        raise SystemExit(f"{paths.page_dir(a.doc)}에 쪽 사진이 없습니다. C가 나눠 준 쪽 이미지(C_v0.2)를 data/pages/에 두세요")
    try:
        server = HTTPServer(("127.0.0.1", a.port), make_handler(sheet, a.cross))
    except OSError:                       # 포트가 이미 쓰이면 빈 포트로
        server = HTTPServer(("127.0.0.1", 0), make_handler(sheet, a.cross))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"검수 화면: {url}  (검수표 {sheet.path})")
    print("이 창을 닫거나 Ctrl+C를 누르면 끝납니다. 쓰는 동안 같은 검수표를 엑셀에서 열지 마세요.")
    if not a.no_browser:
        open_chrome(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
