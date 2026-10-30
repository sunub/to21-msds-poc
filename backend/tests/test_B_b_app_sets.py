"""scripts/b_app_sets.py 시험 (작업 화면의 문서 묶음 찾기, ADR-028).

쪽 글자 폴더 배치는 tmp_path에 직접 만든 짧은 가짜 글로만 만든다. 실제 data/pages/, data/silver/, runs/는 읽지 않는다 (D-43·D-47).
manifest는 test_B_b_app_runs의 env 픽스처로 가짜 ROWS(X01·X02 개발, X09 평가)를 끼운다.
"""
import importlib
import json

import pytest

from test_B_b_app_runs import env  # noqa: F401  env는 픽스처
from test_B_compare_models import ROWS, SCRIPTS, X01, X02, X09, write_json

SET_IDS = [".", "prev", "prev/evalonly", "prev/v2", "prev/v9", "version13_신규40"]
NUMBERED = "L001 가짜 제품 이름\nL002 가짜 공급자\n"
PLAIN = "가짜 제품 이름\n가짜 공급자\n"
NO_COUNTS = {"dev": 0, "eval_locked": 0, "other": 0, "outside": 0, "unknown": 0}


@pytest.fixture
def bsets(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_sets")


@pytest.fixture
def bt(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_text")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app")


def page(doc_dir, text=NUMBERED, name="p001.txt"):
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / name).write_text(text, encoding="utf-8")


def meta(doc_dir, doc_id):
    write_json(doc_dir / "meta.json", {"doc_id": doc_id, "source_file": "가짜.pdf", "page_count": 2,
                                       "text_layer": "정상", "pages": []})


@pytest.fixture
def pages(env):
    """가짜 data/pages 배치. 바로 아래 신규 문서 둘, prev/ 아래 옛 판들, 빈 폴더 하나."""
    root = env / "data" / "pages"
    # 첫 쪽은 빈 줄 뒤에 줄 번호가 오고, 둘째 쪽은 줄 번호가 없다. 판정은 가장 작은 쪽의 첫 글자 줄로 한다
    page(root / "RAW-90", "\n  \nL001 가짜 제품 이름\n")
    page(root / "RAW-90", PLAIN, "p002.txt")
    meta(root / "RAW-90", "RAW-90")
    page(root / "RAW-90" / "tables", "| 가짜 | 표 |", "t001.md")
    page(root / "RAW-91")                                   # meta.json 없음 → 용도를 모름
    page(root / "prev" / X01, PLAIN)                         # prev 바로 아래 문서별 복사본(줄 번호 없음)
    for d in (X01, X02, X09):
        page(root / "prev" / "v9" / d)
    meta(root / "prev" / "v9" / X09, X09)
    (root / "prev" / "v9" / "summary.json").write_text("{}", encoding="utf-8")
    (root / "prev" / "v9" / "report.md").write_text("# 가짜", encoding="utf-8")
    page(root / "prev" / "v2" / X01, PLAIN)
    page(root / "prev" / "evalonly" / X09)
    (root / "version13_신규40").mkdir()
    (root / "summary.json").write_text("{}", encoding="utf-8")
    return root


def by_id(sets):
    return {s["id"]: s for s in sets}


def docs_of(s):
    return {d["doc_id"]: d for d in s["docs"]}


# ── 묶음 목록 ──────────────────────────────────────────

def test_list_sets_ids(bsets, pages):
    sets = bsets.list_sets(pages)
    assert [s["id"] for s in sets] == SET_IDS                 # RAW-90/tables, 묶음을 담기만 하는 폴더는 없다


def test_top_level_set_has_outside_and_unknown_docs(bsets, bt, pages):
    top = by_id(bsets.list_sets(pages))["."]
    assert top["usable"] is True and top["reason"] is None
    assert top["label"] == bt.set_label(".") and top["path"] == "data/pages"
    assert top["counts"] == {**NO_COUNTS, "outside": 1, "unknown": 1}
    assert [d["doc_id"] for d in top["docs"]] == ["RAW-90", "RAW-91"]
    docs = docs_of(top)
    assert docs["RAW-90"] == {"doc_id": "RAW-90", "group": "outside", "locked": False, "reason": None,
                              "pages": 2, "line_numbers": True}
    assert docs["RAW-91"]["group"] == "unknown" and docs["RAW-91"]["locked"] is True
    assert docs["RAW-91"]["reason"] == bt.SET_TEXT["unknown_doc"]


def test_version_set_locks_eval_doc(bsets, pages):
    v9 = by_id(bsets.list_sets(pages))["prev/v9"]
    assert v9["usable"] is True and v9["reason"] is None
    assert v9["label"] == "prev/v9" and v9["path"] == "data/pages/prev/v9"
    assert v9["counts"] == {**NO_COUNTS, "dev": 2, "eval_locked": 1}
    assert [d["doc_id"] for d in v9["docs"]] == [X01, X02, X09]
    docs = docs_of(v9)
    assert docs[X01]["group"] == "dev" and docs[X01]["line_numbers"] is True and docs[X01]["locked"] is False
    x09 = docs[X09]
    assert x09["group"] == "eval" and x09["locked"] is True and x09["line_numbers"] is None and x09["pages"] == 1
    assert "평가" in x09["reason"] and "D-43" in x09["reason"]


def test_unusable_sets_say_why(bsets, bt, pages):
    sets = by_id(bsets.list_sets(pages))
    for sid in ("prev", "prev/v2"):
        assert sets[sid]["usable"] is False and sets[sid]["reason"] == bt.SET_TEXT["no_line_numbers"], sid
        assert docs_of(sets[sid])[X01]["line_numbers"] is False
    assert sets["prev"]["counts"] == {**NO_COUNTS, "dev": 1}
    assert sets["prev/evalonly"]["usable"] is False and sets["prev/evalonly"]["reason"] == bt.SET_TEXT["eval_only"]
    empty = sets["version13_신규40"]
    assert empty["usable"] is False and empty["reason"] == bt.SET_TEXT["empty"]
    assert empty["docs"] == [] and empty["counts"] == NO_COUNTS


def test_nothing_open_when_every_doc_is_locked(bsets, bt, env):
    root = env / "other_pages"
    page(root / "odd" / "RAW-77")                            # meta.json 없음 → 잠김
    page(root / "odd" / X09)                                 # 평가용 → 잠김
    sets = bsets.list_sets(root)
    assert [s["id"] for s in sets] == ["odd"]                # 바로 아래 문서가 없는 root는 묶음을 담는 폴더다
    assert sets[0]["usable"] is False and sets[0]["reason"] == bt.SET_TEXT["nothing_open"]


def test_missing_root_is_empty_list(bsets, env):
    assert bsets.list_sets(env / "없는_폴더") == []


def test_list_sets_does_not_open_eval_files(bsets, bt, pages):
    locked = [pages / "prev" / "v9" / X09 / "p001.txt", pages / "prev" / "v9" / X09 / "meta.json",
              pages / "prev" / "evalonly" / X09 / "p001.txt"]
    for f in locked:
        f.chmod(0o000)
    try:
        sets = by_id(bsets.list_sets(pages))
    finally:
        for f in locked:
            f.chmod(0o644)
    assert sets["prev/evalonly"]["reason"] == bt.SET_TEXT["eval_only"]
    assert docs_of(sets["prev/v9"])[X09]["pages"] == 1


# ── 문서 하나 ──────────────────────────────────────────

def test_doc_entry_other_and_meta_mismatch(bsets, bt, env):
    rows = ROWS + [{"doc_id": "T21-X05", "purpose": "기타"}]
    page(env / "p" / "T21-X05")
    other = bsets.doc_entry(env / "p" / "T21-X05", rows)
    assert other["group"] == "other" and other["locked"] is False and other["line_numbers"] is True
    page(env / "p" / "RAW-92")
    meta(env / "p" / "RAW-92", "RAW-99")                     # meta.json의 doc_id가 폴더 이름과 다르면 믿지 않는다
    odd = bsets.doc_entry(env / "p" / "RAW-92", rows)
    assert odd["group"] == "unknown" and odd["locked"] is True and odd["line_numbers"] is None
    page(env / "p" / "RAW-93")
    (env / "p" / "RAW-93" / "meta.json").write_text("{깨진", encoding="utf-8")
    assert bsets.doc_entry(env / "p" / "RAW-93", rows)["reason"] == bt.SET_TEXT["unknown_doc"]


def test_doc_lock(bsets, bt, pages):
    assert "평가" in bsets.doc_lock(X09, None, ROWS)
    assert "평가" in bsets.doc_lock(X09, pages / "prev" / "v9" / X09, ROWS)
    assert bsets.doc_lock(X01, None, ROWS) is None
    assert bsets.doc_lock("RAW-90", pages / "RAW-90", ROWS) is None
    assert bsets.doc_lock("RAW-90", None, ROWS) == bt.SET_TEXT["unknown_doc"]
    assert bsets.doc_lock("RAW-91", pages / "RAW-91", ROWS) == bt.SET_TEXT["unknown_doc"]
    assert bsets.doc_lock("../RAW-90", pages / "RAW-90", ROWS) == bt.SET_TEXT["unknown_doc"]


def test_is_doc_dir(bsets, pages):
    assert bsets.is_doc_dir(pages / "RAW-90")
    assert not bsets.is_doc_dir(pages / "RAW-90" / "tables")
    assert not bsets.is_doc_dir(pages / "prev")
    assert not bsets.is_doc_dir(pages / "version13_신규40")


@pytest.mark.parametrize("doc_id,ok", [("T21-S003", True), ("RAW-01", True), ("T21-X01", True),
                                       ("t21-x01", False), ("../T21-X01", False), ("T21-X01/p001", False),
                                       ("T21-", False), ("", False)])
def test_doc_id_pattern(bsets, doc_id, ok):
    assert bool(bsets.DOC_ID.fullmatch(doc_id)) is ok


# ── 고르기 ─────────────────────────────────────────────

def test_find_set_only_listed_ids(bsets, pages):
    sets = bsets.list_sets(pages)
    assert bsets.find_set(sets, "prev/v9")["id"] == "prev/v9"
    assert bsets.find_set(sets, ".")["id"] == "."
    for bad in ("../x", "/etc", "prev/../prev", "prev/v9/", "없는_묶음", None, 3):
        assert bsets.find_set(sets, bad) is None, bad
    assert bsets.set_dir(pages, "prev/v9") == pages / "prev" / "v9"
    assert bsets.set_dir(pages, ".") == pages


def test_default_set(bsets, pages, monkeypatch):
    sets = bsets.list_sets(pages)
    assert bsets.default_set(sets, pages / "prev" / "v9", pages) == "prev/v9"
    monkeypatch.setattr(bsets, "DEFAULT_SET", "prev/v9")
    assert bsets.default_set(sets, pages / "prev" / "v2", pages) == "prev/v9"        # 켤 때 받은 폴더가 쓸 수 없는 판
    assert bsets.default_set(sets, None, pages) == "prev/v9"
    monkeypatch.setattr(bsets, "DEFAULT_SET", "prev/version9")                       # 기본 묶음이 없으면 첫 번째 쓸 수 있는 묶음
    assert bsets.default_set(sets, pages / "없는_폴더", pages) == "."
    assert bsets.default_set([s for s in sets if not s["usable"]], pages / "prev" / "v2", pages) is None


def test_default_set_constant(bsets):
    assert bsets.DEFAULT_SET == "prev/version9"


# ── 실행이 쓴 묶음 ─────────────────────────────────────

@pytest.mark.parametrize("recorded,doc_id,expected", [
    ("data/pages/v9", X01, ("prev/v9", "moved")),             # 10/30 배치 변경으로 prev/ 아래로 옮겨진 판
    ("data/pages/prev/v9", X01, ("prev/v9", "run")),
    ("./data/pages/prev/v9/", X01, ("prev/v9", "run")),       # 앞의 ./와 끝의 /는 뗀다
    ("../data/pages/v9", X01, ("prev/v9", "moved")),
    ("data/pages", X01, ("prev", "moved")),                    # 바로 아래 문서별 복사본은 prev/로 옮겨졌다
    ("data/pages", "RAW-90", (".", "run")),
    ("data/pages/v2", X01, ("prev/v2", "moved")),             # 줄 번호가 없는 판도 지난 실행이면 그대로 보인다
    (None, X01, (None, "none")),
    ("", X01, (None, "none")),
    ("data/pages/v2", X02, (None, "none")),                   # 그 묶음에 문서가 없다
    ("data/pages/v9", X09, (None, "none")),                   # 평가용은 잠겨 있다
    ("data/pages/없는판", X01, (None, "none")),
    ("data/pagesX/v9", X01, (None, "none")),                  # data/pages 폴더 밖
    ("runs/v9", X01, (None, "none")),
])
def test_resolve_run_set(bsets, pages, recorded, doc_id, expected):
    assert bsets.resolve_run_set(recorded, doc_id, bsets.list_sets(pages)) == expected


def test_resolve_run_set_without_sets(bsets):
    assert bsets.resolve_run_set("data/pages/prev/v9", X01, []) == (None, "none")


# ── 작업 검사 ──────────────────────────────────────────

def outside_support(monkeypatch, on: bool):
    """실행기가 manifest 밖 문서를 받는 경우(phase format40 합친 뒤)와 아닌 경우를 만든다."""
    from msds.extract import section_runner
    if on:
        monkeypatch.setattr(section_runner, "doc_meta_from_pages", lambda *a, **k: None, raising=False)
    else:
        monkeypatch.delattr(section_runner, "doc_meta_from_pages", raising=False)


def test_outside_run_support_follows_runner(bsets, monkeypatch):
    outside_support(monkeypatch, True)
    assert bsets.outside_run_support() is True
    outside_support(monkeypatch, False)
    assert bsets.outside_run_support() is False                # 부를 때마다 다시 본다


@pytest.mark.parametrize("on", [True, False])
def test_job_check(bsets, bt, pages, monkeypatch, on):
    outside_support(monkeypatch, on)
    sets = by_id(bsets.list_sets(pages))
    top, v9, v2 = docs_of(sets["."]), docs_of(sets["prev/v9"]), docs_of(sets["prev/v2"])
    for kind in ("try", "run"):
        assert bsets.job_check(v9[X01], kind) is None
        assert bsets.job_check(top["RAW-91"], kind) == bt.SET_TEXT["unknown_doc"]
        reason = bsets.job_check(v9[X09], kind)
        assert "평가" in reason and "D-43" in reason
        assert bsets.job_check(v2[X01], kind) == bt.SET_TEXT["no_line_numbers_doc"]
    assert bsets.job_check(top["RAW-90"], "try") == bt.SET_TEXT["outside_try"]      # 한 항 시험은 manifest 문서만
    assert bsets.job_check(top["RAW-90"], "run") == (None if on else bt.SET_TEXT["outside_wait"])


def test_job_check_other_purpose(bsets, bt, env):
    rows = ROWS + [{"doc_id": "T21-X05", "purpose": "기타"}]
    page(env / "p" / "T21-X05")
    other = bsets.doc_entry(env / "p" / "T21-X05", rows)
    for kind in ("try", "run"):
        assert bsets.job_check(other, kind) == "개발용 문서만 넣을 수 있습니다"


def test_job_text(bt):
    for key in ("no_line_numbers_doc", "outside_try", "outside_wait"):
        assert bt.SET_TEXT[key].strip(), key
    assert "L001" in bt.SET_TEXT["no_line_numbers_doc"]
    assert "format40" in bt.SET_TEXT["outside_wait"] and "manifest" in bt.SET_TEXT["outside_wait"]
    assert "manifest" in bt.SET_TEXT["outside_try"]


# ── 글 ─────────────────────────────────────────────────

def test_set_text(bt):
    keys = {"eval_locked", "unknown_doc", "empty", "eval_only", "no_line_numbers", "nothing_open"}
    assert keys <= set(bt.SET_TEXT)
    for key, text in bt.SET_TEXT.items():
        assert text.strip() and "합격" not in text, key
    assert "평가" in bt.SET_TEXT["eval_locked"] and "D-43" in bt.SET_TEXT["eval_locked"]
    assert "L001" in bt.SET_TEXT["no_line_numbers"]
    assert "data/pages" in bt.set_label(".")
    assert bt.set_label("prev/version9") == "prev/version9"
    moved = bt.SET_TEXT["run_moved"].format(recorded="data/pages/version9", id="prev/version9")
    assert "data/pages/version9" in moved and "prev/version9" in moved and "prev/" in moved
    missing = bt.SET_TEXT["run_missing"].format(recorded="기록 없음", name="prev/version9")
    assert "기록 없음" in missing and "prev/version9" in missing and "줄 번호" in missing


# ── 앱 ─────────────────────────────────────────────────

def make_ctx(app, env, **kw):
    return app.AppContext(runs_dir=env / "runs", gold_dir=env / "gold", pages_dir=kw.pop("pages_dir", env / "pages"),
                          static_dir=app.STATIC, cache_dir=None, gaps_file=env / "silver_gaps.yaml", **kw)


def test_route_sets(app, env, pages):
    ctx = make_ctx(app, env, pages_dir=pages / "prev" / "v9", pages_root=pages)
    code, ctype, body = app.route("GET", "/api/sets", {}, None, ctx)
    data = json.loads(body)
    assert code == 200 and ctype.startswith("application/json")
    assert [s["id"] for s in data["sets"]] == SET_IDS
    assert data["default"] == "prev/v9"
    assert "평가" in docs_of(by_id(data["sets"])["prev/v9"])[X09]["reason"]


def test_route_sets_without_root(app, env):
    ctx = make_ctx(app, env)
    assert ctx.pages_root is None                            # 넘기지 않으면 실제 data/pages를 읽지 않는다
    code, _, body = app.route("GET", "/api/sets", {}, None, ctx)
    assert code == 200 and json.loads(body) == {"sets": [], "default": None}


def test_main_default_pages_dir(app, monkeypatch, env):
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

    def spy(ctx):
        seen["ctx"] = ctx
        return real(ctx)

    monkeypatch.setattr(app, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(app, "make_handler", spy)
    assert app.main(["--runs-dir", str(env / "runs"), "--no-browser"]) == 0
    assert seen["ctx"].pages_dir == app.PAGES / "prev" / "version9"
    assert seen["ctx"].pages_root == app.PAGES
