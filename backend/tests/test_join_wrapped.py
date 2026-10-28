"""넘어간 줄을 칸에 잇기 시험 (layout.join_wrapped). 좌표는 pt, 글자 크기(h) 10."""
from msds.preprocess.layout import join_wrapped


def it(text, x0, x1, y):
    return {"text": text, "box": [x0, y, x1, y + 10]}


def texts(rows):
    return [" | ".join(i["text"] for i in r) for r in rows]


def test_value_wrapped_to_next_line():
    rows = [[it("가. 눈에 들어갔을 때", 30, 120, 0), it("즉시 의사 또는", 150, 500, 0)],
            [it("의료기관의 진찰을 받으시오.", 150, 300, 12)],
            [it("나. 피부에 접촉했을 때", 30, 125, 26), it("비누와 물로 씻을 것.", 150, 320, 26)]]
    assert texts(join_wrapped(rows, 10)) == ["가. 눈에 들어갔을 때 | 즉시 의사 또는 의료기관의 진찰을 받으시오.",
                                             "나. 피부에 접촉했을 때 | 비누와 물로 씻을 것."]


def test_first_column_wrapped_in_table_row():
    """성분 표: 이름 칸만 다음 줄로 넘어갔다 (M013 3쪽 'ethylenediamine')."""
    rows = [[it("화학물질명", 30, 80, 0), it("CAS 번호", 290, 330, 0), it("함유량(%)", 500, 540, 0)],
            [it("포름알데히드, polymers with branched 4-nonylphenol and", 30, 253, 14),
             it("1152269-15-2", 290, 346, 14), it("1- <5", 500, 520, 14)],
            [it("ethylenediamine", 30, 99, 26)]]
    out = texts(join_wrapped(rows, 10))
    assert out[1] == "포름알데히드, polymers with branched 4-nonylphenol and ethylenediamine | 1152269-15-2 | 1- <5"
    assert len(out) == 2


def test_short_cell_is_not_wrapped():
    """위 줄 칸이 열 끝까지 차지 않았으면 다음 줄은 새 행이다 (머리글 아래 빈 칸 있는 행)."""
    rows = [[it("화학물질명", 30, 80, 0), it("관용명", 150, 190, 0), it("CAS 번호", 290, 330, 0)],
            [it("벤젠", 30, 50, 12), it("71-43-2", 290, 330, 12)],
            [it("포름알데히드, polymers with branched 4-nonylphenol and", 30, 253, 24), it("1152269-15-2", 290, 346, 24)]]
    assert texts(join_wrapped(rows, 10)) == texts(rows)


def test_merged_table_row_keeps_cells():
    """선으로 그린 표에서 한 조각으로 묶인 행(parts)도 칸 자리를 따라 잇는다."""
    row = {"text": "가. 눈에 들어갔을 때  즉시 의사 또는", "box": [30, 0, 500, 10],
           "parts": [{"text": "가. 눈에 들어갔을 때", "x0": 30, "x1": 120}, {"text": "즉시 의사 또는", "x0": 150, "x1": 500}]}
    rows = [[row], [it("의료기관의 진찰을 받으시오.", 150, 300, 12)]]
    assert texts(join_wrapped(rows, 10)) == ["가. 눈에 들어갔을 때  즉시 의사 또는 의료기관의 진찰을 받으시오."]
