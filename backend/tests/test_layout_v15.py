"""v15 opt-in: 빈 표 칸과 줄이 접힌 항목|값의 경계를 보존한다."""
from copy import deepcopy
from pathlib import Path

import pytest

from msds.preprocess.layout import reading_order


def piece(text, x0, y0, x1, y1):
    return {"text": text, "box": [x0, y0, x1, y1]}


def rows(items, tables=None):
    return reading_order(items, tables, preserve_empty_cells=True, repair_table_layout=True)


def cells(row):
    return [part["text"] for entry in row for part in entry.get("parts", [entry])]


def test_empty_middle_and_trailing_table_cells_keep_their_positions():
    items = [piece("물질명", 5, 2, 40, 12), piece("CAS", 105, 2, 135, 12),
             piece("UN", 205, 2, 230, 12), piece("EU", 305, 2, 330, 12),
             piece("혼합물", 5, 22, 40, 32), piece("123-45-6", 105, 22, 150, 32),
             piece("200-000-0", 305, 22, 350, 32), piece("다음물질", 5, 42, 50, 52)]
    table = [[[100 * c, 20 * r, 100 * (c + 1), 20 * (r + 1)] for c in range(4)] for r in range(3)]
    original = deepcopy(items)
    actual = rows(items, [table])
    assert [cells(row) for row in actual] == [
        ["물질명", "CAS", "UN", "EU"], ["혼합물", "123-45-6", "", "200-000-0"], ["다음물질", "", "", ""]]
    assert items == original
    # 기존 버전 호출은 빈 칸을 생략하던 동작을 그대로 유지한다.
    assert cells(reading_order(items, [table])[1]) == ["혼합물", "123-45-6", "200-000-0"]


def test_spanned_cells_are_not_invented_as_separate_empty_columns():
    items = [piece("합친 칸", 10, 5, 70, 15), piece("값", 220, 5, 240, 15)]
    table = [[[0, 0, 200, 20], None, [200, 0, 300, 20]]]
    assert cells(rows(items, [table])[0]) == ["합친 칸", "값"]


def test_actual_table_rows_do_not_merge_when_the_next_label_cell_is_empty():
    description = "설명을 충분히 길게 작성하고 각 단어의 순서를 보존하는 첫 번째 값"
    continuation = "이것도 긴 설명이지만 별도의 표 행에 있으므로 합치면 안 됩니다"
    items = [piece("가. 길고 자세한 항목명", 5, 2, 95, 12), piece(description, 105, 2, 400, 12),
             piece(continuation, 105, 14, 390, 24)]
    table = [[[0, 0, 100, 13], [100, 0, 450, 13]], [[0, 13, 100, 26], [100, 13, 450, 26]]]
    assert [cells(row) for row in rows(items, [table])] == [
        ["가. 길고 자세한 항목명", description], [continuation]]


def test_only_data_table_headers_enable_empty_column_slots():
    items = [piece("물질안전보건자료", 110, 2, 180, 12),
             piece("회사명", 5, 22, 40, 32), piece("회사", 110, 22, 150, 32)]
    frame = [[[100 * c, 20 * r, 100 * (c + 1), 20 * (r + 1)] for c in range(3)] for r in range(2)]
    assert [cells(row) for row in rows(items, [frame])] == [["물질안전보건자료"], ["회사명", "회사"]]


def test_data_table_header_retains_an_empty_leading_cell_in_a_new_row():
    header = [piece("경로", 5, 2, 40, 12), piece("설명", 105, 2, 130, 12), piece("조건", 455, 2, 480, 12)]
    items = header + [piece("첫 경로", 5, 15, 45, 25), piece("첫 설명", 105, 15, 400, 25),
                      piece("첫 조건", 455, 15, 480, 25), piece("별도 설명", 105, 28, 390, 38),
                      piece("별도 조건", 455, 28, 480, 38)]
    table = [[[0, y, 100, y + 13], [100, y, 450, y + 13], [450, y, 500, y + 13]] for y in [0, 13, 26]]
    assert [cells(row) for row in rows(items, [table])] == [
        ["경로", "설명", "조건"], ["첫 경로", "첫 설명", "첫 조건"], ["", "별도 설명", "별도 조건"]]


@pytest.mark.parametrize("heading", ["예방조치문구", "Precautionary statements:"])
def test_real_whitespace_above_short_subheading_keeps_previous_hazard_before_it(heading):
    items = [piece("이전 라벨", 0, 0, 40, 10), piece("H280 가열하면 폭발할 수 있음", 150, 27, 250, 37),
             piece(heading, 0, 50, 80, 60), piece("P210 화기로부터 멀리하시오", 150, 70, 250, 80)]
    actual = [text for row in rows(items) for text in cells(row)]
    assert actual.index("H280 가열하면 폭발할 수 있음") < actual.index(heading)


def test_subheading_keyword_inside_a_sentence_does_not_create_a_boundary():
    from msds.preprocess.layout import _gaps, _subheading_cut, _y

    items = [piece("앞 문장", 0, 0, 40, 10), piece("예방조치문구를 확인하시오", 0, 30, 100, 40)]
    assert _subheading_cut(items, _gaps([_y(i) for i in items], 0), 10) is None


def test_subheading_requires_a_gap_across_the_whole_region():
    from msds.preprocess.layout import _gaps, _subheading_cut, _y

    items = [piece("예방조치문구", 0, 40, 80, 50), piece("오른쪽 연속 본문", 150, 0, 250, 100)]
    assert _subheading_cut(items, _gaps([_y(i) for i in items], 0), 10) is None


def test_false_table_row_cannot_attach_previous_value_to_next_section_heading():
    value = "노출된 경우에는 의사에게 사용한 물질을 알리고 필요한 예방 조치를 취할 수"
    tail = "있도록 조치하며 의사에게 자료를 보여주고 의복을 다시 세척하시오."
    items = [piece("일반 조치", 0, 100, 70, 110), piece(value, 180, 100, 570, 110),
             piece(tail, 180, 112, 500, 122), piece("5. 폭발·화재시 대처방법", 0, 140, 140, 152)]
    fake = [[[0, 95, 150, 112], [150, 95, 600, 112]],
            [[0, 112, 150, 160], [150, 112, 600, 160]]]
    actual = rows(list(reversed(items)), [fake])
    assert [cells(row) for row in actual] == [["일반 조치", value + " " + tail], ["5. 폭발·화재시 대처방법"]]


def test_wrapped_label_and_value_join_by_column_and_stop_at_next_list_item():
    value = "긴 설명의 처음 부분이며 의미와 순서를 유지하면서 다음 줄로 이어집니다"
    tail = "설명의 두 번째 부분도 원래 값에 이어서 읽어야 하는 문장입니다"
    items = [piece("가. 인체를 보호하기 위해 필요한", 0, 100, 114, 110), piece(value, 150, 100, 550, 110),
             piece("조치사항 및 보호구", 0, 112, 95, 122), piece(tail, 150, 112, 500, 122),
             piece("나. 환경을 보호하기 위해 필요한", 0, 126, 114, 136), piece(value, 150, 126, 550, 136)]
    actual = rows(items)
    assert [cells(row) for row in actual] == [
        ["가. 인체를 보호하기 위해 필요한 조치사항 및 보호구", value + " " + tail],
        ["나. 환경을 보호하기 위해 필요한", value]]


def test_short_toxicity_codes_are_not_treated_as_prose_continuations():
    items = [piece("LD50", 0, 100, 30, 110), piece("1200", 150, 100, 180, 110),
             piece("경피", 150, 112, 170, 122)]
    assert len(rows(items)) == 2


def test_section_heading_is_always_a_boundary_even_after_a_filled_line():
    items = [piece("앞 항목", 0, 100, 40, 110),
             piece("설명은 오른쪽 끝까지 채워져 있지만 다음 제목과 합치면 안 됩니다", 150, 100, 550, 110),
             piece("9. 물리화학적 특성", 150, 112, 260, 122)]
    assert len(rows(items)) == 2


@pytest.mark.parametrize("relative", ["수집MSDS_50건/47_T-480_MSDS.pdf", "M013_베올리아_Petroflo.pdf"])
def test_original_pdf_regressions_when_private_fixture_is_available(relative):
    """개인 원본은 저장소에 없으므로 CI에서는 이 두 회귀 사례만 건너뛴다."""
    from msds.preprocess import layout
    import pymupdf

    source = Path(__file__).resolve().parents[2] / "data" / "raw" / relative
    if not source.exists():
        pytest.skip("비공개 PDF 회귀 자료 없음")
    with pymupdf.open(source) as document:
        page = document[0 if relative.startswith("수집") else 2]
        actual = [cells(row) for row in rows(layout.char_items(page), layout.page_tables(page))]
    if relative.startswith("수집"):
        row = next(row for row in actual if any("65997-17-3" in text for text in row))
        assert len(row) == 5 and row[3] == "" and row[4] == "266-046-0"
    else:
        heading = next(i for i, row in enumerate(actual) if any(text.startswith("5. 폭발") for text in row))
        assert actual[heading] == ["5. 폭발·화재시 대처방법"]
        assert "예방 조치를 취할 수 있도록 할 것." in actual[heading - 1][1]
        label = next(row for row in actual if any(text.startswith("나. 화학물질로부터") for text in row))
        assert len(label) == 2 and "유해성 (예: 연소시 발생 유해물질)" in label[0]
        assert "증기는" in label[1] and "화재 발생 시" in label[1]
