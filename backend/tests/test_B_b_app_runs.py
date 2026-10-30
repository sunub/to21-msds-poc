"""scripts/b_app_runs.py 시험 (작업 화면의 runs/ 읽기, ADR-025).

결과·정답 문서는 test_B_expand의 가짜 MSDS를 펼친 것이고, 실행 폴더·정답 폴더·manifest·캐시는 모두 tmp_path에 만든다 (D-43).
저장소의 runs/, data/는 읽거나 쓰지 않는다. 모델 서버를 부르지 않는다.
"""
import copy
import importlib
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from msds.common import manifest
from msds.evaluate.score import score_set
from test_B_compare_models import ROWS, SCRIPTS, X01, X02, X09, make_doc, write_json

KST = timezone(timedelta(hours=9))
ACUTE = "11항 급성독성(경구·경피·흡입)"


def iso(hours_ago: float) -> str:
    return (datetime.now(KST) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def make_run(runs, name, docs, *, info=None, timing=(), checks=None, raw=None):
    """가짜 실행 폴더. raw는 {파일 이름: 내용}."""
    run = runs / name
    run.mkdir(parents=True)
    base = {"model_tag": "m1", "model": "가상/모델-1", "prompt_version": "p1", "pages_dir": "data/pages/version9",
            "concurrency": 16, "prompt_hashes": {1: "aaa111", 2: "bbb222"}, "started_at": iso(24),
            "git_commit": "abc1234"}
    (run / "run_info.yaml").write_text(yaml.safe_dump({**base, **(info or {})}, allow_unicode=True),
                                       encoding="utf-8")
    for d, doc in docs.items():
        write_json(run / "outputs" / f"{d}.json", doc)
    for d, c in (checks or {}).items():
        write_json(run / "checks" / f"{d}.json", c)
    for fname, r in (raw or {}).items():
        write_json(run / "raw" / fname, r)
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
    for d in (X01, X02, X09):
        write_json(tmp_path / "gold" / f"{d}.json", make_doc(d))
    (tmp_path / "runs").mkdir()
    return tmp_path


@pytest.fixture
def br(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_runs")


def summarize(br, env, name, **kw):
    return br.summarize_run(env / "runs" / name, env / "gold", cache_dir=kw.pop("cache_dir", None), **kw)


def gold(env, d):
    return json.loads((env / "gold" / f"{d}.json").read_text(encoding="utf-8"))


def no_value_tox(status="자료없음") -> dict:
    """값 없는 급성독성 행 (실제 모양: 행 status만 있고 q가 비어 있다)."""
    return {"comp_ref": "MIX", "endpoint": "TX_ORAL", "descriptor": None, "q": None, "species": None, "sex": None,
            "duration_value": None, "duration_unit": None, "physical_form": None, "exposure_type": None,
            "converted": None, "read_across_cas": None, "guideline": None, "data_source": None,
            "classification": None, "statements": [], "status": status}


def req(finish="length", chars=1000, ws=100, head="", tail="정상적인 끝맺음 글"):
    return {"mode": "json_schema", "finish_reason": finish, "usage": {"completion_tokens": 10}, "seconds": 1.0,
            "chars": chars, "whitespace": ws, "head": head, "tail": tail}


# ── 채점 ──────────────────────────────────────────────

def test_summary_matches_score_set(br, env):
    pred = {X01: make_doc(X01, toxicity=True), X02: make_doc(X02)}
    make_run(env / "runs", "r1", pred, timing=[(X01, 120.5), (X02, 80)])
    s = summarize(br, env, "r1")
    expect = score_set([(d, gold(env, d), pred[d]) for d in (X01, X02)])
    assert s["docs"] == [X01, X02]
    assert s["weighted"] == pytest.approx(expect["weighted"]) and s["weighted"] < 100
    assert s["items"] == expect["items"]
    assert (s["must_passed"], s["must_total"], s["passed"]) == (
        expect["must_passed_count"], expect["must_total"], expect["passed"])
    assert s["details"] == expect["details"]
    assert s["per_doc"][X01]["weighted"] == pytest.approx(expect["docs"][X01]["weighted"])
    assert s["per_doc"][X01]["failed_must"] == expect["docs"][X01]["failed_must"]
    assert s["per_doc"][X01]["seconds"] == 120.5
    assert len(s["per_doc"][X02]["items"]) == 23
    assert s["rows"]["toxicity"] == {"pred": 1, "gold": 2}
    assert s["rows"]["extras"] == {"pred": 2, "gold": 2}


def test_summary_carries_run_info(br, env):
    make_run(env / "runs", "r1", {X01: make_doc(X01)})
    s = summarize(br, env, "r1")
    assert (s["name"], s["kind"], s["model_tag"], s["model"]) == ("r1", "run", "m1", "가상/모델-1")
    assert (s["prompt_version"], s["pages_dir"], s["concurrency"], s["git_commit"]) == (
        "p1", "data/pages/version9", 16, "abc1234")
    assert s["prompt_hashes"] == {"1": "aaa111", "2": "bbb222"}       # 캐시(JSON)와 같은 모양
    assert isinstance(s["started_at"], str)


def test_na_excluded_drops_no_value_rows(br, env):
    doc = make_doc(X01)
    doc["msds"][0]["toxicity"].append(no_value_tox())                  # 정답에는 없는 값 없는 행
    make_run(env / "runs", "r1", {X01: doc})
    s = summarize(br, env, "r1")
    plain = {i["name"]: i["score"] for i in s["items"]}
    na = {i["name"]: i["score"] for i in s["items_na_excluded"]}
    assert na[ACUTE] >= plain[ACUTE]
    assert plain[ACUTE] < 1.0 and na[ACUTE] == pytest.approx(1.0)
    assert s["weighted_na_excluded"] >= s["weighted"]
    assert [i["name"] for i in s["items_na_excluded"]] == [i["name"] for i in s["items"]]


def test_strip_no_value_rows(br):
    doc = make_doc(X01)
    m = doc["msds"][0]
    m["toxicity"].append(no_value_tox(" 해당없음 "))
    m["cmr"].append({"comp_ref": "MIX", "hazard": "생식독성", "agency": None, "class": None, "status": "자료없음",
                     "note": None})
    m["physchem"].append({"prop_code": "ODOR", "comp_ref": "MIX", "q": None, "text_value": "자료없음", "cond": None,
                          "seq": 2, "data_source": None})
    m["exposure_limits"].append({**m["exposure_limits"][0], "q": {"raw": "미기재", "status": "미기재", "value": None}})
    m["regulations"].append({**m["regulations"][0], "seq": 2, "applicable": "비해당"})
    m["extras"].append({**m["extras"][0], "seq": 2, "q": {"raw": "자료없음", "value": None}})
    kept_value = {**m["physchem"][0], "seq": 3, "text_value": "자료없음"}   # 상태 글이 있어도 숫자 값이 있으면 남긴다
    m["physchem"].append(kept_value)
    before = copy.deepcopy(doc)

    out = br.strip_no_value_rows(doc)
    assert doc == before                                               # 원본은 그대로
    o, g = out["msds"][0], make_doc(X01)["msds"][0]
    for table in ("toxicity", "cmr", "exposure_limits", "regulations", "extras", "components"):
        assert o[table] == g[table], table                            # 값 없는 행만 빠지고 값 있는 행은 남는다
    assert o["physchem"] == g["physchem"] + [kept_value]


# ── 한도 걸림 분류 ─────────────────────────────────────

def test_limit_kind(br):
    assert br.limit_kind(req(finish="stop", ws=900)) is None
    assert br.limit_kind(req(ws=900)) == "공백폭주"
    assert br.limit_kind(req(tail="앞" + " " * 250)) == "공백폭주"            # 끝 공백 200자 넘음
    assert br.limit_kind(req(tail="머리" + "가상물질 갑의 경구 독성 값을 다시 적는다 반복되는 글 " * 5)) == "반복"
    assert br.limit_kind(req()) == "긴출력"


# ── 호출 격자 ──────────────────────────────────────────

def test_grid(br, env):
    checks = {X01: {"sections": [
        {"msds_index": 0, "section": 1, "ok": True, "mode": "json_schema", "reextracted": False, "attempts": 1,
         "seconds": 3.5},
        {"msds_index": 0, "section": 2, "ok": True, "mode": "json_object", "reextracted": True, "attempts": 2,
         "seconds": 70.0},
        {"msds_index": 0, "section": 11, "ok": False, "mode": "rows", "reextracted": False, "attempts": 1,
         "seconds": 9.0}]}}
    raw = {f"{X01}_m0_s01.json": {"requests": [req(finish="stop")]},
           f"{X01}_m0_s02.json": {"requests": [req(finish="stop")],
                                  "first_attempt": {"requests": [req(ws=950)]}},    # 첫 시도가 한도에 걸림
           f"{X01}_m0_s11.json": {"requests": [req()]}}
    make_run(env / "runs", "r1", {X01: make_doc(X01)}, checks=checks, raw=raw)
    g = summarize(br, env, "r1")["grid"][X01]
    assert set(g) == {"1", "2", "11"}
    assert g["1"] == {"ok": True, "mode": "json_schema", "reextracted": False, "attempts": 1, "seconds": 3.5,
                      "limit_kind": None}
    assert (g["2"]["ok"], g["2"]["reextracted"], g["2"]["limit_kind"]) == (True, True, "공백폭주")
    assert (g["11"]["ok"], g["11"]["limit_kind"]) == (False, "긴출력")


# ── 진행률 ─────────────────────────────────────────────

def test_progress(br, env):
    docs = {X01: make_doc(X01), X02: make_doc(X02)}
    make_run(env / "runs", "now", docs, timing=[(X01, 100)], info={"started_at": iso(1)})
    make_run(env / "runs", "old", docs, timing=[(X01, 100)], info={"started_at": iso(7)})
    make_run(env / "runs", "done", docs, timing=[(X01, 100), (X02, 90)], info={"started_at": iso(1)})
    assert summarize(br, env, "now")["progress"] == {"done": 1, "total": 2, "running": True}
    assert summarize(br, env, "old")["progress"] == {"done": 1, "total": 2, "running": False}
    assert summarize(br, env, "done")["progress"] == {"done": 2, "total": 2, "running": False}


# ── 평가용 문서 (D-43) ─────────────────────────────────

def test_eval_docs_are_excluded(br, env):
    checks = {X09: {"sections": [{"msds_index": 0, "section": 1, "ok": True}]}}
    make_run(env / "runs", "r1", {X01: make_doc(X01), X09: make_doc(X09)}, checks=checks,
             timing=[(X01, 10), (X09, 10)])
    s = summarize(br, env, "r1")
    assert s["docs"] == [X01] and s["excluded"] == [X09]
    assert X09 not in s["per_doc"] and X09 not in s["grid"]
    assert all(d["doc_id"] != X09 for d in s["details"])
    assert s["progress"]["total"] == 1
    assert X09 not in json.dumps(s, ensure_ascii=False).replace(json.dumps(s["excluded"]), "")


def test_doc_without_gold_is_not_scored(br, env):
    (env / "gold" / f"{X02}.json").unlink()
    make_run(env / "runs", "r1", {X01: make_doc(X01), X02: make_doc(X02)})
    s = summarize(br, env, "r1")
    assert s["docs"] == [X01] and s["no_gold"] == [X02]


def test_run_without_outputs(br, env):
    make_run(env / "runs", "r1", {}, info={"started_at": iso(0.1)})
    s = summarize(br, env, "r1")
    assert s["docs"] == [] and s["weighted"] is None and s["items"] == []
    assert s["progress"] == {"done": 0, "total": 0, "running": False}


# ── 캐시 ───────────────────────────────────────────────

def test_cache(br, env, monkeypatch):
    run = make_run(env / "runs", "r1", {X01: make_doc(X01)})
    calls = []
    real = br.score_set
    monkeypatch.setattr(br, "score_set", lambda pairs: calls.append(1) or real(pairs))
    cache = env / "cache"

    first = summarize(br, env, "r1", cache_dir=cache)
    n = len(calls)
    assert n > 0
    path = cache / "r1.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["result"] == first

    second = summarize(br, env, "r1", cache_dir=cache)
    assert len(calls) == n and second == first                    # 두 번째는 캐시를 읽는다

    out = run / "outputs" / f"{X01}.json"
    write_json(out, make_doc(X01, toxicity=True))
    t = out.stat().st_mtime + 10
    os.utime(out, (t, t))
    third = summarize(br, env, "r1", cache_dir=cache)
    assert len(calls) > n and third["weighted"] < first["weighted"]  # 결과가 바뀌면 다시 계산한다


def test_default_cache_dir_is_outside_repo(br):
    from msds.common import paths
    assert not br.CACHE_DIR.resolve().is_relative_to(paths.ROOT.resolve())


# ── 목록 ───────────────────────────────────────────────

def test_list_runs_and_load_all(br, env):
    runs = env / "runs"
    make_run(runs, "20261029_sections_b", {X01: make_doc(X01)}, info={"started_at": "2026-10-29T09:00:00+09:00"})
    make_run(runs, "20261028_sections_a", {X01: make_doc(X01)}, info={"started_at": "2026-10-28T09:00:00+09:00"})
    make_run(runs / "manual", "20261030_1200_T21-X01_s11", {X01: make_doc(X01)},
             info={"started_at": "2026-10-30T12:00:00+09:00"})
    (runs / "20261029_models_비교").mkdir()
    (runs / "20261029_models_비교" / "compare.md").write_text("# 비교\n", encoding="utf-8")
    (runs / "빈폴더").mkdir()
    (runs / "manual" / "server_log.md").write_text("기록\n", encoding="utf-8")

    listed = br.list_runs(runs)
    assert sorted(p.name for p in listed) == sorted(
        ["20261029_sections_b", "20261028_sections_a", "20261030_1200_T21-X01_s11", "20261029_models_비교"])

    res = br.load_all(runs, env / "gold", cache_dir=None)
    assert res["gold_dir"] == str(env / "gold")
    assert len(res["criteria"]["items"]) == 23
    names = [r["name"] for r in res["runs"]]
    assert names == ["20261028_sections_a", "20261029_models_비교", "20261029_sections_b",
                     "manual/20261030_1200_T21-X01_s11"]
    kinds = {r["name"]: r["kind"] for r in res["runs"]}
    assert kinds["manual/20261030_1200_T21-X01_s11"] == "manual"
    assert kinds["20261029_models_비교"] == "models" and kinds["20261028_sections_a"] == "run"
    models = next(r for r in res["runs"] if r["kind"] == "models")
    assert "weighted" not in models                                  # 비교표 폴더는 채점하지 않는다


def test_load_all_keeps_going_when_a_run_is_broken(br, env):
    make_run(env / "runs", "ok", {X01: make_doc(X01)})
    bad = make_run(env / "runs", "bad", {X01: make_doc(X01)})
    (bad / "outputs" / f"{X01}.json").write_text("{깨진", encoding="utf-8")   # 쓰는 중인 파일
    res = br.load_all(env / "runs", env / "gold", cache_dir=None)
    by = {r["name"]: r for r in res["runs"]}
    assert by["ok"]["weighted"] == pytest.approx(100)
    assert "error" in by["bad"]


# ── 합격 기준 ──────────────────────────────────────────

def test_criteria(br):
    c = br.criteria()
    assert c["pass_score"] == 90.0 and c["weights"] == {"필수": 3, "중요": 2, "일반": 1}
    assert "90" in c["rule"] and "17" in c["rule"]
    assert len(c["items"]) == 23
    assert sum(i["level"] == "필수" for i in c["items"]) == 17
    for i in c["items"]:
        assert set(i) == {"name", "level", "metric", "target", "help"}
        assert i["help"].strip(), i["name"]
    helps = {i["name"]: i["help"] for i in c["items"]}
    assert helps["15항 국내 규제(성분·항목·해당여부)"] != helps["15항 국내 규제 기준농도"]   # 가장 긴 앞부분으로 찾는다
    assert helps["구성성분(CAS 기준 매칭)"] != helps["구성성분 필드(성분명·KE)"]
