"""전처리: PDF → 쪽 이미지 + 쪽 텍스트층 + 텍스트층 상태 판별 (D-44).

동작하는 상태로 제공한다. C는 실행하고 결과(특히 text_layer 판별)를 확인한다.

출력 (paths 참고)
- data/pages/<문서번호>/p001.png ...   쪽 이미지 (기본 150dpi)
- data/pages/<문서번호>/p001.txt ...   쪽 텍스트층 (PyMuPDF get_text)
- data/pages/<문서번호>/meta.json      쪽수, 쪽별 판별 수치, 문서 판정

텍스트층 판별 (TO21 doc.text_layer 값과 같은 이름)
- 정상     : 글자를 그대로 믿어도 됨
- 글꼴깨짐 : 글꼴 매핑이 깨져 글자가 바뀜. 두 가지를 잡는다
             ① 한글이 나오는데 'ㄴ'받침 자리에 'ㄲ'받침이 비정상적으로 많음 (예: 43번 '심한'→'심핚')
             ② 글자는 많은데 한글·영문이 아닌 기호가 대부분 (예: S003)
- 없음     : 모든 쪽이 이미지뿐 (스캔본)
- 혼합     : 일부 쪽만 이미지뿐
판별 기준값은 20건(2026-10-24)에서 정상 문서 최대 0.012, 43번 0.69로 확인해 0.05로 잡았다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from ..common import paths

KK_RATIO_LIMIT = 0.05      # ㄲ받침 / ㄴ받침 비율이 이보다 크면 글꼴깨짐
SYMBOL_RATIO_LIMIT = 0.3   # 한글·영문이 아닌 글자 비율이 이보다 크면 글꼴깨짐
MIN_PAGE_CHARS = 20        # 이보다 글자가 적으면 글자가 없는 쪽
MIN_NN_FOR_KK = 20         # ㄴ받침이 이보다 적은 쪽은 ㄲ받침 비율을 믿을 수 없어 쪽만으로 판정하지 않는다
SCAN_COVER_LIMIT = 0.5     # 글자 없는 쪽에서 그림이 쪽 면적의 이 비율 이상이면 스캔 쪽 (로고만 있는 빈 쪽과 구분)


def _counts(text: str) -> dict:
    hangul = [c for c in text if "가" <= c <= "힣"]
    jong = [(ord(c) - 0xAC00) % 28 for c in hangul]
    stripped = [c for c in text if not c.isspace()]
    latin = sum(1 for c in stripped if c.isascii() and c.isalpha())
    symbol = sum(1 for c in stripped if not c.isascii() and not ("가" <= c <= "힣"))
    return {
        "chars": len(stripped),
        "hangul": len(hangul),
        "kk": sum(1 for j in jong if j == 2),   # ㄲ받침
        "nn": sum(1 for j in jong if j == 4),   # ㄴ받침
        "latin": latin,
        "symbol": symbol,
    }


def _image_cover(page) -> float:
    """쪽 면적 대비 가장 큰 그림의 면적 비율."""
    area = page.rect.width * page.rect.height or 1
    best = 0.0
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        best = max(best, abs((x1 - x0) * (y1 - y0)) / area)
    return best


def judge_page(c: dict, image_cover: float) -> str:
    if c["chars"] < MIN_PAGE_CHARS:
        return "이미지만" if image_cover >= SCAN_COVER_LIMIT else "빈쪽"
    if c["nn"] >= MIN_NN_FOR_KK and c["kk"] / max(c["nn"], 1) > KK_RATIO_LIMIT:
        return "글꼴깨짐"
    if c["symbol"] / max(c["chars"], 1) > SYMBOL_RATIO_LIMIT and c["hangul"] == 0:
        return "글꼴깨짐"
    return "정상"


def judge_doc(page_states: list[str], totals: dict) -> str:
    content = [s for s in page_states if s != "빈쪽"]
    if not content:
        return "없음"
    if any(s == "글꼴깨짐" for s in content):
        return "글꼴깨짐"
    if all(s == "이미지만" for s in content):
        return "없음"
    if any(s == "이미지만" for s in content):
        return "혼합"
    # 쪽 단위로 못 잡은 경우 문서 전체 비율로 한 번 더 본다
    if totals["nn"] >= 50 and totals["kk"] / max(totals["nn"], 1) > KK_RATIO_LIMIT:
        return "글꼴깨짐"
    return "정상"


def follow_doc(pages: list[dict], text_layer: str) -> list[dict]:
    """글자가 적어 쪽만으로 깨짐을 판정하지 못한 '정상' 쪽은 문서 판정이 글꼴깨짐이면 그것을 따른다.

    43번 16쪽은 81자(ㄴ받침 4, ㄲ받침 5)라 ㄲ받침 검사를 건너뛰어 '정상'이 됐지만 '귺로자, 홖경'처럼
    깨져 있었다 (2026-10-27 OCR 대조). 같은 문서의 같은 글꼴이라 깨짐도 같다고 본다.
    문서 판정(text_layer)과 모델 입력(input_mode)은 바꾸지 않는다. 쪽 상태는 원문 대조가 쓴다.
    """
    if text_layer != "글꼴깨짐":
        return pages
    out = []
    for p in pages:
        if p["state"] == "정상" and p["nn"] < MIN_NN_FOR_KK:
            p = {**p, "state": "글꼴깨짐", "state_reason": "글자가 적어 문서 판정을 따름"}
        out.append(p)
    return out


def judge_language(totals: dict) -> str | None:
    h, l = totals["hangul"], totals["latin"]
    if h + l < 50:
        return None
    r = h / (h + l)
    if r > 0.3:
        return "ko"
    if r < 0.05:
        return "en"
    return "mixed"


def preprocess(pdf_path: Path, doc_id: str, dpi: int = 150, force: bool = False) -> dict:
    out_dir = paths.page_dir(doc_id)
    meta_path = paths.page_meta(doc_id)
    if meta_path.exists() and not force:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(pdf_path)
    pages = []
    totals = {"chars": 0, "hangul": 0, "kk": 0, "nn": 0, "latin": 0, "symbol": 0}
    for i, page in enumerate(doc, start=1):
        text = page.get_text()
        paths.page_txt(doc_id, i).write_text(text, encoding="utf-8")
        page.get_pixmap(dpi=dpi).save(paths.page_png(doc_id, i))
        c = _counts(text)
        for k in totals:
            totals[k] += c[k]
        cover = _image_cover(page)
        state = judge_page(c, cover)
        pages.append({"page": i, "state": state, "image_cover": round(cover, 3), **c})

    text_layer = judge_doc([p["state"] for p in pages], totals)
    pages = follow_doc(pages, text_layer)
    language = judge_language(totals)
    if text_layer in ("글꼴깨짐", "없음") and totals["hangul"] == 0:
        language = None   # 글자를 믿을 수 없어 언어를 판정하지 않는다. manifest에서 사람이 채운다
    meta = {
        "doc_id": doc_id,
        "source_file": pdf_path.name,
        "page_count": len(pages),
        "dpi": dpi,
        "text_layer": text_layer,
        "language": language,
        "input_mode": "이미지+글자" if text_layer in ("정상", "혼합") else "이미지만",
        "totals": totals,
        "pages": pages,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_pages(doc_id: str) -> dict:
    """추출 단계에서 쓰는 쪽 입력. {'meta': ..., 'pages': [{page, image, text, state}]}"""
    meta = json.loads(paths.page_meta(doc_id).read_text(encoding="utf-8"))
    out = []
    for p in meta["pages"]:
        n = p["page"]
        out.append({
            "page": n,
            "image": paths.page_png(doc_id, n),
            "text": paths.page_txt(doc_id, n).read_text(encoding="utf-8"),
            "state": p["state"],
        })
    return {"meta": meta, "pages": out}
