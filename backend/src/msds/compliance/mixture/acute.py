"""급성독성 혼합물 ATEmix 계산 (고시 별표1 3.1)."""
import csv
import operator
from pathlib import Path

RULES = Path(__file__).resolve().parents[1] / "rules" / "acute_tox_ate.csv"
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


def _rows(route, form):
    with open(RULES, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)
                if r["route"] == route and (r["form"] or None) == (form or None)]


def category_to_ate(route, form, category):
    for r in _rows(route, form):
        if r["category"] == str(category):
            return float(r["ate_convert"])
    return None


def _ok(value, op, bound):
    return not op or OPS[op](value, float(bound))


def value_to_category(route, form, value):
    for r in _rows(route, form):
        if r["in_notice"] != "Y":
            continue
        if _ok(value, r["lower_op"], r["lower"]) and _ok(value, r["upper_op"], r["upper"]):
            return r["category"]
    return None


def ate_mix(parts):
    unknown = sum(p["c"] for p in parts if not p["known"])
    total = sum(p["c"] / p["ate"] for p in parts if p["ate"])
    if total == 0:
        return None, "공식1" if unknown <= 10 else "공식2"
    if unknown <= 10:
        return 100 / total, "공식1"
    return sum(p["c"] for p in parts if p["known"]) / total, "공식2"
