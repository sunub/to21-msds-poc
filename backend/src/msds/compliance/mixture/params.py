"""규칙 파일(rules/*.csv)을 읽는 공통 함수와 rules/params.csv의 값 읽기. 키가 없으면 KeyError이고 기본값을 쓰지 않는다."""
import csv
from functools import lru_cache
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"


def read_rules(path: Path) -> list[dict]:
    """'#'으로 시작하는 줄(머리 정보·설명)은 건너뛰고 행을 dict로 읽는다."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


@lru_cache
def _params() -> dict[str, str]:
    return {r["key"]: r["value"] for r in read_rules(RULES_DIR / "params.csv")}


def has_param(key: str) -> bool:
    return key in _params()


def param(key: str):
    """숫자로 읽을 수 있으면 숫자(정수 또는 실수), 아니면 글자."""
    v = _params()[key]
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def param_list(key: str) -> list[str]:
    return _params()[key].split(";")
