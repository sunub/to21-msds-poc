"""분류(class_code, category) 목록에서 그림문자·신호어·H코드를 도출한다 (고시 별표2, 제6조의2).

생략·우선순위 규칙은 rules/label_rules.yaml, 분류 ↔ 표시 요소는 rules/hazard_label_map.csv에서 읽는다.
"""
from functools import lru_cache
from pathlib import Path

import yaml

from .mixture.params import read_rules

_RULES = Path(__file__).parent / "rules"
_MAP = _RULES / "hazard_label_map.csv"


@lru_cache
def label_rules() -> dict:
    with open(_RULES / "label_rules.yaml", encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


@lru_cache
def _rows() -> list[dict]:
    return read_rules(_MAP)


_EFFECT_WORDS = ("마취", "호흡기")


def _find(code: str, cat: str | None, effect: str | None = None) -> list[dict]:
    if not cat or any(code.startswith(s["class_prefix"]) and cat == s["category"] for s in label_rules()["skip_category"]):
        return []
    rows = [r for r in _rows() if r["class_code"] == code]
    found = [r for r in rows if r["category"] == cat] or [r for r in rows if r["category"].startswith(cat)]
    words = [w for w in _EFFECT_WORDS if w in (effect or "")]
    if words and len(found) > 1:  # 표적장기 1회 구분3: 효과(마취 → H336, 호흡기 자극 → H335)로 행을 고른다(11/02 F)
        found = [r for r in found if any(w in (r.get("note") or "") for w in words)] or found
    return found


def _match(pc: set, pictogram: str, from_classes: list[str] | None) -> set:
    return {x for x in pc if x[0] == pictogram and (from_classes is None or x[1] in from_classes)}


def derive_label(classes: list[tuple]) -> dict:
    """classes: [(class_code, category)] 또는 [(class_code, category, effect)]. 반환: pictograms, signal_word, h_codes."""
    rules = label_rules()
    hits = [(c[0], r) for c in classes for r in _find(c[0], c[1], c[2] if len(c) > 2 else None)]
    pc = {(r["pictogram"], c) for c, r in hits if r["pictogram"]}
    omitted = set()
    for rule in rules["pictogram_omit"]:  # 조건은 생략 전 상태로 판단한다
        cond, omit = rule["if_present"], rule["omit"]
        if _match(pc, cond["pictogram"], cond.get("from_classes")):
            omitted |= _match(pc, omit["pictogram"], omit.get("from_classes"))
    pc -= omitted

    sig, words = rules["signal_word"], {r["signal_word"] for _, r in hits}
    return {
        "pictograms": sorted({p for p, _ in pc}),
        "signal_word": next((w for w in sig["priority"] if w in words),
                            sig["fallback_with_hits"] if hits else sig["fallback_no_hits"]),
        "h_codes": sorted({r["h_code"] for _, r in hits}),
    }
