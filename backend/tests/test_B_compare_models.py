"""scripts/compare_models.py 시험.

결과·정답 문서는 test_B_expand의 가짜 MSDS를 펼친 것이고, 실행 폴더·정답 폴더·manifest는 모두 tmp_path에 만든다 (D-43).
저장소의 runs/, data/는 읽거나 쓰지 않는다. 모델 서버를 부르지 않는다.
"""
import copy
import importlib
import json
import statistics
from pathlib import Path

import pytest
import yaml

from msds.common import manifest, paths
from msds.evaluate.score import score_pair, score_set
from msds.extract import expand as ex
from test_B_expand import DOC_META, LINES, responses

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
X01, X02, X09 = "T21-X01", "T21-X02", "T21-X09"
ROWS = [
    {"doc_id": X01, "source_file": "가상 A.pdf", "purpose": "개발", "pages": "7", "text_layer": "정상", "language": "ko"},
    {"doc_id": X02, "source_file": "가상 B.pdf", "purpose": "개발", "pages": "7", "text_layer": "정상", "language": "ko"},
    {"doc_id": X09, "source_file": "가상 C.pdf", "purpose": "평가", "pages": "7", "text_layer": "정상", "language": "ko"},
]


def make_doc(doc_id: str = X01, **empty) -> dict:
    """가짜 TO21 문서. empty에 든 표는 비운다(예: toxicity=True)."""
    doc, _ = ex.to_to21({**DOC_META, "doc_id": doc_id}, [responses()], LINES, "가상엔진")
    for table, on in empty.items():
        if on:
            doc["msds"][0][table] = []
    return doc


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def make_run(root: Path, name: str, docs: dict, model_tag="m1", prompt="p1", pages="data/pages",
             timing: list | None = None, checks: dict | None = None) -> Path:
    run = root / "runs" / name
    run.mkdir(parents=True)
    (run / "run_info.yaml").write_text(
        yaml.safe_dump({"model_tag": model_tag, "prompt_version": prompt, "pages_dir": pages}), encoding="utf-8")
    for d, doc in docs.items():
        write_json(run / "outputs" / f"{d}.json", doc)
    for d, c in (checks or {}).items():
        write_json(run / "checks" / f"{d}.json", c)
    if timing:
        (run / "timing.jsonl").write_text(
            "".join(json.dumps({"doc_id": d, "stage": "total", "seconds": s}) + "\n" for d, s in timing),
            encoding="utf-8")
    return run


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "manifest.csv"
    manifest.save(ROWS, path)
    orig = manifest.load
    monkeypatch.setattr(manifest, "load", lambda p=path: orig(p))
    monkeypatch.setattr(paths, "run_dir", lambda name: tmp_path / "runs" / name)
    gold = tmp_path / "gold"
    for d in (X01, X02, X09):
        write_json(gold / f"{d}.json", make_doc(d))
    return tmp_path


@pytest.fixture
def cm(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("compare_models")


def golds(env: Path, docs=(X01, X02)) -> dict:
    return {d: json.loads((env / "gold" / f"{d}.json").read_text(encoding="utf-8")) for d in docs}


def loaded(cm, env: Path, specs: list[tuple[str, str]]) -> list[dict]:
    return [cm.load_run(env / "runs" / name, label) for label, name in specs]


def two_docs(**empty_x01) -> dict:
    return {X01: make_doc(X01, **empty_x01), X02: make_doc(X02)}


# ── row_counts ─────────────────────────────────────────

def test_row_counts(cm):
    c = cm.row_counts(make_doc())
    assert c == {"components": 2, "exposure_limits": 1, "physchem": 1, "toxicity": 1, "cmr": 1,
                 "ecotox": 0, "regulations": 1, "intl_class": 0, "extras": 1}


def test_row_counts_sums_msds(cm):
    doc = make_doc()
    doc["msds"].append(copy.deepcopy(doc["msds"][0]))
    c = cm.row_counts(doc)
    assert c["components"] == 4 and c["toxicity"] == 2 and c["extras"] == 2 and c["ecotox"] == 0


# ── load_run ───────────────────────────────────────────

def test_load_run(cm, env):
    make_run(env, "r1", two_docs(), model_tag="tagA", prompt="v9", pages="data/pages/chars_wrap",
             timing=[(X01, 100), (X01, 350), (X02, 50)])
    r = cm.load_run(env / "runs" / "r1")
    assert (r["label"], r["name"]) == ("r1", "r1")
    assert (r["model_tag"], r["prompt_version"], r["pages_dir"]) == ("tagA", "v9", "data/pages/chars_wrap")
    assert set(r["outputs"]) == {X01, X02} and r["checks"] == {}
    assert r["seconds"] == {X01: 350, X02: 50}
    assert cm.load_run(env / "runs" / "r1", "라벨")["label"] == "라벨"


# ── compare_runs ───────────────────────────────────────

def test_identical_run_scores_full(cm, env):
    make_run(env, "r1", two_docs())
    runs = loaded(cm, env, [("a", "r1")])
    res = cm.compare_runs(runs, golds(env), [X01, X02])
    r = res["runs"][0]
    assert r["weighted"] == pytest.approx(100)
    assert r["value_score"] == pytest.approx(1.0)
    assert r["rows"]["components"] == {"pred": 4, "gold": 4, "ratio": 1.0}
    assert r["rows"]["ecotox"] == {"pred": 0, "gold": 0, "ratio": None}
    assert r["time"] == {"median": None, "max": None, "over_limit": 0}
    assert res["docs"] == [X01, X02]


def test_run_matches_score_set(cm, env):
    make_run(env, "r1", two_docs(toxicity=True))
    runs = loaded(cm, env, [("a", "r1")])
    g = golds(env)
    res = cm.compare_runs(runs, g, [X01, X02])
    expect = score_set([(d, g[d], runs[0]["outputs"][d]) for d in (X01, X02)])
    r = res["runs"][0]
    assert r["weighted"] == pytest.approx(expect["weighted"]) and r["weighted"] < 100
    assert (r["must_passed"], r["must_total"]) == (expect["must_passed_count"], expect["must_total"])
    assert r["items"] == {i["name"]: i["score"] for i in expect["items"]}
    assert r["levels"] == {i["name"]: i["level"] for i in expect["items"]}
    assert r["rows"]["toxicity"]["pred"] == 1 and r["rows"]["toxicity"]["gold"] == 2
    assert r["docs"][X01]["weighted"] == pytest.approx(expect["docs"][X01]["weighted"])


def test_spread_within_group(cm, env):
    make_run(env, "r1", two_docs())
    make_run(env, "r2", two_docs(toxicity=True))
    runs = loaded(cm, env, [("a", "r1"), ("b", "r2")])
    g = golds(env)
    res = cm.compare_runs(runs, g, [X01, X02])
    assert len(res["groups"]) == 1
    grp = res["groups"][0]
    assert grp["runs"] == ["a", "b"] and grp["spread"] > 0
    assert grp["row_spread"]["toxicity"] == 1 and grp["row_spread"]["components"] == 0
    hi = score_pair(g[X01], runs[0]["outputs"][X01])
    lo = score_pair(g[X01], runs[1]["outputs"][X01])
    positive = {k: v for k, v in grp["item_spread"].items() if v > 0}
    assert positive
    for name, v in positive.items():
        a = {i["name"]: i["score"] for i in hi["items"]}[name]
        b = {i["name"]: i["score"] for i in lo["items"]}[name]
        assert v == pytest.approx(abs(a - b) / 2)          # X02는 같고 X01만 달라서 문서 2건 평균
    assert grp["doc_weighted_spread"] == pytest.approx(abs(hi["weighted"] - lo["weighted"]) / 2)


def test_identical_runs_have_zero_spread(cm, env):
    make_run(env, "r1", two_docs())
    make_run(env, "r2", two_docs())
    res = cm.compare_runs(loaded(cm, env, [("a", "r1"), ("b", "r2")]), golds(env), [X01, X02])
    assert res["groups"][0]["spread"] == 0
    assert res["groups"][0]["weighted_mean"] == pytest.approx(100)


def test_different_prompt_makes_two_groups(cm, env):
    make_run(env, "r1", two_docs(), prompt="p1")
    make_run(env, "r2", two_docs(toxicity=True), prompt="p2")
    res = cm.compare_runs(loaded(cm, env, [("a", "r1"), ("b", "r2")]), golds(env), [X01, X02])
    assert len(res["groups"]) == 2
    for grp in res["groups"]:
        assert grp["spread"] is None and grp["item_spread"] == {} and grp["row_spread"] == {}
        assert len(grp["runs"]) == 1


def test_time_uses_last_total_and_limit(cm, env):
    make_run(env, "r1", two_docs(), timing=[(X01, 100), (X01, 350), (X02, 50)])
    res = cm.compare_runs(loaded(cm, env, [("a", "r1")]), golds(env), [X01, X02])
    r = res["runs"][0]
    assert r["docs"][X01]["seconds"] == 350
    assert r["time"] == {"median": statistics.median([350, 50]), "max": 350, "over_limit": 1}
    assert r["time"]["median"] == 200


def test_checks_counts(cm, env):
    checks = {X01: {"sections": [{"ok": True}, {"ok": False}, {"ok": True}],
                    "to21_validator": [{"rule": "V1"}, {"rule": "V2"}], "schema_errors": ["e"]}}
    make_run(env, "r1", two_docs(), checks=checks)
    r = cm.compare_runs(loaded(cm, env, [("a", "r1")]), golds(env), [X01, X02])["runs"][0]
    assert (r["sections_failed"], r["validator_errors"], r["schema_errors"]) == (1, 2, 1)
    assert r["docs"][X01]["sections_failed"] == 1 and r["docs"][X02]["validator_errors"] == 0


# ── select_docs ────────────────────────────────────────

def test_select_docs_missing_in_a_run(cm, env):
    make_run(env, "r1", two_docs())
    make_run(env, "r2", {X01: make_doc(X01)})
    runs = loaded(cm, env, [("run_a", "r1"), ("run_b", "r2")])
    docs, excluded = cm.select_docs(runs, env / "gold")
    assert docs == [X01]
    assert len(excluded) == 1 and excluded[0]["doc_id"] == X02
    assert "run_b" in excluded[0]["reason"] and "run_a" not in excluded[0]["reason"]


def test_select_docs_missing_gold(cm, env):
    (env / "gold" / f"{X02}.json").unlink()
    make_run(env, "r1", two_docs())
    docs, excluded = cm.select_docs(loaded(cm, env, [("a", "r1")]), env / "gold")
    assert docs == [X01]
    assert excluded == [{"doc_id": X02, "reason": "정답 없음"}]


def test_select_docs_narrowed_by_docs(cm, env):
    make_run(env, "r1", two_docs())
    docs, _ = cm.select_docs(loaded(cm, env, [("a", "r1")]), env / "gold", [X02])
    assert docs == [X02]


def test_select_docs_rejects_eval(cm, env):
    make_run(env, "r1", {X01: make_doc(X01), X09: make_doc(X09)})
    with pytest.raises(ValueError, match=X09):
        cm.select_docs(loaded(cm, env, [("a", "r1")]), env / "gold")


def test_select_docs_rejects_eval_in_docs_option(cm, env):
    make_run(env, "r1", two_docs())
    with pytest.raises(ValueError, match=X09):
        cm.select_docs(loaded(cm, env, [("a", "r1")]), env / "gold", [X01, X09])


# ── main ───────────────────────────────────────────────

def test_main_writes_files(cm, env):
    make_run(env, "r1", two_docs())
    make_run(env, "r2", two_docs(toxicity=True))
    out = cm.main(["--title", "시험", "--runs", "첫째=r1", "둘째=r2", "--gold-dir", str(env / "gold")])
    folder = env / "runs" / f"{cm.today()}_models_시험"
    assert out == folder / "compare.md"
    md = out.read_text(encoding="utf-8")
    for needle in ("시험", "첫째", "둘째", str(env / "gold"),
                   "정답 자리 파일이 실버라면 점수는 순위 비교용이다. 합격 판정에 쓰지 않는다.",
                   "그림문자는 이미지 모델 전이라 모든 실행이 0점이다."):
        assert needle in md
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert [r["label"] for r in result["runs"]] == ["첫째", "둘째"]
    assert result["docs"] == [X01, X02]


def test_main_stops_without_run(cm, env):
    with pytest.raises(SystemExit):
        cm.main(["--title", "시험", "--runs", "없는실행", "--gold-dir", str(env / "gold")])


def test_main_stops_without_docs(cm, env):
    make_run(env, "r1", {X01: make_doc(X01)})
    with pytest.raises(SystemExit):
        cm.main(["--title", "시험", "--runs", "r1", "--docs", X02, "--gold-dir", str(env / "gold")])
