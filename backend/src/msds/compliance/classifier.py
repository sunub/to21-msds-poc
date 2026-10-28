"""단일물질·혼합물 판별.

표기(composition.type)를 먼저 따르고, 표기가 없을 때만 성분 개수로 추정한다.
"성분 1개 + 함유량 하한 80% 이상이면 단일물질" 같은 임계값은 근거를 확인하지 못해 두지 않았다
(설계서 v0.2 가 저장소에 없다, docs/adr/0001). 근거가 부족하면 판단불가로 사람에게 넘긴다.
"""


def product_type(inputs: dict) -> dict:
    """load_inputs 결과로 {"type": 단일물질|혼합물|판단불가, "basis": 근거 문구} 를 돌려준다."""
    t = (inputs.get("composition") or {}).get("type")
    if t in ("단일물질", "혼합물"):  # TO21 스키마의 값은 이 둘뿐이다
        return {"type": t, "basis": f"3항 단일/혼합 표기 '{t}'"}
    n = len(inputs.get("components") or [])
    if n >= 2:
        return {"type": "혼합물", "basis": f"표기 없음, 성분 {n}개로 추정"}
    return {
        "type": "판단불가",
        "basis": f"단일/혼합 표기가 없고 성분이 {n}개라 판단할 근거가 부족함",
    }
