"""깨진 텍스트층 보완: 쪽 이미지 → PaddleOCR → 줄 단위 글자 (역할 C, 시험 단계).

OCR 결과는 원문 대조(D-14)와 2주차 검사(D-38, D-40)에서 깨진 쪽을 대조할 글자로 쓴다.
글꼴 판정이 '정상'인데 텍스트층과 어절이 크게 다른 쪽은 OCR 글을 모델 입력으로 쓴다 (source.choose, 2026-10-27).
글꼴깨짐 쪽을 모델 입력으로 쓸지는 F와 정한다.

출력 (data/pages/<문서번호>/, 저장소에 올리지 않는다)
- p001.ocr.json   {dpi, items}. items는 줄마다 {text, score, box}. box는 OCR 이미지 좌표(dpi 픽셀)
- p001.ocr.txt    줄을 읽는 순서로 이은 글자
- p001.ocr.cells.json  줄을 '왼쪽 항목명 | 오른쪽 값' 칸으로 묶은 것 (group_cells)

OCR 이미지는 쪽 이미지(150dpi, 모델 입력)와 따로 300dpi로 그린다. 작은 숫자·기호를 읽기 위해서다.
PaddleOCR은 런타임 의존성에 없다(폐쇄망 반입 여부 미정). pyproject.toml의 ocr 그룹으로 GPU 서버에 설치한다:
  cd backend && uv sync --group ocr
S003 시험(2026-10-26, paddleocr 3.7.0): 원문 조각 44개 중 42개 일치. 틀린 2개는 ℃ 오인식
(℃→C, ℃→°c). 기록: runs/20261026_s003_ocr_source_match/
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pymupdf

from ..common import paths

OCR_DPI = 300


def ocr_json(doc_id: str, page_no: int) -> Path:
    return paths.page_dir(doc_id) / f"p{page_no:03d}.ocr.json"


def ocr_txt(doc_id: str, page_no: int) -> Path:
    return paths.page_dir(doc_id) / f"p{page_no:03d}.ocr.txt"


def ocr_cells(doc_id: str, page_no: int) -> Path:
    return paths.page_dir(doc_id) / f"p{page_no:03d}.ocr.cells.json"


def _rows(items: list[dict]) -> list[list[dict]]:
    """OCR 조각을 줄로 묶는다. 위에서 아래, 줄 안에서는 왼쪽에서 오른쪽.

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
    return [sorted(r["items"], key=lambda i: i["box"][0]) for r in rows]


def group_lines(items: list[dict]) -> list[str]:
    """OCR 조각을 줄로 묶어 읽는 순서로 돌려준다."""
    return [" ".join(i["text"] for i in row) for row in _rows(items)]


# ── 칸 묶기 ─────────────────────────────────────────────
# MSDS 본문은 대부분 '왼쪽 항목명 | 오른쪽 값' 두 열이다. OCR은 눈에 보이는 한 줄씩만 주므로
# 값이 여러 줄이면 줄마다 떨어진다. 왼쪽 열에 새 항목명이 나올 때까지 오른쪽 열의 줄을 한 칸으로 모은다.
# 기준값은 RULE_DPI(300dpi) 픽셀이다 (S003 6쪽에서 값 열 x≈980, 항목명 x≈280~400, 오른쪽 끝 x≈2200).
# 다른 dpi로 OCR한 쪽은 좌표를 300dpi로 바꿔 같은 기준값으로 묶는다.
RULE_DPI = 300
MIN_SCORE = 0.6         # 이보다 낮은 조각은 칸에 넣지 않고 dropped로 남긴다 (예: S003 1쪽 그림문자를 '/'로 읽음)
COL_GAP = 30             # 값 열 시작보다 이만큼 왼쪽까지는 값으로 본다
SEG_GAP = 20             # 한 줄 안에서 조각 사이가 이보다 가까우면 한 덩어리다 (양쪽 정렬 문장이 쪼개진 것: -8~10px.
                         # 항목명과 값 사이는 35px 이상, S003 2쪽 6항)
LABEL_FILL = 100         # 항목명 줄이 값 열 시작 근처까지 차면 다음 줄로 넘어갈 수 있다
INDENT = 10              # 넘어간 줄은 앞 줄보다 왼쪽(내어쓰기)에서, 소항목·새 문단은 오른쪽(들여쓰기)에서 시작한다
PARA_OVER = 200          # 값이 없는 왼쪽 줄이 값 열 안으로 이만큼 넘어가면 쪽 폭 문단이다 (16항 출처 목록)
PARA_GAP = 60            # 값이 없는 줄 사이 세로 간격이 이보다 크면 다른 구간이다 (S003 6쪽 맨 아래 상자)
PARA_FILL = 0.9          # 문단 줄이 오른쪽 끝의 이 비율까지 차면 다음 줄(같은 들여쓰기)로 이어진다
WRAP_FILL = 0.95         # 값 줄이 오른쪽 끝의 이 비율까지 차면 폭 때문에 넘어간 줄이다


def _value_col(items: list[dict]) -> int | None:
    """값 열의 시작 x. 쪽 폭의 30%보다 오른쪽에서 시작하는 줄의 x를 20px 단위로 모아 가장 많은 곳."""
    right = max(i["box"][2] for i in items)
    xs = [i["box"][0] for i in items if i["box"][0] > right * 0.3]
    if not xs:
        return None
    bins: dict[int, list[int]] = {}
    for x in xs:
        bins.setdefault(round(x / 20), []).append(x)
    return min(max(bins.values(), key=len))


def _join(a: str, b: str, wrapped: bool) -> str:
    """같은 칸의 두 줄을 잇는다. 폭 때문에 넘어간 줄이면 붙이고, 아니면 줄을 바꾼다.

    한글과 한글 사이는 공백 없이 붙인다. 이 문서들은 글자 단위로 줄을 넘긴다('건' / '조 상자').
    '-'로 끝난 줄도 붙인다 (주소 'cgi-' / 'bin').
    """
    if not a:
        return b
    if not wrapped:
        return a + "\n" + b
    hangul = lambda c: "가" <= c <= "힣"
    glue = (hangul(a[-1]) and hangul(b[0])) or a.endswith("-")
    return a + ("" if glue else " ") + b


def _segments(row: list[dict]) -> list[dict]:
    """한 줄 안에서 거의 붙어 있는 조각을 한 덩어리로 합친다 (x 순서로 들어온다)."""
    out: list[dict] = []
    for it in row:
        if out and it["box"][0] - out[-1]["box"][2] < SEG_GAP:
            prev = out[-1]
            out[-1] = {"text": prev["text"] + " " + it["text"], "score": min(prev["score"], it["score"]),
                       "box": [prev["box"][0], min(prev["box"][1], it["box"][1]),
                               it["box"][2], max(prev["box"][3], it["box"][3])]}
        else:
            out.append(dict(it))
    return out


def group_cells(items: list[dict], dpi: int = RULE_DPI) -> dict:
    """OCR 조각 → 칸 목록. dpi는 OCR 이미지를 그린 해상도 (좌표 단위).

    돌려주는 값: {"value_x": 값 열 시작, "cells": [...], "dropped": [...]}. 좌표는 들어온 dpi 그대로
    칸: {"kind", "label", "value", "y": [위, 아래]}
    - 항목: 왼쪽 항목명과 그 값 (값이 없으면 소제목)
    - 이어짐: 쪽 맨 위에서 항목명 없이 시작한 값. 앞 쪽 마지막 칸에 이어진다
    - 문단: 두 열이 아닌 쪽 폭 글 (16항 출처 목록, 맨 아래 안내문). 값이 없는 줄이 이어지는 구간에
            값 열 안으로 크게 넘어가는 줄이 있으면 그 구간 전체를 문단으로 본다. 들여쓴 줄에서 새 문단이 시작한다
    - 표 행: 오른쪽에 떨어진 덩어리가 여럿 나란히 있는 줄 (1쪽 물질명·CAS No. 표). value는 칸 목록
    """
    dropped = [i for i in items if i["score"] < MIN_SCORE]
    scale = RULE_DPI / dpi   # 기준값(300dpi)에 맞춰 좌표를 바꾼다
    items = [{**i, "box": [v * scale for v in i["box"]]} for i in items if i["score"] >= MIN_SCORE]
    if not items:
        return {"value_x": None, "cells": [], "dropped": dropped}
    out = _group_cells(items)
    if out["value_x"] is not None:
        out["value_x"] = round(out["value_x"] / scale)
    for c in out["cells"]:
        c["y"] = [round(v / scale) for v in c["y"]]
    return {**out, "dropped": dropped}


def _group_cells(items: list[dict]) -> dict:
    """group_cells 본체. items의 좌표는 RULE_DPI 픽셀이다."""
    vx = _value_col(items)
    split = (vx - COL_GAP) if vx is not None else max(i["box"][2] for i in items) + 1
    right = max((i["box"][2] for i in items if i["box"][0] >= split), default=0)

    rows = []
    for row in _rows(items):
        segs = _segments(row)
        rows.append({"left": [s for s in segs if s["box"][0] < split],
                     "vals": [s for s in segs if s["box"][0] >= split],
                     "y": [min(s["box"][1] for s in segs), max(s["box"][3] for s in segs)]})

    # 문단 구간: 값이 없는 줄이 이어지는 구간 중 값 열 안으로 크게 넘어가는 줄이 있는 곳
    para = [False] * len(rows)
    i = 0
    while i < len(rows):
        j = i
        while (j < len(rows) and not rows[j]["vals"] and rows[j]["left"]
               and (j == i or rows[j]["y"][0] - rows[j - 1]["y"][1] <= PARA_GAP)):
            j += 1
        if j > i and vx is not None and any(rows[k]["left"][-1]["box"][2] > vx + PARA_OVER for k in range(i, j)):
            para[i:j] = [True] * (j - i)
        i = max(j, i + 1)

    cells: list[dict] = []
    cur = None          # 지금 글을 모으는 칸
    last_x = None       # cur의 마지막 왼쪽 줄 [x0, x1]
    label_row = None    # cur의 마지막 항목명 줄 번호 (넘어간 항목명은 바로 다음 줄에만 온다)
    last_value = None   # cur의 마지막 값 줄 (넘어간 줄인지 보려고)
    for k, row in enumerate(rows):
        left, vals, y = row["left"], row["vals"], row["y"]

        if len(vals) > 1:   # 오른쪽에 떨어진 덩어리가 여럿: 표의 한 행
            label = " ".join(s["text"] for s in left) or None
            cells.append({"kind": "표 행", "label": label, "value": [s["text"] for s in vals], "y": y})
            cur = last_x = last_value = None
            continue

        if left:
            text = " ".join(s["text"] for s in left)
            x0, x1 = left[0]["box"][0], left[-1]["box"][2]
            if para[k]:
                # 이어지는 줄: 내어썼거나, 같은 들여쓰기인데 앞 줄이 끝까지 찼다. 들여썼으면 새 문단이다
                cont = cur and cur["kind"] == "문단" and (
                    x0 < last_x[0] - INDENT
                    or (abs(x0 - last_x[0]) <= INDENT and last_x[1] >= right * PARA_FILL))
                if cont:
                    cur["value"] = _join(cur["value"], text, True)
                else:
                    cur = {"kind": "문단", "label": None, "value": text, "y": list(y)}
                    cells.append(cur)
                cur["y"][1] = y[1]
                last_x, last_value = [x0, x1], None
                continue
            if (vx is not None and cur and cur["kind"] == "항목" and label_row == k - 1
                    and last_x[1] >= vx - LABEL_FILL
                    and x0 < last_x[0] - INDENT):   # 바로 아래 내어쓴 줄: 앞 항목명이 넘어온 것
                cur["label"] = _join(cur["label"], text, True)
                cur["y"][1] = y[1]
                last_x = [x0, x1]
            else:
                cur = {"kind": "항목", "label": text, "value": "", "y": list(y)}
                cells.append(cur)
                last_x, last_value = [x0, x1], None
            label_row = k

        if vals:
            v = vals[0]
            if cur is None or cur["kind"] == "문단":
                cur = {"kind": "이어짐", "label": None, "value": "", "y": list(y)}
                cells.append(cur)
                last_x = last_value = None
            wrapped = last_value is not None and last_value["box"][2] >= right * WRAP_FILL
            cur["value"] = _join(cur["value"], v["text"], wrapped)
            cur["y"][1] = y[1]
            last_value = v
    return {"value_x": vx, "cells": cells}


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
            ocr_json(doc_id, n).write_text(json.dumps({"dpi": dpi, "items": items}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
            ocr_txt(doc_id, n).write_text("\n".join(group_lines(items)), encoding="utf-8")
            write_cells(doc_id, n, items, dpi)
            scores = [i["score"] for i in items]
            summary.append({"page": n, "lines": len(items),
                            "mean_score": round(sum(scores) / max(len(scores), 1), 3),
                            "low_score_lines": sum(1 for s in scores if s < 0.8)})
    return summary


def read_ocr_json(path: Path) -> tuple[list[dict], int]:
    """p001.ocr.json → (조각 목록, dpi).

    dpi를 함께 저장하기 전(2026-10-27 이전)에 만든 파일은 조각 목록만 있다. 그때는 300dpi로만 OCR했다.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, OCR_DPI
    return data["items"], data["dpi"]


_DEG_C = re.compile(r"(?<=\d)(\s?)(?:°c|C)(?![A-Za-z0-9])")


def fix_symbols(text: str) -> str:
    """OCR이 낼 수 없는 기호를 되돌린다. 한국어 인식 모델 사전에 '℃'가 없어 숫자 뒤 'C'나 '°c'로 읽힌다 (S003).

    숫자 바로 뒤(공백 하나까지)의 단독 'C', '°c'만 '°C'로 바꾼다 ('℃'와 NFKC로 같다).
    'DEG C'처럼 숫자 뒤가 아니거나 'Cl', 'CO2'처럼 뒤에 글자가 붙은 C는 그대로 둔다.
    """
    return _DEG_C.sub(r"\1°C", text)


def page_text(items: list[dict], dpi: int) -> str:
    """OCR 조각 → 읽는 순서의 글 (텍스트층이 깨진 쪽의 대조 글). 기호를 되돌린다 (fix_symbols)."""
    from .layout import reading_text

    return fix_symbols(reading_text(items))


def write_cells(doc_id: str, page_no: int, items: list[dict], dpi: int) -> dict:
    cells = {"page": page_no, "dpi": dpi, **group_cells(items, dpi)}
    ocr_cells(doc_id, page_no).write_text(json.dumps(cells, ensure_ascii=False, indent=1), encoding="utf-8")
    return cells


def rebuild_cells(doc_id: str) -> list[dict]:
    """이미 OCR한 쪽(p001.ocr.json)에서 OCR을 다시 돌리지 않고 칸만 다시 만든다."""
    out = []
    for f in sorted(paths.page_dir(doc_id).glob("p*.ocr.json")):
        n = int(f.name[1:4])
        out.append(write_cells(doc_id, n, *read_ocr_json(f)))
    return out


def load_ocr_texts(doc_id: str) -> dict[int, str]:
    """OCR한 쪽의 글자. {쪽 번호: 글자}. OCR하지 않은 쪽은 없다."""
    out = {}
    for f in sorted(paths.page_dir(doc_id).glob("p*.ocr.txt")):
        out[int(f.name[1:4])] = f.read_text(encoding="utf-8")
    return out
