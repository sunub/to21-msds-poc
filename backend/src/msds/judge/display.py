"""화면 표시 문장 (계약 5-api finding_display). 숫자·부등호 표기 규칙을 서버 한 곳에 둔다. 판정 값은 만들지 않는다."""
import re

from msds.compliance.trace import cat_text

_EVIDENCE_SECTION = {"hazard": 2, "components": 3, "composition": 3, "physchem": 9, "toxicity": 11, "ecotox": 12,
                     "transport": 14, "regulations": 15, "dangerous_goods": 15}
_NOT_COMPARED = "비교하지 않음"


def _with_form(text: str, form) -> str:
    return f"{text} ({form})" if form else text


def _applicable(value, threshold) -> str:
    if value is None:
        return "기재 없음"
    raw = (threshold or {}).get("raw")
    return f"{value} ({raw.replace('>=', '≥').replace('<=', '≤')})" if raw else str(value)


def _class_expected(exp: dict) -> str:
    low, high = exp.get("low"), exp.get("high")
    if low is None and exp.get("category") is None:
        if "low" not in exp:
            return _NOT_COMPARED
        return "판단 못 함" if exp.get("status") == "근거부족" else "없음"
    if low is None:
        return cat_text(exp.get("category"))
    return cat_text(low) if low == high else f"{cat_text(low)}~{cat_text(high)}"


def _texts(f: dict) -> tuple[str, str]:
    msds, exp, kind = f["msds"], f["expected"], f["kind"]
    if kind == "class":
        return (_with_form(cat_text(msds.get("category")), msds.get("route_form")),
                _with_form(_class_expected(exp), exp.get("route_form")))
    if kind == "label":
        code = msds.get("code")
        return (f"{code} 기재" if code else "기재 없음", exp.get("code") or "해당 없음")
    if kind == "product_type":
        return (msds.get("product_type") or "기재 없음", exp.get("product_type") or "판단 못 함")
    expected = _applicable(exp.get("applicable"), exp.get("threshold"))
    if not exp.get("present"):
        expected = _NOT_COMPARED if f["verdict"] in ("참고", "범위 외") else "기준 없음"
    if kind == "dangerous_goods" and (exp.get("dg") or {}).get("item") and exp.get("applicable"):
        expected = f"{exp['applicable']} ({exp['dg']['item']})"
    return _applicable(msds.get("applicable"), msds.get("threshold")), expected


def _component(f: dict) -> str | None:
    if f["section"] != "15":
        return None
    comp = f.get("comp")
    if not comp:
        return "제품"
    raw = str((f["expected"].get("content") or {}).get("raw") or "").replace("%", "").strip()
    name = comp.get("name") or comp.get("cas") or comp.get("comp_ref")
    return f"{name} ({raw})" if raw else str(name)


def _pages(evidence) -> list[dict]:
    pages = set()
    for e in evidence or []:
        section = _EVIDENCE_SECTION.get(re.split(r"[.\[]", e.get("field") or "")[0])
        if section and e.get("page"):
            pages.add((section, e["page"]))
    return [{"section": s, "page": p} for s, p in sorted(pages)]


def finding_display(f: dict, trace: dict | None) -> dict:
    msds, expected = _texts(f)
    basis = list((trace or {}).get("basis_lines") or [])
    if f["reason"] and f["reason"] not in basis:
        basis.insert(0, f["reason"])
    return {"msds": msds, "expected": expected, "component": _component(f), "basis_lines": basis,
            "calc_lines": list((trace or {}).get("calc_lines") or []), "source_pages": _pages(f["msds"].get("evidence"))}


def view_display(consistency: dict) -> dict:
    return {f["id"]: finding_display(f, r["traces"].get(f["trace_id"])) for r in consistency["results"] for f in r["findings"]}
