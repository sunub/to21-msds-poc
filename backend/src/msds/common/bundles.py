"""추출 묶음 정의 읽기 (configs/bundles.yaml, D-35)."""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from .paths import CONFIGS


@dataclass
class Bundle:
    id: str
    name: str
    sections: str
    keys: list[str]
    doc_keys: list[str] = field(default_factory=list)
    code_tables: list[str] = field(default_factory=list)
    dictionary: list[str] = field(default_factory=list)


def load_bundles() -> dict[str, Bundle]:
    with open(CONFIGS / "bundles.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return {bid: Bundle(id=bid, **{k: v for k, v in b.items()}) for bid, b in cfg["bundles"].items()}


def bundle_order() -> list[str]:
    """b1을 먼저 돌려야 한다(성분 목록을 다른 묶음에 넘김)."""
    return list(load_bundles().keys())
