"""H코드로 추론한 그림문자와 모델이 쪽 이미지에서 읽은 그림문자를 대조한다 (B, ADR-019).

매핑표는 E의 hazard_label_map.csv(고용노동부고시 별표2에서 만든 표) 사본 configs/hazard_label_map.csv다.
e/classify를 합치지 않고 파일만 가져왔다(출처는 hazard_label_map.SOURCE.txt). E가 main에 합치면 읽는 경로만 바꾼다.
대조 결과로 재추출하지 않는다. 실행기가 checks에 남기고 다르면 사람 검토로 표시한다.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from msds.common.paths import CONFIGS

HAZARD_MAP = CONFIGS / "hazard_label_map.csv"
SKIPPED = "hazard_label_map.csv 없음"
_BASE = re.compile(r"H\d{3}")


def load_hazard_map(path: Path | None = None) -> dict[str, set[str]] | None:
    """backend/configs/hazard_label_map.csv(E 표의 사본)를 읽어 H코드 → 그림문자 집합. 파일이 없으면 None.
    기본 경로는 msds.common.paths.CONFIGS / "hazard_label_map.csv". 빈 pictogram 칸(구분 5 등)은 넣지 않는다."""
    path = Path(path) if path else HAZARD_MAP
    if not path.is_file():
        return None
    out: dict[str, set[str]] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            h, pictogram = (r.get("h_code") or "").strip(), (r.get("pictogram") or "").strip()
            if h and pictogram:
                out.setdefault(h, set()).add(pictogram)
    return out


def infer_pictograms(h_codes: list[str], hmap: dict[str, set[str]]) -> set[str]:
    """H코드마다 매핑표의 그림문자를 모은다. 결합 코드(H302+H312)는 나눠 보고, 표에 없으면 접미 문자(H360FD)를 떼고 찾는다."""
    out: set[str] = set()
    for code in h_codes:
        for part in (code or "").split("+"):
            part = part.strip()
            base = _BASE.match(part)
            out |= hmap.get(part) or (hmap.get(base.group(0)) if base else None) or set()
    return out


def compare(model_codes: list[str], inferred: set[str]) -> dict:
    """{"model": [...], "inferred": [...], "missing": [...], "extra": [...], "ok": bool}
    missing은 추론했는데 모델이 안 쓴 것, extra는 모델이 썼는데 추론에 없는 것이다."""
    model = {c for c in model_codes if c}
    return {"model": sorted(model), "inferred": sorted(inferred), "missing": sorted(inferred - model),
            "extra": sorted(model - inferred), "ok": model == inferred}


def check_msds(msds_item: dict, hmap: dict[str, set[str]] | None) -> dict:
    """TO21 msds 항목 하나: hazard.h_statements의 코드로 추론해 hazard.pictograms의 코드와 비교한다.
    매핑표가 없으면(hmap None) {"skipped": "hazard_label_map.csv 없음"}."""
    if hmap is None:
        return {"skipped": SKIPPED}
    hazard = msds_item.get("hazard") or {}
    h_codes = [r.get("code") for r in hazard.get("h_statements") or []]
    return compare([r.get("code") for r in hazard.get("pictograms") or []], infer_pictograms(h_codes, hmap))
