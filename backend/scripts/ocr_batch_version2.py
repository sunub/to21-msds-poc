"""Build data/pages/<doc_id>/version2 for every manifest document at 200 DPI."""

from __future__ import annotations

import csv
import json
import shutil
import time
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "data" / "pages"
VERIFIED_IMAGE_TEXT = {
    "T21-025": {
        "고려아연주식회사": "고려아연주식회사",
        "Korea Zinc Go.,Ltd.": "Korea Zinc Co.,Ltd.",
    }
}


def normalized_name(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def find_pdf(filename: str) -> Path:
    wanted = normalized_name(filename)
    return next(p for p in (ROOT / "data" / "raw").iterdir() if p.suffix.lower() == ".pdf" and normalized_name(p.name) == wanted)


def norm(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value or "").split())


def coverage(container: tuple[float, ...], candidate: tuple[float, ...]) -> float:
    x1, y1 = max(container[0], candidate[0]), max(container[1], candidate[1])
    x2, y2 = min(container[2], candidate[2]), min(container[3], candidate[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area = max(1.0, (candidate[2] - candidate[0]) * (candidate[3] - candidate[1]))
    return intersection / area


def pdf_lines(page: pymupdf.Page, scale: float) -> list[dict]:
    output = []
    for block in page.get_text("dict", sort=True).get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text:
                output.append({
                    "text": text,
                    "bbox": [float(v) * scale for v in line["bbox"]],
                    "source": "pdf_text",
                    "confidence": 1.0,
                    "needs_review": False,
                })
    return output


def paddle_data(ocr, image: Path) -> dict:
    results = []
    for result in ocr.predict(str(image)):
        value = getattr(result, "json", None)
        value = value() if callable(value) else value
        value = json.loads(value) if isinstance(value, str) else value
        results.append(value)
    if not results:
        return {}
    return results[0].get("res", results[0])


def entries_to_text(
    entries: list[dict], pipe_rows: bool = False, y_tolerance: float = 12.0,
    line_numbers: bool = False,
) -> str:
    """Serialize extraction entries; version4 joins same-row cells immediately."""
    if not pipe_rows:
        return "\n".join(item["text"] for item in entries).rstrip() + "\n"
    ordered = sorted(entries, key=lambda item: (
        (item["bbox"][1] + item["bbox"][3]) / 2,
        item["bbox"][0],
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
            centers[-1] = sum((cell["bbox"][1] + cell["bbox"][3]) / 2 for cell in rows[-1]) / len(rows[-1])
    lines = []
    for index, row in enumerate(rows, start=1):
        row.sort(key=lambda item: item["bbox"][0])
        text = " | ".join(item["text"].strip() for item in row)
        lines.append(f"L{index:03d} {text}" if line_numbers else text)
    return "\n".join(lines).rstrip() + "\n"


def main(
    output_version: str = "version2",
    pipe_rows: bool = False,
    force: bool = False,
    selected_doc_id: str | None = None,
    line_numbers: bool = False,
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
    overall = []
    for row in docs:
        doc_id = row["doc_id"]
        if selected_doc_id and doc_id != selected_doc_id:
            continue
        page_dir = PAGES / doc_id
        images = sorted(page_dir.glob("p[0-9][0-9][0-9].png"))
        if not images:
            # Existing 200-DPI renders are valid image inputs; OCR/text is still
            # freshly extracted below and is never copied from version2.
            page_dir = PAGES / "version1" / doc_id
            images = sorted(page_dir.glob("p[0-9][0-9][0-9].png"))
        if not images:
            continue
        output = PAGES / output_version / doc_id
        output.mkdir(parents=True, exist_ok=True)
        document_started = time.perf_counter()
        for image in images:
            target_image = output / image.name
            if not target_image.exists():
                shutil.copy2(image, target_image)
        old_summary = output / "summary.json"
        if not force and old_summary.exists() and len(list(output.glob("p[0-9][0-9][0-9].txt"))) == len(images):
            prior = json.loads(old_summary.read_text(encoding="utf-8"))
            overall.append({"doc_id": doc_id, "pages": len(prior), "mode": prior[0]["mode"], "paddle_added": sum(x["paddle_added"] for x in prior), "needs_review": sum(x["needs_review"] for x in prior)})
            print(f"[{doc_id}] completed; skipped", flush=True)
            continue
        usable_pdf_text = row["text_layer"] == "정상"
        pdf = find_pdf(row["source_file"])
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
                text_path = output / f"p{page_no:03d}.txt"
                text_path.write_text(entries_to_text(entries, pipe_rows=pipe_rows, line_numbers=line_numbers), encoding="utf-8")
                detail = {
                    "page": page_no,
                    "mode": "pdf_plus_paddle" if usable_pdf_text else "paddle_full_page",
                    "pdf_lines": pdf_count,
                    "paddle_added": additions,
                    "needs_review": pending,
                    "timing": {
                        "paddle_ocr_seconds": round(paddle_seconds, 6),
                        "page_total_seconds": round(time.perf_counter() - page_started, 6),
                    },
                    "entries": entries,
                }
                (output / f"p{page_no:03d}.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                page_row = {k: detail[k] for k in ("page", "mode", "pdf_lines", "paddle_added", "needs_review")}
                page_row.update(detail["timing"])
                page_rows.append(page_row)
                print(f"[{doc_id}] {page_no}/{len(images)}", flush=True)
        config = {
            "doc_id": doc_id,
            "version": output_version,
            "dpi": 200,
            "device": "gpu",
            "models": ["PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec"],
            "text_layer": row["text_layer"],
            "method": "PDF coordinate-sorted text + non-overlapping PaddleOCR" if usable_pdf_text else "PaddleOCR full page",
            "text_format": "coordinate rows; cells joined with ' | '" if pipe_rows else "one extracted entry per line",
            "line_numbers": line_numbers,
            "status": "completed_requires_review" if sum(x["needs_review"] for x in page_rows) else "completed",
            "timing": {
                "document_total_seconds": round(time.perf_counter() - document_started, 6),
                "paddle_ocr_seconds": round(sum(x["paddle_ocr_seconds"] for x in page_rows), 6),
            },
        }
        (output / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "summary.json").write_text(json.dumps(page_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = [f"# {doc_id} version2 OCR 결과\n\n", f"- 방식: {config['method']}\n- 입력: 200 DPI\n- 페이지: {len(page_rows)}\n- Paddle 추가 줄: {sum(x['paddle_added'] for x in page_rows)}\n- 검토 후보: {sum(x['needs_review'] for x in page_rows)}\n\n", "| 페이지 | 모드 | PDF 줄 | Paddle 추가 | 검토 후보 |\n|---:|---|---:|---:|---:|\n"]
        report.extend(f"| {x['page']} | {x['mode']} | {x['pdf_lines']} | {x['paddle_added']} | {x['needs_review']} |\n" for x in page_rows)
        (output / "report.md").write_text("".join(report), encoding="utf-8")
        overall.append({"doc_id": doc_id, "pages": len(page_rows), "mode": page_rows[0]["mode"], "paddle_added": sum(x["paddle_added"] for x in page_rows), "needs_review": sum(x["needs_review"] for x in page_rows)})
    destination = PAGES / output_version / "summary.json"
    destination.write_text(json.dumps(overall, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
