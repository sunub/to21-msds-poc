"""추출 JSON 코드 → HTODB 코드 번역(기업 '13_TO21DB매핑' 시트 그대로)과 추출 JSON 안의 코드 위치 찾기.

DB 없이 동작하는 순수 함수만 둔다. 번역 결과에는 근거인 시트 행 번호(sheet_row)와 원래 셀 값을 함께 돌려준다.
시트가 한 셀에 여러 코드를 적은 곳(' · '로 묶은 추출 코드, '/'로 줄여 쓴 DIV_CODE)만 나눠 읽고, 그 밖의 값은 바꾸지 않는다.
"""
from __future__ import annotations

import re

NOT_CLASSIFIED = "(hazard.classified = false)"  # 시트 B묶음의 '분류 결과 없음' 행


def _cells(r: dict) -> list[str]:
    return [r.get(f"c{i}") or "" for i in range(1, 8)]


def parse_div_codes(cell: str) -> list[str]:
    """한 셀의 DIV_CODE를 모두 꺼낸다. 'GHSnnnn / mmmm' 처럼 앞 글자를 줄인 표기는 GHS를 붙여 펼친다."""
    return ["GHS" + d for d in re.findall(r"(?:GHS)?(\d{4})\b", cell or "")]


def normalize_cas(cas: str) -> str:
    """R02 중 입력 쪽 표기만 맞춘다: 공백 제거, 전각·유니코드 하이픈 → '-'. 체크디지트 판정은 하지 않는다."""
    return re.sub(r"\s+", "", re.sub(r"[­‐-―⁃−﹣－]", "-", cas))


def normalize_un(un: str) -> str:
    """13_TO21DB매핑 A묶음의 UN 비교 규칙(입력 쪽만 맞춘다)."""
    return re.sub(r"^UN", "", re.sub(r"\s+", "", un).upper())


class Map13:
    """sheet13 행(dict: sheet_row, section, c1~c7)으로 만든 번역표."""

    def __init__(self, rows: list[dict]):
        sec = lambda s: [r for r in rows if r["section"] == s]
        self.hazard_rows = [r for r in sec("B") if re.fullmatch(r"GHS\d{6}", r["c5"] or "")]
        self.pictogram_rows = [r for r in sec("C") if re.fullmatch(r"GHS0\d", r["c1"] or "")]
        self.signal_rows = [r for r in self.pictogram_rows if r["c5"] and r["c6"]]  # 신호어는 그림문자 행의 오른쪽 칸
        # 괄호로 시작하는 c1은 추출 코드가 아닌 자리표시라 번역 대상에서 뺀다(시트 행은 DB에 그대로 있음)
        is_code = lambda r: not (r["c1"] or "").startswith("(")
        self.property_rows = [r for r in sec("D") if re.fullmatch(r"G\d{10}", r["c2"] or "") and is_code(r)]
        self.endpoint_rows = [r for r in sec("E") if parse_div_codes(r["c2"] or "")]
        self.regulation_rows = [r for r in sec("F") if re.fullmatch(r"KR\d{9}(_\d+)?", r["c4"] or "") and is_code(r)]

    @staticmethod
    def _out(r: dict, **codes) -> dict:
        return {"sheet_row": r["sheet_row"], "sheet_cells": _cells(r), **codes}

    def hazard(self, class_code: str, category: str | None, route_form: str | None = None,
               effect: str | None = None) -> list[dict]:
        """class_code·category가 같은 행. 그 행들에 route_form/effect 구분이 있으면 그 값까지 같아야 한다."""
        if class_code == NOT_CLASSIFIED:
            cand = [r for r in self.hazard_rows if r["c1"] == NOT_CLASSIFIED]
        else:
            cand = [r for r in self.hazard_rows if r["c1"] == class_code and r["c2"] == category]
        if any(r["c3"] for r in cand):
            cand = [r for r in cand if r["c3"] == route_form]
        if any(r["c4"] for r in cand):
            cand = [r for r in cand if r["c4"] == effect]
        return [self._out(r, class_result_code=r["c5"]) for r in cand]

    def pictogram(self, code: str) -> list[dict]:
        return [self._out(r, symbol=r["c2"]) for r in self.pictogram_rows if r["c1"] == code]

    def signal_word(self, word: str) -> list[dict]:
        return [self._out(r, sign_word=r["c6"]) for r in self.signal_rows if r["c5"] == word]

    def property(self, prop_code: str) -> list[dict]:
        return [self._out(r, property_id=r["c2"]) for r in self.property_rows
                if prop_code in [p.strip() for p in (r["c1"] or "").split("·")]]

    def endpoint(self, endpoint: str) -> list[dict]:
        return [self._out(r, div_codes=parse_div_codes(r["c2"])) for r in self.endpoint_rows if r["c1"] == endpoint]

    def regulation(self, item_code: str) -> list[dict]:
        return [self._out(r, regulate_item_id=r["c4"]) for r in self.regulation_rows if r["c1"] == item_code]


def _list(obj: dict, key: str, path: str) -> list[dict]:
    v = obj.get(key)
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
        raise ValueError(f"{path + '.' if path else ''}{key}는 객체 배열이어야 함")
    return v


def _text(obj: dict, key: str, path: str) -> str | None:
    v = obj.get(key)
    if v is not None and not isinstance(v, str):
        raise ValueError(f"{path}.{key}는 문자열이어야 함")
    return v or None


def code_sites(doc: dict) -> list[dict]:
    """추출 JSON(TO21 스키마)에서 HTODB와 대응되는 코드 위치를 모두 찾는다. 값은 손대지 않는다.
    형식이 스키마와 다르면 ValueError(어느 경로인지 포함)."""
    if not isinstance(doc.get("msds"), list):
        raise ValueError("msds 배열이 있어야 함")
    out = []
    for i, m in enumerate(_list(doc, "msds", "")):
        p = f"msds[{i}]"
        for j, c in enumerate(_list(m, "components", p)):
            q = f"{p}.components[{j}]"
            for key, kind in (("cas_no", "cas"), ("ke_no", "ke")):
                if v := _text(c, key, q):
                    out.append({"path": f"{q}.{key}", "kind": kind, "value": v, "seq": c.get("seq")})
        for j, t in enumerate(_list(m, "transport", p)):
            if v := _text(t, "un_no", f"{p}.transport[{j}]"):
                out.append({"path": f"{p}.transport[{j}].un_no", "kind": "un", "value": v})
        hz = m.get("hazard") or {}
        if not isinstance(hz, dict):
            raise ValueError(f"{p}.hazard는 객체여야 함")
        if hz.get("classified") is False:
            out.append({"path": f"{p}.hazard.classified", "kind": "hazard_class",
                        "value": {"class_code": NOT_CLASSIFIED, "category": None}})
        for j, h in enumerate(_list(hz, "classes", f"{p}.hazard")):
            q = f"{p}.hazard.classes[{j}]"
            if _text(h, "class_code", q):
                out.append({"path": q, "kind": "hazard_class",
                            "value": {k: _text(h, k, q) for k in ("class_code", "category", "route_form", "effect")}})
        for j, g in enumerate(_list(hz, "pictograms", f"{p}.hazard")):
            if v := _text(g, "code", f"{p}.hazard.pictograms[{j}]"):
                out.append({"path": f"{p}.hazard.pictograms[{j}].code", "kind": "pictogram", "value": v})
        if v := _text(hz, "signal_word", f"{p}.hazard"):
            out.append({"path": f"{p}.hazard.signal_word", "kind": "signal_word", "value": v})
        for j, h in enumerate(_list(hz, "h_statements", f"{p}.hazard")):
            if v := _text(h, "code", f"{p}.hazard.h_statements[{j}]"):
                out.append({"path": f"{p}.hazard.h_statements[{j}].code", "kind": "h_code", "value": v})
        for key, field, kind in (("physchem", "prop_code", "property"), ("toxicity", "endpoint", "endpoint"),
                                 ("ecotox", "endpoint", "endpoint"), ("regulations", "item_code", "regulation")):
            for j, x in enumerate(_list(m, key, p)):
                if v := _text(x, field, f"{p}.{key}[{j}]"):
                    out.append({"path": f"{p}.{key}[{j}].{field}", "kind": kind, "value": v, "comp_ref": x.get("comp_ref")})
    return out
