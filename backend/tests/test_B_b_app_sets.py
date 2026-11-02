"""scripts/b_app_sets.py 시험 (작업 화면의 문서 묶음 찾기, ADR-028).

쪽 글자 폴더 배치는 tmp_path에 직접 만든 짧은 가짜 글로만 만든다. 정답지는 test_B_compare_models의 가짜 MSDS(make_doc)다. 실제 data/pages/, data/silver/, runs/는 읽지 않는다 (D-43·D-47).
manifest는 test_B_b_app_runs의 env 픽스처로 가짜 ROWS(X01·X02 개발, X09 평가)를 끼운다.
"""
import builtins
import importlib
import io
import json
import os
import shutil
from datetime import datetime

import pytest

from test_B_b_app_text import approved_copy
from test_B_b_app_runs import env  # noqa: F401  env는 픽스처
from test_B_compare_models import ROWS, SCRIPTS, X01, X02, X09, make_doc, write_json

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
    assert x09["reason"] == approved_copy("context.set_reason.eval_locked")


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


@pytest.fixture
def moved_pages(env):
    """10/30 배치 변경 뒤의 가짜 data/pages: 옛 version9가 prev/version9로 옮겨졌다."""
    root = env / "moved_pages"
    for d in (X01, X02):
        page(root / "prev" / "version9" / d)
    return root


def test_run_set_moved_and_run(bsets, bt, moved_pages):
    sets = bsets.list_sets(moved_pages)
    moved = bsets.run_set("data/pages/version9", [X01, X02], sets)
    assert moved == {"id": "prev/version9", "label": bt.set_label("prev/version9"), "source": "moved",
                     "usable": True, "missing_docs": []}
    assert bsets.run_set("data/pages/prev/version9", [X01, X02], sets)["source"] == "run"


def test_run_set_none_mixed_and_missing(bsets, pages):
    sets = bsets.list_sets(pages)
    for recorded in (None, "", "data/pages/없는판"):
        assert bsets.run_set(recorded, [X01], sets) == {"id": None, "label": None, "source": "none", "usable": False,
                                                        "missing_docs": [X01]}, recorded
    assert bsets.run_set("data/pages/prev/v9", [], sets)["source"] == "none"          # 문서가 없는 실행
    mixed = bsets.run_set("data/pages", [X01, "RAW-90"], sets)                         # X01은 prev로 옮겨졌고 RAW-90은 그대로
    assert mixed["id"] is None and mixed["source"] == "mixed" and mixed["missing_docs"] == []
    part = bsets.run_set("data/pages/v2", [X02, X01], sets)                            # prev/v2에는 X01만 있다
    assert part == {"id": "prev/v2", "label": "prev/v2", "source": "moved", "usable": False, "missing_docs": [X02]}
    assert bsets.run_set("data/pages/prev/v9", [X01], [])["source"] == "none"         # 묶음 목록이 없다


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
        assert reason == approved_copy("context.set_reason.eval_locked")
        assert bsets.job_check(v2[X01], kind) == bt.SET_TEXT["no_line_numbers_doc"]
    assert bsets.job_check(top["RAW-90"], "try") == bt.SET_TEXT["outside_try"]      # 한 항 시험은 manifest 문서만
    assert bsets.job_check(top["RAW-90"], "run") == (None if on else bt.SET_TEXT["outside_wait"])


def test_job_check_other_purpose(bsets, bt, env):
    rows = ROWS + [{"doc_id": "T21-X05", "purpose": "기타"}]
    page(env / "p" / "T21-X05")
    other = bsets.doc_entry(env / "p" / "T21-X05", rows)
    for kind in ("try", "run"):
        assert bsets.job_check(other, kind) == approved_copy("context.set_reason.dev_only")


def test_job_text(bt):
    for key in ("no_line_numbers_doc", "outside_try", "outside_wait"):
        assert bt.SET_TEXT[key].strip(), key
    for key in ("no_line_numbers_doc", "outside_wait", "outside_try"):
        assert bt.SET_TEXT[key] == approved_copy(f"context.set_reason.{key}")


# ── 글 ─────────────────────────────────────────────────

def test_set_text(bt):
    keys = {"eval_locked", "unknown_doc", "empty", "eval_only", "no_line_numbers", "nothing_open"}
    assert keys <= set(bt.SET_TEXT)
    for key, text in bt.SET_TEXT.items():
        assert text.strip() and "합격" not in text, key
    assert bt.SET_TEXT["eval_locked"] == approved_copy("context.set_reason.eval_locked")
    assert bt.SET_TEXT["no_line_numbers"] == approved_copy("context.set_reason.no_line_numbers")
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


def test_main_default_pages_dir(app, monkeypatch, env, tmp_path):
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

    def spy(ctx):
        seen["ctx"] = ctx
        return real(ctx)

    monkeypatch.setattr(app, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(app, "make_handler", spy)
    assert app.main(["--runs-dir", str(env / "runs"), "--no-browser"]) == 0
    assert seen["ctx"].pages_dir == app.PAGES / "prev" / "version9"
    assert seen["ctx"].pages_root == app.PAGES


# ── 정답지 ─────────────────────────────────────────────

KEY_IDS = ["gold/a3", "gold/bad", "gold/evalonly", "gold/layout", "silver/claude", "silver/gpt"]


@pytest.fixture
def answer_keys(env):
    """가짜 data/ 아래 정답지 배치. 실제 data/silver/gpt처럼 빈 폴더에도 .gitkeep이 있다."""
    data = env / "data"
    claude = data / "silver" / "claude"
    write_json(claude / f"{X01}.json", make_doc(X01))
    write_json(claude / f"{X01}.review.json", {"doc_id": X01, "notes": ["가짜 검토 메모"]})
    write_json(claude / f"{X09}.json", make_doc(X09))                     # 평가용 정답. 열지 않고 이름만 센다
    (data / "silver" / "gpt").mkdir(parents=True)
    (data / "silver" / "gpt" / ".gitkeep").write_text("", encoding="utf-8")
    write_json(data / "gold" / "layout" / "table_goldset_data.json", {"tables": []})   # 표 배치 정답(TO21 답 아님)
    write_json(data / "gold" / "bad" / f"{X01}.json", {"rows": []})
    write_json(data / "gold" / "a3" / f"{X02}.json", make_doc(X02))
    write_json(data / "gold" / "evalonly" / f"{X09}.json", make_doc(X09))
    return data


def test_list_keys_ids_and_reasons(bsets, bt, answer_keys):
    keys = bsets.list_keys(answer_keys)
    assert [k["id"] for k in keys] == KEY_IDS
    reasons = [None, "key_not_to21", "key_eval_only", "key_no_doc_files", None, "key_empty"]
    for k, reason in zip(keys, reasons):
        assert k["reason"] == (bt.KEY_TEXT[reason] if reason else None), k["id"]
        assert k["usable"] is (reason is None), k["id"]
        assert k["label"] == bt.key_label(k["id"])
        assert k["kind"] == k["id"].split("/")[0]
        assert k["path"] == f"data/{k['id']}"


def test_list_keys_counts_without_review_files(bsets, answer_keys):
    keys = {k["id"]: k for k in bsets.list_keys(answer_keys)}
    claude = keys["silver/claude"]
    assert claude["docs"] == [X01]                                         # .review.json과 평가용은 빠진다
    assert claude["counts"] == {"docs": 1, "eval_locked": 1, "outside": 0}
    assert keys["gold/a3"]["docs"] == [X02]
    assert keys["gold/evalonly"]["docs"] == [] and keys["gold/evalonly"]["counts"]["eval_locked"] == 1


def test_list_keys_counts_outside_docs(bsets, answer_keys):
    write_json(answer_keys / "gold" / "a3" / "RAW-90.json", make_doc("RAW-90"))   # manifest 밖 문서
    a3 = {k["id"]: k for k in bsets.list_keys(answer_keys)}["gold/a3"]
    assert a3["docs"] == ["RAW-90", X02]
    assert a3["counts"] == {"docs": 2, "eval_locked": 0, "outside": 1}


def test_list_keys_does_not_open_eval_answers(bsets, bt, answer_keys):
    locked = [answer_keys / "silver" / "claude" / f"{X09}.json", answer_keys / "gold" / "evalonly" / f"{X09}.json"]
    for f in locked:
        f.chmod(0o000)
    try:
        keys = {k["id"]: k for k in bsets.list_keys(answer_keys)}
    finally:
        for f in locked:
            f.chmod(0o644)
    assert keys["gold/evalonly"]["reason"] == bt.KEY_TEXT["key_eval_only"]
    assert keys["silver/claude"]["counts"]["eval_locked"] == 1


def copy_key(data, src_id, dst_id, docs):
    """정답지 폴더의 문서 파일을 바이트 그대로 다른 정답지 폴더로 옮겨 적는다."""
    dst = data / dst_id
    dst.mkdir(parents=True)
    for d in docs:
        shutil.copyfile(data / src_id / f"{d}.json", dst / f"{d}.json")


def keys_by_id(bsets, data):
    return {k["id"]: k for k in bsets.list_keys(data, ROWS)}


def test_key_fingerprint_follows_content(bsets, answer_keys):
    copy_key(answer_keys, "silver/claude", "gold/same", [X01])       # 같은 X01 바이트. .review.json·평가용은 지문 밖
    keys = keys_by_id(bsets, answer_keys)
    fp = keys["silver/claude"]["fingerprint"]
    assert isinstance(fp, str) and len(fp) == 16 and int(fp, 16) >= 0
    assert keys["gold/same"]["fingerprint"] == fp
    assert keys["gold/a3"]["fingerprint"] not in (None, fp)
    f = answer_keys / "gold" / "same" / f"{X01}.json"
    f.write_bytes(f.read_bytes().replace(b"}", b" }", 1))              # 한 글자 바꾸기
    assert keys_by_id(bsets, answer_keys)["gold/same"]["fingerprint"] != fp


def test_key_fingerprint_includes_doc_names(bsets, answer_keys):
    src = answer_keys / "silver" / "claude" / f"{X01}.json"
    (answer_keys / "gold" / "renamed").mkdir()
    shutil.copyfile(src, answer_keys / "gold" / "renamed" / f"{X02}.json")          # 같은 바이트, 다른 문서
    keys = keys_by_id(bsets, answer_keys)
    assert keys["gold/renamed"]["fingerprint"] != keys["silver/claude"]["fingerprint"]


def test_key_updated_at_follows_mtime_only(bsets, answer_keys):
    copy_key(answer_keys, "gold/a3", "gold/two", [X02])
    shutil.copyfile(answer_keys / "silver" / "claude" / f"{X01}.json", answer_keys / "gold" / "two" / f"{X01}.json")
    files = [answer_keys / "gold" / "two" / f"{d}.json" for d in (X01, X02)]
    for f, t in zip(files, (1_790_000_000, 1_790_000_500)):
        os.utime(f, (t, t))
    before = keys_by_id(bsets, answer_keys)["gold/two"]
    assert before["updated_at"] == datetime.fromtimestamp(1_790_000_500).astimezone().isoformat(timespec="seconds")
    os.utime(files[0], (1_790_009_000, 1_790_009_000))                 # 내용은 그대로 두고 수정 시각만 바꾼다
    after = keys_by_id(bsets, answer_keys)["gold/two"]
    assert after["fingerprint"] == before["fingerprint"]
    assert after["updated_at"] == datetime.fromtimestamp(1_790_009_000).astimezone().isoformat(timespec="seconds")
    keys = keys_by_id(bsets, answer_keys)
    for key_id in ("silver/gpt", "gold/evalonly", "gold/layout", "gold/bad"):        # 정답 파일이 없으면 둘 다 None
        assert keys[key_id]["fingerprint"] is None and keys[key_id]["updated_at"] is None, key_id


def test_key_fingerprint_does_not_open_eval_answers(bsets, answer_keys, monkeypatch):
    eval_file = answer_keys / "silver" / "claude" / f"{X09}.json"
    before = keys_by_id(bsets, answer_keys)["silver/claude"]
    eval_file.write_text(json.dumps({**make_doc(X09), "가짜": "바뀐 평가용 정답"}, ensure_ascii=False), encoding="utf-8")
    opened = []
    real = io.open

    def spy(file, *a, **k):
        opened.append(os.fspath(file) if isinstance(file, (str, os.PathLike)) else file)
        return real(file, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(io, "open", spy)
        m.setattr(builtins, "open", spy)
        after = keys_by_id(bsets, answer_keys)["silver/claude"]
    assert after["fingerprint"] == before["fingerprint"]
    assert str(eval_file) not in opened
    assert opened.count(str(answer_keys / "silver" / "claude" / f"{X01}.json")) == 1    # 모양 검사와 지문이 한 번 읽은 바이트를 쓴다


def test_list_keys_missing_folders(bsets, env):
    assert bsets.list_keys(env / "없는_data") == []
    (env / "data" / "silver").mkdir(parents=True)
    assert bsets.list_keys(env / "data") == []


def test_find_key_only_listed_ids(bsets, answer_keys):
    keys = bsets.list_keys(answer_keys)
    assert bsets.find_key(keys, "silver/claude")["id"] == "silver/claude"
    for bad in ("../silver/claude", "silver/claude/..", "/tmp", "없는/정답지", None, 3):
        assert bsets.find_key(keys, bad) is None, bad


def test_key_for_dir(bsets, answer_keys, env):
    keys = bsets.list_keys(answer_keys)
    assert bsets.key_for_dir(keys, answer_keys / "gold" / "a3")["id"] == "gold/a3"
    assert bsets.key_for_dir(keys, answer_keys / "silver" / "gpt" / ".." / "claude")["id"] == "silver/claude"
    other = bsets.key_for_dir(keys, env / "gold")
    assert other["id"] == "gold" and other["label"] == "gold"
    assert other["kind"] == "custom" and other["usable"] is True
    assert bsets.key_for_dir([], answer_keys / "silver" / "claude")["kind"] == "custom"


def test_default_key(bsets, answer_keys, env):
    keys = bsets.list_keys(answer_keys)
    assert bsets.DEFAULT_KEY == "gold"
    assert bsets.default_key(keys, answer_keys / "silver" / "claude") == "silver/claude"
    assert bsets.default_key(keys, answer_keys / "gold" / "a3") == "gold/a3"             # --gold-dir가 정한다
    assert bsets.default_key(keys, answer_keys / "silver" / "gpt") == "gold/a3"           # 기본(gold)이 없으면 첫 번째 쓸 수 있는 정답지
    assert bsets.default_key(keys, env / "gold") == "gold"                                # 목록 밖 폴더는 그 폴더
    assert bsets.default_key([], env / "gold") == "gold"


def test_gold_folder_itself_is_a_key(bsets, bt, answer_keys):
    """A가 골드를 data/gold/<문서>.json에 바로 올린다. 그 폴더 자체가 정답지 하나이고 기본값이다."""
    gold_dir = answer_keys / "gold"
    write_json(gold_dir / f"{X01}.json", make_doc(X01))
    write_json(gold_dir / f"{X09}.json", make_doc(X09))                   # 평가용 정답. 열지 않고 이름만 센다
    (gold_dir / f"{X01}.unreviewed.json").write_text("[]", encoding="utf-8")   # 검수 기록은 정답 파일이 아니다
    keys = bsets.list_keys(answer_keys)
    assert [k["id"] for k in keys] == ["gold", *KEY_IDS]
    gold = keys[0]
    assert gold["usable"] is True and gold["reason"] is None and gold["kind"] == "gold"
    assert gold["docs"] == [X01] and gold["counts"] == {"docs": 1, "eval_locked": 1, "outside": 0}
    assert gold["path"] == "data/gold" and gold["label"] == "사람이 확인한 정답" == bt.key_label("gold")
    assert gold["fingerprint"]
    assert bsets.find_key(keys, "gold") is gold
    assert bsets.key_dir(answer_keys, "gold") == gold_dir
    assert bsets.key_for_dir(keys, gold_dir)["id"] == "gold"
    assert bsets.default_key(keys, gold_dir) == "gold"
    assert bsets.default_key(keys, answer_keys / "silver" / "gpt") == "gold"   # 켤 때 폴더를 못 쓰면 기본 정답지


def test_gold_folder_without_doc_files_is_not_a_key(bsets, answer_keys):
    """layout 같은 하위 폴더만 있으면 data/gold 자체는 목록에 없다."""
    assert "gold" not in [k["id"] for k in bsets.list_keys(answer_keys)]


def test_same_source_as_eval_doc_is_locked(bsets, bt, env, monkeypatch):
    """manifest 밖 번호라도 원본 PDF가 평가 문서와 같으면 평가 문서다. 예: RAW-50은 T21-050이다 (D-43)."""
    import unicodedata
    root = env / "data" / "pages"
    write_json(root / "RAW-90" / "meta.json", {"doc_id": "RAW-90", "source_file": "가상 C.pdf"})
    write_json(root / "RAW-91" / "meta.json", {"doc_id": "RAW-91", "source_file": unicodedata.normalize("NFD", "가상 C.pdf")})
    write_json(root / "RAW-92" / "meta.json", {"doc_id": "RAW-92", "source_file": "다른 원본.pdf"})
    write_json(root / "RAW-93" / "meta.json", {"doc_id": "RAW-93", "source_file": "가상 A.pdf"})   # 개발 문서와 같은 원본은 잠그지 않는다
    for doc in ("RAW-90", "RAW-91", "RAW-92", "RAW-93"):
        page(root / doc)
    entries = {d: bsets.doc_entry(root / d, ROWS) for d in ("RAW-90", "RAW-91", "RAW-92", "RAW-93")}
    for doc in ("RAW-90", "RAW-91"):
        assert entries[doc]["group"] == "eval" and entries[doc]["locked"] is True, doc
        assert entries[doc]["reason"] == bt.SET_TEXT["eval_locked"]
        assert entries[doc]["line_numbers"] is None                       # 잠긴 문서의 쪽 글자는 열지 않는다
        assert bsets.doc_lock(doc, root / doc, ROWS) == bt.SET_TEXT["eval_locked"]
    assert entries["RAW-92"]["group"] == "outside" and entries["RAW-92"]["locked"] is False
    assert entries["RAW-93"]["group"] == "outside" and entries["RAW-93"]["locked"] is False
    assert bsets.doc_lock("RAW-92", root / "RAW-92", ROWS) is None


def test_main_default_answer_key_is_gold(app, monkeypatch, env, tmp_path):
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

    def spy(ctx):
        seen["ctx"] = ctx
        return real(ctx)

    monkeypatch.setattr(app, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(app, "make_handler", spy)
    assert app.main(["--runs-dir", str(env / "runs"), "--no-browser"]) == 0
    assert seen["ctx"].gold_dir == app.GOLD


def test_key_text(bt):
    for key in ("key_empty", "key_no_doc_files", "key_not_to21", "key_eval_only", "unknown_key", "unusable_key"):
        assert bt.KEY_TEXT[key].strip() and "합격" not in bt.KEY_TEXT[key], key
    assert bt.KEY_TEXT["key_eval_only"] == approved_copy("context.key_reason.key_eval_only")
    assert "x/y" in bt.KEY_TEXT["unknown_key"].format(id="x/y")
    assert bt.KEY_TEXT["key_empty"] in bt.KEY_TEXT["unusable_key"].format(reason=bt.KEY_TEXT["key_empty"])


@pytest.mark.parametrize("key_id,label", [
    ("silver/claude", "AI 정답 초안 · Claude"), ("silver/gpt", "AI 정답 초안 · gpt"),
    ("gold/a3", "사람이 확인한 정답 · a3"), ("gold", "사람이 확인한 정답"), ("기타/x", "기타/x")])
def test_key_label(bt, key_id, label):
    assert bt.key_label(key_id) == label
    assert "합격" not in bt.key_label(key_id)
