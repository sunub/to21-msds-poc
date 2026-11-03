"""15항 판정 시험 (설계서 7·27~30장, 11/01 F 결정 1~5, 11/02 결정 6~9).

앞쪽은 이 파일 안의 가짜 지식 제공자로, 뒤쪽은 샘플 CSV(로컬에 있을 때)로 25번 황산을 확인한다.
"""
import json
from pathlib import Path

import pytest

from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.htodb.regulation import RegulationProvider, regulation_rows
from msds.compliance.loader import load_inputs
from msds.compliance.sec15_judge import judge_sec15

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude" / "T21-025.json"
A, WATER = "1111-11-1", "7732-18-5"
RANGE = {"lower_op": ">=", "lower": 93, "upper_op": "<=", "upper": 98, "unit": "%"}


def db(item, law, value=None, op=">=", kind="compare", rid="KR000000000"):
    return {"law": law, "item_code": item, "kind": kind, "regulate_item_id": rid, "db_item_name": item, "group_name": None,
            "threshold_op": op if value is not None else None, "threshold_value": value,
            "threshold_unit": "%" if value is not None else None, "source": f"가짜 {item}", "rule_id": "RM-T", "note": ""}


class Fake:
    def __init__(self, table, version="test-1"):
        self.table, self.version = table, version

    def get_regulation(self, cas, as_of):
        if cas not in self.table:
            return {"cas_no": cas, "as_of": as_of, "knowledge_version": None, "rows": [], "reason": "지식DB에 등록되지 않은 CAS"}
        return {"cas_no": cas, "as_of": as_of, "knowledge_version": self.version, "rows": self.table[cas], "reason": None}


def sup(item, law, applicable, ref="1", threshold=None, value_raw=None):
    return {"comp_ref": ref, "law": law, "item_code": item, "applicable": applicable, "threshold": threshold,
            "value_raw": value_raw}


def pct(v):
    return {"raw": f"{v}% 이상", "value": None, "lower_op": ">=", "lower": v, "unit": "%"}


def inputs(regs, comps=None, physchem=None):
    comps = comps or [{"seq": 1, "cas_no": A, "content": RANGE}]
    return {"as_of_date": "2022-06-29", "components": comps, "regulations": regs, "physchem": physchem or {},
            "dangerous_goods": []}


# 15항을 읽었다는 표시. 법마다 본다: 그 법의 행이 하나도 없으면 누락 대신 근거부족이다
READ = [sup("OSH_PROHIBIT", "OSH", "비해당"), sup("CCA_PROHIBIT", "CCA", "비해당")]


def one(out, item, ref="1"):
    return next(v for v in out["verdicts"] if v["item_code"] == item and v["comp_ref"] == ref)


def ex(out, item, ref="1"):
    return next(e for e in out["excluded"] if e["item_code"] == item and e["comp_ref"] == ref)


# ── 판정 유형·심각도 (설계서 7·27·30장) ──────────────────────────────
def test_함량상_해당인데_MSDS_비해당이면_규제누락_높음():
    v = one(judge_sec15(inputs([sup("OSH_MEASURE", "OSH", "비해당")]), Fake({A: [db("OSH_MEASURE", "OSH", 1)]})), "OSH_MEASURE")
    assert (v["verdict"], v["type"], v["severity"], v["sv_id"]) == ("불일치", "규제 누락", "높음", "SV-02")


def test_MSDS가_행을_빠뜨려도_규제누락():
    v = one(judge_sec15(inputs(READ), Fake({A: [db("CCA_ACCIDENT", "CCA", 10)]})), "CCA_ACCIDENT")
    assert (v["type"], v["msds_value"]) == ("규제 누락", None)


def test_둘다_해당인데_기준농도가_다르면_기준불일치_중간():
    out = judge_sec15(inputs([sup("OSH_MANAGED", "OSH", "해당", threshold=pct(1))]), Fake({A: [db("OSH_MANAGED", "OSH", 0.1)]}))
    v = one(out, "OSH_MANAGED")
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "기준 불일치", "중간")
    assert v["msds_threshold"] == ">= 1%" and v["db_threshold"] == ">= 0.1%"


def test_기준농도가_같거나_MSDS가_기준을_안적으면_일치():
    p = Fake({A: [db("OSH_MEASURE", "OSH", 1)]})
    assert one(judge_sec15(inputs([sup("OSH_MEASURE", "OSH", "해당", threshold=pct(1))]), p), "OSH_MEASURE")["verdict"] == "일치"
    assert one(judge_sec15(inputs([sup("OSH_MEASURE", "OSH", "해당")]), p), "OSH_MEASURE")["verdict"] == "일치"


def test_DB가_다루는_항목인데_행이_없고_MSDS_해당이면_과기재_낮음():
    v = one(judge_sec15(inputs([sup("CCA_ACCIDENT", "CCA", "해당")]), Fake({A: []})), "CCA_ACCIDENT")
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "과기재", "낮음")


def test_DB가_다루지_않는_항목은_해당이면_근거부족_비해당이면_일치():
    out = judge_sec15(inputs([sup("POPS", "POPS", "해당"), sup("CCA_PERMIT", "CCA", "비해당")]), Fake({A: []}))
    assert one(out, "POPS")["verdict"] == "근거부족" and one(out, "CCA_PERMIT")["verdict"] == "일치"


def test_함량범위가_기준에_걸치면_경계():
    comps = [{"seq": 1, "cas_no": A, "content": {"lower_op": ">=", "lower": 8, "upper_op": "<=", "upper": 12, "unit": "%"}}]
    v = one(judge_sec15(inputs([sup("CCA_TOXIC", "CCA", "해당")], comps), Fake({A: [db("CCA_TOXIC", "CCA", 10)]})), "CCA_TOXIC")
    assert v["verdict"] == "경계" and v["type"] is None  # 설계서 26장 예: 8~12%, 기준 10% → 경계
    assert v["causes"][0]["text"] == ("함량 범위 8~12% 중 하한 8%는 기준(>= 10%)에 못 미치고 상한 12%는 기준을 충족해, "
                                      "실제 함량에 따라 해당 여부가 갈리는 경계")  # 설명 4·6차: 원인 문장은 읽는 말, reason은 그대로
    assert v["reason"] == "함량 8~12% 가 기준 >= 10% 에 걸침"
    comps = [{"seq": 1, "cas_no": A, "content": {"upper_op": "<=", "upper": 25, "unit": "%"}}]       # 하한 없음 → 0
    v = one(judge_sec15(inputs([sup("CCA_TOXIC", "CCA", "해당")], comps), Fake({A: [db("CCA_TOXIC", "CCA", 1)]})), "CCA_TOXIC")
    assert "하한 0%는 기준(>= 1%)에 못 미치고 상한 25%" in v["causes"][0]["text"]


def test_규제누락_원인_문장은_MSDS에_행이_없는지_비해당인지_구분한다():
    p = Fake({A: [db("OSH_MEASURE", "OSH", 1)]})
    no_row = one(judge_sec15(inputs(READ), p), "OSH_MEASURE")["causes"][0]["text"]
    said = one(judge_sec15(inputs([sup("OSH_MEASURE", "OSH", "비해당")]), p), "OSH_MEASURE")["causes"][0]["text"]
    assert no_row.startswith("함량상 해당인데 MSDS 15항에 이 규제 항목이 없음(성분은 3항에 있음)")
    assert said.startswith("함량상 해당인데 MSDS 기재는 비해당")


def test_지식DB에_없는_CAS는_근거부족():
    v = one(judge_sec15(inputs([sup("OSH_MEASURE", "OSH", "해당")]), Fake({})), "OSH_MEASURE")
    assert v["verdict"] == "근거부족" and "등록되지 않은" in v["reason"]


# ── 11/01 F 결정 1~5 ─────────────────────────────────────────────
def test_결정1_화관법_세분항목은_MSDS가_옛체계면_구버전_참고():
    p = Fake({A: [db("CCA_TOXIC", "CCA", 10), db("CCA_ACUTE", "CCA", 10, kind="new_cca")]})
    out = judge_sec15(inputs([sup("CCA_TOXIC", "CCA", "해당")]), p)
    assert ex(out, "CCA_ACUTE")["status"] == "구버전" and one(out, "CCA_TOXIC")["verdict"] == "일치"
    out = judge_sec15(inputs([sup("CCA_TOXIC", "CCA", "해당"), sup("CCA_ECO", "CCA", "비해당")]), p)  # MSDS가 새 체계를 씀
    assert one(out, "CCA_ACUTE")["type"] == "규제 누락"


def test_결정2_물의_화관법_유해성_연결은_참고():
    comps = [{"seq": 2, "cas_no": WATER, "content": {"lower": 2, "upper": 7, "lower_op": ">=", "upper_op": "<=", "unit": "%"}}]
    out = judge_sec15(inputs([], comps), Fake({WATER: [db("CCA_CHRONIC", "CCA", 1, op=">", kind="new_cca")]}))
    e = ex(out, "CCA_CHRONIC", "2")
    assert e["status"] == "참고" and "확인 필요" in e["reason"]
    assert not [v for v in out["verdicts"] if v["item_code"] == "CCA_CHRONIC"]


def test_결정3_지위정보는_MSDS가_적었을_때만_비교():
    p = Fake({A: [db("KREACH_EXIST", "KREACH", kind="status_only")]})
    assert ex(judge_sec15(inputs([]), p), "KREACH_EXIST")["status"] == "참고"
    assert one(judge_sec15(inputs([sup("KREACH_EXIST", "KREACH", "해당")]), p), "KREACH_EXIST")["verdict"] == "일치"


def test_결정4_칸은_비었지만_값이_있으면_해당으로_본다():
    out = judge_sec15(inputs([sup("KREACH_REG", "KREACH", None, value_raw="321")]), Fake({A: [db("KREACH_REG", "KREACH")]}))
    v = one(out, "KREACH_REG")
    assert v["verdict"] == "일치" and v["msds_value"] == "해당" and any("결정 4" in a for a in v["assumptions"])


def test_결정5_폐기물은_참고_위험물은_9항_인화점으로():
    liquid = {"APPEARANCE_STATE": [{"comp_ref": "MIX", "text_value": "액체"}]}
    fp = lambda v: {**liquid, "FLASH_POINT": [{"comp_ref": "MIX", "q": {"value": v, "status": "값있음"}}]}
    regs = [sup("WASTE_DESIG", "WASTE", "비해당", ref="MIX"), sup("DG_HAZMAT", "DG", "비해당", ref="MIX")]
    out = judge_sec15(inputs(regs, physchem=fp(12)), Fake({A: []}))
    assert ex(out, "WASTE_DESIG", "MIX")["status"] == "참고"
    dg = one(out, "DG_HAZMAT", "MIX")
    assert (dg["verdict"], dg["type"], dg["db_threshold"]) == ("불일치", "규제 누락", "제1석유류")
    assert one(judge_sec15(inputs(regs, physchem=fp(50)), Fake({A: []})), "DG_HAZMAT", "MIX")["verdict"] == "경계"  # 제2석유류 예외
    unflam = {**liquid, "FLASH_POINT": [{"comp_ref": "MIX", "q": {"value": None, "status": "해당없음"}}]}
    assert one(judge_sec15(inputs(regs, physchem=unflam), Fake({A: []})), "DG_HAZMAT", "MIX")["verdict"] == "일치"


def test_같은_입력이면_같은_결과():
    args = (inputs([sup("OSH_MEASURE", "OSH", "비해당")]), Fake({A: [db("OSH_MEASURE", "OSH", 1)]}))
    assert judge_sec15(*args) == judge_sec15(*args)


# ── 지식 제공자: DB 행 해석 ────────────────────────────────────────
def test_DB_부호·단위·PSM_물질군_기준을_읽는다():
    data = {"rows": [{"regulate_item_id": i, "is_del": "0"} for i in ("KR001001005", "KR001001009", "KR002009006", "KR001001011")],
            "notice_std": [
                {"regulate_item_id": "KR001001005", "std_value_primary": "1.000", "std_value_primary_unit": "vol%",
                 "std_value_primary_sign": "＞", "is_del": "0"},
                {"regulate_item_id": "KR001001009", "std_value_primary": "20000.000", "std_value_primary_unit": "kg/일",
                 "chem_group_name": "황산(중량 20% 이상)", "research_range": "20", "is_del": "0"},
                {"regulate_item_id": "KR002009006", "research_range_std": "1.000", "research_range_unit": "wt%",
                 "research_range_sign": "≥", "is_del": "0"}]}
    by = {r["item_code"]: r for r in regulation_rows(data)}
    assert set(by) == {"OSH_MEASURE", "OSH_PSM", "CCA_PRTR"}  # 국소배기(참고)는 빠짐
    assert (by["OSH_MEASURE"]["threshold_op"], by["OSH_MEASURE"]["threshold_value"]) == (">", 1.0)
    assert "vol%" in by["OSH_MEASURE"]["note"]
    assert (by["OSH_PSM"]["threshold_op"], by["OSH_PSM"]["threshold_value"]) == (">=", 20.0)
    assert (by["CCA_PRTR"]["threshold_op"], by["CCA_PRTR"]["threshold_value"]) == (">=", 1.0)


# ── 25번 황산 (샘플 CSV) ────────────────────────────────────────────
@pytest.mark.skipif(not (CsvRepo().available() and SILVER.exists()), reason="to21_sample 또는 T21-025.json 없음")
def test_25번_황산_15항():
    out = judge_sec15(load_inputs(json.loads(SILVER.read_text(encoding="utf-8"))), RegulationProvider(CsvRepo()))
    mism = {(v["comp_ref"], v["item_code"]): v["type"] for v in out["verdicts"] if v["verdict"] == "불일치"}
    assert mism == {("1", "OSH_MANAGED"): "기준 불일치"}  # 특별관리물질은 관리대상 행 비고에 적혀 있다
    for item in ("OSH_MEASURE", "OSH_HEALTH_EXAM", "OSH_PSM", "OSH_PERMISSIBLE", "CCA_TOXIC", "CCA_ACCIDENT", "CCA_PRTR"):
        assert one(out, item)["verdict"] == "일치", item  # 설계서 39장의 일치 줄
    assert one(out, "DG_HAZMAT", "MIX")["verdict"] == "일치"  # 인화점 해당없음 → 위험물 비해당
    assert ex(out, "CCA_ACUTE")["status"] == "구버전"
    assert {e["item_code"] for e in out["excluded"] if e["comp_ref"] == "2"} >= {"CCA_CHRONIC", "CCA_ECO"}


# ── 11/02 F 결정 6~8 ───────────────────────────────────────────────
def test_결정6_금지물질은_함량상_해당이어도_MSDS_비해당이면_경계():
    p = Fake({A: [db("OSH_PROHIBIT", "OSH", 5, op=">", kind="compare_human")]})
    v = one(judge_sec15(inputs([sup("OSH_PROHIBIT", "OSH", "비해당")]), p), "OSH_PROHIBIT")
    assert (v["verdict"], v["type"], v["severity"]) == ("경계", None, None)
    assert "고무풀" in v["reason"] and "결정 6" in v["reason"]
    c = v["causes"][0]
    assert c["code"] == "CONDITION_CHECK" and "고무풀" not in c["text"] and "사람 확인" in c["text"]  # 설명 4차
    both = one(judge_sec15(inputs([sup("OSH_PROHIBIT", "OSH", "해당")]), p), "OSH_PROHIBIT")
    assert both["verdict"] == "일치"  # MSDS도 해당이면 그대로 비교


def test_결정7_단일물질은_제품전체_행을_성분_행으로_본다():
    single = lambda regs: {**inputs(regs), "composition": {"type": "단일물질"}}
    p = Fake({A: [db("OSH_PSM", "OSH", 1)]})
    out = judge_sec15(single([sup("OSH_PSM", "OSH", "해당", ref="MIX")]), p)
    v = one(out, "OSH_PSM")
    assert v["verdict"] == "일치" and any("결정 7" in a for a in v["assumptions"])
    assert not [e for e in out["excluded"] if e["item_code"] == "OSH_PSM"]
    mixed = judge_sec15(inputs([sup("OSH_PSM", "OSH", "해당", ref="MIX")]), p)  # 표기 없음 → 결정 7이 아니라 결정 9
    assert ex(mixed, "OSH_PSM", ref="MIX")["status"] == "참고"
    assert any("결정 9" in a for a in one(mixed, "OSH_PSM")["assumptions"])
    # 성분 번호로 적은 위험물 행은 제품 행으로 본다
    dg = judge_sec15(single([sup("DG_HAZMAT", "DG", "비해당", ref="1")]), Fake({A: []}))
    assert one(dg, "DG_HAZMAT", ref="MIX")["msds_value"] == "비해당"


def test_결정8_법_단위_비해당은_항목별_판정에_이어쓴다():
    p = Fake({A: [db("OSH_MANAGED", "OSH", 1)]})
    blanket = {**sup(None, "OSH", "비해당"), "item_raw": "산업안전보건법에 의한 규제"}
    out = judge_sec15(inputs([blanket]), p)
    v = one(out, "OSH_MANAGED")
    assert (v["verdict"], v["type"], v["msds_value"]) == ("불일치", "규제 누락", "비해당")
    assert any("법 단위" in a for a in v["assumptions"])
    e = ex(out, None)
    assert e["status"] == "참고" and "이어 씀" in e["reason"]
    assert not [r for r in out["verdicts"] if r["item_code"] is None]  # 항목 없는 줄은 판정하지 않음
    # 항목별 행이 있으면 그 행이 우선
    own = judge_sec15(inputs([blanket, sup("OSH_MANAGED", "OSH", "해당", threshold=pct(1))]), p)
    assert one(own, "OSH_MANAGED")["verdict"] == "일치"


def test_결정8_법_단위_해당은_항목을_특정할_수_없어_비교하지_않는다():
    p = Fake({A: [db("OSH_MANAGED", "OSH", 1)]})
    out = judge_sec15(inputs([{**sup(None, "OSH", "해당"), "item_raw": "영업비밀인정제외물질"}]), p)
    assert "특정할 수 없어" in ex(out, None)["reason"]
    assert one(out, "OSH_MANAGED")["msds_value"] is None  # '해당'은 이어 쓰지 않는다(과기재 오탐 방지)


B = "2222-22-2"
TWO = [{"seq": 1, "cas_no": A, "content": RANGE}, {"seq": 2, "cas_no": B, "content": {"lower": 0.1, "upper": 0.5, "unit": "%"}}]


def test_결정9_혼합물의_제품전체_행은_성분_판정에_이어쓴다():
    p = Fake({A: [db("OSH_MANAGED", "OSH", 1)], B: [db("OSH_MANAGED", "OSH", 1)]})
    out = judge_sec15(inputs([sup("OSH_MANAGED", "OSH", "해당", ref="MIX", threshold=pct(1))], TWO), p)
    a = one(out, "OSH_MANAGED", ref="1")
    assert (a["verdict"], a["msds_value"]) == ("일치", "해당") and any("결정 9" in x for x in a["assumptions"])
    b = one(out, "OSH_MANAGED", ref="2")  # 0.1~0.5% < 1% → 비해당. 제품 '해당'은 성분 1 때문 → 과기재로 세지 않음
    assert b["verdict"] == "일치" and "다른 성분" in b["reason"]
    assert "이어 씀" in ex(out, "OSH_MANAGED", ref="MIX")["reason"]
    # 제품 전체 '비해당'이면 해당 성분은 규제 누락
    neg = judge_sec15(inputs([sup("OSH_MANAGED", "OSH", "비해당", ref="MIX")], TWO), p)
    assert one(neg, "OSH_MANAGED", ref="1")["type"] == "규제 누락"


def test_결정9_성분별_행이_있으면_그_행이_우선이고_지위정보도_비교한다():
    p = Fake({A: [db("OSH_MANAGED", "OSH", 1), db("KREACH_EXIST", "KREACH", kind="status_only")]})
    out = judge_sec15(inputs([sup("OSH_MANAGED", "OSH", "해당", ref="MIX"), sup("OSH_MANAGED", "OSH", "비해당", ref="1"),
                              sup("KREACH_EXIST", "KREACH", "해당", ref="MIX")]), p)
    assert one(out, "OSH_MANAGED")["msds_value"] == "비해당"          # 성분 행 우선
    assert one(out, "KREACH_EXIST")["verdict"] == "일치"              # 제품 전체로 적었으면 결정 3의 '적었을 때'에 해당


def test_결정9_DB에_걸리는_성분이_없는_제품전체_해당은_참고로_확인필요():
    out = judge_sec15(inputs([sup("OSH_PSM", "OSH", "해당", ref="MIX")]), Fake({A: []}))
    assert "확인 필요" in ex(out, "OSH_PSM", ref="MIX")["reason"]


def test_혼합물의_제품전체_법단위_비해당도_모든_성분에_이어쓴다():
    p = Fake({A: [db("OSH_MANAGED", "OSH", 1)]})
    out = judge_sec15(inputs([{**sup(None, "OSH", "비해당", ref="MIX"), "item_raw": "산업안전보건법에 의한 규정"}]), p)
    v = one(out, "OSH_MANAGED")
    assert v["msds_value"] == "비해당" and any("법 단위" in a for a in v["assumptions"])


def test_액화가스는_위험물_제4류가_아니다():
    phys = {"APPEARANCE_STATE": [{"text_value": "액체가스"}, {"text_value": "기체"}],
            "FLASH_POINT": [{"comp_ref": "MIX", "q": {"value": -76}}]}
    v = one(judge_sec15(inputs([sup("DG_HAZMAT", "DG", "비해당", ref="MIX")], physchem=phys), Fake({A: []})),
            "DG_HAZMAT", ref="MIX")
    assert v["verdict"] == "일치" and v["expected"] == "비해당" and "가스" in v["reason"]


# ── 11/02 F 결정 10·11 (실제 HTODB로 silver 전체를 돌려 찾은 오탐) ─────────────
def test_PSM_조문과_범주를_읽는다():
    data = {"rows": [{"regulate_id": "KR001001", "regulate_item_id": "KR001001009", "is_del": "0"}],
            "notice_std": [{"regulate_item_id": "KR001001009", "notice_seq": "3", "chem_group_name": "수소",
                            "research_range": "100", "is_del": "0"}],
            "notice_content": [{"regulate_item_id": "KR001001009", "notice_seq": "3", "lang_code": "ko", "is_del": "0",
                                "apply_basis": "수소 중량 %: 0~100 제조ㆍ취급ㆍ저장(kg/일): 5000"}]}
    psm = regulation_rows(data)[0]  # RESEARCH_RANGE 100 을 '100% 이상'으로 읽던 것 → 조문 '0~' = 함유하면 해당
    assert (psm["threshold_op"], psm["threshold_value"], psm["kind"]) == (">", 0.0, "compare")
    assert psm["db_text"] == ["수소 중량 %: 0~100 제조ㆍ취급ㆍ저장(kg/일): 5000"]
    data["notice_std"][0].update(chem_group_name="인화성 액체", research_range="")
    data["notice_content"][0]["apply_basis"] = "인화성 액체 제조ㆍ취급(kg/일): 5000 저장(kg/일): 200000"
    assert regulation_rows(data)[0]["kind"] == "psm_category"


def test_결정10_인화성_범주의_PSM은_판정하지_않는다():
    p = Fake({A: [db("OSH_PSM", "OSH", kind="psm_category")]})
    out = judge_sec15(inputs([]), p)
    assert not [v for v in out["verdicts"] if v["item_code"] == "OSH_PSM"]
    assert "결정 10" in ex(out, "OSH_PSM")["reason"]


def test_조문_조건을_읽는다():
    data = {"rows": [{"regulate_id": "KR001001", "regulate_item_id": "KR001001007", "is_del": "0"},
                     {"regulate_id": "KR001001", "regulate_item_id": "KR001001005", "is_del": "0"}],
            "notice_std": [{"regulate_item_id": "KR001001007", "notice_seq": "5", "std_value_primary": "0.100",
                            "std_value_primary_unit": "wt%", "std_value_primary_sign": "≥", "is_del": "0"}],
            "notice_content": [{"regulate_item_id": "KR001001007", "notice_seq": "5", "is_del": "0",
                                "apply_basis": "및 이를 0.1 wt% 이상 함유한 제제(≤ pH 2.0)"},
                               {"regulate_item_id": "KR001001005", "notice_seq": "4", "is_del": "0",
                                "notice_contents": "유리섬유", "chem_state": "분진인 경우에 한함"}]}
    by = {r["item_code"]: r for r in regulation_rows(data)}
    assert by["OSH_SPECIAL"]["condition"] == {"state": None, "ph_max": 2.0}
    assert by["OSH_MEASURE"]["condition"] == {"state": "분진인 경우에 한함", "ph_max": None}


def _cond(item, value, **c):
    return {**db(item, "OSH", value), "condition": {"state": None, "ph_max": None, **c}}


def test_결정11_pH_조건은_9항_pH로_확인한다():
    p = Fake({A: [_cond("OSH_SPECIAL", 0.1, ph_max=2.0)]})
    ph = lambda v: {"PH": [{"comp_ref": "MIX", "q": {"value": v}}]}
    met = one(judge_sec15(inputs(READ, physchem=ph(0.3)), p), "OSH_SPECIAL")
    assert met["type"] == "규제 누락" and any("pH 0.3" in a for a in met["assumptions"])
    over = one(judge_sec15(inputs(READ, physchem=ph(5.0)), p), "OSH_SPECIAL")
    assert (over["verdict"], over["expected"]) == ("일치", "비해당")
    none = one(judge_sec15(inputs(READ), p), "OSH_SPECIAL")
    assert none["verdict"] == "경계" and "pH" in none["reason"]


def test_결정11_성상_조건이_있으면_경계():
    p = Fake({A: [_cond("OSH_MEASURE", 0.0, state="분진인 경우에 한함")]})
    v = one(judge_sec15(inputs([sup("OSH_MEASURE", "OSH", "비해당")]), p), "OSH_MEASURE")
    assert v["verdict"] == "경계" and "분진" in v["reason"]


# ── 2026-11-03 실버 대조에서 나온 거짓 규제 누락 ──────────────────────
def test_지위_정보는_MSDS가_비해당이라_적어도_규제_누락이_아니다():
    # T21-050: 물의 '면제' 지위와 MSDS의 '신규물질: 해당 없음'이 같은 칸에 묶여 높음으로 나왔다
    table = {A: [db("KREACH_ETC", "KREACH", kind="status_only")]}
    out = judge_sec15(inputs([sup("KREACH_ETC", "KREACH", "비해당"), sup("OSH_MANAGED", "OSH", "비해당")]), Fake(table))
    assert not [v for v in out["verdicts"] if v["item_code"] == "KREACH_ETC"]
    assert ex(out, "KREACH_ETC")["status"] == "참고"


def test_15항을_한_행도_못_읽으면_누락이_아니라_근거부족이다():
    # T21-S013: 15항 표가 그림이라 추출에 행이 없다. 누락인지 추출 실패인지 가릴 수 없다
    table = {A: [db("OSH_MANAGED", "OSH", 1.0), db("위험물", "DG", kind="dg", rid="KR004001")]}
    out = judge_sec15(inputs([]), Fake(table))
    assert (one(out, "OSH_MANAGED")["verdict"], one(out, "OSH_MANAGED")["type"]) == ("근거부족", None)
    assert one(out, "DG_HAZMAT", "MIX")["verdict"] == "근거부족"


def test_관리대상_행의_비고에_특별관리물질이_있으면_해당으로_본다():
    # T21-025: '해당됨 (1% 이상 함유한 황산(특별관리물질))'
    table = {A: [db("OSH_SPECIAL", "OSH", 0.1)]}
    row = {**sup("OSH_MANAGED", "OSH", "해당"), "remark": "특별관리물질"}
    assert one(judge_sec15(inputs([row]), Fake(table)), "OSH_SPECIAL")["verdict"] == "일치"
    plain = sup("OSH_MANAGED", "OSH", "해당")
    assert one(judge_sec15(inputs([plain]), Fake(table)), "OSH_SPECIAL")["type"] == "규제 누락"


# ── 화평법 항목 누락 (설계서 30장, 고시 별표 4 제15호 다목·부칙 제2조·제3조) ─────────────
def _dated(regs, date):
    return {**inputs(regs), "revision_date": date}


def test_시행일_이후_작성분에_화평법_행이_없으면_항목_누락_중간():
    out = judge_sec15(_dated(READ, "2025-08-07"), Fake({A: []}))
    v = one(out, "KREACH_SECTION", "MIX")
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "화평법 항목 누락", "중간")


@pytest.mark.parametrize("regs,date", [(READ, "2025-08-06"), (READ, None), ([], "2026-01-01"),
                                        (READ + [sup("KREACH_REG", "KREACH", "비해당")], "2026-01-01"),
                                        (READ + [{"comp_ref": "MIX", "law": "KREACH", "item_code": None, "applicable": "비해당"}], "2026-01-01")])
def test_화평법_항목_누락을_내지_않는_경우(regs, date):
    out = judge_sec15(_dated(regs, date), Fake({A: []}))
    assert not [v for v in out["verdicts"] if v["item_code"] == "KREACH_SECTION"]


def test_불순물_ppm_함량도_15항_기준과_비교한다():
    table = {A: [db("OSH_MANAGED", "OSH", 0.1)]}
    comp = lambda v: [{"seq": 1, "cas_no": A, "content": {"value": v, "unit": "ppm"}, "content_note": "불순물"}]
    assert one(judge_sec15(inputs([sup("OSH_MANAGED", "OSH", "비해당")], comps=comp(500)), Fake(table)), "OSH_MANAGED")["verdict"] == "일치"
    assert one(judge_sec15(inputs([sup("OSH_MANAGED", "OSH", "비해당")], comps=comp(2000)), Fake(table)), "OSH_MANAGED")["type"] == "규제 누락"


# ── 2026-11-03 재현 기반 검토에서 나온 입력 ──────────────────────────
NOT_STATED = {"comp_ref": "MIX", "law": "KREACH", "item_code": None, "applicable": "미기재"}


def test_추출기가_넣은_미기재_행은_화평법_기재로_보지_않는다():
    v = one(judge_sec15(_dated(READ + [NOT_STATED], "2026-01-01"), Fake({A: []})), "KREACH_SECTION", "MIX")
    assert v["type"] == "화평법 항목 누락"


def test_미기재_행만_있으면_15항을_읽지_못한_것이다():
    table = {A: [db("OSH_MANAGED", "OSH", 1.0)]}
    out = judge_sec15(_dated([NOT_STATED], "2026-01-01"), Fake(table))
    assert one(out, "OSH_MANAGED")["verdict"] == "근거부족"
    assert not [v for v in out["verdicts"] if v["item_code"] == "KREACH_SECTION"]


def test_기타_법규_칸에_적은_화평법도_기재로_본다():
    row = {"comp_ref": "MIX", "law": "KR_ETC", "item_code": None, "applicable": "해당", "item_raw": "화학물질의 등록 및 평가 등에 관한 법률"}
    out = judge_sec15(_dated(READ + [row], "2026-01-01"), Fake({A: []}))
    assert not [v for v in out["verdicts"] if v["item_code"] == "KREACH_SECTION"]


def test_시행일_전_문서의_화평법_행_없음은_규제_누락이_아니라_구버전이다():
    table = {A: [db("KREACH_CMR", "KREACH")]}
    out = judge_sec15(_dated(READ, "2025-05-08"), Fake(table))
    assert not [v for v in out["verdicts"] if v["item_code"] == "KREACH_CMR"]
    assert ex(out, "KREACH_CMR")["status"] == "구버전"
    after = judge_sec15(_dated(READ, "2026-01-01"), Fake(table))  # 화평법을 통째로 안 적음: 항목 누락 한 줄, 성분 줄은 판단 못 함
    assert one(after, "KREACH_CMR")["verdict"] == "근거부족" and one(after, "KREACH_SECTION", "MIX")["type"] == "화평법 항목 누락"
    # 시행일 전 문서가 다른 화평법 행을 적었어도, 적지 않은 항목은 구버전이다 (T21-050). 적은 항목은 비교한다
    stated = judge_sec15(_dated(READ + [sup("KREACH_REG", "KREACH", "비해당")], "2025-05-08"), Fake(table))
    assert ex(stated, "KREACH_CMR")["status"] == "구버전"
    wrote = judge_sec15(_dated(READ + [sup("KREACH_CMR", "KREACH", "비해당")], "2025-05-08"), Fake(table))
    assert one(wrote, "KREACH_CMR")["type"] == "규제 누락"


@pytest.mark.parametrize("raw,want", [("2025.08.07", "2025-08-07"), ("2025-8-7", "2025-08-07"), ("2025년 8월 7일", "2025-08-07"),
                                      ("2025. 8. 7.", "2025-08-07"), ("20250101", "2025-01-01"), ("24.01.01", "2024-01-01"),
                                      ("2025-08", "2025-08-01"), ("자료없음", None), ("", None), (None, None), ("2025-13-01", None)])
def test_날짜_표기를_맞춘다(raw, want):
    from msds.compliance.loader import _ymd

    assert _ymd(raw) == want


def test_개정일이_자료없음이면_최초_작성일로_본다():
    doc = {"msds": [{"meta": {"last_revision_date": "자료없음", "first_issue_date": "2010-06-21"}}]}
    assert load_inputs(doc, 0)["revision_date"] == "2010-06-21"


def test_특별관리물질_아님_비고는_해당이_아니다():
    table = {A: [db("OSH_SPECIAL", "OSH", 0.1)]}
    row = {**sup("OSH_MANAGED", "OSH", "해당"), "remark": "특별관리물질 아님"}
    assert one(judge_sec15(inputs([row]), Fake(table)), "OSH_SPECIAL")["type"] == "규제 누락"


def test_ppm_경계_문장은_퍼센트로_적는다():
    table = {A: [db("OSH_MANAGED", "OSH", 0.1)]}
    comp = [{"seq": 1, "cas_no": A, "content": {"lower": 500, "upper": 2000, "unit": "ppm"}}]
    v = one(judge_sec15(inputs([sup("OSH_MANAGED", "OSH", "비해당")], comps=comp), Fake(table)), "OSH_MANAGED")
    assert v["verdict"] == "경계" and "0.05~0.2%" in v["causes"][0]["text"]


def test_해외_행만_있으면_국내_법은_읽지_못한_것이다():
    table = {A: [db("OSH_MANAGED", "OSH", 1.0)]}
    intl = {"comp_ref": "MIX", "law": "INTL", "item_code": None, "applicable": "해당"}
    assert one(judge_sec15(inputs([intl]), Fake(table)), "OSH_MANAGED")["verdict"] == "근거부족"


def test_못_읽은_15항은_금지물질도_읽지_못했다고_적는다():
    table = {A: [db("OSH_PROHIBIT", "OSH", 1.0, kind="compare_human")]}
    v = one(judge_sec15(inputs([]), Fake(table)), "OSH_PROHIBIT")
    assert v["verdict"] == "근거부족" and "읽은 규제 행이 없어" in v["reason"]


def test_기타_칸에_화평법을_적었으면_성분별_규제_누락이_아니다():
    table = {A: [db("KREACH_REG", "KREACH")]}
    row = {"comp_ref": "MIX", "law": "KR_ETC", "item_code": None, "applicable": "해당",
           "value_raw": "화학물질의 등록 및 평가 등에 관한 법률: 등록대상기존화학물질"}
    new = judge_sec15(_dated(READ + [row], "2026-01-10"), Fake(table))
    assert not [v for v in new["verdicts"] if v["item_code"] == "KREACH_REG"] and ex(new, "KREACH_REG")["status"] == "참고"
    old = judge_sec15(_dated(READ + [row], "2024-01-01"), Fake(table))
    assert ex(old, "KREACH_REG")["status"] == "구버전"


def test_법마다_읽었는지_본다():
    # T21-M001 런: 화관법 행 하나만 읽힌 추출본에서 산안법 항목이 규제 누락으로 나왔다
    table = {A: [db("OSH_MANAGED", "OSH", 1.0), db("CCA_ACCIDENT", "CCA", 10)]}
    out = judge_sec15(inputs([sup("CCA_PRTR", "CCA", "비해당")]), Fake(table))
    assert one(out, "OSH_MANAGED")["verdict"] == "근거부족"
    assert one(out, "CCA_ACCIDENT")["type"] == "규제 누락"


@pytest.mark.parametrize("note", ["특별관리물질 미해당", "특별관리물질 없음", "특별관리물질 비대상", "특별관리물질: X"])
def test_특별관리물질_부정_표기(note):
    table = {A: [db("OSH_SPECIAL", "OSH", 0.1)]}
    row = {**sup("OSH_MANAGED", "OSH", "해당"), "remark": note}
    assert one(judge_sec15(inputs([row]), Fake(table)), "OSH_SPECIAL")["type"] == "규제 누락"


def test_가운뎃점_화평법_이름도_찾는다():
    row = {"comp_ref": "MIX", "law": "KR_ETC", "item_code": None, "applicable": "해당", "item_raw": "화학물질의 등록·평가 등에 관한 법률"}
    out = judge_sec15(_dated(READ + [row], "2026-01-01"), Fake({A: []}))
    assert not [v for v in out["verdicts"] if v["item_code"] == "KREACH_SECTION"]


@pytest.mark.parametrize("raw", ["08/07/2025", "07-08-2025"])
def test_일월_순서를_모르는_날짜는_읽지_않는다(raw):
    from msds.compliance.loader import _ymd

    assert _ymd(raw) is None
    assert _ymd("99-12-31") == "1999-12-31"
