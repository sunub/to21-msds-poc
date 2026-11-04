"""compliance/ 의 입력 로더·판별기 시험 (역할 D 완료 확인)."""
import json
from pathlib import Path

import pytest

from msds.compliance import knowledge
from msds.compliance.classifier import product_type
from msds.compliance.loader import load_inputs
from scripts.d_check import main as d_check_main

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "to21" / "v0.5" / "TO21_MSDS_추출예제_25_황산_v0.5.json"
needs_example = pytest.mark.skipif(not EXAMPLE.exists(), reason="TO21 제공 파일이 없습니다 (to21/README.md 참고)")


@pytest.fixture(scope="module")
def sulfuric():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


# ── 25번 황산 (TO21 정답 예제) ──────────────────────────────────────────

@needs_example
def test_loader_reads_sulfuric_acid(sulfuric):
    x = load_inputs(sulfuric)
    assert x["doc_id"] == "T21-025"
    assert x["as_of_date"] == "2022-06-29"
    assert [c["cas_no"] for c in x["components"]] == ["7664-93-9", "7732-18-5"]
    assert x["missing"] == []


@needs_example
def test_loader_attaches_cas_to_rows(sulfuric):
    # 15항 첫 행은 comp_ref "1" (황산)을 가리킨다
    assert load_inputs(sulfuric)["regulations"][0]["cas_no"] == "7664-93-9"


@needs_example
def test_loader_keeps_every_ph_row(sulfuric):
    # 황산 예제의 pH 는 세 줄이다. 하나로 덮어쓰면 안 된다
    assert len(load_inputs(sulfuric)["physchem"]["PH"]) == 3


@needs_example
def test_sulfuric_acid_is_mixture_by_label(sulfuric):
    r = product_type(load_inputs(sulfuric))
    assert r["type"] == "혼합물"
    assert r["basis"].startswith("3항")  # 성분 개수 추정이 아니라 표기를 따랐다


# ── 파일이 필요 없는 최소 케이스 ───────────────────────────────────────

def _doc(composition=None, components=None):
    return {"msds": [{"composition": composition, "components": components}]}


def test_단일물질_표기인데_유효_성분이_둘이면_불명확이다():  # 설계서 17장
    r = product_type(load_inputs(_doc({"type": "단일물질"}, [{"seq": 1}, {"seq": 2}])))
    assert r["type"] == "판단불가" and "2개" in r["basis"]


def test_불순물과_안정제는_유효_성분에서_뺀다():  # 설계서 17장 톨루엔 99.5% + 벤젠 0.05% 예
    comps = [{"seq": 1, "name": "톨루엔"}, {"seq": 2, "name": "벤젠", "content_note": "불순물"}, {"seq": 3, "name": "안정제 BHT"}]
    assert product_type(load_inputs(_doc({"type": "단일물질"}, comps)))["type"] == "단일물질"


def test_성분표가_없으면_혼합물_표기여도_불명확이다():  # 설계서 17장 유해성분 미함유 → 사람
    assert product_type(load_inputs(_doc({"type": "혼합물", "no_hazardous_component": True}, [])))["type"] == "판단불가"


def test_as_of_falls_back_to_first_issue_date():
    doc = {"msds": [{"meta": {"first_issue_date": "2010-03-11"}}]}
    assert load_inputs(doc)["as_of_date"] == "2010-03-11"


def test_표기_없이_성분이_둘이면_불명확이다():  # 설계서 17장: 혼합물 표기가 아니면 불명확
    assert product_type(load_inputs(_doc(components=[{"seq": 1}, {"seq": 2}])))["type"] == "판단불가"


@pytest.mark.parametrize("components", [[{"seq": 1, "content": {"lower": 99}}], [], None])
def test_no_label_and_fewer_than_two_components_is_undecidable(components):
    assert product_type(load_inputs(_doc(components=components)))["type"] == "판단불가"


def test_empty_msds_reports_missing_without_error():
    x = load_inputs({"msds": [{}]})
    assert {"as_of_date", "composition.type", "components", "hazard.classes", "hazard.signal_word"} <= set(x["missing"])


def test_missing_msds_key_reads_as_empty():
    assert "components" in load_inputs({})["missing"]


def test_d_check_skips_unreviewed_sidecar(tmp_path, capsys):
    gold = tmp_path / "T21-001.json"
    gold.write_text(json.dumps(_doc({"type": "단일물질"})), encoding="utf-8")
    sidecar = tmp_path / "T21-001.unreviewed.json"
    sidecar.write_text("not an extraction document", encoding="utf-8")

    assert d_check_main([str(tmp_path / "T21-*.json")]) == 0
    output = capsys.readouterr().out
    assert str(gold) in output
    assert str(sidecar) not in output


def test_empty_provider_returns_empty_reference_with_query_context():
    result = knowledge.EmptyProvider().get_reference("7664-93-9", "2022-06-29")

    assert result == {
        "cas_no": "7664-93-9",
        "as_of": "2022-06-29",
        "knowledge_version": None,
        "classes": [],
        "ate": {},
        "un_no": None,
        "source": None,
    }


def test_empty_provider_returns_empty_regulation_with_query_context():
    result = knowledge.EmptyProvider().get_regulation("7664-93-9", "2022-06-29")

    assert result == {
        "cas_no": "7664-93-9",
        "as_of": "2022-06-29",
        "knowledge_version": None,
        "rows": [],
    }


def test_empty_provider_returns_empty_mixture_rules_with_query_context():
    result = knowledge.EmptyProvider().classify_mixture([], "2022-06-29")

    assert result == {
        "as_of": "2022-06-29",
        "knowledge_version": None,
        "cut_off": {},
        "additivity": {},
    }


# ── 한계농도 (고시 별표6) ───────────────────────────────────────────────

SCHEMA = ROOT / "to21" / "v0.5" / "TO21_MSDS_추출스키마_v0.5.json"

# 고용노동부고시 제2026-26호 별표6 을 그대로 옮긴 기대값. 급성독성 한 행은 경로별 class_code 3개로 나눈다.
TABLE6 = {
    "HH_ACUTE_ORAL": [(None, 1.0)],
    "HH_ACUTE_DERMAL": [(None, 1.0)],
    "HH_ACUTE_INHAL": [(None, 1.0)],
    "HH_SKIN_CORR": [(None, 1.0)],
    "HH_EYE_DMG": [(None, 1.0)],
    "HH_RESP_SENS": [(None, 0.1)],
    "HH_SKIN_SENS": [(None, 0.1)],
    "HH_MUTAGEN": [(["1A", "1B"], 0.1), (["2"], 1.0)],
    "HH_CARCINOGEN": [(None, 0.1)],
    "HH_REPRO": [(None, 0.1)],
    "HH_STOT_SE": [(None, 1.0)],
    "HH_STOT_RE": [(None, 1.0)],
    "HH_ASPIRATION": [(None, 1.0)],
    "ENV_AQ_ACUTE": [(None, 1.0)],
    "ENV_AQ_CHRONIC": [(None, 1.0)],
    "ENV_OZONE": [(None, 0.1)],
}


def test_cut_off_matches_table6():
    cut_off = knowledge.load_cut_off()

    assert {code: [(r["categories"], r["threshold_value"]) for r in rows]
            for code, rows in cut_off.items()} == TABLE6


def test_cut_off_rows_are_inclusive_percent_with_source():
    # 제11조⑨: 한계농도 "미만"이면 제외하므로 계산에 넣는 조건은 >= 이다.
    for rows in knowledge.load_cut_off().values():
        for r in rows:
            assert (r["threshold_op"], r["threshold_unit"]) == (">=", "%")
            assert "별표6" in r["source"]


@pytest.mark.skipif(not SCHEMA.exists(), reason="TO21 제공 파일이 없습니다 (to21/README.md 참고)")
def test_cut_off_class_codes_exist_in_schema():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    cls = schema["properties"]["msds"]["items"]["properties"]["hazard"]["properties"]["classes"]
    codes = set(cls["items"]["properties"]["class_code"]["anyOf"][0]["enum"])

    assert set(knowledge.load_cut_off()) <= codes
