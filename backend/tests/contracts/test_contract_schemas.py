"""계약 자체 시험: 스키마가 올바르고, 견본은 통과하고, 틀린 값은 걸린다. 구현(judge·DB) 없이 돌고 TO21 추출스키마만 있으면 된다.

역할마다 자기 구현 시험을 따로 둔다 (contracts/README.md 4절). samples/ 견본은 TO21 원문을 담지 않은 손으로 만든 값이다.
"""
import asyncio
import json
import threading
import time

import jsonschema
import pytest

from msds.common.paths import ROOT

from .fakes import FakeGate, fake_process, make_handoff

CONTRACTS = ROOT / "docs" / "superpowers" / "specs" / "contracts"
FID = "m0/F2:HH_ACUTE_INHAL:분진·미스트"


@pytest.mark.parametrize("path", sorted(CONTRACTS.glob("*.json")), ids=lambda p: p.name)
def test_스키마_자체가_올바르다(path):
    jsonschema.Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


SAMPLES = CONTRACTS / "samples"


def sample(name):
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def consistency(**over):
    return {**sample("consistency"), **over}


def finding(**over):
    return {**sample("consistency")["results"][0]["findings"][0], **over}


NOT_API = {"consistency"}
GOOD = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLES.glob("*.json")) if p.stem not in NOT_API}
SNAPSHOT = GOOD["snapshot"]
BAD = [
    ("judgment_status", {**GOOD["judgment_status"], "state": "모름"}),
    ("judgment_batch_item", {**GOOD["judgment_batch_item"], "data_grade": "브론즈"}),
    ("review_event_request", {"finding_id": FID, "action": "예외 승인", "reviewer": "김검수", "seen_version": 1}),
    ("review_event_request", {**GOOD["review_event_request"], "finding_id": "F-2-001"}),
    ("review_state", {**GOOD["review_state"], "status": "보류"}),
    ("snapshot", {**SNAPSHOT, "counts": {"findings": 1}}),
    ("report_request", {"format": "docx", "include": GOOD["report_request"]["include"]}),
    ("report_request", {"format": "pdf"}),
    ("history_entry", {**GOOD["history_entry"], "area": "기타"}),
    ("to_judgment_response", {"job_id": "abc", "handoff_seq": 1}),
    ("queue_fields", {**GOOD["queue_fields"], "queue_position": 0}),
    ("document_extras", {**GOOD["document_extras"], "values_review": {"state": "미검수"}}),
    ("review_field_extras", {"confidence": 0.5}),
    ("save_overview", {**GOOD["save_overview"], "reviews": {"unreviewed_ids": []}}),
    ("finding_display", {"msds": "구분 2"}),
]


def test_화면_API_정의를_모두_견본으로_덮었다():
    defs = json.loads((CONTRACTS / "5-api.schema.json").read_text(encoding="utf-8"))["$defs"]
    assert set(defs) - {"report_document"} == set(GOOD)  # report_document 는 추출값을 담아 시험에서 만든다 (test_b2_service)


@pytest.mark.parametrize("name", sorted(GOOD))
def test_견본이_통과한다(name, contract_errors):
    assert contract_errors(f"5-api.schema.json#/$defs/{name}", GOOD[name]) == []


@pytest.mark.parametrize("name,obj", BAD, ids=[f"{n}-{i}" for i, (n, _) in enumerate(BAD)])
def test_틀린_값은_걸린다(name, obj, contract_errors):
    assert contract_errors(f"5-api.schema.json#/$defs/{name}", obj) != []


def test_판정_결과_견본이_통과한다(contract_errors):
    assert contract_errors("3-consistency.schema.json", consistency()) == []


@pytest.mark.parametrize("over", [{"contract": "consistency/1"}, {"knowledge": {"provider": "htodb", "version": "x", "rules": "r", "logic": "l"}}, {"results": []}])
def test_틀린_판정_결과는_걸린다(over, contract_errors):
    assert contract_errors("3-consistency.schema.json", consistency(**over)) != []


@pytest.mark.parametrize("over", [{"id": "F-2-001"}, {"verdict": "모름"}, {"causes": [{"code": "FORM_DIFF", "text": "x"}]}, {"out_of_scope_reason": "모름"},
                                  {"causes": ["NEW_CODE"]}])
def test_틀린_finding은_걸린다(over, contract_errors):
    doc = consistency()
    doc["results"][0]["findings"] = [finding(**over)]
    assert contract_errors("3-consistency.schema.json", doc) != []


def test_설명이_완료인데_내용이_없으면_걸린다(contract_errors):
    view = {**GOOD["judgment_view"], "explanations": {FID: {"status": "완료"}}}
    assert contract_errors("5-api.schema.json#/$defs/judgment_view", view) != []


def test_TO21_정답_예제로_만든_넘김_기록이_통과한다(gold25, contract_errors):
    body = make_handoff(gold25)
    assert contract_errors("1-handoff.schema.json", body) == []
    assert contract_errors("1-handoff.schema.json", {**body, "contract": "handoff/2"}) != []
    assert contract_errors("1-handoff.schema.json", {**body, "field_status": [{"msds_index": 0, "field": "x", "status": "미검수"}]}) != []


def test_같은_작업의_넘김_두_건은_번호와_해시로_구분된다(gold25, contract_errors):
    first = make_handoff(gold25)
    changed = json.loads(json.dumps(gold25))
    changed["msds"][0]["product"]["name"] += " 수정"
    second = make_handoff(changed, 2, reason="value_edited", field_status=[{"msds_index": 0, "field": "product.name", "status": "수정됨"}])
    assert contract_errors("1-handoff.schema.json", second) == []
    assert (first["job_id"], first["handoff_seq"] + 1) == (second["job_id"], second["handoff_seq"])
    assert first["extraction_sha256"] != second["extraction_sha256"]


class _Ctx:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def test_가짜_단계_함수의_이벤트가_약속_2를_지킨다(contract_errors):
    ctx = _Ctx()
    fake_process("U-20261102-001", ctx)
    for event in ctx.events:
        assert contract_errors("2-job-event.schema.json", event) == [], event
    kinds = [e["type"] for e in ctx.events]
    assert kinds.index("handoff") < kinds.index("done") and kinds[-1] == "done"


def test_가짜_단계_함수의_실패는_예외가_아니라_failed_이벤트다(contract_errors):
    ctx = _Ctx()
    fake_process("U-20261102-001", ctx, fail="모델 응답 없음")
    assert ctx.events[-1] == {"type": "failed", "error": "모델 응답 없음"}
    assert contract_errors("2-job-event.schema.json", ctx.events[-1]) == []
    assert contract_errors("2-job-event.schema.json", {"type": "failed"}) != []


def test_가짜_창구는_상한을_지키고_종류를_검사한다():
    gate, lock = FakeGate(2), threading.Lock()
    now, peak = [0], [0]

    def work():
        with gate.slot_sync("explain"):
            with lock:
                now[0] += 1
                peak[0] = max(peak[0], now[0])
            time.sleep(0.02)
            with lock:
                now[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 2
    with pytest.raises(AssertionError):
        with gate.slot_sync("모름"):
            pass

    async def async_work():
        async with gate.slot("extract"):
            return True

    assert asyncio.run(async_work())
