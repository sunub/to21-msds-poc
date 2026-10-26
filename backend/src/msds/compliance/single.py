"""단일물질 2항 판정: 지식DB의 기준 분류와 공급사가 2항에 적은 분류를 비교한다 (설계서 3단계).

설계서 v0.2 가 저장소에 없어 아래 규칙은 2026-10-27 팀 결정으로 정했다. 설계서를 받으면 맞춘다.
- 분류는 (class_code, route_form) 단위로 비교한다. 흡입 형태가 다르면 다른 분류다.
- 구분이 같으면 일치. 한쪽이 세부구분 없이 적었으면(1 ↔ 1B) 고시가 세부구분을 "필요에 따라" 쓰게
  하므로 일치로 보고 basis 에 남긴다. 세부구분끼리 다르면(1A ↔ 1B) 불일치.
- 기준에 있는 구분을 공급사가 빠뜨렸거나 다르게 적었으면 불일치.
- 기준에 없는 분류·구분을 공급사만 적었으면 근거부족. 지식DB에 없다는 것만으로 해당 없음을 단정할 수 없다.
- 지식이 없거나(knowledge_version 이 None) 성분 CAS 가 없으면 모두 근거부족.

지식DB 없이 get_reference 의 임시 형태만 가정해 만들었다. 가정, 한계, 실제 지식DB가 다를 때의
대응은 docs/adr/0003 에 있다.
"""
import re
from typing import Literal

Verdict = Literal["일치", "불일치", "근거부족"]


def _main(cat: str | None) -> str | None:
    """세부구분을 뗀 구분. "1B" → "1". 그 밖의 표기는 그대로 둔다."""
    return cat[:-1] if cat and re.fullmatch(r"\d[A-C]", cat) else cat


def _same(a: str | None, b: str | None) -> bool:
    return a == b or a == _main(b) or _main(a) == b


def _group(classes: list[dict]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for c in classes:
        out.setdefault((c.get("class_code"), c.get("route_form")), []).append(c)
    return out


def _judge(sup: list[str | None], ref: list[str | None]) -> tuple[Verdict, str]:
    if not ref:
        return "근거부족", "기준에 없는 분류를 공급사만 적음"
    if not sup:
        return "불일치", "기준 분류를 공급사가 적지 않음"
    left, unmatched, loose = list(sup), [], False
    for r in ref:
        s = next((s for s in left if _same(s, r)), None)
        if s is None:
            unmatched.append(r)
            continue
        left.remove(s)
        loose = loose or s != r
    if unmatched:
        return "불일치", f"기준 구분 {unmatched} 을 공급사가 다르게 적거나 빠뜨림"
    if left:
        return "근거부족", f"기준에 없는 구분 {left} 을 공급사가 더 적음"
    return "일치", "구분 같음 (세부구분 표기 차이 포함)" if loose else "구분 같음"


def compare_single(inputs: dict, provider) -> list[dict]:
    """load_inputs 결과(단일물질)와 지식 제공자로 분류마다 판정 한 줄을 돌려준다.

    [{"class_code", "route_form", "verdict": 일치|불일치|근거부족, "supplier": [구분], "reference": [구분],
      "basis": 판정 이유, "source": [기준 출처], "knowledge_version", "as_of"}]
    """
    as_of = inputs.get("as_of_date")
    comps = inputs.get("components") or []
    cas = comps[0].get("cas_no") if comps else None
    know = provider.get_reference(cas, as_of) if cas else None
    version = know["knowledge_version"] if know else None
    sup = _group((inputs.get("hazard") or {}).get("classes") or [])
    ref = _group(know["classes"]) if version else {}

    rows = []
    for key in sorted(sup.keys() | ref.keys(), key=str):
        s = [c.get("category") for c in sup.get(key, [])]
        r = [c.get("category") for c in ref.get(key, [])]
        if not cas:
            verdict, basis = "근거부족", "성분 CAS 가 없어 기준을 조회하지 못함"
        elif not version:
            verdict, basis = "근거부족", "기준 지식이 없음"
        else:
            verdict, basis = _judge(s, r)
        rows.append({
            "class_code": key[0], "route_form": key[1], "verdict": verdict,
            "supplier": s, "reference": r, "basis": basis,
            "source": [c.get("source") for c in ref.get(key, [])],
            "knowledge_version": version, "as_of": as_of,
        })
    return rows
