"""B2 판정 서비스 시험: 넘김 기록 → 판정 버전 → 설명 → 검토 → 저장본 → 리포트. 약속 ①·④·⑤.

시험 전용 DB(judge_test)와 샘플 CSV 지식을 쓴다. 모델 서버는 부르지 않는다.
"""
import copy
import io
import threading
import unicodedata
from datetime import timedelta

import psycopg
import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from msds.api.judge_app import router
from msds.compliance.htodb.config import pg_kwargs
from msds.compliance.explain import engine_basis
from msds.compliance.htodb.csv_repo import CsvRepo
from msds.judge import explain as ex
from msds.judge import reports
from msds.judge import service as svc_mod
from msds.judge.service import Conflict, InvalidAction, JudgeService, NotFound, insert_handoff, writer_kwargs

from .fakes import make_handoff as handoff

JOB = "U-20261102-001"
AS_OF = "2026-11-02"
SHA = "a" * 64
FID = "m0/F2:HH_ACUTE_INHAL:분진·미스트"
ALL = dict(reports.ALL_INCLUDE)
NOTHING = {k: False for k in ALL}


@pytest.fixture(scope="module")
def admin(judge_database):
    with psycopg.connect(**{**pg_kwargs("admin"), "dbname": judge_database}, autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="module")
def pool(judge_database):
    p = ConnectionPool("", kwargs={**writer_kwargs(judge_database), "row_factory": dict_row}, min_size=1, max_size=6, open=True)
    yield p
    p.close()


@pytest.fixture
def svc(pool, admin):
    repo = CsvRepo()
    if not repo.available():
        pytest.skip("to21_sample CSV 없음")
    admin.execute("TRUNCATE extract.handoff, judge.handoff_state, judge.judgment, judge.explanation, judge.review_event, judge.snapshot RESTART IDENTITY")
    return JudgeService(pool=pool, provider=repo)


@pytest.fixture
def put(admin):
    def _put(body):
        insert_handoff(admin, body)
    return _put


@pytest.fixture
def api(svc):
    app = FastAPI()
    app.include_router(router)
    app.state.judge = svc
    return TestClient(app)


def edited(doc):
    d = copy.deepcopy(doc)
    classes = d["msds"][0]["hazard"]["classes"]
    d["msds"][0]["hazard"]["classes"] = [c for c in classes if c["class_code"] != "HH_SKIN_CORR"]
    return d


# ── 넘김 기록 → 판정 버전 ───────────────────────────────────────────────

def test_견본_넘김_기록이_계약을_통과한다(gold25, contract_errors):
    assert contract_errors("1-handoff.schema.json", handoff(gold25)) == []


def test_넘김_한_건이_판정_버전이_되고_화면_응답이_계약을_지킨다(svc, put, gold25, contract_errors):
    assert svc.status(JOB)["state"] == "판정 없음"
    put(handoff(gold25))
    assert svc.status(JOB)["state"] == "판정 중"
    svc.drain()
    st = svc.status(JOB)
    assert contract_errors("5-api.schema.json#/$defs/judgment_status", st) == []
    assert st["state"] == "판정 있음" and st["latest_version"] == 1 and st["pending_handoff"] is None
    assert st["explanations"]["total"] > 0 and st["explanations"]["done"] == st["explanations"]["total"]
    v = svc.view(JOB)
    assert contract_errors("5-api.schema.json#/$defs/judgment_view", v) == []
    assert v["consistency"]["as_of"] == AS_OF
    need = {f["id"] for r in v["consistency"]["results"] for f in r["findings"] if f["needs_explanation"]}
    assert set(v["explanations"]) == need
    assert all(e["status"] == "완료" and e["by"] == "template" and e["checked"] for e in v["explanations"].values())


def test_확인만_한_넘김은_새_버전을_만들지_않고_칸_상태만_갱신한다(svc, put, gold25, monkeypatch):
    put(handoff(gold25))
    svc.drain()
    monkeypatch.setattr(svc_mod, "judge", lambda *a, **k: pytest.fail("다시 계산하면 안 됨"))
    marks = [{"msds_index": 0, "field": "product.name", "status": "확인함"}]
    put(handoff(gold25, 2, reason="values_reviewed", field_status=marks))
    svc.drain()
    assert [x["version"] for x in svc.versions(JOB)] == [1]
    assert svc.status(JOB)["state"] == "판정 있음"
    assert svc.view(JOB)["field_status"] == marks


def test_값을_고치면_새_버전이_생기고_바뀐_항목을_알려준다(svc, put, gold25, contract_errors):
    put(handoff(gold25))
    svc.drain()
    put(handoff(edited(gold25), 2, reason="value_edited"))
    st = svc.status(JOB)
    assert st["pending_handoff"] == 2 and st["state"] == "판정 중" and st["latest_version"] == 1
    svc.drain()
    versions = svc.versions(JOB)
    for row in versions:
        assert contract_errors("5-api.schema.json#/$defs/version_list_item", row) == []
    assert [x["version"] for x in versions] == [2, 1]
    assert "m0/F2:HH_SKIN_CORR:-" in versions[0]["changed_findings"]
    old = svc.view(JOB, 1)
    assert old["is_latest"] is False and svc.view(JOB)["is_latest"] is True
    with pytest.raises(NotFound):
        svc.view(JOB, 9)


def test_값을_되돌리면_다시_계산하지_않고_새_버전으로_쌓는다(svc, put, gold25, monkeypatch):
    put(handoff(gold25))
    svc.drain()
    put(handoff(edited(gold25), 2))
    svc.drain()
    first = svc.view(JOB, 1)["consistency"]
    monkeypatch.setattr(svc_mod, "judge", lambda *a, **k: pytest.fail("이미 판정한 값"))
    put(handoff(gold25, 3))
    svc.drain()
    assert svc.view(JOB)["version"] == 3
    assert svc.view(JOB)["consistency"] == first


def test_기준일이_다르면_다시_판정한다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    put(handoff(gold25, 2, as_of="2026-12-01"))
    svc.drain()
    assert svc.view(JOB)["consistency"]["as_of"] == "2026-12-01" and svc.view(JOB)["version"] == 2


def test_저장된_판정은_같은_입력의_직접_계산과_같다(svc, put, gold25):
    from msds.compliance.judge import judge

    put(handoff(gold25))
    svc.drain()
    assert ex.canonical(svc.view(JOB)["consistency"]) == ex.canonical(judge(gold25, AS_OF, svc.provider))


def test_밀린_넘김은_가장_큰_번호만_판정한다(svc, put, gold25, admin):
    put(handoff(gold25))
    put(handoff(edited(gold25), 2))
    svc.drain()
    assert [x["handoff_seq"] for x in svc.versions(JOB)] == [2]
    assert admin.execute("SELECT state FROM judge.handoff_state WHERE job_id=%s AND handoff_seq=1", (JOB,)).fetchone()[0] == "건너뜀"


def test_추출_실패_항을_판정에_반영한다(svc, put, gold25):
    put(handoff(gold25, failed=[{"msds_index": 0, "section": 15, "error": "시간 초과"}]))
    svc.drain()
    rows = [f for f in svc.view(JOB)["consistency"]["results"][0]["findings"] if f["kind"] == "regulation" and f["verdict"] == "근거부족"]
    assert rows and all("추출 실패" in f["reason"] for f in rows)


def test_해시가_맞지_않으면_판정하지_않고_이유를_남긴다(svc, put, gold25):
    bad = handoff(gold25)
    bad["extraction_sha256"] = SHA
    put(bad)
    svc.drain()
    assert svc.status(JOB)["latest_version"] is None
    with pytest.raises(NotFound):
        svc.view(JOB)


def test_판정이_계속_실패하면_판정_실패로_보이고_이전_버전은_남는다(svc, put, gold25, admin, monkeypatch):
    put(handoff(gold25))
    svc.drain()

    def boom(*a, **k):
        raise ValueError("계산할 수 없는 값")

    monkeypatch.setattr(svc_mod, "judge", boom)
    put(handoff(edited(gold25), 2))
    for _ in range(svc_mod.MAX_ATTEMPTS):
        admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour' WHERE state = '실패'")
        svc.drain()
    st = svc.status(JOB)
    assert st["state"] == "판정 실패" and "ValueError" in st["error"] and "계산할 수 없는 값" not in st["error"] and st["pending_handoff"] == 2
    assert st["latest_version"] == 1 and svc.view(JOB)["version"] == 1
    admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour' WHERE state = '실패'")
    assert svc.claim_handoff() is None  # 한도를 넘으면 더 잡지 않는다


def test_다른_프로세스가_살아_있으면_그_작업을_빼앗지_않는다(svc, put, gold25, pool, judge_database):
    put(handoff(gold25))
    first = JudgeService(pool=pool, provider=svc.provider)
    second = JudgeService(pool=pool, provider=svc.provider)
    first.recover_if_alone()
    try:
        assert first.claim_handoff()["handoff_seq"] == 1
        with psycopg.connect(**pool.kwargs, autocommit=True) as other_session:  # 첫 프로세스의 잠금을 보는 다른 연결
            assert other_session.execute("SELECT pg_try_advisory_lock(%s) AS ok", (svc_mod.ALIVE_LOCK,)).fetchone()["ok"] is False
        second.recover_if_alone()
        try:
            assert second.claim_handoff() is None  # 임대 중인 작업을 다시 잡지 않는다
        finally:
            second._alive.close()
    finally:
        first._alive.close()
    third = JudgeService(pool=pool, provider=svc.provider)
    third.recover_if_alone()  # 모두 죽었으니 바로 이어받는다
    try:
        assert third.claim_handoff()["handoff_seq"] == 1
    finally:
        third._alive.close()


def test_A1_창구가_있으면_바깥에서_다시_잡지_않고_없으면_임시_창구를_쓴다(monkeypatch):
    import sys
    import types
    monkeypatch.setitem(sys.modules, "msds.common.model_gate", types.ModuleType("msds.common.model_gate"))
    assert isinstance(ex.default_gate(), ex._ClientGated)
    monkeypatch.setitem(sys.modules, "msds.common.model_gate", None)
    assert isinstance(ex.default_gate(), ex._SemaphoreGate)


def test_서버가_죽은_뒤_다시_켜면_잡던_일을_이어서_한다(svc, put, gold25, pool):
    put(handoff(gold25))
    assert svc.claim_handoff()["handoff_seq"] == 1
    assert svc.claim_handoff() is None  # 임대 중에는 다른 작업자가 못 잡는다
    assert svc.status(JOB)["state"] == "판정 중"
    again = JudgeService(pool=pool, provider=svc.provider)
    again.recover()
    again.drain()
    assert again.status(JOB)["state"] == "판정 있음"


def test_같은_넘김을_두_작업자가_동시에_잡아도_한_번만_나간다(svc, put, gold25):
    put(handoff(gold25))
    got = []
    threads = [threading.Thread(target=lambda: got.append(svc.claim_handoff())) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(x is not None for x in got) == 1


# ── 설명 ──────────────────────────────────────────────────────────────

def test_바뀌지_않은_항목은_설명을_다시_만들지_않는다(svc, put, gold25, admin):
    put(handoff(gold25))
    svc.drain()
    before = admin.execute("SELECT count(*) FROM judge.explanation").fetchone()[0]
    put(handoff(edited(gold25), 2))
    svc.drain()
    after = admin.execute("SELECT count(*) FROM judge.explanation").fetchone()[0]
    keys = svc.view(JOB)["explanations"]
    assert after - before <= 2 and len(keys) >= 1  # 피부 부식성 한 항목 + 그로 바뀐 표시 요소만


def test_모델_설명이_숫자를_지어내면_문장틀로_대체하고_이유를_남긴다(svc, put, gold25, pool, admin):
    calls = []

    def liar(system, user):
        calls.append(user)
        return {"summary": "ATEmix 123.456입니다.", "reasons": [], "basis": [], "used_numbers": [123.456]}, {"model": "fake", "errors": []}

    fake = JudgeService(pool=pool, provider=svc.provider, llm=liar)
    put(handoff(gold25))
    fake.drain()
    body = admin.execute("SELECT body FROM judge.explanation WHERE finding_id = %s", (FID,)).fetchone()[0]
    assert body["by"] == "template" and body["checked"] is True and "123.456" not in body["summary"]
    assert any("123.456" in x for x in body["check_failures"])
    assert len(calls) >= 2 and "검사에 걸렸습니다" in calls[1]


def test_검사를_통과한_모델_설명은_그대로_저장하고_창구를_거친다(svc, put, gold25, pool, contract_errors, admin):
    kinds = []

    class Gate:
        def slot_sync(self, kind):
            kinds.append(kind)
            return ex._SemaphoreGate(1).slot_sync(kind)

    def good(system, user):
        # 근거는 원문에 없는 쪽·항 번호를 지어낸다. 저장본 근거는 엔진이 요청에서 만든 것이어야 한다 (우진 결정 14)
        return {"summary": "흡입 형태가 다릅니다.", "reasons": ["MSDS와 계산의 형태가 다릅니다."],
                "basis": ["MSDS 9쪽 2항 기재"], "used_numbers": []}, {"model": "fake-1", "errors": []}

    fake = JudgeService(pool=pool, provider=svc.provider, llm=good, gate=Gate())
    put(handoff(gold25))
    fake.drain()
    e = fake.view(JOB)["explanations"][FID]
    assert e["by"] == "llm" and e["summary"] == "흡입 형태가 다릅니다." and e["checked"]
    assert kinds and set(kinds) == {"explain"}
    stored = admin.execute("SELECT body FROM judge.explanation WHERE finding_id=%s", (FID,)).fetchone()[0]
    assert contract_errors("4-explanation.schema.json#/$defs/stored", stored) == []
    request = admin.execute("SELECT request FROM judge.explanation WHERE finding_id=%s", (FID,)).fetchone()[0]
    assert contract_errors("4-explanation.schema.json#/$defs/request", request) == []
    assert stored["basis"] == engine_basis(request) and stored["basis"] and "9쪽" not in " ".join(stored["basis"])


def test_모델이_응답하지_않아도_저장_흐름은_멈추지_않는다(svc, put, gold25, pool):
    fake = JudgeService(pool=pool, provider=svc.provider, llm=lambda s, u: (None, {"model": "x", "errors": ["timeout"]}))
    put(handoff(gold25))
    fake.drain()
    assert fake.view(JOB)["explanations"][FID]["by"] == "template"


# ── 검토 ──────────────────────────────────────────────────────────────

def test_검토는_이어지고_의견은_상태를_바꾸지_않는다(svc, put, gold25, contract_errors):
    put(handoff(gold25))
    svc.drain()
    s = svc.add_review(JOB, FID, "의견", "확인 중", "김검수", 1)
    assert s["status"] == "미검토" and s["comment"] == "확인 중"
    assert FID in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]  # 의견만으로는 처리가 아니다
    s = svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    assert s["status"] == "불일치 확정" and s["history_count"] == 2
    assert FID not in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]
    s = svc.add_review(JOB, FID, "의견", "추가 의견", "이검수", 1)
    assert s["status"] == "불일치 확정" and s["comment"] is None and s["reviewer"] == "김검수" and s["history_count"] == 3
    assert contract_errors("5-api.schema.json#/$defs/review_state", s) == []
    s = svc.add_review(JOB, FID, "되돌리기", None, "김검수", 1)
    assert s["status"] == "미검토" and s["stale"] is False and s["history_count"] == 4
    rows = svc.history(JOB)
    assert len(rows) == 4 and rows[0]["action"] == "되돌리기" and rows[0]["target"] == "급성독성물질(흡입)" and rows[0]["area"] == "2항"
    for row in rows:
        assert contract_errors("5-api.schema.json#/$defs/history_entry", row) == []


def test_옛_버전을_보고_검토하면_막는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    put(handoff(edited(gold25), 2))
    svc.drain()
    with pytest.raises(Conflict) as e:
        svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    assert e.value.latest == 2
    with pytest.raises(NotFound):
        svc.add_review(JOB, "m0/F2:NOPE:-", "확인", None, "김검수", 2)


def test_재판정해도_검토가_남고_값이_바뀐_항목만_다시_확인을_요청한다(svc, put, gold25):
    skin = "m0/F2:HH_SKIN_CORR:-"
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, skin, "확인", None, "김검수", 1)
    svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    # 표시 요소·9항은 그대로 두고 11항 값만 바꾸면 FID 는 판정이 같다
    put(handoff(edited(gold25), 2))
    svc.drain()
    reviews = svc.view(JOB)["reviews"]
    assert reviews[FID]["status"] == "불일치 확정" and reviews[FID]["stale"] is False
    assert reviews[skin]["status"] == "확인" and reviews[skin]["stale"] is True
    assert svc.view(JOB)["version"] == 2 and len(svc.history(JOB)) == 2


def test_계정_권한이_약속을_지킨다(svc, put, gold25, pool):
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    for sql in ("UPDATE judge.review_event SET reviewer = 'x'", "DELETE FROM judge.review_event",
                "UPDATE judge.judgment SET judge_key = 'x'", "DELETE FROM judge.snapshot",
                "INSERT INTO extract.handoff (job_id, handoff_seq, reason, as_of, extraction_sha256, payload_json, created_at)"
                " VALUES ('x', 1, 'rerun', '2026-11-03', 'x', '{}', now())",
                "UPDATE extract.handoff SET payload_json = '{}'"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), pool.connection() as conn:
            conn.execute(sql)


# ── 저장 ──────────────────────────────────────────────────────────────

def test_미검토가_남아도_저장되고_다시_저장하면_새_번호다(svc, put, gold25, contract_errors):
    put(handoff(gold25))
    svc.drain()
    o = svc.save_overview(JOB)
    assert contract_errors("5-api.schema.json#/$defs/save_overview", o) == []
    assert FID in o["reviews"]["unreviewed_ids"] and o["values"]["state"] == "미검수" and svc.summary([JOB])[0]["data_grade"] == "실버"
    first = svc.save_snapshot(JOB, "김검수", 1, "미검토 포함")
    assert contract_errors("5-api.schema.json#/$defs/snapshot", first) == []
    assert first["snapshot_no"] == 1 and first["counts"]["미검토"] == len(o["reviews"]["unreviewed_ids"]) > 0
    second = svc.save_snapshot(JOB, "김검수", 1, None)
    assert second["snapshot_no"] == 2
    assert [s["snapshot_no"] for s in svc.save_overview(JOB)["snapshots"]] == [2, 1]
    assert svc.status(JOB)["saved_snapshot"] == 2


def test_저장_뒤_검토_처리를_하면_저장_개요의_마지막_처리_번호가_저장본과_달라진다(svc, put, gold25, contract_errors):
    # 판정 버전·넘김 번호가 그대로라 화면이 "저장본이 최신"이라 하고, 리포트는 옛 저장본(처리 전)으로 나가던 일 (#162 검토)
    put(handoff(gold25))
    svc.drain()
    assert svc.save_overview(JOB)["last_review_event_id"] is None
    svc.add_review(JOB, FID, "의견", "확인 중", "김검수", 1)
    snap = svc.save_snapshot(JOB, "김검수", 1, None)
    o = svc.save_overview(JOB)
    assert contract_errors("5-api.schema.json#/$defs/save_overview", o) == []
    assert o["last_review_event_id"] == snap["last_review_event_id"] is not None
    svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    after = svc.save_overview(JOB)
    assert after["last_review_event_id"] > snap["last_review_event_id"]
    assert (after["version"], after["handoff_seq"]) == (o["version"], o["handoff_seq"])  # 이 둘만 보면 바뀐 것을 모른다


def test_옛_버전을_보고_저장하면_막는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    put(handoff(edited(gold25), 2))
    svc.drain()
    with pytest.raises(Conflict):
        svc.save_snapshot(JOB, "김검수", 1, None)


def test_모두_처리하고_칸도_확인해야_골드다(svc, put, gold25):
    doc = {"doc": gold25["doc"], "msds": [{"meta": {"last_revision_date": "2022-06-29"}, "product": {"name": "황산"},
                                           "composition": {"type": "혼합물"}, "components": []}]}
    put(handoff(doc))
    svc.drain()
    for fid in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]:
        svc.add_review(JOB, fid, "예외 승인", "확인함", "김검수", 1)
    assert svc.save_overview(JOB)["reviews"]["unreviewed_ids"] == []
    svc.save_snapshot(JOB, "김검수", 1, None)
    assert svc.summary([JOB])[0]["data_grade"] == "실버"  # 칸 미검수
    leaves = ["meta.last_revision_date", "product.name", "composition.type"]
    marks = [{"msds_index": 0, "field": k, "status": "확인함"} for k in leaves]
    put(handoff(doc, 2, reason="values_reviewed", field_status=marks, fields_total=3))
    svc.drain()
    svc.save_snapshot(JOB, "김검수", 1, None)
    o = svc.save_overview(JOB)
    assert o["values"]["model_as_is"] == 0 and o["values"]["state"] == "완료" and svc.summary([JOB])[0]["data_grade"] == "골드"
    assert svc.summary([JOB])[0]["data_grade"] == "골드"


def test_동시에_저장해도_번호가_겹치지_않는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    out, errors = [], []

    def go():
        try:
            out.append(svc.save_snapshot(JOB, "김검수", 1, None)["snapshot_no"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and sorted(out) == [1, 2, 3, 4, 5]


# ── 화면 API ───────────────────────────────────────────────────────────

def test_API_경로와_오류_코드(api, svc, put, gold25, contract_errors):
    assert api.get(f"/api/judgments/{JOB}/status").json()["state"] == "판정 없음"
    assert api.get(f"/api/judgments/{JOB}").status_code == 404
    assert api.get(f"/api/judgments/{JOB}/save-overview").status_code == 404
    assert api.get("/api/judgments/bad-id/status").status_code == 422
    put(handoff(gold25))
    svc.drain()
    assert api.get(f"/api/judgments/{JOB}").json()["version"] == 1
    assert api.get(f"/api/judgments/{JOB}?version=9").status_code == 404
    assert api.get(f"/api/judgments/{JOB}?version=0").status_code == 422
    assert len(api.get(f"/api/judgments/{JOB}/versions").json()) == 1

    review = {"finding_id": FID, "action": "예외 승인", "reviewer": "김검수", "seen_version": 1}
    assert api.post(f"/api/judgments/{JOB}/reviews", json=review).status_code == 422  # 의견 없음
    assert api.post(f"/api/judgments/{JOB}/reviews", json={**review, "comment": "   "}).status_code == 422
    assert contract_errors("5-api.schema.json#/$defs/review_event_request", {**review, "comment": "공급사 확인"}) == []
    r = api.post(f"/api/judgments/{JOB}/reviews", json={**review, "comment": "공급사 확인"})
    assert r.status_code == 201 and r.json()["action"] == "예외 승인"
    assert contract_errors("5-api.schema.json#/$defs/review_event", r.json()) == []
    assert api.post(f"/api/judgments/{JOB}/reviews", json={**review, "comment": "x", "extra": 1}).status_code == 422
    assert api.post(f"/api/judgments/{JOB}/reviews", json={**review, "comment": "x", "finding_id": "m0/F2:NOPE:-"}).status_code == 404
    assert api.post(f"/api/judgments/{JOB}/reviews", json={**review, "reviewer": ""}).status_code == 422

    put(handoff(edited(gold25), 2))
    svc.drain()
    stale = api.post(f"/api/judgments/{JOB}/reviews", json={**review, "comment": "x"})
    assert stale.status_code == 409 and stale.json()["detail"]["latest_version"] == 2
    assert api.post(f"/api/judgments/{JOB}/snapshots", json={"reviewer": "김검수", "seen_version": 1}).status_code == 409
    saved = api.post(f"/api/judgments/{JOB}/snapshots", json={"reviewer": "김검수", "seen_version": 2})
    assert saved.status_code == 201 and contract_errors("5-api.schema.json#/$defs/snapshot", saved.json()) == []


def test_목록_요약은_여러_작업을_한_번에_돌려준다(api, svc, put, gold25, contract_errors):
    other = "U-20261102-002"
    put(handoff(gold25))
    svc.drain()
    rows = api.get("/api/judgments/summary", params={"job_ids": f"{JOB},{other}"}).json()
    for row in rows:
        assert contract_errors("5-api.schema.json#/$defs/judgment_batch_item", row) == []
    assert [r["job_id"] for r in rows] == [JOB, other]
    assert rows[0]["state"] == "판정 있음" and rows[0]["unreviewed"] > 0 and rows[1]["state"] == "판정 없음"
    assert api.get("/api/judgments/summary", params={"job_ids": "bad"}).status_code == 422


def test_리포트_네_가지_형식(api, svc, put, gold25, contract_errors):
    put(handoff(gold25))
    svc.drain()
    url = f"/api/judgments/{JOB}/reports"
    assert contract_errors("5-api.schema.json#/$defs/report_request", {"format": "pdf", "snapshot_no": None, "include": ALL}) == []

    page = api.post(url, json={"format": "html", "include": ALL})
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "급성독성물질(흡입)" in page.text and "재생성 MSDS" in page.text and "만들지 못함" not in page.text

    only = api.post(url, json={"format": "html", "include": {**NOTHING, "findings_2": True}}).text
    assert "2항 판정" in only and "재생성 MSDS" not in only

    pdf = api.post(url, json={"format": "pdf", "include": ALL})
    assert pdf.headers["content-type"] == "application/pdf" and "filename*=UTF-8''" in pdf.headers["content-disposition"]
    assert len(pdf.content) < 1_500_000
    doc = pymupdf.open(stream=pdf.content, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    assert doc.page_count >= 1 and "급성독성물질" in text and "황산" in text

    xlsx = api.post(url, json={"format": "xlsx", "include": ALL})
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert {"2항 판정", "15항 판정", "성분", "검토 이력"} <= set(wb.sheetnames)
    assert wb["2항 판정"]["B2"].value and wb["15항 판정"].max_row > 1

    data = api.post(url, json={"format": "json", "include": ALL}).json()
    assert data["contract"] == "report/1" and data["extraction"]["doc"]["doc_id"] == "T21-025"
    assert api.post(url, json={"format": "doc", "include": ALL}).status_code == 422
    assert api.post(url, json={"format": "pdf", "snapshot_no": 9, "include": ALL}).status_code == 404


def test_저장본_리포트는_저장_뒤_변경을_담지_않는다(api, svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, FID, "의견", "저장 전 의견", "김검수", 1)
    svc.save_snapshot(JOB, "김검수", 1, None)
    svc.add_review(JOB, FID, "의견", "저장 뒤 의견", "김검수", 1)
    put(handoff(edited(gold25), 2))
    svc.drain()
    url = f"/api/judgments/{JOB}/reports"
    pinned = api.post(url, json={"format": "json", "snapshot_no": 1, "include": ALL}).json()
    assert pinned["version"] == 1 and [e["comment"] for e in pinned["events"]] == ["저장 전 의견"]
    assert pinned["extraction"]["msds"][0]["hazard"]["classes"] == gold25["msds"][0]["hazard"]["classes"]
    now = api.post(url, json={"format": "json", "include": ALL}).json()
    assert now["version"] == 2 and len(now["events"]) == 2


def test_위험한_글자는_리포트에서_무력화한다(svc, put, gold25, api):
    doc = copy.deepcopy(gold25)
    doc["msds"][0]["product"]["name"] = "<script>alert(1)</script>"
    put(handoff(doc))
    svc.drain()
    svc.add_review(JOB, FID, "의견", "=HYPERLINK(\"http://x\")", "김검수", 1)
    url = f"/api/judgments/{JOB}/reports"
    assert "<script>alert" not in api.post(url, json={"format": "html", "include": ALL}).text
    wb = load_workbook(io.BytesIO(api.post(url, json={"format": "xlsx", "include": ALL}).content))
    cells = [c.value for row in wb["검토 이력"].iter_rows(min_row=2) for c in row]
    assert "=HYPERLINK(\"http://x\")" in cells  # 글자는 그대로 두고 수식으로만 만들지 않는다
    assert all(c.data_type != "f" for ws in wb for row in ws.iter_rows() for c in row)


def test_임대_시간은_재시도_간격보다_길다():
    assert svc_mod.LEASE > svc_mod.RETRY_AFTER and svc_mod.EXPLAIN_LEASE >= timedelta(minutes=5)


# ── 독립 검증에서 재현된 결함 ───────────────────────────────────────────

class FlakyRepo(CsvRepo):
    """연결 확인은 되는데 조회 중에 끊기는 지식DB."""
    down = True

    def regulations(self, chem_id):
        if self.down:
            raise ConnectionError("too many clients")
        return super().regulations(chem_id)


def test_조회_중_지식DB_장애는_근거부족이_아니라_판정_실패다(svc, put, gold25, pool, admin):
    repo = FlakyRepo()
    flaky = JudgeService(pool=pool, provider=repo)
    put(handoff(gold25))
    flaky.drain()
    assert flaky.status(JOB)["latest_version"] is None
    st = flaky.status(JOB)
    assert st["state"] == "판정 실패" and st["error"] == svc_mod.TRANSIENT_MESSAGE


def test_지식DB가_복구되면_시도_한도와_상관없이_자동으로_판정한다(svc, put, gold25, pool, admin):
    repo = FlakyRepo()
    flaky = JudgeService(pool=pool, provider=repo)
    put(handoff(gold25))
    for _ in range(svc_mod.MAX_ATTEMPTS + 2):  # 한도보다 오래 끊겨 있어도
        admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour' WHERE state = '실패'")
        flaky.drain()
        assert flaky.status(JOB)["state"] == "판정 실패"
    assert admin.execute("SELECT attempts FROM judge.handoff_state WHERE job_id=%s", (JOB,)).fetchone()[0] < svc_mod.MAX_ATTEMPTS
    assert flaky.claim_handoff() is None  # 30초 간격은 지킨다
    repo.down = False
    admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour' WHERE state = '실패'")
    flaky.drain()
    st = flaky.status(JOB)
    assert st["state"] == "판정 있음" and st["latest_version"] == 1 and st["error"] is None


class BrokenRepo(CsvRepo):
    def regulations(self, chem_id):
        raise ValueError("코드 문제")


def test_조회_안의_일반_오류는_연결_장애가_아니라_한도에서_멈춘다(svc, put, gold25, pool, admin):
    broken = JudgeService(pool=pool, provider=BrokenRepo())
    put(handoff(gold25))
    for _ in range(svc_mod.MAX_ATTEMPTS):
        admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour' WHERE state = '실패'")
        broken.drain()
    assert broken.status(JOB)["state"] == "판정 실패" and broken.status(JOB)["error"] != svc_mod.TRANSIENT_MESSAGE
    admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour' WHERE state = '실패'")
    assert broken.claim_handoff() is None


def test_지식DB_적재_차수_문제는_이유를_보이고_해결되면_판정한다(svc, put, gold25, admin, monkeypatch):
    real = svc_mod.current_versions

    def boom(*a):
        raise svc_mod.KnowledgeUnavailable("지식DB 적재 차수가 하나로 정해지지 않음")

    monkeypatch.setattr(svc_mod, "current_versions", boom)
    put(handoff(gold25))
    svc.drain()
    st = svc.status(JOB)
    assert st["state"] == "판정 실패" and "적재 차수" in st["error"]
    monkeypatch.setattr(svc_mod, "current_versions", real)
    admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour' WHERE state = '실패'")
    svc.drain()
    assert svc.status(JOB)["state"] == "판정 있음"


@pytest.mark.parametrize("exc", [RuntimeError, ValueError, KeyError])
def test_다른_오류의_원문도_상태_API로_나가지_않는다(svc, put, gold25, monkeypatch, exc):
    def boom(*a, **k):
        raise exc("설정 없음: /home/x/.env host=10.0.0.9 user=kdb")

    monkeypatch.setattr(svc_mod, "judge", boom)
    put(handoff(gold25))
    svc.drain()
    svc_error = svc.status(JOB)["error"] or ""
    assert not any(x in svc_error for x in (".env", "10.0.0.9", "kdb"))


def test_쿼리_제한_시간_초과는_연결_장애가_아니라_한도에서_멈춘다():
    from msds.compliance.judge import is_connection_error
    assert not is_connection_error(psycopg.errors.QueryCanceled("canceling statement due to statement timeout"))
    assert not is_connection_error(psycopg.errors.ProgramLimitExceeded("too big"))
    assert is_connection_error(psycopg.errors.TooManyConnections("too many clients")) and is_connection_error(psycopg.errors.AdminShutdown("shutdown"))
    assert is_connection_error(psycopg.OperationalError("connection failed")) and is_connection_error(ConnectionError())


def test_접속_정보는_상태_API로_나가지_않는다(svc, put, gold25, monkeypatch):
    def boom(*a, **k):
        raise psycopg.OperationalError('connection to server at "10.0.0.9", port 5433 failed: password for user "kdb"')

    monkeypatch.setattr(svc_mod, "judge", boom)
    put(handoff(gold25))
    svc.drain()
    st = svc.status(JOB)
    assert st["state"] == "판정 실패" and not any(x in st["error"] for x in ("10.0.0.9", "5433", "kdb"))


def test_본문의_작업_번호가_표와_다르면_다른_작업에_저장하지_않는다(svc, put, gold25, admin):
    body = handoff(gold25)
    put(body)
    admin.execute("UPDATE extract.handoff SET payload_json = jsonb_set(payload_json, '{job_id}', '\"U-다른작업\"') WHERE job_id = %s", (JOB,))
    svc.drain()
    assert svc.status(JOB)["state"] == "판정 실패"
    assert admin.execute("SELECT count(*) FROM judge.judgment").fetchone()[0] == 0


@pytest.mark.parametrize("bad", [[], "x", [1]])
def test_본문이_객체가_아닌_넘김도_뒤_작업을_막지_않는다(svc, put, gold25, admin, bad):
    admin.execute("INSERT INTO extract.handoff (job_id, handoff_seq, reason, as_of, extraction_sha256, payload_json, created_at)"
                  " VALUES ('U-망가짐', 1, 'rerun', '2026-11-03', 'x', %s, now())", (Jsonb(bad),))
    put(handoff(gold25))
    svc.drain()  # 망가진 줄을 멈추면 그 차례는 빈손으로 끝난다. 작업자는 다음 차례에 뒤 작업을 잡는다
    svc.drain()
    assert svc.status("U-망가짐")["state"] == "판정 실패"
    assert svc.status(JOB)["state"] == "판정 있음"


def test_해시가_다른_넘김은_다시_해도_같으니_바로_멈춘다(svc, put, gold25, admin):
    put({**handoff(gold25), "extraction_sha256": SHA})
    svc.drain()
    st = svc.status(JOB)
    assert st["state"] == "판정 실패" and "extraction_sha256" in st["error"]
    admin.execute("UPDATE judge.handoff_state SET finished_at = now() - interval '1 hour'")
    assert svc.claim_handoff() is None


def test_임대가_끝난_늦은_작업자는_완료된_설명을_덮어쓰지_못한다(svc, put, gold25, pool, admin):
    llm = JudgeService(pool=pool, provider=svc.provider, llm=lambda s, u: ({"summary": "늦은 줄입니다.", "reasons": [], "basis": [], "used_numbers": []}, {"model": "fake", "errors": []}))
    put(handoff(gold25))
    svc.judge_step()
    slow = svc.claim_explanation()
    admin.execute("UPDATE judge.explanation SET taken_at = now() - %s WHERE finding_id=%s AND input_sha256=%s",
                  (svc_mod.EXPLAIN_LEASE * 2, slow["finding_id"], slow["input_sha256"]))
    fast = svc.claim_explanation()
    assert (fast["finding_id"], fast["input_sha256"]) == (slow["finding_id"], slow["input_sha256"])
    llm.process_explanation(fast)
    before = admin.execute("SELECT body FROM judge.explanation WHERE finding_id=%s AND input_sha256=%s", (slow["finding_id"], slow["input_sha256"])).fetchone()[0]
    svc.process_explanation(slow)  # 문장틀로 늦게 끝남
    after = admin.execute("SELECT body FROM judge.explanation WHERE finding_id=%s AND input_sha256=%s", (slow["finding_id"], slow["input_sha256"])).fetchone()[0]
    assert after == before


def test_서비스는_관리자_비밀번호_없이_시작한다(monkeypatch):
    real = svc_mod.setting
    monkeypatch.setattr("msds.compliance.htodb.config.setting", lambda k, *d: (_ for _ in ()).throw(RuntimeError(k)) if k == "HTODB_PG_PASSWORD" else real(k, *d))
    assert writer_kwargs("x")["user"] == "judge_writer"


@pytest.mark.parametrize("summary, bad", [(": ", True), (":", True), ("- 1.", True), ("", True),
                                          ("흡인유해성은 동점도 값이 없어 판정하지 못했습니다.", False)])
def test_글이_없는_요약은_검사에_걸린다(summary, bad):
    # 실제 모델(Qwen3.6 35B)이 근거부족·경계 줄에서 요약을 ": "로 자주 보냈다. 공백만 막던 검사를 통과해 화면에 ':'만 나갔다
    req = {"finding": {"section": "2", "kind": "class", "verdict": "근거부족", "msds": {"category": "1"}, "expected": {}}}
    assert ("요약에 글이 없음" in ex.claim_problems({"summary": summary}, req)) is bad
    fixed = {"finding": {**req["finding"], "type": next(iter(ex.engine._DIRECTION_TYPES))}}
    assert "요약에 글이 없음" not in ex.claim_problems({"summary": ": "}, fixed)  # 과소·과대 요약은 문장틀로 덮어쓴다


_M013 = "포름알데히드, polymers with branched 4-nonylphenol and ethylenediamine"


@pytest.mark.parametrize("text, bad", [
    # 실제 모델 응답(T21-M013, 2026-11-04): 한 성분을 둘로 나눔
    (f"포름알데히드와 polymers with branched 4-nonylphenol and ethylenediamine는 지식DB에 분류 정보가 없습니다.", True),
    ("자료가 없는 성분은 나프탈렌, 포름알데히드 및 polymers with branched 4-nonylphenol입니다.", True),
    ("포름알데히드과 polymers는 자료가 없습니다.", True),
    ("포름알데히드이나 polymers 중 하나는 자료가 없습니다.", True),
    ("포름알데히드 또는 polymers 자료가 없습니다.", True),
    (f"계산에서 빠진 성분은 나프탈렌, {_M013}입니다.", False),   # 이름을 그대로 쓰면 통과
    ("나프탈렌과 포름알데히드 성분은 분류가 없습니다.", False),   # 줄여 쓴 것은 나눈 것이 아니다
    ("파라포름알데히드와 polymers 자료는 없습니다.", False),       # 다른 이름 안에 든 글자
    ("MSDS는 구분 1과 2를 함께 적었습니다.", False),               # '1, 2,4-트리메틸벤젠'의 앞부분 '1'은 보지 않는다
    ("나프탈렌은 해당 분류가 없습니다.", False),
])
def test_쉼표가_든_성분_이름을_나누면_검사에_걸린다(text, bad):
    req = {"finding": {"section": "2", "kind": "class", "verdict": "근거부족", "msds": {"category": "1C"}, "expected": {}},
           "trace": {"inputs": [{"name": "나프탈렌"}, {"name": _M013}, {"name": "1, 2,4-트리메틸벤젠"}, {"name": 5}, {"name": ["a, b"]}, None, "x"]}}
    assert any(p.startswith("성분 이름") for p in ex.claim_problems({"summary": "피부 부식성은 판정하지 못했습니다.", "reasons": [text]}, req)) is bad


def test_앞부분이_따로_있는_성분이면_나눠_써도_통과한다():
    req = {"finding": {"section": "2", "kind": "class", "verdict": "근거부족", "msds": {}, "expected": {}},
           "trace": {"inputs": [{"name": "포름알데히드"}, {"name": _M013}]}}
    assert not ex.claim_problems({"summary": "판정하지 못했습니다.", "reasons": ["포름알데히드와 polymers 자료는 없습니다."]}, req)


@pytest.mark.parametrize("section, verdict, text, bad", [
    ("15", "경계", "유독물질은 MSDS가 해당으로 더 강하게 적었습니다.", True),   # 실제 모델 응답(T21-M005 유독물질, 2026-11-04)
    ("15", "경계", "MSDS는 기준보다 더 높게 적었습니다.", True),
    ("15", "경계", "MSDS가 과기재했습니다.", True),
    ("15", "불일치", "유독물질은 MSDS가 해당으로 더 강하게 적었습니다.", False),
    ("2", "경계", "유독물질은 MSDS가 해당으로 더 강하게 적었습니다.", False),
    # 경계를 바르게 설명한 말은 걸지 않는다 (검증자가 찾은 오탐)
    ("15", "경계", "함량 상한 43.9%가 기준 25%보다 더 높게 걸쳐 있어 사람 확인이 필요합니다.", False),
    ("15", "경계", "과기재인지 규제 누락인지 확정할 수 없습니다.", False),
    ("15", "경계", "과기재로 단정할 수 없어 사람 확인이 필요합니다.", False),
    ("15", "경계", "하한 0%는 기준보다 더 낮게 걸쳐 있습니다.", False),
    ("15", "경계", "MSDS가 과소기재했습니다.", True),
    ("15", "경계", "MSDS는 과대분류했습니다.", True),
    ("15", "경계", "MSDS가 과소 분류로 적었습니다.", True),
    ("15", "경계", "MSDS가 더 약하게 적었습니다.", True),
    ("15", "경계", "MSDS가 기준을 낮게 기재했습니다.", True),
    ("15", "경계", "기준을 높게 적용하면 해당일 수 있습니다.", False),
    ("15", "경계", "과대분류인지는 함량에 따라 갈립니다.", False),
    ("15", "경계", "과기재로 볼 수 없습니다.", False),
    ("15", "경계", "과기재 여부는 실제 함량을 봐야 합니다.", False),
    ("15", "경계", "과기재라고 단정할 수 없습니다.", False),
    ("15", "경계", "과소 기재 여부를 정하기 어렵습니다.", False),
    ("15", "경계", "지식DB 기준이 더 엄격하게 정해져 있어 함량에 따라 갈립니다.", False),
    # 예외가 쉼표·다음 절까지 보면 놓치던 단정 (최종 검증자가 찾음)
    ("15", "경계", "MSDS가 과기재했으며, 해당 여부는 함량에 따라 갈립니다.", True),
    ("15", "경계", "MSDS가 과기재했으며 이 때문에 판단이 어렵습니다.", True),
    ("15", "경계", "MSDS가 과대분류했고 규제 여부와 무관합니다.", True),
    ("15", "경계", "함량 상한이 기준보다 높게 기재되어 있어 해당일 수 있습니다.", False),
    ("15", "경계", "MSDS가 더 강하게 적었는지 단정할 수 없습니다.", False),
])
def test_15항_경계_줄에_방향을_말하면_검사에_걸린다(section, verdict, text, bad):
    # 15항 경계는 함량에 따라 갈린다는 뜻이라 과기재·과소 방향이 없다
    exp = {"applicable": "경계"} if section == "15" else {}
    req = {"finding": {"section": section, "kind": "regulation" if section == "15" else "class", "verdict": verdict,
                       "msds": {"applicable": "해당"} if section == "15" else {}, "expected": exp}}
    # 15항 경계 요약은 문장틀로 덮어쓰므로(_fixed_summary) 모델 글인 이유 문장에서 본다
    assert any(p.startswith("경계 줄에 방향") for p in ex.claim_problems({"summary": "확인이 필요합니다.", "reasons": [text]}, req)) is bad


def test_설명_모델_태그는_따로_없으면_추출_모델을_따른다(monkeypatch):
    # 48GB 태그로 띄운 서버를 80GB 기본 태그로 부르지 않게. 한 포트 실행 스크립트가 sed로 하던 일
    from msds.extract.client import load_model_config
    seen = []
    monkeypatch.setattr("msds.extract.client.load_model_config", lambda t: seen.append(t) or {"base_url_env": "NO_SUCH_URL_ENV"})
    monkeypatch.delenv("NO_SUCH_URL_ENV", raising=False)
    for explain, service, want in [(None, None, ex.EXPLAIN_MODEL_DEFAULT), (None, "qwen36_35b_runpod_48g", "qwen36_35b_runpod_48g"),
                                   ("gpt", "qwen36_35b_runpod_48g", "gpt"), ("", "qwen36_35b_runpod_48g", "qwen36_35b_runpod_48g")]:
        for k, v in (("MSDS_EXPLAIN_MODEL", explain), ("MSDS_SERVICE_MODEL", service)):
            monkeypatch.setenv(k, v) if v is not None else monkeypatch.delenv(k, raising=False)
        assert ex.make_llm() is None and seen[-1] == want


def test_설명_모델_태그는_env를_읽은_뒤에_정한다(monkeypatch, capsys):
    # 판정 앱을 혼자 띄우면 msds.extract.client를 아직 안 읽었다. 가져올 때 load_dotenv가 .env를 읽으므로 태그는 그 뒤에 읽어야 한다
    import sys
    import dotenv
    for k in ("MSDS_EXPLAIN_MODEL", "MSDS_SERVICE_MODEL"):
        monkeypatch.delenv(k, raising=False)
    # 시험이 끝나면 원래 모듈·환경으로 돌아온다 (혼자 돌려도, 다른 시험과 같이 돌려도 새지 않게 모두 monkeypatch로)
    import msds.extract
    monkeypatch.delitem(sys.modules, "msds.extract.client", raising=False)
    monkeypatch.delattr(msds.extract, "client", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: monkeypatch.setenv("MSDS_SERVICE_MODEL", "태그_env파일") or True)
    assert ex.make_llm() is None  # 없는 태그라 설정을 못 읽고 문장틀로 간다
    assert "태그_env파일" in capsys.readouterr().out  # .env에서 온 태그로 설정을 찾았다

def test_설명_모델은_문법_강제_없이_받는다(monkeypatch):
    # json_schema 강제로 받으면 실제 모델이 요약을 ": "로 자주 채웠다 (T-26). 설명만 바꾸고 같은 모델을 쓰는 추출에는 번지지 않아야 한다
    from msds.extract.client import ChatClient, load_model_config
    tag = ex.EXPLAIN_MODEL_DEFAULT
    cfg = load_model_config(tag)
    monkeypatch.setenv(cfg["base_url_env"], "http://127.0.0.1:9/v1")
    if cfg.get("api_key_env"):
        monkeypatch.setenv(cfg["api_key_env"], "test")
    monkeypatch.setenv("MSDS_EXPLAIN_MODEL", tag)
    llm = ex.make_llm()
    assert llm is not None and llm.client.cfg["structured"] == ["none"]
    assert load_model_config(tag)["structured"][0] == "json_schema"
    # 설명 호출이 성공해 방식을 기억해도(client.py의 기록과 같은 동작) 추출 클라이언트가 쓰는 공용 기억은 그대로다
    monkeypatch.setattr(ChatClient, "_working_mode", {})
    llm.client._working_mode[llm.client.model] = "none"
    assert ChatClient._working_mode == {}
    assert ChatClient(cfg)._working_mode.get(llm.client.model) is None


@pytest.mark.parametrize("text", [
    "MSDS 기재와 계산 결과가 일치합니다.", "두 값이 동일합니다.", "불일치입니다.", "차이가 없습니다.", "산출한 분류는 구분 3입니다."])
def test_판정과_반대되는_설명은_검사에_걸린다(text):
    req = {"finding": {"section": "2", "kind": "class", "verdict": "경계", "msds": {"category": "2"}, "expected": {}}}
    assert ex.claim_problems({"summary": text}, req)


@pytest.mark.parametrize("text", [
    "이 항목은 일치 판정입니다.", "일치로 볼 수 있습니다.", "MSDS 기재 내용은 계산 결과와 부합합니다.", "두 값은 서로 맞습니다.",
    "MSDS의 구분이 계산 결과와 동일하므로 문제가 없습니다.", "기재된 분류는 적절합니다.", "혼합물의 분류는 구분 1입니다.", "구분 1이 산출되었습니다.",
    "계산 결과와 일치하는 것으로 확인되었습니다.", "양쪽 값이 서로 일치해 수정할 필요가 없습니다.", "두 값 사이에 차이는 없습니다.", "MSDS의 분류는 올바릅니다.",
    "MSDS 기재에는 오류가 없습니다.", "이 줄은 정상입니다.", "본 항목은 적합합니다.", "계산 결과와 어긋나지 않습니다.", "이상이 없습니다."])
def test_불일치_줄에_맞다고_하는_설명은_검사에_걸린다(text):
    req = {"finding": {"section": "2", "kind": "class", "verdict": "불일치", "msds": {"category": "2"}, "expected": {"low": "3", "high": "3"}}}
    assert ex.claim_problems({"summary": text}, req)


@pytest.mark.parametrize("text", ["동일하지 않습니다.", "부적절합니다.", "일치한다고 보기 어렵습니다.", "차이가 없다고 단정할 수 없습니다.", "MSDS 기재와 일치하는지 검토자가 확인해야 합니다.", "MSDS 기재는 계산 결과와 일치해야 합니다.", "MSDS가 틀렸을 가능성이 있어 확인이 필요합니다.", "농도 기준과 같습니다만 구분은 다릅니다.", "성분 A의 값은 시험 자료와 같습니다. 그러나 구분이 달라 불일치입니다.",
                                  "계산 과정에서 사용한 기준은 구분 1 기준이며 결과는 구분 3입니다."])
def test_정직한_설명은_검사를_지나간다(text):
    req = {"finding": {"section": "2", "kind": "class", "verdict": "불일치", "msds": {"category": "2"}, "expected": {"low": "3", "high": "3"}}}
    assert ex.claim_problems({"summary": text}, req) == []


def test_문장틀_설명은_검사에_걸리지_않는다(svc, put, gold25, admin):
    from msds.compliance import explain as engine
    put(handoff(gold25))
    svc.judge_step()
    rows = admin.execute("SELECT request FROM judge.explanation").fetchall()
    assert rows and [p for (r,) in rows for p in ex.claim_problems(engine.template(r), r)] == []


def test_문장틀로_덮은_과대분류_요약은_모델_글로_검사하지_않는다():
    req = {"finding": {"section": "2", "kind": "class", "verdict": "불일치", "msds": {"category": "1"}, "expected": {}}}
    req["finding"]["type"] = next(iter(ex.engine._DIRECTION_TYPES))
    # 이유가 비면 '이유에 글이 없음'으로 걸리므로(요약을 고정한 줄은 이유가 모델 글의 전부) 정상 이유를 둔다
    fixed = {"summary": "두 값이 일치합니다.", "reasons": ["MSDS는 구분 1로 적었습니다."], "basis": []}
    assert ex.claim_problems(fixed, req) == []
    req["finding"]["type"] = "기준 불일치"  # 덮어쓰지 않는 줄은 모델이 무엇을 붙여 보내도 요약을 본다
    assert ex.claim_problems({**fixed, "llm_summary": "x"}, req)


def test_일치하지_않는다는_설명은_검사를_지나간다():
    req = {"finding": {"section": "2", "kind": "class", "verdict": "불일치", "msds": {"category": "2"}, "expected": {"low": "3", "high": "3"}}}
    assert ex.claim_problems({"summary": "MSDS는 구분 2이고 계산 결과는 구분 3으로 일치하지 않습니다."}, req) == []


@pytest.mark.parametrize("text,bad", [
    ("규제DB 결과는 비해당이고 MSDS는 해당입니다.", True), ("규제DB 결과는 해당 없음입니다.", True), ("규제DB에 따르면 해당합니다.", False),
    ("MSDS에 해당 항목이 없습니다.", False), ("규제DB 결과는 해당이고 MSDS는 비해당입니다.", False), ("규제DB 기준 미해당입니다.", True),
    ("규제 적용 대상에서 제외됩니다.", True), ("함량이 기준 미만이라 적용되지 않습니다.", True), ("규제DB 결과와 달리 MSDS는 비해당입니다.", False)])
def test_15항_해당_비해당을_엔진과_대조한다(text, bad):
    req = {"finding": {"section": "15", "kind": "regulation", "verdict": "불일치", "msds": {"applicable": "비해당"}, "expected": {"applicable": "해당"}}}
    assert bool(ex.claim_problems({"summary": text}, req)) is bad


@pytest.mark.parametrize("section, verdict, fixed", [("15", "경계", True), ("15", "불일치", False), ("2", "경계", False)])
def test_15항_경계_줄의_요약은_문장틀로_고정한다(section, verdict, fixed):
    # 실제 모델이 15항 경계 요약에서 "MSDS가 더 강하게 적었다"고 방향을 단정했다(T21-M005). 요약만 문장틀로 두고 이유는 모델 글을 쓴다
    finding = {"id": "x", "section": section, "kind": "regulation" if section == "15" else "class", "item": "a", "item_name": "유독물질",
               "component": "2", "verdict": verdict, "type": verdict,
               "msds": {"applicable": "해당"} if section == "15" else {}, "expected": {"applicable": verdict} if section == "15" else {}}
    req = {"finding": finding, "causes": [], "trace": {"inputs": [{"name": "1,3-Butadiene"}]}, "evidence": []}
    said = "유독물질은 MSDS가 해당으로 더 강하게 적었습니다."
    reason = "결과를 가장 크게 좌우한 성분은 1,3-Butadiene입니다."
    body = ex.generate(req, lambda s, u: ({"summary": said, "reasons": [reason], "basis": []}, {"model": "m"}), retries=0)
    assert (body["summary"] == ex.engine._summary(req)) is fixed
    if fixed:
        assert body["by"] == "llm" and body["reasons"] == [reason] and "사람 확인" in body["summary"]


@pytest.mark.parametrize("reasons, by", [([], "template"), ([":", "basis"], "template"),
                                         (["MSDS는 PRTR물질에 해당한다고 기재되어 있습니다.", ":"], "template"),
                                         (["MSDS는 해당, 계산 결과는 경계입니다."], "llm")])
def test_요약을_고정한_줄은_이유에_글이_없으면_문장틀로_간다(reasons, by):
    # 실제 기록(T21-M005 PRTR): 요약 ':'와 이유 ':'·'basis'가 요약 고정 뒤 'AI 설명 · 검사 ✓'로 나갈 뻔했다
    finding = {"id": "x", "section": "15", "kind": "regulation", "item": "a", "item_name": "PRTR물질", "component": "2",
               "verdict": "경계", "type": None, "msds": {"applicable": "해당"}, "expected": {"applicable": "경계"}}
    req = {"finding": finding, "causes": [], "trace": {"inputs": [{"name": "1,3-Butadiene"}]}, "evidence": []}
    body = ex.generate(req, lambda s, u: ({"summary": ":", "reasons": reasons, "basis": []}, {"model": "m"}), retries=0)
    assert body["by"] == by


def test_실패_이유의_서버_주소는_저장하지_않는다():
    body = ex.generate({"finding": {"id": "x", "section": "2", "kind": "class", "item": "a", "item_name": "a", "verdict": "불일치", "msds": {}, "expected": {}},
                        "causes": [], "trace": None, "evidence": []},
                       lambda s, u: (_ for _ in ()).throw(ConnectionError("http://10.1.2.3:8000/v1 host=llm.internal localhost:8000 끊김")), retries=0)
    joined = " ".join(body["check_failures"])
    assert body["by"] == "template" and not any(x in joined for x in ("10.1.2.3", "llm.internal", "localhost:8000"))


def test_설명_검사는_아주_긴_글자에도_오래_걸리지_않는다():
    import time
    req = {"finding": {"section": "15", "kind": "regulation", "verdict": "불일치", "msds": {"applicable": "비해당"}, "expected": {"applicable": "해당"}}}
    start = time.monotonic()
    for text in ("MSDS " * 20000, "계산 " * 20000, "가" * 100000, "a.b-c" * 20000, "[" * 100000, "기재 " * 20000):
        ex.claim_problems({"summary": text}, req)
    assert time.monotonic() - start < 20


def test_모든_설명_요청이_계약을_지킨다(svc, put, gold25, admin, contract_errors):
    put(handoff(gold25))
    svc.judge_step()
    rows = admin.execute("SELECT request FROM judge.explanation").fetchall()
    assert rows and [e for (r,) in rows for e in contract_errors("4-explanation.schema.json#/$defs/request", r)] == []
    found = {f["id"]: f for r in svc.view(JOB)["consistency"]["results"] for f in r["findings"]}
    for (r,) in rows:  # 값이 있으면 빠지지 않는다. 계약은 null 칸만 생략을 허용한다
        f = found[r["finding"]["id"]]
        assert (r["finding"].get("type"), r["finding"].get("severity")) == (f["type"], f["severity"])


def test_15항_판정의_원문_탭은_15항을_먼저_연다():
    from msds.judge.display import _pages
    pages = _pages([{"field": "components[0]", "page": 1}, {"field": "regulations[0]", "page": 5}], "15")
    assert [p["section"] for p in pages] == [15, 3]


def test_엑셀은_글머리_값을_바꾸지_않고_수식으로_만들지_않는다():
    from openpyxl import Workbook
    wb = Workbook()
    reports._append(wb.active, ["- 글머리", "=1+1", "+82", "@a", "보통", 3, None])
    saved = io.BytesIO()
    wb.save(saved)
    ws = load_workbook(io.BytesIO(saved.getvalue())).active
    cells = list(ws[1])
    assert [c.value for c in cells[:6]] == ["- 글머리", "=1+1", "+82", "@a", "보통", 3]
    assert all(c.data_type == "s" and c.quotePrefix for c in cells[:4])


def test_판정_전_값으로는_저장도_검토도_할_수_없다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    put(handoff(edited(gold25), 2))
    with pytest.raises(Conflict) as e:
        svc.save_snapshot(JOB, "김검수", 1, None)
    assert e.value.pending == 2
    with pytest.raises(Conflict):
        svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    svc.drain()
    saved = svc.save_snapshot(JOB, "김검수", 2, None)
    assert (saved["handoff_seq"], saved["version"]) == (2, 2)


def test_보던_버전이_미래여도_막는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    with pytest.raises(Conflict):
        svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 999)
    with pytest.raises(Conflict):
        svc.save_snapshot(JOB, "김검수", 999, None)


def test_판정이_바뀐_항목은_미검토로_돌아가고_의견으로_지워지지_않는다(svc, put, gold25):
    skin = "m0/F2:HH_SKIN_CORR:-"
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, skin, "확인", None, "김검수", 1)
    assert skin not in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]
    put(handoff(edited(gold25), 2))
    svc.drain()
    o = svc.save_overview(JOB)
    assert skin in o["reviews"]["unreviewed_ids"] and svc.status(JOB)["unreviewed"] == len(o["reviews"]["unreviewed_ids"])
    s = svc.add_review(JOB, skin, "의견", "확인 중", "김검수", 2)
    assert s["status"] == "확인" and s["stale"] is True
    assert skin in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]
    s = svc.add_review(JOB, skin, "불일치 확정", None, "김검수", 2)
    assert s["stale"] is False and skin not in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]


def test_모델이_예외를_내도_문장틀로_끝난다(svc, put, gold25, pool, admin):
    def dead(system, user):
        raise RuntimeError("모델 호출 실패")

    fake = JudgeService(pool=pool, provider=svc.provider, llm=dead)
    put(handoff(gold25))
    fake.drain()
    assert admin.execute("SELECT count(*) FROM judge.explanation WHERE state <> '완료'").fetchone()[0] == 0
    e = admin.execute("SELECT body FROM judge.explanation WHERE finding_id=%s", (FID,)).fetchone()[0]
    assert e["by"] == "template" and "모델 응답 없음" in e["check_failures"]


def test_늦게_끝난_옛_넘김은_최신_판정을_덮지_않는다(svc, put, gold25):
    put(handoff(gold25))
    old = svc.claim_handoff()
    put(handoff(edited(gold25), 2))
    new = svc.claim_handoff()
    assert new["handoff_seq"] == 2
    assert svc.process_handoff(new) == 1
    assert svc.process_handoff(old) is None
    v = svc.view(JOB)
    assert (v["version"], v["handoff_seq"]) == (1, 2) and svc.status(JOB)["state"] == "판정 있음"


def test_죽는_작업을_끝없이_다시_잡지_않는다(svc, put, gold25, admin):
    put(handoff(gold25))
    svc.claim_handoff()
    admin.execute("UPDATE judge.handoff_state SET attempts = %s, taken_at = now() - interval '1 hour'", (svc_mod.MAX_ATTEMPTS,))
    assert svc.claim_handoff() is None
    st = svc.status(JOB)
    assert st["state"] == "판정 실패" and "시도 한도" in st["error"]


def test_동작과_판정이_맞지_않으면_거절한다(svc, put, gold25, api):
    put(handoff(gold25))
    svc.drain()
    with pytest.raises(InvalidAction):
        svc.add_review(JOB, FID, "확인", None, "김검수", 1)
    with pytest.raises(InvalidAction):
        svc.add_review(JOB, "m0/F2:HH_SKIN_CORR:-", "불일치 확정", None, "김검수", 1)
    r = api.post(f"/api/judgments/{JOB}/reviews", json={"finding_id": FID, "action": "확인", "reviewer": "김검수", "seen_version": 1})
    assert r.status_code == 422


def test_칸_수는_넘김_기록의_fields_total_로_센다():
    marks = [{"msds_index": 0, "field": "product.name", "status": "확인함"}, {"msds_index": 0, "field": "meta.a", "status": "수정됨"},
             {"msds_index": 0, "field": "product.name", "status": "수정됨"}]  # 같은 칸은 마지막 표시만
    body = {"fields_total": 4, "field_status": marks}
    assert svc_mod.value_counts(body) == {"state": "일부", "model_as_is": 2, "confirmed": 0, "edited": 2, "fields_total": 4}
    assert svc_mod.value_counts({"fields_total": 2, "field_status": marks})["state"] == "완료"
    assert svc_mod.value_counts({"fields_total": 4, "field_status": []})["state"] == "미검수"
    assert svc_mod.value_counts({"fields_total": 0, "field_status": marks})["state"] == "미검수"


def test_옛_버전_화면은_그_버전의_칸_상태를_보인다(svc, put, gold25):
    first = [{"msds_index": 0, "field": "product.name", "status": "확인함"}]
    put(handoff(gold25, field_status=first))
    svc.drain()
    put(handoff(edited(gold25), 2, field_status=[]))
    svc.drain()
    assert svc.view(JOB, 1)["field_status"] == first and svc.view(JOB)["field_status"] == []


def test_제어_문자와_수식이_엑셀을_막지_않는다(svc, put, gold25, api):
    doc = copy.deepcopy(gold25)
    doc["msds"][0]["components"][0]["cas_no"] = '=HYPERLINK("http://x")'
    doc["msds"][0]["components"][0]["name"] = "황\x01산"
    put(handoff(doc))
    svc.drain()
    svc.add_review(JOB, "m0/FPT:TYPE", "의견", "수직탭\x0b글", "김검수", 1)
    r = api.post(f"/api/judgments/{JOB}/reports", json={"format": "xlsx", "include": ALL})
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert all(c.data_type != "f" for ws in wb for row in ws.iter_rows() for c in row)


def test_NUL_입력은_422다(api, svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    bad = {"finding_id": FID, "action": "의견", "comment": "a\x00b", "reviewer": "김검수", "seen_version": 1}
    assert api.post(f"/api/judgments/{JOB}/reviews", json=bad).status_code == 422
    assert api.post(f"/api/judgments/{JOB}/reviews", json={**bad, "comment": "ok", "reviewer": "a\x00"}).status_code == 422
    assert api.post(f"/api/judgments/{JOB}/snapshots", json={"reviewer": "김검수", "seen_version": 1, "note": "\x00"}).status_code == 422


def test_끝에_줄바꿈이_붙은_작업_번호와_빈_구성(api, svc, put, gold25):
    assert api.get("/api/judgments/summary", params={"job_ids": f"{JOB}\n"}).status_code == 422
    put(handoff(gold25))
    svc.drain()
    empty = api.post(f"/api/judgments/{JOB}/reports", json={"format": "html", "include": []}).text
    assert "2항 판정" not in empty and "재생성" not in empty


def test_긴_제품명도_헤더가_넘치지_않는다(api, svc, put, gold25):
    doc = copy.deepcopy(gold25)
    doc["msds"][0]["product"]["name"] = "가" * 5000
    put(handoff(doc))
    svc.drain()
    r = api.post(f"/api/judgments/{JOB}/reports", json={"format": "json", "include": ALL})
    assert len(r.headers["content-disposition"]) < 1200


def test_JSON_리포트가_계약을_지키고_409_모양이_맞다(api, svc, put, gold25, contract_errors):
    put(handoff(gold25))
    svc.drain()
    data = api.post(f"/api/judgments/{JOB}/reports", json={"format": "json", "include": ALL}).json()
    assert contract_errors("5-api.schema.json#/$defs/report_document", data) == []
    put(handoff(edited(gold25), 2))
    r = api.post(f"/api/judgments/{JOB}/snapshots", json={"reviewer": "김검수", "seen_version": 1})
    assert r.status_code == 409 and contract_errors("5-api.schema.json#/$defs/conflict_response", r.json()) == []


# ── 재검증에서 재현된 결함 ─────────────────────────────────────────────

def test_값을_되돌린_넘김_뒤에_늦게_온_옛_넘김은_저장되지_않는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    put(handoff(edited(gold25), 2))
    late = svc.claim_handoff()
    put(handoff(gold25, 3))
    svc.drain()  # 3번은 값이 v1과 같아 새 버전을 만들지 않는다
    assert svc.process_handoff(late) is None
    assert [x["version"] for x in svc.versions(JOB)] == [1]
    saved = svc.save_snapshot(JOB, "김검수", 1, None)
    assert (saved["handoff_seq"], saved["version"]) == (3, 1)


def test_같은_넘김을_둘이_처리해도_버전은_하나다(svc, put, gold25):
    body = handoff(gold25)
    put(body)
    claimed = svc.claim_handoff()
    assert svc.process_handoff(claimed) == 1 and svc.process_handoff(claimed) == 1
    assert len(svc.versions(JOB)) == 1


def _gold_doc(gold25):
    return {"doc": gold25["doc"], "msds": [{"meta": {"last_revision_date": "2022-06-29"}, "product": {"name": "황산"},
                                           "composition": {"type": "혼합물"}, "components": []}]}


def test_골드는_지금_값과_지금_판정의_저장본에만_붙는다(svc, put, gold25):
    doc = _gold_doc(gold25)
    marks = [{"msds_index": 0, "field": k, "status": "확인함"} for k in ("meta", "product", "composition")]
    put(handoff(doc, field_status=marks, fields_total=len(marks)))
    svc.drain()
    for fid in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]:
        svc.add_review(JOB, fid, "예외 승인", "확인함", "김검수", 1)
    svc.save_snapshot(JOB, "김검수", 1, None)
    assert svc.summary([JOB])[0]["data_grade"] == "골드"
    changed = copy.deepcopy(doc)
    changed["msds"][0]["product"]["name"] = "질산"
    put(handoff(changed, 2, field_status=marks, fields_total=len(marks)))
    assert svc.summary([JOB])[0]["data_grade"] == "실버"  # 판정 전
    svc.drain()
    assert svc.summary([JOB])[0]["data_grade"] == "실버"  # 판정 뒤, 저장 전


def test_칸이_없는_문서는_골드가_되지_않는다(svc, put, gold25):
    put(handoff({"doc": gold25["doc"], "msds": []}, fields_total=0))
    svc.drain()
    for fid in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]:
        svc.add_review(JOB, fid, "예외 승인", "확인함", "김검수", 1)
    svc.save_snapshot(JOB, "김검수", 1, None)
    o = svc.save_overview(JOB)
    assert o["values"]["state"] == "미검수" and svc.summary([JOB])[0]["data_grade"] == "실버"


def test_판정_전에는_화면과_리포트가_직전_판정의_값을_읽는다(svc, put, gold25, api):
    marks = [{"msds_index": 0, "field": "product.name", "status": "확인함"}]
    put(handoff(gold25, field_status=marks))
    svc.drain()
    put(handoff(edited(gold25), 2, field_status=[]))
    assert svc.view(JOB)["field_status"] == marks
    assert svc.save_overview(JOB)["handoff_seq"] == 1
    data = api.post(f"/api/judgments/{JOB}/reports", json={"format": "json", "include": ALL}).json()
    assert data["version"] == 1 and data["extraction"]["msds"][0]["hazard"]["classes"] == gold25["msds"][0]["hazard"]["classes"]


def test_확인만_한_넘김_뒤의_옛_버전은_그_넘김의_칸_상태를_보인다(svc, put, gold25):
    marks = [{"msds_index": 0, "field": "product.name", "status": "확인함"}]
    put(handoff(gold25))
    svc.drain()
    put(handoff(gold25, 2, field_status=marks))
    svc.drain()
    put(handoff(edited(gold25), 3))
    svc.drain()
    assert svc.view(JOB, 1)["field_status"] == marks and svc.view(JOB)["field_status"] == []


def test_MSDS_값이_바뀌면_승인을_다시_확인하게_한다(svc, put, gold25):
    target = "m0/F2:ENV_AQ_CHRONIC:-"
    put(handoff(gold25))
    svc.drain()
    assert svc.view(JOB)["consistency"]["results"][0]["findings"]
    svc.add_review(JOB, target, "예외 승인", "공급사 확인", "김검수", 1)
    doc = copy.deepcopy(gold25)
    for c in doc["msds"][0]["hazard"]["classes"]:
        if c["class_code"] == "ENV_AQ_CHRONIC":
            c["category"] = "2"
    put(handoff(doc, 2))
    svc.drain()
    assert target in svc.versions(JOB)[0]["changed_findings"]
    assert svc.view(JOB)["reviews"][target]["stale"] is True
    assert target in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]


def test_창구가_죽어도_설명이_멈추지_않는다(svc, put, gold25, pool, admin):
    class Broken:
        def slot_sync(self, kind):
            raise RuntimeError("창구 장애")

    fake = JudgeService(pool=pool, provider=svc.provider, llm=lambda s, u: ({}, {}), gate=Broken())
    put(handoff(gold25))
    fake.drain()
    assert admin.execute("SELECT count(*) FROM judge.explanation WHERE state <> '완료'").fetchone()[0] == 0
    body = admin.execute("SELECT body FROM judge.explanation WHERE finding_id=%s", (FID,)).fetchone()[0]
    assert body["by"] == "template" and "창구 장애" not in " ".join(body["check_failures"]) and body["check_failures"]


def test_이상한_글자도_엑셀과_입력을_막지_않는다(svc, put, gold25, api):
    doc = copy.deepcopy(gold25)
    doc["msds"][0]["product"]["name"] = 123
    doc["msds"][0]["components"][0]["content"]["raw"] = ["93", "98"]
    put(handoff(doc))
    svc.drain()
    svc.add_review(JOB, "m0/FPT:TYPE", "의견", "끝\uffff\ufffe글", "김검수", 1)
    for fmt in ("xlsx", "pdf", "json", "html"):
        assert api.post(f"/api/judgments/{JOB}/reports", json={"format": fmt, "include": ALL}).status_code == 200, fmt
    wb = load_workbook(io.BytesIO(api.post(f"/api/judgments/{JOB}/reports", json={"format": "xlsx", "include": ALL}).content))
    assert "\uffff" not in str(wb["검토 이력"]["E2"].value)
    bad = {"finding_id": "m0/FPT:TYPE", "action": "의견", "comment": "ok", "reviewer": "김검수", "seen_version": 1}
    assert api.post(f"/api/judgments/{JOB}/reviews", json={**bad, "reviewer": "   "}).status_code == 422


# ── 3차 검증에서 재현된 결함 ───────────────────────────────────────────

def test_값이_같은_넘김과_옛_넘김이_겹쳐도_저장본은_한_값만_가리킨다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    put(handoff(edited(gold25), 2))
    late = svc.claim_handoff()
    put(handoff(gold25, 3))
    newest = svc.claim_handoff()
    # 2번이 먼저 끝나 B가 최신이 되어도, 3번(값 A)이 결과를 재사용해 최신을 A로 되돌린다
    assert svc.process_handoff(late) == 2
    assert svc.process_handoff(newest) == 3
    assert svc.view(JOB)["consistency"] == svc.view(JOB, 1)["consistency"]
    # 순서가 반대면 2번은 건너뛴다 (test_값을_되돌린_넘김_뒤에…)
    assert svc.save_snapshot(JOB, "김검수", 3, None)["handoff_seq"] == 3


def test_끝난_넘김을_늦게_다시_처리해도_기록이_그대로다(svc, put, gold25, admin):
    marks = [{"msds_index": 0, "field": "product.name", "status": "확인함"}]
    put(handoff(gold25))
    svc.drain()
    body = handoff(gold25, 2, field_status=marks)
    put(body)
    svc.drain()
    put(handoff(edited(gold25), 3))
    svc.drain()
    assert svc.process_handoff(body) == 1
    assert svc.view(JOB, 1)["field_status"] == marks
    bad = {**body, "extraction_sha256": SHA}
    assert svc.process_handoff(bad) is None
    row = admin.execute("SELECT state, version FROM judge.handoff_state WHERE job_id=%s AND handoff_seq=2", (JOB,)).fetchone()
    assert row == ("완료", 1) and svc.status(JOB)["state"] == "판정 있음"


def test_저장_못_할_글자를_쓴_모델_설명도_문장틀로_끝난다(svc, put, gold25, pool, admin):
    fake = JudgeService(pool=pool, provider=svc.provider,
                        llm=lambda s, u: ({"summary": "널\x00글자", "reasons": [], "basis": [], "used_numbers": []}, {"model": "m", "errors": []}))
    put(handoff(gold25))
    fake.drain()
    assert admin.execute("SELECT count(*) FROM judge.explanation WHERE state <> '완료'").fetchone()[0] == 0
    assert fake.view(JOB)["explanations"][FID]["by"] == "template"


def test_저장_뒤_검토를_되돌리면_골드가_아니다(svc, put, gold25):
    doc = {"doc": gold25["doc"], "msds": [{"meta": {"last_revision_date": "2022-06-29"}, "product": {"name": "황산"},
                                           "composition": {"type": "혼합물"}, "components": [],
                                           "hazard": {"classes": [{"seq": 1, "class_code": "HH_SKIN_CORR", "category": "1"}]}}]}
    marks = [{"msds_index": 0, "field": k, "status": "확인함"} for k in ("meta", "product", "composition", "hazard")]
    put(handoff(doc, field_status=marks, fields_total=len(marks)))
    svc.drain()
    ids = svc.save_overview(JOB)["reviews"]["unreviewed_ids"]
    assert ids
    for fid in ids:
        svc.add_review(JOB, fid, "예외 승인", "확인함", "김검수", 1)
    svc.save_snapshot(JOB, "김검수", 1, None)
    assert svc.summary([JOB])[0]["data_grade"] == "골드"
    svc.add_review(JOB, ids[0], "되돌리기", None, "김검수", 1)
    assert svc.summary([JOB])[0]["data_grade"] == "실버" and svc.summary([JOB])[0]["unreviewed"] == 1


def test_상태_폴링은_추출값을_읽지_않는다(svc, put, gold25, monkeypatch):
    put(handoff(gold25))
    svc.drain()
    monkeypatch.setattr(JudgeService, "_handoff", staticmethod(lambda *a, **k: pytest.fail("status 가 추출값을 읽음")))
    assert svc.status(JOB)["unreviewed"] > 0


# ── 4차 검증에서 재현된 결함 ───────────────────────────────────────────

def test_저장_중_끼어든_넘김은_저장본에_섞이지_않는다(svc, put, gold25, monkeypatch):
    put(handoff(gold25))
    svc.drain()
    checked = JudgeService._check_current

    def racing(conn, job_id, latest, seen):
        seq = checked(conn, job_id, latest, seen)
        put(handoff(edited(gold25), 2))  # 확인 직후 A가 새 넘김을 쓴다
        return seq

    monkeypatch.setattr(JudgeService, "_check_current", staticmethod(racing))
    saved = svc.save_snapshot(JOB, "김검수", 1, None)
    assert (saved["handoff_seq"], saved["version"]) == (1, 1)
    assert svc.summary([JOB])[0]["data_grade"] == "실버"


def test_건너뛴_넘김을_다시_처리해도_상태가_그대로다(svc, put, gold25, admin):
    first = handoff(gold25)
    put(first)
    put(handoff(edited(gold25), 2))
    svc.drain()
    assert svc.process_handoff(first) is None
    assert svc.process_handoff({**first, "extraction_sha256": SHA}) is None
    assert admin.execute("SELECT state, version FROM judge.handoff_state WHERE handoff_seq=1").fetchone() == ("건너뜀", None)


def test_저장_뒤_검토가_바뀌면_다시_저장할_때까지_골드가_아니다(svc, put, gold25):
    doc = {"doc": gold25["doc"], "msds": [{"meta": {"last_revision_date": "2022-06-29"}, "product": {"name": "황산"},
                                           "composition": {"type": "혼합물"}, "components": [{"seq": 1, "name": "황산"}],
                                           "hazard": {"classes": [{"seq": 1, "class_code": "HH_SKIN_CORR", "category": "1"}]}}]}
    marks = [{"msds_index": 0, "field": k, "status": "확인함"} for k in ("meta", "product", "composition", "components", "hazard")]
    put(handoff(doc, field_status=marks, fields_total=len(marks)))
    svc.drain()
    for fid in svc.save_overview(JOB)["reviews"]["unreviewed_ids"]:
        svc.add_review(JOB, fid, "예외 승인", "확인함", "김검수", 1)
    svc.save_snapshot(JOB, "김검수", 1, None)
    assert svc.summary([JOB])[0]["data_grade"] == "골드"
    svc.add_review(JOB, "m0/FPT:TYPE", "확인", None, "김검수", 1)  # 일치 항목의 처리도 저장본에 없는 변경이다
    assert svc.summary([JOB])[0]["data_grade"] == "실버"
    svc.save_snapshot(JOB, "김검수", 1, None)
    assert svc.summary([JOB])[0]["data_grade"] == "골드"
    svc.add_review(JOB, "m0/FPT:TYPE", "되돌리기", None, "김검수", 1)
    assert svc.summary([JOB])[0]["data_grade"] == "실버"


# ── 문서 대조에서 나온 누락 ────────────────────────────────────────────

def test_이력은_판정_버전과_최신_판정_여부를_알려준다(svc, put, gold25):
    doc = copy.deepcopy(gold25)
    hz = doc["msds"][0]["hazard"]
    hz["h_statements"].append({**hz["h_statements"][0], "code": "H999"})
    gone = "m0/F2L:H:H999"  # 값을 고치면 사라지는 항목
    put(handoff(doc))
    svc.drain()
    assert any(f["id"] == gone for f in svc.view(JOB)["consistency"]["results"][0]["findings"])
    svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    svc.add_review(JOB, gone, "의견", "확인 중", "김검수", 1)
    put(handoff(gold25, 2))
    svc.drain()
    svc.save_snapshot(JOB, "김검수", 2, "저장 메모")
    history = svc.history(JOB)
    assert history[0]["area"] == "저장" and history[0]["target"] == "저장본 1" and history[0]["comment"] == "저장 메모"
    rows = {r["ref"]["finding_id"]: r for r in history if r["area"] != "저장"}
    assert rows[FID]["ref"]["version"] == 1 and rows[FID]["ref"]["in_latest"] is True
    assert rows[gone]["ref"]["version"] == 1 and rows[gone]["ref"]["in_latest"] is False


def test_다른_검토자의_처리를_모르고_덮으면_막는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    first = svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1)
    with pytest.raises(Conflict, match="먼저 처리"):
        svc.add_review(JOB, FID, "예외 승인", "다른 판단", "이검수", 1, seen_event_id=first["last_event_id"] + 5)
    second = svc.add_review(JOB, FID, "예외 승인", "다른 판단", "이검수", 1, seen_event_id=first["last_event_id"])
    assert second["status"] == "예외 승인"
    with pytest.raises(Conflict):  # 처음 처리한다고 믿었지만(보낸 번호 없음은 검사 안 함) 번호를 보내면 잡힌다
        svc.add_review(JOB, FID, "불일치 확정", None, "김검수", 1, seen_event_id=first["last_event_id"])


def test_설명이_엔진과_다른_결론을_말하면_문장틀로_대체한다(svc, put, gold25, pool, admin):
    target = "m0/F2:ENV_AQ_CHRONIC:-"  # MSDS 구분 3, 계산 분류안됨, 불일치

    def wrong(system, user):
        return {"summary": "판정은 일치입니다.", "reasons": ["판정은 일치입니다.", "계산 결과는 구분 3입니다."], "basis": []}, {"model": "fake", "errors": []}

    fake = JudgeService(pool=pool, provider=svc.provider, llm=wrong)
    put(handoff(gold25))
    fake.drain()
    body = admin.execute("SELECT body FROM judge.explanation WHERE finding_id=%s", (target,)).fetchone()[0]
    assert body["by"] == "template" and "판정은 일치" not in body["summary"]
    assert any("엔진 판정" in x for x in body["check_failures"]) and any("계산 결과를 구분 3" in x for x in body["check_failures"])


def test_맞는_설명은_판정_문장이_있어도_통과한다():
    req = {"finding": {"kind": "class", "verdict": "불일치", "expected": {"low": "분류안됨", "high": "분류안됨"}, "msds": {"category": "3"}}}
    good = {"summary": "판정은 불일치입니다. MSDS는 구분 3이고 계산 결과는 분류안됨입니다.", "reasons": ["구분은 일치하지 않습니다."], "basis": []}
    assert ex.claim_problems(good, req) == []


def test_리포트에_처리_현황과_기준이_나오고_심각도_순이다(api, svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    unreviewed = len(svc.save_overview(JOB)["reviews"]["unreviewed_ids"])
    url = f"/api/judgments/{JOB}/reports"
    page = api.post(url, json={"format": "html", "include": ALL}).text
    assert f"미검토 {unreviewed}건" in page and "미검수 칸" in page and "처리 불필요" in page and "ATEmix 계산" in page and "성분별 요약" in page
    only2 = api.post(url, json={"format": "html", "include": {**NOTHING, "findings_2": True}}).text
    assert "2항 판정" in only2 and "15항 판정" not in only2
    wb = load_workbook(io.BytesIO(api.post(url, json={"format": "xlsx", "include": {**NOTHING, "findings_15": True}}).content))
    assert "2항 판정" not in wb.sheetnames and "15항 판정" in wb.sheetnames
    values = {r[0].value: r[1].value for r in wb["요약"].iter_rows()}
    assert values["기준일"] == AS_OF and "to21_sample" in values["지식"] and values["미검토"] == unreviewed
    rows = [r[6].value for r in wb["15항 판정"].iter_rows(min_row=2)]
    assert rows[0].startswith("불일치 · 높음") and rows == sorted(rows, key=lambda v: (reports._VERDICT[v.split(" · ")[0]]))


def test_지원하지_않는_리포트_옵션은_422다(api, svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    url = f"/api/judgments/{JOB}/reports"
    assert api.post(url, json={"format": "xlsx", "include": ["cover"]}).status_code == 422
    assert api.post(url, json={"format": "json", "sections": [2]}).status_code == 422
    assert api.post(url, json={"format": "html", "sections": [8]}).status_code == 422
    assert api.post(url, json={"format": "html", "sections": []}).status_code == 422


def test_값_없는_칸과_다른_문장_모양도_결론을_대조한다():
    lacking = {"finding": {"kind": "class", "verdict": "근거부족", "expected": {}, "msds": {}}}
    assert ex.claim_problems({"summary": "계산 결과는 구분 3입니다. MSDS는 구분 3입니다.", "reasons": [], "basis": []}, lacking)
    wrong = {"finding": {"kind": "class", "verdict": "불일치", "expected": {"low": "1", "high": "1"}, "msds": {"category": "1"}}}
    for text in ("판정 결과는 일치입니다.", "일치로 판정되었습니다.", "계산 결과, 구분 3입니다.", "계산 결과는 3입니다."):
        assert ex.claim_problems({"summary": text, "reasons": [], "basis": []}, wrong), text


def test_승인_뒤_의견이_승인_사유와_처리자를_지우지_않는다(svc, put, gold25, api):
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, FID, "예외 승인", "공급사 확인", "김검수", 1)
    s = svc.add_review(JOB, FID, "의견", "메모", "이검수", 1)
    assert (s["status"], s["comment"], s["reviewer"]) == ("예외 승인", "공급사 확인", "김검수")
    assert "공급사 확인" in api.post(f"/api/judgments/{JOB}/reports", json={"format": "html", "include": ALL}).text
    assert [r["comment"] for r in svc.history(JOB)] == ["메모", "공급사 확인"]


def _pdf_text(content):
    return "".join("".join(page.get_text().split()) for page in pymupdf.open(stream=content, filetype="pdf"))


def _rows_in_order(data, raw):
    """판정 줄의 모든 칸이 PDF에 순서대로 있는지 (제품 코드와 별개로 직접 센다)."""
    text = "".join(unicodedata.normalize("NFKC", _pdf_text(raw)).split())
    at = 0
    for section in ("2", "15"):
        for f, s in reports._rows(data, section):
            for cell in (f["label"], f["display"]["msds"], f["display"]["expected"], f["method"], f["verdict"]):
                piece = "".join(unicodedata.normalize("NFKC", reports._for_font(cell)).split())
                found = text.find(piece, at)
                assert found >= 0, (f["id"], cell)
                at = found + len(piece)


def test_PDF는_쪽_경계에서_판정_줄을_잃지_않는다(svc, put, gold25):
    """앞의 글 양을 바꿔 표 위치를 옮겨 가며 본다."""
    for n, padding in enumerate((0, 7, 23, 41), 1):
        doc = copy.deepcopy(gold25)
        doc["doc"]["doc_id"] = f"T21-P{n}"
        job = f"U-20261102-{n:03d}"
        put(handoff(doc, job=job))
        svc.drain()
        for i in range(padding):
            svc.add_review(job, FID, "의견", f"채움 {i}", "김검수", 1)
        data = svc.report_data(job, None)
        _rows_in_order(data, reports.to_pdf(data, {**ALL, "regenerated_msds": False}))


def test_실버_전체의_PDF에_모든_판정_줄이_나온다(svc, put):
    import json as _json

    from msds.common.paths import ROOT

    paths = [p for p in sorted((ROOT / "data" / "silver" / "claude").glob("T21-*.json")) if not p.name.endswith(".review.json")]
    if not paths:
        pytest.skip("silver 추출본 없음")
    for n, path in enumerate(paths, 1):
        job = f"U-20261102-{n:03d}"
        put(handoff(_json.loads(path.read_text(encoding="utf-8")), job=job))
        assert svc.judge_step()
        data = svc.report_data(job, None)
        _rows_in_order(data, reports.to_pdf(data))  # 재생성 MSDS까지 전체 구성. 빠진 글이 있으면 여기서도 실패한다


def test_리포트_요청은_계약의_include를_요구한다(api, svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    url = f"/api/judgments/{JOB}/reports"
    assert api.post(url, json={"format": "html"}).status_code == 422
    assert api.post(url, json={"format": "html", "include": {"findings_2": True}}).status_code == 422
    only = api.post(url, json={"format": "html", "include": NOTHING}).text
    assert "2항 판정" not in only and "재생성 MSDS" not in only and "검토 결과" in only


def test_시험용_넘김_API는_켰을_때만_있다(api, svc, gold25, monkeypatch):
    url, body = "/api/judgments/_test/handoffs", handoff(gold25)
    monkeypatch.delenv("MSDS_JUDGE_TEST_API", raising=False)
    assert api.post(url, json=body).status_code == 404
    monkeypatch.setenv("MSDS_JUDGE_TEST_API", "1")
    assert api.post(url, json={**body, "job_id": "bad"}).status_code == 422
    assert api.post(url, json=body).status_code == 201
    svc.drain()
    assert svc.status(JOB)["state"] == "판정 있음"


def test_PDF_표는_쪽이_바뀌어도_머리줄을_다시_찍고_글이_칸을_넘지_않는다():
    table = reports._Table(reports._FINDING_HEAD, reports._FINDING_WIDTHS, [[f"항목 {i} END", "구분 2 (증기)", "구분 2 (분진·미스트)", "ATEmix 계산", "불일치 · 중간", "미검토"] for i in range(200)])
    doc = reports._layout([table])
    text = [page.get_text() for page in doc]
    assert sum(t.count("END") for t in text) == 200 and doc.page_count > 1
    assert all("MSDS 기재" in t for t in text)
    right = reports._MARGIN + reports._WIDTH
    assert all(word[2] <= right + 0.5 for page in doc for word in page.get_text("words"))


def test_글꼴에서_잉크_없이_찍히는_글자는_코드값으로_보인다():
    assert reports._for_font("a\u203eb") == "a[U+203E]b"


def test_의견의_줄바꿈은_PDF에서도_유지된다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, FID, "의견", "첫 줄\n둘째 줄", "김검수", 1)
    text = "".join(p.get_text() for p in pymupdf.open(stream=reports.to_pdf(svc.report_data(JOB, None), {**NOTHING, "history": True}), filetype="pdf"))
    assert "의견 첫 줄\n" in text and "의견 둘째 줄" in text


def test_완전성_검사는_빠진_글과_순서_뒤바뀜과_기호_유실을_잡는다():
    lines = ["판정 일치 첫째", "둘째 ﬁ합자", "≥ ≤"]
    assert reports._first_missing(lines, "판정 일치 첫째\n둘째 fi합자\n≥ ≤") is None
    assert reports._first_missing(lines, "판정 일치 첫째\n둘째 fi합자") == "≥ ≤"
    assert reports._first_missing(lines, "둘째 fi합자 판정 일치 첫째 ≥ ≤") is not None
    assert reports._first_missing(["값 98"], "값 \x00 98") is not None
    # 의견에 판정 글자가 있어도 다른 줄의 누락을 가리지 못한다
    assert reports._first_missing(["판정 일치", "판정 일치", "빠진 줄"], "판정 일치 판정 일치 판정 일치") == "빠진 줄"


def _blocks_of(lines, size=10.0):
    return [reports._Block([(size, line)]) for line in lines]


@pytest.mark.parametrize("size", [8, 9, 9.5, 10, 10.5, 11, 12, 13, 14])
def test_어떤_글자_크기에서도_쪽_넘김에서_줄을_잃지_않는다(size):
    lines = [f"줄 {i} END" for i in range(1500)]
    doc = reports._layout(_blocks_of(lines, size))
    text = "".join(page.get_text() for page in doc)
    assert text.count("END") == 1500 and doc.page_count > 1
    bottom = doc[0].rect.y1 - reports._MARGIN
    assert all(word[3] <= bottom + 0.5 for page in doc for word in page.get_text("words"))


def test_영역_높이에_줄이_정확히_맞아도_쪽을_넘긴다(monkeypatch):
    """예전 Story 조판에서 줄이 사라지던 조건: 줄 높이의 배수가 영역 높이와 같은 경우."""
    size, line = 10.0, 13.5
    monkeypatch.setattr(reports, "_GAP", 0.0)
    height = pymupdf.paper_rect("a4").height - 72
    count = int(height // line)
    monkeypatch.setattr(reports, "_line_height", lambda s: (height / count))
    doc = reports._layout(_blocks_of([f"줄 {i} END" for i in range(count * 3 + 2)], size))
    assert "".join(page.get_text() for page in doc).count("END") == count * 3 + 2
    assert doc.page_count == 4


def test_블록은_가능하면_쪽에서_나뉘지_않고_너무_길면_나뉜다():
    filler = reports._Block([(10.0, f"채움 {i}") for i in range(50)])
    row = reports._Block([(10.0, "머리 HEAD"), (10.0, "내용 TAIL")])
    doc = reports._layout([filler, row] * 6)
    for page in doc:
        text = page.get_text()
        assert text.count("HEAD") == text.count("TAIL")
    huge = reports._Block([(10.0, f"긴 블록 {i} END") for i in range(300)])
    assert "".join(p.get_text() for p in reports._layout([huge])).count("END") == 300


def test_띄어쓰기_없는_긴_글자도_PDF에서_잘리지_않는다(svc, put, gold25):
    doc = copy.deepcopy(gold25)
    long_name = ",".join(f"7732-18-{i}" for i in range(60))
    doc["msds"][0]["components"][0]["name"] = long_name
    put(handoff(doc))
    svc.drain()
    svc.add_review(JOB, FID, "의견", "W" * 400, "김검수", 1)
    text = _pdf_text(reports.to_pdf(svc.report_data(JOB, None)))
    assert long_name in text and "W" * 400 in text


def test_줄바꿈은_글자_폭을_넘지_않고_단어를_되도록_자르지_않는다():
    width = reports._WIDTH
    lines = reports._wrap("가나다 " * 300 + "W" * 500, 10.0)
    assert all(reports._FONT.text_length(line, fontsize=10.0) <= width + 0.01 for line in lines)
    assert "".join("".join(lines).split()) == "가나다" * 300 + "W" * 500
    assert all(line.rstrip().endswith("가나다") for line in lines[:3])
    assert reports._wrap("", 10.0) == [""]


@pytest.mark.parametrize("given,shown", [
    ("TWA 0.2 mg/㎥, 5㎎, 3㎖, 2㎍, 1㎏, 2㎟", "TWA 0.2 mg/㎥, 5㎎, 3㎖, 2㎍, 1㎏, 2㎟"),
    ("10⁻³ m² H₂O ≥ ≤ ℃ ± ① ㈜ α", "10^-3 m² H₂O ≥ ≤ ℃ ± ① ㈜ α"),
    ("C₅H₁₂", "C_5H_12"),
    ("C₂H₅OH H₂O", "C_2H_5OH H₂O"),
    ("물∙알코올", "물·알코올"),
    (unicodedata.normalize("NFD", "황산 맥 파일"), "황산 맥 파일"),
    ("硫酸 理 燐", "硫酸 理 燐"),
    ("리터럴 &amp; &lt; 값", "리터럴 &amp; &lt; 값"),
    ("이모지 😀 끝", "이모지 [U+1F600] 끝"),
    ("함량 \uf0b3 98 %", "함량 [U+F0B3] 98 %"),
    ("수학 \U0001d431 끝", "수학 [U+1D431] 끝"),
    ("안\u200b보\ufeff임", "안보임"),
    ("끝\uffff\ufffe글\x0b자", "끝 글 자"),
    ("10\x0b20", "10 20"),  # 제어 문자를 지워 숫자가 붙으면 값이 바뀐다
    ("67\u00ad56\u00ad1", "67-56-1"),  # 하이픈으로 쓰인 소프트 하이픈
    ("\u221210 ℃, 5 µg, a\u2011b, a\u2012b, 2\u22c53, \u2206H, \ufb00", "-10 ℃, 5 μg, a-b, a-b, 2·3, ΔH, ff"),
    ("값 \ufffd 98", "값 [U+FFFD] 98"),  # 글꼴에는 있다고 나오지만 다른 글자로 읽힌다
    ("끝\u11a8", "끝[U+11A8]"),
    ("좌우\u200e표시\u200f", "좌우표시"),
])
def test_글자_처리(given, shown):
    assert reports._for_font(given) == shown


def test_특수_글자가_PDF에서_원문대로_읽히고_네모가_없다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, FID, "의견", "TWA 0.2 mg/㎥ 😀 10⁻³ ≥ 硫", "김검수", 1)
    raw = reports.to_pdf(svc.report_data(JOB, None), {**NOTHING, "history": True})
    text = "".join(page.get_text() for page in pymupdf.open(stream=raw, filetype="pdf"))
    assert "\x00" not in text and "TWA 0.2 mg/㎥ [U+1F600] 10^-3 ≥ 硫" in text


def test_T21_010도_재생성_MSDS가_나온다(svc):
    import json as _json

    from msds.common.paths import ROOT

    path = ROOT / "data" / "silver" / "claude" / "T21-010.json"
    if not path.exists():
        pytest.skip("silver 추출본 없음")
    original = _json.loads(path.read_text(encoding="utf-8"))
    before = copy.deepcopy(original)
    lines, error = reports._regenerated_lines(original)
    assert error is None and len(lines) > 100 and all(isinstance(line, str) for line in lines)
    assert original == before  # 넘김 기록을 바꾸지 않는다


def test_재생성이_실패해도_판정_표는_나온다(api, svc, put, gold25, monkeypatch):
    put(handoff(gold25))
    svc.drain()

    def broken():
        raise TypeError("재생성 실패")

    monkeypatch.setattr(reports, "_load_regen", broken)
    page = api.post(f"/api/judgments/{JOB}/reports", json={"format": "html", "include": ALL}).text
    assert "만들지 못함" in page and "2항 판정" in page
    assert "만들지못함" in _pdf_text(reports.to_pdf(svc.report_data(JOB, None)))


def test_PDF에_글이_빠지면_내보내지_않고_이유를_응답한다(api, svc, put, gold25, monkeypatch):
    put(handoff(gold25))
    svc.drain()
    monkeypatch.setattr(reports, "_first_missing", lambda lines, text: "빠진 글")
    with pytest.raises(reports.ReportError, match="빠진 글"):
        reports.to_pdf(svc.report_data(JOB, None))
    r = api.post(f"/api/judgments/{JOB}/reports", json={"format": "pdf", "include": ALL})
    assert r.status_code == 422 and "빠진 글" in r.json()["detail"]


def test_긴_제품명도_PDF_표지에_온전히_나온다(svc, put, gold25):
    doc = copy.deepcopy(gold25)
    doc["msds"][0]["product"]["name"] = "W" * 60
    put(handoff(doc))
    svc.drain()
    raw = reports.to_pdf(svc.report_data(JOB, None), NOTHING)
    assert "W" * 60 in _pdf_text(raw)


def test_빈_구성의_PDF도_만들어진다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    assert pymupdf.open(stream=reports.to_pdf(svc.report_data(JOB, None), NOTHING), filetype="pdf").page_count >= 1


def test_PDF를_동시에_만들어도_깨지지_않는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    data, out, errors = svc.report_data(JOB, None), [], []

    def go():
        try:
            out.append(reports.to_pdf(data, {**ALL, "regenerated_msds": False}))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and len(out) == 6
    assert len({_pdf_text(raw) for raw in out}) == 1


def test_글꼴에_있어도_다시_읽히지_않는_글자는_PDF를_막지_않는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, FID, "의견", "값 \ufffd 98 \u11a8 끝", "김검수", 1)
    text = "".join(p.get_text() for p in pymupdf.open(stream=reports.to_pdf(svc.report_data(JOB, None), {**NOTHING, "history": True}), filetype="pdf"))
    assert "값 [U+FFFD] 98 [U+11A8] 끝" in text


def test_일치_행의_처리_표기가_겹치지_않는다(svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    data = svc.report_data(JOB, None)
    text = _pdf_text(reports.to_pdf(data, {**NOTHING, "findings_2": True, "findings_15": True}))
    assert "처리처리불필요" not in text and "처리불필요" in text


def test_아주_긴_글자도_오래_걸리지_않는다():
    import time

    start = time.monotonic()
    lines = reports._wrap("W" * 40000, 10.0)
    # 지금 약 2초(글자마다 폭을 재는 pymupdf 비용). 통째로 재던 제곱 시간은 수십 초라 10초로 가른다. 3초는 부하에서 흔들렸다
    assert time.monotonic() - start < 10 and "".join(lines) == "W" * 40000


def test_HTML도_긴_글자가_폭을_넘지_않게_한다():
    assert "overflow-wrap:anywhere" in reports._CSS.split("}")[0]


def test_첫_처리끼리도_충돌을_잡는다(api, svc, put, gold25):
    put(handoff(gold25))
    svc.drain()
    url = f"/api/judgments/{JOB}/reviews"
    first = {"finding_id": FID, "action": "불일치 확정", "reviewer": "김검수", "seen_version": 1, "seen_event_id": None}
    assert api.post(url, json=first).status_code == 201
    second = {**first, "action": "예외 승인", "comment": "다른 판단", "reviewer": "이검수"}
    assert api.post(url, json=second).status_code == 409
    no_check = {k: v for k, v in second.items() if k != "seen_event_id"}
    assert api.post(url, json=no_check).status_code == 201


def test_판정이_일치로_바뀐_옛_처리는_처리_수에_넣지_않는다(svc, put, gold25):
    target = "m0/F2:ENV_AQ_CHRONIC:-"
    put(handoff(gold25))
    svc.drain()
    svc.add_review(JOB, target, "불일치 확정", None, "김검수", 1)
    assert svc.save_overview(JOB)["reviews"]["불일치 확정"] == 1
    doc = copy.deepcopy(gold25)
    doc["msds"][0]["hazard"]["classes"] = [c for c in doc["msds"][0]["hazard"]["classes"] if c["class_code"] != "ENV_AQ_CHRONIC"]
    put(handoff(doc, 2))
    svc.drain()
    o = svc.save_overview(JOB)
    assert svc.view(JOB)["reviews"][target]["stale"] is True and o["reviews"]["불일치 확정"] == 0 and target not in o["reviews"]["unreviewed_ids"]


def test_여러_MSDS_리포트는_어느_MSDS_줄인지_보인다(svc, put, gold25):
    doc = copy.deepcopy(gold25)
    doc["msds"] = [doc["msds"][0], copy.deepcopy(doc["msds"][0])]
    put(handoff(doc))
    svc.drain()
    data = svc.report_data(JOB, None)
    labels = [f["label"] for f, _ in reports._rows(data, "2")]
    assert any(x.startswith("MSDS 1 · ") for x in labels) and any(x.startswith("MSDS 2 · ") for x in labels)
    assert "MSDS1·급성독성물질(흡입)" in _pdf_text(reports.to_pdf(data, {**NOTHING, "findings_2": True}))


def test_시험용_넘김_API는_잘못된_값을_막는다(api, svc, gold25, monkeypatch):
    monkeypatch.setenv("MSDS_JUDGE_TEST_API", "1")
    url, body = "/api/judgments/_test/handoffs", handoff(gold25)
    assert api.post(url, json={**body, "handoff_seq": "x"}).status_code == 422
    assert api.post(url, json={k: v for k, v in body.items() if k != "field_status"}).status_code == 422
    assert api.post(url, json=body).status_code == 201
    assert api.post(url, json=body).status_code == 409


def test_제목은_다음_내용과_같은_쪽에_둔다():
    filler = [reports._Block([(10.0, f"채움 {i}")]) for i in range(40)]
    table = reports._Table(["머리"], [1.0], [["첫 줄 BODY"]])
    for extra in range(0, 25):
        doc = reports._layout(filler + [reports._Block([(10.0, "더")]) for _ in range(extra)] + [reports._one(reports._HEADING, "제목 HEAD"), table])
        for page in doc:
            text = page.get_text()
            assert ("HEAD" in text) == ("BODY" in text), extra


def test_결합_문자가_이어져도_폭을_넘지_않는다():
    text = "\u0301" * 400 + "가" * 200
    lines = reports._wrap(text, 10.0)
    assert all(reports._FONT.text_length(line, fontsize=10.0) <= reports._WIDTH + 0.01 for line in lines) and "".join(lines) == text


def test_엑셀에_재생성과_수정_칸도_나온다(api, svc, put, gold25):
    put(handoff(gold25, field_status=[{"msds_index": 0, "field": "product.name", "status": "수정됨"}]))
    svc.drain()
    wb = load_workbook(io.BytesIO(api.post(f"/api/judgments/{JOB}/reports", json={"format": "xlsx", "include": ALL}).content))
    assert wb["재생성 MSDS"].max_row > 10 and wb["수정한 칸"]["A1"].value == "product.name"
    wb = load_workbook(io.BytesIO(api.post(f"/api/judgments/{JOB}/reports", json={"format": "xlsx", "include": NOTHING}).content))
    assert wb.sheetnames == ["요약"]
