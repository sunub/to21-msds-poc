"""두 결과(예: GPT 실버와 Claude 실버)의 목록 항목을 짝짓는 기준.

목록의 순서는 모델마다 다를 수 있다. 그래서 '몇 번째'가 아니라 '무엇인지'로 짝짓는다.
짝짓기 기준은 TO21 채점기와 같게 맞췄다 (성분은 CAS 우선, 없으면 이름).

핵심 함수
- keyed_flatten(msds_item): 칸 단위로 펼치되, 목록 번호 대신 항목 키를 쓴 경로를 만든다.
    regulations[3].applicable  →  regulations[k=7664-93-9|OSH|OSH_MEASURE].applicable
  두 결과를 이 경로로 맞추면 같은 칸끼리 비교된다.
- unflatten_keyed(pairs): 위 경로와 값 목록으로 msds 항목을 다시 조립한다(골드 만들기에 사용).
- generic(path): 번호·키를 지운 경로 (regulations[].applicable). 칸 이름표·우선순위에 사용.

한계: 키가 같은 항목이 여러 개면(예: 조건이 다른 pH 값 두 개) 나온 순서로 #2, #3을 붙인다.
이 경우만 순서에 따라 짝이 바뀔 수 있으므로, 검수표에서 '불일치'로 보이면 항목 전체를 함께 확인한다.
"""
from __future__ import annotations

import re
from collections import Counter

from .jsonpath import is_atomic


def _nz(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def comp_map(msds_item: dict) -> dict:
    """성분 순번(seq) → 성분 키(CAS 우선, 없으면 공백 없앤 이름). 채점기의 comp_key_map과 같다."""
    out = {"MIX": "MIX"}
    for c in msds_item.get("components") or []:
        out[str(c.get("seq"))] = c.get("cas_no") or _nz(c.get("name"))
    return out


def _cref(item: dict, cm: dict) -> str:
    ref = item.get("comp_ref")
    return cm.get(str(ref), str(ref))


# 목록별 짝짓기 키. 일반 경로(번호를 지운 경로) → 키 함수
LIST_KEYS = {
    "companies": lambda it, cm: (it.get("role"), _nz(it.get("name"))),
    "companies[].contacts": lambda it, cm: (it.get("type"),),
    "hazard.classes": lambda it, cm: (it.get("class_code"), it.get("category"), it.get("route_form")),
    "hazard.pictograms": lambda it, cm: (it.get("code"),),
    "hazard.h_statements": lambda it, cm: (it.get("code"),),
    "hazard.p_statements": lambda it, cm: (it.get("code"),),
    "components": lambda it, cm: (it.get("cas_no") or _nz(it.get("name")),),
    "exposure_limits": lambda it, cm: (_cref(it, cm), it.get("standard"), it.get("limit_type")),
    "physchem": lambda it, cm: (_cref(it, cm), it.get("prop_code")),
    "toxicity": lambda it, cm: (_cref(it, cm), it.get("endpoint"), it.get("descriptor"), it.get("species")),
    "cmr": lambda it, cm: (_cref(it, cm), it.get("hazard"), it.get("agency")),
    "ecotox": lambda it, cm: (_cref(it, cm), it.get("endpoint"), it.get("descriptor"), it.get("species")),
    "transport": lambda it, cm: (it.get("mode"),),
    # 해외·기타 규제는 같은 코드(INTL_US 등) 아래 여러 행이 있어 원문 항목명까지 키에 넣는다
    "regulations": lambda it, cm: (_cref(it, cm), it.get("law"), it.get("item_code"), it.get("country"))
    + ((_nz(it.get("item_raw")),) if it.get("law") in ("INTL", "KR_ETC") or not it.get("item_code") else ()),
    "dangerous_goods": lambda it, cm: (_cref(it, cm), it.get("class"), it.get("item")),
    "waste": lambda it, cm: (_cref(it, cm),),
    "intl_class": lambda it, cm: (_cref(it, cm), it.get("system"), it.get("h_code")),
    "narratives": lambda it, cm: (it.get("item_code"),),
    "narratives[].statements": lambda it, cm: (it.get("seq"),),
    "extras": lambda it, cm: (it.get("section_no"), _nz(it.get("title_raw"))),
    "evidence": lambda it, cm: (it.get("field"), it.get("page")),
    "validation": lambda it, cm: (it.get("rule"), it.get("field")),
}


def _key_str(parts: tuple) -> str:
    s = "|".join("" if p is None else str(p) for p in parts)
    return s.replace("[", "(").replace("]", ")")


def generic(path: str) -> str:
    """번호와 키를 지운 경로: regulations[k=...].threshold → regulations[].threshold"""
    return re.sub(r"\[(?:k=[^\]]*|\d+)\]", "[]", path)


def keyed_flatten(msds_item: dict) -> list[tuple[str, object]]:
    cm = comp_map(msds_item)
    out: list[tuple[str, object]] = []

    def walk(node, path: str):
        if is_atomic(node):
            out.append((path, node))
            return
        if isinstance(node, dict):
            if not node:
                out.append((path, node))
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
            return
        if isinstance(node, list):
            if not node:
                out.append((path, node))
                return
            g = generic(path)
            keyfn = LIST_KEYS.get(g)
            seen: Counter = Counter()
            for i, it in enumerate(node):
                if keyfn and isinstance(it, dict):
                    ks = _key_str(keyfn(it, cm))
                    seen[ks] += 1
                    if seen[ks] > 1:          # 같은 키가 또 나오면 몇 번째인지 붙인다
                        ks = f"{ks}#{seen[ks]}"
                    walk(it, f"{path}[k={ks}]")
                else:
                    walk(it, f"{path}[{i}]")

    walk(msds_item, "")
    return out


_KTOKEN = re.compile(r"\[k=([^\]]*)\]|\[(\d+)\]|([^.\[\]]+)")


def _tokens(path: str) -> list[tuple[str, str]]:
    toks = []
    for k, idx, name in _KTOKEN.findall(path):
        if name:
            toks.append(("name", name))
        elif idx:
            toks.append(("idx", idx))
        else:
            toks.append(("key", k))
    return toks


class _ListBuilder(dict):
    """목록 자리. 키 → 항목, 넣은 순서를 유지한다."""


def unflatten_keyed(pairs: list[tuple[str, object]]) -> dict:
    """keyed_flatten의 반대. 목록 항목은 경로가 처음 나온 순서대로 놓인다."""
    root: dict = {}
    for path, value in pairs:
        toks = _tokens(path)
        cur = root
        for i, (kind, tok) in enumerate(toks):
            last = i == len(toks) - 1
            nxt_is_list = (not last) and toks[i + 1][0] in ("key", "idx")
            if kind == "name":
                if last:
                    cur[tok] = value
                else:
                    if tok not in cur or cur[tok] is None or (isinstance(cur[tok], list) and not cur[tok]):
                        cur[tok] = _ListBuilder() if nxt_is_list else {}
                    cur = cur[tok]
            else:  # key / idx: cur는 _ListBuilder
                if last:
                    cur[tok] = value
                else:
                    if tok not in cur:
                        cur[tok] = _ListBuilder() if nxt_is_list else {}
                    cur = cur[tok]

    def finish(node):
        if isinstance(node, _ListBuilder):
            return [finish(v) for v in node.values()]
        if isinstance(node, dict):
            return {k: finish(v) for k, v in node.items()}
        return node

    return finish(root)


def item_path_map(msds_item: dict) -> dict[str, str]:
    """번호 경로 → 키 경로 대응표 (목록 항목 단위).

    모델의 근거(evidence.field)는 'regulations[3]'처럼 번호로 적힌다.
    검수표의 행은 키 경로를 쓰므로, 이 표로 근거를 해당 행에 붙인다.
    예: {"regulations[3]": "regulations[k=7664-93-9|OSH|OSH_MEASURE|]", "companies[0].contacts[1]": "companies[k=..].contacts[k=..]"}
    """
    cm = comp_map(msds_item)
    out: dict[str, str] = {}

    def walk(node, ipath: str, kpath: str):
        if is_atomic(node):
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{ipath}.{k}" if ipath else k, f"{kpath}.{k}" if kpath else k)
        elif isinstance(node, list):
            keyfn = LIST_KEYS.get(generic(ipath))
            seen: Counter = Counter()
            for i, it in enumerate(node):
                ip = f"{ipath}[{i}]"
                if keyfn and isinstance(it, dict):
                    ks = _key_str(keyfn(it, cm))
                    seen[ks] += 1
                    if seen[ks] > 1:
                        ks = f"{ks}#{seen[ks]}"
                    kp = f"{kpath}[k={ks}]"
                else:
                    kp = f"{kpath}[{i}]"
                out[ip] = kp
                walk(it, ip, kp)

    walk(msds_item, "", "")
    return out


def to_keyed(field: str, path_map: dict[str, str]) -> str:
    """근거의 번호 경로(components[0].content)를 키 경로로 바꾼다. 가장 긴 앞부분이 맞는 항목을 쓴다."""
    best = ""
    for ip in path_map:
        if (field == ip or field.startswith(ip + ".") or field.startswith(ip + "[")) and len(ip) > len(best):
            best = ip
    return path_map[best] + field[len(best):] if best else field
