"""급성독성 혼합물 ATEmix 계산 (고시 별표1 3.1)."""
import csv
import operator
from pathlib import Path

RULES = Path(__file__).resolve().parents[1] / "rules" / "acute_tox_ate.csv"
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


def _rows(route, form):
    with open(RULES, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)
                if r["route"] == route and (r["form"] or None) == (form or None)]


def category_to_ate(route, form, category):
    for r in _rows(route, form):
        if r["category"] == str(category):
            return float(r["ate_convert"])
    return None


def _ok(value, op, bound):
    return not op or OPS[op](value, float(bound))


def value_to_category(route, form, value):
    for r in _rows(route, form):
        if r["in_notice"] != "Y":
            continue
        if _ok(value, r["lower_op"], r["lower"]) and _ok(value, r["upper_op"], r["upper"]):
            return r["category"]
    return None


def ate_mix(parts):
    unknown = sum(p["c"] for p in parts if not p["known"])
    total = sum(p["c"] / p["ate"] for p in parts if p["ate"])
    if total == 0:
        return None, "공식1" if unknown <= 10 else "공식2"
    if unknown <= 10:
        return 100 / total, "공식1"
    return sum(p["c"] for p in parts if p["known"]) / total, "공식2"


_ROUTE = {"oral": "경구", "dermal": "경피", "inhal": "흡입"}
_FORM = {"gas": "가스", "vapour": "증기", "mist": "분진·미스트"}


def _ref_cat5(route, value):
    """고시 본문 밖 구분5(in_notice=N) 구간에 드는지. 표에 구분5 행이 없으면 False."""
    return any(r["category"] == "5" and _ok(value, r["lower_op"], r["lower"]) and _ok(value, r["upper_op"], r["upper"])
               for r in _rows(route, None))


def _no_content(c):
    """함량이 없다: content가 None이거나 low·high 중 하나라도 None."""
    ct = c.get("content")
    return not ct or ct.get("low") is None or ct.get("high") is None


def _side(comps, side, route, form, include_min, unknown_limit):
    sigma = unknown = 0.0
    use, part = [], []
    for c in comps:
        if _no_content(c):  # 여기까지 온 함량 없는 성분은 non_toxic·inequality뿐이라 Σ·이용불가에 영향이 없다
            use.append("이용가능")
            part.append(None)
            continue
        pct, kind = c["content"][side], c["ate"]["kind"]
        if pct < include_min:
            use.append("한계농도미만")
        elif kind in ("value", "conversion"):
            part.append(pct / c["ate"]["value"])
            sigma += part[-1]
            use.append("계산")
        elif kind == "unknown":
            unknown += pct
            use.append("이용불가")
        else:  # inequality, non_toxic: Σ에는 넣지 않고 이용 가능 성분으로만 센다
            use.append("이용가능")
        if len(part) < len(use):
            part.append(None)
    formula = "공식2" if unknown > unknown_limit else "공식1"
    ate = (100 - unknown if formula == "공식2" else 100) / sigma if sigma else None
    cat = value_to_category(route, form, ate) if ate is not None else None
    return {"ate_mix": ate, "category": cat or "분류안됨", "formula": formula, "unknown_pct": unknown,
            "ref_cat5": cat is None and ate is not None and route != "흡입" and _ref_cat5(route, ate),
            "sigma": sigma}, use, [p / sigma if p is not None and sigma else None for p in part]


def _insufficient(comps):
    """함량 없는 성분 때문에 이 경로를 계산할 수 없다. 그 성분을 빼고 계산하지 않는다."""
    side = {"ate_mix": None, "category": None, "formula": None, "unknown_pct": None, "ref_cat5": False, "sigma": None}
    blocked = lambda c: _no_content(c) and c["ate"]["kind"] in ("value", "conversion", "unknown")
    use = {s: "함량없음" for s in ("low", "high")}
    return {"low": dict(side), "high": dict(side), "status": "근거부족", "reason": "함량 없음",
            "terms": [{"name": c["name"], "content": c.get("content"), "ate": c["ate"].get("value"),
                       "src": c["ate"].get("src"), "step": c["ate"].get("step"),
                       "사용여부": use if blocked(c) else {s: "미계산" for s in use},
                       "share": {"low": None, "high": None}} for c in comps]}


def mix_acute(comps, route, form=None, *, include_min=1.0, unknown_limit=10):
    """성분별 ATE로 혼합물 급성독성 ATEmix와 구분을 함량 하한(low)·상한(high) 각각 계산한다.

    comps: [{"name","cas","content":{"low","high"},"ate":{"kind","value","src","step"}}]
    route: oral|dermal|inhal, form: gas|vapour|mist (inhal만)
    """
    r, f = _ROUTE[route], _FORM.get(form)
    if any(_no_content(c) and c["ate"]["kind"] in ("value", "conversion", "unknown") for c in comps):
        return _insufficient(comps)
    out, uses, shares = {}, {}, {}
    for side in ("low", "high"):
        out[side], uses[side], shares[side] = _side(comps, side, r, f, include_min, unknown_limit)
    lack = any(out[s]["ate_mix"] is None and out[s]["unknown_pct"] > 0 for s in out)
    same = out["low"]["category"] == out["high"]["category"]
    out["status"] = "근거부족" if lack else "확정" if same else "경계"
    out["terms"] = [{"name": c["name"], "content": c.get("content"), "ate": c["ate"].get("value"),
                     "src": c["ate"].get("src"), "step": c["ate"].get("step"),
                     "사용여부": {s: uses[s][i] for s in uses},
                     "share": {s: shares[s][i] for s in shares}} for i, c in enumerate(comps)]
    return out
