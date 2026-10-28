"""기업 명세서 v0.6의 '13_TO21DB매핑' 시트를 PostgreSQL `htodb_map.sheet13`에 셀 값 그대로 적재한다.

추출 JSON 코드(class_code·prop_code·endpoint·item_code 등) ↔ HTODB 코드 번역표다. 기업 자료라 값을 바꾸지 않는다.
section은 시트의 'A. …'~'F. …' 묶음 제목 행에서 따온 글자다(제목 행 아래 행들에 붙인다).
검증: 다시 읽은 행이 시트 행과 셀 단위로 모두 같아야 커밋한다.

사용법: cd backend && .venv/bin/python scripts/load_htodb_map.py   (명세서는 to21/v0.6/에 각자 둔 파일, D-47)
"""
from __future__ import annotations

from datetime import datetime, timezone

import _common  # noqa: F401  (src 경로 등록)
import psycopg
from load_htodb import sha256
from psycopg import sql

from msds.common.paths import to21_file
from msds.compliance.htodb.config import pg_kwargs
from msds.compliance.htodb.sheet13 import NCOL, SHEET, read_sheet

SCHEMA = "htodb_map"


def main() -> None:
    xlsx = to21_file("spec")
    rows = read_sheet(xlsx)
    xlsx_sha = sha256(xlsx)
    version = f"map13-{xlsx_sha[:12]}"
    with psycopg.connect(**pg_kwargs("admin")) as pg:
        pg.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        pg.execute(f"CREATE SCHEMA {SCHEMA}")
        cols = ", ".join(f"c{i} text" for i in range(1, NCOL + 1))
        pg.execute(f"CREATE TABLE {SCHEMA}.sheet13 (sheet_row int PRIMARY KEY, section text, {cols})")
        with pg.cursor().copy(f"COPY {SCHEMA}.sheet13 FROM STDIN") as cp:
            for r in rows:
                cp.write_row(r)
        back = [tuple(r) for r in pg.execute(f"SELECT * FROM {SCHEMA}.sheet13 ORDER BY sheet_row").fetchall()]
        if back != rows:
            raise SystemExit("시트와 적재본이 다름 → 롤백")
        pg.execute(
            f"CREATE TABLE {SCHEMA}.load_log (map_version text, source_file text, source_sha256 text, sheet text, "
            "loaded_at timestamptz, row_count int)"
        )
        pg.execute(
            f"INSERT INTO {SCHEMA}.load_log VALUES (%s, %s, %s, %s, %s, %s)",
            (version, xlsx.name, xlsx_sha, SHEET, datetime.now(timezone.utc), len(rows)),
        )
        pg.execute(sql.SQL("COMMENT ON SCHEMA {} IS {}").format(
            sql.Identifier(SCHEMA), sql.Literal(f"기업 명세서 v0.6 {SHEET} 셀 값 그대로, {version}, 수정 금지")))
    print(f"완료: {version} ({len(rows)}행, 시트와 셀 단위 일치)")


if __name__ == "__main__":
    main()
