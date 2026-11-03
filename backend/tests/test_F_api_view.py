"""정합성 결과 → 화면 계약(API-12 판정 목록, API-13 상세) 변환 시험 (11/03 F).

화면 계약은 E의 e/frontend-review `frontend/src/api/findings-schemas.ts`(zod)다. 아래 check_* 는 그 스키마를 파이썬으로 옮긴 것이다.
계약이 바뀌면 이 파일의 칸 목록부터 고친다.
앞쪽은 가짜 입력만 쓰고, 뒤쪽 25번·silver 시험은 샘플 CSV·silver 추출본이 있을 때만 돈다(D-47).
"""
import json
import re
from pathlib import Path

import pytest

from msds.compliance.api_view import api_view, finding_detail, findings_response, readable_formula
from msds.compliance.consistency import run_consistency
from msds.compliance.explain import explain_consistency
from msds.compliance.htodb.csv_repo import CsvRepo

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude"

# ── 화면 스키마(findings-schemas.ts) ──────────────────────────────────
VERDICTS = {"match", "mismatch", "borderline", "insufficient_evidence", "warning", "outdated", "not_applicable", "excluded"}
SUMMARY_KEYS = {"finding_id", "validation_id", "msds_id", "section", "item", "law", "component_id", "msds_value",
                "expected_value", "method", "verdict", "severity", "review_state", "opinion_count", "trace_id", "source_refs"}
DETAIL_KEYS = {"finding", "explanation", "trace", "evidence", "review", "law_effective_date", "msds_revision_date", "reference_date"}
LIST_KEYS = {"validation_id", "extraction_id", "review_revision", "items", "page", "page_size", "total", "counts",
             "excluded_counts", "groups"}
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_ref(r):
    assert set(r) == {"page_no", "bbox", "input_path"} and isinstance(r["page_no"], int) and r["page_no"] > 0
    assert r["bbox"] is None and isinstance(r["input_path"], str)


def check_summary(s):
    assert set(s) == SUMMARY_KEYS, set(s) ^ SUMMARY_KEYS
    for k in ("finding_id", "validation_id", "msds_id", "item", "method", "trace_id"):
        assert isinstance(s[k], str) and s[k], k
    assert s["section"] in (2, 15) and s["verdict"] in VERDICTS
    assert s["severity"] in (None, "high", "medium", "low") and s["review_state"] == "unreviewed" and s["opinion_count"] == 0
    assert s["law"] is None or isinstance(s["law"], str)
    assert s["component_id"] is None or isinstance(s["component_id"], str)
    for k in ("msds_value", "expected_value"):
        assert set(s[k]) == {"text"} and isinstance(s[k]["text"], str)
    for r in s["source_refs"]:
        check_ref(r)


def check_detail(d):
    assert set(d) == DETAIL_KEYS
    check_summary(d["finding"])
    e = d["explanation"]
    assert set(e) == {"text", "source", "check_status", "limitations"} and isinstance(e["text"], str)
    assert e["source"] in ("ai", "template", "unavailable") and e["check_status"] in ("passed", "failed", "not_checked")
    assert all(isinstance(x, str) for x in e["limitations"])
    t = d["trace"]
    if t is not None:
        assert set(t) == {"trace_id", "rule", "inputs", "thresholds", "assumptions"} and t["trace_id"] == d["finding"]["trace_id"]
        assert set(t["rule"]) == {"id", "version"} and all(isinstance(v, str) for v in t["rule"].values())
        for k in ("inputs", "thresholds", "assumptions"):
            assert all(isinstance(x, str) for x in t[k]), k
    for r in d["evidence"]:
        check_ref(r)
    assert d["review"] == {"state": "unreviewed", "opinions": []}
    assert DAY.match(d["reference_date"]) and (d["msds_revision_date"] is None or DAY.match(d["msds_revision_date"]))


def check_list(resp):
    assert set(resp) == LIST_KEYS
    for s in resp["items"]:
        check_summary(s)
    assert all(isinstance(v, int) and v >= 0 for v in list(resp["counts"].values()) + list(resp["excluded_counts"].values()))
    for g in resp["groups"]:
        assert set(g) == {"component_id", "title", "total", "matching_count"} and g["matching_count"] <= g["total"]
    assert resp["page"] >= 1 and resp["page_size"] >= 1


# ── 가짜 입력 ─────────────────────────────────────────────────────────

def fake_result():
    trace = {"kind": "mixture", "result": {"low": "2", "high": "2", "status": "확정"},
             "rule": {"id": "ATE-MIX-01", "basis": "고시 별표1"},
             "inputs": [{"name": "황산", "content": {"low": 93.0, "high": 98.0}, "ate_used": 0.375, "source": "TO21 독성DB",
                         "step": 1, "share": 1.0},
                        {"name": "물", "content": {"low": 2.0, "high": 7.0}, "step": 5, "excluded": "무독성"}],
             "calc": {"ate_mix_low": 0.4032, "ate_mix_high": 0.3827},
             "thresholds": [{"category": "2", "range": "0.05 < x ≤ 0.5", "rule_id": "ATE-INHAL-MIST"}], "assumptions": []}
    f2 = {"id": "F-2-005", "section": "2", "class_code": "HH_ACUTE_INHAL", "form": "분진·미스트", "verdict": "불일치",
          "type": "형태·세부 표기", "severity": "중간", "msds_value": ["2"], "msds_form": "증기",
          "our_value": {"low": "2", "high": "2"}, "reason": "", "trace_id": "T-2-005", "assumptions": [],
          "causes": [{"code": "FORM_DIFF", "text": "MSDS 증기, 계산 분진·미스트"}],
          "explanation": {"by": "llm", "checked": True, "summary": "형태만 다릅니다.", "summary_by": "llm",
                          "reasons": ["MSDS는 증기입니다."], "llm_problems": []}}
    f15 = {"id": "F-15-001", "section": "15", "comp_ref": "1", "law": "OSH", "item_code": "OSH_SPECIAL", "verdict": "불일치",
           "type": "규제 누락", "severity": "높음", "msds_value": None, "msds_threshold": None, "expected": "해당",
           "db_threshold": ">= 0.1%", "reason": "", "trace_id": "T-15-001", "assumptions": [],
           "causes": [{"code": "REG_MISSING", "text": "MSDS 15항에 이 규제 항목이 없음"}]}
    ok = {"id": "F-15-002", "section": "15", "comp_ref": "MIX", "law": "DG", "item_code": "DG_HAZMAT", "verdict": "일치",
          "type": None, "severity": None, "msds_value": "비해당", "expected": "비해당", "trace_id": None, "assumptions": [], "causes": []}
    t15 = {"kind": "regulation", "result": "해당", "rule": {"id": "S15-2"}, "law": "OSH", "item_code": "OSH_SPECIAL",
           "inputs": [{"comp_ref": "1", "name": "황산", "content": {"raw": "93 ~ 98", "low": 93, "high": 98}}],
           "expected": "해당", "db_threshold": ">= 0.1%", "msds_value": None, "source": ["HTODB KR001001007"], "db_text": ["… 0.1 wt% 이상"]}
    return {"consistency": {"as_of": "2022-06-29", "knowledge": {"rules": "r2026.10c", "version": ["test-1"]},
                            "findings": [f2, f15, ok], "traces": {"T-2-005": trace, "T-15-001": t15},
                            "excluded": [{"section": "15", "comp_ref": "1", "law": "CCA", "item_code": "CCA_ACUTE",
                                          "status": "구버전", "reason": "개정 전 체계", "source": []},
                                         {"section": "2", "class_code": "PH_FLAM_GAS", "status": "해당 없음", "reason": "가스용"}]}}


ITEM = {"meta": {"last_revision_date": "2022-06-29"},
        "components": [{"seq": 1, "name": "황산", "cas_no": "7664-93-9", "content": {"raw": "93 ~ 98"}}]}


@pytest.fixture
def view():
    return api_view(fake_result(), ITEM, msds_id="m1", validation_id="v1")


def test_모든_줄이_화면_스키마를_따른다(view):
    for d in view["details"]:
        check_detail(d)
    check_list(findings_response([view], validation_id="v1", extraction_id="e1"))


def test_판정·심각도·번호를_화면_값으로_바꾼다(view):
    s = view["details"][0]["finding"]
    assert (s["finding_id"], s["trace_id"], s["verdict"], s["severity"]) == ("m1-F-2-005", "m1-T-2-005", "mismatch", "medium")
    assert (s["item"], s["msds_value"]["text"], s["expected_value"]["text"], s["method"]) == \
        ("급성독성물질(흡입)", "구분 2 (증기)", "구분 2 (분진·미스트)", "ATEmix 계산")
    s15 = view["details"][1]["finding"]
    assert (s15["law"], s15["item"], s15["component_id"], s15["verdict"], s15["severity"]) == \
        ("산안법", "특별관리물질", "m1-c1", "mismatch", "high")
    assert (s15["msds_value"]["text"], s15["expected_value"]["text"]) == ("기재 없음", "해당 (>= 0.1%)")


def test_계산_근거는_글자_줄로_펼친다(view):
    t = view["details"][0]["trace"]
    assert t["rule"] == {"id": "ATE-MIX-01", "version": "r2026.10c"}
    assert t["inputs"][:2] == ["황산 93~98% · ATE 0.375 mg/L (TO21 독성DB, 1단계) · 기여도 100%",
                               "물 2~7% · 무독성 성분이라 계산에서 뺌 · 5단계"]
    assert "→ 구분 2 (확정)" in t["inputs"] and "차이 원인: MSDS 증기, 계산 분진·미스트" in t["inputs"]
    assert t["thresholds"] == ["0.05 < x ≤ 0.5 → 구분 2"]
    t15 = view["details"][1]["trace"]
    assert "지식DB 기준: >= 0.1% → 해당" in t15["inputs"] and "조문: … 0.1 wt% 이상" in t15["inputs"]
    assert t15["rule"]["version"] == "test-1"                                 # 15항은 지식DB 버전


def test_설명_출처와_한계(view):
    e = view["details"][0]["explanation"]
    assert (e["source"], e["check_status"], e["text"]) == ("ai", "passed", "형태만 다릅니다. MSDS는 증기입니다.")
    assert e["limitations"] == ["AI가 쓴 설명입니다. 판정은 규칙 엔진이 정했습니다."]
    assert view["details"][2]["explanation"] == {"text": "", "source": "unavailable", "check_status": "not_checked",
                                                 "limitations": []}       # 일치 줄에는 설명이 없다


def test_계산_근거가_없는_줄도_trace_id는_있다(view):
    d = view["details"][2]
    assert d["trace"] is None and d["finding"]["trace_id"] == "m1-T-15-002" and d["finding"]["component_id"] is None


def test_판정에서_뺀_줄은_구버전은_목록에_해당_없음은_건수만(view):
    resp = findings_response([view], validation_id="v1", extraction_id="e1")
    assert [i["verdict"] for i in resp["items"]] == ["mismatch", "mismatch", "match", "outdated"]
    assert resp["excluded_counts"] == {"not_applicable": 1, "excluded": 0}
    assert resp["counts"]["outdated"] == 1 and resp["counts"]["warning"] == 0


def test_목록_거르기·쪽_나누기·묶음은_화면_데모와_같은_규칙(view):
    resp = findings_response([view], validation_id="v1", extraction_id="e1", section=15, verdict="mismatch")
    assert resp["total"] == 1 and resp["counts"]["match"] == 1                 # counts 는 거르기 전
    assert resp["groups"] == [{"component_id": "m1-c1", "title": "황산 (93~98%)", "total": 2, "matching_count": 0},
                              {"component_id": "product", "title": "제품", "total": 1, "matching_count": 1}]
    page2 = findings_response([view], validation_id="v1", extraction_id="e1", page=2, page_size=2)
    assert [i["finding_id"] for i in page2["items"]] == ["m1-F-15-002", "m1-X-15-001"] and page2["total"] == 4


def test_상세는_번호로_찾고_없으면_None(view):
    assert finding_detail([view], "m1-F-2-005")["finding"]["item"] == "급성독성물질(흡입)"
    assert finding_detail([view], "없음") is None


def test_조건식은_읽는_말로():
    assert readable_formula('sum("1") >= 10 and prop("VISCOSITY_40") <= 20.5') == \
        "구분 1 성분 합계 >= 10 그리고 9항 40℃ 동점도 <= 20.5"
    assert readable_formula('10*sumx("1") + sum("2") >= 25') == "10*구분 1 합계(M 곱함) + 구분 2 성분 합계 >= 25"


# ── 25번 황산·silver (샘플 CSV) ─────────────────────────────────────────

@pytest.fixture(scope="module")
def repo():
    r = CsvRepo()
    if not (r.available() and (SILVER / "T21-025.json").exists()):
        pytest.skip("to21_sample CSV 또는 silver 추출본 없음")
    return r


def test_25번_15항_목록(repo):
    doc = json.loads((SILVER / "T21-025.json").read_text(encoding="utf-8"))
    r = run_consistency(doc, repo, 0)
    explain_consistency(r, doc["msds"][0])
    v = api_view(r, doc["msds"][0], msds_id="m", validation_id="v")
    resp = findings_response([v], validation_id="v", extraction_id="e", section=15)
    s15 = r["consistency"]["summary"]["15항"]
    assert (resp["counts"]["match"], resp["counts"]["mismatch"]) == (s15["일치"], s15["불일치"])
    assert [g["title"] for g in resp["groups"]] == ["황산 (93~98%)", "물 (2~7%)", "제품"]
    inhal = next(d for d in v["details"] if d["finding"]["item"] == "급성독성물질(흡입)" and d["finding"]["verdict"] == "mismatch")
    assert inhal["finding"]["expected_value"]["text"] == "구분 2 (분진·미스트)" and inhal["trace"]["rule"]["id"] == "ATE-MIX-01"


def test_silver_전체가_화면_스키마를_따르고_건수가_맞는다(repo):
    n = 0
    for path in sorted(SILVER.glob("*.json")):
        if path.name.endswith(".review.json"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        views = []
        for i, item in enumerate(doc.get("msds") or []):
            r = run_consistency(doc, repo, i)
            explain_consistency(r, item)
            v = api_view(r, item, msds_id=f"{path.stem}_{i}", validation_id="v")
            c = r["consistency"]
            assert len(v["details"]) == len(c["findings"]) + len(c["excluded"]), path.stem
            for d in v["details"]:
                check_detail(d)
                n += 1
            views.append(v)
        ids = [d["finding"]["finding_id"] for v in views for d in v["details"]]
        assert len(ids) == len(set(ids)), path.stem                          # 한 검증 안에서 번호가 겹치지 않음
        for sec in (None, 2, 15):
            resp = findings_response(views, validation_id="v", extraction_id="e", section=sec)
            check_list(resp)
            assert resp["total"] == sum(resp["counts"].values())
    assert n > 1000
