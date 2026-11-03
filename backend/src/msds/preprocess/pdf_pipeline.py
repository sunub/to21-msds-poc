"""Fresh PDF-only v17 extraction. Only installed model weights are reused.

No manifest, previous page text, OCR result, image or table cache is an input.
Heavy model libraries are imported lazily, and missing weights never download.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from . import layout, source_fidelity, table_fidelity, unit_fidelity

PIPELINE = "msds.preprocess.pdf_pipeline"
REVISION = "version17-fresh-pdf"
DEFAULT_DEVICE = "gpu:0"
_MODEL_LOAD_LOCK = RLock()


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return value


def _dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def _offline_model_loading():
    """Block import-time PaddleX probes and downloads; restore the HTTP client.

    Explicit local model paths prevent later downloader use. PaddleX 3.2 still
    probes remote hosts while importing, so model initialization is serialized
    and requests is temporarily denied in addition to HF offline settings.
    """
    import requests
    from unittest.mock import patch

    def offline(*args, **kwargs):
        raise requests.ConnectionError("PDF extraction uses installed local model weights only")
    with _MODEL_LOAD_LOCK:
        previous = {key: os.environ.get(key) for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        try:
            with patch.object(requests.sessions.Session, "request", offline):
                yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def build_ocr_engine(device=DEFAULT_DEVICE):
    """Load local Korean PP-OCRv5 detection and recognition weights."""
    models = Path(os.environ.get("TO21_OCR_MODELS_DIR", Path.home() / ".paddlex/official_models"))
    names = ("PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec")
    for name in names:
        folder = models / name
        if not (folder / "inference.yml").is_file() or not any(folder.glob("*.pdiparams")):
            raise RuntimeError(f"Local OCR model is missing: {folder}. Install weights before offline extraction.")
    try:
        with _offline_model_loading():
            from paddleocr import PaddleOCR
            return PaddleOCR(
                lang="korean", device=device,
                text_detection_model_name=names[0], text_detection_model_dir=str(models / names[0]),
                text_recognition_model_name=names[1], text_recognition_model_dir=str(models / names[1]),
                use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False,
                # The native CPU Conv/im2col path crashes with the installed
                # Paddle 3.2 build; the supported oneDNN backend is verified.
                **({"enable_mkldnn": True, "cpu_threads": 4} if device == "cpu" else {}),
            )
    except ImportError as error:
        raise RuntimeError("Fresh OCR requires installed PaddleOCR and PaddlePaddle packages") from error


def build_unit_recognizer(device=DEFAULT_DEVICE):
    models = Path(os.environ.get("TO21_OCR_MODELS_DIR", Path.home() / ".paddlex/official_models"))
    with _offline_model_loading():
        return unit_fidelity.build_unit_recognizer(device, models / "korean_PP-OCRv5_mobile_rec")


def _cached_weights(repo, required):
    """Read installed model-weight paths only, without asking HF to download."""
    cache = Path(os.environ.get("HF_HUB_CACHE", Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"))
    snapshots = cache / ("models--" + repo.replace("/", "--")) / "snapshots"
    for candidate in reversed(sorted(snapshots.glob("*"))):
        if (candidate / required).is_file():
            return candidate
    raise FileNotFoundError(f"Installed Docling weights not found for {repo}; provide DOCLING_ARTIFACTS_PATH")


class _LocalTableConverter:
    def __init__(self, converter, directory):
        self.converter, self.directory = converter, directory

    def convert(self, pdf_path):
        with _offline_model_loading():
            return self.converter.convert(pdf_path)

    def close(self):
        if self.directory is not None:
            self.directory.cleanup()


def build_table_converter(device=DEFAULT_DEVICE):
    """Build a fresh Docling converter using explicit installed artifacts."""
    directory = None
    provided = os.environ.get("DOCLING_ARTIFACTS_PATH")
    if provided:
        artifacts = Path(provided)
        if not artifacts.is_dir():
            raise FileNotFoundError(f"DOCLING_ARTIFACTS_PATH does not exist: {artifacts}")
    else:
        table = _cached_weights("docling-project/docling-models", "model_artifacts/tableformer/accurate/tm_config.json")
        detector = _cached_weights("docling-project/docling-layout-heron", "model.safetensors")
        directory = tempfile.TemporaryDirectory(prefix="msds-model-weights-")
        artifacts = Path(directory.name)
        (artifacts / "docling-project--docling-models").symlink_to(table, target_is_directory=True)
        (artifacts / "docling-project--docling-layout-heron").symlink_to(detector, target_is_directory=True)
    try:
        with _offline_model_loading():
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import AcceleratorOptions, PdfPipelineOptions, TableFormerMode
            from docling.document_converter import DocumentConverter, PdfFormatOption
            options = PdfPipelineOptions(artifacts_path=artifacts, enable_remote_services=False)
            options.do_ocr = False
            options.do_table_structure = True
            options.table_structure_options.mode = TableFormerMode.ACCURATE
            options.generate_page_images = False
            options.accelerator_options = AcceleratorOptions(num_threads=4, device=device.replace("gpu", "cuda"))
            converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        return _LocalTableConverter(converter, directory)
    except Exception:
        if directory is not None:
            directory.cleanup()
        raise


def _ocr_data(engine, image):
    with _offline_model_loading():
        results = engine.predict(str(image)) if hasattr(engine, "predict") else engine(image)
        if isinstance(results, dict):
            results = [results]
        records = []
        for result in results:
            value = getattr(result, "json", result)
            value = value() if callable(value) else value
            value = json.loads(value) if isinstance(value, str) else _jsonable(value)
            if not isinstance(value, dict):
                raise ValueError("OCR returned a result other than a JSON object")
            records.append(value.get("res", value))
    if len(records) != 1:
        raise ValueError(f"Expected one OCR result for one rendered page, received {len(records)}")
    return records[0]


def _ocr_items(data):
    texts = data.get("rec_texts", [])
    scores = data.get("rec_scores", [None] * len(texts))
    boxes = data.get("rec_boxes", data.get("rec_polys", []))
    if len(texts) != len(scores) or len(texts) != len(boxes):
        raise ValueError("OCR text, score and box counts differ; refusing to drop OCR rows")
    items = []
    for text, score, box in zip(texts, scores, boxes):
        if not str(text).strip():
            continue
        if len(box) != 4 or isinstance(box[0], (list, tuple)):
            box = [min(p[0] for p in box), min(p[1] for p in box), max(p[0] for p in box), max(p[1] for p in box)]
        bounds = [float(v) for v in box]
        if not all(math.isfinite(v) for v in bounds) or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise ValueError("OCR returned an invalid text box")
        items.append({"text": str(text).strip(), "box": bounds,
                      "confidence": float(score) if score is not None else None, "source": "paddle"})
    return items


def _native_state(page, items):
    visible = [c for item in items for c in item["text"] if not c.isspace()]
    hangul = [c for c in visible if "가" <= c <= "힣"]
    nn = sum((ord(c) - 0xAC00) % 28 == 4 for c in hangul)
    kk = sum((ord(c) - 0xAC00) % 28 == 2 for c in hangul)
    odd = sum(c == "\ufffd" or unicodedata.category(c) in {"Co", "Cc", "Cn"} for c in visible)
    symbol = sum(not c.isascii() and not "가" <= c <= "힣" for c in visible)
    area = page.rect.width * page.rect.height or 1
    coverage = max((abs((i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1])) / area
                    for i in page.get_image_info()), default=0)
    counts = {"chars": len(visible), "hangul": len(hangul), "nn": nn, "kk": kk,
              "invalid_chars": odd, "image_cover": round(coverage, 6)}
    if not visible:
        return ("이미지만" if coverage > 0.01 or page.get_drawings() else "빈쪽"), counts
    if odd / len(visible) > 0.05 or (nn >= 10 and kk / nn > 0.05):
        return "글꼴깨짐", counts
    if not hangul and symbol / len(visible) > 0.5:
        return "글꼴깨짐", counts
    if len(visible) < 20 and coverage >= 0.65:
        return "이미지만", counts
    return "정상", counts


def _table_grids(engine, pdf):
    converted = engine.convert(pdf) if hasattr(engine, "convert") else engine(pdf)
    if isinstance(converted, dict):
        return {int(page): grids for page, grids in converted.items()}
    result = {}
    for item, _ in converted.document.iterate_items():
        if getattr(item, "label", None) != "table":
            continue
        pages = {p.page_no for p in getattr(item, "prov", [])}
        if len(pages) != 1:
            continue
        rows = [[cell.text.strip().replace("\n", " ") for cell in row] for row in item.data.grid]
        rows = [row for row in rows if any(row)]
        if rows:
            result.setdefault(next(iter(pages)), []).append(rows)
    return result


def page_regions(items, tables, previous_schema, scale):
    previous = None if not previous_schema else {
        **previous_schema, "cols": [(a * scale, b * scale) for a, b in previous_schema["cols"]],
    }
    result = table_fidelity.resolve_page_data_tables(items, tables, previous)
    following = result["next_schema"]
    if following:
        following = {**following, "cols": [(a / scale, b / scale) for a, b in following["cols"]]}
    return result, following


def _validate_destination(output, pdf, source_hash, force):
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("Output must be an ordinary directory, not a linked path or file")
    if pdf.is_relative_to(output.resolve()):
        raise ValueError("Output directory must not contain the original PDF")
    if not output.exists() or not any(output.iterdir()):
        return
    if not force:
        raise ValueError(f"Output directory is not empty: {output}. Choose a new output directory.")
    marker = output / "config.json"
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("--force only replaces this pipeline's own completed outputs")
    try:
        config = json.loads(marker.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise ValueError("Cannot verify output ownership for --force") from error
    if config.get("pipeline") != PIPELINE or config.get("source_pdf_sha256") != source_hash:
        raise ValueError("--force cannot replace historical outputs or outputs of a different original PDF")
    expected = set(config.get("generated_files", []))
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if not expected or actual != expected or any(p.is_symlink() for p in output.rglob("*")):
        raise ValueError("--force refuses a directory with unowned, missing or linked files")


def extract_pdf(
    pdf_path: str | Path, output_dir: str | Path, *, doc_id: str | None = None,
    dpi: int = 200, ocr_device: str = DEFAULT_DEVICE, force: bool = False, use_docling: bool = True,
    ocr_engine: Any = None, table_engine: Any = None, unit_recognizer: Any = None,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Extract any original PDF, publishing outputs only after full success.

    OCR engines implement ``predict(image_path)`` or are callable, returning one
    Paddle-style JSON result. Table engines implement ``convert(pdf_path)`` or
    are callable and return ``{1: [grid, ...]}``. Injected engines support tests
    without importing model libraries. ``force`` only accepts this entrypoint's
    verified completed outputs for the same source; historical outputs are safe.
    """
    import pymupdf

    pdf = Path(pdf_path).expanduser().resolve()
    output = Path(output_dir).expanduser().absolute()
    if not pdf.is_file():
        raise FileNotFoundError(f"Original PDF does not exist: {pdf}")
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 72 <= dpi <= 600:
        raise ValueError("dpi must be an integer from 72 to 600")
    if not isinstance(ocr_device, str) or not ocr_device:
        raise ValueError("ocr_device must be cpu or a Paddle device such as gpu:0")
    source_hash = _sha(pdf)
    _validate_destination(output, pdf, source_hash, force)
    try:
        document = pymupdf.open(pdf)
    except (RuntimeError, ValueError) as error:
        raise ValueError(f"Cannot open original PDF: {pdf.name}") from error
    if not document.is_pdf or document.needs_pass or not len(document):
        document.close()
        raise ValueError("Input must be a nonempty, unencrypted PDF")
    identifier = str(doc_id) if doc_id is not None else pdf.stem
    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    warnings, pages, traces, repairs, symbol_repairs = [], [], [], [], []
    def notify(stage, **event):
        if on_progress is not None:
            on_progress({"stage": stage, "doc_id": identifier, "page_count": len(document),
                         "total_pages": len(document), **event})
    native = [layout.char_items(page) for page in document]
    states = [_native_state(page, items) for page, items in zip(document, native)]
    grids, own_converter = {}, None
    docling_attempted, docling_completed, docling_error = False, False, None
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / f".{output.name}.pdf-pipeline.lock"
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        document.close()
        raise ValueError("Another extraction is using this output directory") from error
    os.close(lock_fd)
    try:
        notify("start", completed_pages=0)
        if use_docling and (table_engine is not None or any(state == "정상" and len(items) > 8
                                                          for items, (state, _) in zip(native, states))):
            docling_attempted = True
            notify("tables", completed_pages=0)
            try:
                if table_engine is None:
                    table_engine = own_converter = build_table_converter(ocr_device)
                grids = _table_grids(table_engine, pdf)
                docling_completed = True
            except Exception as error:
                docling_error = f"{type(error).__name__}: {error}"
                warnings.append(f"Auxiliary table analysis unavailable; native geometry retained: {docling_error}")
        with tempfile.TemporaryDirectory(prefix=f".{output.name}-fresh-", dir=output.parent) as temporary:
            work = Path(temporary) / "document"
            work.mkdir()
            previous, section = None, None
            for index, page in enumerate(document):
                number, page_started = index + 1, time.perf_counter()
                image_name, text_name = f"p{number:03d}.png", f"p{number:03d}.txt"
                image = work / image_name
                pixmap = page.get_pixmap(dpi=dpi)
                pixmap.save(image)
                state, counts = states[index]
                raw, items, mode, scale = native[index], native[index], "pdf_xycut", 1.0
                ocr_seconds = unit_seconds = 0.0
                if state in ("이미지만", "글꼴깨짐"):
                    if ocr_engine is None:
                        ocr_engine = build_ocr_engine(ocr_device)
                    ocr_started = time.perf_counter()
                    data = _ocr_data(ocr_engine, image)
                    ocr_seconds = time.perf_counter() - ocr_started
                    _dump(work / "raw_ocr" / f"p{number:03d}.json", data)
                    raw = _ocr_items(data)
                    items = copy.deepcopy(raw)
                    if any(unit_fidelity._suspects(item, items) for item in items):
                        try:
                            if unit_recognizer is None:
                                unit_recognizer = build_unit_recognizer(ocr_device)
                            unit_started = time.perf_counter()
                            with _offline_model_loading():
                                items, audit = unit_fidelity.repair_unit_items(items, image, unit_recognizer)
                            unit_seconds = time.perf_counter() - unit_started
                            repairs.extend(dict(record, page=number) for record in audit)
                        except (RuntimeError, FileNotFoundError, ImportError) as error:
                            warnings.append(f"Page {number}: unit recheck unavailable: {error}")
                            repairs.append({"page": number, "applied": False, "needs_review": True, "error": str(error)})
                    scale, mode = pixmap.width / page.rect.width, "paddle_fresh_layout"
                elif state == "빈쪽":
                    mode = "blank"
                items, audit = source_fidelity.normalize_emergency_codes(items)
                symbol_repairs.extend(dict(record, page=number) for record in audit)
                tables = layout.page_tables(page, scale)
                resolved, following = page_regions(items, tables, previous, scale)
                if mode == "paddle_fresh_layout":
                    corrected, audit = source_fidelity.repair_ascii_punctuation(items, page, scale, resolved["regions"])
                    if audit:
                        items = corrected
                        symbol_repairs.extend(dict(record, page=number) for record in audit)
                        resolved, following = page_regions(items, tables, previous, scale)
                previous = following
                if previous:
                    previous["source_page"] = number
                body = resolved["body_items"]
                covered = {id(item) for table in resolved["tables"] for row in table for box in row
                           if box is not None for item in body if layout._inside(item, box)}
                matches, matched_ids = [], set()
                for grid in grids.get(number, []) if mode == "pdf_xycut" else []:
                    matched = match_table_to_items(grid, [i for i in body if id(i) not in matched_ids], covered)
                    if matched is not None:
                        matches.append((matched, grid))
                        matched_ids.update(id(i) for i in matched)
                (work / text_name).write_text(page_text(resolved["items"], resolved["tables"], matches), encoding="utf-8")
                headings = layout.section_headings(items, after=section[0] if section else 0)
                tables_meta = []
                for table_no, region in enumerate(resolved["regions"], 1):
                    table_name = f"tables/p{number:03d}_t{table_no}.md"
                    table_path = work / table_name
                    table_path.parent.mkdir(exist_ok=True)
                    table_path.write_text(layout.table_md(region["grid"]), encoding="utf-8")
                    above = [(h[1], h[2]) for h in headings if h[0] < region["box"][1]]
                    table_section = above[-1] if above else section
                    tables_meta.append({"file": table_name, "section": table_section[1] if table_section else None,
                        "box": [round(v / scale, 3) for v in region["box"]], "columns": len(region["grid"][0]),
                        "kind": region["kind"], "cell_kinds": region["cell_kinds"],
                        "schema_source_page": region.get("schema_source_page"),
                        "source_table_index": region["source_table_index"]})
                indices = {id(item): i for i, item in enumerate(items)}
                # Accepted auxiliary grids participate in TXT and the saved
                # tables too. Matching proves whole source pieces only; it
                # does not supply per-cell geometry, so do not invent it.
                for matched, grid in matches:
                    table_name = f"tables/p{number:03d}_t{len(tables_meta) + 1}.md"
                    table_path = work / table_name
                    table_path.parent.mkdir(exist_ok=True)
                    table_path.write_text(layout.table_md(grid), encoding="utf-8")
                    bounds = [min(i["box"][0] for i in matched), min(i["box"][1] for i in matched),
                              max(i["box"][2] for i in matched), max(i["box"][3] for i in matched)]
                    above = [(h[1], h[2]) for h in headings if h[0] < bounds[1]]
                    table_section = above[-1] if above else section
                    tables_meta.append({"file": table_name, "section": table_section[1] if table_section else None,
                        "box": [round(v / scale, 3) for v in bounds], "columns": len(grid[0]),
                        "kind": "docling_data_table", "source_table_index": None,
                        "source_item_indices": [indices[id(i)] for i in matched],
                        "cell_provenance": "not_available; whole-grid source-item correspondence only"})
                if headings:
                    section = headings[-1][1:]
                traces.append({"page": number, "mode": mode, "raw_items": raw, "final_items": items,
                    "pdf_tables": tables, "resolved_regions": resolved["regions"],
                    "docling_tables_matched": len(matches),
                    "docling_matches": [{"grid": grid, "source_item_indices": [indices[id(i)] for i in matched]}
                                        for matched, grid in matches]})
                info = {"page": number, "mode": mode, "state": state, **counts,
                    "text_file": text_name, "image_file": image_name, "width": pixmap.width, "height": pixmap.height,
                    "scale": scale, "text_source": "OCR" if mode == "paddle_fresh_layout" else "텍스트층" if mode == "pdf_xycut" else "없음",
                    "tables": tables_meta, "resolved_data_tables": len(tables_meta),
                    "continued_tables": sum(r["kind"] == "continued_data_table" for r in resolved["regions"]),
                    "docling_tables_matched": len(matches), "docling_tables_detected": len(grids.get(number, [])),
                    "paddle_ocr_seconds": round(ocr_seconds, 6), "unit_recheck_seconds": round(unit_seconds, 6),
                    "page_total_seconds": round(time.perf_counter() - page_started, 6)}
                pages.append(info)
                notify("page", page=number, completed_pages=number, mode=mode)
            if _sha(pdf) != source_hash:
                raise ValueError("The original PDF changed during extraction")
            result = {"pipeline": PIPELINE, "version": REVISION, "doc_id": identifier,
                "source_pdf": str(pdf), "source_file": pdf.name, "source_pdf_sha256": source_hash,
                "output_dir": str(output), "page_count": len(pages), "pages": pages,
                "dpi": dpi, "ocr_device": ocr_device, "fresh_pdf_render": True,
                "fresh_ocr": any(p["mode"] == "paddle_fresh_layout" for p in pages),
                "fresh_ocr_pages": sum(p["mode"] == "paddle_fresh_layout" for p in pages),
                "fresh_native_text_pages": sum(p["mode"] == "pdf_xycut" for p in pages),
                "cached_raw_ocr_pages": 0, "cached_unit_repairs_reused": False,
                "no_prior_document_artifacts_used": True, "table_grid_shared_with_model_input": True,
                "docling_requested": bool(use_docling), "docling_attempted": docling_attempted,
                "docling_completed": docling_completed, "docling_error": docling_error,
                "docling_tables_detected": sum(len(value) for value in grids.values()),
                "fresh_docling_analysis": docling_completed, "warnings": warnings,
                "started_utc": started_utc, "completed_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "code_sha256": {name: _sha(Path(__file__).with_name(name)) for name in
                                ("pdf_pipeline.py", "layout.py", "table_fidelity.py", "source_fidelity.py", "unit_fidelity.py")}}
            native_states = {state for state, _ in states} - {"빈쪽"}
            result["text_layer"] = "글꼴깨짐" if "글꼴깨짐" in native_states else "혼합" if len(native_states) > 1 else "없음" if native_states != {"정상"} else "정상"
            _dump(work / "meta.json", result)
            _dump(work / "summary.json", pages)
            _dump(work / "item_trace.json", traces)
            _dump(work / "unit_repairs.json", repairs)
            _dump(work / "symbol_repairs.json", symbol_repairs)
            result["generated_files"] = sorted([p.relative_to(work).as_posix() for p in work.rglob("*") if p.is_file()] + ["config.json"])
            _dump(work / "config.json", result)
            _validate_destination(output, pdf, source_hash, force)
            backup = Path(temporary) / "previous-output"
            if output.exists():
                output.rename(backup)
            try:
                work.rename(output)
            except Exception:
                if backup.exists():
                    backup.rename(output)
                raise
        notify("complete", completed_pages=len(pages))
        return result
    finally:
        if own_converter is not None and hasattr(own_converter, "close"):
            own_converter.close()
        document.close()
        lock.unlink(missing_ok=True)


def _norm(text: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', text).split())


def match_table_to_items(grid: list[list[str]], items: list[dict], covered: set[int]) -> list[dict] | None:
    """Accept only a genuinely >=70% matched, fully source-backed grid.

    Every cell must equal an entire source item or contiguous complete source
    items in the matched region. A numeric substring of another value cannot
    supply evidence. Rejected grids leave the original PDF items untouched.
    """
    cells = [_norm(cell) for row in grid for cell in row if cell.strip()]
    wanted, available = Counter(cells), Counter(_norm(i['text']) for i in items)
    # Without Docling provenance boxes, repeated text elsewhere on the page
    # cannot safely identify which occurrence belongs to this table.
    if any(available[cell] > count for cell, count in wanted.items()):
        return None
    remaining, matched = list(cells), []
    for item in items:
        text = _norm(item['text'])
        if text and text in remaining:
            matched.append(item)
            remaining.remove(text)
    if len(matched) < max(2, math.ceil(0.7 * len(cells))):
        return None
    if sum(id(item) in covered for item in matched) / len(matched) >= 0.5:
        return None
    if not remaining:
        return matched
    bounds = [min(i['box'][0] for i in matched), min(i['box'][1] for i in matched),
              max(i['box'][2] for i in matched), max(i['box'][3] for i in matched)]
    region = [i for i in items if layout._inside(i, bounds)]
    sequences = [[i for row in layout._rows(region) for i in row]]
    sequences.extend(layout._rows(region))
    maximum = max(map(len, remaining))
    supported = {}
    consumed = {id(i) for i in matched}
    for sequence in sequences:
        for start in range(len(sequence)):
            text = ''
            for end, item in enumerate(sequence[start:], start + 1):
                if id(item) in consumed:
                    break
                text += _norm(item['text'])
                if len(text) > maximum:
                    break
                supported.setdefault(text, []).append(sequence[start:end])
    if any(cell not in supported for cell in remaining):
        return None
    for cell, count in Counter(remaining).items():
        spans = {tuple(id(item) for item in span) for span in supported[cell]}
        if len(spans) > count:
            return None
    # The complete source pieces used by multipart cells must also be removed
    # from the body when their corroborated grid replaces them.
    for cell in remaining:
        support = next((span for span in supported[cell] if all(id(i) not in consumed for i in span)), None)
        if support is None:
            return None
        matched.extend(support)
        consumed.update(id(i) for i in support)
    if sum(id(item) in covered for item in matched) / len(matched) >= 0.5:
        return None
    return matched


def _atomic_cut(items: list[dict], height: float) -> list[list[dict]]:
    """XY-cut with whole Docling grids participating in the same page flow.

    A tall table's centre aligning with a body line is not a label/value pair.
    Never split or re-sort a grid after the column order has been established.
    """
    if len(items) == 1:
        return [items]
    ys = layout._gaps([layout._y(i) for i in items], 0)
    boundary = layout._subheading_cut(items, ys, height)
    if boundary is not None:
        top, bottom = layout._split(items, [boundary], lambda i: sum(layout._y(i)) / 2)
        return _atomic_cut(top, height) + _atomic_cut(bottom, height)
    xs = layout._gaps([(i['box'][0], i['box'][2]) for i in items], layout.GUTTER * height)
    x_cut = None
    for cut, width in sorted(xs, key=lambda gap: gap[1], reverse=True):
        columns = layout._split(items, [cut], lambda i: (i['box'][0] + i['box'][2]) / 2)
        ordinary = [[i for i in column if 'docling_grid' not in i] for column in columns]
        # A table elsewhere in the region cannot turn aligned labels and
        # values into separate columns. Try the next gap, which may instead
        # separate the complete form from its neighbouring table.
        if all(ordinary) and layout._aligned(ordinary):
            continue
        if any('docling_grid' in i for i in items) or not layout._aligned(columns):
            x_cut = columns, width
            break
    y_width = max((gap[1] for gap in ys), default=None)
    if x_cut and (y_width is None or x_cut[1] > y_width):
        return [row for column in x_cut[0] for row in _atomic_cut(column, height)]
    if ys:
        cut = max(ys, key=lambda gap: gap[1])[0]
        top, bottom = layout._split(items, [cut], lambda i: sum(layout._y(i)) / 2)
        return _atomic_cut(top, height) + _atomic_cut(bottom, height)
    return layout._rows(items)


def page_text(items, tables, matches, line_numbers=True):
    """Pipe-delimited cells; escape literal pipes inside source cell content."""
    def escape(text):
        return text.replace('|', r'\|')
    def row_text(row):
        return ' '.join(' | '.join(escape(p['text'].strip()) for p in item['parts'])
                        if item.get('parts') else escape(item['text'].rstrip()) for item in row)
    if not items:
        return ""
    matched_ids = {id(i) for matched, _ in matches for i in matched}
    body = [i for i in items if id(i) not in matched_ids]
    if not matches:
        rows = layout.reading_order(body, tables, preserve_empty_cells=True, repair_table_layout=True)
    else:
        height = statistics.median(i['box'][3] - i['box'][1] for i in items)
        valid = [table for table in tables if not layout._table_crosses_heading(body, table)]
        body = layout._table_rows(body, valid, preserve_empty_cells=True)
        blocks = [{'text': '\ufffc', 'docling_grid': grid, 'table_row': ['docling', n],
                   'box': [min(i['box'][0] for i in matched), min(i['box'][1] for i in matched),
                           max(i['box'][2] for i in matched), max(i['box'][3] for i in matched)]}
                  for n, (matched, grid) in enumerate(matches)]
        rows = layout.join_wrapped(_atomic_cut(body + blocks, height), height, repair_table_layout=True)
    lines = []
    for row in rows:
        pending = []
        for item in row:
            if 'docling_grid' in item or 'table_row' in item:
                if pending:
                    lines.append(row_text(pending)); pending = []
                if 'docling_grid' in item:
                    lines.extend(' | '.join(escape(cell) for cell in cells) for cells in item['docling_grid'])
                else:
                    lines.append(row_text([item]))
            else:
                pending.append(item)
        if pending:
            lines.append(row_text(pending))
    if line_numbers:
        lines = [f'L{n:03d} {line}' for n, line in enumerate(lines, 1)]
    return '\n'.join(lines).rstrip() + '\n'
