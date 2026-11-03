"""도출한 표시 요소(derive_label)와 MSDS 2항의 그림문자·신호어·H코드를 비교한다 (설계서 v0.4 31장)."""
from .label import label_rules


def _finding(item, rule, derived, msds, *, verdict=None, missing=(), extra=()):
    return {"item": item, "verdict": verdict or rule["verdict"], "severity": rule.get("severity"),
            "rule_id": rule["rule_id"], "missing": sorted(missing), "extra": sorted(extra),
            "msds": msds, "derived": derived}


def _same(item, derived, msds):
    return {"item": item, "verdict": "일치", "severity": None, "rule_id": None, "missing": [], "extra": [],
            "msds": msds, "derived": derived}


def _h_codes(derived, msds, cmp, optional):
    d, m = set(derived), set(msds)
    missing, extra, out = d - m, m - d, []
    for opt in optional:  # 생략 가능한 H코드는 다른 코드가 함께 빠져도 불일치 사유가 아니라 참고다 (H314 있으면 H318 생략)
        if opt["optional"] in missing and opt["if_present"] in m:  # MSDS가 H314를 적었으면 H318 생략은 참고
            out.append(_finding("h_codes", opt, derived, msds, missing={opt["optional"]}))
            missing = missing - {opt["optional"]}
    if missing:
        out.append(_finding("h_codes", cmp["missing_h"], derived, msds, missing=missing))
    if extra:
        out.append(_finding("h_codes", cmp["extra_h"], derived, msds, extra=extra))
    return out or [_same("h_codes", derived, msds)]


def _pictograms(derived, msds, cmp, limit):
    d, m = set(derived), set(msds)
    if d == m:
        return [_same("pictograms", derived, msds)]
    if len(d) >= limit["min_derived"] and len(m) == limit["max_display"] and m <= d:
        return [_finding("pictograms", limit, derived, msds, verdict="일치", missing=d - m)]
    return [_finding("pictograms", cmp["pictogram_diff"], derived, msds, missing=d - m, extra=m - d)]


def compare_label(derived: dict, msds: dict) -> list[dict]:
    """derived: derive_label 결과, msds: {"pictograms", "signal_word", "h_codes"}. 항목별 발견 목록."""
    rules = label_rules()
    cmp = rules["compare"]
    out = []
    for item in ("h_codes", "pictograms", "signal_word"):
        d = derived[item]
        m = msds.get(item)
        m = [x for x in m if x is not None] if isinstance(m, list) else m
        if not m:  # None 또는 빈 목록. 양쪽 다 비었으면 비교할 것이 없다
            out.append(_same(item, d, m) if not d else _finding(item, cmp["msds_empty"], d, m, missing=d if isinstance(d, list) else [d]))
        elif item == "h_codes":
            out += _h_codes(d, m, cmp, rules["h_code_optional"])
        elif item == "pictograms":
            out += _pictograms(d, m, cmp, rules["pictogram_limit"])
        else:
            out.append(_same(item, d, m) if d == m else _finding(item, cmp["signal_diff"], d, m))
    return out
