"""전처리 산출물은 지정한 실행 폴더에만 쓰고 읽는다."""
import json
from pathlib import Path

import pymupdf

from msds.common import paths
from msds.preprocess import render


def pdf(path: Path, text: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


def test_same_document_id_isolated_between_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'PAGES', tmp_path / 'canonical')
    first, second = tmp_path / 'attempt-1', tmp_path / 'attempt-2'
    one = pdf(tmp_path / 'one.pdf', 'First distinct product name and hazard description')
    two = pdf(tmp_path / 'two.pdf', 'Second distinct product name and different description')
    doc_id = 'U-20261103-001'

    render.preprocess(one, doc_id, dpi=50, pages_root=first)
    render.preprocess(two, doc_id, dpi=50, pages_root=second)
    page_one = render.load_pages(doc_id, pages_root=first)['pages'][0]
    page_two = render.load_pages(doc_id, pages_root=second)['pages'][0]
    assert 'First distinct' in page_one['text']
    assert 'Second distinct' in page_two['text']
    assert page_one['image'] == first / doc_id / 'p001.png'
    assert page_two['image'] == second / doc_id / 'p001.png'
    assert not (paths.PAGES / doc_id).exists()

    # 강제 재실행과 구 표 삭제가 다른 시도나 기본 폴더에 영향을 주지 않는다.
    for root in (first, second, paths.PAGES):
        (root / doc_id / 'tables').mkdir(parents=True, exist_ok=True)
        (root / doc_id / 'tables' / 'marker.md').write_text(root.name)
    render.preprocess(one, doc_id, dpi=50, force=True, pages_root=first)
    assert not (first / doc_id / 'tables' / 'marker.md').exists()
    assert (second / doc_id / 'tables' / 'marker.md').read_text() == second.name
    assert (paths.PAGES / doc_id / 'tables' / 'marker.md').read_text() == paths.PAGES.name


def test_custom_root_does_not_read_or_delete_default_ocr(tmp_path, monkeypatch):
    default, attempt = tmp_path / 'pages', tmp_path / 'attempt'
    monkeypatch.setattr(paths, 'PAGES', default)
    doc_id = 'U-20261103-002'
    for root, text in ((default, 'DEFAULT OCR ONLY'), (attempt, 'ATTEMPT OCR ONLY')):
        doc_dir = root / doc_id
        doc_dir.mkdir(parents=True)
        (doc_dir / 'p001.ocr.json').write_text(json.dumps({
            'dpi': 300, 'items': [{'text': text, 'score': 1.0, 'box': [300, 300, 900, 360]}]
        }))
        (doc_dir / 'p001.ocr_input.txt').write_text('old ' + text)
    input_pdf = pdf(tmp_path / 'input.pdf', 'This product contains text unrelated to the image recognition output')

    meta = render.preprocess(input_pdf, doc_id, dpi=50, pages_root=attempt)
    assert meta['pages'][0]['text_source'] == 'OCR'
    loaded = render.load_pages(doc_id, pages_root=attempt)['pages'][0]
    assert 'ATTEMPT OCR ONLY' in loaded['match_text']
    assert (default / doc_id / 'p001.ocr_input.txt').read_text() == 'old DEFAULT OCR ONLY'
    assert not (default / doc_id / 'meta.json').exists()


def test_default_root_remains_backward_compatible(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'PAGES', tmp_path / 'pages')
    doc_id = 'U-20261103-003'
    input_pdf = pdf(tmp_path / 'default.pdf', 'The ordinary default preprocessing still uses the original pages root')
    render.preprocess(input_pdf, doc_id, dpi=50)
    assert (paths.PAGES / doc_id / 'meta.json').exists()
    assert render.load_pages(doc_id)['pages'][0]['image'] == paths.PAGES / doc_id / 'p001.png'
