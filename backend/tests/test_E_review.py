"""service/review.py 와 검수 API 시험. 모델을 부르지 않는다."""
import json

import pytest
from fastapi.testclient import TestClient

from msds.api import extract_app
from msds.extract.inputs import EXTRACT_SECTIONS
from msds.service import pipeline, review
from msds.service.store import DocumentStore

MSDS = {
    "meta": {"msds_no": "A-1", "revision_no": 3, "doc_code": None},
    "product": {"name": "젯소", "uses": ["도료", "접착"]},
    "companies": [{"name": "노루", "address": None}],
    "components": [{"seq": 1, "name": "물", "cas_no": "7732-18-5",
                    "content": {"raw": "1~2", "lower": 1, "upper": 2, "unit": "%"}}],
    "narratives": [{"item_code": "S8_PPE", "title_raw": "가. 눈 보호", "status": "값있음",
                    "statements": [{"seq": 1, "key": None, "value": "씻으시오", "text": "가. 눈 : 씻으시오"}]}],
    "extras": [{"seq": 1, "section_no": 9, "title_raw": "취급", "statements": [{"key": "저장", "value": "서늘한 곳", "text": "x"}]}],
    "evidence": [{"field": "components[0]", "page": 2, "source_text": "물 7732-18-5", "needs_review": None},
                 {"field": "product.name", "page": 1, "source_text": "제품명 : 젯소", "needs_review": None}],
    "validation": [],
}
DOC = {"doc": {"doc_id": "x"}, "msds": [MSDS]}
CHECKS = {"needs_review": [{"msds_index": 0, "section": 3}],
          "sections": [{"msds_index": 0, "section": 3, "check_problems": ["없는 줄"], "errors": ["행 버림"]}],
          "expand_problems": [{"msds_index": 0, "section": 3, "kind": "k", "detail": "d"}],
          "to21_validator": [{"level": "오류", "rule": "V01", "field": "msds[0].components[0].cas_no", "message": "CAS 확인 숫자"}]}


def by_no(view):
    return {s["section"]: s for s in view["msds"][0]["sections"]}


def fields(section):
    return {f["path"]: f for g in section["groups"] for f in g["fields"]}


def build(record=None):
    return review.build_view(DOC, CHECKS, [], record or review.empty())


def test_every_root_goes_to_its_section():
    secs = by_no(build())
    assert sorted(secs) == list(EXTRACT_SECTIONS)          # 추출하지 않는 항은 보이지 않는다
    assert "meta.msds_no" in fields(secs[1]) and "companies[0].name" in fields(secs[1])
    assert "components[0].name" in fields(secs[3])
    assert "narratives[0].statements[0].value" in fields(secs[8])
    assert "extras[0].statements[0].value" in fields(secs[9])
    assert fields(secs[12]) == {}
    assert 4 not in secs and 7 not in secs


def test_hides_null_raw_and_bookkeeping_fields():
    f = fields(by_no(build())[3])
    assert "components[0].content.raw" not in f and "components[0].seq" not in f
    assert "components[0].content.lower" in f
    assert "meta.doc_code" not in fields(by_no(build())[1])


def test_field_has_label_value_and_longest_evidence():
    f = fields(by_no(build())[3])["components[0].cas_no"]
    assert f["label"] == "CAS 번호" and f["value"] == "7732-18-5"
    assert f["page"] == 2 and f["source_text"] == "물 7732-18-5"
    assert fields(by_no(build())[1])["product.name"]["page"] == 1
    assert fields(by_no(build())[9])["extras[0].statements[0].value"]["label"] == "저장"


def test_group_title_uses_item_name_or_korean_root_title():
    secs = by_no(build())
    assert [g["title"] for g in secs[1]["groups"]][:2] == ["문서 정보", "젯소"]
    assert [g["title"] for g in secs[3]["groups"]] == ["물"]


def test_problems_attach_to_section_and_field():
    s = by_no(build())[3]
    assert s["needs_review"] is True and "없는 줄" in s["problems"] and "행 버림" in s["problems"]
    assert fields(s)["components[0].cas_no"]["problems"] == ["V01 CAS 확인 숫자"]
    assert fields(s)["components[0].name"]["problems"] == []


def test_edit_keeps_original_and_type():
    rec = review.empty()
    review.set_field(rec, DOC, 0, "meta.revision_no", "edit", "4", "김검수", "t1")
    review.set_field(rec, DOC, 0, "meta.revision_no", "edit", "5", "이검수", "t2")
    f = fields(by_no(build(rec))[1])["meta.revision_no"]
    assert f["value"] == 5 and f["original"] == 3 and f["state"] == "edited"
    assert f["reviewer"] == "이검수" and f["at"] == "t2"
    assert [e["value"] for e in rec["log"]] == [4, 5]


def test_edit_rejects_bad_number_and_unknown_path():
    rec = review.empty()
    with pytest.raises(ValueError):
        review.set_field(rec, DOC, 0, "meta.revision_no", "edit", "셋", "김", "t")
    with pytest.raises(KeyError):
        review.set_field(rec, DOC, 0, "meta.nothing", "confirm", None, "김", "t")
    with pytest.raises(KeyError):
        review.set_field(rec, DOC, 9, "meta.msds_no", "confirm", None, "김", "t")
    assert rec["fields"] == {} and rec["log"] == []


def test_confirm_and_reset():
    rec = review.empty()
    review.set_field(rec, DOC, 0, "product.name", "confirm", None, "김", "t")
    assert fields(by_no(build(rec))[1])["product.name"]["state"] == "confirmed"
    review.set_field(rec, DOC, 0, "product.name", "edit", "새 이름", "김", "t")
    review.set_field(rec, DOC, 0, "product.name", "reset", None, "김", "t")
    f = fields(by_no(build(rec))[1])["product.name"]
    assert f["state"] == "unchecked" and f["value"] == "젯소" and f["original"] is None
    assert len(rec["log"]) == 3


def test_apply_edits_does_not_touch_source():
    rec = review.empty()
    review.set_field(rec, DOC, 0, "components[0].content.lower", "edit", "1.5", "김", "t")
    review.set_field(rec, DOC, 0, "product.uses[1]", "edit", "", "김", "t")
    out = review.apply_edits(DOC, rec)
    assert out["msds"][0]["components"][0]["content"]["lower"] == 1.5
    assert out["msds"][0]["product"]["uses"][1] is None
    assert MSDS["components"][0]["content"]["lower"] == 1


def test_section_confirm_counts_in_summary():
    rec = review.empty()
    review.set_section(rec, 0, 3, True, "김", "t")
    view = build(rec)
    assert view["summary"]["sections_confirmed"] == 1 and view["summary"]["sections_total"] == len(EXTRACT_SECTIONS)
    assert by_no(view)[3]["confirmed"] == {"reviewer": "김", "at": "t"}
    review.set_section(rec, 0, 3, False, "김", "t")
    assert build(rec)["summary"]["sections_confirmed"] == 0
    with pytest.raises(KeyError):
        review.set_section(rec, 0, 17, True, "김", "t")
    with pytest.raises(KeyError):          # 추출 대상이 아닌 항
        review.set_section(rec, 0, 4, True, "김", "t")


# ── API ─────────────────────────────────────────────

class W:
    def __init__(self): self.submitted = []
    def start(self): pass
    def stop(self, timeout=None): pass
    def submit(self, d): self.submitted.append(d)


@pytest.fixture
def api(tmp_path):
    store = DocumentStore(tmp_path / "service")
    with TestClient(extract_app.create_app(store=store, worker=W(), pages_dir=tmp_path / "pages")) as client:
        doc = client.post("/api/documents", params={"filename": "a.pdf"}, content=b"%PDF-1.7").json()["id"]
        out, checks = pipeline.result_paths(store, doc)
        out.parent.mkdir(parents=True)
        checks.parent.mkdir(parents=True)
        out.write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
        checks.write_text(json.dumps(CHECKS, ensure_ascii=False), encoding="utf-8")
        yield client, store, doc


def done(store, doc):
    store.apply(doc, {"type": "done", "summary": {}})


def test_api_conflict_until_done(api):
    client, store, doc = api
    assert client.get(f"/api/documents/{doc}/review").status_code == 409
    body = {"msds_index": 0, "path": "product.name", "action": "confirm", "reviewer": "김"}
    assert client.put(f"/api/documents/{doc}/review/fields", json=body).status_code == 409


def test_api_edit_persists_and_changes_regenerated_input(api, monkeypatch):
    client, store, doc = api
    done(store, doc)
    body = {"msds_index": 0, "path": "product.name", "action": "edit", "value": "새 이름", "reviewer": "김검수"}
    r = client.put(f"/api/documents/{doc}/review/fields", json=body)
    assert r.status_code == 200
    f = fields(by_no(r.json())[1])["product.name"]
    assert f["value"] == "새 이름" and f["original"] == "젯소"
    assert fields(by_no(client.get(f"/api/documents/{doc}/review").json())[1])["product.name"]["reviewer"] == "김검수"
    seen = {}
    monkeypatch.setattr(extract_app, "load_regen", lambda: None)
    monkeypatch.setattr(extract_app.regenerated, "regenerate_sections",
                        lambda d, mod: seen.update(name=d["msds"][0]["product"]["name"]) or [])
    assert client.get(f"/api/documents/{doc}/regenerated").status_code == 200
    assert seen["name"] == "새 이름"
    assert client.get(f"/api/documents/{doc}/result").json()["to21"]["msds"][0]["product"]["name"] == "젯소"


@pytest.mark.parametrize("body,code", [
    ({"msds_index": 0, "path": "nope", "action": "confirm", "reviewer": "김"}, 404),
    ({"msds_index": 0, "path": "meta.revision_no", "action": "edit", "value": "셋", "reviewer": "김"}, 422),
    ({"msds_index": 0, "path": "product.name", "action": "confirm", "reviewer": "  "}, 422),
    ({"msds_index": 0, "path": "product.name", "action": "edit", "reviewer": "김"}, 422),
    ({"msds_index": 0, "path": "product.name", "action": "삭제", "reviewer": "김"}, 422),
])
def test_api_rejects_bad_field_request(api, body, code):
    client, store, doc = api
    done(store, doc)
    assert client.put(f"/api/documents/{doc}/review/fields", json=body).status_code == code


def test_api_section_confirm(api):
    client, store, doc = api
    done(store, doc)
    body = {"msds_index": 0, "section": 3, "confirmed": True, "reviewer": "김"}
    r = client.put(f"/api/documents/{doc}/review/sections", json=body)
    assert r.status_code == 200 and r.json()["summary"]["sections_confirmed"] == 1
    assert client.put(f"/api/documents/{doc}/review/sections", json={**body, "section": 2, "msds_index": 5}).status_code == 404


def test_retry_sets_aside_review_of_previous_run(api):
    client, store, doc = api
    store.apply(doc, {"type": "plan", "msds_count": 1, "page_count": 1, "sections": [
        {"msds_index": 0, "section": 1, "title": "t", "pages": [1]}]})
    store.apply(doc, {"type": "section_done", "msds_index": 0, "section": 1, "ok": False, "reextracted": False,
                      "needs_review": True, "seconds": 1, "errors": []})
    done(store, doc)
    body = {"msds_index": 0, "path": "product.name", "action": "confirm", "reviewer": "김"}
    assert client.put(f"/api/documents/{doc}/review/fields", json=body).status_code == 200
    assert client.post(f"/api/documents/{doc}/retry").status_code == 202
    assert store.load_review(doc)["fields"] == {}
    assert list((store.root / doc).glob("review.이전-*.json"))
