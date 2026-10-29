"""텍스트 추출 평가 점수 시험 (scripts/score_extraction.py)."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "score_extraction.py"
sys.path.insert(0, str(SCRIPT.parent))   # 스크립트가 _common을 import한다
spec = importlib.util.spec_from_file_location("score_extraction", SCRIPT)
se = importlib.util.module_from_spec(spec)
spec.loader.exec_module(se)


def test_row_keeps_punctuation():
    cells = ["1,3,5-트리메틸벤젠", "108-67-8", "KE-34411", "1- <5"]
    assert se.row_on_one_line(cells, "1,3,5-트리메틸벤젠  108-67-8 KE-34411 1-<5")
    # 하이픈·부등호를 다른 층으로 찍어 떨어져 나온 글은 틀림 (느슨한 채점은 글자·숫자만 봐서 맞다고 했다)
    assert not se.row_on_one_line(cells, "135트리메틸벤젠 108678 15\n, - - - <")


def test_row_must_be_on_one_line():
    cells = ["포름알데히드, polymers with branched 4-nonylphenol and ethylenediamine", "1152269-15-2"]
    assert se.row_on_one_line(cells, "포름알데히드, polymers with branched 4-nonylphenol and ethylenediamine 1152269-15-2 1-<5")
    assert not se.row_on_one_line(cells, "포름알데히드, polymers with branched 4-nonylphenol and 1152269-15-2\nethylenediamine")


def test_total_needs_both_parts():
    t = se.total({"ok": 129, "n": 151}, {"ok": 44, "n": 44})
    assert t["score"] == round((129 / 151 + 1) / 2 * 100, 1)
    assert t["pass"] is False   # 한쪽이 90 미만이면 평균이 90을 넘어도 불합격
    assert se.total({"ok": 140, "n": 151}, {"ok": 42, "n": 44})["pass"] is True


def test_table_cells_by_position():
    gold = [["물질명", "CAS No.", "함유량(%)"], ["벤젠", "71-43-2", ""]]
    md = "| 물질명 | CAS No. | 함유량(%) |\n| --- | --- | --- |\n| 벤젠 | 71-43-2 \\| x | |\n"
    got = se.read_md(md)
    assert got == [["물질명", "CAS No.", "함유량(%)"], ["벤젠", "71-43-2 | x", ""]]
    assert se.cells_ok(gold, got) == (4, 5)   # 빈 칸은 세지 않는다
    assert se.cells_ok(gold, []) == (0, 5)
