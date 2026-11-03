"""우리가 만든 규칙 CSV의 형식(머리 정보, rule_id, source)과 params 연결 시험."""
import pytest

from msds.compliance.mixture.acute import ate_mix, mix_acute
from msds.compliance.mixture.acute_classify import classify_acute
from msds.compliance.mixture.ate_source import inhal_forms
from msds.compliance.mixture.params import RULES_DIR, param, param_list, read_rules

FILES = ["hazard_label_map", "acute_tox_ate", "units", "units_time", "params"]


def first_line(name):
    with open(RULES_DIR / f"{name}.csv", encoding="utf-8-sig") as f:
        return f.readline()


@pytest.mark.parametrize("name", FILES)
def test_머리_정보_rule_id_source(name):
    head = first_line(name)
    assert head.startswith("# version:") and "source:" in head
    rows = read_rules(RULES_DIR / f"{name}.csv")
    assert rows and "rule_id" in rows[0] and "source" in rows[0]
    assert all(r["rule_id"] for r in rows)
    assert all(r["source"].strip() for r in rows)


def test_rule_id는_파일_전체에서_중복_없음():
    ids = [r["rule_id"] for n in FILES for r in read_rules(RULES_DIR / f"{n}.csv")]
    assert len(ids) == len(set(ids))


def test_acute_table_id():
    rows = read_rules(RULES_DIR / "acute_tox_ate.csv")
    assert {r["table_id"] for r in rows} == {"ATE-ORAL", "ATE-DERMAL", "ATE-INHAL-GAS", "ATE-INHAL-VAPOUR",
                                             "ATE-INHAL-MIST"}
    assert all(r["rule_id"] == f"{r['table_id']}-{r['category']}" for r in rows)


def test_params_값():
    keys = ["acute_include_min", "acute_unknown_limit", "acute_mix_rule_id", "acute_basis", "ppm_vapour_molar_volume",
            "density_to_mg_factor", "inhal_base_hours", "trace_amount_upper_percent", "classification_source_order",
            "inhal_forms_기체", "inhal_forms_액체", "inhal_forms_고체", "non_toxic_cas"]
    assert {r["key"] for r in read_rules(RULES_DIR / "params.csv")} == set(keys)
    assert param("acute_include_min") == 1.0 and param("acute_unknown_limit") == 10
    assert param_list("inhal_forms_액체") == ["vapour", "mist"]
    assert param_list("classification_source_order") == ["환경부", "고용노동부"]
    assert param_list("non_toxic_cas") == ["7732-18-5"]  # 물 (설계서 21·24장)
    assert inhal_forms("액체") == ["vapour", "mist"] and inhal_forms("플라즈마") == []


def test_없는_키는_KeyError():
    with pytest.raises(KeyError):
        param("없는_키")


def comps(unknown):
    ate = lambda kind, v=None: {"kind": kind, "value": v, "src": "t", "step": 1}
    c = lambda name, pct, a: {"name": name, "cas": None, "content": {"low": pct, "high": pct}, "ate": a}
    return [c("U", unknown, ate("unknown")), c("A", 100 - unknown, ate("value", 100))]


def test_명시_인자가_params보다_우선():
    assert mix_acute(comps(7), "oral")["low"]["formula"] == "공식1"  # params 10
    assert mix_acute(comps(7), "oral", unknown_limit=5)["low"]["formula"] == "공식2"
    assert mix_acute(comps(0.5), "oral", include_min=0.1)["low"]["unknown_pct"] == 0.5  # 0.5%는 명시 한계 이상
    assert mix_acute(comps(0.5), "oral")["low"]["unknown_pct"] == 0.0  # params 1.0 미만이라 건너뜀


def test_ate_mix_한계는_params():
    parts = [{"c": 7, "ate": None, "known": False}, {"c": 93, "ate": 100, "known": True}]
    assert ate_mix(parts)[1] == "공식1" and ate_mix(parts, unknown_limit=5)[1] == "공식2"


def test_황산_결과가_이전과_같음():
    s = {"name": "황산", "cas": "7664-93-9", "content": {"low": 93, "high": 98}, "non_toxic": False, "classes": [],
         "msds": [], "db": [{"route": "inhal", "form": "mist", "value": 0.375, "unit": "mg/L", "op": "=", "hours": 4}]}
    w = {"name": "물", "cas": None, "content": {"low": 2, "high": 7}, "non_toxic": True, "db": [], "classes": [], "msds": []}
    mist = next(r for r in classify_acute([s, w], "액체") if r["form"] == "분진·미스트")
    assert mist["thresholds"][0]["rule_id"] == "ATE-INHAL-MIST" and mist["rule"]["id"] == "ATE-MIX-01"
    assert mist["rule"]["basis"] == "고시 별표1" and mist["result"] == {"low": "2", "high": "2", "status": "확정"}
