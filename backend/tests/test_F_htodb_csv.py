"""지식DB 샘플 CSV 연결 시험 (설계서 21·43장).

- CsvRepo: to21_sample CSV를 htodb.repo 와 같은 모양으로 읽는다.
- make_db_tox_lookup: 독성 표의 급성독성 행을 ATE 수집 1단계 값으로 바꾼다.
앞쪽 시험은 이 파일 안에서 만든 가짜 CSV만 쓴다. 맨 뒤 25번 시험은 로컬에 to21_sample 이 있을 때만 돈다(D-47, 저장소에 없음).
"""
import csv
import json
import os
from pathlib import Path

import pytest

from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.htodb.regulation import RegulationProvider
from msds.compliance.mixture.ate_source import get_ate
from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.class_lookup_db import _DbRepo, make_db_class_lookup, make_db_tox_lookup
from msds.compliance.mixture.classify_mixture import classify_mixture_all
from msds.compliance.mixture.physical import physical_inputs
from msds.compliance.mixture.verdict import aggregate_verdicts

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude" / "T21-025.json"
A, B = "1111-11-1", "2222-22-2"  # 가짜 CAS


def _write(folder, table, header, rows):
    with open(folder / f"{table}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def repo(tmp_path):
    _write(tmp_path, "TB_ENG_CHEM_MASTER_INFO", ["CHEM_ID", "CAS_NO", "MOLECULAR_WEIGHT"],
           [["T-001", A, "100"], ["T-002", B, ""]])
    _write(tmp_path, "TB_GHS_CHEM_CLASS_MAP", ["CLASS_SOURCE_DB_CODE", "CLASS_RESULT_CODE", "CHEM_ID", "HCODE_SEQ", "H_CODE"],
           [["KR03", "GHS020601", "T-001", "2", "H314"], ["KR03", "GHS020601", "T-001", "1", "H314"],
            ["KR02", "GHS021001", "T-001", "1", "H350"]])
    _write(tmp_path, "TB_ENG_CHEM_TOXICITY_TEST_INFO",
           ["CHEM_ID", "EXPERIMENT_DIV", "DIV_CODE", "TOXIC_SEQ", "PRIMARY_VALUE_TEXT", "PRIMARY_VALUE"],
           [["T-001", "GHS02", "GHS0201", "1", "LD50 500 ㎎/㎏ 실험종 : Rat", "500"],
            ["T-001", "GHS02", "GHS0201", "2", "자극성 있음", ""],                      # 정성 문장 → 뺌
            ["T-001", "GHS02", "GHS0202", "1", "LD50 >2000 ㎎/㎏ 실험종 : Rabbit", ""],  # 부등호 → op ">"
            ["T-001", "GHS02", "GHS0204", "1", "LC50 10~20 ㎎/ℓ 실험종 : Rat", ""],     # 범위 → 하한·상한
            ["T-001", "GHS02", "GHS0205", "1", "LC50 1.2 ㎎/ℓ 실험종 : Rat", "1.2"],
            ["T-001", "GHS03", "GHS0311", "1", "LC50 1 mg/l", ""]])                     # 수생 → 급성독성 아님
    return CsvRepo(tmp_path)


def test_CsvRepo는_DB_repo와_같은_모양(repo):
    assert repo.available()
    chems = repo.chemicals(cas=A)
    assert chems["total"] == 1 and chems["rows"][0]["chem_id"] == "T-001" and chems["rows"][0]["molecular_weight"] == "100"
    rows = repo.classifications("T-001")["rows"]
    assert [(r["class_source_db_code"], r["class_result_code"], r["hcode_seq"]) for r in rows] == [
        ("KR02", "GHS021001", "1"), ("KR03", "GHS020601", "1"), ("KR03", "GHS020601", "2")]  # repo.py 와 같은 정렬
    assert len(repo.toxicity("T-001")["rows"]) == 6


def test_분류_조회에_DB_대신_CSV를_끼운다(repo):
    rows = make_db_class_lookup(repo)(A)
    assert [(r["result_code"], r["source"], r["class_code"], r["category"]) for r in rows] == [
        ("GHS021001", "KR02", "HH_CARCINOGEN", "1A"), ("GHS020601", "KR03", "HH_SKIN_CORR", "1")]  # H코드 순번 중복은 한 번만


def test_독성_조회는_급성독성만_ATE_행으로_바꾼다(repo):
    rows = make_db_tox_lookup(repo)(A)
    by = {(r["route"], r.get("form")): r for r in rows}
    assert set(by) == {("oral", None), ("dermal", None), ("inhal", "vapour"), ("inhal", "mist")}
    assert (by[("oral", None)]["op"], by[("oral", None)]["value"], by[("oral", None)]["unit"]) == ("=", 500.0, "mg/kg")
    assert (by[("dermal", None)]["op"], by[("dermal", None)]["value"]) == (">", 2000.0)
    vap = by[("inhal", "vapour")]
    assert (vap["op"], vap["value"], vap["op_hi"], vap["value_hi"]) == ("=", 10.0, "<=", 20.0)
    assert all(r["source"] == "TO21 독성DB" for r in rows)


def test_없는_CAS와_없는_파일은_멈추지_않고_이유를_남긴다(repo, tmp_path):
    assert "등록되지 않은" in make_db_tox_lookup(repo)("9999-99-9").reason
    assert "급성독성 수치 없음" in make_db_tox_lookup(repo)(B).reason
    missing = make_db_tox_lookup(CsvRepo(tmp_path / "없음"))(A)
    assert list(missing) == [] and "실패" in missing.reason


def test_독성DB_값은_ATE_수집_1단계로_쓰인다(repo):
    comp = {"db": make_db_tox_lookup(repo)(A), "classes": [], "msds": [{"route": "흡입", "form": "분진·미스트", "op": "=",
                                                                          "value": 9.9, "unit": "mg/L"}]}
    ate = get_ate(comp, "inhal", "mist")
    assert (ate["kind"], ate["value"], ate["step"]) == ("value", 1.2, 1) and ate["src"].startswith("TO21 독성DB")
    assert get_ate(comp, "inhal", "vapour")["value"] == 10.0  # 범위는 최솟값 (D-12)
    assert get_ate(comp, "dermal")["kind"] == "inequality"    # ">" 는 Σ 제외, 이용 가능 성분 (D-12)


@pytest.mark.skipif(not (CsvRepo().available() and SILVER.exists()), reason="to21_sample 또는 T21-025.json 없음")
def test_25번_황산_샘플DB_연결():
    item = json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0]
    db = CsvRepo()
    b = build_components(item, make_db_class_lookup(db), make_db_tox_lookup(db))
    results = classify_mixture_all(b["components"], b["mixture_props"], state="액체", physical=physical_inputs(item))
    acute = {(r["class_code"], r.get("form")): r for r in results if r["class_code"].startswith("HH_ACUTE")}
    mist = acute[("HH_ACUTE_INHAL", "분진·미스트")]
    assert round(mist["calc"]["ate_mix_low"], 3) == 0.403 and round(mist["calc"]["ate_mix_high"], 3) == 0.383  # 설계서 41장
    used = next(i for i in mist["inputs"] if i.get("name") == "황산")
    assert used["step"] == 1 and used["source"].startswith("TO21 독성DB")
    oral = acute[("HH_ACUTE_ORAL", None)]
    assert oral["result"]["low"] == oral["result"]["high"] == "분류안됨"  # ATEmix > 2,000
    # 물은 무독성 성분(params non_toxic_cas)이라 독성DB의 LD50 90,000 이 있어도 Σ에서 빠진다 → 설계서 24장 예제 1과 같은 값
    assert round(oral["calc"]["ate_mix_high"], 1) == 2183.7 and round(oral["calc"]["ate_mix_low"], 1) == 2301.1
    assert mist["calc"]["unknown_pct"] == 0  # 물이 '이용 불가 성분'으로 세어지지 않음
    out = aggregate_verdicts(results, item["hazard"]["classes"])
    inhal = [v for v in out["verdicts"] if v["class_code"] == "HH_ACUTE_INHAL"]
    assert len(inhal) == 1 and inhal[0]["type"] == "형태·세부 표기"
    carc = next(v for v in out["verdicts"] if v["class_code"] == "HH_CARCINOGEN")
    assert carc["verdict"] == "일치"  # 1A 는 고용노동부(KR03)에만 있음 — 출처 우선순위를 항목 단위로 적용


# ── 샘플 CSV ↔ 실제 HTODB(로컬 PostgreSQL) 대조 ─────────────────────────────
SAMPLE_CAS = ["7664-93-9", "7732-18-5", "64-17-5", "71-43-2", "108-88-3", "111-76-2", "1310-73-2", "1330-20-7"]


def _real_db():
    """실제 HTODB에 붙을 수 있으면 repo, 아니면 None. HTODB_SKIP=1 이면 시도하지 않는다."""
    if os.environ.get("HTODB_SKIP") == "1":
        return None
    try:
        repo = _DbRepo()
        repo.chemicals(cas="7664-93-9")
        return repo
    except Exception:
        return None


@pytest.mark.skipif(not CsvRepo().available(), reason="to21_sample 없음")
def test_샘플CSV와_실제DB의_분류·독성값이_같다():
    real = _real_db()
    if real is None:
        pytest.skip("실제 HTODB에 붙을 수 없음(HTODB_SKIP=1 또는 deploy/htodb 미적재)")
    sample = CsvRepo()
    for cas in SAMPLE_CAS:  # 샘플 8종: 같은 CAS를 두 창고에서 찾은 결과가 같아야 바꿔 끼울 수 있다(설계서 15장)
        assert list(make_db_class_lookup(sample)(cas)) == list(make_db_class_lookup(real)(cas)), cas
        assert list(make_db_tox_lookup(sample)(cas)) == list(make_db_tox_lookup(real)(cas)), cas
        reg = lambda repo: RegulationProvider(repo, knowledge_version="v").get_regulation(cas, None)["rows"]
        assert reg(sample) == reg(real), cas  # 15항 규제 행(항목 코드·기준 농도)도 같아야 한다


def test_지식DB_보정표의_행은_실제DB에_그대로_있고_읽을_때만_고친다():
    """보정 행이 가리키는 DB 행이 원래 값 그대로 있어야 한다. 지식DB가 고쳐지면 이 시험이 실패해 보정을 지울 때를 알린다."""
    from msds.compliance.htodb.regulation import fixes, regulation_rows
    real = _real_db()
    if real is None:
        pytest.skip("실제 HTODB에 붙을 수 없음(HTODB_SKIP=1 또는 deploy/htodb 미적재)")
    for (cas, item_id), f in fixes().items():
        chem = real.chemicals(cas=cas)["rows"][0]["chem_id"]
        raw = next(r for r in regulation_rows(real.regulations(chem)) if r["regulate_item_id"] == item_id)
        assert f"{raw['threshold_op']}{raw['threshold_value']:g}" == f["db_value"], f["fix_id"]
        row = next(r for r in RegulationProvider(real).get_regulation(cas, None)["rows"] if r["regulate_item_id"] == item_id)
        op, value, state = FIX_CASES[f["fix_id"]][-1]  # 보정표가 아니라 법령에서 정한 기대값과 대조
        assert (row["threshold_op"], row["threshold_value"], row["condition"]["state"]) == (op, value, state), f["fix_id"]
        assert f["fix_id"] in row["source"] and row["condition"]["ph_max"] == raw["condition"]["ph_max"]



# 보정 행마다 판정이 어떻게 바뀌는지 하나씩. 보정이 빠지거나 새로 생기면 이 표도 고쳐야 한다(결정 B-43)
_TALC = "석면이 1% 이상 함유된 탈크만 해당"
FIX_CASES = {  # fix_id: (CAS, 함량 %, 법, 항목, MSDS 기재, 보정 후 판정, 보정 후 (부호, 기준 %, 적용 조건))
    "FX-01": ("61788-33-8", 1.0, "OSH", "OSH_PROHIBIT", "비해당", "일치", (">", 1.0, None)),    # 1% 이하는 제외. 보정 전에는 경계
    "FX-02": ("14807-96-6", 0.5, "CCA", "CCA_PROHIBIT", "비해당", "경계", (">=", 0.0, _TALC)),  # 석면 함유 탈크만, 함량 기준 없음. 보정 전에는 일치(30%면 규제 누락 높음)
    "FX-03": ("14807-96-6", 0.5, "OSH", "OSH_PROHIBIT", "비해당", "경계", (">=", 0.0, _TALC)),  # 제9호는 1% 제외가 없다. 보정 전에는 일치
    "FX-04": ("12001-29-5", 1.0, "OSH", "OSH_PROHIBIT", "비해당", "경계", (">=", 1.0, None)),  # 1% 이상 금지. 보정 전에는 일치
}


@pytest.mark.parametrize("fix_id", sorted(FIX_CASES))
def test_지식DB_보정은_판정에_반영되고_근거에_보정_번호가_남는다(fix_id):
    from msds.compliance.htodb.regulation import fixes
    from msds.compliance.sec15_judge import judge_sec15
    assert {f["fix_id"] for f in fixes().values()} == set(FIX_CASES)
    real = _real_db()
    if real is None:
        pytest.skip("실제 HTODB에 붙을 수 없음")
    cas, content, law, item, said, verdict, _ = FIX_CASES[fix_id]
    inp = {"as_of_date": "2026-11-01", "physchem": {}, "dangerous_goods": [],
           "components": [{"seq": 1, "cas_no": cas, "content": {"raw": str(content), "value": content, "unit": "%"}}],
           "regulations": [{"comp_ref": "1", "law": l, "item_code": i, "applicable": said, "threshold": None, "value_raw": None}
                           for l, i in (("CCA", "CCA_PROHIBIT"), ("OSH", "OSH_PROHIBIT"))]}
    out = judge_sec15(inp, RegulationProvider(real))
    v = next(v for v in out["verdicts"] if v["item_code"] == item and v["comp_ref"] == "1")
    assert v["verdict"] == verdict and f"보정 {fix_id}" in " ".join(v["source"]), v


@pytest.mark.parametrize("threshold, verdict", [(None, "일치"), (0.0, "일치"), (1.0, "일치"), (5.0, "불일치")])
def test_탈크를_금지물질로_적은_MSDS의_0퍼센트_1퍼센트_기준은_일치(threshold, verdict):
    """MSDS는 탈크 금지물질을 '0% 이상'(함유하면) 또는 '석면이 1% 이상 함유된 탈크'로 적는다. 1%는 조건의 숫자다(결정 B-43)."""
    from msds.compliance.sec15_judge import judge_sec15
    real = _real_db()
    if real is None:
        pytest.skip("실제 HTODB에 붙을 수 없음")
    thr = None if threshold is None else {"value": threshold, "unit": "%"}
    inp = {"as_of_date": "2026-11-01", "physchem": {}, "dangerous_goods": [],
           "components": [{"seq": 1, "cas_no": "14807-96-6", "content": {"raw": "30", "value": 30.0, "unit": "%"}}],
           "regulations": [{"comp_ref": "1", "law": l, "item_code": i, "applicable": "해당", "threshold": thr, "value_raw": None}
                           for l, i in (("CCA", "CCA_PROHIBIT"), ("OSH", "OSH_PROHIBIT"))]}
    out = judge_sec15(inp, RegulationProvider(real))["verdicts"]
    assert {v["verdict"] for v in out if v["comp_ref"] == "1" and v["item_code"] in ("CCA_PROHIBIT", "OSH_PROHIBIT")} == {verdict}
