"""쪽마다 모델 입력 글의 출처를 고른다: 텍스트층 / OCR.

글꼴 판정(render.judge_page)이 '정상'이어도 텍스트층을 믿을 수 없는 쪽이 있다.
- M013: 글자와 띄어쓰기·문장부호를 다른 층으로 겹쳐 찍어 '점막과눈그리고경피로…', '말함피부자극성을…아님 ( ).'
- 039번 1쪽: 표가 그림으로만 들어 있어 텍스트층에 내용이 없다
글자 묶음은 같아도(f1_all) 어절이 깨지거나 빠진다. 그래서 텍스트층과 OCR의 어절 일치율로 본다.
일치율이 WORD_AGREE_MIN보다 낮으면 그 쪽은 OCR 글을 모델 입력과 원문 대조에 쓴다.

기준값은 개발 문서로만 정했다 (D-43, 2026-10-27): 정상 쪽 최소 0.784 (M002 1쪽), M013 최대 0.679 (7쪽).
OCR 결과(ocr_all/ 또는 쪽 폴더의 p001.ocr.json)가 없는 쪽은 텍스트층을 그대로 쓴다.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

from ..common import paths

WORD_AGREE_MIN = 0.75


def words(text: str) -> Counter:
    """어절 묶음. NFKC 뒤 글자·숫자가 아닌 것에서 자르고 두 글자 이상만 센다."""
    return Counter(w for w in re.split(r"[^\w]+", unicodedata.normalize("NFKC", text or "")) if len(w) >= 2)


def word_agreement(layer: str, ocr: str) -> float | None:
    """두 글의 어절 일치율 (F1, 순서 무시). 한쪽이라도 어절이 없으면 None."""
    a, b = words(layer), words(ocr)
    if not a or not b:
        return None
    same = sum((a & b).values())
    p, r = same / sum(a.values()), same / sum(b.values())
    return round(2 * p * r / (p + r), 3) if p + r else 0.0


def ocr_json_for(doc_id: str, page_no: int) -> Path | None:
    """그 쪽의 OCR 결과. 모든 쪽을 OCR한 ocr_all/을 먼저 본다."""
    for f in (paths.page_dir(doc_id) / "ocr_all" / f"p{page_no:03d}.ocr.json",
              paths.page_dir(doc_id) / f"p{page_no:03d}.ocr.json"):
        if f.exists():
            return f
    return None


def page_ocr_input(doc_id: str, page_no: int) -> Path:
    """출처가 OCR인 쪽의 모델 입력·원문 대조 글."""
    return paths.page_dir(doc_id) / f"p{page_no:03d}.ocr_input.txt"


def choose(layer: str, ocr: str | None) -> dict:
    """{'input_source': '텍스트층' | 'OCR', 'word_agree': 일치율 | None}. layer는 겹쳐찍기 사본을 지운 글."""
    if ocr is None:
        return {"input_source": "텍스트층", "word_agree": None}
    w = word_agreement(layer, ocr)
    return {"input_source": "OCR" if w is not None and w < WORD_AGREE_MIN else "텍스트층", "word_agree": w}
