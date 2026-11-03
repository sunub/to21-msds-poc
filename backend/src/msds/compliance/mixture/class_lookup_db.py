"""지식DB(HTODB)에서 CAS로 성분 정보를 조회해 build_components 의 class_lookup·tox_lookup 을 만든다.

repo 는 주입식이다. 쓰는 메서드는 셋: chemicals(cas=...) → {"rows":[{"chem_id", "molecular_weight"…}]},
classifications(chem_id) → {"rows":[…]}, toxicity(chem_id) → {"rows":[…]}.
htodb.repo 의 함수는 conn 을 첫 인자로 받으므로, 기본 repo(_DbRepo)가 읽기 전용 연결을 열어 감싼다.
샘플 CSV로 개발할 때는 htodb.csv_repo.CsvRepo 를 repo 로 넘긴다(설계서 43장).
조회 실패는 예외로 올리지 않고 빈 결과와 사유(.reason)로 돌려준다.
"""
import os

from ..htodb.parsers import parse_acute, to_float
from .rules_loader import lookup_class


class ClassRows(list):
    """class_rows 목록. 비어 있으면 reason 에 이유를 싣는다(build_components 가 gaps 에 옮긴다)."""

    def __init__(self, rows=(), reason=None):
        super().__init__(rows)
        self.reason = reason


class _DbRepo:
    """htodb.repo 를 repo.chemicals / repo.classifications 모양으로 감싼다. 호출마다 읽기 전용 연결을 연다."""

    def _run(self, fn, *args, **kw):
        import psycopg
        from psycopg.rows import dict_row

        from ..htodb import repo
        from ..htodb.config import pg_kwargs
        with psycopg.connect(**pg_kwargs("reader"), row_factory=dict_row, connect_timeout=2) as conn:
            return getattr(repo, fn)(conn, *args, **kw)

    def chemicals(self, **kw):
        return self._run("chemicals", **kw)

    def classifications(self, chem_id):
        return self._run("classifications", chem_id)

    def toxicity(self, chem_id):
        return self._run("toxicity", chem_id)

    def regulations(self, chem_id):
        return self._run("regulations", chem_id)

    def version(self):
        return self._run("versions")["knowledge_version"]


def _convert(db_rows) -> list[dict]:
    """tb_ghs_chem_class_map 행 → {"result_code","source",…}. hcode_seq 때문에 같은 (코드, 출처)가 여러 번 나오므로 한 번만 담는다."""
    out, seen = [], set()
    for r in db_rows:
        key = (r["class_result_code"], r["class_source_db_code"])
        if key in seen:
            continue
        seen.add(key)
        hit = lookup_class(key[0])  # (class_code, category, form, effect) 또는 None
        out.append({"result_code": key[0], "source": key[1], "class_code": hit[0] if hit else None,
                    "category": hit[1] if hit else None, "form": hit[2] if hit else None, "effect": hit[3] if hit else None})
    return out


def make_db_class_lookup(repo=None):
    """class_lookup(cas) → ClassRows. 같은 CAS는 이 callable 안에서 한 번만 조회한다."""
    cache: dict[str, ClassRows] = {}

    def lookup(cas):
        if cas in cache:
            return cache[cas]
        cache[cas] = _query(cas)
        return cache[cas]

    def _query(cas):
        if repo is None and os.environ.get("HTODB_SKIP") == "1":
            return ClassRows(reason="지식DB 조회 안 함(HTODB_SKIP=1)")
        try:
            r = repo or _DbRepo()
            chems = r.chemicals(cas=cas)["rows"]
            if not chems:
                return ClassRows(reason="지식DB에 등록되지 않은 CAS")
            rows = _convert([x for c in chems for x in r.classifications(c["chem_id"])["rows"]])
        except Exception as e:  # 접속 불가·권한·쿼리 오류 모두 중단하지 않고 사유로 남긴다
            return ClassRows(reason=f"지식DB 접속·조회 실패({type(e).__name__}: {e})")
        return ClassRows(rows, reason=None if rows else "지식DB에 분류결과 행 없음")

    return lookup


# ── 급성독성 값 (설계서 21장 ATE 수집 1단계 "TO21 독성DB 수치") ─────────────────────
# DIV_CODE → (ate_source 의 경로, 흡입 형태). 부록 55장: GHS0201~0205 급성독성
_ACUTE_DIV = {"GHS0201": ("oral", None), "GHS0202": ("dermal", None), "GHS0203": ("inhal", "gas"),
              "GHS0204": ("inhal", "vapour"), "GHS0205": ("inhal", "mist")}


def _tox_rows(db_rows, mw):
    """tb_eng_chem_toxicity_test_info 행 → ate_source 가 읽는 독성 행(route·form·op·value·unit).

    파싱은 htodb.parsers.parse_acute(D-21: 숫자 컬럼 우선, 없으면 문장)를 그대로 쓴다.
    부호를 정할 수 없거나 단위가 맞지 않는 행(sign "?")과 정성 문장(None)은 뺀다.
    범위값은 하한을 value, 상한을 value_hi 로 둔다(D-12: 계산은 최솟값).
    """
    out = []
    for r in db_rows:
        hit = _ACUTE_DIV.get(r.get("div_code"))
        if hit is None:
            continue
        p = parse_acute(r.get("primary_value_text"), r.get("primary_value"), r["div_code"], mw)
        if p is None or p["sign"] == "?":
            continue
        route, form = hit
        row = {"route": route, "op": p["sign"], "value": p["value"], "unit": p["unit"], "source": "TO21 독성DB",
               "div_code": r["div_code"], "species": p["species"], "basis": p["basis"],
               "text": r.get("primary_value_text")}
        if form:
            row["form"] = form
        if p.get("value_max") is not None:
            row["op_hi"], row["value_hi"] = "<=", p["value_max"]
        out.append(row)
    return out


def make_db_tox_lookup(repo=None):
    """tox_lookup(cas) → ClassRows(독성 행 목록). 비어 있으면 .reason 에 이유. 같은 CAS는 한 번만 조회한다."""
    cache: dict[str, ClassRows] = {}

    def lookup(cas):
        if cas not in cache:
            cache[cas] = _query(cas)
        return cache[cas]

    def _query(cas):
        if repo is None and os.environ.get("HTODB_SKIP") == "1":
            return ClassRows(reason="지식DB 조회 안 함(HTODB_SKIP=1)")
        try:
            r = repo or _DbRepo()
            chems = r.chemicals(cas=cas)["rows"]
            if not chems:
                return ClassRows(reason="지식DB에 등록되지 않은 CAS")
            rows = []
            for c in chems:
                rows += _tox_rows(r.toxicity(c["chem_id"])["rows"], to_float(c.get("molecular_weight")))
        except Exception as e:  # 접속 불가·권한·쿼리 오류 모두 중단하지 않고 사유로 남긴다
            return ClassRows(reason=f"지식DB 접속·조회 실패({type(e).__name__}: {e})")
        return ClassRows(rows, reason=None if rows else "지식DB에 쓸 수 있는 급성독성 수치 없음")

    return lookup


# ── 성분 정보: 분자량 · 수생 M 계수 (11/02 F, 설계서 36·56장 D-07) ─────────────────────
def make_db_info_lookup(repo=None):
    """info_lookup(cas) → {"mw", "m", "m_basis", "aquatic", "reason"}. 같은 CAS는 한 번만 조회한다.

    mw: tb_eng_chem_master_info.molecular_weight. m: {ENV_AQ_ACUTE: M 또는 None, ENV_AQ_CHRONIC: …}(m_factor.py).
    조회 실패는 예외로 올리지 않고 reason 에 남기며, 이때 mw·m 은 비운다.
    """
    from .m_factor import aquatic_values, m_factors

    cache: dict[str, dict] = {}

    def lookup(cas):
        if cas not in cache:
            cache[cas] = _query(cas)
        return cache[cas]

    def _query(cas):
        empty = {"mw": None, "m": {}, "m_basis": {}, "aquatic": None}
        if repo is None and os.environ.get("HTODB_SKIP") == "1":
            return {**empty, "reason": "지식DB 조회 안 함(HTODB_SKIP=1)"}
        try:
            r = repo or _DbRepo()
            chems = r.chemicals(cas=cas)["rows"]
            if not chems:
                return {**empty, "reason": "지식DB에 등록되지 않은 CAS"}
            mws = [v for v in (to_float(c.get("molecular_weight")) for c in chems) if v]
            tox = [x for c in chems for x in r.toxicity(c["chem_id"])["rows"]]
        except Exception as e:  # 접속 불가·권한·쿼리 오류 모두 중단하지 않고 사유로 남긴다
            return {**empty, "reason": f"지식DB 접속·조회 실패({type(e).__name__}: {e})"}
        vals = aquatic_values(tox)
        ms = m_factors(vals)
        return {"mw": mws[0] if mws else None, "m": {k: v["m"] for k, v in ms.items()},
                "m_basis": {k: v["basis"] for k, v in ms.items()}, "aquatic": vals, "reason": None}

    return lookup
