#!/usr/bin/env python3
"""최신 쪽 글자에서 C-5 번호판 파일(data/codes/<doc_id>.json)을 만든다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from msds.checks.regex_codes import scan_codes


def read_pages(doc_dir: Path) -> dict[int, str]:
    return {int(path.stem[1:]): path.read_text(encoding="utf-8")
            for path in sorted(doc_dir.glob("p[0-9][0-9][0-9].txt"))}


def write_codes(doc_id: str, pages_root: Path, output_dir: Path) -> dict:
    source_dir = (pages_root / doc_id).resolve()
    pages = read_pages(source_dir)
    if not pages:
        raise FileNotFoundError(f"쪽 글자 없음: {source_dir}")
    details = scan_codes(pages)
    try:
        source = str(source_dir.relative_to(ROOT))
    except ValueError:
        source = str(source_dir)
    result = {
        "doc_id": doc_id,
        "source": source,
        "cas": [item["value"] for item in details["cas"]],
        "h": [item["value"] for item in details["h"]],
        "p": [item["value"] for item in details["p"]],
        "un": [item["value"] for item in details["un"]],
        "details": details,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{doc_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="C-5 H/P/CAS/UN 번호판 추출")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--doc-id")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--pages-root", type=Path, default=ROOT / "data" / "pages" / "version14")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "codes")
    args = parser.parse_args()
    doc_ids = sorted(path.name for path in args.pages_root.iterdir() if path.is_dir()) if args.all else [args.doc_id]
    for doc_id in doc_ids:
        result = write_codes(doc_id, args.pages_root, args.output_dir)
        print(f"[{doc_id}] CAS {len(result['cas'])}, H {len(result['h'])}, P {len(result['p'])}, UN {len(result['un'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
