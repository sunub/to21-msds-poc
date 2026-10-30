"""Build data/pages/<output_version> using Docling (GPU) for table-structure OCR.

Docling's layout + TableFormer models run on GPU (CUDA) and detect table
structure (rows/cols/cells) directly from the page image/PDF, instead of the
y-coordinate row-grouping heuristic used by ocr_batch_version2's pipe_rows.
Each detected table is serialized as pipe-joined rows ("a | b | c"), and the
page's plain-text reading order is kept from Docling's markdown export for
everything outside tables.

Usage:
    python backend/scripts/ocr_batch_docling.py --output-version version11
    python backend/scripts/ocr_batch_docling.py --doc-id T21-025 --force
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


def _exec_with_nvidia_pip_libs_on_ld_path() -> None:
    """onnxruntime-gpu's CUDAExecutionProvider dlopen()s libcurand/libcudnn/etc.
    at session-creation time, which only exist under the nvidia-* pip packages
    (installed as torch's CUDA deps) rather than on the system loader path.
    The dynamic linker only consults LD_LIBRARY_PATH at process start, so an
    os.environ mutation after Python has already started has no effect -- we
    have to set it and re-exec this same process once."""
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


def normalized_name(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def find_pdf(filename: str) -> Path:
    wanted = normalized_name(filename)
    return next(
        p
        for p in (ROOT / "data" / "raw").iterdir()
        if p.suffix.lower() == ".pdf" and normalized_name(p.name) == wanted
    )


def table_to_pipe_rows(table) -> list[str]:
    """Serialize a Docling TableItem's grid as pipe-joined rows."""
    grid = table.data.grid
    rows = []
    for row in grid:
        cells = [cell.text.strip().replace("\n", " ") for cell in row]
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def page_text(doc, page_no: int, line_numbers: bool) -> str:
    """Reconstruct one page's text: tables as pipe rows, everything else as-is,
    in the document's native reading order."""
    from docling_core.types.doc import TableItem, TextItem

    lines: list[str] = []
    for item, _level in doc.iterate_items():
        page_nos = {prov.page_no for prov in getattr(item, "prov", [])}
        if page_no not in page_nos:
            continue
        if isinstance(item, TableItem):
            lines.extend(table_to_pipe_rows(item))
        elif isinstance(item, TextItem):
            text = item.text.strip()
            if text:
                lines.append(text)
    if line_numbers:
        lines = [f"L{index + 1:03d} {line}" for index, line in enumerate(lines)]
    return "\n".join(lines) + ("\n" if lines else "")


def main(
    output_version: str = "version11",
    line_numbers: bool = True,
    force: bool = False,
    selected_doc_id: str | None = None,
) -> int:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    pipeline_options.images_scale = 200 / 72  # match the 200 DPI renders used elsewhere
    pipeline_options.generate_page_images = False
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=8, device=AcceleratorDevice.CUDA
    )
    # RapidOCR only has korean models for the onnxruntime backend (not torch),
    # so route it onto CUDAExecutionProvider instead of the torch accelerator.
    pipeline_options.ocr_options = RapidOcrOptions(
        lang=["korean"],
        backend="onnxruntime",
        rapidocr_params={
            "EngineConfig.onnxruntime.use_cuda": True,
            "EngineConfig.onnxruntime.cuda_ep_cfg.device_id": 0,
        },
    )

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )

    with (ROOT / "data" / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        docs = list(csv.DictReader(stream))

    overall = []
    for row in docs:
        doc_id = row["doc_id"]
        if selected_doc_id and doc_id != selected_doc_id:
            continue
        output = PAGES / output_version / doc_id
        output.mkdir(parents=True, exist_ok=True)
        summary_path = output / "summary.json"
        if not force and summary_path.exists():
            print(f"[{doc_id}] completed; skipped", flush=True)
            continue

        pdf_path = find_pdf(row["source_file"])
        started = time.perf_counter()
        result = converter.convert(pdf_path)
        docling_doc = result.document
        page_count = len(docling_doc.pages)

        # Keep the same on-disk shape as every other version: pNNN.png next to
        # pNNN.txt, reusing the 200 DPI renders already produced for version1/2.
        source_image_dir = PAGES / doc_id
        if not any(source_image_dir.glob("p[0-9][0-9][0-9].png")):
            source_image_dir = PAGES / "version1" / doc_id
        for index in range(1, page_count + 1):
            source_image = source_image_dir / f"p{index:03d}.png"
            target_image = output / source_image.name
            if source_image.exists() and not target_image.exists():
                shutil.copy2(source_image, target_image)

        page_rows = []
        for page_no in range(1, page_count + 1):
            page_started = time.perf_counter()
            text = page_text(docling_doc, page_no, line_numbers)
            (output / f"p{page_no:03d}.txt").write_text(text, encoding="utf-8")
            page_rows.append({
                "page": page_no,
                "seconds": round(time.perf_counter() - page_started, 3),
            })
            print(f"[{doc_id}] {page_no}/{page_count}", flush=True)

        elapsed = round(time.perf_counter() - started, 3)
        summary_path.write_text(
            json.dumps(page_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output / "config.json").write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "version": output_version,
                    "method": "docling (layout + TableFormer, GPU/CUDA) table structure extraction",
                    "table_mode": "ACCURATE",
                    "line_numbers": line_numbers,
                    "pages": page_count,
                    "seconds": elapsed,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        overall.append({"doc_id": doc_id, "pages": page_count, "seconds": elapsed})

    (PAGES / output_version / "overall_summary.json").write_text(
        json.dumps(overall, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    _exec_with_nvidia_pip_libs_on_ld_path()
    parser = argparse.ArgumentParser(description="Docling(GPU, TableFormer) 기반 OCR/표 추출")
    parser.add_argument("--doc-id", help="한 문서만 실행")
    parser.add_argument("--force", action="store_true", help="기존 결과도 새로 실행")
    parser.add_argument("--output-version", default="version11", help="출력 폴더 이름")
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
