"""문서 목록(data/manifest.csv) 읽기·쓰기.

manifest는 모두가 같은 문서를 같은 이름으로 쓰도록 맞추는 기준표다.
원본 PDF는 data/raw/ 에 원래 파일 이름 그대로 두고, 문서 번호와의 연결은 이 표로 한다.
"""
from __future__ import annotations

import csv
import unicodedata
from pathlib import Path

from .paths import MANIFEST, RAW

# 열 순서는 바꾸지 않는다. 다른 역할의 코드가 이 이름으로 읽는다.
COLUMNS = [
    "doc_id",        # T21-025, T21-S016 ...
    "source_file",   # 원본 파일 이름(확장자 포함)
    "folder",        # 받은 폴더 (첫번째 / 두번째)
    "purpose",       # 개발 / 평가 / 기타  (D-34)
    "pages",         # 쪽수
    "text_layer",    # 정상 / 글꼴깨짐 / 없음 / 혼합  (TO21 doc.text_layer 값과 같음)
    "language",      # ko / en / mixed
    "input_mode",    # 이미지+글자 / 이미지만  (D-35, D-44)
    "reviewer",      # 검수 담당 역할 (A~F)
    "cross_checker", # 교차 확인 역할
    "note",
]

PURPOSES = ("개발", "평가", "기타")
TEXT_LAYERS = ("정상", "글꼴깨짐", "없음", "혼합")
INPUT_MODES = ("이미지+글자", "이미지만")


def load(path: Path = MANIFEST) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def save(rows: list[dict], path: Path = MANIFEST) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})


def get(doc_id: str, rows: list[dict] | None = None) -> dict:
    for r in rows or load():
        if r["doc_id"] == doc_id:
            return r
    raise KeyError(f"manifest에 없는 문서 번호: {doc_id}")


def select(purpose: str | None = None, doc_ids: list[str] | None = None) -> list[dict]:
    rows = load()
    if doc_ids:
        want = set(doc_ids)
        rows = [r for r in rows if r["doc_id"] in want]
        missing = want - {r["doc_id"] for r in rows}
        if missing:
            raise KeyError(f"manifest에 없는 문서 번호: {sorted(missing)}")
    if purpose:
        rows = [r for r in rows if r["purpose"] == purpose]
    return rows


def _nfc(s: str) -> str:
    # macOS에서 받은 파일은 한글 이름이 NFD로 저장되는 경우가 있어 NFC로 맞춰 비교한다.
    return unicodedata.normalize("NFC", s)


def raw_pdf(row: dict) -> Path:
    """manifest 행의 원본 PDF 경로를 data/raw/ 에서 찾는다(한글 정규화 차이 무시)."""
    target = _nfc(row["source_file"])
    for p in RAW.iterdir():
        if _nfc(p.name) == target:
            return p
    raise FileNotFoundError(f"data/raw/ 에 원본이 없습니다: {row['source_file']} ({row['doc_id']})")
