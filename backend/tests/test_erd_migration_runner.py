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
        assert runner.apply(conn, migrations, role_a, role_b) == 4
        assert runner.apply(conn, migrations, role_a, role_b) == 0
        rows = conn.execute("SELECT name, sha256 FROM to21_erd_control.migration_history").fetchall()
        assert {name: digest for name, digest in rows} == {m.name: m.sha256 for m in migrations}
        assert conn.execute("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='extract'").fetchone()[0] == 5
        assert conn.execute("SELECT pg_catalog.to_regnamespace('judge') IS NULL").fetchone()[0]


@pytest.mark.parametrize("b_first", [True, False])
def test_runner_preserves_independent_b_schema_before_and_after_a_install(disposable_database, b_first):
    test_dsn, role_a, role_b = disposable_database
    migrations = runner.load_migrations()
    with _connection(test_dsn) as conn:
        if not b_first:
            assert runner.apply(conn, migrations, role_a, role_b) == 4
        # A minimal B-owned object exercises coexistence without prescribing B2's schema.
        conn.execute(sql.SQL("CREATE SCHEMA judge AUTHORIZATION {}").format(sql.Identifier(role_b)))
        conn.execute("CREATE TABLE judge.judgment (id integer PRIMARY KEY, payload_json jsonb NOT NULL)")
        conn.execute("INSERT INTO judge.judgment VALUES (1, '{}')")
        conn.execute(sql.SQL("GRANT SELECT, INSERT ON judge.judgment TO {}").format(sql.Identifier(role_b)))
        assert runner.apply(conn, migrations, role_a, role_b) == (4 if b_first else 0)
        before = runner.schema_fingerprint(conn)
        conn.execute("ALTER TABLE judge.judgment ADD COLUMN note text")
        conn.execute("UPDATE judge.judgment SET note='B migration preserved'")
        assert runner.schema_fingerprint(conn) == before
        assert runner.apply(conn, migrations, role_a, role_b) == 0
        assert conn.execute("SELECT id, payload_json, note FROM judge.judgment").fetchall() == [
            (1, {}, "B migration preserved"),
        ]
        assert conn.execute("SELECT pg_catalog.pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace "
                            "WHERE nspname='judge'").fetchone()[0] == role_b
        assert conn.execute("SELECT has_table_privilege(%s, 'judge.judgment', 'INSERT')",
                            (role_b,)).fetchone()[0]
        assert conn.execute("SELECT has_table_privilege(%s, 'extract.handoff', 'SELECT'), "
                            "has_table_privilege(%s, 'extract.handoff', 'INSERT')",
                            (role_b, role_b)).fetchone() == (True, False)


def test_runner_preserves_and_rejects_legacy_b2_history(disposable_database):
    test_dsn, role_a, role_b = disposable_database
    migrations = runner.load_migrations()
    with _connection(test_dsn) as conn:
        assert runner.apply(conn, migrations, role_a, role_b) == 4
        conn.execute("""INSERT INTO to21_erd_control.migration_history
                            (name, sha256, schema_fingerprint)
                        VALUES ('b2_0004_judge_runs_versions.sql', %s, %s)""",
                     ("a" * 64, runner.schema_fingerprint(conn)))
        before = conn.execute("SELECT * FROM to21_erd_control.migration_history ORDER BY name").fetchall()
        with pytest.raises(runner.MigrationError, match="알 수 없는 마이그레이션"):
            runner.apply(conn, migrations, role_a, role_b)
        assert conn.execute("SELECT * FROM to21_erd_control.migration_history ORDER BY name").fetchall() == before


def test_runner_rejects_changed_file_checksum(disposable_database, tmp_path):
    test_dsn, role_a, role_b = disposable_database
    originals = runner.load_migrations()
    with _connection(test_dsn) as conn:
        assert runner.apply(conn, originals, role_a, role_b) == 4
        for name in runner.MIGRATION_FILES:
            shutil.copyfile(runner.MIGRATIONS_DIR / name, tmp_path / name)
        changed = tmp_path / runner.MIGRATION_FILES[0]
        # The comment is legal after COMMIT but still changes the file checksum.
        with changed.open("a", encoding="utf-8") as f:
            f.write("\n-- changed after application\n")
        altered = runner.load_migrations(tmp_path)
        with pytest.raises(runner.MigrationError, match="체크섬"):
            runner.apply(conn, altered, role_a, role_b)
        assert conn.execute("SELECT count(*) FROM to21_erd_control.migration_history").fetchone()[0] == 4


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
        assert runner.apply(conn, originals, role_a, role_b) == 2
        assert runner.apply(conn, originals, role_a, role_b) == 0
