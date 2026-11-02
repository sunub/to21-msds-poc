"""2차 정합성 검증 묶음: 추출 JSON 한 건 → 2항·15항 판정을 설계서 44장 결과 구조(consistency 블록)로 만든다.

    run_consistency(doc, repo=None, msds_index=0) → {"doc_id", "msds_index", "consistency": {...}}
    repo: None 이면 로컬 HTODB(PostgreSQL), htodb.csv_repo.CsvRepo() 면 샘플 CSV.

흐름(설계서 8장): 입력 정리(loader) → 판별(classifier) → 2항(혼합물: mixture 계산 + verdict / 단일물질: 기준 분류 + verdict)
→ 표시 요소(MSDS 2항 분류 → 그림문자·신호어·H코드, 설계서 31장) → 15항(sec15_judge) → 판정 집계(summary). 판정·구분 값은 규칙과 계산으로만 정하고, LLM 설명은 이 결과를 읽기만 한다.
"""
from collections import Counter

import yaml

from .classifier import effective_components, product_type
from .htodb.reference import ReferenceProvider
from .htodb.regulation import RegulationProvider
from .label import derive_label
from .label_compare import compare_label
from .loader import load_inputs
from .mixture.ate_source import inhal_forms
from .mixture.build_components import _state, build_components
from .mixture.class_lookup_db import make_db_class_lookup, make_db_info_lookup, make_db_tox_lookup
from .mixture.classify_mixture import classify_mixture_all
from .mixture.params import RULES_DIR
from .mixture.physical import physical_inputs
from .mixture.ranges import content_range
from .mixture.rules_loader import load_mixture_rules
from .mixture.verdict import _order, _rank, aggregate_verdicts
from .sec15_judge import judge_sec15
from .trace import TRACE_ASSUMPTIONS, attach_mixture, attach_single, label_causes, label_sources, label_trace, sec15_trace

ENGINE_VERSION = "0.2.0"
SINGLE_ASSUMPTIONS = [
    "단일물질은 지식DB 기준 분류(D-05 항목 단위 환경부→고용노동부)를 그대로 '우리 결과'로 보고 MSDS 2항과 비교(설계서 18장)",
    "기준 분류에 없는 항목을 MSDS만 적었으면 근거부족(설계서 18장: 두 출처 모두 없음 → 근거부족)",
    "같은 항목에 기준 구분이 여럿이면 가장 위험한 구분으로 비교",
    "환경부 '흡입:가스'가 액체·고체 물질이면 다른 출처 형태로, 없으면 성상으로 재지정(D-22, D-06)",
]


_FORM_NAME = {"gas": "가스", "vapour": "증기", "mist": "분진·미스트"}


def _reassign_gas(classes: list[dict], raw_rows: list[dict], state: str | None) -> list[dict]:
    """D-22: 환경부 '흡입:가스'가 액체·고체 물질이면 다른 출처 형태로, 없으면 성상 기준(D-06)으로 재지정한다. 성상을 모르면 그대로 둔다."""
    if state not in ("액체", "고체"):
        return classes
    allowed = inhal_forms(state)
    other = {r["form"] for r in raw_rows if r.get("class_code") == "HH_ACUTE_INHAL" and r.get("form") in allowed}
    form = _FORM_NAME[next((f for f in allowed if f in other), allowed[0])]  # 성상 순서대로 (액체: 증기, 분진·미스트)
    return [{**c, "route_form": form} if c["class_code"] == "HH_ACUTE_INHAL" and c["route_form"] == "가스" and c.get("source") == "환경부" else c
            for c in classes]


def _impurity_rows(inputs: dict, provider: ReferenceProvider) -> list[tuple[str, str, float, float | None, float | None, str]]:
    """불순물의 (항목, 구분, 한계농도, 함량 하한, 상한, 이름). 함량이 없으면 하한·상한이 None 이다 (설계서 19장)."""
    limits = yaml.safe_load((RULES_DIR / "impurity_limits.yaml").read_text(encoding="utf-8"))["limits"]
    out = []
    for c in inputs.get("components") or []:
        if c.get("content_note") != "불순물" or not c.get("cas_no"):
            continue
        rng = content_range([c])[0]
        know = provider.get_reference(c["cas_no"], inputs.get("as_of_date")) or {}
        for k in know.get("classes") or []:
            if k["category"] in limits.get(k["class_code"], {}):
                out.append((k["class_code"], k["category"], limits[k["class_code"]][k["category"]], rng["low"], rng["high"], c.get("name") or c["cas_no"]))
    return out


def _apply_impurities(results: list[dict], rows: list[tuple], rules: dict) -> dict[str, str]:
    """한계농도를 넘는 불순물이 있는 항목만 혼합물 규칙으로 고친다. 반환: 항목별 설명."""
    by_key = {(r["class_code"], r.get("form")): r for r in results}
    notes: dict[str, str] = {}
    for cc, cat, limit, low, high, name in rows:
        order = _order(cc, None, rules, None)
        main = (by_key.get((cc, None)) or {"result": {"low": "분류안됨", "high": "분류안됨"}})["result"]
        worse = lambda a, b: min((a, b), key=lambda x: _rank(x, order) if _rank(x, order) is not None else 99)
        if low is None and high is None:
            res = {**main, "status": "근거부족", "reason": f"근거부족(불순물 함량): {name}의 함량이 없음"}
            notes[cc] = res["reason"]
        elif high < limit:
            continue
        else:
            res = {"low": worse(main["low"], cat) if low >= limit else main["low"], "high": worse(main["high"], cat)}
            res["status"] = "확정" if res["low"] == res["high"] else "경계"
            notes[cc] = f"불순물 {name} {cat} 함량 {low}~{high}%, 한계농도 {limit}%: 이 항목만 혼합물 규칙 적용(설계서 19장)"
        by_key[(cc, None)] = {"class_code": cc, "form": None, "result": res}
    results[:] = list(by_key.values())
    return notes


def _single_2(inputs: dict, item: dict, provider: ReferenceProvider) -> dict:
    comps = effective_components(inputs.get("components"))
    cas = comps[0].get("cas_no") if comps else None
    know = provider.get_reference(cas, inputs.get("as_of_date")) if cas else None
    if know and know.get("classes"):
        know = {**know, "classes": _reassign_gas(know["classes"], provider.class_rows(cas), _state(item, []))}
    msds_classes = (item.get("hazard") or {}).get("classes") or []
    rules = load_mixture_rules()
    groups: dict[tuple, list[str]] = {}
    for c in (know or {}).get("classes") or []:
        cat = c["category"] + (f":{c['effect']}" if c.get("effect") else "")
        groups.setdefault((c["class_code"], c["route_form"]), []).append(cat)
    results = []
    for (cc, form), cats in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        order = _order(cc, form, rules, None)
        ranked = sorted(set(cats), key=lambda x: (_rank(x, order) if _rank(x, order) is not None else 99, x))
        results.append({"class_code": cc, "form": form, "result": {"low": ranked[0], "high": ranked[0], "status": "확정"}})
    notes = _apply_impurities(results, _impurity_rows(inputs, provider), rules)
    out = aggregate_verdicts(results, msds_classes, rules=rules)
    why = ("성분 CAS가 없음" if not cas else (know or {}).get("reason") if not (know or {}).get("knowledge_version")
           else "지식DB에 이 항목의 기준 분류가 없음(환경부·고용노동부 모두 없음, 설계서 18장)")
    for v in out["verdicts"]:
        v["assumptions"] = v["assumptions"] + SINGLE_ASSUMPTIONS
        if v["class_code"] in notes and notes[v["class_code"]] not in v["reason"]:
            v["reason"] = f"{v['reason']} / {notes[v['class_code']]}"
        if v["verdict"] == "근거부족" and v["reason"] == "우리 결과에 같은 항목이 없음":
            v["reason"] = why
    out["excluded"] += [{"class_code": c["class_code"], "form": c["route_form"], "status": "참고",
                         "msds_value": None, "our_value": c["category"],
                         "reason": f"국내 고시 밖 구분(class_map '참고', D-18) — {c['source']}"}
                        for c in (know or {}).get("reference_only") or []]
    out["knowledge_version"] = (know or {}).get("knowledge_version")
    attach_single(out["verdicts"], know, provider.class_rows(cas))
    return out


LABEL_CODE = {"h_codes": "LABEL_H_CODES", "pictograms": "LABEL_PICTOGRAMS", "signal_word": "LABEL_SIGNAL_WORD"}
LABEL_NAME = {"h_codes": "H코드", "pictograms": "그림문자", "signal_word": "신호어"}
LABEL_ASSUMPTIONS = [
    "표시 요소는 MSDS 2항에 적힌 분류에서 도출해(고시 별표2, 제6조의2) MSDS의 그림문자·신호어·H코드와 비교한다(설계서 31장 공통 검증)",
    "H314가 있으면 H318은 적지 않아도 불일치가 아니라 참고(10/30 결정 C3). 그림문자 5개 이상이면 4개만 적어도 일치(PIC-4)",
    "분류에 없는 H코드를 MSDS가 더 적은 경우(label_rules '경고')는 판정 4종에 맞춰 불일치·낮음으로 낸다",
    "표적장기 1회 구분3은 효과로 H335(호흡기 자극)·H336(마취)을 고른다. 효과가 비어 있으면 MSDS H코드로 짐작",
    "MSDS의 묶음 H코드(예: H302+H332)는 나눠 비교하고, MSDS 신호어 '없음·해당없음'은 '없음'으로 맞춘다",
]


def _fmt_list(v):
    return ", ".join(v) if isinstance(v, list) else (v if v else "없음")


def _label(item: dict) -> tuple[list[dict], list[dict]]:
    """MSDS 2항 분류 → 표시 요소 도출 → MSDS 표시 요소와 비교. (판정 줄, 참고 줄). item = 추출 JSON msds[i]
    (loader 입력에는 분류의 효과(effect) 칸이 없어 원본을 읽는다)."""
    hz = item.get("hazard") or {}
    # MSDS 값 정리: 'H302+H332' 같은 묶음 H코드는 나눠 보고, 신호어 '없음'은 신호어 없음으로 본다(11/02 F)
    raw_h = [h.get("code") if isinstance(h, dict) else h for h in hz.get("h_statements") or []]
    h_codes = sorted({p.strip() for h in raw_h if h for p in str(h).split("+") if p.strip()})
    pictograms = [p.get("code") if isinstance(p, dict) else p for p in hz.get("pictograms") or []]
    signal = hz.get("signal_word")
    signal = "없음" if str(signal or "").strip() in ("없음", "해당없음", "해당 없음") else (signal or None)
    classes = []
    for c in hz.get("classes") or []:
        if not c.get("class_code"):
            continue
        effect = c.get("effect")
        if c["class_code"] == "HH_STOT_SE" and str(c.get("category")) == "3" and not effect:
            # 효과가 비어 있으면 MSDS H코드로 짐작한다(H336 마취, H335 호흡기 자극). 둘 다 없으면 둘 다 도출
            effect = " ".join(w for w, h in (("마취", "H336"), ("호흡기", "H335")) if h in h_codes) or None
        classes.append((c["class_code"], c.get("category"), effect))
    derived = derive_label(classes)
    if signal == "없음" and derived["signal_word"] is None:  # 분류가 없어 신호어도 없음 = MSDS '없음'
        derived["signal_word"] = "없음"
    msds = {"pictograms": pictograms, "signal_word": signal, "h_codes": h_codes}
    rows, excluded = [], []
    src = label_sources(classes)
    for f in compare_label(derived, msds):
        code, name, d, m = LABEL_CODE[f["item"]], LABEL_NAME[f["item"]], f["derived"], f["msds"]
        if f["verdict"] == "참고":
            excluded.append({"class_code": code, "form": None, "status": "참고", "msds_value": m, "our_value": d,
                             "reason": f"{name}: 생략 가능한 {_fmt_list(f['missing'])}를 MSDS가 적지 않음({f['rule_id']}, 결정 C3)"})
            continue
        verdict = "불일치" if f["verdict"] in ("불일치", "경고") else f["verdict"]
        if verdict == "일치":
            reason = f"{name} 같음" + (f" (그림문자 5개 이상이라 4개만 표시, {f['rule_id']})" if f["missing"] else "")
        elif verdict == "근거부족":
            reason = f"MSDS에 {name}가 없음 — 분류로 보면 {_fmt_list(d)}"
        elif f["item"] == "signal_word":
            reason = f"신호어: 분류로 보면 '{d or '없음'}', MSDS는 '{m or '기재 없음'}'"
        else:
            parts = []
            if f["missing"]:
                parts.append(f"분류로 보면 있어야 하는데 MSDS에 없음: {_fmt_list(f['missing'])}")
            if f["extra"]:
                parts.append(f"분류에 없는데 MSDS가 더 적음: {_fmt_list(f['extra'])}")
            reason = f"{name}: " + "; ".join(parts)
        bad = verdict == "불일치"
        rows.append({"class_code": code, "form": None, "verdict": verdict, "type": "표시 요소 불일치" if bad else None,
                     "severity": f["severity"] if bad else None, "sv_id": "SV-06" if bad else None,
                     "msds_value": m, "msds_form": None, "our_value": {"low": d, "high": d},
                     "missing": f["missing"], "extra": f["extra"], "reason": reason, "rule_id": f["rule_id"] or "LBL-1",
                     "assumptions": list(LABEL_ASSUMPTIONS), "trace": label_trace(f, classes, f["rule_id"] or "LBL-1"),
                     "causes": label_causes(verdict, f, name, src)})
    return rows, excluded


def _mixture_2(item: dict, repo) -> tuple[dict, list, list]:
    b = build_components(item, make_db_class_lookup(repo), make_db_tox_lookup(repo), make_db_info_lookup(repo))
    results = classify_mixture_all(b["components"], b["mixture_props"], state=b["mixture_props"].get("STATE"),
                                   physical=physical_inputs(item))
    out = aggregate_verdicts(results, (item.get("hazard") or {}).get("classes"))
    attach_mixture(out["verdicts"], results, b["components"], item)  # 판정 근거(41장)·차이 원인 코드
    for e in out["excluded"]:
        if e["status"] == "대조" and not e.get("reason"):
            e["reason"] = "판정하지 않고 MSDS 기재와 성분 분류를 나란히 두는 항목(규칙표 compare 방식)"
    return out, b["gaps"], b["assumptions"]


def _summary(rows: list[dict]) -> dict:
    c = Counter(r["verdict"] for r in rows)
    sev = Counter(r["severity"] for r in rows if r.get("severity"))
    return {"일치": c["일치"], "불일치": c["불일치"], "경계": c["경계"], "근거부족": c["근거부족"],
            "심각도": {"높음": sev["높음"], "중간": sev["중간"], "낮음": sev["낮음"]}}


def run_consistency(doc: dict, repo=None, msds_index: int = 0) -> dict:
    inputs = load_inputs(doc, msds_index)
    item = (doc.get("msds") or [{}])[msds_index]
    pt = product_type(inputs)
    gaps, assumptions = [], []
    if pt["type"] == "혼합물":
        s2, gaps, assumptions = _mixture_2(item, repo)
    elif pt["type"] == "단일물질":
        s2 = _single_2(inputs, item, ReferenceProvider(repo))
    else:
        s2 = {"verdicts": [], "excluded": [{"class_code": None, "form": None, "status": "판단불가", "msds_value": None,
                                            "our_value": None, "reason": pt["basis"]}]}
    s15 = judge_sec15(inputs, RegulationProvider(repo))
    label_rows, label_excl = _label(item)
    s2["excluded"] = s2["excluded"] + label_excl
    f2 = [{"id": f"F-2-{i:03d}", "section": "2", **v} for i, v in enumerate(s2["verdicts"] + label_rows, 1)]
    f15 = [{"id": f"F-15-{i:03d}", **v} for i, v in enumerate(s15["verdicts"], 1)]
    comps_by_seq = {str(c.get("seq")): c for c in inputs.get("components") or []}
    for f in f15:
        f["trace"] = sec15_trace(f, comps_by_seq)
    traces = {}
    for f in f2 + f15:  # 설계서 44장: 판정 줄에는 trace_id, 계산 과정은 traces 에
        t = f.pop("trace", None)
        f["trace_id"] = None if t is None else "T" + f["id"][1:]
        f.setdefault("causes", [])
        if t is not None:
            traces[f["trace_id"]] = t
    versions = {v.get("knowledge_version") for v in s15["verdicts"]} | {s2.get("knowledge_version")}
    versions.discard(None)
    if repo is not None and hasattr(repo, "version"):
        versions.add(repo.version())
    return {
        "doc_id": inputs.get("doc_id"), "msds_index": msds_index,
        "consistency": {
            "engine_version": ENGINE_VERSION,
            "as_of": inputs.get("as_of_date"),
            "knowledge": {"provider": "to21_sample" if repo is not None else "htodb", "version": sorted(versions),
                          "rules": load_mixture_rules()["meta"]["version"]},
            "product_type": {"value": pt["type"], "basis": pt["basis"]},
            "summary": {"2항": _summary(f2), "15항": _summary(f15), "전체": _summary(f2 + f15),
                        "참고": len(s2["excluded"]) + len(s15["excluded"])},
            "findings": f2 + f15,
            "traces": traces,
            "excluded": [{"section": "2", **e} for e in s2["excluded"]] + s15["excluded"],
            "gaps": gaps, "assumptions": assumptions + TRACE_ASSUMPTIONS, "missing": inputs.get("missing"),
        },
    }
