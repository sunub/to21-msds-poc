"""15항 규제 지식 제공자: CAS → 지식DB 규제 행 → 15항 항목 코드와 함량 기준 (설계서 14장 get_regulation, 27·28장).

knowledge.py 의 약속 모양(RegulationKnowledge)으로 돌려준다:
    {"cas_no", "as_of", "knowledge_version", "rows": [{"law", "item_code", "threshold_op", "threshold_value",
     "threshold_unit", "source", "rule_id", "regulate_item_id", "kind", "note", "group_name"}], "reason"}
- repo 는 htodb.repo(로컬 PostgreSQL) 또는 htodb.csv_repo.CsvRepo(샘플 CSV). chemicals(cas=), regulations(chem_id) 를 쓴다.
- 규제 번호 → 항목 코드 번역은 rules/reg_map.csv. kind=reference(15항 기재 대상 아님)는 돌려주지 않는다.
- 지식DB에 없는 CAS, 접속 실패는 knowledge_version=None 과 reason 으로 돌려준다(설계서 27장: 자료 없음 → 근거부족).
- DB 값은 바꾸지 않고 해석만 한다: 부호 ≥→>=, ＞→>, 단위 wt%·vol%→% (vol%는 중량%로 비교, 설계서 미결 7).
"""
import os
import re
from functools import lru_cache
from pathlib import Path

from ..mixture.params import read_rules

REG_MAP = Path(__file__).resolve().parents[1] / "rules" / "reg_map.csv"
_SIGN = {"≥": ">=", "≧": ">=", ">=": ">=", "이상": ">=", "＞": ">", ">": ">", "초과": ">", "": ">=", "=": ">="}
_PCT = {"%": "%", "wt%": "%", "w/w%": "%", "vol%": "%", "v/v%": "%"}
_GROUP_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(이상|초과)")


@lru_cache
def reg_map() -> dict[str, dict]:
    """REGULATE_ITEM_ID → reg_map.csv 행."""
    return {r["regulate_item_id"]: r for r in read_rules(REG_MAP)}


def covered_items() -> set[str]:
    """지식DB가 다루는 15항 항목 코드. 여기에 없는 항목(POPS, CCA_PERMIT 등)은 DB로 해당 여부를 알 수 없다."""
    return {r["item_code"] for r in reg_map().values() if r["item_code"] and r["kind"] != "reference"}


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _alive(r) -> bool:
    return str(r.get("is_del", "0")).strip().lower() in ("0", "false", "none", "")


def _pct(value, unit, sign, label):
    v, u = _num(value), (unit or "").strip().lower()
    if v is None or u not in _PCT:
        return None
    note = f"{label} {(sign or '').strip()}{v:g} {unit}"
    if u.startswith("vol") or u.startswith("v/v"):
        note += " (vol% 기준을 중량%로 비교, 설계서 미결 7)"
    return _SIGN.get((sign or "").strip(), ">="), v, note


def _threshold(field: str, r: dict):
    """REG_NOTICE_STD 행 하나에서 (op, 값, 설명). 함량(%) 기준이 아니면 None."""
    if field == "STD":
        return _pct(r.get("std_value_primary"), r.get("std_value_primary_unit"), r.get("std_value_primary_sign"),
                    "STD_VALUE_PRIMARY")
    if field == "RESEARCH":
        return _pct(r.get("research_range_std"), r.get("research_range_unit"), r.get("research_range_sign"),
                    "RESEARCH_RANGE_STD")
    if field == "PSM":
        if m := _GROUP_PCT.search(r.get("chem_group_name") or ""):
            return (">=" if m.group(2) == "이상" else ">"), float(m.group(1)), f"물질군 이름 '{r['chem_group_name']}'"
        if (v := _num(r.get("research_range"))) is not None:
            return ">=", v, f"RESEARCH_RANGE {v:g} (단위 없음 → %로 봄)"
    return None


def regulation_rows(data: dict) -> list[dict]:
    """repo.regulations(chem_id) 결과 → get_regulation 의 rows. 같은 항목에 기준이 여럿이면 가장 낮은 값을 쓴다."""
    std_by_item: dict[str, list[dict]] = {}
    for s in data.get("notice_std") or []:
        if _alive(s):
            std_by_item.setdefault(s["regulate_item_id"], []).append(s)
    out = []
    for m in data.get("rows") or []:
        meta = reg_map().get(m.get("regulate_item_id"))
        if not _alive(m) or meta is None or meta["kind"] == "reference":
            continue
        stds = std_by_item.get(m["regulate_item_id"], [])
        found = [t for t in (_threshold(meta["threshold_field"], s) for s in stds) if t]
        row = {"law": meta["law_code"], "item_code": meta["item_code"], "regulate_item_id": m["regulate_item_id"],
               "rule_id": meta["rule_id"], "kind": meta["kind"], "db_item_name": meta["db_item_name"],
               "group_name": next((s.get("chem_group_name") for s in stds if s.get("chem_group_name")), None),
               "threshold_op": None, "threshold_value": None, "threshold_unit": None,
               "source": f"HTODB {m['regulate_item_id']} {meta['db_item_name']} ({meta['rule_id']})", "note": ""}
        if found:
            op, v, note = min(found, key=lambda t: t[1])  # 여러 기준이면 가장 낮은(엄격한) 값
            row.update(threshold_op=op, threshold_value=v, threshold_unit="%", note=note)
            if len({(t[0], t[1]) for t in found}) > 1:
                row["note"] += f" · 기준 {len(found)}개 중 가장 낮은 값"
        else:
            row["note"] = "함량 기준 없음 → 함유하면 해당(설계서 28장)"
        out.append(row)
    return sorted(out, key=lambda r: (r["law"], r["item_code"], r["regulate_item_id"]))


class RegulationProvider:
    """get_regulation(cas_no, as_of). repo 를 주지 않으면 로컬 PostgreSQL(HTODB)을 쓴다."""

    def __init__(self, repo=None, knowledge_version: str | None = None):
        self.repo, self.version = repo, knowledge_version
        self._cache: dict[str, dict] = {}

    def _open(self):
        if self.repo is not None:
            return self.repo
        from ..mixture.class_lookup_db import _DbRepo  # psycopg 는 DB를 쓸 때만 읽는다
        return _DbRepo()

    def get_regulation(self, cas_no: str, as_of: str | None) -> dict:
        if cas_no not in self._cache:
            self._cache[cas_no] = self._query(cas_no)
        return {**self._cache[cas_no], "as_of": as_of}

    def _query(self, cas_no):
        base = {"cas_no": cas_no, "knowledge_version": None, "rows": [], "reason": None}
        if self.repo is None and os.environ.get("HTODB_SKIP") == "1":
            return {**base, "reason": "지식DB 조회 안 함(HTODB_SKIP=1)"}
        try:
            repo = self._open()
            chems = repo.chemicals(cas=cas_no)["rows"]
            if not chems:
                return {**base, "reason": "지식DB에 등록되지 않은 CAS"}
            rows = []
            for c in chems:
                rows += regulation_rows(repo.regulations(c["chem_id"]))
            version = self.version or (repo.version() if hasattr(repo, "version") else None) or "htodb"
        except Exception as e:  # 접속 불가·권한·쿼리 오류는 멈추지 않고 이유로 남긴다
            return {**base, "reason": f"지식DB 접속·조회 실패({type(e).__name__}: {e})"}
        return {**base, "knowledge_version": version, "rows": rows}
