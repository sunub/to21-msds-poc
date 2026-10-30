"""작업 화면 탭 ⑤ 서버: 모델 서버 상태, RNGD ssh 작업, RunPod Pod, 사용 기록 (개발 전용, ADR-025).

낮은 층(model_status, rngd_*, append_server_log)과 그 위의 상태 기계 ServerActions가 있다.
ServerActions의 변경 동작(Pod 만들기·지우기, RNGD 올리기·내리기)은 두 단계다: propose가 요약과 1회용 확인 토큰을 주고,
execute가 그 토큰으로 실행한다. run_sections.py·try_section.py가 돌고 있으면 두 단계 모두 409로 막는다.
키는 반환값·예외·기록 어디에도 쓰지 않는다. Pod에 넣는 vLLM 키는 앱 메모리에만 둔다. 시험은 opener·runner·watchdog_spawner·clock을 가짜로 끼운다.
"""
import json
import re
import secrets
import shlex
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

import yaml

import _common  # noqa: F401  src 경로 등록
import b_app_jobs as bj
import pod
from msds.common.paths import CONFIGS

SERVER_ENV_PREFIXES = ("RNGD_", "RUNPOD_", "VLLM_")
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


def rngd_ssh_args(env) -> list[str] | None:
    raw = env.get("RNGD_SSH")
    if not raw:
        return None
    return ["ssh", "-n", "-o", "BatchMode=yes", *shlex.split(raw)]


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
    ok, out, err = _remote(env, "furiosa-smi ps; ps -eo pid,comm,args | grep -i [f]uriosa-llm", runner)
    if err == "RNGD_SSH 없음" or (not ok and not out):
        return {"ok": False, "text": "", "models": [], "error": err}
    text = mask_keys(out, [])
    models = [{"pid": int(m.group(1)), "model": m.group(2)}
              for m in re.finditer(r"^\s*(\d+)\s+\S+\s+.*furiosa-llm serve (\S+)", text, re.M)]
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


# ── 탭 ⑤의 상태 기계: 요약과 확인 토큰 → 실행 ─────────────────

ACTIONS = ("pod_create", "pod_delete", "rngd_up", "rngd_down")
OURS = "to21-b-"                                     # 이 도구가 만든 Pod 이름의 앞부분
POD_NAME = "to21-b-qwen36"
POD_TAG = "qwen36_35b_runpod"                        # Pod가 띄우는 모델의 태그. 모델 이름·주소 변수는 models.yaml에서 읽는다
POD_GPU = "RTX PRO 6000 1장"                          # pod.create_pod의 기본 GPU
POD_COST_HINT = 2.49                                 # 시간당 달러. 10/29 보안 클라우드 기록 (RunPod_사용기록)
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
_POD_ID = re.compile(r"^[a-z0-9]{6,40}$")
_SECRET_PREFIXES = ("RNGD_", "RUNPOD_", "VLLM_", "LLM_", "ANTHROPIC_")
_WHERE = (("RUNPOD_", "RunPod"), ("RNGD_", "RNGD"), ("VLLM_", "vLLM"))


class _Refuse(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _spawn_watchdog(argv: list[str], cwd: Path) -> bj._Group:
    """앱을 꺼도 살아 있게 새 세션으로 띄운다. 출력은 버린다(pod.py delete는 키를 찍지 않는다)."""
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    return bj._Group(proc)


def _running_text(r: dict) -> str:
    kind = {"run": "본 실행", "try": "시험"}.get(r.get("kind"), r.get("kind"))
    what = r.get("run_name") or r.get("label") or r.get("doc") or f"pid {r.get('pid')}"
    return f"{kind} {what} — 돌고 있음"


def _minutes_cost(b: dict, prefix: str) -> str:
    mins = f"{prefix} {b['minutes']:.0f}분" if b.get("minutes") is not None else "켜진 시간 모름"
    cost = f"추정 ${b['est_cost']:.2f}" if b.get("est_cost") is not None else "추정 비용 모름"
    return f"{mins}, {cost}"


class ServerActions:
    """탭 ⑤의 서버 동작. 확인 토큰, 이 앱이 만든 Pod 세션(vLLM 키 포함), 감시 프로세스는 이 객체의 메모리에만 있다.

    propose·execute는 dict를 돌려준다. 실패하면 "code"(400·404·409·410·502)와 "error"가 있고, 앱 라우트가 code를 상태 코드로 쓴다.
    """

    def __init__(self, env: Mapping[str, str], jobs: "bj.JobManager", log_path: Path, *, opener=None, runner=None,
                 watchdog_spawner=None, clock=None, sleep=None, models_cfg: dict | None = None):
        self.env, self.jobs, self.log_path = env, jobs, Path(log_path)
        self._opener, self._runner = opener, runner
        self._watchdog_spawner = watchdog_spawner or _spawn_watchdog
        self._clock, self._sleep = clock or time.time, sleep or time.sleep
        self.models_cfg = models_cfg or yaml.safe_load((CONFIGS / "models.yaml").read_text(encoding="utf-8"))
        self._tokens: dict[str, dict] = {}
        self._session: dict | None = None            # 이 앱이 만든 Pod {"pod_id", "key", "created"}. 앱을 끄면 잊는다
        self._watchdogs: dict[str, dict] = {}        # Pod 번호 → {"proc", "deadline"}
        self._lock = threading.Lock()

    # ── 읽기 ───────────────────────────────────────────

    def job_env(self) -> dict[str, str]:
        """작업(run_sections·try_section)과 연결 확인에 쓸 Pod 주소·키. 이 앱이 만든 Pod가 없으면 빈 dict."""
        s = self._session
        if not s:
            return {}
        cfg = self.models_cfg["models"][POD_TAG]
        return {cfg["base_url_env"]: pod.pod_url(s["pod_id"]), cfg["api_key_env"]: s["key"]}

    def model_status(self) -> list[dict]:
        """all_model_status에 서버 종류(where)를 붙인다. 이 앱이 만든 Pod가 있으면 .env의 RunPod 주소 대신 그 Pod를 본다."""
        cfg = self.models_cfg["models"]
        out = all_model_status(self.models_cfg, {**self.env, **self.job_env()}, opener=self._opener)
        for s in out:
            name = str(cfg[s["tag"]].get("base_url_env", ""))
            s["where"] = next((w for p, w in _WHERE if name.startswith(p)), name)
        return out

    def status(self) -> dict:
        running = self._running()
        models = self.model_status()
        out = {"models": models, "pods": [], "volumes": None, "rngd": rngd_ps(self.env, runner=self._runner),
               "running_jobs": running, "locked": bool(running),
               "lock_reason": "; ".join(map(_running_text, running)) or None,
               "session": None, "rngd_choices": self._rngd_choices(), "log_tail": self._log_tail(10)}
        ready = None
        if self._session:
            cfg = self.models_cfg["models"]
            pod_env = cfg[POD_TAG]["base_url_env"]
            ready = any(m["reachable"] for m in models if cfg[m["tag"]].get("base_url_env") == pod_env)
            out["session"] = {"pod_id": self._session["pod_id"], "url": pod.pod_url(self._session["pod_id"]),
                              "tag": POD_TAG, "ready": ready}
        if not self.env.get("RUNPOD_API_KEY"):
            out["runpod_error"] = "RUNPOD_API_KEY 없음"
            return out
        try:
            now = self._now()
            out["pods"] = [self._pod_view(pod.brief(p, now=now), ready) for p in self._pods()]
            out["volumes"] = len(pod.list_volumes(opener=self._opener, env=self.env))
        except RuntimeError as e:                    # RunPod 연결·HTTP 오류. 다른 칸은 그대로 보인다
            out["runpod_error"] = self._mask(str(e))
        return out

    # ── 두 단계: 요약·토큰 → 실행 ─────────────────────────

    def propose(self, action: str, params: dict | None = None) -> dict:
        if action not in ACTIONS:
            return {"code": 400, "error": f"모르는 동작: {action!r} (가능: {', '.join(ACTIONS)})"}
        params = {} if params is None else params
        if not isinstance(params, dict):
            return {"code": 400, "error": "params는 JSON 객체여야 합니다"}
        running = self._running()
        if running:
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
        if running:
            return self._locked(running)
        try:
            return getattr(self, "_do_" + item["action"])(item["params"])
        except _Refuse as e:
            return {"code": e.code, "ok": False, "error": self._mask(str(e))}
        except RuntimeError as e:
            return {"code": 502, "ok": False, "error": self._mask(str(e))}

    # ── 요약 ───────────────────────────────────────────

    def _plan_pod_create(self, params: dict) -> dict:
        self._need_runpod()
        model = self.models_cfg["models"][POD_TAG]["model"]
        warn = []
        live = [p for p in self._pods() if p.get("desiredStatus") == "RUNNING"]
        if live:
            warn.append(f"이미 켜진 Pod {len(live)}개가 있습니다({', '.join(str(p.get('id')) for p in live)}). 새 Pod는 따로 과금됩니다")
        if self._session:
            warn.append(f"이 앱이 쓰던 Pod {self._session['pod_id']} 대신 새 Pod를 씁니다. 옛 Pod의 vLLM 키는 잊습니다")
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
        b = pod.brief(found, now=self._now())
        summary = f"Pod {pid} ({b['name']}, {_minutes_cost(b, '켜진 지')})를 지웁니다. 과금이 멈춥니다. {RELOAD_TEXT}"
        warn = []
        if not str(b["name"] or "").startswith(OURS):   # 계정이 공용일 수 있다. 막지는 않는다
            summary += f". 이 Pod는 이 도구가 만든 것이 아닙니다(이름이 {OURS}로 시작하지 않음)"
            warn.append("다른 사람이 쓰는 Pod일 수 있습니다. 이름과 켜진 시간을 확인하세요")
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

    # ── 실행 ───────────────────────────────────────────

    def _do_pod_create(self, params: dict) -> dict:
        self._need_runpod()
        model = self.models_cfg["models"][POD_TAG]["model"]
        key = secrets.token_urlsafe(32)              # Pod 환경 변수로만 보내고 이 객체의 메모리에만 둔다
        pod_id = pod.create_pod(POD_SERVE.format(model=model), key, name=POD_NAME, opener=self._opener, env=self.env)
        self._session = {"pod_id": pod_id, "key": key, "created": self._clock()}
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
        b = pod.brief(before, now=self._now()) if before else {"name": None, "minutes": None, "est_cost": None}
        pod.delete_pod(pid, opener=self._opener, env=self.env)
        self._sleep(DELETE_WAIT)
        left = self._pods()
        gone = all(p.get("id") != pid for p in left)
        if gone:
            if self._session and self._session["pod_id"] == pid:
                self._session = None                 # vLLM 키도 함께 잊는다
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

    def _pods(self) -> list[dict]:
        return pod.list_pods(opener=self._opener, env=self.env)

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

    def _pod_view(self, b: dict, ready: bool | None) -> dict:
        mine = self._session and self._session["pod_id"] == b["id"]
        w = self._watchdogs.get(b["id"])
        return {**b, "ours": str(b.get("name") or "").startswith(OURS), "session": bool(mine),
                "state": ("준비됨" if ready else "준비 중") if mine else None,
                "auto_delete_min": max(0, round((w["deadline"] - self._clock()) / 60)) if w else None}

    def _log_tail(self, n: int) -> list[str]:
        if not self.log_path.exists():
            return []
        rows = [l for l in self.log_path.read_text(encoding="utf-8").splitlines()
                if l.startswith("| ") and not l.startswith("| 시각 |")]
        return rows[-n:]

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc)

    def _secrets(self) -> list[str]:
        vals = [v for k, v in self.env.items()
                if k.startswith(_SECRET_PREFIXES) and _SECRET_FIELD.search(k) and v and len(v) >= 8]
        return vals + ([self._session["key"]] if self._session else [])

    def _mask(self, text: str) -> str:
        return mask_keys(text, self._secrets())
