"""성분 하나의 ATE를 수집 순서대로 고른다 (설계서 v0.4 21장, D-04·D-05·D-12·D-22)."""
from .acute import _FORM, _ROUTE, _rows, category_to_ate
from .params import has_param, param_list
from .units import to_target

_CLASS = {"oral": "HH_ACUTE_ORAL", "dermal": "HH_ACUTE_DERMAL", "inhal": "HH_ACUTE_INHAL"}
_EXACT = {"=", ">=", "<="}
_BOUND = {">", "<"}
# 행의 route·form은 영문(oral, vapour)과 한글(경구, 증기) 표기를 모두 받는다 (adapter의 tox는 한글)
_ROUTE_EN = {**{k: k for k in _ROUTE}, **{v: k for k, v in _ROUTE.items()}}
_FORM_EN = {**{k: k for k in _FORM}, **{v: k for k, v in _FORM.items()}}


def inhal_forms(state: str) -> list[str]:
    key = f"inhal_forms_{state}"  # 규칙 파일에 없는 성상은 형태를 정하지 않는다
    return param_list(key) if has_param(key) else []


def _match(row, route, form):
    if _ROUTE_EN.get(row.get("route")) != route:
        return False
    return route != "inhal" or _FORM_EN.get(row.get("form")) == form


def _lowest(rows, route, form, comp):
    """(최저값, 환산 설명). 단위·시간은 to_target으로 맞추고, 맞출 수 없는 행은 뺀다."""
    best = None
    for r in rows:
        if not (_match(r, route, form) and r.get("op") in _EXACT and r.get("value") is not None):
            continue
        t = to_target(r["value"], r.get("unit"), route, form, mw=comp.get("mw"),
                      density=comp.get("density"), hours=r.get("hours"))
        if t and (best is None or t["value"] < best[0]):
            best = (t["value"], t["note"])
    return best


def _from_class(comp, route, form, order):
    r, f = _ROUTE[route], _FORM.get(form)
    code = _CLASS[route]
    for src in order:
        found = []
        for c in comp.get("classes") or []:
            if c.get("class_code") != code or not str(c.get("source", "")).startswith(src):
                continue
            if route == "inhal" and _FORM_EN.get(c.get("route_form")) != form:
                continue
            ate = category_to_ate(r, f, c.get("category"))
            if ate is not None:
                found.append((ate, c["category"]))
        if found:
            ate, cat = min(found)  # 한 출처에 구분이 여럿이면 ATE가 가장 낮은(엄격한) 구분
            ref = any(x["category"] == cat and x["in_notice"] != "Y" for x in _rows(r, f))
            return {"kind": "conversion", "value": ate, "src": f"{src} 구분{cat} 환산", "step": 2, "ref_cat5": ref, "note": ""}
    return None


def get_ate(comp: dict, route: str, form: str | None = None, *, source_order=None) -> dict:
    """반환: {"kind", "value", "src", "step", "ref_cat5"} — mix_acute 입력의 ate 칸과 같은 모양."""
    def out(kind, value, src, step, ref=False, note=""):
        return {"kind": kind, "value": value, "src": src + (f" · {note}" if note else ""), "step": step,
                "ref_cat5": ref, "note": note}

    source_order = param_list("classification_source_order") if source_order is None else source_order
    if comp.get("non_toxic"):
        return out("non_toxic", None, "무독성 성분", 5)
    db, msds = comp.get("db") or [], comp.get("msds") or []
    if hit := _lowest(db, route, form, comp):
        return out("value", hit[0], "TO21 독성DB", 1, note=hit[1])
    if hit := _from_class(comp, route, form, source_order):
        return hit
    if hit := _lowest(msds, route, form, comp):
        return out("value", hit[0], "MSDS 11항", 3, note=hit[1])
    if any(_match(r, route, form) and r.get("op") in _BOUND for r in db + msds):
        return out("inequality", None, "부등호 값(> 또는 <)", 4)
    return out("unknown", None, "자료 없음", 6)
