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


def test_api_criteria(app, ctx):
    code, data = get_json(app, ctx, "/api/criteria")
    assert code == 200 and len(data["items"]) == 23 and data["pass_score"] == 90.0


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
