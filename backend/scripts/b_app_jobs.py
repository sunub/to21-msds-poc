"""작업 화면 탭 ④ 작업: 항 시험·본 실행·비교표 만들기를 띄우고, 진행을 보고, 멈춘다 (역할 B, 개발 전용, ADR-025).

명령줄 도구(try_section.py, run_sections.py, compare_models.py)를 고치지 않고 그대로 부른다. backend/에서 돈다.
- 평가용 문서는 어떤 작업에도 넣지 않는다. --allow-eval을 넘기지 않는다 (D-43).
- 바꾼 안내문 글은 저장소 밖 임시 파일(tempfile)에만 쓰고, 작업이 끝나면 지운다. 로그·상태 파일에는 경로만 남는다 (D-47).
- 작업마다 jobs_dir(runs/manual/jobs)에 로그 <id>.log와 상태 <id>.json을 남긴다. 앱을 다시 켜도 지난 작업이 보인다.
- 작업은 새 세션(프로세스 묶음)으로 띄운다. 앱을 꺼도 작업은 계속 돌고, 멈추기는 묶음 전체(bash와 그 아래 python)에 보낸다.
- 시험은 spawner·ps·sleep을 가짜로 끼운다. 진짜 프로세스를 띄우지 않는다.
"""
from __future__ import annotations   # JobManager.list가 뒤 메서드의 list[...] 표기를 가리지 않게

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from _common import today
from msds.common import manifest
from msds.common.paths import RUNS
from msds.extract.client import load_model_config

_NAME = re.compile(r"^\w[\w.-]*$")                   # 실행 이름·비교표 제목·라벨 (경로 탈출·셸 글자 막기)
_RUN = re.compile(r"^(manual/)?\w[\w.-]*$")          # 기존 실행 폴더 이름 (runs/manual/<이름> 포함)
_SCRIPTS = {"run_sections.py": "run", "try_section.py": "try"}   # ps에서 찾는 스크립트
MAX_REPEAT = 10
STOP_WAIT = 5.0                                      # terminate 뒤 kill까지 기다리는 초
TMP_GRACE = 60                                       # 지난 앱이 띄운 작업의 임시 파일을 지워도 되는 시간(초). try_section은 시작하자마자 읽는다


@dataclass
class Job:
    id: str
    kind: str                                        # try | run | compare
    argv: list[str]
    log: Path
    started: float
    pid: int | None
    returncode: int | None
    label: str
    runs: list[str] = field(default_factory=list)    # 본 실행: 실행 이름들(_r1, _r2…), 비교표: 비교표 폴더 이름
    total: int | None = None                         # 본 실행: 실행 하나의 문서 수
    stopped: bool = False
    tmp: str | None = None                           # 바꾼 안내문 임시 파일 경로 (글은 남기지 않는다)


class _Group:
    """Popen을 감싸 멈추기·죽이기를 프로세스 묶음 전체에 보낸다."""

    def __init__(self, proc: subprocess.Popen):
        self._proc, self.pid = proc, proc.pid

    def poll(self):
        return self._proc.poll()

    def _signal(self, sig) -> None:
        try:
            os.killpg(self.pid, sig)
        except ProcessLookupError:
            pass

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def kill(self) -> None:
        self._signal(signal.SIGKILL)


def _spawn(argv: list[str], log_path: Path, cwd: Path, extra_env: dict[str, str] | None = None) -> _Group:
    """extra_env: 서버 탭이 만든 Pod의 주소·키(RUNPOD_VLLM_*). 자식 환경에만 넣고 상태 파일·로그에는 남기지 않는다."""
    with open(log_path, "ab") as log:                # 자식이 파일을 물려받으므로 여기서는 닫아도 된다
        proc = subprocess.Popen(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True,
                                env={**os.environ, "PYTHONUNBUFFERED": "1", **(extra_env or {})})
    return _Group(proc)


def _ps_text() -> str:
    try:
        return subprocess.run(["ps", "-axo", "pid=,pgid=,command="], capture_output=True, text=True,
                              timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _opt(tokens: list[str], name: str) -> str | None:
    return tokens[tokens.index(name) + 1] if name in tokens[:-1] else None


def _script_proc(command: str) -> dict | None:
    """python으로 run_sections.py·try_section.py를 돌리는 줄이면 종류·실행 이름·모델·문서. bash -c 줄 등은 None."""
    tokens = command.split()
    if not tokens or not os.path.basename(tokens[0]).lower().startswith("python"):
        return None
    kind = next((_SCRIPTS[os.path.basename(t)] for t in tokens[1:] if os.path.basename(t) in _SCRIPTS), None)
    if kind is None:
        return None
    return {"kind": kind, "run_name": _opt(tokens, "--run-name"), "model": _opt(tokens, "--model"),
            "doc": _opt(tokens, "--doc")}


def _total_lines(timing: Path) -> int:
    """timing.jsonl의 total 줄 수 = 끝난 문서 수. 쓰는 중인 마지막 줄은 건너뛴다."""
    if not timing.exists():
        return 0
    n = 0
    for line in timing.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            n += json.loads(line).get("stage") == "total"
        except (ValueError, AttributeError):
            pass
    return n


def suggest_run_name(model_tag: str, prompt_version: str, pages_dir: str, purpose: str = "dev10") -> str:
    """날짜_sections_태그_안내문_입력판_용도. 입력판은 쪽 폴더 이름의 version을 v로 줄인다(version9 → v9)."""
    short = re.sub(r"^version", "v", Path(pages_dir).name)
    return f"{today()}_sections_{model_tag}_{prompt_version}_{short}_{purpose}"


def free_run_name(runs_dir: Path, name: str) -> str:
    """runs/에 그 이름(또는 <이름>_r…)이 이미 있으면 _2, _3…을 붙인다."""
    runs_dir = Path(runs_dir)

    def taken(n: str) -> bool:
        return (runs_dir / n).exists() or any(runs_dir.glob(f"{n}_r*"))

    k, out = 1, name
    while taken(out):
        k += 1
        out = f"{name}_{k}"
    return out


class JobManager:
    def __init__(self, jobs_dir: Path, python: Path, backend_dir: Path, *, spawner=None, runs_dir: Path = RUNS,
                 platform: str = sys.platform, which=shutil.which, ps=None, sleep=time.sleep):
        self.jobs_dir, self.python, self.backend_dir = Path(jobs_dir), Path(python), Path(backend_dir)
        self.runs_dir = Path(runs_dir)
        self._spawner, self._platform, self._which = spawner or _spawn, platform, which
        self._ps, self._sleep = ps or _ps_text, sleep
        self._jobs: dict[str, Job] = {}                  # 이 앱이 띄운 작업
        self._procs: dict = {}                           # 아직 돌고 있는 작업의 프로세스
        self._lock = threading.Lock()

    # ── 검사 ───────────────────────────────────────────

    @staticmethod
    def _model(tag) -> dict:
        try:
            return load_model_config(tag)
        except (KeyError, TypeError):
            raise ValueError(f"configs/models.yaml에 없는 모델 태그: {tag}") from None

    @staticmethod
    def _dev_docs(doc_ids) -> list[str]:
        """개발용 문서만 (순서 유지). 평가용이 있으면 ValueError (D-43)."""
        if not isinstance(doc_ids, list) or not all(isinstance(d, str) for d in doc_ids):
            raise ValueError(f"문서 번호 목록을 확인하세요: {doc_ids}")
        try:
            rows = manifest.select(None, doc_ids)
        except KeyError as e:
            raise ValueError(f"문서 번호를 확인하세요: {e}") from None
        evals = [r["doc_id"] for r in rows if r["purpose"] == "평가"]
        if evals:
            raise ValueError(f"평가용 문서는 작업에 넣을 수 없습니다: {', '.join(evals)} (D-43)")
        others = [r["doc_id"] for r in rows if r["purpose"] != "개발"]
        if others:
            raise ValueError(f"개발용 문서만 넣을 수 있습니다: {', '.join(others)}")
        return list(dict.fromkeys(doc_ids))

    def _pages(self, pages_dir) -> str:
        if not isinstance(pages_dir, str) or not pages_dir or not (self.backend_dir / pages_dir).is_dir():
            raise ValueError(f"쪽 글자 폴더가 없습니다: {pages_dir}")
        return pages_dir

    @staticmethod
    def _name(value, what: str) -> str:
        if not isinstance(value, str) or not _NAME.fullmatch(value) or len(value) > 120:
            raise ValueError(f"{what}에는 글자·숫자·_·.·-만 쓸 수 있습니다: {value!r}")
        return value

    def _existing_run(self, name, need: str = "run_info.yaml") -> str:
        if not isinstance(name, str) or not _RUN.fullmatch(name) or not (self.runs_dir / name / need).is_file():
            raise ValueError(f"실행 폴더가 없습니다: {name} (runs/{name}/{need})")
        return name

    # ── 띄우기 ─────────────────────────────────────────

    def _start(self, kind: str, argv: list[str], label: str, extra_env: dict[str, str] | None = None, **extra) -> Job:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        job_id = f"{datetime.now():%Y%m%d_%H%M%S}_{kind}_{os.urandom(3).hex()}"
        job = Job(id=job_id, kind=kind, argv=argv, log=self.jobs_dir / f"{job_id}.log", started=time.time(),
                  pid=None, returncode=None, label=label, **extra)
        try:
            # 넘길 환경이 있을 때만 인자로 준다(Job에는 담지 않아 상태 파일에 키가 남지 않는다)
            proc = self._spawner(argv, job.log, self.backend_dir, **({"extra_env": extra_env} if extra_env else {}))
        except Exception:
            self._remove_tmp(job)
            raise
        job.pid = proc.pid
        with self._lock:
            self._jobs[job.id], self._procs[job.id] = job, proc
            self._save(job)
            self._refresh(job)                           # 바로 끝난 작업(잘못된 인자 등)
        return job

    def start_try(self, *, model: str, doc: str, sections: list[int] | None, all_: bool, pages_dir: str,
                  system_text: str | None, base_run: str | None, dry_run: bool = False,
                  extra_env: dict[str, str] | None = None) -> Job:
        self._model(model)
        self._dev_docs([doc])
        pages_dir = self._pages(pages_dir)
        if all_:
            secs = None
        else:
            if not isinstance(sections, list) or not sections:
                raise ValueError("시험할 항을 하나 이상 고르세요")
            secs = sorted(set(sections))
            if not all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 16 for n in secs):
                raise ValueError(f"항 번호는 1~16입니다: {sections}")
        if system_text is not None:
            if all_ or len(secs) != 1:
                raise ValueError("바꾼 안내문은 항 하나를 시험할 때만 쓸 수 있습니다")
            if not isinstance(system_text, str) or not system_text.strip():
                raise ValueError("바꾼 안내문이 비었습니다")
        if base_run:
            self._existing_run(base_run, f"outputs/{doc}.json")
        argv = [str(self.python), "scripts/try_section.py", "--model", model, "--doc", doc]
        argv += ["--all"] if all_ else [x for n in secs for x in ("--section", str(n))]
        argv += ["--pages-dir", pages_dir, "--json"]
        if dry_run:
            argv.append("--dry-run")
        if base_run:
            argv += ["--base-run", base_run]
        tmp = None
        if system_text is not None:                      # 저장소 밖 임시 파일. 끝나면 지운다 (D-47)
            fd, tmp = tempfile.mkstemp(prefix="b_app_system_", suffix=".txt", dir=tempfile.gettempdir())
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(system_text)
            argv += ["--system-file", tmp]
        scope = "문서 전체" if all_ else "·".join(map(str, secs)) + "항"
        label = " · ".join([f"{doc} {scope}", model] + (["바꾼 안내문"] if tmp else []) + (["dry-run"] if dry_run else []))
        return self._start("try", argv, label, extra_env=extra_env, tmp=tmp)

    def _check_run(self, model, docs, pages_dir, run_name, repeat) -> tuple[dict, list[str], list[str], str]:
        cfg = self._model(model)
        doc_ids = self._dev_docs(docs) if docs else [r["doc_id"] for r in manifest.select("개발")]
        pages_dir = self._pages(pages_dir)
        self._name(run_name, "실행 이름")
        if not isinstance(repeat, int) or isinstance(repeat, bool) or not 1 <= repeat <= MAX_REPEAT:
            raise ValueError(f"반복 수는 1~{MAX_REPEAT}입니다: {repeat}")
        names = [f"{run_name}_r{k}" for k in range(1, repeat + 1)]
        taken = [n for n in names if (self.runs_dir / n).exists()]
        if taken:
            raise ValueError(f"이미 있는 실행 이름입니다: {', '.join(taken)}. 다른 이름을 쓰세요")
        return cfg, doc_ids, names, pages_dir

    def run_summary(self, *, model: str, docs: list[str] | None, pages_dir: str, run_name: str, repeat: int) -> str:
        """본 실행을 시작하기 전에 보여 줄 요약. 검사에 걸리면 ValueError."""
        cfg, doc_ids, names, pages_dir = self._check_run(model, docs, pages_dir, run_name, repeat)
        text = (f"{len(doc_ids)}건 × {repeat}회, 모델 {model} ({cfg['model']}), 쪽 폴더 {pages_dir}, "
                f"실행 이름 {', '.join(names)}")
        busy = self.running()
        if busy:
            text += f"\n주의: 지금 도는 실행·시험이 {len(busy)}개 있습니다. 같은 서버를 함께 쓰면 문서 시간이 늘어납니다."
        return text

    def start_run(self, *, model: str, docs: list[str] | None, pages_dir: str, run_name: str, repeat: int,
                  extra_env: dict[str, str] | None = None) -> list[Job]:
        """repeat번의 run_sections.py를 차례로 돌리는 셸 한 줄을 작업 하나로 띄운다. Mac이 잠들면 실행이 멈추므로(10/28)
        darwin에 caffeinate가 있으면 그것으로 감싼다."""
        _, doc_ids, names, pages_dir = self._check_run(model, docs, pages_dir, run_name, repeat)
        cmds = [[str(self.python), "scripts/run_sections.py", "--model", model, "--docs", *doc_ids,
                 "--run-name", n, "--pages-dir", pages_dir] for n in names]
        argv = ["bash", "-c", "; ".join(shlex.join(c) for c in cmds)]
        if self._platform == "darwin" and self._which("caffeinate"):
            argv = ["caffeinate", "-dimsu", *argv]
        label = f"{run_name} · {len(doc_ids)}건 × {repeat}회 · {model}"
        return [self._start("run", argv, label, extra_env=extra_env, runs=names, total=len(doc_ids))]

    def start_compare(self, *, title: str, runs: list[str], labels: list[str | None] | None) -> Job:
        """labels의 빈 칸은 라벨 없이(실행 이름 그대로) 넘긴다."""
        self._name(title, "비교표 제목")
        if not isinstance(runs, list) or not runs:
            raise ValueError("비교할 실행을 하나 이상 고르세요")
        for r in runs:
            self._existing_run(r)
        if labels is not None and (not isinstance(labels, list) or len(labels) != len(runs)):
            raise ValueError("라벨 수가 실행 수와 다릅니다")
        labels = labels or [None] * len(runs)
        for lb in labels:
            if lb:
                self._name(lb, "라벨")
        out = f"{today()}_models_{title}"
        if (self.runs_dir / out).exists():
            raise ValueError(f"이미 있는 비교표입니다: runs/{out}. 다른 제목을 쓰세요")
        specs = [f"{lb}={r}" if lb else r for lb, r in zip(labels, runs)]
        argv = [str(self.python), "scripts/compare_models.py", "--title", title, "--runs", *specs]
        return self._start("compare", argv, f"{title} · 실행 {len(runs)}개", runs=[out])

    # ── 상태 ───────────────────────────────────────────

    def _save(self, job: Job) -> None:
        state = {**asdict(job), "log": str(job.log)}
        tmp = self.jobs_dir / f"{job.id}.json.tmp"
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.jobs_dir / f"{job.id}.json")

    @staticmethod
    def _remove_tmp(job: Job) -> None:
        if job.tmp:
            Path(job.tmp).unlink(missing_ok=True)
            job.tmp = None

    def _finish(self, job: Job) -> None:
        self._procs.pop(job.id, None)
        self._remove_tmp(job)
        self._save(job)

    def _refresh(self, job: Job) -> None:
        """잠금 안에서 부른다. 끝난 작업의 종료 코드를 남기고 임시 파일을 지운다."""
        proc = self._procs.get(job.id)
        if proc is None:
            return
        code = proc.poll()
        if code is not None:
            job.returncode = code
            self._finish(job)

    def _disk(self) -> dict[str, Job]:
        """jobs_dir의 상태 파일 중 이 앱이 띄우지 않은 것 (지난 앱의 작업)."""
        out = {}
        for f in sorted(self.jobs_dir.glob("*.json")) if self.jobs_dir.exists() else []:
            if f.stem in self._jobs:
                continue
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                job = Job(**{**d, "log": Path(d["log"])})
            except (ValueError, TypeError, KeyError):
                continue                                 # 쓰다 만 상태 파일
            if job.tmp and time.time() - job.started > TMP_GRACE:
                self._remove_tmp(job)
                self._save(job)
            out[job.id] = job
        return out

    def _get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id) or self._disk().get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _status(self, job: Job) -> str:
        if job.stopped:
            return "stopped"
        if job.returncode is None:
            return "running" if job.id in self._procs else "unknown"     # unknown: 지난 앱이 띄워 결과를 모른다
        return "done" if job.returncode == 0 else "failed"

    def _view(self, job: Job) -> dict:
        out = None
        if job.kind == "compare" and (self.runs_dir / job.runs[0] / "compare.md").is_file():
            out = os.path.relpath(self.runs_dir / job.runs[0] / "compare.md", self.runs_dir.parent)
        progress = None
        if job.kind == "run":
            progress = [{"name": n, "done": _total_lines(self.runs_dir / n / "timing.jsonl"), "total": job.total}
                        for n in job.runs]
        return {"id": job.id, "kind": job.kind, "label": job.label, "started": job.started, "pid": job.pid,
                "returncode": job.returncode, "status": self._status(job), "stoppable": job.id in self._procs,
                "command": shlex.join(job.argv), "log": os.path.relpath(job.log, self.runs_dir.parent),
                "runs": job.runs, "progress": progress, "output": out}

    def list(self) -> list[dict]:
        with self._lock:
            for job in list(self._jobs.values()):
                self._refresh(job)
            jobs = [*self._jobs.values(), *self._disk().values()]
            return [self._view(j) for j in sorted(jobs, key=lambda j: j.started, reverse=True)]

    def running(self) -> list[dict]:
        """이 앱이 띄워 아직 도는 작업 + 밖(다른 터미널·지난 앱·다른 세션)에서 도는 run_sections.py·try_section.py."""
        with self._lock:
            for job in list(self._jobs.values()):
                self._refresh(job)
            mine = [self._jobs[i] for i in self._procs]
        out = [{"mine": True, "id": j.id, "kind": j.kind, "label": j.label, "pid": j.pid} for j in mine]
        groups = {j.pid for j in mine}                   # 이 앱의 작업은 새 세션이라 묶음 번호(pgid)가 그 pid다
        for line in self._ps().splitlines():
            m = re.match(r"\s*(\d+)\s+(\d+)\s+(.*)", line)
            if not m or int(m[2]) in groups:
                continue
            info = _script_proc(m[3])
            if info:
                out.append({"mine": False, "pid": int(m[1]), **info})
        return out

    def stop(self, job_id: str) -> bool:
        """terminate를 보내고 STOP_WAIT초 안에 안 끝나면 kill. 이 앱이 띄워 아직 도는 작업만 멈출 수 있다."""
        with self._lock:
            job, proc = self._jobs.get(job_id), self._procs.get(job_id)
            if job is None or proc is None:
                return False
            self._refresh(job)
            if job.id not in self._procs:
                return False
        proc.terminate()                                 # 기다리는 동안 다른 요청이 막히지 않게 잠금 밖에서
        for _ in range(int(STOP_WAIT / 0.1)):
            if proc.poll() is not None:
                break
            self._sleep(0.1)
        else:
            proc.kill()
            for _ in range(10):
                if proc.poll() is not None:
                    break
                self._sleep(0.1)
        with self._lock:
            job.returncode, job.stopped = proc.poll(), True
            self._finish(job)
        return True

    def tail(self, job_id: str, lines: int = 200) -> str:
        job = self._get(job_id)
        if not job.log.exists():
            return ""
        text = job.log.read_text(encoding="utf-8", errors="replace")
        return "".join(text.splitlines(keepends=True)[-max(1, lines):])

    def result(self, job_id: str) -> dict | None:
        """try 작업 로그의 마지막 JSON 덩이(try_section --json 출력). 맨 앞 칸의 '{' 줄부터 읽는다. 없으면 None."""
        job = self._get(job_id)
        if job.kind != "try" or not job.log.exists():
            return None
        text = job.log.read_text(encoding="utf-8", errors="replace")
        for pos in reversed([m.start() for m in re.finditer(r"^\{[ \t]*$", text, re.M)]):
            try:
                obj, _ = json.JSONDecoder().raw_decode(text, pos)
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
        return None
