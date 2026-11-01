"""service/regenerated.py 시험. 나누기는 가짜 재생성 모듈로, 실제 모양은 TO21 제공 파일로 본다."""
import json
import types

import pytest

from msds.checks.validator import load_to21_module
from msds.common import paths
from msds.service import regenerated


def fake_module(*per_msds):
    class Alt(str):
        pass

    class Db:
        closed = False

        def close(self):
            Db.closed = True

    mod = types.SimpleNamespace(Alt=Alt, Db=Db)
    mod.to_db = lambda doc, path: (mod.__dict__.setdefault("paths", []).append(path), Db())[1]
    mod.regenerate = lambda db, msds_id: [Alt(x[4:]) if x.startswith("ALT:") else x for x in per_msds[msds_id - 1]]
    return mod


def test_splits_by_section_and_merges_repeated_heading():
    mod = fake_module(["물질안전보건자료", "1. 회사 정보", "가. 제품명", "- 젯소", "1. 회사 정보(원문)", "- 추가",
                       "2. 유해성", "1) 예방", "- 환기"])
    out = regenerated.regenerate_sections({"msds": [{}]}, mod)
    assert out == [{"msds_index": 0, "header": ["물질안전보건자료"], "sections": [
        {"section": 1, "title": "회사 정보", "lines": [{"kind": "head", "text": "가. 제품명"},
                                                   {"kind": "item", "text": "젯소"},
                                                   {"kind": "item", "text": "추가"}]},
        {"section": 2, "title": "유해성", "lines": [{"kind": "head", "text": "1) 예방"},
                                                 {"kind": "item", "text": "환기"}]}]}]


def test_number_that_is_not_next_section_stays_a_line():
    mod = fake_module(["1. 회사", "39. 조절제", "1.5 kg", "2. 유해성", "1. 다시 나온 앞 번호"])
    secs = regenerated.regenerate_sections({"msds": [{}]}, mod)[0]["sections"]
    assert [s["section"] for s in secs] == [1, 2]
    assert secs[0]["lines"] == [{"kind": "head", "text": "39. 조절제"}, {"kind": "head", "text": "1.5 kg"}]
    assert secs[1]["lines"] == [{"kind": "head", "text": "1. 다시 나온 앞 번호"}]


def test_hides_alt_lines_like_to_html():
    mod = fake_module(["1. 회사", "ALT:가. 제품명 젯소", "- 젯소"])
    assert regenerated.regenerate_sections({"msds": [{}]}, mod)[0]["sections"][0]["lines"] == [
        {"kind": "item", "text": "젯소"}]


@pytest.mark.parametrize("line,text", [
    ("- None", "값 없음"),
    ("- 환원제 : None", "환원제 : 값 없음"),
    ("최초 작성일: None  최종 개정일: 2023-11-24", "최초 작성일: 값 없음  최종 개정일: 2023-11-24"),
    ("- Nonel 비이온", "Nonel 비이온"),
])
def test_literal_none_becomes_missing_text(line, text):
    mod = fake_module(["1. 회사", line])
    assert regenerated.regenerate_sections({"msds": [{}]}, mod)[0]["sections"][0]["lines"][0]["text"] == text


def test_each_msds_uses_memory_db_and_closes_it():
    mod = fake_module(["1. 가"], ["1. 나"])
    out = regenerated.regenerate_sections({"msds": [{}, {}]}, mod)
    assert [m["msds_index"] for m in out] == [0, 1] and out[1]["sections"][0]["title"] == "나"
    assert mod.paths == [":memory:"] and mod.Db.closed


has_regen = pytest.mark.skipif(not (paths.TO21 / paths.TO21_FILES["regen"]).is_file(),
                               reason="TO21 제공 파일이 없습니다 (to21/README.md 참고)")


@has_regen
def test_real_module_gives_sixteen_sections_for_example():
    doc = json.loads(paths.to21_file("example25").read_text(encoding="utf-8"))
    out = regenerated.regenerate_sections(doc, load_to21_module("regen"))
    assert len(out) == len(doc["msds"])
    assert all([s["section"] for s in m["sections"]] == list(range(1, 17)) for m in out)


@has_regen
def test_real_module_survives_document_with_all_sections_failed():
    """전 항 실패 문서: 10-26판 재생성 파일은 여기서 KeyError로 멈췄다."""
    doc = json.loads(paths.to21_file("example25").read_text(encoding="utf-8"))
    empty = {"doc": doc["doc"], "msds": [{"product": {}, "meta": {}}]}
    out = regenerated.regenerate_sections(empty, load_to21_module("regen"))
    assert [s["section"] for s in out[0]["sections"]] == list(range(1, 17))
