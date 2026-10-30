"""작업 화면 서버 (역할 B, 개발 전용, ADR-025). 사용법: python scripts/b_app.py [--port 8765] [--no-browser]

내 컴퓨터(127.0.0.1)에서만 연다. 다른 주소에는 묶지 않는다. 쪽 글자·그림·안내문은 화면에만 보이고 파일로 남기지 않는다 (D-47).
표준 http.server만 쓴다. 요청 처리는 순수 함수 route()가 하고 핸들러는 그것을 부르기만 한다(시험은 route를 직접 부른다).
탭 ① 점수판은 b_app_runs의 요약을 보여 준다. 탭 ②~⑤와 도움말은 다음 step에서 채운다.
"""
import argparse
import json
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import yaml

import _common  # noqa: F401  src 경로 등록
import b_app_runs as br
from msds.common.paths import CONFIGS, PAGES, RUNS, SILVER
from msds.extract.section_runner import DOC_TIME_LIMIT

HOST = "127.0.0.1"
STATIC = Path(__file__).resolve().parent / "b_app_static"
GAPS_FILE = CONFIGS / "silver_gaps.yaml"
_HEAVY = ("details", "per_doc", "grid")              # /api/runs 목록에서 빼는 큰 칸. /api/run/<이름>에만 준다
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8"}
_LOCK = threading.Lock()                             # 요약 캐시 파일을 두 요청이 함께 쓰지 않게 한다


@dataclass
class AppContext:
    runs_dir: Path
    gold_dir: Path
    pages_dir: Path
    static_dir: Path = STATIC
    cache_dir: Path | None = br.CACHE_DIR
    gaps_file: Path = GAPS_FILE


def _json(code: int, obj) -> tuple[int, str, bytes]:
    return code, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False, default=str).encode()


def _static(rel: str, ctx: AppContext) -> tuple[int, str, bytes]:
    if ".." in rel or rel.startswith("/") or "\\" in rel:
        return _json(400, {"error": "잘못된 경로"})
    f = ctx.static_dir / rel
    if not f.is_file():
        return _json(404, {"error": f"없는 파일: {rel}"})
    return 200, _TYPES.get(f.suffix, "application/octet-stream"), f.read_bytes()


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


def route(method: str, path: str, query: dict[str, list[str]], body: bytes | None,
          ctx: AppContext) -> tuple[int, str, bytes]:
    """(상태 코드, Content-Type, 본문). path는 아직 % 풀기 전의 경로다."""
    path = unquote(path)
    if method != "GET":
        return _json(404, {"error": f"없는 주소: {method} {path}"})
    if path == "/":
        return _static("index.html", ctx)
    if path.startswith("/static/"):
        return _static(path[len("/static/"):], ctx)
    if path == "/api/runs":
        with _LOCK:
            data = br.load_all(ctx.runs_dir, ctx.gold_dir, cache_dir=ctx.cache_dir)
        runs = [{k: v for k, v in r.items() if k not in _HEAVY} for r in data["runs"]]
        return _json(200, {**data, "runs": runs, "current": pick_current(runs), "doc_time_limit": DOC_TIME_LIMIT})
    if path.startswith("/api/run/"):
        run = _run_paths(ctx).get(path[len("/api/run/"):])
        if run is None:
            return _json(404, {"error": f"없는 실행: {path[len('/api/run/'):]}"})
        with _LOCK:
            return _json(200, br.summarize_run(run, ctx.gold_dir, cache_dir=ctx.cache_dir))
    if path == "/api/criteria":
        return _json(200, br.criteria())
    if path == "/api/silver_gaps":
        return _json(200, _gaps(ctx))
    return _json(404, {"error": f"없는 주소: {path}"})


def allowed_host(host: str | None, port: int) -> bool:
    """다른 웹페이지가 다른 이름으로 이 화면을 부르지 못하게(DNS 재바인딩) Host가 내 컴퓨터일 때만 받는다."""
    return host in (f"{HOST}:{port}", f"localhost:{port}")


def make_handler(ctx: AppContext):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # 요청마다 찍히는 줄은 끈다
            pass

        def do_GET(self):
            if not allowed_host(self.headers.get("Host"), self.server.server_port):
                return self._send(403, "text/plain; charset=utf-8", b"forbidden")
            u = urlsplit(self.path)
            try:
                code, ctype, body = route("GET", u.path, parse_qs(u.query), None, ctx)
            except Exception as e:        # 쓰는 중인 결과 파일 등. 화면에 원인을 보인다
                code, ctype, body = _json(500, {"error": f"{type(e).__name__}: {e}"})
            self._send(code, ctype, body)

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
    ctx = AppContext(runs_dir=a.runs_dir, gold_dir=a.gold_dir, pages_dir=a.pages_dir)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
