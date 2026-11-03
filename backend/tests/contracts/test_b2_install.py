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


def test_B를_깐_뒤에도_A_실행기를_다시_돌릴_수_있다(empty_db):
    b2 = _module("b2_migrate")
    assert _a_runner(empty_db)[0] == 0
    b2.migrate(empty_db)
    code, out = _a_runner(empty_db)
    assert code == 0, out
    with psycopg.connect(**{**pg_kwargs("admin"), "dbname": empty_db}) as c:
        can = c.execute("SELECT has_table_privilege('judge_writer', 'extract.handoff', 'SELECT'),"
                        " has_table_privilege('judge_writer', 'extract.handoff', 'UPDATE')").fetchone()
    assert can == (True, False)


def test_A_설치_전에_B를_돌리면_안내하고_멈춘다(empty_db):
    with pytest.raises(SystemExit, match="A 설치"):
        _module("b2_migrate").migrate(empty_db)
