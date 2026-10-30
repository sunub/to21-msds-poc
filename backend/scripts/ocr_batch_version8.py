"""version8 OCR extraction: version2 method with table rows joined by '|'
and line numbers written into the text (L001 ...).

version2's main() defaults to pipe_rows=False and line_numbers=False, which
is why version2/version7 were produced without table-row joining or line
numbers. This wrapper pins both to True so the run is reproducible without
relying on an ad-hoc interactive call.
"""

from __future__ import annotations

import argparse

from ocr_batch_version2 import main as run_extractor


def main() -> int:
    parser = argparse.ArgumentParser(description="version8: pipe-row OCR 전체 실행")
    parser.add_argument("--doc-id", help="한 문서만 실행")
    parser.add_argument("--force", action="store_true", help="기존 결과도 새로 실행")
    parser.add_argument("--output-version", default="version8", help="출력 폴더 이름 (예: version9)")
    args = parser.parse_args()
    return run_extractor(
        output_version=args.output_version,
        pipe_rows=True,
        line_numbers=True,
        force=args.force,
        selected_doc_id=args.doc_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
