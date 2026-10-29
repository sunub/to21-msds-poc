"""글자 단위 재조립 시험 (layout.char_items)."""
import pymupdf

from msds.preprocess.layout import char_items


def _page(draw):
    doc = pymupdf.open()
    page = doc.new_page()
    draw(page)
    return page


def _texts(page):
    return [i["text"] for i in sorted(char_items(page), key=lambda i: (i["box"][1], i["box"][0]))]


def test_layers_are_merged_by_position():
    """M013처럼 숫자와 하이픈을 따로 찍어도 좌표 순서로 한 조각이 된다."""
    x = {}
    pos = 100
    for part in ("64742", "-1", "94", "-2", "5"):   # 원래 글 '64742-94-5'에서 각 조각이 놓일 자리
        x[part] = pos
        pos += pymupdf.get_text_length(part[0] if part.startswith("-") else part, fontsize=10)

    def draw(p):
        for part in ("64742", "94", "5"):
            p.insert_text((x[part], 100), part, fontsize=10)
        for part in ("-1", "-2"):   # 나중에 다른 층으로 찍은 하이픈
            p.insert_text((x[part], 100), "-", fontsize=10)
    assert _texts(_page(draw)) == ["64742-94-5"]


def test_overstrike_copy_is_dropped():
    def draw(p):
        for dx in (0, 0.1, 0.2):   # 굵게 보이려고 조금씩 밀어 여러 번 찍은 글
            p.insert_text((100 + dx, 100), "Benzene", fontsize=10)
    assert _texts(_page(draw)) == ["Benzene"]


def test_spaces_and_far_columns():
    """띄어쓴 곳은 공백 하나, 칸처럼 멀리 떨어진 곳은 다른 조각."""
    def draw(p):
        p.insert_text((100, 100), "CAS No.", fontsize=10)
        p.insert_text((300, 100), "71-43-2", fontsize=10)
    assert _texts(_page(draw)) == ["CAS No.", "71-43-2"]


def test_ocr_degree_c_restored():
    """OCR 사전에 ℃가 없어 숫자 뒤 'C', '°c'로 읽힌다 (S003). 숫자 뒤 단독 C만 °C로 되돌린다."""
    from msds.preprocess.ocr import fix_symbols

    assert fix_symbols("-196 C (-195.79 DEG C /LIQ/") == "-196 °C (-195.79 DEG C /LIQ/"
    assert fix_symbols("(1.18E+004mg/L(25°c))") == "(1.18E+004mg/L(25°C))"
    for keep in ("Hydrocarbons (C=4)", "C6H6", "P-M(CC)", "4 Cl", "25 CO2", "58 °C"):
        assert fix_symbols(keep) == keep
