"""규칙표 조건식 해석기 (설계서 45장 rule_eval). 규칙표_v0.3 rules_check.py와 같은 문법이며 eval은 쓰지 않는다."""

import ast
import operator as op

FUNCS = {"sum", "max", "sumx", "other", "flag", "prop", "has"}
_CMP = {ast.GtE: op.ge, ast.Gt: op.gt, ast.LtE: op.le, ast.Lt: op.lt, ast.Eq: op.eq, ast.NotEq: op.ne}
_ARI = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul}
_OK = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.BinOp, ast.Div, ast.Call, ast.Name, ast.Load,
       ast.Constant, ast.UnaryOp, ast.USub, ast.Compare, *_CMP, *_ARI)


class Missing(Exception):
    """prop()가 읽으려는 물성 값이 없을 때."""


def parse_when(expr: str) -> ast.Expression:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"문법 오류: {expr!r}") from e
    for n in ast.walk(tree):
        if not isinstance(n, _OK):
            raise ValueError(f"허용하지 않는 표현 {type(n).__name__}: {expr!r}")
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in FUNCS):
            raise ValueError(f"허용하지 않는 함수: {expr!r}")
        if isinstance(n, ast.Name) and n.id not in FUNCS:
            raise ValueError(f"알 수 없는 이름 {n.id!r}: {expr!r}")
    return tree


def apply_include_min(comps: dict, minimum) -> dict:
    """한계농도 미만 함량을 뺀다. minimum은 숫자 또는 {구분: 숫자}."""
    if not minimum:
        return comps
    lim = (lambda c: minimum.get(c.split(":")[0], 0)) if isinstance(minimum, dict) else (lambda c: minimum)
    return {c: [v for v in vs if v >= lim(c)] for c, vs in comps.items()}


def _call(n, c):
    f, a = n.func.id, [x.value for x in n.args]
    comps = c["comps"]
    if f == "sum":
        return sum(sum(comps.get(k, [])) for k in a)
    if f == "max":
        return max([v for k in a for v in comps.get(k, [])] or [0])
    if f == "sumx":
        return c["m"] * sum(sum(comps.get(k, [])) for k in a)
    if f == "other":
        oc = c["other"].get(a[0], {})
        return sum(sum(oc.get(k, [])) for k in a[1:])
    if f == "flag":
        return c["flags"].get(a[0], 0)
    if f == "has":
        return a[0] in c["props"]
    if a[0] not in c["props"]:
        raise Missing(a[0])
    return c["props"][a[0]]


def _ev(n, c):
    if isinstance(n, ast.Expression):
        return _ev(n.body, c)
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.UnaryOp):
        return -_ev(n.operand, c)
    if isinstance(n, ast.BoolOp):
        vals = (_ev(v, c) for v in n.values)
        return all(vals) if isinstance(n.op, ast.And) else any(vals)
    if isinstance(n, ast.BinOp):
        a, b = _ev(n.left, c), _ev(n.right, c)
        return (a / b if b else 0) if isinstance(n.op, ast.Div) else _ARI[type(n.op)](a, b)
    if isinstance(n, ast.Compare):
        left = _ev(n.left, c)
        for o, rc in zip(n.ops, n.comparators):
            right = _ev(rc, c)
            if not _CMP[type(o)](left, right):
                return False
            left = right
        return True
    return _call(n, c)


def evaluate_rules(rules, comps, *, other=None, flags=None, props=None, m=1, include_min=None) -> str:
    """rules를 위에서부터 검사해 처음 참인 규칙의 category를 돌려준다. 모두 거짓이면 '분류안됨'.

    comps {구분: [함량…]}, other {class_code: {구분: [함량…]}}, flags {이름: 함량}, props {이름: 값}, m = M-factor.
    prop 값이 없으면 '근거부족(prop 이름)'.
    """
    ctx = {"comps": apply_include_min(comps, include_min), "other": other or {}, "flags": flags or {},
           "props": props or {}, "m": m}
    for r in rules:
        try:
            if _ev(parse_when(r["when"]), ctx):
                return str(r["category"])
        except Missing as e:
            return f"근거부족(prop {e})"
    return "분류안됨"
