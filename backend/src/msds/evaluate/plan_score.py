"""기획서 기준 채점 (TO21_MSDS_PoC_기획서 v1.0).

TO21 채점기 v0.6은 기획서의 결정(D-1 9개 항, D-2 판정 범위, 표 1-3 입력 범위)이 반영되지 않아
"우리 기획 안에서 정확한가"를 재지 못한다. 이 모듈은 기획서가 정한 범위 안에서 골드와 칸 단위로 비교한다.
TO21 점수는 성적표에 참고로만 붙인다.

- 범위: 1·2·3·8·9·11·12·14·15항과 1항 머리글 관리정보 (D-1). 서술형은 항목 코드(S8_…)의 항 번호로 가른다.
- 16항 개정 정보(meta.first_issue_date·revision_no·revision_label·last_revision_date)는 범위 밖이라
  '16항 참고'로 따로 센다 (D-1, 기획서 10장 '구조적 미달').
- 15항 해외·기타 규제(국내 OSH·KREACH·CCA·DG·WASTE 밖의 법령 행)는 추출은 하지만 2단계가 판정하지 않아(D-2)
  '15항 해외·기타'로 따로 센다. TO21 채점기의 '15항 해외·기타 규제' 항목과 같은 구분이다.
- 칸: 검수자가 골드를 확정한 단위(기술명세 2.7, align.keyed_flatten). 목록은 순서가 아니라 키로 짝짓고,
  숫자 묶음(Q)은 한 칸이며 7요소(부등호·값·하한·상한·단위·상태)만 비교한다(기획서 4.3). 근거·검사·extras·순번은 칸이 아니다.
- 비교는 골드와 같은지만 본다. 표기 정규화나 부분 점수는 기획서에 정한 것이 없어 하지 않는다.
- 엔진 입력 칸: 2단계가 읽는 칸 (compliance.loader.load_inputs). 2항 분류·신호어·그림문자·H 코드, 3항 조성·성분
  (이름·CAS·함량·영업비밀), 9·11·12항 행, 15항 국내 규제(D-2: 해외 규제는 판정하지 않음)와 위험물.
- 미검수 칸(골드의 .unreviewed.json)은 정확도에 넣지 않고 따로 센다 (기획서 7.1).

함수
- cells(item)                    msds 항목 하나 → {키 경로: 값} (칸만)
- scope_of(path)                 '범위' | '16항 참고' | '15항 해외·기타' | '범위 밖'
- is_engine_cell(path)           2단계 입력 칸인지
- compare_doc(gold, pred, unreviewed)   문서 한 건의 칸 비교 결과
- cell_agreement(a, b)           두 실행 결과의 칸 일치 (재현성, 기획서 2.3)
"""
from __future__ import annotations

import re
from collections import Counter

from ..common.align import generic, keyed_flatten

SCOPE_SECTIONS = (1, 2, 3, 8, 9, 11, 12, 14, 15)
REVISION_FIELDS = ("first_issue_date", "revision_no", "revision_label", "last_revision_date")   # 16항 객체 (section_specs)
_NOT_CELLS = ("evidence", "validation", "extras")
# 최상위 키 → 항 번호. 서술형(narratives)은 항목 코드로 정한다
TOP_SECTION = {
    "meta": 1, "product": 1, "companies": 1,
    "hazard": 2,
    "composition": 3, "components": 3,
    "exposure_limits": 8,
    "physchem": 9,
    "toxicity": 11, "cmr": 11,
    "ecotox": 12,
    "transport": 14,
    "regulations": 15, "dangerous_goods": 15, "waste": 15, "intl_class": 15,
}
DOMESTIC_LAWS = {"OSH", "KREACH", "CCA", "DG", "WASTE"}     # D-2: 2단계가 판정하는 국내 규제
_ENGINE_PATHS = (
    "composition.type",
    "components[].name", "components[].cas_no", "components[].content", "components[].content_note",
    "components[].trade_secret",
    "hazard.signal_word", "hazard.h_statements[].code", "hazard.pictograms[].code",
)
_ENGINE_PREFIXES = ("hazard.classes[]", "physchem[]", "toxicity[]", "ecotox[]", "dangerous_goods[]")
_KEY = re.compile(r"\[k=([^\]]*)\]")
_NARRATIVE = re.compile(r"^narratives\[k=S(\d+)_")


def top_key(path: str) -> str:
    return re.split(r"[.\[]", path, maxsplit=1)[0]


def empty(v) -> bool:
    return v in (None, "", [], {})


def canon(v):
    """값 없음의 꼴(None·빈 글·빈 목록·빈 dict)을 None 하나로 맞춘다. 묶음 칸(Q·문장) 안의 빈 하위 칸도 같다.
    골드는 refs=null, 결과는 refs=[]처럼 '없음'을 다르게 적어도 같은 값이다. 글자 표기는 바꾸지 않는다."""
    if isinstance(v, dict):
        d = {k: canon(x) for k, x in v.items()}
        d = {k: x for k, x in d.items() if x is not None}
        return d or None
    if isinstance(v, list):
        xs = [canon(x) for x in v]
        return xs if any(x is not None for x in xs) else None
    return None if v == "" else v


Q_FIELDS = ("value", "lower_op", "lower", "upper_op", "upper", "unit", "status")
# 스키마에서 Q($defs.Q)를 쓰는 칸 이름
Q_CELLS = {"q", "content", "converted", "cycle", "designated_qty", "qty", "qty_alt", "threshold"}


def q_only(path: str, v):
    """숫자 묶음(Q) 칸은 7요소(부등호·값·하한·상한·단위·상태)만 비교한다 (기획서 4.3, 명세서 6_평가기준 'Q 비교').
    raw(원문 사본)·approx·dp·note는 비교하지 않는다. 보면 '해당 없음'/'해당없음' 같은 원문 사본 차이나
    소수 자리 표시가 틀림이 된다 (s10에서 Q 틀림 대부분)."""
    if isinstance(v, dict) and path.rsplit(".", 1)[-1] in Q_CELLS:
        return {k: v.get(k) for k in Q_FIELDS}
    return v


def cells(item: dict) -> dict[str, object]:
    """keyed_flatten 칸 가운데 근거·검사·extras·순번을 뺀 것. Q는 7요소만, 값은 canon으로 맞춘다."""
    return {p: canon(q_only(p, v)) for p, v in keyed_flatten(item)
            if top_key(p) not in _NOT_CELLS and not p.endswith(".seq")}


def section_of(path: str) -> int | None:
    m = _NARRATIVE.match(path)
    if m:
        return int(m.group(1))
    return TOP_SECTION.get(top_key(path))


def _law(path: str) -> str | None:
    """규제 행 키 경로의 법령 (regulations[k=성분|법령|항목|국가…])."""
    key = _KEY.search(path)
    parts = key.group(1).split("|") if key else []
    return parts[1] if len(parts) > 1 else None


def scope_of(path: str) -> str:
    """'범위' | '16항 참고' | '15항 해외·기타' | '범위 밖'.
    15항 해외·기타 규제(국내 5개 법령 밖)는 추출 범위 안이지만 2단계가 판정하지 않아(D-2) 주 지표와 따로 센다."""
    if path.startswith("meta.") and path.split(".", 1)[1] in REVISION_FIELDS:
        return "16항 참고"
    if generic(path).startswith("regulations[]") and _law(path) not in DOMESTIC_LAWS:
        return "15항 해외·기타"
    return "범위" if section_of(path) in SCOPE_SECTIONS else "범위 밖"


def is_engine_cell(path: str) -> bool:
    g = generic(path)
    if g.startswith("regulations[]"):
        return _law(path) in DOMESTIC_LAWS
    return g in _ENGINE_PATHS or g.startswith(_ENGINE_PREFIXES)


def _pairs(gold: dict, pred: dict) -> list[tuple[dict, dict]]:
    """MSDS 건을 순서대로 짝짓는다. 건수가 다르면 남는 쪽은 빈 항목과 짝짓는다."""
    g, p = gold.get("msds") or [], pred.get("msds") or []
    n = max(len(g), len(p))
    return [(g[i] if i < len(g) else {}, p[i] if i < len(p) else {}) for i in range(n)]


def compare_doc(gold: dict, pred: dict, unreviewed: set[str] | None = None) -> dict:
    """문서 한 건. 반환: {'cells': [칸 결과], 'msds_count': (골드 건수, 추출 건수)}.
    칸 결과: {msds, path, section, scope, engine, gold, pred, result}
    result: 맞음 | 틀림(둘 다 값이 있고 다름) | 빠뜨림(골드만 값) | 지어냄(추출만 값) | 미검수"""
    unreviewed = unreviewed or set()
    out = []
    for i, (gm, pm) in enumerate(_pairs(gold, pred)):
        gc, pc = cells(gm), cells(pm)
        for path in sorted(set(gc) | set(pc)):
            gv, pv = gc.get(path), pc.get(path)
            if empty(gv) and empty(pv):
                continue
            if f"msds[{i}].{path}" in unreviewed:
                result = "미검수"
            elif empty(gv):
                result = "지어냄"
            elif empty(pv):
                result = "빠뜨림"
            else:
                result = "맞음" if gv == pv else "틀림"
            out.append({"msds": i, "path": path, "section": section_of(path), "scope": scope_of(path),
                        "engine": is_engine_cell(path), "gold": gv, "pred": pv, "result": result})
    return {"cells": out, "msds_count": (len(gold.get("msds") or []), len(pred.get("msds") or []))}


def tally(rows: list[dict]) -> dict:
    """칸 결과 목록 → 세기. accuracy = 맞음 / 골드에 값이 있는 칸(맞음+틀림+빠뜨림).
    to_fix = 사람이 고쳐야 할 칸(틀림+빠뜨림+지어냄)."""
    c = Counter(r["result"] for r in rows)
    gold_n = c["맞음"] + c["틀림"] + c["빠뜨림"]
    return {"gold_n": gold_n, "correct": c["맞음"], "wrong": c["틀림"], "missing": c["빠뜨림"],
            "extra": c["지어냄"], "unreviewed": c["미검수"], "to_fix": c["틀림"] + c["빠뜨림"] + c["지어냄"],
            "accuracy": c["맞음"] / gold_n if gold_n else None}


def cell_agreement(a: dict, b: dict) -> dict:
    """같은 문서를 두 번 추출한 결과의 범위 안 칸 일치. 한쪽에만 값이 있는 칸은 다름으로 센다."""
    same = total = 0
    for am, bm in _pairs(a, b):
        ac, bc = cells(am), cells(bm)
        for path in set(ac) | set(bc):
            if scope_of(path) != "범위" or (empty(ac.get(path)) and empty(bc.get(path))):
                continue
            total += 1
            same += ac.get(path) == bc.get(path)
    return {"same": same, "total": total, "rate": same / total if total else None}
