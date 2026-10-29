"""OCR 결과 다시 쓰기: 같은 설정으로 OCR한 쪽은 OCR을 다시 하지 않는다 (scripts/ocr_agreement.same_config)."""
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ocr_agreement.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("ocr_agreement", SCRIPT)
oa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oa)


def test_same_config(tmp_path):
    f = tmp_path / "p001.ocr.json"
    assert not oa.same_config(f)                                            # 없음
    f.write_text(json.dumps({"dpi": 300, "config": {**oa.CONFIG, "seeded_from": "x"}, "items": []}))
    assert oa.same_config(f)                                                # 가져온 곳은 보지 않는다
    f.write_text(json.dumps({"dpi": 150, "config": {**oa.CONFIG, "dpi": 150}, "items": []}))
    assert not oa.same_config(f)                                            # 화질이 다르다
    f.write_text(json.dumps([{"text": "a", "box": [0, 0, 1, 1]}]))
    assert not oa.same_config(f)                                            # 설정이 없는 예전 형식
