"""mixture_rules.yaml·class_map.csv 로더와 형식 검증 시험."""
import pytest
import yaml

from msds.compliance.mixture.rules_loader import (RulesFormatError, load_class_map, load_mixture_rules,
                                                  lookup_class)

HEAD = "rule_id,to21_result_code,to21_div_code,db_div_name,db_result_name,class_code,category,form,effect,note\n"


def write_rules(tmp_path, classes, **meta):
    doc = {"meta": {"version": "t1", "source": "시험", "checked_by": "", "checked_date": "", **meta}, "classes": classes}
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return p


def write_map(tmp_path, *lines, header="# version: t1 | source: 시험 | checked_by: | checked_date:\n"):
    p = tmp_path / "m.csv"
    p.write_text(header + HEAD + "".join(l + "\n" for l in lines), encoding="utf-8")
    return p


GOOD = {"HH_X": {"method": "cutoff", "rules": [{"id": "X-1", "category": "1", "when": 'sum("1") >= 1'}]}}


def test_실제_파일을_읽는다():
    r = load_mixture_rules()
    assert len(r["classes"]) > 0 and r["meta"]["version"]
    m = load_class_map(rules=r)
    assert len(m["rows"]) > 0 and m["version"] and m["source"]
    assert all(len(code) == 9 for code in m["by_code"])


def test_실제_파일의_경고와_알림():
    r = load_mixture_rules()
    assert any("checked_by" in w for w in r["warnings"]) and any("checked_date" in w for w in r["warnings"])
    assert isinstance(r["notices"], list) and isinstance(load_class_map(rules=r)["notices"], list)


def test_lookup_class():
    assert lookup_class("GHS010101") == ("PH_EXPLOSIVE", "불안정", None, None)
    assert lookup_class("GHS999999")[0] == "NONE"  # '분류 결과 없음' 행
    assert lookup_class("GHS123456") is None and lookup_class("GHS01010") is None


def test_정상_입력은_통과(tmp_path):
    r = load_mixture_rules(write_rules(tmp_path, GOOD))
    assert r["warnings"] and r["notices"] == []


def test_method_오타(tmp_path):
    with pytest.raises(RulesFormatError, match=r"HH_X\.method"):
        load_mixture_rules(write_rules(tmp_path, {"HH_X": {**GOOD["HH_X"], "method": "cutof"}}))


def test_rules_안_id_중복(tmp_path):
    rules = GOOD["HH_X"]["rules"] * 2
    with pytest.raises(RulesFormatError, match="X-1.*중복"):
        load_mixture_rules(write_rules(tmp_path, {"HH_X": {"method": "cutoff", "rules": rules}}))


def test_항목_사이_id_중복(tmp_path):
    with pytest.raises(RulesFormatError, match="중복"):
        load_mixture_rules(write_rules(tmp_path, {"A": GOOD["HH_X"], "B": GOOD["HH_X"]}))


def test_같은_rule_id를_여러_항목이_써도_됨(tmp_path):
    ate = {"method": "ate", "rule_id": "ATE-MIX-01"}
    assert load_mixture_rules(write_rules(tmp_path, {"A": ate, "B": ate}))["classes"]


def test_파싱_안_되는_when은_모아서_보고(tmp_path):
    bad = {"method": "cutoff", "rules": [{"id": "B-1", "category": "1", "when": 'open("x")'},
                                         {"id": "B-2", "category": "2", "when": "sum("}]}
    with pytest.raises(RulesFormatError) as e:
        load_mixture_rules(write_rules(tmp_path, {"HH_B": bad}))
    assert len(e.value.errors) == 2 and "B-1" in str(e.value) and "B-2" in str(e.value)


def test_빈_version_과_빈_rule_id(tmp_path):
    with pytest.raises(RulesFormatError) as e:
        load_mixture_rules(write_rules(tmp_path, {"A": {"method": "ate", "rule_id": ""}}, version=""))
    assert any("version" in x for x in e.value.errors) and any("A.rule_id" in x for x in e.value.errors)


def test_rules_없는_항목은_알림(tmp_path):
    r = load_mixture_rules(write_rules(tmp_path, {"PH_X": {"method": "transport"}, "PH_Y": {"method": "compare"}}))
    assert r["notices"] == ["PH_X: method 'transport' 인데 rules가 없음"]


def test_class_map_코드_중복(tmp_path):
    p = write_map(tmp_path, "CC-1,GHS010101,GHS0101,a,b,PH_EXPLOSIVE,1,,,", "CC-2,GHS010101,GHS0101,a,b,PH_EXPLOSIVE,2,,,")
    with pytest.raises(RulesFormatError, match="GHS010101.*중복"):
        load_class_map(p, rules={"classes": {}})


def test_class_map_8자리_코드(tmp_path):
    with pytest.raises(RulesFormatError, match="9자리"):
        load_class_map(write_map(tmp_path, "CC-1,GHS01010,GHS0101,a,b,PH_EXPLOSIVE,1,,,"), rules={"classes": {}})


def test_class_map_빈_값과_rule_id_중복(tmp_path):
    p = write_map(tmp_path, "CC-1,GHS010101,GHS0101,a,b,,1,,,", "CC-1,GHS010102,GHS0101,a,b,PH_EXPLOSIVE,2,,,")
    with pytest.raises(RulesFormatError) as e:
        load_class_map(p, rules={"classes": {}})
    assert any("class_code" in x for x in e.value.errors) and any("rule_id" in x and "중복" in x for x in e.value.errors)


def test_class_map_양방향_알림(tmp_path):
    p = write_map(tmp_path, "CC-1,GHS010101,GHS0101,a,b,PH_EXPLOSIVE,1,,,", "CC-2,GHS990001,GHS9900,a,b,ZZ_NEW,1,,,참고")
    m = load_class_map(p, rules={"classes": {"PH_EXPLOSIVE": {}, "HH_ONLY_RULES": {}}})
    assert any("ZZ_NEW" in n and "참고" in n for n in m["notices"])
    assert any("HH_ONLY_RULES" in n for n in m["notices"])
    assert not any("PH_EXPLOSIVE" in n for n in m["notices"])
