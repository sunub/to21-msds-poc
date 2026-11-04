"""TO21 검증기(V01~V23)를 우리 코드에서 부르는 창구.

TO21 파일은 이름에 한글과 점이 있어 일반 import가 안 되므로 파일 경로로 읽는다.
TO21 원본은 고치지 않는다 (to21/v0.6/).
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache

from ..common.paths import to21_file


@lru_cache(maxsize=None)
def load_to21_module(kind: str):
    """kind: validator | scorer | regen | coverage"""
    path = to21_file(kind)
    spec = importlib.util.spec_from_file_location(f"to21_{kind}", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SyntaxError:
        # shortcut: 재생성 스크립트 main()(명령줄 실행용)이 3.12 문법이라 3.11에서 못 읽는다(B-15). 쓰는 함수는 main 앞에 있어 그 앞만 읽는다. 팀이 3.12로 가면 지운다
        source = path.read_text(encoding="utf-8").split("\ndef main():")[0]
        exec(compile(source, str(path), "exec"), mod.__dict__)
    return mod


def run_to21_validator(doc: dict) -> list[dict]:
    """[{level: 오류|경고, rule: V01.., field: 경로, message: 설명}]"""
    mod = load_to21_module("validator")
    out = []
    for r in mod.check(doc):
        level, rule, field, message = (list(r) + [None] * 4)[:4]
        out.append({"level": level, "rule": rule, "field": field, "message": message})
    return out
