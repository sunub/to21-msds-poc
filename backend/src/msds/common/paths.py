"""저장소 경로와 파일 이름 규칙 (실행 계획서 12장).

모든 코드는 경로를 직접 조립하지 말고 이 모듈의 함수를 쓴다.
그래야 폴더 구조가 바뀌어도 한 곳만 고치면 된다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
RAW = DATA / "raw"
PAGES = DATA / "pages"
SILVER = DATA / "silver"
REVIEW = DATA / "review"
GOLD = DATA / "gold"
MANIFEST = DATA / "manifest.csv"
RUNS = ROOT / "runs"
CONFIGS = ROOT / "configs"
PROMPTS = ROOT / "src" / "msds" / "extract" / "prompts"
TO21 = ROOT / "to21" / "v0.5"

TO21_FILES = {
    "schema": "TO21_MSDS_추출스키마_v0.5.json",
    "spec": "TO21_MSDS_추출명세서_v0.5.xlsx",
    "dictionary": "TO21_MSDS_동의어사전_v0.5.json",
    "validator": "TO21_MSDS_검증기_v0.5.py",
    "scorer": "TO21_MSDS_채점기_v0.5.py",
    "regen": "TO21_MSDS_DB적재_재생성_v0.5.py",
    "coverage": "TO21_MSDS_커버리지점검_v0.5.py",
    "example25": "TO21_MSDS_추출예제_25_황산_v0.5.json",
}


def to21_file(kind: str) -> Path:
    """TO21 제공 파일 경로. kind는 TO21_FILES의 키.

    TO21 제공 자료는 TO21 확인 전까지 저장소에 올리지 않는다(결정 D-47).
    각자 팀 공유 위치에서 받아 to21/v0.5/에 원래 이름 그대로 둔다. 목록은 to21/README.md.
    """
    p = TO21 / TO21_FILES[kind]
    if not p.exists():
        raise FileNotFoundError(
            f"TO21 제공 파일이 없습니다: {p}\n"
            "TO21 자료는 저장소에 올리지 않습니다(D-47). 팀 공유 위치(노션)에서 받아 "
            "to21/v0.5/에 원래 파일 이름 그대로 두세요. 목록: to21/README.md"
        )
    return p


# ── 전처리 결과 (C) ─────────────────────────────────────
def page_dir(doc_id: str) -> Path:
    return PAGES / doc_id


def page_png(doc_id: str, page_no: int) -> Path:
    """쪽 이미지. 쪽 번호는 1부터."""
    return page_dir(doc_id) / f"p{page_no:03d}.png"


def page_txt(doc_id: str, page_no: int) -> Path:
    """쪽 텍스트층. 쪽 번호는 1부터."""
    return page_dir(doc_id) / f"p{page_no:03d}.txt"


def page_meta(doc_id: str) -> Path:
    """전처리 요약(쪽수, 쪽별 텍스트층 상태, 판별 근거)."""
    return page_dir(doc_id) / "meta.json"


# ── 실버·검수표·골드 (A) ────────────────────────────────
def silver_path(model_tag: str, doc_id: str) -> Path:
    """실버 JSON (TO21 형식). model_tag는 configs/models.yaml의 키(gpt, claude)."""
    return SILVER / model_tag / f"{doc_id}.json"


def silver_review_path(model_tag: str, doc_id: str) -> Path:
    """실버의 검수 정보(원문 조각, 쪽, 적용 규칙, 설명). TO21 형식에 칸이 없어 따로 둔다(D-33)."""
    return SILVER / model_tag / f"{doc_id}.review.json"


def review_sheet_path(doc_id: str) -> Path:
    return REVIEW / f"{doc_id}.xlsx"


def gold_path(doc_id: str) -> Path:
    return GOLD / f"{doc_id}.json"


def gold_unreviewed_path(doc_id: str) -> Path:
    """골드 중 검수하지 못한 칸 목록 (D-35, 성적표에서 '참고'로 표시)."""
    return GOLD / f"{doc_id}.unreviewed.json"


# ── 실행 결과 ───────────────────────────────────────────
def run_dir(run_name: str) -> Path:
    """실험 결과 폴더. run_name 예: 20261026_baseline_qwen38"""
    return RUNS / run_name
