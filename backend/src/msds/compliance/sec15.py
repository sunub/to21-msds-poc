"""15항 국내 규제 판정: 지식DB의 규제 기준과 성분 함량으로 해당 여부를 정하고 공급사 15항과 비교한다 (설계서 4단계).

설계서 v0.2 가 저장소에 없어 아래 규칙은 2026-10-27 팀 결정으로 정했다. 설계서를 받으면 맞춘다.
- 비교 단위는 (성분, law, item_code) 이다. 해외 규제(law INTL)는 국내 규제가 아니라 판정하지 않는다.
- 기대 해당 여부는 성분 함량을 기준 농도와 비교해 정한다. 함량 하한과 상한으로 두 번 판단해 둘 다 기준
  이상이면 해당, 둘 다 미만이면 비해당, 갈리면 경계다. 기준 농도가 없는 규제는 함량과 관계없이 해당이다.
- 기대가 해당인데 공급사가 비해당·자료없음·미기재로 적었거나 행을 빠뜨렸으면 불일치.
- 기대가 비해당인데 공급사가 해당으로 적었으면 불일치. 적지 않았거나 자료없음·미기재면 일치.
- 지식에 그 규제 행이 없으면 비해당·자료없음·미기재는 일치, 해당은 근거부족(기록이 없다는 것만으로
  해당 여부를 확인할 수 없다).
- 지식이 없거나 성분 CAS·함량을 알 수 없거나 단위가 % 가 아니면 근거부족. 혼합물 전체 행(comp_ref MIX)은
  성분 CAS 로 조회할 수 없어 근거부족이다.

지식DB 없이 get_regulation 의 임시 형태만 가정해 만들었다. 가정과 한계는 docs/adr/0004 에 있다.
"""
from typing import Literal

Verdict = Literal["일치", "불일치", "경계", "근거부족"]


def _expected(q: dict | None, ref: dict) -> tuple[str | None, str]:
    """기준 행 하나에 대한 기대 해당 여부: 해당 / 비해당 / 경계, 알 수 없으면 None."""
    t = ref.get("threshold_value")
    if t is None:
        return "해당", "기준 농도 없음 (함유하면 해당)"
    q = q or {}
    if q.get("unit") != "%" or ref.get("threshold_unit") != "%":
        return None, "함량 또는 기준 농도의 단위가 % 가 아님"
    op = ref.get("threshold_op") or ">="
    v = q.get("value")
    lo, hi = (v, v) if v is not None else (q.get("lower"), q.get("upper"))
    if lo is None and hi is None:
        return None, "성분 함량이 없음"
    # 하한이 없으면 0, 상한이 없으면 100 까지 가능한 것으로 본다.
    lo_ok = lo is not None and (lo >= t if q.get("lower_op") == ">" else (lo > t if op == ">" else lo >= t))
    hi_ok = (hi > t if q.get("upper_op") == "<" else (hi > t if op == ">" else hi >= t)) if hi is not None else True
    if lo_ok and hi_ok:
        return "해당", f"함량 {lo}~{hi}% 가 기준 {op} {t}% 를 만족"
    if not hi_ok:
        return "비해당", f"함량 {lo}~{hi}% 가 기준 {op} {t}% 미만"
    return "경계", f"함량 {lo}~{hi}% 가 기준 {op} {t}% 에 걸침"


def _judge(sup: str | None, exp: str | None) -> Verdict:
    if exp == "경계":
        return "경계"
    if exp == "해당":
        return "일치" if sup == "해당" else "불일치"
    return "불일치" if sup == "해당" else "일치"   # 비해당


def compare_sec15(inputs: dict, provider) -> list[dict]:
    """load_inputs 결과와 지식 제공자로 (성분, 법령, 항목)마다 판정 한 줄을 돌려준다.

    [{"comp_ref", "cas_no", "law", "item_code", "verdict": 일치|불일치|경계|근거부족,
      "supplier": 공급사 해당 여부, "expected": 기대 해당 여부, "basis", "source": [기준 출처],
      "knowledge_version", "as_of"}]
    """
    as_of = inputs.get("as_of_date")
    comps = {str(c.get("seq")): c for c in inputs.get("components") or []}
    sup = {(str(r.get("comp_ref")), r.get("law"), r.get("item_code")): r
           for r in inputs.get("regulations") or [] if r.get("law") != "INTL"}

    know: dict[str, dict] = {}   # comp_ref → get_regulation 응답
    for ref_no, c in comps.items():
        if c.get("cas_no"):
            know[ref_no] = provider.get_regulation(c["cas_no"], as_of)
    refs: dict[tuple, list[dict]] = {}
    for ref_no, k in know.items():
        for r in k["rows"] if k["knowledge_version"] else []:
            if r.get("law") != "INTL":
                refs.setdefault((ref_no, r.get("law"), r.get("item_code")), []).append(r)

    rows = []
    for key in sorted(sup.keys() | refs.keys(), key=str):
        ref_no, law, item = key
        s = (sup.get(key) or {}).get("applicable")
        comp = comps.get(ref_no) or {}
        k = know.get(ref_no)
        version = k["knowledge_version"] if k else None
        exp = None
        if ref_no == "MIX":
            verdict, basis = "근거부족", "혼합물 전체 행은 성분 CAS 로 조회할 수 없음"
        elif not comp.get("cas_no"):
            verdict, basis = "근거부족", "성분 CAS 가 없어 기준을 조회하지 못함"
        elif not version:
            verdict, basis = "근거부족", "기준 지식이 없음"
        elif key not in refs:
            verdict = "근거부족" if s == "해당" else "일치"
            basis = "기준에 규제 기록이 없음"
        else:
            results = [_expected(comp.get("content"), r) for r in refs[key]]
            found = [e for e, _ in results if e]
            exp = "해당" if "해당" in found else "경계" if "경계" in found else "비해당" if found else None
            basis = "; ".join(b for _, b in results)
            verdict = _judge(s, exp) if exp else "근거부족"
        rows.append({
            "comp_ref": ref_no, "cas_no": comp.get("cas_no"), "law": law, "item_code": item,
            "verdict": verdict, "supplier": s, "expected": exp, "basis": basis,
            "source": [r.get("source") for r in refs.get(key, [])],
            "knowledge_version": version, "as_of": as_of,
        })
    return rows
