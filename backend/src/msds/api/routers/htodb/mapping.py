"""추출 코드 → HTODB 코드 번역 (13_TO21DB매핑 시트). DB를 다시 읽지 않고 켤 때 읽어 둔 시트로 답한다."""

from fastapi import APIRouter, HTTPException

from msds.api.routers.htodb.deps import state, wrap

router = APIRouter(prefix="/mapping", tags=["mapping"])

MAP_KINDS = {
    "pictogram": "pictogram",
    "signal-word": "signal_word",
    "property": "property",
    "endpoint": "endpoint",
    "regulation": "regulation",
}


@router.get("/hazard")
def map_hazard(
    class_code: str,
    category: str | None = None,
    route_form: str | None = None,
    effect: str | None = None,
):
    return wrap(state["map"].hazard(class_code, category, route_form, effect))


@router.get("/{kind}/{code}")
def map_code(kind: str, code: str):
    if kind not in MAP_KINDS:
        raise HTTPException(
            404, f"알 수 없는 종류: {kind} (가능: hazard, {', '.join(MAP_KINDS)})"
        )
    return wrap(getattr(state["map"], MAP_KINDS[kind])(code))
