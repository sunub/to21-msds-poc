"""mixture_rules.yaml과 class_map.csv를 읽고 형식을 검증한다. 읽기·검증만 하고 판정은 하지 않는다."""
from functools import lru_cache
from pathlib import Path

import yaml

from .params import RULES_DIR, read_rules
from .rule_eval import parse_when

METHODS = {"ate", "additive", "cutoff", "summation", "property", "transport", "compare"}
_RULE_LISTS = ("rules", "extra_rules")
_CLASS_MAP_COLS = ["rule_id", "to21_result_code", "to21_div_code", "db_div_name", "db_result_name", "class_code",
                   "category", "form", "effect", "note"]


class RulesFormatError(ValueError):
    """규칙 파일 형식 오류. 고친 곳을 한 번에 알 수 있도록 오류를 모두 모아 담는다."""

    def __init__(self, path, errors):
        self.errors = errors
        super().__init__(f"{Path(path).name} 형식 오류 {len(errors)}건:\n" + "\n".join(f"- {e}" for e in errors))


def _blank(v) -> bool:
    return v is None or not str(v).strip()


def load_mixture_rules(path=None) -> dict:
    """반환: yaml 내용(meta, classes, …)에 "warnings"(경고)와 "notices"(알림)를 더한 dict."""
    path = Path(path) if path else RULES_DIR / "mixture_rules.yaml"
    with open(path, encoding="utf-8-sig") as f:
        doc = yaml.safe_load(f)
    errors, warnings, notices = [], [], []
    meta, classes = (doc or {}).get("meta"), (doc or {}).get("classes")
    if not isinstance(meta, dict) or not isinstance(classes, dict):
        raise RulesFormatError(path, ["meta와 classes가 있어야 함"])
    for key in ("version", "source"):
        if _blank(meta.get(key)):
            errors.append(f"meta.{key}가 비어 있음")
    warnings += [f"meta.{k}가 비어 있음 (TO21 담당자 확인 전)" for k in ("checked_by", "checked_date") if _blank(meta.get(k))]

    seen: dict[str, str] = {}  # 규칙 id → 처음 나온 항목
    for name, item in classes.items():
        if not isinstance(item, dict):
            errors.append(f"{name}: 항목이 dict가 아님")
            continue
        method = item.get("method")
        if method not in METHODS:
            errors.append(f"{name}.method: {method!r} 는 {sorted(METHODS)} 중 하나여야 함")
        if "rule_id" in item and _blank(item["rule_id"]):
            errors.append(f"{name}.rule_id가 비어 있음")
        for list_key in _RULE_LISTS:
            for i, rule in enumerate(item.get(list_key) or []):
                where = f"{name}.{list_key}[{i}]"
                for key in ("id", "category", "when"):
                    if _blank(rule.get(key)):
                        errors.append(f"{where}.{key}가 비어 있음")
                rid = rule.get("id")
                if not _blank(rid):
                    if rid in seen:
                        errors.append(f"{where}.id {rid!r} 중복 (처음: {seen[rid]})")
                    seen.setdefault(rid, name)
                if not _blank(rule.get("when")):
                    try:
                        parse_when(rule["when"])
                    except ValueError as e:
                        errors.append(f"{where}.when 파싱 실패 (id {rid}): {e}")
        if item.get("flag_if"):
            try:
                parse_when(item["flag_if"])
            except ValueError as e:
                errors.append(f"{name}.flag_if 파싱 실패: {e}")
        if method not in ("ate", "compare") and not item.get("rules"):
            notices.append(f"{name}: method {method!r} 인데 rules가 없음")
    if errors:
        raise RulesFormatError(path, errors)
    return {**doc, "warnings": warnings, "notices": notices}


def _header(path) -> dict:
    """'# version: … | source: … | checked_by: …' 줄에서 값을 뽑는다."""
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("# version:"):
                parts = (p.split(":", 1) for p in line[1:].strip().split(" | "))
                return {k.strip(): v.strip() for k, v in parts}
    return {}


def load_class_map(path=None, rules=None) -> dict:
    """반환: version, source, rows, by_code(분류결과코드 → 행), notices(정보).

    rules: load_mixture_rules 결과. 없으면 기본 파일로 읽는다.
    """
    path = Path(path) if path else RULES_DIR / "class_map.csv"
    head, rows, errors = _header(path), read_rules(path), []
    if _blank(head.get("version")):
        errors.append("'# version:' 머리 정보가 없거나 version이 비어 있음")
    if rows and list(rows[0]) != _CLASS_MAP_COLS:
        errors.append(f"헤더가 {','.join(_CLASS_MAP_COLS)} 가 아님: {','.join(rows[0])}")
    ids, codes, by_code = {}, {}, {}
    for n, r in enumerate(rows, 1):
        where = f"행 {n} ({r.get('rule_id')})"
        rid, code = r.get("rule_id"), r.get("to21_result_code") or ""
        if _blank(rid):
            errors.append(f"{where}: rule_id가 비어 있음")
        elif rid in ids:
            errors.append(f"{where}: rule_id {rid!r} 중복 (행 {ids[rid]})")
        ids.setdefault(rid, n)
        if len(code) != 9:
            errors.append(f"{where}: to21_result_code {code!r} 는 9자리가 아님")
        elif code in codes:
            errors.append(f"{where}: to21_result_code {code!r} 중복 (행 {codes[code]})")
        codes.setdefault(code, n)
        for key in ("class_code", "category"):
            if _blank(r.get(key)):
                errors.append(f"{where}: {key}가 비어 있음")
        by_code.setdefault(code, r)
    if errors:
        raise RulesFormatError(path, errors)

    known = set((rules or load_mixture_rules())["classes"])
    used = {r["class_code"] for r in rows}
    notices = [f"{r['rule_id']} {r['to21_result_code']}: class_code {r['class_code']!r} 가 mixture_rules.yaml classes에 없음"
               f"{' (note: ' + r['note'] + ')' if r['note'] else ''}" for r in rows if r["class_code"] not in known]
    notices += [f"mixture_rules.yaml {c}: class_map에 대응 행이 없음" for c in known if c not in used]
    return {"version": head["version"], "source": head.get("source", ""), "rows": rows, "by_code": by_code,
            "notices": notices}


@lru_cache
def _default_map() -> dict:
    return load_class_map()


def lookup_class(to21_result_code: str):
    """9자리 분류결과코드 → (class_code, category, form, effect). 없으면 None. form·effect가 비면 None."""
    r = _default_map()["by_code"].get(to21_result_code)
    return r and (r["class_code"], r["category"], r["form"] or None, r["effect"] or None)
