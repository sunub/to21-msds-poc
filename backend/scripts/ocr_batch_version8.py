"""version8 OCR extraction: version2 method with table rows joined by '|'.

version2's main() defaults to pipe_rows=False, which is why version2/version7
were produced without table-row joining. This wrapper pins pipe_rows=True so
the run is reproducible without relying on an ad-hoc interactive call.
"""

from __future__ import annotations

import argparse

from ocr_batch_version2 import main as run_extractor


def main() -> int:
    parser = argparse.ArgumentParser(description="version8: pipe-row OCR 전체 실행")
    parser.add_argument("--doc-id", help="한 문서만 실행")
    parser.add_argument("--force", action="store_true", help="기존 결과도 새로 실행")
    args = parser.parse_args()
    return run_extractor(
        output_version="version8",
        pipe_rows=True,
        force=args.force,
        selected_doc_id=args.doc_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
