"""판정 설명 시험 (11/02 F 결정 13, 설계서 13장 설명 요청·응답과 안전장치, 40·44장).

- 요청은 판정 줄 하나의 원인 코드·trace 요약·MSDS 원문 조각만 담는다.
- LLM 설명은 숫자·코드·구분 검사를 통과해야 쓰고, 실패하면 한 번 다시 요청한 뒤 문장틀로 대체한다.
- LLM이 없으면 문장틀 설명. 문장틀도 같은 검사를 통과해야 한다.
LLM 서버는 쓰지 않고 가짜 함수로 시험한다. 뒤쪽 25번·silver 시험은 샘플 CSV·silver 추출본이 있을 때만 돈다(D-47).
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from msds.compliance.consistency import run_consistency
from msds.compliance.explain import (ChatExplainer, build_request, check, explain_consistency, explain_finding,
                                     item_names, ro)
from msds.compliance.htodb.csv_repo import CsvRepo

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude"


def finding():
    return {"id": "F-2-005", "section": "2", "class_code": "HH_ACUTE_INHAL", "form": "분진·미스트", "verdict": "불일치",
            "type": "형태·세부 표기", "severity": "중간", "msds_value": ["2"], "msds_form": "증기",
            "our_value": {"low": "2", "high": "2"}, "reason": "구분은 같고 형태만 다름", "trace_id": "T-2-005",
            "causes": [{"code": "FORM_DIFF", "text": "MSDS 증기, 계산 분진·미스트"},
                       {"code": "MAIN_COMPONENT", "text": "황산 (ATE 기여도 100%)"}]}


TRACE = {"kind": "mixture", "result": {"low": "2", "high": "2", "status": "확정"},
         "rule": {"id": "ATE-MIX-01", "basis": "고시 별표1", "formula": "100/ATEmix = Σ(Ci/ATEi)"},
         "inputs": [{"name": "황산", "cas": "7664-93-9", "content": {"low": 93.0, "high": 98.0}, "ate_used": 0.375,
                     "source": "TO21 독성DB", "step": 1, "share": 1.0}],
         "calc": {"ate_mix_low": 0.4032258, "ate_mix_high": 0.3826531}, "thresholds": [{"category": "2", "range": "0.05 < x ≤ 0.5"}],
         "assumptions": [], "knowledge_version": "r2026.10c"}
ITEM = {"hazard": {"classes": [{"class_code": "HH_ACUTE_INHAL", "category": "2", "route_form": "증기"}]},
        "evidence": [{"field": "hazard.classes[0]", "page": 1, "source_text": "- 급성 독성(흡입: 증기) :  구분2"}]}
GOOD = {"summary": "흡입 급성독성은 구분 2로 같지만 MSDS는 증기, 계산은 분진·미스트입니다.",
        "reasons": ["주성분 황산(CAS 7664-93-9, 함량 93~98%)의 흡입 독성값은 0.375 mg/L이고 기여도는 100%입니다.",
                    "계산한 ATEmix 0.383~0.403 mg/L는 구분 2 범위(0.05 < x ≤ 0.5)입니다."],
        "basis": ["적용 규칙 ATE-MIX-01(고시 별표1)", "MSDS 1쪽 2항"], "used_numbers": [0.375, 0.383, 0.403, 100]}


def fake(*responses):
    calls = []

    def llm(system, user):
        calls.append(user)
        r = responses[min(len(calls), len(responses)) - 1]
        return r, {"model": "가짜", "errors": [] if r else ["연결 실패"]}
    llm.calls = calls
    return llm


def test_조사_으로_로():
    assert [ro(x) for x in ("구분 3", "구분 2", "구분 1A", "분류안됨", "비해당", "압축가스")] == \
        ["구분 3으로", "구분 2로", "구분 1A로", "분류안됨으로", "비해당으로", "압축가스로"]


def test_항목_이름():
    n = item_names()
    assert n["HH_ACUTE_INHAL"] == "급성독성물질(흡입)" and n["DG_HAZMAT"] == "위험물안전관리법 위험물"
    assert n["LABEL_PICTOGRAMS"] == "표시 요소(그림문자)"


def test_요청은_설계서_13장_모양이고_원문_조각을_담는다():
    req = build_request(finding(), TRACE, ITEM)
    assert req["task"] == "explain_finding" and req["finding"]["msds"] == {"category": ["2"], "route_form": "증기"}
    assert req["evidence"] == [{"page": 1, "text": "- 급성 독성(흡입: 증기) :  구분2", "field": "hazard.classes[0]"}]
    assert req["trace"]["calc"]["ate_mix_low"] == 0.4032                       # 긴 소수는 4자리로


def test_검사는_근거에_없는_숫자·코드·구분을_잡는다():
    req = build_request(finding(), TRACE, ITEM)
    assert check(GOOD, req) == []                                              # 0.383 ← 0.3826531, 100% ← 기여도 1.0
    assert check({**GOOD, "summary": "황산의 LC50 0.375 mg/L로 ATEmix를 계산했습니다(11항·2항)."}, req) == []  # 용어 속 숫자
    bad = {**GOOD, "reasons": GOOD["reasons"] + ["4시간 노출 기준 LC50 0.5 mg/L, H331, 구분 3과 비교했습니다."]}
    problems = check(bad, req)
    assert "근거에 없는 숫자 4" in problems and "근거에 없는 코드 H331" in problems and "근거에 없는 구분 3" in problems
    assert check({"summary": ""}, req) == ["응답 형식이 맞지 않음(summary 없음)"]


def test_LLM이_없으면_문장틀_설명():
    e = explain_finding(finding(), TRACE, ITEM)
    assert e["by"] == "template" and e["checked"] and e["model"] is None
    assert e["summary"] == "급성독성물질(흡입): 구분은 같지만 흡입 형태가 다릅니다(MSDS 증기 구분 2, 계산 분진·미스트 구분 2)."
    assert e["reasons"][:2] == ["MSDS 증기, 계산 분진·미스트", "황산 (ATE 기여도 100%)"] and e["evidence"][0]["page"] == 1


def test_LLM_설명이_검사를_통과하면_쓴다():
    e = explain_finding(finding(), TRACE, ITEM, fake(GOOD))
    assert (e["by"], e["checked"], e["model"], e["llm_problems"]) == ("llm", True, "가짜", [])


def test_검사에_걸리면_문제를_알려_한_번_다시_요청한다():
    bad = {**GOOD, "summary": "구분 3으로 바꿔야 합니다."}
    llm = fake(bad, GOOD)
    e = explain_finding(finding(), TRACE, ITEM, llm)
    assert e["by"] == "llm" and e["llm_problems"] == ["근거에 없는 구분 3"]
    assert "앞 응답이 검사에 걸렸습니다: 근거에 없는 구분 3" in llm.calls[1]


def test_두_번_다_실패하거나_응답이_없으면_문장틀로_대체():
    e = explain_finding(finding(), TRACE, ITEM, fake({**GOOD, "summary": "LC50 9.9 mg/L"}))
    assert e["by"] == "template" and e["checked"] and "근거에 없는 숫자 9.9" in e["llm_problems"]
    e = explain_finding(finding(), TRACE, ITEM, fake(None))
    assert e["by"] == "template" and e["llm_problems"][0].startswith("LLM 응답 없음")


def test_ChatExplainer는_ChatClient_결과에서_설명만_꺼낸다():
    client = SimpleNamespace(model="m", call=lambda *a, **k: SimpleNamespace(parsed=GOOD, ok=True, errors=[], model="m", seconds=1.2))
    resp, meta = ChatExplainer(client=client)("s", "u")
    assert resp == GOOD and meta == {"model": "m", "seconds": 1.2, "errors": []}
    client.call = lambda *a, **k: SimpleNamespace(parsed=None, ok=False, errors=["[json_schema] 거부됨"], model="m", seconds=0)
    assert ChatExplainer(client=client)("s", "u")[0] is None


def test_외부_중계_모델은_설명에_쓰지_않는다():
    with pytest.raises(ValueError, match="외부 중계"):
        ChatExplainer("gpt", cfg={"model": "x", "base_url_env": "LLM_BASE_URL", "api_key_env": "LLM_API_KEY"})


def test_25번과_silver_전체_문장틀_설명은_모두_검사를_통과한다():
    repo = CsvRepo()
    if not repo.available() or not (SILVER / "T21-025.json").exists():
        pytest.skip("to21_sample CSV 또는 silver 추출본 없음")
    n = 0
    for path in sorted(SILVER.glob("*.json")):
        if path.name.endswith(".review.json"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for i, item in enumerate(doc.get("msds") or []):
            r = run_consistency(doc, repo, i)
            stats = explain_consistency(r, item)
            for f in r["consistency"]["findings"]:
                assert ("explanation" in f) == (f["verdict"] != "일치"), (path.stem, f["id"])
                if "explanation" in f:
                    assert f["explanation"]["checked"], (path.stem, f["id"], f["explanation"])
            n += stats["설명"]
    assert n > 100
