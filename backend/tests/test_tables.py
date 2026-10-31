"""선으로 그린 표 → 칸 격자 → 데이터 표만 md (layout.table_grid, is_data_table, table_md)."""
from msds.preprocess.layout import is_data_table, table_grid, table_md


def it(text, x0, y0, x1, y1):
    return {"text": text, "box": [x0, y0, x1, y1]}


def test_grid_puts_items_in_cells():
    """칸 상자마다 든 조각을 읽는 순서로 잇는다. 합친 칸 자리(None)는 빈 칸."""
    table = [[[0, 0, 100, 20], [100, 0, 200, 20], None],
             [[0, 20, 100, 40], [100, 20, 200, 40], [200, 20, 300, 40]]]
    items = [it("관용명 및", 110, 2, 190, 9), it("이명", 110, 11, 140, 18), it("물질명", 10, 5, 60, 15),
             it("벤젠", 10, 25, 40, 35), it("71-43-2", 110, 25, 170, 35), it("100", 210, 25, 240, 35),
             it("표 밖 글", 10, 60, 60, 70)]
    assert table_grid(items, table) == [["물질명", "관용명 및 이명", ""], ["벤젠", "71-43-2", "100"]]


def test_data_table_needs_header_row():
    composition = [["화학물질명", "관용명 및 이명", "CAS No.", "함유량(%)"], ["벤젠", "", "71-43-2", "100"]]
    assert is_data_table(composition)
    assert is_data_table([["물질명", "NFPA 지수", "", ""], ["", "보건", "화재", "반응성"]])   # 머리글이 여러 칸에 걸침


def test_item_value_frames_are_not_data_tables():
    assert not is_data_table([["특성", "제품"], ["1)외관", "압축가스"]])                       # 2열 항목|값
    assert not is_data_table([["녹는점/어는점", "-259.2℃ at 54mmHg", "자료없음"]] * 3)        # 머리글 없이 바로 값
    assert not is_data_table([["H335", "호흡기 자극을 일으킬 수 있음.", ""]] * 3)
    assert not is_data_table([["16 기타 참고사항", "", ""], ["가. 자료의 출처", "", "x"]])     # 첫 행이 항 제목 (칸 하나)
    assert not is_data_table([["", "기초소재", "02 829 4114", "첨단소재"]] * 2)                # 전화번호 목록


def test_md_escapes_pipe_and_pads_header():
    grid = [["구성성분", "국내 기준"], ["벤젠", "TWA 0.5 | STEL 2.5"]]
    assert table_md(grid) == ("| 구성성분 | 국내 기준 |\n"
                              "| --- | --- |\n"
                              "| 벤젠 | TWA 0.5 \\| STEL 2.5 |\n")


def test_continued_table_takes_previous_columns():
    """M013 3쪽: 열 선 없이 머리글이 되풀이된 성분 표. 앞 쪽 표의 열 자리로 칸을 나누고, 칸이 하나뿐인 행(항 제목)에서 멈춘다."""
    from msds.preprocess.layout import continue_grid, table_columns

    prev = [[[33, 0, 153, 20], [153, 0, 252, 20], [252, 0, 366, 20]],
            [[33, 20, 153, 40], None, [252, 20, 366, 40]]]
    cols = table_columns(prev)
    assert cols == [(33, 153), (153, 252), (252, 366)]
    table = [[[33, 133, 156, 157], [156, 133, 569, 157]],          # 선으로는 2열로만 잡힌다
             [[33, 157, 156, 175], [156, 157, 569, 175]],
             [[33, 175, 569, 202], None],
             [[33, 202, 156, 225], [156, 202, 569, 225]]]
    items = [it("화학물질명", 33, 132, 72, 142), it("관용명 및 이명", 158, 132, 210, 142), it("CAS 번호", 300, 132, 336, 142),
             it("벤젠", 33, 160, 60, 168), it("71-43-2", 300, 160, 336, 168),
             it("포름알데히드, polymers and", 33, 178, 140, 187), it("1152269-15-2", 290, 178, 346, 187),
             it("ethylenediamine", 33, 188, 99, 197),
             it("4. 응급조치 요령", 34, 211, 106, 222)]
    head = ["화학물질명", "관용명및 이명", "CAS번호"]
    assert continue_grid(items, table, cols, head) == [
        ["화학물질명", "관용명 및 이명", "CAS 번호"],
        ["벤젠", "", "71-43-2"],
        ["포름알데히드, polymers and ethylenediamine", "", "1152269-15-2"]]
    assert continue_grid(items, table, cols, ["물질명", "CAS번호", "함유량"]) is None   # 머리글이 다르면 이어진 표가 아니다
