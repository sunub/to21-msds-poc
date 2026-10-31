"""scripts/run_silver.py의 apply_conventions_to_silver 시험.

가짜 실버 파일은 tmp_path에만 만든다. 실제 data/silver/는 읽거나 쓰지 않는다. 모델 서버를 부르지 않는다.
"""
import importlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module("run_silver")


def fake_silver(tmp_path: Path, applied: bool = False) -> Path:
    msds = {
        "exposure_limits": [{"standard": "국내", "limit_type": "TWA" if applied else "기타",
                             "q": {"status": "자료없음"}}],
        "toxicity": [{"comp_ref": "C1", "endpoint": "TX_ORAL", "status": "자료없음",
                      "descriptor": "결과기술" if applied else None,
                      "q": {"raw": "자료없음", "status": "자료없음"} if applied else None}],
    }
    p = tmp_path / "T21-X01.json"
    p.write_text(json.dumps({"doc": {"doc_id": "T21-X01"}, "msds": [msds]}, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def test_applies_conventions_and_rewrites(tmp_path):
    rs = load_script()
    p = fake_silver(tmp_path)
    assert rs.apply_conventions_to_silver(p) == 1
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    m = data["msds"][0]
    assert m["exposure_limits"][0]["limit_type"] == "TWA"
    assert m["toxicity"][0]["descriptor"] == "결과기술"
    assert text == json.dumps(data, ensure_ascii=False, indent=2)
    assert '\n  "doc"' in text


def test_already_conventional_file_is_unchanged(tmp_path):
    rs = load_script()
    p = fake_silver(tmp_path, applied=True)
    before = p.read_text(encoding="utf-8")
    assert rs.apply_conventions_to_silver(p) == 0
    assert p.read_text(encoding="utf-8") == before
