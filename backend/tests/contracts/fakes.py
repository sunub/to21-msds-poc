"""역할마다 상대 대신 끼우는 가짜 (나누기 문서 1절). 계약이 바뀌면 test_contract_schemas.py 가 이 파일도 함께 검사한다.

    make_handoff    약속 ① 넘김 기록. TO21 예제를 담으므로 파일로 두지 않고 그 자리에서 만든다 (D-47)
    fake_process    약속 ② 단계 함수. 몇 초 자고 이벤트만 낸다 (A1이 대기열을 시험할 때)
    FakeGate        약속 ④ 모델 창구. 동시 수만 막는다 (A2·B2가 A1의 창구를 기다릴 때)
"""
import asyncio
import hashlib
import json
import threading
import time
from contextlib import contextmanager

_SHA = "a" * 64


def extraction_sha256(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def make_handoff(doc, seq=1, job="U-20261102-001", reason="extraction_done", as_of="2026-11-02", field_status=(), failed=(), fields_total=100):
    return {
        "contract": "handoff/1", "job_id": job, "handoff_seq": seq, "reason": reason,
        "created_at": "2026-11-02T10:00:00+09:00", "as_of": as_of,
        "source": {"filename": "황산.pdf", "file_sha256": _SHA, "page_count": 14, "text_layer": "정상"},
        "extraction_settings": {"model_tag": "qwen36_35b_runpod", "model_config_sha256": _SHA, "code_commit": "abc1234",
                                "schema_version": "TO21-MSDS-EXT v0.6", "dictionary_version": "v0.6", "reused_from": None},
        "extraction": doc, "extraction_sha256": extraction_sha256(doc),
        "checks": {"validator": {"version": "v0.6", "errors": 0, "warnings": 0}, "failed_sections": list(failed),
                   "reextracted_sections": [], "source_mismatch": []},
        "fields_total": fields_total, "field_status": list(field_status)}


JOB_EVENTS = [
    {"type": "started"},
    {"type": "page", "page": 1, "total": 2},
    {"type": "page", "page": 2, "total": 2},
    {"type": "preprocess_done", "page_count": 2, "text_layer": "정상"},
    {"type": "stage", "stage": "extract"},
    {"type": "plan", "msds_count": 1, "page_count": 2, "sections": [{"msds_index": 0, "section": 2, "title": "유해성·위험성", "pages": [1, 2]}]},
    {"type": "section_started", "msds_index": 0, "section": 2},
    {"type": "section_done", "msds_index": 0, "section": 2, "ok": True, "reextracted": False, "needs_review": False, "seconds": 0.1, "errors": []},
    {"type": "finalize"},
    {"type": "stage", "stage": "checks"},
    {"type": "checks_done", "errors": 0, "warnings": 0, "reextracted": 0},
    {"type": "handoff", "handoff_seq": 1},
    {"type": "done", "summary": {}},
]


def fake_process(job_id: str, ctx, seconds: float = 0.0, fail: str | None = None) -> None:
    """process(job_id, ctx) -> None. 예외를 내지 않고 failed 이벤트로 끝낸다."""
    for event in JOB_EVENTS:
        if fail and event["type"] == "finalize":
            ctx.emit({"type": "failed", "error": fail})
            return
        ctx.emit(event)
        time.sleep(seconds)


class FakeGate:
    """slot(kind)은 async, slot_sync(kind)는 스레드용. 상한만 지키고 추출 우선 순서는 흉내 내지 않는다."""

    KINDS = ("extract", "reextract", "explain")

    def __init__(self, limit: int = 2):
        self.limit = limit
        self._sem = threading.Semaphore(limit)
        self._async = asyncio.Semaphore(limit)

    @contextmanager
    def slot_sync(self, kind):
        assert kind in self.KINDS, kind
        with self._sem:
            yield

    def slot(self, kind):
        assert kind in self.KINDS, kind
        return self._async
