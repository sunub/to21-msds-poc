"""작업 화면 탭 ⑤ 서버: 모델 서버 상태, RNGD ssh 작업, RunPod Pod, 사용 기록 (개발 전용, ADR-025).

낮은 층(model_status, rngd_*, tunnel_*, port_open, append_server_log)과 그 위의 상태 기계 ServerActions가 있다.
ServerActions의 변경 동작(Pod 만들기·지우기, RNGD 올리기·내리기, RNGD 터널 열기·닫기)은 두 단계다: propose가 요약과
1회용 확인 토큰을 주고, execute가 그 토큰으로 실행한다. run_sections.py·try_section.py가 돌고 있으면 두 단계 모두 409로 막는다.
터널 열기만은 막지 않는다(돌고 있는 실행을 해치지 않는다).
RNGD 터널은 내 컴퓨터 포트(RNGD_BASE_URL의 포트) → RNGD 8000번이다. 앱이 연 ssh는 새 세션이라 앱을 꺼도 살고,
앱을 다시 켜면 ps 줄(ssh -N -L <포트>:127.0.0.1:…)로 이어 받는다. 명령 줄 인자(키 파일 경로)는 응답·기록에 쓰지 않는다.
키는 반환값·예외·기록 어디에도 쓰지 않는다. Pod에 넣는 vLLM 키는 .env의 RUNPOD_VLLM_API_KEY이고 세션에 두지 않는다(부를 때마다 읽는다).
앱을 다시 켜면 첫 요청 때 이 앱이 만든 켜진 Pod(이름이 OURS로 시작)를 찾아 이어 쓴다. 앱이 만들지 않은 Pod는 지우지 않는다(403).
.env는 reload_env로 앱을 끄지 않고 다시 읽는다(읽기만 하고 쓰지 않는다. 돌려주는 것은 이름과 줄 번호뿐이다).
시험은 opener·runner·watchdog_spawner·clock·tunnel_spawner·connector·ps·killer와 tmp_path의 가짜 .env를 끼운다.
"""
import json
import os
import re
import secrets
import shlex
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping
from urllib.parse import urlsplit

import yaml
from dotenv.parser import parse_stream

import _common  # noqa: F401  src 경로 등록
import b_app_jobs as bj
import b_app_text as bt
import pod
from msds.common.paths import CONFIGS, ROOT

ENV_FILE = ROOT / ".env"
SERVER_ENV_PREFIXES = ("RNGD_", "RUNPOD_")          # VLLM_ 태그(qwen38)는 명령줄 기준선 실행 전용이라 앱이 지켜보지 않는다
REMOTE_DIR = "/root/to21-bc"
_SAFE_MODEL = re.compile(r"^[\w./:-]+$")
_SAFE_DEVICES = re.compile(r"^[\w:,]+$")
_SAFE_LOG = re.compile(r"^[\w.-]+$")
_SECRET_FIELD = re.compile(r"key|secret|token|password", re.I)


def mask_keys(text: str, secrets: Iterable[str] = ()) -> str:
    text = re.sub(r"(--api-key(?:\s+|=))(\"[^\"]*\"|'[^']*'|\S+)", r"\1***", text)
    text = re.sub(r"(Bearer\s+)\S+", r"\1***", text, flags=re.I)
    text = re.sub(r"\b(?:sk|rpa|hf)[-_][A-Za-z0-9_-]{8,}", "***", text)
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def model_status(tag: str, cfg: dict, env: Mapping[str, str], *, opener=None, timeout=5) -> dict:
    out = {"tag": tag, "model_expected": cfg["model"], "url_set": False, "reachable": False,
           "model_served": None, "match": None, "error": None}
    base = env.get(cfg["base_url_env"])
    if not base:
        out["friendly"] = bt.friendly_error("env", "주소 설정 없음", {"base_url": cfg["base_url_env"]})
        return out
    out["url_set"] = True
    headers = {"User-Agent": "to21-b-app/1.0"}
    key = env.get(cfg["api_key_env"])
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base.rstrip("/") + "/models", headers=headers)
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as e:  # 키가 메시지에 섞일 수 있어 종류만 남긴다
        code = getattr(e, "code", None)
        out["error"] = f"HTTP {code}" if code else type(e).__name__
        reason = getattr(e, "reason", None)
        raw = out["error"] + (f": {type(reason).__name__}" if isinstance(reason, Exception) else "")
        out["friendly"] = bt.friendly_error("model", raw)
        return out
    out["reachable"] = True
    ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
    if ids:
        out["match"] = cfg["model"] in ids
        out["model_served"] = cfg["model"] if out["match"] else ids[0]
    return out


def all_model_status(models_cfg: dict, env, *, opener=None) -> list[dict]:
    return [model_status(tag, c, env, opener=opener) for tag, c in models_cfg["models"].items()
            if str(c.get("base_url_env", "")).startswith(SERVER_ENV_PREFIXES)]


def _ssh_target(env) -> list[str]:
    """RNGD_SSH의 접속 인자. 앞의 "ssh"는 뗀다. 없으면 []."""
    args = shlex.split(env.get("RNGD_SSH") or "")
    return args[1:] if args and args[0] == "ssh" else args


def rngd_ssh_args(env) -> list[str] | None:
    args = _ssh_target(env)
    return ["ssh", "-n", "-o", "BatchMode=yes", *args] if args else None


RNGD_REMOTE_PORT = 8000                              # rngd_up의 --port 8000과 같다
RNGD_URL_ENV = "RNGD_BASE_URL"                       # models.yaml의 RNGD 태그 base_url_env


def tunnel_port(env) -> int | None:
    """RNGD_BASE_URL이 내 컴퓨터 주소(127.0.0.1·localhost)이고 포트가 있으면 그 포트. 아니면 None."""
    try:
        u = urlsplit(env.get(RNGD_URL_ENV) or "")
        return u.port if u.hostname in ("127.0.0.1", "localhost") else None
    except ValueError:                               # 포트가 숫자가 아니다
        return None


def tunnel_args(env) -> list[str] | None:
    """내 컴퓨터 포트 → RNGD 8000번 터널의 ssh 명령. RNGD_SSH나 포트가 없으면 None. 키 값은 넣지 않는다."""
    port, target = tunnel_port(env), _ssh_target(env)
    if port is None or not target:
        return None
    return ["ssh", "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
            "-L", f"{port}:127.0.0.1:{RNGD_REMOTE_PORT}", *target]


def port_open(port: int, *, connector=None, timeout: float = 0.5) -> bool:
    """127.0.0.1:port에 TCP 연결이 되는가. 거부·권한·시간 초과(OSError)는 모두 False."""
    try:
        conn = (connector or socket.create_connection)(("127.0.0.1", port), timeout=timeout)
    except OSError:
        return False
    conn.close()
    return True


def tunnel_ps_pids(ps_text: str, port: int) -> list[int]:
    """ps 글(pid pgid command, b_app_jobs._ps_text 모양)에서 ssh -N -L <port>:127.0.0.1:… 줄의 pid."""
    pids = []
    for line in ps_text.splitlines():
        m = re.match(r"\s*(\d+)\s+\d+\s+(.*)", line)
        tokens = m[2].split() if m else []
        if not tokens or os.path.basename(tokens[0]) != "ssh" or "-N" not in tokens:
            continue
        if any(a == "-L" and b.startswith(f"{port}:127.0.0.1:") for a, b in zip(tokens, tokens[1:])):
            pids.append(int(m[1]))
    return pids


def _run(args, timeout):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _remote(env, command, runner, timeout=30):
    """(ok, stdout, error). ssh 인자 + 원격 명령 한 덩어리."""
    args = rngd_ssh_args(env)
    if args is None:
        return False, "", "RNGD_SSH 없음"
    try:
        code, out, err = (runner or _run)([*args, command], timeout)
    except Exception as e:
        return False, "", type(e).__name__
    if code != 0:
        return False, mask_keys(out, []), mask_keys(err.strip()[:200], [])
    return True, out, None


def rngd_ps(env, *, runner=None) -> dict:
    """models: [{"pid", "model", "elapsed_s"}]. elapsed_s는 프로세스가 뜬 뒤 지난 초(ps etimes). 옛 모양(pid comm args)이면 None."""
    ok, out, err = _remote(env, "furiosa-smi ps; ps -eo pid,etimes,comm,args | grep -i [f]uriosa-llm", runner)
    if err == "RNGD_SSH 없음" or (not ok and not out):
        return {"ok": False, "text": "", "models": [], "error": err}
    text = mask_keys(out, [])
    models = [{"pid": int(m.group(1)), "model": m.group(3), "elapsed_s": int(m.group(2)) if m.group(2) else None}
              for m in re.finditer(r"^\s*(\d+)\s+(?:(\d+)\s+)?\S+\s+.*furiosa-llm serve (\S+)", text, re.M)]
    # grep이 아무것도 못 찾으면 종료 코드 1이라도 smi 출력은 쓴다
    return {"ok": True, "text": text, "models": models, "error": None}


def rngd_down(model: str, env, *, runner=None, sleep=time.sleep) -> dict:
    if not _SAFE_MODEL.match(model):
        return {"ok": False, "killed": [], "remaining": [], "error": "모델 이름 형식 오류"}
    pattern = shlex.quote(f"[f]uriosa-llm serve {model}")
    ok, out, err = _remote(env, f"pgrep -f {pattern}", runner)
    if err == "RNGD_SSH 없음":
        return {"ok": False, "killed": [], "remaining": [], "error": err}
    pids = [int(x) for x in out.split() if x.isdigit()]
    if not pids:
        return {"ok": True, "killed": [], "remaining": [], "error": None}
    ok, _, err = _remote(env, "kill -TERM " + " ".join(map(str, pids)), runner)
    if not ok:
        return {"ok": False, "killed": [], "remaining": pids, "error": err}
    sleep(5)
    ps = rngd_ps(env, runner=runner)
    remaining = [m["pid"] for m in ps["models"] if m["model"] == model]
    return {"ok": not remaining, "killed": pids, "remaining": remaining, "error": None}


def rngd_up(model: str, devices: str, env, *, log_name: str, runner=None) -> dict:
    if not (_SAFE_MODEL.match(model) and _SAFE_DEVICES.match(devices) and _SAFE_LOG.match(log_name)):
        return {"ok": False, "error": "모델·장치·로그 이름 형식 오류"}
    cmd = (f"cd {REMOTE_DIR} && setsid nohup /usr/local/bin/furiosa-llm serve {model} --devices {devices} "
           f"--host 127.0.0.1 --port 8000 --api-key \"$(cat {REMOTE_DIR}/api_key)\" "
           f"> {REMOTE_DIR}/{log_name}.log 2>&1 < /dev/null & disown")
    ok, _, err = _remote(env, cmd, runner)
    return {"ok": ok, "error": err}


def append_server_log(log_path: Path, action: str, *, _secrets: Iterable[str] = (), **fields) -> str:
    """runs/manual/server_log.md에 표 한 줄을 더하고 그 줄을 돌려준다 (사람이 docs/plan/RunPod_사용기록.md로 옮긴다)."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def cell(v):
        return mask_keys(str(v), _secrets).replace("|", "/").replace("\n", " ")

    target = fields.pop("target", "")
    note = fields.pop("note", "")
    extra = [f"{k}={'***' if _SECRET_FIELD.search(k) else v}" for k, v in fields.items()]
    row = "| " + " | ".join(cell(x) for x in (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action, target,
                                              " ".join([str(note), *extra]).strip())) + " |\n"
    new = not log_path.exists()
    with open(log_path, "a", encoding="utf-8") as f:
        if new:
            f.write("| 시각 | 동작 | 대상 | 비고 |\n|---|---|---|---|\n")
        f.write(row)
    return row.rstrip("\n")


def read_env_file(path: Path) -> tuple[dict[str, str], list[int]]:
    """.env를 python-dotenv의 파서로 읽는다: (이름→값, 읽지 못한 줄 번호). 줄의 글은 돌려주지 않는다. 파일이 없으면 ({}, []).

    ${이름} 끼워 넣기는 풀지 않는다(load_dotenv와 다름. 10/31 .env에는 없다)."""
    path = Path(path)
    if not path.is_file():
        return {}, []
    values, problems = {}, []
    with open(path, encoding="utf-8") as f:
        for b in parse_stream(f):
            if b.error:
                problems.append(b.original.line)
            elif b.key is not None and b.value is not None:   # "이름"만 있고 =가 없는 줄은 load_dotenv처럼 건너뛴다
                values[b.key] = b.value
    return values, problems


def apply_env_file(path: Path, environ: MutableMapping[str, str], previous: set[str]) -> dict:
    """파일 값으로 environ을 덮어쓰고, previous(지난번 파일의 이름)에 있었는데 파일에서 빠진 이름은 지운다. 값은 담지 않는다."""
    values, problems = read_env_file(path)
    changed = sorted(k for k, v in values.items() if environ.get(k) != v)
    removed = sorted(k for k in set(previous) - set(values) if k in environ)
    for k in changed:
        environ[k] = values[k]
    for k in removed:
        del environ[k]
    return {"names": sorted(values), "changed": changed, "removed": removed, "problems": problems}


# ── 탭 ⑤의 상태 기계: 요약과 확인 토큰 → 실행 ─────────────────

ACTIONS = ("pod_create", "pod_delete", "rngd_up", "rngd_down", "tunnel_open", "tunnel_close")
UNLOCKED_ACTIONS = ("tunnel_open",)                  # 실행이 돌고 있어도 되는 동작 (여는 것은 실행을 해치지 않는다)
OURS = "to21-b-"                                     # 이 도구가 만든 Pod 이름의 앞부분
POD_NAME = "to21-b-qwen36"
POD_TAG = "qwen36_35b_runpod"                        # Pod가 띄우는 모델의 태그. 모델 이름·주소 변수는 models.yaml에서 읽는다
POD_GPU = "RTX PRO 6000 1장"                          # pod.create_pod의 기본 GPU
POD_COST_HINT = 2.49                                 # 시간당 달러. 10/29 보안 클라우드 기록 (RunPod_사용기록)
POD_KEY_ENV = "RUNPOD_VLLM_API_KEY"                  # Pod의 vLLM 키. Pod 환경(VLLM_API_KEY)과 작업·연결 확인에 같은 .env 값을 쓴다
ADOPT_EVERY = 30                                     # 이 앱이 전에 만든 Pod를 찾는 목록 요청 간격(초)
# 10/29 인계 문서의 시작 줄 + 2항 쪽 이미지 2장 (ADR-019). 키는 Pod 안의 환경 변수로만 받는다
POD_SERVE = ('vllm serve {model} --trust-remote-code --host 0.0.0.0 --port 8000 --api-key "$VLLM_API_KEY" '
             "--max-model-len 40960 --max-num-seqs 64 --gpu-memory-utilization 0.85 "
             "--limit-mm-per-prompt '{{\"image\": 2}}'")
WATCHDOG_SECONDS = 14400                             # Pod를 만들고 4시간이 지나면 지운다 (지우기를 잊어도 과금이 멈추게)
TOKEN_TTL = 600                                      # 확인 토큰 유효 시간(초)
DELETE_WAIT = 5                                      # Pod를 지운 뒤 목록을 다시 볼 때까지(초)
RELOAD_TEXT = "다시 띄우면 15~25분 걸립니다"
RNGD_UP = {"qwen3_30b_a3b_rngd": ("Qwen3-30B", "npu:0,npu:1,npu:2,npu:3"),   # 태그 → (단추 이름, 카드). 카드는 4장뿐이다
           "gpt_oss_20b_rngd": ("gpt-oss", "npu:0")}
LOCKING_KINDS = ("run", "try")                       # 모델 서버를 쓰는 작업. 비교표는 서버를 쓰지 않아 막지 않는다
TUNNEL_WAIT, TUNNEL_STEP = 10, 0.5                   # 터널 포트가 열리기·닫히기를 기다리는 최대 초와 간격
_POD_ID = re.compile(r"^[a-z0-9]{6,40}$")
_SECRET_PREFIXES = ("RNGD_", "RUNPOD_", "VLLM_", "LLM_", "ANTHROPIC_")
_WHERE = (("RUNPOD_", "RunPod"), ("RNGD_", "RNGD"))


class _Refuse(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _spawn_watchdog(argv: list[str], cwd: Path) -> bj._Group:
    """앱을 꺼도 살아 있게 새 세션으로 띄운다. 출력은 버린다(pod.py delete는 키를 찍지 않는다)."""
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    return bj._Group(proc)


def _spawn_tunnel(argv: list[str]) -> subprocess.Popen:
    """ssh 터널. 앱을 꺼도 살아 있게 새 세션으로 띄우고 입출력은 버린다(다시 켜면 ps 줄로 이어 받는다)."""
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def _local_iso(ts: float) -> str:
    """로컬 시각 ISO 글 (터널을 연 시각, 모델을 올리기 시작한 시각)."""
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def diagnose_rngd(ps: dict, tunnel: dict, models: list[dict]) -> str | None:
    """RNGD 상태 진단. 위에서부터: 떠 있는 모델 없음 → 터널 닫힘 → 기대 모델 응답 → 모델 프로세스만 있음(올리는 중) → 모름(None).
    ps는 rngd_ps, tunnel은 tunnel_status, models는 where가 붙은 model_status 결과다. 주소가 있는 RNGD 태그만 본다.
    서버가 HTTP로 답했으면(예: 401) 올리는 중이 아니라 다른 원인이라 None이다(기존 오류 글이 원인을 말한다)."""
    if ps["ok"] and not ps["models"]:
        return "no_model"
    if tunnel["port"] is not None and not tunnel["open"]:
        return "tunnel_closed"
    rngd = [m for m in models if m.get("where") == "RNGD" and m.get("url_set")]
    if any(m["reachable"] and m["match"] for m in rngd):
        return "ok"
    answered = any(m["reachable"] or str(m.get("error") or "").startswith("HTTP ") for m in rngd)
    if ps["ok"] and rngd and not answered:
        return "loading"
    return None


def _running_text(r: dict) -> str:
    kind = {"run": "본 실행", "try": "시험"}.get(r.get("kind"), r.get("kind"))
    what = r.get("run_name") or r.get("label") or r.get("doc") or f"pid {r.get('pid')}"
    return f"{kind} {what} — 돌고 있음"


def _owned(p: dict) -> bool:
    """이 앱이 만든 Pod인가 (이름 태그 OURS)."""
    return str(p.get("name") or "").startswith(OURS)


def _minutes_cost(b: dict, prefix: str) -> str:
    mins = f"{prefix} {b['minutes']:.0f}분" if b.get("minutes") is not None else "켜진 시간 모름"
    cost = f"추정 ${b['est_cost']:.2f}" if b.get("est_cost") is not None else "추정 비용 모름"
    return f"{mins}, {cost}"


class ServerActions:
    """탭 ⑤의 서버 동작. 확인 토큰, 이 앱이 쓰는 Pod 세션(키는 두지 않음), 감시 프로세스는 이 객체의 메모리에만 있다.

    propose·execute는 dict를 돌려준다. 실패하면 "code"(400·403·404·409·410·502)와 "error"가 있고, 앱 라우트가 code를 상태 코드로 쓴다.
    env는 앱에서 os.environ이다. reload_env가 같은 객체를 바꿔야 이후 연결 확인과 작업(자식 프로세스)이 새 값을 쓴다.
    """

    def __init__(self, env: MutableMapping[str, str], jobs: "bj.JobManager", log_path: Path, *, opener=None, runner=None,
                 watchdog_spawner=None, clock=None, sleep=None, models_cfg: dict | None = None,
                 env_file: Path | None = None, tunnel_spawner=None, connector=None, ps=None, killer=None):
        self.env, self.jobs, self.log_path = env, jobs, Path(log_path)
        self._opener, self._runner = opener, runner
        self._watchdog_spawner = watchdog_spawner or _spawn_watchdog
        self._tunnel_spawner, self._connector = tunnel_spawner or _spawn_tunnel, connector or socket.create_connection
        self._ps, self._killer = ps or bj._ps_text, killer or os.kill
        self._tunnel: dict | None = None             # 이 앱이 연 터널 {"proc", "port", "started"(clock 값)}
        self._clock, self._sleep = clock or time.time, sleep or time.sleep
        self.models_cfg = models_cfg or yaml.safe_load((CONFIGS / "models.yaml").read_text(encoding="utf-8"))
        self._tokens: dict[str, dict] = {}
        self.env_file = Path(env_file) if env_file else None
        self._env_names = set(read_env_file(self.env_file)[0]) if self.env_file else set()   # 다시 읽을 때 빠진 이름을 지우려고
        # 이 앱이 쓰는 Pod {"pod_id", "created", "adopted"(다시 켠 뒤 찾은 것인가), "others"(찾은 나머지)}. 키는 두지 않는다
        self._session: dict | None = None
        self._adopt_checked: float | None = None     # 마지막으로 Pod 목록에서 이어 쓸 Pod를 찾은 시각
        self._watchdogs: dict[str, dict] = {}        # Pod 번호 → {"proc", "deadline"}
        self._lock = threading.Lock()

    # ── 읽기 ───────────────────────────────────────────

    def job_env(self) -> dict[str, str]:
        """작업(run_sections·try_section)과 연결 확인에 쓸 Pod 주소·키. 이 앱의 Pod가 없거나 .env에 Pod 키가 없으면 빈 dict.
        키는 부를 때마다 env에서 읽는다(설정 다시 읽기를 따라간다)."""
        self._ensure_session()
        s, key = self._session, self.env.get(POD_KEY_ENV)
        if not s or not key:
            return {}
        cfg = self.models_cfg["models"][POD_TAG]
        return {cfg["base_url_env"]: pod.pod_url(s["pod_id"]), cfg["api_key_env"]: key}

    def model_status(self) -> list[dict]:
        """all_model_status에 서버 종류(where)를 붙인다. 이 앱이 만든 Pod가 있으면 .env의 RunPod 주소 대신 그 Pod를 본다."""
        cfg = self.models_cfg["models"]
        out = all_model_status(self.models_cfg, {**self.env, **self.job_env()}, opener=self._opener)
        for s in out:
            name = str(cfg[s["tag"]].get("base_url_env", ""))
            s["where"] = next((w for p, w in _WHERE if name.startswith(p)), name)
        return out

    def tunnel_status(self) -> dict:
        """RNGD 터널: 포트, 열림, 이 앱의 것인가(앱이 띄운 ssh가 살아 있거나 ps에 ssh -N -L <포트>:127.0.0.1: 줄이 있음),
        pid, since(앱이 연 터널이 열려 있을 때만 연 시각, 로컬 ISO). 명령 줄 인자는 담지 않는다."""
        port = tunnel_port(self.env)
        out = {"port": port, "open": False, "owned": False, "pid": None, "since": None}
        if port is None:
            return out
        out["open"] = port_open(port, connector=self._connector)
        mine = self._app_tunnel(port)
        if mine:
            out.update(owned=True, pid=mine["proc"].pid, since=_local_iso(mine["started"]) if out["open"] else None)
        else:
            pids = tunnel_ps_pids(self._ps(), port)
            if pids:
                out.update(owned=True, pid=pids[0])
        return out

    def status(self) -> dict:
        self._ensure_session()
        running = self._running()
        models = self.model_status()
        out = {"models": models, "pods": [], "volumes": None, "rngd": rngd_ps(self.env, runner=self._runner),
               "ui_text": bt.server_ui_text(), "env_problems": self._env_problems(),
               "running_jobs": running, "locked": bool(running),
               "lock_reason": "; ".join(map(_running_text, running)) or None,
               "session": None, "rngd_choices": self._rngd_choices(), "log_tail": self._log_tail(10)}
        ready = None
        if self._session:
            cfg = self.models_cfg["models"]
            pod_env = cfg[POD_TAG]["base_url_env"]
            ready = any(m["reachable"] for m in models if cfg[m["tag"]].get("base_url_env") == pod_env)
            out["session"] = {"pod_id": self._session["pod_id"], "url": pod.pod_url(self._session["pod_id"]),
                              "tag": POD_TAG, "ready": ready, "adopted": self._session["adopted"],
                              "others": list(self._session.get("others") or [])}
        if not self.env.get("RUNPOD_API_KEY"):
            out["runpod_error"] = "RUNPOD_API_KEY 없음"
        else:
            try:
                now = self._now()
                out["pods"] = [self._pod_view(self._brief(p, now), ready, locked=bool(running)) for p in self._pods()]
                out["volumes"] = len(pod.list_volumes(opener=self._opener, env=self.env))
            except RuntimeError as e:                # RunPod 연결·HTTP 오류. 다른 칸은 그대로 보인다
                out["runpod_error"] = self._mask(str(e))
        if out.get("runpod_error"):
            out["friendly"] = bt.friendly_error("runpod", out["runpod_error"])
        if not out["rngd"]["ok"]:
            out["rngd"]["error"] = self._mask(out["rngd"]["error"] or "")
            out["rngd"]["friendly"] = bt.friendly_error("rngd", out["rngd"]["error"])
        tunnel = self.tunnel_status()
        self._diagnose(out["rngd"], tunnel, models)
        controls = bt.server_controls(running=bool(running), runpod_ok=not bool(out.get("runpod_error")),
                                      rngd_ok=out["rngd"]["ok"], tunnel=tunnel, ssh_set=bool(_ssh_target(self.env)))
        out["can"], out["why"] = controls["can"], controls["why"]
        return out

    # ── 두 단계: 요약·토큰 → 실행 ─────────────────────────

    def propose(self, action: str, params: dict | None = None) -> dict:
        if action not in ACTIONS:
            return {"code": 400, "error": f"모르는 동작: {action!r} (가능: {', '.join(ACTIONS)})"}
        params = {} if params is None else params
        if not isinstance(params, dict):
            return {"code": 400, "error": "params는 JSON 객체여야 합니다"}
        running = self._running()
        if running and action not in UNLOCKED_ACTIONS:
            return self._locked(running)
        try:
            plan = getattr(self, "_plan_" + action)(params)
        except _Refuse as e:
            return {"code": e.code, "error": self._mask(str(e))}
        except RuntimeError as e:                    # RunPod 연결·HTTP 오류
            return {"code": 502, "error": self._mask(str(e))}
        token, now = secrets.token_urlsafe(24), self._clock()
        with self._lock:                             # 아주 오래된 토큰만 버린다(지난 토큰은 410을 돌려줄 수 있게 남긴다)
            self._tokens = {t: v for t, v in self._tokens.items() if now - v["created"] <= TOKEN_TTL * 6}
            self._tokens[token] = {"action": action, "params": plan["params"], "created": now}
        return {"token": token, "action": action, "summary": plan["summary"], "warning": plan["warning"],
                "expires_in": TOKEN_TTL}

    def execute(self, token) -> dict:
        with self._lock:                             # 한 번 쓰면 지운다. 두 요청이 같은 토큰을 함께 쓰지 못한다
            item = self._tokens.pop(token, None) if isinstance(token, str) and token else None
        if item is None:
            return {"code": 400, "error": "확인 토큰이 맞지 않습니다. 이미 썼거나 잘못된 토큰입니다. 단추를 다시 눌러 요약부터 받으세요"}
        if self._clock() - item["created"] > TOKEN_TTL:
            return {"code": 410, "error": f"확인 토큰의 유효 시간({TOKEN_TTL // 60}분)이 지났습니다. 단추를 다시 눌러 요약부터 받으세요"}
        running = self._running()                    # 요약을 본 뒤에 실행이 시작됐을 수 있다
        if running and item["action"] not in UNLOCKED_ACTIONS:
            return self._locked(running)
        try:
            return getattr(self, "_do_" + item["action"])(item["params"])
        except _Refuse as e:
            return {"code": e.code, "ok": False, "error": self._mask(str(e))}
        except RuntimeError as e:
            return {"code": 502, "ok": False, "error": self._mask(str(e))}

    # ── 요약 ───────────────────────────────────────────

    def reload_env(self) -> dict:
        """.env를 다시 읽어 env를 바꾼다. 확인 토큰은 받지 않는다(돈·서버를 바꾸지 않는다). 응답에는 이름과 줄 번호만 있다."""
        if self.env_file is None:
            return {"ok": False, "error": bt.SERVER_TEXT["env_file_unknown"]}
        with self._lock:
            r = apply_env_file(self.env_file, self.env, self._env_names)
            self._env_names = set(r["names"])
            self._adopt_checked = None               # 관리 키가 바뀌었을 수 있어 다음 요청에서 Pod를 다시 찾는다
        return {"ok": True, "names": r["names"], "changed": r["changed"], "removed": r["removed"],
                "problems": [bt.env_problem(n) for n in r["problems"]]}

    def _plan_pod_create(self, params: dict) -> dict:
        self._need_runpod()
        if not self.env.get(POD_KEY_ENV):
            raise _Refuse(400, bt.SERVER_TEXT["pod_key_missing"])
        model = self.models_cfg["models"][POD_TAG]["model"]
        warn = []
        live = [p for p in self._pods() if p.get("desiredStatus") == "RUNNING"]
        if live:
            warn.append(f"이미 켜진 Pod {len(live)}개가 있습니다({', '.join(str(p.get('id')) for p in live)}). 새 Pod는 따로 과금됩니다")
        if self._session:
            warn.append(f"이 앱이 쓰던 Pod {self._session['pod_id']} 대신 새 Pod를 씁니다")
        summary = (f"{POD_GPU}, vLLM 0.32.0, {model} (이미지 2장, 최대 길이 40960). 시간당 약 ${POD_COST_HINT:.2f}. "
                   f"{WATCHDOG_SECONDS // 3600}시간 뒤 자동 삭제 감시를 함께 띄웁니다. 모델을 받아 뜨기까지 몇 분 걸립니다(10/29 기록 약 6분)")
        return {"params": {}, "summary": summary, "warning": " / ".join(warn) or None}

    def _plan_pod_delete(self, params: dict) -> dict:
        self._need_runpod()
        pid = params.get("pod_id")
        if not isinstance(pid, str) or not _POD_ID.fullmatch(pid):
            raise _Refuse(400, f"Pod 번호 형식이 아닙니다: {pid!r}")
        found = next((p for p in self._pods() if p.get("id") == pid), None)
        if found is None:
            raise _Refuse(404, f"없는 Pod입니다: {pid} (이미 지워졌을 수 있습니다)")
        if not _owned(found):                        # 계정이 공용일 수 있다. 남의 Pod는 지우지 않는다 (ADR-028)
            raise _Refuse(403, bt.SERVER_TEXT["pod_not_ours"].format(prefix=OURS))
        b = self._brief(found, self._now())
        summary = f"Pod {pid} ({b['name']}, {_minutes_cost(b, '켜진 지')})를 지웁니다. 과금이 멈춥니다. {RELOAD_TEXT}"
        warn = []
        if self._session and self._session["pod_id"] == pid:
            warn.append("이 앱이 지금 쓰는 Pod입니다. 지우면 RunPod 모델 연결이 끊깁니다")
        return {"params": {"pod_id": pid}, "summary": summary, "warning": " / ".join(warn) or None}

    def _plan_rngd_up(self, params: dict) -> dict:
        self._need_rngd()
        tag, cfg = params.get("tag"), self.models_cfg["models"]
        if not isinstance(tag, str) or tag not in RNGD_UP or tag not in cfg:
            raise _Refuse(400, f"RNGD에 올릴 수 있는 태그가 아닙니다: {tag!r} (가능: {', '.join(RNGD_UP)})")
        model, devices = cfg[tag]["model"], RNGD_UP[tag][1]
        up = self._rngd_models()
        if model in up:
            raise _Refuse(400, f"이미 떠 있는 모델입니다: {model}")
        warn = (f"지금 떠 있는 모델: {', '.join(up)}. 카드는 4장뿐이고 같은 포트(8000)를 쓰므로, 먼저 내리지 않으면 올리기가 실패합니다"
                if up else None)
        summary = (f"RNGD에 이 모델을 카드 {len(devices.split(','))}장({devices})으로 올립니다: {model}. "
                   "뜨기까지 15~25분 걸릴 수 있습니다")
        return {"params": {"tag": tag, "model": model, "devices": devices}, "summary": summary, "warning": warn}

    def _plan_rngd_down(self, params: dict) -> dict:
        self._need_rngd()
        model = params.get("model")
        if not isinstance(model, str) or not _SAFE_MODEL.match(model):
            raise _Refuse(400, f"모델 이름 형식이 아닙니다: {model!r}")
        if model not in self._rngd_models():
            raise _Refuse(404, f"RNGD에 떠 있지 않은 모델입니다: {model}")
        summary = (f"RNGD에서 이 모델을 내립니다: {model}. 이 모델을 쓰는 실행·시험은 연결 오류로 실패합니다. "
                   "다시 올리면 15~25분 걸립니다")
        return {"params": {"model": model}, "summary": summary, "warning": None}

    def _plan_tunnel_open(self, params: dict) -> dict:
        port = self._closed_tunnel_port()
        return {"params": {}, "summary": f"내 컴퓨터 {port}번을 RNGD {RNGD_REMOTE_PORT}번에 잇는 통로(SSH 터널)를 엽니다",
                "warning": None}

    def _plan_tunnel_close(self, params: dict) -> dict:
        st = self._owned_tunnel()
        summary = (f"내 컴퓨터 {st['port']}번과 RNGD를 잇는 통로(SSH 터널)를 닫습니다. "
                   "RNGD 모델 연결이 끊깁니다. 다시 열면 몇 초 걸립니다")
        warn = (None if self._app_tunnel(st["port"])
                else f"앱을 다시 켜기 전에 열었거나 다른 터미널에서 연 터널입니다(pid {st['pid']})")
        return {"params": {}, "summary": summary, "warning": warn}

    # ── 실행 ───────────────────────────────────────────

    def _do_pod_create(self, params: dict) -> dict:
        self._need_runpod()
        key = self.env.get(POD_KEY_ENV)              # Pod 환경 변수로만 보낸다. 앱을 다시 켜도 같은 .env 값으로 이어 쓴다
        if not key:                                  # 요약을 본 뒤 설정 다시 읽기로 빠졌을 수 있다
            raise _Refuse(400, bt.SERVER_TEXT["pod_key_missing"])
        model = self.models_cfg["models"][POD_TAG]["model"]
        pod_id = pod.create_pod(POD_SERVE.format(model=model), key, name=POD_NAME, opener=self._opener, env=self.env)
        self._session = {"pod_id": pod_id, "created": self._clock(), "adopted": False}
        watchdog = self._start_watchdog(pod_id)
        note = (f"{model}, {POD_GPU}, 시간당 약 ${POD_COST_HINT:.2f}, "
                + (f"{WATCHDOG_SECONDS // 3600}시간 뒤 자동 삭제 감시" if watchdog else "자동 삭제 감시를 띄우지 못함 — 직접 지울 것"))
        line = append_server_log(self.log_path, "pod_create", target=f"{pod_id} ({POD_NAME})", note=note,
                                 _secrets=self._secrets())
        return {"ok": True, "result": {"pod_id": pod_id, "name": POD_NAME, "url": pod.pod_url(pod_id), "tag": POD_TAG,
                                       "watchdog": watchdog}, "log_line": line}

    def _do_pod_delete(self, params: dict) -> dict:
        self._need_runpod()
        pid = params["pod_id"]
        before = next((p for p in self._pods() if p.get("id") == pid), None)
        if before is None:                           # 주인을 확인할 수 없으면 지우지 않는다
            raise _Refuse(404, f"없는 Pod입니다: {pid} (이미 지워졌을 수 있습니다)")
        if not _owned(before):                       # 요약을 본 뒤 목록이 바뀌었을 수 있어 지우기 직전에 다시 본다
            raise _Refuse(403, bt.SERVER_TEXT["pod_not_ours"].format(prefix=OURS))
        b = self._brief(before, self._now())
        pod.delete_pod(pid, opener=self._opener, env=self.env)
        self._sleep(DELETE_WAIT)
        left = self._pods()
        gone = all(p.get("id") != pid for p in left)
        if gone:
            if self._session and self._session["pod_id"] == pid:
                self._session = None
            w = self._watchdogs.pop(pid, None)
            if w:
                w["proc"].terminate()
        note = f"{_minutes_cost(b, '켜진')}, 남은 Pod {len(left)}개" + ("" if gone else " — 지운 뒤에도 목록에 남아 있음")
        line = append_server_log(self.log_path, "pod_delete", target=f"{pid} ({b['name']})" if b["name"] else pid,
                                 note=note, _secrets=self._secrets())
        return {"ok": gone, "result": {"pod_id": pid, "gone": gone, "minutes": b["minutes"], "est_cost": b["est_cost"],
                                       "remaining": [p.get("id") for p in left]}, "log_line": line}

    def _do_rngd_up(self, params: dict) -> dict:
        self._need_rngd()
        model, devices = params["model"], params["devices"]
        r = rngd_up(model, devices, self.env, log_name=params["tag"], runner=self._runner)
        started = bool(r["ok"]) and model in [m["model"] for m in rngd_ps(self.env, runner=self._runner)["models"]]
        note = f"카드 {devices}" + ("" if started else f" — 실패: {r['error'] or '프로세스를 찾지 못함'}")
        line = append_server_log(self.log_path, "rngd_up", target=model, note=note, _secrets=self._secrets())
        return {"ok": started, "result": {"model": model, "devices": devices, "started": started, "error": r["error"]},
                "log_line": line}

    def _do_rngd_down(self, params: dict) -> dict:
        self._need_rngd()
        model = params["model"]
        r = rngd_down(model, self.env, runner=self._runner, sleep=self._sleep)
        note = f"멈춘 pid {' '.join(map(str, r['killed'])) or '없음'}"
        if r["remaining"]:
            note += f", 남은 pid {' '.join(map(str, r['remaining']))}"
        if r["error"]:
            note += f" — 오류: {r['error']}"
        line = append_server_log(self.log_path, "rngd_down", target=model, note=note, _secrets=self._secrets())
        return {"ok": r["ok"], "result": r, "log_line": line}

    def _do_tunnel_open(self, params: dict) -> dict:
        port = self._closed_tunnel_port()            # 요약을 본 뒤 다른 터미널이 열었을 수 있다
        started, code, opened, error = self._clock(), None, False, None
        try:
            proc = self._tunnel_spawner(tunnel_args(self.env))
        except OSError:
            proc, error = None, bt.SERVER_TEXT["tunnel_spawn_failed"]
        if proc is not None:
            for _ in range(int(TUNNEL_WAIT / TUNNEL_STEP)):
                opened = port_open(port, connector=self._connector)
                code = None if opened else proc.poll()
                if opened or code is not None:
                    break
                self._sleep(TUNNEL_STEP)
            else:
                opened = port_open(port, connector=self._connector)
            if opened:
                self._tunnel = {"proc": proc, "port": port, "started": started}
            elif code is not None:
                error = bt.SERVER_TEXT["tunnel_exited"].format(code=code)
            else:                                    # 시간 안에 열리지 않았다. 남은 ssh를 끝낸다
                proc.terminate()
                error = bt.SERVER_TEXT["tunnel_timeout"].format(seconds=TUNNEL_WAIT)
        note = "열림" if opened else "실패" + (f": 종료 코드 {code}" if code is not None else "")
        line = append_server_log(self.log_path, "tunnel_open", target=f"127.0.0.1:{port}", note=note,
                                 _secrets=self._secrets())
        out = {"ok": opened, "result": {"port": port, "open": opened, "exit_code": code}, "log_line": line}
        return out if opened else {**out, "error": error}

    def _do_tunnel_close(self, params: dict) -> dict:
        st = self._owned_tunnel()                    # 죽이기 직전에 포트와 ps 줄을 다시 본다
        port, pid, mine = st["port"], st["pid"], self._app_tunnel(st["port"])
        if mine:
            mine["proc"].terminate()
        else:
            try:
                self._killer(pid, signal.SIGTERM)
            except ProcessLookupError:               # 그 사이 끝났다
                pass
            except OSError:                          # 다른 사용자의 프로세스
                raise _Refuse(403, bt.SERVER_TEXT["tunnel_not_ours"].format(port=port)) from None
        closed = self._wait_port(port, want_open=False)
        if mine and (closed or mine["proc"].poll() is not None):
            self._tunnel = None
        note = ("앱이 연 터널" if mine else f"이어 받은 터널 pid {pid}") + ("" if closed else " — 포트가 아직 열려 있음")
        line = append_server_log(self.log_path, "tunnel_close", target=f"127.0.0.1:{port}", note=note,
                                 _secrets=self._secrets())
        out = {"ok": closed, "result": {"port": port, "pid": pid, "closed": closed}, "log_line": line}
        return out if closed else {**out, "error": bt.SERVER_TEXT["tunnel_still_open"].format(port=port)}

    # ── 도구 ───────────────────────────────────────────

    def _running(self) -> list[dict]:
        return [r for r in self.jobs.running() if r.get("kind") in LOCKING_KINDS]

    @staticmethod
    def _locked(running: list[dict]) -> dict:
        return {"code": 409, "error": "실행이 돌고 있어 서버를 바꿀 수 없습니다", "running": running,
                "lock_reason": "; ".join(map(_running_text, running))}

    def _need_runpod(self) -> None:
        if not self.env.get("RUNPOD_API_KEY"):
            raise _Refuse(400, "RUNPOD_API_KEY 없음 (.env에 넣고 앱을 다시 켜세요)")

    def _need_rngd(self) -> None:
        if not self.env.get("RNGD_SSH"):
            raise _Refuse(400, "RNGD_SSH 없음 (.env에 ssh 접속 인자를 넣고 앱을 다시 켜세요)")

    def _app_tunnel(self, port: int) -> dict | None:
        """이 앱이 띄운 ssh가 살아 있고 그 포트의 것이면 그 기록. 끝났으면 잊는다."""
        t = self._tunnel
        if t and t["proc"].poll() is not None:
            self._tunnel = t = None
        return t if t and t["port"] == port else None

    def _closed_tunnel_port(self) -> int:
        """터널을 열 수 있으면 그 포트. RNGD_SSH 없음·내 컴퓨터 주소 아님은 400, 이미 열림은 409."""
        self._need_rngd()
        port = tunnel_port(self.env)
        if port is None:
            raise _Refuse(400, bt.SERVER_TEXT["tunnel_no_port"])
        if tunnel_args(self.env) is None:            # RNGD_SSH가 "ssh" 한 낱말뿐이다
            raise _Refuse(400, "RNGD_SSH에 접속 인자가 없습니다 (.env에 -i <키> -p <포트> <사용자>@<호스트>를 넣으세요)")
        if port_open(port, connector=self._connector):
            raise _Refuse(409, bt.SERVER_TEXT["tunnel_already_open"].format(port=port))
        return port

    def _owned_tunnel(self) -> dict:
        """닫을 수 있는 터널의 tunnel_status. 포트 없음 400, 닫힘 404, 이 앱의 것이 아님 403."""
        st = self.tunnel_status()
        if st["port"] is None:
            raise _Refuse(400, bt.SERVER_TEXT["tunnel_no_port"])
        if not st["open"]:
            raise _Refuse(404, bt.SERVER_TEXT["tunnel_closed"].format(port=st["port"]))
        if not st["owned"]:
            raise _Refuse(403, bt.SERVER_TEXT["tunnel_not_ours"].format(port=st["port"]))
        return st

    def _wait_port(self, port: int, *, want_open: bool) -> bool:
        for _ in range(int(TUNNEL_WAIT / TUNNEL_STEP)):
            if port_open(port, connector=self._connector) == want_open:
                return True
            self._sleep(TUNNEL_STEP)
        return port_open(port, connector=self._connector) == want_open

    def _diagnose(self, rngd: dict, tunnel: dict, models: list[dict]) -> None:
        """status()["rngd"]에 tunnel·diagnosis·loading_since·diagnosis_text를 넣고, 진단이 원인을 말하면
        주소가 있는 RNGD 태그의 friendly를 진단 글로 바꾼다(모델이 없을 때 터널을 탓하지 않게). 원래 오류 종류(raw)는 남긴다."""
        diagnosis = diagnose_rngd(rngd, tunnel, models)
        secs = [m["elapsed_s"] for m in rngd["models"] if m.get("elapsed_s") is not None]
        since = _local_iso(self._clock() - max(secs)) if secs and diagnosis != "ok" else None
        text = bt.rngd_diagnosis(diagnosis, since, datetime.fromtimestamp(self._clock()).astimezone())
        rngd.update(tunnel=tunnel, diagnosis=diagnosis, loading_since=since, diagnosis_text=text)
        if text and diagnosis != "ok":
            for m in models:
                if m.get("where") == "RNGD" and m.get("url_set") and m.get("friendly"):
                    m["friendly"] = {**text, "raw": m["friendly"]["raw"]}

    def _pods(self) -> list[dict]:
        return pod.list_pods(opener=self._opener, env=self.env)

    def _ensure_session(self) -> None:
        """세션이 없으면 이 앱이 전에 만든 켜진 Pod를 이어 쓴다(앱을 다시 켠 뒤 첫 요청 때). 가장 최근에 켜진 것을 고르고
        나머지는 others에 둔다. 목록 요청은 ADOPT_EVERY초에 한 번까지이고, RunPod 오류면 세션 없이 넘어간다."""
        if self._session or not self.env.get("RUNPOD_API_KEY"):
            return
        now = self._clock()
        if self._adopt_checked is not None and now - self._adopt_checked < ADOPT_EVERY:
            return
        self._adopt_checked = now
        try:
            pods = self._pods()
        except RuntimeError:
            return
        t = self._now()
        ours = sorted((self._brief(p, t) for p in pods if _owned(p) and p.get("desiredStatus") == "RUNNING"),
                      key=lambda b: float("inf") if b["uptime_s"] is None else b["uptime_s"])
        if ours:
            self._session = {"pod_id": ours[0]["id"], "created": None, "adopted": True,
                             "others": [b["id"] for b in ours[1:]]}

    def _brief(self, p: dict, now: datetime) -> dict:
        """pod.brief. 시각을 못 얻은 이 앱의 Pod는 server_log.md의 pod_create 줄 시각으로 켜진 시간·추정 비용을 채운다."""
        b = pod.brief(p, now=now)
        if b["uptime_s"] is None and _owned(p):
            started = self._logged_create(b["id"])
            if started:
                b = pod.brief({**p, "lastStartedAt": started.isoformat()}, now=now)
        return b

    def _logged_create(self, pod_id) -> datetime | None:
        """server_log.md에서 그 Pod의 마지막 pod_create 줄 시각. 기록은 로컬 시각이다."""
        found = None
        for row in self._log_rows():
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[1] == "pod_create" and cells[2].split(" ")[0] == pod_id:
                found = cells[0]
        try:
            return datetime.strptime(found, "%Y-%m-%d %H:%M:%S").astimezone() if found else None
        except ValueError:
            return None

    def _env_problems(self) -> list[dict]:
        return [bt.env_problem(n) for n in read_env_file(self.env_file)[1]] if self.env_file else []

    def _rngd_models(self) -> list[str]:
        ps = rngd_ps(self.env, runner=self._runner)
        if not ps["ok"]:
            raise _Refuse(502, f"RNGD에 접속하지 못했습니다: {ps['error']}")
        return [m["model"] for m in ps["models"]]

    def _rngd_choices(self) -> list[dict]:
        cfg = self.models_cfg["models"]
        return [{"tag": t, "label": label, "model": cfg[t]["model"], "devices": d, "cards": len(d.split(","))}
                for t, (label, d) in RNGD_UP.items() if t in cfg]

    def _start_watchdog(self, pod_id: str) -> bool:
        cmd = f"sleep {WATCHDOG_SECONDS}; {shlex.quote(str(self.jobs.python))} scripts/pod.py delete {shlex.quote(pod_id)}"
        try:
            proc = self._watchdog_spawner(["nohup", "bash", "-c", cmd], self.jobs.backend_dir)
        except OSError:
            return False
        self._watchdogs[pod_id] = {"proc": proc, "deadline": self._clock() + WATCHDOG_SECONDS}
        return True

    def _pod_view(self, b: dict, ready: bool | None, *, locked: bool) -> dict:
        mine = self._session and self._session["pod_id"] == b["id"]
        w = self._watchdogs.get(b["id"])
        owned = _owned(b)
        return {**b, "ours": owned, "owned": owned, "deletable": owned and not locked, "session": bool(mine),
                "state": ("준비됨" if ready else "준비 중") if mine else None,
                "auto_delete_min": max(0, round((w["deadline"] - self._clock()) / 60)) if w else None}

    def _log_tail(self, n: int) -> list[str]:
        return self._log_rows()[-n:]

    def _log_rows(self) -> list[str]:
        if not self.log_path.exists():
            return []
        return [l for l in self.log_path.read_text(encoding="utf-8").splitlines()
                if l.startswith("| ") and not l.startswith("| 시각 |")]

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc)

    def _secrets(self) -> list[str]:
        return [v for k, v in self.env.items()                  # .env의 RUNPOD_VLLM_API_KEY(Pod 키)도 여기서 가린다
                if k.startswith(_SECRET_PREFIXES) and _SECRET_FIELD.search(k) and v and len(v) >= 8]

    def _mask(self, text: str) -> str:
        return mask_keys(text, self._secrets())
