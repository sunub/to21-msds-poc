"""값 없는 행(자료없음·해당없음·미기재)의 칸 모양을 TO21 v0.6 표기로 맞춘다 (A-1).

입력·출력: MSDS 한 건(TO21 msds[]의 원소). 입력은 바꾸지 않고 새 dict를 돌려준다.
규칙은 TO21 예제(25 황산)의 값 없는 행에서 가져왔다. 행을 새로 만들거나 지우지 않는다
(원문에 있는 "해당없음" 행을 적는 것은 추출 쪽 몫이다).
- 8항 노출기준: 종류(limit_type)가 비었거나 '기타'면 국내·ACGIH는 TWA, 생물학적은 BEI
- 11항 독성: 지표(descriptor)가 비었으면 '결과기술'. 원문 줄에 ATE가 있어 추출이 채운 'ATE'는 그대로 둔다
- 12항 생태: 지표가 비었으면 '결과기술', 잔류성은 '분해율', 생물농축성은 같은 성분에 아직 없는 'BCF'→'분해율' 순
- 11항 CMR: 등급(class)은 null
- 11·12항 값 없는 행의 수치(q)가 비었으면 상태만 담은 빈 수치 객체(채점기가 줄을 짝지을 때 q의 상태까지 본다)
"""
from __future__ import annotations

import copy

NO_VALUE = {"자료없음", "해당없음", "미기재"}
# shortcut: 아래 기본값은 TO21 예제 1건(25 황산)에서 미룬 것, 작은 골드(A-2)가 나오면 다시 맞춘다
LIMIT_TYPE = {"국내": "TWA", "ACGIH": "TWA", "생물학적": "BEI"}
ECO_DESCRIPTORS = {"ECO_PERSIST": ["분해율"], "ECO_BIOACC": ["BCF", "분해율"]}


def _blank_q(status: str) -> dict:
    # 예제의 미기재 행은 원문이 빈칸이라 raw가 ''
    return {"raw": "" if status == "미기재" else status, "approx": False, "value": None, "lower_op": None, "lower": None,
            "upper_op": None, "upper": None, "unit": None, "dp": None, "status": status, "note": None}


def apply(msds_item: dict) -> dict:
    m = copy.deepcopy(msds_item)
    for r in m.get("exposure_limits") or []:
        if ((r.get("q") or {}).get("status") in NO_VALUE and r.get("limit_type") in (None, "기타")
                and r.get("standard") in LIMIT_TYPE):
            r["limit_type"] = LIMIT_TYPE[r["standard"]]
    for r in m.get("toxicity") or []:
        if r.get("status") in NO_VALUE and r.get("descriptor") is None:
            r["descriptor"] = "결과기술"
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
    for r in (m.get("toxicity") or []) + eco:
        if r.get("status") in NO_VALUE and r.get("q") is None:
            r["q"] = _blank_q(r["status"])
    return m
