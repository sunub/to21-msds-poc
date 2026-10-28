"""텍스트 추출 평가 점수 (역할 C): 사람이 검수한 정답 두 가지로 추출한 글을 엄격하게 채점한다.

1. 행 점수: data/gold/layout/rows_dev10.json (개발 문서 10쪽, 151행, 골드)
   모델 입력 글(render.load_pages의 text)의 **한 줄 안에** 행의 칸들이 차례로 들어 있으면 맞음.
   NFKC 뒤 공백만 지우고 비교한다. 문장부호·기호·대소문자는 그대로 본다.
   (score_layout_rows.py는 글자·숫자만 보고 줄바꿈도 무시해서, 문장부호가 떨어져 나간 글과
   줄이 끊긴 행도 맞다고 한다. 이 점수는 그 둘을 틀림으로 센다)
2. 조각 점수: runs/20261026_s003_ocr_source_match/fragments.json (S003, 사람이 쪽 이미지를 보고 옮겨 적은 조각)
   텍스트층이 깨진 S003을 OCR 글(ocr.page_text)로 원문 대조(checks.source_match)해 실제 조각 44개 중 '일치'의 비율.
   대조군 8개(expect)는 점수에 넣지 않고, 기대와 다르면 따로 알린다 (정규화를 너무 넓히면 지어낸 조각도 맞게 된다)

종합 점수 = 두 점수의 평균. 합격 = 두 점수가 모두 90 이상.

3. 표 점수 (참고, 합격에 넣지 않음): rows_dev10.json의 데이터 표 칸 격자와 tables/*.md의 칸을 자리별로 비교한다.
   정답의 글이 든 칸 중 같은 자리에 같은 글이 든 비율. 그 쪽에서 가장 잘 맞는 md 표와 비교한다.
   어느 정답 표가 데이터 표인지(DATA_TABLES)는 Claude가 붙인 구분이고 사람이 검수하지 않았다 (미검수).
   그래서 이 점수는 참고로만 본다. 정답 쪽에서 데이터 표와 맞지 않는 md는 '잘못 꺼냄'으로 센다.
정답은 개발 문서다 (D-43). 평가 문서로 규칙을 고치지 않는다.

사용법 (backend/에서. 모델 입력이 바뀌는 코드를 고쳤으면 먼저 전처리를 다시 돌린다)
  python scripts/preprocess.py --purpose 개발 --force
  python scripts/score_extraction.py           # 점수
  python scripts/score_extraction.py --bad     # 틀린 행·조각도 보여 준다
"""
import argparse
import json
import re
import unicodedata

import _common  # noqa: F401
from msds.checks.source_match import match
from msds.common import paths
from msds.preprocess.ocr import page_text, read_ocr_json
from msds.preprocess.render import PREPROCESS_VERSION, load_pages

ROWS_GOLD = paths.DATA / "gold" / "layout" / "rows_dev10.json"
FRAGMENTS = paths.ROOT / "runs" / "20261026_s003_ocr_source_match" / "fragments.json"
FRAGMENT_DOC = "T21-S003"
PASS = 90
# 정답 표 중 데이터 표 (문서, 쪽, 머리글 첫 칸). 미검수. 나머지 정답 표는 항목|값 틀이다
# (S001 7쪽 특성|제품, S013 6쪽 머리글 없는 9항, S014 5쪽 상자, M001 1쪽 전화번호, M013 항목값)
DATA_TABLES = {("T21-S001", 3, "화학물질명"), ("T21-M004", 2, "물질명"), ("T21-M004", 2, "화학물질명"),
               ("T21-M002", 2, "물질명"), ("T21-M005", 2, "보건(Health)"), ("T21-M005", 2, "구성성분"),
               ("T21-M013", 3, "화학물질명")}


def key(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def row_on_one_line(cells: list[str], text: str) -> bool:
    row = "".join(key(c) for c in cells)
    return any(row in key(line) for line in text.splitlines())


def score_rows(gold: dict, bad: list) -> dict:
    out = {"ok": 0, "n": 0}
    cache: dict[str, dict] = {}
    for p in gold["pages"]:
        if p["doc_id"] not in cache:
            cache[p["doc_id"]] = load_pages(p["doc_id"])
            got = cache[p["doc_id"]]["meta"].get("preprocess_version")
            if got != PREPROCESS_VERSION:
                raise SystemExit(f"{p['doc_id']}: 전처리 버전 {got} ≠ {PREPROCESS_VERSION}. "
                                 "python scripts/preprocess.py --purpose 개발 --force 를 먼저 돌리세요")
        text = cache[p["doc_id"]]["pages"][p["page"] - 1]["text"]
        for t in p["tables"]:
            for r in t["rows"]:
                cells = [c for c in r if c.strip()]   # 빈 칸("")은 열 자리만 지킨다
                if len(cells) < 2:
                    continue
                out["n"] += 1
                if row_on_one_line(cells, text):
                    out["ok"] += 1
                else:
                    bad.append(f"[행] {p['doc_id']} {p['page']}쪽: {' | '.join(c[:30] for c in cells)}")
    return out


def score_fragments(frags: list[dict], bad: list) -> dict:
    texts, states = {}, {}
    for f in sorted(paths.page_dir(FRAGMENT_DOC).glob("p*.ocr.json")):
        n = int(f.name[1:4])
        texts[n], states[n] = page_text(*read_ocr_json(f)), "정상"
    out = {"ok": 0, "n": 0, "control_wrong": 0}
    for f in frags:
        r = match(f["text"], f["page"], texts, states)
        got = r["result"] if r["result"] != "일치" or r["found_page"] == f["page"] else "다른쪽일치"
        if "expect" in f:   # 대조군: 쪽 틀림 → 다른 쪽에서 일치, 지어냄·다듬음 → 불일치
            want = "다른쪽일치" if f["expect"].startswith("일치") else f["expect"]
            if got != want:
                out["control_wrong"] += 1
                bad.append(f"[대조군] {f['id']} {f['text']!r}: 기대 {f['expect']} → {got}")
            continue
        out["n"] += 1
        if got == "일치":
            out["ok"] += 1
        else:
            bad.append(f"[조각] {f['id']} {f['page']}쪽 {f['text']!r} → {got}")
    return out


def read_md(text: str) -> list[list[str]]:
    rows = [ln.strip()[1:-1] for ln in text.splitlines() if ln.strip().startswith("|")]
    return [[c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", r)] for i, r in enumerate(rows) if i != 1]


def cells_ok(gold: list[list[str]], got: list[list[str]]) -> tuple[int, int]:
    """정답의 글이 든 칸 중 같은 자리에 같은 글이 든 칸 수, 정답의 글이 든 칸 수."""
    pos = [(r, c) for r, row in enumerate(gold) for c, v in enumerate(row) if v.strip()]
    ok = sum(1 for r, c in pos if r < len(got) and c < len(got[r]) and key(got[r][c]) == key(gold[r][c]))
    return ok, len(pos)


def score_tables(gold: dict, bad: list) -> dict:
    out = {"ok": 0, "n": 0, "tables": 0, "found": 0, "extra": 0}
    for p in gold["pages"]:
        meta = load_pages(p["doc_id"])["meta"]["pages"][p["page"] - 1]
        md = {n: read_md((paths.page_dir(p["doc_id"]) / "tables" / n).read_text(encoding="utf-8"))
              for n in meta.get("tables", [])}
        used = set()
        for t in p["tables"]:
            if (p["doc_id"], p["page"], t["rows"][0][0]) not in DATA_TABLES:
                continue
            best = max(((cells_ok(t["rows"], g), n) for n, g in md.items() if n not in used),
                       default=((0, cells_ok(t["rows"], [])[1]), None))
            (ok, n), name = best
            out["tables"] += 1
            out["ok"] += ok
            out["n"] += n
            if name and ok:
                used.add(name)
                out["found"] += 1
            if ok < n:
                bad.append(f"[표] {p['doc_id']} {p['page']}쪽 {t['rows'][0][0]}: 칸 {ok}/{n}"
                           f" ({name or '꺼낸 표 없음'})")
        for name in sorted(set(md) - used):
            out["extra"] += 1
            bad.append(f"[표] {p['doc_id']} {p['page']}쪽 {name}: 데이터 표가 아닌데 꺼냄")
    return out


def total(rows: dict, frags: dict) -> dict:
    r, f = rows["ok"] / rows["n"] * 100, frags["ok"] / frags["n"] * 100
    return {"rows": round(r, 1), "fragments": round(f, 1), "score": round((r + f) / 2, 1),
            "pass": r >= PASS and f >= PASS}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bad", action="store_true", help="틀린 행·조각을 보여 준다")
    a = ap.parse_args()
    bad: list[str] = []
    rows = score_rows(json.loads(ROWS_GOLD.read_text(encoding="utf-8")), bad)
    frags = score_fragments(json.loads(FRAGMENTS.read_text(encoding="utf-8")), bad)
    tables = score_tables(json.loads(ROWS_GOLD.read_text(encoding="utf-8")), bad)
    t = total(rows, frags)
    print(f"행 점수 {t['rows']} ({rows['ok']}/{rows['n']})  조각 점수 {t['fragments']} ({frags['ok']}/{frags['n']})"
          f"  대조군 어긋남 {frags['control_wrong']}")
    print(f"표 점수(참고, 미검수 구분) {round(tables['ok'] / tables['n'] * 100, 1)} ({tables['ok']}/{tables['n']}칸)"
          f"  데이터 표 {tables['found']}/{tables['tables']}개 꺼냄  잘못 꺼냄 {tables['extra']}")
    print(f"종합 {t['score']}  → {'합격' if t['pass'] else '불합격'} (두 점수 모두 {PASS} 이상)")
    if a.bad:
        print("\n".join(bad))
