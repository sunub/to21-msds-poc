"""작업 화면 서버 (역할 B, 개발 전용, ADR-025). 사용법: python scripts/b_app.py [--port 8765] [--no-browser]

내 컴퓨터(127.0.0.1)에서만 연다. 다른 주소에는 묶지 않는다. 쪽 글자·그림·안내문은 화면에만 보이고 파일로 남기지 않는다 (D-47).
표준 http.server만 쓴다. 요청 처리는 순수 함수 route()가 하고 핸들러는 그것을 부르기만 한다(시험은 route를 직접 부른다).
탭 ① 점수판은 b_app_runs의 요약을, 탭 ② 두 실행 비교는 b_app_diff의 결과를, 탭 ③ 원문 대조는 b_app_doc의 결과를 보여 준다.
쪽 그림(/pages/<문서>/pNNN.png)은 요청 때 pages_dir에서 읽어 보낸다. 평가용 문서는 보내지 않는다 (D-43).
탭 ④ 작업은 b_app_jobs의 JobManager로 시험·본 실행·비교표를 띄운다. POST는 같은 화면에서 보낸 JSON만 받는다(다른 웹페이지의
폼 보내기 막기). 안내문 글(/api/prompt)은 요청 때 만들어 보여 주기만 한다 (D-47).
탭 ⑤ 서버는 b_app_servers.ServerActions를 부른다. 바꾸는 동작은 propose(요약·확인 토큰) → execute(토큰) 두 단계이고,
이 앱이 만든 Pod의 주소·키는 작업을 띄울 때 그 작업의 환경에만 넣는다(파일에 쓰지 않는다). 도움말은 다음 step에서 채운다.
"""
import argparse
import json
import os
import re
import sys
import threading
import webbrowser
from dataclasses import dataclass
from typing import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import yaml

import _common  # noqa: F401  src 경로 등록
import b_app_diff as bd
import b_app_doc as bdoc
import b_app_jobs as bj
import b_app_runs as br
import b_app_servers as bs
import b_app_text as bt
from msds.common import manifest
from msds.common.paths import BACKEND, CONFIGS, PAGES, ROOT, RUNS, SILVER
from msds.extract.client import load_model_config
from msds.extract.section_prompts import SECTION_PROMPT_VERSION, build_system, prompt_hash
from msds.extract.section_runner import DOC_TIME_LIMIT

HOST = "127.0.0.1"
STATIC = Path(__file__).resolve().parent / "b_app_static"
GAPS_FILE = CONFIGS / "silver_gaps.yaml"
_HEAVY = ("details", "per_doc", "grid")              # /api/runs 목록에서 빼는 큰 칸. /api/run/<이름>에만 준다
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8"}
_LOCK = threading.Lock()                             # 요약 캐시 파일을 두 요청이 함께 쓰지 않게 한다
_DOC_ID = re.compile(r"^T21-[A-Z0-9]+$")              # 쪽 그림·원문 대조 주소에서 받는 문서 번호 (경로 탈출 막기)
_PAGE_PNG = re.compile(r"^p\d{3}\.png$")
_JOB_PATH = re.compile(r"^/api/jobs/([\w-]+)/(log|result|stop)$")
MAX_BODY = 2 * 1024 * 1024                           # POST 본문 한도 (바꾼 안내문 글이 가장 길다)


@dataclass
class AppContext:
    runs_dir: Path
    gold_dir: Path
    pages_dir: Path
    static_dir: Path = STATIC
    cache_dir: Path | None = br.CACHE_DIR
    gaps_file: Path = GAPS_FILE
    repo_root: Path = ROOT                           # 안내문 차이에서 커밋을 꺼낼 저장소
    jobs: bj.JobManager | None = None                # 탭 ④ 작업. 없으면 작업 주소는 503
    pages_root: Path = PAGES                         # 쪽 폴더 후보(version*)를 찾는 곳
    model_status: Callable[[], list[dict]] | None = None   # 모델 서버 연결 상태 (ServerActions.model_status). 없으면 확인하지 않는다
    servers: bs.ServerActions | None = None          # 탭 ⑤ 서버. 없으면 서버 주소는 503
    last_model_connections: dict[str, bool] | None = None  # 마지막 조회 결과만. 점수 요청은 서버를 부르지 않는다
    run_history: list[dict] | None = None            # /api/runs가 읽은 가벼운 목록. 새로 읽을 때 갱신


def _json(code: int, obj) -> tuple[int, str, bytes]:
    return code, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False, default=str).encode()


def _labeled_run(info: dict) -> dict:
    """채점·캐시는 그대로 두고 응답에만 표시 글을 붙인다."""
    return {**info, "label": bt.run_label(info), "model_label": bt.model_label(info.get("model_tag"))}


def _remember_connections(ctx: AppContext, models: list[dict]) -> None:
    ctx.last_model_connections = {m["tag"]: bool(m.get("reachable") and m.get("match")) for m in models}


def _run_list(ctx: AppContext) -> dict:
    data = br.load_all(ctx.runs_dir, ctx.gold_dir, cache_dir=ctx.cache_dir)
    runs = [_labeled_run({k: v for k, v in r.items() if k not in _HEAVY}) for r in data["runs"]]
    ctx.run_history = runs
    return {**data, "runs": runs, "current": pick_current(runs), "doc_time_limit": DOC_TIME_LIMIT}


def _run_with_text(run: Path, ctx: AppContext) -> dict:
    info = _labeled_run(br.summarize_run(run, ctx.gold_dir, cache_dir=ctx.cache_dir))
    if ctx.run_history is None:
        _run_list(ctx)
    connected = (ctx.last_model_connections or {}).get(info.get("model_tag"))
    # 지금 요청한 실행은 가장 최근 값을 쓴다. 원본 채점 dict와 캐시는 수정하지 않는다.
    history = [info if r["name"] == info["name"] else r for r in ctx.run_history]
    summaries = {kind: bt.card_summary(kind, info) for kind in ("docs", "grid", "rows")}
    summaries["history"] = bt.card_summary("history", {"runs": history})
    return {**info, "status_text": bt.score_status(info, br.criteria(), connected=connected),
            "card_summaries": summaries}


def _static(rel: str, ctx: AppContext) -> tuple[int, str, bytes]:
    if ".." in rel or rel.startswith("/") or "\\" in rel:
        return _json(400, {"error": "잘못된 경로"})
    f = ctx.static_dir / rel
    if not f.is_file():
        return _json(404, {"error": f"없는 파일: {rel}"})
    content = f.read_bytes()
    if rel == "index.html":
        # script의 닫는 태그가 글 안에 있어도 HTML로 해석되지 않게 한다.
        copy = json.dumps(bt.POLISH_TEXT, ensure_ascii=False).replace("<", "\\u003c")
        content = content.replace(b"__B_APP_UI_TEXT__", copy.encode("utf-8"))
    return 200, _TYPES.get(f.suffix, "application/octet-stream"), content


def pick_current(runs: list[dict]) -> str | None:
    """점수판이 처음 보여 줄 실행. 점수가 있는 실행 중 가장 최근 dev10 본 실행, 없으면 가장 최근 실행.
    runs는 load_all 순서(시작 시각 순)다."""
    scored = [r for r in runs if r.get("kind") != "models" and r.get("weighted") is not None]
    main_runs = [r for r in scored if r["kind"] == "run" and "dev10" in r["name"]]
    found = main_runs or scored
    return found[-1]["name"] if found else None


def _run_paths(ctx: AppContext) -> dict[str, Path]:
    return {p.relative_to(ctx.runs_dir).as_posix(): p for p in br.list_runs(ctx.runs_dir)}


def _gaps(ctx: AppContext) -> list:
    if not ctx.gaps_file.exists():
        return []
    return yaml.safe_load(ctx.gaps_file.read_text(encoding="utf-8")) or []


def _pair(query: dict[str, list[str]], ctx: AppContext):
    """쿼리 a, b의 실행 폴더 두 개. 잘못되면 (오류 응답, None)."""
    names = [(query.get(k) or [""])[0] for k in ("a", "b")]
    if not all(names):
        return _json(400, {"error": "a와 b에 실행 이름을 둘 다 주세요"}), None
    runs = _run_paths(ctx)
    missing = [n for n in names if n not in runs]
    if missing:
        return _json(404, {"error": f"없는 실행: {', '.join(missing)}"}), None
    return None, [runs[n] for n in names]


def _prompt_diff(query: dict[str, list[str]], pair: list[Path], ctx: AppContext):
    no = (query.get("no") or [""])[0]
    if not (no.isascii() and no.isdigit() and 1 <= int(no) <= 16):
        return _json(400, {"error": f"no는 1~16 항 번호여야 합니다 (받은 값: {no})"})
    no = int(no)
    infos = [yaml.safe_load((p / "run_info.yaml").read_text(encoding="utf-8")) or {} for p in pair]
    missing = [p.name for p, i in zip(pair, infos) if not i.get("git_commit")]
    if missing:
        return _json(400, {"error": f"run_info.yaml에 git_commit이 없어 그때의 안내문을 만들 수 없습니다: {', '.join(missing)}"})
    commits = [str(i["git_commit"]) for i in infos]
    rows = [no in (i.get("rows_sections") or []) for i in infos]
    try:
        res = bd.prompt_diff(no, rows[0], commits[0], commits[1], ctx.repo_root, rows_b=rows[1])
    except ValueError as e:
        return _json(400, {"error": str(e)})
    # 실행이 기록한 해시. 다시 만든 글의 해시와 다르면 그 실행은 커밋되지 않은 안내문으로 돌았다
    recorded = [{str(k): v for k, v in (i.get("prompt_hashes") or {}).items()}.get(str(no)) for i in infos]
    return _json(200, {**res, "rows": rows, "recorded": {"a": recorded[0], "b": recorded[1]}})


def _page_png(rest: str, ctx: AppContext) -> tuple[int, str, bytes]:
    """/pages/<문서>/pNNN.png. 정규식 밖의 주소는 400, 평가용·manifest 밖 문서와 없는 쪽은 404."""
    parts = rest.split("/")
    if len(parts) != 2 or not _DOC_ID.fullmatch(parts[0]) or not _PAGE_PNG.fullmatch(parts[1]):
        return _json(400, {"error": "잘못된 쪽 그림 주소"})
    f = ctx.pages_dir / parts[0] / parts[1]
    if not bdoc.allowed_doc(parts[0]) or not f.is_file():
        return _json(404, {"error": "없는 쪽 그림"})
    return 200, "image/png", f.read_bytes()


def _doc(query: dict[str, list[str]], ctx: AppContext) -> tuple[int, str, bytes]:
    name, doc_id = [(query.get(k) or [""])[0] for k in ("run", "doc")]
    if not name or not _DOC_ID.fullmatch(doc_id):
        return _json(400, {"error": "run에 실행 이름, doc에 문서 번호(T21-…)를 주세요"})
    run = _run_paths(ctx).get(name)
    if run is None:
        return _json(404, {"error": f"없는 실행: {name}"})
    missing = _json(404, {"error": f"이 실행에 없는 문서: {doc_id}"})     # 평가용도 같은 말로 돌려준다(이유를 말하지 않는다)
    if not bdoc.allowed_doc(doc_id) or not (run / "outputs" / f"{doc_id}.json").is_file():
        return missing
    try:
        view = bdoc.doc_view(run, doc_id, ctx.pages_dir, ctx.gold_dir)
        return _json(200, {**view, "legend": bt.doc_legend(), "ui_text": bt.doc_ui_text(view)})
    except PermissionError:
        return missing
    except FileNotFoundError:
        return _json(404, {"error": f"쪽 글자가 없습니다: {ctx.pages_dir.name}/{doc_id}"})


def _why_offline(s: dict | None) -> str | None:
    if s is None:
        return "서버 탭이 연결을 보지 않는 태그(실버용 등)"
    if s.get("reachable") and s.get("match"):
        return None
    if s.get("error"):
        return s["error"]
    if s.get("reachable"):
        return f"다른 모델이 떠 있음: {s.get('model_served')}"
    return "주소가 .env에 없음"


def _options(ctx: AppContext, *, advanced: bool = False) -> tuple[int, str, bytes]:
    """탭 ④의 고를 거리: 모델 태그(연결 여부), 개발용 문서, 쪽 폴더 후보, 추천 실행 이름."""
    cfg = yaml.safe_load((CONFIGS / "models.yaml").read_text(encoding="utf-8"))["models"]
    status = ctx.model_status() if ctx.model_status else None
    if status is not None:
        _remember_connections(ctx, status)
    by_tag = {s["tag"]: s for s in status or []}
    models = [{"tag": tag, "label": bt.model_label(tag), "model": c["model"], "connected": None if status is None else _why_offline(by_tag.get(tag)) is None,
               "error": None if status is None else _why_offline(by_tag.get(tag)),
               "rows_sections": c.get("rows_sections") or [], "image_input": bool(c.get("image_input"))}
              for tag, c in cfg.items()]
    backend = ctx.jobs.backend_dir if ctx.jobs else BACKEND
    runs_dir = ctx.jobs.runs_dir if ctx.jobs else RUNS
    found = sorted((p for p in Path(ctx.pages_root).glob("version*") if p.is_dir()), key=lambda p: p.name)
    pages = [{"name": p.name, "value": os.path.relpath(p, backend)} for p in found]
    default = next((v["value"] for p, v in zip(found, pages) if p.resolve() == Path(ctx.pages_dir).resolve()),
                   next((v["value"] for v in pages if v["name"] == "version9"), pages[0]["value"] if pages else None))
    names = {tag: {v["value"]: {purpose: bj.free_run_name(runs_dir, bj.suggest_run_name(
        tag, SECTION_PROMPT_VERSION, v["value"], purpose)) for purpose in ("dev10", "probe")} for v in pages}
        for tag in cfg}
    return _json(200, {"models": bt.order_models(models), "status_checked": status is not None, "ui_text": bt.server_ui_text(),
                       "field_help": bt.FIELD_HELP, "try_hint": bt.try_hint(models, advanced),
                       "try_stage_help": bt.TRY_STAGE_HELP, "job_ui_text": bt.JOB_UI_TEXT,
                       "docs": [{"doc_id": r["doc_id"], "pages": r.get("pages")} for r in manifest.select("개발")],
                       "pages_dirs": pages, "default_pages_dir": default, "prompt_version": SECTION_PROMPT_VERSION,
                       "run_names": names})


def _prompt(query: dict[str, list[str]]) -> tuple[int, str, bytes]:
    """그 모델 태그가 no항에 보내는 안내문 글. 화면의 글상자에 채울 때만 쓴다. 파일로 남기지 않는다 (D-47)."""
    tag, no = [(query.get(k) or [""])[0] for k in ("model", "no")]
    if not (no.isascii() and no.isdigit() and 1 <= int(no) <= 16):
        return _json(400, {"error": f"no는 1~16 항 번호여야 합니다 (받은 값: {no})"})
    try:
        cfg = load_model_config(tag)
    except KeyError:
        return _json(400, {"error": f"configs/models.yaml에 없는 모델 태그: {tag}"})
    rows = int(no) in (cfg.get("rows_sections") or [])
    return _json(200, {"no": int(no), "rows": rows, "text": build_system(int(no), rows),
                       "hash": prompt_hash(int(no), rows)})


def _job_get(path: str, query: dict[str, list[str]], ctx: AppContext) -> tuple[int, str, bytes]:
    if path == "/api/jobs":
        return _json(200, {"jobs": ctx.jobs.list(), "running": ctx.jobs.running()})
    m = _JOB_PATH.match(path)
    if not m or m[2] == "stop":
        return _json(404, {"error": f"없는 주소: {path}"})
    lines = (query.get("lines") or ["200"])[0]
    if not (lines.isascii() and lines.isdigit()):
        return _json(400, {"error": f"lines는 숫자여야 합니다 (받은 값: {lines})"})
    try:
        if m[2] == "log":
            return _json(200, {"id": m[1], "text": ctx.jobs.tail(m[1], min(int(lines), 5000))})
        res = ctx.jobs.result(m[1])
    except KeyError:
        return _json(404, {"error": f"없는 작업: {m[1]}"})
    return _json(200, res) if res is not None else (204, "application/json; charset=utf-8", b"")


def _body(body: bytes | None) -> dict | None:
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _server_post(path: str, body: bytes | None, ctx: AppContext) -> tuple[int, str, bytes]:
    """탭 ⑤의 두 단계. 결과 dict의 code(없으면 200)를 상태 코드로 쓴다. 토큰이 틀리면 400, 지났으면 410, 실행 중이면 409."""
    if ctx.servers is None:
        return _json(503, {"error": "서버 탭이 꺼져 있습니다"})
    data = _body(body)
    if data is None:
        return _json(400, {"error": "본문은 JSON 객체여야 합니다"})
    if path == "/api/servers/propose":
        res = ctx.servers.propose(data.get("action"), data.get("params"))
    elif path == "/api/servers/execute":
        res = ctx.servers.execute(data.get("token"))
    else:
        return _json(404, {"error": f"없는 주소: POST {path}"})
    res = dict(res)
    return _json(res.pop("code", 200), res)


def _post(path: str, body: bytes | None, ctx: AppContext) -> tuple[int, str, bytes]:
    if path.startswith("/api/servers/"):
        return _server_post(path, body, ctx)
    if ctx.jobs is None:
        return _json(503, {"error": "작업 탭이 꺼져 있습니다(--runs-dir를 기본 runs/가 아닌 곳으로 주면 꺼집니다)"})
    data = _body(body)
    if data is None:
        return _json(400, {"error": "본문은 JSON 객체여야 합니다"})
    jobs = ctx.jobs
    extra_env = ctx.servers.job_env() if ctx.servers else None   # 이 앱이 만든 Pod의 주소·키. 작업 환경에만 넣는다
    try:
        if path == "/api/jobs/try":
            job = jobs.start_try(model=data.get("model"), doc=data.get("doc"), sections=data.get("sections"),
                                 all_=bool(data.get("all")), pages_dir=data.get("pages_dir"),
                                 system_text=data.get("system_text"), base_run=data.get("base_run") or None,
                                 dry_run=bool(data.get("dry_run")), extra_env=extra_env)
            return _json(200, {"id": job.id})
        if path == "/api/jobs/run":
            args = {k: data.get(k) for k in ("model", "docs", "pages_dir", "run_name", "repeat")}
            summary = jobs.run_summary(**args)
            if data.get("confirm") is not True:         # 오래 돌고 서버 비용이 드는 작업이라 요약을 보고 한 번 더 누른다
                return _json(409, {"summary": summary, "needs_confirm": True})
            return _json(200, {"id": jobs.start_run(**args, extra_env=extra_env)[0].id, "summary": summary})
        if path == "/api/jobs/compare":
            job = jobs.start_compare(title=data.get("title"), runs=data.get("runs"), labels=data.get("labels"))
            return _json(200, {"id": job.id})
    except (ValueError, TypeError) as e:
        return _json(400, {"error": str(e)})
    m = _JOB_PATH.match(path)
    if m and m[2] == "stop":
        return _json(200, {"stopped": jobs.stop(m[1])})
    return _json(404, {"error": f"없는 주소: POST {path}"})


def route(method: str, path: str, query: dict[str, list[str]], body: bytes | None,
          ctx: AppContext) -> tuple[int, str, bytes]:
    """(상태 코드, Content-Type, 본문). path는 아직 % 풀기 전의 경로다."""
    path = unquote(path)
    if method == "POST":
        return _post(path, body, ctx)
    if method != "GET":
        return _json(404, {"error": f"없는 주소: {method} {path}"})
    if path == "/":
        return _static("index.html", ctx)
    if path.startswith("/static/"):
        return _static(path[len("/static/"):], ctx)
    if path == "/api/runs":
        if query.get("count") == ["1"]:
            return _json(200, {"count": len(br.list_runs(ctx.runs_dir))})
        with _LOCK:
            return _json(200, _run_list(ctx))
    if path.startswith("/api/run/"):
        run = _run_paths(ctx).get(path[len("/api/run/"):])
        if run is None:
            return _json(404, {"error": f"없는 실행: {path[len('/api/run/'):]}"})
        with _LOCK:
            return _json(200, _run_with_text(run, ctx))
    if path in ("/api/diff", "/api/prompt_diff"):
        err, pair = _pair(query, ctx)
        if err:
            return err
        if path == "/api/prompt_diff":
            return _prompt_diff(query, pair, ctx)
        with _LOCK:
            a, b = [br.summarize_run(p, ctx.gold_dir, cache_dir=ctx.cache_dir) for p in pair]
        diff = bd.diff_runs(a, b)
        return _json(200, {**diff, "headline": bt.diff_headline(diff, bt.run_label(a)["title"], bt.run_label(b)["title"]),
                           "ui_text": bt.diff_ui_text(diff)})
    if path == "/api/doc":
        return _doc(query, ctx)
    if path.startswith("/pages/"):
        return _page_png(path[len("/pages/"):], ctx)
    if path == "/api/jobs" or path.startswith("/api/jobs/"):
        if ctx.jobs is None:
            return _json(503, {"error": "작업 탭이 꺼져 있습니다(--runs-dir를 기본 runs/가 아닌 곳으로 주면 꺼집니다)"})
        return _job_get(path, query, ctx)
    if path == "/api/options":
        return _options(ctx, advanced=(query.get("advanced") or ["0"])[0] == "1")
    if path == "/api/servers":
        if ctx.servers is None:
            return _json(503, {"error": "서버 탭이 꺼져 있습니다"})
        result = ctx.servers.status()
        _remember_connections(ctx, result.get("models") or [])
        return _json(200, result)
    if path == "/api/prompt":
        return _prompt(query)
    if path == "/api/criteria":
        return _json(200, br.criteria())
    if path == "/api/glossary":
        return _json(200, {"items": bt.glossary_entries()})
    if path == "/api/start":
        return _json(200, bt.START_TEXT)
    if path == "/api/silver_gaps":
        return _json(200, _gaps(ctx))
    return _json(404, {"error": f"없는 주소: {path}"})


def allowed_host(host: str | None, port: int) -> bool:
    """다른 웹페이지가 다른 이름으로 이 화면을 부르지 못하게(DNS 재바인딩) Host가 내 컴퓨터일 때만 받는다."""
    return host in (f"{HOST}:{port}", f"localhost:{port}")


def allowed_post(content_type: str | None, origin: str | None, port: int) -> bool:
    """POST는 이 화면이 보낸 JSON만 받는다. 다른 웹페이지의 폼은 JSON 형식을 붙일 수 없고, 보내더라도 Origin이 다르다."""
    if not content_type or content_type.split(";")[0].strip().lower() != "application/json":
        return False
    return origin is None or origin in (f"http://{HOST}:{port}", f"http://localhost:{port}")


def make_handler(ctx: AppContext):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # 요청마다 찍히는 줄은 끈다
            pass

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method: str):
            port = self.server.server_port
            if not allowed_host(self.headers.get("Host"), port):
                return self._send(403, "text/plain; charset=utf-8", b"forbidden")
            body = None
            if method == "POST":
                if not allowed_post(self.headers.get("Content-Type"), self.headers.get("Origin"), port):
                    return self._send(403, "text/plain; charset=utf-8", b"forbidden")
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._send(*_json(413, {"error": "본문이 너무 깁니다"}))
                body = self.rfile.read(n)
            u = urlsplit(self.path)
            try:
                code, ctype, out = route(method, u.path, parse_qs(u.query), body, ctx)
            except Exception as e:        # 쓰는 중인 결과 파일 등. 화면에 원인을 보인다
                code, ctype, out = _json(500, {"error": f"{type(e).__name__}: {e}"})
            self._send(code, ctype, out)

        def _send(self, code: int, ctype: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="B 작업 화면: 점수판·두 실행 비교·원문 대조·작업·서버 (개발 전용)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default=HOST, help=f"{HOST}만 받는다. 쪽 글자·안내문이 화면에 보이기 때문이다 (D-47)")
    ap.add_argument("--runs-dir", type=Path, default=RUNS)
    ap.add_argument("--gold-dir", type=Path, default=SILVER / "claude", help="정답 자리 폴더 (기본: Claude 실버)")
    ap.add_argument("--pages-dir", type=Path, default=PAGES / "version9", help="쪽 글자·그림 폴더")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않는다")
    a = ap.parse_args(argv)
    if a.host != HOST:
        raise SystemExit(f"--host는 {HOST}만 받습니다 (받은 값: {a.host}). 쪽 글자·안내문이 화면에 보입니다 (D-47).")
    # 명령줄 도구는 늘 runs/에 쓴다. 다른 폴더를 보는 동안에는 진행·이름 검사가 어긋나므로 작업 탭을 끈다.
    # 서버 탭은 어느 폴더를 보든 켠다. 실행 중 잠금은 같은 JobManager의 running()으로 본다(ps로 다른 터미널의 실행도 본다)
    manager = bj.JobManager(RUNS / "manual" / "jobs", Path(sys.executable), BACKEND)
    jobs = manager if a.runs_dir.resolve() == RUNS.resolve() else None
    servers = bs.ServerActions(os.environ, manager, RUNS / "manual" / "server_log.md")   # 키는 .env(load_dotenv로 읽힘)에서만
    ctx = AppContext(runs_dir=a.runs_dir, gold_dir=a.gold_dir, pages_dir=a.pages_dir, jobs=jobs,
                     model_status=servers.model_status, servers=servers)
    server = ThreadingHTTPServer((HOST, a.port), make_handler(ctx))
    url = f"http://{HOST}:{server.server_port}/"
    print(f"작업 화면: {url}  (실행 폴더 {a.runs_dir}, 정답 {a.gold_dir})")
    print("Ctrl+C를 누르면 끝납니다.")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if jobs:
            jobs.list()                           # 끝난 작업의 상태를 남기고 임시 안내문 파일을 지운다
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
