"""OCR 글자로 원문 대조가 되는지 시험한다 (역할 C, 시험 단계).

원문 조각 파일(JSON 목록: id, page, kind, text, expect?)을 세 가지 글자로 대조한다.
  현재    텍스트층 + 전처리가 판별한 쪽 상태 (깨진 쪽은 '대조불가')
  OCR     OCR한 쪽은 OCR 글자를 '정상'으로 넣는다
expect가 있는 조각은 대조군(쪽 틀림, 지어냄, 다듬음)이다.

사용법
  python scripts/check_ocr_match.py T21-S003 ../runs/20261026_s003_ocr_source_match/fragments.json
결과는 조각 파일 옆 result.json에 저장한다.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import _common  # noqa: F401
from msds.checks.source_match import match
from msds.preprocess.ocr import load_ocr_texts
from msds.preprocess.render import load_pages


def label(r: dict, page: int) -> str:
    if r["result"] == "일치" and r["found_page"] != page:
        return f"일치({r['found_page']}쪽)"
    return r["result"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("doc_id")
    ap.add_argument("fragments", type=Path)
    a = ap.parse_args()

    pages = load_pages(a.doc_id)["pages"]
    layer = {p["page"]: p["text"] or "" for p in pages}
    states = {p["page"]: p["state"] for p in pages}
    ocr = load_ocr_texts(a.doc_id)
    setups = {
        "현재": (layer, states),
        "OCR": ({**layer, **ocr}, {**states, **{n: "정상" for n in ocr}}),
    }
    frags = json.loads(a.fragments.read_text(encoding="utf-8"))
    rows = [dict(f) for f in frags]
    for name, (texts, st) in setups.items():
        cnt = Counter()
        for f, row in zip(frags, rows):
            row[name] = label(match(f["text"], f["page"], texts, st), f["page"])
            cnt[row[name]] += 1
        print(name, dict(cnt))

    real = [r for r in rows if "expect" not in r]
    print(f"\n실제 원문 조각 {len(real)}개 중 OCR 일치 {sum(r['OCR'] == '일치' for r in real)}개")
    for r in real:
        if r["OCR"] != "일치":
            print(f"  [{r['id']}] {r['page']}쪽 {r['kind']}: {r['text']!r} → {r['OCR']}")
    print("대조군")
    for r in rows:
        if "expect" in r:
            print(f"  [{r['id']}] {r['kind']}: {r['text']!r} 기대 {r['expect']} → {r['OCR']}"
                  f" {'OK' if r['OCR'] == r['expect'] else '다름'}")
    out = a.fragments.with_name("result.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {out}")
