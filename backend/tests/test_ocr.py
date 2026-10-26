"""OCR 줄 묶기 시험. PaddleOCR 없이 돈다."""
from msds.preprocess.ocr import group_lines


def item(text, x0, y0, x1, y1):
    return {"text": text, "score": 1.0, "box": [x0, y0, x1, y1]}


def test_same_line_with_small_offset():
    # S003 6쪽: '참고하여'만 몇 픽셀 낮게 잡혀도 같은 줄이어야 한다
    items = [
        item("작성된 물질 안전보건자료(MSDS)는", 342, 1137, 957, 1187),
        item("한국산업안전보건공단에서 제공한MSDS를", 949, 1135, 1683, 1186),
        item("편집,일부 수정한", 1858, 1134, 2197, 1191),
        item("참고하여", 1693, 1140, 1851, 1183),
        item("자료입니다.", 346, 1186, 556, 1231),
    ]
    assert group_lines(items) == [
        "작성된 물질 안전보건자료(MSDS)는 한국산업안전보건공단에서 제공한MSDS를 참고하여 편집,일부 수정한",
        "자료입니다.",
    ]


def test_label_and_value_columns_join_in_order():
    items = [item("7727-37-9", 980, 268, 1160, 300), item("CAS 번호", 300, 270, 450, 302)]
    assert group_lines(items) == ["CAS 번호 7727-37-9"]
