"""지식DB 번역표(13_TO21DB매핑) 읽기와 추출 JSON 코드 찾기. DB 없이 동작한다.

TO21 자료의 값은 시험 코드에 적지 않는다(D-47). 동작 규칙은 만든 가짜 행으로 시험하고,
실제 시트·25번 예제는 각자 둔 파일(to21/v0.6/)을 실행 때 읽어 '시트가 적은 그대로 번역되는지'만 확인한다.
"""
import pytest

from msds.compliance.htodb.mapping import NOT_CLASSIFIED, Map13, code_sites, normalize_cas, normalize_un, parse_div_codes
from msds.compliance.htodb.sheet13 import read_sheet

COLS = ["sheet_row", "section"] + [f"c{i}" for i in range(1, 8)]


def row(n, section, *cells):
    return dict(zip(COLS, (n, section, *(cells + ("",) * (7 - len(cells))))))


# 시트와 같은 모양의 가짜 행(코드 값은 모두 지어낸 것)
FAKE = [
    row(1, None, "제목"),
    row(2, "B", "B. 분류"),
    row(3, "B", "머리글1", "머리글2", "머리글3", "머리글4", "머리글5"),
    row(4, "B", "T_PLAIN", "1", "", "", "GHS990101"),
    row(5, "B", "T_ROUTE", "2", "가스", "", "GHS990201"),
    row(6, "B", "T_ROUTE", "2", "증기", "", "GHS990202"),
    row(7, "B", "T_EFFECT", "3", "", "자극", "GHS990301"),
    row(8, "B", "T_EFFECT", "3", "", "마취", "GHS990302"),
    row(9, "B", "T_EFFECT", "1", "", "", "GHS990303"),
    row(10, "B", NOT_CLASSIFIED, "x", "", "", "GHS990999"),
    row(11, "C", "머리글1", "머리글2", "머리글3", "", "머리글5", "머리글6"),
    row(12, "C", "GHS01", "SYMX1", "", "", "신호가", "SW_A"),
    row(13, "C", "GHS02", "SYMX9"),
    row(14, "D", "머리글1", "머리글2"),
    row(15, "D", "P_A · P_B", "G0000000001"),
    row(16, "D", "(자리표시)", "G0000000002"),
    row(17, "E", "머리글1", "머리글2"),
    row(18, "E", "E_ONE", "GHS9901"),
    row(19, "E", "E_SHORT", "GHS9902 / 9903 / 9904"),
    row(20, "E", "E_DOT", "GHS9905 (가) · GHS9906 (나)"),
    row(21, "F", "머리글1", "머리글2", "머리글3", "머리글4"),
    row(22, "F", "R_A", "법", "가", "KR990000001"),
    row(23, "F", "R_A", "법", "가", "KR990000002"),
    row(24, "F", "R_SUB", "법", "가", "KR990000001_1"),
    row(25, "F", "(자리표시)", "법", "가", "KR990000003"),
]


@pytest.fixture(scope="module")
def fake():
    return Map13(FAKE)


def ids(rows, key):
    return [r[key] for r in rows]


@pytest.mark.parametrize("cell, expected", [
    ("GHS9901", ["GHS9901"]),
    ("GHS9902 / 9903 / 9904", ["GHS9902", "GHS9903", "GHS9904"]),
    ("GHS9905 (가) · GHS9906 (나)", ["GHS9905", "GHS9906"]),
    ("(메모 GHS9907)", ["GHS9907"]),
    ("머리글", []),
])
def test_parse_div_codes(cell, expected):
    assert parse_div_codes(cell) == expected


def test_key_normalization():
    for raw in [" 50-00-0 ", "50－00－0", "50‐00‐0", "50﹣00­0", "50−00⁃0"]:
        assert normalize_cas(raw) == "50-00-0", raw
    assert normalize_un("UN1234  ") == normalize_un("1234") == normalize_un("un 1234") == "1234"


def test_hazard_rules(fake):
    assert ids(fake.hazard("T_PLAIN", "1"), "class_result_code") == ["GHS990101"]
    assert fake.hazard("T_PLAIN", "1")[0]["sheet_row"] == 4
    assert ids(fake.hazard("T_ROUTE", "2", "증기"), "class_result_code") == ["GHS990202"]
    assert fake.hazard("T_ROUTE", "2", None) == []                  # 시트가 형태로 나누면 형태 없이는 고르지 않음
    assert ids(fake.hazard("T_EFFECT", "3", effect="마취"), "class_result_code") == ["GHS990302"]
    assert ids(fake.hazard("T_EFFECT", "1", effect="마취"), "class_result_code") == ["GHS990303"]  # 나누지 않는 구분
    assert ids(fake.hazard(NOT_CLASSIFIED, None), "class_result_code") == ["GHS990999"]
    assert fake.hazard("T_PLAIN", "9") == [] and fake.hazard("category", "route_form") == []


def test_other_kinds(fake):
    assert ids(fake.pictogram("GHS02"), "symbol") == ["SYMX9"]
    assert ids(fake.signal_word("신호가"), "sign_word") == ["SW_A"]
    assert fake.pictogram("머리글1") == [] and fake.signal_word("머리글5") == []          # 머리글 행 제외
    assert ids(fake.property("P_A"), "property_id") == ids(fake.property("P_B"), "property_id") == ["G0000000001"]
    assert fake.property("(자리표시)") == [] and fake.regulation("(자리표시)") == []
    assert fake.endpoint("E_SHORT")[0]["div_codes"] == ["GHS9902", "GHS9903", "GHS9904"]
    assert ids(fake.regulation("R_A"), "regulate_item_id") == ["KR990000001", "KR990000002"]
    assert ids(fake.regulation("R_SUB"), "regulate_item_id") == ["KR990000001_1"]
    assert fake.regulation("NONE") == []


def test_real_sheet_rows_map_as_written():
    """각자 둔 명세서의 시트 행마다, 번역 결과가 그 행이 적은 코드와 같아야 한다(값은 실행 때 읽음)."""
    rows = [dict(zip(COLS, r)) for r in read_sheet()]
    m = Map13(rows)
    assert m.hazard_rows and m.pictogram_rows and m.property_rows and m.endpoint_rows and m.regulation_rows
    for r in m.hazard_rows:
        got = m.hazard(r["c1"], r["c2"], r["c3"] or None, r["c4"] or None)
        assert ids(got, "sheet_row") == [r["sheet_row"]], r["sheet_row"]
    for r in m.pictogram_rows:
        assert r["sheet_row"] in ids(m.pictogram(r["c1"]), "sheet_row")
    for r in m.property_rows:
        for code in (c.strip() for c in r["c1"].split("·")):
            assert r["sheet_row"] in ids(m.property(code), "sheet_row")
    for r in m.endpoint_rows:
        assert r["sheet_row"] in ids(m.endpoint(r["c1"]), "sheet_row")
    for r in m.regulation_rows:
        assert r["sheet_row"] in ids(m.regulation(r["c1"]), "sheet_row")
    data_rows = {r["sheet_row"] for r in m.hazard_rows + m.pictogram_rows + m.signal_rows + m.property_rows
                 + m.endpoint_rows + m.regulation_rows}
    for r in rows:                                               # 제목·머리글·설명 행은 어떤 번역에도 안 걸림
        if r["sheet_row"] in data_rows:
            continue
        for v in filter(None, [r[f"c{i}"] for i in range(1, 8)]):
            assert not (m.pictogram(v) or m.signal_word(v) or m.property(v) or m.endpoint(v) or m.regulation(v)), r


def _count_codes(doc):
    """code_sites와 독립으로 같은 위치를 센다."""
    n = 0
    for m in doc["msds"]:
        for c in m.get("components") or []:
            n += bool(c.get("cas_no")) + bool(c.get("ke_no"))
        n += sum(bool(t.get("un_no")) for t in m.get("transport") or [])
        hz = m.get("hazard") or {}
        n += (hz.get("classified") is False) + sum(bool(h.get("class_code")) for h in hz.get("classes") or [])
        n += sum(bool(g.get("code")) for g in hz.get("pictograms") or []) + bool(hz.get("signal_word"))
        n += sum(bool(h.get("code")) for h in hz.get("h_statements") or [])
        for key, f in (("physchem", "prop_code"), ("toxicity", "endpoint"), ("ecotox", "endpoint"), ("regulations", "item_code")):
            n += sum(bool(x.get(f)) for x in m.get(key) or [])
    return n


def test_code_sites_on_example(gold25):
    sites = code_sites(gold25)
    assert len(sites) == _count_codes(gold25) > 0
    for s in sites:                                              # path가 실제로 그 값을 가리킨다
        node = gold25
        for part in s["path"].replace("]", "").replace("[", ".").split("."):
            node = node[int(part)] if part.isdigit() else node[part]
        if s["kind"] == "hazard_class":
            assert node is False or node["class_code"] == s["value"]["class_code"], s["path"]
        else:
            assert node == s["value"], s["path"]


def test_code_sites_synthetic():
    doc = {"msds": [{"components": [{"seq": 1, "cas_no": "50-00-0", "ke_no": None}],
                     "hazard": {"classified": False, "classes": [], "signal_word": "신호가",
                                "pictograms": [{"code": "GHS01"}], "h_statements": [{"code": "H999"}]},
                     "ecotox": [{"endpoint": "E_ONE", "comp_ref": "1"}], "regulations": [{"item_code": "R_A"}]}]}
    kinds = [(s["path"], s["kind"]) for s in code_sites(doc)]
    assert kinds == [("msds[0].components[0].cas_no", "cas"), ("msds[0].hazard.classified", "hazard_class"),
                     ("msds[0].hazard.pictograms[0].code", "pictogram"), ("msds[0].hazard.signal_word", "signal_word"),
                     ("msds[0].hazard.h_statements[0].code", "h_code"), ("msds[0].ecotox[0].endpoint", "endpoint"),
                     ("msds[0].regulations[0].item_code", "regulation")]


@pytest.mark.parametrize("body", [
    {}, {"msds": [1]}, {"msds": [{"hazard": "x"}]}, {"msds": [{"transport": "x"}]},
    {"msds": [{"components": [{"cas_no": 123}]}]}, {"msds": [{"hazard": {"h_statements": [{"code": 5}]}}]},
])
def test_code_sites_rejects_malformed(body):
    with pytest.raises(ValueError):
        code_sites(body)
