"""[A2] 목록·머리줄 칸(document_extras)과 사람 구간 상태(review_stage)가 5-api 계약을 지키는가."""
from msds.extract.inputs import EXTRACT_SECTIONS
from msds.service import review

MSDS = {
    "meta": {"doc_code": "TEST-001", "last_revision_date": "2022-06-29"},
    "product": {"name": "가상 혼합물"},
    "composition": {"type": "혼합물"},
    "components": [{"name": "가상 성분 A", "cas_no": None}, {"name": "가상 성분 B", "cas_no": None}],
}
DOC = {"doc": {"doc_id": "U-20990101-001"}, "msds": [MSDS]}


def test_document_extras_matches_contract(contract_errors):
    record = review.empty()
    assert contract_errors("5-api.schema.json#/$defs/document_extras", review.document_extras(DOC, {}, [], record)) == []
    for no in EXTRACT_SECTIONS:
        review.set_section(record, 0, no, True, "김", "t")
    full = review.document_extras(DOC, {}, [], record)
    assert full["values_review"]["state"] == "완료"
    assert contract_errors("5-api.schema.json#/$defs/document_extras", full) == []
    empty = review.document_extras({"doc": {}, "msds": []}, {}, [], review.empty())
    assert contract_errors("5-api.schema.json#/$defs/document_extras", empty) == []


def test_review_stage_values_are_contract_values(contract_errors):
    queue = {"queue_position": None, "eta_seconds": None}
    for stage in (review.review_stage("done", review.empty(), handed_off=False),
                  review.review_stage("done", review.empty(), handed_off=True),
                  review.review_stage("queued", review.empty(), handed_off=False)):
        assert contract_errors("5-api.schema.json#/$defs/queue_fields", {**queue, "review_stage": stage}) == []
