"""깨진 텍스트층 보완: 쪽 이미지 → PaddleOCR → 줄 단위 글자 (역할 C, 시험 단계).

모델 입력(p001.txt, D-44)은 바꾸지 않는다. OCR 결과는 원문 대조(D-14)와 2주차 검사(D-38, D-40)에서
깨진 쪽을 대조할 글자로만 쓴다. 모델 입력으로 쓸지는 F와 정한다.

출력 (data/pages/<문서번호>/, 저장소에 올리지 않는다)
- p001.ocr.json   줄마다 {text, score, box}. box는 OCR 이미지 좌표(픽셀)
- p001.ocr.txt    줄을 읽는 순서로 이은 글자

OCR 이미지는 쪽 이미지(150dpi, 모델 입력)와 따로 300dpi로 그린다. 작은 숫자·기호를 읽기 위해서다.
PaddleOCR은 requirements.txt에 없다(폐쇄망 반입 여부 미정). 별도 환경에 설치해 쓴다:
  pip install paddlepaddle paddleocr
S003 시험(2026-10-26, paddleocr 3.7.0): 원문 조각 44개 중 42개 일치. 틀린 2개는 ℃ 오인식
(℃→C, ℃→°c). 기록: runs/20261026_s003_ocr_source_match/
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pymupdf

from ..common import paths

OCR_DPI = 300


def ocr_json(doc_id: str, page_no: int) -> Path:
    return paths.page_dir(doc_id) / f"p{page_no:03d}.ocr.json"


def ocr_txt(doc_id: str, page_no: int) -> Path:
    return paths.page_dir(doc_id) / f"p{page_no:03d}.ocr.txt"


def group_lines(items: list[dict]) -> list[str]:
    """OCR 조각을 줄로 묶어 읽는 순서로 돌려준다.

    세로 중심이 이미 만든 줄의 높이 안에 들면 같은 줄로 본다. 고정 간격으로 자르면
    같은 줄의 단어가 몇 픽셀 차이로 다음 줄로 밀린다(S003 6쪽 '참고하여').
    """
    rows: list[dict] = []
    for it in sorted(items, key=lambda i: i["box"][1]):
        cy = (it["box"][1] + it["box"][3]) / 2
        for r in rows:
            if r["y0"] <= cy <= r["y1"]:
                r["items"].append(it)
                break
        else:
            rows.append({"y0": it["box"][1], "y1": it["box"][3], "items": [it]})
    return [" ".join(i["text"] for i in sorted(r["items"], key=lambda i: i["box"][0])) for r in rows]


def _engine():
    from paddleocr import PaddleOCR   # 설치 확인을 늦춰, 다른 모듈은 paddleocr 없이도 읽히게 한다

    return PaddleOCR(lang="korean", use_doc_orientation_classify=False,
                     use_doc_unwarping=False, use_textline_orientation=False)


def ocr_document(pdf_path: Path, doc_id: str, pages: list[int] | None = None, dpi: int = OCR_DPI) -> list[dict]:
    """pages 쪽(없으면 텍스트층이 '정상'이 아닌 쪽)을 OCR해 저장한다. 쪽별 요약을 돌려준다.

    전처리(render.preprocess)를 먼저 돌려 meta.json이 있어야 한다.
    """
    meta = json.loads(paths.page_meta(doc_id).read_text(encoding="utf-8"))
    if pages is None:
        pages = [p["page"] for p in meta["pages"] if p["state"] != "정상"]
    engine = _engine()
    doc = pymupdf.open(pdf_path)
    summary = []
    with tempfile.TemporaryDirectory() as tmp:
        for n in pages:
            png = Path(tmp) / f"p{n:03d}.png"
            doc[n - 1].get_pixmap(dpi=dpi).save(png)
            res = engine.predict(str(png))[0]
            items = [{"text": t, "score": round(float(s), 3), "box": [int(v) for v in b]}
                     for t, s, b in zip(res["rec_texts"], res["rec_scores"], res["rec_boxes"])]
            ocr_json(doc_id, n).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
            ocr_txt(doc_id, n).write_text("\n".join(group_lines(items)), encoding="utf-8")
            scores = [i["score"] for i in items]
            summary.append({"page": n, "lines": len(items),
                            "mean_score": round(sum(scores) / max(len(scores), 1), 3),
                            "low_score_lines": sum(1 for s in scores if s < 0.8)})
    return summary


def load_ocr_texts(doc_id: str) -> dict[int, str]:
    """OCR한 쪽의 글자. {쪽 번호: 글자}. OCR하지 않은 쪽은 없다."""
    out = {}
    for f in sorted(paths.page_dir(doc_id).glob("p*.ocr.txt")):
        out[int(f.name[1:4])] = f.read_text(encoding="utf-8")
    return out
