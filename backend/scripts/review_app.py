"""검수 화면 (역할 A, D-36). 사용법: python scripts/review_app.py --doc T21-M013

왼쪽에 쪽 사진, 오른쪽에 그 쪽에서 나온 칸을 띄우고, 고른 결과를 검수표(data/review/<문서>.xlsx)의
검수 칸에 바로 적는다. 원본 기록은 검수표이고 이 화면은 엑셀 대신 쓰는 입력 도구라 열 형식은 그대로다.
내 컴퓨터(127.0.0.1)에서만 열린다. 쪽 사진은 TO21 자료라 밖으로 보내지 않는다 (D-47).
"""
import argparse
from collections import Counter
import json
import os
import platform
import re
import subprocess
import unicodedata
import webbrowser
from datetime import date, datetime, time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import openpyxl
import pymupdf
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

import _common  # noqa: F401
from review_cards import QUESTIONS, _batchim, _cell_now, build_cards, card_key, comps_from_rows, dropped, gone_by, human, overlaps, overlaps_src
from msds.common import paths
from msds.common.align import LIST_KEYS, _key_str, generic
from msds.common.conventions import ECO_DESCRIPTORS, LIMIT_TYPE, NO_VALUE
from msds.common.jsonpath import from_cell, to_cell
from msds.common.priority import ACUTE, DOMESTIC_LAWS, MUST_PHYSCHEM, priority_of
from msds.common.schema import load_schema, msds_item_schema, validate
from msds.extract.expand import fill_q
from msds.extract.rows import parse_qm
from msds.preprocess.ocr import ocr_json
from msds.review.build_gold import _KEY_PATH, _ROW_PATH, _branch, _excel_value, _resolve, _schema_at, default_model
from msds.review.make_sheet import REVIEW_SECTIONS, SECTION_TITLES, _spec_rows, flat_doc, in_scope, label_of, scope_key, section_of
from msds.review.sheet_spec import COLUMNS, RESULT_OPTIONS, SHEET_INFO, SHEET_MAIN

HUMAN = COLUMNS[COLUMNS.index("검수 결과"):]          # 사람이 쓰는 열만 고친다
INFO_EDIT = ("검수 시작", "검수 끝", "검수자", "교차 확인자")
NEED_SOURCE = ("수정", "누락 추가")                       # 수정값, 수정 원문 조각, 수정 쪽을 함께 적는다 (계획서 13.2)
WHEN = {"datetime": datetime, "date": date, "time": time}   # 엑셀이 날짜로 바꾼 셀: 되돌리기용 원래 값은 {"datetime": "…"}로 보낸다


def _unraw(v):
    """되돌리기로 받은 원래 셀 값: {"datetime": "…"} 꼴은 날짜로, 나머지는 그대로."""
    if isinstance(v, dict) and len(v) == 1 and (k := next(iter(v))) in WHEN:
        try:
            return WHEN[k].fromisoformat(str(v[k]))
        except ValueError:
            raise ValueError(f"되돌릴 날짜 값을 읽지 못했어요: {v[k]}") from None
    return v


def _set(c, v):
    """셀에 쓴다. '='로 시작하는 글은 수식이 되지 않게 글자로 둔다 (열 때 실행되지 않게)."""
    c.value = v
    if isinstance(v, str) and v.startswith("="):
        c.data_type = "s"


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
        ws = self.wb[SHEET_MAIN]
        return [row for r in range(2, ws.max_row + 1) if any((row := self._row_at(r)).values())]

    def _row_at(self, r: int) -> dict:
        """엑셀 한 줄 → 화면 줄(글). 검수 결과는 앞뒤 공백을 뗀다(골드와 같게).
        사람 열의 원래 셀 값이 그 글과 다르면(숫자 7, 공백 붙은 결과) '_raw'에 두어 되돌리기가 그대로 다시 쓰게 한다."""
        ws, row, raw = self.wb[SHEET_MAIN], {}, {}
        for c in COLUMNS:
            v = ws.cell(r, self.col[c]).value
            row[c] = _cell(v).strip() if c == "검수 결과" else _cell(v)
            if c in HUMAN and v != row[c] and isinstance(v, (str, int, float, *WHEN.values())):   # JSON으로 보낼 수 있는 값만
                raw[c] = {type(v).__name__: v.isoformat()} if isinstance(v, (*WHEN.values(),)) else v
        return {**row, "_raw": raw} if raw else row

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
            raise ValueError("고치기와 빠진 값 넣기는 값, 근거 줄, 쪽을 모두 적어야 합니다")
        pg = _clean(values.get("수정 쪽"))
        if pg and not re.fullmatch(r"\d+(\s*,\s*\d+)*", pg):
            raise ValueError(f"쪽은 숫자로 적어 주세요 (예: 7, 여러 쪽이면 7,8). 지금: {pg}")
        return values

    def _put(self, r: int, values: dict):
        ws = self.wb[SHEET_MAIN]
        for k, v in values.items():
            v = _clean(v)
            _set(ws.cell(r, self.col[k]), int(v) if k == "수정 쪽" and v and v.isdecimal() else v)

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
            todo.append((r, self._comp_ok(path, self._unchanged(r, _typed(path, self._check(it["values"]))))))   # 바뀐 것 없는 '수정'은 맞음과 같게 (맞음 길은 카드 ⚠로 알린다)
        for r, values in todo:
            self._put(r, values)
        if any(v.get("검수 결과") for _, v in todo):
            self._stamp_start()
        self._save()
        return [self._row_at(r) for r, _ in todo]

    def restore(self, items: list) -> list[dict]:
        """카드 되돌리기: 줄마다 판단 전 사람 열을 그대로 다시 쓴다(원래 셀 값: 숫자는 숫자, '6쪽'·앞뒤 공백도 그대로. 수식만 글자로).
        검사하는 것: 같은 줄이 두 번인지, 검수 결과가 드롭다운 목록(또는 빈칸)인지, 다시 넣는 줄(사람이 넣은 누락 추가 줄만)의 경로 형식·스키마·검수 범위(add_rows와 같게).
        값 자체(수정값 모양·쪽 번호·성분 번호)는 판단 전에 검수표에 있던 그대로라 다시 검사하지 않는다. 사람 열 밖은 고치지 않는다. 하나라도 틀리면 아무것도 고치지 않는다."""
        if not isinstance(items, list) or not items or not all(isinstance(x, dict) for x in items):
            raise ValueError("items는 [{열: 값}] 목록이어야 함")
        todo, seen = [], set()
        for row in items:
            path = str(row.get("경로") or "").strip()
            if path in seen:
                raise ValueError(f"같은 줄이 두 번 있어요: {path}")
            seen.add(path)
            raw = row.get("_raw") if isinstance(row.get("_raw"), dict) else {}
            values = {k: _unraw(raw[k]) if k in raw else row.get(k) for k in HUMAN}
            res = str(values["검수 결과"] or "").strip()
            if res and res not in RESULT_OPTIONS:   # 검수표 드롭다운 목록: 엑셀로 적힌 'GPT 채택'(이 표에 GPT 값이 없어도)을 판단 전 값으로 되돌릴 수 있어야 한다
                raise ValueError(f"검수 결과는 {'·'.join(RESULT_OPTIONS)} 중 하나여야 해요 (지금: {res})")
            r = self._find(path)
            if r is None and (str(row.get("일치") or "").strip() or res != "누락 추가"):
                raise ValueError(f"검수표에 없는 경로: {path}")       # 다시 넣는 것은 사람이 넣은 누락 추가 줄만
            todo.append((r, path, None if r else self._new_path(path), values))
        ws, out = self.wb[SHEET_MAIN], []
        for r, path, rel, values in todo:
            if r is None:
                r = self._append(path, rel)
            for k, v in values.items():
                _set(ws.cell(r, self.col[k]), v if isinstance(v, (int, float, *WHEN.values())) or v is None else ILLEGAL_CHARACTERS_RE.sub("", str(v)) or None)
            out.append(r)
        ws.auto_filter.ref = ws.dimensions
        self._save()
        return [self._row_at(r) for r in out]

    @staticmethod
    def _new_path(path: str) -> str:
        """새로 넣을 줄의 경로 검사(누락 추가·되돌리기 같게) → 키 경로."""
        m = _ROW_PATH.fullmatch(path)
        if not m or not _KEY_PATH.fullmatch(m.group(2)):
            raise ValueError("경로 형식이 맞지 않음 (msds[0].이름[k=키].이름 …). 비슷한 줄의 경로를 본떠 고쳐 주세요")
        if _schema_at(generic(m.group(2))) is None:
            raise ValueError(f"TO21 스키마에 없는 칸입니다: {generic(m.group(2))}. 끝 이름을 비슷한 줄과 맞춰 주세요")
        if not in_scope(m.group(2)):
            raise ValueError(f"검수 범위 밖 항입니다. {'·'.join(map(str, REVIEW_SECTIONS[1:]))}항과 관리정보만 검수합니다")
        return m.group(2)

    def _append(self, path: str, rel: str) -> int:
        ws = self.wb[SHEET_MAIN]
        r = ws.max_row + 1
        ws.cell(r, self.col["경로"]).value = path
        ws.cell(r, self.col["칸 이름"]).value = label_of(rel)
        ws.cell(r, self.col["우선순위"]).value = priority_of(rel)   # 1순위면 교차 확인 대상
        return r

    def _comp_ok(self, path: str, values: dict) -> dict:
        """대상 성분(comp_ref)·상위 성분(parent_seq) 번호는 같은 MSDS 건 성분표의 순번(골드에 남는 성분)이거나 MIX(대상 성분만)여야 한다.
        표에 없는 번호('99')가 저장되지 않게."""
        v = values.get("수정값")
        if not path.endswith((".comp_ref", ".parent_seq")) or _clean(values.get("검수 결과")) not in NEED_SOURCE or v in (None, "", "null"):
            return values
        rows, pre = self.rows(), re.match(r"msds\[\d+\]\.", path).group(0)
        drop = dropped(rows, default_model(self.doc_id))
        ok = {_val(x) for x in rows if re.fullmatch(re.escape(pre) + r"components\[k=[^\]]*\]\.seq", x["경로"]) and not gone_by(x["경로"], drop)}
        ok |= {"MIX"} if path.endswith(".comp_ref") else set()
        if _plain(v) not in ok:
            raise ValueError(f"성분표에 없는 성분 번호예요 (지금: {_plain(v)}). 성분표의 순번{'이나 MIX(제품 전체)' if path.endswith('.comp_ref') else ''}를 골라 주세요")
        return values

    def _unchanged(self, r: int, values: dict) -> dict:
        """'수정'인데 값(칸 모양으로 바꾼 값)·근거 줄·쪽이 모두 모델 값과 같으면 그 모델 채택(맞음)으로 바꾼다 (바꾼 것이 없는 고치기)."""
        if _clean(values.get("검수 결과")) != "수정":
            return values
        cell = lambda c: _cell(self.wb[SHEET_MAIN].cell(r, self.col[c]).value)
        t = next((t for t in ("Claude", "GPT") if cell(f"{t} 값") != ""), None)
        nums = lambda x: re.findall(r"\d+", str(x or ""))
        same = lambda v: {**v, "approx": v.get("approx") or None} if isinstance(v, dict) and "approx" in v else v   # 수치: approx False = None
        if (t in self.tags and same(from_cell(str(values.get("수정값") or ""))) == same(from_cell(cell(f"{t} 값")))
                and (_clean(values.get("수정 원문 조각")) or "") == (_clean(cell(f"{t} 원문 조각")) or "")
                and nums(values.get("수정 쪽")) == nums(cell(f"{t} 쪽"))):
            return {**values, "검수 결과": f"{t} 채택", "수정값": None, "수정 원문 조각": None, "수정 쪽": None}
        return values

    def add_row(self, values: dict) -> dict:
        """누락 추가: 두 모델이 모두 빠뜨린 칸을 새 줄로 넣는다."""
        return self.add_rows([values])[0]

    def add_rows(self, items: list) -> list[dict]:
        """누락 추가 여러 칸(새 항목 하나의 칸들)을 한 번에 넣는다. 하나라도 틀리면 아무것도 넣지 않는다."""
        todo = []
        for values in items:
            if not isinstance(values, dict):
                raise ValueError("values는 {열: 값} 형태여야 함")
            values = dict(values)
            path = str(values.pop("경로", "") or "").strip()
            rel = self._new_path(path)
            if self._find(path) or path in [t[0] for t in todo]:
                raise ValueError("이미 있는 칸입니다. 그 줄에서 '수정'을 고르세요")
            todo.append((path, rel, self._comp_ok(path, _typed(path, self._check({**values, "검수 결과": "누락 추가"})))))
        ws, out = self.wb[SHEET_MAIN], []
        for path, rel, values in todo:
            r = self._append(path, rel)
            self._put(r, values)
            out.append(r)
        ws.auto_filter.ref = ws.dimensions         # 새 줄도 엑셀 필터에 들어가게
        self._stamp_start()
        self._save()
        return [self._row_at(r) for r in out]

    def remove_added(self, paths: str | list):
        """사람이 넣은 누락 추가 줄(여럿이면 한 번에)을 지운다. 비워 두기만 하면 골드셋에 값이 빈 항목이 생긴다.
        하나라도 지울 수 없으면 아무것도 지우지 않는다(카드의 줄이 반만 지워지지 않게)."""
        ws, rs = self.wb[SHEET_MAIN], []
        for path in [paths] if isinstance(paths, str) else paths:
            r = self._find(str(path).strip())
            if r is None or ws.cell(r, self.col["일치"]).value not in (None, "") or r in rs:
                raise ValueError("사람이 넣은 누락 추가 줄만 지울 수 있습니다")
            rs.append(r)
        if not rs:
            raise ValueError("지울 줄이 없습니다")
        for r in sorted(rs, reverse=True):       # 아래 줄부터 (위 줄을 먼저 지우면 행 번호가 밀린다)
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
                   and not _clean(ws.cell(r, self.col["검수 결과"]).value))   # 공백만 든 칸은 미검수 (화면·골드와 같게)
        if left:                          # 가이드 4.6: 1순위를 끝낸 뒤 교차 확인
            raise ValueError(f"1순위 {left}줄이 아직 미검수입니다. 1순위를 모두 끝낸 뒤 반영해 주세요")
        for r in range(2, ws.max_row + 1):
            if str(ws.cell(r, self.col["우선순위"]).value) == "1":
                _set(ws.cell(r, self.col["교차 확인자"]), name)
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
        _set(cell, _clean(value))
        self._save()

    def excel_open(self) -> bool:
        """엑셀이 이 파일을 열면 같은 폴더에 '~$파일이름' 잠금 파일이 생긴다(윈도우, 맥 모두).
        맥 엑셀은 파일을 잠그지 않아 그대로 저장하면 나중에 엑셀이 덮어쓰므로 미리 막는다."""
        n = self.path.name
        return any((self.path.parent / f"~${x}").exists() for x in (n, n[2:]))

    def _save(self):
        """저장. 못 하면 바꾼 것을 버리고(파일 상태로 다시 읽음) 까닭별 안내를 OSError로 알린다 (409)."""
        if self.excel_open():
            self.load()
            raise PermissionError(f"엑셀에서 이 검수표가 열려 있어요. 엑셀을 닫고 다시 눌러 주세요. 엑셀을 닫았는데도 계속 뜨면 같은 폴더의 '~${self.path.name}' 파일을 지워 주세요")
        try:
            self.wb.save(self.path)
        except OSError as e:
            self.load()
            if not os.access(self.path, os.W_OK):
                raise PermissionError(f"검수표 파일에 쓸 권한이 없어 저장하지 못했어요. 파일이 읽기 전용인지 확인해 주세요 ({self.path.name})") from e
            if isinstance(e, PermissionError):     # 윈도우: 다른 프로그램이 파일을 쥐고 있음
                raise PermissionError("다른 프로그램이 검수표 파일을 쓰고 있어 저장하지 못했어요. 그 프로그램을 닫고 다시 눌러 주세요") from e
            raise OSError(f"검수표를 저장하지 못했어요 ({e.strerror or e}). 저장 공간과 파일 위치를 확인해 주세요") from e
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


_COND = {"temp": "온도", "temp_unit": "온도 단위", "pressure": "압력", "pressure_unit": "압력 단위", "method": "방법",
         "reference": "기준", "conc_value": "농도", "conc_unit": "농도 단위", "raw": "원문 표기"}


def _alts_of(s: dict | None) -> list[dict]:
    """스키마 칸 → 허용하는 모양들(anyOf를 펼침)."""
    if not s:
        return []
    s = _resolve(s)
    return [a for a in (_resolve(x) for x in s.get("anyOf", [s])) if a.get("type") or a.get("enum") or a.get("properties")]


def _alts(path: str) -> list[dict]:
    m = _ROW_PATH.fullmatch(path.replace("[*]", "[0]"))     # '[*]' = 새 항목 자리
    return _alts_of(_schema_at(generic(m.group(2)))) if m else []


def _types(alts: list[dict]) -> set[str]:
    return {t for a in alts for t in ([a["type"]] if isinstance(a.get("type"), str) else a.get("type") or [])}


def _props(alts: list[dict]) -> dict:
    return next((a["properties"] for a in alts if a.get("properties")), {})


def _form(path: str) -> dict:
    """입력 방식(_form_kind)과 이 칸의 빈 값(blank: '비움으로 저장'이 보낼 칸 글. null 허용이면 null, 배열이면 [], 글 칸이면 ""; 비울 수 없으면 None)."""
    return {**_form_kind(path), "blank": _blank_cell(_alts(path))}


def _blank_cell(alts: list[dict]) -> str | None:
    if not alts:
        return None
    if "null" in _types(alts):
        return "null"
    return next((_cell_of(x) for x in ([], "") if not validate(x, {"$defs": load_schema()["$defs"], "anyOf": alts})), None)


def _form_kind(path: str) -> dict:
    """사람이 JSON을 몰라도 고칠 수 있게 칸 모양에 맞는 입력 방식. 고르기(정해진 값·예/아니오·성분), 수치(원문 표기 그대로),
    문장(소제목·내용), 조건(칸 나눠 적기), 목록(한 줄에 하나), 숫자, 글."""
    alts = _alts(path)
    types, props = _types(alts), _props(alts)
    empty = [["null", "비움 (원문에 적힌 것이 없음)"]] if "null" in types else []
    if path.endswith((".comp_ref", ".parent_seq")):
        return {"kind": "comp", "empty": empty}
    enum = list(dict.fromkeys(v for a in alts for v in a.get("enum") or [] if isinstance(v, str)))
    if enum:
        return {"kind": "choice", "options": [[v, _choice_label(v)] for v in enum] + empty}
    if "boolean" in types:
        return {"kind": "choice", "options": [["true", "예"], ["false", "아니오"]] + empty}
    if {"raw", "status", "unit"} <= props.keys():
        return {"kind": "q"}
    if {"key", "value", "text"} <= props.keys():
        return {"kind": "stmt"}
    if props:                          # 칸마다 입력 방식(단위처럼 정해진 값은 고르기)
        return {"kind": "obj", "fields": [[k, _COND.get(k, k), _form(f"{path}.{k}")] for k in props]}
    if "array" in types:
        return {"kind": "list"}
    if types & {"integer", "number"} and "string" not in types:
        return {"kind": "number"}
    return {"kind": "text"}


def _names(rows: list[dict]) -> dict[str, str]:
    """카드 제목·값에 나오는 TO21 코드 → 한글 이름 (검수자는 코드를 모른다: 'TX_ORAL' → '급성 독성(경구)')."""
    out = {}
    for r in rows:
        key = re.search(r"\(([^()]*)\)$", str(r["칸 이름"]))
        for tok in [*(re.sub(r"#\d+$", "", x) for x in (key.group(1).split(" / ") if key else [])), _val(r)]:   # 'APPEARANCE_STATE#2'도
            if tok in _code_names() and _code_names()[tok][0] != tok:
                out[tok] = _code_names()[tok][0]
    return out


def _choice_label(v: str) -> str:
    if v in STATUS_TEXT:
        return f"{v} — {STATUS_TEXT[v]}"
    names = _code_names().get(v)
    return f"{names[0]} · {v}" if names and names[0] != v else v         # 검수자는 코드를 모른다: 이름 먼저


def _coerce(s: str, alts: list[dict], path: str = ""):
    """사람이 적은 글 → 칸 모양의 TO21 값. 수치 칸은 원문 표기('> 2000 mg/kg')를 R04대로 나눈 Q,
    글 칸은 숫자처럼 보여도 글자, 숫자 칸은 숫자. 맞지 않으면 ValueError(사람이 읽을 이유)."""
    types, props, parsed = _types(alts), _props(alts), from_cell(s)
    if s in ("null", "비움"):
        val = None
    elif {"raw", "status", "unit"} <= props.keys():
        val = parsed if isinstance(parsed, dict) else fill_q(parse_qm(s))
        if val.get("status") is None:         # 숫자도 상태어도 못 읽음: 줄 전체를 붙여 넣은 경우 등
            raise ValueError("수치를 읽지 못했습니다. '> 2000 mg/kg'처럼 값 부분만 남겨 주세요 (원문에 수치가 없으면 자료없음·해당없음·미기재 중 하나)")
    elif props:
        if not isinstance(parsed, dict):
            raise ValueError("칸을 나눠 적는 칸입니다. 화면의 입력칸에 나눠 적어 주세요")
        val = {}
        for k, x in parsed.items():               # 나눠 적는 칸: 틀린 칸 이름을 붙여 알린다 ('온도 단위: 목록에서 골라 주세요')
            try:
                val[k] = _coerce(x, _alts_of(props[k])) if isinstance(x, str) and k in props and k not in ("raw", "text") else x
            except ValueError as e:
                raise ValueError(f"{_COND.get(k, k)}: {e}") from None
    elif "array" in types:
        val = parsed if isinstance(parsed, list) else [x.strip() for x in re.split(r"[\n;]", s) if x.strip()]
    elif "boolean" in types and s in ("예", "아니오"):
        val = s == "예"
    elif types & {"integer", "number"} and "string" not in types:
        num = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s) else s   # 천 단위 쉼표만 지운다('1,5'는 받지 않음)
        try:
            val = json.loads(num)
            assert isinstance(val, (int, float)) and not isinstance(val, bool)
        except (ValueError, AssertionError):
            raise ValueError(f"숫자만 적어 주세요. 소수점은 '.'으로 (지금: {s})") from None
        if "integer" in types and "number" not in types:
            if not float(val).is_integer():
                raise ValueError(f"정수만 적어 주세요 (지금: {s})")
            val = int(val)
    elif "string" in types:
        val = s                       # 글 칸: '01', '12345'도 글자 그대로
    else:
        val = parsed
    errs = validate(val, {"$defs": load_schema()["$defs"], "anyOf": alts})
    if errs:
        enum = [v for a in alts for v in a.get("enum") or [] if isinstance(v, str)]
        pat = any(a.get("pattern") for a in alts)
        ex = (_spec_row(path) or [None] * 11)[10] if path else None      # 명세서의 보기 값 ('P280', 'KE-32570')
        if props and isinstance(val, dict):   # 칸을 나눠 적는 값: JSON 대신 맞지 않는 칸 이름으로
            bad = next((k for k, x in val.items() if k in props and validate(x, {"$defs": load_schema()["$defs"], "anyOf": _alts_of(props[k])})), None)
            raise ValueError(f"‘{_COND.get(bad, bad)}’ 칸 값이 맞지 않아요 (지금: {val[bad]})" if bad else "나눠 적은 칸 가운데 맞지 않는 것이 있어요. 칸마다 확인해 주세요")
        raise ValueError(f"목록에서 골라 주세요 (지금: {s})" if enum and not props          # 칸 모양별 쉬운 말 (스키마 영어 오류 대신)
                         else f"형식이 맞지 않아요{f' (예: {ex})' if ex else ''}. 지금: {s}" if pat
                         else f"이 칸에 맞지 않는 값이에요 (지금: {s})")
    return val


def _cell_of(val) -> str:
    """검수표 칸에 적을 글. 숫자·true처럼 읽히는 글자는 따옴표로 감싸 골드셋에서도 글자로 남게 한다."""
    if val is None:
        return "null"
    if isinstance(val, str) and from_cell(val) != val:
        return json.dumps(val, ensure_ascii=False)
    return to_cell(val)


def _typed(path: str, values: dict) -> dict:
    """수정값을 칸 모양의 TO21 값으로 바꾸고 스키마로 바로 검사한다. 틀리면 저장하지 않고 이유를 알린다
    (전에는 골드셋을 만들 때에야 스키마 오류로 드러났다)."""
    v, alts = values.get("수정값"), _alts(path)
    if v in (None, "") or not alts:
        return values
    s = str(v).strip()
    if s not in ("null", "비움") and _cell_of(x := from_cell(s)) == s and not validate(x, {"$defs": load_schema()["$defs"], "anyOf": alts}):
        return {**values, "수정값": s}    # 이미 칸 글자 꼴(사람이 따옴표까지 적은 '"2"', 검수표에서 옮겨 붙인 값 등)이면 그대로: 한 번 더 따옴표로 감싸지 않는다
    return {**values, "수정값": _cell_of(_coerce(s, alts, path))}


def _val(r: dict) -> str:
    return _plain(_cell_now(r))


def _comp_options(rows: list[dict], drop: dict) -> dict[str, list]:
    """MSDS 건마다 대상 성분 고르기 목록: MIX(제품 전체)와 성분표의 순번·이름·CAS."""
    out = {}
    for r in rows:
        m = re.fullmatch(r"msds\[(\d+)\]\.components\[k=([^\]]*)\]\.seq", r["경로"])
        if m and not gone_by(r["경로"], drop):          # 골드에서 빠지는 성분은 고를 수 없다
            name = next((_val(x) for x in rows if x["경로"] == r["경로"][:-4] + ".name"), "")
            out.setdefault(m.group(1), [["MIX", "제품 전체 · MIX"]]).append(
                [_val(r), f"{_val(r)} — {name or m.group(2)}" + (f" (CAS {m.group(2)})" if m.group(2) != _norm(name) else "")])
    return out


def _key_fields(list_rel: str) -> list[str]:
    """목록(번호를 지운 경로)의 항목을 가르는 칸 이름: 짝짓기 키 함수가 읽는 칸."""
    fn, seen = LIST_KEYS.get(list_rel), []

    class Rec(dict):
        def get(self, k, d=None):
            seen.append(k) if k not in seen else None
            return None
    if fn:
        fn(Rec(), {})
    return seen


def _addable(path: str) -> bool:
    """사람이 한 칸으로 넣을 수 있는 칸인가: 안에 항목 목록(객체 목록)을 품은 칸은 그 목록의 카드에서 넣는다."""
    m = _ROW_PATH.fullmatch(path)
    arr = _branch(_schema_at(generic(m.group(2))) or {}, "array") if m else None
    return bool(m) and in_scope(m.group(2)) and not (arr and _props(_alts_of(arr.get("items"))))


def _field_label(path: str) -> str:
    return label_of(_ROW_PATH.fullmatch(path).group(2)).split(" (")[0].split(" · ")[-1]


def _must(path: str) -> str:
    """TO21 채점기가 필수 항목으로 재는 칸이면 그 항목 이름. 작은 골드(개발용 2~3건의 필수 항목만 검수, 재계획 결정 10)에서
    이 칸만 골라 보게 한다. 채점기(TO21_MSDS_채점기_v0.6.py)가 비교하는 칸과 같게 둔다."""
    m = _ROW_PATH.fullmatch(path)
    rel = m.group(2) if m else ""
    g, f = generic(rel), rel.rsplit(".", 1)[-1].split("[")[0]
    key = lambda lst: ((re.search(lst + r"\[k=([^\]]*)\]", rel) or [None, ""])[1].split("#")[0].split("|") + ["", ""])
    rules = (
        ("관리정보(제출번호·작성일·개정일·개정횟수)", g in {f"meta.{k}" for k in ("msds_no", "first_issue_date", "last_revision_date", "revision_no")}),
        ("제품명·회사명·긴급연락처", g in {"product.name", "companies[].name", "companies[].site", "companies[].role"}
         or (g in ("companies[].contacts[].type", "companies[].contacts[].value") and key("contacts")[0] == "긴급"   # 채점기는 첫 긴급 연락처만
             and "#" not in (re.search(r"contacts\[k=([^\]]*)\]", rel) or [None, ""])[1])),
        ("신호어", g == "hazard.signal_word"),
        ("그림문자", g in ("hazard.pictograms[].code", "hazard.pictograms")),          # 목록 자체(빈 목록 [])도 채점된다
        ("H 코드", g in ("hazard.h_statements[].code", "hazard.h_statements")),
        ("P 코드", g in ("hazard.p_statements[].code", "hazard.p_statements")),
        ("유해성 분류(코드+구분)", g in {"hazard.classes[].class_code", "hazard.classes[].category", "hazard.classes"}),
        ("구성성분(CAS·성분명·KE·함유량)", g in {f"components[].{k}" for k in ("cas_no", "name", "ke_no", "content", "seq")} | {"components"}),
        ("8항 노출기준(성분·출처·종류·값)", g.startswith("exposure_limits[].") and f in {"comp_ref", "standard", "limit_type", "q"}),
        ("9항 필수 물성(특성·값)", g.startswith("physchem[].") and key("physchem")[1] in MUST_PHYSCHEM and f in {"comp_ref", "prop_code", "text_value", "q"}),
        ("11항 급성독성(경구·경피·흡입)", g.startswith("toxicity[].") and key("toxicity")[1] in ACUTE and f in {"comp_ref", "endpoint", "descriptor", "status", "q"}),
        ("15항 국내 규제(성분·항목·해당여부·기준농도)", g.startswith("regulations[].") and key("regulations")[1] in DOMESTIC_LAWS
         and f in {"comp_ref", "law", "item_code", "applicable", "threshold"}),
        ("14항 운송(UN번호·등급·용기등급)", g in {"transport[].un_no", "transport[].hazard_class", "transport[].packing_group"}),
    )
    return next((name for name, hit in rules if hit), "")


def _pick(pg: "_Page", x: float, y: float) -> dict:
    """사진에서 누른 자리(쪽 너비·높이 비율)의 원문 글자: 그 칸(띄어쓰기보다 넓은 틈으로 나뉜 덩어리)과 그 줄 전체.
    검수자가 원문 조각을 손으로 옮겨 적지 않게 한다."""
    X, Y = x * pg.W, y * pg.H
    if not pg.vb:
        return {}
    k0 = min(range(len(pg.vb)), key=lambda k: (0 if pg.vb[k][1] - 2 <= Y <= pg.vb[k][3] + 2 else 1 + abs((pg.vb[k][1] + pg.vb[k][3]) / 2 - Y),
                                               abs((pg.vb[k][0] + pg.vb[k][2]) / 2 - X)))
    if not pg.vb[k0][1] - pg.lh(k0) <= Y <= pg.vb[k0][3] + pg.lh(k0):
        return {}
    ks = [k for k in range(len(pg.vt)) if pg.line[k] == pg.line[k0]]
    gap = lambda a, b: pg.vb[b][0] - pg.vb[a][2]

    raw = getattr(pg, "raw", {})

    def text(seq):                    # 원문 글자 그대로(대소문자·부호). 한 글자가 찾기용 글자 여럿이 된 것은 한 번만
        out = ""
        for a, b in zip([None] + seq, seq):
            if a is not None and pg.vb[a] is pg.vb[b]:
                continue
            out += (" " if a is not None and gap(a, b) > pg.lh(b) * .25 else "") + raw.get(id(pg.vb[b]), pg.vt[b])
        return re.sub(r"\s+", " ", out).strip()
    i = j = ks.index(k0)
    while i > 0 and gap(ks[i - 1], ks[i]) < pg.lh(ks[i]) * 1.2:
        i -= 1
    while j < len(ks) - 1 and gap(ks[j], ks[j + 1]) < pg.lh(ks[j]) * 1.2:
        j += 1
    return {"cell": text(ks[i:j + 1]), "line": text(ks)}


def _row_pages(r: dict) -> set[int]:
    return {int(x) for c in ("Claude 쪽", "GPT 쪽", "수정 쪽") for x in re.findall(r"\d+", str(r.get(c) or ""))}


_HEAD = re.compile(r"^\s*(?:\d{1,2}\.(?!\d)|[가-하][.)]|[①-⑳]|\(?\d{1,2}\)|[○●■□▶◆◇•·*-])?\s*([^:：]{0,40}?)[:：]?\s*$")


def _repeated(locator: "Locator") -> set[str]:
    """쪽마다 되풀이되는 줄(머리말·꼬리말: '버전 : 4.1', '페이지 5 of 11'). 숫자는 #로 바꿔 센다."""
    if not hasattr(locator, "_rep"):
        pages = [n for n in range(1, (len(locator.doc) if locator.doc else 0) + 1) if n in locator.ok or n in locator.ocr]
        seen = Counter(t for n in pages for t in {re.sub(r"\d+", "#", x) for x in locator.page(n).line_text().values()})
        locator._rep = {t for t, c in seen.items() if len(pages) >= 3 and c >= max(3, len(pages) / 2)}
    return locator._rep


def _unused(locator: "Locator", no: int, rows: list[dict]) -> list:
    """이 쪽에서 검수 범위 안인데 어떤 칸의 근거(원문 조각·값 자리)로도 쓰이지 않은 원문 줄의 상자.
    모델이 통째로 빠뜨린 값을 검수자가 찾게 돕는다. 항·소항목 제목처럼 값이 없는 줄('가. 노출 경로에 관한 정보')은 뺀다."""
    if no not in locator.ok and no not in locator.ocr:
        return []
    mine = [r for r in rows if no in _row_pages(r)]
    sig = (no, tuple((r["경로"], r["수정값"], r["수정 원문 조각"]) for r in mine))   # '맞음'만 누른 것은 다시 계산하지 않는다
    cache = locator.__dict__.setdefault("_unused", {})
    if sig in cache:
        return cache[sig]
    pg, used, hints = locator.page(no), set(), {}
    for r in mine:
        edited = r["수정값"] != "" and r["검수 결과"] in NEED_SOURCE
        t = next((t for t in ("Claude", "GPT") if r[f"{t} 값"] != ""), "Claude")
        item = (re.match(r"msds\[\d+\]\..*\[k=[^\]]*\]", r["경로"]) or [""])[0]    # 이름 힌트는 가장 안쪽 키 항목마다 같다
        if item not in hints:
            hints[item] = _hints(r["경로"], rows)
        used |= locator.locate(no, _val(r), r["수정 원문 조각"] if edited else r[f"{t} 원문 조각"], section_of(r["경로"]),
                               hints[item], r["칸 이름"], light=True)["chars"]
    carry = next((v for n in range(no - 1, 0, -1) if n in locator.ok or n in locator.ocr
                  for v in [next((x for x in reversed(locator.page(n).section_at()) if x and x > 0), None)] if v), None)
    sec, text, out = pg.section_at(), pg.line_text(), []
    for ln, t in sorted(text.items()):
        v = sec[ln] if ln < len(sec) else None
        v = carry if v is None or v < 0 and carry and carry < -v else (None if v < 0 else v)
        ks = [k for k in range(len(pg.vt)) if pg.line[k] == ln]
        if (v not in REVIEW_SECTIONS[1:] or len(re.findall(r"[0-9a-z가-힣]", t)) < 2 or used & set(ks)
                or re.sub(r"\d+", "#", t) in _repeated(locator)):
            continue
        raw = "".join(getattr(pg, "raw", {}).get(id(pg.vb[k]), pg.vt[k]) for k in ks)
        m = _HEAD.match(raw)               # 제목·이름표 줄: 번호·글머리표 뒤에 숫자(괄호 안 제외)·상태어가 없는 짧은 글
        if m and not re.search(r"\d", re.sub(r"\([^)]*\)", "", m.group(1))) and _norm(m.group(1)) not in _status_words():
            continue
        out += pg.rects(ks)
    cache[sig] = out
    return out


def _stmt_like(alts: list[dict]) -> bool:
    return {"key", "value", "text"} <= _props(alts).keys()


def _obj_list(path: str) -> bool:
    """항목 목록(객체 목록) 칸인가 (연락처, 서술 문장 등)."""
    m = _ROW_PATH.fullmatch(path.replace("[*]", "[0]"))
    arr = _branch(_schema_at(generic(m.group(2))) or {}, "array") if m else None
    return bool(arr and _props(_alts_of(arr.get("items"))))


def _item_form(item: str, rows: list[dict]) -> dict:
    """카드(목록 항목 하나, 또는 칸 묶음)에 사람이 넣을 수 있는 칸: 이 항목에 빠진 칸, 같은 종류의 새 항목 칸,
    비어 있는 하위 목록(연락처 등)의 새 항목, 맞는 TO21 칸이 없을 때의 미정의 항목(R24).
    item이 '…[*]'이면 그 목록의 새 항목. 경로를 사람이 쓰지 않게 칸 이름과 입력 방식만 준다."""
    probe = item.replace("[*]", "[0]")      # 스키마를 볼 때만 쓰는 자리 번호
    m = _ROW_PATH.fullmatch(probe)
    if not m:
        raise ValueError(f"카드 경로가 맞지 않음: {item}")
    alts = _alts_of(_schema_at(generic(m.group(2))))
    if any(r["경로"] == item for r in rows) or _stmt_like(alts):   # 항목이 칸 하나(서술 문장 한 줄 등): 같은 종류의 새 줄만
        return {"missing": [], "new": {"single": {"name": "", "label": _field_label(probe), "form": _form(probe)}}}
    props = _props(alts)
    have = {re.split(r"[.\[]", p[len(item) + 1:])[0] for p in (r["경로"] for r in rows) if p.startswith(item + ".")}
    names = [k for k in props if _addable(f"{probe}.{k}")]
    field = lambda k: {"name": k, "label": _field_label(f"{probe}.{k}") + (" (채점 필수)" if _must(f"{probe}.{k}") else ""), "form": _form(f"{probe}.{k}")}
    out = {"missing": [field(k) for k in names if k not in have]}
    lst = re.sub(r"\[[^\]]*\]$", "", item)
    if lst != item:                         # 목록 항목이면 같은 종류의 새 항목도 넣을 수 있다
        keys = _key_fields(generic(lst[len(f"msds[{m.group(1)}]."):]))
        out["new"] = ({"fields": [{**field(k), "key": k in keys} for k in sorted(names, key=lambda k: k not in keys)]}
                      if props else {"single": {"name": "", "label": _field_label(probe), "form": _form(probe)}})
    if "[*]" not in item:
        sub = lambda k: [_field_label(f"{probe}.{k}[0].{c}") for c in list(_props(_alts_of((_branch(_schema_at(generic(f"{m.group(2)}.{k}")), "array") or {}).get("items"))))[:3]]
        out["lists"] = [{"item": f"{item}.{k}[*]", "label": ("문장" if k == "statements" else "·".join(sub(k)))} for k in props
                        if _obj_list(f"{probe}.{k}") and in_scope(f"{m.group(2)}.{k}")]
        sec = next((section_of(r["경로"]) for r in rows if r["경로"].startswith(item)), None)
        if sec and sec in REVIEW_SECTIONS and ".extras[" not in item:
            out["extra"] = {"section": sec}
    return out


def _new_rows(item: str, mode: str, fields: dict, common: dict, rows: list[dict]) -> list[dict]:
    """빠진 칸·새 항목 → 누락 추가 줄들. 새 항목의 경로(키)는 사람이 적은 값으로 짝짓기 키 함수가 만든다."""
    m = _ROW_PATH.fullmatch(item)
    if not m or not isinstance(fields, dict):
        raise ValueError("item, fields가 맞지 않음")
    filled = {k: str(v).strip() for k, v in fields.items() if str(v if v is not None else "").strip()}
    if not filled:
        raise ValueError("넣을 값을 적어 주세요")
    if mode == "field":
        return [{**common, "경로": f"{item}.{k}", "수정값": v} for k, v in filled.items()]
    if mode == "extra":                     # 맞는 TO21 칸이 없는 값: 미정의 항목(R24)으로
        pre = f"msds[{m.group(1)}]."
        sec, title = filled.get("section_no", ""), filled.get("title_raw", "")
        if not title or "" not in filled:
            raise ValueError("원문 항목 제목과 내용을 적어 주세요")
        if not sec.isdigit() or not 1 <= int(sec) <= 16:
            raise ValueError("항 번호는 1~16 숫자로 적어 주세요")
        ks = _key_str(LIST_KEYS['extras']({'section_no': int(sec), 'title_raw': title}, {}))
        n = 1
        while any(r["경로"].startswith(f"{pre}extras[k={ks if n == 1 else f'{ks}#{n}'}].") for r in rows):
            n += 1
        new = f"{pre}extras[k={ks if n == 1 else f'{ks}#{n}'}]"
        seqs = [int(v) for r in rows if re.fullmatch(re.escape(pre) + r"extras\[k=[^\]]*\]\.seq", r["경로"]) and (v := _val(r)).isdigit()]
        stmt = from_cell(filled[""])
        if isinstance(stmt, dict) and stmt.get("seq") is None:
            stmt["seq"] = 1
        vals = {"seq": str(max(seqs, default=0) + 1), "section_no": sec, "title_raw": title, "reason": "필드없음"}
        if str(common.get("수정 쪽") or "").strip().isdigit():
            vals["page"] = str(common["수정 쪽"]).strip()
        return ([{**common, "경로": f"{new}.{k}", "수정값": v} for k, v in vals.items()]
                + [{**common, "경로": f"{new}.statements[0]", "수정값": json.dumps(stmt, ensure_ascii=False) if isinstance(stmt, dict) else filled[""]}])
    pre, lst = f"msds[{m.group(1)}].", re.sub(r"\[[^\]]*\]$", "", item)
    probe = item.replace("[*]", "[0]")
    if lst == item:
        raise ValueError("목록 항목이 아니라 새 항목을 넣을 수 없습니다. '빠진 칸 넣기'를 쓰세요")
    rel = generic(lst[len(pre):])
    one = _coerce(filled[""], _alts(probe), probe) if "" in filled else None    # 항목이 칸 하나(서술 문장 등)
    if isinstance(one, dict) and "seq" in one and one["seq"] is None:   # 새 문장의 순번: 같은 목록의 끝 번호 다음
        seqs = [x.get("seq") for r in rows if r["경로"].startswith(lst + "[") for x in [from_cell(_cell_now(r))]
                if isinstance(x, dict) and isinstance(x.get("seq"), int)]
        one["seq"] = max(seqs, default=0) + 1
        filled[""] = json.dumps(one, ensure_ascii=False)
    if fn := LIST_KEYS.get(rel):
        if "" in filled:                    # 그 값 안의 칸으로 키를 만든다 (키가 있는 서술 문장)
            vals = one
            if not isinstance(vals, dict):
                raise ValueError("이 목록의 새 항목은 칸을 나눠 적어야 합니다")
        else:
            vals = {k: _coerce(v, _alts(f"{probe}.{k}"), f"{probe}.{k}") for k, v in filled.items()}
        keys = _key_fields(rel)
        if "comp_ref" in keys and vals.get("comp_ref") in (None, ""):
            raise ValueError("대상 성분을 골라 주세요")
        if not any(vals.get(k) not in (None, "") for k in keys):
            raise ValueError("항목을 가르는 칸(★)을 하나 이상 적어 주세요: " + ", ".join(_field_label(f"{probe}.{k}") for k in keys))
        cm = {"MIX": "MIX"} | {_val(r): r["경로"][len(pre + "components[k="):-len("].seq")] for r in rows
                               if r["경로"].startswith(pre + "components[k=") and r["경로"].endswith("].seq")}
        ks = _key_str(fn(vals, cm))
        taken = lambda k: any(r["경로"] == f"{lst}[k={k}]" or r["경로"].startswith(f"{lst}[k={k}].") for r in rows)
        n = 1                              # 같은 키가 이미 있으면 keyed_flatten처럼 '#2', '#3'을 붙인다 (두 번째 긴급 연락처 등)
        while taken(ks if n == 1 else f"{ks}#{n}"):
            n += 1
        new = f"{lst}[k={ks if n == 1 else f'{ks}#{n}'}]"
    else:
        idx = [int(x.group(1)) for r in rows if (x := re.match(re.escape(lst) + r"\[(\d+)\]", r["경로"]))]
        new = f"{lst}[{max(idx, default=-1) + 1}]"
    if "" in filled:
        return [{**common, "경로": new, "수정값": filled[""]}]
    return [{**common, "경로": f"{new}.{k}", "수정값": v} for k, v in filled.items()]


def _same(v):
    """중복 비교용 값: 문장은 소제목·내용만(순번·원문 줄·점수 등 화면이 채운 칸은 뺀다), 수치는 원문 표기, 글은 정규화."""
    if isinstance(v, dict) and "value" in v and "key" in v:
        return ("문장", _norm(str(v.get("key") or "")), _norm(str(v.get("value") or "")))
    if isinstance(v, dict) and "raw" in v:
        return ("수치", _norm(str(v.get("raw") or "")))
    return _norm(v) if isinstance(v, str) else v


def _dup(new: list[dict], rows: list[dict]) -> dict:
    """새 항목과 겹치는 것이 이미 있나 → {"dup": "same"}(같은 목록의 다른 항목에 새 칸 값이 모두 같게 있음) 또는
    {"dup": "kind", "kind": 이름, "n": 장 수}(값은 다르고 키만 겹쳐 '#2'가 붙음), 없으면 {}.
    ('필수 칸만'에서 숨은 카드를 못 보고 같은 줄을 또 넣는 것을 막되, 값이 다른 같은 종류는 겁주지 않는다)"""
    item = lambda p: p[:p.rfind("]") + 1]                    # 항목 경로 (…[k=…] 또는 …[n])
    if not new or "]" not in new[0]["경로"]:
        return {}
    it = item(new[0]["경로"])
    lst = lambda i: re.sub(r"\[[^\]]*\]$", "", i)
    try:                                                     # 사람이 적은 글 → 칸 모양 값 (틀린 값은 add_rows가 알린다)
        want = {r["경로"][len(it):]: _same(from_cell(_typed(r["경로"], {"수정값": r["수정값"]})["수정값"])) for r in new}
    except ValueError:
        return {}
    if lst(it).endswith(".extras"):                         # 미정의 항목: 순번·사유는 화면이 정한 값이라 견주지 않는다
        want = {f: x for f, x in want.items() if f not in (".seq", ".reason")}
    have, gone, top = {}, set(), re.compile(re.escape(lst(it)) + r"\[[^\]]*\]")
    for r in rows:                                           # 같은 목록 항목마다 칸 값 (항목 안 하위 목록 줄도: 미정의 항목의 문장)
        if (m := top.match(r["경로"])) and (i := m.group(0)) != it:
            have.setdefault(i, {})[r["경로"][len(i):]] = _same(from_cell(_cell_now(r)))
            if r.get("검수 결과") == "삭제":                 # 이미 삭제한 항목은 골드에 없으니 같은 내용으로 세지 않는다
                gone.add(i)
    have = {i: v for i, v in have.items() if i not in gone}
    if any(all(v.get(f) == x for f, x in want.items()) for v in have.values()):
        return {"dup": "same"}
    if m := re.search(r"\[k=([^\]]*)#\d+\]$", it):
        base = f"{lst(it)}[k={m.group(1)}"
        n = sum(1 for i in have if i == base + "]" or i.startswith(base + "#"))
        kind = " · ".join((_code_names().get(x) or [x])[0] for x in m.group(1).split("|") if x)
        return {"dup": "kind", "kind": kind, "n": n}
    return {}


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


def _stamp(t: str, doc_id: str) -> int:
    """모델 실버 파일의 수정 시각(없으면 0). 캐시 키에 넣어, 실버가 바뀌면 다시 읽는다."""
    f = paths.silver_path(t, doc_id) if doc_id else None
    return os.stat(f).st_mtime_ns if f and f.exists() else 0


@lru_cache(maxsize=16)
def _silver(t: str, doc_id: str, stamp: int) -> dict:
    """모델 실버를 펼친 것 {경로: (…, 키 경로, 값)}."""
    return flat_doc(json.loads(paths.silver_path(t, doc_id).read_text(encoding="utf-8"))) if stamp else {}


def silver_rank(doc_id: str) -> dict[str, int]:
    """칸 경로마다 실버 JSON 안 순서. 모델은 목록을 문서에 적힌 순서로 내므로, 순번 칸이 없는 목록(8항 노출기준 등)도 문서 순서로 놓을 수 있다."""
    return _rank_at(doc_id, _stamp("claude", doc_id), _stamp("gpt", doc_id))


@lru_cache(maxsize=8)
def _rank_at(doc_id: str, sc: int, sg: int) -> dict[str, int]:
    rank = {}
    for t, st in (("claude", sc), ("gpt", sg)):
        for p in _silver(t, doc_id, st):
            rank.setdefault(p, len(rank))
    return rank


def page_count(doc_id: str) -> int:
    return len(list(paths.page_dir(doc_id).glob("p*.png")))


_DASH = str.maketrans("‐‑‒–—―−", "-------")    # 글자층의 en dash 등과 조각의 '-'를 같게 본다


def _norm(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", s or "").lower().translate(_DASH) if not ch.isspace() and ch != "|")


def _visual(chars: list) -> tuple[list, list]:
    """글자를 사진에서 읽는 순서로: 세로 가운데가 글자 높이 절반 안이면 같은 줄, 줄 안은 왼쪽부터. (글자 목록, 줄 번호 목록)"""
    lines = []
    for ch, bb in sorted(chars, key=lambda t: (t[1][1] + t[1][3]) / 2):
        y = (bb[1] + bb[3]) / 2
        if lines and abs(y - lines[-1][0]) < max(bb[3] - bb[1], 1) / 2:
            lines[-1][1].append((ch, bb))
        else:
            lines.append([y, [(ch, bb)]])
    out, no = [], []
    for k, (_, ln) in enumerate(lines):
        out += sorted(ln, key=lambda t: t[1][0])
        no += [k] * len(ln)
    return out, no


class _Page:
    """한 쪽의 글자. vt·vb·line = 사진에서 읽는 순서의 글자·상자·줄 번호.
    orders = [(글자, 각 글자의 사진 순서 번호)] 두 벌: 글자층에 저장된 순서, 사진 순서.
    글자층은 한 줄 안에서도 한글과 영문·숫자를 따로 담기도 해서('N,N 디sec-부틸' → '디부틸 … n,nsec-')
    두 순서에서 모두 찾는다."""

    def __init__(self, chars: list, W: float, H: float, ocr: bool = False):
        self.ocr = ocr                            # OCR 줄 상자로 만든 쪽 (글자 오독이 있을 수 있다)
        vis, self.line = _visual(chars)
        self.vt, self.vb, self.W, self.H = "".join(c for c, _ in vis), [b for _, b in vis], W, H
        at = {id(b): k for k, b in enumerate(self.vb)}
        self.orders = [("".join(c for c, _ in chars), [at[id(b)] for _, b in chars]), (self.vt, list(range(len(vis))))]
        self._grams = [None, None]

    def lh(self, k: int) -> float:
        return max(self.vb[k][3] - self.vb[k][1], 1)

    def overlaps(self, a: set, b: set) -> bool:
        """두 글자 묶음이 사진에서 같은 자리인가 (같은 줄에서 상자가 겹침)."""
        return any(self.line[i] == self.line[j] and self.vb[i][0] < self.vb[j][2] and self.vb[j][0] < self.vb[i][2] for i in a for j in b)

    def line_text(self) -> dict:
        if not hasattr(self, "_lt"):
            self._lt = {}
            for k, ch in enumerate(self.vt):
                self._lt[self.line[k]] = self._lt.get(self.line[k], "") + ch
        return self._lt

    def pick_by_hints(self, found: list, groups: list, every: bool = False) -> list:
        """같은 조각의 여러 자리 가운데 이 칸의 자리를 고른다. groups = [(우리 이름들, 같은 목록의 다른 이름들)] (_hints).
        자리마다 그 줄부터 위로 올라가며(안쪽 목록 단계는 바깥 단계 이름이 나온 줄까지만) 이름(우리 것이든 다른 것이든)이 처음 나오는 줄을 본다:
        우리 이름이면 맞는 자리, 다른 성분·소항목 이름이면 버린다, 쪽 위까지 없으면 앞 쪽에서 이어진 자리로 남겨 둔다.
        ('· NTP : 해당없음'이 성분 블록마다 되풀이되면 바로 위 '- 시스 2 부텐' 블록의 것은 '부텐 1' 칸이 아니다)"""
        keep = []
        for f in found:
            hit, other = self.scan_names(f, groups)
            if not other:
                keep.append((hit, f))
        if every:                 # 모순 없는 자리 모두 (reanchor가 원래 자리를 지킬지 정할 때)
            return [f for _, f in keep]
        if not keep:
            return found
        best = max(h for h, _ in keep)
        return [f for h, f in keep if h == best]

    def scan_names(self, f: set, groups: list) -> tuple[int, str]:
        """f 위로 올라가며 묶음마다 처음 나오는 이름: (우리 이름이 먼저 나온 묶음 수, 다른 항목 이름이 먼저 나왔으면 그 이름)."""
        lt, top, hit, other = self.line_text(), min(self.line[k] for k in f), 0, ""
        floor, lv_now, lv_hit = 0, 0, 0   # 안쪽 목록 이름은 바깥 항목 이름이 나온 줄 아래에서만 찾는다
        for own, others, lv in groups:    # (공급자 묶음 위의 '긴급 전화번호'는 제조자 묶음의 것)
            if lv != lv_now:
                floor, lv_now = max(floor, lv_hit), lv
            for ln in range(top, floor - 1, -1):
                text = lt.get(ln, "")
                if any(h in text for h in own):
                    hit += 1
                    lv_hit = max(lv_hit, ln)
                    break
                if o := next((h for h in others if h in text), ""):
                    other = other or o
                    break
        return hit, other

    def hint_hit(self, f: set, groups: list) -> bool:
        """f 위에서 가장 가까운 이름이 우리 이름인 묶음이 하나라도 있나 (없으면 앞 쪽에서 이어진 자리로 고른 것)."""
        lt, top = self.line_text(), min(self.line[k] for k in f)
        for own, others, _ in groups:
            for ln in range(top, -1, -1):
                if any(h in lt.get(ln, "") for h in own):
                    return True
                if any(h in lt.get(ln, "") for h in others):
                    break
        return False

    def reanchor(self, f: set, hints: list, snippet: str) -> set:
        """f에서 가장 긴 한 줄 조각(4글자 이상)이 쪽에 여러 번 나오고 지금 자리가 힌트와 모순되면(위에서 가장 가까운 이름이 다른 성분·소항목),
        pick_by_hints로 한 곳이 정해질 때 그 자리로 옮기고 원문 조각 전체를 그 자리 근처(위 12줄 ~ 아래 3줄)에서만 다시 정렬한다
        (처음 자리에 맞춰 집은 제목 조각이 남지 않게). 지금 자리가 모순되지 않거나 다시 정렬이 안 되면 그대로 둔다."""
        runs, cur = [], []
        for k in sorted(f):
            if cur and k == cur[-1] + 1 and self.line[k] == self.line[cur[-1]]:
                cur.append(k)
            else:
                cur = [k]
                runs.append(cur)
        run = max(runs, key=len)
        text = "".join(self.vt[k] for k in run)
        if len(text) < 4:
            return f
        occ = [set(range(m.start(), m.end())) for m in re.finditer(re.escape(text), self.vt)]
        if len(occ) < 2:
            return f
        if set(run) in self.pick_by_hints(occ, hints, every=True):
            return f              # 지금 자리가 힌트와 모순되지 않으면 옮기지 않는다
        pick = self.pick_by_hints(occ, hints)
        if len(pick) != 1:
            return f
        lo, hi = min(self.line[k] for k in pick[0]) - 12, max(self.line[k] for k in pick[0]) + 3
        keep = [k for k in range(len(self.vt)) if lo <= self.line[k] <= hi]
        sub = _Page([(self.vt[k], self.vb[k]) for k in keep], self.W, self.H, self.ocr)
        back = {id(b): k for k, b in zip(keep, (self.vb[k] for k in keep))}
        again = [{back[id(sub.vb[j])] for j in g} for g in _align(sub, snippet)]
        best = max(again, key=lambda g: len(g & pick[0]), default=set())
        if not best & pick[0]:
            return f
        out, top = best | pick[0], min(self.line[k] for k in best | pick[0])
        for part in {_norm(w) for p in snippet.split(" | ") for w in [p, *p.split()]}:   # 창 밖의 위쪽 제목('고용노동부고시 생식독성 | …'의 '고용노동부고시')은
            if len(part) >= 4 and part not in "".join(self.vt[k] for k in sorted(out)):    # 위에서 가장 가까운 것을 더한다
                above = [set(range(m.start(), m.end())) for m in re.finditer(re.escape(part), self.vt) if self.line[m.end() - 1] <= top]
                out |= max(above, key=min, default=set())
        return out

    def section_at(self) -> list:
        """줄마다 MSDS 항 번호 (모르면 None). 항 제목 줄 = 줄 첫머리 'N.' 뒤에 한글 제목(1~16항), 위에서 아래로 번호가 커지는 것만 쓴다
        ('1. 가능성이 …' 같은 항 안 목록 번호를 거른다). 첫 제목보다 위 줄은 앞 쪽에서 이어진 항이라 -(첫 제목 번호)로 둔다."""
        if not hasattr(self, "_sec"):
            text, heads = self.line_text(), []
            for ln in sorted(text):
                m = re.match(r"(\d{1,2})\.(?!\d)(.*)", text[ln])
                if m and 1 <= int(m.group(1)) <= 16 and len(re.findall(r"[가-힣]", m.group(2))) >= 2 \
                        and (not heads or int(m.group(1)) > heads[-1][1]):
                    heads.append((ln, int(m.group(1))))
            sec, h = [], 0
            for ln in range(max(self.line, default=-1) + 1):
                while h < len(heads) and heads[h][0] <= ln:
                    h += 1
                sec.append(heads[h - 1][1] if h else (-heads[0][1] if heads else None))
            self._sec = sec
        return self._sec

    def in_section(self, ks: set, n: int) -> bool:
        """글자들이 n항 안에 있는가 (쪽 첫 제목보다 위는 그보다 앞 항으로 본다. 항 제목이 없는 쪽은 앞 쪽에서 이어진 항이라 모른다 → 막지 않는다)."""
        sec = self.section_at()
        vals = {sec[self.line[k]] for k in ks}
        return all(v is None or v == n or (v < 0 and n < -v) for v in vals)

    def grams(self, o: int) -> dict:
        """세 글자 덩어리 → 자리 목록 (조각과 같은 덩어리를 빨리 찾으려고)."""
        if self._grams[o] is None:
            t, g = self.orders[o][0], {}
            for i in range(len(t) - 2):
                g.setdefault(t[i:i + 3], []).append(i)
            self._grams[o] = g
        return self._grams[o]

    def alone(self, k: int, n: int) -> bool:
        """사진 순서 k부터 n글자가 따로 떨어진 낱말인가 (같은 줄 양옆 글자와 글자 높이 1/4 넘게 떨어짐). '화학물질' 속 '물'을 걸러 낸다."""
        def apart(a, b):
            return self.line[a] != self.line[b] or self.vb[b][0] - self.vb[a][2] > 0.25 * self.lh(b)
        return (k == 0 or apart(k - 1, k)) and (k + n >= len(self.vb) or apart(k + n - 1, k + n))

    def rects(self, ks) -> list:
        """사진 순서 번호들 → 줄마다 이은 상자(비율). 같은 줄에서 글자 1.5칸 안으로 떨어진 상자는 잇는다(사이의 ';'·'-'·공백까지 덮게)."""
        out = []
        for k in sorted(ks):
            r = pymupdf.Rect(self.vb[k])
            if out and out[-1][0] == self.line[k] and r.x0 - out[-1][1].x1 < 1.5 * r.height:
                out[-1][1] |= r
            else:
                out.append([self.line[k], r])
        return [[round(r.x0 / self.W, 4), round(r.y0 / self.H, 4), round(r.width / self.W, 4), round(r.height / self.H, 4)] for _, r in out]


def _align(pg: _Page, snippet: str) -> list[set]:
    """원문 조각이 쪽의 어디인지: 자리 후보마다 칠할 글자(사진 순서 번호)의 집합. 후보가 둘 이상이면 어느 것인지 모르는 것(같은 줄이 여러 곳).

    문서 모양에 기대지 않는 한 가지 원리로 찾는다: 조각의 글자 순서는 문서를 읽는 순서와 같다.
    1) 조각 전체가 그대로 있는 자리 (저장 순서·사진 순서 어느 쪽이든)
    2) 없으면 정렬(alignment): 조각과 쪽에 함께 있는 덩어리(한 줄 안, 3글자 이상)와 따로 떨어진 한두 글자 낱말을 모아,
       조각 순서와 읽는 순서를 함께 지키며 맞는 글자가 가장 많은 사슬을 고른다. 줄이 멀어질수록 깎는다(다음 줄까지는 그대로).
       모델이 칸을 이어 붙이거나(표 머리 + 아래 줄, 멀리 위 소제목 + 문장), 줄여 쓰거나('...'), 조각이 다음 쪽으로 이어져도
       맞는 부분만 순서대로 칠하고, 같은 글자가 다른 행에 있어도 순서가 맞지 않으면 집지 않는다
    3) 사슬 줄 범위 안에서 아직 못 칠한 3글자 이상 덩어리를 채운다(칸 안에서 두 줄로 접혀 읽는 순서가 섞인 성분명 등)
    4) 칠한 글자 바로 옆(같은 줄)의 조각 글자를 잇는다('○'·'-'·'='·'1' 같은 짧은 부호)"""
    P = _norm(snippet)
    if len(P) < 2:
        return []
    for t, vi in pg.orders[::-1]:       # 사진 순서 먼저: 저장 순서는 떨어진 줄을 이어 붙이기도 한다(OCR '해당없음(302) 302 제목 해당없음(304)')
        whole = list({frozenset(vi[m.start():m.end()]) for m in re.finditer(re.escape(P), t)})
        if whole:
            return [set(k) for k in whole]

    blocks = {}                                   # (조각 자리, 사진 순서 번호들) → (글자 수, 양 끝 불일치 수)
    for o, (t, vi) in list(enumerate(pg.orders))[1:]:   # 덩어리는 사진 순서로만: 한 줄 안은 왼쪽→오른쪽이 맞는 순서다
        g = pg.grams(o)                                  # (저장 순서는 같은 줄의 떨어진 마침표 셋을 '...'로 잇기도 한다)
        for i in range(len(P) - 2):
            for v in g.get(P[i:i + 3], ()):
                if not pg.line[vi[v]] == pg.line[vi[v + 1]] == pg.line[vi[v + 2]]:
                    continue                      # 덩어리는 한 줄 안에서만 (저장 순서에서 '것을|근거로'처럼 줄을 넘는 세 글자)
                if i and v and P[i - 1] == t[v - 1] and pg.line[vi[v - 1]] == pg.line[vi[v]]:
                    continue                      # 왼쪽으로 더 이어지면 더 긴 덩어리의 일부
                n, sub = 3, 0
                same = lambda q: v + q < len(t) and pg.line[vi[v + q]] == pg.line[vi[v]]
                while i + n < len(P) and same(n):
                    if P[i + n] == t[v + n]:
                        n += 1
                    elif pg.ocr and not sub and i + n + 2 < len(P) and same(n + 2) and P[i + n + 1:i + n + 3] == t[v + n + 1:v + n + 3]:
                        n, sub = n + 1, 1         # OCR 쪽만: 한 글자 오독('끓는점'→'끊는점')은 뒤 두 글자가 다시 맞으면 한 번 이어 간다
                        #                           (PDF 글자층은 글자가 정확해서 허용하면 'LOAEL=50'과 'NOAEL=20'처럼 다른 문장이 맞아 버린다)
                    else:
                        break
                # 불일치: 덩어리 끝에서 조각도 쪽(같은 줄)도 글자가 이어지는데 서로 다름 (',체중을' ↔ ',체중과', 'loael' ↔ 'noael')
                mm = sub + (i > 0 and v > 0 and pg.line[vi[v - 1]] == pg.line[vi[v]]) + (i + n < len(P) and same(n))
                blocks[(i, tuple(vi[v:v + n]))] = (n, mm)
    if not blocks:
        return []
    near = {pg.line[k] for (_, ks) in blocks for k in ks}
    pos, toks = 0, []
    for tok in re.findall(r"[^\s|]+", snippet or ""):
        w = _norm(tok)
        pos = P.find(w, pos) if w else pos
        if w and pos >= 0:
            toks.append((pos, w))
        pos = max(pos, 0) + len(w)
    # 따로 떨어진 한두 글자 낱말 (NFPA '2', 성분 '물'): 긴 덩어리 근처(3줄 안)만.
    # 조각에서 붙어 있는 짧은 낱말 둘은 이어서도 찾는다 (조각 '- 3'을 쪽은 '-3'으로 붙여 적음. OCR은 띄어쓰기를 자주 뺀다)
    short = [t for t in toks if len(t[1]) <= 2]
    short += [(p, w + w2) for (p, w), (p2, w2) in zip(toks, toks[1:]) if p + len(w) == p2 and len(w + w2) <= 3]
    for pos, w in short:
        for m in re.finditer(re.escape(w), pg.vt):
            k = m.start()
            if pg.alone(k, len(w)) and any(pg.line[k] + d in near for d in range(-3, 4)):
                blocks[(pos, tuple(range(k, k + len(w))))] = (len(w), 0)

    # 모델이 떨어진 자리를 이었다고 적은 곳(' / ', '...', '…'): 그 사이는 위아래 어디로든 잇는다(가까운 곳 우선)
    jumps, pos = set(), 0
    for piece in re.split(r"\s+/\s+|\s*(?:…|\.\.\.)\s*", snippet or "")[:-1]:
        pos += len(_norm(piece))
        jumps.add(pos)
    # 조각의 칸('|'·줄바꿈·' / '·'...'로 나뉜 부분): 한 칸 전체가 그대로 맞는 덩어리는 반만큼 더 쳐 준다(칸 일부만 비슷한 다른 줄보다 앞서게)
    cells, pos = [], 0
    for piece in re.split(r"\s*\|\s*|\n|\s+/\s+|\s*(?:…|\.\.\.)\s*", snippet or ""):
        n = len(_norm(piece))
        if n:
            pos = P.find(_norm(piece), pos)
            cells.append((pos, pos + n))
            pos += n
    gain = lambda p, n: n + 0.5 * sum(b - a for a, b in cells if p <= a and b <= p + n)
    B = sorted(((i, ks, n, set(ks), mm) for (i, ks), (n, mm) in blocks.items()), key=lambda b: (b[0], b[1][0]))
    score, prev, top = [0.0] * len(B), [-1] * len(B), [0] * len(B)   # top: 사슬의 맨 윗줄
    for j, (pj, kj, nj, sj, mj) in enumerate(B):
        score[j], top[j] = gain(pj, nj) - mj, pg.line[kj[0]]
        for i in range(j):
            pi, ki, ni, si, _ = B[i]
            if pi + ni > pj or si & sj:           # 조각 순서, 같은 글자를 두 번 쓰지 않음
                continue
            gap = pg.line[kj[0]] - pg.line[ki[-1]]
            if any(pi + ni <= q <= pj for q in jumps):
                pen = abs(gap) * 0.05
            elif gap < -2 or gap > 40 or (gap == 0 and kj[0] < ki[-1]) or (pg.line[kj[0]] < top[i] and not (
                    pg.line[kj[0]] == top[i] - 1 and pg.vb[kj[0]][0] > pg.vb[ki[-1]][2] and any(c.isalnum() for c in P[pi:pi + ni]))):
                continue                          # 읽는 순서를 거스름. 위로는 두 줄까지, 그것도 사슬 맨 윗줄 아래로만
                #   (표에서 이름 칸이 두 줄로 접혀 오른쪽 칸이 첫 줄에 있는 경우. 위 항목의 줄은 집지 않는다)
                #   맨 윗줄보다 한 줄 위는 오른쪽 다른 칸일 때만(행 이름이 세로 가운데에 있고 오른쪽 칸 글이 한 줄 위에서 시작하는 표).
                #   부호 한 글자('-')는 행 이름이 아니라 아래 줄 첫머리 부호일 수 있어 위로 잇지 않는다('- Air transport' 위 줄)
            else:
                pen = 0.5 * -gap if gap < 0 else max(0, gap - 1) * 0.4
            s = score[i] + gain(pj, nj) - mj - pen - 0.02 * (pj - pi - ni)
            if s > score[j]:
                score[j], prev[j], top[j] = s, i, min(top[i], pg.line[kj[0]])
    best = max(score)
    if max(b[2] for b in B) < 3:            # 한두 글자만 맞으면 어디인지 말할 수 없다
        return []
    found = []
    for j in sorted(range(len(B)), key=lambda j: -score[j]):
        if score[j] < best - 1e-9:
            break
        chain = []
        while j >= 0:
            chain.append(B[j])
            j = prev[j]
        chars = {k for _, ks, *_ in chain for k in ks}
        if all(not (chars & f) for _, f in found):   # 점수가 같은 다른 자리(같은 줄이 여러 곳)
            found.append((chain[::-1], chars))
    if len(found) > 5:
        return []
    return [_fill(pg, P, blocks, [b[:3] for b in chain]) for chain, _ in found]


def _fill(pg: _Page, P: str, blocks: dict, chain: list) -> set:
    """고른 사슬에 3) 못 칠한 덩어리, 4) 바로 옆 짧은 부호를 더한다.
    3)은 읽는 순서를 지킨다: 조각에서 앞뒤로 이미 칠한 글자 사이 줄(앞 글자 줄 2줄 위 ~ 뒤 글자 줄 2줄 아래, 사슬 맨 윗줄 아래)에 있을 때만.
    조각 맨 앞(뒤) 칸이면 첫(끝) 칠한 줄 바로 위(아래) 2줄 안. 표에서 두 줄로 접힌 칸('(mgO2/g)')을 채우고, 다른 항목 줄은 집지 않는다."""
    pmap = {p + d: k for p, ks, n in chain for d, k in enumerate(ks[:n])}   # 조각 자리 → 사진 순서 번호
    used, top = set(pmap.values()), min(pg.line[k] for k in pmap.values())
    for (p, ks), (n, mm) in sorted(blocks.items(), key=lambda b: (-b[1][0], b[1][1])):
        if n < 3 or any(p + d in pmap for d in range(n)) or any(k in used for k in ks):
            continue
        before = [pg.line[pmap[q]] for q in pmap if q < p]
        after = [pg.line[pmap[q]] for q in pmap if q >= p + n]
        a, b = pg.line[ks[0]], pg.line[ks[-1]]
        lo = max(before[-1] - 2, top) if before else (after[0] - 2 if after else a)
        hi = (after[0] + 2) if after else (before[-1] + 2 if before else b)
        if not before:
            hi = min(hi, after[0])
        if (not before and max(ks) > min(pmap[q] for q in pmap if q >= p + n)) or \
                (not after and min(ks) < max(pmap[q] for q in pmap if q < p)):
            continue              # 조각 맨 앞(뒤) 칸은 읽는 순서로 첫(끝) 칠한 글자보다 앞(뒤)에 있어야 한다
        if lo <= a and b <= hi:
            pmap.update({p + d: k for d, k in enumerate(ks)})
            used.update(ks)
            pmap = dict(sorted(pmap.items()))
    changed = True
    while changed:
        changed = False
        for p, k in list(pmap.items()):
            for dp in (-1, 1):
                q, kk = p + dp, k + dp
                if 0 <= q < len(P) and q not in pmap and 0 <= kk < len(pg.vt) and kk not in used and pg.vt[kk] == P[q] \
                        and pg.line[kk] == pg.line[k] and abs(pg.vb[kk][0] - pg.vb[k][0]) < 3 * pg.lh(k):
                    pmap[q] = kk
                    used.add(kk)
                    changed = True
    return used


def _value_chars(pg: _Page, value: str, area: set, label: str = "") -> set:
    """값 상자: 값 글자(원문 그대로가 아니면 값의 낱말)가 노란 상자 안에 있는 자리만. 원문에 없는 정규화 값(비해당, 코드)은 그리지 않는다.
    한두 글자 값('0', '1')은 다른 낱말 속 글자가 아닐 때만(앞이 ':'·'='면 괜찮다).
    상자 안에 여러 번 있으면 같은 줄 바로 앞(24글자 안)에 칸 이름의 낱말('보건', 'TWA', '해양오염물질(해당/비해당) :')이 있는 자리만."""
    units = [value] if any(_norm(value) in t for t, _ in pg.orders) else re.split(r"\s+", value or "")
    found = []
    for unit in units:
        u = _norm(unit)
        if len(u) < (1 if unit is value else 2):
            continue
        for t, vi in pg.orders[::-1]:
            for m in re.finditer(re.escape(u), t):
                ks = vi[m.start():m.end()]
                k = min(ks)
                e = k + len(u)            # 바로 뒤 글자: 줄 끝·떨어짐·부호(',.;)')면 낱말 끝
                end_ok = e >= len(pg.vt) or pg.line[e] != pg.line[k] or pg.vt[e] in ",.;)" or pg.vb[e][0] - pg.vb[e - 1][2] > 0.25 * pg.lh(e)
                short_ok = len(u) > 2 or pg.alone(k, len(u)) or (k > 0 and pg.vt[k - 1] in ":=" and end_ok)
                if set(ks) <= area and short_ok and set(ks) not in found:
                    found.append(set(ks))
    if len(found) > 1:
        words = {w for w in map(_norm, re.findall(r"[0-9A-Za-z가-힣]+", label.split("·", 1)[-1])) if len(w) >= 2}   # '14항 운송 · 해양오염물질'의 '운송'은 빼고
        near = [f for f in found if any(w in "".join(pg.vt[j] for j in range(max(0, min(f) - 24), min(f))
                                                    if pg.line[j] == pg.line[min(f)]) for w in words)]
        found = near or found
    return set().union(*found) if found else set()


def _value_elsewhere(pg: _Page, value: str, area: set, section: int | None = None, exact: bool = False) -> tuple[set, str]:
    """값이 원문 조각 상자 안에 없을 때: 쪽에 값 글자가 그대로 있으면 그 자리(조각에 가장 가까운 곳, 조각이 없으면 한 곳일 때만)와 'outside',
    쪽에 없으면 'absent'(정규화 값·코드). 세 글자 미만 값은 어디인지 말할 수 없어, 숫자(순번)면 'short', 글자(코드 '대표')면 'absent'.
    TO21 코드('OSH')·상태어('비해당', '해당없음')는 원문 글자가 아니라 찾지 않는다('OSHA'·다른 항의 '비해당'을 집지 않게).
    찾을 때는 낱말 경계를 지키고('mg/kg/day'의 day는 아님) 그 칸의 항 안에서만 찾는다."""
    u = _norm(value)
    if len(u) < 3:
        return set(), "short" if not u or u.isdigit() else "absent"
    if "_" in value or u in _status_words():
        return set(), "absent"              # 밑줄 있는 TO21 코드·상태어 ('ACGIH', 'ECHA', 'NITE'처럼 원문에 그대로 쓰는 이름은 찾는다)
    w = lambda c: c.isascii() and c.isalnum()
    start = lambda t, i: i == 0 or not (w(t[i - 1]) and w(t[i]) or t[i - 1] in "/-" and i > 1 and w(t[i - 2]) and w(t[i]))   # 영문·숫자가 이어지거나
    end = lambda t, i: i == len(t) or not (w(t[i - 1]) and w(t[i]) or t[i] in "/-" and i + 1 < len(t) and w(t[i - 1]) and w(t[i + 1]))   # 영문·숫자 사이 '/'·'-'로 이어지면 같은 낱말
    occ = list({frozenset(vi[m.start():m.end()]) for t, vi in pg.orders[::-1] for m in re.finditer(re.escape(u), t)
                if start(t, m.start()) and end(t, m.end())})
    bare = re.sub(r"[\W_]", "", u)
    if not occ and not exact and len(bare) >= 3 and len(bare) <= 60:   # 띄어쓰기·부호·OCR 차이: 글자 사이 부호를 무시하고 다시 찾는다
        pat = r"[\W_]*".join(map(re.escape, bare))
        t = pg.vt
        occ = list({frozenset(range(m.start(), m.end())) for m in re.finditer(pat, t)
                    if start(t, m.start()) and end(t, m.end())})
    if not occ and not exact and len(u) >= 15:          # 긴 서술 값: 줄바꿈·표 칸으로 끊겨도 원문 조각처럼 정렬해서 찾는다
        occ = [frozenset(f) for f in _align(pg, value)]
    if section:
        occ = [f for f in occ if pg.in_section(f, section)]
    if not occ:
        return set(), "absent"
    if area:
        top = min(pg.line[k] for k in area)
        return set(min(occ, key=lambda f: abs(min(pg.line[k] for k in f) - top))), "outside"
    return (set(occ[0]), "outside") if len(occ) == 1 else (set(), "absent")


class Locator:
    """고른 칸이 쪽 사진의 어디인지 찾는다. 원본 PDF 글자층(깨진 쪽은 C의 OCR 줄 상자)에서 원문 조각(_align)과 값을 찾아
    사진 크기에 대한 비율(0~1) 상자로 돌려준다. 못 찾으면 빈 목록."""

    def __init__(self, doc_id: str):
        self.doc, self.ok, self.ocr, self.cache = None, set(), {}, {}
        meta_path = paths.page_meta(doc_id)
        if not meta_path.exists():        # preprocess.py의 meta.json이 없으면(version2만 복사했을 때 등) 상자 없이 연다
            print(f"위치 상자 없이 엽니다: {meta_path} 없음")
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pdf = paths.RAW / meta["source_file"]
        self.doc = pymupdf.open(pdf) if pdf.exists() else None
        self.ok = {p["page"] for p in meta["pages"] if p["state"] == "정상"} if self.doc else set()
        # 글자층이 깨진 쪽: C의 OCR 결과(preprocess.ocr, scripts/ocr_pages.py가 만든 data/pages/<문서>/p001.ocr.json)의 줄 상자
        for p in meta["pages"] if self.doc else []:
            if p["page"] not in self.ok and ocr_json(doc_id, p["page"]).exists():
                self.ocr[p["page"]] = ocr_json(doc_id, p["page"])

    def page(self, no: int) -> _Page:
        if no not in self.cache:
            out, raw = [], {}               # raw: 글자 상자 → 원문 글자 (찾기용 글자는 소문자·NFKC로 바꿔 둔다)
            if no in self.ok:
                page, seen = self.doc[no - 1], set()
                for b in page.get_text("rawdict")["blocks"]:
                    for line in b.get("lines", []):
                        for span in line["spans"]:
                            for c in span["chars"]:
                                r = tuple(pymupdf.Rect(c["bbox"]) * page.rotation_matrix)   # 글자 좌표는 회전 전 기준, 사진은 회전 후
                                k = (c["c"], round((r[0] + r[2]) / 3), round((r[1] + r[3]) / 3))   # 가운데 1.5pt 안의 같은 글자
                                if k in seen:     # 굵게 보이려고 같은 글자를 조금씩 옮겨 여러 번 찍은 PDF('최최최최최종종종…')
                                    continue
                                seen.add(k)
                                out += [(ch, r) for ch in _norm(c["c"])]
                                raw[id(r)] = c["c"]
                W, H = page.rect.width, page.rect.height
            else:                 # OCR 줄: 줄 상자를 글자 폭 비율(한글 1, 영문·숫자·부호·띄어쓰기 0.55)로 나눠 글자 상자로 쓴다
                o, seen = json.loads(self.ocr[no].read_text(encoding="utf-8")), set()   # (ponytail: 글꼴마다 폭이 달라 한두 글자 어긋날 수 있음)
                for e in o["items"]:
                    text, (x0, y0, x1, y1) = e["text"], e["box"]
                    key = (_norm(text), round(x0 / 10), round(y0 / 10))
                    if not key[0] or key in seen:   # 같은 줄이 두 번 든 OCR 결과
                        continue
                    seen.add(key)
                    w = [1.0 if ord(c) >= 0x2E80 else 0.55 for c in text]
                    x, step = x0, (x1 - x0) / sum(w)
                    for c, wc in zip(text, w):
                        box = (x, y0, x + wc * step, y1)
                        out += [(ch, box) for ch in _norm(c)]
                        raw[id(box)] = c
                        x += wc * step
                r = self.doc[no - 1].rect            # OCR 좌표는 o["dpi"]로 그린 쪽 이미지 픽셀
                W, H = r.width * o["dpi"] / 72, r.height * o["dpi"] / 72
            self.cache[no] = _Page(out, W, H, no not in self.ok)
            self.cache[no].raw = raw
        return self.cache[no]

    def locate(self, no: int, value: str, snippet: str, section: int | None = None, hints: list | None = None, label: str = "",
               light: bool = False) -> dict:
        """같은 조각이 쪽에 여러 곳이면(소항목마다 '- 이소부텐 : 자료없음'이 되풀이되는 표 등)
        1) section(그 칸의 MSDS 항 번호) 안의 자리만, 2) hints(그 칸의 소항목 이름 묶음, _hints)가 바로 앞 구간에 가장 많은 자리만 남긴다.
        그래도 여럿이면 모두 칠하고 몇 곳인지 알린다."""
        if no not in self.ok and no not in self.ocr:
            return {"value": [], "area": [], "many": 0, "nopage": True}
        pg = self.page(no)
        found = []
        for f in _align(pg, snippet):     # 글자층에 같은 글자가 두 벌 든 PDF: 같은 줄에서 겹치는 자리는 하나로
            same = next((g for g in found if pg.overlaps(f, g)), None)
            same.update(f) if same is not None else found.append(set(f))
        if len(found) > 1 and section:
            found = [f for f in found if pg.in_section(f, section)] or found
        picked = None                             # 같은 조각 여러 곳 중 이름으로 골랐으면 (후보 수, 고른 자리 위에 우리 이름이 있었는지)
        if len(found) > 1 and hints:
            n, found = len(found), pg.pick_by_hints(found, hints)
            if len(found) == 1:
                picked = (n, pg.hint_hit(found[0], hints))
        elif len(found) == 1 and hints:           # 자리가 하나로 정해져도, 그 안의 가장 긴 줄 조각이 쪽에 여러 번 나오면 소항목 이름으로 다시 고른다
            found = [pg.reanchor(found[0], hints, snippet)]  # ('[아이소뷰틸 아세테이트] : 해당없음'이 발암성·생식세포·생식독성 아래 되풀이)
        area = set().union(*found) if found else set()
        val, where = _value_chars(pg, value, area, label), "in"
        if light:                                 # 칠한 글자만 필요할 때(_unused): 앞뒤 쪽 찾기는 건너뛴다
            return {"chars": area | val}
        if not val:
            val, where = _value_elsewhere(pg, value, area, section)
        # 이 쪽에 없으면(또는 부호를 무시해야만 비슷한 줄이 맞으면) 앞뒤 쪽에서 글자 그대로 찾는다
        # (모델이 쪽을 하나만 적었는데 값은 다음 쪽 첫머리에 있는 경우. '· 용기등급 : 해당없음' ↔ 이 쪽 '라. 용기등급 : 해당없음')
        near = lambda exact: [n for n in (no - 1, no + 1) if (n in self.ok or n in self.ocr)
                              and _value_elsewhere(self.page(n), value, set(), section, exact)[1] == "outside"]
        other = near(False) if where == "absent" and len(_norm(value)) >= 3 else []
        similar = False
        if where == "outside" and _value_elsewhere(pg, value, area, section, True)[1] != "outside" and (other := near(True)):
            val, where, similar = set(), "absent", True
        # 원문 조각의 칸 중 이 쪽에 없고 앞뒤 쪽에 있는 것 (조각이 쪽을 넘어감: '- 해상운송(IMDG)'은 앞 쪽 끝)
        split = [(c.strip(), n) for c in re.split(r"\s*\|\s*", snippet or "")      # (표 칸 안에서 줄이 바뀐 글은 정렬로 이 쪽에서 찾히면 이 쪽 것)
                 if len(_norm(c)) >= 4 and not any(_norm(c) in t for t, _ in pg.orders) and not _align(pg, c)
                 for n in [next((n for n in (no - 1, no + 1) if (n in self.ok or n in self.ocr) and _norm(c) in self.page(n).vt), None)] if n]
        return {"value": pg.rects(val), "area": pg.rects(area), "many": len(found) if len(found) > 1 else 0, "value_at": where,
                "picked": picked, "other_pages": other, "split": split, "similar": similar, "chars": area | val, "area_chars": area}


@lru_cache(maxsize=1)
def _status_words() -> set[str]:
    """TO21 동의어 사전의 상태 표기(자료없음·해당없음·해당 …)와 해당 여부 값."""
    dic = json.loads(paths.to21_file("dictionary").read_text(encoding="utf-8"))
    return {_norm(w) for code, names in (dic.get("status") or {}).items() for w in [code, *names]} | {"비해당", "미기재", "미규정", "값있음"}


@lru_cache(maxsize=1)
def _enums() -> dict[str, list[str]]:
    """TO21 스키마에서 '목록.칸' 이름 → 정해진 값 목록(enum) ('ecotox.duration_unit': hr, day). 같은 이름이 여럿이면 합친다."""
    out = {}

    def walk(o, key="", parent=""):
        if isinstance(o, dict):
            if isinstance(o.get("enum"), list):
                k = f"{parent}.{key}"
                out.setdefault(k, []).extend(x for x in o["enum"] if isinstance(x, str) and x not in out.get(k, []))
            for k, v in o.items():
                walk(v, *((key, parent) if k in ("anyOf", "items", "properties", "enum") else (k, key)))
        elif isinstance(o, list):
            for x in o:
                walk(x, key, parent)
    walk(json.loads(paths.to21_file("schema").read_text(encoding="utf-8")))
    return out


STATUS_TEXT = {"값있음": "원문에 값이 적혀 있음", "자료없음": "원문이 '자료 없음' 뜻(자료없음, 정보 없음 등)", "해당없음": "원문이 '해당 없음' 뜻(해당없음, 해당되는 분류 없음 등)",
               "미기재": "원문 칸이 비었거나 '-'", "판독불가": "원문을 읽을 수 없음", "마스킹": "원문 값이 가려짐"}   # TO21 상태 구분 (C7·R15)


def _out_seqs(doc_id: str, t: str = "claude") -> dict[str, set]:
    """이 줄 모델(t)의 실버에서 검수 범위 밖 항 항목의 순번: 목록 경로(msds[i].extras 등) → 순번들. 범위 안 목록의 건너뛴 번호가 이 자리인지 본다."""
    return _out_seqs_at(doc_id, t, _stamp(t, doc_id))


@lru_cache(maxsize=16)
def _out_seqs_at(doc_id: str, t: str, stamp: int) -> dict[str, set]:
    out = {}
    for p, (_, kp, v) in _silver(t, doc_id, stamp).items():
        if p.endswith(".seq") and isinstance(v, int) and not in_scope(kp):
            out.setdefault(re.sub(r"\[k=[^\]]*\]$", "", p[:-4]), set()).add(v)
    return out


def _explain(r: dict, rows: list[dict], pages: int = 0, doc: str = "", drop: dict | None = None) -> str:
    """값이 원문 글자가 아닐 때 화면에 함께 보여 줄 풀이: 성분 번호 → 성분명·CAS, 순번(목록 순서 자동 확인), 쪽·항 번호,
    TO21 코드 → 이름·원문 표기 예. pages: PDF 전체 쪽수(관리정보의 시작·끝 쪽 확인용). doc: 문서 번호(순번이 건너뛴 자리가 범위 밖 항인지 실버에서 본다).
    drop: 골드에서 빠지는 항목(review_cards.dropped). 없으면 rows로 구한다 (성분·순번 풀이에서 그 항목을 뺀다)."""
    p, v = r["경로"], _val(r)
    if not v:
        return ""
    if p.endswith(".comp_ref") or p.endswith(".parent_seq"):
        if v == "MIX":
            return "제품 전체(MIX)"
        pre = re.match(r"msds\[\d+\]\.", p).group(0)
        drop = dropped(rows, default_model(doc)) if drop is None else drop
        seq = next((x["경로"][:-4] for x in rows if x["경로"].startswith(pre + "components[") and x["경로"].endswith("].seq")
                    and _val(x) == v and not gone_by(x["경로"], drop)), None)   # 성분표의 지금 값으로, 골드에서 빠지는 성분은 빼고 (카드의 성분명 표와 같게)
        name = next((_val(x) for x in rows if seq and x["경로"] == seq + ".name"), "")
        cas = (re.search(r"\[k=([^\]]*)\]$", seq) or [None, ""])[1] if seq else ""
        out = f"{v}번 성분" + (f": {name}" if name else "") + (f" (CAS {cas})" if cas and cas != name else "")
        return out + ("의 하위 성분" if p.endswith(".parent_seq") else "")
    if p.endswith(".seq"):                # 순번은 사진으로 세기 어렵다: 같은 목록의 순번이 1부터 문서 순서대로 이어지는지 직접 확인해 보여 준다
        item = p[:-4]
        lst = re.sub(r"\[k=[^\]]*\]$", "", item)
        what = "성분표" if ".components[" in p else "이 목록"
        drop = dropped(rows, default_model(doc)) if drop is None else drop
        if gone_by(p, drop):
            return f"{what} 순번 {v} (이 항목은 골드에서 빠져 순서는 보지 않음: 자동 확인)"
        rank = silver_rank(doc)               # 목록 순서: 실버 항목은 실버 순서 (엑셀에서 줄을 정렬해도 같게)
        mine = lambda x: x.get("검수 결과") == "누락 추가" and not x.get("일치")
        cand = [x for x in rows if x["경로"].startswith(lst + "[k=") and x["경로"].endswith(".seq") and not gone_by(x["경로"], drop)
                and re.fullmatch(re.escape(lst) + r"\[k=[^\]]*\]", x["경로"][:-4])]   # 형제: 골드에 남는 항목만 (골드와 같은 기준)
        sib = sorted((x for x in cand if not mine(x)), key=lambda x: rank.get(x["경로"], len(rank)))
        num = lambda x: int(_val(x)) if _val(x).isdigit() else None
        for x in sorted((x for x in cand if mine(x)), key=lambda x: (num(x) is None, num(x) or 0)):   # 사람이 넣은 항목은 지금 순번 값 자리에
            sib.insert(next((i for i, y in enumerate(sib) if num(x) is not None and num(y) is not None and num(y) > num(x)), len(sib)), x)
        sibs = [x["경로"][:-4] for x in sib]
        seqs = [_val(x) for x in sib]         # 형제도 지금 값 (고친 순번·사람이 넣은 항목의 순번 포함)
        if item not in sibs or not v.isdigit():
            return f"{what} {v}번째"
        pos, run = sibs.index(item) + 1, seqs == [str(n) for n in range(1, len(seqs) + 1)]
        if run and v == str(pos):
            return f"{what} {len(sibs)}개 중 {pos}번째 (목록 순서대로 순번이 1부터 빠짐없이 이어짐: 자동 확인)"
        base = lambda x: re.search(r"\[k=([^\]]*)\]$", x).group(1).split("#")[0]     # 같은 특성 값이 여럿일 때의 순번(physchem: 'pH' 1, 2)
        grp = [k for k in sibs if base(k) == base(item)]
        gseq = [seqs[sibs.index(k)] for k in grp]
        phys = lst.endswith(".physchem")      # 항목마다 1부터 다시 세는 목록은 물리화학적 특성뿐 (다른 목록은 목록 순서대로 1..n)
        if phys and len(grp) > 1 and gseq == [str(n) for n in range(1, len(grp) + 1)] and v == str(grp.index(item) + 1):
            code = base(item).split("|")[-1]
            return f"같은 항목({(_code_names().get(code) or [code])[0]}) 값 {len(grp)}개 중 {v}번째 (같은 항목 안에서 1부터 이어짐: 자동 확인)"
        bys = {}
        for k, x in zip(sibs, seqs):
            bys.setdefault(base(k), []).append(x)
        restart = phys and all(g == [str(n) for n in range(1, len(g) + 1)] for g in bys.values())   # 모든 항목이 각각 1부터 센다
        if len(grp) == 1 and v == "1" and restart:   # 값이 하나뿐인 특성은 1이면 맞다 (성분표 [1, 1, 1]·[1, 1, 2]는 틀림)
            code = base(item).split("|")[-1]
            return f"같은 항목({(_code_names().get(code) or [code])[0]}) 값 1개 중 1번째 (자동 확인)"
        nums = [int(x) for x in seqs if x.isdigit()]
        if len(nums) == len(seqs) and all(a < b for a, b in zip(nums, nums[1:])):
            gone = [n for n in range(1, nums[-1]) if n not in nums and n not in _out_seqs(doc, "claude" if r["Claude 값"] != "" else "gpt").get(lst, ())]   # 범위 밖 항 항목도 아닌 빈 번호
            if gone:
                return (f"{what} {len(sibs)}개 중 {pos}번째 — 순번 {gone[0]}{'가' if _batchim(str(gone[0])) is False else '이'} 빠졌어요"
                        f"(같은 목록 순번: {', '.join(seqs[:12])}): 확인 필요")
            return (f"{what} {len(sibs)}개 중 {pos}번째 (순번이 목록 순서대로 커짐: 자동 확인. 건너뛴 번호는 AI가 검수 범위 밖 항에 적은 항목"
                    + (f", 이 줄 앞: {seqs[pos - 2]}" if pos > 1 else "") + ")")
        return f"{what} {len(sibs)}개 중 {pos}번째 — 순번 {v}{'가' if _batchim(v) is False else '이'} 목록 순서와 맞지 않음(같은 목록 순번: {', '.join(seqs[:12])}): 확인 필요"
    if p.endswith(("meta.page_start", "meta.page_end")) and pages:
        return f"{v}쪽 (PDF 전체 {pages}쪽)"
    if ".extras[" in p:
        if p.endswith(".page"):
            return f"{v}쪽"
        if p.endswith(".section_no"):
            return f"{v}항"
        if p.endswith(".reason") and v == "필드없음":
            return "TO21 명세서에 맞는 칸이 없어 미정의 항목(extras)으로 보냄 (R24)"
    if p.endswith("status") and v in STATUS_TEXT:
        return f"{v}: {STATUS_TEXT[v]} (R15)"
    if p.endswith((".after_item", ".suggested_code")) and ".extras[" in p:   # 모델이 정한 위치·제안이라 원문 글자가 아니다
        row = _spec_row(p)
        code = f" ({v} = {_code_names()[v][0]})" if v in _code_names() else ""
        return f"원문 글자가 아니라 AI가 정한 {row[4]}{code}: {row[8]} (R24)" if row else ""
    if conv := _convention(p, v, rows):
        return conv
    allowed = _allowed(p)
    if v in ("true", "false") and (row := _spec_row(p)) and row[5] == "boolean":
        return f"{v} = {row[4]} {'예' if v == 'true' else '아니오'} — 원문 표기를 참·거짓으로 옮김" + (f" (TO21 명세서: {row[8]})" if row[8] else "")
    if v in allowed and v not in _code_names() and len(allowed) <= 12:
        desc = (_spec_row(p) or [None] * 9)[8]   # '공통 / 육상(ADR·국내) / 해상(IMDG) / 항공(IATA) — 구분 없으면 공통'
        return (f"TO21이 이 칸에 정한 값({', '.join(allowed)}) 중 하나 — 원문 표기를 이 값으로 옮김"
                + (f" (TO21 명세서: {desc})" if desc and _norm(desc) != _norm("/".join(allowed)) else ""))
    names = _code_names().get(v)
    if names:
        syn = [n for n in names[1:] if n != names[0]][:4]
        return f"{v} = {names[0]}" + (f" (원문 표기 예: {', '.join(syn)})" if syn else "")
    return ""


def _convention(p: str, v: str, rows: list[dict]) -> str:
    """값 없는 행(자료없음·해당없음·미기재)에 표기 규칙(common.conventions, TO21 정답 예제 모양)으로 채운 지표·기준 종류.
    원문 글자가 아니라서 풀이가 없으면 검수자가 '원문에 없는 값'으로 지우기 쉽다."""
    item, field = p.rsplit(".", 1)
    if field not in ("descriptor", "limit_type"):
        return ""
    st = next((_val(x) for x in rows if x["경로"] == item + ".status"), "")
    q = next((from_cell(_cell_now(x)) for x in rows if x["경로"] == item + ".q"), None)
    st = st or (q.get("status") if isinstance(q, dict) else "")
    rule = {"limit_type": f"국내·ACGIH 노출기준 → TWA, 생물학적 노출기준 → BEI ({'·'.join(f'{a} {b}' for a, b in LIMIT_TYPE.items())})",
            "descriptor": "독성·생태 지표 → 결과기술, 혼합물 급성독성 → ATE, 잔류성 → " + "·".join(ECO_DESCRIPTORS["ECO_PERSIST"])
                          + ", 생물농축성 → " + "·".join(ECO_DESCRIPTORS["ECO_BIOACC"])}[field]
    if st in NO_VALUE and v in {*LIMIT_TYPE.values(), "결과기술", "ATE", *sum(ECO_DESCRIPTORS.values(), [])}:
        return (f"원문 글자가 아니라, 값이 없는 줄(상태 '{st}')에 TO21 표기 규칙으로 넣는 값 ({rule}; TO21 정답 예제와 같은 모양). "
                f"원문이 정말 '{st}' 뜻이면 '맞음'")
    return ""


def _allowed(p: str) -> list[str]:
    """칸 경로 → TO21 스키마가 그 칸에 정한 값 목록(enum). 없으면 []."""
    return _enums().get(".".join(re.sub(r"\[[^\]]*\]", "", p).split(".")[-2:]), [])


def _spec_note(p: str) -> str:
    """칸의 TO21 명세서 기준(1_항목정의의 설명·규칙·예시·비고). 검수자가 정규화한 값이 맞는지 볼 잣대."""
    row = _spec_row(p)
    if not row:
        return ""
    rules = "; ".join(f"{c} {_rule_names().get(c, '')}" + (f": {_rule_texts()[c]}" if c in _rule_texts() else "")
                      for c in re.findall(r"[RV]\d{2}", str(row[9] or "")))
    note = str(row[11]) if len(row) > 11 and row[11] and not str(row[11]).startswith("※") else ""   # '※ …필수로 평가'는 채점 안내라 뺀다
    desc = re.sub(r"\bC(\d)\b", lambda m: f"코드표 C{m.group(1)}({_code_tables().get('C' + m.group(1), '')})", str(row[8] or ""))   # 'C3' → 코드표 C3(서술 항목 코드)
    parts = [desc, f"규칙 {rules}" if rules else "", f"명세서 예시(다른 문서의 예): {row[10]}" if row[10] not in (None, "") else "", note]
    return " · ".join(x for x in parts if x)


def _spec_row(p: str) -> tuple | None:
    """칸 경로 → TO21 명세서 1_항목정의 줄 (4: 한글 이름, 5: 형식, 8: 설명)."""
    return next((r for r in _spec_rows() if r[3] == generic(p)), None)


@lru_cache(maxsize=1)
def _code_tables() -> dict[str, str]:
    """TO21 명세서 코드표 시트 제목: 'C3' → '서술 항목 코드' ('5-3. 서술 항목 코드(C3)')."""
    wb = openpyxl.load_workbook(paths.to21_file("spec"), read_only=True, data_only=True)
    out = {}
    for name in (n for n in wb.sheetnames if n.startswith("5-")):
        title = str(next(wb[name].iter_rows(values_only=True))[0] or "")
        if m := re.match(r"5-\d+\.\s*(.*?)\((C\d)\)", title):
            out[m.group(2)] = m.group(1).strip()
    wb.close()
    return out


@lru_cache(maxsize=1)
def _rule_texts() -> dict[str, str]:
    """TO21 명세서 규칙 내용: 'R09' → "'UN', 'UN No.' 제거, 4자리 숫자.", 'V18' → 'regulated=true면 …'."""
    wb = openpyxl.load_workbook(paths.to21_file("spec"), read_only=True, data_only=True)
    out = {}
    for sh, col in (("3_정규화규칙", 2), ("4_검증규칙", 4)):
        for r in wb[sh].iter_rows(values_only=True):
            if r and re.fullmatch(r"[RV]\d{2}", str(r[0] or "")) and len(r) > col and r[col]:
                out[str(r[0])] = str(r[col])
    wb.close()
    return out


@lru_cache(maxsize=1)
def _rule_names() -> dict[str, str]:
    """TO21 명세서 3_정규화규칙·4_검증규칙: 'R04' → '수치 분해(Q)', 'V18' → '운송 정보 쌍'."""
    wb = openpyxl.load_workbook(paths.to21_file("spec"), read_only=True, data_only=True)
    out = {str(r[0]): str(r[1]) for sh in ("3_정규화규칙", "4_검증규칙") for r in wb[sh].iter_rows(values_only=True)
           if r and re.fullmatch(r"[RV]\d{2}", str(r[0] or "")) and r[1]}
    wb.close()
    return out


def _is_code(x: str) -> bool:
    """TO21 코드 모양: 대문자·숫자·밑줄('OSH_MANAGED', 'TX_INHAL', 'OSH', 'ACGIH', 'GHS02')."""
    return bool(re.fullmatch(r"[A-Z][A-Z0-9]*(_[A-Z0-9]+)*", x)) and len(x) >= 2


_NOT_NAME = re.compile(r"^(필수|중요|일반)$|^(숫자|텍스트)(/(숫자|텍스트))*$|개정| — |원문은")   # 코드표 줄의 중요도·값 형식('숫자')·비고('2025 개정 분류', '…(원문은 raw에 저장)') 칸은 이름이 아니다


@lru_cache(maxsize=1)
def _code_names() -> dict[str, list[str]]:
    """TO21 코드 → 한글 이름: 명세서 코드표(5-x 시트)의 코드 줄에 적힌 이름과 동의어 사전(물성·규제·서술 항목)."""
    out = {}
    wb = openpyxl.load_workbook(paths.to21_file("spec"), read_only=True, data_only=True)
    for name in (n for n in wb.sheetnames if n.startswith("5-")):
        for r in wb[name].iter_rows(values_only=True):
            cells = [str(c).strip() for c in r if c not in (None, "")]
            at = [i for i, c in enumerate(cells) if _is_code(c)]
            names = [x for x in cells[at[-1] + 1:] if not x.isdigit() and not _NOT_NAME.search(x)] if at else []
            if names:             # 한 줄에 코드가 여럿이면 마지막이 그 줄의 코드('OSH | OSH_MANAGED | 관리대상유해물질'), 앞은 상위 코드·대분류('건강')라 이름은 코드 오른쪽 칸만
                out.setdefault(cells[at[-1]], []).extend(names)   # 이름 칸이 없는 줄('NIOSH')은 코드로 넣지 않는다(원문 표기 그대로라 쪽에서 찾는다)
    wb.close()
    dic = json.loads(paths.to21_file("dictionary").read_text(encoding="utf-8"))
    for part in ("physchem", "regulations", "narratives"):
        for code, names in (dic.get(part) or {}).items():
            out.setdefault(code, []).extend(names)
    return out


FIELD_HINTS = (".item_raw", ".title_raw", ".basis_raw", ".key", ".physical_form", ".species")   # 같은 목록 항목끼리 갈라 주는 원문 칸


def _is_head(text: str, key: str) -> bool:
    """줄이 키 제목 줄인가: 앞 번호('가.', '-', '1)')를 떼면 키로 시작하고 뒤에 값이 거의 없다('마. 해양오염물질 : 해당없음'은 값 줄)."""
    head = re.sub(r"^[\W_]*(?:(?:[가-힣]|\d{1,2})[.)])?[\W_]*", "", text)
    return head.startswith(key) and len(head) - len(key) <= 3


def _key_elsewhere(pg: "_Page", area_rects: list, r: dict, rows: list[dict], pages: list = ()) -> tuple[str, int | None]:
    """키 있는 문장 목록 항목('국제해상위험물 (IMDG)': …)인데 노란 자리 위에서 가장 가까운 같은 목록 키 제목이 다른 키('IATA')이고,
    이 문장의 키도 어딘가(pages: 앞뒤 쪽 [(쪽 번호, 쪽)])에 제목 줄로 있으면 (그 다른 키, 이 문장 키 제목이 있는 쪽 — 이 쪽이면 None).
    같은 문장이 운송 방식·소항목마다 되풀이될 때 모델이 다른 묶음의 줄을 근거로 적은 경우를 알린다."""
    m = re.match(r"(.*\.statements)\[k=[^\]]*\]$", r["경로"])
    if not m or not area_rects:
        return "", None
    key = lambda x: (json.loads(x) if str(x).startswith("{") else {}).get("key") or ""
    own = _norm(key(r["Claude 값"] or r["GPT 값"]))
    others = {_norm(key(x["Claude 값"] or x["GPT 값"])) for x in rows if x["경로"].startswith(m.group(1) + "[k=") and x is not r} - {own, ""}
    others = {o for o in others if len(o) >= 3 and o not in own and own not in o}
    at = [n for n, p in [(None, pg), *pages] if any(_is_head(t, own) for t in p.line_text().values())]
    if len(own) < 3 or not others or not at:
        return "", None
    top = min(y for _, y, _, _ in area_rects) * pg.H
    lt = pg.line_text()
    lines = sorted({pg.line[k] for k, b in enumerate(pg.vb) if b[1] < top - 1}, reverse=True)
    for ln in lines:
        if own in lt.get(ln, ""):
            return "", None
        if o := next((o for o in others if _is_head(lt.get(ln, ""), o)), ""):
            return o, at[0]
    return "", None


def _hints(path: str, rows: list[dict]) -> list[tuple[set[str], set[str], int]]:
    """같은 조각이 여러 자리일 때 고르는 이름 묶음 [(우리 이름들, 같은 목록 다른 항목의 이름들, 목록 단계)] (정규화, Locator.locate).
    키 있는 목록이 겹쳐 있으면('companies[k=공급자|…].contacts[k=대표]') 바깥 단계(0)부터 안쪽까지 단계마다 만든다.
    목록 항목 키([k=...])의 자리마다 하나씩: 같은 목록의 다른 줄이 그 자리에 가진 값들이 '이 자리에 올 수 있는 이름'이다.
    값 → 이름: TO21 코드는 코드표·동의어 사전 이름(TX_SKIN → 피부 부식성/자극성 …), CAS 번호는 성분명(components[k=CAS].name),
    그 밖의 글(한글 키 '발암성', 시험 동물 등)은 그대로. 같은 항목의 원문 이름 칸·노출 형태·시험 동물(FIELD_HINTS)도 칸마다 같은 방식으로 한 묶음."""
    m = re.match(r"(msds\[\d+\]\.)(.*\[k=[^\]]*\])", path)   # 가장 안쪽의 키 있는 목록 항목까지 ('…statements[0].text'의 앞)
    if not m:
        return []
    pre, inner = m.group(1), m.group(2)
    return [(own, others, lv) for lv, k in enumerate(re.finditer(r"\[k=[^\]]*\]", inner))
            for own, others in _hints_level(pre, inner[:k.end()], rows)]


def _hints_level(pre: str, item: str, rows: list[dict]) -> list[tuple[set[str], set[str]]]:
    """_hints의 한 단계: item(키 있는 목록 항목 경로)과 같은 목록의 다른 항목들로 만든 이름 묶음."""
    lst = re.sub(r"\[k=[^\]]*\]$", "", item)          # 'cmr', 'narratives[k=S4].statements' …
    value = _val
    comp = {}
    for r in rows:
        mm = re.fullmatch(re.escape(pre) + r"components\[k=([^\]]*)\]\.name", r["경로"])
        if mm:
            comp[mm.group(1)] = value(r)

    def names(x: str) -> set[str]:
        if x in _code_names():
            return {v for n in _code_names()[x] for v in _variants(n)}
        if x in comp:
            return _variants(comp[x]) | {_norm(x)}
        return {_norm(x)} if len(_norm(x)) >= 2 and x != "MIX" and re.search(r"[가-힣A-Za-z]", x) else set()

    keys, items = {}, {}                               # 같은 목록 항목들: 키 → [자리별 값], 원문 이름 칸 값
    for r in rows:
        mm = re.match(re.escape(pre + lst) + r"\[k=([^\]]*)\](.*)$", r["경로"])     # 항목 안 어느 칸이든 (…].statements[0].text 포함)
        if mm:
            keys[mm.group(1)] = mm.group(1).split("#")[0].split("|")
            if mm.group(2) in FIELD_HINTS:
                items.setdefault(mm.group(2), {}).setdefault(mm.group(1), set()).update(_variants(value(r)))
    own_key = re.search(r"\[k=([^\]]*)\]$", item).group(1)
    out = []
    def pair(own: set, others: set, shared_out: bool = True) -> None:
        """키 이름의 공통 조각('급성독성'은 경구·경피·흡입 모두)은 어느 쪽에도 넣지 않는다(shared_out).
        원문 칸 값('분진·미스트')은 다른 성분 항목에도 같은 값이 있을 수 있어 우리 이름에서 빼지 않는다. 다른 이름이 우리 이름의 일부면 다른 이름에서 뺀다."""
        own, others = (own - others if shared_out else own), others - own
        others = {o for o in others if not any(o in w for w in own)}
        if own and others:
            out.append((own, others))

    for j, part in enumerate(keys.get(own_key, [])):
        pair(names(part), set().union(*[names(k[j]) for kk, k in keys.items() if kk != own_key and len(k) > j and k[j] != part]))
    for field in items.values():
        pair(field.get(own_key, set()), set().union(*[v for kk, v in field.items() if kk != own_key]), shared_out=False)
    return out


def _variants(s: str) -> set[str]:
    """이름 → 찾을 조각(정규화): 전체, 괄호 밖, 괄호 안, '·/,'로 나눈 것."""
    out = set()
    for part in [s, re.sub(r"\(.*?\)", "", s), *re.findall(r"\((.*?)\)", s)]:
        out |= {n for q in [part, *re.split(r"[·/,]", part)] if len(n := _norm(q)) >= 2}
    return out


@lru_cache(maxsize=1)
def _shared_variants() -> set[str]:
    """둘 이상의 코드 이름에 들어 있는 조각."""
    seen, shared = {}, set()
    for code, names in _code_names().items():
        for v in {v for s in names for v in _variants(s)}:
            if seen.setdefault(v, code) != code:
                shared.add(v)
    return shared


def _notes(r: dict, got: dict, single: bool, edited: bool) -> list[str]:
    """검수자가 사진만 보고 판단할 수 있게, 상자만으로는 알 수 없는 사정과 무엇을 하면 되는지를 적는다(사진 위 노란 띠)."""
    t = next((t for t in ("Claude", "GPT") if r[f"{t} 값"] != ""), "Claude")
    snippet, name = r["수정 원문 조각"] if edited else r[f"{t} 원문 조각"], r["칸 이름"].split(" (")[0].split(" · ")[-1]
    value = _plain(r["수정값"] if edited else r[f"{t} 값"])
    nm = (_code_names().get(value) or [value])[0]                # 코드는 이름으로 보인다
    shown = nm if len(nm) <= 40 else nm[:38] + "…"             # 긴 서술 값은 카드에 다 있으니 안내에는 앞부분만
    rules = re.findall(r"R\d{2}", r["적용 규칙"] or "")
    out = []
    if got.get("picked"):
        n, hit = got["picked"]
        out.append(f"같은 줄이 이 쪽에 {n}곳 있어, 가장 가까운 성분·소항목 제목 아래 자리를 칠했어요. 카드 제목과 같은 소항목인지 봐 주세요." if hit else
                   f"같은 줄이 이 쪽에 {n}곳 있는데 이 칸의 성분·소항목 제목이 이 쪽에 없어 첫 자리를 칠했어요. 앞 쪽 끝의 제목도 함께 봐 주세요.")
    if got.get("many", 0) > 1:
        out.append(f"같은 줄이 이 쪽에 {got['many']}곳 있어 모두 칠했어요. 카드 제목(소항목)과 맞는 곳을 보고 판단해 주세요.")
    elif snippet and not got.get("area"):
        out.append("이 쪽은 글자를 읽지 못해 자리를 칠하지 못했어요. 사진에서 직접 찾아 주세요." if got.get("nopage") else
                   "근거 줄을 이 쪽에서 찾지 못했어요(쪽 번호가 다르거나 떨어진 줄을 이어 적었을 수 있어요). 사진에서 직접 찾아 주세요.")
    if (ok := got.get("other_key") or ("", None))[0]:
        out.append(f"노란 자리는 이 카드가 아니라 다른 묶음(‘{ok[0]}’) 아래에 있어요. "
                   + (f"{ok[1]}쪽의 이 카드 묶음" if ok[1] else "이 쪽의 이 카드 묶음") + "에도 같은 문장이 있는지 봐 주세요.")
    for c, n in got.get("split", [])[:3]:
        out.append(f"근거 줄 중 ‘{c if len(c) <= 40 else c[:38] + '…'}’은(는) {n}쪽에 있어요(쪽을 넘어감). 그 쪽도 함께 봐 주세요.")
    if got.get("value_at") == "outside":
        out.append(f"‘{name}’ 값 ‘{shown}’은(는) 노란 줄 밖에 있어 그 자리에 색 테두리를 따로 쳤어요. 그 자리가 이 칸의 값이 맞으면 ‘같아요’ 단추를 눌러 주세요.")
    elif got.get("value_at") in ("absent", "short") and single and value and re.search(
            r"(?<![0-9a-z가-힣])" + re.escape(unicodedata.normalize("NFKC", value).lower()) + r"(?![0-9a-z가-힣])",
            unicodedata.normalize("NFKC", snippet or "").lower()):
        out.append(f"‘{name}’ 값 ‘{shown}’은(는) 노란 줄 안에 그대로 있어요(짧아서 따로 칠하지 않았어요).")
    elif got.get("value_at") == "absent" and single and value and not r["경로"].endswith(".seq"):   # 순번은 풀이(자동 확인)로 본다
        if got.get("other_pages"):
            pages = '·'.join(map(str, got['other_pages']))
            out.append(f"‘{name}’ 값 ‘{shown}’은(는) " + (f"이 쪽의 비슷한 줄이 아니라 {pages}쪽에 글자 그대로 있어요"
                       if got.get("similar") else f"이 쪽에는 없고 {pages}쪽에 있어요") + ". 그 쪽에서 확인해 주세요.")
        elif _norm(value) in _status_words() and value not in _allowed(r["경로"]):   # 해양오염물질 '비해당'은 스키마가 정한 값(풀이로 본다)
            out.append(f"‘{name}’ 값 ‘{shown}’은(는) 원문 값이 "
                       + (f"‘{STATUS_TEXT[value]}’" if value in STATUS_TEXT else "어떤 상태인지") + "라는 뜻이에요. 노란 줄이 그런지 봐 주세요.")
        elif value in _code_names() and not r["경로"].endswith((".after_item", ".suggested_code")):   # 위치·제안 코드는 원문 조각과 대조하지 않는다
            b = _batchim(nm)
            out.append(f"‘{name}’ 값은 ‘{nm}’{'(이)에요' if b is None else '이에요' if b else '예요'}. " + _code_in_snippet(value, snippet))
        elif _explain(r, []):              # 풀이(제품 전체 MIX, 스키마가 정한 값, 미정의 항목 사유 등)가 있으면 그것으로 본다
            pass
        elif _normalized(value) or rules:
            out.append(f"‘{name}’ 값 ‘{shown}’은(는) 원문 글자 그대로가 아니라 정해진 규칙으로 바꾼 값이에요. 노란 줄을 바꾸면 이 값이 되는지 봐 주세요.")
        else:
            out.append(f"‘{name}’ 값 ‘{shown}’을(를) 이 쪽에서 그대로 찾지 못했어요(줄이 끊겼을 수도 있어요). 다른 쪽에서 왔거나 AI가 만든 값일 수 있으니 근거를 확인해 주세요.")
    return out


def _code_forms(code: str, snippet: str) -> tuple[str, str, str, bool]:
    """원문 조각 속 코드 표기 → (이 코드의 표기, 같은 갈래(OSH_…) 다른 코드, 그 표기, 이 코드 표기가 그 긴 표기 안에만 있나).
    '특별관리대상물질'만 있는 원문의 '관리대상물질'은 OSH_MANAGED가 아니라 OSH_SPECIAL의 표기다(긴 표기를 지우면 남지 않음)."""
    s = _norm(snippet or "")
    show = lambda w: (m.group(0) if (m := re.search(r"\s*".join(map(re.escape, w)), snippet, re.I)) else w)   # 정규화 글자 → 원문 표기
    forms = lambda n: {v for v in _variants(n) if len(v) >= 3} | {w for w in map(_norm, re.split(r"[\s·/,()]+", n)) if len(w) >= 4}   # 이름 낱말('고용노동부')도
    hit = lambda c, t=s: max((v for n in _code_names().get(c, []) for v in forms(n) if v in t), key=len, default="")
    head = code.split("_")[0]
    others = [(c, v) for c in _code_names() if c != code and c.split("_")[0] == head and not code.startswith(c + "_") if (v := hit(c))]
    w = hit(code)
    if not w:                                     # 세 글자 미만 이름('pH', '냄새')은 낱말로 있을 때만 이 코드 표기 (다른 코드와 견주지 않는다)
        low = unicodedata.normalize("NFKC", snippet or "").lower()
        sw = next((n for n in _code_names().get(code, []) if 0 < len(_norm(n)) < 3 and re.search(   # 글자 사이 띄어 쓴 '냄  새'도
            r"(?<![0-9a-z가-힣])" + r"\s*".join(map(re.escape, _norm(n))) + r"(?![0-9a-z가-힣])", low)), "")
        if sw:
            return show(_norm(sw)), "", "", False
    if w:
        longer = sorted(((c, v) for c, v in others if len(v) > len(w) and w in v), key=lambda x: -len(x[1]))
        rest = s
        for _, v in longer:
            rest = rest.replace(v, "\0")
        if longer and not hit(code, rest):        # 이 코드 표기가 긴 다른 코드 표기 안에서만 나온다
            return "", longer[0][0], show(longer[0][1]), True
        return show(hit(code, rest) or w), "", "", False
    oc, ow = max(others, key=lambda x: len(x[1]), default=("", ""))
    return "", oc, (show(ow) if ow else ""), False


def _code_match(code: str, snippet: str) -> tuple[str, str, str]:
    """카드 칩용 (이 코드 표기, 다른 코드, 그 표기): 다른 코드는 이 코드 표기가 그 긴 표기 안에만 있을 때만(칩 ⚠).
    이 코드 표기를 아예 못 찾았으면 칩은 조용히 두고 사진 위 안내(_code_in_snippet)만 한다."""
    own, oc, ow, inside = _code_forms(code, snippet)
    return (own, oc, ow) if inside or own else ("", "", "")


def _code_in_snippet(code: str, snippet: str) -> str:
    """원문 조각에 이 코드의 사전 표기가 있는지. 원문이 같은 갈래 다른 코드의 표기면 그 코드를 알린다(_code_forms)."""
    own, oc, ow, inside = _code_forms(code, snippet)
    if own:
        return f"노란 줄의 ‘{own}’이(가) 이 코드의 이름이에요."
    if oc and oc.startswith(code + "_"):    # 법령 칸 'INTL'에 원문 'EU 규제'(INTL_EU): 하위 항목이라 맞는 관계
        return f"노란 줄의 ‘{ow}’은(는) {_code_names()[oc][0]}의 표기인데, 이 칸은 그 위 분류라 맞아요."
    if oc:
        return (f"노란 줄의 ‘{ow}’은(는) 다른 항목 ‘{_code_names()[oc][0]}’의 표기예요"
                + ("(이 코드 이름은 그 안의 일부 글자일 뿐이에요)" if inside else "") + ". 어느 쪽이 맞는지 봐 주세요.")
    return "노란 줄에 이 코드의 이름이 그대로 있지는 않아요. 같은 뜻인지 봐 주세요."


def _normalized(v: str) -> bool:
    """TO21 규칙으로 원문을 바꾼 꼴의 값인가: 코드, 상태어, 날짜, 숫자, 참·거짓, 한두 글자 구분값."""
    s = v.strip()
    return (s in _code_names() or "_" in s or _norm(s) in _status_words() or len(_norm(s)) <= 2
            or bool(re.fullmatch(r"\d{4}-\d{2}(-\d{2})?|[-+]?[\d.,]+|true|false|null", s)))


def _plain(v) -> str:
    """검수표 칸 글자 → 찾을 글자. '"54588"'처럼 따옴표로 감싼 글자 값은 따옴표를 뗀다."""
    v = from_cell(str(v)) if v not in (None, "") else ""
    if isinstance(v, dict):               # Q 객체는 원문(raw)으로 찾는다. 문장 목록 항목은 키가 있으면 원문 줄(text '· 용기등급 : 해당없음'),
        if v.get("raw"):                  # 없으면 그 문장(value. 키 없는 항목의 text는 여러 문장을 이은 글일 때가 있다)
            return str(v["raw"])
        return str((v.get("text") if v.get("key") else None) or (v["value"] if isinstance(v.get("value"), str) else "") or v.get("text") or "")
    return "" if isinstance(v, list) else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


@lru_cache(maxsize=None)
def _tip_of(g: str) -> str:
    """일반 경로 → 명세서 설명의 첫 문장 (칩 설명)."""
    row = _spec_row(g)
    return re.split(r"(?<=[.。])\s", (row[8] or "").strip(), maxsplit=1)[0] if row else ""


def _cards(rows: list[dict], pages: int, explain: dict, keys: set | None, drop: dict) -> dict:
    """문장 카드. keys: 이 카드만 다시 만든다(저장 뒤 바뀐 카드. 성분명 표·골드에서 빠지는 항목은 문서 전체에서)."""
    names, comps = _code_names(), comps_from_rows(rows, drop)
    mine = rows if keys is None else [r for r in rows if card_key(r["경로"]) in keys]
    labels = {r["경로"]: r["칸 이름"].split(" · ")[-1].split(" (")[0] for r in mine}
    tips = {r["경로"]: t for r in mine if (t := _tip_of(generic(r["경로"])))}
    out = build_cards(mine, names=names, comps=comps, labels=labels, tips=tips, pages=pages, explain=explain, code_match=_code_match, drop=drop)
    ov = overlaps(rows, _page_count_of, drop) if _LOCATOR else {}      # 겹침은 늘 전체 줄로 (카드 몇 장만 다시 만들어도 같게)
    for k, c in out.items():
        c["overlap"] = ov.get(k, [])
    return out


_LOCATOR = None                       # 글자층 조회용 (make_handler가 정함. 없으면 겹침을 판정하지 않음)


def _page_count_of(no: int, s: str) -> int:
    """쪽 글자층(공백 뺀 소문자)에 조각이 나오는 횟수. 글자층이 없는 쪽은 0."""
    L = _LOCATOR
    return L.page(no).vt.count(_norm(s)) if L and (no in L.ok or no in L.ocr) else 0


def _view(rows: list[dict], doc: str, keys: set | None = None) -> dict:
    """줄에서 나오는 화면 상태: 카드·값 풀이·칸 정보(순서·항·명세·입력 모양·필수). keys가 있으면 그 카드의 줄만 (성분 목록·코드 이름은 늘 전체)."""
    pc, mine, drop = page_count(doc), rows if keys is None else [r for r in rows if card_key(r["경로"]) in keys], dropped(rows, default_model(doc))
    ex = {r["경로"]: x for r in mine if (x := _explain(r, rows, pc, doc, drop))}
    return {"cards": _cards(rows, pc, ex, keys, drop), "explain": ex,
            "order": {r["경로"]: field_order(generic(r["경로"])) for r in mine}, "sec": {r["경로"]: scope_key(r["경로"]) for r in mine},
            "spec": {r["경로"]: x for r in mine if (x := _spec_note(r["경로"]))},
            "forms": {g: _form(x) for g, x in {generic(r["경로"]): r["경로"] for r in mine}.items()},
            "must": {r["경로"]: x for r in mine if (x := _must(r["경로"]))}, "comps": _comp_options(rows, drop), "names": _names(rows)}


def _wide(path: str) -> bool:
    """이 줄의 값에 다른 카드가 기대나: 성분표 줄(다른 카드의 대상 성분 이름·번호), 순번 줄(같은 목록 형제의 순번 확인)."""
    return ".components[" in path or path.endswith(".seq")


def _scope(old: list[dict] | None, rows: list[dict], touched: list[str], model: str) -> set | None:
    """다시 만들 카드: 다른 카드에 영향을 주는 변화면 None(문서의 모든 카드), 아니면 바뀐 줄의 카드들.
    영향: 골드에서 빠지는 항목이 달라짐(삭제 → 그 항목의 다른 카드, 순번 형제, 성분명 표), 성분표·순번 줄의 지금 값이 바뀌거나 줄이 생기고 없어짐.
    old가 없으면(이전 상태를 모름) 성분표·순번 줄이면 전체."""
    if old is None:
        return None if any(map(_wide, touched)) else {card_key(p) for p in touched}
    was, now = {r["경로"]: r for r in old}, {r["경로"]: r for r in rows}
    moved = lambda p: (p in was) != (p in now) or (p in now and _val(was[p]) != _val(now[p]))
    norm = lambda d: {k: sorted(v) for k, v in d.items()}
    if any(_wide(p) and moved(p) for p in touched) or norm(dropped(old, model)) != norm(dropped(rows, model)) \
            or any(overlaps_src(was.get(p)) != overlaps_src(now.get(p)) for p in touched):      # 삭제·근거 줄이 바뀌면 겹친 카드의 띠도 바뀐다
        return None
    return {card_key(p) for p in touched}


def _update(sheet: "Sheet", touched: list[str], old: list[dict] | None = None) -> dict:
    """줄을 바꾼 뒤(저장·삭제·추가·되돌리기·교차 확인) 화면이 받을 것 (old: 바꾸기 전 줄). 다른 카드에 영향을 주는 변화면 문서의 모든 카드(keys None),
    아니면 그 줄들의 카드만(_scope). rows: 아직 있는 바뀐 줄, gone: 없어진 줄."""
    rows = sheet.rows()
    by, touched = {r["경로"]: r for r in rows}, list(dict.fromkeys(touched))
    keys = _scope(old, rows, touched, default_model(sheet.doc_id))
    return {"rows": [by[p] for p in touched if p in by], "gone": [p for p in touched if p not in by],
            "keys": None if keys is None else sorted(keys), **_view(rows, sheet.doc_id, keys)}


def _checks(pg: "_Page", no: int, rows: list[dict], area_by_path: dict[str, set]) -> dict[str, str]:
    """숨긴 칸(쪽·항 번호)이 원문 조각이 찾힌 자리와 다르면 이유. 조각이 이 쪽에서 안 찾혔으면 말하지 않는다."""
    area = set().union(*area_by_path.values()) if area_by_path else set()
    if not area:
        return {}
    sec = pg.section_at()
    secs = sorted({s for k in area if (s := sec[pg.line[k]]) is not None and s > 0})
    out = {}
    for r in rows:
        v, name = _val(r), r["경로"].rsplit(".", 1)[-1]
        if not v.isdigit():
            continue
        if name == "page" and int(v) != no:          # page_start/page_end는 MSDS 시작·끝 쪽이라 조각 쪽과 견주지 않는다(쪽수 안인지만 자동 확인)
            out[r["경로"]] = f"원문은 {no}쪽에 있음"
        elif name == "section_no" and secs and int(v) not in secs:
            out[r["경로"]] = f"원문은 {secs[0]}항에 있음"
    return out


def _area_ok(r: dict, got: dict) -> bool:
    """값 상자가 없는 칩에 노란 상자를 대신 칠해도 되나: 예·아니오 칸은 안 됨(항 전체가 칠해진다), 노란 상자가 4줄 넘게 커도 안 됨.
    안 되면 칩은 회색 점선 + '원문에서 직접 찾아 주세요'."""
    if r["경로"].rsplit(".", 1)[-1] in QUESTIONS or "boolean" in _types(_alts(r["경로"])):
        return False
    return _lines(got.get("area") or []) <= 4


def _lines(rects: list) -> int:
    """상자(비율 [x, y, w, h])들이 몇 줄인가: 세로로 겹치는 상자는 한 줄로 묶는다(표 한 줄의 칸들은 y가 조금씩 다르다)."""
    n, bottom = 0, -1.0
    for _, y, _, h in sorted(rects, key=lambda b: b[1]):
        if y >= bottom - 1e-6:            # 앞 줄 아래 끝보다 아래에서 시작하면 새 줄
            n += 1
            bottom = y + h
        else:
            bottom = max(bottom, y + h)
    return n


def _err(e: Exception) -> str:
    """요청 오류 → 사람이 읽을 글 (KeyError의 "'items'" 대신)."""
    return f"요청에 ‘{e.args[0]}’ 값이 없어요" if isinstance(e, KeyError) and e.args else str(e)


def make_handler(sheet: Sheet, readonly: bool, locator: Locator):
    global _LOCATOR
    _LOCATOR = locator
    def locate(query: str) -> dict:
        sheet.fresh()                     # 엑셀에서 고친 직후에도 지금 값으로 찾는다
        q = parse_qs(query)
        no, want = int(q["page"][0]), set(q.get("path", []))
        out = {"value": [], "area": [], "many": 0, "notes": [], "per": {}, "checks": {}}
        rows, areas, mine = sheet.rows(), {}, []
        for r in rows:
            if r["경로"] in want:
                t = next((t for t in ("Claude", "GPT") if r[f"{t} 값"] != ""), "Claude")
                edited = r["수정값"] != "" and r["검수 결과"] in NEED_SOURCE
                got = locator.locate(no, _plain(r["수정값"] if edited else r[f"{t} 값"]),
                                     r["수정 원문 조각"] if edited else r[f"{t} 원문 조각"], section_of(r["경로"]), _hints(r["경로"], rows), r["칸 이름"])
                if no in locator.ok or no in locator.ocr:
                    got["other_key"] = _key_elsewhere(locator.page(no), got["area"], r, rows,
                                                      [(n, locator.page(n)) for n in (no - 1, no + 1) if n in locator.ok or n in locator.ocr])
                for k in ("value", "area"):
                    out[k] += [b for b in got.get(k, []) if b not in out[k]]
                out["per"][r["경로"]] = got.get("value") or (got.get("area") if _area_ok(r, got) else []) or []   # 줄마다 값 상자, 없으면 노란 상자(될 때만)
                areas[r["경로"]] = got.get("area_chars", set())
                mine.append(r)
                out["many"] = max(out["many"], got.get("many", 0))
                out["notes"] += [n for n in _notes(r, got, len(want) == 1, edited) if n not in out["notes"]]
        if no in locator.ok or no in locator.ocr:
            out["checks"] = _checks(locator.page(no), no, mine, areas)
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
                                        "rank": silver_rank(sheet.doc_id), "rows": rows, "pages": page_count(sheet.doc_id), "reloaded": reloaded,
                                        **_view(rows, sheet.doc_id),
                                        "sections": [SECTION_TITLES[s] for s in REVIEW_SECTIONS],
                                        "excel_open": sheet.excel_open(), "readonly": readonly})
            u = urlsplit(self.path)
            if u.path in ("/api/preview", "/api/item_form"):
                q = parse_qs(u.query)
                try:
                    if u.path == "/api/preview":     # 저장 전에 '저장될 값'을 보여 주고 틀리면 이유를 알린다
                        alts = _alts(q["path"][0])
                        if not alts:
                            raise ValueError("TO21에 없는 칸입니다")
                        cell = _cell_of(_coerce(q["v"][0].strip(), alts, q["path"][0]))
                        rows = sheet.rows()
                        return self._json(200, {"cell": cell, "text": human(q["path"][0], cell, _code_names(), comps_from_rows(rows, dropped(rows, default_model(sheet.doc_id))))["text"]})
                    return self._json(200, _item_form(q["item"][0], sheet.rows()))
                except (KeyError, ValueError, IndexError) as e:
                    return self._json(400, {"error": _err(e)})
            if u.path == "/api/unused":
                try:
                    return self._json(200, {"boxes": _unused(locator, int(parse_qs(u.query)["page"][0]), sheet.rows())})
                except (KeyError, ValueError, IndexError) as e:
                    return self._json(400, {"error": _err(e)})
            if u.path == "/api/pick":
                q = parse_qs(u.query)
                try:
                    no, x, y = int(q["page"][0]), float(q["x"][0]), float(q["y"][0])
                    ok = (no in locator.ok or no in locator.ocr) and 0 <= x <= 1 and 0 <= y <= 1
                    return self._json(200, _pick(locator.page(no), x, y) if ok else {})
                except (KeyError, ValueError, IndexError) as e:
                    return self._json(400, {"error": _err(e)})
            if u.path == "/api/locate":
                try:
                    return self._json(200, locate(u.query))
                except (KeyError, ValueError, IndexError) as e:
                    return self._json(400, {"error": _err(e)})
            m = re.fullmatch(r"/page/(\d+)\.png", u.path)   # 주소에 문서 번호(?d=)가 붙어 온다: 같은 포트로 다른 문서를 열어도 앞 문서 사진을 캐시에서 꺼내지 않게
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
                if not isinstance(body, dict):
                    raise ValueError("요청 내용은 {이름: 값} 꼴이어야 해요")
                reloaded = sheet.fresh()
                old = sheet.rows() if self.path != "/api/info" else None   # 바꾸기 전 줄: 다른 카드에 영향을 주는 변화인지 _update가 견준다 (문서 정보는 줄을 안 바꿈)
                # 줄을 바꾸는 길은 모두 _update(바뀐 줄 경로, old)를 돌려준다: 화면은 apply() 하나로 반영한다
                if self.path == "/api/save":
                    out = _update(sheet, [sheet.save_row(str(body["경로"]).strip(), body["values"])["경로"]], old)
                elif self.path == "/api/save_many":
                    out = _update(sheet, [r["경로"] for r in sheet.save_rows(body["items"])], old)
                elif self.path == "/api/add":
                    out = _update(sheet, [sheet.add_row(body["values"])["경로"]], old)
                elif self.path == "/api/add_item":
                    common = {k: body["values"].get(k) for k in ("수정 원문 조각", "수정 쪽", "메모", "검수자")}
                    new = _new_rows(str(body["item"]), body.get("mode"), body.get("fields"), common, sheet.rows())
                    if not body.get("force") and body.get("mode") != "field" and (d := _dup(new, sheet.rows())):     # 숨은 카드(필수 칸만 등)를 못 보고 또 넣는 것을 막는다
                        return self._json(200, {**d, "reloaded": reloaded})
                    out = _update(sheet, [r["경로"] for r in sheet.add_rows(new)], old)
                elif self.path == "/api/restore":          # 카드 되돌리기: 판단 전 사람 열을 그대로
                    out = _update(sheet, [r["경로"] for r in sheet.restore(body["items"])], old)
                elif self.path == "/api/remove":           # 경로 하나, 또는 카드의 직접 넣은 줄 목록을 한 번에
                    gone = body["경로"] if isinstance(body["경로"], list) else [str(body["경로"])]
                    sheet.remove_added(gone)
                    out = _update(sheet, [str(p).strip() for p in gone], old)
                elif self.path == "/api/cross":
                    n = sheet.cross_done(body["name"])
                    out = {"count": n, **_update(sheet, [r["경로"] for r in sheet.rows() if str(r["우선순위"]) == "1"], old)}
                elif self.path == "/api/info":
                    sheet.save_info(body["key"], body["value"])
                    out = {"info": sheet.info()}
                else:
                    return self._json(404, {"error": "없는 주소"})
                self._json(200, {**out, "reloaded": reloaded})
            except OSError as e:              # 저장 못 함: Sheet._save가 까닭별 안내를 준다
                self._json(409, {"error": str(e)})
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                sheet.load()                  # 반쯤 바뀐 메모리 상태를 버리고 파일 상태로 되돌린다
                self._json(400, {"error": _err(e)})

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
.sechd { font-size: .95rem; margin: 18px 0 8px; padding: 4px 0 4px 10px; border-left: 4px solid var(--accent); }
.sechd:first-of-type { margin-top: 6px; }
#me { width: 9em; }
#q { width: 12em; }
.bar { width: 160px; height: 8px; background: var(--chip); border-radius: 4px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--ok); }
#saved { font-size: .8rem; color: var(--muted); }
main { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(360px, 1fr); min-height: 0; }
#left { display: grid; grid-template-rows: auto auto 1fr; min-height: 0; border-right: 1px solid var(--line); }
#notes:empty { display: none; }
#notes { padding: 6px 12px; background: var(--warnbg); color: var(--ink); border-bottom: 1px solid var(--line); font-size: .85rem; }
#notes p { margin: 2px 0; }
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
.hl.unused { outline: 2px dashed #6b7cff; outline-offset: 1px; background: rgba(107, 124, 255, .07); pointer-events: none; }
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
.ex { font-size: .82rem; color: var(--muted); flex-basis: 100%; }
.v small { font-weight: 400; color: var(--muted); }
.acts.sm button { padding: 1px 8px; font-size: .82rem; }
.card > .acts { border-top: 1px solid var(--line); padding-top: 8px; }
details { font-size: .82rem; color: var(--muted); margin: 4px 0; }
.acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.res { font-weight: 700; color: var(--ok); }
.card.busy .acts button, .card.busy .res button, .card.busy .chip { pointer-events: none; opacity: .5; }
.res.bad, .q.bad, .help.bad { color: var(--bad); }
body.saving #right .acts button, body.saving #right .ed button { pointer-events: none; opacity: .5; }
.ed { display: grid; gap: 6px; margin-top: 8px; padding: 8px; background: var(--bg); border-radius: 6px; }
.ed label { font-size: .78rem; color: var(--muted); }
.pv { font-size: .8rem; color: var(--muted); } .pv.ok { color: var(--ok); } .pv.bad { color: var(--bad); }
.sub { display: grid; grid-template-columns: repeat(auto-fill, minmax(9em, 1fr)); gap: 4px; } .sub label { display: grid; gap: 2px; }
.fld { display: grid; gap: 4px; }
.tag.must { background: var(--badbg); color: var(--bad); }
.memo { font-size: .82rem; color: var(--warn); margin-top: 4px; }
#toast { position: fixed; bottom: 14px; left: 50%; transform: translateX(-50%); padding: 8px 14px; border-radius: 8px; background: var(--ink); color: var(--bg); display: none; max-width: 90vw; z-index: 9; }
#toast.err { background: var(--bad); color: #fff; }
.help { font-size: .8rem; color: var(--muted); }
/* 문장 카드: 칩 색 = 왼쪽 사진의 상자 색. 칩 글자색은 다크 모드에서 밝게, 사진 위 상자는 늘 흰 종이 위라 진한 색 그대로 */
:root { --c1:#2563eb; --c2:#b45309; --c3:#047857; --c4:#7e22ce; --c5:#0e7490; --c6:#be185d; }
@media (prefers-color-scheme: dark) { :root { --c1:#7aa7ff; --c2:#f0a54a; --c3:#4fd1a1; --c4:#c79bff; --c5:#4cc9e0; --c6:#f472b6; } }
.chip[data-c="1"] { --k: var(--c1); } .chip[data-c="2"] { --k: var(--c2); } .chip[data-c="3"] { --k: var(--c3); }
.chip[data-c="4"] { --k: var(--c4); } .chip[data-c="5"] { --k: var(--c5); } .chip[data-c="6"] { --k: var(--c6); }
.hl.chipbox[data-c="1"] { --k: #2563eb; } .hl.chipbox[data-c="2"] { --k: #b45309; } .hl.chipbox[data-c="3"] { --k: #047857; }
.hl.chipbox[data-c="4"] { --k: #7e22ce; } .hl.chipbox[data-c="5"] { --k: #0e7490; } .hl.chipbox[data-c="6"] { --k: #be185d; }
.hl.chipbox { outline: 2px solid var(--k); outline-offset: 1px; background: color-mix(in srgb, var(--k) 10%, transparent); }
#hls.pick .hl.chipbox { opacity: .3; }
#hls.pick .hl.chipbox.hot { opacity: 1; outline-width: 3px; background: color-mix(in srgb, var(--k) 24%, transparent); }
.card.sc { cursor: pointer; }
.card.sc.sel { box-shadow: 0 0 0 2px var(--accent); }
.card h3 .m { color: var(--bad); font-weight: 700; }
.sent { font-size: 1rem; line-height: 2.1; margin: 4px 0; }
.chip { display: inline-block; max-width: 100%; padding: 0 8px; border-radius: 1em; border: 2px solid var(--k); color: var(--k); font-weight: 650; cursor: pointer; line-height: 1.55; }
.card .chip.on { background: color-mix(in srgb, var(--k) 16%, transparent); }
.chip.nobox { border-style: dashed; border-color: var(--muted); }
.chip.warn { border-color: var(--bad); background: var(--badbg); }
.chip.warn::before { content: "⚠ "; color: var(--bad); }
.chip.jd::after { content: " ✓"; font-size: .8em; } .chip.fx::after { content: " ✎"; font-size: .8em; }
.chip.del { text-decoration: line-through; }
.card.fixing .chip { background: var(--chip); }
.pop { margin: 6px 0; padding: 6px 10px; border-radius: 6px; background: var(--bg); font-size: .85rem; }
.q { font-weight: 700; font-size: .9rem; margin-top: 6px; }
.hint { font-size: .85rem; background: var(--warnbg); border-radius: 6px; padding: 5px 10px; margin-top: 6px; }
.auto { font-size: .78rem; color: var(--muted); margin-top: 6px; }
button.yes { color: var(--ok); border-color: var(--ok); font-weight: 700; }   /* 처음엔 테두리만: 칠해져 있으면 이미 눌린 것처럼 보인다 */
button.yes:hover, button.yes.pulse { background: var(--ok); color: var(--panel); }
button.yes.pulse { box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 35%, transparent); }
.modes { display: grid; grid-template-columns: repeat(auto-fill, minmax(14em, 1fr)); gap: 6px; }
.modes button { text-align: left; } .modes button small { display: block; font-size: .78rem; opacity: .85; }
.fix { margin-top: 6px; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; grid-template-rows: 55vh auto; } }
/* 첫 화면 사용법 */
#tourbg { position: fixed; inset: 0; background: rgba(10,14,20,.55); display: none; z-index: 95; }   /* 어두운 막: 밖을 누르면 아무 일도 없게 막는다 (테두리 친 요소는 z 100으로 이 위) */
#tour { position: fixed; inset: 0; display: none; align-items: center; justify-content: center; z-index: 200; pointer-events: none; }
#tour .box { pointer-events: auto; }
#tour button.pri.pulse { box-shadow: 0 0 0 4px #fbbf24; }
#tour.low { align-items: flex-end; padding-bottom: 18px; }
#tour.side { justify-content: flex-start; padding-left: 16px; }   /* 카드는 오른쪽 칸에 있으니 설명 상자는 왼쪽 아래에 둬서 카드의 풀이를 가리지 않게 */
#tour .box { background: var(--panel); color: var(--ink); border-radius: 14px; max-width: 520px; width: calc(100% - 32px); padding: 18px 20px; box-shadow: 0 10px 40px rgba(0,0,0,.3); border: 1px solid var(--line); }
#tour .step { font-size: .8rem; color: var(--muted); } #tour h3 { margin: 4px 0 8px; }
#tour .dots { display: flex; gap: 6px; margin: 10px 0; } #tour .dots i { width: 9px; height: 9px; border-radius: 50%; background: var(--line); } #tour .dots i.on { background: var(--c1); }
#tour .acts { display: flex; justify-content: space-between; gap: 8px; margin-top: 12px; }
#tour button { font: inherit; padding: 6px 14px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel); color: var(--ink); cursor: pointer; }
#tour button.pri { background: var(--c1); color: #fff; border-color: var(--c1); }
.ring { outline: 4px solid #fbbf24 !important; outline-offset: 4px; border-radius: 10px; z-index: 100 !important; }
@media (prefers-color-scheme: dark) { #tour button.pri { color: #12161c; } }
.ring.lock { pointer-events: none; }
#view.ring { outline-offset: -4px; }
</style></head><body>
<header>
  <h1 id="title">검수 화면</h1>
  <div class="grp"><span class="lbl">내 이름</span><input id="me" placeholder="이름 (필수)"></div>
  <span id="modelbl" class="tag"></span>
  <div class="grp" id="prio"><span class="lbl">우선순위</span><button data-p="1" class="on" title="1순위(가장 중요한 칸, 교차 확인 대상) 보이기·숨기기">1</button><button data-p="2" class="on" title="2순위 칸 보이기·숨기기">2</button><button data-p="3" class="on" title="3순위(덜 중요한 칸) 보이기·숨기기">3</button></div>
  <div class="grp" id="stat"><span class="lbl">보기</span><button data-s="todo" class="on" title="아직 확인하지 않은 칸만 봐요">남은 칸</button><button data-s="all" title="확인한 칸까지 모두 봐요">전체</button><button id="mustbtn" title="TO21 채점기의 필수 항목에 들어가는 칸만 봅니다 (작은 골드: 개발용 2~3건 필수 항목 검수)">필수 칸만</button><button id="detailbtn" title="문장 카드 대신 칸마다 한 줄씩 봅니다">자세히(칸별)</button></div>
  <input id="q" placeholder="찾기 (칸 이름, 값)">
  <div class="grp"><div class="bar"><i id="barfill"></i></div><span id="prog" class="lbl"></span><span id="mustleft" class="tag must" title="작은 골드는 필수 칸을 빈칸 없이 채웁니다"></span></div>
  <div class="grp"><button id="crossbtn" title="다른 사람의 교차 확인 의견을 모두 고친 뒤 눌러요 (1순위 칸에 확인한 사람 이름을 적어요)">교차 확인 반영</button><button id="endbtn" title="이 문서 검수를 다 마쳤을 때 눌러요 (끝난 시각을 적어요)">검수 끝 시각 적기</button><button id="gonebtn" hidden>방금 지운 카드 되돌리기</button><span id="saved"></span><button id="tourbtn" title="사용법을 다시 봅니다">? 사용법</button></div>
</header>
<main>
  <section id="left"><div id="pager"></div><div id="notes" role="status"></div><div id="view"></div></section>
  <section id="right"></section>
</main>
<div id="toast"></div>
<div id="tourbg"></div>
<div id="tour"><div class="box">
  <div class="step" id="tstep"></div><h3 id="ttitle"></h3><div id="tbody"></div>
  <div class="dots" id="tdots"></div>
  <div class="acts"><button id="tskip">건너뛰기</button><span><button id="tprev">이전</button> <button class="pri" id="tnext">다음</button></span></div>
</div></div>
<script>
const $ = s => document.querySelector(s);
const MAC = /Mac/i.test(navigator.userAgentData?.platform || navigator.platform), MOD = MAC ? "⌘" : "Ctrl";
const CHROMIUM = !!navigator.userAgentData?.brands?.some(b => /Chrom/.test(b.brand));
const h = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let S = {rows: [], info: {}, pages: 0}, page = 1, mode = "검수", prio = new Set([1, 2, 3]), show = "todo", q = "", open = null, zoom = 100, mustOnly = false;
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
const rowOdd = r => { const res = r["검수 결과"] || "";   // 엑셀로만 생기는, 골드에 값이 안 들어가는 판단 (review_cards._odd와 같은 규칙): 확인한 칸으로 세지 않는다
  return (/^(수정|누락 추가)$/.test(res) && !r["수정값"]) || (/ 채택$/.test(res) && !r[res.slice(0, -3) + " 값"]); };
const judgedOk = r => !!r["검수 결과"] && !rowOdd(r);
const moot = r => !r["검수 결과"] && !!S.cards?.[gkey(r["경로"])]?.drop;   // 골드에서 빠지는 항목의 미판단 줄: 볼 필요 없음 (진행률·남은 칸에서 뺀다, 저장은 안 함)
const isDone = r => mode === "검수" && judgedOk(r);
const keep = new Set();      // 이 쪽에서 방금 저장한 줄: 쪽을 떠나기 전까지 그 자리에 둔다(눌러 둔 단추 밑으로 다음 줄이 올라와 잘못 누르지 않게)
const passes = (r, must = mustOnly) => inMode(r) && prio.has(Number(r["우선순위"]) || 3) && (show === "all" || (!isDone(r) && !moot(r))) && (!must || !!S.must?.[r["경로"]])
  && (!q || [r["칸 이름"], r["경로"], ...tags.map(t => r[t + " 값"]), r["수정값"]].join(" ").toLowerCase().includes(q));
const visible = r => keep.has(r["경로"]) || passes(r);

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
function render() { renderPager(); renderView(); renderCards(); renderProg(); loadUnused(); }
// 점선 상자: 검수 범위 안인데 어떤 칸의 근거로도 쓰이지 않은 원문 줄 (모델이 통째로 빠뜨린 값일 수 있다)
let unusedOn = store("unused") !== "off", unusedKey = "";
async function loadUnused() {
  const box = $("#unused"), key = page + "|" + S.rows.length + "|" + S.rows.filter(r => r["수정 원문 조각"]).length;
  if (!box) return;
  if (!unusedOn || !page) { box.innerHTML = ""; unusedKey = ""; return; }
  if (key === unusedKey && box.dataset.pg === String(page)) return;
  unusedKey = key;
  let j; try { j = await api("/api/unused?" + new URLSearchParams({page})); } catch { return; }
  if (unusedKey !== key || !$("#unused")) return;
  $("#unused").dataset.pg = page;
  $("#unused").innerHTML = j.boxes.map(([x, y, w, hh]) => `<div class="hl unused" style="left:${x*100}%;top:${y*100}%;width:${w*100}%;height:${hh*100}%"></div>`).join("");
  $("#unusedbtn").title = `이 쪽 ${j.boxes.length}곳: 검수 범위 안인데 어떤 칸의 근거로도 쓰이지 않은 원문 줄. AI가 빠뜨린 값이면 그 항목 카드의 '빠진 칸·항목 추가'로 넣으세요`;
}

function renderProg() {
  const own = r => r["일치"] !== "";      // 진행률은 스크립트가 만든 줄 기준 (누락 추가 줄 제외)
  const base = S.rows.filter(r => inMode(r) && own(r) && !moot(r)), done = base.filter(isDone).length;
  const by = n => { const x = S.rows.filter(r => own(r) && !moot(r) && String(r["우선순위"]) === n); return `${n}순위 ${x.filter(judgedOk).length}/${x.length}`; };
  const cards = new Map();            // 카드(같은 대상의 칸 묶음) 단위: 모든 칸을 판단했으면 끝난 카드
  for (const r of base) { const k = gkey(r["경로"]); cards.set(k, (cards.get(k) ?? true) && isDone(r)); }
  const cdone = [...cards.values()].filter(Boolean).length;
  $("#prog").textContent = mode === "검수" ? `카드 ${cdone} / ${cards.size}장 · 칸 ${done} / ${base.length} (${by("1")}, ${by("2")}, ${by("3")})` : `1순위 ${base.length}줄`;
  $("#barfill").style.width = (base.length ? 100 * done / base.length : 0) + "%";
  const left = S.rows.filter(r => S.must?.[r["경로"]] && !judgedOk(r) && !moot(r)).length, ml = $("#mustleft");
  ml.hidden = mode !== "검수"; ml.className = "tag " + (left ? "must" : "ok");
  ml.textContent = left ? `남은 필수 칸 ${left}` : "필수 칸 끝 ✔";
}
function renderPager() {
  const cnt = {};
  for (const r of S.rows) if (passes(r) && !isDone(r) && !moot(r)) for (const p of pagesOf(r)) cnt[p] = (cnt[p] || 0) + 1;   // 남은 칸만 (카드 판단으로 함께 저장된 숨은 줄이 keep으로 보여도 세지 않는다)
  const list = [...Array(S.pages).keys()].map(i => i + 1);
  if (S.rows.some(r => pagesOf(r)[0] === 0)) list.push(0);
  $("#pager").innerHTML = `<button id="prev" title="이전 쪽 (←)">◀</button>` + list.map(p =>
    `<button data-pg="${p}" title="이 쪽에 남은 칸${cnt[p] ? " " + cnt[p] + "개" : " 없음"}" class="${p === page ? "on" : ""} ${cnt[p] ? "" : "clear"}">${p || "쪽 없음"}${cnt[p] ? `<small>${cnt[p]}</small>` : ""}</button>`).join("")
    + `<button id="next" title="다음 쪽 (→)">▶</button><span class="grp" style="margin-left:auto"><button id="unusedbtn" class="${unusedOn ? "on" : ""}">점선: 근거 없는 줄</button><button id="zo">−</button><button id="zf">맞춤</button><button id="zi">+</button></span>`;
}
function renderView() {
  const v = $("#view"), w = v.querySelector(".pgw");
  if (page && w && Number(w.dataset.pg) === page) { w.style.width = zoom + "%"; return; }   // 확대만 바뀌면 사진을 다시 그리지 않는다
  v.innerHTML = page ? `<div class="pgw" data-pg="${page}" style="width:${zoom}%"><img src="/page/${page}.png?d=${encodeURIComponent(S.doc)}" alt="${page}쪽" decoding="async"><div id="unused"></div><div id="hls"></div></div>`
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
  return `<div class="none"><p>여기 칸들은 AI가 쪽 번호를 적지 않은 칸입니다. 대부분 "문서에 이런 표기가 없다"는 판단이라 가리킬 쪽이 없습니다.
    예를 들어 "유해성분 미함유 표기: false"는 문서에 "유해성분 없음"이라는 표기가 없다는 뜻입니다.</p>
    <p>확인하는 법: 아래 쪽을 열어 그 표기가 정말 없는지 보고, 없으면 '맞음'입니다. 있으면 '수정'으로 값과 쪽을 적어 주세요.</p>${jump}</div>`;
}
$("#view").addEventListener("click", e => { const b = e.target.closest("button[data-go]"); if (b) go(Number(b.dataset.go)); });
// 고른 칸(또는 묶음)이 사진의 어디인지 표시한다. 노란 상자 = 원문 조각, 주황 테두리 = 값
let sel = [], selSeq = 0;
// 문장 카드의 위치 찾기 결과 {key, per: {경로: [상자]}, checks: {경로: 까닭}}. per가 없으면 아직 응답 전
let loc = {}, pick = null, fixing = null;
const seenCards = new Set();       // 눌러서 왼쪽 위치를 본 카드: 이 카드만 '같아요'를 받는다 (생각 없이 누르기 방지)
function toBox(first) {            // 왼쪽 사진만 움직인다 (scrollIntoView는 오른쪽 칸 목록까지 밀어 누르려던 단추가 움직일 수 있다)
  const img = $("#view img"), go = () => {
    const V = $("#view"), r = first.getBoundingClientRect(), v = V.getBoundingClientRect();
    V.scrollTo({top: V.scrollTop + r.top - v.top - (V.clientHeight - r.height) / 2, left: V.scrollLeft + Math.min(0, r.left - v.left - 20), behavior: "smooth"});
  };
  if (first) img && !img.complete ? img.addEventListener("load", go, {once: true}) : go();   // 사진이 다 불려 온 뒤에 (그 전엔 높이가 달라 엉뚱한 곳으로 간다)
}
async function highlight(paths, key) {
  sel = paths; const seq = ++selSeq, prev = loc.key;
  loc = key ? {key} : {};
  if (pick && pick.key !== key) pick = null;
  if (prev && prev !== key) redraw(prev);              // 앞 카드의 칩 표시(점선·풀이)를 지운다
  document.querySelectorAll(".ln, .card").forEach(el => el.classList.remove("sel"));
  for (const p of paths) document.querySelector(`.ln[data-p="${CSS.escape(p)}"]`)?.classList.add("sel");
  if (key) document.querySelector(`.card[data-g="${CSS.escape(key)}"]`)?.classList.add("sel");
  const box = $("#hls"); $("#notes").innerHTML = "";
  if (!box || !page || !paths.length) { if (key) { seenCards.add(key); redraw(key); } return box && (box.innerHTML = ""); }   // 쪽 없는 칸: 보여 줄 자리가 없다
  const qs = new URLSearchParams([["page", page], ...paths.map(p => ["path", p])]);
  let j; try { j = await api("/api/locate?" + qs); } catch { if (key && seq === selSeq) seenCards.add(key); return; }
  if (seq !== selSeq) return;                          // 그사이 다른 칸을 골랐으면 버린다
  const div = (k, [x, y, w, hh], at = "") => `<div class="hl ${k}" ${at} style="left:${x*100}%;top:${y*100}%;width:${w*100}%;height:${hh*100}%"></div>`;
  if (key) loc = {key, per: j.per || {}, checks: j.checks || {}};
  const col = key ? chipColors(key) : null;            // 문장 카드: 값 상자를 칩마다 칩과 같은 색으로 (경고 칩 포함)
  box.innerHTML = j.area.map(b => div("area", b)).join("") + (col
    ? Object.entries(col).flatMap(([p, c]) => (j.per?.[p] || []).map(b => div("chipbox", b, `data-c="${c}" data-p="${h(p)}"`))).join("")
    : j.value.map(b => div("value", b)).join(""));
  toBox(box.querySelector(".chipbox, .value") || box.querySelector(".area"));
  const yes = key ? document.querySelector(`.card[data-g="${CSS.escape(key)}"] button[data-a=same]`)?.textContent : "맞음";   // 안내의 단추 이름 = 실제 단추
  $("#notes").innerHTML = (j.notes || []).map(n => `<p>${h(yes ? n.replaceAll("‘같아요’", `‘${yes}’`) : n)}</p>`).join("");   // 상자만으로는 알 수 없는 사정 (사진 위에 남겨 둔다)
  if (key) { seenCards.add(key); redraw(key); paintPick(); }
}
function paintPick() {             // 누른 칩의 상자만 진하게
  const box = $("#hls"), on = pick && loc.key === pick.key ? pick.path : null; if (!box) return;
  const hot = [...box.querySelectorAll(".chipbox")].filter(d => { const x = d.dataset.p === on; d.classList.toggle("hot", x); return x; });
  box.classList.toggle("pick", hot.length > 0);
  if (hot.length) toBox(hot[0]);
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
function meaning(r, v, t) {   // 값 풀이(성분명·순번·코드 이름)는 서버(_explain)가 만든다. 판정용 그림도 같은 풀이를 쓴다
  return S.explain?.[r["경로"]] || "";
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
    const ex = meaning(r, v, t);        // 값은 늘 보이고, 풀이는 옆에 작게 (풀이만 보이면 검수자가 실제 값을 못 본다)
    const nm = S.names?.[v];          // 코드 값은 이름을 크게, 코드는 작게 (검수자는 코드를 모른다)
    html += `<span class="v">${tags.length > 1 ? `<small>${t} </small>` : ""}${nm ? `${h(nm)} <small>${h(v)}</small>` : fmt(v)}${GHS[v] ? ` <small>${GHS[v]}</small>` : ""}</span>${ex ? `<span class="ex">${h(ex)}</span>` : ""}`;
  }
  html += `${S.must?.[r["경로"]] ? `<span class="tag must" title="TO21 채점기 필수 항목">필수 · ${h(S.must[r["경로"]])}</span>` : ""}${r["검증기"] ? `<span class="tag bad">${h(r["검증기"])}</span>` : ""}</div>`;
  for (const t of tags) if (r[t + " 원문 조각"] && r[t + " 원문 조각"] !== shared) html += srcBox(r[t + " 원문 조각"], r[t + " 쪽"]);
  if (r["설명"] || r["적용 규칙"]) html += `<details><summary>AI 설명</summary>${h(r["적용 규칙"])} ${h(r["설명"])}</details>`;
  if (S.spec?.[r["경로"]]) html += `<details><summary>TO21 기준</summary>${h(S.spec[r["경로"]])}</details>`;
  if (rowOdd(r)) html += `<div><span class="res bad">⚠ 고른 값이 비어 있어 골드에 들어가지 않아요. ‘수정’으로 맞는 값을 적어 주세요</span></div>`;
  else if (res) html += `<div><span class="res">✔ ${h(/채택$/.test(res) ? "맞음" : res)}</span>${res === "수정" || res === "누락 추가" ? ` → <b>${fmt(plain(r["수정값"]))}</b> <span class="lbl">${h(r["수정 원문 조각"])} ${r["수정 쪽"] ? "(" + h(r["수정 쪽"]) + "쪽)" : ""}</span>` : ""}
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
    <h3 title="${h(key)}"><span class="tag">${pr}순위</span>${h(sec)}${k ? ` <b>${h(k.split(" / ").map(x => { const [, c, n] = x.match(/^(.*?)(#\d+)?$/); return (S.names?.[c] || c) + (n ? " " + n : ""); }).join(" / "))}</b>` : ""}${S.cards?.[key]?.drop ? ` <span class="tag bad" title="항목 안 칸을 삭제해 이 항목은 골드에서 빠져요">골드에서 빠지는 항목</span>` : ""}</h3>`;
  if (shared) html += srcBox(shared, rs[0][mainTag(rs[0]) + " 쪽"]);
  html += items.map(([r, i]) => line(r, i, shared)).join("");
  if (mode === "교차") return html + `</div>`;
  return html + `<div class="acts">${todo > 1 ? `<button data-a="adopt_all">전부 맞음 (${todo}칸)</button>` : ""}
    <button data-a="add" title="이 카드에 빠진 칸, 또는 같은 종류인데 AI가 통째로 빠뜨린 항목">빠진 칸·항목 추가</button>
</div>
    ${open && open.g === key ? editor(rs[0], "add") : ""}</div>`;
}
// 문장 카드: 서버(S.cards)가 만든 문장에 칸마다 색 칩. 저장은 지금처럼 칸마다 한 줄
let byKey = new Map(), detail = store("detail") === "on";
const rowsOf = key => byKey.get(key) || [];
const partChips = key => (S.cards?.[key]?.parts || []).filter(p => p.t === "chip");
const lateOf = key => loc.key === key && loc.checks ? S.cards[key].auto.filter(a => loc.checks[a.path]) : [];   // 숨긴 칸이 위치와 안 맞으면 경고 칩으로 드러낸다
const chipsOf = key => [...partChips(key), ...lateOf(key)];
const cardPaths = key => { const c = S.cards[key]; return [...partChips(key), ...c.auto, ...c.meta].map(x => x.path); };
const chipColors = key => Object.fromEntries(chipsOf(key).map((p, n) => [p.path, n % 6 + 1]));
function asSentence(key, items) {      // 문장으로 못 그리는 카드는 칸별 카드로 (줄이 화면에서 사라지지 않게)
  if (detail || !S.cards?.[key]) return false;
  const ps = new Set(cardPaths(key));
  if (!items.every(([r]) => ps.has(r["경로"]))) return false;     // 카드를 만든 뒤 넣은 줄(누락 추가)
  return !dual(key);
}
const dual = key => rowsOf(key).some(r => r["GPT 값"] !== "" && r["Claude 값"] !== "" && r["GPT 값"] !== r["Claude 값"]);   // 두 모델 값이 다르면 칸별로
const cardActs = new Map();            // 카드 판단(같아요·원문에 없어요) 전의 줄 전체: '되돌리기'가 /api/restore로 사람 열을 그대로 다시 쓴다 (이 쪽을 떠나면 비운다)
const cardH = new Map();               // 판단한 카드의 높이: 쪽을 떠날 때까지 지킨다 (접히면 아래 카드가 올라와 다음 클릭이 엉뚱한 곳에 눌린다)
const fixedRow = r => /^(수정|누락 추가)$/.test(r["검수 결과"]) && !!r["수정값"];   // 지금 값이 수정값인 줄 (review_cards._cell_now·골드와 같은 규칙)
const curCell = r => (fixedRow(r) && r["수정값"]) || r["Claude 값"] || r["GPT 값"] || "";
const RES = res => /채택$/.test(res) ? "맞음" : res;
function popOf(key, p) {               // 칩 풀이: 뜻·저장 코드, 값 풀이(성분명 등), 그리고 상자·자동 확인 사정
  const r = rowsOf(key).find(x => x["경로"] === p.path) || {}, L = loc.key === key ? loc : {};   // 저장하면 서버가 이 카드를 지금 값으로 다시 만들어 준다
  const warn = p.warn || L.checks?.[p.path], tip = p.tip;
  const nobox = L.per && !L.per[p.path]?.length;      // tip = 용어 풀이 → 짝 풀이 → 값 풀이(성분명 등) → 쉬운 명세 풀이 (서버, 한두 줄)
  return [`<b>${h(p.label)}</b> · ${tip ? h(tip) : nobox || warn ? "" : "왼쪽 같은 색 상자의 글자와 같은지 보세요"}`.replace(/ · $/, ""), warn && `⚠ ${h(warn)}`,   // 풀이가 없어도 칸 이름만 덩그러니 두지 않는다
    nobox && "원문에서 직접 찾아 주세요",
    judgedOk(r) && `이미 확인했어요: ${h(RES(r["검수 결과"]))}${r["검수자"] ? " (" + h(r["검수자"]) + ")" : ""}`]
    .filter(Boolean).map(x => `<div>${x}</div>`).join("");
}
function dropText(key, dr) {           // 골드에서 항목 전체가 빠지는 까닭 (그렇게 만든 칸, 상위 항목의 칸이면 그렇다고)과 할 일
  const lab = p => `‘${parts(S.rows.find(r => r["경로"] === p)?.["칸 이름"] || p).fn || p}’`;
  const up = dr.by.some(p => gkey(p) !== key), del = dr.by.every(p => S.rows.find(r => r["경로"] === p)?.["검수 결과"] === "삭제");
  return `${up ? "상위 항목의 " : ""}${dr.by.map(lab).join(", ")} 칸${del ? "을 삭제해서" : " 때문에"} 이 항목은 골드에서 빠져요. 나머지 칸은 볼 필요 없어요. `
    + `되살리려면 ‘삭제한 칸 되돌리기’를 누르세요.${up ? "" : " 그 칸만 틀렸으면 ‘다른 칩이 있어요’로 맞는 값이나 비움을 적어도 돼요."}`;
}
function sentenceCard(key, items) {
  const c = S.cards[key], rs = rowsOf(key), R = Object.fromEntries(rs.map(r => [r["경로"], r]));
  const pr = Math.min(...rs.map(r => Number(r["우선순위"]) || 3)), judged = rs.filter(judgedOk).length;
  const L = loc.key === key ? loc : null, col = chipColors(key), q = c.type === "question", late = lateOf(key);
  const chip = p => {
    const r = R[p.path] || {}, res = r["검수 결과"], warn = p.warn || L?.checks?.[p.path];
    const cls = [warn && "warn", L?.per && !L.per[p.path]?.length && "nobox", judgedOk(r) && ({"수정": "fx", "삭제": "del"}[res] || "jd"),
      pick?.key === key && pick.path === p.path && "on"].filter(Boolean).join(" ");
    return `<span class="chip ${cls}" data-p="${h(p.path)}" data-c="${col[p.path]}" title="${h(p.label)}">${h(p.text)}</span>`;
  };
  let html = `<div class="card sc p${pr} ${judged === rs.length ? "done" : ""} ${fixing === key ? "fixing" : ""} ${L ? "sel" : ""} ${busy.has(key) ? "busy" : ""}" data-g="${h(key)}" data-o="${h(JSON.stringify(open))}"${cardH.has(key) ? ` style="min-height:${cardH.get(key)}px"` : ""}>
    <h3 title="${h(key)}"><span class="tag">${pr}순위</span>${h(c.title)}${rs.some(r => S.must?.[r["경로"]]) ? ` <span class="m">· 필수</span>` : ""}${judged && judged < rs.length ? ` <span class="tag ok">${judged}칸은 이미 확인했어요</span>` : ""}</h3>
    <div class="sent">${c.parts.map(p => p.t === "chip" ? chip(p) : h(p.s)).join("")}${late.map(a => `${c.parts.length ? " · " : ""}${h(a.label)}: ${chip(a)}`).join("")}</div>`;
  const pp = pick?.key === key && chipsOf(key).find(p => p.path === pick.path);
  if (pp) html += `<div class="pop">${popOf(key, pp)}</div>`;
  if (c.hint) html += `<div class="hint">💡 ${h(c.hint)}</div>`;
  for (const o of c.overlap || []) {      // 같은 원문 줄이 다른 표 카드에도 들어감 (서버가 정함). 맞지 않는 쪽은 띠 + 이동 단추
    const go = `<button data-a="goto" data-k="${h(o.other_key)}">그 카드로 가기</button>`;
    html += o.keep === "other" ? `<div class="q bad">⚠ 같은 원문 줄이 ‘${h(o.other_title)}’ 카드에도 들어가 있어요. TO21 기준(${h(o.why)})으로는 ‘${h(o.other_title)}’에만 적어요 → 이 카드는 ‘원문에 없어요’로 지워 주세요</div><div class="acts">${go}</div>`
      : `<div class="hint">${o.keep === "this" ? `같은 줄이 ‘${h(o.other_title)}’ 카드에도 있어요(그 카드를 지우면 돼요)` : `같은 원문 줄이 ‘${h(o.other_title)}’ 카드에도 들어갔어요. 한쪽만 맞는지 확인해 주세요`} ${go}</div>`;
  }
  if (mode !== "교차") {
    const undo = cardActs.get(key)?.length ? ` <button data-a="card_undo" title="이 카드에서 방금 한 판단만 그 전 상태로 되돌립니다">되돌리기</button>` : "";
    const mine = !undo && rs.every(r => r["검수 결과"] === "누락 추가" && !r["일치"]);   // 사람이 넣은 줄만 있는 카드: 잘못 넣었으면 카드째 지운다
    const odd = rs.filter(rowOdd).length, dr = c.drop && !c.drop.all ? c.drop : null;   // dr: 칸 몇 개 때문에 항목 전체가 골드에서 빠짐 (골드와 같은 규칙, 서버가 정함)
    if (dr) {                           // 빠지는 항목: 판단 단추 대신 되살리기 (상위 항목 때문이면 그 카드로 가는 단추)
      const up = dr.by.find(p => gkey(p) !== key);
      html += `<div class="q bad">⚠ ${h(dropText(key, dr))}</div><div class="acts"><button data-a="undrop" title="그 칸들을 미검수로 되돌려요 (메모는 남아요)">삭제한 칸 되돌리기</button>`
        + (up ? `<button data-a="goto" data-k="${h(gkey(up))}">상위 항목 카드로 가기</button>` : `<button data-a="fix" class="${fixing === key ? "on" : ""}">✗ 다른 칩이 있어요</button>`) + `${undo}</div>`;
    } else if (judged === rs.length) html += `<div class="res">✔ 확인했어요${c.drop?.all ? ` <span class="lbl">· 원문에 없는 항목이라 골드에서 빠져요</span>` : ""}${undo || (mine ? ` <button data-a="absent">원문에 없어요</button>` : ` <span class="lbl">바꾸려면 ‘자세히(칸별)’에서</span>`)}</div>`;
    else if (!dr && !rs.some(r => !r["검수 결과"])) {        // 남은 것은 고른 값이 없는 칸뿐: '확인했어요'가 아니라 다시 고르게 한다 (같아요는 이런 칸을 바꾸지 않는다)
      html += `<div class="q bad">${fixing === key ? "⚠ 칩을 눌러 맞는 값을 적어 주세요" : `⚠ ${odd}칸 다시 골라 주세요`}</div><div class="acts">
        <button data-a="fix" class="${fixing === key ? "on" : ""}">✗ 다른 칩이 있어요</button><button data-a="absent">원문에 없어요</button>${undo}</div>`;
    } else {
      const rest = judged > 0;          // 칩 몇 개를 고친 뒤: 남은 칩 판단을 놓치면 카드가 미판단으로 남는다
      const ask = rest ? "남은 칩이 맞으면 ‘✓ 나머지는 같아요’를 눌러 주세요" : fixing === key ? "틀린 칩을 눌러 고쳐 주세요. 나머지가 맞으면 ‘✓ 나머지는 같아요’" : q ? c.question : "왼쪽 노란 줄과 뜻이 같나요?";
      html += `<div class="q">${h(ask)}</div><div class="acts">
        <button class="yes ${rest ? "pulse" : ""}" data-a="same">${judged || fixing === key ? "✓ 나머지는 같아요" : q ? "✓ AI 답이 맞아요" : "✓ 같아요"}</button>
        <button data-a="fix" class="${fixing === key ? "on" : ""}">${q ? "✗ AI 답이 틀려요(고치기)" : "✗ 다른 칩이 있어요"}</button>
        ${q ? "" : `<button data-a="absent">원문에 없어요</button>`}
        <button data-a="add" title="이 카드에 빠진 칸, 또는 같은 종류인데 AI가 통째로 빠뜨린 항목">빠진 칸·항목 추가</button></div>`;
    }
  }
  const ok = c.auto.filter(a => !late.includes(a));
  if (ok.length) html += `<div class="auto">화면이 확인함 ✓ ${ok.map(a => `<span title="${h(a.why)}">${h(a.label)} ${h(a.text)}</span>`).join(" · ")}</div>`;
  if (c.meta.length) html += `<details><summary>AI가 정한 정보</summary>${c.meta.map(m => `${h(m.label)}: ${h(m.text)}`).join(" · ")}</details>`;
  const fr = open?.kind === "edit" && S.rows[open.i];
  if (fr && R[fr["경로"]]) html += `<div class="fix" data-i="${open.i}" data-p="${h(fr["경로"])}"><div class="lbl">고칠 칸: ${h(chipsOf(key).find(p => p.path === fr["경로"])?.label || fr["칸 이름"])}</div>${editor(fr, "edit")}</div>`;
  if (open && open.g === key) html += editor(rs[0], "add");
  return html + `</div>`;
}
function redraw(key) {                 // 카드 한 장만 다시 그린다 (위치 찾기 응답 뒤, 칩을 누른 뒤). 열린 양식에 적던 글은 그대로 둔다
  const el = document.querySelector(`.card.sc[data-g="${CSS.escape(key)}"]`);
  if (!el || !asSentence(key, groups.get(key) || [])) return;
  const same = el.dataset.o === JSON.stringify(open), typed = same ? [...el.querySelectorAll("input[id], textarea[id], select[id]")].map(x => [x.id, x.value]) : [];
  const pvs = same ? [...el.querySelectorAll(".pv[id]")].map(x => [x.id, x.className, x.textContent]) : [];
  const li = lastIn && el.contains(lastIn) ? lastIn.id : "";
  const ae = document.activeElement, top0 = ae && ae !== document.body && !el.contains(ae) && $("#right").contains(ae) ? ae.getBoundingClientRect().top : null;
  el.outerHTML = sentenceCard(key, groups.get(key) || []);
  if (top0 !== null) $("#right").scrollTop += ae.getBoundingClientRect().top - top0;   // 다른 카드에서 치던 칸이 화면에서 제자리
  for (const [id, v] of typed) { const x = document.getElementById(id); if (x) x.value = v; }
  for (const [id, c, t] of pvs) { const x = document.getElementById(id); if (x) { x.className = c; x.textContent = t; } }
  if (li) lastIn = document.getElementById(li);
  if (typed.length) { const x = $("#e_val"); if (x) preview(x); }
}
async function chipClick(key, path) {
  if (busy.has(key)) return;            // 판단·되돌리기를 처리하는 중인 카드는 칩도 잠근다
  pick = {key, path};
  const was = JSON.stringify(open);
  if (fixing === key && mode !== "교차") open = {i: S.rows.findIndex(r => r["경로"] === path), kind: "edit"};
  if (JSON.stringify(open) !== was) renderCards();      // 다른 칸의 수정 양식: 새로 연다
  if (loc.key !== key) await highlight(cardPaths(key), key); else paintPick();
  redraw(key);
}
// 칸 모양에 맞는 입력칸. 사람은 JSON을 몰라도 된다: 정해진 값은 고르고, 수치는 원문 표기 그대로, 문장은 소제목·내용으로 적는다
const gen = p => p.replace(/\[(?:k=[^\]]*|\d+)\]/g, "[]");
const formOf = p => S.forms?.[gen(p)] || {kind: "text"};
function curText(f, v) {                // 지금 값 → 입력칸에 넣을 글
  const s = plain(v); let o = null; try { o = JSON.parse(s); } catch {}
  if (f.kind === "q") return o && typeof o === "object" ? o.raw ?? "" : s;
  if (f.kind === "list") return Array.isArray(o) ? o.join("\n") : s;
  return s;
}
function input(f, path, id, cur) {
  const pv = `<div class="pv" id="${id}_pv"></div>`;
  if (f.kind === "comp" || f.kind === "choice") {
    const opts = f.kind === "comp" ? [...(S.comps?.[(path.match(/^msds\[(\d+)\]/) || [0, "0"])[1]] || []), ...(f.empty || [])] : f.options;
    const c = String(plain(cur) || (cur === "" ? "" : "null"));
    const known = opts.some(([v]) => v === c);
    return `<select id="${id}" data-path="${h(path)}"><option value="">— 고르세요 —</option>${known || !c ? "" : `<option value="${h(c)}" selected>지금 값: ${h(c)} (목록에 없음)</option>`}`
      + opts.map(([v, l]) => `<option value="${h(v)}" ${v === c ? "selected" : ""}>${h(l)}</option>`).join("") + `</select>` + pv;
  }
  if (f.kind === "stmt") {
    let o = {}; try { o = JSON.parse(plain(cur)) || {}; } catch {}
    return `<input id="${id}_k" data-path="${h(path)}" placeholder="소제목 (원문에 '소제목 : 내용' 꼴일 때만. 없으면 비움)" value="${h(o.key ?? "")}">
      <textarea id="${id}" data-path="${h(path)}" rows="2" placeholder="내용 (원문 그대로)">${h(o.value ?? "")}</textarea>` + pv;
  }
  if (f.kind === "obj") {
    let o = {}; try { o = JSON.parse(plain(cur)) || {}; } catch {}
    return `<div class="sub">` + f.fields.map(([k, l, sf]) => `<label>${h(l)}${sf && sf.kind === "choice"
      ? `<select id="${id}_${k}" data-path="${h(path)}"><option value=""></option>${sf.options.filter(([v]) => v !== "null").map(([v, t]) => `<option value="${h(v)}" ${String(o[k] ?? "") === v ? "selected" : ""}>${h(t)}</option>`).join("")}</select>`
      : `<input id="${id}_${k}" data-path="${h(path)}" value="${h(o[k] ?? "")}">`}</label>`).join("") + `</div>` + pv;
  }
  const ph = {q: "원문 표기 그대로 (예: > 2000 mg/kg, 10~20 %, 자료없음). 숫자·단위·상태는 화면이 나눕니다",
    list: "한 줄에 하나씩", number: "숫자만 (예: 96, 0.5)", text: "원문 그대로"}[f.kind];
  const t = curText(f, cur);
  return (f.kind === "number" || f.kind === "q" ? `<input id="${id}" data-path="${h(path)}" placeholder="${h(ph)}" value="${h(t)}">`
    : `<textarea id="${id}" data-path="${h(path)}" rows="2" placeholder="${h(ph)}">${h(t)}</textarea>`) + pv;
}
function readInput(f, id, orig) {       // 입력칸 → 검수표에 보낼 글 (서버가 칸 모양대로 바꾸고 검사한다)
  if (f.kind === "stmt") {
    let o = {}; try { o = JSON.parse(plain(orig)) || {}; } catch {}
    const v = $("#" + id).value.trim(), k = $("#" + id + "_k").value.trim();
    if (!v) return "";
    const base = {seq: null, key: null, value: null, refs: null, cond: null, std_code: null, match_score: null, text: null, ...o};
    return JSON.stringify({...base, key: k || null, value: v, text: ($("#e_src")?.value.trim() || base.text || (k ? k + " " + v : v))});
  }
  if (f.kind === "obj") {
    const o = Object.fromEntries(f.fields.map(([k]) => [k, $(`#${id}_${k}`).value.trim() || null]));
    return Object.values(o).some(x => x !== null) ? JSON.stringify(o) : "";
  }
  return $("#" + id).value.trim();
}
let pvT = 0;
function preview(el) {                  // 저장 전에 '저장될 값'을 보여 주고, 틀리면 이유를 바로 알린다
  const ed = el.closest("[data-f]"); if (!ed) return;
  const id = ed.dataset.f, path = ed.dataset.path, f = JSON.parse(ed.dataset.form), out = $("#" + id + "_pv");
  clearTimeout(pvT);
  pvT = setTimeout(async () => {
    const v = readInput(f, id, ed.dataset.orig || "");
    if (!out) return;
    if (!v) { out.innerHTML = ""; return; }
    try { const j = await api("/api/preview?" + new URLSearchParams({path, v})); out.className = "pv ok"; out.textContent = "저장될 값: " + (j.text ?? j.cell); }
    catch (e) { out.className = "pv bad"; out.textContent = "✖ " + e.message; }
  }, 250);
}
function field(f, path, id, cur, label, orig) {
  return `<div class="fld" data-f="${id}" data-path="${h(path)}" data-form="${h(JSON.stringify(f))}" data-orig="${h(orig ?? "")}"><label>${h(label)}</label>${input(f, path, id, cur)}</div>`;
}
const PICK = `<p class="help">왼쪽 사진에서 원문 줄을 누르면, 마지막으로 누른 입력칸(처음엔 근거 줄)에 그 글자가 들어가고 쪽도 채워집니다. Shift를 누른 채 누르면 이어 붙입니다.</p>`;
const SRC = (src, pg) => `<label>근거 줄 (필수. 값이 적힌 원문 줄 그대로)</label><textarea id="e_src" rows="2">${h(src)}</textarea>
    <label>쪽 (필수)</label><input id="e_pg" value="${h(pg)}">`;
// 골드 규칙: 목록 항목 안의 줄 하나라도 '삭제'면 그 항목 전체가 골드에서 빠진다(build_gold._assemble). 칸 하나만 지우려는 사람에게 알리고 '비움'을 준다
const partOf = r => { const p = r["경로"].replace(/^msds\[\d+\]\./, ""); return p.includes("[") && !p.endsWith("]"); };   // 목록 항목 안의 한 칸 (항목 자체인 한 칸은 아님)
const kids = item => !item.endsWith("]") ? 0   // 골드(_assemble)가 항목째 빼는 것은 목록 항목뿐: 그 아래 카드 수 (목록 항목이 아닌 카드는 칸만 지워지고 아래 카드는 남는다)
  : [...byKey.keys()].filter(k => k !== item && (k.startsWith(item + ".") || k.startsWith(item + "["))).length;
const canBlank = r => formOf(r["경로"]).blank != null;   // 칸 모양별 빈 값(null·[]·"")이 있나 (서버 _form의 blank)
function dropWarn(r) {
  const n = kids(gkey(r["경로"]));
  return `이 칸을 지우면 이 항목(카드)${n ? `과 하위 항목 카드 ${n}장이 함께` : " 전체가"} 골드에서 빠져요. 이 칸만 틀렸으면 맞는 값으로 고치세요.`
    + (canBlank(r) ? " 원문에 없는 칸이면 ‘비움으로 저장’을 누르세요 (이 칸만 비고 항목은 남아요)." : " 이 칸은 비울 수 없어요.")
    + " 항목 전체가 원문에 없으면 카드의 ‘원문에 없어요’를 쓰세요.";
}
const dropHelp = r => partOf(r) ? `<p class="help bad">⚠ ${h(dropWarn(r))}</p>` : "";
const emptyBtn = r => partOf(r) && canBlank(r) ? `<button data-a="save_empty" title="이 칸만 비우고 항목은 골드에 남겨요">비움으로 저장</button>` : "";
let itemForm = null;                    // 빠진 칸·항목 추가: 서버가 칸 이름과 입력 방식을 준다(경로는 사람이 쓰지 않는다)
function editor(r, kind) {
  const t = tags.includes("Claude") ? "Claude" : tags[0];
  if (kind === "edit") {
    const f = formOf(r["경로"]), fx = fixedRow(r);     // 처음 값은 지금 값: 고친 줄만 수정값·수정 근거·수정 쪽 (채택 줄에 엑셀로 남은 수정값은 보지 않는다)
    return `<div class="ed">${PICK}${field(f, r["경로"], "e_val", fx ? r["수정값"] : r[t + " 값"], "맞는 값", r[t + " 값"])}
    ${SRC((fx && r["수정 원문 조각"]) || r[t + " 원문 조각"], (fx && r["수정 쪽"]) || r[t + " 쪽"] || page || "")}
    <label>메모 (선택)</label><input id="e_memo" value="${h(r["메모"])}">${dropHelp(r)}
    <div class="acts"><button class="on" data-a="save_edit">저장 (${MOD}+Enter)</button>${emptyBtn(r)}<button data-a="edit_del" title="AI가 원문에 없는 값을 지어냈을 때">${partOf(r) ? "이 칸 삭제(항목 전체가 빠져요)" : "이 칸은 원문에 없어요(삭제)"}</button><button data-a="close">닫기</button></div></div>`;
  }
  if (kind === "del") return `<div class="ed"><label>삭제 이유 (필수. 예: 원문에 없는 값)</label><input id="e_memo" value="${h(r["메모"])}">${dropHelp(r)}
    <div class="acts"><button class="on" data-a="save_del">삭제로 저장</button>${emptyBtn(r)}<button data-a="close">닫기</button></div></div>`;
  if (kind === "opinion") return `<div class="ed"><label>의견 (무엇이 왜 틀렸는지, 맞는 값)</label><textarea id="e_val" rows="3"></textarea>
    <div class="acts"><button class="on" data-a="copy_op">의견 복사 (디스코드에 붙여 넣기)</button><button data-a="close">닫기</button></div></div>`;
  if (kind === "memo") return `<div class="ed"><label>메모</label><input id="e_memo" value="${h(r["메모"])}">
    <div class="acts"><button class="on" data-a="save_memo">메모 저장</button><button data-a="close">닫기</button></div></div>`;
  if (kind === "add") {
    const F = itemForm;
    if (!F || F.item !== open.g) return `<div class="ed"><p class="help">칸 목록을 불러오는 중…</p></div>`;
    if (F.error) return `<div class="ed"><p class="pv bad">${h(F.error)}</p></div>`;
    const modes = [F.missing.length && ["field", "이 카드에 빠진 칸", "문장에 있어야 할 칸 하나가 비었을 때"],
      F.new && ["new", "같은 종류 새 줄(AI가 통째로 빠뜨림)", "원문에 같은 종류 줄이 더 있는데 카드가 아예 없을 때"],
      ...(F.lists || []).map((x, i) => ["list" + i, `새 ${x.label}`, `이 카드에 ${x.label} 하나를 더 넣을 때`]),
      F.extra && ["extra", "표에 맞는 자리가 없는 내용", "원문 내용이 표의 어느 칸에도 맞지 않을 때"]].filter(Boolean);
    if (!modes.length) return `<div class="ed"><p class="help">이 카드에는 더 넣을 칸이 없습니다.</p><div class="acts"><button data-a="close">닫기</button></div></div>`;
    const m = F.mode || modes[0][0], g = open.g;
    let body = "";
    if (m === "field") {
      const k = F.pick ?? F.missing[0].name, x = F.missing.find(y => y.name === k);
      body = `<label>빠진 칸</label><select id="e_field">${F.missing.map(y => `<option value="${h(y.name)}" ${y.name === k ? "selected" : ""}>${h(y.label)}</option>`).join("")}</select>`
        + field(x.form, `${g}.${x.name}`, "e_val", "", "값");
    } else if (m === "extra") {
      body = `<p class="help">원문 내용이 표의 어느 칸에도 맞지 않을 때만 씁니다. 맞는 칸이 있으면 위의 다른 단추를 쓰세요.</p>
        <label>MSDS 항 번호</label><input id="e_x_sec" value="${h(F.extra.section)}">
        <label>원문 항목 제목 (예: MARPOL 73/78 부록 II 및 IBC 코드에 따른 벌크 운송)</label><input id="e_x_title">`
        + field({kind: "stmt"}, g.match(/^msds\[\d+\]/)[0] + ".extras[*].statements[*]", "e_val", "", "내용");
    } else {
      const N = m.startsWith("list") ? F.sub : F.new, gp = m.startsWith("list") ? F.lists[Number(m.slice(4))].item : g;
      if (!N) body = `<p class="help">칸 목록을 불러오는 중…</p>`;
      else if (N.error) body = `<p class="pv bad">${h(N.error)}</p>`;
      else if (N.single) body = field(N.single.form, gp, "e_val", "", N.single.label);
      else body = `<p class="help">★ 칸은 항목을 가르는 칸입니다(하나 이상 필수). '(채점 필수)' 칸은 원문에 있으면 꼭 채우세요. 원문에 없는 칸은 비워 두세요.</p>`
        + N.fields.map(x => field(x.form, `${gp}.${x.name}`, "e_n_" + x.name, "", (x.key ? "★ " : "") + x.label)).join("")
        + (N.fields.some(x => x.name === "seq") ? `<p class="help">순번은 원문 목록에서의 차례예요. 화면은 같은 목록의 순번끼리만 확인해요 (원문 위치는 확인하지 못해요).</p>` : "");
    }
    return `<div class="ed">${modes.length > 1 ? `<p class="help">어떤 것이 빠졌나요?</p><div class="modes">${modes.map(([k, l, d]) => `<button data-a="add_mode" data-m="${k}" class="${k === m ? "on" : ""}">${h(l)}<small>${h(d)}</small></button>`).join("")}</div>` : `<p class="help">${h(modes[0][1])}: ${h(modes[0][2])}</p>`}
    ${PICK}${body}${SRC("", page || "")}
    <label>메모 (선택)</label><input id="e_memo">
    <div class="acts"><button class="on" data-a="save_add">누락 추가로 저장</button><button data-a="close">닫기</button></div></div>`;
  }
  return "";
}
function renderCards() {
  const list = S.rows.map((r, i) => [r, i]).filter(([r]) => visible(r) && pagesOf(r).includes(page));
  groups = new Map(); byKey = new Map();
  for (const r of S.rows) { const k = gkey(r["경로"]); byKey.has(k) ? byKey.get(k).push(r) : byKey.set(k, [r]); }
  RANK = new Map();     // 목록 항목 경로(…[k=…])마다 그 안 칸 가운데 가장 앞선 실버 순서
  for (const [p, n] of Object.entries(S.rank || {}))
    for (const m of p.matchAll(/\]/g)) { const k = p.slice(0, m.index + 1); if (!(RANK.get(k) <= n)) RANK.set(k, n); }
  for (const it of list) { const k = gkey(it[0]["경로"]); groups.has(k) ? groups.get(k).push(it) : groups.set(k, [it]); }
  for (const items of groups.values()) items.sort(([a], [b]) => byDoc(a["경로"], b["경로"]));
  const hint = mode === "교차" ? "보기 전용입니다. 1순위 줄을 원문과 대조하고, 의견이 있으면 '의견 남기기'로 복사해 디스코드의 문서별 스레드에 붙여 넣으세요. 검수표는 검수 담당이 고칩니다 (역할 A 가이드 4.6)." + (detail ? "" : " '의견 남기기'는 '자세히(칸별)'에 있어요.") :
    !detail ? "카드를 누르면 왼쪽 사진에 노란 줄과 칩 색 상자가 켜져요. 칩을 누르면 짧은 풀이가 나와요. 뜻이 같으면 '✓ 같아요', 틀린 칩이 있으면 '✗ 다른 칩이 있어요', 원문에 아예 없으면 '원문에 없어요'를 눌러 주세요." :
    "칸을 누르면 왼쪽 사진에 위치가 표시됩니다(노란 상자 = 근거 줄, 주황 테두리 = 값). 파란 점선 = 어떤 칸의 근거로도 쓰이지 않은 원문 줄(AI가 빠뜨렸을 수 있음 → 그 항목 카드의 '빠진 칸·항목 추가'). 맞으면 '맞음', 틀리면 '수정'(정해진 값은 목록에서 고르고, 저장 전에 '저장될 값'을 확인), 원문에 없는 값이면 '삭제'. 누르면 바로 검수표에 저장됩니다. 칸 순서는 문서에 적힌 순서입니다. '1번째', '7번 성분 (CAS)' 같은 칸은 원문 글자가 아니라 줄끼리 잇는 번호라, 카드 제목과 맞으면 '맞음'입니다.";
  let last = "";        // 항이 바뀌는 자리에 항 제목을 넣는다
  const head = ([m, s]) => { const id = m + "|" + s; if (id === last) return ""; last = id;
    return `<h2 class="sechd">${h(S.sections?.[s] ?? "검수 범위 밖")}${m ? ` <span class="lbl">(MSDS ${m + 1}번째)</span>` : ""}</h2>`; };
  $("#right").innerHTML = `<p class="help">${hint}</p>` + (list.length ? [...groups].map(([k, it]) => [k, it, cardKey(k, it)]).sort(cardCmp).map(([k, items, key]) => head(key) + (asSentence(k, items) ? sentenceCard(k, items)
      : (!detail && S.cards?.[k] && dual(k) ? `<p class="help">두 AI 값이 달라 칸별로 보여 드려요</p>` : "") + card(k, items))).join("")
    : mustOnly && S.rows.some(r => passes(r, false) && pagesOf(r).includes(page))
      ? `<p class="none">필수 칸만 보는 중이라 이 쪽 카드가 숨겨져 있어요 <button data-a="allfields">모든 칸 보기</button></p>`
    : `<p class="none">${page ? page + "쪽에" : "여기에"} ${show === "todo" ? "남은 칸이 없습니다 ✔" : "칸이 없습니다"}</p>`);
  for (const p of sel) document.querySelector(`.ln[data-p="${CSS.escape(p)}"]`)?.classList.add("sel");
  if (open && !keepFocus) { const el = $("#e_val") || $("#e_memo"); if (el) el.focus(); lastIn = null; }   // 양식을 처음 열 때만 (사진에서 고른 글자는 처음엔 원문 조각으로)
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
  const o = S.order?.[it[0][0]["경로"]] || [999], pre = k.match(/^msds\[\d+\]\.?/)?.[0] || "", body = k.slice(pre.length);
  const out = [Number(pre.match(/\d+/)?.[0] ?? 0), ...(S.sec?.[it[0][0]["경로"]] || [99, 0])];   // 다중 MSDS는 건 번호부터, 그다음 항 순서(1·2·3·8·…)와 항 안 종류(정해진 칸 → 서술 → 미정의)
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
const VIEW = ["cards", "explain", "order", "sec", "spec", "forms", "must"];   // 서버 _view가 주는, 줄에서 나오는 화면 상태
let keepFocus = false;                 // apply가 다시 그릴 때: 열린 양식으로 포커스를 옮기지 않는다 (치던 칸·커서·스크롤을 되살린다)
function apply(j, act, light) {        // 줄을 바꾼 모든 길(저장·삭제·추가·되돌리기·교차 확인)의 응답(_update)을 화면 상태에 반영하는 단 하나의 함수.
                                       // light: 교차 확인 반영처럼 판단이 아닌 변화 (남은 칸 자리·되돌리기는 그대로)
  const op = open && open.i >= 0 ? S.rows[open.i]?.["경로"] : null;
  const touched = [...j.rows.map(r => r["경로"]), ...j.gone], tk = new Set(touched.map(gkey));
  const before = new Map(S.rows.map(r => [r["경로"], curCell(r)]));
  S.rows = S.rows.filter(r => !j.gone.includes(r["경로"]));
  for (const row of j.rows) {
    const idx = S.rows.findIndex(x => x["경로"] === row["경로"]);
    idx < 0 ? S.rows.push(row) : S.rows[idx] = row;
    if (!light) keep.add(row["경로"]);
  }
  if (j.keys) {                         // 이 카드들만: 그 카드의 옛 상태를 지우고 새 것을 넣는다 (없어진 카드는 지운다)
    for (const p of [...j.gone, ...S.rows.filter(r => tk.has(gkey(r["경로"]))).map(r => r["경로"])]) for (const f of VIEW.slice(1)) delete S[f][p];
    for (const k of j.keys) { if (j.cards[k]) S.cards[k] = j.cards[k]; else delete S.cards[k]; }
    for (const f of VIEW.slice(1)) Object.assign(S[f], j[f]);
  } else for (const f of VIEW) S[f] = j[f];   // 다른 카드가 기대는 줄(성분표·순번)이 바뀜: 문서의 모든 카드
  S.comps = j.comps; S.names = j.names;
  if (!light) for (const k of tk) cardActs.delete(k);   // 카드 판단 뒤 다른 길로 고친 카드는 되돌리기가 그것까지 지우지 않게 단추를 없앤다
  if (act) cardActs.set(...act);
  if (open && !light) {                 // 바뀐 카드의 양식만 닫는다 (다른 카드에 적던 양식은 그대로)
    const g = open.g ?? (op && gkey(op));
    if (!g || tk.has(g)) { open = null; itemForm = null; }
    else if (op) { open.i = S.rows.findIndex(r => r["경로"] === op); if (open.i < 0) open = null; }
  }
  const typed = open ? [...document.querySelectorAll(".ed input[id], .ed textarea[id], .ed select[id]")].map(x => [x.id, x.value]) : [];
  const pvs = [...document.querySelectorAll(".ed .pv[id]")].map(x => [x.id, x.className, x.textContent]);   // '저장될 값' 글도 그대로 (나중에 채워지며 칸이 밀리지 않게)
  const ae = document.activeElement, fid = open && ae?.id && ae.closest(".ed") ? ae.id : "", li = lastIn?.id || "", st = $("#right").scrollTop;
  const sel0 = fid && typeof ae.selectionStart === "number" ? [ae.selectionStart, ae.selectionEnd] : null, top0 = fid ? ae.getBoundingClientRect().top : 0;
  $("#saved").textContent = "저장됨 " + new Date().toLocaleTimeString("ko-KR");
  keepFocus = true; render(); keepFocus = false;
  for (const [id, v] of typed) { const x = document.getElementById(id); if (x) x.value = v; }   // 열어 둔 다른 카드 양식에 적던 글은 그대로
  for (const [id, c, t] of pvs) { const x = document.getElementById(id); if (x) { x.className = c; x.textContent = t; } }
  const x = fid && document.getElementById(fid);
  $("#right").scrollTop = st;
  if (x) {                              // 치던 칸·커서 자리 그대로. 포커스를 준 뒤, 위 카드 높이가 바뀌었어도 그 칸이 화면에서 제자리가 되게 목록을 맞춘다
    x.focus({preventScroll: true}); if (sel0) x.setSelectionRange(...sel0);
    $("#right").scrollTop += x.getBoundingClientRect().top - top0;
  }
  lastIn = li ? document.getElementById(li) : null;
  if (typed.length && $("#e_val")) preview($("#e_val"));
  if (loc.key && tk.has(loc.key)) {     // 보던 카드: 없어졌으면 사진 표시를 지우고, 값·줄이 바뀌었으면 위치·숨긴 칸 확인을 새로
    if (!S.cards[loc.key] && !rowsOf(loc.key).length) highlight([]);
    else if (j.gone.length || touched.some(p => before.get(p) !== curCell(S.rows.find(r => r["경로"] === p) || {}))) highlight(cardPaths(loc.key), loc.key);
  }
}
let saving = false;                    // 줄 저장을 처리하는 중: 저장 단추를 잠근다 (두 번 눌러 엇갈리지 않게)
async function locked(fn) {
  if (saving) { toast("저장하는 중이에요. 끝나면 다시 눌러 주세요", true); return false; }
  saving = true; document.body.classList.add("saving");
  try { return await fn(); } finally { saving = false; document.body.classList.remove("saving"); }
}
const save = (r, values, msg) => locked(async () => {
  try {
    const j = await api("/api/save", {"경로": r["경로"], values});
    if (values["검수 결과"] === "수정" && j.rows[0]["검수 결과"] !== "수정") msg = "바뀐 것이 없어 ‘맞음’으로 저장했어요";
    if (msg) toast(msg);
    apply(j);
  } catch (e) { toast(e.message, true); }
});
const saveMany = (items, msg, act) => !items.length ? Promise.resolve(false) : locked(async () => {   // 저장했으면 true. act: [카드, 판단 전 줄] (카드 판단이면 되돌리기용)
  try {
    const j = await api("/api/save_many", {items});
    toast(msg); apply(j, act);
    return true;
  } catch (e) { toast(e.message, true); return false; }
});
const who = me => ({"검수자": me});
const busy = new Set();                // 판단·되돌리기를 처리하는 중인 카드
const gone = [];                       // 이 쪽에서 지운, 직접 넣은 줄만 있던 카드의 줄들 (카드가 없어져 위쪽 막대에서 되돌린다)
async function cardAct(g, a) {
  if (a === "card_undo") {                            // 카드 판단만 되돌린다: 판단 전 사람 열을 원래 셀 값 그대로 (지운 누락 추가 줄은 다시 넣음)
    const prev = cardActs.get(g) || [];
    let j; try { j = await api("/api/restore", {items: prev}); }
    catch (err) { return toast("되돌리지 못했어요: " + err.message, true); }   // 데이터·되돌리기 단추는 그대로
    apply(j);                                         // 다시 넣은 줄·바뀐 값으로 카드를 새로 (되돌리기 단추는 없어진다)
    return toast(`카드 판단을 되돌렸어요 (${prev.length}칸)`);
  }
  if (a === "same" && !seenCards.has(g)) return toast("먼저 카드를 눌러 왼쪽 위치를 보세요", true);   // 문장 카드 판단: 아직 판정하지 않은 줄만 (이미 판정한 줄은 그대로)
  const me = needName(); if (!me) return;
  // 원문에 없는 항목이면 이미 고친 칸도 뜻이 없다: 판정한 줄까지 삭제 (반쪽 항목을 남기지 않는다)
  const todo = rowsOf(g).filter(r => a === "absent" ? r["검수 결과"] !== "삭제" : !r["검수 결과"] && mainTag(r));
  if (!todo.length) return;
  const mine = todo.filter(r => r["검수 결과"] === "누락 추가" && !r["일치"]), rest = todo.filter(r => !mine.includes(r));   // 사람이 넣은 줄은 '삭제' 대신 줄을 지운다 (골드 경고 막기)
  const done = rest.filter(r => r["검수 결과"]).length, fixed = todo.some(r => /^(수정|누락 추가)$/.test(r["검수 결과"]));
  if (a === "absent" && !confirm(!rest.length   // 사람이 넣은 줄만 있는 카드: 지우면 카드가 없어져 되돌리기는 위쪽 막대에서
    ? `이 카드의 직접 넣은 ${mine.length}칸을 지울까요?\n이 쪽을 보는 동안은 위쪽 ‘방금 지운 카드 되돌리기’로 되돌릴 수 있어요.`
    : `이 카드의 ${todo.length}칸을 '원문에 없음'으로 삭제할까요?` + (done ? `\n이미 확인한 ${done}칸도 함께 삭제돼요.` : "")
      + (mine.length ? `\n직접 넣은 ${mine.length}칸은 줄을 지워요.` : "") + (kids(g) ? `\n하위 항목 카드 ${kids(g)}장도 함께 골드에서 빠져요.` : "") + `\n${fixed ? "고친 값은 지워지고, " : ""}되돌리기는 이 쪽을 보는 동안만 할 수 있어요.`)) return;
  fixing = null; cardH.set(g, document.querySelector(`.card.sc[data-g="${CSS.escape(g)}"]`)?.offsetHeight || 0);
  const before = todo.map(r => ({...r}));            // 되돌리기용: 판단 전 줄 전체 (원래 셀 값 _raw 포함)
  if (rest.length && !await saveMany(rest.map(r => ({"경로": r["경로"], values: a === "same" ? {"검수 결과": mainTag(r) + " 채택", ...who(me)}
    : {"검수 결과": "삭제", "메모": r["메모"] || "원문에 없음", "수정값": "", "수정 원문 조각": "", "수정 쪽": "", ...who(me)}})),
    a === "same" ? "카드를 저장했어요" : "‘원문에 없음’으로 저장했어요", [g, before])) return;
  if (!mine.length) return;
  let j; try { j = await api("/api/remove", {"경로": mine.map(r => r["경로"])}); }   // 한 번에 지운다: 실패하면 한 줄도 지우지 않는다
  catch (err) { return toast(err.message, true); }
  if (rest.length) return apply(j, [g, before]);      // 섞인 카드: 되돌리기가 지운 줄까지 다시 넣는다
  gone.push(before); renderGone(); apply(j);          // 직접 넣은 줄만 있던 카드는 없어진다: 위쪽 막대에서 되돌린다
  toast("직접 넣은 줄을 지웠어요. 위쪽 ‘방금 지운 카드 되돌리기’로 되돌릴 수 있어요");
}
function renderGone() { $("#gonebtn").hidden = !gone.length; $("#gonebtn").title = `이 쪽에서 지운 카드 ${gone.length}장 가운데 마지막 카드를 다시 넣어요`; }
$("#gonebtn").onclick = async () => {
  const prev = gone.at(-1); if (!prev || busy.has("gone")) return;
  busy.add("gone");
  try { const j = await api("/api/restore", {items: prev}); gone.pop(); renderGone(); apply(j); toast(`지운 카드를 되돌렸어요 (${prev.length}칸)`); }
  catch (err) { toast("되돌리지 못했어요: " + err.message, true); }
  finally { busy.delete("gone"); }
};
$("#right").addEventListener("click", async e => {
  const src = e.target.closest(".src"); if (src) return src.classList.toggle("full");
  const b = e.target.closest("button[data-a]"), ln = e.target.closest(".ln, .fix"), cd = e.target.closest(".card");
  if (b?.dataset.a === "allfields") return $("#mustbtn").click();
  const chip = e.target.closest(".chip");
  if (chip && cd) return chipClick(cd.dataset.g, chip.dataset.p);
  if (!e.target.closest(".ed, .fix, button, summary")) {   // 칸이나 묶음 제목을 누르면 사진에 위치 표시 (카드 안 수정 양식 줄은 빼고)
    if (ln) return highlight([ln.dataset.p]);
    if (cd?.classList.contains("sc")) return highlight(cardPaths(cd.dataset.g), cd.dataset.g);
    if (cd) return highlight((groups.get(cd.dataset.g) || []).map(([r]) => r["경로"]));
  }
  if (!b) return;
  const g = cd.dataset.g, a = b.dataset.a;
  if (!ln) {                                            // 묶음 단추
    const items = groups.get(g) || [];
    if (a === "add") {
      open = open && open.g === g ? null : {g, kind: "add"}; renderCards();
      if (!open) return;
      try { itemForm = {item: g, ...(await api("/api/item_form?" + new URLSearchParams({item: g})))}; }
      catch (err) { itemForm = {item: g, error: err.message}; }
      return renderCards();
    }
    if (a === "add_mode") {
      itemForm.mode = b.dataset.m; itemForm.sub = null; renderCards();
      if (b.dataset.m.startsWith("list")) {                  // 비어 있는 하위 목록(연락처 등)의 새 항목 칸
        const it = itemForm.lists[Number(b.dataset.m.slice(4))].item;
        try { itemForm.sub = (await api("/api/item_form?" + new URLSearchParams({item: it}))).new; }
        catch (err) { itemForm.sub = {error: err.message}; }
        renderCards();
      }
      return;
    }
    if (["same", "absent", "card_undo"].includes(a)) {   // 처리하는 동안 이 카드 단추는 잠근다 (두 번 눌러 판단·되돌리기가 엇갈리지 않게)
      if (busy.has(g)) return;
      busy.add(g); redraw(g);
      try { await cardAct(g, a); } finally { busy.delete(g); redraw(g); }
      return;
    }
    if (a === "undrop") {                               // 빠지는 항목 되살리기: 그렇게 만든 칸을 미검수로 (판단·고친 값·검수자를 지운다, 메모는 남김)
      const by = S.cards[g]?.drop?.by || [];
      return saveMany(by.map(p => ({"경로": p, values: {"검수 결과": "", "수정값": "", "수정 원문 조각": "", "수정 쪽": "", "검수자": ""}})), `삭제한 칸 ${by.length}개를 미검수로 되돌렸어요`);   // 미검수 줄이니 검수자도 비운다
    }
    if (a === "goto") {                                 // 상위 항목 카드로: 그 쪽으로 가서 카드를 보이게 하고 강조
      const k = b.dataset.k, rs = rowsOf(k), pg = rs.some(r => pagesOf(r).includes(page)) || !rs.length ? page : pagesOf(rs[0])[0];   // 상위 카드가 이 쪽에도 있으면 쪽을 옮기지 않는다
      if (pg !== page) go(pg);
      for (const r of rs) keep.add(r["경로"]);
      renderCards();
      const el = document.querySelector(`.card[data-g="${CSS.escape(k)}"]`);
      el?.scrollIntoView({block: "center"});
      return highlight(S.cards?.[k] && el?.classList.contains("sc") ? cardPaths(k) : rs.map(r => r["경로"]), el?.classList.contains("sc") ? k : undefined);
    }
    if (a === "fix") {                                  // 고치기: 칩을 누르면 그 줄의 수정 양식. 질문 카드는 예·아니오 줄을 바로 연다
      fixing = fixing === g ? null : g; open = null;
      const yn = chipsOf(g).filter(p => { const r = rowsOf(g).find(x => x["경로"] === p.path); return r && /^(true|false)$/.test(plain(r[(mainTag(r) || "Claude") + " 값"])); });
      if (fixing && S.cards[g].type === "question" && yn.length === 1) { pick = {key: g, path: yn[0].path}; open = {i: S.rows.findIndex(r => r["경로"] === yn[0].path), kind: "edit"}; }
      return renderCards();
    }
    if (a === "adopt_all") {
      const me = needName(); if (!me) return;
      const todo = items.map(([r]) => r).filter(r => !r["검수 결과"] && mainTag(r));
      return saveMany(todo.map(r => ({"경로": r["경로"], values: {"검수 결과": mainTag(r) + " 채택", ...who(me)}})), `${todo.length}칸을 맞음으로 저장했습니다`);
    }
  }
  const i = ln ? Number(ln.dataset.i) : -1, r = ln ? S.rows[i] : null;      // 묶음 편집기(빠진 항목 추가)는 줄 밖에 있다
  if (ln?.classList.contains("ln") && (ln.dataset.p !== sel[0] || sel.length !== 1)) highlight([ln.dataset.p]);
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
    try { apply(await api("/api/remove", {"경로": r["경로"]})); toast("누락 추가 줄을 지웠습니다"); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (a === "undo") return save(r, {"검수 결과": "", "수정값": "", "수정 원문 조각": "", "수정 쪽": ""}, "미검수로 되돌렸습니다");
  if (a === "save_edit") {
    const v = readInput(formOf(r["경로"]), "e_val", r[(tags.includes("Claude") ? "Claude" : tags[0]) + " 값"]);
    if (!v) {                                   // 빈 값 안내는 칸 모양대로 (목록 항목 안 칸은 삭제로 이끌지 않는다: 항목 전체가 빠진다)
      const f = formOf(r["경로"]);
      return toast(partOf(r) ? (canBlank(r) ? "값을 비우려면 ‘비움으로 저장’을 눌러 주세요 (이 칸만 비고 항목은 골드에 남아요)" : "이 칸은 비울 수 없어요. 맞는 값을 적어 주세요")
        : (/choice|comp/.test(f.kind) ? `목록에서 값을 고르세요.${canBlank(r) ? " 원문에 적힌 것이 없으면 '비움'을 고르세요." : ""} ` : "맞는 값을 적어 주세요. ")
          + "원문에 아예 없는 값이면 아래 ‘이 칸은 원문에 없어요(삭제)’ 단추를 눌러 주세요", true);
    }
    if (!$("#e_src").value.trim() || !$("#e_pg").value.trim()) return toast("근거 줄과 쪽도 적어 주세요", true);
    return save(r, {"검수 결과": "수정", "수정값": v, "수정 원문 조각": $("#e_src").value, "수정 쪽": $("#e_pg").value, "메모": $("#e_memo").value, ...who(me)});
  }
  if (a === "save_del" && !$("#e_memo").value.trim()) return toast("삭제 이유를 메모에 적어 주세요", true);   // 확인창보다 먼저
  if (["edit_del", "save_del"].includes(a) && partOf(r) && !confirm(dropWarn(r) + "\n\n그래도 이 칸을 삭제할까요?")) return;
  if (a === "save_empty") {                     // 이 칸만 비움(칸 모양별 빈 값 null·[]·""): 항목은 골드에 남는다. 근거는 양식의 근거 줄·쪽, 없으면 AI 근거
    const t = mainTag(r) || "Claude", src = $("#e_src")?.value.trim() || r[t + " 원문 조각"] || "원문에 적힌 값 없음";
    const pg = $("#e_pg")?.value.trim() || String(r[t + " 쪽"] || page || "");
    if (!pg) return toast("쪽을 적어 주세요", true);
    return save(r, {"검수 결과": "수정", "수정값": formOf(r["경로"]).blank, "수정 원문 조각": src, "수정 쪽": pg, "메모": $("#e_memo")?.value ?? r["메모"], ...who(me)},
      "‘비움’으로 저장했어요 (이 칸만 비고 항목은 골드에 남아요)");
  }
  if (a === "edit_del") return save(r, {"검수 결과": "삭제", "메모": $("#e_memo").value.trim() || "원문에 없음", "수정값": "", "수정 원문 조각": "", "수정 쪽": "", ...who(me)}, "‘원문에 없음’으로 저장했어요");
  if (a === "save_del") {
    const m = $("#e_memo").value.trim();
    if (!m) return toast("삭제 이유를 메모에 적어 주세요", true);
    return save(r, {"검수 결과": "삭제", "메모": m, "수정값": "", "수정 원문 조각": "", "수정 쪽": "", ...who(me)});
  }
  if (a === "save_memo") return save(r, {"메모": $("#e_memo").value}, "메모를 저장했습니다");
  if (a === "save_add") {
    const F = itemForm, m = F.mode || (F.missing.length ? "field" : F.new ? "new" : (F.lists || []).length ? "list0" : "extra"), fields = {};
    let item = open.g, mode = m;
    if (m === "field") { const k = $("#e_field").value, x = F.missing.find(y => y.name === k); fields[k] = readInput(x.form, "e_val", ""); }
    else if (m === "extra") Object.assign(fields, {section_no: $("#e_x_sec").value, title_raw: $("#e_x_title").value, "": readInput({kind: "stmt"}, "e_val", "")});
    else {
      const N = m.startsWith("list") ? F.sub : F.new;
      if (m.startsWith("list")) { item = F.lists[Number(m.slice(4))].item; mode = "new"; }
      if (!N || N.error) return;
      if (N.single) fields[""] = readInput(N.single.form, "e_val", "");
      else for (const x of N.fields) fields[x.name] = readInput(x.form, "e_n_" + x.name, "");
    }
    if (!$("#e_src").value.trim() || !$("#e_pg").value.trim()) return toast("근거 줄과 쪽을 채워 주세요 (왼쪽 사진에서 줄을 누르면 채워집니다)", true);
    if (saving) return toast("저장하는 중이에요. 끝나면 다시 눌러 주세요", true);
    saving = true; document.body.classList.add("saving");
    try {
      const body = {item, mode, fields, values: {"수정 원문 조각": $("#e_src").value, "수정 쪽": $("#e_pg").value, "메모": $("#e_memo").value, "검수자": me}};
      let j = await api("/api/add_item", body);
      if (j.dup) {                       // '필수 칸만' 등으로 숨은 카드를 못 보고 같은 줄을 또 넣지 않게
        if (!confirm(j.dup === "same" ? "같은 내용의 카드가 이미 있어요(지금 보기에서 숨겨져 있을 수 있어요). 그래도 넣을까요?"
          : `같은 종류(${j.kind}) 카드가 이미 ${j.n}장 있어요. 값이 다르면 ‘확인’을 눌러 그대로 넣으세요`)) return;
        j = await api("/api/add_item", {...body, force: true});
      }
      open = null; itemForm = null;      // 넣기 양식은 닫는다 (새 항목은 다른 카드가 된다)
      apply(j);                          // 서버가 새 줄의 카드·항 자리를 만들어 준다 (새 줄도 제 항 아래 문장 카드로)
      toast(`빠진 칸 ${j.rows.length}개를 넣었어요` + (mustOnly && j.rows.some(x => !j.must[x["경로"]]) ? " (필수가 아닌 칸도 이 쪽을 떠나기 전까지 보여요)" : ""));
    } catch (err) { toast(err.message, true); }
    finally { saving = false; document.body.classList.remove("saving"); }
  }
});
let lastIn = null;           // 사진에서 고른 글자가 들어갈 입력칸
$("#right").addEventListener("input", e => preview(e.target));
$("#right").addEventListener("change", e => {
  if (e.target.id === "e_field") { itemForm.pick = e.target.value; return renderCards(); }
  preview(e.target);
});
for (const ev of ["focusin", "pointerdown"])   // 이미 커서가 있는 칸을 다시 눌러도 그 칸으로
  $("#right").addEventListener(ev, e => { if (e.target.matches(".ed input:not([type]), .ed textarea")) lastIn = e.target; });
$("#view").addEventListener("click", async e => {
  const img = e.target.closest(".pgw") && $("#view img"); if (!img) return;
  const rc = img.getBoundingClientRect(), x = (e.clientX - rc.left) / rc.width, y = (e.clientY - rc.top) / rc.height;
  if (!$(".ed #e_src")) {
    if ([...document.querySelectorAll("#unused .hl")].some(d => { const b = d.getBoundingClientRect(); return e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top - 4 && e.clientY <= b.bottom + 4; }))
      toast("점선 줄이 AI가 빠뜨린 값이면, 오른쪽에서 가장 관련 있는 카드의 '빠진 칸·항목 추가'를 연 다음 이 줄을 누르세요. 맞는 칸이 없으면 '표에 맞는 자리가 없는 내용'을 고릅니다");
    return;
  }
  let j; try { j = await api("/api/pick?" + new URLSearchParams({page, x, y})); } catch (err) { return toast(err.message, true); }
  if (!j.cell) return toast("그 자리에서 글자를 찾지 못했습니다. 글자 위를 눌러 주세요", true);
  const el = lastIn && document.body.contains(lastIn) ? lastIn : $("#e_src");
  const text = el.id === "e_src" ? j.line : j.cell;      // 원문 조각은 줄 전체, 값은 누른 칸만
  el.value = e.shiftKey && el.value.trim() ? el.value.trim() + " " + text : text;
  $("#e_pg").value = page; preview(el); el.focus();
});
$("#right").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { const b = $(".ed button.on"); if (b) b.click(); } });
function go(p) { page = p; open = null; sel = []; selSeq++; keep.clear(); cardActs.clear(); cardH.clear(); gone.length = 0; renderGone(); $("#notes").innerHTML = ""; loc = {}; pick = null; fixing = null; render(); $("#view").scrollTop = 0; $("#right").scrollTop = 0; }
$("#pager").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  const list = [...document.querySelectorAll("#pager [data-pg]")].map(x => Number(x.dataset.pg)), k = list.indexOf(page);
  if (b.dataset.pg !== undefined) return go(Number(b.dataset.pg));
  if (b.id === "prev" && k > 0) return go(list[k - 1]);
  if (b.id === "next" && k < list.length - 1) return go(list[k + 1]);
  if (b.id === "unusedbtn") { unusedOn = !unusedOn; store("unused", unusedOn ? "on" : "off"); renderPager(); return loadUnused(); }
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
  try { const j = await api("/api/cross", {name: name.trim()}); apply(j, null, true); toast(`1순위 ${j.count}줄에 교차 확인자 '${name.trim()}'을 적었습니다`); }
  catch (e) { toast(e.message, true); }
};
document.querySelectorAll("[data-p]").forEach(b => b.onclick = () => {
  const p = Number(b.dataset.p); prio.has(p) ? prio.delete(p) : prio.add(p); b.classList.toggle("on", prio.has(p)); render(); });
document.querySelectorAll("[data-s]").forEach(b => b.onclick = () => {
  show = b.dataset.s; document.querySelectorAll("[data-s]").forEach(x => x.classList.toggle("on", x === b)); render(); });
$("#mustbtn").onclick = e => { mustOnly = !mustOnly; e.target.classList.toggle("on", mustOnly); render(); };
$("#detailbtn").classList.toggle("on", detail);
$("#detailbtn").onclick = e => { detail = !detail; store("detail", detail ? "on" : "off"); e.target.classList.toggle("on", detail); open = null; renderCards(); };
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
// 첫 화면 사용법: 단계마다 실제 요소에 노란 테두리(.ring)를 두르고, 그 요소만 어두운 막 위로 올려 눌리게 한다
const TOUR = [
  ["처음 오셨네요", "이 화면은 <b>왼쪽 문서</b>와 <b>오른쪽 문장</b>이 같은 뜻인지 확인하는 곳이에요. 1분이면 됩니다.", null],
  ["① 왼쪽 노란 줄", "카드를 누르면 왼쪽 문서에서 AI가 읽은 줄이 <b>노랗게</b> 칠해져요. 이 줄이 기준입니다.", () => [$("#view")]],
  ["② 색 칩", "카드의 <b>색 칩</b>을 누르면 왼쪽의 같은 색 밑줄이 켜지고 짧은 풀이가 나와요. 지금 아무 칩이나 눌러 보세요.", () => [tourCard()]],
  ["③ 같으면 ‘같아요’", "뜻이 같으면 <b>✓ 같아요</b>, 틀린 칩이 있으면 <b>✗ 다른 칩이 있어요</b>, 원문에 아예 없으면 <b>원문에 없어요</b>를 누르세요.", () => [tourCard()], true],
  ["④ 파란 점선과 남은 필수 칸", "<b>파란 점선</b>은 어떤 카드도 쓰지 않은 줄이에요. AI가 빠뜨린 값이면 카드의 <b>빠진 칸·항목 추가</b>로 넣으세요. 위쪽에는 남은 <b>필수 칸</b> 수가 나와요.", () => [$("#unusedbtn"), $("#mustleft")]],
];
let tourAt = -1, tourG = "";
const tourCard = () => document.querySelector(`.card.sc[data-g="${CSS.escape(tourG)}"]`) || document.querySelector(".card.sc");
function tourRing() {
  document.querySelectorAll(".ring").forEach(x => { x.classList.remove("ring", "lock"); if (x.dataset.tp) { x.style.position = ""; delete x.dataset.tp; } });
  const t = TOUR[tourAt]; if (!t || !t[2]) return;
  for (const el of t[2]().filter(Boolean)) {
    if (getComputedStyle(el).position === "static") { el.style.position = "relative"; el.dataset.tp = "1"; }
    el.classList.add("ring"); if (t[3]) el.classList.add("lock");
  }
}
async function tour(i) {
  if (i < 0 || i >= TOUR.length) { tourAt = -1; tourRing(); $("#tour").style.display = $("#tourbg").style.display = "none"; store("tour", "done"); return; }
  if (i >= 1 && i <= 3 && !document.querySelector(".card.sc")) {   // 이 쪽에 문장 카드가 없으면 카드가 있는 첫 쪽으로
    for (const b of document.querySelectorAll("#pager [data-pg]")) { go(Number(b.dataset.pg)); if (document.querySelector(".card.sc")) break; }
  }
  const noCard = !document.querySelector(".card.sc");
  if (noCard && i >= 1 && i <= 3) return tour(i > tourAt ? 4 : 0);   // 카드가 전혀 없으면 카드 단계는 건너뜀
  const back = i < tourAt;
  tourAt = i; const t = TOUR[i];
  if (i === 1) { const c = document.querySelector(".card.sc"); tourG = c.dataset.g; if (!back) c.click(); }   // 사람이 누른 것과 같은 길
  $("#tour").style.display = "flex"; $("#tourbg").style.display = "block"; $("#tnext").classList.remove("pulse"); $("#tour").classList.toggle("low", !!t[2]); $("#tour").classList.toggle("side", i === 2 || i === 3);
  $("#tstep").textContent = `사용법 ${i + 1} / ${TOUR.length}`;
  $("#ttitle").textContent = t[0]; $("#tbody").innerHTML = t[1];
  $("#tdots").innerHTML = TOUR.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("");
  $("#tprev").style.visibility = i ? "visible" : "hidden";
  $("#tnext").textContent = i === TOUR.length - 1 ? "시작하기" : "다음";
  tourRing();
  if (t[2]) (t[2]().find(Boolean))?.scrollIntoView({block: "nearest"});
}
$("#tskip").onclick = () => tour(-1);
$("#tprev").onclick = () => tour(tourAt - 1);
$("#tnext").onclick = () => tour(tourAt + 1);
$("#tourbtn").onclick = () => tour(0);
document.addEventListener("keydown", e => { if (e.key === "Escape" && tourAt >= 0) { e.stopPropagation(); tour(-1); } }, true);
document.addEventListener("click", e => { if (tourAt === 2 && e.target.closest(".chip")) { $("#tbody").innerHTML = "잘 하셨어요! 풀이를 읽고 <b>다음</b>을 눌러 주세요."; $("#tnext").classList.add("pulse"); } }, true);   // 칩을 누르면 칭찬 글과 다음 단추 강조
new MutationObserver(() => { if (tourAt >= 0 && TOUR[tourAt][2] && !document.querySelector(".ring")) tourRing(); }).observe($("#right"), {childList: true, subtree: true});   // 카드가 다시 그려져도 테두리 유지
load().catch(e => toast("불러오지 못했습니다: " + e.message, true)).then(() => { if (store("tour") !== "done") tour(0); });
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
