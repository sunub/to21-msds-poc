"""읽기 순서(XY-cut)와 순서 일치율 시험. PDF·PaddleOCR 없이 돈다."""
import importlib.util
import sys
from pathlib import Path

from msds.preprocess.layout import reading_order, reading_text

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ocr_agreement.py"


def item(text, x0, y0, x1, y1):
    return {"text": text, "score": 1.0, "box": [x0, y0, x1, y1]}


def texts(items):
    return [[i["text"] for i in row] for row in reading_order(items)]


def test_stored_order_is_replaced_by_position():
    # S001 2쪽 텍스트층(pt): 2번 항목 본문이 1번 제목보다 먼저 저장돼 있다
    items = [item("1)유해 위험성 분류: 고압가스 압축가스", 19, 315, 251, 327),
             item("2)경고 표지 항목", 19, 334, 131, 346),
             item("1. 화학제품과 회사에 관한 정보", 17, 30, 218, 44),
             item("1)제품명 : N₂(NITROGEN)", 6, 54, 179, 66),
             item("2. 유해위험성", 17, 291, 109, 305)]
    assert reading_text(items).splitlines() == [
        "1. 화학제품과 회사에 관한 정보", "1)제품명 : N₂(NITROGEN)", "2. 유해위험성",
        "1)유해 위험성 분류: 고압가스 압축가스", "2)경고 표지 항목"]


def test_ocr_pieces_of_one_line_stay_in_one_row():
    # S001 2쪽 OCR(300dpi): 한 줄이 조각으로 끊기고, 다음 줄은 내어 쓴 자리에서 시작한다
    items = [item("분위기 가스(철강,금속,석유화학,반도체,의약품 등의 제조공정)", 683, 378, 2109, 442),
             item("가.권고 용도:불활성", 189, 382, 675, 436),
             item("", 666, 402, 676, 417),
             item("각종", 522, 465, 626, 518),
             item("금속열처리,분위기가스,화학 플랜트,배관,탱크 등의 퍼지가스", 637, 462, 2082, 519)]
    assert texts(items) == [["가.권고 용도:불활성", "분위기 가스(철강,금속,석유화학,반도체,의약품 등의 제조공정)"],
                            ["각종", "금속열처리,분위기가스,화학 플랜트,배관,탱크 등의 퍼지가스"]]


def test_label_and_value_on_same_row_are_not_columns():
    # 항목명|값 두 열: 세로 빈 띠가 넓어도 줄 높이가 맞으면 단이 아니다
    items = [item("CAS 번호", 300, 270, 450, 302), item("7727-37-9", 980, 268, 1160, 300),
             item("분자량", 300, 330, 420, 362), item("28.01", 980, 330, 1080, 362)]
    assert texts(items) == [["CAS 번호", "7727-37-9"], ["분자량", "28.01"]]


def test_two_columns_with_offset_lines_read_column_by_column():
    # 줄 높이가 어긋난 두 단 본문은 왼쪽 단을 다 읽고 오른쪽 단을 읽는다
    left = [item(f"왼{k}", 100, 100 + 40 * k, 900, 130 + 40 * k) for k in range(3)]
    right = [item(f"오{k}", 1100, 118 + 40 * k, 1900, 148 + 40 * k) for k in range(3)]
    assert [r[0] for r in texts(right + left)] == ["왼0", "왼1", "왼2", "오0", "오1", "오2"]


def load_agreement():
    sys.path.insert(0, str(SCRIPT.parent))   # 스크립트가 _common을 import한다
    spec = importlib.util.spec_from_file_location("ocr_agreement", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_order_ratio_separates_order_from_characters():
    order_ratio = load_agreement().order_ratio
    a, b = "1. 화학제품과 회사에 관한 정보\n", "2. 유해위험성 고압가스 압축가스\n"
    assert order_ratio(a + b, a + b) == 1.0
    assert order_ratio(b + a, a + b) < 0.7          # 같은 글자, 덩어리 순서만 바뀜
    assert order_ratio(a + b, a.replace("정보", "점보") + b) > 0.95   # 글자 하나 틀림은 순서 문제가 아니다


def test_leading_spaces_of_row_are_kept():
    items = [item("   -예방    용기는", 19, 451, 443, 463), item("  2)경고 표지 항목", 19, 334, 131, 346)]
    assert reading_text(items) == "  2)경고 표지 항목\n   -예방    용기는"


def test_ruled_table_row_keeps_multiline_cells_together():
    # M005 2쪽 성분 표(pt): 두 줄 칸 둘 옆에 가운데 맞춘 한 줄 칸. 칸 안 줄 간격(7.1)과 행 간격(6.8)이 같아
    # 위치만으로는 행을 못 나눈다. 그려진 선의 칸 경계로 한 행을 묶는다
    items = [item("구성성분", 106.5, 717.0, 142.5, 725.5), item("CAS No.", 391.5, 717.0, 426.5, 725.5),
             item("Hydrocarbons, (C=4), ethylene-", 49.0, 732.3, 174.7, 740.7),
             item("manuf.-by-product", 49.0, 747.8, 122.0, 756.2),
             item("Hydrocarbons, (C=4), ethylene-", 206.0, 732.3, 331.7, 740.7),
             item("manuf.-by-product", 206.0, 747.8, 279.0, 756.2),
             item("68476-52-8", 386.0, 737.0, 432.0, 745.5)]
    tables = [[[[47, 714, 204, 729], [204, 714, 384, 729], [384, 714, 470, 729]],
               [[47, 729, 204, 760], [204, 729, 384, 760], [384, 729, 470, 760]]]]
    assert reading_text(items, tables).splitlines() == [
        "구성성분  CAS No.",
        "Hydrocarbons, (C=4), ethylene- manuf.-by-product  Hydrocarbons, (C=4), ethylene- manuf.-by-product  68476-52-8"]
    # 선 정보가 없으면 줄 단위로 읽어 두 칸이 섞인다 (이 시험이 막으려는 것)
    assert "ethylene- manuf.-by-product  Hydrocarbons" not in reading_text(items)


def test_source_choice_uses_ocr_when_words_break():
    # M013: 텍스트층은 글자는 같지만 띄어쓰기·문장부호가 다른 층에 있어 어절이 붙어 버린다
    from msds.preprocess.source import choose

    ocr = "점막과 눈 그리고 경피로 흡수되어 전신 영향을 일으킬 수 있는 물질을 말함(피부자극성을 뜻하는 것이 아님)."
    broken = "점막과눈그리고경피로흡수되어전신영향을일으킬수있는물질을 말함피부자극성을뜻하는것이아님 ( )."
    assert choose(broken, ocr)["input_source"] == "OCR"
    assert choose(ocr.replace("(", " ("), ocr)["input_source"] == "텍스트층"   # 띄어쓰기 조금 다른 정도는 그대로
    assert choose(broken, None) == {"input_source": "텍스트층", "word_agree": None}   # OCR이 없으면 텍스트층
