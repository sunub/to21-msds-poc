"""classify_mixture_all 결과와 공급사(MSDS) 기재 분류를 항목별로 비교해 판정 4종·유형·심각도를 붙인다.

판정 이름·유형·심각도·근거 규칙 id 는 아래 상수 한 곳에 모았다. 유형 이름과 심각도는 설계서 7장·18장
(규칙표 v0.3 severity.yaml)을 따르고, 근거 규칙 id(VRD-*)는 설계서에 없어 우리 쪽 번호를 쓴다. 항목 필드는 2항에 한정된 이름을 쓰지 않아 15항 비교도 같은 모양으로 쓸 수 있다.
"""
from ..single import _main, _same
from .acute import _rows
from .rules_loader import load_mixture_rules

# ── 상수 (설계서 7장·18장, 규칙표 v0.3 severity.yaml) ─────────────────────
MATCH, MISMATCH, BORDER, LACK = "일치", "불일치", "경계", "근거부족"
# 틀림의 네 경우(안쪽 구분). rule_id 와 이유 문장은 네 경우를 나눠 쓰고, 결과의 type 은 설계서 2항 이름 두 가지로 낸다.
UNDER, OVER, MISSING, EXTRA = "under", "over", "missing", "extra"
# 설계서 18장: MSDS 미기재 또는 낮은 구분 → 과소분류, MSDS가 더 높은 구분·추가 기재 → 과대분류
TYPE_NAME = {UNDER: "과소분류", MISSING: "과소분류", OVER: "과대분류", EXTRA: "과대분류"}
SEVERITY = {UNDER: "높음", MISSING: "높음", OVER: "낮음", EXTRA: "낮음"}
RULE_IDS = {"match": "VRD-1", "type": {UNDER: "VRD-2", OVER: "VRD-3", MISSING: "VRD-4", EXTRA: "VRD-5"},
            "border": "VRD-6", "lack": "VRD-7"}
NOT_COMPARED = ("해당 없음", "대조")  # 비교 대상에서 빼는 우리 결과 status
NO_CLASS = "분류안됨"
_INF = float("inf")
_ACUTE_ROUTE = {"HH_ACUTE_ORAL": "경구", "HH_ACUTE_DERMAL": "경피", "HH_ACUTE_INHAL": "흡입"}
BASE_ASSUMPTIONS = [
    "rule_id(VRD-1~7)는 설계서에 정의가 없어 우리 쪽 번호를 씀(상수는 verdict.py 상단)",
    "구분 순서는 규칙표 rules 의 나열 순서(위험한 구분부터), 급성독성은 acute_tox_ate.csv 구분 순서. 분류안됨은 가장 약함",
    "세부구분 차이(1 ↔ 1B)는 일치로 봄(single.py 팀 결정과 같음)",
    "MSDS 미기재는 분류안됨과 같은 뜻으로 봄",
]


def _order(class_code, form, rules, override):
    """구분 이름 → 위험 순서(작을수록 위험). 정의가 없으면 빈 dict."""
    if override and class_code in override:
        cats = override[class_code]
    elif class_code in _ACUTE_ROUTE:
        cats = [r["category"] for r in _rows(_ACUTE_ROUTE[class_code], form)]
    else:
        item = rules["classes"].get(class_code) or {}
        cats = [str(r["category"]) for r in item.get("rules") or []]
    return {c: i for i, c in reversed(list(enumerate(cats)))}  # 같은 구분이 여럿이면 가장 위험한 위치


def _rank(cat, order):
    if cat == NO_CLASS:
        return _INF
    return order.get(cat, order.get(_main(cat)))


def _key(c):
    return c["category"] + (f":{c['effect']}" if c.get("effect") else "")


def _row(class_code, form, verdict, rule_id, *, type_=None, msds=None, low=None, high=None, reason="", extra_asm=()):
    return {"class_code": class_code, "form": form, "verdict": verdict, "type": TYPE_NAME.get(type_), "severity": SEVERITY.get(type_),
            "msds_value": msds, "our_value": {"low": low, "high": high}, "reason": reason, "rule_id": rule_id,
            "assumptions": BASE_ASSUMPTIONS + list(extra_asm)}


def _mismatch(cc, form, type_, msds, low, high, reason):
    return _row(cc, form, MISMATCH, RULE_IDS["type"][type_], type_=type_, msds=msds, low=low, high=high, reason=reason)


def _lack(cc, form, msds, low, high, reason):
    return _row(cc, form, LACK, RULE_IDS["lack"], msds=msds, low=low, high=high, reason=reason)


def _compare_one(cc, form, r, msds, order):
    low, high = r["low"], r["high"]
    ends = [low] if low == high else [low, high]
    m = msds or []
    if low == high:
        if not m:
            return (_row(cc, form, MATCH, RULE_IDS["match"], low=low, high=high, reason="둘 다 분류 없음") if low == NO_CLASS else
                    _mismatch(cc, form, MISSING, None, low, high, f"우리는 구분 {low}, MSDS에 항목 없음"))
        if low == NO_CLASS:
            return _mismatch(cc, form, EXTRA, m, low, high, f"우리는 분류안됨, MSDS는 {', '.join(m)}")
        if any(_same(x, low) for x in m):
            return _row(cc, form, MATCH, RULE_IDS["match"], msds=m, low=low, high=high, reason="구분 같음")
    else:
        if not m:
            return (_row(cc, form, BORDER, RULE_IDS["border"], low=low, high=high, reason="MSDS 미기재(분류안됨)가 범위 안")
                    if NO_CLASS in ends else
                    _mismatch(cc, form, MISSING, None, low, high, f"우리는 구분 {low}~{high}, MSDS에 항목 없음"))
        if any(_same(x, e) for x in m for e in ends if e != NO_CLASS):
            return _row(cc, form, BORDER, RULE_IDS["border"], msds=m, low=low, high=high, reason="MSDS 기재가 우리 범위의 끝값과 같음")
    # 구분이 다르다 → 위험 순서로 방향을 정한다
    mr = [(_rank(x, order), x) for x in m]
    er = [_rank(e, order) for e in ends]
    bad = [x for rk, x in mr if rk is None] + [e for e, rk in zip(ends, er) if rk is None]
    if bad:
        return _lack(cc, form, m, low, high, f"위험 순서가 정의되지 않은 구분: {', '.join(dict.fromkeys(bad))} ({cc})")
    strong, weak = min(er), max(er)
    mrk = min(rk for rk, _ in mr)  # MSDS 기재가 여럿이면 가장 위험하게 적은 것
    if low != high and strong <= mrk <= weak:
        return _row(cc, form, BORDER, RULE_IDS["border"], msds=m, low=low, high=high, reason="MSDS 기재가 우리 범위 안")
    if mrk > weak:
        return _mismatch(cc, form, UNDER, m, low, high, "MSDS가 우리 결과보다 약하게 기재")
    return _mismatch(cc, form, OVER, m, low, high, "MSDS가 우리 결과보다 강하게 기재")


def aggregate_verdicts(results, msds_classes, *, rules=None, order=None) -> dict:
    """results: classify_mixture_all 결과, msds_classes: 추출 JSON hazard.classes[]. order: {class_code: [구분…위험한 순]} 덮어쓰기.

    반환: {"verdicts": [항목별 판정…], "excluded": [비교에서 뺀 항목…]}. 둘 다 (class_code, form) 순으로 정렬한다.
    """
    rules = rules or load_mixture_rules()
    stated = {}
    for c in msds_classes or []:
        if c.get("class_code") and c.get("category"):
            stated.setdefault((c["class_code"], c.get("route_form") or None), []).append(_key(c))
    verdicts, excluded, seen = [], [], set()
    for r in results:
        cc, form = r["class_code"], r.get("form") or None
        seen.add((cc, form))
        msds = sorted(stated.get((cc, form), [])) or None
        res = r.get("result")
        if res is None or res["status"] in NOT_COMPARED:
            status = "건너뜀" if res is None else res["status"]
            ours = (r.get("calc") or {}).get("compare", {}).get("ours") if res else None
            excluded.append({"class_code": cc, "form": form, "status": status, "msds_value": msds, "our_value": ours,
                             "reason": (res or {}).get("reason") or r.get("skipped", "")})
        elif res["status"] == "근거부족":
            verdicts.append(_lack(cc, form, msds, res["low"], res["high"], res.get("reason") or "우리 결과가 근거부족"))
        else:
            verdicts.append(_compare_one(cc, form, res, msds, _order(cc, form, rules, order)))
    for (cc, form), m in stated.items():  # MSDS에만 있는 항목: 비교할 우리 결과가 없다
        if (cc, form) not in seen:
            verdicts.append(_lack(cc, form, sorted(m), None, None, "우리 결과에 같은 항목이 없음"))
    keyf = lambda x: (x["class_code"], x["form"] or "")
    return {"verdicts": sorted(verdicts, key=keyf), "excluded": sorted(excluded, key=keyf)}
