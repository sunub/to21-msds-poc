"""15항 판정: 성분 함량과 지식DB 규제 기준으로 해당 여부를 정하고 MSDS 15항과 비교해 판정·유형·심각도를 붙인다.

근거: 설계서 7장(유형·심각도), 27·28장(판정 FLOW·기준 농도 비교), 29장(위험물 제4류), 30장(유형), 10/30 결정 D4,
11/01 F 결정 1~5와 11/02 결정 6~11(작업 기록 '15항 사전 분석과 결정'). 기대 해당 여부 계산은 정민의 sec15._expected(ADR 0004)를 그대로 쓴다.

    judge_sec15(inputs, provider) → {"verdicts": [...], "excluded": [...]}
    inputs: loader.load_inputs 결과. provider: get_regulation(cas_no, as_of) 를 가진 지식 제공자(htodb.regulation)

판정 줄 모양은 2항(mixture.verdict)과 맞춘다: verdict(일치·불일치·경계·근거부족), type, severity, rule_id, reason, assumptions.
excluded 는 판정하지 않고 참고로만 보여 줄 줄이다(구버전, DB 값 확인 필요, 지위 정보, 폐기물).
결정 6: 금지물질(reg_map kind=compare_human)은 함량상 해당이어도 MSDS가 비해당이면 '규제 누락'으로 단정하지 않고 경계.
결정 7: 단일물질 제품에서 제품 전체(MIX)로 적은 성분 규제 행은 그 성분의 행으로, 성분에 적은 위험물·폐기물 행은 제품 행으로 본다.
결정 8: 항목 코드 없이 법 단위로 적은 행은 판정하지 않고, '비해당'이면 같은 성분(혼합물의 제품 전체 행이면 모든 성분)·같은 법의
        항목별 판정에 이어 쓴다.
결정 10: PSM 행이 '인화성 액체·가스' 범주(제품 인화성·취급량으로 정해짐)면 판정하지 않고 참고.
결정 11: 지식DB 조문에 성상 조건이 있으면 MSDS 비해당을 규제 누락으로 단정하지 않고 경계, pH 조건은 9항 제품 pH로 확인.
결정 9: 혼합물에서 제품 전체(MIX)로 적은 항목 행은, 성분별 행이 없는 성분의 같은 항목 판정에 이어 쓴다. 제품 전체 '해당'은
        다른 성분 때문일 수 있어, 함량상 비해당인 성분에는 과기재로 세지 않는다.
"""
import re
from functools import lru_cache

import yaml

from .classifier import effective_components
from .htodb.regulation import covered_items
from .mixture.params import RULES_DIR, param_list
from .mixture.rule_eval import evaluate_rules_trace
from .sec15 import _expected, as_percent
from .trace import cause as _cause

_INF = float("inf")


@lru_cache
def _dg_table() -> dict:
    """rules/dg_class4.yaml (규칙표 v0.3, 위험물안전관리법 시행령 별표1). 전에는 같은 기준을 코드에 적어 두었다(11/02 F)."""
    with open(RULES_DIR / "dg_class4.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

MATCH, MISMATCH, BORDER, LACK = "일치", "불일치", "경계", "근거부족"
# 설계서 7장 · 규칙표 v0.3 severity.yaml (15항)
MISSING, THRESHOLD, EXTRA, KREACH_MISSING = "규제 누락", "기준 불일치", "과기재", "화평법 항목 누락"
SEVERITY = {MISSING: "높음", THRESHOLD: "중간", EXTRA: "낮음", KREACH_MISSING: "중간"}
SV = {MISSING: "SV-02", THRESHOLD: "SV-04", EXTRA: "SV-08", KREACH_MISSING: "SV-04"}
RULE_IDS = {"match": "S15-1", MISSING: "S15-2", THRESHOLD: "S15-3", EXTRA: "S15-4", "border": "S15-5", "lack": "S15-6",
            KREACH_MISSING: "S15-7"}
# 차이 원인 코드(trace.CAUSE_TEXT). 경계는 함량이 기준에 걸칠 때 RANGE_EDGE, 조문 조건 때문이면 CONDITION_CHECK(_row 의 cause)
CAUSE = {MISSING: "REG_MISSING", KREACH_MISSING: "REG_MISSING", THRESHOLD: "THRESHOLD_DIFF", EXTRA: "OVER_STATED", LACK: "NO_BASIS", BORDER: "RANGE_EDGE"}
NEW_CCA = {"CCA_ACUTE", "CCA_CHRONIC", "CCA_ECO"}
BASE_ASSUMPTIONS = [
    "rule_id(S15-1~7)는 설계서에 없어 우리 쪽 번호를 씀. 유형·심각도는 설계서 7장(severity.yaml SV-02·04·08)",
    "지식DB가 다루는 항목인데 그 성분에 규제 행이 없으면 비해당으로 봄(설계서 27장 '규제DB 비해당')",
    "같은 항목에 기준이 여럿이면 가장 낮은 값을 씀. vol% 기준은 중량%로 비교(설계서 미결 7)",
]


def _straddle_text(q, rows, results):
    """함량 범위가 기준에 걸칠 때 원인 문장(11/02 F 설명 4차). 경계를 낸 기준 행 중 가장 낮은 기준으로 쓴다.
    sec15._expected 와 같이 하한이 없으면 0, 상한이 없으면 100으로 본다."""
    border = [r for r, (e, _) in zip(rows, results) if e == "경계" and r.get("threshold_value") is not None]
    if not border:
        return None
    r = min(border, key=lambda x: x["threshold_value"])
    q = as_percent(q)
    v = q.get("value")
    lo = v if v is not None else (q.get("lower") if q.get("lower") is not None else 0)
    hi = v if v is not None else (q.get("upper") if q.get("upper") is not None else 100)
    t, op = r["threshold_value"], r.get("threshold_op") or ">="
    return (f"함량 범위 {lo:g}~{hi:g}% 중 하한 {lo:g}%는 기준({op} {t:g}%)에 못 미치고 상한 {hi:g}%는 기준을 충족해, "
            "실제 함량에 따라 해당 여부가 갈리는 경계")  # '갈림'은 LLM이 '갈림니다'로 바꿈(6차)


def _row(comp_ref, cas, law, item, verdict, rule_id, *, type_=None, supplier=None, expected=None, msds_threshold=None,
         db_threshold=None, reason="", source=(), version=None, as_of=None, extra_asm=(), db_text=(), cause=None,
         cause_text=None):
    code = cause or CAUSE.get(type_) or CAUSE.get(verdict)
    return {"section": "15", "comp_ref": comp_ref, "cas_no": cas, "law": law, "item_code": item, "verdict": verdict,
            "type": type_, "severity": SEVERITY.get(type_), "sv_id": SV.get(type_), "rule_id": rule_id,
            "msds_value": supplier, "msds_threshold": msds_threshold, "expected": expected, "db_threshold": db_threshold,
            "reason": reason, "source": list(source), "db_text": list(db_text), "knowledge_version": version,
            "as_of": as_of, "assumptions": BASE_ASSUMPTIONS + list(extra_asm),
            "causes": [] if verdict == MATCH or not code else [_cause(code, cause_text or reason)]}


def _excl(comp_ref, cas, law, item, status, reason, supplier=None, source=()):
    return {"section": "15", "comp_ref": comp_ref, "cas_no": cas, "law": law, "item_code": item, "status": status,
            "msds_value": supplier, "reason": reason, "source": list(source)}


def _fmt(op, v, unit="%"):
    return None if v is None else f"{op or '>='} {v:g}{unit or ''}"


def _msds_threshold(r):
    """MSDS 15항 행에 적힌 기준 농도 (op, 값). 없으면 None."""
    q = (r or {}).get("threshold") or {}
    if q.get("unit") not in ("%", None) or q.get("lower") is None and q.get("value") is None:
        return None
    if q.get("value") is not None:
        return ">=", q["value"]
    return q.get("lower_op") or ">=", q["lower"]


def _supplier(regs, single_ref=None):
    """MSDS 15항 행 → {(comp_ref, law, item): 행}. 결정 4: applicable 이 비었는데 값이 적혀 있으면 해당으로 본다.

    single_ref: 단일물질 제품이면 그 성분 번호. 제품 전체(MIX)로 적은 성분 규제 행을 그 성분의 행으로 본다(위험물·폐기물 제외).
    """
    out = {}
    for r in regs or []:
        if r.get("law") == "INTL":
            continue
        r = dict(r)
        r["_asm"] = []
        product_item = r.get("item_code") in ("DG_HAZMAT", "WASTE_DESIG")
        if single_ref and str(r.get("comp_ref")) == "MIX" and not product_item:
            if (single_ref, r.get("law"), r.get("item_code")) in out:
                continue
            r["comp_ref"] = single_ref
            r["_asm"].append("단일물질 제품이라 제품 전체(MIX)로 적은 행을 그 성분의 행으로 봄(11/02 F 결정 7)")
        elif single_ref and str(r.get("comp_ref")) == single_ref and product_item:
            if ("MIX", r.get("law"), r.get("item_code")) in out:
                continue
            r["comp_ref"] = "MIX"
            r["_asm"].append("단일물질 제품이라 성분에 적은 위험물·폐기물 행을 제품 행으로 봄(11/02 F 결정 7)")
        if r.get("applicable") is None and (r.get("value_raw") or r.get("threshold")):
            r["applicable"] = "해당"
            r["_asm"] += [f"MSDS 칸은 비었지만 값('{r.get('value_raw') or (r.get('threshold') or {}).get('raw')}')이 적혀 있어 "
                         "해당으로 봄(11/01 F 결정 4)"]
        out[(str(r.get("comp_ref")), r.get("law"), r.get("item_code"))] = r
    # '해당됨 (1% 이상 함유한 황산(특별관리물질))'처럼 관리대상 행의 비고로 적는 문서가 있다 (T21-025)
    for (ref, law, item), r in list(out.items()):
        note = str(r.get("remark") or "") + str(r.get("value_raw") or "")
        if item == "OSH_MANAGED" and r.get("applicable") == "해당" and "특별관리" in note \
                and not re.search(r"아님|비\s*해당|미해당|제외|해당\s*없|없음|비대상|특별관리[^\s]*\s*[:：]?\s*[X×]", note):
            out.setdefault((ref, law, "OSH_SPECIAL"), {**r, "item_code": "OSH_SPECIAL", "threshold": None, "_asm": r["_asm"] + [
                "관리대상유해물질 행의 비고에 적은 특별관리물질을 해당으로 봄"]})
    return out


_KREACH_WORDS = re.compile(r"화학물질\s*의?\s*등록\s*[·ㆍ및,]?\s*평가|화평법|K-?REACH", re.I)
KREACH_LINE_FROM = "2025-08-07"  # 고시 별표 4 제15호 다목 시행일. 종전 서식도 화평법 현황은 적어야 한다 (부칙 제2조·제3조)
_NOT_READ = "15항에서 읽은 규제 행이 없어 누락인지 추출 실패인지 정할 수 없음"


def _judge_component(key, s_row, comp, know, db_rows, covered, ph=None, sec15_read=True):
    ref_no, law, item = key
    cas = comp.get("cas_no")
    s = (s_row or {}).get("applicable")
    asm = list((s_row or {}).get("_asm", []))
    version = know.get("knowledge_version") if know else None
    as_of = know.get("as_of") if know else None
    mt = _msds_threshold(s_row)
    texts = list(dict.fromkeys(x for r in db_rows for x in r.get("db_text") or []))
    common = dict(supplier=s, msds_threshold=_fmt(*mt) if mt else None, version=version, as_of=as_of, extra_asm=asm,
                  source=[r["source"] for r in db_rows], db_text=texts)
    if not cas:
        return _row(ref_no, cas, law, item, LACK, RULE_IDS["lack"], reason="성분 CAS가 없어 기준을 조회하지 못함", **common)
    if not version:
        return _row(ref_no, cas, law, item, LACK, RULE_IDS["lack"],
                    reason=(know or {}).get("reason") or "기준 지식이 없음", **common)
    if not db_rows:
        if item not in covered:  # POPS, CCA_PERMIT, KR_ETC 등 지식DB가 다루지 않는 항목
            if s == "해당":
                return _row(ref_no, cas, law, item, LACK, RULE_IDS["lack"],
                            reason="지식DB가 다루지 않는 규제 항목이라 해당 여부를 확인할 수 없음", **common)
            return _row(ref_no, cas, law, item, MATCH, RULE_IDS["match"], expected=None,
                        reason="지식DB가 다루지 않는 항목, MSDS 비해당·미기재", **common)
        if s == "해당":
            return _row(ref_no, cas, law, item, MISMATCH, RULE_IDS[EXTRA], type_=EXTRA, expected="비해당",
                        reason="지식DB에 이 성분의 규제 행이 없는데 MSDS는 해당", **common)
        return _row(ref_no, cas, law, item, MATCH, RULE_IDS["match"], expected="비해당", reason="둘 다 비해당", **common)
    results = [_expected(comp.get("content"), {**r}) for r in db_rows]
    found = [e for e, _ in results if e]
    exp = "해당" if "해당" in found else "경계" if "경계" in found else "비해당" if found else None
    basis = "; ".join(b for _, b in results)
    best = min((r for r in db_rows if r["threshold_value"] is not None), key=lambda r: r["threshold_value"], default=None)
    dbt = _fmt(best["threshold_op"], best["threshold_value"]) if best else "기준 농도 없음(함유하면 해당)"
    common["db_threshold"] = dbt
    if exp is None:
        return _row(ref_no, cas, law, item, LACK, RULE_IDS["lack"], reason=basis, **common)
    # 결정 11: 조문에 붙은 조건(성상, pH)
    cond = [r.get("condition") or {} for r in db_rows]
    state = next((c["state"] for c in cond if c.get("state")), None)
    ph_max = next((c["ph_max"] for c in cond if c.get("ph_max") is not None), None)
    if ph_max is not None and exp in ("해당", "경계"):
        if ph is not None and ph > ph_max:
            exp, basis = "비해당", f"{basis}; 조문 조건 pH {ph_max:g} 이하인데 9항 pH {ph:g} (11/02 F 결정 11)"
        elif ph is not None:
            asm.append(f"조문 조건 pH {ph_max:g} 이하를 9항 pH {ph:g}로 충족(11/02 F 결정 11)")
    if exp == "경계":
        return _row(ref_no, cas, law, item, BORDER, RULE_IDS["border"], expected=exp, reason=basis,
                    cause_text=_straddle_text(comp.get("content"), db_rows, results) or basis, **common)
    if exp == "해당":
        if s != "해당" and not sec15_read:
            return _row(ref_no, cas, law, item, LACK, RULE_IDS["lack"], expected=exp, reason=f"{_NOT_READ}: {basis}", **common)
        quote = f" 조문: {texts[0][:80]}" if texts else ""
        if s != "해당" and any(r["kind"] == "compare_human" for r in db_rows):
            return _row(ref_no, cas, law, item, BORDER, RULE_IDS["border"], expected=exp,
                        reason=f"함량상 해당이지만 금지물질은 제품 형태 조건(예: 고무풀)이 붙는 경우가 있어 사람 확인: {basis}"
                               f" (11/02 F 결정 6).{quote}", cause="CONDITION_CHECK",
                        cause_text=f"함량은 기준을 넘음({basis}). 다만 이 금지물질 조문은 특정 제품 형태에만 적용될 수 있고, "
                                   f"이 제품이 그 형태인지는 정해지지 않아 사람 확인 필요. MSDS 기재: {s or '15항에 없음'}",
                        **common)
        if s != "해당" and state:
            return _row(ref_no, cas, law, item, BORDER, RULE_IDS["border"], expected=exp,
                        reason=f"함량상 해당이지만 조문에 성상 조건('{state}')이 있어 사람 확인: {basis} (11/02 F 결정 11)",
                        cause="CONDITION_CHECK", **common)
        if s != "해당" and ph_max is not None and ph is None:
            return _row(ref_no, cas, law, item, BORDER, RULE_IDS["border"], expected=exp,
                        reason=f"함량상 해당이지만 조문 조건 pH {ph_max:g} 이하를 9항 pH가 없어 확인 못 함: {basis}"
                               " (11/02 F 결정 11)", cause="CONDITION_CHECK", **common)
        if s != "해당":
            said = f"MSDS 기재는 {s}" if s else "MSDS 15항에 이 규제 항목이 없음(성분은 3항에 있음)"
            return _row(ref_no, cas, law, item, MISMATCH, RULE_IDS[MISSING], type_=MISSING, expected=exp,
                        reason=f"함량상 해당인데 MSDS는 {s or '행 없음'}: {basis}",
                        cause_text=f"함량상 해당인데 {said}: {basis}", **common)
        if mt and best and (mt[0] != best["threshold_op"] or abs(float(mt[1]) - best["threshold_value"]) > 1e-9):
            return _row(ref_no, cas, law, item, MISMATCH, RULE_IDS[THRESHOLD], type_=THRESHOLD, expected=exp,
                        reason=f"둘 다 해당이지만 기준 농도 표기가 다름: MSDS {_fmt(*mt)}, 지식DB {dbt}", **common)
        return _row(ref_no, cas, law, item, MATCH, RULE_IDS["match"], expected=exp, reason=basis, **common)
    if s == "해당" and (s_row or {}).get("_from_mix"):
        return _row(ref_no, cas, law, item, MATCH, RULE_IDS["match"], expected=exp,
                    reason=f"함량상 비해당. MSDS의 제품 전체 '해당'은 다른 성분 때문일 수 있어 이 성분과는 비교하지 않음: {basis}"
                           " (11/02 F 결정 9)", **common)
    if s == "해당":
        return _row(ref_no, cas, law, item, MISMATCH, RULE_IDS[EXTRA], type_=EXTRA, expected=exp,
                    reason=f"함량상 비해당인데 MSDS는 해당: {basis}", **common)
    return _row(ref_no, cas, law, item, MATCH, RULE_IDS["match"], expected=exp, reason=basis, **common)


# ── 위험물안전관리법 제4류 (설계서 29장, 규칙표 v0.3 dg_class4.yaml) ─────────────────
def _product_rows(physchem, code) -> list[dict]:
    """제품 값 행. MIX 행이 없고 모든 행이 한 성분 것이면(성분 1개 문서) 그 행을 쓴다."""
    rows = (physchem or {}).get(code) or []
    mix = [p for p in rows if str(p.get("comp_ref", "MIX")) in ("MIX", "None")]
    refs = {str(p.get("comp_ref")) for p in rows}
    return mix or (rows if len(refs) == 1 else [])


def _celsius(v, unit):
    return (v - 32) * 5 / 9 if v is not None and re.fullmatch(r"[°º˚]?\s*F|℉", str(unit or "").strip(), re.I) else v


def _prop(physchem, code):
    rows = _product_rows(physchem, code)
    for p in rows:  # 값이 있는 행을 먼저 본다 ('자료없음' 행 뒤에 값이 오기도 한다)
        q = p.get("q") or {}
        if q.get("value") is not None:
            return _celsius(q["value"], q.get("unit")), q.get("status")
    for p in rows:
        q = p.get("q") or {}
        if q.get("status"):
            return None, q.get("status")
    return None, None


def _flash_range(physchem) -> dict | None:
    """인화점이 '<23℃', '>93℃'처럼 값 하나가 아닌 행."""
    for p in _product_rows(physchem, "FLASH_POINT"):
        q = p.get("q") or {}
        if q.get("value") is None and (q.get("lower") is not None or q.get("upper") is not None):
            return {**q, "lower": _celsius(q.get("lower"), q.get("unit")), "upper": _celsius(q.get("upper"), q.get("unit"))}
    return None


def _class4(physchem):
    """9항 값으로 제4류 품명. (품명|None, 경계 여부, 설명, 액체·값이 불확실해서 생긴 경계인가)."""
    states = [p.get("text_value") for p in (physchem or {}).get("APPEARANCE_STATE") or [] if p.get("text_value")]
    state = " / ".join(states)
    if _DG_GAS.search(state):  # '액체가스'(액화가스)는 고압가스 — 제4류 아님
        return None, False, f"성상 '{state}' — 가스·액화가스는 제4류가 아님(11/02 F)", False
    liquid, solid = bool(_DG_LIQUID.search(state)), bool(_DG_SOLID.search(state))
    fp, fp_status = _prop(physchem, "FLASH_POINT")
    if solid and not liquid:
        if fp is not None and fp < 40:  # 인화성고체(제2류)는 인화점 40℃ 미만 고체 (시행령 별표 1)
            return None, True, f"성상 '{state}', 인화점 {fp:g}℃ — 인화성고체(제2류)일 수 있어 사람 확인 → 경계", True
        return None, False, f"성상 '{state}' — 제4류는 액체만", False
    sure_liquid = liquid and not solid
    bp, _ = _prop(physchem, "BOILING")
    ai, _ = _prop(physchem, "AUTOIGNITION")
    if fp is None:
        rng = _flash_range(physchem)
        if rng and (rng.get("upper") is not None or rng["lower"] < 250):
            return None, True, f"9항 인화점 '{rng.get('raw') or '범위'}' — 값이 하나가 아니라 품명을 못 정함 → 경계", True
        return None, False, f"9항 인화점 {fp_status or '없음'} — 제4류 품명 없음", False
    table = _dg_table()
    # 자연발화온도·끓는점이 없으면 아주 높은 값으로 둔다(특수인화물 조건을 만족하지 않는 쪽, 전과 같은 처리)
    props = {"STATE": "액체", "FLASH_POINT": fp, "BOILING": _INF if bp is None else bp,
             "AUTOIGNITION": _INF if ai is None else ai}
    rules = [{"id": r["id"], "category": r["item"], "when": r["when"]} for r in table["rules"]]
    tr = evaluate_rules_trace(rules, {}, props=props)
    if tr["rule_id"] is None:
        return None, False, f"인화점 {fp:g}℃ — 제4류 품명 없음({tr['category']})", False
    rule = next(r for r in table["rules"] if r["id"] == tr["rule_id"])
    # 제2석유류 제외는 가연성 액체량 40중량% 이하이면서 인화점 40℃ 이상일 때만이다 (시행령 별표 1 비고)
    edge = rule.get("edge") if rule["id"] != "DG4-2" or fp >= 40 else None
    if not sure_liquid:
        edge = f"성상 '{state or '모름'}'이 액체인지 불확실"
    return rule["item"], bool(edge), f"인화점 {fp:g}℃ ({rule['id']}" + (f", {edge} → 경계" if edge else "") + ")", not sure_liquid


_DG_ITEM = re.compile(r"특수인화물|알코올류|제[1-4]석유류|동식물유류")
_DG_NOT_BY_FLASH = ("특수인화물", "알코올류", "동식물유류")  # 성분 정보나 끓는점·발화점이 있어야 정한다
_DG_LITER = ("L", "ℓ", "리터", "l")
_DG_GAS = re.compile(r"가스|기체|\bgas\b|liquefied|compressed", re.I)
_DG_LIQUID = re.compile(r"액체|액상|용액|오일|유상|liquid|solution|\boil\b", re.I)
_DG_SOLID = re.compile(r"고체|고상|분말|가루|파우더|과립|펠[렛릿]|결정|입자|플레이크|solid|powder|pellet|granul|crystal|flake", re.I)
_C1_C3_ALCOHOL = {"67-56-1", "64-17-5", "71-23-8", "67-63-0"}  # 탄소 1~3개 포화1가 알코올
_WATER = "7732-18-5"
_WATER_NAMES = re.compile(r"^\s*(물|정제수|증류수|탈이온수|이온교환수|순수|(de-?ionized\s+|purified\s+|distilled\s+)?water)\s*$", re.I)


def _alcohol_solution(components) -> str | None:
    """탄소 1~3개 알코올 수용액이면 '미만'(60중량% 미만일 수 있음) 또는 '이상', 아니면 None (시행령 별표 1 비고 14호)."""
    def bound(c, key):
        q = c.get("content") or {}
        if q.get("value") is not None:
            return q["value"]
        return q.get(key) if q.get(key) is not None or key == "upper" else (0.0 if q.get("upper") is not None else None)
    alcohol = [c for c in components or [] if c.get("cas_no") in _C1_C3_ALCOHOL]
    water = [c for c in components or [] if c.get("cas_no") == _WATER or _WATER_NAMES.match(str(c.get("name") or ""))]
    others = [c for c in components or [] if c not in alcohol and c not in water]
    lows = [bound(c, "lower") for c in alcohol]
    # 다른 성분이 많으면 수용액이 아니다. 함량을 모르는 성분도 수용액으로 보지 않는다
    if not alcohol or not water or None in lows or any(bound(c, "upper") is None for c in others) \
            or sum(bound(c, "upper") for c in others) > 10:
        return None
    return "이상" if sum(lows) >= 60 else "미만"


def _dg_db_name(group_name) -> tuple[str | None, str | None]:
    """DB 품명 '제3석유류 비수용성액체' → (품명, 수용성). 제4류가 아니면 (None, None)."""
    m = _DG_ITEM.search(group_name or "")
    if not m:
        return None, None
    water = "비수용성" if "비수용성" in group_name else "수용성" if "수용성액체" in group_name else None
    return m.group(), water


def _dg_item_name(text) -> str | None:
    """'제 1 석유류', '제1석유류 비수용성액체' → 제1석유류."""
    m = _DG_ITEM.search(re.sub(r"\s+", "", str(text or "")))
    return m.group() if m else None


def _dg_differences(inputs, item9, db_class, db_item, db_water) -> list[str]:
    """MSDS 15항 제품 위험물 행의 류·품명·수용성·지정수량을 맞춰 본다 (설계서 29장 5단계).

    품명은 지식DB가 9항으로 못 정하는 품명이면 DB, 아니면 9항, 9항이 없으면 DB 순으로 본다. MSDS가 9항으로 못 정하는 품명을 적었으면 DB로만 본다.
    shortcut: 9항 용해도와 DB 지정수량은 대조하지 않는다. 용해도 문구 판독과 품목별 지정수량 행 선택을 만들 때 넣는다.
    """
    with_item = [d for d in inputs.get("dangerous_goods") or [] if d.get("item")]
    rows = [d for d in with_item if str(d.get("comp_ref")) == "MIX"]
    if not rows and (inputs.get("composition") or {}).get("type") == "단일물질":
        rows = with_item  # 단일물질은 성분 행이 제품 행이다
    if not rows:
        return []
    row = rows[0]
    written_class = re.sub(r"\s+", "", str(row.get("class") or ""))
    written_class = (re.search(r"제\d류", written_class) or [None])[0]
    if db_class and written_class and written_class != db_class:
        return [f"류: MSDS {written_class}, 지식DB {db_class}"]
    if written_class not in (None, "제4류") and _dg_item_name(row["item"]):
        return [f"류: MSDS {written_class}인데 품명은 제4류의 {_dg_item_name(row['item'])}"]
    if written_class not in (None, "제4류") or (db_class and db_class != "제4류"):
        return []  # 제4류가 아니면 인화점 품명 표를 쓰지 않는다
    rows = [d for d in rows if _dg_item_name(d["item"])]  # '인화성액체'처럼 품명이 아닌 글은 비교하지 않는다
    if not rows:
        return []
    written = [_dg_item_name(d["item"]) for d in rows]
    if db_item in _DG_NOT_BY_FLASH or written[0] in _DG_NOT_BY_FLASH:
        want_item = db_item
    else:
        want_item = item9 or db_item
    if want_item is None:
        return []
    if want_item not in written:
        return [f"품명: MSDS {', '.join(written)}, 판정 {want_item}"]
    row = rows[written.index(want_item)]
    if want_item != db_item:
        db_water = None
    out, water = [], row.get("water_soluble") if row.get("water_soluble") in ("수용성", "비수용성") else None
    if water and db_water and water != db_water:
        out.append(f"수용성: MSDS {water}, 지식DB {db_water}")
    rule = next((r for r in _dg_table()["rules"] if r["item"] == want_item), None)
    table_qty = (rule or {}).get("qty") or {}
    expected_qty = table_qty.get("any") or table_qty.get(water or db_water)
    qty = row.get("designated_qty") or {}
    msds_qty = qty.get("value") if qty.get("unit") in _DG_LITER else None
    if expected_qty and msds_qty is not None and float(msds_qty) != float(expected_qty):
        out.append(f"지정수량: MSDS {msds_qty:g}L, 시행령 별표1 {expected_qty:g}L")
    return out


def _dg(inputs, sup, know_all, sec15_read=True):
    s_row = sup.get(("MIX", "DG", "DG_HAZMAT"))
    s = (s_row or {}).get("applicable")
    s = None if s == "미기재" else s
    dg = inputs.get("dangerous_goods") or []
    cls = next((d.get("class") for d in dg if d.get("class")), None)
    if s is None and cls is not None:
        s = ("비해당" if re.search(r"해당\s*없|해당\s*사항\s*없|해당\s*되지\s*않|규제\s*되지\s*않|비\s*해당|미해당|비위험물|아님", cls)
             else "자료없음" if "자료" in cls else "해당")
    written_class = (re.search(r"제\s*\d\s*류", str(cls or "")) or [None])[0]
    db = sorted({(r["regulate_item_id"], r["db_item_name"], r.get("group_name"))
                 for k in know_all for r in k.get("rows") or [] if r["kind"] == "dg"})
    item, edge, basis, unsure = _class4(inputs.get("physchem"))
    db_names = {_dg_db_name(g) for _, _, g in db} - {(None, None)}
    db_item, db_water = next(iter(db_names)) if len(db_names) == 1 else (None, None)
    is_single = (inputs.get("composition") or {}).get("type") == "단일물질"
    # 인화점이 없으면 DB 품명으로 비교한다 (설계서 29장 6단계). 혼합물의 DB 품명은 성분 것이라 제품 품명이 아니다
    db_item, db_water = (db_item, db_water) if is_single else (None, None)
    db_classes = {n for _, n, _ in db}
    db_class = next(iter(db_classes)) if is_single and len(db_classes) == 1 else None
    if db_item in _DG_NOT_BY_FLASH or (db_class and db_class != "제4류"):  # 인화점 품명이 이 물질의 품명이 아니다
        item, edge = None, False
    want_item = item or db_item
    src = [f"HTODB {i} {n}" + (f" {g}" if g else "") for i, n, g in db] + [f"9항: {basis}"]
    alcohol = None if is_single or not item else _alcohol_solution(inputs.get("components"))
    if alcohol == "미만":
        # 비고 14호는 알코올류에서 빼는 단서라 인화점 품명까지 없애지는 않는다. 공식 해석을 못 찾았고 실제 MSDS는
        # 비위험물로 적으므로(하이콜 59 등), 규제 누락으로 단정하지 않고 사람이 확인한다
        edge, basis = True, f"{basis}, 알코올 60중량% 미만 수용액은 알코올류에서 제외(비고 14호) — 인화점 품명 적용 여부는 사람 확인 → 경계"
    elif alcohol == "이상":
        item, want_item, basis = "알코올류", "알코올류", f"{basis}, 탄소 1~3개 알코올 60중량% 이상 수용액 → 알코올류(비고 14호)"
    only_component = False
    if is_single:  # 순물질에는 함량 제외 규정이 없다. 액체·값이 불확실할 때만 경계
        exp = "해당" if db or (item and not unsure) else "경계" if item or edge else "비해당"
    elif item or edge:  # 함량 제외 규정은 위험물에서 빼는 규정이라 MSDS가 해당으로 적었으면 반박할 근거가 아니다 (시행령 별표 1 비고)
        exp = "경계" if edge and s != "해당" else "해당"
    elif db and s == "해당":
        exp = "해당"
    elif db:  # 15항은 혼합물 전체로 적는다 (고시 제11조⑪). 성분 지정만으로는 제품이 해당인지 정할 수 없다
        exp, only_component = "경계", True
    else:
        exp = "비해당"
    reason = f"지식DB 위험물 {len(db)}건, 9항 {item or '제4류 품명 없음'} ({basis})"
    if only_component:
        reason = f"성분이 위험물로 지정됐지만 제품 인화점으로 품명을 정하지 못해 제품 해당 여부를 사람이 확인: {reason}"
    asm = ["위험물은 제품 단위(성분 CAS가 아님): 지식DB 위험물 지정(KR004001) 또는 9항 인화점 제4류 품명(설계서 29장)",
           "동식물유류·알코올류(함량 60%)는 9항만으로 정할 수 없어 판정하지 않음"]
    version = next((k.get("knowledge_version") for k in know_all if k.get("knowledge_version")), None)
    common = dict(supplier=s, source=src, version=version, as_of=inputs.get("as_of_date"), extra_asm=asm,
                  db_threshold=want_item)
    fp_value, fp_status = _prop(inputs.get("physchem"), "FLASH_POINT")
    gas = bool(_DG_GAS.search(" ".join(str(p.get("text_value") or "") for p in (inputs.get("physchem") or {}).get("APPEARANCE_STATE") or [])))
    # 가스는 어느 류의 위험물도 아니다(시행령 별표 1은 고체·액체). 인화점이 없어도 판단할 수 있다
    if exp == "비해당" and s in ("해당", "자료없음") and not db and not gas and fp_value is None and fp_status in (None, "자료없음"):
        return _row("MIX", None, "DG", "DG_HAZMAT", LACK, RULE_IDS["lack"], expected=None,
                    reason=f"MSDS는 위험물 {s}인데 인화점이 없어 확인할 수 없음: {reason}", **common)
    if exp == "비해당" and s == "해당" and not db and written_class not in (None, "제4류"):
        return _row("MIX", None, "DG", "DG_HAZMAT", LACK, RULE_IDS["lack"], expected=None,
                    reason=f"MSDS는 {written_class} 위험물인데 제4류 밖은 9항으로 판정하지 않음: {reason}", **common)
    if s is None and not sec15_read and exp != "비해당":
        return _row("MIX", None, "DG", "DG_HAZMAT", LACK, RULE_IDS["lack"], expected=exp, reason=f"{_NOT_READ}: {reason}", **common)
    if exp == "경계":
        return _row("MIX", None, "DG", "DG_HAZMAT", BORDER, RULE_IDS["border"], expected=exp, reason=reason,
                    cause="CONDITION_CHECK", **common)
    if exp == "해당":
        if s == "해당":
            diff = _dg_differences(inputs, item, db_class, db_item, db_water)
            if diff:
                return _row("MIX", None, "DG", "DG_HAZMAT", MISMATCH, RULE_IDS[THRESHOLD], type_=THRESHOLD, expected=exp,
                            reason=f"위험물 {'; '.join(diff)}: {reason}", **common)
            if item and db_item and item != db_item and db_item not in _DG_NOT_BY_FLASH:
                return _row("MIX", None, "DG", "DG_HAZMAT", "경고", RULE_IDS["match"], expected=exp,
                            reason=f"9항으로 정한 품명 {item}과 지식DB 품명 {db_item}이 다름: {reason}", **common)
            return _row("MIX", None, "DG", "DG_HAZMAT", MATCH, RULE_IDS["match"], expected=exp, reason=reason, **common)
        return _row("MIX", None, "DG", "DG_HAZMAT", MISMATCH, RULE_IDS[MISSING], type_=MISSING, expected=exp,
                    reason=f"위험물 해당인데 MSDS는 {s or '행 없음'}: {reason}", **common)
    if s == "해당":
        return _row("MIX", None, "DG", "DG_HAZMAT", MISMATCH, RULE_IDS[EXTRA], type_=EXTRA, expected=exp,
                    reason=f"위험물 비해당인데 MSDS는 해당: {reason}", **common)
    return _row("MIX", None, "DG", "DG_HAZMAT", MATCH, RULE_IDS["match"], expected=exp, reason=reason, **common)


def _product_ph(physchem):
    """9항 제품 pH 중 가장 낮은 값(농도별로 여럿이면 가장 산성). 없으면 None."""
    vals = [(p.get("q") or {}).get("value") for p in (physchem or {}).get("PH") or []
            if str(p.get("comp_ref", "MIX")) in ("MIX", "None")]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return min(vals) if vals else None


def judge_sec15(inputs: dict, provider, *, non_toxic_cas=None) -> dict:
    """성분×규제 항목마다 판정 한 줄, 제품 단위 위험물 한 줄, 참고 줄은 excluded 로."""
    non_toxic = set(param_list("non_toxic_cas") if non_toxic_cas is None else non_toxic_cas)
    as_of = inputs.get("as_of_date")
    comps = {str(c.get("seq")): c for c in inputs.get("components") or []}
    main_comps = effective_components(inputs.get("components"))
    single = (inputs.get("composition") or {}).get("type") == "단일물질" and len(main_comps) == 1
    sup = _supplier(inputs.get("regulations"), str(main_comps[0].get("seq")) if single else None)
    uses_new_cca = any(k[2] in NEW_CCA for k in sup)
    know = {ref: provider.get_regulation(c["cas_no"], as_of) for ref, c in comps.items() if c.get("cas_no")}
    refs: dict[tuple, list[dict]] = {}
    for ref, k in know.items():
        for r in k.get("rows") or []:
            refs.setdefault((ref, r["law"], r["item_code"]), []).append(r)
    covered = covered_items()
    # 항목 코드 없이 법 단위로 적은 행(예: '산업안전보건법에 의한 규제: 비해당'). 판정하지 않고, 같은 성분·같은 법에서
    # 항목별 행이 없는 항목에 '비해당'을 이어 쓴다(11/02 F 결정 8).
    blanket = {(k[0], k[1]): r for k, r in sup.items() if k[2] is None and r.get("applicable") == "비해당"}
    # 혼합물에서 제품 전체(MIX)로 적은 항목 행. 성분별 행이 없으면 그 항목의 성분 판정에 이어 쓴다(11/02 F 결정 9).
    mix_item = {(k[1], k[2]): r for k, r in sup.items()
                if k[0] == "MIX" and k[2] and k[2] not in ("DG_HAZMAT", "WASTE_DESIG")}
    db_items = {(k[1], k[2]) for k, rows in refs.items() if any(r["kind"] != "psm_category" for r in rows)}
    ph = _product_ph(inputs.get("physchem"))
    regs = inputs.get("regulations") or []
    stated = lambda r: r.get("applicable") not in (None, "", "미기재") or r.get("value_raw") or r.get("threshold")
    # 법마다 읽었는지 본다. 한 법의 행만 읽힌 추출본에서 다른 법을 누락으로 내지 않는다 (추출기는 없으면 '미기재' 행을 넣는다)
    read_laws = {r.get("law") for r in regs if stated(r)}
    if any(d.get("class") or d.get("item") for d in inputs.get("dangerous_goods") or []):
        read_laws.add("DG")
    sec15_read = bool(read_laws)
    kreach_rows = any(r.get("law") == "KREACH" and stated(r) for r in regs)
    # 종전 서식은 기타 법규 칸에 적기도 한다 (부칙 제3조). 그때는 항목이 나뉘지 않아 성분별로 비교하지 못한다
    kreach_text = any(_KREACH_WORDS.search(" ".join(str(r.get(k) or "") for k in ("item_raw", "value_raw", "remark")))
                      for r in regs if r.get("applicable") != "미기재")
    kreach_stated = kreach_rows or kreach_text
    revised = inputs.get("revision_date")
    kreach_due = bool(revised) and str(revised) >= KREACH_LINE_FROM
    verdicts, excluded = [], []
    for key in sorted((set(sup) | set(refs)), key=lambda k: (k[0], k[1] or "", k[2] or "")):
        ref_no, law, item = key
        s_row, db_rows = sup.get(key), refs.get(key, [])
        kinds = {r["kind"] for r in db_rows}
        comp = comps.get(ref_no) or {}
        cas = comp.get("cas_no")
        s = (s_row or {}).get("applicable")
        src = [r["source"] for r in db_rows]
        if item is None:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  f"항목 없이 법 단위로 적은 행('{(s_row or {}).get('item_raw') or law}')"
                                  + (" — 같은 법의 항목별 판정에 '비해당'으로 이어 씀" if (ref_no, law) in blanket
                                     else " — 항목을 특정할 수 없어 비교하지 않음") + "(11/02 F 결정 8)", s, src))
            continue
        if ref_no != "MIX" and item in ("DG_HAZMAT", "WASTE_DESIG") and not db_rows:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "위험물·폐기물은 제품 단위로 본다(설계서 29장, 11/01 F 결정 5) — 성분에 적은 행은 참고", s, src))
            continue
        if ref_no == "MIX":
            if item == "DG_HAZMAT":
                continue  # 아래에서 제품 단위로 판정
            if item == "WASTE_DESIG":
                reason = "폐기물은 제품 단위이고 판정 규칙이 설계서에 없어 참고로만 표시(11/01 F 결정 5)"
            elif (law, item) in db_items:
                reason = "제품 전체로 적은 행 — 성분별 행이 없는 성분의 같은 항목 판정에 이어 씀(11/02 F 결정 9)"
            else:
                reason = ("제품 전체로 적었으나 지식DB에서 이 항목에 걸리는 성분이 없음"
                          + (" — 과기재일 수 있어 확인 필요" if s == "해당" else "") + "(11/02 F 결정 9)")
            excluded.append(_excl(ref_no, None, law, item, "참고", reason, s, src))
            continue
        if "waste" in kinds:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "지식DB 지정폐기물 연결 — 폐기물은 제품 단위·판정 규칙 없음(11/01 F 결정 5)", s, src))
            continue
        if "dg" in kinds:
            continue  # 성분의 위험물 지정은 제품 단위 위험물 판정에 쓴다
        if "psm_category" in kinds:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "인화성 액체·가스 범주로 PSM 규정량에 연결 — 성분이 아니라 제품의 인화성과 취급량으로 정해져 "
                                  "함량으로 판정하지 않음(산안법 시행령 별표13, 11/02 F 결정 10)", s, src))
            continue
        if cas in non_toxic and item in NEW_CCA:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "무독성 성분(물)이 지식DB에서 화관법 유해성 항목에 연결됨 — DB 값 확인 필요"
                                  "(설계서 57장 8번, 미결 5, 11/01 F 결정 2)", s, src))
            continue
        item_row = s_row or mix_item.get((law, item))  # 이 항목을 MSDS가 직접 적은 행(법 단위 행 제외)
        if item in NEW_CCA and not uses_new_cca and item_row is None:
            excluded.append(_excl(ref_no, cas, law, item, "구버전",
                                  "MSDS가 2025 화관법 개정 전 '유독물질' 체계로 기재 — 세분 항목은 구버전 판정 제외"
                                  "(D-09, 설계서 39장, 11/01 F 결정 1)", s, src))
            continue
        if law == "KREACH" and not kreach_rows and kreach_due and kreach_text and "status_only" not in kinds:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "화평법 규제현황을 기타 법규 칸에 글로 적어 항목별로 비교하지 못함 (고시 부칙 제2025-50호 제3조)", s, src))
            continue
        # 시행일 전 문서는 화평법 항목을 적을 의무가 없다. 다른 화평법 행을 적었어도 적지 않은 항목은 비교하지 않는다
        if law == "KREACH" and not kreach_due and "status_only" not in kinds and (item_row or {}).get("applicable") in (None, "", "미기재"):
            status = "구버전" if revised else "참고"
            excluded.append(_excl(ref_no, cas, law, item, status,
                                  f"화평법 기재 의무({KREACH_LINE_FROM}) 전 작성분이거나 작성일을 몰라 비교하지 않음 (고시 부칙 제2025-50호 제2조)", s, src))
            continue
        if "status_only" in kinds and (item_row or {}).get("applicable") != "해당":
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "기존화학물질 등 규제 의무가 아닌 지위 정보 — MSDS가 해당으로 적지 않으면 비교하지 않음(11/01 F 결정 3)",
                                  s, src))
            continue
        if s_row is None and (law, item) in mix_item:
            m = mix_item[(law, item)]
            s_row = {**m, "_from_mix": True, "_asm": m["_asm"] + [
                f"성분별 행이 없어 제품 전체로 적은 행('{m.get('item_raw') or item}: {m.get('applicable')}')을 "
                "이 성분에 적용(11/02 F 결정 9)"]}
        b = blanket.get((ref_no, law)) or blanket.get(("MIX", law))
        if s_row is None and b:
            s_row = {**b, "threshold": None, "_asm": b["_asm"] + [
                f"항목별 행이 없어 법 단위 기재('{b.get('item_raw') or law}: 비해당')를 이 항목에 적용(11/02 F 결정 8)"]}
        verdicts.append(_judge_component(key, s_row, comp, know.get(ref_no), db_rows, covered, ph, law in read_laws))
    # 불순물은 제품의 위험물 품명을 정하지 않는다
    verdicts.append(_dg(inputs, sup, [k for ref, k in know.items() if comps[ref].get("content_note") != "불순물"], "DG" in read_laws))
    if sec15_read and kreach_due and not kreach_stated:
        verdicts.append(_row("MIX", None, "KREACH", "KREACH_SECTION", MISMATCH, RULE_IDS[KREACH_MISSING], type_=KREACH_MISSING,
                             expected="해당", reason=f"{KREACH_LINE_FROM} 이후 작성분인데 15항에 화평법 규제현황이 없음 (개정일 {revised})",
                             version=next((k.get("knowledge_version") for k in know.values() if k.get("knowledge_version")), None),
                             as_of=as_of, source=["고시 제2026-26호 별표 4 제15호 다목"]))
    keyf = lambda r: (r["comp_ref"], r["law"] or "", r["item_code"] or "")
    return {"verdicts": sorted(verdicts, key=keyf), "excluded": sorted(excluded, key=keyf)}
