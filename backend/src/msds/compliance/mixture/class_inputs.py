"""성분별 분류결과코드(9자리)를 evaluate_rules 입력(by_class)으로 바꾼다. 입력 조립만 하고 판정은 하지 않는다."""
import ast

from .params import param_list
from .rule_eval import parse_when
from .rules_loader import load_class_map, load_mixture_rules, lookup_class

# 지식DB 출처 코드 → 분류 출처 이름. 저장소에는 이 대응이 없어 연습 패키지(ghsclass/reference/to21_tables.py SOURCE_NAME)를 따랐다.
_SOURCE_NAME = {"KR02": "환경부", "KR03": "고용노동부"}
_NOT_USED = {"NONE": "분류 결과 없음", "PH_DESENS_EXPL": "국내 고시 밖 구분"}


def _key(category, effect):
    """구분키. effect가 있으면 규칙표의 sum("3:호흡기자극") 표기와 같은 "category:effect" 하나만 쓴다."""
    return f"{category}:{effect}" if effect else category


def _rank(source, order):
    name = _SOURCE_NAME.get(source, source)
    return next((i for i, o in enumerate(order) if name.startswith(o)), len(order))


def build_class_inputs(components, *, mode, source_order=None) -> dict:
    """components: [{"cas","name","low","high","class_rows":[{"result_code","source"}]}], mode: "low"|"high".

    반환: by_class {class_code: {구분키: [함량…]}}, used, dropped, assumptions.
    항목 X 판정은 evaluate_rules(rules, by_class.get(X, {}), other=by_class, ...)로 호출한다.
    """
    if mode not in ("low", "high"):
        raise ValueError(f"mode는 'low' 또는 'high': {mode!r}")
    order = param_list("classification_source_order") if source_order is None else list(source_order)
    assumptions = [f"구분키: effect가 있으면 'category:effect' 하나만 쓴다 (규칙표 sum(\"3:호흡기자극\") 표기)",
                   f"출처 우선순위: {'; '.join(order)}" + (" (기본값, ate_source.get_ate와 같은 params)" if source_order is None else ""),
                   f"출처 코드 대응: {_SOURCE_NAME} (저장소에 정의 없음, 연습 패키지를 따름)"]
    by_class, used, dropped = {}, [], []
    for c in components:
        pct = c.get(mode)
        who = {"cas": c.get("cas"), "name": c.get("name")}
        if pct is None:
            dropped.append({**who, "reason": f"함량({mode}) 없음"})
            continue
        found = {}  # class_code → [(순위, 출처, 구분키, 코드)]
        for row in c.get("class_rows") or []:
            hit = lookup_class(row["result_code"])
            if hit is None:
                dropped.append({**who, "result_code": row["result_code"], "reason": "class_map에 없는 분류결과코드"})
            elif hit[0] in _NOT_USED:
                dropped.append({**who, "result_code": row["result_code"], "reason": f"{hit[0]}: {_NOT_USED[hit[0]]}"})
            else:
                found.setdefault(hit[0], []).append((_rank(row["source"], order), row["source"], _key(hit[1], hit[3]),
                                                     row["result_code"]))
        for code, rows in found.items():
            best = min(r[0] for r in rows)  # 같은 class_code에 출처가 여럿이면 우선순위가 높은 출처의 행만 쓴다
            for rank, source, key, rc in rows:
                if rank != best:
                    dropped.append({**who, "result_code": rc, "reason": f"{code}: 우선순위가 낮은 출처 {source}"})
                elif key not in {u["key"] for u in used if u["cas"] == who["cas"] and u["class_code"] == code}:
                    by_class.setdefault(code, {}).setdefault(key, []).append(pct)
                    used.append({**who, "class_code": code, "key": key, "content": pct, "source": source, "result_code": rc})
    return {"by_class": by_class, "used": used, "dropped": dropped, "assumptions": assumptions}


def _used_keys(rules: dict) -> dict[str, set]:
    """규칙표 when·flag_if에서 문자열로 쓰는 구분 이름을 항목별로 모은다. other("항목", ...)는 그 항목 몫."""
    used: dict[str, set] = {}
    for name, item in rules["classes"].items():
        exprs = [r["when"] for k in ("rules", "extra_rules") for r in item.get(k) or []]
        exprs += [item["flag_if"]] if item.get("flag_if") else []
        for expr in exprs:
            for n in ast.walk(parse_when(expr)):
                if isinstance(n, ast.Call) and n.func.id in ("sum", "max", "sumx"):
                    used.setdefault(name, set()).update(a.value for a in n.args)
                elif isinstance(n, ast.Call) and n.func.id == "other":
                    used.setdefault(n.args[0].value, set()).update(a.value for a in n.args[1:])
    return used


def check_category_coverage() -> dict:
    """항목별로 {"in_map_unused": class_map에만 있는 구분, "used_not_in_map": 규칙표 when에만 있는 구분}.

    when이 없는 항목(method ate 등)은 건너뛴다. 오류로 막지 않고 목록만 돌려준다.
    """
    rules = load_mixture_rules()
    in_map: dict[str, set] = {}
    for r in load_class_map(rules=rules)["rows"]:
        in_map.setdefault(r["class_code"], set()).add(_key(r["category"], r["effect"]))
    used = _used_keys(rules)
    out = {}
    for name, item in rules["classes"].items():
        if not (item.get("rules") or item.get("extra_rules") or item.get("flag_if")):
            continue
        out[name] = {"in_map_unused": sorted(in_map.get(name, set()) - used.get(name, set())),
                     "used_not_in_map": sorted(used.get(name, set()) - in_map.get(name, set()))}
    return out
