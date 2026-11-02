"""수생 M 계수·분자량을 지식DB에서 읽는 보완 시험 (11/02 F, 설계서 36·56장 D-07).

- rules/m_factor.yaml 표(고시 제2026-26호 별표1 4.2 다)와 examples
- 수생독성 문장 파싱: 부등호 >·< 제외(D-12), 범위 최솟값, ㎍/L 환산, 한 문장 여러 값
- 만성: NOEC 없으면 급성 값, 생분해성 없으면 '빠르게 분해되지 않음'
- 혼합물 판정에 M 이 들어가 구분이 바뀌는지, 근거가 assumptions 에 남는지
- 분자량: 지식DB 먼저, 없으면 9항
"""
import pytest

from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.class_lookup_db import make_db_class_lookup, make_db_info_lookup
from msds.compliance.mixture.classify_mixture import classify_item
from msds.compliance.mixture.m_factor import aquatic_values, load_m_rules, m_factors, m_from
from msds.compliance.mixture.rules_loader import load_class_map

RULES = load_m_rules()
MAP = load_class_map()["rows"]


def spec(kind):
    return RULES["acute"] if kind == "acute" else RULES["chronic"][kind]


@pytest.mark.parametrize("ex", RULES["examples"], ids=lambda e: f"{e['kind']}-{e['value']}")
def test_M표_예시(ex):
    assert m_from(ex["value"], spec(ex["kind"])) == ex["out"]


def tox(div, text):
    return {"div_code": div, "primary_value_text": text}


def test_급성은_쓸_수_있는_값의_최솟값():
    v = aquatic_values([tox("GHS0311", "LC50 > 100 ㎎/ℓ 96 hr"),                 # 부등호 > → 제외
                        tox("GHS0312", "EC50 0.05 ~ 0.2 ㎎/ℓ 48 hr Daphnia"),    # 범위 → 0.05
                        tox("GHS0313", "ErC50 0.3 mg/L 72 hr")])
    assert v["lc50"]["value"] == 0.05 and v["lc50"]["div_code"] == "GHS0312"
    assert any("부등호" in u for u in v["unused"])
    assert m_factors(v)["ENV_AQ_ACUTE"]["m"] == 10


def test_마이크로그램은_mg_L로_환산하고_한_문장의_값을_모두_읽는다():
    v = aquatic_values([tox("GHS0314", "LC50 2.6 mg/L 96 hr; EC50 5 ㎍/L 48 hr")])
    assert v["lc50"]["value"] == pytest.approx(0.005)
    assert m_factors(v)["ENV_AQ_ACUTE"]["m"] == 100


def test_만성은_NOEC와_생분해성으로_정한다():
    rows = [tox("GHS0326", "물벼룩 만성독성시험 NOEC=0.005 mg/L"), tox("GHS0331", "35 % 28 day (난분해성)")]
    ms = m_factors(aquatic_values(rows))
    assert ms["ENV_AQ_CHRONIC"]["m"] == 10 and "빠르게 분해되지 않음" in ms["ENV_AQ_CHRONIC"]["basis"]
    rows[1] = tox("GHS0331", "90 % 28 day (이분해성, OECD TG301F)")
    assert m_factors(aquatic_values(rows))["ENV_AQ_CHRONIC"]["m"] == 1


def test_생분해성_자료가_없으면_빠르게_분해되지_않는_것으로_본다():
    ms = m_factors(aquatic_values([tox("GHS0328", "NOEC 21d = 0.0005 mg/L")]))
    assert ms["ENV_AQ_CHRONIC"]["m"] == 100 and "생분해성 자료 없음" in ms["ENV_AQ_CHRONIC"]["basis"]


def test_NOEC가_없으면_급성_값으로_정한다():
    ms = m_factors(aquatic_values([tox("GHS0311", "LC50 0.02 mg/L 96 hr")]))
    assert ms["ENV_AQ_CHRONIC"]["m"] == 10 and "NOEC 없음" in ms["ENV_AQ_CHRONIC"]["basis"]


def test_값이_없거나_표_밖이면_M을_정하지_않는다():
    ms = m_factors(aquatic_values([]))
    assert ms["ENV_AQ_ACUTE"]["m"] is None and "쓸 값 없음" in ms["ENV_AQ_ACUTE"]["basis"]
    ms = m_factors(aquatic_values([tox("GHS0311", "LC50 2.6 ㎎/ℓ 96 hr")]))
    assert ms["ENV_AQ_ACUTE"]["m"] is None and "표 밖" in ms["ENV_AQ_ACUTE"]["basis"]


def test_샘플CSV_분자량과_M():
    repo = CsvRepo()
    if not repo.available():
        pytest.skip("to21_sample CSV 없음")
    info = make_db_info_lookup(repo)("7664-93-9")               # 황산: LC50 16~28 mg/L → 표 밖
    assert info["mw"] == pytest.approx(98.07) and info["reason"] is None
    assert info["m"]["ENV_AQ_ACUTE"] is None
    assert make_db_info_lookup(repo)("9999-99-9")["reason"] == "지식DB에 등록되지 않은 CAS"


# ── 혼합물 판정에 들어가는지 ────────────────────────────────────────────────

def code(class_code, category):
    return next(r["to21_result_code"] for r in MAP if (r["class_code"], r["category"], r["form"]) == (class_code, category, ""))


class FakeRepo:
    """chemicals·classifications·toxicity 만 있는 지식DB 대용."""

    def __init__(self, table):
        self.table = table  # cas → {"mw", "classes": [결과코드], "tox": [행]}

    def chemicals(self, *, cas, **kw):
        t = self.table.get(cas)
        return {"total": int(bool(t)), "rows": [{"chem_id": cas, "molecular_weight": t.get("mw")}] if t else []}

    def classifications(self, chem_id):
        return {"rows": [{"class_result_code": c, "class_source_db_code": "KR02", "hcode_seq": 1}
                         for c in self.table[chem_id]["classes"]]}

    def toxicity(self, chem_id):
        return {"rows": self.table[chem_id].get("tox", [])}


X = {"mw": "250.3", "classes": [code("ENV_AQ_ACUTE", "1"), code("ENV_AQ_CHRONIC", "1")],
     "tox": [tox("GHS0311", "LC50 0.05 mg/L 96 hr"), tox("GHS0326", "NOEC=0.005 mg/L"), tox("GHS0331", "난분해성")]}


def item(content="3", mw=None):
    comps = [{"seq": 1, "name": "가상성분 X", "cas_no": "1-1-1", "content": {"raw": content, "value": float(content)}},
             {"seq": 2, "name": "물", "cas_no": "7732-18-5", "content": {"raw": "97", "value": 97.0}}]
    phys = [{"prop_code": "MOL_WEIGHT", "comp_ref": "1", "q": {"value": mw, "status": "값있음"}}] if mw else []
    return {"components": comps, "physchem": phys}


def built(it, info=True):
    repo = FakeRepo({"1-1-1": X, "7732-18-5": {"mw": "18.01", "classes": []}})
    return build_components(it, make_db_class_lookup(repo), None, make_db_info_lookup(repo) if info else None)


def test_M10이면_만성1_3퍼센트가_구분1이_된다():
    b = built(item("3"))
    x = b["components"][0]
    assert x["m"] == {"ENV_AQ_ACUTE": 10, "ENV_AQ_CHRONIC": 10}
    r = classify_item("ENV_AQ_CHRONIC", b["components"], b["mixture_props"])
    assert r["result"]["low"] == "1"                                   # 3 × 10 = 30 ≥ 25
    assert any("지식DB 수생독성으로 산출" in a and "M=10" in a for a in r["assumptions"])
    r = classify_item("ENV_AQ_ACUTE", b["components"], b["mixture_props"])
    assert r["result"]["low"] == "1"


def test_info_lookup이_없으면_예전처럼_M1_가정():
    b = built(item("3"), info=False)
    r = classify_item("ENV_AQ_CHRONIC", b["components"], b["mixture_props"])
    assert r["result"]["low"] == "2"                                   # 10 × 3 = 30 ≥ 25 → 구분2
    assert any("m_factor_default(1)" in a for a in r["assumptions"])


def test_분자량은_지식DB_먼저_9항과_다르면_gaps():
    b = built(item("3", mw=180.0))
    x = b["components"][0]
    assert (x["mw"], x["mw_source"]) == (pytest.approx(250.3), "지식DB")
    assert any("분자량 9항 180 ≠ 지식DB 250.3" in g["reason"] for g in b["gaps"])
    b = built(item("3", mw=180.0), info=False)
    assert (b["components"][0]["mw"], b["components"][0]["mw_source"]) == (180.0, "9항")
