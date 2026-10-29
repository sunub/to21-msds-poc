"""값 없는 행(자료없음·해당없음·미기재)의 칸 모양을 TO21 v0.6 표기로 맞춘다 (A-1).

입력·출력: MSDS 한 건(TO21 msds[]의 원소). 입력은 바꾸지 않고 새 dict를 돌려준다.
규칙은 TO21 예제(25 황산)의 값 없는 행에서 가져왔다. 행을 새로 만들거나 지우지 않는다
(원문에 있는 "해당없음" 행을 적는 것은 추출 쪽 몫이다).
- 8항 노출기준: 종류(limit_type)가 비었거나 '기타'면 국내·ACGIH는 TWA, 생물학적은 BEI
- 11항 독성: 지표(descriptor)가 비었으면 '결과기술', 혼합물(MIX) 급성독성은 'ATE'
- 12항 생태: 지표가 비었으면 '결과기술', 잔류성은 '분해율', 생물농축성은 같은 성분에 아직 없는 'BCF'→'분해율' 순
- 11항 CMR: 등급(class)은 null
"""
from __future__ import annotations

import copy

NO_VALUE = {"자료없음", "해당없음", "미기재"}
# shortcut: 아래 기본값은 TO21 예제 1건(25 황산)에서 미룬 것, 작은 골드(A-2)가 나오면 다시 맞춘다
LIMIT_TYPE = {"국내": "TWA", "ACGIH": "TWA", "생물학적": "BEI"}
ACUTE = {"TX_ORAL", "TX_DERMAL", "TX_INHAL"}
ECO_DESCRIPTORS = {"ECO_PERSIST": ["분해율"], "ECO_BIOACC": ["BCF", "분해율"]}


def apply(msds_item: dict) -> dict:
    m = copy.deepcopy(msds_item)
    for r in m.get("exposure_limits") or []:
        if ((r.get("q") or {}).get("status") in NO_VALUE and r.get("limit_type") in (None, "기타")
                and r.get("standard") in LIMIT_TYPE):
            r["limit_type"] = LIMIT_TYPE[r["standard"]]
    for r in m.get("toxicity") or []:
        if r.get("status") in NO_VALUE and r.get("descriptor") is None:
            r["descriptor"] = "ATE" if r.get("comp_ref") == "MIX" and r.get("endpoint") in ACUTE else "결과기술"
    eco = m.get("ecotox") or []
    used = {(r.get("comp_ref"), r.get("endpoint"), r.get("descriptor")) for r in eco}
    for r in eco:
        if r.get("status") in NO_VALUE and r.get("descriptor") is None:
            key = (r.get("comp_ref"), r.get("endpoint"))
            free = [d for d in ECO_DESCRIPTORS.get(key[1], []) if (*key, d) not in used]
            r["descriptor"] = free[0] if free else "결과기술"
            used.add((*key, r["descriptor"]))
    for r in m.get("cmr") or []:
        if r.get("status") in NO_VALUE:
            r["class"] = None
    return m
