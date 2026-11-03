"""지식 DB 접속 설정. 값은 deploy/htodb/.env(git 제외)에서 읽고, 같은 이름의 환경 변수가 있으면 그쪽을 쓴다."""
import os

from dotenv import dotenv_values

from msds.common.paths import ROOT

ENV_FILE = ROOT / "deploy" / "htodb" / ".env"


def setting(name: str, default: str | None = None) -> str:
    value = os.environ.get(name) or dotenv_values(ENV_FILE).get(name) or default
    if value is None:
        raise RuntimeError(f"{name} 설정이 없습니다. {ENV_FILE} 에 넣으세요 (견본: .env.example)")
    return value


def pg_address() -> dict:
    return {"host": setting("HTODB_PG_HOST", "127.0.0.1"), "port": int(setting("HTODB_PG_PORT", "5433"))}


def pg_kwargs(user: str = "reader") -> dict:
    """reader = 쓰기 권한 없는 조회 계정(API·시험), admin = 적재 계정(적재 스크립트만)."""
    kw = {**pg_address(), "dbname": "kdb"}
    if user == "admin":
        return {**kw, "user": "kdb", "password": setting("HTODB_PG_PASSWORD")}
    return {**kw, "user": "kdb_reader", "password": setting("HTODB_READER_PASSWORD"),
            "options": "-c default_transaction_read_only=on"}
