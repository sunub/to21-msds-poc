"""TO21 스키마 v0.6 읽기, 묶음별로 자르기, 모델 응답 형식 만들기, 검증.

- 최종 결과(실버·기준선·골드)는 항상 TO21 스키마 그대로다 (D-31).
- 모델에게는 묶음별로 잘라 낸 스키마를 응답 형식으로 준다 (D-35).
- 응답 형식에는 TO21 칸 외에 근거 목록(evidence)을 함께 받는다.
  실버 모드에서는 근거마다 적용 규칙(rules)과 설명(note)을 추가로 받는다 (D-33, D-36).
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache

from jsonschema import Draft202012Validator

from .paths import to21_file


@lru_cache(maxsize=1)
def load_schema() -> dict:
    with open(to21_file("schema"), encoding="utf-8") as f:
        return json.load(f)


def msds_item_schema() -> dict:
    return load_schema()["properties"]["msds"]["items"]


def doc_schema() -> dict:
    return load_schema()["properties"]["doc"]


def _nullable(t: dict) -> dict:
    return {"anyOf": [t, {"type": "null"}]}


def evidence_item_schema(with_review: bool) -> dict:
    """모델 응답 안의 근거 항목.

    field: msds 항목 안의 경로. 목록은 항목 단위(components[0], regulations[3]),
           단일 칸은 칸 단위(meta.last_revision_date)로 적는다.
    msds_index: 한 파일에 MSDS가 여러 건일 때 몇 번째 MSDS인지 (0부터).
    """
    props = {
        "msds_index": {"type": "integer"},
        "field": {"type": "string"},
        "page": _nullable({"type": "integer"}),
        "source_text": _nullable({"type": "string"}),
    }
    if with_review:
        props["rules"] = {"type": "array", "items": {"type": "string"}}
        props["note"] = _nullable({"type": "string"})
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


def bundle_response_schema(keys: list[str], doc_keys: list[str] | None = None, with_review: bool = False) -> dict:
    """묶음 하나의 모델 응답 형식.

    {
      "doc":      {language, msds_count}        # 묶음 ①만
      "msds":     [ {묶음 키만 담은 msds 항목}, ... ]
      "evidence": [ {msds_index, field, page, source_text, (rules, note)} ]
    }
    """
    full = load_schema()
    item = msds_item_schema()
    sliced_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {k: copy.deepcopy(item["properties"][k]) for k in keys},
        "required": list(keys),
    }
    props: dict = {}
    if doc_keys:
        dprops = doc_schema()["properties"]
        props["doc"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {k: copy.deepcopy(dprops[k]) for k in doc_keys},
            "required": list(doc_keys),
        }
    props["msds"] = {"type": "array", "items": sliced_item}
    props["evidence"] = {"type": "array", "items": evidence_item_schema(with_review)}
    return {
        "type": "object",
        "additionalProperties": False,
        "$defs": copy.deepcopy(full["$defs"]),
        "properties": props,
        "required": list(props),
    }


# 구조화 출력(strict)에서 거부될 수 있는 키워드. 검증은 원래 스키마로 다시 하므로 빼도 된다.
_DROP_KEYS = {"$schema", "$id", "format", "minimum", "maximum", "minLength", "maxLength",
              "pattern", "minItems", "maxItems", "examples", "default", "title"}


def to_strict(schema: dict) -> dict:
    """구조화 출력용으로 스키마를 다듬는다.

    - x- 로 시작하는 TO21 확장 키와 일부 키워드를 뺀다.
    - 모든 객체에 additionalProperties=false, 모든 속성을 required로 둔다
      (TO21 스키마는 모든 칸이 null을 허용하므로, '전부 필수 + null 허용'과 의미가 같다).
    """
    def walk(node):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k.startswith("x-") or k in _DROP_KEYS:
                    continue
                out[k] = walk(v)
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"].keys())
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(copy.deepcopy(schema))


def validate(instance, schema: dict) -> list[str]:
    """스키마 위반 목록을 사람이 읽을 수 있는 문장으로 돌려준다. 비어 있으면 통과."""
    v = Draft202012Validator(schema)
    errs = []
    for e in sorted(v.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        loc = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path) or "(최상위)"
        errs.append(f"{loc}: {e.message[:200]}")
    return errs


def validate_to21(doc: dict) -> list[str]:
    """완성된 TO21 문서를 TO21 스키마로 검증한다."""
    return validate(doc, load_schema())
