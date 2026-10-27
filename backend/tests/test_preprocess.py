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


def _span(text, x0, y0):
    return {"text": text, "bbox": [x0, y0, x0 + 10 * len(text), y0 + 20]}


def test_drop_overstrike_keeps_longest_copy():
    # 45번 1쪽: 굵은 제목을 0.1pt씩 밀어 5번 찍고, 마지막 사본에만 '(MSDS)'가 이어 붙어 있다
    from msds.preprocess.render import _lines_text, drop_overstrike

    lines = [[_span("물질안전보건자료", 345.3 + 0.1 * k, 50.4)] for k in range(4)]
    lines += [[_span("물질안전보건자료(MSDS)", 345.7, 50.4)], [_span("본 물질안전보건자료는", 332.4, 70.5)]]
    kept, removed = drop_overstrike(lines)
    assert _lines_text(kept) == "물질안전보건자료(MSDS)\n본 물질안전보건자료는\n"
    assert removed == 4 * len("물질안전보건자료")


def test_drop_overstrike_keeps_same_text_elsewhere():
    # 같은 글이라도 다른 자리(다른 줄, 같은 줄의 다른 칸)에 있으면 사본이 아니다
    from msds.preprocess.render import drop_overstrike

    lines = [[_span("자료없음", 300, 100), _span("자료없음", 500, 100)], [_span("자료없음", 300, 130)]]
    kept, removed = drop_overstrike(lines)
    assert kept == lines and removed == 0


def test_overstrike_recorded_and_match_text_deduplicated():
    # 실제 문서: 45번만 겹쳐찍기가 있다. 모델 입력(text)은 그대로, 대조용(match_text)만 사본이 빠진다
    from msds.preprocess.render import load_pages

    for doc_id, expect in (("T21-045", True), ("T21-S016", False)):
        row = manifest.get(doc_id)
        try:
            pdf = manifest.raw_pdf(row)
        except FileNotFoundError:
            pytest.skip(f"data/raw/에 {row['source_file']} 없음")
        m = preprocess(pdf, doc_id, force=True)
        assert (m["overstrike"] > 0) is expect
        p1 = load_pages(doc_id)["pages"][0]
        if expect:
            assert p1["text"].count("물질안전보건자료\n") >= 4
            assert p1["match_text"].count("물질안전보건자료\n") <= 1
        else:
            assert "".join(p1["match_text"].split()) == "".join(p1["text"].split())
