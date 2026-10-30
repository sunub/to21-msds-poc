"""작업 화면 서버 탭의 낮은 층: 모델 서버 상태, RNGD ssh 작업, 사용 기록 (개발 전용, ADR-025).

키는 반환값·예외·기록 어디에도 쓰지 않는다. 시험은 opener·runner를 가짜로 끼운다.
"""
import json
import re
import shlex
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

import _common  # noqa: F401  src 경로 등록

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


def append_server_log(log_path: Path, action: str, *, _secrets: Iterable[str] = (), **fields) -> None:
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
