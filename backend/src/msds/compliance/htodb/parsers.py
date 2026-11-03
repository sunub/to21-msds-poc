"""HTODB 텍스트 값 → 숫자 파싱 규칙. to21/Msds-test_v0.4/ghsclass/reference/parsers.py를 옮겨 왔다.

독성·물성 값은 대부분 문장(primary_value_text)으로 들어 있고, 숫자 컬럼(primary_value)은 '=' 값일 때만 채워져 있다.
아래 규칙으로 숫자·부등호·단위를 뽑고, 못 뽑은 값은 None으로 돌려 '자료 부족'으로 처리한다.
원본 행은 바꾸지 않는다. API는 원본 행 옆에 이 결과를 따로 붙여 돌려준다.
"""
from __future__ import annotations

import re
from typing import Optional

NUM = r"(\d[\d,]*\.?\d*|\.\d+)"
SIGNS = {"＞": ">", "＜": "<", "≥": ">=", "≤": "<=", "=": "=", ">": ">", "<": "<", "≧": ">=", "≦": "<=", "": "="}
UNITS = {"㎎/㎏": "mg/kg", "mg/kg": "mg/kg", "㎎/kg": "mg/kg", "mg/㎏": "mg/kg", "㎎/ℓ": "mg/L", "mg/l": "mg/L",
         "mg/L": "mg/L", "㎎/L": "mg/L", "ppm": "ppm", "ppmV": "ppm", "mg/m3": "mg/m3", "㎎/㎥": "mg/m3"}
ROUTE_UNIT = {"GHS0201": "mg/kg", "GHS0202": "mg/kg", "GHS0203": "ppm", "GHS0204": "mg/L", "GHS0205": "mg/L"}

NOEC_GAP = r"(?:(?![A-Za-z]*C50|LOEC|NOEC|EC\d|ChV|NOEL|LOEL|MATC)[^=<>＞≥≤]){0,30}?"

ACUTE_DIVS = set(ROUTE_UNIT)
AQUATIC_ACUTE_DIVS = {"GHS0311", "GHS0312", "GHS0313", "GHS0314"}
AQUATIC_CHRONIC_DIVS = {"GHS0325", "GHS0326", "GHS0327", "GHS0328"}
RAPID_DIV = "GHS0331"
PHYS_IDS = {"G0901000001": "STATE", "G0904000000": "PH", "G0906000000": "BOILING_POINT",
            "G0907000000": "FLASH_POINT", "G0918000000": "VISCOSITY_40"}


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def to_float(v) -> Optional[float]:
    """DB의 문자열 숫자 컬럼(primary_value, molecular_weight) → float. 비었거나 숫자가 아니면 None."""
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


_RANGE_FACTORS = (1.0, 0.5, 0.25, 2 ** -0.5, 2.0, 4.0, 0.001, 1000.0)  # 그대로, 시간 환산(T-02·03), mg/㎥↔mg/L


def parse_acute(text: str, primary_value: Optional[str], div_code: str, mw: Optional[float] = None) -> Optional[dict]:
    """급성독성 1건 → {descriptor, sign, value, value_max, unit, species, basis} 또는 None(정성 문장)."""
    text = text or ""
    m = re.search(r"(LD50|LC50|ATE)\s*([＞＜≥≤≧≦><=]{0,2})\s*" + NUM + r"\s*(?:~\s*" + NUM + r")?\s*"
                  r"(㎎/㎏|mg/kg|㎎/kg|mg/㎏|㎎/ℓ|mg/l|mg/L|㎎/L|ppmV|ppm|mg/m3|㎎/㎥)?", text)
    sp = re.search(r"실험종\s*:\s*([A-Za-z가-힣]+(?:\s+pig)?)", text)
    species = sp.group(1) if sp else ""
    target = ROUTE_UNIT.get(div_code, "")
    pv = to_float(primary_value)
    headline = bool(m) and not text[:m.start()].strip()  # 괄호 속 다른 시험 값은 보지 않는다
    head_unit = UNITS.get(m.group(5) or "", m.group(5) or "") if headline else ""
    # 정규식이 모르는 단위(㎖/㎏, ㎍ 등)가 붙은 문장이면 문장 숫자를 쓰지 않는다
    unknown_unit = headline and not m.group(5) and text[m.end():].lstrip()[:1] in tuple("㎖㎍µμmMuU")
    lo = _num(m.group(3)) if headline else None
    hi = _num(m.group(4)) if headline and m.group(4) else None
    # 숫자 칸이 단위를 안 바꾼 문장 값 그대로인 행(159행)은 문장을 읽는다. 흡입 칸의 'LC50 … ㎎/㎏'은 값이 행의 구분과
    # 맞는 단위 오타라 숫자 칸을 쓰고, 'LD50 … ㎎/㎏'은 경피 값을 잘못 넣은 것이라 문장 쪽에서 계산에서 뺀다
    unconverted = (headline and head_unit and target and head_unit != target and pv == (lo if hi is None else max(lo, hi))
                   and not (head_unit == "mg/kg" and m.group(1) == "LC50"))
    if pv is not None and not unconverted:  # DB가 표준 단위로 바꿔 둔 숫자를 우선 사용
        # 문장 첫머리가 부등호면 숫자 칸이 차 있어도 부등호다. '<'는 실제 값이 더 낮으므로 그 값을 안전한 쪽 상한으로 계산한다
        raw_sign = {">=": ">=", "<=": "<=", "<": "<="}.get(m.group(2), SIGNS.get(m.group(2), "=")) if headline else "="
        value, value_max, basis = pv, None, "PRIMARY_VALUE"
        if hi is not None and not unknown_unit:
            small, big = min(lo, hi), max(lo, hi)
            factor = pv / big if big else None
            # 범위는 최솟값을 쓴다 (D-12). 숫자 칸은 대부분 상한이고(735행), 노출시간·단위 환산을 상한에만 한 행도 있어
            # 같은 배율을 하한에 곱한다. 배율이 알려진 환산이 아니면(기하평균 등) 숫자 칸을 그대로 둔다
            # 단위가 다르면 숫자 칸은 시간만 환산한 값일 수 있다(말로노니트릴 ㎎/㎥). ㎎/㎥만 단위까지 맞추고 나머지는 그대로 둔다
            scale = 1.0 if head_unit in ("", target) else 0.001 if (head_unit, target) == ("mg/m3", "mg/L") else None
            if scale and factor is not None and any(abs(factor - k) <= 0.01 * k for k in _RANGE_FACTORS):
                value, value_max, basis = small * factor * scale, pv * scale, "PRIMARY_VALUE · 범위 최솟값"
        return {"descriptor": m.group(1) if m else "", "sign": raw_sign, "value": value, "value_max": value_max,
                "unit": target, "species": species, "basis": basis}
    if not m:
        return None
    sign = {">=": ">=", "<=": "<="}.get(m.group(2), SIGNS.get(m.group(2), "?"))
    v, vmax = _num(m.group(3)), (_num(m.group(4)) if m.group(4) else None)
    unit = UNITS.get(m.group(5) or "", m.group(5) or "")
    note = "PRIMARY_VALUE_TEXT 파싱"
    if unit == "ppm" and target == "mg/L" and mw:            # 증기 ppm → mg/L (25℃, 설계서 U-07 — 참고)
        v, vmax, unit, note = v * mw / 24450, (vmax * mw / 24450 if vmax else None), "mg/L", note + " · ppm→mg/L 환산(참고)"
    if unit == "mg/m3" and target == "mg/L":
        v, vmax, unit, note = v / 1000, (vmax / 1000 if vmax else None), "mg/L", note + " · mg/㎥→mg/L 환산"
    if target and unit and unit != target:
        note += f" · 단위 {unit} ≠ {target} — 계산 제외"
        return {"descriptor": m.group(1), "sign": "?", "value": v, "value_max": vmax, "unit": unit,
                "species": species, "basis": note}
    if vmax is not None:                                      # 범위값은 최소값 (D-12)
        note += " · 범위값 → 최소값"
    return {"descriptor": m.group(1), "sign": sign, "value": v, "value_max": vmax, "unit": unit or target,
            "species": species, "basis": note}


def parse_lc50(text: str) -> Optional[tuple[str, float]]:
    """수생 급성(GHS0311~0314) → (부등호, 값 mg/L). 범위면 최소값."""
    m = re.search(r"(?:LC50|EC50|ErC50|EbC50|EL50)\s*([＞＜><≥≤]?)\s*" + NUM + r"\s*(?:~\s*" + NUM + r")?\s*(㎎/ℓ|mg/l|mg/L)", text or "")
    if not m:
        return None
    return SIGNS.get(m.group(1), "="), _num(m.group(2))


def parse_noec(text: str) -> Optional[float]:
    """수생 만성(GHS0325~0328) 문장에서 '=' NOEC 값 중 최소값 (mg/L). '>' 값만 있으면 None."""
    vals = []
    # NOEC와 값 사이에 시험 기간(72h, 21d)이나 종 이름이 끼어도 받는다. 사이에 다른 종말점(LC50 등)이 나오면 그 값은 가져오지 않는다.
    for m in re.finditer(r"NOEC(?!\d+\s*[=<>＞≥≤])" + NOEC_GAP + r"([=<>＞]?)\s*" + NUM + r"\s*(?:mg/L|mg/l|㎎/ℓ)", text or ""):
        if m.group(1) in ("", "="):
            vals.append(_num(m.group(2)))
    return min(vals) if vals else None


def parse_rapid(text: str) -> Optional[bool]:
    """생분해성(GHS0331) → 빠르게 분해되는가. '이분해성' True, '난분해성' False, 28일 ≥60% True."""
    t = text or ""
    if "이분해성" in t:
        return True
    if "난분해성" in t:
        return False
    m = re.search(NUM + r"\s*%\s*28\s*day", t)
    if m:
        return _num(m.group(1)) >= 60
    return None


def parse_phys(prop_id: str, text: str) -> Optional[float | str]:
    """물성 1건 → 판정에 쓰는 값. 성상은 문자열, 나머지는 숫자. 못 뽑으면 None."""
    t = text or ""
    if prop_id == "G0901000001":                              # 성상
        for k in ("기체", "가스", "액체", "고체"):
            if k in t:
                return "기체" if k == "가스" else k
        return None
    if any(k in t for k in ("해당없음", "불연성", "자료없음")):
        return None
    if prop_id == "G0907000000":                              # 인화점: ℃ 값이 여러 개면 최소값
        vals = [_num(x) if not x.startswith("-") else -_num(x[1:]) for x in re.findall(r"(-?\d+\.?\d*)\s*℃", t)]
        return min(vals) if vals else None
    if prop_id == "G0918000000":                              # 점도: 40℃ 동점도(mm2/s)만 사용, cP·mPa·s(점성도)는 제외
        is_40c = re.search(r"(?<![\d.,~-])40\s*(?:℃|°C|°|도|C\b)", t)   # '40 cSt'·'140'·'30-40' 같은 숫자는 40℃가 아님
        if any(k in t for k in ("cP", "mPa")) or not any(k in t for k in ("동점성", "mm2/s", "㎟/s", "cSt")) or not is_40c:
            return None
        m = re.search(r"(-?\d+\.?\d*)", t)
        return float(m.group(1)) if m else None
    m = re.search(r"(-?\d+\.?\d*)", t)
    return float(m.group(1)) if m else None


# ---- 원본 행 1건 → 파싱 결과 ----
# 적용할 규칙이 없는 행은 None, 규칙은 있으나 값을 못 뽑았으면 {"rule": ..., "result": None}(자료 부족).

def parse_toxicity_row(row: dict, mw: Optional[float] = None) -> Optional[dict]:
    div, text = row.get("div_code"), row.get("primary_value_text")
    if div in ACUTE_DIVS:
        return {"rule": "acute", "result": parse_acute(text, row.get("primary_value"), div, mw)}
    if div in AQUATIC_ACUTE_DIVS:
        p = parse_lc50(text)
        return {"rule": "aquatic_acute", "result": None if p is None else {"sign": p[0], "value": p[1], "unit": "mg/L"}}
    if div in AQUATIC_CHRONIC_DIVS:
        v = parse_noec(text)
        return {"rule": "aquatic_chronic_noec", "result": None if v is None else {"value": v, "unit": "mg/L"}}
    if div == RAPID_DIV:
        rd = parse_rapid(text)
        return {"rule": "rapid_degradability", "result": None if rd is None else {"rapidly_degradable": rd}}
    return None


def parse_property_row(row: dict) -> Optional[dict]:
    pid = row.get("property_id")
    if pid not in PHYS_IDS:
        return None
    v = parse_phys(pid, row.get("primary_value_text"))
    return {"rule": PHYS_IDS[pid], "result": None if v is None else {"value": v}}
