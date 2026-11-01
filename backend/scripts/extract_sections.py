#!/usr/bin/env python3
"""C-1 항목 경계 파일(data/sections/<doc_id>.json)을 만든다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from msds.preprocess.section_contract import extract_sections


def write_sections(doc_id: str, pages_root: Path, output_dir: Path) -> dict:
    result = extract_sections(doc_id, pages_root / doc_id)
    if not result["msds"]:
        raise FileNotFoundError(f"쪽 글자 없음: {(pages_root / doc_id).resolve()}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{doc_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="C-1 layout.section_headings 기반 16항 경계 생성")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--doc-id")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--pages-root", type=Path, default=ROOT / "data" / "pages" / "version14")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "sections")
    args = parser.parse_args()
    doc_ids = sorted(path.name for path in args.pages_root.iterdir() if path.is_dir()) if args.all else [args.doc_id]
    for doc_id in doc_ids:
        result = write_sections(doc_id, args.pages_root, args.output_dir)
        stats = result["stats"]
        print(f"[{doc_id}] MSDS {stats['msds']}건, 항목 {stats['found']}개, 완전 {stats['complete']}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
