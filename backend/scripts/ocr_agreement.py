"""텍스트층 신뢰 점검 (역할 C, 시험 단계): 모든 쪽을 OCR해 텍스트층과 비교한다.

전처리 판별(정상/글꼴깨짐)이 놓친 쪽이 있는지 보려고, 쪽마다 두 지표를 잰다.
- f1_all / f1_hangul / f1_digit: 텍스트층과 OCR의 글자 묶음 일치율(순서 무시, NFKC·공백 제거).
  S003처럼 글자가 전부 깨진 쪽을 잡는다 (S003 0.06~0.09, 정상 0.92~0.996)
- missing_ratio: 텍스트층 한글 음절 중 OCR에 한 번도 안 나오는 음절이 차지하는 비율.
  43번처럼 일부 음절만 바뀐 쪽을 잡는다 (글자 일치율은 0.963으로 정상과 겹친다).
  정상 표본 25쪽에서 0~0.005였다 (2026-10-27)
- order_layer / order_layer_xy: 순서 일치율 (order_ratio). OCR은 읽기 순서(layout.reading_order)로 놓고,
  텍스트층은 모델 입력(p001.txt) 그대로 / PDF에서 다시 읽은 읽기 순서로 놓아 비교한다. 글자 일치율이 높은데
  order_layer가 낮으면 모델 입력의 순서가 틀린 쪽이다. 전처리가 PDF 저장 순서를 쓰던 때(PREPROCESS_VERSION 이전)
  S001 2쪽은 0.44였다 (2번 항목이 1번보다 먼저 나온다)

출력 (data/pages/<문서번호>/ocr_all/, 저장소에 올리지 않는다. 모델 입력 p001.txt는 건드리지 않는다)
- p001.ocr.json    {dpi, config, items}
- p001.agree.json  쪽 지표
- data/pages/ocr_all_summary.jsonl  모든 쪽 지표를 한 줄씩 (끝날 때 다시 만든다)

이미 같은 설정(CONFIG: dpi·모델·버전)으로 OCR한 쪽은 OCR을 다시 하지 않고 지표만 다시 잰다(중간에 멈춰도 다시 돌리면 이어진다).
설정이 다른 결과는 다시 OCR한다. --seed로 다른 곳에서 같은 설정으로 OCR한
결과(dpi가 없는 예전 형식은 300dpi)를 먼저 가져올 수 있다.

사용법 (backend/에서, PaddleOCR 환경)
  python scripts/ocr_agreement.py --all
  python scripts/ocr_agreement.py --docs T21-005 --seed <폴더>   # 폴더 안의 <문서>_p001.ocr.json
"""
import argparse
import json
import shutil
import tempfile
import time
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import _common  # noqa: F401
import pymupdf

from msds.common import manifest, paths
from msds.preprocess.layout import layer_items, page_tables, reading_text
from msds.preprocess.ocr import OCR_DPI, _engine, group_lines, read_ocr_json

CONFIG = {"dpi": OCR_DPI, "det": "PP-OCRv5_server_det", "rec": "korean_PP-OCRv5_mobile_rec",
          "paddleocr": "3.7.0", "paddlepaddle": "3.3.1"}


def out_dir(doc_id: str) -> Path:
    return paths.page_dir(doc_id) / "ocr_all"


def chars(t: str, keep=lambda c: True) -> Counter:
    s = "".join(unicodedata.normalize("NFKC", t or "").split())
    return Counter(c for c in s if keep(c))


def f1(a: Counter, b: Counter):
    if not a and not b:
        return None
    inter = sum((a & b).values())
    p, r = inter / max(sum(a.values()), 1), inter / max(sum(b.values()), 1)
    return round(2 * p * r / (p + r), 3) if p + r else 0.0


def hangul(c: str) -> bool:
    return "가" <= c <= "힣"


def agree(layer: str, ocr: str) -> dict:
    lh, oh = chars(layer, hangul), chars(ocr, hangul)
    missing = {c: n for c, n in lh.items() if c not in oh}
    total = sum(lh.values())
    return {"layer_chars": sum(chars(layer).values()), "ocr_chars": sum(chars(ocr).values()),
            "f1_all": f1(chars(layer), chars(ocr)), "f1_hangul": f1(lh, oh),
            "f1_digit": f1(chars(layer, str.isdigit), chars(ocr, str.isdigit)),
            "layer_hangul": total,
            "missing_ratio": round(sum(missing.values()) / total, 3) if total else None,
            "missing_top": sorted(missing.items(), key=lambda x: -x[1])[:10]}


def order_ratio(a: str, b: str):
    """순서 일치율: 두 글에서 같은 순서로 이어지는 글자 수 / 순서와 관계없이 같은 글자 수.

    글자가 틀린 것(f1_all이 잡는다)과 순서가 틀린 것을 떼어 본다. 글자가 같아도 덩어리 순서가 바뀌면
    뒤로 밀린 덩어리가 순서 맞춤에서 빠져 1보다 작아진다.
    """
    na = "".join(unicodedata.normalize("NFKC", a or "").split())
    nb = "".join(unicodedata.normalize("NFKC", b or "").split())
    common = sum((Counter(na) & Counter(nb)).values())
    if not common:
        return None
    same = sum(m.size for m in SequenceMatcher(None, na, nb, autojunk=False).get_matching_blocks())
    return round(same / common, 3)


def seed(doc_id: str, src: Path) -> int:
    n = 0
    for f in sorted(src.glob(f"{doc_id}_p*.ocr.json")):
        pg = int(f.name.split("_p")[1][:3])
        dst = out_dir(doc_id) / f"p{pg:03d}.ocr.json"
        if dst.exists():
            continue
        items, dpi = read_ocr_json(f)
        if dpi != OCR_DPI:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps({"dpi": dpi, "config": {**CONFIG, "seeded_from": str(f)}, "items": items},
                                  ensure_ascii=False), encoding="utf-8")
        n += 1
    return n


def same_config(oj: Path) -> bool:
    """이 쪽 OCR 결과가 있고 지금 설정(CONFIG)으로 OCR한 것인가. 가져온 곳(seeded_from)은 보지 않는다."""
    if not oj.exists():
        return False
    data = json.loads(oj.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return False   # dpi·설정이 없는 예전 형식
    got = {k: v for k, v in (data.get("config") or {}).items() if k != "seeded_from"}
    return got == CONFIG


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", nargs="*", type=Path, default=[], help="같은 설정으로 OCR해 둔 결과 폴더")
    a = ap.parse_args()
    if not (a.docs or a.all):
        ap.error("--docs 또는 --all")

    rows = manifest.load() if a.all else manifest.select(None, a.docs)
    for r in rows:
        for src in a.seed:
            k = seed(r["doc_id"], src)
            if k:
                print(f"[가져옴] {r['doc_id']} {k}쪽 ← {src}", flush=True)

    engine = None
    for r in rows:
        doc_id = r["doc_id"]
        meta = json.loads(paths.page_meta(doc_id).read_text(encoding="utf-8"))
        pdf = pymupdf.open(manifest.raw_pdf(r))
        out_dir(doc_id).mkdir(parents=True, exist_ok=True)
        for p in meta["pages"]:
            n = p["page"]
            oj, aj = out_dir(doc_id) / f"p{n:03d}.ocr.json", out_dir(doc_id) / f"p{n:03d}.agree.json"
            t0 = time.time()
            if not same_config(oj):
                engine = engine or _engine()
                with tempfile.TemporaryDirectory() as tmp:
                    png = Path(tmp) / "p.png"
                    pdf[n - 1].get_pixmap(dpi=OCR_DPI).save(png)
                    res = engine.predict(str(png))[0]
                items = [{"text": t, "score": round(float(s), 3), "box": [int(v) for v in b]}
                         for t, s, b in zip(res["rec_texts"], res["rec_scores"], res["rec_boxes"])]
                tmpf = oj.with_suffix(".tmp")   # 쓰는 도중 멈춰도 반쪽 파일이 남지 않게
                tmpf.write_text(json.dumps({"dpi": OCR_DPI, "config": CONFIG, "items": items},
                                           ensure_ascii=False), encoding="utf-8")
                shutil.move(tmpf, oj)
            items, dpi = read_ocr_json(oj)
            layer = paths.page_txt(doc_id, n).read_text(encoding="utf-8")
            tables = page_tables(pdf[n - 1])   # 전처리와 같이 선으로 그린 표의 행을 묶는다
            ocr_xy = reading_text(items, page_tables(pdf[n - 1], dpi / 72))
            rec = {"doc_id": doc_id, "purpose": r["purpose"], "page": n, "state": p["state"],
                   "doc_text_layer": meta["text_layer"], **agree(layer, "\n".join(group_lines(items))),
                   "order_layer": order_ratio(layer, ocr_xy),
                   "order_layer_xy": order_ratio(reading_text(layer_items(pdf[n - 1]), tables), ocr_xy),
                   "seconds": round(time.time() - t0, 1)}
            aj.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            print(f"[완료] {doc_id} {n}/{meta['page_count']}쪽 {p['state']} f1={rec['f1_all']} "
                  f"없는음절={rec['missing_ratio']} 순서={rec['order_layer']}→{rec['order_layer_xy']} ({rec['seconds']}초)", flush=True)

    summary = paths.PAGES / "ocr_all_summary.jsonl"
    with open(summary, "w", encoding="utf-8") as f:
        for d in sorted(paths.PAGES.glob("*/ocr_all/p*.agree.json")):
            f.write(d.read_text(encoding="utf-8") + "\n")
    print(f"[요약] {summary}", flush=True)
