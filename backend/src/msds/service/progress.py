"""업로드한 문서 한 건의 진행 상태: 상태 dict 만들기, 이벤트 반영, 화면용 보기 (서비스 API).

파일을 읽거나 쓰지 않는 순수 함수만 둔다. 저장은 store, 이벤트를 내는 쪽은 pipeline과
section_runner.run_document(on_event)다.

진행의 기본 단위는 항목(MSDS 건 × 추출 대상 항(extract.inputs.EXTRACT_SECTIONS))이다. 추출이 항별로 동시에 돌기 때문에 쪽 단위 진행은 실제와
맞지 않는다. 항이 걸친 쪽(pages)은 원문 이동용으로만 같이 둔다.

status  : queued(대기) → running → done | failed | interrupted(서버가 꺼져 멈춤)
stage   : preprocess(1) → sections(2) → extract(3) → finalize(4) → done
항 status: queued → running → done | failed. needs_review는 따로 둔다(성공했지만 사람이 볼 항).
"""
from __future__ import annotations

STAGES = ("preprocess", "sections", "extract", "finalize")
UNTRUSTED_TEXT_LAYERS = ("글꼴깨짐", "없음", "혼합")
ERRORS_KEPT = 3            # 항마다 남기는 오류 문장 수. 전체는 실행 기록(raw, checks)에 있다
_SECTION_STATUSES = ("queued", "running", "done", "failed")


def new_state(doc_id: str, filename: str, sha256: str, size: int, as_of: str | None, model_tag: str,
              now: str, duplicate_of: list[str] | None = None) -> dict:
    return {
        "id": doc_id, "filename": filename, "sha256": sha256, "size": size, "as_of": as_of,
        "model_tag": model_tag, "duplicate_of": list(duplicate_of or []),
        "created_at": now, "updated_at": now,
        **_run_fields(),
    }


def _run_fields() -> dict:
    """다시 돌릴 때 비우는 칸."""
    return {"status": "queued", "stage": None, "error": None, "warnings": [],
            "page_count": None, "text_layer": None, "preprocess": {"done": 0, "total": None},
            "msds_count": None, "sections": [], "summary": None}


def _section(state: dict, event: dict) -> dict:
    key = (event["msds_index"], event["section"])
    for s in state["sections"]:
        if (s["msds_index"], s["section"]) == key:
            return s
    raise ValueError(f"계획에 없는 항: MSDS {key[0]} {key[1]}항")


def apply_event(state: dict, event: dict) -> dict:
    """event를 state에 반영하고 state를 돌려준다(제자리에서 바꾼다). 모르는 이벤트는 ValueError."""
    kind = event.get("type")
    if kind == "queued":
        state.update(_run_fields())
    elif kind == "started":
        state.update(status="running", stage="preprocess", error=None)
    elif kind == "page":
        state["page_count"] = event["total"]
        state["preprocess"] = {"done": event["page"], "total": event["total"]}
    elif kind == "preprocess_done":
        n = event["page_count"]
        state.update(page_count=n, text_layer=event.get("text_layer"), preprocess={"done": n, "total": n})
        if state["text_layer"] in UNTRUSTED_TEXT_LAYERS:
            state["warnings"].append(f"텍스트층 {state['text_layer']}: 일부 쪽은 OCR로 읽었습니다. "
                                     "그 쪽의 추출값은 원문과 꼭 맞춰 보세요")
    elif kind == "stage":
        if event["stage"] not in STAGES:
            raise ValueError(f"모르는 단계: {event['stage']}")
        state["stage"] = event["stage"]
    elif kind == "plan":
        state["msds_count"] = event["msds_count"]
        state["sections"] = [{"msds_index": s["msds_index"], "section": s["section"], "title": s.get("title"),
                              "pages": list(s.get("pages") or []), "status": "queued", "needs_review": False,
                              "reextracted": False, "seconds": None, "errors": []}
                             for s in event["sections"]]
    elif kind == "section_started":
        _section(state, event)["status"] = "running"
    elif kind == "section_done":
        s = _section(state, event)
        s.update(status="done" if event["ok"] else "failed", needs_review=bool(event["needs_review"]),
                 reextracted=bool(event["reextracted"]), seconds=event.get("seconds"),
                 errors=list(event.get("errors") or [])[:ERRORS_KEPT])
    elif kind == "finalize":
        state["stage"] = "finalize"
    elif kind == "reused":
        state["reused_from"] = event["job_id"]
    elif kind == "done":
        summary = dict(event.get("summary") or {})
        state["warnings"] += list(summary.pop("warnings", []) or [])
        state.update(status="done", stage="done", summary=summary)
    elif kind == "failed":
        state.update(status="failed", error=event["error"])
    elif kind == "interrupted":
        state.update(status="interrupted", error="서버가 다시 켜져 작업이 멈췄습니다. 다시 실행하세요")
    else:
        raise ValueError(f"모르는 진행 이벤트: {kind}")
    return state


def counts(state: dict) -> dict:
    secs = state["sections"]
    out = {"total": len(secs), **{k: sum(s["status"] == k for s in secs) for k in _SECTION_STATUSES}}
    out["needs_review"] = sum(s["needs_review"] for s in secs)
    return out


def stage_index(state: dict) -> int:
    """1~4. 시작 전이면 0, 끝났으면 4."""
    if state["stage"] == "done":
        return len(STAGES)
    return STAGES.index(state["stage"]) + 1 if state["stage"] in STAGES else 0


def can_retry(state: dict) -> bool:
    """처음부터 다시 돌릴 수 있는가: 실패·멈춘 문서, 또는 끝났지만 실패한 항이 있는 문서."""
    if state["status"] in ("failed", "interrupted"):
        return True
    return state["status"] == "done" and any(s["status"] == "failed" for s in state["sections"])


def summary_view(state: dict) -> dict:
    """목록 화면 한 줄: 항별 목록 없이 개수만."""
    keep = ("id", "filename", "size", "as_of", "model_tag", "created_at", "updated_at", "status", "stage",
            "error", "page_count", "text_layer", "msds_count")
    return {**{k: state[k] for k in keep}, "stage_index": stage_index(state), "stage_total": len(STAGES),
            "counts": counts(state), "can_retry": can_retry(state),
            "reused_from": state.get("reused_from"),
            "validation": (state.get("summary") or {}).get("validation")}


def view(state: dict) -> dict:
    """진행 화면: 목록 한 줄에 항별 상태·전처리 진행·경고를 더한다. 저장소 경로와 해시는 내보내지 않는다."""
    return {**summary_view(state), "preprocess": dict(state["preprocess"]), "warnings": list(state["warnings"]),
            "duplicate_of": list(state["duplicate_of"]), "summary": state["summary"],
            "sections": [dict(s) for s in state["sections"]]}
