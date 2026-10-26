"""역할 F 완료 기준: 이 파일의 시험이 모두 passed (skipped 0)."""
import copy

from conftest import todo
from msds.evaluate import score as sc


def test_perfect(gold25):
    r = todo(sc.score_pair, gold25, gold25)
    assert round(r["weighted"], 1) == 100.0 and r["must_pass"]


def test_cas_typo_fails(gold25):
    bad = copy.deepcopy(gold25)
    bad["msds"][0]["components"][0]["cas_no"] = "7664-93-8"
    r = todo(sc.score_pair, gold25, bad)
    assert not r["must_pass"]


def test_set(gold25, tmp_path):
    res = todo(sc.score_set, [("T21-025", gold25, gold25)])
    out = todo(sc.write_report, res, tmp_path, "시험")
    assert out.exists()
