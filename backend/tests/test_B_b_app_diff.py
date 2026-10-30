"""scripts/b_app_diff.py 시험 (작업 화면 탭 ② 두 실행 비교, ADR-025).

두 실행은 test_B_b_app_runs의 가짜 실행 폴더(tmp_path)를 summarize_run으로 요약한 것이다. 저장소의 runs/, data/는 읽지 않는다 (D-43).
git 명령과 네트워크를 부르지 않는다. 안내문 글은 가짜 builder로 만든다.
"""
import ast
import importlib
import inspect
import json
import textwrap

import pytest

from msds.evaluate.score import TOP_TO_ITEMS
from test_B_b_app_runs import ACUTE, br, env, make_run, req, summarize  # noqa: F401  br·env는 픽스처
from test_B_compare_models import SCRIPTS, X01, X02, make_doc

HASHES = {n: f"h{n:02d}" for n in range(1, 17)}


@pytest.fixture
def bd(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    mod = importlib.import_module("b_app_diff")
    monkeypatch.setattr(mod, "_PROMPTS", {})                   # 시험마다 빈 메모리 캐시
    return mod


def full_docs() -> dict:
    return {X01: make_doc(X01), X02: make_doc(X02)}


def two(br, env, *, a_docs=None, b_docs=None, info_a=None, info_b=None, **kw):
    """실행 a, b를 만들고 요약 두 개를 돌려준다. 기본: a는 정답과 같고, b는 X01의 독성 행을 비운다."""
    base = {"prompt_hashes": HASHES}
    make_run(env / "runs", "a", a_docs or full_docs(), info={**base, **(info_a or {})},
             checks=kw.get("checks_a"), raw=kw.get("raw_a"))
    make_run(env / "runs", "b", b_docs or {X01: make_doc(X01, toxicity=True), X02: make_doc(X02)},
             info={**base, **(info_b or {})}, checks=kw.get("checks_b"), raw=kw.get("raw_b"))
    return summarize(br, env, "a"), summarize(br, env, "b")


def item(diff: dict, name: str) -> dict:
    return next(i for i in diff["items"] if i["name"] == name)


def cause(diff: dict, name: str) -> dict:
    return next(c for c in diff["causes"] if c["item"] == name)


def section_cell(no: int, ok=True, reextracted=False) -> dict:
    return {"msds_index": 0, "section": no, "ok": ok, "mode": "rows", "reextracted": reextracted, "attempts": 1,
            "seconds": 5.0}


# ── 점수 차와 원인 ─────────────────────────────────────

def test_dropped_rows_show_up_as_cause(bd, br, env):
    a, b = two(br, env)
    d = bd.diff_runs(a, b)
    acute = item(d, ACUTE)
    assert acute["delta"] < 0 and acute["delta"] == pytest.approx((acute["b"] - acute["a"]))
    assert (acute["a"], acute["b"]) == (pytest.approx(100), pytest.approx(50))      # 점수는 0~100
    assert acute["pass_a"] and not acute["pass_b"]
    assert acute["sections"] == [11]
    c = cause(d, ACUTE)
    assert c["delta"] == pytest.approx(acute["delta"])
    assert any("행" in r or "빠뜨림" in r for r in c["reasons"]), c["reasons"]
    assert any("빠뜨림이 0 → 1" in r for r in c["reasons"]), c["reasons"]
    assert any("독성 행이 2 → 1 (정답 2)" in r for r in c["reasons"]), c["reasons"]
    assert any("X01 −100.0" in r for r in c["reasons"]), c["reasons"]                # 가장 많이 내려간 문서
    assert d["weighted"]["delta"] == pytest.approx(b["weighted"] - a["weighted"]) and d["weighted"]["delta"] < 0
    assert d["weighted_na_excluded"]["a"] == pytest.approx(a["weighted_na_excluded"])
    assert d["rows"]["toxicity"] == {"a": 2, "b": 1, "gold": 2}


def test_only_drops_of_two_points_or_more_get_causes(bd, br, env):
    a, b = two(br, env)
    d = bd.diff_runs(a, b)
    assert all(c["delta"] <= -2.0 for c in d["causes"])
    assert {c["item"] for c in d["causes"]} == {i["name"] for i in d["items"]
                                                  if i["delta"] is not None and i["delta"] <= -2.0}
    assert bd.diff_runs(a, a)["causes"] == []


def test_prompt_change_is_first_reason(bd, br, env):
    a, b = two(br, env, info_a={"prompt_version": "s6"},
               info_b={"prompt_version": "s7", "prompt_hashes": {**HASHES, 11: "다른해시"}})
    d = bd.diff_runs(a, b)
    assert d["prompt_changed_sections"] == [11]
    reasons = cause(d, ACUTE)["reasons"]
    assert "안내문" in reasons[0] and "s6 → s7" in reasons[0] and "11항" in reasons[0]
    assert not any("흔들림" in r for r in reasons)


def test_same_conditions_end_with_flutter(bd, br, env):
    a, b = two(br, env)
    d = bd.diff_runs(a, b)
    assert d["prompt_changed_sections"] == []
    assert all(not c["changed"] for c in d["conditions"])
    assert [c["what"] for c in d["conditions"]] == ["모델", "안내문 버전", "입력 판", "동시 호출", "코드 커밋"]
    reasons = cause(d, ACUTE)["reasons"]
    assert "흔들림" in reasons[-1] and "16" in reasons[-1]
    assert not any("안내문" in r for r in reasons)


def test_other_condition_changes(bd, br, env):
    a, b = two(br, env, info_b={"model_tag": "m2", "pages_dir": "data/pages/version13", "concurrency": 1})
    d = bd.diff_runs(a, b)
    changed = {c["what"]: (c["a"], c["b"]) for c in d["conditions"] if c["changed"]}
    assert changed == {"모델": ("m1", "m2"), "입력 판": ("data/pages/version9", "data/pages/version13"),
                       "동시 호출": (16, 1)}
    reasons = cause(d, ACUTE)["reasons"]
    assert any("모델" in r and "m1 → m2" in r for r in reasons)
    assert any("입력 판" in r and "version9 → version13" in r for r in reasons)
    assert any("동시 호출" in r and "16 → 1" in r for r in reasons)
    assert not any("흔들림" in r for r in reasons)


def test_calls_only_in_b_are_reasons(bd, br, env):
    checks_a = {X01: {"sections": [section_cell(11), section_cell(2)]}}
    checks_b = {X01: {"sections": [section_cell(11, reextracted=True), section_cell(2, ok=False)]}}
    raw_b = {f"{X01}_m0_s11.json": {"requests": [req(finish="stop")], "first_attempt": {"requests": [req()]}}}
    a, b = two(br, env, checks_a=checks_a, checks_b=checks_b, raw_b=raw_b)
    reasons = cause(bd.diff_runs(a, b), ACUTE)["reasons"]
    assert any("X01 11항" in r and "출력 한도(긴출력)" in r for r in reasons), reasons
    assert any("X01 11항" in r and "재추출" in r for r in reasons), reasons
    assert not any("2항" in r for r in reasons)                     # 이 항목(11항)과 상관없는 항은 쓰지 않는다
    assert bd.diff_runs(b, b)["causes"] == []


def test_calls_already_in_a_are_not_reasons(bd, br, env):
    checks = {X01: {"sections": [section_cell(11, reextracted=True)]}}
    a, b = two(br, env, checks_a=checks, checks_b=checks)
    assert not any("재추출" in r for r in cause(bd.diff_runs(a, b), ACUTE)["reasons"])


def test_explain_drop_needs_evidence(bd, br, env):
    a, b = two(br, env, info_a={"git_commit": "aaa1111"}, info_b={"git_commit": "bbb2222"})
    d = bd.diff_runs(a, b)
    reasons = bd.explain_drop(item(d, ACUTE), a, b)
    assert reasons == cause(d, ACUTE)["reasons"]
    assert not any("흔들림" in r for r in reasons)                  # 코드 커밋이 달라 조건이 같지 않다
    assert all(any(ch.isdigit() for ch in r) for r in reasons)      # 모든 문장에 수치나 번호가 있다


# ── 바뀐 값·문서 ───────────────────────────────────────

def test_changed_values(bd, br, env):
    a, b = two(br, env, a_docs={X01: make_doc(X01, toxicity=True), X02: make_doc(X02)},
               b_docs={X01: make_doc(X01), X02: make_doc(X02, toxicity=True)})
    d = bd.diff_runs(a, b)
    ch = d["changed_values"][ACUTE]
    a_only = [x for x in a["details"] if x["item"] == ACUTE]
    b_only = [x for x in b["details"] if x["item"] == ACUTE]
    assert a_only and b_only
    assert ch["fixed"] == [{"doc_id": x["doc_id"], "kind": x["kind"], "content": x["content"]} for x in a_only]
    assert ch["broken"] == [{"doc_id": x["doc_id"], "kind": x["kind"], "content": x["content"]} for x in b_only]
    assert {x["doc_id"] for x in ch["fixed"]} == {X01} and {x["doc_id"] for x in ch["broken"]} == {X02}
    assert bd.diff_runs(a, a)["changed_values"] == {}


def test_docs_only_in_one_run(bd, br, env):
    a, b = two(br, env, b_docs={X01: make_doc(X01)})
    d = bd.diff_runs(a, b)
    assert d["docs"] == {"common": [X01], "only_a": [X02], "only_b": []}
    assert d["changed_values"] == {}                                 # a에만 있는 문서의 값은 고친 것으로 치지 않는다


def test_run_without_scores(bd, br, env):
    make_run(env / "runs", "empty", {})
    a, _ = two(br, env)
    d = bd.diff_runs(summarize(br, env, "empty"), a)
    assert len(d["items"]) == 23
    assert all(i["a"] is None and i["delta"] is None for i in d["items"])
    assert d["causes"] == [] and d["weighted"]["delta"] is None


# ── 항목 ↔ 항 ──────────────────────────────────────────

def test_item_sections_cover_all_items(bd, br):
    names = [i["name"] for i in br.criteria()["items"]]
    for n in names:
        assert bd.sections_of(n), n
    assert bd.sections_of("구성성분 필드(성분명·KE)") == [3]
    assert bd.sections_of("관리정보(제출번호·작성일·개정일·개정횟수)") == [1, 16]
    assert bd.sections_of("11항 CMR(성분·유해성·기관·등급)") == [11]


def test_item_sections_match_section_specs(bd):
    from msds.extract.section_specs import load_specs
    for no, spec in load_specs().items():
        for key in spec.targets:
            for prefix in TOP_TO_ITEMS.get(key, []):
                assert no in bd.sections_of(prefix), (no, key, prefix)
    assert 16 in bd.sections_of("관리정보")                          # 16항 meta_revision이 관리정보를 채운다


# ── 안내문 글 차이 ─────────────────────────────────────

def test_prompt_diff_with_fake_builder(bd, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    texts = {"c1": "가\n나\n다", "c2": "가\n나\n다", "c3": "가\n라\n다\n마"}
    same = bd.prompt_diff(11, True, "c1", "c2", tmp_path, builder=texts.get)
    assert same["same"] is True and same["diff"] == "" and same["a_hash"] == same["b_hash"]
    assert (same["section"], same["a_lines"], same["b_lines"]) == (11, 3, 3)
    d = bd.prompt_diff(11, True, "c1", "c3", tmp_path, builder=texts.get)
    lines = d["diff"].splitlines()
    assert d["same"] is False and d["a_hash"] != d["b_hash"] and len(d["a_hash"]) == 12
    assert "-나" in lines and "+라" in lines and "+마" in lines
    assert d["b_lines"] == 4
    assert list(tmp_path.iterdir()) == []                            # 파일을 하나도 만들지 않는다


def test_prompt_hash_matches_run_info_rule(bd):
    import hashlib
    d = bd.prompt_diff(2, False, "c1", "c2", None, builder=lambda c: "안내문 " + c)
    assert d["a_hash"] == hashlib.sha256("안내문 c1".encode("utf-8")).hexdigest()[:12]   # prompt_hash와 같은 규칙


def test_worktree_is_removed_in_finally(bd):
    tree = ast.parse(textwrap.dedent(inspect.getsource(bd._system_at_commit)))
    finals = [ast.unparse(ast.Module(body=t.finalbody, type_ignores=[])) for t in ast.walk(tree)
              if isinstance(t, ast.Try) and t.finalbody]
    assert any("worktree" in f and "remove" in f for f in finals), finals
    assert any("prune" in f for f in finals), finals
    src = inspect.getsource(bd._system_at_commit)
    assert "mkdtemp" in src and "timeout" in src


def test_bad_commit_is_rejected_before_git(bd, monkeypatch):
    def no_git(*a, **k):
        raise AssertionError("git을 부르면 안 된다")
    monkeypatch.setattr(bd.subprocess, "run", no_git)
    for commit in ("--help", "abc 123", "", None, "HEAD~1"):
        with pytest.raises(ValueError):
            bd._system_at_commit(commit, 11, True, SCRIPTS)


# ── 라우트 ─────────────────────────────────────────────

@pytest.fixture
def app(monkeypatch, bd):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    mod = importlib.import_module("b_app")
    monkeypatch.setattr(mod, "bd", bd)
    return mod


@pytest.fixture
def ctx(app, env):
    return app.AppContext(runs_dir=env / "runs", gold_dir=env / "gold", pages_dir=env / "pages",
                          static_dir=app.STATIC, cache_dir=None, gaps_file=env / "silver_gaps.yaml")


def call(app, ctx, path, **query):
    code, ctype, body = app.route("GET", path, {k: [v] for k, v in query.items()}, None, ctx)
    assert ctype.startswith("application/json")
    return code, json.loads(body)


def test_route_diff(app, ctx, br, env):
    two(br, env)
    code, data = call(app, ctx, "/api/diff", a="a", b="b")
    assert code == 200 and len(data["items"]) == 23
    assert data["a"]["name"] == "a" and data["b"]["name"] == "b"
    assert any(c["item"] == ACUTE for c in data["causes"])
    assert call(app, ctx, "/api/diff", a="a", b="없는실행")[0] == 404
    assert call(app, ctx, "/api/diff", a="a")[0] == 400


def test_route_diff_adds_headline_with_run_titles_without_changing_diff(app, ctx, br, env):
    a, b = two(br, env)
    expected = app.bd.diff_runs(a, b)
    code, data = call(app, ctx, "/api/diff", a="a", b="b")
    assert code == 200
    assert data["headline"] == app.bt.diff_headline(
        expected, app.bt.run_label(a)["title"], app.bt.run_label(b)["title"])
    assert data["ui_text"] == app.bt.diff_ui_text(expected)
    assert {k: v for k, v in data.items() if k not in {"headline", "ui_text", "key"}} == expected


def test_route_prompt_diff(app, ctx, br, env, bd, monkeypatch):
    two(br, env, info_a={"git_commit": "abc1234", "rows_sections": [11]},
        info_b={"git_commit": "def5678", "rows_sections": []})
    seen = []

    def fake(commit, no, rows, repo_root):
        seen.append((commit, no, rows))
        return f"{commit} {no}항 rows={rows}"
    monkeypatch.setattr(bd, "_system_at_commit", fake)
    code, data = call(app, ctx, "/api/prompt_diff", a="a", b="b", no="11")
    assert code == 200
    assert seen == [("abc1234", 11, True), ("def5678", 11, False)]     # 실행마다 자기 rows_sections로 만든다
    assert "-abc1234 11항 rows=True" in data["diff"].splitlines()
    assert "+def5678 11항 rows=False" in data["diff"].splitlines()
    call(app, ctx, "/api/prompt_diff", a="a", b="b", no="11")
    assert len(seen) == 2                                               # 같은 커밋·항·형식은 메모리 캐시
    for no in ("0", "17", "x"):
        assert call(app, ctx, "/api/prompt_diff", a="a", b="b", no=no)[0] == 400
    assert call(app, ctx, "/api/prompt_diff", a="a", b="없는실행", no="11")[0] == 404


def test_route_prompt_diff_without_commit(app, ctx, br, env):
    two(br, env, info_b={"git_commit": None})
    code, data = call(app, ctx, "/api/prompt_diff", a="a", b="b", no="11")
    assert code == 400 and "git_commit" in data["error"]
