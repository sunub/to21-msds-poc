"""judge 스키마를 만든다. 관리자 계정으로 migrations/b2_*.sql 을 차례로 돌리고 judge_writer 비밀번호를 맞춘다.

    python scripts/b2_migrate.py --database msds_service   # 서비스 DB (A의 apply_erd_migrations.py 뒤에)
    python scripts/b2_migrate.py --dev --database judge_test   # 시험용 DB. 개발용 extract.handoff 대역도 만든다

서비스 DB에는 --dev 를 쓰지 않는다. 대역 표가 있으면 A의 a2_0003 마이그레이션이 실패한다 (docs/A1_작업_흐름_실행.md).

JUDGE_PG_PASSWORD 가 deploy/htodb/.env 에 없으면 만들어 적는다 (값은 출력하지 않는다).
"""
import argparse
import secrets
import sys
from pathlib import Path

import psycopg
import psycopg.sql

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))

from msds.compliance.htodb.config import ENV_FILE, pg_kwargs, setting  # noqa: E402

MIGRATIONS = BACKEND / "migrations"


def writer_password() -> str:
    try:
        return setting("JUDGE_PG_PASSWORD")
    except RuntimeError:
        password = secrets.token_urlsafe(24)
        with open(ENV_FILE, "a", encoding="utf-8") as f:
            f.write(f"\nJUDGE_PG_PASSWORD={password}\n")
        return password


_NOT_INSTALLED = ("A 설치가 끝나지 않았습니다 ({}). 팀 DB는 deploy/htodb/TEAM_SETUP.md 6절(A 실행기)을 끝까지 마친 뒤 "
                  "다시 실행하고, 개발용이면 --dev 를 붙이세요")


def migrate(database: str = "kdb", dev: bool = False) -> None:
    admin = pg_kwargs("admin")
    with psycopg.connect(**admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone()
        if not exists and not dev:  # 팀 DB는 A가 먼저 만든다. 없는 DB를 B가 만들지 않는다
            raise SystemExit(_NOT_INSTALLED.format(f"DB {database} 없음"))
        if not exists:
            conn.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(database)))
    files = ([MIGRATIONS / "dev" / "a2_stub_extract_handoff.sql"] if dev else []) + sorted(MIGRATIONS.glob("b2_*.sql"))
    with psycopg.connect(**{**admin, "dbname": database}) as conn:
        if not dev:
            # A 실행기가 0007(권한 단계)까지 마쳐야 to21_judge가 넘김을 읽는다. 중간에 멈춘 DB에서 B가 직접 권한을 주면
            # A 실행기가 다시 돌지 못해 서로 막힌다 (2026-11-03 검증)
            ready = conn.execute("""SELECT to_regclass('extract.handoff') IS NOT NULL
                                           AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'to21_judge')""").fetchone()[0]
            if not ready:
                raise SystemExit(_NOT_INSTALLED.format("extract.handoff 또는 to21_judge 없음"))
            if not conn.execute("SELECT has_table_privilege('to21_judge', 'extract.handoff', 'SELECT')").fetchone()[0]:
                raise SystemExit(_NOT_INSTALLED.format("0007 권한 단계 미적용"))
        old_stub = conn.execute("""SELECT 1 FROM information_schema.columns WHERE table_schema = 'extract'
                                   AND table_name = 'handoff' AND column_name = 'body'""").fetchone()
        if dev and old_stub:  # 예전 개발용 대역(body 칸)은 A2 표 모양으로 다시 만든다. 개발 DB에서만
            conn.execute("DROP TABLE extract.handoff")
            print("예전 개발용 extract.handoff(body 칸)를 지우고 다시 만듦")
        conn.execute("SELECT set_config('msds.b2_dev', %s, false)", ("on" if dev else "off",))  # b2_002가 개발용 분기를 고른다
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))
        conn.execute(psycopg.sql.SQL("ALTER ROLE judge_writer PASSWORD {}").format(psycopg.sql.Literal(writer_password())))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--database", default="kdb")
    args = parser.parse_args()
    migrate(args.database, args.dev)
    print(f"judge 스키마 준비 끝 (database={args.database}, dev={args.dev})")
