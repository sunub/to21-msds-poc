"""정합성 검증 결과 → 화면 계약(API-12 판정 목록, API-13 판정 상세) 변환 (11/03 F).

화면(E, e/frontend-review `frontend/src/api/findings-schemas.ts`)은 판정을 화면용 글자와 영문 판정 값으로 받는다.
엔진 결과(run_consistency + explain_consistency, 설계서 44장)는 코드·한글 판정·구조화된 계산 근거라서 여기서 바꾼다.
백엔드는 `api_view()` 결과를 저장해 두고 `findings_response()`·`finding_detail()`로 내보내면 된다.
엔진이 바뀌어도 화면 계약은 그대로 두고 이 파일만 고친다.

    view = api_view(result, item, msds_id="msds_a", validation_id="val_1")   # MSDS 한 건
    findings_response([view], validation_id="val_1", extraction_id="ext_1", section=15, page=1, page_size=20)  # API-12
    finding_detail([view], finding_id)                                         # API-13

정한 것(되돌릴 때는 아래 표만 고친다)
- 판정: 일치·불일치·경계·근거부족 → match·mismatch·borderline·insufficient_evidence.
  판정에서 뺀 줄(consistency.excluded): 15항 구버전 → outdated(목록에 보임), 참고·대조 → excluded, 해당 없음 → not_applicable(건수만).
  warning 은 쓰지 않는다(엔진은 표시 요소 '경고'도 불일치·낮음으로 낸다).
- 번호: finding_id = "{msds_id}-F-2-005", trace_id = "{msds_id}-T-2-005"(엔진 번호 앞에 MSDS 번호). 판정에서 뺀 줄은 X-2-001처럼 매긴다.
  component_id = "{msds_id}-c{성분 seq}", 제품 전체(MIX) 줄은 null 이고 묶음은 "product".
- 계산 근거가 없는 줄(MSDS에만 있는 항목)도 trace_id 는 문자열로 주고, 상세의 trace 는 null.
- 검토 상태(review_state·opinion_count·review)와 review_revision 은 백엔드 값이라 기본값(미검토, 0)만 채운다.
"""
import re
from datetime import date

from .explain import _rows, class_label, item_names, msds_evidence
from .trace import EXCLUDED_TEXT, cat_text

VERDICT = {"일치": "match", "불일치": "mismatch", "경계": "borderline", "근거부족": "insufficient_evidence"}
EXCLUDED_VERDICT = {"구버전": "outdated", "참고": "excluded", "대조": "excluded", "해당 없음": "not_applicable",
                    "판단불가": "excluded"}
LISTED = ("mismatch", "borderline", "insufficient_evidence", "warning", "outdated", "match")  # 목록에 보이는 판정
NOT_LISTED = ("not_applicable", "excluded")                                                   # 건수만 세는 판정
SEVERITY = {"높음": "high", "중간": "medium", "낮음": "low"}
PRODUCT_GROUP_ID = "product"
METHOD_15 = "규제DB 조회 (as_of 기준)"
_LAW_EXTRA = {"POPS": "잔류성유기오염물질관리법", "KR_ETC": "기타 국내 규제", "INTL": "국외 규제"}
_ITEM_EXTRA = {"POPS": "잔류성유기오염물질", "CCA_PERMIT": "허가물질", "CCA_RESTRICT": "제한물질", "CCA_PROHIBIT": "금지물질",
               "KR_ETC": "기타 국내 규제", "DG_HAZMAT": "위험물", "WASTE_DESIG": "폐기물", "KREACH_ETC": "기타 대상 여부"}
_INHAL_UNIT = {"가스": "ppm", "증기": "mg/L", "분진·미스트": "mg/L"}
_ATE_UNIT = {"HH_ACUTE_ORAL": "mg/kg", "HH_ACUTE_DERMAL": "mg/kg"}
_DROP_ASSUMPTION = ("rule_id(", "구분키:", "출처 코드 대응", "출처 우선순위:")  # 엔진 내부 메모라 화면에 안 보임


# ── 이름표 ────────────────────────────────────────────────────────────

def _law_names() -> tuple[dict, dict]:
    """reg_map.csv → (법 코드 → 법 이름, 항목 코드 → 항목 이름). 항목 하나에 세부규제가 여럿이면 묶음 이름."""
    laws, items = dict(_LAW_EXTRA), {}
    for r in _rows("reg_map.csv"):
        laws.setdefault(r["law_code"], r["law"])
        if r["item_code"]:
            items.setdefault(r["item_code"], []).append(r["db_item_name"])
    names = {k: v[0] if len(v) == 1 else _ITEM_EXTRA.get(k, "·".join(v)) for k, v in items.items()}
    for k, v in _ITEM_EXTRA.items():  # 지식DB가 다루지 않아 reg_map 에 없는 항목
        names.setdefault(k, v)
    return laws, names


def _g(x) -> str:
    return f"{x:,.4g}" if isinstance(x, float) else str(x)


def _pct(c) -> str:
    """{low, high} 또는 {raw} → '93~98%'."""
    if not c:
        return "함량 없음"
    if c.get("raw") and c.get("low") is None and c.get("high") is None:
        return str(c["raw"])
    lo, hi = c.get("low"), c.get("high")
    if lo is None and hi is None:
        return "함량 없음"
    if lo == hi or hi is None or lo is None:
        return f"{_g(lo if lo is not None else hi)}%"
    return f"{_g(lo)}~{_g(hi)}%"


def _cats(v) -> str | None:
    vals = [x for x in (v if isinstance(v, list) else [v]) if x not in (None, "")]
    return ", ".join(cat_text(x) for x in vals) if vals else None


# ── 화면 글자: 값·방법 ────────────────────────────────────────────────

def _values_2(f) -> tuple[str, str]:
    cc = f.get("class_code") or ""
    if cc.startswith("LABEL_"):
        m, o = f.get("msds_value"), (f.get("our_value") or {}).get("low")
        join = lambda v: ", ".join(v) if isinstance(v, list) else (v or None)  # noqa: E731
        return join(m) or "미기재", join(o) or "없음"
    msds = _cats(f.get("msds_value")) or "미기재"
    if f.get("msds_form"):
        msds += f" ({f['msds_form']})"
    ov = f.get("our_value") or {}
    lo, hi = ov.get("low"), ov.get("high")
    if f.get("verdict") == "근거부족":
        head = next((c["text"].split(" — ")[0] for c in f.get("causes") or [] if c["code"] == "NO_BASIS"), None)
        return msds, f"— ({head or '판정 근거 부족'})"
    if lo is None and hi is None:
        return msds, "—"
    exp = cat_text(lo) if lo == hi else f"{cat_text(lo)}~{cat_text(hi)}"
    if f.get("form"):
        exp += f" ({f['form']})"
    return msds, exp


def _values_15(f) -> tuple[str, str]:
    m, mt = f.get("msds_value"), f.get("msds_threshold")
    msds = (f"{m} ({mt})" if m and mt else m) or "기재 없음"
    e, et = f.get("expected"), f.get("db_threshold")
    if f.get("verdict") == "근거부족" or e is None:
        return msds, f"— ({f.get('reason') or '지식DB 기준 없음'})"[:80]
    return msds, f"{e} ({et})" if et and e in ("해당", "경계") else e


def _method(f, trace) -> str:
    if f.get("section") == "15":
        return METHOD_15
    if not trace:
        return "비교할 계산 결과 없음"
    kind = trace.get("kind")
    if kind == "label":
        return "별표2 매핑"
    if kind == "reference":
        return "지식DB 기준 분류(단일물질)"
    rid = _rule_id(trace, f)
    if rid.startswith("ATE") or any(t.get("range") for t in trace.get("thresholds") or []):
        return "ATEmix 계산"
    if rid.startswith("PHY-UN"):
        return "14항 UN 운송정보"
    if rid.startswith("PHY-") or any(i.get("role") == "물성" for i in trace.get("inputs") or []):
        return "대표성분·9항 물성"
    if (f.get("class_code") or "").startswith("ENV_AQ"):
        return "M계수 가산"
    return "가산·한계농도"


# ── 계산 근거(trace) → 글자 줄 ────────────────────────────────────────

_PROP = {"VISCOSITY_40": "40℃ 동점도", "PH": "pH", "STATE": "성상", "LEL": "폭발 하한", "UEL": "폭발 상한",
         "FLASH_POINT": "인화점", "BOILING": "초기끓는점"}
_FLAG = {"ph_extreme": "극단 pH 성분 수", "non_additive_1": "가산 불가 성분 수"}


def readable_formula(s: str) -> str:
    """규칙표 조건식 → 읽는 말. sum("1","1A") → '구분 1·1A 성분 합계', prop("PH") → '9항 pH'."""
    def cats(m):
        return "·".join(x.strip().strip('"') for x in m.group(2).split(","))
    s = re.sub(r'sumx\(([^)]*)\)', lambda m: f"구분 {'·'.join(x.strip().strip(chr(34)) for x in m.group(1).split(','))} 합계(M 곱함)", s)
    s = re.sub(r'(sum)\(([^)]*)\)', lambda m: f"구분 {cats(m)} 성분 합계", s)
    s = re.sub(r'prop\("(\w+)"\)', lambda m: f"9항 {_PROP.get(m.group(1), m.group(1))}", s)
    s = re.sub(r'has\("(\w+)"\)', lambda m: f"9항 {_PROP.get(m.group(1), m.group(1))} 있음", s)
    s = re.sub(r'flag\("(\w+)"\)', lambda m: _FLAG.get(m.group(1), m.group(1)), s)
    return s.replace(" and ", " 그리고 ").replace(" or ", " 또는 ")


def _rule_id(trace, f) -> str:
    rid = (trace.get("rule") or {}).get("id")
    if isinstance(rid, dict):  # 함량 하한·상한에서 다른 규칙이 걸린 줄
        rid = rid.get("high") or rid.get("low")
    return rid or f"MIX-{f.get('class_code')}"


def _result_line(r) -> str:
    if isinstance(r, dict):
        lo, hi, st = r.get("low"), r.get("high"), r.get("status")
        if lo is None and hi is None:
            return f"→ 판정 못 함 ({r.get('reason') or st or '근거부족'})"
        cat = cat_text(lo) if lo == hi else f"{cat_text(lo)}~{cat_text(hi)}"
        return f"→ {cat}" + (f" ({st})" if st else "")
    return f"→ {r}"


def _mixture_lines(t, f) -> tuple[list, list]:
    lines, form = [], f.get("form")
    unit = _ATE_UNIT.get(f.get("class_code")) or _INHAL_UNIT.get(form or "", "")
    for i in t.get("inputs") or []:
        role, name = i.get("role"), i.get("name")
        if role == "UN":
            lines.append(f"14항 UN {i.get('un_no')} · {i.get('hazard_class')}급"
                         + (f" · 부위험성 {i['sub_risk']}" if i.get("sub_risk") else "")
                         + (f" · 용기등급 {i['packing_group']}" if i.get("packing_group") else ""))
            continue
        if role == "물성":
            raws = lambda k: ", ".join(q.get("raw") or "" for q in i.get(k) or [] if isinstance(q, dict)) or "없음"  # noqa: E731
            lines.append(f"9항 인화점 {raws('flash_point')} · 초기끓는점 {raws('boiling')}")
            continue
        content = "" if i.get("excluded") == "함량 없음" else f" {_pct(i.get('content'))}"
        head = f"{'대표성분 ' if role == '대표성분' else ''}{name}{content}"
        if i.get("excluded"):
            step = f" · {i['step']}단계" if i.get("step") else ""
            lines.append(f"{head} · {EXCLUDED_TEXT.get(i['excluded'], i['excluded'])}{step}")
        elif i.get("ate_used") is not None:
            share = f" · 기여도 {i['share']:.0%}" if isinstance(i.get("share"), (int, float)) else ""
            lines.append(f"{head} · ATE {_g(i['ate_used'])} {unit} ({i.get('source') or ''}, {i.get('step')}단계){share}".replace(" ()", ""))
        else:
            used = ", ".join(cat_text(x) for x in i.get("used_as") or [])
            lines.append(f"{head} · 사용한 구분: {used or '없음'}")
    calc = t.get("calc") or {}
    if calc.get("ate_mix_low") is not None or calc.get("ate_mix_high") is not None:
        lines.append(f"ATEmix: 함량 하한일 때 {_g(calc.get('ate_mix_low'))}, 상한일 때 {_g(calc.get('ate_mix_high'))} {unit}".rstrip())
    if calc.get("unknown_pct"):
        lines.append(f"독성 자료가 없는 성분의 함량 상한 합계 {_g(calc['unknown_pct'])}%")
    vals = calc.get("values") or {}
    for key in dict.fromkeys(list((vals.get("low") or {}).keys()) + list((vals.get("high") or {}).keys())):
        lo, hi = (vals.get("low") or {}).get(key), (vals.get("high") or {}).get(key)
        if key.startswith(("sum", "prop")) and (lo or hi):
            lines.append(f"{readable_formula(key)}: 하한 {_g(lo)} · 상한 {_g(hi)}" if lo != hi else f"{readable_formula(key)}: {_g(lo)}")
    lines.append(_result_line(t.get("result")))
    th = t.get("thresholds") or []
    fired = [x for x in th if x.get("result") is True] or ([x for x in th if x.get("range")])
    out, seen = [], set()
    for x in fired or th[:4]:
        cond = x.get("range") or readable_formula(x.get("when") or "")
        key = (cond, x.get("category"))
        if key not in seen:
            seen.add(key)
            out.append(f"{cond} → {cat_text(x.get('category'))}" + ("" if fired else " (해당 안 됨)"))
    return lines, out


def _reference_lines(t) -> list:
    lines = [f"지식DB 기준 분류: {cat_text(i.get('category'))}" + (f" ({i['route_form']})" if i.get("route_form") else "")
             + (f" · {i['source']}" if i.get("source") else "") for i in t.get("inputs") or []]
    for s in t.get("all_sources") or []:
        extra = "".join(f" ({x})" for x in (s.get("form"), s.get("effect")) if x)
        lines.append(f"{s.get('source')}: {cat_text(s.get('category'))}{extra}")
    lines.append(_result_line(t["result"]) if t.get("result") else "→ 지식DB에 이 항목의 기준 분류 없음")
    return lines


def _label_lines(t) -> list:
    join = lambda v: ", ".join(v) if isinstance(v, list) else (v or "없음")  # noqa: E731
    lines = ["MSDS 2항 분류: " + ", ".join(class_label(i["class"]) for i in t.get("inputs") or [] if i.get("class"))]
    lines += [f"분류에서 도출: {join(t.get('derived'))}", f"MSDS 기재: {join(t.get('msds'))}"]
    if t.get("missing"):
        lines.append(f"MSDS에 빠진 것: {join(t['missing'])}")
    if t.get("extra"):
        lines.append(f"MSDS에 더 적힌 것: {join(t['extra'])}")
    for code, src in (t.get("from_classes") or {}).items():
        if src:
            lines.append(f"{code} ← " + ", ".join(class_label(x) for x in src))
    return lines


def _regulation_lines(t) -> tuple[list, list]:
    lines = [f"{i.get('name') or '성분 ' + str(i.get('comp_ref'))} {_pct(i.get('content'))}" for i in t.get("inputs") or []]
    if t.get("expected") is None and not t.get("db_threshold"):
        lines.append("지식DB 기준: 없음")
    else:
        lines.append(f"지식DB 기준: {t.get('db_threshold') or '함유하면 해당'} → {t.get('expected')}")
    lines.append(f"MSDS 기재: {t.get('msds_value') or '없음'}" + (f" ({t['msds_threshold']})" if t.get("msds_threshold") else ""))
    lines += [f"출처: {s}" for s in t.get("source") or []]
    lines += [f"조문: {s[:200]}" for s in (t.get("db_text") or [])[:2]]
    return lines, ([f"{t['db_threshold']} → 해당"] if t.get("db_threshold") else [])


def _trace_view(f, t, trace_id, rules_version, common=frozenset(), knowledge_version=None) -> dict | None:
    if not t:
        return None
    kind, thresholds = t.get("kind"), []
    if kind == "mixture":
        inputs, thresholds = _mixture_lines(t, f)
    elif kind == "reference":
        inputs = _reference_lines(t)
    elif kind == "label":
        inputs = _label_lines(t)
    else:
        inputs, thresholds = _regulation_lines(t)
    inputs += [f"차이 원인: {c['text']}" for c in f.get("causes") or []]
    asm = [a for a in list(t.get("assumptions") or []) + list(f.get("assumptions") or [])
           if isinstance(a, str) and not a.startswith(_DROP_ASSUMPTION) and a not in common]
    rid = _rule_id(t, f) if kind == "mixture" else ((t.get("rule") or {}).get("id") or f.get("rule_id") or kind)
    version = (t.get("knowledge_version") or knowledge_version) if kind == "regulation" else rules_version
    return {"trace_id": trace_id, "rule": {"id": str(rid), "version": str(version or "")},
            "inputs": [x for x in inputs if x], "thresholds": thresholds, "assumptions": list(dict.fromkeys(asm))}


# ── 설명 ───────────────────────────────────────────────────────────────

def _sentence(x: str) -> str:
    """문장틀 이유(원인 문장)는 마침표가 없어 이어 붙이면 한 덩어리가 된다."""
    x = str(x).strip()
    return x if x.endswith((".", "!", "?")) else x + "."


def _explanation_view(f) -> dict:
    e = f.get("explanation")
    if not e:
        return {"text": "", "source": "unavailable", "check_status": "not_checked", "limitations": []}
    lim = []
    if e.get("by") == "llm":
        lim.append("AI가 쓴 설명입니다. 판정은 규칙 엔진이 정했습니다.")
        if e.get("summary_by") == "template":
            lim.append("한 줄 요약은 판정 방향을 지키려고 문장틀로 고정했습니다.")
    elif e.get("llm_problems"):
        lim.append("AI 설명이 검사에 걸려 원인 문장틀로 바꿨습니다.")
    if any(c.get("code") == "ASSUMED" for c in f.get("causes") or []):
        lim.append("가정값을 써서 계산했습니다(계산 과정의 가정 참고).")
    text = " ".join(_sentence(x) for x in [e.get("summary") or ""] + list(e.get("reasons") or []) if x).strip()
    return {"text": text, "source": "ai" if e.get("by") == "llm" else "template",
            "check_status": "passed" if e.get("checked") else "failed", "limitations": lim}


# ── 한 MSDS ────────────────────────────────────────────────────────────

def _refs(f, item, page_path) -> list:
    pages = []
    for ev in msds_evidence(f, item) if item else []:
        p = ev.get("page")
        if isinstance(p, int) and p > 0 and p not in pages:
            pages.append(p)
    return [{"page_no": p, "bbox": None, "input_path": page_path.format(page=p)} for p in pages]


def _components(item, msds_id) -> dict:
    """성분 seq → (component_id, 묶음 제목 '황산 (93~98%)')."""
    out = {}
    for c in (item or {}).get("components") or []:
        name = c.get("name") or c.get("cas_no") or f"성분 {c.get('seq')}"
        raw = ((c.get("content") or {}).get("raw") or "").replace(" ", "")
        if raw and not raw.endswith("%"):
            raw += "%"
        out[str(c.get("seq"))] = (f"{msds_id}-c{c.get('seq')}", f"{name} ({raw})" if raw else name)
    return out


def _date(s) -> str | None:
    return s if isinstance(s, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None


def api_view(result: dict, item: dict | None, *, msds_id: str, validation_id: str,
             page_path: str = "pages/{page}.png") -> dict:
    """run_consistency(+explain_consistency) 결과 하나(MSDS 한 건) → 화면용 판정 상세 목록.

    반환: {"msds_id", "validation_id", "details": [API-13 상세 …], "groups": {component_id: 제목}}
    details 의 finding 이 API-12 목록 한 줄이다. 판정에서 뺀 줄도 verdict outdated·excluded·not_applicable 로 들어 있다.
    """
    c = result["consistency"]
    laws, items15 = _law_names()
    names = item_names()
    comps = _components(item, msds_id)
    rules_version = (c.get("knowledge") or {}).get("rules")
    kver = "; ".join((c.get("knowledge") or {}).get("version") or []) or None
    meta = (item or {}).get("meta") or {}
    ref_date = _date(c.get("as_of")) or _date(meta.get("last_revision_date")) or date.today().isoformat()
    details, groups = [], {}
    # 판정 줄 대부분에 똑같이 붙는 엔진 공통 가정은 줄마다 보이지 않는다(가정 목록 문서에 있음)
    seen, size = {}, {}
    for f in c.get("findings") or []:
        sec = str(f.get("section"))
        size[sec] = size.get(sec, 0) + 1
        for a in set(f.get("assumptions") or []):
            seen[(sec, a)] = seen.get((sec, a), 0) + 1
    common = {}
    for (sec, a), k in seen.items():
        if k >= max(3, size[sec] // 2):
            common.setdefault(sec, set()).add(a)

    def summary(f, fid, tid, verdict, severity, method, refs):
        sec = 15 if str(f.get("section")) == "15" else 2
        if sec == 15:
            comp = comps.get(str(f.get("comp_ref")))
            comp_id = comp[0] if comp else None
            if comp:
                groups.setdefault(comp_id, comp[1])
            elif str(f.get("comp_ref")) in ("MIX", "None", ""):
                groups.setdefault(PRODUCT_GROUP_ID, "제품")
            code = f.get("item_code")
            item_name = items15.get(code, code) if code else "법 단위 기재"
            law = laws.get(f.get("law"), f.get("law"))
            msds_t, exp_t = _values_15(f)
        else:
            comp_id, law = None, None
            code = f.get("class_code")
            item_name = names.get(code, code or "단일/혼합 판별")
            msds_t, exp_t = _values_2(f)
        return {"finding_id": fid, "validation_id": validation_id, "msds_id": msds_id, "section": sec,
                "item": item_name, "law": law, "component_id": comp_id,
                "msds_value": {"text": msds_t}, "expected_value": {"text": exp_t}, "method": method,
                "verdict": verdict, "severity": severity, "review_state": "unreviewed", "opinion_count": 0,
                "trace_id": tid, "source_refs": refs}

    for f in c.get("findings") or []:
        fid = f"{msds_id}-{f['id']}"
        tid = f"{msds_id}-{f.get('trace_id') or f['id'].replace('F-', 'T-', 1)}"
        t = (c.get("traces") or {}).get(f.get("trace_id"))
        refs = _refs(f, item, page_path)
        fs = summary(f, fid, tid, VERDICT[f["verdict"]], SEVERITY.get(f.get("severity")), _method(f, t), refs)
        details.append({"finding": fs, "explanation": _explanation_view(f), "trace": _trace_view(f, t, tid, rules_version, frozenset(common.get(str(f.get("section")), ())), kver),
                        "evidence": refs, "review": {"state": "unreviewed", "opinions": []},
                        "law_effective_date": None, "msds_revision_date": _date(meta.get("last_revision_date")),
                        "reference_date": ref_date})
    n = {}
    for x in c.get("excluded") or []:
        sec = str(x.get("section"))
        n[sec] = n.get(sec, 0) + 1
        fid = f"{msds_id}-X-{sec}-{n[sec]:03d}"
        tid = fid.replace("-X-", "-XT-", 1)
        f = {**x, "verdict": None}
        fs = summary(f, fid, tid, EXCLUDED_VERDICT.get(x.get("status"), "excluded"), None,
                     METHOD_15 if sec == "15" else "판정하지 않음", [])
        fs["expected_value"] = {"text": f"— ({x.get('status')})"}
        lines = [x.get("reason") or ""] + [f"출처: {s}" for s in x.get("source") or []]
        details.append({"finding": fs,
                        "explanation": {"text": x.get("reason") or "", "source": "template", "check_status": "not_checked",
                                        "limitations": []},
                        "trace": {"trace_id": tid, "rule": {"id": f"EXCLUDED-{x.get('status')}", "version": str(rules_version or "")},
                                  "inputs": [s for s in lines if s], "thresholds": [], "assumptions": []},
                        "evidence": [], "review": {"state": "unreviewed", "opinions": []},
                        "law_effective_date": None, "msds_revision_date": _date(meta.get("last_revision_date")),
                        "reference_date": ref_date})
    return {"msds_id": msds_id, "validation_id": validation_id, "details": details, "groups": groups}


# ── API-12·13 ──────────────────────────────────────────────────────────

def findings_response(views: list[dict], *, validation_id: str, extraction_id: str, review_revision: int = 0,
                      verdict: str | None = None, section: int | None = None, page: int = 1,
                      page_size: int | None = None) -> dict:
    """API-12 판정 목록. 화면 데모(demo-findings.ts)와 같은 규칙:
    - items 는 목록에 보이는 판정만(not_applicable·excluded 는 excluded_counts 에만).
    - counts·groups 는 항(section) 기준 전체, verdict 로 거르기 전 값. total 은 거른 뒤 개수.
    """
    rows = [d["finding"] for v in views for d in v["details"] if section is None or d["finding"]["section"] == section]
    shown = [r for r in rows if r["verdict"] in LISTED]
    counts = {k: sum(r["verdict"] == k for r in shown) for k in LISTED}
    excluded = {k: sum(r["verdict"] == k for r in rows) for k in NOT_LISTED}
    groups = []
    for v in views:
        for gid, title in v["groups"].items():
            mine = [r for r in shown if r["section"] == 15 and r["msds_id"] == v["msds_id"]
                    and (r["component_id"] == gid or (gid == PRODUCT_GROUP_ID and r["component_id"] is None))]
            if mine:
                groups.append({"component_id": gid, "title": title, "total": len(mine), "matching_count": sum(r["verdict"] == "match" for r in mine)})
    items = [r for r in shown if verdict is None or r["verdict"] == verdict]
    size = page_size or max(len(items), 1)
    start = (max(page, 1) - 1) * size
    return {"validation_id": validation_id, "extraction_id": extraction_id, "review_revision": review_revision,
            "items": items[start:start + size], "page": max(page, 1), "page_size": size, "total": len(items),
            "counts": counts, "excluded_counts": excluded, "groups": groups}


def finding_detail(views: list[dict], finding_id: str) -> dict | None:
    """API-13 판정 상세. 없는 번호면 None(백엔드가 404)."""
    return next((d for v in views for d in v["details"] if d["finding"]["finding_id"] == finding_id), None)
