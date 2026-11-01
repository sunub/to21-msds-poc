"""추출 JSON msds[i] 한 건에서 classify_mixture_all 입력(components, mixture_props)을 만든다.

지식DB는 직접 열지 않고 인자로 받은 조회 함수를 쓴다: class_lookup(cas) → 분류코드 행,
tox_lookup(cas) → 급성독성 수치 행(선택, class_lookup_db.make_db_tox_lookup). 없는 값은 만들어내지 않고 gaps에 이유를 남긴다.
"""
from types import SimpleNamespace

from .adapter import to_acute_components
from .params import param_list
from .ranges import content_range

_VALID = {"값있음", None}  # 추출 q.status 중 값을 쓸 수 있는 것
_KIN_UNITS = {"mm2/s", "mm²/s", "cst", "㎟/s"}  # 동점도 단위 (1 cSt = 1 mm²/s)
_DYN_UNITS = {"cp", "mpa·s", "mpa.s", "mpas", "mpa*s", "pa·s", "pa.s", "poise"}
_STATE = {"액체": "액체", "고체": "고체", "기체": "가스", "가스": "가스"}  # 규칙표 prop("STATE") 값 형식
_FLAG_NAMES = ("non_additive_1", "non_additive_2", "ph_extreme")


def _unit_key(unit):
    return "".join(str(unit or "").split()).lower()


def _value(q):
    """q에서 단일 수치. value가 있을 때만 쓴다(범위·부등호는 단일값이 아니다)."""
    if not isinstance(q, dict) or q.get("status") not in _VALID:
        return None
    return q.get("value")


def _rows(msds_item, prop_code, comp_ref=None):
    return [p for p in msds_item.get("physchem") or []
            if p.get("prop_code") == prop_code and (comp_ref is None or str(p.get("comp_ref")) == str(comp_ref))]


def _temp_c(row):
    cond = row.get("cond") or {}
    t = cond.get("temp")
    return t if t is None or cond.get("temp_unit") in (None, "C") else "단위다름"


def _product_ph(msds_item, gaps):
    rows = _rows(msds_item, "PH", "MIX")
    if not rows:
        gaps.append({"field": "mixture_props.PH", "reason": "9항 pH 없음"})
        return None
    prod = [r for r in rows if (r.get("cond") or {}).get("conc_value") is None]
    if not prod:
        gaps.append({"field": "mixture_props.PH",
                     "reason": f"pH {len(rows)}건 모두 농도 조건(N 희석액 등)이 붙어 제품 pH가 아님(D-19)"})
        return None
    vals = {_value(r.get("q")) for r in prod}
    if len(vals) != 1 or None in vals:
        gaps.append({"field": "mixture_props.PH", "reason": "제품 pH가 단일 수치로 정해지지 않음(범위·부등호·복수값)"})
        return None
    return vals.pop()


def _viscosity40(msds_item, gaps):
    rows = _rows(msds_item, "VISCOSITY_KIN") + _rows(msds_item, "VISCOSITY")
    if not rows:
        gaps.append({"field": "mixture_props.VISCOSITY_40", "reason": "9항 점도 없음"})
        return None
    found = None
    for r in rows:
        q = r.get("q") or {}
        unit = _unit_key(q.get("unit"))
        if unit in _DYN_UNITS:
            gaps.append({"field": "mixture_props.VISCOSITY_40",
                         "reason": f"점도 단위가 동점도가 아님({q.get('unit')}): '{q.get('raw')}' — 밀도 없이 환산하지 않음(D-23)"})
        elif unit not in _KIN_UNITS:
            gaps.append({"field": "mixture_props.VISCOSITY_40", "reason": f"점도 단위를 알 수 없음({q.get('unit')}): '{q.get('raw')}'"})
        elif _temp_c(r) != 40:
            gaps.append({"field": "mixture_props.VISCOSITY_40", "reason": f"동점도 측정온도가 40℃가 아님: '{q.get('raw')}'"})
        elif _value(q) is None:
            gaps.append({"field": "mixture_props.VISCOSITY_40", "reason": f"동점도가 단일 수치가 아님: '{q.get('raw')}'"})
        else:
            found = _value(q)
    return found


def _state(msds_item, gaps):
    rows = _rows(msds_item, "APPEARANCE_STATE", "MIX")
    text = next((r.get("text_value") for r in rows if r.get("text_value")), None)
    if text is None:
        gaps.append({"field": "mixture_props.STATE", "reason": "9항 성상(APPEARANCE_STATE) 없음"})
        return None
    hit = next((v for k, v in _STATE.items() if k in text), None)
    if hit is None:
        gaps.append({"field": "mixture_props.STATE", "reason": f"규칙표 STATE 값(액체·고체·가스)에 맞지 않는 성상: '{text}'"})
    return hit


def _limit(msds_item, code, gaps):
    rows = _rows(msds_item, code, "MIX")
    vals = [_value(r.get("q")) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        gaps.append({"field": f"mixture_props.{code}", "reason": "9항 값 없음(해당없음·자료없음 포함)"})
        return None
    return vals[0]


def _per_component(msds_item, comp_ref, only_one, code):
    """성분 전용 물성(분자량·상대밀도). 성분 번호가 맞거나, 성분이 하나뿐일 때 MIX 값을 쓴다."""
    rows = _rows(msds_item, code, comp_ref) or (_rows(msds_item, code, "MIX") if only_one else [])
    return next((v for v in (_value(r.get("q")) for r in rows) if v is not None), None)


def _acute_inputs(msds_item, comps):
    """adapter.to_acute_components 재사용: 쓰는 속성만 가진 객체로 GhsInputs 를 대신한다."""
    shim = SimpleNamespace(
        components=[SimpleNamespace(seq=c.get("seq"), name=c.get("name"), cas_no=c.get("cas_no"),
                                    content=SimpleNamespace(value=None, lower=None, upper=None)) for c in comps],
        toxicity=msds_item.get("toxicity") or [])
    return to_acute_components(shim)


def build_components(msds_item, class_lookup, tox_lookup=None) -> dict:
    raw = msds_item.get("components") or []
    gaps, assumptions = [], [
        "함량: ranges.content_range 표 그대로(범위는 하한~상한, 단일값은 low=high, 상한만 있는 표기는 만들지 않음)",
        "함량 단위: % 계열만 사용, 단위 없음은 %로 간주(content_flags에 표시)",
        "독성값(11항)은 comp_ref가 성분 seq와 같은 행만 성분에 붙이고 MIX 행은 쓰지 않음(혼합물 ATE 직접 기재값은 계산에 안 씀)",
        "MSDS 11항 독성 행은 msds 키에 담음(ATE 수집 3단계)",
        "non_toxic: rules/params.csv non_toxic_cas 목록(물)에 있는 CAS만 True(설계서 21장 5단계, 24장 예제). "
        "나머지 성분은 추출 JSON에 근거가 없어 False",
        "mixture_props: 값이 없으면 키를 넣지 않음",
        "PH: comp_ref=MIX이고 농도 조건(cond.conc_value)이 없는 단일 수치만 제품 pH로 봄(D-19)",
        "VISCOSITY_40: 단위 mm²/s·cSt 이고 측정온도 40℃, 단일 수치인 행만 사용. 1 cSt = 1 mm²/s (D-23)",
        "STATE: 9항 성상 텍스트를 액체·고체·가스 중 하나로 맞춤(기체→가스)",
        "분자량·상대밀도: 성분 번호가 맞는 행, 성분이 하나뿐이면 MIX 행도 사용. 상대밀도(물=1)는 g/mL 로 간주",
    ]
    if tox_lookup is None:
        assumptions.append("tox_lookup 없음: TO21 독성DB 값(ATE 수집 1단계)을 쓰지 않고 db는 비워 둠")
    else:
        assumptions.append("TO21 독성DB 급성독성 수치는 db 키에 담음(ATE 수집 1단계, D-21 파싱). "
                           "흡입 값은 DB 숫자를 노출시간 환산 없이 그대로 씀(설계서 미결 4)")
    non_toxic_cas = set(param_list("non_toxic_cas"))
    ranges = content_range(raw)
    acute = {a["seq"]: a for a in _acute_inputs(msds_item, raw)}
    components = []
    for c, rng in zip(raw, ranges):
        who = c.get("name") or c.get("cas_no") or f"seq {c.get('seq')}"
        cas = c.get("cas_no")
        if rng["low"] is None:
            gaps.append({"field": f"components[{who}].content", "reason": f"함량 값 없음({'; '.join(rng['flags']) or '표기 없음'})"})
        if not cas:
            class_rows = []
            gaps.append({"field": f"components[{who}].class_rows", "reason": "CAS 없음 — 분류코드 조회 불가"})
        else:
            found = class_lookup(cas)
            class_rows = list(found or [])
            if not class_rows:  # class_lookup_db 의 결과는 .reason 에 빈 이유(미등록·접속 불가)를 싣는다
                why = getattr(found, "reason", None)
                gaps.append({"field": f"components[{who}].class_rows",
                             "reason": f"CAS {cas} 분류코드 조회 결과 없음" + (f" — {why}" if why else "")})
        db = []
        if tox_lookup is not None and cas:
            found_tox = tox_lookup(cas)
            db = list(found_tox or [])
            if not db:
                why = getattr(found_tox, "reason", None)
                gaps.append({"field": f"components[{who}].db",
                             "reason": f"CAS {cas} 독성DB 급성독성 수치 없음" + (f" — {why}" if why else "")})
        only_one = len(raw) == 1
        mw = _per_component(msds_item, c.get("seq"), only_one, "MOL_WEIGHT")
        dens = _per_component(msds_item, c.get("seq"), only_one, "RELATIVE_DENSITY")
        for key, val, code in (("mw", mw, "MOL_WEIGHT"), ("density", dens, "RELATIVE_DENSITY")):
            if val is None:
                mix = _rows(msds_item, code, "MIX")
                why = (f"9항 {code}가 혼합물(MIX) 값이라 성분 {len(raw)}개 중 어느 성분 값인지 알 수 없어 쓰지 않음"
                       if mix else f"9항 {code} 없음")
                gaps.append({"field": f"components[{who}].{key}", "reason": why})
        tox = acute[c.get("seq")]["tox"]
        for t in msds_item.get("toxicity") or []:
            q = t.get("q") or {}
            ep = str(t.get("endpoint") or "")
            if str(t.get("comp_ref")) != str(c.get("seq")) or not (ep in ("TX_ORAL", "TX_DERMAL") or ep.startswith("TX_INHAL")):
                continue
            if q.get("value") is None and (q.get("lower") is not None and not q.get("lower_op")
                                           or q.get("upper") is not None and not q.get("upper_op")):
                gaps.append({"field": f"components[{who}].msds", "reason": f"{ep} '{q.get('raw')}' 부등호(op) 없음 — 제외"})
        for r in tox:
            if r["route"] == "흡입" and r.get("form") is None:
                gaps.append({"field": f"components[{who}].msds", "reason": "흡입 독성 행에 physical_form 없음 — 형태별 ATE에 쓰이지 않음"})
            if r.get("hours") is None and r["route"] == "흡입":
                gaps.append({"field": f"components[{who}].msds", "reason": "흡입 독성 행에 노출시간 없음 — 4시간 환산 안 됨"})
        components.append({
            "cas": cas, "name": c.get("name"), "low": rng["low"], "high": rng["high"],
            "class_rows": class_rows, "flags": [], "m": None, "non_toxic": cas in non_toxic_cas,
            "db": db, "msds": tox, "mw": mw, "density": dens, "content_flags": rng["flags"],
        })
    gaps.append({"field": "components[*].flags",
                 "reason": f"근거 없음 — {', '.join(_FLAG_NAMES)} 표시를 만들 근거가 추출 JSON에 없음(스키마에 해당 필드 없음)"})
    props = {"PH": _product_ph(msds_item, gaps), "VISCOSITY_40": _viscosity40(msds_item, gaps),
             "STATE": _state(msds_item, gaps), "LEL": _limit(msds_item, "LEL", gaps), "UEL": _limit(msds_item, "UEL", gaps)}
    return {"components": components, "mixture_props": {k: v for k, v in props.items() if v is not None},
            "gaps": gaps, "assumptions": assumptions}
