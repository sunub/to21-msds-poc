"""공용 코드 시험 (이미 동작해야 하는 것)."""
import copy

import pytest

from msds.checks.validator import run_to21_validator
from msds.common.align import item_path_map, keyed_flatten, to_keyed, unflatten_keyed
from msds.common.bundles import load_bundles
from msds.common.jsonpath import from_cell, get, set_, to_cell
from msds.common.merge import merge_bundles
from msds.common.priority import priority_of
from msds.common.schema import bundle_response_schema, to_strict, validate, validate_to21
from msds.extract.client import page_parts
from msds.extract.prompt_builder import build_bundle_prompt


def test_example25_is_valid(gold25):
    assert validate_to21(gold25) == []
    assert [r for r in run_to21_validator(gold25) if r["level"] == "오류"] == []


def test_keyed_roundtrip(gold25):
    m = gold25["msds"][0]
    assert unflatten_keyed(keyed_flatten(m)) == m


def test_keyed_alignment_ignores_order(gold25):
    a = copy.deepcopy(gold25["msds"][0])
    b = copy.deepcopy(a)
    b["regulations"].reverse()
    assert dict(keyed_flatten(a)) == dict(keyed_flatten(b))


def test_to_keyed(gold25):
    pm = item_path_map(gold25["msds"][0])
    assert to_keyed("components[0].content", pm).startswith("components[k=7664-93-9]")


def test_priority(gold25):
    paths = [p for p, _ in keyed_flatten(gold25["msds"][0])]
    assert priority_of("components[k=7664-93-9].cas_no") == 1
    assert any(priority_of(p) == 2 for p in paths if p.startswith("physchem"))
    assert any(priority_of(p) == 1 for p in paths if p.startswith("physchem"))
    assert priority_of("narratives[k=S4_EYE].statements[k=1]") == 3


def test_cells():
    assert from_cell(to_cell({"a": 1})) == {"a": 1}
    assert from_cell("") is None
    assert from_cell("KE-32570") == "KE-32570"
    assert from_cell('"01"') == "01"
    d = {}
    set_(d, "a[1].b", 3)
    assert get(d, "a[1].b") == 3


def test_bundle_schemas_accept_example(gold25):
    m = gold25["msds"][0]
    responses = {}
    for bid, b in load_bundles().items():
        r = {"msds": [{k: m.get(k) for k in b.keys}], "evidence": []}
        if b.doc_keys:
            r["doc"] = {"language": "ko", "msds_count": 1}
        s = bundle_response_schema(b.keys, b.doc_keys, with_review=True)
        assert validate(r, s) == [], bid
        assert "x-importance" not in str(to_strict(s))
        responses[bid] = r
    doc, review, warnings = merge_bundles(responses, {"doc_id": "T21-025", "source_file": "x.pdf", "pages": "10",
                                                      "text_layer": "정상", "language": "ko"}, engine="test")
    assert validate_to21(doc) == []
    assert warnings == []


def test_prompts_build():
    for bid in load_bundles():
        p = build_bundle_prompt(bid)
        assert "이번 묶음" in p and "[필드 정의]" in p and "[규칙]" in p


def _texts(parts):
    return [x["text"] for x in parts if x["type"] == "text"]


def test_page_parts_input_mode(tmp_path):
    """이미지만 조건(입력 비교 실험)은 정상 쪽의 글을 빼고, 깨진 쪽 안내는 두 조건 모두 그대로다."""
    img = tmp_path / "p.png"
    img.write_bytes(b"png")
    pages = [{"page": 1, "state": "정상", "source": "텍스트층", "text": "벤젠 71-43-2", "image": img},
             {"page": 2, "state": "글꼴깨짐", "source": None, "text": "", "image": img}]

    both = _texts(page_parts(pages, "이미지+글자"))
    assert both[0] == "=== 쪽 1 ===\n[텍스트층]\n벤젠 71-43-2"

    only = page_parts(pages, "이미지만")
    texts = _texts(only)
    assert texts[0] == "=== 쪽 1 ===\n[글자 없이 이미지만 보고 읽으세요]"
    assert texts[1] == both[1] == "=== 쪽 2 ===\n[텍스트층 없음 또는 깨짐: 이미지만 보고 읽으세요]"
    assert sum(x["type"] == "image_url" for x in only) == 2


def test_pick_pages():
    """부분 시험(--pages): 고른 쪽만 넣고, 모델 안내에 어느 쪽인지 적는다. 안 고르면 지금과 같다."""
    from msds.extract.runner import parse_pages, pick_pages

    assert parse_pages("2-4,6") == [2, 3, 4, 6]
    pages = [{"page": n} for n in (1, 2, 3)]
    assert pick_pages(pages, None) == (pages, "아래는 문서 전체 쪽이다.")
    got, note = pick_pages(pages, [3, 2])
    assert [p["page"] for p in got] == [2, 3]
    assert note == "아래는 문서의 2, 3쪽이다 (일부 쪽만 넣었다)."
    with pytest.raises(ValueError):
        pick_pages(pages, [4])
