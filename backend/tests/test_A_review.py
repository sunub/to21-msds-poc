"""역할 A 완료 기준: 이 파일의 시험이 모두 passed (skipped 0)."""
import copy

from conftest import todo
from msds.checks.validator import run_to21_validator
from msds.common.schema import validate_to21
from msds.review import build_gold as bg
from msds.review import make_sheet as ms
from msds.review.sheet_spec import COLUMNS


def test_same_docs_all_match(gold25):
    rows = todo(ms.build_rows, gold25, gold25, [], [], {}, {})
    assert rows and all(set(COLUMNS) <= set(r) for r in rows)
    assert {r["일치"] for r in rows} == {"일치"}


def test_mismatch_detected(gold25):
    other = copy.deepcopy(gold25)
    other["msds"][0]["components"][0]["content"]["lower_op"] = ">"
    rows = todo(ms.build_rows, gold25, other, [], [], {}, {})
    bad = [r for r in rows if r["일치"] != "일치"]
    assert len(bad) == 1 and "content" in bad[0]["경로"]


def test_scope_and_order(gold25):
    """검수 범위(1·2·3·8·9·11·12·14·15항 + 관리정보)만, 항 순서대로 (2026-10-29 기업 합의)."""
    rows = todo(ms.build_rows, gold25, gold25, [], [], {}, {})
    secs = [ms.section_of(r["경로"]) for r in rows]
    assert set(secs) <= set(ms.REVIEW_SECTIONS) and 13 not in secs and 14 in secs
    assert secs == sorted(secs, key=ms.REVIEW_SECTIONS.index)
    assert ms.section_of("msds[0].narratives[k=S8_ENGINEERING].statements") == 8
    assert ms.section_of("msds[0].extras[k=12|TOC].title_raw") == 12
    assert ms.section_of("msds[0].transport[k=육상].un_no") == 14


def test_roundtrip_gold(gold25, tmp_path):
    rows = todo(ms.build_rows, gold25, gold25, [], [], {}, {})
    for r in rows:
        r["검수 결과"] = "GPT 채택"
    path = tmp_path / "T21-025.xlsx"
    todo(ms.write_sheet, rows, {"문서 번호": "T21-025"}, path)
    rows2, info = todo(bg.read_sheet, path)
    gold, unreviewed = todo(bg.build_gold, rows2, gold25)
    assert unreviewed == []
    assert validate_to21(gold) == []
    assert [r for r in run_to21_validator(gold) if r["level"] == "오류"] == []
    for k in ("meta", "product", "hazard", "components", "regulations", "toxicity"):
        assert gold["msds"][0][k] == gold25["msds"][0][k], k
