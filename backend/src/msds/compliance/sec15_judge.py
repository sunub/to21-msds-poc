"""15항 판정: 성분 함량과 지식DB 규제 기준으로 해당 여부를 정하고 MSDS 15항과 비교해 판정·유형·심각도를 붙인다.

근거: 설계서 7장(유형·심각도), 27·28장(판정 FLOW·기준 농도 비교), 29장(위험물 제4류), 30장(유형), 10/30 결정 D4,
11/01 F 결정 1~5(작업 기록 '15항 사전 분석과 결정'). 기대 해당 여부 계산은 정민의 sec15._expected(ADR 0004)를 그대로 쓴다.

    judge_sec15(inputs, provider) → {"verdicts": [...], "excluded": [...]}
    inputs: loader.load_inputs 결과. provider: get_regulation(cas_no, as_of) 를 가진 지식 제공자(htodb.regulation)

판정 줄 모양은 2항(mixture.verdict)과 맞춘다: verdict(일치·불일치·경계·근거부족), type, severity, rule_id, reason, assumptions.
excluded 는 판정하지 않고 참고로만 보여 줄 줄이다(구버전, DB 값 확인 필요, 지위 정보, 폐기물).
"""
from .htodb.regulation import covered_items
from .mixture.params import param_list
from .sec15 import _expected

MATCH, MISMATCH, BORDER, LACK = "일치", "불일치", "경계", "근거부족"
# 설계서 7장 · 규칙표 v0.3 severity.yaml (15항)
MISSING, THRESHOLD, EXTRA = "규제 누락", "기준 불일치", "과기재"
SEVERITY = {MISSING: "높음", THRESHOLD: "중간", EXTRA: "낮음"}
SV = {MISSING: "SV-02", THRESHOLD: "SV-04", EXTRA: "SV-08"}
RULE_IDS = {"match": "S15-1", MISSING: "S15-2", THRESHOLD: "S15-3", EXTRA: "S15-4", "border": "S15-5", "lack": "S15-6"}
NEW_CCA = {"CCA_ACUTE", "CCA_CHRONIC", "CCA_ECO"}
BASE_ASSUMPTIONS = [
    "rule_id(S15-1~6)는 설계서에 없어 우리 쪽 번호를 씀. 유형·심각도는 설계서 7장(severity.yaml SV-02·04·08)",
    "지식DB가 다루는 항목인데 그 성분에 규제 행이 없으면 비해당으로 봄(설계서 27장 '규제DB 비해당')",
    "같은 항목에 기준이 여럿이면 가장 낮은 값을 씀. vol% 기준은 중량%로 비교(설계서 미결 7)",
]


def _row(comp_ref, cas, law, item, verdict, rule_id, *, type_=None, supplier=None, expected=None, msds_threshold=None,
         db_threshold=None, reason="", source=(), version=None, as_of=None, extra_asm=()):
    return {"section": "15", "comp_ref": comp_ref, "cas_no": cas, "law": law, "item_code": item, "verdict": verdict,
            "type": type_, "severity": SEVERITY.get(type_), "sv_id": SV.get(type_), "rule_id": rule_id,
            "msds_value": supplier, "msds_threshold": msds_threshold, "expected": expected, "db_threshold": db_threshold,
            "reason": reason, "source": list(source), "knowledge_version": version, "as_of": as_of,
            "assumptions": BASE_ASSUMPTIONS + list(extra_asm)}


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


def _supplier(regs):
    """MSDS 15항 행 → {(comp_ref, law, item): 행}. 결정 4: applicable 이 비었는데 값이 적혀 있으면 해당으로 본다."""
    out = {}
    for r in regs or []:
        if r.get("law") == "INTL":
            continue
        r = dict(r)
        r["_asm"] = []
        if r.get("applicable") is None and (r.get("value_raw") or r.get("threshold")):
            r["applicable"] = "해당"
            r["_asm"] = [f"MSDS 칸은 비었지만 값('{r.get('value_raw') or (r.get('threshold') or {}).get('raw')}')이 적혀 있어 "
                         "해당으로 봄(11/01 F 결정 4)"]
        out[(str(r.get("comp_ref")), r.get("law"), r.get("item_code"))] = r
    return out


def _judge_component(key, s_row, comp, know, db_rows, covered):
    ref_no, law, item = key
    cas = comp.get("cas_no")
    s = (s_row or {}).get("applicable")
    asm = (s_row or {}).get("_asm", [])
    version = know.get("knowledge_version") if know else None
    as_of = know.get("as_of") if know else None
    mt = _msds_threshold(s_row)
    common = dict(supplier=s, msds_threshold=_fmt(*mt) if mt else None, version=version, as_of=as_of, extra_asm=asm,
                  source=[r["source"] for r in db_rows])
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
    if exp == "경계":
        return _row(ref_no, cas, law, item, BORDER, RULE_IDS["border"], expected=exp, reason=basis, **common)
    if exp == "해당":
        if s != "해당":
            return _row(ref_no, cas, law, item, MISMATCH, RULE_IDS[MISSING], type_=MISSING, expected=exp,
                        reason=f"함량상 해당인데 MSDS는 {s or '행 없음'}: {basis}", **common)
        if mt and best and (mt[0] != best["threshold_op"] or abs(float(mt[1]) - best["threshold_value"]) > 1e-9):
            return _row(ref_no, cas, law, item, MISMATCH, RULE_IDS[THRESHOLD], type_=THRESHOLD, expected=exp,
                        reason=f"둘 다 해당이지만 기준 농도 표기가 다름: MSDS {_fmt(*mt)}, 지식DB {dbt}", **common)
        return _row(ref_no, cas, law, item, MATCH, RULE_IDS["match"], expected=exp, reason=basis, **common)
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
    state = next((p.get("text_value") for p in (physchem or {}).get("APPEARANCE_STATE") or [] if p.get("text_value")), "")
    if "액체" not in (state or ""):
        return None, False, f"성상 '{state or '모름'}' — 제4류는 액체만"
    fp, fp_status = _prop(physchem, "FLASH_POINT")
    bp, _ = _prop(physchem, "BOILING")
    ai, _ = _prop(physchem, "AUTOIGNITION")
    if fp is None:
        return None, False, f"9항 인화점 {fp_status or '없음'} — 제4류 품명 없음"
    if (ai is not None and ai <= 100) or (fp <= -20 and bp is not None and bp <= 40):
        return "특수인화물", False, f"인화점 {fp:g}℃"
    if fp < 21:
        return "제1석유류", False, f"인화점 {fp:g}℃ < 21"
    if fp < 70:
        return "제2석유류", True, f"인화점 {fp:g}℃ (가연성 액체량 40% 이하 예외 → 경계)"
    if fp < 200:
        return "제3석유류", True, f"인화점 {fp:g}℃ (도료류 예외 → 경계)"
    if fp < 250:
        return "제4석유류", True, f"인화점 {fp:g}℃ (도료류 예외 → 경계)"
    return None, False, f"인화점 {fp:g}℃ ≥ 250 — 제4류 아님"


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
                  db_threshold=(item or None))
    if exp == "경계":
        return _row("MIX", None, "DG", "DG_HAZMAT", BORDER, RULE_IDS["border"], expected=exp, reason=reason, **common)
    if exp == "해당":
        if s == "해당":
            return _row("MIX", None, "DG", "DG_HAZMAT", MATCH, RULE_IDS["match"], expected=exp, reason=reason, **common)
        return _row("MIX", None, "DG", "DG_HAZMAT", MISMATCH, RULE_IDS[MISSING], type_=MISSING, expected=exp,
                    reason=f"위험물 해당인데 MSDS는 {s or '행 없음'}: {reason}", **common)
    if s == "해당":
        return _row("MIX", None, "DG", "DG_HAZMAT", MISMATCH, RULE_IDS[EXTRA], type_=EXTRA, expected=exp,
                    reason=f"위험물 비해당인데 MSDS는 해당: {reason}", **common)
    return _row("MIX", None, "DG", "DG_HAZMAT", MATCH, RULE_IDS["match"], expected=exp, reason=reason, **common)


def judge_sec15(inputs: dict, provider, *, non_toxic_cas=None) -> dict:
    """성분×규제 항목마다 판정 한 줄, 제품 단위 위험물 한 줄, 참고 줄은 excluded 로."""
    non_toxic = set(param_list("non_toxic_cas") if non_toxic_cas is None else non_toxic_cas)
    as_of = inputs.get("as_of_date")
    comps = {str(c.get("seq")): c for c in inputs.get("components") or []}
    sup = _supplier(inputs.get("regulations"))
    uses_new_cca = any(k[2] in NEW_CCA for k in sup)
    know = {ref: provider.get_regulation(c["cas_no"], as_of) for ref, c in comps.items() if c.get("cas_no")}
    refs: dict[tuple, list[dict]] = {}
    for ref, k in know.items():
        for r in k.get("rows") or []:
            refs.setdefault((ref, r["law"], r["item_code"]), []).append(r)
    covered = covered_items()
    verdicts, excluded = [], []
    for key in sorted((set(sup) | set(refs)), key=lambda k: (k[0], k[1] or "", k[2] or "")):
        ref_no, law, item = key
        s_row, db_rows = sup.get(key), refs.get(key, [])
        kinds = {r["kind"] for r in db_rows}
        comp = comps.get(ref_no) or {}
        cas = comp.get("cas_no")
        s = (s_row or {}).get("applicable")
        src = [r["source"] for r in db_rows]
        if ref_no == "MIX":
            if item == "DG_HAZMAT":
                continue  # 아래에서 제품 단위로 판정
            reason = ("폐기물은 제품 단위이고 판정 규칙이 설계서에 없어 참고로만 표시(11/01 F 결정 5)" if item == "WASTE_DESIG"
                      else "제품 전체 행은 성분 CAS로 조회할 수 없어 참고로만 표시")
            excluded.append(_excl(ref_no, None, law, item, "참고", reason, s, src))
            continue
        if "waste" in kinds:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "지식DB 지정폐기물 연결 — 폐기물은 제품 단위·판정 규칙 없음(11/01 F 결정 5)", s, src))
            continue
        if "dg" in kinds:
            continue  # 성분의 위험물 지정은 제품 단위 위험물 판정에 쓴다
        if cas in non_toxic and item in NEW_CCA:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "무독성 성분(물)이 지식DB에서 화관법 유해성 항목에 연결됨 — DB 값 확인 필요"
                                  "(설계서 57장 8번, 미결 5, 11/01 F 결정 2)", s, src))
            continue
        if item in NEW_CCA and not uses_new_cca and s_row is None:
            excluded.append(_excl(ref_no, cas, law, item, "구버전",
                                  "MSDS가 2025 화관법 개정 전 '유독물질' 체계로 기재 — 세분 항목은 구버전 판정 제외"
                                  "(D-09, 설계서 39장, 11/01 F 결정 1)", s, src))
            continue
        if "status_only" in kinds and s_row is None:
            excluded.append(_excl(ref_no, cas, law, item, "참고",
                                  "기존화학물질 등 규제 의무가 아닌 지위 정보 — MSDS가 적지 않으면 비교하지 않음(11/01 F 결정 3)",
                                  s, src))
            continue
        verdicts.append(_judge_component(key, s_row, comp, know.get(ref_no), db_rows, covered))
    verdicts.append(_dg(inputs, sup, list(know.values())))
    keyf = lambda r: (r["comp_ref"], r["law"] or "", r["item_code"] or "")
    return {"verdicts": sorted(verdicts, key=keyf), "excluded": sorted(excluded, key=keyf)}
