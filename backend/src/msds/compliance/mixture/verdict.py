"""classify_mixture_all 결과와 공급사(MSDS) 기재 분류를 항목별로 비교해 판정 4종·유형·심각도를 붙인다.

판정 이름·유형·심각도·근거 규칙 id 는 아래 상수 한 곳에 모았다. 유형 이름과 심각도는 설계서 7장·18장
(규칙표 v0.3 severity.yaml)을 따르고, 근거 규칙 id(VRD-*)는 설계서에 없어 우리 쪽 번호를 쓴다. 항목 필드는 2항에 한정된 이름을 쓰지 않아 15항 비교도 같은 모양으로 쓸 수 있다.
"""
from functools import lru_cache

from ..single import _main, _same
from .acute import _rows
from .rules_loader import load_class_map, load_mixture_rules

# ── 상수 (설계서 7장·18장, 규칙표 v0.3 severity.yaml) ─────────────────────
MATCH, MISMATCH, BORDER, LACK = "일치", "불일치", "경계", "근거부족"
# 틀림의 다섯 경우(안쪽 구분). rule_id 와 이유 문장은 경우마다 나눠 쓰고, 결과의 type 은 설계서 2항 이름으로 낸다.
UNDER, OVER, MISSING, EXTRA, FORM = "under", "over", "missing", "extra", "form"
# 설계서 18장: MSDS 미기재 또는 낮은 구분 → 과소분류, MSDS가 더 높은 구분·추가 기재 → 과대분류,
#             흡입 형태(가스·증기·미스트)만 다름 → 형태·세부 표기 (severity.yaml SV-03)
TYPE_NAME = {UNDER: "과소분류", MISSING: "과소분류", OVER: "과대분류", EXTRA: "과대분류", FORM: "형태·세부 표기"}
SEVERITY = {UNDER: "높음", MISSING: "높음", OVER: "낮음", EXTRA: "낮음", FORM: "중간"}
RULE_IDS = {"match": "VRD-1", "type": {UNDER: "VRD-2", OVER: "VRD-3", MISSING: "VRD-4", EXTRA: "VRD-5", FORM: "VRD-8"},
            "border": "VRD-6", "lack": "VRD-7"}
NOT_COMPARED = ("해당 없음", "대조")  # 비교 대상에서 빼는 우리 결과 status
NO_CLASS = "분류안됨"
_INF = float("inf")
_ACUTE_ROUTE = {"HH_ACUTE_ORAL": "경구", "HH_ACUTE_DERMAL": "경피", "HH_ACUTE_INHAL": "흡입"}
BASE_ASSUMPTIONS = [
    "rule_id(VRD-1~8)는 설계서에 정의가 없어 우리 쪽 번호를 씀(상수는 verdict.py 상단)",
    "구분 순서는 규칙표 rules 의 나열 순서(위험한 구분부터), 급성독성은 acute_tox_ate.csv 구분 순서. 분류안됨은 가장 약함",
    "세부구분 차이(1 ↔ 1B)는 일치로 봄(single.py 팀 결정과 같음)",
    "MSDS 미기재는 분류안됨과 같은 뜻으로 봄",
    "규칙표에 순서가 없는 항목(물리적 위험성, 표적장기 1회 구분3)은 class_map 결과코드 순서(위험한 구분부터)로 비교. "
    "고압가스 종류(압축·액화·냉동액화·용해)는 위험 순서가 아니라 세부 표기 차이로 봄(11/02 F)",
]
# 같은 순위로 보는 항목: 고압가스는 종류 차이일 뿐 어느 쪽이 더 위험하다고 할 수 없다
_SAME_RANK = {"PH_PRESS_GAS"}
FORM_ASSUMPTION = ("형태만 다른 두 줄(우리가 확정한 형태 ↔ MSDS가 적은 형태)을 한 줄로 묶음(설계서 18·24장). 구분이 같으면 "
                   "형태·세부 표기(중간), 구분도 다르면 구분 방향으로 과소·과대를 정하고 형태 차이는 이유에 적음(이 경우는 설계서에 없어 가정)")


def _order(class_code, form, rules, override):
    """구분 이름 → 위험 순서(작을수록 위험). 정의가 없으면 빈 dict."""
    if override and class_code in override:
        cats = override[class_code]
    elif class_code in _ACUTE_ROUTE:
        cats = [r["category"] for r in _rows(_ACUTE_ROUTE[class_code], form)]
    else:
        item = rules["classes"].get(class_code) or {}
        cats = [str(r["category"]) for r in item.get("rules") or []]
    order = {c: i for i, c in reversed(list(enumerate(cats)))}  # 같은 구분이 여럿이면 가장 위험한 위치
    n = len(cats)
    for c in _map_cats(class_code):  # 규칙표에 없는 구분은 class_map 순서로 뒤에 붙인다
        if c not in order:
            order[c] = len(cats) if class_code in _SAME_RANK else n
            n += 1
    return order


@lru_cache
def _map_cats(class_code) -> tuple:
    """class_map 의 그 항목 구분을 결과코드 순서(GHSxxxx01, 02 … = 위험한 구분부터)로."""
    rows = sorted(load_class_map()["by_code"].items())
    return tuple(dict.fromkeys(r["category"] for _, r in rows if r["class_code"] == class_code))


_EFFECT_WORDS = {"마취": "마취", "졸음": "마취", "현기증": "마취", "호흡기": "호흡기", "기도": "호흡기"}  # H336·H335 문구도 같은 효과다


def _effects(text) -> set[str]:
    return {v for k, v in _EFFECT_WORDS.items() if k in text}


def _same_effect(msds_cat, ours):
    """표적장기 1회 구분3처럼 '구분:효과'로 적은 두 값이 같은 구분·같은 효과인가. 효과 문구는 낱말(마취·호흡기)로 맞춘다."""
    if not (msds_cat and ours and ":" in msds_cat and ":" in ours):
        return False
    (mh, me), (oh, oe) = (s.split(":", 1) for s in (msds_cat, ours))
    return mh.strip() == oh.strip() and bool(_effects(oe)) and _effects(oe) <= _effects(me)


def _rank(cat, order):
    """구분의 위험 순위. '3:마취 영향'처럼 효과가 붙은 구분은 앞의 구분(3)으로 본다."""
    if cat == NO_CLASS:
        return _INF
    keys = [cat, _main(cat)]
    if cat and ":" in cat:
        head = cat.split(":", 1)[0].strip()
        keys += [head, _main(head)]
    return next((order[k] for k in keys if k in order), None)


def _key(c):
    return c["category"] + (f":{c['effect']}" if c.get("effect") else "")


def _row(class_code, form, verdict, rule_id, *, type_=None, msds=None, low=None, high=None, reason="", extra_asm=()):
    return {"class_code": class_code, "form": form, "verdict": verdict, "type": TYPE_NAME.get(type_), "severity": SEVERITY.get(type_),
            "msds_value": msds, "msds_form": form, "our_value": {"low": low, "high": high}, "reason": reason, "rule_id": rule_id,
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
        if any(_same_effect(x, low) for x in m):
            return _row(cc, form, MATCH, RULE_IDS["match"], msds=m, low=low, high=high, reason="구분·효과 같음(효과 문구만 다름)")
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
    if low == high and mrk == strong:  # 순위는 같고 표기만 다름(구분3의 효과, 고압가스 종류)
        return _mismatch(cc, form, FORM, m, low, high, f"구분 순위는 같고 세부 표기만 다름: MSDS {', '.join(m)}, 우리 {low}")
    if mrk > weak:
        return _mismatch(cc, form, UNDER, m, low, high, "MSDS가 우리 결과보다 약하게 기재")
    return _mismatch(cc, form, OVER, m, low, high, "MSDS가 우리 결과보다 강하게 기재")


def _joined(main, effects):
    return "·".join(([main] if main != NO_CLASS else []) + effects) or NO_CLASS


def _compare_with_effects(cc, form, res, extra, msds, order):
    """표적장기 1회: 구분 1·2와 함께 표시되는 구분3을 효과별로 비교한다 (설계서 25·36장, 규칙표 extra_rules)."""
    effect_cats = lambda side: [f"{e['category']}:{e['effect']}" for e in extra.get(side) or []]
    low, high = effect_cats("low"), effect_cats("high")
    shown = {"low": _joined(res["low"], low), "high": _joined(res["high"], high)}
    is_effect = lambda x: x.split(":", 1)[0].strip() == "3"
    m = msds or []
    stated, others = [x for x in m if is_effect(x)], [x for x in m if not is_effect(x)]
    has = lambda ours: any(_same_effect(x, ours) or x.strip() == "3" for x in stated)
    ours_effects = lambda ours: set().union(*(_effects(o) for o in ours)) if ours else set()
    wrote = lambda x, ours: x.strip() == "3" or (bool(_effects(x)) and _effects(x) <= ours_effects(ours))  # 한 칸에 여러 효과를 적어도 각각 본다
    main = _compare_one(cc, form, res, others, order)
    missing = [o for o in low if not has(o)]
    over = [x for x in stated if not wrote(x, high)]
    if main["verdict"] == MISMATCH:  # 구분 1·2가 틀린 것이 더 무겁다. 구분3 표시 차이로 가리지 않는다
        row = {**main, "msds_value": m or None}
        if stated:
            row["reason"] = f"{main['reason'].replace(', MSDS에 항목 없음', '')}, MSDS는 {', '.join(stated)}만 적음"
    elif low != high and not over and not missing:
        row = _row(cc, form, BORDER, RULE_IDS["border"], msds=m, reason="함량 범위에 따라 구분3 해당 여부가 갈림")
    elif missing:
        type_ = UNDER if m else MISSING
        row = _mismatch(cc, form, type_, m or None, None, None, f"우리는 {', '.join(missing)}, MSDS에 없음")
    elif over:
        row = _mismatch(cc, form, OVER, m, None, None, f"우리 결과에 없는 구분3: {', '.join(over)}")
    elif main["verdict"] != MATCH:
        row = {**main, "msds_value": m or None}
    else:
        row = _row(cc, form, MATCH, RULE_IDS["match"], msds=m, reason="구분·효과 같음")
    row["our_value"] = shown
    return row


def _merge_form_pairs(verdicts, rules, override):
    """같은 항목에서 흡입 형태만 다른 두 줄을 한 줄로 묶는다 (설계서 18·24장, severity.yaml SV-03).

    짝 조건
      우리 쪽 줄: 형태 B에서 구분을 확정했는데 MSDS에는 B가 없음(미기재 → 과소분류 줄)
      MSDS 쪽 줄: 같은 항목을 다른 형태 A로 적었는데, 우리 A 결과가 근거부족이거나 분류안됨(과대분류 줄)
    우리 결과가 범위(하한 ≠ 상한)이거나 위험 순서를 모르면 묶지 않고 두 줄을 그대로 둔다.
    """
    out = list(verdicts)
    for ours in [v for v in verdicts if v["rule_id"] == RULE_IDS["type"][MISSING]]:
        cc, form_b = ours["class_code"], ours["form"]
        low, high = ours["our_value"]["low"], ours["our_value"]["high"]
        if low != high:
            continue
        cands = [v for v in out if v["class_code"] == cc and v["form"] != form_b and v["msds_value"]
                 and (v["verdict"] == LACK or v["rule_id"] == RULE_IDS["type"][EXTRA])]
        if not cands:
            continue
        same = [v for v in cands if any(_same(x, low) for x in v["msds_value"])]
        theirs = (same or cands)[0]
        cats, form_a = theirs["msds_value"], theirs["form"]
        said = f"MSDS는 {form_a or '형태 미기재'} {', '.join(cats)}, 우리는 {form_b} {low}"
        if same:
            row = _mismatch(cc, form_b, FORM, cats, low, high, f"구분은 같고 형태만 다름: {said}")
        else:
            order = _order(cc, form_b, rules, override)
            ranks = [_rank(x, order) for x in cats] + [_rank(low, order)]
            if None in ranks:
                continue
            type_ = UNDER if min(ranks[:-1]) > ranks[-1] else OVER
            row = _mismatch(cc, form_b, type_, cats, low, high, f"구분과 형태가 모두 다름: {said}")
        row["msds_form"] = form_a
        row["assumptions"] = row["assumptions"] + [FORM_ASSUMPTION]
        out = [v for v in out if v is not ours and v is not theirs] + [row]
    return out


def _no_proof(row, r):
    """지식DB에는 '분류 안 됨' 행이 없어 빈칸은 자료 없음이다. 빈칸 성분이 있으면 MSDS가 과하다고 말할 근거가 없다 (멘토링 3번)."""
    if row["type"] != TYPE_NAME[OVER]:
        return row
    limits = (r.get("calc") or {}).get("include_min") or 0
    limit = min((v for v in limits.values() if v is not None), default=0) if isinstance(limits, dict) else (limits or 0)
    names = [i.get("name") or i.get("cas") or "이름 없는 성분" for i in r.get("inputs") or []
             if i.get("excluded") in ("해당 분류 없음", "분류 정보 없음", "함량 없음", "자료 없음")
             and ((i.get("content") or {}).get("high") is None or i["content"]["high"] >= limit)]
    if not names:
        return row
    return _lack(row["class_code"], row["form"], row["msds_value"], row["our_value"]["low"], row["our_value"]["high"],
                 f"MSDS가 더 강하게 적었으나 기준 분류나 함량을 알 수 없는 성분이 있어 과대 여부를 정할 수 없음: {', '.join(names)}")


def _sum_note(row, res):
    if res.get("to21_sum"):
        row["reason"] += " (같은 구분 성분 합산으로 분류됨, TO21 기준)"
    return row


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
        elif cc == "HH_STOT_SE" and ((r.get("extra") or {}).get("low") or (r.get("extra") or {}).get("high")):
            verdicts.append(_sum_note(_no_proof(_compare_with_effects(cc, form, res, r["extra"], msds, _order(cc, form, rules, order)), r), res))
        else:
            verdicts.append(_sum_note(_no_proof(_compare_one(cc, form, res, msds, _order(cc, form, rules, order)), r), res))
    for (cc, form), m in stated.items():  # MSDS에만 있는 항목: 비교할 우리 결과가 없다
        if (cc, form) not in seen:
            verdicts.append(_lack(cc, form, sorted(m), None, None, "우리 결과에 같은 항목이 없음"))
    keyf = lambda x: (x["class_code"], x["form"] or "")
    verdicts = _merge_form_pairs(sorted(verdicts, key=keyf), rules, order)  # 정렬 뒤 묶어야 같은 입력에 같은 짝이 나온다
    return {"verdicts": sorted(verdicts, key=keyf), "excluded": sorted(excluded, key=keyf)}
