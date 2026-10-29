"""version13: PR #91's XY-cut reading-order text extraction (layout.py) as the
base method, kept as plain image+txt output (not layout.py's own meta.json /
.match.txt / tables/*.md convention), with version12's Docling TableFormer
grid substitution layered on top.

Why: PR #91 (now on origin/main) replaced the naive "join lines by y-distance"
approach we used in version2/8/9/12 with a proper recursive XY-cut reading-
order algorithm (layout.reading_order) that also merges table rows using the
PDF's actual drawn table-line geometry (layout.page_tables / _table_rows).
That's a strictly better base than our own y-tolerance row grouping.

This script keeps our own simple output shape (pNNN.png + pNNN.txt, optional
L001 line numbers, "|"-joined table rows) instead of switching to layout.py's
own file layout, and -- like version12 -- additionally swaps in Docling's
TableFormer grid for any table whose cells can be confidently matched against
the page's extracted items, for tables layout.py's own line-based detection
might miss (e.g. no visible grid lines) or get wrong.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "data" / "pages"
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymupdf

from msds.preprocess import layout  # noqa: E402

from ocr_batch_version2 import VERIFIED_IMAGE_TEXT, find_pdf, paddle_data  # noqa: E402
from ocr_batch_version12 import (  # noqa: E402
    _exec_with_nvidia_pip_libs_on_ld_path,
    build_table_converter,
    docling_tables_by_page,
)


def norm(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value or "").split())


def paddle_items(ocr, image: Path, doc_id: str) -> list[dict]:
    """PaddleOCR 결과를 layout.py 조각 형식({'text', 'box'})으로 변환한다."""
    pdata = paddle_data(ocr, image)
    texts = pdata.get("rec_texts", [])
    scores = pdata.get("rec_scores", [])
    boxes = pdata.get("rec_boxes", [])
    items = []
    for raw_text, score, raw_box in zip(texts, scores, boxes):
        text = str(raw_text).strip()
        if not text:
            continue
        confirmed = VERIFIED_IMAGE_TEXT.get(doc_id, {}).get(text)
        items.append({"text": confirmed or text, "box": [float(v) for v in raw_box], "confidence": float(score)})
    return items


def covered_by_layout_tables(items: list[dict], layout_tables: list) -> set[int]:
    """layout.page_tables()가 이미 찾은(=선 정보로 있는) 표 영역 안의 조각 id 집합.

    이 영역은 layout.reading_order()가 _table_rows로 이미 올바르게 칸 순서대로
    묶어주므로, Docling으로 다시 덮어쓸 필요가 없다 (불필요한 재작업/잠재적 악화 방지).
    """
    covered: set[int] = set()
    for table in layout_tables:
        for row in table:
            for box in row:
                if box is None:
                    continue
                covered.update(id(i) for i in items if layout._inside(i, box))
    return covered


def match_table_to_items(
    table_rows: list[list[str]], items: list[dict], already_covered: set[int]
) -> list[dict] | None:
    """Docling 표의 셀 텍스트와 layout.py 조각(items)을 텍스트 일치로 매칭한다.

    layout.page_tables()가 이미 선 정보로 찾아낸 표(= already_covered 조각이 과반)는
    건드리지 않는다 — Docling은 **PyMuPDF가 표 자체를 못 찾은 경우(테두리 없는 표 등)에만
    보조로 쓴다.** 일치하는 조각이 70% 미만이어도 마찬가지로 None.
    """
    cell_texts = [norm(cell) for row in table_rows for cell in row if cell.strip()]
    if not cell_texts:
        return None
    remaining = list(cell_texts)
    matched: list[dict] = []
    for item in items:
        item_norm = norm(item["text"])
        if item_norm and item_norm in remaining:
            matched.append(item)
            remaining.remove(item_norm)
    if len(matched) < max(2, int(0.7 * len(cell_texts))):
        return None
    if sum(1 for i in matched if id(i) in already_covered) / len(matched) >= 0.5:
        return None   # layout.py가 이미 선표로 올바르게 처리하고 있던 영역 -> 손대지 않음
    return matched


def page_text(items: list[dict], tables: list, table_matches: list[tuple[list[dict], list[list[str]]]], line_numbers: bool) -> str:
    matched_ids = {id(i) for matched, _ in table_matches for i in matched}
    body_items = [i for i in items if id(i) not in matched_ids]

    blocks: list[tuple[float, list[str]]] = []
    for row in layout.reading_order(body_items, tables):
        center = sum((i["box"][1] + i["box"][3]) / 2 for i in row) / len(row)
        # layout._table_rows가 선표 행 하나를 조각 하나로 합칠 때 parts(칸별 텍스트)를 남겨둔다.
        # 우리 컨벤션(표는 '|')을 지키려고, 그런 행은 parts를 '|'로 다시 join한다.
        if len(row) == 1 and len(row[0].get("parts", [])) > 1:
            text = " | ".join(p["text"].strip() for p in row[0]["parts"])
        else:
            text = row[0]["text"].rstrip() + "".join(" " + i["text"].strip() for i in row[1:])
        blocks.append((center, [text]))

    for matched, table_rows in table_matches:
        center = sum((i["box"][1] + i["box"][3]) / 2 for i in matched) / len(matched)
        blocks.append((center, [" | ".join(row) for row in table_rows]))

    blocks.sort(key=lambda b: b[0])
    lines = [line for _, block_lines in blocks for line in block_lines]
    if line_numbers:
        lines = [f"L{index:03d} {line}" for index, line in enumerate(lines, start=1)]
    return "\n".join(lines).rstrip() + "\n"


def main(
    output_version: str = "version13",
    line_numbers: bool = True,
    force: bool = False,
    selected_doc_id: str | None = None,
) -> int:
    from paddleocr import PaddleOCR

    with (ROOT / "data" / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        docs = list(csv.DictReader(stream))

    ocr = PaddleOCR(
        lang="korean",
        device="gpu",
        text_detection_model_name="PP-OCRv5_server_det",
        text_detection_model_dir=str(Path.home() / ".paddlex" / "official_models" / "PP-OCRv5_server_det"),
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        text_recognition_model_dir=str(Path.home() / ".paddlex" / "official_models" / "korean_PP-OCRv5_mobile_rec"),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    table_converter = build_table_converter()

    overall = []
    for row in docs:
        doc_id = row["doc_id"]
        if selected_doc_id and doc_id != selected_doc_id:
            continue
        page_dir = PAGES / doc_id
        images = sorted(page_dir.glob("p[0-9][0-9][0-9].png"))
        if not images:
            page_dir = PAGES / "version1" / doc_id
            images = sorted(page_dir.glob("p[0-9][0-9][0-9].png"))
        if not images:
            continue
        output = PAGES / output_version / doc_id
        output.mkdir(parents=True, exist_ok=True)
        for image in images:
            target_image = output / image.name
            if not target_image.exists():
                shutil.copy2(image, target_image)

        summary_path = output / "summary.json"
        if not force and summary_path.exists() and len(list(output.glob("p[0-9][0-9][0-9].txt"))) == len(images):
            print(f"[{doc_id}] completed; skipped", flush=True)
            continue

        usable_pdf_text = row["text_layer"] == "정상"
        pdf = find_pdf(row["source_file"])
        document_started = time.perf_counter()
        docling_started = time.perf_counter()
        tables_by_page = docling_tables_by_page(table_converter, pdf) if usable_pdf_text else {}
        docling_seconds = round(time.perf_counter() - docling_started, 6)

        page_rows = []
        with pymupdf.open(pdf) as document:
            for index, image in enumerate(images):
                page_started = time.perf_counter()
                page_no = index + 1
                paddle_seconds = 0.0
                if usable_pdf_text:
                    page = document[index]
                    items = layout.char_items(page)
                    tables = layout.page_tables(page)
                else:
                    paddle_started = time.perf_counter()
                    items = paddle_items(ocr, image, doc_id)
                    tables = []
                    paddle_seconds = round(time.perf_counter() - paddle_started, 6)

                already_covered = covered_by_layout_tables(items, tables)
                table_matches = []
                for table_rows in tables_by_page.get(page_no, []):
                    matched = match_table_to_items(table_rows, items, already_covered)
                    if matched is not None:
                        table_matches.append((matched, table_rows))

                text = page_text(items, tables, table_matches, line_numbers)
                (output / f"p{page_no:03d}.txt").write_text(text, encoding="utf-8")
                page_rows.append({
                    "page": page_no,
                    "mode": "pdf_xycut" if usable_pdf_text else "paddle_full_page",
                    "docling_tables_matched": len(table_matches),
                    "docling_tables_detected": len(tables_by_page.get(page_no, [])),
                    "paddle_ocr_seconds": paddle_seconds,
                    "page_total_seconds": round(time.perf_counter() - page_started, 6),
                })
                print(f"[{doc_id}] {page_no}/{len(images)}", flush=True)

        config = {
            "doc_id": doc_id,
            "version": output_version,
            "dpi": 200,
            "method": "PR#91 layout.py XY-cut reading order (PDF char items) or PaddleOCR full page + Docling TableFormer (GPU) grid substitution for matched tables",
            "line_numbers": line_numbers,
            "timing": {
                "document_total_seconds": round(time.perf_counter() - document_started, 6),
                "docling_table_detection_seconds": docling_seconds,
            },
        }
        (output / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "summary.json").write_text(json.dumps(page_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        overall.append({
            "doc_id": doc_id,
            "pages": len(page_rows),
            "docling_tables_matched": sum(x["docling_tables_matched"] for x in page_rows),
            "docling_tables_detected": sum(x["docling_tables_detected"] for x in page_rows),
        })

    (PAGES / output_version / "overall_summary.json").write_text(
        json.dumps(overall, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    _exec_with_nvidia_pip_libs_on_ld_path()
    parser = argparse.ArgumentParser(description="version13: PR#91 XY-cut 읽기순서 + Docling 표 결합")
    parser.add_argument("--doc-id", help="한 문서만 실행")
    parser.add_argument("--force", action="store_true", help="기존 결과도 새로 실행")
    parser.add_argument("--output-version", default="version13", help="출력 폴더 이름")
    parser.add_argument("--no-line-numbers", action="store_true", help="L001 줄번호 끄기")
    args = parser.parse_args()
    raise SystemExit(
        main(
            output_version=args.output_version,
            line_numbers=not args.no_line_numbers,
            force=args.force,
            selected_doc_id=args.doc_id,
        )
    )
