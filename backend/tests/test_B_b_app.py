"""scripts/b_app.py 시험 (작업 화면 서버와 탭 ① 점수판, ADR-025).

route()를 직접 부른다. 서버 소켓을 열지 않고 네트워크를 부르지 않는다.
실행 폴더·정답 폴더·manifest는 test_B_b_app_runs의 가짜 픽스처(tmp_path)를 쓴다. 저장소의 runs/, data/는 읽지 않는다 (D-43).
"""
import importlib
import json
import re

import pytest

from test_B_b_app_runs import env, make_run  # noqa: F401  env는 픽스처
from test_B_compare_models import SCRIPTS, X01, X02, make_doc

STATIC_FILES = ("index.html", "app.js", "app.css")
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
    for tab in TABS:
        assert tab in text, tab


def test_static(app, ctx):
    code, ctype, body = get(app, ctx, "/static/app.js")
    assert code == 200 and "javascript" in ctype and b"/api/runs" in body
    code, ctype, _ = get(app, ctx, "/static/app.css")
    assert code == 200 and ctype.startswith("text/css")


def test_static_rejects_parent_paths(app, ctx):
    assert get(app, ctx, "/static/../b_app.py")[0] == 400
    assert get(app, ctx, "/static/%2e%2e/b_app.py")[0] == 400
    assert get(app, ctx, "/static/없는파일.js")[0] == 404


@pytest.mark.parametrize("name", STATIC_FILES)
def test_static_files_call_no_outside_address(app, name):
    text = (app.STATIC / name).read_text(encoding="utf-8")
    assert not re.search(r"https?://", text), name


# ── API ────────────────────────────────────────────────

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
            "title": "10/30 Qwen3.6 35B (RunPod) · 안내문 s7 · 입력 version9 · 분류 검사 · 개발 10건 · 2회차",
            "subtitle": name,
            "parts": ["10/30 Qwen3.6 35B (RunPod)", "안내문 s7", "입력 version9", "분류 검사", "개발 10건", "2회차"],
        }
        assert result["model_label"] == "Qwen3.6 35B (RunPod)"
    # Step 4 adds presentation fields; every original scoring field remains identical.
    assert {k: v for k, v in detail.items()
            if k not in ("label", "model_label", "status_text", "card_summaries")} == before
    assert summary == before


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
            assert r["label"]["title"].startswith("[수동] 10/30")


def test_options_model_labels_keep_tags_and_connection_state(app, ctx):
    ctx.model_status = lambda: [{"tag": "qwen36_35b_runpod", "reachable": True, "match": True}]
    ctx.pages_root = ctx.pages_dir
    code, data = get_json(app, ctx, "/api/options")
    assert code == 200
    models = {m["tag"]: m for m in data["models"]}
    assert models["qwen36_35b_runpod"]["label"] == "Qwen3.6 35B (RunPod)"
    assert models["qwen36_35b_runpod"]["connected"] is True
    assert models["gpt_oss_20b_rngd"]["label"] == "gpt-oss 20B (RNGD)"
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


def test_api_run(app, ctx, env):
    three_runs(env)
    code, data = get_json(app, ctx, "/api/run/20261029_sections_m1_dev10_r1")
    assert code == 200
    assert {"details", "grid", "items_na_excluded", "per_doc"} <= set(data)
    assert data["docs"] == [X01, X02]
    code, data = get_json(app, ctx, "/api/run/manual/20261030_1200_T21-X01_s11")
    assert code == 200 and data["kind"] == "manual"


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
    assert result["status_text"] == app.bt.score_status(before, app.br.criteria(), connected=None)
    assert set(result["card_summaries"]) == {"history", "docs", "grid", "rows"}
    assert result["card_summaries"]["history"].startswith("실행 2개,")
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
    def capture(info, criteria, *, connected=None):
        seen.append(connected)
        return real(info, criteria, connected=connected)
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


def test_main_binds_127_only(app, monkeypatch, env):
    seen, opened = {}, []

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


# ── 도움말 (step 8) ────────────────────────────────────

GUIDE_SECTIONS = ("이 도구는 무엇을 하나", "점수는 어떻게 읽나", "탭마다 무엇을 보나", "처음 한 번 준비",
                  "시험 하나 돌리기", "안내문을 바꿔 보기", "자주 보는 실패 네 가지", "하지 말 것", "용어 풀이")
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
    assert "도움말" in text
    assert text.count("자세히 → 도움말") == 5
