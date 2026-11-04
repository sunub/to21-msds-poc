"""지식DB 접속 확인과 적재 버전."""

from fastapi import APIRouter

from msds.api.routers.htodb.deps import conn, state

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    with conn() as c:
        c.execute("SELECT 1")
    return {"status": "ok", **state["versions"]}
