"""Run the ERD migration runner against a new, disposable PostgreSQL database.

Requires TO21_ERD_TEST_DATABASE_URL with CREATEDB and CREATEROLE privileges.
Each test creates UUID-named database and NOLOGIN roles; it never points the
runner at the database in the supplied DSN. Only these fresh objects are
removed in teardown. No Docker/container or shared service schemas are touched.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import apply_erd_migrations as runner  # noqa: E402


@pytest.fixture
def disposable_database():
    dsn = os.environ.get("TO21_ERD_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set TO21_ERD_TEST_DATABASE_URL to an admin connection for disposable PostgreSQL tests")
    suffix = uuid4().hex
    db_name = f"erd_test_{suffix}"
    role_a, role_b = f"erd_extract_{suffix}", f"erd_judge_{suffix}"
    # Exact generated names guard every destructive cleanup below.
    assert re.fullmatch(r"erd_test_[0-9a-f]{32}", db_name)
    assert re.fullmatch(r"erd_extract_[0-9a-f]{32}", role_a)
    assert re.fullmatch(r"erd_judge_[0-9a-f]{32}", role_b)
    made_roles = []
    made_db = False
    with psycopg.connect(dsn, autocommit=True) as admin:
        superuser, createdb, createrole = admin.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_catalog.pg_roles WHERE rolname=current_user"
        ).fetchone()
        if not (superuser or createdb) or not (superuser or createrole):
            pytest.skip("Disposable runner tests require CREATEDB and CREATEROLE")
        try:
            for role in (role_a, role_b):
                admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(role)))
                made_roles.append(role)
            admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'")
                          .format(sql.Identifier(db_name)))
            made_db = True
            # Retain the explicitly supplied server/auth settings but force all
            # runner operations to the fresh, generated test database.
            test_dsn = make_conninfo(dsn, dbname=db_name)
            yield test_dsn, role_a, role_b
        finally:
            if made_db:
                admin.execute(sql.SQL("DROP DATABASE {} ").format(sql.Identifier(db_name)))
            for role in reversed(made_roles):
                admin.execute(sql.SQL("DROP ROLE {} ").format(sql.Identifier(role)))


def _connection(test_dsn):
    conn = psycopg.connect(test_dsn, autocommit=True)
    conn.execute("SET search_path = pg_catalog")
    return conn


def test_runner_applies_once_then_reapplies_without_changes(disposable_database):
    test_dsn, role_a, role_b = disposable_database
    migrations = runner.load_migrations()
    with _connection(test_dsn) as conn:
        assert runner.apply(conn, migrations, role_a, role_b) == 7
        assert runner.apply(conn, migrations, role_a, role_b) == 0
        rows = conn.execute("SELECT name, sha256 FROM to21_erd_control.migration_history").fetchall()
        assert {name: digest for name, digest in rows} == {m.name: m.sha256 for m in migrations}
        assert conn.execute("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname IN ('extract', 'judge')").fetchone()[0] == 11


def test_runner_rejects_changed_file_checksum(disposable_database, tmp_path):
    test_dsn, role_a, role_b = disposable_database
    originals = runner.load_migrations()
    with _connection(test_dsn) as conn:
        assert runner.apply(conn, originals, role_a, role_b) == 7
        for name in runner.MIGRATION_FILES:
            shutil.copyfile(runner.MIGRATIONS_DIR / name, tmp_path / name)
        changed = tmp_path / runner.MIGRATION_FILES[0]
        # The comment is legal after COMMIT but still changes the file checksum.
        with changed.open("a", encoding="utf-8") as f:
            f.write("\n-- changed after application\n")
        altered = runner.load_migrations(tmp_path)
        with pytest.raises(runner.MigrationError, match="체크섬"):
            runner.apply(conn, altered, role_a, role_b)
        assert conn.execute("SELECT count(*) FROM to21_erd_control.migration_history").fetchone()[0] == 7


def test_runner_refuses_unmanaged_existing_service_table(disposable_database):
    test_dsn, role_a, role_b = disposable_database
    with _connection(test_dsn) as conn:
        conn.execute("CREATE SCHEMA extract")
        conn.execute("CREATE TABLE extract.unmanaged (id integer PRIMARY KEY)")
        with pytest.raises(runner.MigrationError, match="관리 이력"):
            runner.apply(conn, runner.load_migrations(), role_a, role_b)
        assert conn.execute("SELECT pg_catalog.to_regclass('extract.unmanaged') IS NOT NULL").fetchone()[0]
        assert conn.execute("SELECT pg_catalog.to_regclass('extract.jobs') IS NULL").fetchone()[0]
        assert conn.execute("SELECT pg_catalog.to_regclass('to21_erd_control.migration_history') IS NULL").fetchone()[0]


def test_runner_rolls_back_failed_file_and_can_resume(disposable_database):
    test_dsn, role_a, role_b = disposable_database
    originals = runner.load_migrations()
    broken = list(originals)
    # Inject an error into one migration in memory, not into repository files.
    body = "CREATE TABLE extract.should_rollback (id integer); SELECT nonexistent_erd_test_function();"
    broken[2] = runner.Migration(broken[2].name, hashlib.sha256(body.encode()).hexdigest(), body)
    with _connection(test_dsn) as conn:
        with pytest.raises(psycopg.errors.UndefinedFunction):
            runner.apply(conn, broken, role_a, role_b)
        # Earlier complete files remain applied; the failing file and its
        # history row are both absent, so the real file is safe to retry.
        assert conn.execute("SELECT pg_catalog.to_regclass('extract.should_rollback') IS NULL").fetchone()[0]
        assert conn.execute("SELECT pg_catalog.to_regclass('extract.handoff') IS NULL").fetchone()[0]
        assert conn.execute("SELECT count(*) FROM to21_erd_control.migration_history").fetchone()[0] == 2
        assert runner.apply(conn, originals, role_a, role_b) == 5
        assert runner.apply(conn, originals, role_a, role_b) == 0
