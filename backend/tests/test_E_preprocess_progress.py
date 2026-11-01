"""render.preprocess의 쪽별 진행 알림(on_page) 시험. 결과는 tmp_path에 쓴다 (data/pages를 건드리지 않는다)."""
from pathlib import Path

import pymupdf
import pytest

from msds.common import paths
from msds.preprocess import render


def make_pdf(path: Path, pages: int) -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{i + 1}. Section title page {i + 1}")
        page.insert_text((72, 96), "Product name : virtual cleaner B, manufacturer virtual chem")
    doc.save(path)
    return path


@pytest.fixture
def pages_root(tmp_path, monkeypatch):
    root = tmp_path / "pages"
    monkeypatch.setattr(paths, "PAGES", root)
    return root


def test_on_page_called_once_per_page_in_order(tmp_path, pages_root):
    calls = []
    meta = render.preprocess(make_pdf(tmp_path / "a.pdf", 3), "U-TEST", dpi=50,
                             on_page=lambda page, total: calls.append((page, total)))
    assert calls == [(1, 3), (2, 3), (3, 3)]
    assert meta["page_count"] == 3
    assert (pages_root / "U-TEST" / "p003.png").is_file()


def test_on_page_absent_still_works(tmp_path, pages_root):
    assert render.preprocess(make_pdf(tmp_path / "b.pdf", 1), "U-TEST2", dpi=50)["page_count"] == 1
