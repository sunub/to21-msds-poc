"""version12: version9's method (PDF text + PaddleOCR, pipe_rows, line_numbers)
as the base, with Docling's TableFormer (GPU) used ONLY to re-serialize the
rows that actually belong to a detected table.

Why: version9's row grouping joins cells purely by y-coordinate proximity
(entries_to_text in ocr_batch_version2.py), which works for simple key/value
rows but misreads borderless multi-line tables (merges unrelated lines,
splits one logical row across two "rows"). version11 (pure Docling) fixed
that but, for tables Docling's layout model fails to detect as a table at
all (no visible grid lines), it falls back to plain reading order and loses
the "|" structure entirely -- worse than version9 for those pages.

So: keep version9's per-entry extraction (same pdf_lines/paddle_data dedup
logic, same output format) for everything, and only swap in Docling's table
grid where we can confidently line it up with our own entries (exact text
match on a PDF-text-layer page). Anything we can't confidently match is left
exactly as version9 would have produced it -- no regression.
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

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "data" / "pages"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ocr_batch_version2 import (  # noqa: E402
    VERIFIED_IMAGE_TEXT,
    coverage,
    find_pdf,
    norm,
    paddle_data,
    pdf_lines,
)


def _exec_with_nvidia_pip_libs_on_ld_path() -> None:
    """See ocr_batch_docling.py for why this re-exec is needed: onnxruntime's
    CUDAExecutionProvider dlopen()s libcurand/libcudnn from the nvidia-* pip
    packages, and LD_LIBRARY_PATH only takes effect for a fresh process."""
    if os.environ.get("_DOCLING_LD_PATH_SET"):
        return
    site_packages = Path(__file__).resolve().parents[1] / ".venv" / "lib"
    nvidia_root = next(site_packages.glob("python*/site-packages/nvidia"), None)
    if nvidia_root is None:
        return
    lib_dirs = [str(p) for p in nvidia_root.glob("*/lib") if p.is_dir()]
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ":".join(lib_dirs + ([existing] if existing else []))
    os.environ["_DOCLING_LD_PATH_SET"] = "1"
    os.execv(sys.executable, [sys.executable, *sys.argv])


def build_table_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        PdfPipelineOptions,
        TableFormerMode,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.do_ocr = False  # we already have our own PDF+Paddle text; only need table grids
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    pipeline_options.generate_page_images = False
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=8, device=AcceleratorDevice.CUDA
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )


def docling_tables_by_page(converter, pdf_path: Path) -> dict[int, list[list[str]]]:
    """page_no (1-based) -> list of tables, each a list of pipe-ready row strings."""
    from docling_core.types.doc import TableItem

    result = converter.convert(pdf_path)
    tables: dict[int, list[list[str]]] = {}
    for item, _level in result.document.iterate_items():
        if not isinstance(item, TableItem):
            continue
        page_nos = {prov.page_no for prov in getattr(item, "prov", [])}
        if not page_nos:
            continue
        rows = []
        for grid_row in item.data.grid:
            cells = [cell.text.strip().replace("\n", " ") for cell in grid_row]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.setdefault(next(iter(page_nos)), []).append(rows)
    return tables


def match_table_to_entries(table_rows: list[list[str]], entries: list[dict]) -> list[dict] | None:
    """Find the entries that correspond to a Docling table's cells by exact
    normalized-text match. Returns the matched entries (so callers can drop
    them from normal row grouping) or None if too few cells matched -- in
    which case the caller must leave this page's rows exactly as version9's
    y-tolerance grouping would produce them."""
    cell_texts = [norm(cell) for row in table_rows for cell in row if cell.strip()]
    if not cell_texts:
        return None
    matched: list[dict] = []
    remaining_cells = list(cell_texts)
    for entry in entries:
        entry_norm = norm(entry["text"])
        if entry_norm and entry_norm in remaining_cells:
            matched.append(entry)
            remaining_cells.remove(entry_norm)
    if len(matched) < max(2, int(0.7 * len(cell_texts))):
        return None
    return matched


def entries_to_text_with_tables(
    entries: list[dict],
    table_rows_by_match: list[tuple[list[dict], list[list[str]]]],
    line_numbers: bool,
    y_tolerance: float = 12.0,
) -> str:
    matched_ids = {id(e) for matched, _ in table_rows_by_match for e in matched}
    normal_entries = [e for e in entries if id(e) not in matched_ids]

    blocks: list[tuple[float, list[str]]] = []

    ordered = sorted(normal_entries, key=lambda item: (
        (item["bbox"][1] + item["bbox"][3]) / 2, item["bbox"][0],
    ))
    rows: list[list[dict]] = []
    centers: list[float] = []
    for item in ordered:
        center = (item["bbox"][1] + item["bbox"][3]) / 2
        if not rows or abs(center - centers[-1]) > y_tolerance:
            rows.append([item])
            centers.append(center)
        else:
            rows[-1].append(item)
            centers[-1] = sum((c["bbox"][1] + c["bbox"][3]) / 2 for c in rows[-1]) / len(rows[-1])
    for row, center in zip(rows, centers):
        row.sort(key=lambda item: item["bbox"][0])
        blocks.append((center, [" | ".join(cell["text"].strip() for cell in row)]))

    for matched, table_rows in table_rows_by_match:
        center = sum((e["bbox"][1] + e["bbox"][3]) / 2 for e in matched) / len(matched)
        blocks.append((center, [" | ".join(row) for row in table_rows]))

    blocks.sort(key=lambda block: block[0])
    lines = [line for _, block_lines in blocks for line in block_lines]
    if line_numbers:
        lines = [f"L{index:03d} {line}" for index, line in enumerate(lines, start=1)]
    return "\n".join(lines).rstrip() + "\n"


def main(
    output_version: str = "version12",
    force: bool = False,
    selected_doc_id: str | None = None,
    line_numbers: bool = True,
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
                paddle_started = time.perf_counter()
                pdata = paddle_data(ocr, image)
                paddle_seconds = time.perf_counter() - paddle_started
                texts = pdata.get("rec_texts", [])
                scores = pdata.get("rec_scores", [])
                boxes = pdata.get("rec_boxes", [])
                entries = pdf_lines(document[index], 200 / 72) if usable_pdf_text else []
                pdf_count = len(entries)
                pdf_boxes = [tuple(x["bbox"]) for x in entries]
                additions = 0
                pending = 0
                for raw_text, score, raw_box in zip(texts, scores, boxes):
                    text = str(raw_text).strip()
                    if not text:
                        continue
                    box = tuple(float(v) for v in raw_box)
                    duplicate = any(norm(text) and (norm(text) in norm(x["text"]) or norm(x["text"]) in norm(text)) for x in entries)
                    covered = max((coverage(b, box) for b in pdf_boxes), default=0.0)
                    if usable_pdf_text and (duplicate or covered >= 0.25):
                        continue
                    confirmed = VERIFIED_IMAGE_TEXT.get(doc_id, {}).get(text)
                    item = {
                        "text": confirmed or text,
                        "ocr_text": text,
                        "bbox": list(box),
                        "source": "image_manually_verified" if confirmed else ("paddle_full_page" if not usable_pdf_text else "paddle_image_only"),
                        "confidence": float(score),
                        "needs_review": bool(usable_pdf_text and not confirmed),
                    }
                    entries.append(item)
                    additions += 1
                    pending += int(item["needs_review"])
                entries.sort(key=lambda x: (round(x["bbox"][1] / 8), x["bbox"][0]))

                table_matches = []
                for table_rows in tables_by_page.get(page_no, []):
                    matched = match_table_to_entries(table_rows, entries)
                    if matched is not None:
                        table_matches.append((matched, table_rows))

                text_path = output / f"p{page_no:03d}.txt"
                text_path.write_text(
                    entries_to_text_with_tables(entries, table_matches, line_numbers=line_numbers),
                    encoding="utf-8",
                )
                detail = {
                    "page": page_no,
                    "mode": "pdf_plus_paddle" if usable_pdf_text else "paddle_full_page",
                    "pdf_lines": pdf_count,
                    "paddle_added": additions,
                    "needs_review": pending,
                    "docling_tables_matched": len(table_matches),
                    "docling_tables_detected": len(tables_by_page.get(page_no, [])),
                    "timing": {
                        "paddle_ocr_seconds": round(paddle_seconds, 6),
                        "page_total_seconds": round(time.perf_counter() - page_started, 6),
                    },
                }
                (output / f"p{page_no:03d}.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                page_row = {k: detail[k] for k in ("page", "mode", "pdf_lines", "paddle_added", "needs_review", "docling_tables_matched", "docling_tables_detected")}
                page_row.update(detail["timing"])
                page_rows.append(page_row)
                print(f"[{doc_id}] {page_no}/{len(images)}", flush=True)

        config = {
            "doc_id": doc_id,
            "version": output_version,
            "dpi": 200,
            "method": "version9 (PDF text + PaddleOCR, pipe_rows, line_numbers) + Docling TableFormer (GPU) grid substitution for matched tables",
            "line_numbers": line_numbers,
            "timing": {
                "document_total_seconds": round(time.perf_counter() - document_started, 6),
                "docling_table_detection_seconds": docling_seconds,
                "paddle_ocr_seconds": round(sum(x["paddle_ocr_seconds"] for x in page_rows), 6),
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
    parser = argparse.ArgumentParser(description="version12: version9 + Docling 표 구조 결합")
    parser.add_argument("--doc-id", help="한 문서만 실행")
    parser.add_argument("--force", action="store_true", help="기존 결과도 새로 실행")
    parser.add_argument("--output-version", default="version12", help="출력 폴더 이름")
    parser.add_argument("--no-line-numbers", action="store_true", help="L001 줄번호 끄기")
    args = parser.parse_args()
    raise SystemExit(
        main(
            output_version=args.output_version,
            force=args.force,
            selected_doc_id=args.doc_id,
            line_numbers=not args.no_line_numbers,
        )
    )
