"""표시 요소 비교 compare_label과 label_rules.yaml 형식 시험."""
import pytest

from msds.compliance.label import derive_label, label_rules
from msds.compliance.label_compare import compare_label
from msds.compliance.mixture.params import RULES_DIR, read_rules

SULFURIC = [("PH_METAL_CORR", "1"), ("HH_ACUTE_INHAL", "2"), ("HH_SKIN_CORR", "1"), ("HH_EYE_DMG", "1"),
            ("HH_CARCINOGEN", "1A"), ("HH_STOT_SE", "1"), ("ENV_AQ_CHRONIC", "3")]


def by_item(findings, item):
    return [f for f in findings if f["item"] == item]


def msds_of(d, **over):
    return {"pictograms": d["pictograms"], "signal_word": d["signal_word"], "h_codes": d["h_codes"], **over}


def test_황산_전부_일치():
    d = derive_label(SULFURIC)
    r = compare_label(d, msds_of(d))
    assert [(f["item"], f["verdict"]) for f in r] == [("h_codes", "일치"), ("pictograms", "일치"), ("signal_word", "일치")]


def test_h코드_누락은_불일치():
    d = derive_label(SULFURIC)
    f = by_item(compare_label(d, msds_of(d, h_codes=[h for h in d["h_codes"] if h != "H350"])), "h_codes")[0]
    assert (f["verdict"], f["severity"], f["rule_id"], f["missing"]) == ("불일치", "중간", "CMP-1", ["H350"])


def test_근거_없는_h코드는_경고():
    d = derive_label(SULFURIC)
    f = by_item(compare_label(d, msds_of(d, h_codes=d["h_codes"] + ["H225"])), "h_codes")[0]
    assert (f["verdict"], f["severity"], f["rule_id"], f["extra"]) == ("경고", "낮음", "CMP-2", ["H225"])


def test_h314가_있으면_h318_생략은_참고():
    d = derive_label(SULFURIC)
    assert "H318" in d["h_codes"] and "H314" in d["h_codes"]
    f = by_item(compare_label(d, msds_of(d, h_codes=[h for h in d["h_codes"] if h != "H318"])), "h_codes")
    assert [(x["verdict"], x["rule_id"], x["missing"]) for x in f] == [("참고", "HS-1", ["H318"])]


def test_h318과_다른_코드가_함께_빠지면_다른_코드만_불일치():
    d = derive_label(SULFURIC)
    f = by_item(compare_label(d, msds_of(d, h_codes=[h for h in d["h_codes"] if h not in ("H318", "H350")])), "h_codes")
    assert [(x["verdict"], x["missing"]) for x in f] == [("참고", ["H318"]), ("불일치", ["H350"])]


def test_그림문자_5개_중_4개는_일치():
    derived = {"pictograms": ["GHS02", "GHS05", "GHS06", "GHS08", "GHS09"], "signal_word": "위험", "h_codes": []}
    ok = by_item(compare_label(derived, {"pictograms": ["GHS02", "GHS05", "GHS06", "GHS08"], "signal_word": "위험",
                                         "h_codes": ["H1"]}), "pictograms")[0]
    assert (ok["verdict"], ok["rule_id"]) == ("일치", "PIC-4")
    bad = by_item(compare_label(derived, {"pictograms": ["GHS02", "GHS05", "GHS06", "GHS07"], "signal_word": "위험",
                                          "h_codes": ["H1"]}), "pictograms")[0]
    assert (bad["verdict"], bad["rule_id"]) == ("불일치", "CMP-3")


def test_그림문자_다르면_불일치():
    d = derive_label(SULFURIC)
    f = by_item(compare_label(d, msds_of(d, pictograms=["GHS05", "GHS06"])), "pictograms")[0]
    assert (f["verdict"], f["missing"], f["extra"]) == ("불일치", ["GHS08"], [])


def test_신호어_불일치():
    d = derive_label(SULFURIC)
    f = by_item(compare_label(d, msds_of(d, signal_word="경고")), "signal_word")[0]
    assert (f["verdict"], f["severity"], f["rule_id"]) == ("불일치", "중간", "CMP-4")


def test_msds_값이_없으면_불일치_중간():  # 설계서 7장 "빠지거나 다름 중간". 추출 실패 항은 judge()가 근거부족으로 바꾼다
    d = derive_label(SULFURIC)
    r = compare_label(d, {"pictograms": [], "signal_word": None, "h_codes": None})
    assert {(f["verdict"], f["severity"]) for f in r} == {("불일치", "중간")} and len(r) == 3
    assert all(f["missing"] for f in r)


def test_양쪽_다_비면_일치():
    d = derive_label([])
    assert {f["verdict"] for f in compare_label(d, {})} == {"일치"}


def test_규칙_파일_형식():
    with open(RULES_DIR / "label_rules.yaml", encoding="utf-8") as f:
        assert f.readline().startswith("# version:")
    items = []

    def walk(o):
        if isinstance(o, dict):
            if "rule_id" in o:
                items.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(label_rules())
    ids = [i["rule_id"] for i in items]
    assert len(ids) == len(set(ids)) and {"PIC-1", "PIC-2", "PIC-3", "PIC-4", "SIG-1", "HS-1", "ACUTE-CAT5"} <= set(ids)
    assert all(str(i.get("source") or "").strip() for i in items)
    other = [r["rule_id"] for n in ("hazard_label_map", "acute_tox_ate", "units", "units_time", "params")
             for r in read_rules(RULES_DIR / f"{n}.csv")]
    assert not set(ids) & set(other)


def test_h314도_빠지면_h318은_참고가_아니라_불일치():
    d = derive_label(SULFURIC)
    f = by_item(compare_label(d, msds_of(d, h_codes=[h for h in d["h_codes"] if h not in ("H314", "H318")])), "h_codes")
    assert [(x["verdict"], sorted(x["missing"])) for x in f] == [("불일치", ["H314", "H318"])]


def test_도출은_h318이고_msds가_h314면_h318_누락은_참고다():
    d = derive_label(SULFURIC)
    d = {**d, "h_codes": [h for h in d["h_codes"] if h != "H314"]}
    m = msds_of(d, h_codes=[h for h in d["h_codes"] if h != "H318"] + ["H314"])
    f = by_item(compare_label(d, m), "h_codes")
    assert ("참고", ["H318"]) in [(x["verdict"], x["missing"]) for x in f]
