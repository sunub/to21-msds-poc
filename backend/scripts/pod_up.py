"""SSH 접속 명령어 하나로 RunPod Pod에 vLLM을 띄우고 터널까지 연결한다.

python scripts/pod_up.py "ssh root@<주소> -p <포트> -i ~/.ssh/id_ed25519" [--restart] [--tag <모델 태그>]

되풀이해 실행해도 된다. Pod 상태를 보고 필요한 단계만 한다 (설치 → 서버 기동 → 터널 → 응답 확인).
Pod를 만들고 지우는 일은 scripts/pod.py가 한다. 모델 이름과 주소는 configs/models.yaml과 .env에서 읽는다.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from _common import ROOT
from msds.extract.client import load_model_config

POD_TAG = "qwen36_35b_runpod"
REMOTE_DIR = ROOT.parent / "deploy" / "runpod"
REMOTE_SCRIPTS = (REMOTE_DIR / "setup_vllm.sh", REMOTE_DIR / "serve_vllm.sh")
POLL_SECONDS = 20
WAIT_SECONDS = 3600          # 새 Pod는 설치에 15~25분 걸린다 (b_app_servers.RELOAD_TEXT)
SSH_DROPS_ALLOWED = 5        # 기다리는 동안 ssh가 잠깐 끊겨도 이만큼은 넘어간다
_USER_HOST = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+$")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LOCAL_HOSTS = ("127.0.0.1", "localhost")

STOP_SCRIPT = """pkill -f '[v]llm serve'
for i in $(seq 1 30); do pgrep -f '[v]llm serve' >/dev/null || break; sleep 1; done
"""


class PodError(Exception):
    """사용자에게 그대로 보여 줄 실패."""


@dataclass(frozen=True)
class Target:
    user_host: str
    port: int = 22
    identity: str | None = None

    def options(self) -> list[str]:
        args = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new",
                "-p", str(self.port)]
        return args + (["-i", self.identity] if self.identity else [])


def parse_ssh(text: str) -> Target:
    """RunPod 콘솔의 접속 명령어를 읽는다. 다른 ssh 옵션은 임의 명령을 실행할 수 있어 받지 않는다."""
    tokens = shlex.split(text)
    if tokens[:1] == ["ssh"]:
        tokens = tokens[1:]
    user_host, port, identity = None, 22, None
    while tokens:
        token = tokens.pop(0)
        if token in ("-p", "-i"):
            if not tokens:
                raise PodError(f"{token} 뒤에 값이 없습니다.")
            value = tokens.pop(0)
            if token == "-p":
                if not value.isdigit() or not 1 <= int(value) <= 65535:
                    raise PodError(f"포트가 올바르지 않습니다: {value}. 콘솔에 나온 숫자를 넣어 주세요.")
                port = int(value)
            else:
                identity = str(Path(value).expanduser())
        elif token.startswith("-"):
            raise PodError(f"받지 않는 옵션입니다: {token}. 주소, -p, -i만 넣어 주세요.")
        elif user_host is None:
            user_host = token
        else:
            raise PodError(f"알 수 없는 값입니다: {token}. 형식은 ssh user@host -p 포트 -i 키 입니다.")
    if not user_host or not _USER_HOST.match(user_host):
        raise PodError(f"접속 대상이 user@host 형식이 아닙니다: {user_host}")
    if user_host.endswith("ssh.runpod.io"):
        raise PodError("ssh.runpod.io 주소는 명령 실행과 터널을 지원하지 않습니다. "
                       "콘솔의 'SSH over exposed TCP' 명령어를 넣어 주세요.")
    return Target(user_host, port, identity)


def tunnel_port(base_url: str) -> int | None:
    """주소가 이 컴퓨터를 가리키면 터널 포트. RunPod 프록시 주소처럼 바로 닿으면 None."""
    url = urlparse(base_url)
    return url.port if url.hostname in LOCAL_HOSTS else None


def _marker(model: str) -> str:
    return "/workspace/.vllm_ready_" + model.replace("/", "_")


def probe_script(model: str) -> str:
    return f"""echo gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
echo free=$(df -h /workspace 2>/dev/null | tail -1 | awk '{{print $4}}')
echo health=$(curl -s -m 5 -o /dev/null -w '%{{http_code}}' localhost:8000/health)
echo setup_running=$(pgrep -f '[s]etup_vllm.sh' | head -1)
echo serving=$(pgrep -f '[v]llm serve' | head -1)
[ -f {shlex.quote(_marker(model))} ] && [ -x /workspace/venv/bin/vllm ] && echo installed=1
log=$(ls -t /workspace/setup.log /workspace/vllm.log 2>/dev/null | head -1)
[ -n "$log" ] && echo last=$(tail -c 400 "$log" | tr '\\r' '\\n' | grep -v '^ *$' | tail -1)
"""


def start_script(model: str, action: str) -> str:
    """설치와 서버를 Pod 안의 새 세션으로 띄운다. 접속이 끊겨도 계속 돈다."""
    m = shlex.quote(model)
    serve = f"exec ./serve_vllm.sh {m} > vllm.log 2>&1"
    job = f"./setup_vllm.sh {m} > setup.log 2>&1 && {serve}" if action == "setup" else serve
    return f"cd /workspace && rm -f vllm.log && setsid nohup bash -c {shlex.quote(job)} > /dev/null 2>&1 < /dev/null &\n"


def parse_state(text: str) -> dict:
    state = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            state[key.strip()] = value.strip()
    return state


def decide(state: dict) -> str:
    if not state.get("gpu"):
        return "no_gpu"
    if state.get("health") == "200":
        return "ready"
    if state.get("setup_running") or state.get("serving"):
        return "wait"
    return "serve" if state.get("installed") else "setup"


def ssh_runner(target: Target):
    def run(script: str, stdin: str | None = None, timeout: int = 60) -> str:
        """script를 Pod에서 돌린다. stdin이 있으면 그 내용을 넘기고, 없으면 script 자체를 stdin으로 보낸다
        (명령 줄에 안 남아 pgrep이 자기 자신을 찾지 않는다)."""
        remote, data = (script, stdin) if stdin is not None else ("bash -s", script)
        try:
            p = subprocess.run(["ssh", *target.options(), target.user_host, remote], input=data,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise PodError(f"ssh가 {timeout}초 안에 끝나지 않았습니다.") from None
        if p.returncode == 255:
            raise PodError((p.stderr.strip().splitlines() or ["ssh 실패"])[-1])
        return p.stdout
    return run


class _Mask:
    """vLLM 로그에는 --api-key 값이 그대로 찍힌다. 화면과 오류 문구로 나가는 글에서 가린다."""
    def __init__(self, secret: str):
        self.secret = secret

    def __call__(self, text: str) -> str:
        return _ANSI.sub("", text).replace(self.secret, "***")


def _connect_error(e: PodError) -> PodError:
    return PodError(f"Pod에 접속하지 못했습니다: {e}\n"
                    "RunPod 콘솔에서 Pod가 켜져 있는지 보고, 재시작했다면 바뀐 접속 명령어로 다시 실행해 주세요.")


def _probe(run, model: str) -> dict:
    return parse_state(run(probe_script(model), timeout=60))


def _upload_and_start(run, model: str, key: str, action: str) -> None:
    for path in REMOTE_SCRIPTS:
        run(f"umask 077; cat > /workspace/{path.name}; chmod 700 /workspace/{path.name}", stdin=path.read_text())
    run("umask 077; cat > /workspace/vllm_api_key", stdin=key)   # 명령 줄에 넣으면 ps와 로그에 남는다
    run(start_script(model, action))


def _wait(run, model: str, mask: _Mask, sleep, timeout: int) -> None:
    start, drops, last = time.monotonic(), 0, None
    while True:
        try:
            state = _probe(run, model)
            drops = 0
        except PodError as e:
            drops += 1
            if drops > SSH_DROPS_ALLOWED:
                raise PodError(f"기다리는 중 접속이 끊겼습니다: {e}\n"
                               "Pod 안의 설치는 계속될 수 있습니다. 같은 명령으로 다시 실행해 주세요.") from None
            sleep(POLL_SECONDS)
            continue
        if state.get("health") == "200":
            return
        if not state.get("setup_running") and not state.get("serving"):
            log = run("tail -n 15 /workspace/setup.log; echo ---; tail -n 15 /workspace/vllm.log 2>/dev/null")
            raise PodError(f"설치 또는 서버가 멈췄습니다. Pod 로그:\n{mask(log)}")
        elapsed = int(time.monotonic() - start)
        if elapsed >= timeout:
            raise PodError(f"{timeout}초가 지나도 준비되지 않았습니다. Pod 안에서는 계속 돌고 있으며 GPU 비용도 계속 나옵니다. "
                           "같은 명령으로 다시 실행하면 이어서 기다립니다.")
        line = mask(state.get("last", ""))[:100]
        if line != last:
            print(f"  [{elapsed // 60}분] {line}", flush=True)
            last = line
        sleep(POLL_SECONDS)


def open_ssh_tunnel(target: Target, port: int) -> None:
    """이 컴퓨터의 port → Pod의 8000. 스크립트가 끝나도 살아 있게 뒤로 보낸다."""
    pid = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    if pid:
        args = subprocess.run(["ps", "-o", "args=", "-p", pid[0]], capture_output=True, text=True).stdout
        if not args.startswith("ssh "):
            raise PodError(f"포트 {port}을 다른 프로그램이 쓰고 있습니다 (PID {pid[0]}): {args.strip()[:80]}")
        if target.user_host in args and f"-p {target.port}" in args:
            print(f"터널: 포트 {port} 그대로 사용")
            return
        print(f"터널: 포트 {port}의 이전 터널을 닫습니다 (PID {pid[0]})")
        subprocess.run(["kill", pid[0]])
        time.sleep(1)
    with tempfile.TemporaryFile("w+") as err:
        # -f로 뒤로 간 ssh가 파이프를 물고 있으면 run이 끝나지 않으므로 파일로 받는다
        p = subprocess.run(["ssh", "-f", "-N", *target.options(), "-o", "ExitOnForwardFailure=yes",
                            "-o", "ServerAliveInterval=30", "-L", f"{port}:127.0.0.1:8000", target.user_host],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err, timeout=40)
        if p.returncode != 0:
            err.seek(0)
            raise PodError(f"터널을 열지 못했습니다: {err.read().strip()[-200:]}")
    print(f"터널: 포트 {port} → Pod 8000 연결")


def _request(url: str, key: str, body: dict | None = None, timeout: int = 15):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.load(r)


def verify_model(base_url: str, key: str, model: str) -> None:
    """키가 맞는지, 그 모델이 올라와 있는지, 실제로 생성이 되는지 본다."""
    url = urlparse(base_url)
    root = f"{url.scheme}://{url.netloc}/v1"
    for attempt in range(5):
        try:
            served = [m["id"] for m in _request(f"{root}/models", key)["data"]]
            break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise PodError("서버의 키가 .env의 키와 다릅니다. --restart를 붙여 다시 실행해 주세요.") from None
            raise PodError(f"모델 목록을 받지 못했습니다: HTTP {e.code}") from None
        except OSError as e:
            if attempt == 4:
                raise PodError(f"{root}에 닿지 못했습니다: {e}") from None
            time.sleep(2)
    if model not in served:
        raise PodError(f"다른 모델이 올라와 있습니다: {served}. --restart를 붙여 다시 실행해 주세요.")
    try:
        _request(f"{root}/chat/completions", key, {"model": model, "max_tokens": 1,
                                                   "messages": [{"role": "user", "content": "1"}]}, timeout=120)
    except (OSError, urllib.error.HTTPError) as e:
        raise PodError(f"모델은 올라와 있지만 생성에 실패했습니다: {e}") from None
    print(f"모델 응답 확인: {model}")


def up(target: Target, model: str, key: str, base_url: str, *, restart: bool = False, timeout: int = WAIT_SECONDS,
       run=None, sleep=time.sleep, open_tunnel=open_ssh_tunnel, verify=verify_model) -> None:
    run = run or ssh_runner(target)
    mask = _Mask(key)
    try:
        state = _probe(run, model)
    except PodError as e:
        raise _connect_error(e) from None
    print(f"Pod: GPU {state.get('gpu') or '없음'}, 디스크 여유 {state.get('free') or '?'}, "
          f"서버 {'응답함' if state.get('health') == '200' else '응답 없음'}", flush=True)

    if restart and state.get("gpu") and state.get("serving"):
        print("서버를 내립니다.", flush=True)
        run(STOP_SCRIPT, timeout=60)
        state = _probe(run, model)

    action = decide(state)
    if action == "no_gpu":
        raise PodError("이 Pod에서 GPU를 찾지 못했습니다. 설치하지 않고 멈춥니다.")
    if action in ("setup", "serve"):
        print("설치부터 시작합니다. 15~25분 걸립니다." if action == "setup" else "설치되어 있어 서버만 띄웁니다.", flush=True)
        _upload_and_start(run, model, key, action)
    if action != "ready":
        _wait(run, model, mask, sleep, timeout)
    print("vLLM 서버 준비됨", flush=True)

    port = tunnel_port(base_url)
    if port:
        open_tunnel(target, port)
    verify(base_url, key, model)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="접속 명령어 하나로 Pod에 vLLM을 띄우고 터널을 연결한다")
    parser.add_argument("ssh", help='RunPod 콘솔의 접속 명령어. 예: "ssh root@1.2.3.4 -p 11376 -i ~/.ssh/id_ed25519"')
    parser.add_argument("--tag", default=POD_TAG, help="configs/models.yaml의 모델 태그")
    parser.add_argument("--restart", action="store_true", help="떠 있는 서버를 내리고 다시 띄운다 (키나 모델이 바뀐 경우)")
    parser.add_argument("--timeout", type=int, default=WAIT_SECONDS, help="준비를 기다릴 최대 초")
    args = parser.parse_args(argv)

    cfg = load_model_config(args.tag)
    key, base_url = os.getenv(cfg["api_key_env"]), os.getenv(cfg["base_url_env"])
    try:
        if not key:
            raise PodError(f".env의 {cfg['api_key_env']}가 비어 있습니다. "
                           "만들기 예: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'")
        if not base_url:
            raise PodError(f".env의 {cfg['base_url_env']}가 비어 있습니다. 예: http://127.0.0.1:18000/v1")
        up(parse_ssh(args.ssh), cfg["model"], key, base_url, restart=args.restart, timeout=args.timeout)
    except PodError as e:
        print(f"실패: {e}", file=sys.stderr)
        return 1
    print("끝났습니다. 8020 서버가 이 모델을 쓸 수 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
