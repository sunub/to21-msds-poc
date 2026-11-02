"""2차 정합성 검증 묶음 시험 (설계서 8장 흐름, 14장 get_reference, 18장 단일물질, 44장 결과 구조).

- ReferenceProvider: 지식DB 분류 → 단일물질 기준 분류. 출처 우선순위 D-05는 항목 단위, 국내 고시 밖 구분은 참고(D-18).
- run_consistency: 추출 JSON 한 건 → 2항·15항 판정을 consistency 블록으로.
앞쪽은 이 파일 안의 가짜 CSV만 쓴다. 뒤쪽은 로컬에 to21_sample·silver 추출본이 있을 때만 돈다(D-47, 저장소에 없음).
"""
import csv
import json
from pathlib import Path

import pytest

from msds.compliance.consistency import run_consistency
from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.htodb.reference import ReferenceProvider

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude"
A = "1111-11-1"
VERDICTS = {"일치", "불일치", "경계", "근거부족"}


def _write(folder, table, header, rows=()):
    with open(folder / f"{table}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def repo(tmp_path):
    _write(tmp_path, "TB_ENG_CHEM_MASTER_INFO", ["CHEM_ID", "CAS_NO", "MOLECULAR_WEIGHT"], [["T-001", A, "100"]])
    _write(tmp_path, "TB_GHS_CHEM_CLASS_MAP", ["CLASS_SOURCE_DB_CODE", "CLASS_RESULT_CODE", "CHEM_ID", "HCODE_SEQ", "H_CODE"],
           [["KR02", "GHS020104", "T-001", "1", "H302"],   # 경구 4 (환경부)
            ["KR03", "GHS020103", "T-001", "1", "H301"],   # 경구 3 (고용노동부) → 같은 항목이라 환경부가 우선
            ["KR03", "GHS020601", "T-001", "1", "H314"],   # 피부 1 (고용노동부에만 있음) → 그대로 씀
            ["KR02", "GHS020505", "T-001", "1", ""]])      # 흡입 분진·미스트 5 → 국내 고시 밖, 참고
    _write(tmp_path, "TB_ENG_CHEM_TOXICITY_TEST_INFO",
           ["CHEM_ID", "EXPERIMENT_DIV", "DIV_CODE", "TOXIC_SEQ", "PRIMARY_VALUE_TEXT", "PRIMARY_VALUE"],
           [["T-001", "GHS02", "GHS0201", "1", "LD50 500 ㎎/㎏ 실험종 : Rat", "500"]])
    _write(tmp_path, "TB_ENG_REGULA_CHEM_MAP", ["CHEM_ID", "REGULATE_ID", "REGULATE_ITEM_ID", "IS_DEL"])
    _write(tmp_path, "TB_ENG_REG_NOTICE_STD", ["CHEM_ID", "REGULATE_ITEM_ID", "NOTICE_SEQ", "STD_SEQ", "IS_DEL"])
    return CsvRepo(tmp_path)


def test_기준분류는_항목마다_환경부를_먼저_쓰고_고시_밖_구분은_참고로(repo):
    ref = ReferenceProvider(repo).get_reference(A, "2024-01-01")
    got = {(c["class_code"], c["category"], c["route_form"], c["source"]) for c in ref["classes"]}
    assert got == {("HH_ACUTE_ORAL", "4", None, "환경부"), ("HH_SKIN_CORR", "1", None, "고용노동부")}
    assert [(c["class_code"], c["category"], c["route_form"]) for c in ref["reference_only"]] == \
        [("HH_ACUTE_INHAL", "5", "분진·미스트")]
    assert ref["knowledge_version"] and ref["ate"]["rows"][0]["value"] == 500.0
    miss = ReferenceProvider(repo).get_reference("9999-99-9", None)
    assert miss["knowledge_version"] is None and miss["classes"] == [] and miss["reason"]


def _doc(classes, cas=A, kind="단일물질"):
    return {"doc": {"doc_id": "FAKE-1"},
            "msds": [{"meta": {"last_revision_date": "2024-01-01"}, "composition": {"type": kind},
                      "components": [{"seq": 1, "name": "가짜", "cas_no": cas,
                                      "content": {"value": 100, "unit": "%", "status": "값있음"}}],
                      "hazard": {"classes": [{"class_code": c, "category": k, "route_form": f} for c, k, f in classes],
                                 "signal_word": "위험"},
                      "regulations": []}]}


def test_단일물질_2항은_기준분류와_비교한다(repo):
    out = run_consistency(_doc([("HH_ACUTE_ORAL", "3", None), ("HH_SKIN_CORR", "1", None), ("HH_CARCINOGEN", "2", None)]),
                          repo)
    c = out["consistency"]
    assert out["doc_id"] == "FAKE-1" and c["product_type"]["value"] == "단일물질"
    by = {f["class_code"]: f for f in c["findings"] if f["section"] == "2"}
    assert (by["HH_ACUTE_ORAL"]["verdict"], by["HH_ACUTE_ORAL"]["type"]) == ("불일치", "과대분류")  # MSDS 3 > 기준 4
    assert by["HH_SKIN_CORR"]["verdict"] == "일치"
    assert by["HH_CARCINOGEN"]["verdict"] == "근거부족" and "설계서 18장" in by["HH_CARCINOGEN"]["reason"]
    assert any("D-05" in a for a in by["HH_SKIN_CORR"]["assumptions"])
    assert [e["status"] for e in c["excluded"] if e["section"] == "2"] == ["참고"]  # 흡입 5


def test_결과_구조는_설계서_44장_consistency_블록(repo):
    c = run_consistency(_doc([("HH_SKIN_CORR", "1", None)]), repo)["consistency"]
    assert set(c) >= {"engine_version", "as_of", "knowledge", "product_type", "summary", "findings", "excluded",
                      "gaps", "assumptions", "missing"}
    assert c["as_of"] == "2024-01-01" and c["knowledge"]["provider"] == "to21_sample"
    ids = [f["id"] for f in c["findings"]]
    assert ids == sorted(ids, key=lambda i: (i.split("-")[1] != "2", i)) and len(set(ids)) == len(ids)
    s = c["summary"]
    for k in ("일치", "불일치", "경계", "근거부족"):
        assert s["전체"][k] == s["2항"][k] + s["15항"][k]
    dg = next(f for f in c["findings"] if f["section"] == "15")  # 성분 규제 행이 없어도 제품 단위 위험물 한 줄은 남는다
    assert dg["item_code"] == "DG_HAZMAT"


def test_지식DB에_없는_CAS는_멈추지_않고_근거부족(repo):
    c = run_consistency(_doc([("HH_SKIN_CORR", "1", None)], cas="9999-99-9"), repo)["consistency"]
    f = next(f for f in c["findings"] if f["section"] == "2")
    assert f["verdict"] == "근거부족" and "등록되지 않은" in f["reason"]


# ── 로컬 샘플(저장소 밖)이 있을 때 ─────────────────────────────────
need_sample = pytest.mark.skipif(not (CsvRepo().available() and (SILVER / "T21-025.json").exists()),
                                 reason="to21_sample 또는 silver 추출본 없음")


def _run(name, i=0):
    return run_consistency(json.loads((SILVER / f"{name}.json").read_text(encoding="utf-8")), CsvRepo(), i)["consistency"]


@need_sample
def test_25번_황산_묶음_요약은_e2e_고정본과_같다():
    c = _run("T21-025")
    assert c["product_type"]["value"] == "혼합물"
    assert {k: c["summary"]["2항"][k] for k in VERDICTS} == {"일치": 21, "불일치": 3, "경계": 0, "근거부족": 1}
    assert {k: c["summary"]["15항"][k] for k in VERDICTS} == {"일치": 36, "불일치": 2, "경계": 0, "근거부족": 0}
    assert c["summary"]["전체"]["심각도"] == {"높음": 1, "중간": 2, "낮음": 2}


@need_sample
def test_벤젠_단일물질():
    c = _run("T21-S016")
    assert c["product_type"]["value"] == "단일물질"
    f15 = {(f["comp_ref"], f["item_code"]): f for f in c["findings"] if f["section"] == "15"}
    prohibit = f15[("1", "OSH_PROHIBIT")]
    assert prohibit["verdict"] == "경계" and "고무풀" in " ".join(prohibit["db_text"])  # 결정 6, 근거는 DB 조문
    psm = next(e for e in c["excluded"] if e["section"] == "15" and e["comp_ref"] == "1" and e["item_code"] == "OSH_PSM")
    assert "결정 10" in psm["reason"]                        # 인화성 액체 범주의 PSM은 판정하지 않음
    carc = next(f for f in c["findings"] if f["section"] == "2" and f["class_code"] == "HH_CARCINOGEN")
    assert carc["verdict"] == "일치" and carc["our_value"]["low"] == "1A"


@need_sample
def test_silver_추출본_전체가_멈추지_않고_규칙대로_나온다():
    n = 0
    for path in sorted(SILVER.glob("*.json")):
        if path.name.endswith(".review.json"):  # 추출 검수 기록(목록)이라 추출본이 아님
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for i in range(len(doc.get("msds") or [])):
            c = run_consistency(doc, CsvRepo(), i)["consistency"]
            n += 1
            for f in c["findings"]:
                assert f["verdict"] in VERDICTS, (path.stem, f["id"])
                assert (f["verdict"] == "불일치") == bool(f["type"]), (path.stem, f["id"])  # 유형은 불일치에만
                assert f["reason"], (path.stem, f["id"])
            assert all(e.get("reason") for e in c["excluded"]), path.stem
    assert n >= 20
