"""3항 함량 표기를 low/high로 바꾼다 (설계서 v0.4 26장). 표에 없는 표기는 만들지 않고 None으로 표시한다."""

from .params import param

_PERCENT = {None, "", "%", "wt%", "w/w%"}


def _get(c, key):
    return c.get(key) if isinstance(c, dict) else getattr(c, key, None)


def _q(c):
    q = _get(c, "content")
    return q if isinstance(q, dict) else (q.model_dump() if q is not None else {})


def _unit_flag(unit):
    """(쓸 수 있는가, flag). % 계열이 아니면 값은 그대로 쓰되 단위를 적고, % 계열 밖이면 쓰지 않는다."""
    if unit in _PERCENT:
        return True, ["단위 없음(%로 간주)"] if unit in (None, "") else []
    return (True, [f"단위 참고({unit})"]) if unit.endswith("%") else (False, [f"단위 미지원({unit})"])


def _first_pass(c):
    q, note = _q(c), _get(c, "content_note")
    out = {"low": None, "high": None, "high_exclusive": False, "flags": [], "open_high": False}
    if _get(c, "trade_secret"):
        out["flags"].append("영업비밀")
    value, lo, hi = q.get("value"), q.get("lower"), q.get("upper")
    if value is None and lo is None and hi is None:
        if note in ("미검출", "극미량"):
            out.update(low=0.0, high=float(param("trace_amount_upper_percent")))
            out["flags"].append("극미량(가정)")
        else:
            out["flags"].append("함량 없음")
        return out
    ok, flags = _unit_flag(q.get("unit"))
    out["flags"] += flags
    if not ok:
        return out
    if value is not None:
        out.update(low=float(value), high=float(value))
    elif lo is not None and hi is not None:
        out.update(low=float(lo), high=float(hi))
    elif lo is not None:  # "10 이상": 상한은 다른 성분 하한으로 정한다
        out.update(low=float(lo), open_high=True)
    elif q.get("upper_op") == "<":  # "1 미만"
        out.update(low=0.0, high=float(hi), high_exclusive=True)
    else:
        out["flags"].append("표기 미지원(상한만, 이하)")
    return out


def content_range(components) -> list[dict]:
    """성분마다 {"low","high","high_exclusive","flags"}. 입력 순서 그대로."""
    rows = [_first_pass(c) for c in components]
    lows = [r["low"] or 0 for r in rows]
    over = sum(lows) > 100
    for i, r in enumerate(rows):
        if r.pop("open_high"):
            r["high"] = min(100.0, 100 - (sum(lows) - lows[i]))
            r["flags"].append("상한 계산(100−다른 성분 하한)")
            if r["high"] < r["low"]:
                r["high"] = r["low"]
        if over and "합계 100 초과" not in r["flags"]:
            r["flags"].append("합계 100 초과")
    return rows


def with_ranges(components) -> list[dict]:
    """classify_acute 입력용: 성분 dict에 content {"low","high"}와 content_flags를 더해 돌려준다."""
    out = []
    for c, r in zip(components, content_range(components)):
        base = dict(c) if isinstance(c, dict) else c.model_dump()
        out.append({**base, "content": {"low": r["low"], "high": r["high"]},
                    "content_exclusive": r["high_exclusive"], "content_flags": r["flags"]})
    return out
