"""judge 스키마를 만든다. 관리자 계정으로 migrations/b2_*.sql 을 차례로 돌리고 judge_writer 비밀번호를 맞춘다.

    python scripts/b2_migrate.py           # A2의 extract.handoff 가 이미 있을 때
    python scripts/b2_migrate.py --dev     # 개발용 extract.handoff 대역도 만든다
    python scripts/b2_migrate.py --dev --database judge_test   # 시험용 DB

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


def migrate(database: str = "kdb", dev: bool = False) -> None:
    admin = pg_kwargs("admin")
    if database != admin["dbname"]:
        with psycopg.connect(**admin, autocommit=True) as conn:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone():
                conn.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(database)))
    files = ([MIGRATIONS / "dev" / "a2_stub_extract_handoff.sql"] if dev else []) + sorted(MIGRATIONS.glob("b2_*.sql"))
    password = writer_password()
    with psycopg.connect(**{**admin, "dbname": database}) as conn:
        old_stub = conn.execute("""SELECT 1 FROM information_schema.columns WHERE table_schema = 'extract'
                                   AND table_name = 'handoff' AND column_name = 'body'""").fetchone()
        has_handoff = conn.execute("SELECT to_regclass('extract.handoff') IS NOT NULL").fetchone()[0]
        if not dev and not has_handoff:
            raise SystemExit("extract.handoff 가 없습니다. 팀 DB는 A 설치(deploy/htodb/TEAM_SETUP.md 6절)를 먼저 하고, "
                             "개발용이면 --dev 를 붙이세요")
        if dev and old_stub:  # 예전 개발용 대역(body 칸)은 A2 표 모양으로 다시 만든다. 개발 DB에서만
            conn.execute("DROP TABLE extract.handoff")
            print("예전 개발용 extract.handoff(body 칸)를 지우고 다시 만듦")
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))
        conn.execute(psycopg.sql.SQL("ALTER ROLE judge_writer PASSWORD {}").format(psycopg.sql.Literal(password)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--database", default="kdb")
    args = parser.parse_args()
    migrate(args.database, args.dev)
    print(f"judge 스키마 준비 끝 (database={args.database}, dev={args.dev})")
