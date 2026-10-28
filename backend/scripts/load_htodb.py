"""TO21 지식DB(HTODB) 원본 16개 테이블을 PostgreSQL `htodb` 스키마에 그대로 적재한다.

원칙: 기업 제공 데이터라 값을 바꾸지 않는다(공백·부등호·단위·'NULL' 없음 등 원형 유지).
바꾸는 것은 이름 대소문자(PostgreSQL 관례상 소문자)뿐이다.
검증: 테이블마다 행 수와 '행 순서와 무관한 전체 값 해시'를 SQL Server 원본과 PostgreSQL에서 각각 계산해 같아야 한다.

사용법: deploy/htodb/README.md 순서대로 SQL Server에 mdf를 연결한 뒤
  cd backend && .venv/bin/python scripts/load_htodb.py --source <받은 HTODB.zip 경로>
(--source는 knowledge_version을 원본 zip 해시로 남기려고 받는다. 데이터는 저장소에 두지 않는다, D-47)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import _common  # noqa: F401  (src 경로 등록)
import psycopg
import pymssql
from psycopg import sql

from msds.compliance.htodb.config import pg_kwargs, setting

SCHEMA = "htodb"
# TO21 테이블설명에 적힌 16개 테이블
TABLES = [
    "TB_ENG_CHEM_MASTER_INFO", "TB_GHS_CHEM_CLASS_MAP", "TB_GHS_CLASS_MASTER_LANG", "TB_GHS_HCODE_PHRASE",
    "TB_GHS_HCODE_PHRASE_LANG", "TB_GHS_DIV_MASTER", "TB_ENG_CHEM_TOXICITY_TEST_INFO", "TB_ENG_PHYSICAL_PROPERTY_LANG",
    "TB_ENG_CHEM_PHY_PROPERTY_MAP", "TB_ENG_REGULATE_LANG", "TB_ENG_REGULATE_ITEM_LANG", "TB_ENG_REG_NOTICE_INFO",
    "TB_ENG_REGULA_CHEM_MAP", "TB_ENG_REG_NOTICE_STD", "TB_ENG_REG_NOTICE_CONTENT", "TB_ENG_FORM_EXPOSURE_INFO",
]
BATCH = 20_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def row_digest(row) -> int:
    # None과 문자열 'None'을 구분하고, Decimal은 str로 자릿수(1.000)까지 비교한다.
    text = "\x1f".join("\x00" if v is None else f"{type(v).__name__}:{v}" for v in row)
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


def columns(ms, table: str) -> list[dict]:
    cur = ms.cursor(as_dict=True)
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
        (table,),
    )
    return cur.fetchall()


def primary_key(ms, table: str) -> list[str]:
    cur = ms.cursor()
    cur.execute(
        "SELECT c.name FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id "
        "JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id "
        "WHERE i.is_primary_key=1 AND i.object_id=OBJECT_ID(%s) ORDER BY ic.key_ordinal",
        ("dbo." + table,),
    )
    return [r[0] for r in cur.fetchall()]


def pg_type(c: dict) -> str:
    t = c["DATA_TYPE"]
    if t in ("varchar", "nvarchar"):
        n = c["CHARACTER_MAXIMUM_LENGTH"]
        return "text" if n == -1 else f"varchar({n})"  # SQL Server varchar(n)은 바이트, PG는 글자 수라 원본 값은 항상 들어간다
    if t == "numeric":
        return f"numeric({c['NUMERIC_PRECISION']},{c['NUMERIC_SCALE']})"
    raise SystemExit(f"예상하지 못한 타입 {t} ({c['COLUMN_NAME']}): load_htodb.py에 대응을 추가할 것")


def load_table(ms, pg, table: str) -> dict:
    cols = columns(ms, table)
    pk = primary_key(ms, table)
    names = [c["COLUMN_NAME"] for c in cols]
    ddl = ", ".join(f"{n.lower()} {pg_type(c)}{'' if c['IS_NULLABLE'] == 'YES' else ' NOT NULL'}" for n, c in zip(names, cols))
    pg.execute(f"CREATE TABLE {SCHEMA}.{table.lower()} ({ddl}, PRIMARY KEY ({', '.join(p.lower() for p in pk)}))")

    src_n, src_h = 0, 0
    cur = ms.cursor()
    cur.execute(f"SELECT {', '.join('[' + n + ']' for n in names)} FROM dbo.[{table}]")
    with pg.cursor().copy(f"COPY {SCHEMA}.{table.lower()} ({', '.join(n.lower() for n in names)}) FROM STDIN") as cp:
        while rows := cur.fetchmany(BATCH):
            for row in rows:
                if any(isinstance(v, str) and "\x00" in v for v in row):
                    raise SystemExit(f"{table}: NUL 문자가 있어 PostgreSQL text에 원형 그대로 넣을 수 없음 → 중단")
                cp.write_row(row)
                src_n += 1
                src_h = (src_h + row_digest(row)) & ((1 << 64) - 1)

    dst_n, dst_h = 0, 0
    with pg.cursor(name=f"chk_{table.lower()}") as rc:  # 서버 쪽 커서로 나눠 읽음
        rc.itersize = BATCH
        rc.execute(f"SELECT {', '.join(n.lower() for n in names)} FROM {SCHEMA}.{table.lower()}")
        for row in rc:
            dst_n += 1
            dst_h = (dst_h + row_digest(row)) & ((1 << 64) - 1)

    ok = src_n == dst_n and src_h == dst_h
    print(f"{'OK ' if ok else 'FAIL'} {table:34s} rows {src_n:>8,} → {dst_n:>8,}  hash {src_h:016x} {'==' if src_h == dst_h else '!='} {dst_h:016x}")
    return {"table": table, "rows": dst_n, "source_rows": src_n, "hash": f"{dst_h:016x}", "ok": ok}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, required=True, help="TO21에서 받은 HTODB.zip (해시 기록용)")
    source = ap.parse_args().source
    zip_sha = sha256(source)
    version = f"htodb-{zip_sha[:12]}"
    ms = pymssql.connect(server="127.0.0.1", port=int(setting("HTODB_MSSQL_PORT", "14330")), user="sa",
                         password=setting("HTODB_MSSQL_SA_PASSWORD"), database="HTODB")
    ms_cur = ms.cursor()
    ms_cur.execute("SELECT is_read_only FROM sys.databases WHERE name='HTODB'")
    if ms_cur.fetchone()[0] != 1:
        raise SystemExit("HTODB가 읽기 전용이 아님 → deploy/htodb/README.md의 연결 절차로 READ_ONLY 설정 후 실행")
    ms_cur.execute("SELECT @@VERSION")
    ms_version = ms_cur.fetchone()[0].splitlines()[0]

    with psycopg.connect(**pg_kwargs("admin")) as pg:
        # 한 트랜잭션: 실패하면 이전 적재본이 그대로 남는다
        pg.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        pg.execute(f"CREATE SCHEMA {SCHEMA}")
        results = [load_table(ms, pg, t) for t in TABLES]
        if not all(r["ok"] for r in results):
            raise SystemExit("원본과 적재본이 다른 테이블이 있음 → 롤백")
        pg.execute(
            f"CREATE TABLE {SCHEMA}.load_log (knowledge_version text, source_file text, source_sha256 text, "
            "source_server text, loaded_at timestamptz, table_name text, row_count bigint, row_hash text)"
        )
        now = datetime.now(timezone.utc)
        with pg.cursor().copy(f"COPY {SCHEMA}.load_log FROM STDIN") as cp:
            for r in results:
                cp.write_row((version, source.name, zip_sha, ms_version, now, r["table"], r["rows"], r["hash"]))
        pg.execute(sql.SQL("COMMENT ON SCHEMA {} IS {}").format(
            sql.Identifier(SCHEMA), sql.Literal(f"TO21 HTODB 원본 그대로, {version}, 수정 금지")))
    print(f"완료: {version} ({len(results)}개 테이블, {sum(r['rows'] for r in results):,}행)")


if __name__ == "__main__":
    sys.exit(main())
