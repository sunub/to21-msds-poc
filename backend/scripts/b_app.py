"""작업 화면 서버 (역할 B, 개발 전용, ADR-025). 사용법: python scripts/b_app.py [--port 8765] [--no-browser]

내 컴퓨터(127.0.0.1)에서만 연다. 다른 주소에는 묶지 않는다. 쪽 글자·그림·안내문은 화면에만 보이고 파일로 남기지 않는다 (D-47).
표준 http.server만 쓴다. 요청 처리는 순수 함수 route()가 하고 핸들러는 그것을 부르기만 한다(시험은 route를 직접 부른다).
탭 ① 점수판은 b_app_runs의 요약을, 탭 ② 두 실행 비교는 b_app_diff의 결과를, 탭 ③ 원문 대조는 b_app_doc의 결과를 보여 준다.
쪽 그림(/pages/<문서>/pNNN.png)은 요청 때 pages_dir(?set=이 있으면 그 묶음 폴더)에서 읽어 보낸다. 평가용 문서는 보내지 않는다 (D-43).
원문 대조는 그 실행이 실제로 쓴 입력 폴더(run_info.yaml의 pages_dir, prev/로 옮겨졌으면 그 자리)를 읽는다. 실행 없이도 연다.
탭 ④ 작업은 b_app_jobs의 JobManager로 시험·본 실행·비교표를 띄운다. POST는 같은 화면에서 보낸 JSON만 받는다(다른 웹페이지의
폼 보내기 막기). 안내문 글(/api/prompt)은 요청 때 만들어 보여 주기만 한다 (D-47).
탭 ⑤ 서버는 b_app_servers.ServerActions를 부른다. 바꾸는 동작은 propose(요약·확인 토큰) → execute(토큰) 두 단계이고,
이 앱이 만든 Pod의 주소·키는 작업을 띄울 때 그 작업의 환경에만 넣는다(파일에 쓰지 않는다). 도움말은 다음 step에서 채운다.
설정 다시 읽기(POST /api/servers/reload_env)는 .env를 다시 읽어 이 프로세스의 환경을 바꾸고 이름·줄 번호만 돌려준다(확인 토큰 없음).
문서 묶음(/api/sets)은 b_app_sets가 data/pages 아래에서 찾는다. 평가용 문서는 파일을 열지 않고 잠긴 이유만 준다 (D-43).
작업 POST는 본문의 set(묶음 id)을 목록에서 찾아 그 폴더를 쓴다. /api/options는 묶음별 문서의 작업 가능 여부와 이유를 준다.
정답지(/api/keys)는 b_app_sets가 data/silver·data/gold 아래에서 찾는다. 점수가 든 응답(/api/runs, /api/run, /api/diff,
/api/doc)은 ?key=로 고른 정답지로 채점하고 무엇과 비교했는지(key)를 붙인다. ?key=가 없으면 켤 때 받은 --gold-dir다.
요약 캐시와 실행 역사는 정답지별로 나눠 둔다(정답지를 오가도 서로 덮어쓰지 않는다).
실행마다 종류(run_kind, 사람 말 run_kind_label)와 비교 가능 여부(comparable)를 붙이고, 점수가 든 응답에는 두 목표(targets:
가중 종합 목표선, 필수 중 목표 달성 수)를 둔다. 처음 보여 줄 실행과 실행 역사의 최고 점수는 실버를 만든 실행을 뺀다.
없는 실행·묶음·정답지, 쪽 글자 없음, 잘못된 쿼리, 작업 POST의 ValueError 같은 400·404 본문에는 기존 error에 더해
사실 한 문장(message)과 할 일 한 문장(fix)을 둔다. 글은 b_app_text.problem이 만든다. 잠긴 문서의 404는 이유를 말하지 않는다.
"""
import argparse
import hashlib
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
from urllib.parse import parse_qs, quote, unquote, urlsplit

import yaml

import _common  # noqa: F401  src 경로 등록
import b_app_diff as bd
import b_app_doc as bdoc
import b_app_jobs as bj
import b_app_runs as br
import b_app_servers as bs
import b_app_sets as bsets
import b_app_text as bt
from msds.common import manifest
from msds.common.paths import BACKEND, CONFIGS, DATA, PAGES, ROOT, RUNS, SILVER
from msds.extract.client import load_model_config
from msds.extract.section_prompts import SECTION_PROMPT_VERSION, build_system, prompt_hash
from msds.extract.section_runner import DOC_TIME_LIMIT

HOST = "127.0.0.1"
STATIC = Path(__file__).resolve().parent / "b_app_static"
GAPS_FILE = CONFIGS / "silver_gaps.yaml"
GAPS_KEY = "silver/claude"                           # silver_gaps.yaml은 Claude 실버의 빈 곳만 적는다
_HEAVY = ("details", "per_doc", "grid")              # /api/runs 목록에서 빼는 큰 칸. /api/run/<이름>에만 준다
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8"}
_LOCK = threading.Lock()                             # 요약 캐시 파일을 두 요청이 함께 쓰지 않게 한다
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
    pages_root: Path | None = None                   # 문서 묶음을 찾는 곳(main은 data/pages). None이면 묶음 없이 pages_dir 하나만 쓴다
    model_status: Callable[[], list[dict]] | None = None   # 모델 서버 연결 상태 (ServerActions.model_status). 없으면 확인하지 않는다
    servers: bs.ServerActions | None = None          # 탭 ⑤ 서버. 없으면 서버 주소는 503
    last_model_connections: dict[str, bool] | None = None  # 마지막 조회 결과만. 점수 요청은 서버를 부르지 않는다
    run_history: dict[str, list[dict]] | None = None  # /api/runs가 읽은 가벼운 목록. 정답지 폴더(글자)별, 새로 읽을 때 갱신
    data_root: Path | None = None                    # 정답지(data/silver·gold)를 찾는 곳(main은 data/). None이면 gold_dir 하나만 쓴다


def _json(code: int, obj) -> tuple[int, str, bytes]:
    return code, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False, default=str).encode()


def _fail(code: int, kind: str, **facts) -> tuple[int, str, bytes]:
    """오류 응답 {error, message, fix}. 글은 b_app_text.problem에 있다."""
    return _json(code, bt.problem(kind, **facts))


class Problem(ValueError):
    """오류 본문(bt.problem)을 실은 ValueError. 글(str)은 본문의 error와 같다."""

    def __init__(self, kind: str, **facts):
        self.body = bt.problem(kind, **facts)
        super().__init__(self.body["error"])


def _problem_body(e: Exception) -> dict:
    """예외의 오류 본문. Problem이 아니면 예외 글을 사실로 두고 '입력을 고친 뒤 다시 보내세요'를 붙인다."""
    return e.body if isinstance(e, Problem) else bt.problem("bad_query", detail=str(e))


def _labeled_run(info: dict) -> dict:
    """채점·캐시는 그대로 두고 응답에만 표시 글을 붙인다."""
    return {**info, "label": bt.run_label(info), "model_label": bt.model_label(info.get("model_tag")),
            "run_kind_label": bt.run_kind_label(info.get("run_kind"))}


def _remember_connections(ctx: AppContext, models: list[dict]) -> None:
    ctx.last_model_connections = {m["tag"]: bool(m.get("reachable") and m.get("match")) for m in models}


class UnknownKey(Problem):
    """목록에 없는 정답지 id. GET은 404, 작업 POST는 400(다른 ValueError와 같이)."""


def _key_list(ctx: AppContext) -> list[dict]:
    return bsets.list_keys(Path(ctx.data_root)) if ctx.data_root is not None else []


def _pick_key(ctx: AppContext, want) -> tuple[Path, dict]:
    """(정답지 폴더, {"id", "label"}). want가 None이면 켤 때 받은 gold_dir. 목록 밖의 gold_dir는 그 id로도 다시 받는다.
    없는 id는 UnknownKey, 고를 수 없는 정답지는 ValueError. 요청의 글로 경로를 만들지 않는다(목록의 id만 경로로 바꾼다)."""
    keys = _key_list(ctx)
    startup = bsets.key_for_dir(keys, Path(ctx.gold_dir))
    if want is None or (startup["kind"] == "custom" and want == startup["id"]):
        return Path(ctx.gold_dir), {"id": startup["id"], "label": startup["label"]}
    k = bsets.find_key(keys, want)
    if k is None:
        raise UnknownKey("unknown_key", id=want)
    if not k["usable"]:
        raise Problem("unusable_key", reason=k["reason"])
    return bsets.key_dir(Path(ctx.data_root), k["id"]), {"id": k["id"], "label": k["label"]}


def _query_key(query: dict[str, list[str]], ctx: AppContext):
    """쿼리 key의 정답지. (폴더, key 정보, None) 또는 잘못되면 (None, None, 오류 응답)."""
    try:
        return (*_pick_key(ctx, (query.get("key") or [None])[0]), None)
    except UnknownKey as e:
        return None, None, _json(404, e.body)
    except ValueError as e:
        return None, None, _json(400, _problem_body(e))


def _cache_dir(ctx: AppContext, gold_dir: Path) -> Path | None:
    """정답지별 요약 캐시 폴더. b_app_runs의 캐시 파일 이름이 실행 이름뿐이라 폴더를 나눠야 서로 덮어쓰지 않는다."""
    if ctx.cache_dir is None:
        return None
    return Path(ctx.cache_dir) / hashlib.sha1(str(Path(gold_dir).resolve()).encode()).hexdigest()[:12]


def _run_list(ctx: AppContext, gold_dir: Path, key: dict) -> dict:
    data = br.load_all(ctx.runs_dir, gold_dir, cache_dir=_cache_dir(ctx, gold_dir), pages_root=ctx.pages_root)
    runs = [{**_labeled_run({k: v for k, v in r.items() if k not in _HEAVY}),
             "targets": bt.score_targets(r, data["criteria"])} for r in data["runs"]]
    ctx.run_history = {**(ctx.run_history or {}), str(gold_dir): runs}
    return {**data, "runs": runs, "current": pick_current(runs), "doc_time_limit": DOC_TIME_LIMIT, "key": key}


def _run_with_text(run: Path, ctx: AppContext, gold_dir: Path, key: dict) -> dict:
    info = _labeled_run(br.summarize_run(run, gold_dir, cache_dir=_cache_dir(ctx, gold_dir), pages_root=ctx.pages_root))
    runs = (ctx.run_history or {}).get(str(gold_dir))
    if runs is None:
        runs = _run_list(ctx, gold_dir, key)["runs"]
    connected = (ctx.last_model_connections or {}).get(info.get("model_tag"))
    # 지금 요청한 실행은 가장 최근 값을 쓴다. 원본 채점 dict와 캐시는 수정하지 않는다.
    history = [info if r["name"] == info["name"] else r for r in runs]
    summaries = {kind: bt.card_summary(kind, info) for kind in ("docs", "grid", "rows")}
    summaries["history"] = bt.card_summary("history", {"runs": history})
    status = bt.score_status(info, br.criteria(), connected=connected, per_doc=info.get("per_doc"))
    return {**info, "status_text": status, "targets": status["targets"],
            "card_summaries": summaries, "connection_notes": bt.connection_notes(info.get("model")), "key": key}


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
    """점수판이 처음 보여 줄 실행. runs는 load_all 순서(시작 시각 순)다. 실버를 만든 실행(run_kind silver)은 뺀다.
    비교 가능한(comparable) 실행 중 가장 최근 → 점수가 있는 실행 중 이름에 dev10이 든 가장 최근 → 점수가 있는 가장 최근
    → 가장 최근 실행 순이다. 실행이 하나라도 있으면 None을 돌려주지 않는다(실버뿐이면 실버, 비교표뿐이면 비교표)."""
    pool = [r for r in runs if r.get("kind") != "models" and r.get("run_kind") != "silver"]
    scored = [r for r in pool if r.get("weighted") is not None]
    found = ([r for r in pool if r.get("comparable")]
             or [r for r in scored if r["kind"] == "run" and "dev10" in r["name"]]
             or scored or pool or [r for r in runs if r.get("kind") != "models"] or runs)
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
        return _fail(400, "bad_query", detail="a와 b에 실행 이름을 둘 다 주세요"), None
    runs = _run_paths(ctx)
    missing = [n for n in names if n not in runs]
    if missing:
        return _fail(404, "missing_run", name=", ".join(missing)), None
    return None, [runs[n] for n in names]


def _prompt_diff(query: dict[str, list[str]], pair: list[Path], ctx: AppContext):
    no = (query.get("no") or [""])[0]
    if not (no.isascii() and no.isdigit() and 1 <= int(no) <= 16):
        return _fail(400, "bad_query", detail=f"no는 1~16 항 번호여야 합니다 (받은 값: {no})")
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


def _set_list(ctx: AppContext) -> list[dict]:
    return bsets.list_sets(Path(ctx.pages_root)) if ctx.pages_root is not None else []


def _page_png(rest: str, query: dict[str, list[str]], ctx: AppContext) -> tuple[int, str, bytes]:
    """/pages/<문서>/pNNN.png[?set=<묶음>]. 정규식 밖의 주소는 400, 없는 묶음·잠긴 문서·없는 쪽은 404."""
    parts = rest.split("/")
    if len(parts) != 2 or not bsets.DOC_ID.fullmatch(parts[0]) or not _PAGE_PNG.fullmatch(parts[1]):
        return _fail(400, "bad_query", detail="잘못된 쪽 그림 주소")
    # 없는 묶음·잠긴 문서·없는 쪽을 같은 본문으로 답한다(잠긴 이유를 말하지 않는다)
    not_found = _json(404, {**bt.problem("missing_pages", where=f"{parts[0]}/{parts[1]}"), "error": "없는 쪽 그림"})
    want = (query.get("set") or [None])[0]
    if want is None:
        folder = Path(ctx.pages_dir)
    elif bsets.find_set(_set_list(ctx), want) is None:
        return not_found
    else:
        folder = bsets.set_dir(Path(ctx.pages_root), want)
    f = folder / parts[0] / parts[1]
    if not bdoc.allowed_doc(parts[0], folder / parts[0]) or not f.is_file():
        return not_found
    return 200, "image/png", f.read_bytes()


def _doc_folder(doc_id: str, run: Path | None, want: str | None, ctx: AppContext, missing):
    """원문 대조가 읽을 쪽 글자 폴더와 응답의 set 정보. 고르는 순서: ?set= → 실행이 쓴 폴더 → 켤 때 받은 폴더 → 기본 묶음.
    잘못된 묶음이면 (None, 오류 응답). 묶음 id는 목록(find_set)에 있는 것만 경로로 바꾼다."""
    sets = _set_list(ctx)
    root = Path(ctx.pages_root) if ctx.pages_root is not None else None

    def picked(set_id, source, note=None):
        return bsets.set_dir(root, set_id), {"id": set_id, "label": bt.set_label(set_id), "source": source, "note": note}

    if want is not None:
        s = bsets.find_set(sets, want)
        if s is None:
            return None, _fail(404, "unknown_set", id=want)
        return picked(want, "param") if bsets.has_doc(s, doc_id) else (None, missing)
    recorded = None
    if run is not None:
        info = run / "run_info.yaml"
        recorded = (yaml.safe_load(info.read_text(encoding="utf-8")) or {}).get("pages_dir") if info.exists() else None
        set_id, source = bsets.resolve_run_set(recorded, doc_id, sets)
        if set_id is not None:
            note = bt.SET_TEXT["run_moved"].format(recorded=recorded, id=set_id) if source == "moved" else None
            return picked(set_id, source, note)
    startup = Path(ctx.pages_dir)
    here = startup.resolve()
    default = bsets.default_set(sets, startup, root) if sets else None
    if (startup / doc_id).is_dir() or default is None or not bsets.has_doc(bsets.find_set(sets, default), doc_id):
        # 켤 때 받은 폴더에 문서가 없고 기본 묶음에도 없으면 그 폴더를 그대로 읽는다(옛 동작: 없으면 '쪽 글자가 없습니다')
        set_id = next((s["id"] for s in sets if bsets.set_dir(root, s["id"]).resolve() == here), None)
        folder, info = startup, {"id": set_id, "label": bt.set_label(set_id) if set_id else startup.name,
                                 "source": "startup", "note": None}
    else:
        folder, info = picked(default, "default")
    if run is not None:
        info["note"] = bt.SET_TEXT["run_missing"].format(recorded=recorded or "기록 없음", name=info["label"])
    return folder, info


def _doc(query: dict[str, list[str]], ctx: AppContext) -> tuple[int, str, bytes]:
    """원문 대조. doc은 필수, run·set은 고를 수 있다. run이 없으면 결과 값 없이 쪽 글자만 보인다(신규 RAW-xx 보기)."""
    name, doc_id = [(query.get(k) or [""])[0] for k in ("run", "doc")]
    if not bsets.DOC_ID.fullmatch(doc_id):
        return _fail(400, "bad_query", detail="doc에 문서 번호(T21-…, RAW-…)를 주세요")
    run = None
    if name:
        run = _run_paths(ctx).get(name)
        if run is None:
            return _fail(404, "missing_run", name=name)
    # 평가용·용도를 모르는 문서도 같은 말로 돌려준다(이유를 말하지 않는다). 잠긴 이유는 /api/sets 목록이 보인다
    missing = _fail(404, "doc_not_in_run" if run else "doc_not_in_set", doc=doc_id)
    if run is not None and not (run / "outputs" / f"{doc_id}.json").is_file():
        return missing
    gold_dir, key, err = _query_key(query, ctx)
    if err:
        return err
    folder, info = _doc_folder(doc_id, run, (query.get("set") or [None])[0], ctx, missing)
    if folder is None:
        return info
    if not bdoc.allowed_doc(doc_id, folder / doc_id):
        return missing
    try:
        view = bdoc.doc_view(run, doc_id, folder, gold_dir) if run else bdoc.pages_view(doc_id, folder)
    except PermissionError:
        return missing
    except FileNotFoundError:
        return _fail(404, "missing_pages", where=f"{folder.name}/{doc_id}")
    return _json(200, {**view, "legend": bt.doc_legend(), "ui_text": bt.doc_ui_text(view), "set": info,
                       "image_base": f"/pages/{doc_id}/",
                       "image_query": f"?set={quote(info['id'], safe='')}" if info["id"] else "", "key": key})


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


def _runnable_sets(sets: list[dict]) -> list[dict]:
    """묶음 목록의 문서마다 작업에 넣을 수 있는지(runnable)와 이유(run_reason)를 더한다. 원래 목록은 바꾸지 않는다."""
    def doc(d: dict) -> dict:
        reasons = {kind: bsets.job_check(d, kind) for kind in ("try", "run")}
        return {**d, "runnable": {k: r is None for k, r in reasons.items()}, "run_reason": reasons}
    return [{**s, "docs": [doc(d) for d in s["docs"]]} for s in sets]


def _options(ctx: AppContext, *, advanced: bool = False) -> tuple[int, str, bytes]:
    """탭 ④의 고를 거리: 모델 태그(연결 여부), 개발용 문서, 쪽 폴더 후보(쓸 수 있는 문서 묶음), 묶음별 문서의 작업 가능 여부,
    추천 실행 이름."""
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
    if ctx.pages_root is None:
        found = [Path(ctx.pages_dir)] if Path(ctx.pages_dir).is_dir() else []
        pages = [{"name": p.name, "value": os.path.relpath(p, backend), "id": None} for p in found]
        sets, default_id = [], None
        default = pages[0]["value"] if pages else None
    else:
        root = Path(ctx.pages_root)
        sets = bsets.list_sets(root)
        pages = [{"name": s["label"], "value": os.path.relpath(bsets.set_dir(root, s["id"]), backend), "id": s["id"]}
                 for s in sets if s["usable"]]
        default_id = bsets.default_set(sets, Path(ctx.pages_dir), root)
        default = next((p["value"] for p in pages if p["id"] == default_id), None)
    names = {tag: {v["value"]: {purpose: bj.free_run_name(runs_dir, bj.suggest_run_name(
        tag, SECTION_PROMPT_VERSION, v["value"], purpose)) for purpose in ("dev10", "probe")} for v in pages}
        for tag in cfg}
    return _json(200, {"models": bt.order_models(models), "status_checked": status is not None, "ui_text": bt.server_ui_text(),
                       "field_help": bt.FIELD_HELP, "try_hint": bt.try_hint(models, advanced),
                       "try_stage_help": bt.TRY_STAGE_HELP, "job_ui_text": bt.JOB_UI_TEXT,
                       "docs": [{"doc_id": r["doc_id"], "pages": r.get("pages")} for r in manifest.select("개발")],
                       "pages_dirs": pages, "default_pages_dir": default, "prompt_version": SECTION_PROMPT_VERSION,
                       "run_names": names, "sets": _runnable_sets(sets), "default_set": default_id,
                       "outside_run_support": bsets.outside_run_support()})


def _sets(ctx: AppContext) -> tuple[int, str, bytes]:
    """data/pages 아래의 문서 묶음과 기본 묶음. pages_root가 없으면 빈 목록이다."""
    if ctx.pages_root is None:
        return _json(200, {"sets": [], "default": None})
    root = Path(ctx.pages_root)
    sets = bsets.list_sets(root)
    return _json(200, {"sets": sets, "default": bsets.default_set(sets, ctx.pages_dir, root)})


def _keys(ctx: AppContext) -> tuple[int, str, bytes]:
    """data/silver·data/gold 아래의 정답지와 기본 정답지. data_root가 없으면 빈 목록과 켤 때 받은 폴더의 id다."""
    keys = _key_list(ctx)
    return _json(200, {"keys": keys, "default": bsets.default_key(keys, Path(ctx.gold_dir))})


def _silver_gaps(query: dict[str, list[str]], ctx: AppContext) -> tuple[int, str, bytes]:
    """key가 없으면 지금처럼 목록(배열). 있으면 {key, gaps}이고, Claude 실버가 아닌 정답지의 gaps는 비어 있다."""
    if not query.get("key"):
        return _json(200, _gaps(ctx))
    _, key, err = _query_key(query, ctx)
    if err:
        return err
    return _json(200, {"key": key, "gaps": _gaps(ctx) if key["id"] == GAPS_KEY else []})


def _prompt(query: dict[str, list[str]]) -> tuple[int, str, bytes]:
    """그 모델 태그가 no항에 보내는 안내문 글. 화면의 글상자에 채울 때만 쓴다. 파일로 남기지 않는다 (D-47)."""
    tag, no = [(query.get(k) or [""])[0] for k in ("model", "no")]
    if not (no.isascii() and no.isdigit() and 1 <= int(no) <= 16):
        return _fail(400, "bad_query", detail=f"no는 1~16 항 번호여야 합니다 (받은 값: {no})")
    try:
        cfg = load_model_config(tag)
    except KeyError:
        return _fail(400, "bad_query", detail=f"configs/models.yaml에 없는 모델 태그: {tag}")
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
        return _fail(400, "bad_query", detail=f"lines는 숫자여야 합니다 (받은 값: {lines})")
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
    """탭 ⑤의 두 단계와 설정 다시 읽기. 결과 dict의 code(없으면 200)를 상태 코드로 쓴다. 토큰이 틀리면 400, 지났으면 410, 실행 중이면 409."""
    if ctx.servers is None:
        return _json(503, {"error": "서버 탭이 꺼져 있습니다"})
    data = _body(body)
    if data is None:
        return _fail(400, "bad_query", detail="본문은 JSON 객체여야 합니다")
    if path == "/api/servers/propose":
        res = ctx.servers.propose(data.get("action"), data.get("params"))
    elif path == "/api/servers/execute":
        res = ctx.servers.execute(data.get("token"))
    elif path == "/api/servers/reload_env":          # 돈·서버를 바꾸지 않아 확인 토큰을 받지 않는다
        res = ctx.servers.reload_env()
    else:
        return _json(404, {"error": f"없는 주소: POST {path}"})
    res = dict(res)
    return _json(res.pop("code", 200), res)


def _job_pages_dir(data: dict, ctx: AppContext):
    """작업 본문의 쪽 폴더. set(묶음 id)이 있으면 목록(find_set)에서 찾은 그 묶음 폴더(backend 기준), 없으면 pages_dir 그대로.
    목록에 없는 id는 ValueError(400). 요청의 글로 경로를 직접 만들지 않는다."""
    want = data.get("set")
    if want is None:
        return data.get("pages_dir")
    s = bsets.find_set(_set_list(ctx), want)
    if s is None:
        raise Problem("unknown_set", id=want)
    return os.path.relpath(bsets.set_dir(Path(ctx.pages_root), s["id"]), ctx.jobs.backend_dir)


def _post(path: str, body: bytes | None, ctx: AppContext) -> tuple[int, str, bytes]:
    if path.startswith("/api/servers/"):
        return _server_post(path, body, ctx)
    if ctx.jobs is None:
        return _json(503, {"error": "작업 탭이 꺼져 있습니다(--runs-dir를 기본 runs/가 아닌 곳으로 주면 꺼집니다)"})
    data = _body(body)
    if data is None:
        return _fail(400, "bad_query", detail="본문은 JSON 객체여야 합니다")
    jobs = ctx.jobs
    extra_env = ctx.servers.job_env() if ctx.servers else None   # 이 앱이 만든 Pod의 주소·키. 작업 환경에만 넣는다
    try:
        if path == "/api/jobs/try":
            want = data.get("key") or None               # 정답지(시험의 점수 전→후). 없으면 try_section의 기본
            gold_dir = os.path.relpath(_pick_key(ctx, want)[0], jobs.backend_dir) if want is not None else None
            job = jobs.start_try(model=data.get("model"), doc=data.get("doc"), sections=data.get("sections"),
                                 all_=bool(data.get("all")), pages_dir=_job_pages_dir(data, ctx),
                                 system_text=data.get("system_text"), base_run=data.get("base_run") or None,
                                 dry_run=bool(data.get("dry_run")), extra_env=extra_env, gold_dir=gold_dir)
            return _json(200, {"id": job.id})
        if path == "/api/jobs/run":
            args = {**{k: data.get(k) for k in ("model", "docs", "run_name", "repeat")},
                    "pages_dir": _job_pages_dir(data, ctx)}
            summary = jobs.run_summary(**args)
            if data.get("confirm") is not True:         # 오래 돌고 서버 비용이 드는 작업이라 요약을 보고 한 번 더 누른다
                return _json(409, {"summary": summary, "needs_confirm": True})
            return _json(200, {"id": jobs.start_run(**args, extra_env=extra_env)[0].id, "summary": summary})
        if path == "/api/jobs/compare":
            job = jobs.start_compare(title=data.get("title"), runs=data.get("runs"), labels=data.get("labels"))
            return _json(200, {"id": job.id})
    except (ValueError, TypeError) as e:
        return _json(400, _problem_body(e))
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
        gold_dir, key, err = _query_key(query, ctx)
        if err:
            return err
        with _LOCK:
            return _json(200, _run_list(ctx, gold_dir, key))
    if path.startswith("/api/run/"):
        run = _run_paths(ctx).get(path[len("/api/run/"):])
        if run is None:
            return _fail(404, "missing_run", name=path[len("/api/run/"):])
        gold_dir, key, err = _query_key(query, ctx)
        if err:
            return err
        with _LOCK:
            return _json(200, _run_with_text(run, ctx, gold_dir, key))
    if path in ("/api/diff", "/api/prompt_diff"):
        err, pair = _pair(query, ctx)
        if err:
            return err
        if path == "/api/prompt_diff":
            return _prompt_diff(query, pair, ctx)
        gold_dir, key, err = _query_key(query, ctx)
        if err:
            return err
        with _LOCK:
            a, b = [br.summarize_run(p, gold_dir, cache_dir=_cache_dir(ctx, gold_dir), pages_root=ctx.pages_root)
                    for p in pair]
        diff = bd.diff_runs(a, b)
        criteria = br.criteria()
        return _json(200, {**diff, "headline": bt.diff_headline(diff, bt.run_label(a)["title"], bt.run_label(b)["title"]),
                           "ui_text": bt.diff_ui_text(diff), "key": key,
                           "targets": {"a": bt.score_targets(a, criteria), "b": bt.score_targets(b, criteria)}})
    if path == "/api/doc":
        return _doc(query, ctx)
    if path.startswith("/pages/"):
        return _page_png(path[len("/pages/"):], query, ctx)
    if path == "/api/jobs" or path.startswith("/api/jobs/"):
        if ctx.jobs is None:
            return _json(503, {"error": "작업 탭이 꺼져 있습니다(--runs-dir를 기본 runs/가 아닌 곳으로 주면 꺼집니다)"})
        return _job_get(path, query, ctx)
    if path == "/api/sets":
        return _sets(ctx)
    if path == "/api/keys":
        return _keys(ctx)
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
        return _silver_gaps(query, ctx)
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
    ap.add_argument("--gold-dir", type=Path, default=SILVER / "claude",
                    help="기본 정답지 폴더 (기본: Claude 실버). 화면에서는 data/silver·data/gold 아래 정답지를 고른다")
    ap.add_argument("--pages-dir", type=Path, default=PAGES / "prev" / "version9",
                    help="쪽 글자·그림 폴더 (기본: C의 version9, data/pages/prev/version9)")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않는다")
    a = ap.parse_args(argv)
    if a.host != HOST:
        raise SystemExit(f"--host는 {HOST}만 받습니다 (받은 값: {a.host}). 쪽 글자·안내문이 화면에 보입니다 (D-47).")
    # 명령줄 도구는 늘 runs/에 쓴다. 다른 폴더를 보는 동안에는 진행·이름 검사가 어긋나므로 작업 탭을 끈다.
    # 서버 탭은 어느 폴더를 보든 켠다. 실행 중 잠금은 같은 JobManager의 running()으로 본다(ps로 다른 터미널의 실행도 본다)
    manager = bj.JobManager(RUNS / "manual" / "jobs", Path(sys.executable), BACKEND)
    jobs = manager if a.runs_dir.resolve() == RUNS.resolve() else None
    # 키는 .env에서만: 켤 때 load_dotenv, 그 뒤 '설정 다시 읽기'. 켤 때 네트워크는 부르지 않는다(Pod 이어 쓰기는 첫 요청 때)
    servers = bs.ServerActions(os.environ, manager, RUNS / "manual" / "server_log.md", env_file=bs.ENV_FILE)
    ctx = AppContext(runs_dir=a.runs_dir, gold_dir=a.gold_dir, pages_dir=a.pages_dir, jobs=jobs,
                     pages_root=PAGES, model_status=servers.model_status, servers=servers, data_root=DATA)
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
