"""항별 중간 형식 스키마 ↔ NuExtract 2.0 틀 (B, ADR-010).

NuExtract 2.0은 시스템 안내문 없이 뽑을 칸의 틀(template)만 받는다. 틀의 칸 종류는
verbatim-string, string, integer, number, date-time, 선택지 배열, 배열이고 참/거짓이 없다.
모델은 못 찾은 칸을 null, 배열을 []로 낸다. coerce가 그 응답을 스키마 형으로 맞춘다.
"""
from __future__ import annotations

import math

VERBATIM_KEYS = {"line", "start", "end", "raw"}


def _resolve(node: dict, defs: dict) -> dict:
    while "$ref" in node:
        node = defs[node["$ref"].rsplit("/", 1)[1]]
    return node


def _unwrap(node: dict, defs: dict) -> tuple[dict, bool]:
    """$ref를 풀고 anyOf의 null 가지를 뗀다. (남은 노드, null 허용 여부)."""
    node = _resolve(node, defs)
    if "anyOf" not in node:
        return node, False
    rest = [b for b in node["anyOf"] if b.get("type") != "null"]
    if len(rest) != 1:
        raise ValueError(f"null이 아닌 형이 {len(rest)}개인 anyOf는 틀로 바꿀 수 없다")
    inner, _ = _unwrap(rest[0], defs)
    return inner, len(rest) != len(node["anyOf"])


# ── 틀 ─────────────────────────────────────────────────

def _tmpl(node: dict, defs: dict, key: str, in_lines: bool):
    node, _ = _unwrap(node, defs)
    t = node.get("type")
    if t == "object":
        return {k: _tmpl(v, defs, k, key == "lines") for k, v in node.get("properties", {}).items()}
    if t == "array":
        return [_tmpl(node["items"], defs, key, False)]
    if t == "string":
        if "enum" in node:
            return [v for v in node["enum"] if v is not None]
        return "verbatim-string" if in_lines or key in VERBATIM_KEYS else "string"
    if t in ("number", "integer"):
        return t
    if t == "boolean":
        return ["true", "false"]
    raise ValueError(f"틀로 바꿀 수 없는 형: {t!r}")


def template(schema: dict) -> dict:
    """항별 중간 형식 스키마(response_schema(no))를 NuExtract 2.0 틀로 바꾼다."""
    return _tmpl(schema, schema.get("$defs", {}), "", False)


# ── 응답 맞추기 ────────────────────────────────────────

def _num(v, integer: bool):
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        try:
            v = int(v.strip())
        except ValueError:
            try:
                v = float(v.strip())
            except ValueError:
                return None
    if not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)):
        return None
    if integer:
        return int(v) if float(v).is_integer() else None
    return v


def _empty(v) -> bool:
    return v is None or v == []


def _co(v, node: dict, defs: dict):
    node, nullable = _unwrap(node, defs)
    t = node.get("type")
    if t == "object":
        props = node.get("properties", {})
        src = v if isinstance(v, dict) else {}
        out = {k: _co(src.get(k), sub, defs) for k, sub in props.items()}
        if nullable and (v is None or all(_empty(x) for x in out.values())):
            return None
        return out
    if t == "array":
        if not isinstance(v, list):
            return []
        item, _ = _unwrap(node["items"], defs)
        out = []
        for x in v:
            c = _co(x, node["items"], defs)
            if c is None or (item.get("type") == "object" and not _row_ok(c, item, defs)):
                continue
            out.append(c)
        return out
    if t == "string":
        s = v if isinstance(v, str) else str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        return s if s is None or "enum" not in node or s in node["enum"] else None
    if t in ("number", "integer"):
        return _num(v, t == "integer")
    if t == "boolean":
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in ("true", "false"):
            return v.strip().lower() == "true"
        return None
    return v


def _row_ok(row: dict, item: dict, defs: dict) -> bool:
    """필수이면서 null을 받을 수 없는 칸이 비면 그 행은 쓸 수 없다."""
    props = item.get("properties", {})
    return all(row[k] is not None or _unwrap(props[k], defs)[1] for k in item.get("required", []) if k in props)


def coerce(output, schema: dict) -> dict:
    """NuExtract 응답(parse_json 결과)을 스키마 형에 맞춘다. 입력은 바꾸지 않는다."""
    return _co(output, schema, schema.get("$defs", {}))
