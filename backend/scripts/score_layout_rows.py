"""표 행 묶기 채점 (역할 C, 시험 단계): 정답 행의 칸들이 읽기 순서 글에서 붙어 나오는가.

정답: data/gold/layout/table_goldset_data.json (개발 문서 10쪽, 골드. 초안은 data/silver/claude/layout/)
표마다 열 수를 두고 행은 열 자리에 맞춰 칸을 적었다(빈 칸은 ""). 표 밖 제목(title)과
여러 칸에 걸친 칸(spans)은 행 채점에 쓰지 않는다. 글이 있는 칸이 2개 이상인 행만 채점한다.

- 칸 있음: 칸 글자의 COVER 이상이 쪽 글에 같은 순서로 있다 (떨어져 있어도 된다). 아니면 글자 자체가
  틀린 것이라(텍스트층 깨짐, OCR 오인식) 행 채점에서 뺀다. 여러 줄 칸이 다른 칸과 섞여 떨어진 것은 여기서 빠지지 않는다
- 행 맞음: 칸 있음인 행에서, 칸 글자를 차례로 이은 것이 쪽 글의 한 구간에 COVER 이상 있다
  (구간 길이는 이은 글의 SPAN배까지. 글자 몇 개 오인식은 봐주고, 다른 줄이 끼어든 것은 틀림)
비교는 NFKC 뒤 글자·숫자만 남겨서 한다. 띄어쓰기·문장부호·줄바꿈은 보지 않는다.

출처
- 저장순서: PDF get_text() (PREPROCESS_VERSION 이전 모델 입력)
- 텍스트층: layout.reading_text(텍스트층 줄)
- OCR: layout.reading_text(OCR 조각, data/pages/<문서>/ocr_all)
- +표선: 같은 글에 PDF에 그려진 표 선(layout.page_tables)으로 표의 행을 먼저 묶은 것
- 모델입력: 전처리 결과 그대로 (render.load_pages의 text. 쪽마다 텍스트층 또는 OCR, source.choose)

사용법 (backend/에서)
  python scripts/score_layout_rows.py
  python scripts/score_layout_rows.py --rows        # 틀린 행을 함께 보여 준다
"""
import argparse
import json
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import _common  # noqa: F401
import pymupdf

from msds.common import manifest, paths
from msds.preprocess.layout import layer_items, page_tables, reading_text
from msds.preprocess.ocr import read_ocr_json
from msds.preprocess.render import load_pages

GOLD = paths.DATA / "gold" / "layout" / "table_goldset_data.json"
COVER = 0.9   # 글자의 이 비율 이상이 맞으면 있다고 본다
SPAN = 1.15   # 행 글자가 이 배수 길이 구간 안에 있어야 붙어 나온 것이다


def key(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text or "") if c.isalnum())


def _cover(part: str, text: str) -> float:
    blocks = SequenceMatcher(None, part, text, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / max(len(part), 1)


def present(cell: str, page: str) -> bool:
    return cell in page or _cover(cell, page) >= COVER


def together(row: str, page: str) -> bool:
    if row in page:
        return True
    width = int(len(row) * SPAN) + 4
    for off in range(0, min(len(row) - 3, 8)):   # 첫 글자가 오인식돼도 찾도록 시작점을 몇 글자 밀어 본다
        head = row[off:off + 4]
        pos = page.find(head)
        while pos >= 0:
            start = max(pos - off, 0)
            if _cover(row, page[start:start + width]) >= COVER:
                return True
            pos = page.find(head, pos + 1)
    return False


def score_rows(rows: list[list[str]], text: str) -> dict:
    page = key(text)
    out = {"rows": 0, "present": 0, "ok": 0, "bad": []}
    for r in rows:
        cells = [key(c) for c in r if c.strip()]   # 빈 칸("")은 열 자리만 지킨다
        if len(cells) < 2:
            continue
        out["rows"] += 1
        if not all(present(c, page) for c in cells):
            continue
        out["present"] += 1
        if together("".join(cells), page):
            out["ok"] += 1
        else:
            out["bad"].append(r)
    return out


def sources(doc_id: str, page_no: int) -> dict[str, str]:
    page = pymupdf.open(manifest.raw_pdf(manifest.get(doc_id)))[page_no - 1]
    items = layer_items(page)
    out = {"저장순서": page.get_text(), "텍스트층": reading_text(items),
           "텍스트층+표선": reading_text(items, page_tables(page))}
    oj = paths.page_dir(doc_id) / "ocr_all" / f"p{page_no:03d}.ocr.json"
    if oj.exists():
        ocr, dpi = read_ocr_json(oj)
        out["OCR"] = reading_text(ocr)
        out["OCR+표선"] = reading_text(ocr, page_tables(page, dpi / 72))
    out["모델입력"] = load_pages(doc_id)["pages"][page_no - 1]["text"]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--rows", action="store_true", help="틀린 행을 보여 준다")
    a = ap.parse_args()
    gold = json.loads(a.gold.read_text(encoding="utf-8"))
    print(f"정답: {a.gold.name} (등급 {gold['grade']}, {gold['review']}) — 미검수면 점수는 참고")
    total: dict[str, dict] = {}
    for p in gold["pages"]:
        rows = [r for t in p["tables"] for r in t["rows"]]
        line = [f"{p['doc_id']:9} {p['page']:2}쪽"]
        for name, text in sources(p["doc_id"], p["page"]).items():
            s = score_rows(rows, text)
            t = total.setdefault(name, {"rows": 0, "present": 0, "ok": 0})
            for k in t:
                t[k] += s[k]
            line.append(f"{name} {s['ok']}/{s['present']} (칸없음 {s['rows'] - s['present']})")
            if a.rows:
                for r in s["bad"]:
                    print(f"    [{name} 틀림] {' | '.join(c[:30] for c in r)}")
        print("  ".join(line))
    for name, t in total.items():
        print(f"[합계] {name}: 행 맞음 {t['ok']}/{t['present']} = {t['ok'] / max(t['present'], 1):.0%}"
              f"  (채점 행 {t['rows']}, 칸 글자가 없어 뺀 행 {t['rows'] - t['present']})")
