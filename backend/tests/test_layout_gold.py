"""읽기 순서 회귀 시험: 골드 행 정답(개발 문서 10쪽)에서 표 행 묶기 점수가 떨어지지 않는가.

정답: data/gold/layout/rows_dev10.json (사람 검수, 2026-10-27). 채점: scripts/score_layout_rows.py
하한은 2026-10-27 점수다. layout을 고쳐 점수가 오르면 하한도 올린다. 내리지 않는다.
원본 PDF·OCR 결과는 저장소에 없어(D-47) 없으면 건너뛴다. 모델입력은 data/pages/의 전처리 결과를 읽는다
(전처리 버전이 코드와 다르면 건너뛴다).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "score_layout_rows.py"
FLOOR = {"텍스트층+표선": 148, "OCR+표선": 146, "모델입력": 149}   # 151행 중. 모델입력은 전처리 결과(쪽마다 텍스트층/OCR)


@pytest.fixture(scope="module")
def scores():
    sys.path.insert(0, str(SCRIPT.parent))   # 스크립트가 _common을 import한다
    spec = importlib.util.spec_from_file_location("score_layout_rows", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from msds.common import manifest, paths
    from msds.preprocess.render import PREPROCESS_VERSION

    if not mod.GOLD.exists():
        pytest.skip(f"골드 정답 없음: {mod.GOLD}")
    gold = json.loads(mod.GOLD.read_text(encoding="utf-8"))
    total = {name: {"rows": 0, "ok": 0} for name in FLOOR}
    for p in gold["pages"]:
        try:
            manifest.raw_pdf(manifest.get(p["doc_id"]))
        except FileNotFoundError:
            pytest.skip(f"data/raw/에 {p['doc_id']} 원본 없음")
        if not (paths.page_dir(p["doc_id"]) / "ocr_all" / f"p{p['page']:03d}.ocr.json").exists():
            pytest.skip(f"{p['doc_id']} {p['page']}쪽 OCR 결과 없음 (scripts/ocr_agreement.py)")
        meta = json.loads(paths.page_meta(p["doc_id"]).read_text(encoding="utf-8"))
        if meta.get("preprocess_version") != PREPROCESS_VERSION:
            pytest.skip(f"{p['doc_id']} 전처리 버전 {meta.get('preprocess_version')} ≠ {PREPROCESS_VERSION}. preprocess.py --force")
        rows = [r for t in p["tables"] for r in t["rows"]]
        texts = mod.sources(p["doc_id"], p["page"])
        for name in FLOOR:
            s = mod.score_rows(rows, texts[name])
            total[name]["rows"] += s["rows"]
            total[name]["ok"] += s["ok"]
    return total


@pytest.mark.parametrize("source", FLOOR)
def test_row_grouping_does_not_regress(scores, source):
    s = scores[source]
    assert s["rows"] == 151, "골드 행 수가 바뀌었다. 정답을 고쳤다면 하한을 다시 잰다"
    assert s["ok"] >= FLOOR[source], f"{source} 행 맞음 {s['ok']}/{s['rows']} < 하한 {FLOOR[source]}"
