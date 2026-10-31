"""지식DB(HTODB)에서 CAS로 분류결과코드를 조회해 build_components 의 class_lookup 을 만든다.

repo 는 주입식이다. 쓰는 메서드는 둘: chemicals(cas=...) → {"rows":[{"chem_id"}]}, classifications(chem_id) → {"rows":[…]}.
htodb.repo 의 함수는 conn 을 첫 인자로 받으므로, 기본 repo(_DbRepo)가 읽기 전용 연결을 열어 감싼다.
조회 실패는 예외로 올리지 않고 빈 결과와 사유(.reason)로 돌려준다.
"""
import os

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
