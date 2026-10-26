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


def test_label_beats_component_count():
    r = product_type(load_inputs(_doc({"type": "단일물질"}, [{"seq": 1}, {"seq": 2}])))
    assert r["type"] == "단일물질"


def test_as_of_falls_back_to_first_issue_date():
    doc = {"msds": [{"meta": {"first_issue_date": "2010-03-11"}}]}
    assert load_inputs(doc)["as_of_date"] == "2010-03-11"


def test_no_label_and_two_components_is_estimated_mixture():
    r = product_type(load_inputs(_doc(components=[{"seq": 1}, {"seq": 2}])))
    assert r["type"] == "혼합물"
    assert "추정" in r["basis"]


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
