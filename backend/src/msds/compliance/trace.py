"""판정 근거(trace)와 차이 원인 코드(causes) — 설계서 41장 반환 규격, 44장 traces, D-13.

판정 줄(finding)마다 두 가지를 붙인다. 판정·구분 값은 바꾸지 않는다.
  trace   계산 과정. run_consistency 가 consistency.traces[trace_id] 로 옮기고 판정 줄에는 trace_id 만 남긴다(44장).
          2항 혼합물  classify_mixture 결과(41장 모양: result, rule, inputs, calc, thresholds, assumptions, knowledge_version)
          2항 단일물질 지식DB 기준 분류 행(출처별)
          표시 요소   MSDS 분류 → 표시 요소 대응(어느 분류에서 어느 H코드·그림문자·신호어가 나왔는지)
          15항       성분 함량, 지식DB 기준, MSDS 기재
  causes  차이 원인 코드 목록(일치 줄은 빈 목록). 설명 단계(설계서 40장)가 코드로 문장 틀을 고르고 text·숫자를 채운다.

코드는 설계서 41장 8개에 우리가 필요해서 더한 것을 함께 쓴다(CAUSE_TEXT 의 '추가' 표시).
"""
from .label import _find
from .mixture.class_inputs import _SOURCE_NAME

CAUSE_TEXT = {
    # 설계서 41장
    "CAT_LOWER": "MSDS 구분이 계산 결과보다 낮음(미기재 포함)",
    "CAT_HIGHER": "MSDS 구분이 계산 결과보다 높음(계산 결과 분류안됨 포함)",
    "MAIN_COMPONENT": "결과를 가장 크게 좌우한 성분",
    "FORM_DIFF": "흡입 형태가 다름",
    "RANGE_EDGE": "함량 하한·상한에서 결과가 갈림",
    "ATE_VALUE_DIFF": "MSDS 11항 ATEmix와 계산값이 다름",
    "SOURCE_DIFF": "환경부·고용노동부 분류가 서로 다름",
    "ASSUMED": "가정값을 써서 계산",
    # 추가(설계서에 없음, 11/02 F)
    "DETAIL_DIFF": "구분 순위는 같고 세부 표기(표적장기 구분3 효과, 고압가스 종류)만 다름",
    "PROP_EDGE": "9항 물성 값이 비어 결과가 갈림",
    "MULTI_CATEGORY": "대표성분의 기준 분류에 같은 항목 구분이 여럿",
    "NO_BASIS": "기준정보나 입력값이 없어 판정하지 못함",
    "LABEL_MISSING": "분류로 보면 있어야 할 표시 요소가 MSDS에 없음",
    "LABEL_EXTRA": "분류에 없는 표시 요소를 MSDS가 더 적음",
    "LABEL_DIFF": "신호어가 분류에서 도출한 것과 다름",
    "REG_MISSING": "함량상 규제 해당인데 MSDS는 비해당·행 없음",
    "THRESHOLD_DIFF": "규제 기준 농도 표기가 지식DB와 다름",
    "OVER_STATED": "함량상 비해당인데 MSDS는 해당",
    "CONDITION_CHECK": "조문 조건(제품 형태·성상·pH·예외 규정) 때문에 사람 확인",
}
_FORM_KO = {"gas": "가스", "vapour": "증기", "mist": "분진·미스트"}
_ATE = {"HH_ACUTE_ORAL": ("TX_ORAL", "mg/kg"), "HH_ACUTE_DERMAL": ("TX_DERMAL", "mg/kg"), "HH_ACUTE_INHAL": ("TX_INHAL", None)}
_INHAL_UNIT = {"가스": "ppm", "증기": "mg/L", "분진·미스트": "mg/L"}
ATE_TOLERANCE = 0.05  # MSDS 11항 ATEmix 와 계산값 비교: 5% 안쪽 차이는 같은 값으로 봄(반올림·환산 차이)
TRACE_ASSUMPTIONS = [
    "차이 원인 코드는 설계서 41장 8개에 DETAIL_DIFF·PROP_EDGE·MULTI_CATEGORY·NO_BASIS·표시 요소 3개·15항 4개를 더해 씀(11/02 F)",
    "MAIN_COMPONENT 기여도: 급성독성은 ATE 계산의 성분 기여도(share), 나머지는 그 항목에 쓰인 성분 함량 상한의 비율",
    f"ATE_VALUE_DIFF: MSDS 11항 혼합물(MIX) 독성값의 구간과 계산 ATEmix(하한~상한)가 {ATE_TOLERANCE:.0%} 넘게 떨어져 있을 때만",
]


def cause(code: str, text: str, **extra) -> dict:
    return {"code": code, "text": text, **extra}


def _g(x):
    return f"{x:.4g}" if isinstance(x, (int, float)) else str(x)


def _ours(v):
    low, high = (v.get("our_value") or {}).get("low"), (v.get("our_value") or {}).get("high")
    return low, high, ("없음" if low is None else low if low == high else f"{low}~{high}")


def _msds(v):
    m = v.get("msds_value")
    return ", ".join(m) if isinstance(m, list) and m else (m or "기재 없음")


def _verdict_causes(v) -> list[dict]:
    """판정 줄만 보고 정하는 코드: 근거부족, 과소·과대, 형태·세부 표기."""
    out = []
    if v["verdict"] == "근거부족":
        out.append(cause("NO_BASIS", v.get("reason") or ""))
    t, (_, _, ours), msds = v.get("type"), _ours(v), _msds(v)
    if t == "과소분류":
        out.append(cause("CAT_LOWER", f"MSDS {msds}, 계산 결과 {ours}"))
    elif t == "과대분류":
        out.append(cause("CAT_HIGHER", f"MSDS {msds}, 계산 결과 {ours}"))
    if v.get("msds_form") and v["msds_form"] != v.get("form"):
        out.append(cause("FORM_DIFF", f"MSDS {v['msds_form']}, 계산 {v.get('form')}", msds_form=v["msds_form"], form=v.get("form")))
    elif t == "형태·세부 표기":
        out.append(cause("DETAIL_DIFF", v.get("reason") or ""))
    return out


# ── 2항 혼합물 ─────────────────────────────────────────────────────────

def _contributors(trace):
    """[(입력 행, 기여도 0~1, 기준)]. 급성독성은 share, 대표성분은 1, 나머지는 쓰인 성분 함량 상한의 비율."""
    ins = trace.get("inputs") or []
    ate = [i for i in ins if isinstance(i.get("share"), (int, float))]
    if ate:
        return [(i, i["share"], "ATE 기여도") for i in ate]
    rep = [i for i in ins if i.get("role") == "대표성분" and i.get("used_as")]
    if rep:
        return [(rep[0], 1.0, "대표성분 분류를 혼합물 분류로 채택")]
    used = [i for i in ins if i.get("used_as") and not i.get("excluded") and (i.get("content") or {}).get("high") is not None]
    total = sum(i["content"]["high"] for i in used)
    return [(i, i["content"]["high"] / total, "함량 상한 비율") for i in used] if total else []


def _source_diff(class_code, components) -> list[dict]:
    out = []
    for c in components or []:
        by = {}
        for r in c.get("class_rows") or []:
            if r.get("class_code") != class_code:
                continue
            label = str(r.get("category")) + (f"({_FORM_KO.get(r['form'], r['form'])})" if r.get("form") else "") \
                + (f"({r['effect']})" if r.get("effect") else "")
            by.setdefault(_SOURCE_NAME.get(r.get("source"), r.get("source")), set()).add(label)
        if len(by) >= 2 and len({frozenset(s) for s in by.values()}) > 1:
            shown = {k: sorted(s) for k, s in sorted(by.items())}
            out.append(cause("SOURCE_DIFF", f"{c.get('name')}: " + ", ".join(f"{k} {'·'.join(s)}" for k, s in shown.items()),
                             name=c.get("name"), cas=c.get("cas"), by_source=shown))
    return out


def _assumed(trace) -> list[dict]:
    out = []
    for a in trace.get("assumptions") or []:
        if a.startswith("M 계수 없음") or a.startswith("제품 성상 미상") or "구간(" in a or "TO21 고유 규칙" in a:
            out.append(cause("ASSUMED", a))
    if any(i.get("role") == "대표성분" and i.get("used_as") for i in trace.get("inputs") or []):
        out.append(cause("ASSUMED", "대표성분 정의(지식DB 분류가 있는 성분 중 함량 최대)는 설계서 52장 미결 6 가정"))
    return out


def _form_of(raw):
    s = str(raw or "")
    return "가스" if "가스" in s else "증기" if "증기" in s else "분진·미스트" if ("미스트" in s or "분진" in s) else None


def _ate_diff(v, trace, item):
    cc = v["class_code"]
    if cc not in _ATE:
        return None
    ep, unit = _ATE[cc]
    unit = unit or _INHAL_UNIT.get(v.get("form"))
    calc = trace.get("calc") or {}
    vals = [x for x in (calc.get("ate_mix_low"), calc.get("ate_mix_high")) if isinstance(x, (int, float))]
    if not vals or not unit:
        return None
    lo_c, hi_c = min(vals), max(vals)
    for t in (item or {}).get("toxicity") or []:
        if str(t.get("comp_ref")) != "MIX" or not str(t.get("endpoint") or "").startswith(ep):
            continue
        pf = _form_of(t.get("physical_form"))
        if cc == "HH_ACUTE_INHAL" and pf and pf != v.get("form"):
            continue
        q = t.get("q") or {}
        if q.get("status") not in ("값있음", None) or str(q.get("unit") or "").replace("l", "L") != unit.replace("l", "L"):
            continue
        if q.get("value") is not None:
            lo, hi = q["value"], q["value"]
        elif q.get("lower") is not None or q.get("upper") is not None:
            lo, hi = q.get("lower") or 0, q.get("upper") if q.get("upper") is not None else float("inf")
        else:
            continue
        if hi_c < lo * (1 - ATE_TOLERANCE) or lo_c > hi * (1 + ATE_TOLERANCE):
            return cause("ATE_VALUE_DIFF", f"MSDS 11항 '{q.get('raw')}', 계산 ATEmix {_g(lo_c)}~{_g(hi_c)} {unit}",
                         msds_raw=q.get("raw"), ours={"low": lo_c, "high": hi_c}, unit=unit)
    return None


def mixture_causes(v, trace, components, item) -> list[dict]:
    if v["verdict"] == "일치":
        return []
    out = _verdict_causes(v)
    if not trace:
        return out
    low, high, _ = _ours(v)
    # 근거부족이거나 계산 결과가 분류안됨이면, 성분이 왜 계산에 들어가지 않았는지(제외 사유)를 덧붙인다
    if v["verdict"] == "근거부족" or (low == high == "분류안됨"):
        why = [{"name": i.get("name"), "excluded": i["excluded"]} for i in trace.get("inputs") or [] if i.get("excluded")]
        unknown = (trace.get("calc") or {}).get("unknown_pct")
        tail = ", ".join(f"{w['name']}({w['excluded']})" for w in why)
        if unknown:
            tail += f"{'; ' if tail else ''}이용 불가 성분 {_g(unknown)}%"
        for c in out:
            if c["code"] in ("NO_BASIS", "CAT_HIGHER") and tail:
                c["text"] += f" — 성분: {tail}"
                c["components"] = why
    if low is not None and high is not None and low != high:
        roles = {i.get("role") for i in trace.get("inputs") or []}
        if "대표성분" in roles and not ("물성" in roles):
            out.append(cause("MULTI_CATEGORY", f"대표성분 분류의 구분 {low}·{high}"))
        elif "물성" in roles:
            out.append(cause("PROP_EDGE", f"9항 물성이 비어 {low}~{high} 사이에서 갈림"))
        else:
            out.append(cause("RANGE_EDGE", f"함량 하한으로 {low}, 상한으로 {high}"))
    contrib = _contributors(trace)
    if contrib:
        i, share, basis = max(contrib, key=lambda x: x[1])
        out.append(cause("MAIN_COMPONENT", f"{i.get('name')} ({basis} {share:.0%})", name=i.get("name"), cas=i.get("cas"),
                         share=round(share, 3), basis=basis))
    if d := _ate_diff(v, trace, item):
        out.append(d)
    out += _source_diff(v["class_code"], components)
    out += _assumed(trace)
    return out


def attach_mixture(verdicts, results, components, item) -> None:
    """aggregate_verdicts 판정 줄에 trace·causes 를 붙인다. 우리 결과가 없는 줄(MSDS에만 있는 항목)은 trace 없음."""
    by_key = {(r["class_code"], r.get("form") or None): r for r in results}
    for v in verdicts:
        r = by_key.get((v["class_code"], v.get("form") or None))
        trace = None if r is None else {"kind": "mixture", **{k: x for k, x in r.items() if k not in ("class_code", "form")}}
        v["trace"] = trace
        v["causes"] = mixture_causes(v, trace, components, item)


# ── 2항 단일물질 ───────────────────────────────────────────────────────

def attach_single(verdicts, know, raw_rows) -> None:
    """know: ReferenceProvider.get_reference 결과(D-05 적용), raw_rows: 출처 우선순위를 적용하기 전 지식DB 분류 행."""
    know = know or {}
    for v in verdicts:
        cc, form = v["class_code"], v.get("form")
        used = [c for c in know.get("classes") or [] if c["class_code"] == cc and c.get("route_form") == form]
        all_src = [{"category": r.get("category"), "form": _FORM_KO.get(r.get("form"), r.get("form")), "effect": r.get("effect"),
                    "source": _SOURCE_NAME.get(r.get("source"), r.get("source")), "result_code": r.get("result_code")}
                   for r in raw_rows or [] if r.get("class_code") == cc]
        v["trace"] = {"kind": "reference", "result": v.get("our_value"),
                      "rule": {"id": "REF-D05", "basis": "지식DB 기준 분류, 출처 우선순위 D-05(항목 단위 환경부→고용노동부)"},
                      "inputs": used, "all_sources": all_src, "knowledge_version": know.get("knowledge_version"),
                      "reason": None if used else (know.get("reason") or "지식DB에 이 항목의 기준 분류가 없음")}
        out = [] if v["verdict"] == "일치" else _verdict_causes(v)
        if v["verdict"] != "일치":
            out += _source_diff(cc, [{"name": know.get("cas_no"), "cas": know.get("cas_no"), "class_rows": raw_rows}])
        v["causes"] = out


# ── 표시 요소 ──────────────────────────────────────────────────────────

def label_sources(classes) -> dict:
    """[(class_code, category, effect)] → {H코드·그림문자·신호어: [그것을 낳은 분류…]} (hazard_label_map.csv)."""
    out = {}
    for c in classes:
        name = f"{c[0]} {c[1]}" + (f"({c[2]})" if len(c) > 2 and c[2] else "")
        for r in _find(c[0], c[1], c[2] if len(c) > 2 else None):
            for k in ("h_code", "pictogram", "signal_word"):
                if r.get(k) and name not in out.setdefault(r[k], []):
                    out[r[k]].append(name)
    return out


def label_trace(f, classes, rule_id) -> dict:
    src = label_sources(classes)
    shown = (f["derived"] if isinstance(f["derived"], list) else [f["derived"]] if f["derived"] else []) + list(f["missing"] or [])
    return {"kind": "label", "result": f["derived"],
            "rule": {"id": rule_id, "basis": "고시 별표2·제6조의2 (rules/hazard_label_map.csv, label_rules.yaml)"},
            "inputs": [{"class": f"{c[0]} {c[1]}" + (f"({c[2]})" if c[2] else "")} for c in classes],
            "derived": f["derived"], "msds": f["msds"], "missing": f["missing"], "extra": f["extra"],
            "from_classes": {k: src.get(k, []) for k in dict.fromkeys(shown) if k}}


def label_causes(verdict, f, item_name, src) -> list[dict]:
    if verdict == "일치":
        return []
    if verdict == "근거부족":
        return [cause("NO_BASIS", f"MSDS에 {item_name}가 없음")]
    if f["item"] == "signal_word":
        return [cause("LABEL_DIFF", f"분류로 보면 '{f['derived'] or '없음'}', MSDS '{f['msds']}'",
                      from_classes=src.get(f["derived"], []))]
    out = []
    for code in f["missing"] or []:
        out.append(cause("LABEL_MISSING", f"{code} ← {', '.join(src.get(code, [])) or '분류 대응 없음'}", item=code,
                         from_classes=src.get(code, [])))
    for code in f["extra"] or []:
        out.append(cause("LABEL_EXTRA", f"{code}: MSDS 2항 분류에서 나오지 않음", item=code))
    return out


# ── 15항 ──────────────────────────────────────────────────────────────

def sec15_trace(v, comps_by_seq) -> dict:
    c = comps_by_seq.get(str(v.get("comp_ref"))) or {}
    q = c.get("content") or {}
    one = q.get("value")
    comp = None if not c else {"comp_ref": v.get("comp_ref"), "cas": c.get("cas_no"), "name": c.get("name"),
                               "content": {"raw": q.get("raw"), "low": one if one is not None else q.get("lower"),
                                           "high": one if one is not None else q.get("upper")}}
    return {"kind": "regulation", "result": v.get("expected"),
            "rule": {"id": v.get("rule_id"), "basis": "지식DB 규제 기준(rules/reg_map.csv, 설계서 27·28장)"},
            "inputs": [comp] if comp else [], "law": v.get("law"), "item_code": v.get("item_code"),
            "expected": v.get("expected"), "db_threshold": v.get("db_threshold"), "msds_value": v.get("msds_value"),
            "msds_threshold": v.get("msds_threshold"), "source": v.get("source"), "db_text": v.get("db_text"),
            "knowledge_version": v.get("knowledge_version")}
