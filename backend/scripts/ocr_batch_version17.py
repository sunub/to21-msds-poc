"""Fresh v17 extraction from one original PDF; no manifest or previous run required.

Example: backend/.venv/bin/python backend/scripts/ocr_batch_version17.py
    --pdf /path/to/document.pdf --output-dir /path/to/new-output
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from msds.preprocess.pdf_pipeline import DEFAULT_DEVICE, extract_pdf, page_regions, page_text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path, help="Original PDF, including paths outside the repository")
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory for this document's artifacts")
    parser.add_argument("--doc-id", help="Optional identifier; defaults to the PDF filename stem")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--ocr-device", default=DEFAULT_DEVICE,
                        help="Model inference device (default: gpu:0); cpu requires an explicit choice")
    parser.add_argument("--no-docling", action="store_true", help="Use PDF/OCR geometry without auxiliary Docling tables")
    parser.add_argument("--force", action="store_true", help="Replace only this entrypoint's verified outputs for the same PDF")
    args = parser.parse_args(argv)
    def progress(event):
        if event["stage"] == "page":
            print(f"[{event['doc_id']}] {event['page']}/{event['page_count']} {event['mode']}", file=sys.stderr, flush=True)
    try:
        with redirect_stdout(sys.stderr):
            result = extract_pdf(args.pdf, args.output_dir, doc_id=args.doc_id, dpi=args.dpi,
                                 ocr_device=args.ocr_device, use_docling=not args.no_docling,
                                 force=args.force, on_progress=progress)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"Extraction failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
