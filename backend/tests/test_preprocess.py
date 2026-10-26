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


def _page(n, state, nn):
    return {"page": n, "state": state, "nn": nn}


def test_short_pages_follow_broken_doc():
    from msds.preprocess.render import follow_doc

    pages = [_page(1, "글꼴깨짐", 300), _page(2, "정상", 4), _page(3, "정상", 40), _page(4, "빈쪽", 0)]
    out = follow_doc(pages, "글꼴깨짐")
    # 짧은 '정상' 쪽(ㄴ받침 4)만 문서 판정을 따른다. 쪽만으로 판정한 쪽(ㄴ받침 40)과 빈쪽은 그대로
    assert [p["state"] for p in out] == ["글꼴깨짐", "글꼴깨짐", "정상", "빈쪽"]
    assert out[1]["state_reason"] == "글자가 적어 문서 판정을 따름"


def test_short_pages_unchanged_in_normal_doc():
    from msds.preprocess.render import follow_doc

    pages = [_page(1, "정상", 300), _page(2, "정상", 4)]
    assert follow_doc(pages, "정상") == pages
