"""Build page-preserving Markdown inputs for the evaluation documents."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL_DOCS = [
    "T21-002", "T21-005", "T21-006", "T21-010", "T21-014",
    "T21-023", "T21-025", "T21-039", "T21-043", "T21-045",
]


def build(doc_id: str, prefer_ocr: bool = True) -> Path:
    page_dir = ROOT / "data/pages" / doc_id
    pages = sorted(page_dir.glob("p[0-9][0-9][0-9].txt"))
    out = page_dir / "combined_v2.md"
    chunks = [f"# {doc_id}\n", "\n> 페이지 원문을 페이지 경계와 함께 연결한 모델 입력본입니다.\n"]
    for txt in pages:
        ocr = txt.with_name(f"{txt.stem}_ocr.txt")
        selected = ocr if prefer_ocr and ocr.exists() and ocr.stat().st_size else txt
        label = "OCR" if selected == ocr else "PDF 텍스트층"
        content = selected.read_text(encoding="utf-8", errors="replace").strip()
        chunks.extend([f"\n---\n\n## Page {int(txt.stem[1:])} ({label})\n", "\n", content or "[텍스트 없음 — 페이지 이미지 확인 필요]", "\n"])
    out.write_text("".join(chunks), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", nargs="+", default=EVAL_DOCS)
    parser.add_argument("--no-ocr", action="store_true")
    args = parser.parse_args()
    for doc_id in args.docs:
        path = build(doc_id, prefer_ocr=not args.no_ocr)
        print(f"[생성] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
