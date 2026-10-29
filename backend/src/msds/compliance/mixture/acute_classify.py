"""급성독성 조립: 성상에 맞는 경로 전부를 계산해 설계서 v0.4 41장 trace 모양으로 돌려준다."""
from .acute import _FORM, _ROUTE, _no_content, _rows, mix_acute
from .ate_source import get_ate, inhal_forms

_ROUTES = [("oral", None, "HH_ACUTE_ORAL", "ATE-ORAL"), ("dermal", None, "HH_ACUTE_DERMAL", "ATE-DERMAL")]
_INHAL = {f: ("inhal", f, "HH_ACUTE_INHAL", f"ATE-INHAL-{f.upper()}") for f in _FORM}
_EXCLUDED = {"한계농도미만": "한계농도 미만", "이용불가": "자료 없음"}


def _range(row):
    """CSV 구분 행 → "0.05 < x ≤ 0.5"."""
    lo = f"{float(row['lower']):g} {'<' if row['lower_op'] == '>' else '≤'} " if row["lower_op"] else ""
    hi = f" {'<' if row['upper_op'] == '<' else '≤'} {float(row['upper']):g}" if row["upper_op"] else ""
    return f"{lo}x{hi}"


def _thresholds(route, form, sides, rule_id):
    rows = _rows(_ROUTE[route], _FORM.get(form))
    out = []
    for s in sides:
        row = next((x for x in rows if x["category"] == s["category"]), None)
        if row:
            rng = _range(row)
        else:  # 분류안됨: 고시 구분 중 가장 높은 상한을 넘는 값
            top = max((x for x in rows if x["in_notice"] == "Y"), key=lambda x: int(x["category"]))
            rng = f"x > {float(top['upper']):g}" if s["ate_mix"] is not None else None
        item = {"category": s["category"], "range": rng, "rule_id": rule_id}
        if item not in out:
            out.append(item)
    return out


def _input(c, ate, term):
    flags = (["ref_cat5"] if ate.get("ref_cat5") else []) + ([ate["note"]] if ate.get("note") else [])
    row = {"cas": c.get("cas"), "name": c["name"], "content": c["content"], "step": ate["step"], "flags": flags}
    use = term["사용여부"]["high"]
    if _no_content(c):
        flags.insert(0, "함량 없음")
    flags += [f for f in c.get("content_flags") or [] if f not in flags]
    row["flags"] = flags
    if use == "함량없음":
        return row | {"excluded": "함량 없음"}
    if use == "계산":
        return row | {"ate_used": ate["value"], "source": ate["src"], "share": term["share"]["high"]}
    if use == "미계산":  # 다른 성분의 함량이 없어 이 경로를 계산하지 않았다
        if ate["kind"] in ("value", "conversion"):
            return row | {"ate_used": ate["value"], "source": ate["src"], "share": None}
    reason = _EXCLUDED.get(use) or ("무독성" if ate["kind"] == "non_toxic" else "부등호 값")
    return row | {"excluded": reason}


def _one(comps, state_note, route, form, class_code, rule_id, knowledge_version):
    ates = [get_ate(c, route, form) for c in comps]
    mix = mix_acute([{"name": c["name"], "cas": c.get("cas"), "content": c["content"], "ate": a}
                     for c, a in zip(comps, ates)], route, form)
    low, high = mix["low"], mix["high"]
    lacking = "reason" in mix
    inputs = [_input(c, a, t) for c, a, t in zip(comps, ates, mix["terms"])]
    if low["ref_cat5"] or high["ref_cat5"]:  # 결과 ATEmix가 고시 밖 참고 구분5 구간
        for i in inputs:
            if "ate_used" in i and "ref_cat5" not in i["flags"]:
                i["flags"].append("ref_cat5")
    f2 = high["formula"] == "공식2"
    return {
        "class_code": class_code, "form": _FORM.get(form),
        "result": {"low": low["category"], "high": high["category"], "status": mix["status"]},
        "rule": {"id": "ATE-MIX-01", "basis": "고시 별표1",
                 "formula": "(100 − 이용불가)/ATEmix = Σ(Ci/ATEi)" if f2 else "100/ATEmix = Σ(Ci/ATEi)"},
        "inputs": inputs,
        "calc": {"unknown_pct": high["unknown_pct"], "formula_used": high["formula"],
                 "sum_low": low["sigma"], "sum_high": high["sigma"],
                 "ate_mix_low": low["ate_mix"], "ate_mix_high": high["ate_mix"],
                 "ref_cat5": {"low": low["ref_cat5"], "high": high["ref_cat5"]}},
        "thresholds": [] if lacking else _thresholds(route, form, [low, high], rule_id),
        "assumptions": [state_note] if route == "inhal" else [],
        "knowledge_version": knowledge_version,
    }


def classify_acute(comps, state=None, *, knowledge_version=None) -> list[dict]:
    comps = [{**c, "content": c.get("content") or {"low": None, "high": None}} for c in comps]
    forms = inhal_forms(state)
    note = "흡입 형태: 제품 성상으로 선택(D-06)" if forms else "제품 성상 미상 — 흡입 형태 전체 계산"
    routes = _ROUTES + [_INHAL[f] for f in (forms or _INHAL)]
    return [_one(comps, note, *r, knowledge_version) for r in routes]
