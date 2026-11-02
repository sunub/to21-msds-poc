"""2차 정합성 검증 묶음: 추출 JSON 한 건 → 2항·15항 판정을 설계서 44장 결과 구조(consistency 블록)로 만든다.

    run_consistency(doc, repo=None, msds_index=0) → {"doc_id", "msds_index", "consistency": {...}}
    repo: None 이면 로컬 HTODB(PostgreSQL), htodb.csv_repo.CsvRepo() 면 샘플 CSV.

흐름(설계서 8장): 입력 정리(loader) → 판별(classifier) → 2항(혼합물: mixture 계산 + verdict / 단일물질: 기준 분류 + verdict)
→ 15항(sec15_judge) → 판정 집계(summary). 판정·구분 값은 규칙과 계산으로만 정하고, LLM 설명은 이 결과를 읽기만 한다.
"""
from collections import Counter

from .classifier import product_type
from .htodb.reference import ReferenceProvider
from .htodb.regulation import RegulationProvider
from .loader import load_inputs
from .mixture.build_components import build_components
from .mixture.class_lookup_db import make_db_class_lookup, make_db_tox_lookup
from .mixture.classify_mixture import classify_mixture_all
from .mixture.physical import physical_inputs
from .mixture.rules_loader import load_mixture_rules
from .mixture.verdict import _order, _rank, aggregate_verdicts
from .sec15_judge import judge_sec15

ENGINE_VERSION = "0.1.0"
SINGLE_ASSUMPTIONS = [
    "단일물질은 지식DB 기준 분류(D-05 항목 단위 환경부→고용노동부)를 그대로 '우리 결과'로 보고 MSDS 2항과 비교(설계서 18장)",
    "기준 분류에 없는 항목을 MSDS만 적었으면 근거부족(설계서 18장: 두 출처 모두 없음 → 근거부족)",
    "같은 항목에 기준 구분이 여럿이면 가장 위험한 구분으로 비교",
]


def _single_2(inputs: dict, item: dict, provider: ReferenceProvider) -> dict:
    comps = inputs.get("components") or []
    cas = comps[0].get("cas_no") if comps else None
    know = provider.get_reference(cas, inputs.get("as_of_date")) if cas else None
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
    out = aggregate_verdicts(results, msds_classes, rules=rules)
    why = ("성분 CAS가 없음" if not cas else (know or {}).get("reason") if not (know or {}).get("knowledge_version")
           else "지식DB에 이 항목의 기준 분류가 없음(환경부·고용노동부 모두 없음, 설계서 18장)")
    for v in out["verdicts"]:
        v["assumptions"] = v["assumptions"] + SINGLE_ASSUMPTIONS
        if v["verdict"] == "근거부족" and v["reason"] == "우리 결과에 같은 항목이 없음":
            v["reason"] = why
    out["excluded"] += [{"class_code": c["class_code"], "form": c["route_form"], "status": "참고",
                         "msds_value": None, "our_value": c["category"],
                         "reason": f"국내 고시 밖 구분(class_map '참고', D-18) — {c['source']}"}
                        for c in (know or {}).get("reference_only") or []]
    out["knowledge_version"] = (know or {}).get("knowledge_version")
    return out


def _mixture_2(item: dict, repo) -> tuple[dict, list, list]:
    b = build_components(item, make_db_class_lookup(repo), make_db_tox_lookup(repo))
    results = classify_mixture_all(b["components"], b["mixture_props"], state=b["mixture_props"].get("STATE"),
                                   physical=physical_inputs(item))
    out = aggregate_verdicts(results, (item.get("hazard") or {}).get("classes"))
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
    f2 = [{"id": f"F-2-{i:03d}", "section": "2", **v} for i, v in enumerate(s2["verdicts"], 1)]
    f15 = [{"id": f"F-15-{i:03d}", **v} for i, v in enumerate(s15["verdicts"], 1)]
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
            "excluded": [{"section": "2", **e} for e in s2["excluded"]] + s15["excluded"],
            "gaps": gaps, "assumptions": assumptions, "missing": inputs.get("missing"),
        },
    }
