"""scripts/b_app_jobs.py 시험 (작업 화면 탭 ④ 작업, ADR-025).

진짜 프로세스를 띄우지 않는다: spawner는 바로 끝나는(또는 계속 도는) 가짜 객체를 돌려주고 로그 파일에 미리 정한 글을 쓴다.
ps도 가짜 글을 돌려준다. manifest·실행 폴더·쪽 폴더는 test_B_b_app_runs의 가짜 픽스처(tmp_path)를 쓴다 (D-43).
모델 서버와 네트워크를 부르지 않는다.
"""
import importlib
import json
import shlex
import tempfile
from pathlib import Path

import pytest

from msds.common.paths import ROOT
from test_B_b_app_runs import env, make_run  # noqa: F401  env는 픽스처
from test_B_compare_models import SCRIPTS, X01, X02, X09, make_doc

TAG = "qwen36_35b_runpod"
SECRET_PROMPT = "가상 안내문: 11항 독성 표만 한 줄에 한 행씩 옮긴다. 비밀 표시 ZQX-778"
RESULT = {"plan": {"doc_id": X01, "sections": {"11": {"prompt_hash": "abc123def456"}}},
          "results": {"11": {"ok": True, "raw_text": "가상 답"}}, "score": None}


class FakeProc:
    """Popen 같은 가짜. alive면 poll()이 None. stubborn이면 terminate를 무시하고 kill에만 죽는다."""

    def __init__(self, pid, code=0, alive=False, stubborn=False):
        self.pid, self.code, self.alive, self.stubborn = pid, code, alive, stubborn
        self.terminated = self.killed = False

    def poll(self):
        return None if self.alive else self.code

    def terminate(self):
        self.terminated = True
        if not self.stubborn:
            self.alive, self.code = False, -15

    def kill(self):
        self.killed, self.alive, self.code = True, False, -9


class FakeSpawner:
    def __init__(self, text="", alive=False, stubborn=False, code=0):
        self.text, self.alive, self.stubborn, self.code = text, alive, stubborn, code
        self.calls, self.procs = [], []

    def __call__(self, argv, log_path, cwd):
        system = None
        if "--system-file" in argv:                     # 띄우는 때에 임시 파일이 있어야 한다
            system = Path(argv[argv.index("--system-file") + 1]).read_text(encoding="utf-8")
        self.calls.append({"argv": list(argv), "log": Path(log_path), "cwd": Path(cwd), "system": system})
        Path(log_path).write_text(self.text, encoding="utf-8")
        proc = FakeProc(1000 + len(self.calls), self.code, self.alive, self.stubborn)
        self.procs.append(proc)
        return proc


@pytest.fixture
def bj(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_jobs")


@pytest.fixture
def where(env):
    """가짜 저장소: backend/, data/pages/version9, version13 (개발용 X01·X02의 p001.txt), runs/."""
    (env / "backend").mkdir()
    for v in ("version9", "version13"):
        for d in (X01, X02):
            (env / "data" / "pages" / v / d).mkdir(parents=True)
            (env / "data" / "pages" / v / d / "p001.txt").write_text("L001 가상 글\n", encoding="utf-8")
    return env


def manager(bj, where, spawner=None, *, ps_text="", platform="linux", which=lambda name: None):
    return bj.JobManager(where / "runs" / "manual" / "jobs", Path("/가상/python"), where / "backend",
                         spawner=spawner or FakeSpawner(), runs_dir=where / "runs", platform=platform,
                         which=which, ps=lambda: ps_text, sleep=lambda s: None)


def try_job(m, **kw):
    args = {"model": TAG, "doc": X01, "sections": [11], "all_": False, "pages_dir": "../data/pages/version9",
            "system_text": None, "base_run": None}
    return m.start_try(**{**args, **kw})


def job_of(m, job_id):
    return next(j for j in m.list() if j["id"] == job_id)


def opt(argv, name):
    return argv[argv.index(name) + 1]


# ── 항 시험 ─────────────────────────────────────────────

def test_start_try_argv(bj, where):
    make_run(where / "runs", "20261030_sections_x_dev10_r1", {X01: make_doc(X01)})
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    job = try_job(m, sections=[11, 15], base_run="20261030_sections_x_dev10_r1")
    argv = sp.calls[0]["argv"]
    assert job.kind == "try" and argv[0] == "/가상/python" and argv[1] == "scripts/try_section.py"
    assert "--json" in argv and opt(argv, "--model") == TAG and opt(argv, "--doc") == X01
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--section"] == ["11", "15"]
    assert opt(argv, "--pages-dir") == "../data/pages/version9"
    assert opt(argv, "--base-run") == "20261030_sections_x_dev10_r1"
    assert "--system-file" not in argv and "--all" not in argv and "--allow-eval" not in argv
    assert sp.calls[0]["cwd"] == where / "backend"
    assert sp.calls[0]["log"].parent == where / "runs" / "manual" / "jobs"


def test_start_try_all_and_dry_run(bj, where):
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    try_job(m, sections=None, all_=True, dry_run=True)
    argv = sp.calls[0]["argv"]
    assert "--all" in argv and "--dry-run" in argv and "--section" not in argv


def test_system_text_goes_to_temp_file_outside_repo_and_is_removed(bj, where):
    sp = FakeSpawner(text=json.dumps(RESULT, ensure_ascii=False, indent=1) + "\n")
    m = manager(bj, where, sp)
    job = try_job(m, system_text=SECRET_PROMPT)
    path = Path(opt(sp.calls[0]["argv"], "--system-file"))
    assert sp.calls[0]["system"] == SECRET_PROMPT                         # 띄울 때는 글이 있다
    assert path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert not path.resolve().is_relative_to(ROOT.resolve()) and not path.resolve().is_relative_to(where)
    assert job_of(m, job.id)["status"] == "done"
    assert not path.exists()                                              # 끝나면 지운다


def test_system_text_is_not_written_to_log_or_state(bj, where):
    sp = FakeSpawner(text="가상 로그\n")
    m = manager(bj, where, sp)
    job = try_job(m, system_text=SECRET_PROMPT)
    m.list()
    for f in (where / "runs").rglob("*"):
        if f.is_file():
            assert "ZQX-778" not in f.read_text(encoding="utf-8", errors="ignore"), f
    assert "ZQX-778" not in json.dumps(m.list(), ensure_ascii=False)
    assert job.id in [j["id"] for j in m.list()]


def test_start_try_refuses_eval_and_bad_input(bj, where):
    m = manager(bj, where)
    with pytest.raises(ValueError, match="평가"):
        try_job(m, doc=X09)
    with pytest.raises(ValueError):
        try_job(m, doc="T21-없음")
    with pytest.raises(ValueError):
        try_job(m, model="없는_태그")
    with pytest.raises(ValueError):
        try_job(m, sections=[11, 15], system_text=SECRET_PROMPT)            # 안내문 바꾸기는 항 하나만
    with pytest.raises(ValueError):
        try_job(m, sections=[17])
    with pytest.raises(ValueError):
        try_job(m, sections=[])
    with pytest.raises(ValueError):
        try_job(m, pages_dir="../data/pages/없는폴더")
    with pytest.raises(ValueError):
        try_job(m, base_run="../gold")


# ── 본 실행 ─────────────────────────────────────────────

def run_job(m, **kw):
    args = {"model": TAG, "docs": [X01, X02], "pages_dir": "../data/pages/version9",
            "run_name": "20261030_sections_가상_s7_v9_dev10", "repeat": 2}
    return m.start_run(**{**args, **kw})


def test_start_run_refuses_eval_docs(bj, where):
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    with pytest.raises(ValueError, match="평가"):
        run_job(m, docs=[X01, X09])
    assert sp.calls == []


def test_start_refuses_doc_without_pages_in_folder(bj, where):
    """쪽 폴더에 그 문서의 pNNN.txt가 없으면 띄우지 않는다. 예: 신규 40건 폴더(RAW-01~)에는 개발용 문서가 없다 (10/30)."""
    new40 = where / "data" / "pages" / "version13_신규40" / "RAW-01"
    new40.mkdir(parents=True)
    (new40 / "p001.txt").write_text("L001 가상 글\n", encoding="utf-8")
    (where / "data" / "pages" / "version13" / X02 / "p001.txt").unlink()
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    with pytest.raises(ValueError, match=f"version13_신규40.*{X01}"):
        try_job(m, pages_dir="../data/pages/version13_신규40")
    with pytest.raises(ValueError, match=f"version13.*{X02}"):
        run_job(m, pages_dir="../data/pages/version13")
    with pytest.raises(ValueError, match=X02):
        m.run_summary(model=TAG, docs=None, pages_dir="../data/pages/version13", run_name="요약", repeat=1)
    assert sp.calls == []


def test_start_run_repeat_names_one_job(bj, where):
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    jobs = run_job(m)
    assert len(jobs) == 1 and jobs[0].kind == "run" and len(sp.calls) == 1
    argv = sp.calls[0]["argv"]
    assert argv[:2] == ["bash", "-c"]                                     # darwin이 아니면 caffeinate가 없다
    assert "caffeinate" not in argv
    parts = [shlex.split(p) for p in argv[2].split("; ")]
    assert len(parts) == 2
    assert [opt(p, "--run-name") for p in parts] == ["20261030_sections_가상_s7_v9_dev10_r1",
                                                     "20261030_sections_가상_s7_v9_dev10_r2"]
    for p in parts:
        assert p[:2] == ["/가상/python", "scripts/run_sections.py"] and opt(p, "--model") == TAG
        assert p[p.index("--docs") + 1:p.index("--docs") + 3] == [X01, X02]
        assert opt(p, "--pages-dir") == "../data/pages/version9" and "--allow-eval" not in p


def test_start_run_wraps_caffeinate_on_darwin(bj, where):
    sp = FakeSpawner()
    m = manager(bj, where, sp, platform="darwin", which=lambda name: "/usr/bin/" + name)
    run_job(m)
    assert sp.calls[0]["argv"][:4] == ["caffeinate", "-dimsu", "bash", "-c"]
    sp2 = FakeSpawner()
    run_job(manager(bj, where, sp2, platform="darwin", which=lambda name: None), run_name="다른_이름")
    assert sp2.calls[0]["argv"][:2] == ["bash", "-c"]                      # caffeinate가 없는 Mac


def test_start_run_default_docs_are_dev(bj, where):
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    run_job(m, docs=None, repeat=1)
    p = shlex.split(sp.calls[0]["argv"][2])
    assert p[p.index("--docs") + 1:p.index("--run-name")] == [X01, X02]


def test_start_run_refuses_existing_run_and_bad_names(bj, where):
    make_run(where / "runs", "20261030_sections_가상_s7_v9_dev10_r2", {X01: make_doc(X01)})
    m = manager(bj, where)
    with pytest.raises(ValueError, match="이미"):
        run_job(m)
    for bad in ("../밖", "a b", "", "a;rm"):
        with pytest.raises(ValueError):
            run_job(m, run_name=bad)
    with pytest.raises(ValueError):
        run_job(m, run_name="새_이름", repeat=0)


def test_run_progress_counts_total_lines(bj, where):
    sp = FakeSpawner(alive=True)
    m = manager(bj, where, sp)
    job = run_job(m, run_name="진행", repeat=2)[0]
    r1 = where / "runs" / "진행_r1"
    r1.mkdir()
    (r1 / "timing.jsonl").write_text(
        "".join(json.dumps({"doc_id": d, "stage": s, "seconds": 1}) + "\n"
                for d, s in ((X01, "call"), (X01, "total"), (X02, "call"))), encoding="utf-8")
    j = job_of(m, job.id)
    assert j["status"] == "running"
    assert j["progress"] == [{"name": "진행_r1", "done": 1, "total": 2}, {"name": "진행_r2", "done": 0, "total": 2}]


def test_run_summary(bj, where):
    m = manager(bj, where)
    text = m.run_summary(model=TAG, docs=None, pages_dir="../data/pages/version9", run_name="요약", repeat=2)
    assert "2건 × 2회" in text and TAG in text and "요약_r1" in text and "요약_r2" in text


def test_suggest_run_name(bj):
    from _common import today
    assert bj.suggest_run_name(TAG, "s7", "data/pages/version9") == f"{today()}_sections_{TAG}_s7_v9_dev10"
    assert bj.suggest_run_name(TAG, "s7", "../data/pages/version13", "probe") == f"{today()}_sections_{TAG}_s7_v13_probe"


def test_free_run_name(bj, where):
    runs = where / "runs"
    assert bj.free_run_name(runs, "가상") == "가상"
    make_run(runs, "가상_r1", {X01: make_doc(X01)})
    assert bj.free_run_name(runs, "가상") == "가상_2"


# ── 문서 묶음 (ADR-028) ─────────────────────────────────

RAW = "RAW-90"


@pytest.fixture
def where40(where):
    """where에 신규 문서 RAW-90(data/pages 바로 아래, 가짜 meta.json), 줄 번호 없는 옛 판 prev/v2, 빈 폴더를 더한다."""
    pages = where / "data" / "pages"
    (pages / RAW).mkdir()
    (pages / RAW / "meta.json").write_text(json.dumps(
        {"doc_id": RAW, "source_file": "가짜.pdf", "page_count": 1, "text_layer": "정상", "pages": []},
        ensure_ascii=False), encoding="utf-8")
    (pages / RAW / "p001.txt").write_text("L001 가짜 글\n", encoding="utf-8")
    (pages / "prev" / "v2" / X01).mkdir(parents=True)
    (pages / "prev" / "v2" / X01 / "p001.txt").write_text("가짜 글\n", encoding="utf-8")
    (pages / "version13_신규40").mkdir()
    return where


@pytest.fixture
def bt(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_text")


def outside_support(monkeypatch, on: bool):
    """실행기가 manifest 밖 문서를 받는 경우(phase format40 합친 뒤)와 아닌 경우."""
    from msds.extract import section_runner
    if on:
        monkeypatch.setattr(section_runner, "doc_meta_from_pages", lambda *a, **k: None, raising=False)
    else:
        monkeypatch.delattr(section_runner, "doc_meta_from_pages", raising=False)


def test_run_outside_doc_waits_for_runner(bj, where40, monkeypatch):
    outside_support(monkeypatch, False)
    sp = FakeSpawner()
    m = manager(bj, where40, sp)
    with pytest.raises(ValueError, match="format40"):
        run_job(m, docs=[RAW], pages_dir="../data/pages")
    with pytest.raises(ValueError, match=f"{RAW}.*format40"):
        m.run_summary(model=TAG, docs=[RAW], pages_dir="../data/pages", run_name="신규", repeat=1)
    assert sp.calls == []


def test_run_outside_doc_when_runner_supports(bj, where40, monkeypatch):
    outside_support(monkeypatch, True)
    sp = FakeSpawner()
    m = manager(bj, where40, sp)
    assert "1건 × 1회" in m.run_summary(model=TAG, docs=[RAW], pages_dir="../data/pages", run_name="신규", repeat=1)
    jobs = run_job(m, docs=[RAW], pages_dir="../data/pages", repeat=1)
    assert len(jobs) == 1 and len(sp.calls) == 1
    p = shlex.split(sp.calls[0]["argv"][2])
    assert p[p.index("--docs") + 1:p.index("--run-name")] == [RAW]
    assert opt(p, "--pages-dir") == "../data/pages" and "--allow-eval" not in p


@pytest.mark.parametrize("on", [True, False])
def test_try_outside_doc_is_refused(bj, bt, where40, monkeypatch, on):
    outside_support(monkeypatch, on)
    sp = FakeSpawner()
    m = manager(bj, where40, sp)
    with pytest.raises(ValueError) as e:
        try_job(m, doc=RAW, pages_dir="../data/pages")
    assert bt.SET_TEXT["outside_try"] in str(e.value) and RAW in str(e.value)
    assert sp.calls == []


def test_refuses_set_without_line_numbers(bj, bt, where40):
    sp = FakeSpawner()
    m = manager(bj, where40, sp)
    with pytest.raises(ValueError) as e:
        try_job(m, pages_dir="../data/pages/prev/v2")
    assert "고를 수 없는 묶음" in str(e.value) and bt.SET_TEXT["no_line_numbers"] in str(e.value)
    with pytest.raises(ValueError, match="고를 수 없는 묶음"):
        run_job(m, docs=[X01], pages_dir="../data/pages/prev/v2")
    assert sp.calls == []


def test_refuses_doc_without_line_numbers_in_usable_set(bj, bt, where40):
    (where40 / "data" / "pages" / "version9" / X02 / "p001.txt").write_text("가짜 글\n", encoding="utf-8")
    sp = FakeSpawner()
    m = manager(bj, where40, sp)
    with pytest.raises(ValueError) as e:
        try_job(m, doc=X02)
    assert str(e.value) == f"{X02}: {bt.SET_TEXT['no_line_numbers_doc']}"
    try_job(m, doc=X01)                                                   # 같은 묶음의 다른 문서는 돈다
    assert len(sp.calls) == 1


def test_refuses_folder_that_is_not_a_set(bj, where40):
    """data/pages 밖 폴더는 쪽 글자가 있어도 묶음이 아니라 띄우지 않는다."""
    outside = where40 / "backend" / "다른_쪽" / X01
    outside.mkdir(parents=True)
    (outside / "p001.txt").write_text("L001 가짜 글\n", encoding="utf-8")
    sp = FakeSpawner()
    m = manager(bj, where40, sp)
    with pytest.raises(ValueError, match="고를 수 없는 묶음"):
        try_job(m, pages_dir="다른_쪽")
    assert sp.calls == []


def test_refuses_bad_doc_id_before_paths(bj, where40):
    sp = FakeSpawner()
    m = manager(bj, where40, sp)
    with pytest.raises(ValueError, match="문서 번호"):
        try_job(m, doc="../T21-X01")
    with pytest.raises(ValueError, match="문서 번호"):
        run_job(m, docs=[X01, "../T21-X01"])
    with pytest.raises(ValueError, match="평가"):                           # 폴더에 없어도 평가용은 먼저 거부
        try_job(m, doc=X09, pages_dir="../data/pages")
    assert sp.calls == []


def test_pages_root_default_and_override(bj, where40, tmp_path):
    m = manager(bj, where40)
    assert m.pages_root == where40 / "data" / "pages"
    other = bj.JobManager(where40 / "jobs", Path("/가상/python"), where40 / "backend", spawner=FakeSpawner(),
                          runs_dir=where40 / "runs", pages_root=tmp_path / "없음")
    with pytest.raises(ValueError, match="고를 수 없는 묶음"):              # 묶음을 찾는 곳이 다르면 그 폴더는 묶음이 아니다
        try_job(other)


# ── 비교표 ─────────────────────────────────────────────

def test_start_compare(bj, where):
    for n in ("실행a", "실행b"):
        make_run(where / "runs", n, {X01: make_doc(X01)})
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    job = m.start_compare(title="가상비교", runs=["실행a", "실행b"], labels=["앞", "뒤"])
    argv = sp.calls[0]["argv"]
    assert job.kind == "compare" and argv[1] == "scripts/compare_models.py"
    assert opt(argv, "--title") == "가상비교" and argv[argv.index("--runs") + 1:] == ["앞=실행a", "뒤=실행b"]
    m.start_compare(title="라벨없음", runs=["실행a", "실행b"], labels=None)
    assert sp.calls[1]["argv"][-2:] == ["실행a", "실행b"]


def test_start_compare_refuses_bad_input(bj, where):
    make_run(where / "runs", "실행a", {X01: make_doc(X01)})
    m = manager(bj, where)
    with pytest.raises(ValueError):
        m.start_compare(title="가상", runs=["실행a", "없는실행"], labels=None)
    with pytest.raises(ValueError):
        m.start_compare(title="가상", runs=["실행a"], labels=["하나", "둘"])
    with pytest.raises(ValueError):
        m.start_compare(title="../밖", runs=["실행a"], labels=None)
    with pytest.raises(ValueError):
        m.start_compare(title="가상", runs=[], labels=None)


def test_compare_output_path_when_done(bj, where):
    from _common import today
    make_run(where / "runs", "실행a", {X01: make_doc(X01)})
    m = manager(bj, where)
    job = m.start_compare(title="가상비교", runs=["실행a"], labels=None)
    assert job_of(m, job.id)["output"] is None
    out = where / "runs" / f"{today()}_models_가상비교"
    out.mkdir()
    (out / "compare.md").write_text("# 가상\n", encoding="utf-8")
    assert job_of(m, job.id)["output"] == f"runs/{today()}_models_가상비교/compare.md"


# ── 목록·멈추기·로그 ────────────────────────────────────

def test_list_survives_restart(bj, where):
    m1 = manager(bj, where, FakeSpawner(code=0))
    a = try_job(m1)
    m3 = manager(bj, where, FakeSpawner(code=2))
    b = try_job(m3, sections=[3])
    m2 = manager(bj, where)                                             # 앱을 다시 켠 것
    got = {j["id"]: j for j in m2.list()}
    assert got[a.id]["status"] == "done" and got[b.id]["status"] == "failed"
    assert got[a.id]["kind"] == "try" and got[a.id]["label"] == a.label


def test_list_unknown_after_restart_while_running(bj, where):
    m1 = manager(bj, where, FakeSpawner(alive=True))
    job = try_job(m1)
    assert job_of(m1, job.id)["status"] == "running"
    m2 = manager(bj, where)
    assert job_of(m2, job.id)["status"] == "unknown"                    # 이 앱이 띄운 것이 아니라 상태를 모른다
    assert m2.stop(job.id) is False


def test_stop_terminates(bj, where):
    sp = FakeSpawner(alive=True)
    m = manager(bj, where, sp)
    job = try_job(m, system_text=SECRET_PROMPT)
    path = Path(opt(sp.calls[0]["argv"], "--system-file"))
    assert m.stop(job.id) is True
    assert sp.procs[0].terminated and not sp.procs[0].killed
    assert job_of(m, job.id)["status"] == "stopped" and not path.exists()
    assert m.stop(job.id) is False                                       # 이미 멈춤
    assert manager(bj, where).list()[0]["status"] == "stopped"


def test_stop_kills_if_terminate_is_ignored(bj, where):
    sp = FakeSpawner(alive=True, stubborn=True)
    m = manager(bj, where, sp)
    job = run_job(m)[0]
    assert m.stop(job.id) is True
    assert sp.procs[0].terminated and sp.procs[0].killed


def test_stop_unknown_id(bj, where):
    assert manager(bj, where).stop("없는_작업") is False


def test_tail_returns_last_lines(bj, where):
    m = manager(bj, where, FakeSpawner(text="".join(f"줄 {i}\n" for i in range(300))))
    job = try_job(m)
    assert m.tail(job.id, 5) == "".join(f"줄 {i}\n" for i in range(295, 300))
    assert m.tail(job.id).count("\n") == 200
    with pytest.raises(KeyError):
        m.tail("없는_작업")


def test_result_parses_last_json_block(bj, where):
    older = json.dumps({"plan": {"doc_id": "옛것"}}, indent=1)
    text = "진행 중 경고 한 줄\n" + older + "\n다른 줄\n" + json.dumps(RESULT, ensure_ascii=False, indent=1) + "\n"
    m = manager(bj, where, FakeSpawner(text=text))
    job = try_job(m)
    assert m.result(job.id) == RESULT
    m2 = manager(bj, where, FakeSpawner(text="Traceback (most recent call last):\n  오류\n"))
    assert m2.result(try_job(m2).id) is None


def test_result_only_for_try_jobs(bj, where):
    m = manager(bj, where, FakeSpawner(text=json.dumps(RESULT, indent=1) + "\n"))
    assert m.result(run_job(m)[0].id) is None


# ── 돌고 있는 것 ───────────────────────────────────────

PS = """\
  101   101 /가상/.venv/bin/python scripts/run_sections.py --model qwen3_30b_a3b_rngd --docs T21-X01 --run-name 밖의_실행_r1
  102   102 bash -c /가상/python scripts/run_sections.py --model m --run-name 밖의_실행_r1
  103  1001 /가상/python scripts/try_section.py --model m --doc T21-X01 --json
  104   104 /Library/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python scripts/try_section.py --model qwen36_35b_runpod --doc T21-X02
  105   105 vim scripts/run_sections.py
  106   106 /가상/python scripts/compare_models.py --title 가상
"""


def test_running_includes_mine_and_outside(bj, where):
    sp = FakeSpawner(alive=True)
    m = manager(bj, where, sp, ps_text=PS)
    job = try_job(m)                                                    # 가짜 pid 1001 → 103은 이 앱의 것
    got = m.running()
    mine = [r for r in got if r["mine"]]
    outside = [r for r in got if not r["mine"]]
    assert [r["id"] for r in mine] == [job.id] and mine[0]["kind"] == "try"
    assert [(r["pid"], r["kind"], r["run_name"], r["model"]) for r in outside] == [
        (101, "run", "밖의_실행_r1", "qwen3_30b_a3b_rngd"), (104, "try", None, "qwen36_35b_runpod")]


def test_running_empty_when_nothing(bj, where):
    m = manager(bj, where, FakeSpawner(), ps_text="")
    try_job(m)
    assert m.running() == []


# ── 앱 라우트 ──────────────────────────────────────────

@pytest.fixture
def app(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app")


def ctx_of(app, where, m, **kw):
    return app.AppContext(runs_dir=where / "runs", gold_dir=where / "gold", pages_dir=where / "data/pages/version9",
                          static_dir=app.STATIC, cache_dir=None, gaps_file=where / "silver_gaps.yaml",
                          jobs=m, pages_root=where / "data/pages", **kw)


def call(app, ctx, method, path, body=None, query=None):
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    code, ctype, out = app.route(method, path, query or {}, raw, ctx)
    return code, (json.loads(out) if out and ctype.startswith("application/json") else out)


RUN_BODY = {"model": TAG, "docs": [X01, X02], "pages_dir": "../data/pages/version9", "run_name": "화면실행", "repeat": 2}


def test_route_run_needs_confirm(bj, app, where):
    sp = FakeSpawner()
    ctx = ctx_of(app, where, manager(bj, where, sp))
    code, data = call(app, ctx, "POST", "/api/jobs/run", RUN_BODY)
    assert code == 409 and data["needs_confirm"] is True
    assert "2건 × 2회" in data["summary"] and TAG in data["summary"] and "화면실행" in data["summary"]
    assert sp.calls == []
    code, data = call(app, ctx, "POST", "/api/jobs/run", {**RUN_BODY, "confirm": True})
    assert code == 200 and data["id"] and len(sp.calls) == 1


def test_route_run_refuses_eval_before_confirm(bj, app, where):
    ctx = ctx_of(app, where, manager(bj, where))
    code, data = call(app, ctx, "POST", "/api/jobs/run", {**RUN_BODY, "docs": [X09], "confirm": True})
    assert code == 400 and "평가" in data["error"]


def test_route_try_log_result_stop(bj, app, where):
    sp = FakeSpawner(text="앞 줄\n" + json.dumps(RESULT, ensure_ascii=False, indent=1) + "\n")
    ctx = ctx_of(app, where, manager(bj, where, sp))
    code, data = call(app, ctx, "POST", "/api/jobs/try",
                      {"model": TAG, "doc": X01, "sections": [11], "all": False, "pages_dir": "../data/pages/version9",
                       "system_text": SECRET_PROMPT, "base_run": None, "dry_run": False})
    assert code == 200
    job_id = data["id"]
    code, data = call(app, ctx, "GET", "/api/jobs")
    assert code == 200 and [j["id"] for j in data["jobs"]] == [job_id] and data["running"] == []
    assert "ZQX-778" not in json.dumps(data, ensure_ascii=False)
    code, data = call(app, ctx, "GET", f"/api/jobs/{job_id}/log", query={"lines": ["1"]})
    assert code == 200 and data["text"] == "}\n"
    assert call(app, ctx, "GET", f"/api/jobs/{job_id}/result") == (200, RESULT)
    assert call(app, ctx, "POST", f"/api/jobs/{job_id}/stop", {})[1] == {"stopped": False}
    assert call(app, ctx, "GET", "/api/jobs/없는_작업/log")[0] == 404
    assert call(app, ctx, "GET", "/api/jobs/../x/log")[0] == 404


def test_route_result_204_without_json(bj, app, where):
    ctx = ctx_of(app, where, manager(bj, where, FakeSpawner(text="JSON 없음\n")))
    job_id = call(app, ctx, "POST", "/api/jobs/try", {"model": TAG, "doc": X01, "sections": [11],
                                                     "pages_dir": "../data/pages/version9"})[1]["id"]
    assert call(app, ctx, "GET", f"/api/jobs/{job_id}/result")[0] == 204


def test_route_try_rejects_eval_and_bad_body(bj, app, where):
    ctx = ctx_of(app, where, manager(bj, where))
    code, data = call(app, ctx, "POST", "/api/jobs/try", {"model": TAG, "doc": X09, "sections": [11],
                                                         "pages_dir": "../data/pages/version9"})
    assert code == 400 and "평가" in data["error"]
    code, _, _ = app.route("POST", "/api/jobs/try", {}, b"{not json", ctx)
    assert code == 400
    assert call(app, ctx, "POST", "/api/jobs/try", [1, 2])[0] == 400


def test_route_compare(bj, app, where):
    make_run(where / "runs", "실행a", {X01: make_doc(X01)})
    sp = FakeSpawner()
    ctx = ctx_of(app, where, manager(bj, where, sp))
    code, data = call(app, ctx, "POST", "/api/jobs/compare", {"title": "화면비교", "runs": ["실행a"], "labels": None})
    assert code == 200 and data["id"] and sp.calls[0]["argv"][1] == "scripts/compare_models.py"
    assert call(app, ctx, "POST", "/api/jobs/compare", {"title": "화면비교", "runs": ["없음"]})[0] == 400


def test_route_options(bj, app, where):
    status = [{"tag": TAG, "reachable": True, "match": True, "error": None},
              {"tag": "qwen3_30b_a3b_rngd", "reachable": False, "match": None, "error": "URLError"}]
    ctx = ctx_of(app, where, manager(bj, where), model_status=lambda: status)
    code, data = call(app, ctx, "GET", "/api/options")
    assert code == 200 and data["status_checked"] is True
    models = {m["tag"]: m for m in data["models"]}
    assert models[TAG]["connected"] is True and models["qwen3_30b_a3b_rngd"]["connected"] is False
    assert models["claude"]["connected"] is False                       # 서버 탭이 보지 않는 태그
    assert [d["doc_id"] for d in data["docs"]] == [X01, X02]             # 평가용 X09는 없다
    assert [p["name"] for p in data["pages_dirs"]] == ["version13", "version9"]
    assert data["default_pages_dir"] == "../data/pages/version9"
    names = data["run_names"][TAG]["../data/pages/version9"]
    assert names["dev10"].endswith(f"_sections_{TAG}_{data['prompt_version']}_v9_dev10")
    assert names["probe"].endswith("_v9_probe")


def test_route_options_without_status(bj, app, where):
    ctx = ctx_of(app, where, manager(bj, where))
    data = call(app, ctx, "GET", "/api/options")[1]
    assert data["status_checked"] is False and all(m["connected"] is None for m in data["models"])


@pytest.mark.parametrize("advanced", [None, "0", "1"])
def test_route_options_help_sorting_and_dry_run(bj, app, where, advanced):
    ctx = ctx_of(app, where, manager(bj, where))
    query = {} if advanced is None else {"advanced": [advanced]}
    code, data = call(app, ctx, "GET", "/api/options", query=query)
    assert code == 200
    assert data["field_help"] == app.bt.FIELD_HELP
    assert data["try_stage_help"] == app.bt.TRY_STAGE_HELP
    assert data["try_hint"] == app.bt.try_hint(data["models"], advanced == "1")
    assert data["try_hint"]["dry_run_forced"] is True
    assert all(m["option_label"].endswith("연결 모름") for m in data["models"])
    ctx.model_status = lambda: [{"tag": TAG, "reachable": True, "match": True}]
    data = call(app, ctx, "GET", "/api/options", query=query)[1]
    assert data["models"][0]["tag"] == TAG
    assert data["models"][0]["option_label"].endswith("연결됨")
    assert all(m["option_label"].endswith("연결 안 됨") for m in data["models"][1:])
    assert data["try_hint"]["dry_run_forced"] is False
    assert [d["doc_id"] for d in data["docs"]] == [X01, X02]


def test_route_prompt_text(bj, app, where):
    from msds.extract.section_prompts import build_system
    ctx = ctx_of(app, where, manager(bj, where))
    code, data = call(app, ctx, "GET", "/api/prompt", query={"model": [TAG], "no": ["11"]})
    assert code == 200 and data["rows"] is True and data["text"] == build_system(11, rows=True)
    assert call(app, ctx, "GET", "/api/prompt", query={"model": [TAG], "no": ["17"]})[0] == 400
    assert call(app, ctx, "GET", "/api/prompt", query={"model": ["없는_태그"], "no": ["1"]})[0] == 400
    assert not list((where / "runs").rglob("*.txt"))                    # 안내문을 파일로 남기지 않는다


def test_allowed_post(app):
    assert app.allowed_post("application/json", None, 8765)
    assert app.allowed_post("application/json; charset=utf-8", "http://127.0.0.1:8765", 8765)
    assert app.allowed_post("application/json", "http://localhost:8765", 8765)
    assert not app.allowed_post("text/plain", None, 8765)               # 다른 웹페이지의 폼 보내기
    assert not app.allowed_post("application/json", "http://evil.example", 8765)
    assert not app.allowed_post(None, None, 8765)


# ── 앱 라우트: 문서 묶음 (ADR-028) ─────────────────────

@pytest.mark.parametrize("on", [True, False])
def test_route_options_sets_and_runnable(bj, app, where40, monkeypatch, on):
    outside_support(monkeypatch, on)
    ctx = ctx_of(app, where40, manager(bj, where40))
    code, data = call(app, ctx, "GET", "/api/options")
    assert code == 200
    ids = [p["id"] for p in data["pages_dirs"]]
    assert ids == [".", "version13", "version9"]                          # 빈 폴더·줄 번호 없는 prev/v2는 없다
    assert {p["id"]: p["value"] for p in data["pages_dirs"]}["."] == "../data/pages"
    assert data["default_pages_dir"] == "../data/pages/version9" and data["default_set"] == "version9"
    assert data["outside_run_support"] is on
    sets = {s["id"]: s for s in data["sets"]}
    assert {"version13_신규40", "prev/v2"} <= set(sets) and sets["prev/v2"]["usable"] is False
    raw = {d["doc_id"]: d for d in sets["."]["docs"]}[RAW]
    assert raw["runnable"] == {"try": False, "run": on}
    assert isinstance(raw["run_reason"]["try"], str) and raw["run_reason"]["try"].strip()
    assert (raw["run_reason"]["run"] is None) is on
    x01 = {d["doc_id"]: d for d in sets["version9"]["docs"]}[X01]
    assert x01["runnable"] == {"try": True, "run": True} and x01["run_reason"] == {"try": None, "run": None}
    old = {d["doc_id"]: d for d in sets["prev/v2"]["docs"]}[X01]
    assert old["runnable"] == {"try": False, "run": False}
    assert [d["doc_id"] for d in data["docs"]] == [X01, X02]             # 지금 화면이 쓰는 키는 그대로


def test_route_options_without_pages_root(bj, app, where):
    ctx = ctx_of(app, where, manager(bj, where))
    ctx.pages_root = None
    data = call(app, ctx, "GET", "/api/options")[1]
    assert [p["value"] for p in data["pages_dirs"]] == ["../data/pages/version9"]
    assert data["default_pages_dir"] == "../data/pages/version9"
    assert data["sets"] == [] and data["default_set"] is None


def test_route_jobs_take_set_id(bj, app, where40, monkeypatch):
    outside_support(monkeypatch, True)
    sp = FakeSpawner()
    ctx = ctx_of(app, where40, manager(bj, where40, sp))
    code, data = call(app, ctx, "POST", "/api/jobs/try", {"model": TAG, "doc": X01, "sections": [11], "set": "version9"})
    assert code == 200 and opt(sp.calls[0]["argv"], "--pages-dir") == "../data/pages/version9"
    for bad in ("../x", "/tmp", "없는_묶음"):
        code, data = call(app, ctx, "POST", "/api/jobs/try", {"model": TAG, "doc": X01, "sections": [11], "set": bad})
        assert code == 400 and data["error"]
    code, data = call(app, ctx, "POST", "/api/jobs/try", {"model": TAG, "doc": X01, "sections": [11], "set": "prev/v2"})
    assert code == 400 and "고를 수 없는 묶음" in data["error"]
    body = {"model": TAG, "docs": [RAW], "set": ".", "run_name": "신규", "repeat": 1}
    code, data = call(app, ctx, "POST", "/api/jobs/run", body)
    assert code == 409 and data["needs_confirm"] is True
    code, data = call(app, ctx, "POST", "/api/jobs/run", {**body, "confirm": True})
    assert code == 200
    p = shlex.split(sp.calls[-1]["argv"][2])
    assert opt(p, "--pages-dir") == "../data/pages" and opt(p, "--docs") == RAW
    assert len(sp.calls) == 2


def test_route_try_passes_chosen_key(bj, app, where):
    for key_id, d in (("silver/claude", X01), ("gold/a3", X02)):
        (where / "data" / key_id).mkdir(parents=True)
        (where / "data" / key_id / f"{d}.json").write_text(json.dumps(make_doc(d), ensure_ascii=False), encoding="utf-8")
    (where / "data" / "silver" / "gpt").mkdir()
    sp = FakeSpawner()
    ctx = ctx_of(app, where, manager(bj, where, sp), data_root=where / "data")
    body = {"model": TAG, "doc": X01, "sections": [11], "pages_dir": "../data/pages/version9"}
    assert call(app, ctx, "POST", "/api/jobs/try", body)[0] == 200
    assert "--gold-dir" not in sp.calls[-1]["argv"]                     # key가 없으면 명령 줄은 지금과 같다
    assert call(app, ctx, "POST", "/api/jobs/try", {**body, "key": "gold/a3"})[0] == 200
    assert opt(sp.calls[-1]["argv"], "--gold-dir") == "../data/gold/a3"
    for bad in ("없는/정답지", "../gold/a3", "silver/gpt", 3):
        code, data = call(app, ctx, "POST", "/api/jobs/try", {**body, "key": bad})
        assert code == 400 and data["error"], bad
    assert len(sp.calls) == 2


def test_start_try_gold_dir_argv(bj, where):
    sp = FakeSpawner()
    m = manager(bj, where, sp)
    try_job(m, gold_dir="../data/gold/a3")
    assert opt(sp.calls[0]["argv"], "--gold-dir") == "../data/gold/a3"
    try_job(m)
    assert "--gold-dir" not in sp.calls[1]["argv"]
