"""팀 DB 설치 순서: A 실행기(TEAM_SETUP 6절) → B 마이그레이션 → A 실행기를 다시 돌려도 멈추지 않아야 한다.

B가 extract에 직접 GRANT하면 A 실행기가 "스키마가 이력과 다르다"며 멈췄다 (2026-11-03). 빈 시험 DB를 만들고 지운다.
"""
import importlib.util
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest

from msds.compliance.htodb.config import pg_address, pg_kwargs, setting

BACKEND = Path(__file__).resolve().parents[2]


def _module(name):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def empty_db():
    try:
        admin = pg_kwargs("admin")
        conn = psycopg.connect(**admin, autocommit=True, connect_timeout=3)
    except Exception as e:  # PostgreSQL이 없는 환경
        pytest.skip(f"PostgreSQL 없음: {type(e).__name__}")
    name = f"b_install_{uuid.uuid4().hex[:8]}"
    with conn:
        conn.execute(f"CREATE DATABASE {name}")
        for role in ("to21_extract", "to21_judge"):
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                conn.execute(f"CREATE ROLE {role} NOLOGIN NOINHERIT")
    yield name
    with psycopg.connect(**admin, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def _a_runner(db):
    env = {**os.environ, "PGPASSWORD": setting("HTODB_PG_PASSWORD"),
           "TO21_ERD_DATABASE_URL": f"host={pg_address()['host']} port={pg_address()['port']} dbname={db} user=kdb"}
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "apply_erd_migrations.py"), "--extract-role", "to21_extract",
                        "--judge-role", "to21_judge"], env=env, capture_output=True, text=True, cwd=BACKEND)
    return r.returncode, r.stdout + r.stderr


def _privileges(db):
    """judge_writer가 extract에서 가진 권한 전부 (표마다 SELECT·INSERT·UPDATE·DELETE, 스키마 CREATE)."""
    with psycopg.connect(**{**pg_kwargs("admin"), "dbname": db}) as c:
        tables = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'extract' ORDER BY 1")]
        got = {(t, p) for t in tables for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
               if c.execute("SELECT has_table_privilege('judge_writer', %s, %s)", (f"extract.{t}", p)).fetchone()[0]}
        if c.execute("SELECT has_schema_privilege('judge_writer', 'extract', 'CREATE')").fetchone()[0]:
            got.add(("extract", "CREATE"))
        direct = c.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a "
                           "WHERE n.nspname = 'extract' AND a.grantee = 'judge_writer'::regrole").fetchone()[0]
    return got, direct


def _old_b2_grants(db):
    """예전 b2_002가 하던 직접 권한."""
    with psycopg.connect(**{**pg_kwargs("admin"), "dbname": db}, autocommit=True) as c:
        c.execute("GRANT USAGE ON SCHEMA extract TO judge_writer; GRANT SELECT ON extract.handoff TO judge_writer")


def test_B를_깐_뒤에도_A_실행기를_다시_돌릴_수_있다(empty_db):
    b2 = _module("b2_migrate")
    assert _a_runner(empty_db)[0] == 0
    b2.migrate(empty_db)
    b2.migrate(empty_db)  # 두 번 돌려도 된다
    code, out = _a_runner(empty_db)
    assert code == 0, out
    assert _privileges(empty_db) == ({("handoff", "SELECT")}, 0)  # 넘김 읽기만, 직접 권한 없이 그룹으로
    from msds.judge.service import writer_kwargs
    with psycopg.connect(**writer_kwargs(empty_db)) as c:
        c.execute("SELECT count(*) FROM extract.handoff")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT count(*) FROM extract.jobs")


def test_예전_직접_권한이_있는_DB는_B가_되돌려_A가_다시_돈다(empty_db):
    b2 = _module("b2_migrate")
    assert _a_runner(empty_db)[0] == 0
    b2.migrate(empty_db)
    _old_b2_grants(empty_db)
    assert _a_runner(empty_db)[0] == 1  # 예전 방식이면 A가 멈춘다
    b2.migrate(empty_db)
    assert _privileges(empty_db) == ({("handoff", "SELECT")}, 0)
    assert _a_runner(empty_db)[0] == 0


def test_A_권한_단계가_안_끝났으면_B는_권한을_주지_않고_멈춘다(empty_db):
    # A 실행기가 0007에서 멈춘 상태: 표는 있지만 to21_judge 권한이 없다
    assert _a_runner(empty_db)[0] == 0
    with psycopg.connect(**{**pg_kwargs("admin"), "dbname": empty_db}, autocommit=True) as c:
        c.execute("REVOKE SELECT ON extract.handoff FROM to21_judge")
    with pytest.raises(SystemExit, match="0007"):
        _module("b2_migrate").migrate(empty_db)
    assert _privileges(empty_db)[1] == 0


def test_A_설치_전에_B를_돌리면_안내하고_멈춘다(empty_db):
    with pytest.raises(SystemExit, match="A 설치"):
        _module("b2_migrate").migrate(empty_db)


def test_없는_DB는_개발용이_아니면_만들지_않는다():
    name = f"b_install_none_{uuid.uuid4().hex[:6]}"
    try:
        with pytest.raises(SystemExit, match="없음"):
            _module("b2_migrate").migrate(name)
        with psycopg.connect(**pg_kwargs("admin")) as c:
            assert not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
    except psycopg.OperationalError as e:
        pytest.skip(f"PostgreSQL 없음: {e}")


def test_개발용은_A_없이_대역_표에_직접_권한을_준다(empty_db):
    _module("b2_migrate").migrate(empty_db, dev=True)
    assert _privileges(empty_db)[0] == {("handoff", "SELECT")}
