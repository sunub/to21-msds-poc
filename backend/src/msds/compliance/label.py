"""분류(class_code, category) 목록에서 그림문자·신호어·H코드를 도출한다 (고시 별표2, 제6조의2)."""
from functools import lru_cache
from pathlib import Path

from .mixture.params import read_rules

_MAP = Path(__file__).parent / "rules" / "hazard_label_map.csv"
_IRRITANT = {"HH_SKIN_CORR", "HH_EYE_DMG"}  # 자극성에서 온 GHS07만 부식성(GHS05) 아래로 숨는다


@lru_cache
def _rows() -> list[dict]:
    return read_rules(_MAP)


def _find(code: str, cat: str | None) -> list[dict]:
    if not cat or (code.startswith("HH_ACUTE") and cat == "5"):  # 구분5는 고시 참고라 분류 제외
        return []
    rows = [r for r in _rows() if r["class_code"] == code]
    return [r for r in rows if r["category"] == cat] or [r for r in rows if r["category"].startswith(cat)]


def derive_label(classes: list[tuple[str, str | None]]) -> dict:
    """classes: [(class_code, category)]. 반환: pictograms, signal_word, h_codes."""
    hits = [(c, r) for c, cat in classes for r in _find(c, cat)]
    pc = {(r["pictogram"], c) for c, r in hits if r["pictogram"]}

    def drop07(src: set[str] | None = None) -> None:
        nonlocal pc
        pc = {x for x in pc if not (x[0] == "GHS07" and (src is None or x[1] in src))}

    have = {p for p, _ in pc}
    if "GHS06" in have:  # 제6조의2 ②1호
        drop07()
    if "GHS05" in have:  # ②2호
        drop07(_IRRITANT)
    if ("GHS08", "HH_RESP_SENS") in pc:  # ②3호
        drop07({"HH_SKIN_SENS"} | _IRRITANT)

    words = {r["signal_word"] for _, r in hits}
    return {
        "pictograms": sorted({p for p, _ in pc}),
        "signal_word": "위험" if "위험" in words else "경고" if "경고" in words else "없음" if hits else None,
        "h_codes": sorted({r["h_code"] for _, r in hits}),
    }
