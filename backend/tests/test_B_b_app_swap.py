"""scripts/b_app_swap.py 시험 (자료 바꾸기: 새 문서 폴더 가져오기, 새 정답 확인).

문서 폴더는 tmp_path에 직접 만든 짧은 가짜 글이다. 정답은 test_B_compare_models의 가짜 MSDS다 (D-43·D-47).
git은 tmp_path 안의 저장소끼리만 주고받는다. 네트워크를 부르지 않는다.
"""
import builtins
import importlib
import io
import json
import os
import shutil
import subprocess
import unicodedata

import pytest

from test_B_b_app_runs import env  # noqa: F401  env는 픽스처
from test_B_compare_models import ROWS, SCRIPTS, X01, X02, X09, make_doc, write_json

NUMBERED = "L001 가짜 제품 이름\nL002 가짜 공급자\n"
PLAIN = "가짜 제품 이름\n가짜 공급자\n"


@pytest.fixture
def swap(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_swap")


@pytest.fixture
def bsets(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_sets")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app")


def page(doc_dir, text=NUMBERED, name="p001.txt"):
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / name).write_text(text, encoding="utf-8")


def outside(root, doc_id, source="가상 신규.pdf", text=NUMBERED):
    """manifest 밖 문서. meta.json의 doc_id가 폴더 이름과 같아야 열린다."""
    page(root / doc_id, text)
    write_json(root / doc_id / "meta.json", {"doc_id": doc_id, "source_file": source})


@pytest.fixture
def lab(env):
    """가짜 data/pages, data/gold와 받은 폴더들. 정답은 X01(개발)과 X09(평가)다."""
    pages_root = env / "data" / "pages"
    pages_root.mkdir(parents=True)
    gold = env / "data" / "gold"
    for doc in (X01, X09):
        write_json(gold / f"{doc}.json", make_doc(doc))
    (gold / f"{X01}.unreviewed.json").write_text("[]", encoding="utf-8")
    return env


def inspect(swap, lab, folder):
    return swap.inspect(str(folder), lab / "data" / "pages", lab / "data" / "gold", ROWS)


def apply(swap, lab, folder):
    return swap.apply(str(folder), lab / "data" / "pages", lab / "data" / "gold", ROWS)


def problem(call):
    with pytest.raises(ValueError) as e:
        call()
    return e.value.kind


def spy_opens(monkeypatch):
    """열린 파일 경로를 모은다. Path.read_text와 read_bytes도 io.open을 거친다."""
    opened = []
    real = io.open

    def spy(file, *a, **k):
        opened.append(str(file))
        return real(file, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    return opened


# ── 받은 폴더 찾기 ───────────────────────────────────────

def test_candidates_lists_only_doc_folders_newest_first(swap, lab):
    downloads = lab / "downloads"
    outside(downloads / "version18", "RAW-90")
    outside(downloads / "version18", "RAW-91")
    outside(downloads / "version17", "RAW-90")
    (downloads / "사진모음").mkdir()
    page(downloads / "사진모음" / "휴가", "그림 설명", "memo.txt")      # p001.txt 없는 폴더는 문서가 아니다
    (downloads / ".숨김").mkdir()
    outside(downloads / ".숨김", "RAW-92")
    (downloads / "version18.zip").write_bytes(b"zip")
    os.utime(downloads / "version17", (1_000_000, 1_000_000))
    os.utime(downloads / "version18", (2_000_000, 2_000_000))
    outside(lab / "data" / "pages" / "version17", "RAW-90")

    found = swap.candidates(downloads, lab / "data" / "pages")

    assert found["error"] is None
    assert [c["name"] for c in found["items"]] == ["version18", "version17"]
    assert found["items"][0]["docs"] == 2 and found["items"][0]["in_app"] is False
    assert found["items"][1]["docs"] == 1 and found["items"][1]["in_app"] is True
    assert found["items"][0]["path"] == str(downloads / "version18")
    assert found["items"][0]["modified_at"]


def test_candidates_finds_set_kept_under_prev_as_in_app(swap, lab):
    outside(lab / "downloads" / "version9", "RAW-90")
    outside(lab / "data" / "pages" / "prev" / "version9", "RAW-90")
    found = swap.candidates(lab / "downloads", lab / "data" / "pages")
    assert found["items"][0]["in_app"] is True


def test_candidates_shows_name_in_composed_form(swap, lab):
    """맥의 파일 이름은 자모가 나뉘어 있을 수 있다. 화면과 비교에는 합친 글자를 쓴다."""
    name = "version17_신규40"
    folder = lab / "downloads" / unicodedata.normalize("NFD", name)
    outside(folder, "RAW-90")
    found = swap.candidates(lab / "downloads", lab / "data" / "pages")
    assert found["items"][0]["name"] == name


def test_candidates_reports_unreadable_downloads_without_failing(swap, lab):
    found = swap.candidates(lab / "없는 폴더", lab / "data" / "pages")
    assert found == {"folder": str(lab / "없는 폴더"), "items": [], "error": "unreadable"}


# ── 검사 ────────────────────────────────────────────────

def test_inspect_folder_without_matching_answers_is_format_only(swap, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    outside(folder, "RAW-91")
    info = inspect(swap, lab, folder)
    assert info["verdict"] == "format_only"
    assert info["name"] == "version18" and info["docs_total"] == 2
    assert info["score_docs"] == 0 and info["gold_docs"] == 1
    assert info["batch_docs"] == 2                         # 양식 시험은 manifest 밖 문서도 된다
    assert info["try_docs"] == 0                           # 한 항목 시험은 번호 목록의 개발 문서만 된다
    assert info["no_line_numbers"] == 0
    assert info["locked"] == {"eval": 0, "unknown": 0, "same_as": {}}
    assert info["existing"] == {"state": "new", "set_id": None}
    assert info["target"] == "data/pages/version18"


def test_inspect_folder_with_answers_can_score_and_never_counts_eval_answers(swap, lab):
    folder = lab / "downloads" / "version17"
    for doc in (X01, X02, X09):
        page(folder / doc)
    info = inspect(swap, lab, folder)
    assert info["verdict"] == "score"
    assert info["score_docs"] == 1                         # X09는 정답이 있어도 평가 문서라 세지 않는다
    assert info["batch_docs"] == 2 and info["try_docs"] == 2
    assert info["locked"]["eval"] == 1


def test_inspect_does_not_open_eval_or_same_source_pages(swap, lab, monkeypatch):
    folder = lab / "downloads" / "version17"
    page(folder / X01)
    page(folder / X09)
    outside(folder, "RAW-50", source="가상 C.pdf")          # X09와 원본이 같다
    opened = spy_opens(monkeypatch)
    inspect(swap, lab, folder)
    assert not [p for p in opened if f"/{X09}/" in p or p.endswith(f"{X09}.json")]
    assert not [p for p in opened if "/RAW-50/" in p and not p.endswith("meta.json")]
    assert [p for p in opened if p.endswith(f"/{X01}/p001.txt")]


@pytest.mark.parametrize("source", ["가상 C.pdf", unicodedata.normalize("NFD", "가상 C.pdf")])
def test_inspect_locks_doc_with_same_source_as_eval_and_names_it(swap, lab, source):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    outside(folder, "RAW-50", source=source)
    info = inspect(swap, lab, folder)
    assert info["docs_total"] == 2 and info["batch_docs"] == 1
    assert info["locked"] == {"eval": 1, "unknown": 0, "same_as": {"RAW-50": X09}}


def test_inspect_counts_unknown_and_missing_line_numbers(swap, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    outside(folder, "RAW-91", text=PLAIN)
    page(folder / "RAW-92")                                # meta.json 없음 → 용도를 모름
    info = inspect(swap, lab, folder)
    assert info["no_line_numbers"] == 1 and info["batch_docs"] == 1
    assert info["locked"]["unknown"] == 1


def test_inspect_folder_with_nothing_to_run_is_unusable(swap, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90", text=PLAIN)
    assert inspect(swap, lab, folder)["verdict"] == "unusable"


@pytest.mark.parametrize("make,kind", [
    (lambda root: "상대/경로", "swap_no_path"),
    (lambda root: str(root / "없는 폴더"), "swap_no_path"),
    (lambda root: "", "swap_no_path"),
])
def test_inspect_rejects_bad_paths(swap, lab, make, kind):
    assert problem(lambda: inspect(swap, lab, make(lab))) == kind


def test_inspect_rejects_doc_folder_empty_folder_and_reserved_names(swap, lab):
    downloads = lab / "downloads"
    outside(downloads / "version18", "RAW-90")
    assert problem(lambda: inspect(swap, lab, downloads / "version18" / "RAW-90")) == "swap_doc_folder"
    (downloads / "비어 있음").mkdir()
    assert problem(lambda: inspect(swap, lab, downloads / "비어 있음")) == "swap_no_docs"
    outside(downloads / "prev", "RAW-90")
    assert problem(lambda: inspect(swap, lab, downloads / "prev")) == "swap_bad_name"
    outside(downloads / "이름;나쁨", "RAW-90")
    assert problem(lambda: inspect(swap, lab, downloads / "이름;나쁨")) == "swap_bad_name"


def test_inspect_points_to_best_folder_when_no_answers_match(swap, lab):
    pages_root = lab / "data" / "pages"
    page(pages_root / "prev" / "version9" / X01)
    page(pages_root / "version17" / X01)
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    assert inspect(swap, lab, folder)["score_alternative"] == {"id": "version17", "docs": 1}


def test_inspect_has_no_alternative_when_folder_can_score(swap, lab):
    page(lab / "data" / "pages" / "version17" / X01)
    folder = lab / "downloads" / "version18"
    page(folder / X01)
    assert inspect(swap, lab, folder)["score_alternative"] is None


# ── 앱에 이미 있는 폴더 ──────────────────────────────────

def test_existing_identical_folder_is_same(swap, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    shutil.copytree(folder, lab / "data" / "pages" / "version18")
    assert inspect(swap, lab, folder)["existing"] == {"state": "same", "set_id": "version18"}


def test_existing_identical_folder_under_prev_keeps_its_id(swap, lab):
    folder = lab / "downloads" / "version9"
    outside(folder, "RAW-90")
    shutil.copytree(folder, lab / "data" / "pages" / "prev" / "version9")
    assert inspect(swap, lab, folder)["existing"] == {"state": "same", "set_id": "prev/version9"}


@pytest.mark.parametrize("change", ["text", "extra_file"])
def test_existing_folder_with_other_contents_is_different(swap, lab, change):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90", text="L001 가\n")
    target = lab / "data" / "pages" / "version18"
    shutil.copytree(folder, target)
    if change == "text":
        (target / "RAW-90" / "p001.txt").write_text("L001 나\n", encoding="utf-8")   # 길이가 같아도 다르다
    else:
        page(target / "RAW-90", "L001 다\n", "p002.txt")
    assert inspect(swap, lab, folder)["existing"] == {"state": "different", "set_id": "version18"}


def test_comparing_existing_folder_ignores_finder_files(swap, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    shutil.copytree(folder, lab / "data" / "pages" / "version18")
    (folder / ".DS_Store").write_bytes(b"x")
    assert inspect(swap, lab, folder)["existing"]["state"] == "same"


def test_comparing_existing_folder_does_not_open_eval_pages(swap, lab, monkeypatch):
    folder = lab / "downloads" / "version17"
    page(folder / X01)
    page(folder / X09)
    shutil.copytree(folder, lab / "data" / "pages" / "version17")
    opened = spy_opens(monkeypatch)
    assert inspect(swap, lab, folder)["existing"]["state"] == "same"
    assert not [p for p in opened if f"/{X09}/" in p]


def test_folder_inside_pages_root_is_already_in_app(swap, lab):
    folder = lab / "data" / "pages" / "prev" / "version9"
    outside(folder, "RAW-90")
    assert inspect(swap, lab, folder)["existing"] == {"state": "same", "set_id": "prev/version9"}


def test_empty_placeholder_folder_counts_as_new(swap, lab):
    (lab / "data" / "pages" / "version18").mkdir()
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    assert inspect(swap, lab, folder)["existing"] == {"state": "new", "set_id": None}


# ── 적용 ────────────────────────────────────────────────

def test_apply_copies_folder_and_lists_it_as_a_set(swap, bsets, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    page(folder / "RAW-90" / "tables", "| 표 |", "t001.md")
    (folder / "RAW-90" / "p001.png").write_bytes(b"png")
    (folder / "__MACOSX").mkdir()
    (folder / ".DS_Store").write_bytes(b"x")

    result = apply(swap, lab, folder)

    target = lab / "data" / "pages" / "version18"
    assert result == {"set_id": "version18", "copied": True}
    assert (target / "RAW-90" / "p001.txt").read_text(encoding="utf-8") == NUMBERED
    assert (target / "RAW-90" / "p001.png").read_bytes() == b"png"
    assert (target / "RAW-90" / "tables" / "t001.md").is_file()
    assert not (target / "__MACOSX").exists() and not (target / ".DS_Store").exists()
    assert (folder / "RAW-90" / "p001.txt").is_file()      # 받은 폴더는 그대로 둔다
    assert [p.name for p in (lab / "data" / "pages").iterdir()] == ["version18"]   # 임시 폴더가 남지 않는다
    assert bsets.find_set(bsets.list_sets(lab / "data" / "pages", ROWS), "version18")["usable"] is True


def test_apply_copies_locked_docs_without_changing_them(swap, lab):
    folder = lab / "downloads" / "version17"
    page(folder / X01)
    page(folder / X09)
    apply(swap, lab, folder)
    assert (lab / "data" / "pages" / "version17" / X09 / "p001.txt").read_text(encoding="utf-8") == NUMBERED


def test_apply_stores_composed_name(swap, lab):
    name = "version17_신규40"
    folder = lab / "downloads" / unicodedata.normalize("NFD", name)
    outside(folder, "RAW-90")
    assert apply(swap, lab, folder)["set_id"] == name


def test_apply_same_folder_does_not_copy(swap, lab):
    folder = lab / "downloads" / "version9"
    outside(folder, "RAW-90")
    target = lab / "data" / "pages" / "prev" / "version9"
    shutil.copytree(folder, target)
    os.utime(target, (1_000_000, 1_000_000))
    assert apply(swap, lab, folder) == {"set_id": "prev/version9", "copied": False}
    assert target.stat().st_mtime == 1_000_000
    assert not (lab / "data" / "pages" / "version9").exists()


def test_apply_refuses_to_overwrite_different_folder(swap, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    target = lab / "data" / "pages" / "version18"
    outside(target, "RAW-91")
    assert problem(lambda: apply(swap, lab, folder)) == "swap_conflict"
    assert [p.name for p in target.iterdir()] == ["RAW-91"]


def test_apply_refuses_folder_with_nothing_to_run(swap, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90", text=PLAIN)
    assert problem(lambda: apply(swap, lab, folder)) == "swap_unusable"
    assert not (lab / "data" / "pages" / "version18").exists()


def test_apply_fills_empty_placeholder_folder(swap, lab):
    target = lab / "data" / "pages" / "version18"
    target.mkdir()
    (target / ".DS_Store").write_bytes(b"x")
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")
    assert apply(swap, lab, folder)["copied"] is True
    assert (target / "RAW-90" / "p001.txt").is_file()


def test_apply_failure_leaves_nothing_behind(swap, lab, monkeypatch):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")

    def broken(src, dst, **k):                             # 일부만 복사한 뒤 실패한다
        page(dst / "RAW-90")
        raise OSError("디스크가 가득 찼습니다")

    monkeypatch.setattr(shutil, "copytree", broken)
    assert problem(lambda: apply(swap, lab, folder)) == "swap_copy_failed"
    assert list((lab / "data" / "pages").iterdir()) == []


def test_folder_being_copied_is_not_listed_as_a_set(bsets, lab):
    page(lab / "data" / "pages" / ".version18.copying" / "RAW-90")
    assert not [s["id"] for s in bsets.list_sets(lab / "data" / "pages", ROWS) if "copying" in s["id"] or s["docs"]]


# ── 정답(골드) ───────────────────────────────────────────

def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=가짜", "-c", "user.email=fake@example.invalid", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(env, tmp_path):
    """정답 담당이 올리는 저장소(other), 내 저장소(work). 둘 다 tmp_path 안의 빈 저장소(remote.git)와 주고받는다."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(tmp_path, "clone", str(remote), "work")
    work = tmp_path / "work"
    git(work, "checkout", "-b", "main")
    for doc in (X01, X09):
        write_json(work / "data" / "gold" / f"{doc}.json", make_doc(doc))
    git(work, "add", ".")
    git(work, "commit", "-m", "첫 정답")
    git(work, "push", "-u", "origin", "main")
    git(tmp_path, "clone", str(remote), "other")
    return work, tmp_path / "other"


def push_gold_change(other, *docs, extra=()):
    for doc in docs:
        write_json(other / "data" / "gold" / f"{doc}.json", {**make_doc(doc), "고침": True})
    for name in extra:
        write_json(other / "data" / "gold" / name, [])
    git(other, "add", ".")
    git(other, "commit", "-m", "정답 고침")
    git(other, "push")


def gold(swap, work, **k):
    return swap.gold_status(work / "data" / "gold", work, ROWS, **k)


def test_gold_counts_docs_without_opening_answers(swap, repos, monkeypatch):
    work, _ = repos
    (work / "data" / "gold" / f"{X01}.unreviewed.json").write_text("[]", encoding="utf-8")
    opened = spy_opens(monkeypatch)
    info = gold(swap, work)
    assert info["path"] == "data/gold"
    assert info["docs"] == 1 and info["eval_docs"] == 1
    assert not [p for p in opened if "/data/gold/" in p]


def test_gold_reports_last_commit_that_touched_it(swap, repos):
    work, _ = repos
    sha = git(work, "log", "-1", "--format=%h", "--", "data/gold")
    (work / "기타.txt").write_text("x", encoding="utf-8")
    git(work, "add", ".")
    git(work, "commit", "-m", "정답과 상관없는 커밋")
    info = gold(swap, work)
    assert info["commit"]["sha"] == sha
    assert info["commit"]["at"].startswith("20")


def test_gold_without_fetch_does_not_ask_remote(swap, repos):
    work, other = repos
    push_gold_change(other, X01)
    info = gold(swap, work)
    assert info["fetched"] is None
    assert info["behind"] == {"dev": [], "eval": 0}


def test_gold_fetch_reports_new_answers_by_doc(swap, repos):
    work, other = repos
    push_gold_change(other, X01, X09, extra=[f"{X01}.unreviewed.json"])
    info = gold(swap, work, fetch=True)
    assert info["fetched"] is True
    assert info["behind"] == {"dev": [X01], "eval": 1}     # 평가 문서는 건수만 준다
    assert info["pull"] == f"git -C {work} pull"
    assert info["branch"] == "main"


def test_gold_fetch_ignores_other_files_on_remote(swap, repos):
    work, other = repos
    (other / "다른파일.txt").write_text("x", encoding="utf-8")
    git(other, "add", ".")
    git(other, "commit", "-m", "정답과 상관없는 커밋")
    git(other, "push")
    assert gold(swap, work, fetch=True)["behind"] == {"dev": [], "eval": 0}


def test_gold_fetch_failure_keeps_local_facts(swap, repos, tmp_path):
    work, _ = repos
    git(work, "remote", "set-url", "origin", str(tmp_path / "없는 저장소.git"))
    info = gold(swap, work, fetch=True)
    assert info["fetched"] is False
    assert info["docs"] == 1 and info["commit"] is not None


def test_gold_on_side_branch_shows_merge_command(swap, repos):
    work, other = repos
    git(work, "checkout", "-b", "b/옆가지")
    push_gold_change(other, X01)
    info = gold(swap, work, fetch=True)
    assert info["branch"] == "b/옆가지"
    assert info["pull"] == f"git -C {work} merge origin/main"
    assert info["behind"]["dev"] == [X01]


def test_gold_reports_changes_since_last_seen_commit(swap, repos):
    work, other = repos
    seen = gold(swap, work)["commit"]["sha"]
    assert gold(swap, work, since=seen)["changed"] == {"dev": [], "eval": 0}
    push_gold_change(other, X01, X09)
    git(work, "pull")
    info = gold(swap, work, since=seen)
    assert info["commit"]["sha"] != seen
    assert info["changed"] == {"dev": [X01], "eval": 1}


@pytest.mark.parametrize("since", ["--help", "HEAD", "0000000", "../x", ""])
def test_gold_ignores_bad_or_unknown_since(swap, repos, since):
    work, _ = repos
    assert gold(swap, work, since=since)["changed"] is None


def test_gold_outside_git_repo_still_counts(swap, env, tmp_path):
    for doc in (X01, X09):
        write_json(tmp_path / "plain" / "data" / "gold" / f"{doc}.json", make_doc(doc))
    work = tmp_path / "plain"
    info = gold(swap, work, fetch=True)
    assert info["docs"] == 1 and info["commit"] is None and info["fetched"] is False
    assert info["behind"] == {"dev": [], "eval": 0}


def test_gold_missing_folder_is_empty(swap, env, tmp_path):
    work = tmp_path / "plain"
    work.mkdir()
    info = gold(swap, work)
    assert info["docs"] == 0 and info["eval_docs"] == 0


# ── 주소 ────────────────────────────────────────────────

@pytest.fixture
def ctx(app, lab):
    return app.AppContext(runs_dir=lab / "runs", gold_dir=lab / "gold", pages_dir=lab / "pages", static_dir=app.STATIC,
                          cache_dir=None, gaps_file=lab / "silver_gaps.yaml", pages_root=lab / "data" / "pages",
                          data_root=lab / "data", repo_root=lab, downloads_dir=lab / "downloads")


def call(app, ctx, method, path, body=None, query=None):
    raw = json.dumps(body).encode() if body is not None else None
    code, _, payload = app.route(method, path, query or {}, raw, ctx)
    return code, json.loads(payload)


def test_routes_find_check_and_apply_then_sets_list_the_folder(app, ctx, lab):
    folder = lab / "downloads" / "version18"
    outside(folder, "RAW-90")

    code, found = call(app, ctx, "GET", "/api/swap/candidates")
    assert code == 200 and [c["name"] for c in found["items"]] == ["version18"]

    code, info = call(app, ctx, "POST", "/api/swap/check", {"path": str(folder)})
    assert code == 200 and info["verdict"] == "format_only"
    assert not (lab / "data" / "pages" / "version18").exists()   # 검사만으로는 옮기지 않는다

    code, done = call(app, ctx, "POST", "/api/swap/apply", {"path": str(folder)})
    assert code == 200 and done == {"set_id": "version18", "copied": True}

    code, sets = call(app, ctx, "GET", "/api/sets")
    assert code == 200 and "version18" in [s["id"] for s in sets["sets"]]


def test_routes_give_plain_message_and_next_step_on_problem(app, ctx, lab):
    code, body = call(app, ctx, "POST", "/api/swap/check", {"path": "상대/경로"})
    assert code == 400 and body["message"] and body["fix"] and body["error"]
    assert "상대/경로" in body["message"]
    code, body = call(app, ctx, "POST", "/api/swap/apply", {"path": 3})
    assert code == 400 and body["message"]


def test_routes_refuse_non_object_body(app, ctx):
    code, _, _ = app.route("POST", "/api/swap/check", {}, b"[1]", ctx)
    assert code == 400


def test_gold_route_passes_fetch_and_since(app, ctx, monkeypatch):
    seen = {}

    def fake(gold_root, repo_root, rows=None, *, fetch=False, since=None):
        seen.update(gold_root=gold_root, repo_root=repo_root, fetch=fetch, since=since)
        return {"docs": 1}

    monkeypatch.setattr(app.bswap, "gold_status", fake)
    code, body = call(app, ctx, "GET", "/api/swap/gold", query={"fetch": ["1"], "since": ["abc1234"]})
    assert code == 200 and body == {"docs": 1}
    assert seen == {"gold_root": ctx.data_root / "gold", "repo_root": ctx.repo_root, "fetch": True, "since": "abc1234"}
    call(app, ctx, "GET", "/api/swap/gold")
    assert seen["fetch"] is False and seen["since"] is None


def test_routes_off_without_pages_root(app, lab):
    ctx = app.AppContext(runs_dir=lab / "runs", gold_dir=lab / "gold", pages_dir=lab / "pages", static_dir=app.STATIC,
                         cache_dir=None, gaps_file=lab / "silver_gaps.yaml")
    assert call(app, ctx, "GET", "/api/swap/candidates")[0] == 503
    assert call(app, ctx, "GET", "/api/swap/gold")[0] == 503
    assert call(app, ctx, "POST", "/api/swap/check", {"path": "/x"})[0] == 503


def test_new_gold_changes_saved_scores(app, lab):
    """새 정답을 받으면 저장된 결과의 점수가 AI 호출 없이 달라진다. 캐시 키에 정답 폴더의 수정 시각이 들어 있다."""
    runs_mod = app.br
    run = lab / "runs" / "20261102_fake"
    write_json(run / "outputs" / f"{X01}.json", make_doc(X01))
    (run / "run_info.yaml").write_text("model_tag: fake\n", encoding="utf-8")
    gold_dir, cache = lab / "data" / "gold", lab / "cache"
    before = runs_mod.summarize_run(run, gold_dir, cache_dir=cache)["weighted"]
    write_json(gold_dir / f"{X01}.json", make_doc(X01, toxicity=True, regulations=True))
    os.utime(gold_dir / f"{X01}.json", (2_000_000_000, 2_000_000_000))
    after = runs_mod.summarize_run(run, gold_dir, cache_dir=cache)["weighted"]
    assert before != after
