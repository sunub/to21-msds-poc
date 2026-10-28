"""전처리 시험. data/raw/에 해당 원본이 있을 때만 돈다."""
import pytest

from msds.common import manifest
from msds.preprocess.render import preprocess

CASES = {"T21-S016": "정상", "T21-S003": "글꼴깨짐", "T21-043": "글꼴깨짐", "T21-S013": "정상"}


@pytest.mark.parametrize("doc_id,expected", CASES.items())
def test_text_layer(doc_id, expected):
    row = manifest.get(doc_id)
    try:
        pdf = manifest.raw_pdf(row)
    except FileNotFoundError:
        pytest.skip(f"data/raw/에 {row['source_file']} 없음")
    m = preprocess(pdf, doc_id, force=True)
    assert m["text_layer"] == expected
    assert m["page_count"] == int(row["pages"])
