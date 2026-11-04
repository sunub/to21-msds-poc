"""TO21 지식DB(HTODB) 조회 API (읽기 전용).

기본 응답은 원본 값을 그대로 돌려준다. 독성·물성 조회에 ``parsed=true``를 주면
원본 행은 유지한 채 판정 입력용 파싱 결과를 별도 필드로 덧붙인다.

실행: cd backend && .venv/bin/uvicorn --app-dir src msds.api.htodb_app:app --port 8010  (문서: /docs)

이 파일은 앱 조립(접속 풀·버전·매핑 시트 수명, 라우터 붙이기)만 한다.
경로별 코드는 msds/api/routers/htodb/ 아래 의미별 파일에 있다 (목록은 routers/htodb/__init__.py).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from msds.api.routers.htodb import ROUTERS
from msds.api.routers.htodb.deps import state
from msds.compliance.htodb import repo
from msds.compliance.htodb.config import pg_kwargs
from msds.compliance.htodb.mapping import Map13

__all__ = ["app", "state"]  # state: 시험이 켜진 앱의 풀·매핑을 직접 본다


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 쓰기 권한 없는 계정 + 읽기 전용 세션(config.pg_kwargs), 두 겹으로 막는다.
    pool = ConnectionPool(
        "",
        kwargs={**pg_kwargs("reader"), "row_factory": dict_row},
        min_size=1,
        max_size=8,
        open=True,
    )
    with pool.connection() as conn:
        state["versions"] = repo.versions(conn)
        state["map"] = Map13(
            conn.execute(
                "SELECT * FROM htodb_map.sheet13 ORDER BY sheet_row"
            ).fetchall()
        )
    state["pool"] = pool
    yield
    pool.close()


app = FastAPI(title="TO21 HTODB 조회 API", lifespan=lifespan)
for router in ROUTERS:
    app.include_router(router)
