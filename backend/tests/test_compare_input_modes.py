"""입력 비교 실험 채점 시험 (scripts/compare_input_modes.py)."""
import copy
import importlib.util
import sys
from pathlib import Path

from msds.checks.validator import load_to21_module

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_input_modes.py"
sys.path.insert(0, str(SCRIPT.parent))   # 스크립트가 _common을 import한다
spec = importlib.util.spec_from_file_location("compare_input_modes", SCRIPT)
cim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cim)


def test_mismatch_is_one_cell_even_if_wrong_differently():
    a = [("신호어", "불일치", "정답='위험' / 추출='경고'")]
    b = [("신호어", "불일치", "정답='위험' / 추출=None")]
    out = cim.compare_cells(a, b)
    assert out["A만 틀림"] == [] and out["B만 틀림"] == []
    assert out["둘 다 틀림"] == [("신호어", "불일치", "정답='위험'")]


def test_cells_split_by_condition(gold25):
    scorer = load_to21_module("scorer")
    bad = copy.deepcopy(gold25)
    bad["msds"][0]["components"][0]["cas_no"] = "0000-00-0"
    _, det_a = cim.score_doc(scorer, gold25, bad)
    _, det_b = cim.score_doc(scorer, gold25, gold25)
    out = cim.compare_cells(det_a, det_b)
    assert out["B만 틀림"] == [] and out["둘 다 틀림"] == []
    assert ("구성성분(CAS 기준 매칭)", "오추출", "0000-00-0") in out["A만 틀림"]
