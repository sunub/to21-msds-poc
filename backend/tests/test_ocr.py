"""OCR 줄 묶기·칸 묶기 시험. PaddleOCR 없이 돈다. 좌표는 S003 OCR 결과(300dpi)에서 가져왔다."""
from msds.preprocess.ocr import group_cells, group_lines


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


def cells(items):
    return [(c["kind"], c["label"], c["value"]) for c in group_cells(items)["cells"]]


# 값 열(x≈980)과 오른쪽 끝(x≈2200)을 잡으려면 쪽의 다른 칸이 있어야 해서 함께 넣는다
LONG = "용기가 열에 노출되면 파열되거나 폭발할 수도 있음. 화재 위험은 무시할 수 있음."
FILLER = [item("경구", 410, 400, 480, 440), item("자료없음", 983, 400, 1121, 440),
          item("경피", 410, 460, 480, 500), item(LONG, 983, 460, 2200, 500)]


def test_value_lines_join_into_one_cell():
    # S003 4쪽: 칸 폭 때문에 넘어간 줄은 이어 붙이고, 짧게 끝난 줄 다음은 줄을 바꾼다
    items = FILLER + [
        item("피부부식성 또는 자극성", 363, 723, 715, 757),
        item("Skin, Eye and respiratory Irritations: Contact with liquid may cause frostbite &", 983, 722, 2200, 759),
        item("severe skin burns. /Nitrogen, refrigerated liquid", 984, 767, 1725, 800),
        item("접촉시 동상이 되거나 심하게 탄다", 985, 805, 1499, 842),
        item("심한 눈손상 또는 자극성", 362, 858, 727, 897),
        item("자료없음", 982, 859, 1121, 897),
    ]
    assert cells(items)[2:] == [
        ("항목", "피부부식성 또는 자극성",
         "Skin, Eye and respiratory Irritations: Contact with liquid may cause frostbite & "
         "severe skin burns. /Nitrogen, refrigerated liquid\n접촉시 동상이 되거나 심하게 탄다"),
        ("항목", "심한 눈손상 또는 자극성", "자료없음"),
    ]


def test_wrapped_label_only_on_next_outdented_line():
    # S003 2쪽: '…및 보' / '호구'는 바로 아래 내어쓴 줄이라 이어 붙인다.
    # 1쪽: 들여쓴 '그림문자'는 소항목이다. 값 줄 뒤의 대항목은 항목명에 붙이지 않는다
    items = FILLER + [
        item("가.인체를 보호하기 위해 필요한 조치사항 및 보", 297, 2145, 1023, 2178),
        item("작업자가 위험하지 않다면 직접 화학물질 누출을 중지시키시오.", 1058, 2144, 2008, 2181),
        item("호구", 271, 2185, 344, 2224),
        item("노출지역을 격리조치하고 관계자 이외인의 접근을 통제하시오.", 1061, 2209, 1996, 2243),
        item("나.예방조치문구를 포함한 경고표지 항목", 307, 2300, 931, 2334),
        item("그림문자", 359, 2361, 497, 2399),
        item("자료없음", 983, 2361, 1121, 2399),
        item("7.취급 및 저장방법", 270, 2460, 600, 2500),
    ]
    assert cells(items)[2:] == [
        ("항목", "가.인체를 보호하기 위해 필요한 조치사항 및 보호구",
         "작업자가 위험하지 않다면 직접 화학물질 누출을 중지시키시오.\n노출지역을 격리조치하고 관계자 이외인의 접근을 통제하시오."),
        ("항목", "나.예방조치문구를 포함한 경고표지 항목", ""),
        ("항목", "그림문자", "자료없음"),
        ("항목", "7.취급 및 저장방법", ""),
    ]


def test_full_width_paragraphs_split_on_indent():
    # S003 5쪽 16항 출처: 들여쓴 줄에서 새 문단, 내어쓴 줄은 이어짐. 같은 들여쓰기라도 앞 줄이 짧으면 새 문단
    items = FILLER + [
        item("National Library of Medicine/Hazardous Substances Data Bank(NLM/HSDB)(http://toxnet.nlm.nih.gov/cgi-",
             385, 1000, 2053, 1040),
        item("bin/sis/htmlgen?HSDB)(카.증기압)", 275, 1045, 900, 1085),
        item("SRC(타.용해도)", 385, 1095, 600, 1135),
        item("International Chemical Safety Cards", 385, 1145, 944, 1185),
        item("(ICSC)(http://www.ilo.org/public/english/protection/safework/cis/products/icsc/dtasht/index.htm)(파.증기밀도)",
             275, 1190, 2050, 1230),
    ]
    assert cells(items)[2:] == [
        ("문단", None, "National Library of Medicine/Hazardous Substances Data Bank(NLM/HSDB)"
                      "(http://toxnet.nlm.nih.gov/cgi-bin/sis/htmlgen?HSDB)(카.증기압)"),
        ("문단", None, "SRC(타.용해도)"),
        ("문단", None, "International Chemical Safety Cards (ICSC)(http://www.ilo.org/public/english/protection/"
                      "safework/cis/products/icsc/dtasht/index.htm)(파.증기밀도)"),
    ]


def test_table_row_and_low_score_dropped():
    # S003 1쪽: 오른쪽에 떨어진 조각이 여럿이면 표 행. 신뢰도가 낮은 조각(그림문자를 '/'로 읽음)은 뺀다
    items = FILLER + [
        item("질소(NITROGEN)", 270, 640, 540, 680),
        item("7727-37-9", 1040, 640, 1200, 680), item("KE-25994", 1350, 640, 1520, 680),
        {"text": "/", "score": 0.507, "box": [503, 1940, 750, 2188]},
    ]
    out = group_cells(items)
    assert ("표 행", "질소(NITROGEN)", ["7727-37-9", "KE-25994"]) in [(c["kind"], c["label"], c["value"]) for c in out["cells"]]
    assert [d["text"] for d in out["dropped"]] == ["/"]
