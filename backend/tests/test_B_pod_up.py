"""scripts/pod_up.py 시험. ssh와 네트워크를 부르지 않고 가짜로 끼운다. 키는 어디에도 찍히면 안 된다."""
import importlib
import subprocess
from types import SimpleNamespace

import pytest

from test_B_compare_models import SCRIPTS

KEY = "vllm-test-SHOULD-NEVER-APPEAR-1a2b3c"
MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"


@pytest.fixture
def pod_up(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("pod_up")


# ── 접속 명령어 읽기 ──

def test_parse_reads_runpod_command(pod_up):
    t = pod_up.parse_ssh("ssh root@157.254.50.67 -p 11376 -i ~/.ssh/id_ed25519")
    assert (t.user_host, t.port) == ("root@157.254.50.67", 11376)
    assert t.identity.endswith("/.ssh/id_ed25519") and "~" not in t.identity


def test_parse_works_without_ssh_word_and_identity(pod_up):
    t = pod_up.parse_ssh("root@1.2.3.4 -p 22")
    assert (t.user_host, t.port, t.identity) == ("root@1.2.3.4", 22, None)


@pytest.mark.parametrize("text, hint", [
    ("ssh root@1.2.3.4 -p <포트> -i ~/.ssh/k", "포트"),            # 자리 표시를 그대로 붙인 경우
    ("ssh root@1.2.3.4 -o ProxyCommand=sh", "-o"),                  # 임의 명령을 실행할 수 있는 옵션
    ("ssh -p 22", "user@host"),
    ("ssh abc-644@ssh.runpod.io -i ~/.ssh/k", "TCP"),               # 프록시 주소는 명령 실행이 안 된다
    ("ssh root@1.2.3.4 -p 99999", "포트"),
    ("ssh root@1.2.3.4;rm -p 22", "user@host"),
])
def test_parse_refuses_with_reason(pod_up, text, hint):
    with pytest.raises(pod_up.PodError, match=hint):
        pod_up.parse_ssh(text)


# ── 다음에 할 일 ──

@pytest.mark.parametrize("state, action", [
    (dict(health="200"), "ready"),
    (dict(setup_running="1"), "wait"),
    (dict(serving="1"), "wait"),
    (dict(installed="1"), "serve"),
    (dict(), "setup"),
])
def test_decide(pod_up, state, action):
    assert pod_up.decide({"gpu": "A100", **state}) == action


def test_decide_refuses_pod_without_gpu(pod_up):
    assert pod_up.decide({"gpu": ""}) == "no_gpu"


@pytest.mark.parametrize("url, port", [
    ("http://127.0.0.1:18000/v1", 18000),
    ("http://localhost:18001", 18001),
    ("https://abc-8000.proxy.runpod.net/v1", None),
])
def test_tunnel_port(pod_up, url, port):
    assert pod_up.tunnel_port(url) == port


# ── 처음부터 끝까지 (가짜 Pod) ──

def fake_pod(states, *, logs=""):
    """probe마다 states를 차례로 돌려주고, 부른 스크립트와 stdin을 기록한다."""
    calls, queue = [], list(states)

    def run(script, stdin=None, timeout=60):
        calls.append(SimpleNamespace(script=script, stdin=stdin))
        if "echo gpu=" in script:
            s = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(s, Exception):
                raise s
            lines = {"gpu": "A100", "free": "100G", "health": "000", "setup_running": "", "serving": "",
                     "installed": "", "last": "", **s}
            return "\n".join(f"{k}={v}" for k, v in lines.items())
        return logs
    return run, calls


def go(pod_up, run, **kw):
    done = {"tunnel": 0, "verify": 0}
    pod_up.up(pod_up.parse_ssh("ssh root@1.2.3.4 -p 2200"), MODEL, KEY, "http://127.0.0.1:18000/v1", run=run,
              sleep=lambda s: None, open_tunnel=lambda t, p: done.__setitem__("tunnel", done["tunnel"] + 1),
              verify=lambda *a: done.__setitem__("verify", done["verify"] + 1), **kw)
    return done


def scripts(calls):
    return "\n".join(c.script for c in calls)


def test_new_pod_installs_serves_and_connects(pod_up, capsys):
    run, calls = fake_pod([{}, {"setup_running": "1", "last": f"args api_key {KEY}"}, {"health": "200"}])
    done = go(pod_up, run)
    assert "setup_vllm.sh" in scripts(calls) and "serve_vllm.sh" in scripts(calls)
    assert done == {"tunnel": 1, "verify": 1}
    assert KEY not in scripts(calls)                                  # 명령 줄에 키를 넣지 않는다
    assert any(c.stdin == KEY for c in calls)                         # stdin으로만 보낸다
    assert KEY not in "".join(capsys.readouterr())                    # 로그에 찍힌 키도 가린다


def test_installed_pod_only_starts_server(pod_up):
    run, calls = fake_pod([{"installed": "1"}, {"health": "200"}])
    go(pod_up, run)
    start = [c.script for c in calls if "setsid" in c.script]
    assert len(start) == 1 and "./setup_vllm.sh" not in start[0] and "./serve_vllm.sh" in start[0]


def test_running_pod_only_reconnects_tunnel(pod_up):
    run, calls = fake_pod([{"health": "200"}])
    done = go(pod_up, run)
    assert done == {"tunnel": 1, "verify": 1}
    assert "setsid" not in scripts(calls) and not any(c.stdin for c in calls)


def test_setup_in_progress_is_not_started_twice(pod_up):
    run, calls = fake_pod([{"setup_running": "1"}, {"health": "200"}])
    go(pod_up, run)
    assert "setsid" not in scripts(calls)


def test_restart_stops_server_then_starts(pod_up):
    run, calls = fake_pod([{"health": "200", "serving": "1", "installed": "1"}, {"installed": "1"}, {"health": "200"}])
    go(pod_up, run, restart=True)
    text = scripts(calls)
    assert text.index("pkill") < text.index("setsid")


def test_failed_setup_stops_and_shows_masked_log(pod_up, capsys):
    run, calls = fake_pod([{}, {}], logs=f"No space left on device {KEY}")
    with pytest.raises(pod_up.PodError, match="멈췄") as e:
        go(pod_up, run)
    assert "No space left" in str(e.value) and KEY not in str(e.value)


def test_timeout_says_install_keeps_running(pod_up):
    run, _ = fake_pod([{}, {"setup_running": "1"}])
    with pytest.raises(pod_up.PodError, match="계속"):
        go(pod_up, run, timeout=0)


def test_refused_connection_explains_what_to_check(pod_up):
    run, _ = fake_pod([pod_up.PodError("ssh: connect to host port 2200: Connection refused")])
    with pytest.raises(pod_up.PodError, match="콘솔"):
        go(pod_up, run)


def test_brief_ssh_drop_while_waiting_is_tolerated(pod_up):
    run, _ = fake_pod([{}, pod_up.PodError("Connection reset"), {"health": "200"}])
    assert go(pod_up, run)["verify"] == 1


def test_no_gpu_stops_before_install(pod_up):
    run, calls = fake_pod([{"gpu": ""}])
    with pytest.raises(pod_up.PodError, match="GPU"):
        go(pod_up, run)
    assert "setsid" not in scripts(calls)


def test_proxy_address_skips_tunnel(pod_up):
    run, _ = fake_pod([{"health": "200"}])
    opened = []
    pod_up.up(pod_up.parse_ssh("root@1.2.3.4"), MODEL, KEY, "https://x-8000.proxy.runpod.net/v1", run=run,
              sleep=lambda s: None, open_tunnel=lambda *a: opened.append(a), verify=lambda *a: None)
    assert opened == []


# ── Pod에 보내는 스크립트 ──

def test_remote_scripts_are_valid_bash(pod_up):
    for path in pod_up.REMOTE_SCRIPTS:
        assert subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0
    for script in (pod_up.probe_script(MODEL), pod_up.start_script(MODEL, "setup"), pod_up.STOP_SCRIPT):
        assert subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True).returncode == 0


def test_setup_and_probe_agree_on_ready_marker(pod_up):
    # setup_vllm.sh가 치환해 만드는 이름과 probe가 찾는 이름이 같아야 다음 실행에서 건너뛴다
    done = subprocess.run(["bash", "-c", 'M="$1"; echo "/workspace/.vllm_ready_${M//\\//_}"', "_", MODEL],
                          capture_output=True, text=True).stdout.strip()
    assert done in pod_up.probe_script(MODEL)
