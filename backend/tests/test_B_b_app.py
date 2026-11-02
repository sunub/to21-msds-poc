"""scripts/b_app.py 시험 (작업 화면 서버와 탭 ① 점수판, ADR-025).

route()를 직접 부른다. 서버 소켓을 열지 않고 네트워크를 부르지 않는다.
실행 폴더·정답 폴더·manifest는 test_B_b_app_runs의 가짜 픽스처(tmp_path)를 쓴다. 저장소의 runs/, data/는 읽지 않는다 (D-43).
"""
import importlib
import io
import json
import re
from types import SimpleNamespace

import pytest

from test_B_b_app_runs import env, make_run  # noqa: F401  env는 픽스처
from test_B_b_app_sets import answer_keys, page  # noqa: F401  가짜 data/silver·gold 픽스처
from test_B_b_app_doc import write_lines
from test_B_compare_models import SCRIPTS, X01, X02, make_doc
from test_B_expand import LINES

STATIC_FILES = ("index.html", "app.css", *["js/" + p.name for p in sorted((SCRIPTS / "b_app_static/js").glob("*.js"))])
TABS = ("점수판", "두 실행 비교", "원문 대조", "작업", "서버")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app")


@pytest.fixture
def ctx(app, env):
    return app.AppContext(runs_dir=env / "runs", gold_dir=env / "gold", pages_dir=env / "pages",
                          static_dir=app.STATIC, cache_dir=None, gaps_file=env / "silver_gaps.yaml")


def get(app, ctx, path):
    return app.route("GET", path, {}, None, ctx)


def get_json(app, ctx, path):
    code, ctype, body = get(app, ctx, path)
    assert ctype.startswith("application/json")
    return code, json.loads(body)


def three_runs(env):
    runs = env / "runs"
    make_run(runs, "20261029_sections_m1_dev10_r1", {X01: make_doc(X01), X02: make_doc(X02)},
             info={"started_at": "2026-10-29T09:00:00+09:00"}, timing=[(X01, 100), (X02, 90)])
    make_run(runs, "20261030_sections_m1_probe", {X01: make_doc(X01, toxicity=True)},
             info={"started_at": "2026-10-30T09:00:00+09:00"})
    make_run(runs / "manual", "20261030_1200_T21-X01_s11", {X01: make_doc(X01)},
             info={"started_at": "2026-10-30T12:00:00+09:00"})


# ── 화면 파일 ──────────────────────────────────────────

def test_index(app, ctx):
    code, ctype, body = get(app, ctx, "/")
    text = body.decode("utf-8")
    assert code == 200 and ctype.startswith("text/html")
    assert "<title>" in text
    for element in ["app-header", "main-nav", "global-context", "ui-text"]:
        assert f'id="{element}"' in text
    for no in [1, 2, 3, 4, 5, 6, 7, 10]:
        assert f'<section id="screen-s{no:02}" hidden' in text
    assert 'id="screen-s09"' not in text  # 여러 문서 시험은 S03 첫 단계의 갈래가 됐다 (ADR-039).


def test_static(app, ctx):
    code, ctype, body = get(app, ctx, "/static/js/core.js")
    assert code == 200 and "javascript" in ctype and b"function api" in body
    code, ctype, _ = get(app, ctx, "/static/app.css")
    assert code == 200 and ctype.startswith("text/css")


@pytest.mark.parametrize("path", ["/", "/static/index.html"])
def test_static_initial_ui_text_survives_api_failure_and_escapes_html(app, ctx, monkeypatch, path):
    copy = {"load_error": {"message": "자료를 불러오지 못했습니다.", "fix": "다시 여세요."},
            "probe": "</script><script>가짜 글</script>"}
    monkeypatch.setattr(app.bt, "POLISH_TEXT", copy, raising=False)
    page = get(app, ctx, path)[2].decode()
    payload = re.search(r'<script id="ui-text" type="application/json">(.*?)</script>', page, re.S)
    assert payload is not None
    assert json.loads(payload.group(1)) == copy
    assert "</script><script>가짜 글" not in page


def test_static_rejects_parent_paths(app, ctx):
    assert get(app, ctx, "/static/../b_app.py")[0] == 400
    assert get(app, ctx, "/static/%2e%2e/b_app.py")[0] == 400
    assert get(app, ctx, "/static/없는파일.js")[0] == 404


@pytest.mark.parametrize("name", STATIC_FILES)
def test_static_files_call_no_outside_address(app, name):
    text = (app.STATIC / name).read_text(encoding="utf-8")
    assert not re.search(r"https?://", text), name


# ── API ────────────────────────────────────────────────

def test_api_start_without_runs_or_model_server(app, ctx, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("시작 안내는 실행 파일이나 서버를 읽지 않습니다")
    monkeypatch.setattr(app.br, "load_all", forbidden)
    code, data = get_json(app, ctx, "/api/start")
    assert code == 200
    assert data == app.bt.START_TEXT


def test_static_start_entry_and_replay(app, ctx):
    text = get(app, ctx, "/")[2].decode()
    assert 'id="screen-s08"' not in text
    assert 'id="journey-band"' not in text
    assert 'id="guide-overlay"' in text and 'id="help-guide-records"' in text


def test_api_runs(app, ctx, env):
    three_runs(env)
    code, data = get_json(app, ctx, "/api/runs")
    assert code == 200
    assert len(data["runs"]) == 3
    for r in data["runs"]:
        assert {"weighted", "must_passed", "model_tag"} <= set(r), r["name"]
        assert not {"details", "per_doc", "grid"} & set(r), r["name"]      # 가벼운 목록
    assert len(data["criteria"]["items"]) == 23
    assert data["doc_time_limit"] == 300


def test_api_runs_current_is_latest_dev10(app, ctx, env):
    three_runs(env)
    assert get_json(app, ctx, "/api/runs")[1]["current"] == "20261029_sections_m1_dev10_r1"


def test_run_labels_are_added_without_changing_score_or_cache(app, ctx, env, monkeypatch):
    name = "20261030_sections_qwen36_35b_runpod_s7_v9_cls_dev10_r2"
    run = make_run(env / "runs", name, {X01: make_doc(X01)},
                   info={"model_tag": "qwen36_35b_runpod", "prompt_version": "s7"})
    summary = app.br.summarize_run(run, ctx.gold_dir, cache_dir=None)
    before = json.loads(json.dumps(summary))
    monkeypatch.setattr(app.br, "summarize_run", lambda *a, **kw: summary)
    listing = get_json(app, ctx, "/api/runs")[1]["runs"][0]
    detail = get_json(app, ctx, "/api/run/" + name)[1]
    for result in (listing, detail):
        assert result["label"] == {
            "title": "10/30 Qwen3.6 35B · 빌린 서버 · AI에게 시킨 일 7번째 판 · 원문 자료 9판 · 분류 검사 · 개발 10건 · 2회차",
            "subtitle": name,
            "parts": ["10/30 Qwen3.6 35B", "빌린 서버", "AI에게 시킨 일 7번째 판", "원문 자료 9판", "분류 검사", "개발 10건", "2회차"],
        }
        assert result["model_label"] == "Qwen3.6 35B · 빌린 서버"
    # Steps 4/9 add presentation fields; every original scoring field remains identical.
    assert {k: v for k, v in detail.items()
            if k not in ("label", "model_label", "status_text", "card_summaries", "connection_notes", "key",
                         "run_kind_label", "targets", "set", "problem_rows")} == before
    assert summary == before


def test_run_connection_notes_are_additive_and_need_no_server(app, ctx, env):
    make_run(env / "runs", "fake-run", {X01: make_doc(X01)}, info={"model": "가짜 모델"})
    ctx.model_status = lambda: pytest.fail("점수 조회는 연결을 새로 검사하지 않는다")
    code, result = get_json(app, ctx, "/api/run/fake-run")
    assert code == 200
    assert result["connection_notes"] == app.bt.connection_notes(result["model"])


def test_doc_tooltips_preserve_raw_values_and_translate_all_sides(app, ctx, env, monkeypatch):
    make_run(env / "runs", "fake-run", {X01: make_doc(X01)})
    value = {"seq": 1, "value": "직접 만든 값", "cond": None, "unknown": 0}
    view = {"values": [{"path": "fake", "value": value, "silver": {"value": value, "same": True}}],
            "silver_only": [{"path": "fake", "value": value}]}
    before = json.loads(json.dumps(view))
    monkeypatch.setattr(app.bdoc, "doc_view", lambda *a: view)
    code, _, body = app.route("GET", "/api/doc", {"run": ["fake-run"], "doc": [X01]}, None, ctx)
    result = json.loads(body)
    assert code == 200
    assert result["ui_text"]["value_field_labels"] == app.bt.VALUE_FIELD_LABELS
    for cell in (result["values"][0], result["values"][0]["silver"], result["silver_only"][0]):
        assert cell["value"] == value
    for side in ("result", "silver", "silver_only"):
        assert result["ui_text"]["value_tips"][side]["fake"] == ["순서: 1", "값: 직접 만든 값", "unknown: 0"]
    assert view == before


def test_doc_silver_lines_with_and_without_gold(app, ctx, env):
    """실버 값의 추정 줄 수(silver_lines)는 글이 같은 줄 찾기(text_match)로 낸다. 실버가 없는 문서는 None."""
    for d in (X01, X02):
        write_lines(env / "pages", d, LINES)
    make_run(env / "runs", "fake-run", {X01: make_doc(X01, toxicity=True), X02: make_doc(X02)})
    code, data = get_q(app, ctx, "/api/doc", run="fake-run", doc=X01)
    assert code == 200 and data["has_gold"] is True
    sl = data["silver_lines"]
    assert sl["basis"] == "text_match" and 0 < sl["found"] < sl["total"]
    assert [g["lines"] for g in data["silver_only"] if g["table"] == "toxicity"][0] == ["p5:L8"]
    (env / "gold" / f"{X02}.json").unlink()
    code, data = get_q(app, ctx, "/api/doc", run="fake-run", doc=X02)
    assert code == 200 and data["has_gold"] is False and data["silver_lines"] is None


def test_all_run_kinds_get_labels(app, ctx, env):
    three_runs(env)
    folder = env / "runs" / "20261030_models_custom"
    folder.mkdir()
    (folder / "compare.md").write_text("비교", encoding="utf-8")
    for r in get_json(app, ctx, "/api/runs")[1]["runs"]:
        assert r["label"]["subtitle"] == r["name"]
        assert "model_label" in r
        assert get_json(app, ctx, "/api/run/" + r["name"])[1]["label"] == r["label"]
        if r["kind"] == "manual":
            assert r["label"]["title"].startswith("앱에서 시작 · 10/30")


def test_options_model_labels_keep_tags_and_connection_state(app, ctx):
    ctx.model_status = lambda: [{"tag": "qwen36_35b_runpod", "reachable": True, "match": True}]
    ctx.pages_root = ctx.pages_dir
    code, data = get_json(app, ctx, "/api/options")
    assert code == 200
    models = {m["tag"]: m for m in data["models"]}
    assert models["qwen36_35b_runpod"]["label"] == "Qwen3.6 35B · 빌린 서버"
    assert models["qwen36_35b_runpod"]["connected"] is True
    assert models["gpt_oss_20b_rngd"]["label"] == "gpt-oss 20B · 회사 서버"
    assert models["gpt_oss_20b_rngd"]["connected"] is False
    assert all(m["label"] and m["model"] for m in models.values())


def test_current_falls_back_to_latest_scored_run(app):
    runs = [{"name": "a_probe", "kind": "run", "weighted": 50.0},
            {"name": "b_dev10", "kind": "run", "weighted": None},          # 아직 결과가 없는 dev10
            {"name": "manual/c", "kind": "manual", "weighted": 70.0},
            {"name": "d_models", "kind": "models"}]
    assert app.pick_current(runs) == "manual/c"
    assert app.pick_current(runs[:1] + [{"name": "x_dev10", "kind": "run", "weighted": 40.0}]) == "x_dev10"
    assert app.pick_current([]) is None


def test_current_skips_silver_and_prefers_comparable(app):
    dev = {"name": "20261029_m_s6_v9_r1", "kind": "run", "weighted": 72.7, "run_kind": "dev10", "comparable": True}
    probe = {"name": "20261030_m_s7_v9_dev10_probe", "kind": "run", "weighted": 80.0, "run_kind": "probe",
             "comparable": False}
    silver = {"name": "20261031_silver_claude_p3_dev10", "kind": "run", "weighted": 93.4, "run_kind": "silver",
              "comparable": False}
    assert app.pick_current([dev, probe, silver]) == dev["name"]          # 가장 최근·최고 점수인 실버를 고르지 않는다
    assert app.pick_current([probe, silver]) == probe["name"]             # comparable이 없으면 옛 규칙(이름에 dev10)
    assert app.pick_current([silver]) == silver["name"]                   # 실행이 있으면 None을 돌려주지 않는다
    unscored = {"name": "20261031_m_running", "kind": "run", "weighted": None, "run_kind": "probe", "comparable": False}
    assert app.pick_current([silver, unscored]) == unscored["name"]


def silver_and_dev(env):
    runs = env / "runs"
    make_run(runs, "20261029_sections_m1_v9_r1", {X01: make_doc(X01, toxicity=True), X02: make_doc(X02)},
             info={"started_at": "2026-10-29T09:00:00+09:00"})
    make_run(runs, "20261031_silver_claude_p3_dev", {X01: make_doc(X01), X02: make_doc(X02)},
             info={"mode": "silver", "model_tag": "claude", "started_at": "2026-10-31T09:00:00+09:00"})
    return "20261029_sections_m1_v9_r1", "20261031_silver_claude_p3_dev"


def test_api_runs_skips_silver_and_adds_kind_labels_and_targets(app, ctx, env):
    dev, silver = silver_and_dev(env)
    code, data = get_json(app, ctx, "/api/runs")
    assert code == 200 and data["current"] == dev
    by = {r["name"]: r for r in data["runs"]}
    assert by[silver]["weighted"] > by[dev]["weighted"]
    assert (by[dev]["run_kind"], by[dev]["comparable"], by[dev]["run_kind_label"]) == ("dev10", True, "개발용 10건 시험")
    assert (by[silver]["run_kind"], by[silver]["run_kind_label"]) == ("silver", "AI 정답 초안 만들기")
    for r in data["runs"]:
        assert r["targets"] == app.bt.score_targets(r, data["criteria"])
    assert by[dev]["targets"]["weighted"]["line"] == 90 and by[dev]["targets"]["must"]["total"] == 17


def test_api_run_and_diff_targets(app, ctx, env):
    dev, silver = silver_and_dev(env)
    code, detail = get_json(app, ctx, "/api/run/" + dev)
    assert code == 200
    assert detail["targets"] == detail["status_text"]["targets"] == app.bt.score_targets(detail, app.br.criteria())
    assert detail["card_summaries"]["history"].startswith("저장된 결과 1개 중 최고점은")   # 실버 실행은 역사에서 뺀다
    assert "합격" not in detail["status_text"]["headline"]
    code, _, body = app.route("GET", "/api/diff", {"a": [dev], "b": [silver]}, None, ctx)
    diff = json.loads(body)
    assert code == 200
    assert diff["targets"]["a"] == detail["targets"]
    assert diff["targets"]["b"]["weighted"]["met"] is True and diff["targets"]["b"]["must"]["met_count"] == 17


def test_api_run(app, ctx, env):
    three_runs(env)
    code, data = get_json(app, ctx, "/api/run/20261029_sections_m1_dev10_r1")
    assert code == 200
    assert {"details", "grid", "items_na_excluded", "per_doc"} <= set(data)
    assert data["docs"] == [X01, X02]
    code, data = get_json(app, ctx, "/api/run/manual/20261030_1200_T21-X01_s11")
    assert code == 200 and data["kind"] == "manual"


def test_api_run_status_has_loss_ranking(app, ctx, env):
    name = "20261029_sections_m1_dev10_loss"
    make_run(env / "runs", name, {X01: make_doc(X01, toxicity=True), X02: make_doc(X02)})   # X01만 11항 독성을 비운다
    code, data = get_json(app, ctx, "/api/run/" + name)
    status = data["status_text"]
    assert code == 200 and data["weighted"] < 100
    assert len(status["losses"]) == len(data["items"]) == 23
    assert [r["rank"] for r in status["losses"]] == list(range(1, 24))
    assert sum(r["loss"] for r in status["losses"]) == pytest.approx(100 - data["weighted"])
    assert status["loss_basis"] == {"weight_total": sum(app.br.WEIGHTS[i["level"]] for i in data["items"]),
                                    "loss_total": pytest.approx(100 - data["weighted"])}
    top = status["top_problem"]
    assert top["name"] == status["losses"][0]["name"] and top["loss"] > 0
    assert top["name"].startswith("11항") and top["section"] == 11
    assert [d["doc_id"] for d in top["docs"]] == [X01, X02]                 # 손실은 X01에서만 난다
    assert top["docs"][1]["loss"] == 0
    assert sum(d["loss"] for d in top["docs"]) == pytest.approx(top["loss"])
    assert "top_drops" in status


def test_api_run_status_counts_are_field_level_like_source_view(app, ctx, env):
    """S01 문제 건수는 S02(원문 대조)와 같은 칸 단위로 센다 (사용자 결정 10/31)."""
    from collections import Counter
    name = "20261029_sections_m1_dev10_loss"
    make_run(env / "runs", name, {X01: make_doc(X01, toxicity=True), X02: make_doc(X02)})   # X01만 11항 독성을 비운다
    code, data = get_json(app, ctx, "/api/run/" + name)
    top = data["status_text"]["top_problem"]
    field = app.bdoc.run_field_counts(env / "runs" / name, ctx.gold_dir, data["docs"])
    missing = sum(n for (item, section, kind), n in sum(field.values(), Counter()).items()
                  if (item, section, kind) == (top["name"], top["section"], "missing"))
    assert code == 200 and top["counts_basis"] == "field"
    assert top["counts"]["빠뜨림"] == missing > 0
    assert [d["doc_id"] for d in top["docs"]] == [X01, X02]
    assert top["docs"][0]["counts"]["빠뜨림"] == missing
    assert top["docs"][1]["counts"] == {"빠뜨림": 0, "틀림": 0, "지어냄": 0}


def test_api_run_has_problem_rows_per_criterion_and_doc(app, ctx, env):
    """① 문제 고르기의 문제 행 수(STEPS.md A5). 문서 번호와 수만 싣고 status_text는 바꾸지 않는다."""
    name = "20261029_sections_m1_dev10_loss"
    make_run(env / "runs", name, {X01: make_doc(X01, toxicity=True), X02: make_doc(X02)})   # X01만 11항 독성을 비운다
    code, data = get_json(app, ctx, "/api/run/" + name)
    top = data["status_text"]["top_problem"]
    _, rows = app.bdoc.run_problem_counts(env / "runs" / name, ctx.gold_dir, data["docs"])
    got = data["problem_rows"][top["name"]]
    assert code == 200 and got["row_count"] == rows[X01][(top["name"], top["section"])] > 0
    assert {d["doc_id"]: d["row_count"] for d in got["docs"]} == {X01: got["row_count"], X02: 0}
    assert list(data["problem_rows"]) == [r["name"] for r in data["status_text"]["losses"]]
    assert all("row_count" not in r and "docs" not in r for r in data["status_text"]["losses"])   # 옛 응답 그대로
    assert [set(d) for d in top["docs"]] == [{"doc_id", "score", "loss", "counts"}] * 2


def test_api_run_unknown(app, ctx, env):
    three_runs(env)
    for path in ("/api/run/없는실행", "/api/run/../gold", "/api/run/"):
        code, data = get_json(app, ctx, path)
        assert code == 404 and data["error"], path


def test_run_status_and_summaries_do_not_change_cached_scores(app, ctx, env, monkeypatch):
    three_runs(env)
    name = "20261029_sections_m1_dev10_r1"
    summary = app.br.summarize_run(env / "runs" / name, ctx.gold_dir, cache_dir=None)
    before = json.loads(json.dumps(summary))
    original = app.br.summarize_run
    monkeypatch.setattr(app.br, "summarize_run", lambda run, *a, **kw:
                        summary if run.name == name else original(run, *a, **kw))
    ctx.model_status = lambda: pytest.fail("점수 요청은 모델 서버를 부르면 안 됩니다")
    code, result = get_json(app, ctx, "/api/run/" + name)
    assert code == 200
    # 문제 건수는 칸 단위로 센다(사용자 결정 10/31). 같은 수를 넘겨 다시 만들어도 같아야 한다
    field = app.bdoc.run_field_counts(env / "runs" / name, ctx.gold_dir, before.get("docs") or [])
    assert result["status_text"] == app.bt.score_status(before, app.br.criteria(), connected=None,
                                                        per_doc=before.get("per_doc"), field_counts=field)
    assert set(result["card_summaries"]) == {"history", "docs", "grid", "rows"}
    assert result["card_summaries"]["history"].startswith("저장된 결과 2개 중 최고점은")
    for kind in ("docs", "grid", "rows"):
        assert result["card_summaries"][kind] == app.bt.card_summary(kind, before)
    assert all(result[k] == v for k, v in before.items())
    assert summary == before


@pytest.mark.parametrize("reachable, match, expected", [(True, True, True), (True, False, False), (False, False, False)])
def test_run_status_uses_cached_server_model_state(app, ctx, env, monkeypatch, reachable, match, expected):
    from types import SimpleNamespace
    three_runs(env)
    calls = []
    model = {"tag": "m1", "reachable": reachable, "match": match}
    def server_status():
        calls.append("status")
        return {"models": [model]}
    ctx.servers = SimpleNamespace(status=server_status)
    get_json(app, ctx, "/api/servers")
    seen = []
    real = app.bt.score_status
    def capture(info, criteria, *, connected=None, **kw):     # kw: 문서별 손실에 쓰는 per_doc
        seen.append(connected)
        return real(info, criteria, connected=connected, **kw)
    monkeypatch.setattr(app.bt, "score_status", capture)
    for _ in range(2):
        get_json(app, ctx, "/api/run/20261029_sections_m1_dev10_r1")
    assert seen == [expected, expected]
    assert calls == ["status"]
    model["tag"] = "another-model"
    get_json(app, ctx, "/api/servers")
    get_json(app, ctx, "/api/run/20261029_sections_m1_dev10_r1")
    assert seen[-1] is None


def test_runs_count_is_available_before_scoring(app, ctx, env, monkeypatch):
    three_runs(env)
    monkeypatch.setattr(app.br, "load_all", lambda *a, **kw: pytest.fail("목록 수만 확인할 때 채점하면 안 됩니다"))
    code, _, body = app.route("GET", "/api/runs", {"count": ["1"]}, None, ctx)
    assert code == 200 and json.loads(body) == {"count": 3}


def test_api_criteria(app, ctx):
    code, data = get_json(app, ctx, "/api/criteria")
    assert code == 200 and len(data["items"]) == 23 and data["pass_score"] == 90.0


def test_api_glossary_is_shared_text_without_runs_or_servers(app, ctx, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("용어를 읽을 때 실행 파일이나 서버를 조회하면 안 된다")

    monkeypatch.setattr(app.br, "load_all", forbidden)
    ctx.model_status = forbidden
    code, data = get_json(app, ctx, "/api/glossary")
    assert code == 200
    assert data == {"items": app.bt.glossary_entries()}
    assert len(data["items"]) >= 28


def test_unknown_path_is_404_json(app, ctx):
    code, data = get_json(app, ctx, "/api/없는주소")
    assert code == 404 and "error" in data


# ── 실버 빈 곳 ─────────────────────────────────────────

def test_silver_gaps_from_ctx_file(app, ctx, env):
    assert get_json(app, ctx, "/api/silver_gaps") == (200, [])                   # 파일이 없으면 빈 목록
    (env / "silver_gaps.yaml").write_text(
        '- item: "11항 급성독성"\n  note: "가짜 메모"\n  since: 2026-10-30\n  source: "가짜 출처"\n',
        encoding="utf-8")
    code, data = get_json(app, ctx, "/api/silver_gaps")
    assert code == 200
    assert data == [{"item": "11항 급성독성", "note": "가짜 메모", "since": "2026-10-30", "source": "가짜 출처"}]


def test_real_silver_gaps_name_real_items(app):
    import yaml
    gaps = yaml.safe_load(app.GAPS_FILE.read_text(encoding="utf-8"))
    names = [i["name"] for i in app.br.criteria()["items"]]
    assert len(gaps) >= 4
    for g in gaps:
        assert {"item", "note", "since", "source"} <= set(g)
        assert any(n.startswith(g["item"]) for n in names), g["item"]           # 채점 항목 이름 앞부분


# ── 정답지 ─────────────────────────────────────────────

KEYED_RUN = "20261030_sections_m1_dev10_r1"


@pytest.fixture
def kctx(app, env, answer_keys):
    """정답지 목록이 있는 ctx. 실행 하나가 X01(그대로)·X02(독성 표 비움)를 냈다."""
    make_run(env / "runs", KEYED_RUN, {X01: make_doc(X01), X02: make_doc(X02, toxicity=True)})
    return app.AppContext(runs_dir=env / "runs", gold_dir=answer_keys / "silver" / "claude", pages_dir=env / "pages",
                          static_dir=app.STATIC, cache_dir=env / "cache", gaps_file=env / "silver_gaps.yaml",
                          data_root=answer_keys)


def get_q(app, ctx, path, **query):
    code, ctype, body = app.route("GET", path, {k: [v] for k, v in query.items()}, None, ctx)
    assert ctype.startswith("application/json")
    return code, json.loads(body)


def test_api_keys(app, kctx):
    code, data = get_json(app, kctx, "/api/keys")
    assert code == 200
    assert data["default"] == "silver/claude"
    assert [k["id"] for k in data["keys"]] == ["gold/a3", "gold/bad", "gold/evalonly", "gold/layout",
                                               "silver/claude", "silver/gpt"]


def fingerprints(app, ctx):
    return {k["id"]: k["fingerprint"] for k in get_json(app, ctx, "/api/keys")[1]["keys"]}


def test_runs_have_input_set_outside_cache(app, kctx, env, answer_keys):
    for d in (X01, X02):
        page(answer_keys / "pages" / "prev" / "version9" / d)            # 기록 data/pages/version9가 prev/로 옮겨졌다
    kctx.pages_root = answer_keys / "pages"
    (env / "runs" / "20261030_models_x").mkdir()
    (env / "runs" / "20261030_models_x" / "compare.md").write_text("# 가짜 비교표", encoding="utf-8")
    broken = make_run(env / "runs", "20261030_sections_m1_broken", {X01: make_doc(X01)})
    (broken / "outputs" / f"{X01}.json").write_text("{깨진", encoding="utf-8")
    expected = {"id": "prev/version9", "label": app.bt.set_label("prev/version9"), "source": "moved", "usable": True,
                "missing_docs": []}
    code, data = get_json(app, kctx, "/api/runs")
    runs = {r["name"]: r for r in data["runs"]}
    assert code == 200 and runs[KEYED_RUN]["set"] == expected
    assert runs[KEYED_RUN]["pages_dir"] == "data/pages/version9"          # 기록된 글은 그대로
    assert runs["20261030_models_x"]["set"] is None
    assert runs["20261030_sections_m1_broken"]["error"] and runs["20261030_sections_m1_broken"]["set"] is None
    code, run = get_json(app, kctx, f"/api/run/{KEYED_RUN}")
    assert code == 200 and run["set"] == expected
    cached = [json.loads(f.read_text(encoding="utf-8"))["result"] for f in (env / "cache").rglob("*.json")]
    assert cached and all("set" not in r for r in cached)                  # 폴더 배치가 바뀌면 낡으므로 캐시에 넣지 않는다


def test_runs_set_without_pages_root(app, kctx):
    assert kctx.pages_root is None                                         # 넘기지 않으면 실제 data/pages를 읽지 않는다
    run = get_json(app, kctx, "/api/runs")[1]["runs"][0]
    assert run["set"] == {"id": None, "label": None, "source": "none", "usable": False, "missing_docs": [X01, X02]}


def test_key_fingerprint_matches_keys_list(app, kctx):
    fps = fingerprints(app, kctx)
    for key_id in ("silver/claude", "gold/a3"):
        code, data = get_q(app, kctx, "/api/runs", key=key_id)
        assert code == 200 and data["key"]["fingerprint"] == fps[key_id] is not None
        for path, query in ((f"/api/run/{KEYED_RUN}", {}), ("/api/diff", {"a": KEYED_RUN, "b": KEYED_RUN}),
                            ("/api/silver_gaps", {})):
            assert get_q(app, kctx, path, key=key_id, **query)[1]["key"]["fingerprint"] == fps[key_id], path
    assert get_json(app, kctx, "/api/runs")[1]["key"]["fingerprint"] == fps["silver/claude"]   # 켤 때 받은 정답지
    assert fps["silver/claude"] != fps["gold/a3"]


def test_api_keys_without_data_root(app, ctx):
    assert ctx.data_root is None                       # 넘기지 않으면 실제 data/를 읽지 않는다
    assert get_json(app, ctx, "/api/keys") == (200, {"keys": [], "default": "gold"})


def test_runs_scored_with_chosen_key(app, kctx, env, answer_keys):
    from msds.evaluate.score import score_set
    outputs = {d: json.loads((env / "runs" / KEYED_RUN / "outputs" / f"{d}.json").read_text(encoding="utf-8"))
               for d in (X01, X02)}
    seen, fps = {}, fingerprints(app, kctx)
    for key_id, doc in (("silver/claude", X01), ("gold/a3", X02)):
        gold = json.loads((answer_keys / key_id / f"{doc}.json").read_text(encoding="utf-8"))
        expected = score_set([(doc, gold, outputs[doc])])["weighted"]
        code, data = get_q(app, kctx, "/api/runs", key=key_id)
        assert code == 200
        assert data["key"] == {"id": key_id, "label": app.bt.key_label(key_id), "fingerprint": fps[key_id]}
        assert data["runs"][0]["weighted"] == expected and data["runs"][0]["docs"] == [doc]
        seen[key_id] = expected
    assert seen["silver/claude"] != seen["gold/a3"]
    assert get_q(app, kctx, "/api/runs")[1]["key"]["id"] == "silver/claude"   # 쿼리가 없으면 켤 때 받은 정답지


def test_cache_is_split_by_key(app, kctx, env, monkeypatch):
    calls = []
    real = app.br._summarize
    monkeypatch.setattr(app.br, "_summarize",
                        lambda run, gold_dir, *a: calls.append(gold_dir.name) or real(run, gold_dir, *a))
    weights = [get_q(app, kctx, "/api/runs", key=k)[1]["runs"][0]["weighted"]
               for k in ("gold/a3", "silver/claude", "gold/a3")]
    assert calls == ["a3", "claude"]                   # 두 번째 gold/a3는 캐시 파일을 읽는다
    assert weights[0] == weights[2] != weights[1]
    folders = sorted(p for p in (env / "cache").iterdir())
    assert len(folders) == 2
    assert all((f / f"{KEYED_RUN}.json").is_file() for f in folders)


def test_history_is_kept_per_key(app, kctx):
    get_q(app, kctx, "/api/runs", key="gold/a3")
    get_q(app, kctx, "/api/runs", key="silver/claude")
    assert len(kctx.run_history) == 2
    weights = {k: v[0]["weighted"] for k, v in kctx.run_history.items()}
    assert len(set(weights.values())) == 2


@pytest.mark.parametrize("path", ["/api/runs", f"/api/run/{KEYED_RUN}", "/api/diff", "/api/silver_gaps"])
def test_bad_key_is_refused(app, kctx, path):
    query = {"a": KEYED_RUN, "b": KEYED_RUN} if path == "/api/diff" else {}
    for bad in ("없음", "../silver/claude", "silver"):
        code, data = get_q(app, kctx, path, key=bad, **query)
        assert code == 404 and data["error"], (path, bad)
    code, data = get_q(app, kctx, path, key="silver/gpt", **query)
    assert code == 400 and app.bt.KEY_TEXT["key_empty"] in data["error"]


def test_run_diff_doc_answer_with_key(app, kctx, answer_keys, monkeypatch):
    code, data = get_q(app, kctx, f"/api/run/{KEYED_RUN}", key="gold/a3")
    assert code == 200 and data["key"]["id"] == "gold/a3" and data["docs"] == [X02]
    code, data = get_q(app, kctx, "/api/diff", a=KEYED_RUN, b=KEYED_RUN, key="gold/a3")
    assert code == 200 and data["key"]["id"] == "gold/a3"
    seen = []
    monkeypatch.setattr(app.bdoc, "doc_view", lambda run, doc, pages, gold: seen.append(gold) or {"values": []})
    code, data = get_q(app, kctx, "/api/doc", run=KEYED_RUN, doc=X02, key="gold/a3")
    assert code == 200 and data["key"] == {"id": "gold/a3", "label": app.bt.key_label("gold/a3"),
                                           "fingerprint": fingerprints(app, kctx)["gold/a3"]}
    assert seen == [answer_keys / "gold" / "a3"]
    code, data = get_q(app, kctx, "/api/doc", run=KEYED_RUN, doc=X02)
    assert code == 200 and data["key"]["id"] == "silver/claude" and seen[-1] == kctx.gold_dir


def test_silver_gaps_with_key(app, kctx, env):
    (env / "silver_gaps.yaml").write_text('- item: "11항 급성독성"\n  note: "가짜 메모"\n', encoding="utf-8")
    gaps = [{"item": "11항 급성독성", "note": "가짜 메모"}]
    assert get_json(app, kctx, "/api/silver_gaps") == (200, gaps)                # 쿼리가 없으면 지금처럼 배열
    code, data = get_q(app, kctx, "/api/silver_gaps", key="silver/claude")
    assert code == 200 and data == {"key": {"id": "silver/claude", "label": "AI 정답 초안 · Claude",
                                            "fingerprint": fingerprints(app, kctx)["silver/claude"]}, "gaps": gaps}
    code, data = get_q(app, kctx, "/api/silver_gaps", key="gold/a3")
    assert code == 200 and data["gaps"] == [] and data["key"]["id"] == "gold/a3"


def test_runs_key_without_data_root_is_gold_dir_name(app, ctx, env):
    three_runs(env)
    code, data = get_json(app, ctx, "/api/runs")
    assert code == 200 and data["key"] == {"id": "gold", "label": "gold", "fingerprint": None}   # 목록 밖 폴더는 지문 없음
    assert data["gold_dir"] == str(env / "gold")                                  # 기존 키는 그대로
    assert get_q(app, ctx, "/api/runs", key="gold")[1]["key"]["id"] == "gold"     # 켤 때 받은 폴더의 id는 다시 받는다
    assert get_q(app, ctx, "/api/runs", key="silver/claude")[0] == 404


def test_custom_startup_key_round_trips(app, kctx, env):
    kctx.gold_dir = env / "gold"                       # 목록 밖 폴더를 --gold-dir로 받은 경우
    code, data = get_json(app, kctx, "/api/keys")
    assert data["default"] == "gold"
    code, data = get_q(app, kctx, "/api/runs", key="gold")
    assert code == 200 and data["key"]["id"] == "gold" and data["runs"][0]["docs"] == [X01, X02]


def test_job_post_set_and_key_are_kept_in_target(app, env, answer_keys):
    from test_B_b_app_jobs import TAG, FakeSpawner
    for d in (X01, X02):
        page(answer_keys / "pages" / "prev" / "version9" / d)
    (env / "backend").mkdir()
    sp = FakeSpawner()
    m = app.bj.JobManager(env / "runs" / "manual" / "jobs", env / "가상" / "python", env / "backend", spawner=sp,
                          runs_dir=env / "runs", ps=lambda: "", sleep=lambda s: None)
    ctx = app.AppContext(runs_dir=env / "runs", gold_dir=answer_keys / "silver" / "claude", pages_dir=env / "pages",
                         static_dir=app.STATIC, cache_dir=None, gaps_file=env / "silver_gaps.yaml", jobs=m,
                         pages_root=answer_keys / "pages", data_root=answer_keys)
    fp = {k["id"]: k["fingerprint"] for k in get_json(app, ctx, "/api/keys")[1]["keys"]}
    body = {"model": TAG, "doc": X01, "sections": [8], "set": "prev/version9", "key": "gold/a3"}
    assert app.route("POST", "/api/jobs/try", {}, json.dumps(body).encode(), ctx)[0] == 200
    run = {"model": TAG, "docs": [X01], "set": "prev/version9", "run_name": "묶음실행", "repeat": 1, "confirm": True}
    assert app.route("POST", "/api/jobs/run", {}, json.dumps(run, ensure_ascii=False).encode(), ctx)[0] == 200
    code, data = get_json(app, ctx, "/api/jobs")
    targets = {j["kind"]: j["target"] for j in data["jobs"]}
    assert code == 200 and set(targets) == {"try", "run"}
    assert targets["try"]["set"] == "prev/version9" and targets["try"]["pages_dir"] == "../data/pages/prev/version9"
    assert targets["try"]["key"] == {"id": "gold/a3", "label": app.bt.key_label("gold/a3"), "fingerprint": fp["gold/a3"],
                                     "given": True}
    assert targets["run"]["set"] == "prev/version9" and targets["run"]["docs"] == [X01]
    assert targets["run"]["run_names"] == ["묶음실행_r1"]


def test_main_passes_data_root(app, monkeypatch, env, tmp_path):
    seen = {}
    monkeypatch.setattr(app.bs, "ENV_FILE", tmp_path / ".env")          # 실제 .env를 열지 않는다

    class FakeServer:
        server_port = 8765

        def __init__(self, address, handler):
            pass

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    real = app.make_handler
    monkeypatch.setattr(app, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(app, "make_handler", lambda c: seen.setdefault("ctx", c) and real(c))
    assert app.main(["--runs-dir", str(env / "runs"), "--no-browser"]) == 0
    assert seen["ctx"].data_root == app.DATA
    assert seen["ctx"].gold_dir == app.GOLD


# ── 서버 시작 ──────────────────────────────────────────

def test_allowed_host(app):
    assert app.allowed_host("127.0.0.1:8765", 8765)
    assert app.allowed_host("localhost:8765", 8765)
    assert not app.allowed_host("127.0.0.1:9999", 8765)
    assert not app.allowed_host("evil.example:8765", 8765)       # 다른 이름으로 이 화면을 부르는 경우(DNS 재바인딩)
    assert not app.allowed_host(None, 8765)


def test_main_rejects_other_hosts(app, monkeypatch):
    def no_socket(*a, **k):
        raise AssertionError("소켓을 열면 안 된다")
    monkeypatch.setattr(app, "ThreadingHTTPServer", no_socket)
    for host in ("0.0.0.0", "localhost", "::"):
        with pytest.raises(SystemExit):
            app.main(["--host", host, "--no-browser"])


def test_main_binds_127_only(app, monkeypatch, env, tmp_path):
    seen, opened = {}, []
    monkeypatch.setattr(app.bs, "ENV_FILE", tmp_path / ".env")          # 실제 .env를 열지 않는다

    class FakeServer:
        server_port = 8765

        def __init__(self, address, handler):
            seen["address"] = address

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            seen["closed"] = True

    monkeypatch.setattr(app, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: opened.append(url))
    assert app.main(["--runs-dir", str(env / "runs")]) == 0
    assert seen == {"address": ("127.0.0.1", 8765), "closed": True}
    assert opened == ["http://127.0.0.1:8765/"]


def test_main_gives_servers_env_file_without_network(app, monkeypatch, env, tmp_path):
    f = tmp_path / ".env"
    f.write_text("RUNPOD_API_KEY=FAKEKEY-main-SHOULD-NEVER-APPEAR-0a1b\n", encoding="utf-8")
    monkeypatch.setattr(app.bs, "ENV_FILE", f)
    seen = {}

    def no_network(*a, **k):
        raise AssertionError("켤 때 네트워크를 부르면 안 된다(Pod 이어 쓰기는 첫 요청 때)")

    class FakeServer:
        server_port = 8765

        def __init__(self, address, handler):
            pass

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    real = app.make_handler
    monkeypatch.setattr(app.bs.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(app, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(app, "make_handler", lambda c: seen.setdefault("ctx", c) and real(c))
    assert app.main(["--runs-dir", str(env / "runs"), "--no-browser"]) == 0
    assert seen["ctx"].servers.env_file == f and seen["ctx"].servers.env is app.os.environ


# ── 도움말 (step 8) ────────────────────────────────────

GUIDE_SECTIONS = ('앱은 어떤 일을 하나요?', '점수와 문제 건수는 어떻게 읽나요?', '문제 값을 원문에서 어떻게 확인하나요?', '실제 시험 전에 무엇을 준비하나요?', '한 부분을 어떻게 다시 시험하나요?', 'AI에게 시킬 일은 어떻게 고치나요?', '어느 서버를 고르고 언제 끄나요?', '오류가 나면 어디서 다시 시작하나요?', '어떤 문서와 정보를 보호하나요?')
ENV_NAMES = ("RUNPOD_VLLM_BASE_URL", "RUNPOD_VLLM_API_KEY", "RNGD_BASE_URL", "RNGD_API_KEY", "RUNPOD_API_KEY", "RNGD_SSH")


def test_guide_route_has_all_sections(app, ctx):
    code, ctype, body = get(app, ctx, "/static/guide.html")
    text = body.decode("utf-8")
    assert code == 200 and ctype.startswith("text/html")
    for title in GUIDE_SECTIONS:
        assert f"<h2>{title}</h2>" in text, title


def test_guide_has_no_outside_address_or_secret_values(app):
    for path in (app.STATIC / "guide.html", app.STATIC.parent / "README_b_app.md"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://", text) or path.suffix == ".md", path
        assert not re.search(r"(API_KEY|_SSH|_URL)=\S+", text), path
    text = (app.STATIC / "guide.html").read_text(encoding="utf-8")
    for name in ENV_NAMES:
        assert name in text, name
    assert not re.search(r"https?://", text)


def test_index_has_help_tab_and_links(app):
    text = (app.STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="main-nav"' in text and 'id="screen-s07"' in text
    shell = (app.STATIC / "js/shell.js").read_text(encoding="utf-8")
    assert '"s07"' in shell and '"nav.help"' in shell


# ── 오류 본문의 사실·할 일 (step 7) ───────────────────────

def has_problem_text(data: dict) -> bool:
    return all(isinstance(data.get(k), str) and data[k].strip() for k in ("error", "message", "fix"))


def test_missing_run_has_message_and_fix(app, ctx, env):
    three_runs(env)
    code, data = get_json(app, ctx, "/api/run/없는실행")
    assert code == 404 and has_problem_text(data) and data["error"] == "없는 실행: 없는실행"
    code, data = get_q(app, ctx, "/api/diff", a="없는실행", b="20261029_sections_m1_dev10_r1")
    assert code == 404 and has_problem_text(data)
    code, data = get_q(app, ctx, "/api/diff", a="20261029_sections_m1_dev10_r1")
    assert code == 400 and has_problem_text(data)
    code, data = get_q(app, ctx, "/api/doc", run="없는실행", doc=X01)
    assert code == 404 and has_problem_text(data)


def test_unknown_or_unusable_key_has_message_and_fix(app, kctx):
    code, data = get_q(app, kctx, "/api/runs", key="없음")
    assert code == 404 and has_problem_text(data) and "정답지" in data["fix"]
    assert data["error"] == "없는 정답지입니다: 없음. 정답지 목록에서 고르세요."
    code, data = get_q(app, kctx, "/api/runs", key="silver/gpt")
    assert code == 400 and has_problem_text(data) and app.bt.KEY_TEXT["key_empty"] in data["message"]


def test_unknown_set_has_message_and_fix(app, ctx):
    code, data = get_q(app, ctx, "/api/doc", set="없음", doc=X01)
    assert code == 404 and has_problem_text(data) and data["error"] == "없는 문서 묶음: 없음"


def test_bad_query_has_message_and_fix(app, ctx, env):
    three_runs(env)
    for path, query in (("/api/doc", {"doc": "../x"}), ("/api/prompt", {"model": "qwen36_35b_runpod", "no": "0"}),
                        ("/api/prompt", {"model": "없는태그", "no": "3"}),
                        ("/api/prompt_diff", {"a": "20261029_sections_m1_dev10_r1",
                                              "b": "20261029_sections_m1_dev10_r1", "no": "x"})):
        code, data = get_q(app, ctx, path, **query)
        assert code == 400 and has_problem_text(data), path
        assert data["fix"] == "할 일: 입력을 고친 뒤 다시 보내세요."


# ── README·.env.example (app-redo-api step 8) ───────────────

def _readme(app) -> str:
    return (app.STATIC.parent / "README_b_app.md").read_text(encoding="utf-8")


def _env_example(app) -> str:
    return (app.STATIC.parents[2] / ".env.example").read_text(encoding="utf-8")


def test_readme_covers_new_backend(app):
    text = _readme(app)
    for word in ("/api/sets", "/api/keys", "reload_env", "RUNPOD_VLLM_API_KEY", "prev/version9", "app-redo",
                 "b_app_sets.py", "tunnel_open", "tunnel_close", "ADR-025·028"):
        assert word in text, word
    assert "합격" not in text


def test_env_example_model_server_lines(app):
    lines = _env_example(app).splitlines()
    for name in ("RUNPOD_VLLM_API_KEY", "RUNPOD_VLLM_BASE_URL", "RNGD_BASE_URL", "RUNPOD_API_KEY", "RNGD_SSH"):
        assert f"{name}=" in lines, name
    i = lines.index("RUNPOD_VLLM_API_KEY=")
    above = []
    for line in reversed(lines[:i]):
        if not line.startswith("#"):
            break
        above.append(line)
    assert any("이어 쓴다" in line for line in above)
    assert "proxy.runpod.net" in _env_example(app)


def test_readme_and_env_example_have_no_secret_shapes(app):
    for text in (_readme(app), _env_example(app)):
        assert not re.search(r"(sk-|rpa_|hf_)\w{8,}", text)
        assert not re.search(r"[a-z0-9]{14}-8000", text)


# ── 첫 사용 기록 /api/journey (app-redo-api2 step 5) ─────

JT0 = "2026-10-31T00:58:00.000Z"
JT1 = "2026-10-31T01:02:00.000Z"


@pytest.fixture
def jctx(app, env):
    return app.AppContext(runs_dir=env / "runs", gold_dir=env / "gold", pages_dir=env / "pages",
                          static_dir=app.STATIC, cache_dir=None, gaps_file=env / "silver_gaps.yaml",
                          journey_file=env / "runs" / "manual" / "journey.json")


def journey_body(journey, **extra) -> bytes:
    return json.dumps({"journey": journey, **extra}, ensure_ascii=False).encode()


def put_journey(app, ctx, body: bytes):
    code, ctype, out = app.route("PUT", "/api/journey", {}, body, ctx)
    assert ctype.startswith("application/json")
    return code, json.loads(out)


def with_t1_success(app) -> dict:
    j = app.bjn.default()
    j["outcomes"]["t1"]["real"] = {"first_at": JT0, "last_at": JT0, "count": 1}
    return j


def test_journey_get_default_without_file(app, jctx):
    code, data = get_json(app, jctx, "/api/journey")
    assert code == 200 and data["journey"]["version"] == 2
    assert data == {"journey": app.bjn.default(), "problems": []}
    assert not jctx.journey_file.exists()


def test_journey_get_reports_broken_part(app, jctx):
    stored = with_t1_success(app)
    stored["progress"]["active"] = "t9"
    jctx.journey_file.parent.mkdir(parents=True)
    jctx.journey_file.write_text(json.dumps(stored), encoding="utf-8")
    code, data = get_json(app, jctx, "/api/journey")
    assert code == 200 and [p["part"] for p in data["problems"]] == ["progress"]
    assert data["journey"]["outcomes"] == stored["outcomes"]


def test_journey_put_returns_merged(app, jctx):
    first = with_t1_success(app)
    code, data = put_journey(app, jctx, journey_body(first))
    assert code == 200 and data == {"journey": first, "problems": []}
    second = app.bjn.default()
    second["progress"]["t1"] = {"state": "completed", "step": 3, "updated_at": JT1}
    code, data = put_journey(app, jctx, journey_body(second))
    assert code == 200 and data["problems"] == []
    assert data["journey"]["progress"] == second["progress"]
    assert data["journey"]["outcomes"] == first["outcomes"]       # 비워 보내도 성공 기록은 남는다
    assert get_json(app, jctx, "/api/journey")[1]["journey"] == data["journey"]


def test_journey_put_rejects_big_or_bad_body_and_keeps_file(app, jctx):
    assert put_journey(app, jctx, journey_body(with_t1_success(app)))[0] == 200
    before = jctx.journey_file.read_bytes()
    unknown = app.bjn.default()
    unknown["doc_id"] = X01
    bodies = {
        "17KB": journey_body(app.bjn.default()) + b" " * (17 * 1024),   # 모양은 맞지만 16KB를 넘는다
        "모르는 키": journey_body(unknown),
        "본문의 다른 키": journey_body(app.bjn.default(), extra=1),
        "journey 없음": b"{}",
        "JSON 아님": b"{journey",
        "배열": b"[]",
    }
    for name, body in bodies.items():
        code, data = put_journey(app, jctx, body)
        assert code == 400 and has_problem_text(data), name
        assert jctx.journey_file.read_bytes() == before, name
    assert "16KB" in put_journey(app, jctx, bodies["17KB"])[1]["message"]


def test_journey_without_file_place_is_503(app, ctx):
    assert ctx.journey_file is None
    code, data = get_json(app, ctx, "/api/journey")
    assert code == 503 and has_problem_text(data)
    code, data = put_journey(app, ctx, journey_body(app.bjn.default()))
    assert code == 503 and has_problem_text(data)


def test_journey_save_failure_is_500_with_text(app, jctx, monkeypatch):
    def broken(path, journey):
        raise OSError("가짜 쓰기 실패")
    monkeypatch.setattr(app.bjn, "save", broken)
    code, data = put_journey(app, jctx, journey_body(app.bjn.default()))
    assert code == 500 and has_problem_text(data)
    assert data["message"] == app.bt.JOURNEY_TEXT["errors"]["save_failed"]["message"] == "기록을 저장하지 못했습니다."


def test_put_only_for_journey(app, jctx):
    code, ctype, _ = app.route("PUT", "/api/runs", {}, b"{}", jctx)
    assert code == 404
    code, ctype, _ = app.route("DELETE", "/api/journey", {}, None, jctx)
    assert code == 404


def call_handler(app, ctx, method: str, body: bytes, headers: dict) -> int:
    """소켓 없이 처리기의 do_PUT·do_POST를 부른다. 보낸 상태 코드를 돌려준다."""
    handler = app.make_handler(ctx)
    h = handler.__new__(handler)
    h.server = SimpleNamespace(server_port=8765)
    h.headers = {"Host": "127.0.0.1:8765", "Content-Length": str(len(body)), **headers}
    h.path, h.rfile, sent = "/api/journey", io.BytesIO(body), []
    h._send = lambda code, ctype, out: sent.append(code)
    getattr(h, f"do_{method}")()
    return sent[0]


def test_journey_put_handler_checks_like_post(app, jctx, monkeypatch):
    seen = []
    real = app.allowed_post
    monkeypatch.setattr(app, "allowed_post", lambda *a: seen.append(a) or real(*a))
    body = journey_body(app.bjn.default())
    json_type = {"Content-Type": "application/json"}
    assert call_handler(app, jctx, "PUT", body, {"Content-Type": "text/plain"}) == 403
    assert call_handler(app, jctx, "PUT", body, {**json_type, "Origin": "http://evil.example"}) == 403
    assert call_handler(app, jctx, "PUT", body, {**json_type, "Host": "evil.example:8765"}) == 403
    assert not jctx.journey_file.exists()
    assert call_handler(app, jctx, "PUT", body, {**json_type, "Origin": "http://127.0.0.1:8765"}) == 200
    assert jctx.journey_file.exists()
    assert seen[0] == ("text/plain", None, 8765) and len(seen) == 3   # Host가 다르면 본문 검사 전에 막는다


def test_main_sets_journey_file_without_creating_it(app, monkeypatch, env, tmp_path):
    runs = tmp_path / "repo_runs"                                       # 저장소의 runs/ 대신
    monkeypatch.setattr(app, "RUNS", runs)
    monkeypatch.setattr(app.bs, "ENV_FILE", tmp_path / ".env")          # 실제 .env를 열지 않는다
    seen = {}

    class FakeServer:
        server_port = 8765

        def __init__(self, address, handler):
            pass

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    real = app.make_handler
    monkeypatch.setattr(app, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(app, "make_handler", lambda c: seen.setdefault("ctx", c) and real(c))
    assert app.main(["--runs-dir", str(env / "runs"), "--no-browser"]) == 0
    assert seen["ctx"].journey_file == runs / "manual" / "journey.json"
    assert not seen["ctx"].journey_file.exists()
