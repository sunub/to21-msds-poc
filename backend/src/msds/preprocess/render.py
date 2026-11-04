"""전처리: PDF → 쪽 이미지 + 쪽 텍스트층 + 텍스트층 상태 판별 (D-44).

동작하는 상태로 제공한다. C는 실행하고 결과(특히 text_layer 판별)를 확인한다.

출력 (paths 참고)
- data/pages/<문서번호>/p001.png ...   쪽 이미지 (기본 150dpi)
- data/pages/<문서번호>/p001.txt ...   쪽 텍스트층을 읽기 순서(layout.reading_order)로 놓은 것. 모델 입력 (D-44)
                                        선으로 그린 표는 한 행을 칸 순서대로 한 줄로 묶는다 (칸 사이는 공백 두 칸)
                                        PDF에 저장된 순서는 읽는 순서와 다를 수 있다 (S001 2쪽: 2번 항목이 1번보다 먼저)
- data/pages/<문서번호>/p001.match.txt 원문 대조용 텍스트층. 같은 읽기 순서에서 겹쳐 찍은 사본을 지운 것 (drop_overstrike)
- data/pages/<문서번호>/p001.ocr_input.txt 출처가 OCR인 쪽의 최종 글 (OCR). 텍스트층을 믿을 수 없는 정상 쪽(source.choose)은
                                        모델 입력이기도 하다. 깨진 쪽(S003)은 대조에만 쓰고 모델은 이미지만 본다
- data/pages/<문서번호>/tables/p002_t1.md 선으로 그린 데이터 표(성분·노출기준 등)를 Markdown으로 따로 꺼낸 것 (layout.is_data_table)
                                        항목|값 틀은 꺼내지 않는다. 모델 입력은 아니다. 쪽 번호와 그 쪽 표 순번(1부터)
- data/pages/<문서번호>/meta.json      쪽수, 쪽별 판별 수치·입력 출처(input_source), 문서 판정, 겹쳐찍기 글자 수, 전처리 버전
                                        쪽마다 최종 글 하나: text_source(텍스트층 / OCR / 없음)와 text_file(그 글 파일 이름, 없음이면 null).
                                        밖에서 쪽 글을 읽을 때는 text_file만 본다 (_pick_source)

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
from collections.abc import Callable
from pathlib import Path

import pymupdf

from ..common import paths
from .layout import (char_items, continue_grid, is_data_table, page_lines, page_tables, reading_text, section_headings,
                     table_columns, table_grid, table_md)
from .ocr import fix_symbols, read_ocr_json
from .source import choose, ocr_json_for, page_ocr_input

# 모델 입력(p001.txt)이 달라지는 변경마다 올린다. meta.json과 실행 기록(run_info.yaml)에 남아,
# 어떤 입력으로 돌린 실행인지 구분한다. 버전이 다른 meta로는 추출하지 않는다 (extract.runner)
PREPROCESS_VERSION = "2026-10-29-wrap-mincol"   # 좁은 열(라벨)은 다음 줄을 잇지 않는다 (layout.MIN_WRAP_COL)
# 이전: "2026-10-28-chars-wrap" 칸 글이 다음 줄로 넘어간 것을 그 칸에 잇는다 (layout.join_wrapped)
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


def page_match_txt(doc_id: str, page_no: int, *, pages_root: Path | None = None) -> Path:
    """원문 대조용 텍스트층. 쪽 번호는 1부터."""
    doc_dir = paths.page_dir(doc_id) if pages_root is None else Path(pages_root) / doc_id
    return doc_dir / f"p{page_no:03d}.match.txt"


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


def tables_dir(doc_id: str, *, pages_root: Path | None = None) -> Path:
    """데이터 표 Markdown을 두는 곳."""
    doc_dir = paths.page_dir(doc_id) if pages_root is None else Path(pages_root) / doc_id
    return doc_dir / "tables"


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


def judge_states(doc) -> tuple[list[str], str]:
    """PyMuPDF 문서 → (쪽마다 텍스트층 상태, 문서 판정). preprocess와 같은 판정이다 (judge_page, judge_doc, follow_doc).

    파일을 쓰지 않는다. 전처리 밖의 출력 폴더(scripts/ocr_batch_version13.py)가 meta에 쪽 상태를 남길 때 쓴다.
    """
    pages, totals = [], {"chars": 0, "hangul": 0, "kk": 0, "nn": 0, "latin": 0, "symbol": 0}
    for i, page in enumerate(doc, start=1):
        c = _counts(reading_text(char_items(page), page_tables(page)) + "\n")
        for k in totals:
            totals[k] += c[k]
        pages.append({"page": i, "state": judge_page(c, _image_cover(page)), **c})   # follow_doc이 글자 수(nn)를 본다
    text_layer = judge_doc([p["state"] for p in pages], totals)
    return [p["state"] for p in follow_doc(pages, text_layer)], text_layer


def preprocess(pdf_path: Path, doc_id: str, dpi: int = 150, force: bool = False,
               on_page: Callable[[int, int], None] | None = None, *, pages_root: Path | None = None) -> dict:
    """on_page(쪽 번호, 전체 쪽수)는 쪽 이미지와 글을 쓴 뒤 쪽마다 한 번 부른다 (서비스 API의 진행 표시).
    이미 만든 결과를 그대로 돌려줄 때(force 아님)는 부르지 않는다.
    pages_root를 지정하면 모든 출력과 기존 OCR 입력을 해당 루트의 문서 폴더에서만 읽고 쓴다."""
    out_dir = paths.page_dir(doc_id) if pages_root is None else Path(pages_root) / doc_id
    meta_path = out_dir / "meta.json"
    if meta_path.exists() and not force:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(tables_dir(doc_id, pages_root=pages_root), ignore_errors=True)   # 예전 실행의 표가 남지 않게

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
        (out_dir / f"p{i:03d}.txt").write_text(text, encoding="utf-8")
        png = out_dir / f"p{i:03d}.png"
        if not png_matches(png, page, dpi):
            page.get_pixmap(dpi=dpi).save(png)
        c = _counts(text)
        for k in totals:
            totals[k] += c[k]
        _, overstrike = drop_overstrike(lines)   # 사본 글자 수만 센다. char_items가 사본을 이미 지웠다
        layer_match[i], page_obj[i], layer_items[i] = text, page, items
        page_match_txt(doc_id, i, pages_root=pages_root).write_text(layer_match[i], encoding="utf-8")
        cover = _image_cover(page)
        state = judge_page(c, cover)
        pages.append({"page": i, "state": state, "image_cover": round(cover, 3), **c, "overstrike": overstrike})
        if on_page:
            on_page(i, doc.page_count)

    text_layer = judge_doc([p["state"] for p in pages], totals)
    pages = follow_doc(pages, text_layer)
    pages = [_pick_source(doc_id, p, layer_match[p["page"]], page_obj[p["page"]], pages_root=pages_root) for p in pages]
    prev = None   # 앞 쪽 마지막 데이터 표 (열 자리, 머리글). 다음 쪽에서 이어지는 표를 나눌 때 쓴다
    section = None   # 앞 쪽까지 본 마지막 항 (번호, 제목). 쪽 맨 위의 표는 이 항에 속한다
    for k, p in enumerate(pages):
        pages[k], prev, section = _write_tables(doc_id, p, layer_items[p["page"]], page_obj[p["page"]], prev, section,
                                               pages_root=pages_root)
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


def _pick_source(doc_id: str, p: dict, layer: str, page, *, pages_root: Path | None = None) -> dict:
    """쪽의 최종 글(text_source, text_file)과, 정상 쪽이면 모델 입력 출처(input_source, source.choose)를 고른다.

    최종 글은 쪽마다 하나다. 원문 대조와 외부에서 쪽 글을 읽을 때는 text_file만 본다.
    - 정상 쪽: 모델 입력과 같은 출처. 텍스트층이면 p001.match.txt, OCR이면 p001.ocr_input.txt
    - 정상이 아닌 쪽(글꼴깨짐·이미지만): OCR이 있으면 OCR(p001.ocr_input.txt), 없으면 '없음'(text_file None).
      모델은 여전히 이미지만 보므로 input_source는 두지 않는다 (client.page_parts)
    OCR 결과가 없으면 텍스트층이다. OCR을 나중에 돌렸으면 전처리를 --force로 다시 돌려야 반영된다.
    """
    n = p["page"]
    out_ocr = page_ocr_input(doc_id, n, pages_root=pages_root)
    out_ocr.unlink(missing_ok=True)
    f = ocr_json_for(doc_id, n, pages_root=pages_root)
    ocr = None
    if f is not None:
        items, dpi = read_ocr_json(f)
        ocr = fix_symbols(reading_text(items, page_tables(page, dpi / 72))) + "\n"
    if p["state"] != "정상":
        pick = {"text_source": "OCR" if ocr is not None else "없음"}
    else:
        pick = choose(layer, ocr)
        pick["text_source"] = pick["input_source"]
    if pick["text_source"] == "OCR":
        out_ocr.write_text(ocr, encoding="utf-8")
    pick["text_file"] = {"OCR": out_ocr.name, "텍스트층": page_match_txt(doc_id, n, pages_root=pages_root).name}.get(pick["text_source"])
    return {**p, **pick}


def _write_tables(doc_id: str, p: dict, items: list[dict], page, prev: dict | None,
                  section: tuple[int, str] | None, *, pages_root: Path | None = None) -> tuple[dict, dict | None, tuple[int, str] | None]:
    """선으로 그린 표 중 데이터 표만 tables/pXXX_tN.md로 쓴다. 칸 글은 그 쪽의 최종 글(text_source)과 같은 출처에서 읽는다.

    meta 쪽 항목에 tables와 frames(꺼내지 않은 항목|값 틀 수)를 남긴다. tables는 표마다
    {"file": 문서 폴더 기준 경로 (tables/p002_t1.md, text_file과 같은 기준), "section": 속한 항 제목 (못 찾으면 null),
     "box": 쪽 안 위치 [x0, y0, x1, y1] (pt, 72dpi)}.
    항은 표 위에서 가장 가까운 항 제목(layout.section_headings)이고, 이 쪽에서 표 위에 항 제목이 없으면
    앞 쪽에서 넘어온 항(section)이다. 쪽 이미지(p001.png)는 dpi/72배 좌표다.
    최종 글이 OCR이면 글꼴깨짐 쪽도 OCR 글로 칸을 채운다 (S003 1쪽: 글꼴은 깨졌지만 표 선은 멀쩡하다).
    최종 글이 없는 쪽(없음)은 꺼내지 않는다.
    prev는 앞 쪽 마지막 데이터 표의 열 자리(pt)와 머리글이다. 이 쪽 표가 그 머리글로 시작하면 열 선이 없어도
    앞 쪽 열 자리로 나눈다 (layout.continue_grid, M013 3쪽). 바로 앞 쪽의 표만 잇는다.
    돌려주는 값: (쪽 항목, 다음 쪽에 넘길 prev, 다음 쪽에 넘길 section). 글이 없는 쪽은 section을 그대로 넘긴다
    """
    if p.get("text_source") not in ("텍스트층", "OCR"):
        return p, None, section
    scale = 1.0
    if p["text_source"] == "OCR":
        items, dpi = read_ocr_json(ocr_json_for(doc_id, p["page"], pages_root=pages_root))
        scale = dpi / 72
    return write_page_tables(tables_dir(doc_id, pages_root=pages_root), p, items, page, scale, prev, section)


def write_page_tables(out_dir: Path, p: dict, items: list[dict], page, scale: float, prev: dict | None,
                      section: tuple[int, str] | None) -> tuple[dict, dict | None, tuple[int, str] | None]:
    """_write_tables의 본체. 조각(items, 좌표는 pt의 scale배)에서 데이터 표를 out_dir/pXXX_tN.md로 쓴다.

    tables[].file은 out_dir의 이름을 붙인 문서 폴더 기준 경로다 (out_dir은 문서 폴더 바로 아래 tables/).
    전처리 밖의 출력 폴더(scripts/ocr_batch_version13.py)도 이 함수로 같은 meta를 남긴다.
    """
    heads = section_headings(items, after=section[0] if section else 0)
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
        out_dir.mkdir(exist_ok=True)
        (out_dir / name).write_text(table_md(grid), encoding="utf-8")
        boxes = [c for r in table for c in r if c]
        top = min(c[1] for c in boxes)
        above = [(h[1], h[2]) for h in heads if h[0] < top]
        sec = above[-1] if above else section
        box = [round(f(c[k] for c in boxes) / scale, 1) for f, k in ((min, 0), (min, 1), (max, 2), (max, 3))]
        written.append({"file": f"{out_dir.name}/{name}", "section": sec and sec[1], "box": box})
    if heads:
        section = heads[-1][1:]
    return {**p, "tables": written, "frames": frames}, last, section


def load_pages(doc_id: str, *, pages_root: Path | None = None) -> dict:
    """추출 단계에서 쓰는 쪽 입력. {'meta': ..., 'pages': [{page, image, text, match_text, state, source}]}

    source는 그 쪽의 최종 글 출처(meta의 text_source: 텍스트층 / OCR / 없음), match_text는 최종 글로
    원문 대조(checks.source_match, match_pages)에 쓴다. text는 모델 입력 글이다.
    - 정상 쪽: 텍스트층이면 text는 p001.txt, match_text는 겹쳐찍기 사본을 지운 p001.match.txt (없으면 text).
      OCR이면 둘 다 OCR 글(p001.ocr_input.txt). 모델이 읽은 글과 대조하는 글을 맞춘다
    - 정상이 아닌 쪽: 모델은 이미지만 보므로 text는 "". 깨진 텍스트층은 내보내지 않는다
    text_source가 없는 meta(이 기능 전에 전처리한 결과)는 정상 쪽은 input_source, 아닌 쪽은 '없음'으로 본다.
    """
    doc_dir = paths.page_dir(doc_id) if pages_root is None else Path(pages_root) / doc_id
    meta = json.loads((doc_dir / "meta.json").read_text(encoding="utf-8"))
    out = []
    for p in meta["pages"]:
        n = p["page"]
        normal = p["state"] == "정상"
        source = p.get("text_source") or (p.get("input_source", "텍스트층") if normal else "없음")
        text = match_text = ""
        if source == "OCR":
            text_full = page_ocr_input(doc_id, n, pages_root=pages_root).read_text(encoding="utf-8")
            match_text = text_full
            mt = page_match_txt(doc_id, n, pages_root=pages_root)
            if "preprocess_version" not in meta and mt.exists():   # version17: 줄 번호를 뗀 대조용 글
                match_text = mt.read_text(encoding="utf-8")
            text = text_full if normal else ""
        elif source == "텍스트층":
            text = (doc_dir / f"p{n:03d}.txt").read_text(encoding="utf-8")
            mt = page_match_txt(doc_id, n, pages_root=pages_root)
            match_text = mt.read_text(encoding="utf-8") if mt.exists() else text
        out.append({
            "page": n,
            "image": doc_dir / f"p{n:03d}.png",
            "text": text,
            "match_text": match_text,
            "state": p["state"],
            "source": source,
        })
    return {"meta": meta, "pages": out}


def match_pages(pages: list[dict]) -> tuple[dict[int, str], dict[int, str]]:
    """load_pages의 쪽 목록 → 원문 대조(checks.source_match.match)에 넘길 (쪽 글, 쪽 상태).

    쪽 글은 최종 글(match_text)이다. 최종 글이 있는 쪽은 텍스트층이 깨졌어도(S003, OCR) '정상'으로 넘겨 대조하고,
    최종 글이 없는 쪽(source '없음')만 원래 상태를 넘겨 '대조불가'가 되게 한다.
    """
    texts = {p["page"]: p["match_text"] for p in pages}
    states = {p["page"]: "정상" if p["source"] != "없음" else p["state"] for p in pages}
    return texts, states
