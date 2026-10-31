"""class_lookup_db 시험: 가짜 repo 로 변환·빈 결과·접속 불가·캐시·25번 황산. 실제 DB 시험은 HTODB_SKIP=1 이면 건너뛴다."""
import json
import os
from pathlib import Path

import pytest

from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.class_lookup_db import make_db_class_lookup
from msds.compliance.mixture.rules_loader import load_class_map

MAP = load_class_map()["rows"]
SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude" / "T21-025.json"


def code(class_code, category, form=""):
    return next(r["to21_result_code"] for r in MAP if (r["class_code"], r["category"], r["form"]) == (class_code, category, form))


def cmap(code_, source="KR03", seq=1):
    return {"chem_id": "C1", "class_result_code": code_, "class_source_db_code": source, "hcode_seq": seq}


class FakeRepo:
    """htodb.repo 와 같은 반환 모양: chemicals → {"total","rows"}, classifications → {"rows","codes"}."""

    def __init__(self, table=None, error=None):
        self.table, self.error, self.calls = table or {}, error, []

    def chemicals(self, **kw):
        self.calls.append(kw["cas"])
        if self.error:
            raise self.error
        rows = [{"chem_id": i} for i in self.table.get(kw["cas"], {})]
        return {"total": len(rows), "rows": rows}

    def classifications(self, chem_id):
        return {"rows": [r for cas in self.table.values() for r in cas.get(chem_id, [])], "codes": {}}


SULFURIC = {"7664-93-9": {"C1": [cmap(code("HH_SKIN_CORR", "1")), cmap(code("HH_EYE_DMG", "1")),
                                  cmap(code("HH_ACUTE_INHAL", "2", "mist"), seq=1), cmap(code("HH_ACUTE_INHAL", "2", "mist"), seq=2)]},
            "7732-18-5": {}}


def test_정상_변환():
    rows = make_db_class_lookup(FakeRepo(SULFURIC))("7664-93-9")
    assert [(r["result_code"], r["source"], r["class_code"], r["category"], r["form"]) for r in rows] == [
        (code("HH_SKIN_CORR", "1"), "KR03", "HH_SKIN_CORR", "1", None),
        (code("HH_EYE_DMG", "1"), "KR03", "HH_EYE_DMG", "1", None),
        (code("HH_ACUTE_INHAL", "2", "mist"), "KR03", "HH_ACUTE_INHAL", "2", "mist")]  # hcode_seq 중복은 한 번
    assert rows.reason is None


def test_class_map에_없는_코드도_result_code는_남긴다():
    rows = make_db_class_lookup(FakeRepo({"1-1-1": {"C1": [cmap("GHS123456", "KR02")]}}))("1-1-1")
    assert rows[0]["result_code"] == "GHS123456" and rows[0]["class_code"] is None


def test_결과_없음은_빈_목록과_사유():
    rows = make_db_class_lookup(FakeRepo(SULFURIC))("7732-18-5")
    assert rows == [] and "등록되지 않은" in rows.reason
    rows = make_db_class_lookup(FakeRepo({"2-2-2": {"C1": []}}))("2-2-2")
    assert rows == [] and "분류결과 행 없음" in rows.reason


def test_접속_불가는_예외_없이_사유():
    rows = make_db_class_lookup(FakeRepo(error=ConnectionError("refused")))("7664-93-9")
    assert rows == [] and "ConnectionError" in rows.reason and "refused" in rows.reason


def test_HTODB_SKIP이면_기본_repo를_열지_않는다(monkeypatch):
    monkeypatch.setenv("HTODB_SKIP", "1")
    rows = make_db_class_lookup()("7664-93-9")
    assert rows == [] and "HTODB_SKIP=1" in rows.reason


def test_같은_CAS는_한_번만_조회():
    repo = FakeRepo(SULFURIC)
    lookup = make_db_class_lookup(repo)
    lookup("7664-93-9"), lookup("7664-93-9"), lookup("7732-18-5"), lookup("7732-18-5")
    assert repo.calls == ["7664-93-9", "7732-18-5"]


def test_25번_황산_build_components_gaps():
    if not SILVER.exists():
        pytest.skip("T21-025.json 없음")
    r = build_components(json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0], make_db_class_lookup(FakeRepo(SULFURIC)))
    sul, water = r["components"]
    assert len(sul["class_rows"]) == 3 and water["class_rows"] == []
    water_gap = next(g for g in r["gaps"] if g["field"] == "components[물].class_rows")
    assert "지식DB에 등록되지 않은 CAS" in water_gap["reason"]
    assert not any(g["field"] == "components[황산].class_rows" for g in r["gaps"])


@pytest.mark.skipif(os.environ.get("HTODB_SKIP") == "1", reason="HTODB_SKIP=1: 지식DB 시험을 일부러 끔")
def test_실제_DB_황산():
    rows = make_db_class_lookup()("7664-93-9")
    if not rows and rows.reason and "실패" in rows.reason:
        pytest.skip(rows.reason)
    assert all({"result_code", "source"} <= set(r) for r in rows)
