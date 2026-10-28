"""전처리: PDF → 쪽 이미지 + 쪽 텍스트층 + 텍스트층 상태 판별 (D-44).

동작하는 상태로 제공한다. C는 실행하고 결과(특히 text_layer 판별)를 확인한다.

출력 (paths 참고)
- data/pages/<문서번호>/p001.png ...   쪽 이미지 (기본 150dpi)
- data/pages/<문서번호>/p001.txt ...   쪽 텍스트층을 읽기 순서(layout.reading_order)로 놓은 것. 모델 입력 (D-44)
                                        선으로 그린 표는 한 행을 칸 순서대로 한 줄로 묶는다 (칸 사이는 공백 두 칸)
                                        PDF에 저장된 순서는 읽는 순서와 다를 수 있다 (S001 2쪽: 2번 항목이 1번보다 먼저)
- data/pages/<문서번호>/p001.match.txt 원문 대조용 텍스트층. 같은 읽기 순서에서 겹쳐 찍은 사본을 지운 것 (drop_overstrike)
- data/pages/<문서번호>/p001.ocr_input.txt 텍스트층을 믿을 수 없는 정상 쪽의 모델 입력·대조 글 (OCR, source.choose)
- data/pages/<문서번호>/tables/p002_t1.md 선으로 그린 데이터 표(성분·노출기준 등)를 Markdown으로 따로 꺼낸 것 (layout.is_data_table)
                                        항목|값 틀은 꺼내지 않는다. 모델 입력은 아니다. 쪽 번호와 그 쪽 표 순번(1부터)
- data/pages/<문서번호>/meta.json      쪽수, 쪽별 판별 수치·입력 출처(input_source), 문서 판정, 겹쳐찍기 글자 수, 전처리 버전

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
import shutil
from pathlib import Path

import pymupdf

from ..common import paths
from .layout import (char_items, continue_grid, is_data_table, page_lines, page_tables, reading_text, table_columns,
                     table_grid, table_md)
from .ocr import fix_symbols, read_ocr_json
from .source import choose, ocr_json_for, page_ocr_input

# 모델 입력(p001.txt)이 달라지는 변경마다 올린다. meta.json과 실행 기록(run_info.yaml)에 남아,
# 어떤 입력으로 돌린 실행인지 구분한다. 버전이 다른 meta로는 추출하지 않는다 (extract.runner)
PREPROCESS_VERSION = "2026-10-28-chars-wrap"   # 칸 글이 다음 줄로 넘어간 것을 그 칸에 잇는다 (layout.join_wrapped)
# 이전: "2026-10-28-chars" 텍스트층을 줄이 아니라 글자 좌표로 다시 맞춘다 (layout.char_items)
# 이전: "2026-10-27-xycut-tables-ocrpick" 텍스트층을 믿을 수 없는 정상 쪽은 OCR 글 (source.choose)
# 이전: "2026-10-27-xycut-tables" 선으로 그린 표의 행을 칸 순서대로 한 줄로 (layout.page_tables)
# 이전: "2026-10-27-xycut" 저장 순서(get_text) → 읽기 순서(layout.reading_order)

KK_RATIO_LIMIT = 0.05      # ㄲ받침 / ㄴ받침 비율이 이보다 크면 글꼴깨짐
SYMBOL_RATIO_LIMIT = 0.3   # 한글·영문이 아닌 글자 비율이 이보다 크면 글꼴깨짐
MIN_PAGE_CHARS = 20        # 이보다 글자가 적으면 글자가 없는 쪽
MIN_NN_FOR_KK = 20         # ㄴ받침이 이보다 적은 쪽은 ㄲ받침 비율을 믿을 수 없어 쪽만으로 판정하지 않는다
SCAN_COVER_LIMIT = 0.5     # 글자 없는 쪽에서 그림이 쪽 면적의 이 비율 이상이면 스캔 쪽 (로고만 있는 빈 쪽과 구분)
OVERSTRIKE_DX = 1.0        # 같은 글이 이 거리(pt) 안에서 다시 찍히면 겹쳐찍기의 사본이다
OVERSTRIKE_DY = 0.5        # (45번: 굵은 글씨를 0.1pt씩 밀어 5번 찍는다)


def page_match_txt(doc_id: str, page_no: int) -> Path:
    """원문 대조용 텍스트층. 쪽 번호는 1부터."""
    return paths.page_dir(doc_id) / f"p{page_no:03d}.match.txt"


def png_matches(png: Path, page, dpi: int) -> bool:
    """이미 그린 쪽 이미지가 이 화질(dpi)로 그린 크기와 같은가. 같으면 다시 그리지 않는다 (그리는 데 시간이 든다).

    PNG 머리(16~24바이트)의 가로·세로를 get_pixmap(dpi)이 낼 크기와 비교한다. 없거나 깨졌으면 False.
    """
    try:
        head = png.read_bytes()[:24]
    except FileNotFoundError:
        return False
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    want = (page.rect * pymupdf.Matrix(dpi / 72, dpi / 72)).irect   # get_pixmap(dpi)이 내는 크기
    return int.from_bytes(head[16:20], "big") == want.width and int.from_bytes(head[20:24], "big") == want.height


def tables_dir(doc_id: str) -> Path:
    """데이터 표 Markdown을 두는 곳."""
    return paths.page_dir(doc_id) / "tables"


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


def drop_overstrike(lines: list[list[dict]]) -> tuple[list[list[dict]], int]:
    """겹쳐 찍은 사본을 지운다. lines는 줄마다 조각 목록 [{text, bbox}] (get_text('dict') 순서).

    같은 자리(OVERSTRIKE_DX·DY 안)에서 한쪽이 다른 쪽의 앞부분인 글은 사본으로 보고 하나만 남긴다.
    사본 중 가장 긴 것을 처음 나온 자리에 남긴다 (45번 1쪽: 마지막 사본에만 '(MSDS)'가 이어 붙어 있다).
    돌려주는 값: (남은 줄, 지운 글자 수)
    """
    out: list[list[dict]] = [[] for _ in lines]
    anchors: list[dict] = []
    removed = 0
    for li, line in enumerate(lines):
        for s in line:
            t = s["text"].strip()
            x0, y0 = s["bbox"][0], s["bbox"][1]
            if t:
                hit = next((a for a in anchors
                            if abs(a["y0"] - y0) < OVERSTRIKE_DY and abs(a["x0"] - x0) < OVERSTRIKE_DX
                            and (t.startswith(a["text"]) or a["text"].startswith(t))), None)
                if hit:
                    if len(t) > len(hit["text"]):
                        removed += len(hit["text"])
                        out[hit["line"]][hit["pos"]] = dict(s)
                        hit["text"] = t
                    else:
                        removed += len(t)
                    continue
                anchors.append({"x0": x0, "y0": y0, "text": t, "line": li, "pos": len(out[li])})
            out[li].append(dict(s))
    return out, removed


def _lines_text(lines: list[list[dict]]) -> str:
    return "".join("".join(s["text"] for s in line) + "\n" for line in lines if line)


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
    shutil.rmtree(tables_dir(doc_id), ignore_errors=True)   # 예전 실행의 표가 남지 않게

    doc = pymupdf.open(pdf_path)
    pages = []
    layer_match = {}   # 쪽 번호 → 사본을 지운 텍스트층 (출처 고르기에 쓴다)
    page_obj = {}      # 쪽 번호 → PyMuPDF 쪽 (OCR 글에도 같은 표 묶기를 하려고)
    layer_items = {}   # 쪽 번호 → 텍스트층 조각 (표 Markdown에 쓴다)
    totals = {"chars": 0, "hangul": 0, "kk": 0, "nn": 0, "latin": 0, "symbol": 0}
    for i, page in enumerate(doc, start=1):
        lines = page_lines(page)
        tables = page_tables(page)
        items = char_items(page)
        text = reading_text(items, tables) + "\n"
        paths.page_txt(doc_id, i).write_text(text, encoding="utf-8")
        if not png_matches(paths.page_png(doc_id, i), page, dpi):
            page.get_pixmap(dpi=dpi).save(paths.page_png(doc_id, i))
        c = _counts(text)
        for k in totals:
            totals[k] += c[k]
        _, overstrike = drop_overstrike(lines)   # 사본 글자 수만 센다. char_items가 사본을 이미 지웠다
        layer_match[i], page_obj[i], layer_items[i] = text, page, items
        page_match_txt(doc_id, i).write_text(layer_match[i], encoding="utf-8")
        cover = _image_cover(page)
        state = judge_page(c, cover)
        pages.append({"page": i, "state": state, "image_cover": round(cover, 3), **c, "overstrike": overstrike})

    text_layer = judge_doc([p["state"] for p in pages], totals)
    pages = follow_doc(pages, text_layer)
    pages = [_pick_source(doc_id, p, layer_match[p["page"]], page_obj[p["page"]]) for p in pages]
    prev = None   # 앞 쪽 마지막 데이터 표 (열 자리, 머리글). 다음 쪽에서 이어지는 표를 나눌 때 쓴다
    for k, p in enumerate(pages):
        pages[k], prev = _write_tables(doc_id, p, layer_items[p["page"]], page_obj[p["page"]], prev)
    language = judge_language(totals)
    if text_layer in ("글꼴깨짐", "없음") and totals["hangul"] == 0:
        language = None   # 글자를 믿을 수 없어 언어를 판정하지 않는다. manifest에서 사람이 채운다
    meta = {
        "doc_id": doc_id,
        "preprocess_version": PREPROCESS_VERSION,
        "source_file": pdf_path.name,
        "page_count": len(pages),
        "dpi": dpi,
        "text_layer": text_layer,
        "language": language,
        "input_mode": "이미지+글자" if text_layer in ("정상", "혼합") else "이미지만",
        "totals": totals,
        "overstrike": sum(p["overstrike"] for p in pages),   # 겹쳐 찍은 사본 글자 수. 0이 아니면 대조는 p001.match.txt로
        "pages": pages,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _pick_source(doc_id: str, p: dict, layer: str, page) -> dict:
    """정상 쪽의 모델 입력 출처를 고른다 (source.choose). OCR이면 p001.ocr_input.txt를 쓴다.

    OCR 결과가 없으면 텍스트층이다. OCR을 나중에 돌렸으면 전처리를 --force로 다시 돌려야 반영된다.
    정상이 아닌 쪽(글꼴깨짐·이미지만)은 모델이 이미지만 보므로 고르지 않는다.
    """
    out_ocr = page_ocr_input(doc_id, p["page"])
    out_ocr.unlink(missing_ok=True)
    if p["state"] != "정상":
        return p
    f = ocr_json_for(doc_id, p["page"])
    ocr = None
    if f is not None:
        items, dpi = read_ocr_json(f)
        ocr = fix_symbols(reading_text(items, page_tables(page, dpi / 72))) + "\n"
    pick = choose(layer, ocr)
    if pick["input_source"] == "OCR":
        out_ocr.write_text(ocr, encoding="utf-8")
    return {**p, **pick}


def _write_tables(doc_id: str, p: dict, items: list[dict], page, prev: dict | None) -> tuple[dict, dict | None]:
    """정상 쪽의 선으로 그린 표 중 데이터 표만 tables/pXXX_tN.md로 쓴다. 칸 글은 모델 입력과 같은 출처에서 읽는다.

    meta 쪽 항목에 tables(쓴 파일 이름)와 frames(꺼내지 않은 항목|값 틀 수)를 남긴다.
    글꼴깨짐·이미지만 쪽은 글자를 믿을 수 없어 꺼내지 않는다.
    prev는 앞 쪽 마지막 데이터 표의 열 자리(pt)와 머리글이다. 이 쪽 표가 그 머리글로 시작하면 열 선이 없어도
    앞 쪽 열 자리로 나눈다 (layout.continue_grid, M013 3쪽). 바로 앞 쪽의 표만 잇는다.
    돌려주는 값: (쪽 항목, 다음 쪽에 넘길 prev)
    """
    if p["state"] != "정상":
        return p, None
    scale = 1.0
    if p.get("input_source") == "OCR":
        items, dpi = read_ocr_json(ocr_json_for(doc_id, p["page"]))
        scale = dpi / 72
    written, frames, last = [], 0, None
    for n, table in enumerate(page_tables(page, scale), start=1):
        grid = table_grid(items, table)
        if is_data_table(grid):
            last = {"cols": [(a / scale, b / scale) for a, b in table_columns(table)], "head": grid[0]}
        else:
            cols = prev and [(a * scale, b * scale) for a, b in prev["cols"]]
            grid = cols and n == 1 and continue_grid(items, table, cols, prev["head"])   # 이어진 표는 쪽 맨 위에 있다
            if not grid:
                frames += 1
                continue
            last = prev
        name = f"p{p['page']:03d}_t{n}.md"
        tables_dir(doc_id).mkdir(exist_ok=True)
        (tables_dir(doc_id) / name).write_text(table_md(grid), encoding="utf-8")
        written.append(name)
    return {**p, "tables": written, "frames": frames}, last


def load_pages(doc_id: str) -> dict:
    """추출 단계에서 쓰는 쪽 입력. {'meta': ..., 'pages': [{page, image, text, match_text, state, source}]}

    text는 모델 입력, match_text는 원문 대조(checks.source_match)에 쓴다. 겹쳐찍기가 없으면 둘의 글자가 같다.
    match_text 파일이 없으면(이 기능 전에 전처리한 결과) text를 쓴다.
    source가 'OCR'인 쪽은 둘 다 OCR 글(p001.ocr_input.txt)이다. 모델이 읽은 글과 대조하는 글을 맞춘다.
    """
    meta = json.loads(paths.page_meta(doc_id).read_text(encoding="utf-8"))
    out = []
    for p in meta["pages"]:
        n = p["page"]
        text = paths.page_txt(doc_id, n).read_text(encoding="utf-8")
        mt = page_match_txt(doc_id, n)
        match_text = mt.read_text(encoding="utf-8") if mt.exists() else text
        source = p.get("input_source", "텍스트층")
        if source == "OCR":
            text = match_text = page_ocr_input(doc_id, n).read_text(encoding="utf-8")
        out.append({
            "page": n,
            "image": paths.page_png(doc_id, n),
            "text": text,
            "match_text": match_text,
            "state": p["state"],
            "source": source,
        })
    return {"meta": meta, "pages": out}
