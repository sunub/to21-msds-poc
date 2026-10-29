"""명세서 v0.6의 '13_TO21DB매핑' 시트를 셀 값 그대로 읽는다(적재 스크립트·시험 공용)."""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl

from msds.common.paths import to21_file

SHEET = "13_TO21DB매핑"
NCOL = 7


def read_sheet(xlsx: Path | None = None) -> list[tuple]:
    wb = openpyxl.load_workbook(xlsx or to21_file("spec"), read_only=True, data_only=True)
    out, section = [], None
    for i, row in enumerate(wb[SHEET].iter_rows(values_only=True), start=1):
        cells = tuple(row[:NCOL]) + (None,) * (NCOL - len(row))
        if any(len(row) > NCOL and v is not None for v in row[NCOL:]):
            raise SystemExit(f"{i}행에 {NCOL}열 밖 값이 있음 → NCOL 확인")
        if all(v is None for v in cells):
            continue
        if any(v is not None and not isinstance(v, str) for v in cells):
            raise SystemExit(f"{i}행에 글자가 아닌 셀이 있음 → 원형 보존 방법 확인 필요")
        if m := re.match(r"^([A-Z])\. ", cells[0] or ""):
            section = m.group(1)
        out.append((i, section, *cells))
    return out
