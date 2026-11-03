#!/usr/bin/env python3
"""Apply the extract/judge ERD migrations to one explicitly selected database.

Set TO21_ERD_DATABASE_URL and provide --extract-role and --judge-role (or
TO21_ERD_EXTRACT_ROLE and TO21_ERD_JUDGE_ROLE). Roles must already exist.
Only schemas owned by this migration set are managed; knowledge DB is untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from dataclasses import dataclass

import psycopg
from psycopg import sql

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATION_FILES = (
    "a1_0001_extract_jobs.sql",
    "a2_0002_extract_results_reviews_artifacts.sql",
    "a2_0003_extract_handoff.sql",
    "b2_0004_judge_runs_versions.sql",
    "b2_0005_judge_explanations_reviews.sql",
    "b2_0006_judge_snapshots_artifacts.sql",
    "0007_service_grants.sql",
)
GRANTS_FILE = MIGRATION_FILES[-1]
# A stable, application-specific, signed 64-bit session advisory lock key.
LOCK_KEY = 0x544F32314D534453
ROLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$", re.ASCII)
BEGIN_LINE = re.compile(r"(?im)^[ \t]*BEGIN[ \t]*;[ \t]*(?:\r?\n|$)")
COMMIT_LINE = re.compile(r"(?im)^[ \t]*COMMIT[ \t]*;[ \t]*(?:\r?\n|$)")


class MigrationError(Exception):
    """An anticipated configuration, history or schema mismatch."""


@dataclass(frozen=True)
class Migration:
    name: str
    sha256: str
    body: str


def _only_line_comments_and_whitespace(value: str) -> bool:
    return all(not line.strip() or line.lstrip().startswith("--") for line in value.splitlines())


def strip_transaction_wrapper(source: str) -> str:
    """Strip only the outer BEGIN and COMMIT lines; keep PL/pgSQL intact."""
    begins = list(BEGIN_LINE.finditer(source))
    commits = list(COMMIT_LINE.finditer(source))
    if not begins or not commits:
        raise MigrationError("SQL 파일에 외부 BEGIN/COMMIT이 없습니다")
    first, last = begins[0], commits[-1]
    if first.end() >= last.start() or not _only_line_comments_and_whitespace(source[: first.start()]):
        raise MigrationError("SQL 파일의 외부 BEGIN 위치가 올바르지 않습니다")
    if not _only_line_comments_and_whitespace(source[last.end() :]):
        raise MigrationError("SQL 파일의 외부 COMMIT 뒤에 실행 구문이 있습니다")
    return source[: first.start()] + source[first.end() : last.start()] + source[last.end() :]


def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    result = []
    for name in MIGRATION_FILES:
        path = directory / name
        try:
            data = path.read_bytes()
            source = data.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise MigrationError(f"마이그레이션 파일을 읽을 수 없습니다: {name}") from error
        try:
            body = strip_transaction_wrapper(source)
        except MigrationError as error:
            raise MigrationError(f"{name}: {error}") from error
        result.append(Migration(name, hashlib.sha256(data).hexdigest(), body))
    return result


def render_grants(body: str, extract_role: str, judge_role: str, conn: psycopg.Connection) -> str:
    """Expand only the two psql identifier placeholders with SQL-quoted names."""
    replacements = {
        ':"extract_role"': sql.Identifier(extract_role).as_string(conn),
        ':"judge_role"': sql.Identifier(judge_role).as_string(conn),
    }
    for placeholder, value in replacements.items():
        if placeholder not in body:
            raise MigrationError(f"권한 SQL에 필요한 역할 변수가 없습니다: {placeholder}")
        body = body.replace(placeholder, value)
    if re.search(r':"[A-Za-z_][A-Za-z0-9_]*"', body):
        raise MigrationError("권한 SQL에 알 수 없는 psql 역할 변수가 있습니다")
    return body


def _require_roles(conn: psycopg.Connection, extract_role: str, judge_role: str) -> None:
    found = {row[0]: row[1] for row in conn.execute(
        "SELECT rolname, rolsuper FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
        ([extract_role, judge_role],),
    )}
    missing = {extract_role, judge_role} - found.keys()
    if missing:
        raise MigrationError("요청한 DB 역할이 없습니다: " + ", ".join(sorted(missing)))
    if any(found.values()):
        raise MigrationError("서비스 역할에 슈퍼유저를 사용할 수 없습니다")
    for role in (extract_role, judge_role):
        broad_read, broad_write, db_owner = conn.execute("""
            SELECT pg_catalog.pg_has_role(%s, 'pg_read_all_data', 'MEMBER'),
                   pg_catalog.pg_has_role(%s, 'pg_write_all_data', 'MEMBER'),
                   EXISTS (
                       SELECT 1 FROM pg_catalog.pg_database d
                       JOIN pg_catalog.pg_roles r ON r.oid = d.datdba
                       WHERE d.datname = pg_catalog.current_database() AND r.rolname = %s
                   )
        """, (role, role, role)).fetchone()
        if broad_read or broad_write or db_owner:
            raise MigrationError(f"서비스 역할에 광역 DB 권한 또는 DB 소유권이 있습니다: {role}")
    related = conn.execute("""
        SELECT pg_catalog.pg_has_role(%s, %s, 'MEMBER')
            OR pg_catalog.pg_has_role(%s, %s, 'MEMBER')
    """, (extract_role, judge_role, judge_role, extract_role)).fetchone()[0]
    if related:
        raise MigrationError("추출과 판정 역할이 서로의 멤버입니다")


def _verify_service_permissions(conn: psycopg.Connection, extract_role: str, judge_role: str) -> None:
    """Fail atomically if inherited or PUBLIC grants break the A/B boundary."""
    a_judge, b_extract_create, b_handoff_read, b_handoff_insert, b_handoff_update, b_handoff_delete = conn.execute("""
        SELECT pg_catalog.has_schema_privilege(%s, 'judge', 'USAGE'),
               pg_catalog.has_schema_privilege(%s, 'extract', 'CREATE'),
               pg_catalog.has_table_privilege(%s, 'extract.handoff', 'SELECT'),
               pg_catalog.has_table_privilege(%s, 'extract.handoff', 'INSERT'),
               pg_catalog.has_table_privilege(%s, 'extract.handoff', 'UPDATE'),
               pg_catalog.has_table_privilege(%s, 'extract.handoff', 'DELETE')
    """, (extract_role, judge_role, judge_role, judge_role, judge_role, judge_role)).fetchone()
    if a_judge or b_extract_create or not b_handoff_read or b_handoff_insert or b_handoff_update or b_handoff_delete:
        raise MigrationError("A/B 스키마 및 handoff 접근 권한이 설계 경계와 다릅니다")
    excess = conn.execute("""
        SELECT c.relname FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='extract' AND c.relkind IN ('r','p') AND c.relname <> 'handoff'
          AND (pg_catalog.has_table_privilege(%s,c.oid,'SELECT')
            OR pg_catalog.has_table_privilege(%s,c.oid,'INSERT')
            OR pg_catalog.has_table_privilege(%s,c.oid,'UPDATE')
            OR pg_catalog.has_table_privilege(%s,c.oid,'DELETE'))
        ORDER BY c.relname
    """, (judge_role, judge_role, judge_role, judge_role)).fetchall()
    if excess:
        raise MigrationError("판정 역할이 handoff 외 추출 테이블에 접근할 수 있습니다")


def _has_service_objects(conn: psycopg.Connection) -> bool:
    row = conn.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('extract', 'judge')
              AND c.relkind IN ('r','p','v','m','f','S')
        ) OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_proc p
            JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname IN ('extract', 'judge')
        )
    """).fetchone()
    return bool(row[0])


def schema_fingerprint(conn: psycopg.Connection) -> str:
    """Fingerprint definitions and ACLs, not rows or sequence counter values."""
    queries = (
        """SELECT n.nspname, n.nspowner::text, n.nspacl::text
           FROM pg_catalog.pg_namespace n WHERE n.nspname IN ('extract','judge')
           ORDER BY n.nspname""",
        """SELECT n.nspname, c.relname, c.relkind::text, c.relowner::text, c.relacl::text
           FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname IN ('extract','judge') AND c.relkind IN ('r','p','v','m','f','S')
           ORDER BY n.nspname, c.relname""",
        """SELECT n.nspname, c.relname, a.attnum, a.attname,
                  pg_catalog.format_type(a.atttypid,a.atttypmod), a.attnotnull,
                  a.attidentity::text, a.attgenerated::text, pg_catalog.pg_get_expr(d.adbin,d.adrelid)
           FROM pg_catalog.pg_attribute a
           JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
           JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
           LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
           WHERE n.nspname IN ('extract','judge') AND c.relkind IN ('r','p','v','m','f')
             AND a.attnum>0 AND NOT a.attisdropped
           ORDER BY n.nspname,c.relname,a.attnum""",
        """SELECT n.nspname,c.relname,k.conname,pg_catalog.pg_get_constraintdef(k.oid,true)
           FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
           JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname IN ('extract','judge') ORDER BY n.nspname,c.relname,k.conname""",
        """SELECT n.nspname,t.relname,i.relname,pg_catalog.pg_get_indexdef(i.oid)
           FROM pg_catalog.pg_index x JOIN pg_catalog.pg_class i ON i.oid=x.indexrelid
           JOIN pg_catalog.pg_class t ON t.oid=x.indrelid
           JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
           WHERE n.nspname IN ('extract','judge') ORDER BY n.nspname,t.relname,i.relname""",
        """SELECT n.nspname,c.relname,t.tgname,pg_catalog.pg_get_triggerdef(t.oid,true),t.tgenabled::text
           FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
           JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname IN ('extract','judge') AND NOT t.tgisinternal
           ORDER BY n.nspname,c.relname,t.tgname""",
        """SELECT n.nspname,p.proname,pg_catalog.pg_get_function_identity_arguments(p.oid),
                  pg_catalog.pg_get_functiondef(p.oid),p.proowner::text,p.proacl::text
           FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname IN ('extract','judge') AND p.prokind='f'
           ORDER BY n.nspname,p.proname,pg_catalog.pg_get_function_identity_arguments(p.oid)""",
    )
    snapshot = [conn.execute(query).fetchall() for query in queries]
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_control_table(conn: psycopg.Connection) -> None:
    columns = conn.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='to21_erd_control' AND table_name='migration_history'
        ORDER BY ordinal_position
    """).fetchall()
    expected = [
        ("name", "text", "NO"), ("sha256", "text", "NO"),
        ("schema_fingerprint", "text", "NO"), ("extract_role", "text", "YES"),
        ("judge_role", "text", "YES"), ("applied_at", "timestamp with time zone", "NO"),
    ]
    if columns != expected:
        raise MigrationError("기존 마이그레이션 이력 테이블의 열 정의가 다릅니다")
    pk = conn.execute("""
        SELECT pg_catalog.pg_get_constraintdef(c.oid)
        FROM pg_catalog.pg_constraint c
        WHERE c.conrelid='to21_erd_control.migration_history'::regclass AND c.contype='p'
    """).fetchall()
    if pk != [("PRIMARY KEY (name)",)]:
        raise MigrationError("기존 마이그레이션 이력 테이블의 기본 키가 다릅니다")


def _bootstrap(conn: psycopg.Connection) -> None:
    with conn.transaction():
        existing = conn.execute("SELECT pg_catalog.to_regclass('to21_erd_control.migration_history')").fetchone()[0]
        if existing is None and _has_service_objects(conn):
            raise MigrationError("기존 extract/judge 객체에 관리 이력이 없습니다. 기존 DB 정의를 먼저 확인하세요")
        conn.execute("CREATE SCHEMA IF NOT EXISTS extract")
        conn.execute("CREATE SCHEMA IF NOT EXISTS judge")
        conn.execute("CREATE SCHEMA IF NOT EXISTS to21_erd_control")
        if existing is None:
            conn.execute("""
                CREATE TABLE to21_erd_control.migration_history (
                    name TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
                    schema_fingerprint TEXT NOT NULL CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$'),
                    extract_role TEXT,
                    judge_role TEXT,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
        _verify_control_table(conn)
        count = conn.execute("SELECT count(*) FROM to21_erd_control.migration_history").fetchone()[0]
        if count == 0 and _has_service_objects(conn):
            raise MigrationError("적용 이력은 비어 있지만 기존 extract/judge 객체가 있습니다")


def _verify_history(conn: psycopg.Connection, migrations: list[Migration], extract_role: str, judge_role: str) -> int:
    rows = conn.execute("""
        SELECT name, sha256, schema_fingerprint, extract_role, judge_role
        FROM to21_erd_control.migration_history
    """).fetchall()
    history = {row[0]: row for row in rows}
    known = {m.name for m in migrations}
    if set(history) - known:
        raise MigrationError("알 수 없는 마이그레이션 이력이 있습니다")
    names = [m.name for m in migrations]
    if set(history) != set(names[: len(history)]):
        raise MigrationError("마이그레이션 이력 순서가 불완전합니다")
    for migration in migrations[: len(history)]:
        row = history[migration.name]
        if row[1] != migration.sha256:
            raise MigrationError(f"적용된 마이그레이션의 체크섬이 바뀌었습니다: {migration.name}")
        if migration.name == GRANTS_FILE and (row[3], row[4]) != (extract_role, judge_role):
            raise MigrationError("이미 적용한 권한 역할과 요청한 역할이 다릅니다")
    if history:
        last = history[names[len(history) - 1]]
        if last[2] != schema_fingerprint(conn):
            raise MigrationError("현재 extract/judge 스키마가 마지막 적용 이력과 다릅니다")
        if GRANTS_FILE in history:
            _verify_service_permissions(conn, extract_role, judge_role)
    return len(history)


def apply(conn: psycopg.Connection, migrations: list[Migration], extract_role: str, judge_role: str) -> int:
    """Apply each migration and its history entry in one transaction."""
    _require_roles(conn, extract_role, judge_role)
    locked = conn.execute("SELECT pg_catalog.pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]
    if not locked:
        raise MigrationError("다른 마이그레이션이 실행 중입니다")
    try:
        _bootstrap(conn)
        applied = _verify_history(conn, migrations, extract_role, judge_role)
        for migration in migrations[applied:]:
            body = migration.body
            if migration.name == GRANTS_FILE:
                body = render_grants(body, extract_role, judge_role, conn)
            elif ':"extract_role"' in body or ':"judge_role"' in body:
                raise MigrationError(f"예상하지 못한 psql 역할 변수: {migration.name}")
            print(f"적용 중: {migration.name}", flush=True)
            with conn.transaction():
                # No bound values: Psycopg uses the simple protocol and sends the
                # complete multi-statement script without splitting PL/pgSQL bodies.
                conn.execute(body, prepare=False)
                if migration.name == GRANTS_FILE:
                    _verify_service_permissions(conn, extract_role, judge_role)
                fingerprint = schema_fingerprint(conn)
                roles = (extract_role, judge_role) if migration.name == GRANTS_FILE else (None, None)
                conn.execute("""
                    INSERT INTO to21_erd_control.migration_history
                        (name, sha256, schema_fingerprint, extract_role, judge_role)
                    VALUES (%s, %s, %s, %s, %s)
                """, (migration.name, migration.sha256, fingerprint, *roles))
            print(f"적용: {migration.name}")
        return len(migrations) - applied
    finally:
        conn.execute("SELECT pg_catalog.pg_advisory_unlock(%s)", (LOCK_KEY,))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-role", default=os.environ.get("TO21_ERD_EXTRACT_ROLE"))
    parser.add_argument("--judge-role", default=os.environ.get("TO21_ERD_JUDGE_ROLE"))
    args = parser.parse_args(argv)
    dsn = os.environ.get("TO21_ERD_DATABASE_URL")
    if not dsn:
        parser.error("TO21_ERD_DATABASE_URL 환경 변수가 필요합니다")
    if not args.extract_role or not args.judge_role:
        parser.error("--extract-role과 --judge-role 또는 해당 환경 변수가 필요합니다")
    if not ROLE_PATTERN.fullmatch(args.extract_role) or not ROLE_PATTERN.fullmatch(args.judge_role):
        parser.error("역할명은 영문·숫자·밑줄·$로 구성된 63자 이하 식별자여야 합니다")
    if args.extract_role == args.judge_role:
        parser.error("추출과 판정의 DB 역할은 서로 달라야 합니다")
    try:
        migrations = load_migrations()
        # A session lock spans the independent migration transactions. Autocommit
        # ensures transaction() is a top-level transaction, not a savepoint.
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("SET search_path = pg_catalog")
            count = apply(conn, migrations, args.extract_role, args.judge_role)
        if not count:
            print("변경 없음: 모든 마이그레이션의 체크섬과 스키마가 일치합니다")
        return 0
    except MigrationError as error:
        print(f"마이그레이션 중단: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        # Connection exceptions may include credentials; do not print the DSN or
        # raw exception. SQLSTATE and exception type suffice to locate the class.
        print(f"DB 연결 또는 마이그레이션 실패: {type(error).__name__} (SQLSTATE {error.sqlstate or '없음'})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
