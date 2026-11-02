"""2항 기준 분류 지식 제공자: CAS → 지식DB 분류(환경부·고용노동부) → 단일물질 기준 분류 (설계서 14장 get_reference, 18·19장).

knowledge.py 의 약속 모양(ReferenceKnowledge)에 판정용 칸을 더해 돌려준다:
    {"cas_no", "as_of", "knowledge_version", "classes": [{"class_code", "category", "route_form", "effect", "source",
     "result_code"}], "reference_only": [...국내 고시 밖 구분...], "ate": {"rows": [...]}, "un_no", "source", "reason"}
- 출처 우선순위 D-05: 항목(class_code)마다 환경부(KR02) → 고용노동부(KR03). 같은 항목에 두 출처가 있으면 앞 출처만 쓴다
  (혼합물 class_inputs 와 같은 항목 단위 적용).
- class_map.csv note 에 '참고'가 있는 구분(급성독성 구분5, 피부 3 등 국내 고시 밖)은 reference_only 로 따로 둔다(D-18).
- 흡입 형태는 MSDS 표기(가스·증기·분진·미스트)로 바꾼다.
"""
from ..mixture.class_lookup_db import make_db_class_lookup, make_db_tox_lookup
from ..mixture.params import param_list
from ..mixture.rules_loader import load_class_map

_SRC = {"KR02": "환경부", "KR03": "고용노동부"}
_FORM = {"gas": "가스", "vapour": "증기", "mist": "분진·미스트"}


def _rank(source: str, order: list[str]) -> int:
    name = _SRC.get(source, source)
    return next((i for i, o in enumerate(order) if name.startswith(o)), len(order))


class ReferenceProvider:
    """get_reference(cas_no, as_of). repo 를 주지 않으면 로컬 PostgreSQL(HTODB)."""

    def __init__(self, repo=None, knowledge_version: str | None = None):
        self.repo, self.version = repo, knowledge_version
        self._classes, self._tox = make_db_class_lookup(repo), make_db_tox_lookup(repo)

    def _version(self):
        if self.version:
            return self.version
        try:
            if self.repo is not None:
                return self.repo.version() if hasattr(self.repo, "version") else "htodb"
            from ..mixture.class_lookup_db import _DbRepo
            return _DbRepo().version()
        except Exception:
            return "htodb"

    def get_reference(self, cas_no: str, as_of: str | None) -> dict:
        base = {"cas_no": cas_no, "as_of": as_of, "knowledge_version": None, "classes": [], "reference_only": [],
                "ate": {"rows": []}, "un_no": None, "source": None, "reason": None}
        rows = self._classes(cas_no)
        if not rows:
            return {**base, "reason": getattr(rows, "reason", None) or "지식DB 분류 없음"}
        notes = {code: r["note"] for code, r in load_class_map()["by_code"].items()}
        order = param_list("classification_source_order")
        best: dict[str, int] = {}
        for r in rows:
            if r["class_code"]:
                best[r["class_code"]] = min(best.get(r["class_code"], 99), _rank(r["source"], order))
        classes, ref_only, seen = [], [], set()
        for r in rows:
            if not r["class_code"] or _rank(r["source"], order) != best[r["class_code"]]:
                continue
            row = {"class_code": r["class_code"], "category": r["category"], "route_form": _FORM.get(r["form"]),
                   "effect": r["effect"], "source": _SRC.get(r["source"], r["source"]), "result_code": r["result_code"]}
            key = (row["class_code"], row["category"], row["route_form"], row["effect"])
            if key in seen:
                continue
            seen.add(key)
            (ref_only if "참고" in (notes.get(r["result_code"]) or "") else classes).append(row)
        return {**base, "knowledge_version": self._version(), "classes": classes, "reference_only": ref_only,
                "ate": {"rows": list(self._tox(cas_no))}, "source": "TO21 지식DB GHS_CHEM_CLASS_MAP (D-05 환경부→고용노동부)"}
