"""독성값의 단위·노출시간을 ATE 표의 목표 단위와 4시간 기준으로 맞춘다 (설계서 v0.4 19장)."""
import csv
from functools import lru_cache

from .acute import _FORM, _ROUTE, RULES, _rows

_DIR = RULES.parent
_STD_HOURS = 4  # 고시 ATE 표의 흡입 기준 노출시간
_ALIAS = {
    "mg/kg": "mg/kg", "㎎/㎏": "mg/kg", "mg/kgbw": "mg/kg", "㎎/㎏bw": "mg/kg",
    "mg/l": "mg/L", "㎎/ℓ": "mg/L", "㎎/l": "mg/L",
    "mg/m3": "mg/m3", "mg/m³": "mg/m3", "㎎/㎥": "mg/m3",
    "ppm": "ppm", "ppmv": "ppm",
    "g/kg": "g/kg", "µg/kg": "µg/kg", "μg/kg": "µg/kg", "㎍/㎏": "µg/kg",
    "g/m3": "g/m3", "g/m³": "g/m3", "mmol/kg": "mmol/kg", "ml/kg": "mL/kg", "㎖/㎏": "mL/kg",
}


def _canon(unit):
    return _ALIAS.get("".join(str(unit or "").split()).lower())


@lru_cache
def _table(name):
    with open(_DIR / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def _convert(rule, value, mw, density):
    if rule["needs"] == "mw":
        return value * mw / (24450 if rule["rule_id"] == "U-07" else 1)
    if rule["needs"] == "density":
        return value * density * 1000
    return value * float(rule["factor"])


def to_target(value, unit, route, form=None, *, mw=None, density=None, hours=None) -> dict | None:
    """ATE 목표 단위·4시간 기준의 {"value","unit","note"}. 환산할 수 없으면 None."""
    target = _rows(_ROUTE[route], _FORM.get(form))[0]["unit"]
    src, notes = _canon(unit), []
    if src is None:
        return None
    if src != _canon(target):
        rule = next((r for r in _table("units.csv") if _canon(r["from_unit"]) == src
                     and _canon(r["to_unit"]) == _canon(target)), None)
        if rule is None or (rule["form_only"] and rule["form_only"] != form):
            return None
        if (rule["needs"] == "mw" and not mw) or (rule["needs"] == "density" and not density):
            return None
        value = _convert(rule, value, mw, density)
        notes.append(f"{rule['rule_id']} 환산" + (f" {rule['note']}" if rule["note"] else ""))
    if route == "inhal" and hours not in (None, _STD_HOURS):
        t = next((r for r in _table("units_time.csv") if r["form"] == form and float(r["hours"]) == hours), None)
        if t:
            value /= float(t["divisor"])
            notes.append(f"{t['rule_id']} {hours:g}시간→{_STD_HOURS}시간")
        else:
            notes.append("참고(노출시간 미환산)")
    return {"value": value, "unit": target, "note": " · ".join(notes)}
