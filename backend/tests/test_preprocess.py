"""전처리 시험. data/raw/에 해당 원본이 있을 때만 돈다."""
import shutil

import pytest

from msds.common import manifest, paths
from msds.preprocess.render import preprocess

CASES = {"T21-S016": "정상", "T21-S003": "글꼴깨짐", "T21-043": "글꼴깨짐", "T21-S013": "정상"}


@pytest.fixture(autouse=True)
def isolate_preprocess_outputs(tmp_path, monkeypatch):
    """force=True도 저장된 추출물을 덮어쓰지 않도록 시험별 임시 폴더에 쓴다.

    원본 PDF와 manifest는 그대로 읽고, 출처 선택에 필요한 기존 OCR JSON만 복사한다.
    결과 TXT·PNG·meta·표는 복사하지 않고 전처리가 임시 폴더에서 새로 만들게 한다.
    """
    previous_pages = paths.PAGES
    temporary_pages = tmp_path / "pages"
    for doc_id in (*CASES, "T21-045", "T21-S001"):
        source = previous_pages / doc_id
        for pattern in ("ocr_all/p[0-9][0-9][0-9].ocr.json", "p[0-9][0-9][0-9].ocr.json"):
            for cached in source.glob(pattern):
                target = temporary_pages / doc_id / cached.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cached, target)
    monkeypatch.setattr(paths, "PAGES", temporary_pages)


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
    # 실제 문서: 45번만 겹쳐찍기가 있다. 사본 글자 수는 기록하고, 모델 입력·대조용 모두 사본이 빠진다
    # (2026-10-28 글자 단위 재조립부터. 그 전에는 모델 입력에 사본이 그대로 남았다)
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
        assert "".join(p1["text"].split()).count("물질안전보건자료(MSDS)") == 1   # 45번은 이 제목을 5번 겹쳐 찍었다
        assert "".join(p1["match_text"].split()) == "".join(p1["text"].split())


def test_page_text_follows_reading_order_with_indent():
    # S001 2쪽: PDF에는 2번 항목 본문이 1번보다 먼저 저장돼 있다. 모델 입력·대조용 모두 읽는 순서로 놓고,
    # 앞 공백으로 쓴 들여쓰기는 남긴다
    from msds.preprocess.render import PREPROCESS_VERSION, load_pages

    row = manifest.get("T21-S001")
    try:
        pdf = manifest.raw_pdf(row)
    except FileNotFoundError:
        pytest.skip(f"data/raw/에 {row['source_file']} 없음")
    m = preprocess(pdf, "T21-S001", force=True)
    assert m["preprocess_version"] == PREPROCESS_VERSION
    p2 = load_pages("T21-S001")["pages"][1]
    for text in (p2["text"], p2["match_text"]):
        lines = [ln.strip() for ln in text.splitlines()]
        assert lines.index("1. 화학제품과 회사에 관한 정보") < lines.index("2. 유해위험성") \
            < lines.index("1)유해 위험성 분류: 고압가스 압축가스")
    assert "\n          -예방" in p2["text"]


def test_ruled_table_row_is_one_line():
    # S001 3쪽 성분 표: 관용명 칸만 두 줄이라 줄 단위로 읽으면 한 행이 네 줄로 흩어졌다. 그려진 선의 칸으로 한 줄에 묶는다
    from msds.preprocess.render import load_pages

    row = manifest.get("T21-S001")
    try:
        pdf = manifest.raw_pdf(row)
    except FileNotFoundError:
        pytest.skip(f"data/raw/에 {row['source_file']} 없음")
    preprocess(pdf, "T21-S001", force=True)
    p3 = load_pages("T21-S001")["pages"][2]
    for text in (p3["text"], p3["match_text"]):
        assert "NITROGEN  질소가스 NITROGEN  N₂  7727-37-9  100%" in text.splitlines()
