import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pytest  # noqa: E402
from review_cards import build_cards, card_key, comps_from_rows, dropped, human, GLOSSARY  # noqa: E402


def bc(rows, **kw):
    """build_cards: 골드에서 빠지는 항목은 이 줄들로 (문서 골드 모델은 시험용 gpt)."""
    return build_cards(rows, drop=dropped(rows, "gpt"), **kw)
from msds.review.sheet_spec import COLUMNS  # noqa: E402

NAMES = {"TX_ORAL": ["급성 독성(경구)", "경구"], "OSH": ["산업안전보건법"]}
COMPS = {"1": "벤젠", "MIX": "제품 전체"}

def test_card_key():
    assert card_key("msds[0].toxicity[k=1|TX_ORAL|LD50|쥐].q") == "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    assert card_key("msds[0].meta.revision_no") == "msds[0].meta"
    assert card_key("msds[1].extras[k=1|a].statements[0]") == "msds[1].extras[k=1|a].statements[0]"

def test_human_quantity():
    q = lambda **k: json.dumps({"raw": "", "approx": None, "value": None, "lower_op": None, "lower": None, "upper_op": None, "upper": None, "unit": None, "dp": None, "status": "값있음", "note": None, **k})
    assert human("x.q", q(lower_op=">", lower=2000, unit="mg/kg"), NAMES, COMPS)["text"] == "2000 mg/kg 초과"
    assert human("x.q", q(lower_op=">=", lower=10, upper_op="<=", upper=20, unit="%"), NAMES, COMPS)["text"] == "10~20 %"
    assert human("x.q", q(value=5, approx=True, unit="ppm"), NAMES, COMPS)["text"] == "약 5 ppm"
    assert human("x.q", q(upper_op="<", upper=0.01), NAMES, COMPS)["text"] == "0.01 미만"
    assert human("x.q", q(status="자료없음", raw="자료없음"), NAMES, COMPS)["text"] == "자료 없음"
    assert human("x.q", q(lower_op=">", lower=0, upper_op="<=", upper=20, unit="%"), NAMES, COMPS)["text"] == "0 초과 20 % 이하"
    assert human("x.q", q(lower_op=">=", lower=1, upper_op="<", upper=5), NAMES, COMPS)["text"] == "1 이상 5 미만"
    assert human("x.q", q(lower=10, upper=20, unit="%", approx=True), NAMES, COMPS)["text"] == "약 10~20 %"
    assert human("x.q", q(value=2000.0, unit="mg/kg"), NAMES, COMPS)["text"] == "2000 mg/kg"
    assert human("x.q", q(value=1e-05), NAMES, COMPS)["text"] == "0.00001"
    assert human("x.q", q(status="미기재", raw="-"), NAMES, COMPS)["text"] == "적혀 있지 않음 (-)"
    assert human("x.q", q(status="해당없음", raw="해당 없음"), NAMES, COMPS)["text"] == "해당 없음"
    assert human("x.q", q(status="자료없음", raw="Not available"), NAMES, COMPS)["text"] == "자료 없음 (Not available)"
    assert human("x.q", q(status=None, value=3, unit="ppm"), NAMES, COMPS)["text"] == "3 ppm"      # 상태가 없어도 수가 있으면 값
    assert human("x.q", json.dumps({"raw": "약간", "value": None}), NAMES, COMPS)["text"] == "약간"   # 상태·수 없으면 원문

def test_human_codes_refs_bools():
    assert human("x.endpoint", "TX_ORAL", NAMES, COMPS) == {"text": "급성 독성(경구)", "code": "TX_ORAL"}
    assert human("x.comp_ref", '"1"', NAMES, COMPS)["text"] == "벤젠"
    assert human("x.comp_ref", "MIX", NAMES, COMPS)["text"] == "제품 전체"
    assert human("x.regulated", "true", NAMES, COMPS)["text"] == "예"
    assert human("x.uses", '["세척제", "도료"]', NAMES, COMPS)["text"] == "세척제 · 도료"
    assert human("x.statements[0]", json.dumps({"seq": 1, "key": "성남", "value": "031-1", "text": "성남 031-1"}), NAMES, COMPS)["text"] == "성남: 031-1"

def test_human_edges():
    h = lambda p, c: human(p, c, NAMES, COMPS)["text"]
    assert h("x.flag", "false") == "아니요" and h("x.a", "null") == "비움" and h("x.a", "") == "비움" and h("x.uses", "[]") == "비움"
    assert h("x.cond", json.dumps({"temp": None, "temp_unit": None, "pressure": None, "method": None})) == "조건 없음"
    assert h("x.cond", json.dumps({"temp": 20.0, "temp_unit": "C"})) == "온도 20 C"
    assert h("x.statements[0]", json.dumps({"seq": 1, "key": "용기등급", "value": None, "text": None})) == "용기등급"
    assert h("x.endpoint", "EMPTY") == "EMPTY" and human("x.e", "EMPTY", {"EMPTY": []}, COMPS)["text"] == "EMPTY"   # 이름 없는 코드
    assert h("x.q", '{"raw": "> 2') == '{"raw": "> 2'                  # JSON이 깨진 칸은 글자 그대로
    assert h("x.v", "2000.0") == "2000"
    assert human("msds[1].cmr[k=a].comp_ref", '"1"', NAMES, {"0|1": "벤젠", "1|1": "톨루엔"})["text"] == "톨루엔"   # MSDS 건마다 성분표


def row(path, val):
    return {**{c: "" for c in COLUMNS}, "경로": path, "Claude 값": val}


def cards(rows, **kw):
    return bc(rows, names=NAMES, comps=COMPS, labels={r["경로"]: r["경로"].rsplit(".", 1)[-1] for r in rows},
                       tips={}, pages=10, explain={}, **kw)


def sentence(c):
    return "".join(p["s"] if p["t"] == "text" else f"[{p['text']}]" for p in c["parts"])


def rows_tox():
    item = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    q = json.dumps({"raw": "> 2000 mg/kg", "approx": None, "value": None, "lower_op": ">", "lower": 2000, "upper_op": None, "upper": None, "unit": "mg/kg", "dp": 0, "status": "값있음", "note": None})
    return [row(f"{item}.comp_ref", '"1"'), row(f"{item}.endpoint", "TX_ORAL"), row(f"{item}.descriptor", "LD50"),
            row(f"{item}.species", "쥐"), row(f"{item}.q", q), row(f"{item}.status", "값있음"), row(f"{item}.guideline", "OECD TG 401")]


def test_toxicity_sentence():
    c = cards(rows_tox())["msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"]
    text = sentence(c)
    assert text.startswith("[벤젠]을 [급성 독성(경구)]") and "[쥐] 실험에서" in text and "[2000 mg/kg 초과]" in text
    assert "[OECD TG 401]" in text                     # 틀에 없는 칸은 뒤에 '이름: 값' 칩
    assert [a["path"].rsplit(".", 1)[1] for a in c["auto"]] == ["status"] and c["auto"][0]["ok"]
    assert "[LD50]은 " in text and c["type"] == "sentence" and c["question"] is None
    chip = next(p for p in c["parts"] if p["t"] == "chip" and p["path"].endswith(".descriptor"))
    assert chip["tip"] == GLOSSARY["LD50"] and chip["warn"] == ""


def test_josa_and_missing_slot():
    item = "msds[0].toxicity[k=MIX|TX_ORAL|결과기술|]"
    c = cards([row(f"{item}.comp_ref", "MIX"), row(f"{item}.endpoint", "TX_ORAL"), row(f"{item}.descriptor", "결과기술"), row(f"{item}.status", "자료없음")])[item]
    assert sentence(c) == "[제품 전체]의 [급성 독성(경구)] [결과기술]: [자료 없음]"      # 시험종이 없으면 다른 틀, 상태가 값 자리
    item = "msds[0].toxicity[k=1|TX_CARC|결과기술|]"
    c = bc([row(f"{item}.comp_ref", '"1"'), row(f"{item}.endpoint", "TX_CARC"), row(f"{item}.descriptor", "결과기술"), row(f"{item}.status", "값있음")],
                    names={**NAMES, "TX_CARC": ["발암성"]}, comps=COMPS, labels={}, tips={}, pages=10, explain={})[item]
    assert sentence(c) == "[벤젠]의 [발암성] [결과기술]: [적혀 있음]"          # 매달린 을/를 없음, '값있음' 대신 사람 말
    e = "msds[0].ecotox[k=MIX|ECO_PERSIST|분해율|]"
    assert sentence(cards([row(f"{e}.comp_ref", "MIX"), row(f"{e}.descriptor", "분해율")])[e]) == "[제품 전체]의 [분해율]"
    c = cards([row("msds[0].companies[k=a].role", "제조자"), row("msds[0].companies[k=a].name", "ACME")])["msds[0].companies[k=a]"]
    assert sentence(c) == "[제조자] [ACME]"


def test_every_row_once_all_sheets():
    """data/review/*.xlsx 전수: 모든 줄이 칩·auto·meta 중 정확히 한 번, 빈 문장 0, 예외 0."""
    import review_app
    review_app._use_repo_data()
    docs = sorted(review_app.paths.REVIEW.glob("*.xlsx"))
    if not docs:
        pytest.skip("검수표 없음")
    names, warns = review_app._code_names(), {}
    for f in docs:
        rows = review_app.Sheet(f.stem).rows()
        drop = dropped(rows, review_app.default_model(f.stem))
        comps = comps_from_rows(rows, drop)
        labels = {r["경로"]: r["칸 이름"].split(" · ")[-1].split(" (")[0] for r in rows}
        pages = review_app.page_count(f.stem)
        explain = {r["경로"]: e for r in rows if (e := review_app._explain(r, rows, pages))}
        out = build_cards(rows, names=names, comps=comps, labels=labels, tips={}, pages=pages, explain=explain, code_match=review_app._code_match, drop=drop)
        seen = Counter(x["path"] for c in out.values()
                       for x in [*(p for p in c["parts"] if p["t"] == "chip"), *c["auto"], *c["meta"]])
        assert seen == Counter(r["경로"] for r in rows), f.stem
        for k, c in out.items():
            assert any(p["t"] == "chip" for p in c["parts"]) or c["question"], (f.stem, k)
            shown = [c["title"], c["question"] or "", c["hint"] or "", *(p.get("text", p.get("s", "")) + p.get("warn", "") for p in c["parts"]),
                     *(a["text"] + a["why"] for a in c["auto"]), *(m["text"] for m in c["meta"])]
            assert not [x for x in shown if "None" in x or "undefined" in x], (f.stem, k)
        R = {r["경로"]: r for r in rows}
        for p in (p for c in out.values() for p in c["parts"] if p["t"] == "chip" and p["code"] and "표기예요" in p["warn"]):
            r = R[p["path"]]                                     # 코드 ⚠는 거짓이 없어야 한다: 긴 다른 코드 표기가 원문에 있고, 그것을 지우면 이 코드 표기가 남지 않음
            snip = r["수정 원문 조각"] or r["Claude 원문 조각"] or r["GPT 원문 조각"]
            longer = re.search(r"원문 ‘(.*?)’", p["warn"]).group(1)
            assert longer in snip, (f.stem, p["path"])
            rest = review_app._norm(snip.replace(longer, " "))
            assert not [v for n in names[p["code"]] for v in review_app._variants(n) if len(v) >= 3 and v in rest], (f.stem, p["path"])
        warns[f.stem] = sum(1 for c in out.values() for p in c["parts"] if p["t"] == "chip" and p["code"] and "표기예요" in p["warn"])
    print("코드 경고 칩:", warns)


def test_comps_from_rows():
    rows = [row("msds[0].components[k=71-43-2].seq", "1"), row("msds[0].components[k=71-43-2].name", "벤젠"),
            row("msds[1].components[k=108-88-3].seq", "1"), row("msds[1].components[k=108-88-3].name", "톨루엔"),
            row("msds[1].components[k=x].seq", '"2"')]
    assert comps_from_rows(rows, {}) == {"MIX": "제품 전체", "0|1": "벤젠", "1|1": "톨루엔", "1|2": "2"}


def test_auto_failure_becomes_chip():
    r = rows_tox(); r[5] = row(r[5]["경로"], "자료없음")          # 행 상태가 수치 상태와 다름 → 경고 칩
    c = cards(r)["msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"]
    assert any(p["t"] == "chip" and p["path"].endswith(".status") and p["warn"] for p in c["parts"])
    assert not c["auto"]


def test_auto_checks():
    item = "msds[0].extras[k=1|a]"
    c = cards([row(f"{item}.title_raw", "a"), row(f"{item}.page", "11"), row(f"{item}.section_no", "17")])[item]
    assert {p["path"].rsplit(".", 1)[1] for p in c["parts"] if p["t"] == "chip" and p["warn"]} == {"page", "section_no"}
    assert cards([row(f"{item}.title_raw", "a"), row(f"{item}.section_no", "0")])[item]["auto"][0]["ok"]   # 0 = 머리글
    q = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    c = cards([row(f"{q}.endpoint", "TX_ORAL"), row(f"{q}.q", json.dumps({"raw": None, "value": None})), row(f"{q}.status", "값있음")])[q]
    warn = next(p["warn"] for p in c["parts"] if p["t"] == "chip" and p["path"].endswith(".status"))
    assert "None" not in warn and "비움" in warn                    # 수치에 상태가 없어도 'None'을 보이지 않는다
    p = "msds[0].hazard.p_statements[k=P210]"
    c = cards([row(f"{p}.code", "P210"), row(f"{p}.text", "열을 피하시오"), row(f"{p}.type", "대응")])[p]
    assert any(x["path"].endswith(".type") and x["warn"] for x in c["parts"] if x["t"] == "chip")   # P2xx는 예방
    h = "msds[0].hazard.h_statements[k=H226]"
    assert cards([row(f"{h}.code", "H226"), row(f"{h}.system", "GHS")])[h]["auto"][0]["ok"]
    k = "msds[0].hazard.classes[k=HH_X|1|]"
    assert cards([row(f"{k}.class_code", "HH_X"), row(f"{k}.group", "건강")])[k]["auto"][0]["ok"]
    s = "msds[0].physchem[k=MIX|PH]"
    seq = lambda e: bc([row(f"{s}.seq", "2"), row(f"{s}.prop_code", "PH")], names=NAMES, comps=COMPS, labels={}, tips={}, pages=10, explain={f"{s}.seq": e})[s]
    assert seq("… (자동 확인)")["auto"][0]["ok"] and not seq("… 확인 필요")["auto"]
    t = "msds[0].toxicity[k=9|TX_ORAL|LD50|]"
    c = cards([row(f"{t}.comp_ref", '"9"'), row(f"{t}.endpoint", "TX_ORAL")])[t]
    assert next(x for x in c["parts"] if x["t"] == "chip" and x["path"].endswith("comp_ref"))["warn"]   # 성분표에 없는 번호


def test_extras_hides_model_meta():
    item = "msds[0].extras[k=1|영업사무소]"
    c = cards([row(f"{item}.seq", "1"), row(f"{item}.section_no", "1"), row(f"{item}.title_raw", "영업사무소"),
               row(f"{item}.reason", "필드없음"), row(f"{item}.after_item", "company.phone"), row(f"{item}.page", "1")])[item]
    assert [p["path"].rsplit(".", 1)[1] for p in c["parts"] if p["t"] == "chip"] == ["title_raw"]
    assert {m["path"].rsplit(".", 1)[1] for m in c["meta"]} == {"reason", "after_item"}
    added = [{**row(f"{item}.{k}", ""), "검수 결과": "누락 추가", "수정값": v} for k, v in (("seq", "28"), ("title_raw", "영업사무소"), ("reason", "필드없음"))]
    c = cards(added)[item]                                            # 사람이 넣은 줄: 순번·사유는 화면이 정한 값 (경고 칩·'AI가 정한 정보' 아님)
    assert [p["path"].rsplit(".", 1)[1] for p in c["parts"] if p["t"] == "chip"] == ["title_raw"] and not c["meta"]
    assert {a["path"].rsplit(".", 1)[1] for a in c["auto"]} == {"seq", "reason"} and all(a["ok"] for a in c["auto"])
    typed = [{**row(f"{item}.{k}", ""), "검수 결과": "누락 추가", "수정값": v} for k, v in (("title_raw", "영업사무소"), ("page", "99"), ("section_no", "14"))]
    c = cards(typed)[item]                                            # 사람이 적은 쪽·항 번호는 보통 자동 확인 (쪽수 10 밖이면 경고 칩)
    assert [p["path"].rsplit(".", 1)[1] for p in c["parts"] if p["t"] == "chip" and p["warn"]] == ["page"]
    assert [(a["path"].rsplit(".", 1)[1], a["why"]) for a in c["auto"]] == [("section_no", "MSDS 0~16항 안 (0 = 머리글)")]


def test_boolean_is_question():
    c = cards([row("msds[0].composition.no_hazardous_component", "false")])["msds[0].composition"]
    assert c["question"] == "이 문서에 ‘유해 성분이 없다’는 말이 적혀 있나요?"
    assert c["type"] == "question" and sentence(c) == "AI의 답: [아니요]"
    c = cards([row("msds[0].composition.no_hazardous_component", "false"), row("msds[0].composition.type", "혼합물")])["msds[0].composition"]
    assert c["type"] == "sentence" and c["question"] is None and "유해 성분 없음: [아니요]" in sentence(c) and "[혼합물]" in sentence(c)   # 섞인 카드: 질문 줄 없이 칩
    yn = next(p for p in c["parts"] if p["t"] == "chip" and p["path"].endswith("no_hazardous_component"))
    assert yn["label"] == "유해 성분 없음" and yn["tip"] == "원문에 ‘유해 성분이 없다’는 뜻의 말이 없어서 ‘아니요’예요. 있으면 틀린 칩이에요"
    item = "msds[0].components[k=71-43-2]"
    c = cards([row(f"{item}.name", "벤젠"), row(f"{item}.cas_no", "71-43-2"), row(f"{item}.trade_secret", "false")])[item]
    assert c["type"] == "sentence" and c["question"] is None and "영업비밀로 가림: [아니요]" in sentence(c) and "AI의 답" not in sentence(c)
    c = cards([row("msds[0].x.odd_flag", "true")])["msds[0].x"]
    assert c["question"] == "이 문서에 ‘odd_flag’ 표시가 있나요?"


def test_hwapyeong_hint():
    item = "msds[0].regulations[k=1|KREACH|KREACH_EXISTING|]"
    c = cards([row(f"{item}.law", "KREACH"), row(f"{item}.item_code", "KREACH_EXISTING"), row(f"{item}.applicable", "null"), row(f"{item}.value_raw", "KE-02150")])[item]
    assert "번호" in c["hint"] and "비해당" in c["hint"] and "💡" not in c["hint"]   # 💡는 화면이 붙인다
    t = "msds[0].transport[k=해상]"
    c = cards([row(f"{t}.mode", "해상"), row(f"{t}.regulated", "false"), row(f"{t}.packing_group", "")])[t]
    assert "용기등급" in c["hint"] and c["question"] is None and "운송 규제 대상: [아니요]" in sentence(c)


def test_code_tip_shows_source_synonym():
    item = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    r = {**row(f"{item}.endpoint", "TX_ORAL"), "Claude 원문 조각": "경구 LD50 > 2000 mg/kg"}
    chip = next(p for p in cards([r])[item]["parts"] if p["t"] == "chip")
    assert chip["code"] == "TX_ORAL" and chip["tip"] == "경구 = 입으로 먹었을 때 · 원문 ‘경구’ = 급성 독성(경구)"   # 용어 풀이, 코드 대신 이름
    r = {**r, "Claude 원문 조각": "흡입 독성"}                       # 원문에 코드 표기가 없으면 코드 이름 풀이 ('어떤 말을 옮긴 값인지'는 화면이 점선 칩에만)
    assert next(p for p in cards([r])[item]["parts"] if p["t"] == "chip")["tip"] == "정해진 이름이에요 (원문 표기 예: 경구). 원문의 어느 말인지 확인해 주세요 · 경구 = 입으로 먹었을 때"
    r = {**r, "Claude 원문 조각": "급성 독성(경구) LD50"}
    assert "원문 ‘" not in next(p for p in cards([r])[item]["parts"] if p["t"] == "chip")["tip"]   # '원문 ‘급성 독성(경구)’ = 급성 독성(경구)' 되풀이는 뺀다


def test_code_from_other_code_is_warned():
    """원문 표기가 같은 갈래의 다른 코드 것이면(더 긴 표기 속 일부 글자) 칩을 ⚠로, 풀이에 '원문 → 이름'을 쓰지 않는다."""
    import review_app
    review_app._use_repo_data()
    snip = "특별관리대상물질 | 해당됨 (0.1% 이상 함유한 Benzene)"
    assert review_app._code_match("OSH_MANAGED", snip) == ("", "OSH_SPECIAL", "특별관리대상물질")
    assert review_app._code_match("OSH_SPECIAL", snip)[:2] == ("특별관리대상물질", "")
    assert review_app._code_match("OSH_MANAGED", "관리대상유해물질 | 해당됨")[:2] == ("관리대상유해물질", "")
    assert "‘특별관리물질’" in review_app._code_in_snippet("OSH_MANAGED", snip) and "일부 글자" in review_app._code_in_snippet("OSH_MANAGED", snip)
    assert review_app._code_match("OSH_MANAGED", "관리대상물질 | 특별관리대상물질")[:2] == ("관리대상물질", "")   # 긴 표기 밖에도 있으면 이 코드
    other = "- 1,3-Butadiene : 특별관리물질(0.1% 이상)"           # 이 코드 표기가 아예 없음: 칩은 조용히, 사진 위 안내만
    assert review_app._code_match("OSH_MANAGED", other) == ("", "", "") and "‘특별관리물질’" in review_app._code_in_snippet("OSH_MANAGED", other)
    item = "msds[0].regulations[k=1|OSH|OSH_MANAGED|#2]"
    r = {**row(f"{item}.item_code", "OSH_MANAGED"), "Claude 원문 조각": snip}
    c = bc([r], names=review_app._code_names(), comps=COMPS, labels={}, tips={}, pages=10, explain={},
                    code_match=review_app._code_match)[item]
    chip = c["parts"][0]
    assert chip["warn"] == "원문 ‘특별관리대상물질’은 ‘특별관리물질’ 표기예요. 맞는지 확인해 주세요" and "원문 ‘" not in chip["tip"]


# 19건 검토(라운드 1)에서 거짓 코드 ⚠가 붙었던 (코드, 원문 조각): 이 코드 표기가 아예 없거나 긴 다른 표기 밖에도 있다 → ⚠ 없음
FALSE_WARN = [
    ("KREACH_ETC", "o 신규화학물질 : 미해당"),
    ("TX_STOT_SE", "[4-메틸-2-펜탄온] : 사람에서 기도·점막 자극성, 두통·현기증·구토 등의 마취 작용을 수반하는 중추 신경 증상이 나타남. "
                   "동물 실험에서 마취 작용이 나타남. 구분 3 (호흡기 작용, 마취작용)으로 분류됨. (NITE)"),
    ("KREACH_EXIST", "KECL | 화학물질 목록 법규 준수 현황에 대해 공급자에게 문의할 것."),
    ("TX_RESP_SENS", "호흡기 또는 피부 과민성 | 자료 없음."),
    ("OSH_MANAGED", "● 특별관리물질 | - 해당없음"),
    ("OSH_PERMISSIBLE", "(PRODUCT : 노출기준 설정물질, 허용기준 준수물질, 공정안전관리(PSM) 대상물질)"),
    ("TX_STOT_SE", "NATURAL GAS, LIQUIFIED : 인간에게 노출되었을 때, 급성독성영향은 나타나지 않았음"),
    ("TX_STOT_SE", "Tert-butyl mercaptan : 랫드를 이용한 급성흡입독성시험에서 급성독성 악영향은 관찰되지 않았음 (OECD TG 403, GLP)"),
    ("TX_STOT_SE", "Tetrahydrothiophene : 랫드를 이용한 급성흡입독성시험에서 급성독성 악영향은 관찰되지 않았음 (GLP)"),
    ("CCA_PRTR", "PRODUCT : PRTR물질, 유독물질"),
    ("KREACH_EXIST", "- 1,3-Butadiene : 기존화학물질, 등록대상기존화학물질"),
    ("OSH_MANAGED", "- 1,3-Butadiene : 특별관리물질(0.1% 이상)"),
    ("TX_STOT_RE", "랫드를 이용한 103주 흡입 발암성시험 OECD TG 453, GLP, ... NOAEC=1000 ppm2212 mg/m3 표적장기 : 난소, 정소, 골수,  출처 : ECHA"),
    ("APPEARANCE_COLOR", "1)외관 | 물리적 상태 : 압축가스, 색상 : 무색"),
    ("KREACH_ETC", "다. 화학물질의 등록 및 평가 등에 관한 법률에 의한 규제 | - 유해성미확인물질 | 해당없음"),
]


@pytest.mark.parametrize("code, snip", FALSE_WARN)
def test_no_false_code_warning(code, snip):
    import review_app
    review_app._use_repo_data()
    item = "msds[0].regulations[k=1|X|Y|]"
    r = {**row(f"{item}.item_code", code), "Claude 원문 조각": snip}
    chip = bc([r], names=review_app._code_names(), comps=COMPS, labels={}, tips={}, pages=10, explain={},
                       code_match=review_app._code_match)[item]["parts"][0]
    assert review_app._code_match(code, snip)[1:] == ("", "") and not chip["warn"]
    r = {**r, "Claude 원문 조각": "특별관리대상물질 | 해당됨 (0.1% 이상 함유한 Benzene)", "Claude 값": "OSH_MANAGED"}   # 참: 긴 표기 안에만 있음
    assert "표기예요" in bc([r], names=review_app._code_names(), comps=COMPS, labels={}, tips={}, pages=10, explain={},
                                    code_match=review_app._code_match)[item]["parts"][0]["warn"]


def test_josa_after_english_word():
    item = "msds[0].toxicity[k=1|TX_ORAL|LD50|Rat]"
    rs = [row(f"{item}.comp_ref", '"1"'), row(f"{item}.endpoint", "TX_ORAL"), row(f"{item}.descriptor", "LD50"), row(f"{item}.species", "Rat"),
          row(f"{item}.q", rows_tox()[4]["Claude 값"])]
    c = bc(rs, names=NAMES, comps={"1": "Benzene"}, labels={}, tips={}, pages=10, explain={})[item]
    assert sentence(c) == "[Benzene] — [급성 독성(경구)] [Rat] 실험에서 [LD50]은 [2000 mg/kg 초과]"     # 받침을 모르면 조사 없이, 숫자 끝은 받침으로
    reg = "msds[0].regulations[k=1|OSH|X|]"
    c = bc([row(f"{reg}.comp_ref", '"1"'), row(f"{reg}.law", "OSH")], names=NAMES, comps={"1": "Benzene"}, labels={}, tips={}, pages=10, explain={})[reg]
    assert sentence(c) == "[Benzene]: [산업안전보건법]" and "은(는)" not in sentence(c)


def test_pair_tips():
    """칸 이름만 되풀이하지 않고 짝 풀이: 수치는 원문 표기와 부호 뜻, 해당 여부, 시험종 영어 이름, 여러 값 목록."""
    c = cards(rows_tox())["msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"]
    tip = {p["path"].rsplit(".", 1)[1]: p["tip"] for p in c["parts"] if p["t"] == "chip"}
    assert tip["q"] == "원문 ‘> 2000 mg/kg’ (> = 초과, ≥ = 이상, < = 미만, ≤ = 이하)"
    item = "msds[0].toxicity[k=1|TX_DERMAL|LD50|Guinea pig and rabbit]"
    c = bc([row(f"{item}.species", "Guinea pig and rabbit")], names=NAMES, comps=COMPS, labels={f"{item}.species": "시험종"},
                    tips={f"{item}.species": "시험종"}, pages=10, explain={})[item]
    assert next(p for p in c["parts"] if p["t"] == "chip")["tip"] == "Guinea pig = 기니피그 · rabbit = 토끼"
    reg = "msds[0].regulations[k=1|OSH|X|]"
    c = cards([row(f"{reg}.applicable", "비해당")])[reg]
    assert next(p for p in c["parts"] if p["t"] == "chip")["tip"] == "해당 = 이 규제에 걸림 · 비해당/해당없음 = 걸리지 않음"
    cmr = "msds[0].cmr[k=1|CARC|]"                                     # 상태 칸의 '해당 없음'은 규제 풀이가 아니라 상태 뜻
    c = cards([row(f"{cmr}.comp_ref", '"1"'), row(f"{cmr}.status", "해당없음")])[cmr]
    tip = {p["path"].rsplit(".", 1)[1]: p["tip"] for p in c["parts"] if p["t"] == "chip"}
    assert tip["status"] == "해당 없음 = 이 제품에는 맞지 않는 항목" and "규제" not in tip["status"]
    t = "msds[0].transport[k=해상]"
    c = cards([row(f"{t}.packing_group", "해당없음"), row(f"{t}.marine_pollutant", "비해당")])[t]
    tip = {p["path"].rsplit(".", 1)[1]: p["tip"] for p in c["parts"] if p["t"] == "chip"}
    assert "규제" not in tip["packing_group"] and tip["marine_pollutant"].startswith("해당 = 이 규제에 걸림")
    tx = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    assert next(p for p in cards([row(f"{tx}.status", "값있음")])[tx]["parts"] if p["t"] == "chip")["tip"] == "적혀 있음 = 원문에 이 값이 적혀 있음"
    comp = "msds[0].components[k=71-43-2]"
    c = bc([row(f"{comp}.synonyms", '["Benzol", "Benzole"]'), row(f"{comp}.ke_no", "KE-1")], names=NAMES, comps=COMPS,
                    labels={f"{comp}.synonyms": "관용명·이명", f"{comp}.ke_no": "KE 번호"},
                    tips={f"{comp}.synonyms": "관용명·이명", f"{comp}.ke_no": "KE 번호"}, pages=10, explain={})[comp]
    tip = {p["label"]: p["tip"] for p in c["parts"] if p["t"] == "chip"}
    assert tip == {"관용명·이명": "원문의 여러 값을 ‘ · ’로 나눠 적었어요", "KE 번호": ""}       # 칸 이름과 같은 풀이는 뺀다


def test_area_fallback_only_for_small_non_boolean():
    """값 상자가 없을 때 노란 상자를 대신 칠하는 것은 예·아니오 칸이 아니고 4줄 이하일 때만."""
    import review_app
    box = lambda n: {"area": [[0.1, 0.1 + 0.02 * i, 0.5, 0.015] for i in range(n)]}
    assert review_app._area_ok(row("msds[0].toxicity[k=1|TX_ORAL|LD50|쥐].species", "쥐"), box(2))
    assert not review_app._area_ok(row("msds[0].toxicity[k=1|TX_ORAL|LD50|쥐].species", "쥐"), box(5))
    assert not review_app._area_ok(row("msds[0].transport[k=공통].regulated", "true"), box(1))
    table_row = [[0.05 + 0.15 * i, 0.30 + 0.002 * (i % 3), 0.12, 0.012] for i in range(6)]   # 표 한 줄: 칸마다 y가 조금씩 다름
    assert review_app._lines(table_row) == 1 and review_app._lines(table_row + box(3)["area"]) == 4
    assert review_app._area_ok(row("msds[0].components[k=1].content_basis", "중량"), {"area": table_row})


def test_why_value_not_in_source():
    """원문에 칩 글자가 그대로 없으면 왜 그 값인지: 규정 이름 용어, 예·아니오 낱말, 못 찾으면 확인 부탁."""
    t = "msds[0].transport[k=육상]"
    rs = [{**row(f"{t}.mode", "육상"), "Claude 원문 조각": "KSSTDG | 가. 유엔번호 UN2733 | 해양오염물질 : 예"},
          {**row(f"{t}.marine_pollutant", "해당"), "Claude 원문 조각": "KSSTDG | 가. 유엔번호 UN2733 | 해양오염물질 : 예"},
          {**row(f"{t}.ems_fire", "F-E"), "Claude 원문 조각": "화재 시 : F-E"},
          {**row(f"{t}.shipping_name", "아민"), "Claude 원문 조각": "UN2733"}]
    tip = {p["path"].rsplit(".", 1)[1]: p["tip"] for p in cards(rs)[t]["parts"] if p["t"] == "chip"}
    assert tip["mode"] == "원문 ‘KSSTDG’ = 국내 위험물 운송 규정 이름 (육상)"
    assert tip["marine_pollutant"].endswith("원문 ‘예’ → 해당") and tip["ems_fire"] == ""
    assert tip["shipping_name"] == ""                                   # 정해진 값이 아니면 화면의 상자·점선 안내로 본다
    from review_cards import _why
    assert _why("해당", "UN1307 o-Xylene 해양오염물질") == "" and _why("비해당", "4 x 5L") == ""   # 한 글자 o·x는 예·아니오 근거가 아니다
    e = "msds[0].extras[k=8|한국OELs:피부호칭]"
    c = cards([row(f"{e}.title_raw", "한국 OELs: 피부 호칭")])[e]
    assert "피부 호칭 = 피부로 흡수될 수 있다는 표시" in next(p for p in c["parts"] if p["t"] == "chip")["tip"]


def test_glossary_has_common_terms():
    assert {"LD50", "LC50", "EC50", "NOEC", "TWA", "STEL", "BEI", "BCF"} <= GLOSSARY.keys()


def test_seq_single_value_group():
    """같은 항목 값이 1개뿐이면 순번 1은 맞다 (항목마다 1부터 다시 세는 physchem)."""
    import review_app
    ps = ["msds[0].physchem[k=MIX|PH].seq", "msds[0].physchem[k=MIX|FP].seq", "msds[0].physchem[k=MIX|FP#2].seq"]
    rows = [row(p, v) for p, v in zip(ps, ["1", "1", "2"])]
    one, two = review_app._explain(rows[0], rows, 10), review_app._explain(rows[1], rows, 10)
    assert "자동 확인" in one and "확인 필요" not in one and "자동 확인" in two
    bad = [row(ps[0], "2"), row(ps[1], "1")]
    assert "확인 필요" in review_app._explain(bad[0], bad, 10)         # 1개뿐인데 2번이면 여전히 틀림
    cs = [f"msds[0].components[k={c}].seq" for c in ("71-43-2", "108-88-3", "1330-20-7")]   # 키가 다 다른 목록: 1부터 다시 세는 목록이 아니다
    comp = [row(p, v) for p, v in zip(cs, ["1", "1", "2"])]
    assert all("확인 필요" in review_app._explain(r, comp, 10) for r in comp)
    comp = [row(p, "1") for p in cs]                                   # 모두 1: 성분 번호 잇기가 깨진다
    assert all("확인 필요" in review_app._explain(r, comp, 10) for r in comp)
    ex = [row(f"msds[0].extras[k={i}|t{i}].seq", "1") for i in range(3)]
    assert all("확인 필요" in review_app._explain(r, ex, 10) for r in ex)
    phys = [row(f"msds[0].physchem[k=MIX|{c}].seq", "1") for c in ("PH", "FP", "ODOR")]   # 물리화학적 특성은 항목마다 1부터
    assert all("자동 확인" in review_app._explain(r, phys, 10) for r in phys)


def test_locate_checks():
    import review_app
    from test_A_locate import page
    pg = page([(0, "12.환경에미치는영향")], [(0, "원문조각입니다")])
    area = {k for k, c in enumerate(pg.vt) if pg.line[k] == 1}
    ex = "msds[0].extras[k=1|a]"
    rows = [row(f"{ex}.title_raw", "a"), row(f"{ex}.section_no", "1"), row(f"{ex}.page", "2")]
    assert review_app._checks(pg, 3, rows, {f"{ex}.title_raw": area}) == {f"{ex}.section_no": "원문은 12항에 있음", f"{ex}.page": "원문은 3쪽에 있음"}
    ok = [row(f"{ex}.section_no", "12"), row(f"{ex}.page", "3")]
    assert review_app._checks(pg, 3, ok, {f"{ex}.title_raw": area}) == {}
    meta = [row("msds[0].meta.page_start", "1"), row("msds[0].meta.page_end", "11")]   # MSDS 시작·끝 쪽: 보는 쪽(3)과 달라도 경고 아님
    assert review_app._checks(pg, 3, meta, {"msds[0].meta.msds_no": area}) == {}
    assert review_app._checks(pg, 3, rows, {}) == {}                    # 이 쪽에서 못 찾았으면 말하지 않는다


def test_tip_is_plain():
    """칩 풀이는 쉬운 한두 줄: 스키마·정규식 말은 빼고, 값 풀이(성분명)를 먼저."""
    item = "msds[0].components[k=71-43-2]"
    rs = [row(f"{item}.cas_no", "71-43-2"), row(f"{item}.content", "10"), row(f"{item}.name", "벤젠")]
    tips = {rs[0]["경로"]: "^\\d{2,7}-\\d{2}-\\d$", rs[1]["경로"]: "Q 구조로 분해 (예: '20 ~ 30' → lower_op >=)", rs[2]["경로"]: "원문(한글 우선)"}
    c = bc(rs, names=NAMES, comps=COMPS, labels={}, tips=tips, pages=10, explain={})[item]
    tip = {p["path"].rsplit(".", 1)[1]: p["tip"] for p in c["parts"] if p["t"] == "chip"}
    assert tip == {"cas_no": "", "content": "", "name": "원문(한글 우선)"}
    tox = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    r = row(f"{tox}.comp_ref", '"1"')
    c = bc([r], names=NAMES, comps=COMPS, labels={}, tips={r["경로"]: "성분 seq 또는 'MIX'"}, pages=10,
                    explain={r["경로"]: "1번 성분: 벤젠 (CAS 71-43-2)"})[tox]
    assert c["parts"][0]["tip"] == "1번 성분: 벤젠 (CAS 71-43-2)"
    from review_cards import _plain, TIP_MAX
    assert _plain("TO21이 이 칸에 정한 값(국내, ACGIH) 중 하나 — 원문 표기를 이 값으로 옮김 (TO21 명세서: x)") == "고를 수 있는 값: 국내, ACGIH"
    assert _plain("TX_ORAL = 급성 독성(경구)") == "" and _plain("false = 아니오 — 참·거짓") == "" and _plain("성분 seq 또는 'MIX'") == ""
    long = bc([row(f"{item}.name", "벤젠")], names=NAMES, comps=COMPS, labels={}, tips={f"{item}.name": "가" * 300}, pages=10, explain={})[item]
    assert len(long["parts"][0]["tip"]) == TIP_MAX


def test_short_code_name_found_as_word():
    """세 글자 미만 이름('pH', '냄새')도 원문에 낱말로 있으면 이 코드의 표기다. 코드표의 값 형식('텍스트')은 이름이 아니다."""
    import review_app
    review_app._use_repo_data()
    assert "텍스트" not in review_app._code_names()["ODOR"] and "숫자" not in review_app._code_names()["PH"]
    assert review_app._code_match("ODOR", "2) 냄새 | 약한 특이한 냄새")[0] == "냄새"
    assert review_app._code_match("PH", "3) pH | 해당 없음")[0] == "pH"
    assert review_app._code_match("ODOR", "나. 냄  새 : 무 취")[0] == "냄  새"                # 글자 사이를 띄어 쓴 원문
    assert not any(x in n for n in review_app._code_names()["SOLUBILITY"] for x in ("숫자", "텍스트"))   # '숫자/텍스트'도 값 형식
    assert review_app._code_match("PH", "phosphate 3%")[0] == ""                    # 낱말 안의 글자는 아니다


def test_overlap_words_dropped():
    """칩 글이 틀 이음말로 끝나거나 앞 칩 끝 낱말로 시작하면 되풀이를 뺀다 ('CMR 분류 분류', '위험물안전관리법 위험물안전관리법 위험물')."""
    names = {**NAMES, "MOEL_CMR": ["고용노동부 고시 CMR 분류"], "DGL": ["위험물안전관리법"], "DGL_HAZ": ["위험물안전관리법 위험물"],
             "INTL": ["외국법·국제협약"], "INTL_CONV": ["국제협약(로테르담, 스톡홀름, 몬트리올)"]}
    cmr = "msds[0].cmr[k=1|CARC|MOEL_CMR]"
    c = bc([row(f"{cmr}.comp_ref", '"1"'), row(f"{cmr}.hazard", "발암성"), row(f"{cmr}.agency", "MOEL_CMR"), row(f"{cmr}.class", "1A")],
                    names=names, comps=COMPS, labels={}, tips={}, pages=10, explain={})[cmr]
    assert sentence(c) == "[벤젠]의 [발암성]: [고용노동부 고시 CMR 분류] [1A]"
    reg = "msds[0].regulations[k=MIX|DGL|DGL_HAZ|]"
    rs = [row(f"{reg}.comp_ref", "MIX"), row(f"{reg}.law", "DGL"), row(f"{reg}.item_code", "DGL_HAZ"), row(f"{reg}.applicable", "비해당")]
    c = bc(rs, names=names, comps=COMPS, labels={}, tips={}, pages=10, explain={})[reg]
    assert sentence(c) == "[제품 전체]는 [위험물안전관리법] [위험물]에 [비해당]"
    assert next(p for p in c["parts"] if p.get("text") == "위험물")["tip"].startswith("전체 이름: 위험물안전관리법 위험물")
    reg = "msds[0].regulations[k=MIX|INTL|INTL_CONV|]"
    rs = [row(f"{reg}.comp_ref", "MIX"), row(f"{reg}.law", "INTL"), row(f"{reg}.item_code", "INTL_CONV"), row(f"{reg}.applicable", "비해당")]
    c = bc(rs, names=names, comps=COMPS, labels={}, tips={}, pages=10, explain={})[reg]
    assert sentence(c) == "[제품 전체]는 [외국법·국제협약] [로테르담, 스톡홀름, 몬트리올]에 [비해당]"
    from review_cards import _lead
    assert _lead("산업안전보건법", "산업안전보건법시행령") == "산업안전보건법시행령"          # 낱말 경계가 아니면 그대로
    hs = "msds[0].hazard.h_statements[k=H302]"                          # 코드가 아닌 칩끼리는 떼지 않는다 (모델이 번호까지 문장에 넣은 실수가 보이게)
    c = cards([row(f"{hs}.code", "H302"), row(f"{hs}.text", "H302 삼키면 유해함")])[hs]
    assert sentence(c) == "[H302] [H302 삼키면 유해함]"


def test_plain_field_tips():
    """기술 말뿐인 명세 풀이 대신 처음 보는 사람용 풀이: 나라 약자, H 번호, 문구 원문, 결과기술, 예·아니오 조사."""
    reg = "msds[0].regulations[k=1|X|Y|US]"
    tips = {f"{reg}.country": "해외 규제일 때 ISO 3166-1 2자리(US, JP, EU)"}
    c = bc([row(f"{reg}.country", "US")], names=NAMES, comps=COMPS, labels={}, tips=tips, pages=10, explain={})[reg]
    assert next(p for p in c["parts"] if p["t"] == "chip")["tip"].startswith("규제한 나라·지역 약자 (US = 미국")
    hs = "msds[0].hazard.h_statements[k=H302]"
    c = bc([row(f"{hs}.code", "H302"), row(f"{hs}.text", "삼키면 유해함")], names=NAMES, comps=COMPS, labels={},
                    tips={f"{hs}.text": "원문", f"{hs}.code": "H코드(접미 문자 허용: H360FD, H361d)"}, pages=10, explain={})[hs]
    tip = {p["path"].rsplit(".", 1)[1]: p["tip"] for p in c["parts"] if p["t"] == "chip"}
    assert tip == {"code": "유해·위험 문구 번호 (H로 시작). 원문의 번호와 같은지 보세요", "text": "이 번호의 원문 문장 그대로"}
    tx = "msds[0].toxicity[k=1|TX_ORAL|결과기술|]"
    assert next(p for p in cards([row(f"{tx}.descriptor", "결과기술")])[tx]["parts"] if p["t"] == "chip")["tip"] == "수치 없이 시험 결과를 글로 적은 것"
    x = "msds[0].composition"
    c = cards([row(f"{x}.odd_flag", "false"), row(f"{x}.no_hazardous_component", "false")])[x]
    tip = {p["path"].rsplit(".", 1)[1]: p["tip"] for p in c["parts"] if p["t"] == "chip"}
    assert "‘odd_flag’ 표시가 없어서" in tip["odd_flag"] and "뜻의 말이 없어서" in tip["no_hazardous_component"]


def test_fixed_chip_describes_current_value():
    """고친 칩(수정·누락 추가)의 글·풀이·⚠는 수정값과 그 근거 줄로, 삭제·채택 줄은 AI 값으로 (엑셀에 남은 수정값은 값이 아니다)."""
    from review_cards import _cell_now
    t = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    names = {"TX_ORAL": ["급성 독성(경구)"], "TX_DERMAL": ["급성 독성(경피)"]}
    fix = lambda r, v, src: {**r, "검수 결과": "수정", "수정값": v, "수정 원문 조각": src, "수정 쪽": "3"}
    rs = [fix(row(f"{t}.comp_ref", '"5"'), '"2"', "톨루엔 경피"),
          fix({**row(f"{t}.endpoint", "TX_ORAL"), "Claude 원문 조각": "경구 LD50"}, "TX_DERMAL", "경피 LD50 > 2000 mg/kg")]
    c = bc(rs, names=names, comps={"1": "벤젠", "2": "톨루엔"}, labels={}, tips={}, pages=10, explain={})[t]
    chip = {p["path"].rsplit(".", 1)[1]: p for p in c["parts"] if p["t"] == "chip"}
    assert (chip["comp_ref"]["text"], chip["comp_ref"]["warn"]) == ("톨루엔", "")
    assert chip["endpoint"]["text"] == "급성 독성(경피)" and "경피" in chip["endpoint"]["tip"] and "경구" not in chip["endpoint"]["tip"]
    leftover = {**row(f"{t}.species", "쥐"), "수정값": "랫드"}
    assert _cell_now({**leftover, "검수 결과": "Claude 채택"}) == "쥐" and _cell_now({**leftover, "검수 결과": "삭제"}) == "쥐"
    assert _cell_now({**leftover, "검수 결과": "수정"}) == "랫드" and _cell_now(leftover) == "쥐"


def test_code_tip_not_added_when_reason_found():
    """원문에서 근거(‘경피’ → 급성 독성(경피))를 찾은 코드 칩에는 '원문의 어느 말인지 확인해 주세요'를 붙이지 않는다."""
    t = "msds[0].toxicity[k=1|TX_DERMAL|LD50|]"
    r = {**row(f"{t}.endpoint", "TX_DERMAL"), "Claude 원문 조각": "경피 | LD50 | > 2000 mg/kg"}
    tip = bc([r], names={"TX_DERMAL": ["급성 독성(경피)"]}, comps=COMPS, labels={}, tips={}, pages=10, explain={})[t]["parts"][0]["tip"]
    assert "원문 ‘경피’ → 급성 독성(경피)" in tip and "정해진 이름이에요" not in tip


def test_seq_gap_only_for_out_of_scope_items(monkeypatch):
    """순번이 건너뛰면 그 번호가 실버에서 검수 범위 밖 항 항목일 때만 자동 확인. 아니면 '순번 3이 빠졌어요'."""
    import review_app
    comp = [row(f"msds[0].components[k={c}].seq", v) for c, v in (("71-43-2", "1"), ("108-88-3", "2"), ("1330-20-7", "4"))]
    assert all("순번 3이 빠졌어요" in review_app._explain(r, comp, 10, "X") and "확인 필요" in review_app._explain(r, comp, 10, "X") for r in comp)
    ex = [row(f"msds[0].extras[k={n}|t{n}].seq", v) for n, v in ((2, "1"), (8, "3"))]
    monkeypatch.setattr(review_app, "_out_seqs", lambda doc, t="claude": {"msds[0].extras": {2}} if doc == "X" and t == "claude" else {})
    assert all("자동 확인" in review_app._explain(r, ex, 10, "X") for r in ex)            # 2번은 범위 밖 항(예: 4항)의 항목
    assert "순번 2가 빠졌어요" in review_app._explain(ex[1], ex, 10, "Y")
    gpt = [{**r, "Claude 값": "", "GPT 값": r["Claude 값"]} for r in ex]                   # 이 줄 모델(GPT)의 실버만 본다 (두 모델 합집합이 아님)
    assert "순번 2가 빠졌어요" in review_app._explain(gpt[1], gpt, 10, "X")


def test_out_seqs_reread_when_silver_changes(tmp_path, monkeypatch):
    """범위 밖 순번은 실버 파일이 바뀌면 다시 읽는다 (캐시 키에 수정 시각)."""
    import os
    import review_app
    f = tmp_path / "s.json"
    monkeypatch.setattr(review_app.paths, "silver_path", lambda t, d: f if t == "claude" else tmp_path / "없음.json")
    put = lambda sec, ns: (f.write_text(json.dumps({"msds": [{"extras": [{"seq": 2, "section_no": sec, "title_raw": "a"}]}]})), os.utime(f, ns=(ns, ns)))
    put(4, 10**18)
    assert review_app._out_seqs("Z") == {"msds[0].extras": {2}}                         # 4항은 검수 범위 밖
    put(8, 2 * 10**18)
    assert review_app._out_seqs("Z") == {} and review_app._out_seqs("Z", "gpt") == {}


def test_seq_order_follows_silver_not_sheet(monkeypatch):
    """엑셀에서 경로로 정렬해 줄 순서가 바뀌어도 순번 확인은 실버 순서로 (⚠가 생기지 않는다)."""
    import review_app
    comp = [row(f"msds[0].components[k={c}].seq", v) for c, v in (("71-43-2", "1"), ("108-88-3", "2"), ("1330-20-7", "3"))]
    sheet = sorted(comp, key=lambda r: r["경로"])                                       # 108-88-3, 1330-20-7, 71-43-2
    monkeypatch.setattr(review_app, "silver_rank", lambda doc: {r["경로"]: i for i, r in enumerate(comp)} if doc == "X" else {})
    assert all("자동 확인" in review_app._explain(r, sheet, 10, "X") for r in sheet)
    assert "확인 필요" in review_app._explain(sheet[0], sheet, 10, "Y")                 # 실버가 없으면 검수표 줄 순서 그대로


def test_odd_excel_results_are_warned():
    """엑셀로만 생기는 판단: '수정'인데 수정값이 빔(골드 None), 값이 없는 쪽을 채택(골드는 삭제) → 숨길 칸이어도 ⚠ 칩. 줄은 한 번씩."""
    from msds.review.build_gold import _decide
    t = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]"
    rs = [{**row(f"{t}.descriptor", "LD50"), "검수 결과": "수정"}, {**row(f"{t}.species", "쥐"), "검수 결과": "GPT 채택", "일치": "Claude만"},
          {**row(f"{t}.status", "값있음"), "검수 결과": "GPT 채택", "일치": "Claude만"}, row(f"{t}.endpoint", "TX_ORAL")]
    c = cards(rs)[t]
    warn = {p["path"].rsplit(".", 1)[1]: p["warn"] for p in c["parts"] if p["t"] == "chip"}
    assert warn["descriptor"].startswith("이 칸은 고친 값이 비어 있어 골드에서 빈칸이 돼요. ‘다른 칩이 있어요’")
    assert warn["species"] == warn["status"] and warn["species"].startswith("이 칸은 고른 값이 없어 골드에서 이 항목이 통째로 빠져요.")
    assert not any("채택" in w for w in warn.values())                                    # 내부 말('GPT 채택') 없이
    assert "이 칸이 비어요" in cards([{**row("msds[0].meta.msds_no", "1"), "검수 결과": "GPT 채택"}])["msds[0].meta"]["parts"][-1]["warn"]
    assert not warn["endpoint"] and not c["auto"]
    assert _decide(rs[1], "Claude")[0] == "del" and _decide(rs[0], "Claude")[1] is None      # 골드는 정말 그렇게 만든다


def test_lead_trim_keeps_term_tip():
    """앞 칩과 겹친 낱말을 뗀 코드 칩: 원문에 뗀 이름이 있으면 '어느 말인지' 부탁만 빼고 용어 풀이는 둔다."""
    names = {**NAMES, "L_IMDG": ["IMDG"], "L_IMDG_MP": ["IMDG 해양오염물질"]}
    reg = "msds[0].regulations[k=MIX|L_IMDG|L_IMDG_MP|]"
    rs = [row(f"{reg}.comp_ref", "MIX"), row(f"{reg}.law", "L_IMDG"), {**row(f"{reg}.item_code", "L_IMDG_MP"), "Claude 원문 조각": "해양오염물질 : 해당"}]
    c = bc(rs, names=names, comps=COMPS, labels={}, tips={}, pages=10, explain={})[reg]
    tip = next(p for p in c["parts"] if p.get("text") == "해양오염물질")["tip"]
    assert tip.startswith("전체 이름: IMDG 해양오염물질") and "IMDG = 국제 해상" in tip and "정해진 이름이에요" not in tip


def test_no_dangling_josa():
    """뒤 칸이 없는 틀 조각의 조사로 문장이 끝나지 않는다 ('… [LD50]은' → '… [LD50]')."""
    t = "msds[0].toxicity[k=MIX|TX_ORAL|LD50|토끼]"
    c = cards([row(f"{t}.comp_ref", "MIX"), row(f"{t}.endpoint", "TX_ORAL"), row(f"{t}.descriptor", "LD50"), row(f"{t}.species", "토끼")])[t]
    assert sentence(c) == "[제품 전체]를 [급성 독성(경구)] [토끼] 실험에서 [LD50]"


def _seqs(*vals, **kw):
    return [row(f"msds[0].components[k={c}].seq", v) for c, v in zip(("71-43-2", "108-88-3", "1330-20-7", "64742-94-5"), vals)]


def test_seq_check_uses_current_values():
    """순번 확인은 모든 형제의 지금 값으로 (고친 줄은 수정값, 사람이 넣은 항목 포함, 삭제한 줄 제외)."""
    import review_app
    ex = lambda rs, i: review_app._explain(rs[i], rs, 10, "")
    fix = lambda r, v: {**r, "검수 결과": "수정", "수정값": v}
    rs = _seqs("1", "2", "3", "9")
    assert "확인 필요" in ex(rs, 3)                                                       # 9는 틀림
    rs[3] = fix(rs[3], "4")
    assert all("자동 확인" in ex(rs, i) for i in range(4))                                # 9→4로 바르게 고치면 ⚠ 없음
    bad = _seqs("1", "2", "3")
    bad[1] = fix(bad[1], "7")
    assert "확인 필요" in ex(bad, 1) and "확인 필요" in ex(bad, 2)                          # 2→7로 잘못 고치면 ⚠
    add = _seqs("1", "2", "3") + [{**row("msds[0].components[k=50-00-0].seq", ""), "검수 결과": "누락 추가", "수정값": "4"}]
    assert all("자동 확인" in ex(add, i) for i in range(4))                               # 사람이 넣은 성분(순번 4): 다른 성분 ⚠ 0
    gone = _seqs("1", "2", "3")
    gone[2] = {**gone[2], "검수 결과": "삭제"}
    gone.append(row("msds[0].components[k=64742-94-5].seq", "3"))
    assert all("자동 확인" in ex(gone, i) for i in range(4))                              # 삭제한 줄은 형제로 세지 않는다


def test_dropped_items_follow_gold_rule():
    """골드 규칙(build_gold._assemble): 목록 항목 안 줄 하나라도 '삭제'(또는 값 없는 모델 채택)면 항목째 빠짐, 항목 자체인 한 칸이 빈 값이면 그 항목.
    화면은 같은 판단으로 카드에 표시하고, 성분명 표·순번 형제에서 뺀다."""
    import review_app
    from review_cards import dropped
    t, comp2 = "msds[0].toxicity[k=1|TX_ORAL|LD50|쥐]", "msds[0].components[k=108-88-3]"
    rs = [row(f"{t}.descriptor", "LD50"), {**row(f"{t}.species", "쥐"), "검수 결과": "삭제"}, {**row("msds[0].meta.msds_no", "AA"), "검수 결과": "삭제"},
          {**row("msds[0].hazard.other_hazards[0]", '{"value": "x"}'), "검수 결과": "수정"},
          {**row("msds[0].companies[k=제조자|가나].name", "가나"), "검수 결과": "GPT 채택", "일치": "Claude만"}]
    assert dropped(rs, "gpt") == {t: [f"{t}.species"], "msds[0].hazard.other_hazards[0]": ["msds[0].hazard.other_hazards[0]"],
                           "msds[0].companies[k=제조자|가나]": ["msds[0].companies[k=제조자|가나].name"]}   # meta(목록 아님)는 칸만
    c = cards(rs)
    assert c[t]["drop"] == {"by": [f"{t}.species"], "all": False} and c["msds[0].meta"]["drop"] is None
    assert "항목이 빠져요" in next(p for p in c["msds[0].hazard.other_hazards[0]"]["parts"] if p["t"] == "chip")["warn"]   # 문장 한 칸짜리 항목
    comps = _seqs("1", "2", "3") + [row("msds[0].components[k=71-43-2].name", "벤젠"), {**row(f"{comp2}.name", "톨루엔"), "검수 결과": "삭제"}]
    opts = review_app._comp_options(comps, dropped(comps, "gpt"))["0"]
    assert [o[0] for o in opts] == ["MIX", "1", "3"]                                    # 골드에서 빠지는 2번은 고를 수 없다
    from review_cards import comps_from_rows
    cf = comps_from_rows(comps, dropped(comps, "gpt"))
    assert cf["0|2"] == "" and cf["0|1"] == "벤젠"                                       # 빠지는 성분: 이름 없이 표시만 (카드 ⚠)
    t2 = "msds[0].toxicity[k=108-88-3|TX_ORAL|LD50|]"
    c2 = build_cards([row(f"{t2}.comp_ref", '"2"')], names=NAMES, comps=cf, labels={}, tips={}, pages=10, explain={}, drop={})[t2]
    assert c2["parts"][0]["warn"].startswith("가리키는 성분이 골드에서 빠져요")
    ex = lambda i: review_app._explain(comps[i], comps, 10, "")
    assert "골드에서 빠져" in ex(1) and "순번 2가 빠졌어요" in ex(2)                          # 골드처럼 2번 성분이 빠지면 1, 3만 남는다
    assert "2번 성분" in review_app._explain(row(f"{t}.comp_ref", '"2"'), comps, 10, "") and "톨루엔" not in review_app._explain(row(f"{t}.comp_ref", '"2"'), comps, 10, "")


def test_added_item_sits_at_its_seq():
    """사람이 넣은 항목은 지금 순번 값 자리에 (실버 항목은 실버 순서): 빠진 성분을 3번에 넣고 3·4를 4·5로 고치면 ⚠ 0."""
    import review_app
    fix = lambda r, v: {**r, "검수 결과": "수정", "수정값": v}
    rs = _seqs("1", "2", "3", "4")
    rs[2], rs[3] = fix(rs[2], "4"), fix(rs[3], "5")
    rs.append({**row("msds[0].components[k=50-00-0].seq", ""), "검수 결과": "누락 추가", "수정값": "3"})
    assert all("자동 확인" in review_app._explain(r, rs, 10, "") for r in rs)
    late = rs[:4] + [{**rs[4], "수정값": "9"}]
    assert "확인 필요" in review_app._explain(late[4], late, 10, "")                         # 넣은 순번이 틀리면 ⚠


def _ov(pairs, count=lambda p, s: 1, **kw):
    """겹침 판정: pairs = [(카드 키, 표 이름 줄)...] 모두 같은 쪽·같은 원문 줄."""
    from review_cards import overlaps
    rows = [{**row(f"{k}.x", "v"), "칸 이름": t, "Claude 쪽": "3", "Claude 원문 조각": "다. 위험물안전관리법에 의한 규제 해당없음", **kw} for k, t in pairs]
    return overlaps(rows, count)


@pytest.mark.parametrize("a,b,keep", [
    ("msds[0].regulations[k=MIX|DG|DG_HAZMAT|]", "msds[0].dangerous_goods[k=MIX|x|]", "other"),
    ("msds[0].regulations[k=MIX|WASTE|W|]", "msds[0].waste[k=MIX|x|]", "other"),
    ("msds[0].toxicity[k=1|TX_CARC|a|]", "msds[0].cmr[k=1|IARC|]", "other"),
    ("msds[0].ecotox[k=1|E|a|]", "msds[0].narratives[k=S12]", "this"),
    ("msds[0].intl_class[k=1|EU|]", "msds[0].regulations[k=MIX|INTL|X|]", "this"),
    ("msds[0].toxicity[k=1|TX_ORAL|a|]", "msds[0].narratives[k=S11_ROUTE]", "other"),
    ("msds[0].extras[k=1|a]", "msds[0].physchem[k=1|bp]", "other"),
    ("msds[0].hazard[k=a]", "msds[0].companies[k=b]", None),                    # 규칙 없는 쌍: 안내만
])
def test_overlap_rules(a, b, keep):
    out = _ov([(a, "A 카드 · x"), (b, "B 카드 · x")])
    assert out[a][0]["keep"] == keep and out[a][0]["other_key"] == b and out[a][0]["other_title"] == "B 카드"
    assert out[b][0]["keep"] == {"other": "this", "this": "other", None: None}[keep]
    assert bool(out[a][0]["why"]) == (keep is not None)


def test_overlap_not_overlap():
    pair = [("msds[0].ecotox[k=1|E|a|]", "e"), ("msds[0].narratives[k=S12]", "n")]
    assert _ov(pair, count=lambda p, s: 2) == {}                                   # 쪽 글자에 두 번 = 다른 줄일 수 있음
    assert _ov(pair, count=lambda p, s: 0) == {}
    assert _ov([("msds[0].components[k=1]", "c"), ("msds[0].composition", "d")]) == {}   # 다른 칸을 같은 줄에서 읽음
    assert _ov([("msds[0].ecotox[k=1|E|a|]", "e"), ("msds[0].toxicity[k=1|TX_ORAL|a|]", "t")]) == {}
    assert _ov([("msds[0].toxicity[k=1|a]", "t"), ("msds[0].toxicity[k=2|a]", "t")]) == {}   # 같은 표
    assert _ov(pair, **{"Claude 쪽": "4"}) != {} and _ov([pair[0]]) == {}
    assert _ov(pair, **{"Claude 원문 조각": "짧아요"}) == {}                         # 6글자 미만


def test_overlap_gone_after_delete():
    from review_cards import overlaps
    a, b = "msds[0].regulations[k=MIX|DG|DG_HAZMAT|]", "msds[0].dangerous_goods[k=MIX|x|]"
    rows = [{**row(f"{k}.x", "v"), "Claude 쪽": "3", "Claude 원문 조각": "다. 위험물안전관리법에 의한 규제 해당없음"} for k in (a, b)]
    assert overlaps(rows, lambda p, s: 1)[a][0]["keep"] == "other"
    rows[0]["검수 결과"] = "삭제"
    assert overlaps(rows, lambda p, s: 1) == {}                                    # 한쪽이 지워지면 띠 사라짐


def test_overlap_all_sheets():
    """전수: 겹침 판정 예외 0, 줄은 여전히 정확히 한 번, 맞는 쪽과 안내 쪽이 짝."""
    import review_app
    review_app._use_repo_data()
    docs = sorted(review_app.paths.REVIEW.glob("*.xlsx"))
    if not docs:
        pytest.skip("검수표 없음")
    old = review_app._LOCATOR
    try:
        for f in docs:
            rows = review_app.Sheet(f.stem).rows()
            review_app._LOCATOR = review_app.Locator(f.stem)
            v = review_app._view(rows, f.stem)
            seen = Counter(x["path"] for c in v["cards"].values() for x in [*(p for p in c["parts"] if p["t"] == "chip"), *c["auto"], *c["meta"]])
            assert seen == Counter(r["경로"] for r in rows), f.stem
            for k, c in v["cards"].items():
                for o in c["overlap"]:
                    back = next(x for x in v["cards"][o["other_key"]]["overlap"] if x["other_key"] == k)
                    assert back["keep"] == {"this": "other", "other": "this", None: None}[o["keep"]], (f.stem, k)
    finally:
        review_app._LOCATOR = old
