"""TO21 JSON을 '칸' 단위로 펼치고 다시 조립하는 도구.

검수표(A), 투표(C, 2주차), 성적표(F)가 모두 같은 '칸' 정의를 써야 결과가 맞물린다.
그래서 이 모듈이 칸의 기준이다.

칸(cell)의 정의
- 숫자 묶음(Q: raw·status가 있는 객체)과 측정 조건(COND)은 통째로 한 칸이다.
  채점기도 Q의 7칸을 묶어서 비교한다.
- 서술 문장(STMT: seq·text가 있는 객체)도 한 칸이다.
- 글자 목록(동의어, 용도 등 문자열 배열)은 통째로 한 칸이다.
- 그 밖의 객체·목록은 안으로 들어가 끝 값까지 펼친다.

경로 표기: components[0].content, hazard.h_statements[2].code, meta.last_revision_date
"""
from __future__ import annotations

import json
import re

_COND_KEYS = {"temp", "temp_unit", "pressure", "pressure_unit", "method", "reference", "conc_value", "conc_unit"}


def is_q(v) -> bool:
    return isinstance(v, dict) and "raw" in v and "status" in v and ("value" in v or "lower" in v)


def is_cond(v) -> bool:
    return isinstance(v, dict) and len(v) > 0 and set(v.keys()) <= _COND_KEYS


def is_stmt(v) -> bool:
    return isinstance(v, dict) and "seq" in v and "text" in v and "value" in v


def is_atomic(v) -> bool:
    if v is None or isinstance(v, (str, int, float, bool)):
        return True
    if is_q(v) or is_cond(v) or is_stmt(v):
        return True
    if isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) or x is None for x in v):
        return True
    return False


def flatten(obj, prefix: str = "") -> list[tuple[str, object]]:
    """칸 단위로 펼친 (경로, 값) 목록. 빈 목록·빈 객체는 경로 하나로 남긴다."""
    out: list[tuple[str, object]] = []
    if is_atomic(obj):
        out.append((prefix, obj))
    elif isinstance(obj, dict):
        if not obj:
            out.append((prefix, obj))
        for k, v in obj.items():
            out.extend(flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        if not obj:
            out.append((prefix, obj))
        for i, v in enumerate(obj):
            out.extend(flatten(v, f"{prefix}[{i}]"))
    return out


_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def parse_path(path: str) -> list:
    return [int(i) if i else k for k, i in _TOKEN.findall(path)]


def get(obj, path: str, default=None):
    cur = obj
    for t in parse_path(path):
        try:
            cur = cur[t]
        except (KeyError, IndexError, TypeError):
            return default
    return cur


def set_(obj, path: str, value) -> None:
    """경로에 값을 넣는다. 중간 객체·목록이 없으면 만든다."""
    toks = parse_path(path)
    cur = obj
    for i, t in enumerate(toks):
        last = i == len(toks) - 1
        nxt = None if last else toks[i + 1]
        if isinstance(t, int):
            while len(cur) <= t:
                cur.append(None)
            if last:
                cur[t] = value
            else:
                if cur[t] is None:
                    cur[t] = [] if isinstance(nxt, int) else {}
                cur = cur[t]
        else:
            if last:
                cur[t] = value
            else:
                if cur.get(t) is None:
                    cur[t] = [] if isinstance(nxt, int) else {}
                cur = cur[t]


def delete(obj, path: str) -> None:
    """경로의 값을 지운다. 목록 항목은 None으로 표시해 두고, 다 끝난 뒤 compact()로 정리한다."""
    toks = parse_path(path)
    parent = obj
    for t in toks[:-1]:
        parent = parent[t]
    last = toks[-1]
    if isinstance(last, int):
        parent[last] = None
    else:
        parent.pop(last, None)


def compact(obj):
    """delete()로 None이 된 목록 항목을 걷어 낸다 (목록 안의 None만, 칸 값 None은 유지)."""
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [compact(v) for v in obj if v is not None]
    return obj


def to_cell(value) -> str:
    """검수표 칸에 넣을 글자. 객체·목록은 한 줄 JSON."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def from_cell(text):
    """검수표에 사람이 적은 값을 되돌린다. JSON으로 읽히면 JSON, 아니면 글자 그대로.

    - 빈 칸은 None(원문에 없음)
    - 숫자처럼 보이는 글자도 JSON으로 읽혀 숫자가 된다 (예: '93' → 93)
    - 글자로 남겨야 하는 숫자(예: 개정 번호 '01')는 따옴표로 감싸 적는다: "01"
    """
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    s = text.strip()
    if s == "":
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return s
