"""Create OCR text files for scan, missing-text, or corrupted-text pages.

Usage (Python 3.11/3.12, GPU):
    python scripts/ocr_paddle.py --device gpu:0 --all
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from paddleocr import PaddleOCR  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def result_text(result) -> list[str]:
    data = getattr(result, "json", None)
    if callable(data):
        data = data()
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict):
        data = data.get("res", data)
        texts = data.get("rec_texts", [])
        return [str(text) for text in texts]
    return []


def ocr_document(ocr: PaddleOCR, doc_id: str, force: bool = False) -> None:
    page_dir = ROOT / "data/pages" / doc_id
    metadata_path = page_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    expected_bad = metadata.get("expected_text_layer") in {"없음", "글꼴깨짐"}
    for image in sorted(page_dir.glob("p*.png")):
        raw_txt = page_dir / f"{image.stem}.txt"
        ocr_txt = page_dir / f"{image.stem}_ocr.txt"
        if not force and not expected_bad and raw_txt.exists() and raw_txt.read_text(encoding="utf-8").strip():
            # A usable text layer is kept as-is; OCR is reserved for scan/corrupt pages.
            continue
        results = ocr.predict(str(image))
        lines = []
        for result in results:
            lines.extend(result_text(result))
        ocr_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[OCR 완료] {doc_id}/{image.name} -> {ocr_txt.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--docs", nargs="+")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--device", default="gpu:0", help="Paddle device, e.g. gpu:0 or cpu")
    parser.add_argument("--force", action="store_true", help="정상 텍스트층도 OCR")
    args = parser.parse_args()
    ocr = PaddleOCR(
        lang="korean",
        device=args.device,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    doc_ids = args.docs
    if args.all:
        doc_ids = [p.name for p in sorted((ROOT / "data/pages").iterdir()) if p.is_dir()]
    for doc_id in doc_ids:
        ocr_document(ocr, doc_id, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
