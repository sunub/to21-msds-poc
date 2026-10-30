"""규칙표의 건강·환경 항목 하나를 evaluate_rules로 판정한다 (구분 문자열까지만. trace 조립은 하지 않는다).

입력은 dict로만 받는다. 성분: {"cas","name","low","high","class_rows":[{"result_code","source"}],
"flags":[표시 이름], "m": M 계수(숫자 또는 {class_code: 숫자})}, 혼합물 물성: {"PH","VISCOSITY_40","STATE",…}.
"""
import ast

from ..knowledge import load_cut_off
from .class_inputs import build_class_inputs
from .rule_eval import apply_include_min, evaluate_rules, parse_when
from .rules_loader import load_mixture_rules

_SKIPPED = {"ate", "transport", "compare"}


def _rule_exprs(item):
    exprs = [r["when"] for k in ("rules", "extra_rules") for r in item.get(k) or []]
    return exprs + ([item["flag_if"]] if item.get("flag_if") else [])


def rule_names(rules=None) -> dict[str, set]:
    """규칙표 when에서 flag(...)·prop(...)에 쓰는 이름 전체."""
    rules = rules or load_mixture_rules()
    out = {"flag": set(), "prop": set()}
    for item in rules["classes"].values():
        for expr in _rule_exprs(item):
            for n in ast.walk(parse_when(expr)):
                if isinstance(n, ast.Call) and n.func.id in out:
                    out[n.func.id].add(n.args[0].value)
    return out


def cut_off_include_min(item_id):
    """cut_off.csv의 항목 한계농도를 include_min 모양(숫자 또는 {구분: 숫자})으로. 항목이 없으면 None."""
    rows = load_cut_off().get(item_id)
    if not rows:
        return None
    if len(rows) == 1 and rows[0]["categories"] is None:
        return rows[0]["threshold_value"]
    return {c: r["threshold_value"] for r in rows for c in (r["categories"] or [])}


def include_min_for(item_id, rules=None):
    """규칙표 항목의 include_min. 규칙표에 없으면 cut_off.csv 값."""
    rules = rules or load_mixture_rules()
    value = rules["classes"][item_id].get("include_min")
    return cut_off_include_min(item_id) if value is None else value


def check_include_min(rules=None) -> dict:
    """규칙표 include_min과 cut_off.csv 비교. {"not_in_cut_off": [...], "differs": {항목: (규칙표, cut_off)}}."""
    rules = rules or load_mixture_rules()
    out = {"not_in_cut_off": [], "differs": {}}
    for name, item in rules["classes"].items():
        if item.get("include_min") is None:
            continue
        csv_value = cut_off_include_min(name)
        if csv_value is None:
            out["not_in_cut_off"].append(name)
        elif csv_value != item["include_min"]:
            out["differs"][name] = (item["include_min"], csv_value)
    return out


def build_flags(components, mixture_props, *, mode, include_min=None, rules=None) -> dict:
    """{flag 이름: 표시가 붙은 성분의 함량 합}. 규칙표가 쓰는 이름만 만들고, 표시가 없는 이름은 넣지 않는다.

    ph_extreme은 규칙표에서 'pH 극단 성분' 표시라 성분의 flags로 받는다. 혼합물 pH는 prop("PH")로 판정한다.
    """
    names = rule_names(rules)["flag"]
    out = {}
    for c in components:
        pct = c.get(mode)
        if pct is None or pct < (include_min if isinstance(include_min, (int, float)) else 0):
            continue
        for f in c.get("flags") or []:
            if f in names:
                out[f] = out.get(f, 0) + pct
    return out


def build_props(mixture_props, rules=None) -> dict:
    """규칙표 prop(...) 이름만 담고, 값이 None이면 담지 않는다 (없으면 evaluate_rules가 근거부족)."""
    names = rule_names(rules)["prop"]
    return {k: v for k, v in (mixture_props or {}).items() if k in names and v is not None}


def build_m(item_id, item, components, used):
    """(m, [(함량, M)] 또는 None, 설명). rule_eval의 sumx는 m 하나를 합 전체에 곱한다.

    구분 "1" 성분의 M이 모두 같으면 그 값을 m으로 쓰고(정확), 다르면 함량에 M을 먼저 곱해 m=1로 넘긴다.
    """
    default = item.get("m_factor_default", 1)
    who = {(c.get("cas"), c.get("name")): c for c in components}
    entries = [u for u in used if u["class_code"] == item_id and u["key"] == "1"]
    ms = []
    for u in entries:
        m = who[(u["cas"], u["name"])].get("m")
        m = m.get(item_id) if isinstance(m, dict) else m
        ms.append(default if m is None else m)
    if len(set(ms)) <= 1:
        return (ms[0] if ms else default), None, None
    note = ("성분마다 M 계수가 달라 구분 1 함량에 M을 먼저 곱하고 m=1로 넘김 "
            "(rule_eval sumx는 m 하나만 받음. 같은 구분의 sum()도 가중된 값이 됨)")
    return 1, [(u["content"], m) for u, m in zip(entries, ms)], note


def evaluate_item(item_id, components, mixture_props, *, mode, rules=None, class_map=None, source_order=None) -> dict:
    if class_map is not None:
        raise NotImplementedError("class_map 지정은 지원하지 않음 (build_class_inputs는 기본 class_map만 씀)")
    rules = rules or load_mixture_rules()
    item = rules["classes"][item_id]
    if item["method"] in _SKIPPED:
        return {"item": item_id, "mode": mode, "category": None, "skipped": item["method"]}

    built = build_class_inputs(components, mode=mode, source_order=source_order)
    by_class, assumptions = built["by_class"], list(built["assumptions"])
    imin = include_min_for(item_id, rules)
    comps = dict(by_class.get(item_id, {}))
    # other()는 규칙 해석기가 한계농도를 걸러 주지 않으므로, 그 항목 자신의 한계농도로 미리 거른다
    other = {c: apply_include_min(k, include_min_for(c, rules) if c in rules["classes"] else None)
             for c, k in by_class.items()}
    m, weighted, note = build_m(item_id, item, components, built["used"]) if item["method"] == "summation" else (1, None, None)
    if note:
        assumptions.append(note)
        lim = imin.get("1", 0) if isinstance(imin, dict) else imin or 0
        comps["1"] = [pct * mf for pct, mf in weighted if pct >= lim]  # 한계농도는 M을 곱하기 전 함량으로 거른다
    flags = build_flags(components, mixture_props, mode=mode, include_min=imin, rules=rules)
    props = build_props(mixture_props, rules)
    kw = {"other": other, "flags": flags, "props": props, "m": m, "include_min": imin}
    out = {"item": item_id, "mode": mode,
           "category": evaluate_rules(item.get("rules") or [], comps, **kw),
           "inputs": {"comps": comps, **kw},
           "used": [u for u in built["used"] if u["class_code"] == item_id], "dropped": built["dropped"],
           "assumptions": assumptions}
    extra = [{"id": r["id"], "category": r["category"], "effect": r.get("effect")} for r in item.get("extra_rules") or []
             if evaluate_rules([r], comps, **kw) != "분류안됨"]
    if item.get("extra_rules"):
        out["extra"] = extra
    return out


def evaluate_item_range(item_id, components, mixture_props, **kw) -> dict:
    """함량 하한(low)·상한(high)으로 각각 판정한다. agree는 두 구분이 같은지만 표시한다."""
    low = evaluate_item(item_id, components, mixture_props, mode="low", **kw)
    high = evaluate_item(item_id, components, mixture_props, mode="high", **kw)
    return {"low": low, "high": high, "agree": low["category"] == high["category"]}
