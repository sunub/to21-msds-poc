"""GhsInputs 를 label.py·acute.py 계산 함수가 받는 모양으로 바꾸는 얇은 어댑터.

함량 범위에서 대표값을 고르는 일은 여기서 하지 않는다. lower/upper 를 그대로 넘긴다.
"""
from ..ghs.models import GhsInputs

_HOURS = {"min": 1 / 60, "hr": 1, "day": 24, "week": 168}  # 스키마 duration_unit 값
_ROUTE = {"TX_ORAL": "경구", "TX_DERMAL": "경피"}  # 흡입은 TX_INHAL 로 시작하는 endpoint 전부


def _route(endpoint: str | None) -> str | None:
    if endpoint in _ROUTE:
        return _ROUTE[endpoint]
    return "흡입" if (endpoint or "").startswith("TX_INHAL") else None


def to_label_classes(inputs: GhsInputs) -> list[tuple[str, str | None]]:
    """derive_label 입력. class_code 가 없는 줄은 뺀다. route_form 은 버린다."""
    return [(c.class_code, c.category) for c in inputs.hazard.classes if c.class_code]


def _single(q: dict) -> tuple[str, float] | None:
    """q 에서 (부호, 값) 하나를 만든다. value 가 있으면 "=", 없으면 부등호 쪽 값."""
    if q.get("value") is not None:
        return "=", q["value"]
    for op, v in ((q.get("lower_op"), q.get("lower")), (q.get("upper_op"), q.get("upper"))):
        if op and v is not None:
            return op, v
    return None


def to_acute_components(inputs: GhsInputs) -> list[dict]:
    out = []
    for c in inputs.components:
        cont = c.content
        lower = upper = None
        if cont is not None:
            lower = cont.value if cont.value is not None else cont.lower
            upper = cont.value if cont.value is not None else cont.upper
        tox = []
        for t in inputs.toxicity:
            route = _route(t.get("endpoint"))
            if route is None or str(t.get("comp_ref")) != str(c.seq):
                continue
            one = _single(t.get("q") or {})
            if one is None:
                continue
            row = {"route": route, "op": one[0], "value": one[1], "unit": t["q"].get("unit")}
            if route == "흡입":  # acute.py 의 ATE 표가 흡입은 form(가스·증기·분진·미스트)별이다
                row["form"] = t.get("physical_form")
            if t.get("duration_value") is not None and t.get("duration_unit") in _HOURS:
                row["hours"] = t["duration_value"] * _HOURS[t["duration_unit"]]
            tox.append(row)
        out.append({"seq": c.seq, "name": c.name, "cas_no": c.cas_no,
                    "content_lower": lower, "content_upper": upper, "content_unit": "%", "tox": tox})
    return out


def stated_mix_ate(inputs: GhsInputs) -> list[dict]:
    """MSDS 가 직접 적은 혼합물 ATE (comp_ref == "MIX"). 계산에 쓰지 않고 비교용으로만 둔다."""
    out = []
    for t in inputs.toxicity:
        route, q = _route(t.get("endpoint")), t.get("q") or {}
        if route is None or str(t.get("comp_ref")) != "MIX":
            continue
        if not any(q.get(k) is not None for k in ("value", "lower", "upper")):
            continue
        out.append({"route": route, "value": q.get("value"),
                    "lower_op": q.get("lower_op"), "lower": q.get("lower"),
                    "upper_op": q.get("upper_op"), "upper": q.get("upper"), "unit": q.get("unit")})
    return out
