"""Source-only PDF extraction contracts; fixtures and outputs stay in tmp_path."""
from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
from pathlib import Path

import pymupdf
import pytest

from msds.preprocess import pdf_pipeline


def _pdf(path: Path, texts: tuple[str, ...] = ("Fresh product CAS 71-43-2",)) -> Path:
    with pymupdf.open() as document:
        for text in texts:
            page = document.new_page(width=420, height=540)
            if text:
                page.insert_text((32, 60), text, fontsize=12)
        document.save(path)
    return path


def _scanned_pdf(path: Path) -> Path:
    """Rasterize a locally generated page, leaving no native text in the PDF."""
    with pymupdf.open() as original:
        page = original.new_page(width=420, height=540)
        page.insert_text((32, 60), "Scanned product CAS 71-43-2", fontsize=12)
        png = page.get_pixmap(dpi=120).tobytes("png")
    with pymupdf.open() as document:
        page = document.new_page(width=420, height=540)
        page.insert_image(page.rect, stream=png)
        document.save(path)
    return path


class RecordingOCR:
    def __init__(self):
        self.images: list[Path] = []
        self.image_hashes: list[str] = []

    def predict(self, image: str):
        source = Path(image)
        assert source.is_file()
        content = source.read_bytes()
        assert content.startswith(b"\x89PNG\r\n\x1a\n")
        self.images.append(source)
        self.image_hashes.append(hashlib.sha256(content).hexdigest())
        return [{
            "rec_texts": ["Scanned product", "CAS 71-43-2"],
            "rec_scores": [0.99, 0.98],
            "rec_boxes": [[32, 40, 280, 65], [32, 85, 250, 110]],
        }]


@pytest.fixture(autouse=True)
def no_models_or_historical_inputs(monkeypatch):
    """A test must fail if extraction consults repository artifacts or models."""
    repository = Path(__file__).resolve().parents[2]
    historical = (repository / "data", repository / "runs")
    original_open = builtins.open
    original_path_open = Path.open
    original_mkdir = Path.mkdir
    original_unlink = Path.unlink

    def check(path, mode):
        if isinstance(path, (str, bytes, Path)):
            resolved = Path(path.decode() if isinstance(path, bytes) else path).resolve()
            assert not any(resolved.is_relative_to(root) for root in historical), (
                f"Source-only extraction accessed repository artifacts ({mode}): {resolved}"
            )

    def guarded_open(file, mode="r", *args, **kwargs):
        check(file, mode)
        return original_open(file, mode, *args, **kwargs)

    def guarded_path_open(path, mode="r", *args, **kwargs):
        check(path, mode)
        return original_path_open(path, mode, *args, **kwargs)

    def guarded_mkdir(path, *args, **kwargs):
        check(path, "mkdir")
        return original_mkdir(path, *args, **kwargs)

    def guarded_unlink(path, *args, **kwargs):
        check(path, "unlink")
        return original_unlink(path, *args, **kwargs)

    def forbidden_builder(*args, **kwargs):
        pytest.fail("An isolated pipeline test attempted to initialize a model")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    monkeypatch.setattr(Path, "unlink", guarded_unlink)
    monkeypatch.setattr(pdf_pipeline, "build_ocr_engine", forbidden_builder)
    monkeypatch.setattr(pdf_pipeline, "build_table_converter", forbidden_builder)
    monkeypatch.setattr(pdf_pipeline, "build_unit_recognizer", forbidden_builder)


def test_native_pdf_needs_only_source_and_writes_complete_page_pairs(tmp_path):
    source = _pdf(tmp_path / "new-upload.pdf", ("Fresh product CAS 71-43-2", "Transport UN 1114"))
    output = tmp_path / "fresh-output"
    before = source.read_bytes()

    result = pdf_pipeline.extract_pdf(source, output, doc_id="NEW-UPLOAD", use_docling=False)

    assert result["doc_id"] == "NEW-UPLOAD"
    assert result["page_count"] == 2
    assert len(result["pages"]) == 2
    assert result["fresh_ocr_pages"] == 0
    assert result["cached_raw_ocr_pages"] == 0
    assert result["source_pdf_sha256"] == hashlib.sha256(before).hexdigest()
    assert [page["mode"] for page in result["pages"]] == ["pdf_xycut", "pdf_xycut"]
    assert "71-43-2" in (output / "p001.txt").read_text()
    assert "1114" in (output / "p002.txt").read_text()
    for number in (1, 2):
        assert (output / f"p{number:03d}.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    metadata = json.loads((output / "meta.json").read_text())
    assert metadata["page_count"] == 2
    assert len(metadata["pages"]) == 2
    assert source.read_bytes() == before


def test_scanned_pdf_uses_fresh_injected_ocr_and_retains_raw_result(tmp_path):
    source = _scanned_pdf(tmp_path / "scan.pdf")
    output = tmp_path / "scan-output"
    ocr = RecordingOCR()
    with pymupdf.open(source) as document:
        assert not document[0].get_text().strip()

    result = pdf_pipeline.extract_pdf(source, output, ocr_engine=ocr, use_docling=False)

    assert len(ocr.images) == 1
    assert ocr.images[0].is_relative_to(tmp_path)
    assert ocr.images[0].name == "p001.png"
    assert result["fresh_ocr_pages"] == 1
    assert result["cached_raw_ocr_pages"] == 0
    assert result["pages"][0]["mode"] == "paddle_fresh_layout"
    assert "Scanned product" in (output / "p001.txt").read_text()
    assert "71-43-2" in (output / "p001.txt").read_text()
    raw = json.loads((output / "raw_ocr/p001.json").read_text())
    assert "71-43-2" in json.dumps(raw)


def test_missing_fresh_ocr_is_an_error_instead_of_an_empty_success(tmp_path, monkeypatch):
    source = _scanned_pdf(tmp_path / "scan.pdf")

    def unavailable(device):
        raise RuntimeError("Local OCR weights are unavailable")

    monkeypatch.setattr(pdf_pipeline, "build_ocr_engine", unavailable)
    with pytest.raises(RuntimeError, match="OCR|weights"):
        pdf_pipeline.extract_pdf(source, tmp_path / "output", use_docling=False)


def test_blank_page_does_not_initialize_ocr(tmp_path):
    source = _pdf(tmp_path / "blank.pdf", ("",))
    output = tmp_path / "blank-output"

    result = pdf_pipeline.extract_pdf(source, output, use_docling=False)

    assert result["page_count"] == 1
    assert result["fresh_ocr_pages"] == 0
    assert result["pages"][0]["mode"] == "blank"
    assert not (output / "p001.txt").read_text().strip()
    assert (output / "p001.png").is_file()


def test_progress_reports_completed_pages_and_total(tmp_path):
    source = _pdf(tmp_path / "two-pages.pdf", ("First fresh page", "Second fresh page"))
    events = []

    pdf_pipeline.extract_pdf(source, tmp_path / "output", use_docling=False, on_progress=events.append)

    pages = [event for event in events if event["stage"] == "page"]
    assert [event["page"] for event in pages] == [1, 2]
    assert [event["completed_pages"] for event in pages] == [1, 2]
    assert all(event["page_count"] == event["total_pages"] == 2 for event in pages)


def test_same_native_pdf_has_identical_text_and_images_in_separate_runs(tmp_path):
    source = _pdf(tmp_path / "repeat.pdf", ("Product 71-43-2 concentration 10-20 %", "UN 1114"))
    first, second = tmp_path / "first", tmp_path / "second"

    pdf_pipeline.extract_pdf(source, first, use_docling=False)
    pdf_pipeline.extract_pdf(source, second, use_docling=False)

    for filename in ("p001.txt", "p002.txt", "p001.png", "p002.png"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_same_scanned_pdf_repeats_fresh_ocr_instead_of_loading_first_output(tmp_path):
    source = _scanned_pdf(tmp_path / "scan.pdf")
    first, second = tmp_path / "first", tmp_path / "second"
    ocr = RecordingOCR()

    pdf_pipeline.extract_pdf(source, first, ocr_engine=ocr, use_docling=False)
    pdf_pipeline.extract_pdf(source, second, ocr_engine=ocr, use_docling=False)

    assert len(ocr.images) == 2
    assert ocr.images[0] != ocr.images[1]
    assert all(image.is_relative_to(tmp_path) for image in ocr.images)
    assert ocr.image_hashes[0] == ocr.image_hashes[1]
    assert (first / "p001.txt").read_bytes() == (second / "p001.txt").read_bytes()


def test_injected_docling_converter_uses_fresh_pdf_and_source_backed_grid(tmp_path):
    source = tmp_path / "toxicity.pdf"
    grid = [["Endpoint", "Result"], ["LD50", ">2000"]]
    with pymupdf.open() as document:
        page = document.new_page(width=420, height=540)
        for row_number, row in enumerate(grid):
            for column, text in enumerate(row):
                page.insert_text((32 + column * 180, 60 + row_number * 40), text, fontsize=12)
        document.save(source)

    class Tables:
        def __init__(self):
            self.sources = []

        def convert(self, pdf_path):
            self.sources.append(Path(pdf_path))
            with pymupdf.open(pdf_path) as document:
                assert ">2000" in document[0].get_text()
            return {1: [grid]}

    tables = Tables()
    output = tmp_path / "table-output"
    result = pdf_pipeline.extract_pdf(source, output, table_engine=tables)

    assert tables.sources == [source]
    assert result["fresh_docling_analysis"] is True
    assert result["docling_requested"] is True
    assert result["docling_completed"] is True
    assert result["docling_error"] is None
    assert result["pages"][0]["docling_tables_detected"] == 1
    assert result["pages"][0]["docling_tables_matched"] == 1
    text = (output / "p001.txt").read_text()
    assert "Endpoint | Result" in text
    assert "LD50 | >2000" in text
    metadata = json.loads((output / "meta.json").read_text())
    assert metadata["pages"][0]["docling_tables_matched"] == 1
    saved_tables = metadata["pages"][0]["tables"]
    assert len(saved_tables) == 1
    assert saved_tables[0]["kind"] == "docling_data_table"
    markdown = (output / saved_tables[0]["file"]).read_text()
    assert "Endpoint" in markdown and "Result" in markdown
    assert "LD50" in markdown and ">2000" in markdown


@pytest.mark.parametrize("selected,expected", [(None, "gpu:0"), ("gpu:1", "gpu:1"), ("cpu", "cpu")])
def test_selected_device_reaches_ocr_units_and_table_builders(tmp_path, monkeypatch, selected, expected):
    source = tmp_path / "mixed.pdf"
    scan = _scanned_pdf(tmp_path / "scan.pdf")
    with pymupdf.open() as document:
        page = document.new_page(width=420, height=540)
        for row in range(10):
            page.insert_text((32, 40 + row * 30), f"Native information row {row}", fontsize=12)
        with pymupdf.open(scan) as scanned:
            document.insert_pdf(scanned)
        document.save(source)

    devices = []
    recognizer = object()

    class TemperatureOCR:
        def predict(self, image):
            assert Path(image).is_file()
            return [{"rec_texts": ["Boiling temperature -196 c"], "rec_scores": [0.98],
                     "rec_boxes": [[32, 40, 480, 65]]}]

    class Tables:
        def convert(self, pdf_path):
            assert Path(pdf_path) == source
            return {}

    def ocr_builder(device):
        devices.append(("ocr", device))
        return TemperatureOCR()

    def unit_builder(device):
        devices.append(("units", device))
        return recognizer

    def table_builder(device):
        devices.append(("tables", device))
        return Tables()

    def unit_recheck(items, image, engine):
        assert engine is recognizer
        assert Path(image).is_file()
        assert any("-196 c" in item["text"] for item in items)
        return items, [{"applied": False, "needs_review": True}]

    monkeypatch.setattr(pdf_pipeline, "build_ocr_engine", ocr_builder)
    monkeypatch.setattr(pdf_pipeline, "build_unit_recognizer", unit_builder)
    monkeypatch.setattr(pdf_pipeline, "build_table_converter", table_builder)
    monkeypatch.setattr(pdf_pipeline.unit_fidelity, "repair_unit_items", unit_recheck)
    options = {} if selected is None else {"ocr_device": selected}

    result = pdf_pipeline.extract_pdf(source, tmp_path / "output", **options)

    assert sorted(devices) == sorted([("ocr", expected), ("units", expected), ("tables", expected)])
    assert result["ocr_device"] == expected
    assert result["fresh_ocr_pages"] == 1
    assert result["docling_completed"] is True


def test_gpu_initialization_error_does_not_retry_on_cpu(tmp_path, monkeypatch):
    source = _scanned_pdf(tmp_path / "scan.pdf")
    devices = []

    def unavailable(device):
        devices.append(device)
        raise RuntimeError("CUDA unavailable for requested GPU")

    monkeypatch.setattr(pdf_pipeline, "build_ocr_engine", unavailable)

    with pytest.raises(RuntimeError, match="CUDA unavailable"):
        pdf_pipeline.extract_pdf(source, tmp_path / "output", use_docling=False)

    assert devices == ["gpu:0"]
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("arguments,expected", [([], "gpu:0"), (["--ocr-device", "cpu"], "cpu")])
def test_cli_defaults_to_gpu_and_allows_explicit_cpu(tmp_path, monkeypatch, capsys, arguments, expected):
    script = Path(__file__).resolve().parents[1] / "scripts/ocr_batch_version17.py"
    spec = importlib.util.spec_from_file_location("source_only_v17_cli_test", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    calls = []

    def extract(pdf, output, **options):
        calls.append(options["ocr_device"])
        return {"ocr_device": options["ocr_device"]}

    monkeypatch.setattr(cli, "extract_pdf", extract)
    status = cli.main(["--pdf", str(tmp_path / "input.pdf"), "--output-dir", str(tmp_path / "output"),
                       *arguments])

    assert status == 0
    assert calls == [expected]
    assert json.loads(capsys.readouterr().out)["ocr_device"] == expected


@pytest.mark.parametrize("content", [b"", b"This is not a PDF"])
def test_empty_or_corrupt_source_fails_without_creating_output(tmp_path, content):
    source = tmp_path / "broken.pdf"
    source.write_bytes(content)
    output = tmp_path / "output"

    with pytest.raises(ValueError):
        pdf_pipeline.extract_pdf(source, output, use_docling=False)

    assert source.read_bytes() == content
    assert not output.exists()


def test_encrypted_source_fails_without_creating_output(tmp_path):
    source = tmp_path / "locked.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((32, 60), "Password protected")
        document.save(source, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                      user_pw="test-password", owner_pw="owner-password")
    output = tmp_path / "output"
    before = source.read_bytes()

    with pytest.raises(ValueError):
        pdf_pipeline.extract_pdf(source, output, use_docling=False)

    assert source.read_bytes() == before
    assert not output.exists()


def test_missing_source_fails_without_creating_output(tmp_path):
    output = tmp_path / "output"

    with pytest.raises(FileNotFoundError):
        pdf_pipeline.extract_pdf(tmp_path / "missing.pdf", output, use_docling=False)

    assert not output.exists()


def test_existing_output_is_rejected_without_altering_any_files(tmp_path):
    source = _pdf(tmp_path / "fresh.pdf")
    output = tmp_path / "existing"
    output.mkdir()
    (output / "p001.txt").write_text("Earlier extraction must remain intact")
    (output / "notes.json").write_text('{"reviewed": true}')
    before = {path.name: path.read_bytes() for path in output.iterdir()}

    with pytest.raises(ValueError):
        pdf_pipeline.extract_pdf(source, output, use_docling=False)

    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_force_replaces_only_owned_output_for_the_same_original(tmp_path):
    source = _pdf(tmp_path / "fresh.pdf")
    output = tmp_path / "output"
    pdf_pipeline.extract_pdf(source, output, use_docling=False)
    first_text = (output / "p001.txt").read_bytes()

    result = pdf_pipeline.extract_pdf(source, output, force=True, use_docling=False)

    assert result["page_count"] == 1
    assert (output / "p001.txt").read_bytes() == first_text
    config = json.loads((output / "config.json").read_text())
    assert set(config["generated_files"]) == {
        path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("existing", ["unowned", "different_pdf", "added_review"])
def test_force_refuses_unowned_or_modified_output_without_changing_it(tmp_path, existing):
    source = _pdf(tmp_path / "fresh.pdf")
    output = tmp_path / "output"
    if existing == "unowned":
        output.mkdir()
        (output / "p001.txt").write_text("An earlier pipeline owns this file")
    else:
        pdf_pipeline.extract_pdf(source, output, use_docling=False)
        if existing == "different_pdf":
            source = _pdf(tmp_path / "another.pdf", ("A different original CAS 7732-18-5",))
        else:
            (output / "human-review.json").write_text('{"approved": true}')
    before = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}

    with pytest.raises(ValueError):
        pdf_pipeline.extract_pdf(source, output, force=True, use_docling=False)

    after = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    assert after == before
