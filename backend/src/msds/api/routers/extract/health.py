"""서버 살아 있음과 쓰는 모델 태그."""

from fastapi import APIRouter

from msds.service import pipeline

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {"ok": True, "model_tag": pipeline.model_tag()}
