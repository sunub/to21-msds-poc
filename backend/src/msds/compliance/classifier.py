"""단일물질·혼합물 판별 (설계서 v0.4 17장).

유효 성분 수 n은 불순물·안정제로 표기된 성분을 뺀 수다. 물은 센다.
n = 0 이면 불명확, n = 1 이면 단일물질 표기일 때 단일물질, n >= 2 이면 혼합물 표기일 때 혼합물, 나머지는 불명확.

설계서와 다르게 둔 것: 혼합물 표기 + 유효 성분 1개는 설계서 흐름으로는 불명확이지만 혼합물로 둔다. 유해 성분만 적는
실제 MSDS(실버 T21-014, T21-039)가 여기 해당해, 불명확으로 두면 그 문서의 2항 판정이 전부 사라진다. TO21 확인 대기
(docs/backend/b/mentoring-followups.md).
"""


def effective_components(components: list[dict] | None) -> list[dict]:
    return [c for c in components or []
            if c.get("content_note") != "불순물" and "안정제" not in str(c.get("name") or "")]


def product_type(inputs: dict) -> dict:
    """load_inputs 결과로 {"type": 단일물질|혼합물|판단불가, "basis": 근거 문구} 를 돌려준다."""
    t = (inputs.get("composition") or {}).get("type")
    n = len(effective_components(inputs.get("components")))
    if n == 0:
        return {"type": "판단불가", "basis": "3항에 유효 성분이 없음 (성분표 없음 또는 유해성분 미함유)"}
    if t == "혼합물":
        return {"type": t, "basis": f"3항 단일/혼합 표기 '{t}'"}
    if t == "단일물질" and n == 1:
        return {"type": t, "basis": f"3항 단일/혼합 표기 '{t}'"}
    if t == "단일물질":
        return {"type": "판단불가", "basis": f"3항에 단일물질로 적었으나 유효 성분이 {n}개임"}
    return {"type": "판단불가", "basis": f"단일/혼합 표기가 없고 유효 성분이 {n}개임"}
