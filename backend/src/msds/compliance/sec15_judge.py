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
from .sec15 import _expected
from .trace import cause as _cause

_INF = float("inf")


@lru_cache
def _dg_table() -> dict:
    """rules/dg_class4.yaml (규칙표 v0.3, 위험물안전관리법 시행령 별표1). 전에는 같은 기준을 코드에 적어 두었다(11/02 F)."""
    with open(RULES_DIR / "dg_class4.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

MATCH, MISMATCH, BORDER, LACK = "일치", "불일치", "경계", "근거부족"
# 설계서 7장 · 규칙표 v0.3 severity.yaml (15항)
MISSING, THRESHOLD, EXTRA = "규제 누락", "기준 불일치", "과기재"
SEVERITY = {MISSING: "높음", THRESHOLD: "중간", EXTRA: "낮음"}
SV = {MISSING: "SV-02", THRESHOLD: "SV-04", EXTRA: "SV-08"}
RULE_IDS = {"match": "S15-1", MISSING: "S15-2", THRESHOLD: "S15-3", EXTRA: "S15-4", "border": "S15-5", "lack": "S15-6"}
# 차이 원인 코드(trace.CAUSE_TEXT). 경계는 함량이 기준에 걸칠 때 RANGE_EDGE, 조문 조건 때문이면 CONDITION_CHECK(_row 의 cause)
CAUSE = {MISSING: "REG_MISSING", THRESHOLD: "THRESHOLD_DIFF", EXTRA: "OVER_STATED", LACK: "NO_BASIS", BORDER: "RANGE_EDGE"}
NEW_CCA = {"CCA_ACUTE", "CCA_CHRONIC", "CCA_ECO"}
BASE_ASSUMPTIONS = [
    "rule_id(S15-1~6)는 설계서에 없어 우리 쪽 번호를 씀. 유형·심각도는 설계서 7장(severity.yaml SV-02·04·08)",
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
    q = q or {}
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
    return out


def _judge_component(key, s_row, comp, know, db_rows, covered, ph=None):
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
def _prop(physchem, code):
    rows = [p for p in (physchem or {}).get(code) or [] if str(p.get("comp_ref", "MIX")) == "MIX"]
    for p in rows:
        q = p.get("q") or {}
        if q.get("value") is not None:
            return q["value"], q.get("status")
        if q.get("status"):
            return None, q.get("status")
    return None, None


def _class4(physchem):
    """9항 값으로 제4류 품명. (품명|None, 경계 여부, 설명)."""
    states = [p.get("text_value") for p in (physchem or {}).get("APPEARANCE_STATE") or [] if p.get("text_value")]
    state = " / ".join(states)
    if any(w in state for w in ("가스", "기체")):  # '액체가스'(액화가스)는 고압가스 — 제4류(인화성 액체) 아님
        return None, False, f"성상 '{state}' — 가스·액화가스는 제4류가 아님(11/02 F)"
    if "액체" not in state:
        return None, False, f"성상 '{state or '모름'}' — 제4류는 액체만"
    fp, fp_status = _prop(physchem, "FLASH_POINT")
    bp, _ = _prop(physchem, "BOILING")
    ai, _ = _prop(physchem, "AUTOIGNITION")
    if fp is None:
        return None, False, f"9항 인화점 {fp_status or '없음'} — 제4류 품명 없음"
    table = _dg_table()
    # 자연발화온도·끓는점이 없으면 아주 높은 값으로 둔다(특수인화물 조건을 만족하지 않는 쪽, 전과 같은 처리)
    props = {"STATE": "액체", "FLASH_POINT": fp, "BOILING": _INF if bp is None else bp,
             "AUTOIGNITION": _INF if ai is None else ai}
    rules = [{"id": r["id"], "category": r["item"], "when": r["when"]} for r in table["rules"]]
    tr = evaluate_rules_trace(rules, {}, props=props)
    if tr["rule_id"] is None:
        return None, False, f"인화점 {fp:g}℃ — 제4류 품명 없음({tr['category']})"
    rule = next(r for r in table["rules"] if r["id"] == tr["rule_id"])
    edge = rule.get("edge")
    return rule["item"], bool(edge), f"인화점 {fp:g}℃ ({rule['id']}" + (f", {edge} → 경계" if edge else "") + ")"


_DG_ITEM = re.compile(r"특수인화물|알코올류|제[1-4]석유류|동식물유류")
_DG_NOT_BY_FLASH = ("특수인화물", "알코올류", "동식물유류")  # 성분 정보나 끓는점·발화점이 있어야 정한다
_DG_LITER = ("L", "ℓ", "리터", "l")


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
    rows = [d for d in inputs.get("dangerous_goods") or [] if d.get("item") and str(d.get("comp_ref")) == "MIX"]
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
    written = [_dg_item_name(d["item"]) or d["item"] for d in rows]
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


def _dg(inputs, sup, know_all):
    s_row = sup.get(("MIX", "DG", "DG_HAZMAT"))
    s = (s_row or {}).get("applicable")
    if s is None:
        dg = inputs.get("dangerous_goods") or []
        cls = next((d.get("class") for d in dg if d.get("class")), None)
        s = None if cls is None else ("비해당" if "해당없음" in cls or "비해당" in cls else "해당")
    db = sorted({(r["regulate_item_id"], r["db_item_name"], r.get("group_name"))
                 for k in know_all for r in k.get("rows") or [] if r["kind"] == "dg"})
    item, edge, basis = _class4(inputs.get("physchem"))
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
    if db or (item and not edge):
        exp = "해당"
    elif item and edge:
        exp = "경계"
    else:
        exp = "비해당"
    reason = f"지식DB 위험물 {len(db)}건, 9항 {item or '제4류 품명 없음'} ({basis})"
    asm = ["위험물은 제품 단위(성분 CAS가 아님): 지식DB 위험물 지정(KR004001) 또는 9항 인화점 제4류 품명(설계서 29장)",
           "동식물유류·알코올류(함량 60%)는 9항만으로 정할 수 없어 판정하지 않음"]
    version = next((k.get("knowledge_version") for k in know_all if k.get("knowledge_version")), None)
    common = dict(supplier=s, source=src, version=version, as_of=inputs.get("as_of_date"), extra_asm=asm,
                  db_threshold=want_item)
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
        if "status_only" in kinds and item_row is None:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "기존화학물질 등 규제 의무가 아닌 지위 정보 — MSDS가 적지 않으면 비교하지 않음(11/01 F 결정 3)",
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
        verdicts.append(_judge_component(key, s_row, comp, know.get(ref_no), db_rows, covered, ph))
    # 불순물은 제품의 위험물 품명을 정하지 않는다
    verdicts.append(_dg(inputs, sup, [k for ref, k in know.items() if comps[ref].get("content_note") != "불순물"]))
    keyf = lambda r: (r["comp_ref"], r["law"] or "", r["item_code"] or "")
    return {"verdicts": sorted(verdicts, key=keyf), "excluded": sorted(excluded, key=keyf)}
