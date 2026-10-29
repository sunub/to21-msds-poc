"""성분 하나의 ATE를 수집 순서대로 고른다 (설계서 v0.4 21장, D-04·D-05·D-12·D-22)."""
from .acute import _FORM, _ROUTE, _rows, category_to_ate

_STATE_FORMS = {"기체": ["gas"], "액체": ["vapour", "mist"], "고체": ["mist"]}
_CLASS = {"oral": "HH_ACUTE_ORAL", "dermal": "HH_ACUTE_DERMAL", "inhal": "HH_ACUTE_INHAL"}
_EXACT = {"=", ">=", "<="}
_BOUND = {">", "<"}
# 행의 route·form은 영문(oral, vapour)과 한글(경구, 증기) 표기를 모두 받는다 (adapter의 tox는 한글)
_ROUTE_EN = {**{k: k for k in _ROUTE}, **{v: k for k, v in _ROUTE.items()}}
_FORM_EN = {**{k: k for k in _FORM}, **{v: k for k, v in _FORM.items()}}


def inhal_forms(state: str) -> list[str]:
    return list(_STATE_FORMS.get(state, []))


def _match(row, route, form):
    if _ROUTE_EN.get(row.get("route")) != route:
        return False
    return route != "inhal" or _FORM_EN.get(row.get("form")) == form


def _lowest(rows, route, form, unit):
    vals = [r["value"] for r in rows if _match(r, route, form) and r.get("op") in _EXACT
            and r.get("unit") == unit and r.get("value") is not None]
    return min(vals) if vals else None


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
            return {"kind": "conversion", "value": ate, "src": f"{src} 구분{cat} 환산", "step": 2, "ref_cat5": ref}
    return None


def get_ate(comp: dict, route: str, form: str | None = None, *, source_order=("환경부", "고용노동부")) -> dict:
    """반환: {"kind", "value", "src", "step", "ref_cat5"} — mix_acute 입력의 ate 칸과 같은 모양."""
    def out(kind, value, src, step, ref=False):
        return {"kind": kind, "value": value, "src": src, "step": step, "ref_cat5": ref}

    if comp.get("non_toxic"):
        return out("non_toxic", None, "무독성 성분", 5)
    unit = _rows(_ROUTE[route], _FORM.get(form))[0]["unit"]
    db, msds = comp.get("db") or [], comp.get("msds") or []
    if (v := _lowest(db, route, form, unit)) is not None:
        return out("value", v, "TO21 독성DB", 1)
    if hit := _from_class(comp, route, form, source_order):
        return hit
    if (v := _lowest(msds, route, form, unit)) is not None:
        return out("value", v, "MSDS 11항", 3)
    if any(_match(r, route, form) and r.get("op") in _BOUND for r in db + msds):
        return out("inequality", None, "부등호 값(> 또는 <)", 4)
    return out("unknown", None, "자료 없음", 6)
