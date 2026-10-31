"""역할 A: 검수 화면 위치 찾기(_align)가 오늘 실제로 틀렸던 모양을 다시 틀리지 않는지 본다. 쪽은 글자 상자로 직접 만든다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import review_app as ra  # noqa: E402


def page(*lines):
    """lines: 줄마다 [(x, 글자)]. 글자 하나 = 너비 10, 높이 10, 줄 간격 16."""
    chars = [(ch, (x + 10 * i, 16 * n, x + 10 * i + 10, 16 * n + 10))
             for n, cells in enumerate(lines) for x, text in cells for i, ch in enumerate(ra._norm(text))]
    return ra._Page(chars, 1000, 1000)


def text_of(pg, found):
    return ["".join(pg.vt[k] for k in sorted(f)) for f in found]


def test_wrapped_table_cell():
    """이름 칸이 두 줄로 접히면 오른쪽 칸(TWA, 2 ppm)은 첫 줄에 있다. 아래 행의 TWA를 집지 않는다."""
    pg = page([(0, "디에틸아민(CAS"), (300, "TWA"), (500, "2ppm")],
              [(0, "3710-84-7)")],
              [(0, "나프탈렌(CAS"), (300, "TWA"), (500, "10ppm")])
    assert text_of(pg, ra._align(pg, "디에틸아민 (CAS 3710-84-7) | TWA | 2 ppm")) == ["디에틸아민(castwa2ppm3710-84-7)"]


def test_continues_on_next_page():
    """조각 뒷부분이 다음 쪽에 있으면 이 쪽 윗줄의 다른 행('구분 3')을 집지 않는다."""
    pg = page([(0, "•지정고시:구분3")], [(0, "○피부부식성")], [(0, "•인체피부모델시험결과관찰됨")])
    got = text_of(pg, ra._align(pg, "○ 피부부식성 | • 인체피부모델시험결과관찰됨 (OECD) | • 지정고시 : 구분 1"))
    assert got == ["○피부부식성•인체피부모델시험결과관찰됨"]


def test_same_line_twice():
    """똑같은 줄이 두 곳이면 후보 둘 (화면은 모두 칠하고 몇 곳인지 알린다)."""
    pg = page([(0, "-[물]:자료없음")], [(0, "○생식독성")], [(0, "-[물]:자료없음")])
    assert len(ra._align(pg, "- [물] : 자료없음")) == 2


def test_mismatch_loses():
    """끝이 어긋난 조각 여럿보다 한 덩어리로 맞는 자리('한 LOAEL = 50 ppm')."""
    pg = page([(0, "한LOAEL=50ppm,체중과접촉"), (300, "것을")], [(0, "근거로한NOAEL=20ppm")])
    got = text_of(pg, ra._align(pg, "결과, 체중을 근거로 한 LOAEL = 50 ppm"))
    assert got == ["한loael=50ppm"]


def test_hints_nested_numeric_path():
    """번호 목록이 끝에 오는 경로('…statements[0].text')도 힌트를 만든다 (가장 안쪽 키 있는 항목 기준)."""
    row = lambda p, v: {"경로": p, "Claude 값": v, "GPT 값": "", "수정값": ""}
    rows = [row("msds[0].components[k=64-17-5].name", "에탄올"), row("msds[0].components[k=7664-93-9].name", "황산"),
            row("msds[0].toxicity[k=64-17-5|TX_ORAL||].statements[0].text", "자료없음"),
            row("msds[0].toxicity[k=7664-93-9|TX_ORAL||].statements[0].text", "자료없음")]
    groups = ra._hints("msds[0].toxicity[k=64-17-5|TX_ORAL||].statements[0].text", rows)
    assert any("에탄올" in own and "황산" in others for own, others, _ in groups)


def test_value_elsewhere_no_heading_and_word_edge():
    """항 제목이 없는 쪽(앞 쪽에서 이어짐)에서도 값 자리를 찾고, 'OSH'는 'OSHA' 속에서 집지 않는다."""
    pg = page([(0, "[이소뷰탄올]:시험결과저하(SIDS),래트에")], [(0, "마취효과로분류됨(NITE)")],
              [(0, "미국관리정보(OSHA규정)")])
    area = set(range(len("[이소뷰탄올]:시험결과저하(sids),래트에")))
    got, where = ra._value_elsewhere(pg, "NITE", area, 11)
    assert where == "outside" and "".join(pg.vt[k] for k in sorted(got)) == "nite"
    assert ra._value_elsewhere(pg, "OSH", area, 15)[1] == "absent"
    unit = page([(0, "10일간투여")], [(0, "NOAEL5mg/kg/day")])
    assert ra._value_elsewhere(unit, "day", set(range(6)), 11)[1] == "absent"   # 'mg/kg/day' 속 단위는 값 자리가 아니다


def test_short_pair_and_dash_line_start():
    """조각 '- 3'을 쪽이 '-3'으로 붙여 적어도 칠한다. 다음 줄 첫머리 '- IARC'의 '-'는 윗줄 '발암성'과 같은 낱말이 아니다."""
    pg = page([(0, "다.운송에서의위험성등급")], [(20, "-3")], [(0, "라.용기등급")], [(20, "-II")])
    assert text_of(pg, ra._align(pg, "다. 운송에서의 위험성 등급 - 3 | 라. 용기등급 - II")) == ["다.운송에서의위험성등급-3라.용기등급-ii"]
    cmr = page([(0, "o발암성")], [(20, "-IARC:자료없음")])
    got, where = ra._value_elsewhere(cmr, "발암성", set(range(4, 4 + len("-iarc:자료없음"))), 11)
    assert where == "outside" and "".join(cmr.vt[k] for k in sorted(got)) == "발암성"


def test_statement_value_and_label_pick():
    """문장 목록 항목은 키가 있으면 원문 줄(text), 없으면 그 문장(value)으로 찾는다.
    같은 값이 상자 안에 여러 번이면 칸 이름('·' 뒤)의 낱말이 같은 줄 앞에 있는 자리를 고른다('운송' 같은 항 이름은 쓰지 않는다)."""
    assert ra._plain('{"seq": 6, "key": "용기등급", "value": "해당없음", "text": "· 용기등급 : 해당없음"}') == "· 용기등급 : 해당없음"
    assert ra._plain('{"seq": 2, "key": null, "value": "떨어뜨리지 마시오.", "text": "구멍을 확인하시오. 떨어뜨리지 마시오."}') == "떨어뜨리지 마시오."
    pg = page([(0, "다.운송에서의위험성등급:자료없음")], [(0, "마.해양오염물질(해당/비해당):자료없음")])
    got = ra._value_chars(pg, "자료없음", set(range(len(pg.vt))), "14항 운송 · 해양오염물질")
    assert {pg.line[k] for k in got} == {1}


def test_key_elsewhere_heading_only():
    """키 있는 문장의 노란 자리 위 가장 가까운 묶음 제목이 다른 키('IATA')이고 이 문장의 키도 제목 줄로 있으면 알린다.
    값 줄('마. 해양오염물질 : 해당없음')은 제목이 아니다."""
    pg = page([(0, "IATA")], [(0, "바.특별한안전대책:취급전에안전지침")], [(0, "마.해양오염물질:해당없음")], [(0, "화재시비상조치:F-D")],
              [(0, "국제해상위험물(IMDG)")])
    row = lambda k, key: {"경로": f"msds[0].narratives[k=S14_SPECIAL].statements[k={k}]", "GPT 값": "",
                          "Claude 값": f'{{"seq": {k}, "key": "{key}", "value": "x", "text": "x"}}'}
    rows = [row(1, "IATA"), row(3, "국제해상위험물 (IMDG)"), row(5, "해양오염물질"), row(6, "화재시 비상조치")]
    assert ra._key_elsewhere(pg, [[0, 0.016, 0.3, 0.01]], rows[1], rows) == ("iata", None)
    assert ra._key_elsewhere(pg, [[0, 0.048, 0.3, 0.01]], rows[3], rows) == ("", None)   # 이 문장의 키('화재시 비상조치')는 제목 줄이 아니라 묶음 키가 아니다
    assert ra._key_elsewhere(pg, [[0, 0.048, 0.3, 0.01]], rows[0], rows) == ("", None)
