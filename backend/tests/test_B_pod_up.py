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


# ── 태그별 서버 설정 (48GB 시험대, 결정적 모드) ──

def test_server_settings_default_matches_a100_serving(pod_up):
    # 설정이 없는 태그는 지금까지 serve_vllm.sh가 쓰던 값 그대로 띄운다
    assert pod_up.server_settings({}) == {"max_model_len": 40960, "max_num_seqs": 64,
                                          "gpu_memory_utilization": 0.85, "batch_invariant": False,
                                          "prefix_caching": True}


def test_server_settings_reads_tag_values(pod_up):
    s = pod_up.server_settings({"server": {"max_model_len": 49152, "max_num_seqs": 8, "batch_invariant": True,
                                           "prefix_caching": False}})
    assert s["max_model_len"] == 49152 and s["max_num_seqs"] == 8
    assert s["batch_invariant"] is True and s["prefix_caching"] is False


@pytest.mark.parametrize("server, hint", [
    ({"max_model_len": "4096; rm -rf /"}, "max_model_len"),          # 셸로 넘어가는 값이라 숫자만 받는다
    ({"max_num_seqs": 0}, "max_num_seqs"),
    ({"gpu_memory_utilization": 1.5}, "gpu_memory_utilization"),
    ({"batch_invariant": "yes"}, "batch_invariant"),
    ({"max_seqs": 8}, "max_seqs"),                                    # 오타는 조용히 무시하지 않는다
])
def test_server_settings_refuses_bad_values(pod_up, server, hint):
    with pytest.raises(pod_up.PodError, match=hint):
        pod_up.server_settings({"server": server})


def test_start_script_passes_settings_and_records_them(pod_up):
    s = pod_up.server_settings({"server": {"max_num_seqs": 8, "batch_invariant": True, "prefix_caching": False}})
    script = pod_up.start_script(MODEL, "serve", s)
    for part in ("MAX_NUM_SEQS=8", "BATCH_INVARIANT=1", "PREFIX_CACHING=0", "serve_settings"):
        assert part in script
    assert subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True).returncode == 0


def test_serve_script_applies_settings(pod_up):
    # serve_vllm.sh를 vllm 없이 돌려 넘긴 설정이 명령 줄과 환경에 들어가는지 본다
    serve = (pod_up.REMOTE_DIR / "serve_vllm.sh").read_text()
    fake = serve.replace("exec /workspace/venv/bin/vllm", 'echo "VBI=${VLLM_BATCH_INVARIANT:-}"; echo')
    fake = fake.replace("export VLLM_API_KEY=$(cat /workspace/vllm_api_key)", "VLLM_API_KEY=x")
    env = {"PATH": "/usr/bin:/bin", "MAX_MODEL_LEN": "49152", "MAX_NUM_SEQS": "8", "GPU_UTIL": "0.9",
           "BATCH_INVARIANT": "1", "PREFIX_CACHING": "0"}
    out = subprocess.run(["bash", "-s", MODEL], input=fake, text=True, capture_output=True, env=env).stdout
    assert "VBI=1" in out
    assert "--max-model-len 49152" in out and "--max-num-seqs 8" in out and "--gpu-memory-utilization 0.9" in out
    assert "--no-enable-prefix-caching" in out
    default = subprocess.run(["bash", "-s", MODEL], input=fake, text=True, capture_output=True,
                             env={"PATH": "/usr/bin:/bin"}).stdout
    assert "VBI=" in default and "VBI=1" not in default
    assert "--max-model-len 40960" in default and "--no-enable-prefix-caching" not in default


def test_start_script_detaches_with_fork(pod_up):
    # '&'만 쓰면 sshd가 작업이 끝날 때까지 접속을 붙잡는 Pod가 있다 (11/3). setsid -f로 떼어 낸다
    script = pod_up.start_script(MODEL, "setup")
    assert "setsid -f" in script and not script.rstrip().endswith("&")


def test_request_sends_own_user_agent(pod_up, monkeypatch):
    # RunPod 프록시는 Python-urllib User-Agent를 403으로 막는다 (11/3)
    seen = {}

    class Opener:
        def open(self, req, timeout):
            seen.update(req.headers)
            raise OSError("stop")
    monkeypatch.setattr(pod_up.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(OSError):
        pod_up._request("https://p/v1/models", KEY)
    assert seen.get("User-agent") == pod_up.USER_AGENT


def test_probe_reports_running_settings(pod_up):
    assert "serve_settings" in pod_up.probe_script(MODEL)


def test_server_with_other_settings_needs_restart(pod_up):
    # 결정적 모드 시험에 기본 모드 서버를 쓰면 결과가 틀린 결론이 된다
    want = pod_up.server_settings({"server": {"batch_invariant": True}})
    run, calls = fake_pod([{"health": "200", "serving": "1",
                            "settings": pod_up.settings_line(pod_up.server_settings({}))}])
    with pytest.raises(pod_up.PodError, match="--restart"):
        go(pod_up, run, settings=want)
    assert "setsid" not in scripts(calls)


def test_server_with_same_settings_is_reused(pod_up):
    want = pod_up.server_settings({"server": {"batch_invariant": True}})
    run, calls = fake_pod([{"health": "200", "serving": "1", "settings": pod_up.settings_line(want)}])
    assert go(pod_up, run, settings=want) == {"tunnel": 1, "verify": 1}


def test_restart_starts_with_new_settings(pod_up):
    want = pod_up.server_settings({"server": {"max_num_seqs": 8}})
    run, calls = fake_pod([{"health": "200", "serving": "1", "installed": "1", "settings": "old"},
                           {"installed": "1"}, {"health": "200"}])
    go(pod_up, run, restart=True, settings=want)
    assert "MAX_NUM_SEQS=8" in [c.script for c in calls if "setsid" in c.script][0]


def test_every_tag_server_settings_are_valid(pod_up):
    import yaml
    from msds.common.paths import ROOT
    cfg = yaml.safe_load((ROOT / "backend" / "configs" / "models.yaml").read_text(encoding="utf-8"))
    for tag, m in cfg["models"].items():
        pod_up.server_settings(m)                                     # 형식이 틀리면 PodError
    det = pod_up.server_settings(cfg["models"]["qwen36_35b_runpod_48g_det"])
    assert det["batch_invariant"] and not det["prefix_caching"] and det["max_num_seqs"] == 8


# ── Pod 정보 (GPU 세대, Pod 번호, 팀원용 주소, 디스크). Pod를 바꿔도 접속 명령만 바꾸면 된다 ──

def test_probe_reports_compute_capability_and_pod_id(pod_up):
    script = pod_up.probe_script(MODEL)
    assert "compute_cap" in script and "RUNPOD_POD_ID" in script
    assert subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True).returncode == 0


@pytest.mark.parametrize("text, gb", [("50G", 50.0), ("1.5T", 1536.0), ("800M", 0.78125), ("", None), ("?", None)])
def test_free_gb(pod_up, text, gb):
    assert pod_up.free_gb(text) == gb


def test_team_url(pod_up):
    assert pod_up.team_url("zmb35ot48dwh6t") == "https://zmb35ot48dwh6t-8000.proxy.runpod.net/v1"
    assert pod_up.team_url("") is None


def test_up_prints_gpu_generation_pod_id_and_team_url(pod_up, capsys):
    run, _ = fake_pod([{"health": "200", "cap": "8.6", "pod_id": "abc123"}])
    go(pod_up, run)
    out = capsys.readouterr().out
    assert "8.6" in out and "https://abc123-8000.proxy.runpod.net/v1" in out


def test_small_disk_warns_before_install(pod_up, capsys):
    # 모델(약 36GB)과 vLLM 환경이 들어갈 자리가 빠듯하면 설치 전에 알린다. 멈추지는 않는다
    run, calls = fake_pod([{"free": "50G"}, {"health": "200"}])
    go(pod_up, run)
    assert "디스크" in capsys.readouterr().out
    assert any("setup_vllm.sh" in c.script for c in calls)


def test_enough_disk_does_not_warn(pod_up, capsys):
    run, _ = fake_pod([{"free": "200G"}, {"health": "200"}])
    go(pod_up, run)
    assert "디스크" not in capsys.readouterr().out
