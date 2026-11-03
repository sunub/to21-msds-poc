"""혼합물 분류 결과 조립: 항목 하나(classify_item)와 건강·환경 전체(classify_mixture_all).

설계서 41장 모양(class_code, result, rule, inputs, calc, thresholds, assumptions, knowledge_version)으로 만든다.
MSDS 기재와의 비교(판정 4종·심각도)는 하지 않는다.
"""
from .ate_source import inhal_forms
from .acute_classify import classify_acute
from .class_inputs import _SOURCE_NAME
from .evaluate_item import evaluate_item, include_min_for
from .physical import classify_physical
from .rule_eval import evaluate_rules, evaluate_rules_trace
from .rules_loader import load_mixture_rules, lookup_class

_EVALUATED = {"additive", "cutoff", "summation", "property"}


def _pair(low, high):
    return low if low == high else {"low": low, "high": high}


def _trace(rules, item, ev):
    """evaluate_item 결과와 같은 입력으로 evaluate_rules_trace를 돌린다."""
    i = ev["inputs"]
    t = evaluate_rules_trace(item.get("rules") or [], i["comps"], other=i["other"], flags=i["flags"], props=i["props"],
                             m=i["m"], include_min=i["include_min"])
    assert t["category"] == ev["category"], (t["category"], ev["category"])  # 같은 입력이면 같은 판정이어야 한다
    return t


def _limit(imin, key):
    return imin.get(key.split(":")[0], 0) if isinstance(imin, dict) else imin or 0


def _inputs(item_id, components, evs, imin):
    used = {(u["cas"], u["name"], m): [] for m in ("low", "high") for u in evs[m]["used"]}
    for m in ("low", "high"):
        for u in evs[m]["used"]:
            used[(u["cas"], u["name"], m)].append(u)
    out = []
    for c in components:
        who = (c.get("cas"), c.get("name"))
        keys = {u["key"] for m in ("low", "high") for u in used.get(who + (m,), [])}
        no_content = [m for m in ("low", "high") if c.get(m) is None]
        below = [m for m in ("low", "high") if c.get(m) is not None and used.get(who + (m,))
                 and all(c[m] < _limit(imin, u["key"]) for u in used[who + (m,)])]
        flags = list(c.get("flags") or []) + [f"한계농도 미만({m})" for m in below] + [f"함량 없음({m})" for m in no_content]
        if keys and len(below) == 2:
            excluded = "한계농도 미만"
        elif keys:
            excluded = None
        elif c.get("non_toxic"):
            excluded = "무독성"
        elif len(no_content) == 2:
            excluded = "함량 없음"
        else:
            excluded = "해당 분류 없음" if c.get("class_rows") else "분류 정보 없음"
        out.append({"cas": c.get("cas"), "name": c.get("name"), "content": {"low": c.get("low"), "high": c.get("high")},
                    "used_as": sorted(keys), "flags": flags, "excluded": excluded})
    return out


def _only_by_sum(item, ev) -> bool:
    """같은 구분 합산(D-16) 때문에 나온 구분인가. 고시 문언대로 성분 하나씩 보면 합산 결과만큼 위험하지 않은 경우다 (설계서 35장)."""
    if item.get("aggregate") != "sum" or ev["category"].startswith("근거부족"):
        return False
    i = ev["inputs"]
    one = lambda key, v: evaluate_rules(item["rules"], {key: [v]}, other=i["other"], flags=i["flags"], props=i["props"],
                                        m=i["m"], include_min=i["include_min"])
    order = [str(r["category"]) for r in item["rules"]] + ["분류안됨"]
    alone = {one(k, v) for k, vals in i["comps"].items() for v in vals} or {"분류안됨"}
    return min(order.index(c) for c in alone) > order.index(ev["category"])


def classify_item(item_id, components, mixture_props, *, rules=None, source_order=None) -> dict:
    """항목 하나를 하한·상한으로 각각 판정하고 근거와 함께 41장 모양으로 돌려준다."""
    rules = rules or load_mixture_rules()
    item = rules["classes"][item_id]
    if item["method"] not in _EVALUATED:
        return {"class_code": item_id, "skipped": item["method"]}
    evs = {m: evaluate_item(item_id, components, mixture_props, mode=m, rules=rules, source_order=source_order)
           for m in ("low", "high")}
    tr = {m: _trace(rules, item, evs[m]) for m in evs}
    cats = {m: evs[m]["category"] for m in evs}
    lack = {m: c for m, c in cats.items() if c.startswith("근거부족")}
    status = "근거부족" if lack else "확정" if cats["low"] == cats["high"] else "경계"
    when = {m: next((r["when"] for r in tr[m]["checked"] if r["result"] is True), None) for m in tr}
    imin = evs["low"]["inputs"]["include_min"]
    out = {
        "class_code": item_id, "form": None,
        "result": {"low": None if "low" in lack else cats["low"], "high": None if "high" in lack else cats["high"],
                   "status": status},
        "rule": {"id": _pair(tr["low"]["rule_id"], tr["high"]["rule_id"]), "basis": rules["meta"]["source"],
                 "formula": _pair(when["low"], when["high"])},
        "inputs": _inputs(item_id, components, evs, imin),
        "calc": {"values": {m: {k: v for r in tr[m]["checked"] for k, v in r["values"].items()} for m in tr},
                 "include_min": imin, "m": evs["low"]["inputs"]["m"]},
        "thresholds": [{"side": m, "category": next(x["category"] for x in item["rules"] if x["id"] == r["id"]),
                        "rule_id": r["id"], "when": r["when"], "result": r["result"]}
                       for m in tr for r in tr[m]["checked"]],
        "assumptions": list(dict.fromkeys(a for m in evs for a in evs[m]["assumptions"])),
        "knowledge_version": rules["meta"]["version"],
    }
    if any(_only_by_sum(item, evs[m]) for m in evs):
        out["result"]["to21_sum"] = True
    if lack:
        out["result"]["reason"] = _pair(cats["low"], cats["high"]) if len(lack) == 2 else next(iter(lack.values()))
    if item.get("extra_rules"):
        out["extra"] = {m: evs[m].get("extra", []) for m in evs}
    return out


def _real_inhal_form(comp: dict) -> str | None:
    """D-22: 환경부 '흡입:가스'가 붙은 액체·고체 물질의 실제 흡입 형태. 다른 출처 분류, 독성값, 성상 순으로 정한다. 기체 물질은 그대로 둔다."""
    state = comp.get("state")
    if state not in ("액체", "고체"):
        return None
    for row in comp.get("class_rows") or []:
        hit = lookup_class(row["result_code"])
        if hit and hit[0] == "HH_ACUTE_INHAL" and hit[2] in ("vapour", "mist"):
            return hit[2]
    from_tox = next((r["form"] for r in comp.get("db") or [] if r.get("route") == "inhal" and r.get("form") in ("vapour", "mist")), None)
    return from_tox or inhal_forms(state)[0]


def _acute_components(components) -> list[dict]:
    """classify_acute 입력으로 바꾼다.

    adapter.to_acute_components(GhsInputs)의 모양(cas_no, content_lower/upper, tox)과는 다르다. 여기서는
    성분 dict에 db·msds(또는 tox)·non_toxic·mw·density가 있으면 그대로 쓰고, 기준 분류(classes)는 class_rows에서
    lookup_class로 만든다.
    """
    out = []
    for c in components:
        classes = []
        real_form = _real_inhal_form(c)
        for row in c.get("class_rows") or []:
            hit = lookup_class(row["result_code"])
            if hit and hit[0].startswith("HH_ACUTE"):
                form = real_form if real_form and row["source"] == "KR02" and hit[2] == "gas" else hit[2]
                classes.append({"class_code": hit[0], "category": hit[1], "route_form": form,
                                "source": _SOURCE_NAME.get(row["source"], row["source"])})
        out.append({"cas": c.get("cas") or c.get("cas_no"), "name": c.get("name"),
                    "content": {"low": c.get("low"), "high": c.get("high")}, "non_toxic": c.get("non_toxic", False),
                    "db": c.get("db") or [], "classes": classes, "msds": c.get("msds") or c.get("tox") or [],
                    "mw": c.get("mw"), "density": c.get("density")})
    return out


def classify_mixture_all(components, mixture_props, *, state=None, rules=None, source_order=None,
                         ate_intervals=False, physical=None) -> list[dict]:
    """규칙표의 모든 항목을 순서대로 처리한다. transport·compare는 {"class_code", "skipped"}로 남긴다.

    physical(physical.physical_inputs(msds_item))를 주면 transport·compare 항목을 판정한다(기본은 건너뜀).
    ate_intervals=True 이면 급성독성의 부등호(>·<)·범위를 구간으로 계산한다(기본은 기존 규칙 D-12)."""
    rules = rules or load_mixture_rules()
    out, acute_done = [], False
    for name, item in rules["classes"].items():
        if item["method"] == "ate":
            if not acute_done:  # 급성독성 3개 항목은 classify_acute 한 번으로 경로별 결과가 나온다
                out += classify_acute(_acute_components(components), state, knowledge_version=rules["meta"]["version"],
                                  intervals=ate_intervals)
                acute_done = True
        elif physical is not None and item["method"] in ("transport", "compare"):
            out.append(classify_physical(name, item, components, mixture_props, physical, state=state, rules=rules))
        else:
            out.append(classify_item(name, components, mixture_props, rules=rules, source_order=source_order))
    return out
