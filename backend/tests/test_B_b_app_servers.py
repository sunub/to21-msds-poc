"""scripts/b_app_servers.py 시험. 네트워크·ssh를 부르지 않고 opener·runner를 가짜로 끼운다. 키는 어디에도 나오면 안 된다."""
import importlib
import json

import pytest

from test_B_compare_models import SCRIPTS

FAKE_KEY = "sk-test-SHOULD-NEVER-APPEAR-9f8e7d"
MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"
CFG = {"model": MODEL, "base_url_env": "RUNPOD_VLLM_BASE_URL", "api_key_env": "RUNPOD_VLLM_API_KEY"}
ENV = {"RUNPOD_VLLM_BASE_URL": "http://127.0.0.1:1/v1", "RUNPOD_VLLM_API_KEY": FAKE_KEY,
       "RNGD_SSH": "-i ~/.ssh/fake -p 22 user@host"}


@pytest.fixture
def srv(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_servers")


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_of(payload=None, error=None, seen=None):
    def op(req, timeout=None):
        if seen is not None:
            seen.append(req)
        if error:
            raise error
        return FakeResp(payload)
    return op


def no_key(*objs):
    assert FAKE_KEY not in json.dumps(objs, ensure_ascii=False, default=str)


def test_model_status_no_url(srv):
    s = srv.model_status("t", CFG, {})
    assert s["url_set"] is False and s["reachable"] is False and s["match"] is None


def test_model_status_match(srv):
    seen = []
    s = srv.model_status("t", CFG, ENV, opener=opener_of({"data": [{"id": MODEL}]}, seen=seen))
    assert s["reachable"] and s["match"] is True and s["model_expected"] == MODEL
    assert seen[0].full_url == "http://127.0.0.1:1/v1/models"
    assert seen[0].get_header("Authorization") == f"Bearer {FAKE_KEY}"
    no_key(s)


def test_model_status_mismatch(srv):
    s = srv.model_status("t", CFG, ENV, opener=opener_of({"data": [{"id": "other/model"}]}))
    assert s["match"] is False and s["model_served"] == "other/model"


def test_model_status_exception_only_kind(srv):
    s = srv.model_status("t", CFG, ENV, opener=opener_of(error=ConnectionRefusedError(f"boom {FAKE_KEY}")))
    assert s["reachable"] is False and s["error"] == "ConnectionRefusedError"
    no_key(s)


def test_all_model_status_filters_tags(srv):
    cfg = {"models": {"gpt": {"model": "g", "base_url_env": "LLM_BASE_URL", "api_key_env": "LLM_API_KEY"},
                      "a": {**CFG}, "b": {**CFG, "base_url_env": "RNGD_BASE_URL"}, "c": {**CFG, "base_url_env": "VLLM_BASE_URL"}}}
    out = srv.all_model_status(cfg, {}, opener=opener_of({"data": []}))
    assert [s["tag"] for s in out] == ["a", "b", "c"]


def test_rngd_ssh_args(srv):
    args = srv.rngd_ssh_args(ENV)
    assert args[:4] == ["ssh", "-n", "-o", "BatchMode=yes"] and args[-1] == "user@host"
    assert srv.rngd_ssh_args({}) is None


def test_rngd_ps_masks_api_key(srv):
    out = ("PID 1\n  777 furiosa-llm /usr/local/bin/furiosa-llm serve Qwen/X --devices npu:0 --api-key abc123 --port 8000\n")

    def runner(args, timeout):
        return 0, out, ""
    r = srv.rngd_ps(ENV, runner=runner)
    assert r["ok"] and "abc123" not in r["text"] and "***" in r["text"]
    assert r["models"] == [{"pid": 777, "model": "Qwen/X", "elapsed_s": None}]   # 옛 모양(pid comm args)은 지난 시간 모름


def test_rngd_ps_without_ssh(srv):
    r = srv.rngd_ps({})
    assert r["ok"] is False and r["error"]


def test_rngd_down_kills_pids(srv):
    calls = []

    def runner(args, timeout):
        calls.append(args)
        cmd = args[-1]
        if "pgrep" in cmd:
            return 0, "123\n456\n", ""
        return 0, "", ""
    r = srv.rngd_down("Qwen/X", ENV, runner=runner, sleep=lambda s: None)
    assert r["killed"] == [123, 456] and r["ok"] and r["remaining"] == []
    assert all("-n" in a and "BatchMode=yes" in a for a in calls)
    assert any("kill -TERM" in a[-1] for a in calls)


def test_rngd_down_rejects_odd_model_name(srv):
    r = srv.rngd_down("x; rm -rf /", ENV, runner=lambda a, t: (0, "", ""), sleep=lambda s: None)
    assert r["ok"] is False


def test_rngd_up_command(srv):
    calls = []

    def runner(args, timeout):
        calls.append((args, timeout))
        return 0, "", ""
    r = srv.rngd_up("Qwen/X", "npu:0,npu:1,npu:2,npu:3", ENV, log_name="qwen_x", runner=runner)
    assert r["ok"]
    cmd = calls[0][0][-1]
    assert "setsid nohup" in cmd and "--devices npu:0,npu:1,npu:2,npu:3" in cmd
    assert "$(cat /root/to21-bc/api_key)" in cmd and "/root/to21-bc/qwen_x.log" in cmd
    assert "-n" in calls[0][0] and calls[0][1] == 30
    no_key(cmd)


def test_rngd_up_without_ssh(srv):
    r = srv.rngd_up("Qwen/X", "npu:0", {}, log_name="l", runner=lambda a, t: (0, "", ""))
    assert r["ok"] is False and r["error"]


def test_mask_keys(srv):
    t = f"--api-key zzz and Authorization: Bearer yyy and {FAKE_KEY}"
    m = srv.mask_keys(t, [FAKE_KEY])
    assert "zzz" not in m and "yyy" not in m and FAKE_KEY not in m


def test_append_server_log(srv, tmp_path):
    p = tmp_path / "manual" / "server_log.md"
    srv.append_server_log(p, "pod_create", target="abc", note="ok")
    srv.append_server_log(p, "pod_delete", target="abc", note=f"api_key={FAKE_KEY}", api_key=FAKE_KEY)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert text.count("| 시각 |") == 1 and len([l for l in lines if "pod_" in l]) == 2
    assert FAKE_KEY not in text


@pytest.mark.parametrize("prefix", ["ssh ", "  ssh  ", "'ssh' "])
def test_ssh_accepts_command_or_arguments(srv, prefix):
    assert srv.rngd_ssh_args({**ENV, "RNGD_SSH": prefix + ENV["RNGD_SSH"]}) == srv.rngd_ssh_args(ENV)


def test_ssh_preserves_quoted_arguments(srv):
    value = '-i "<키 경로>" -p <포트> <사용자>@<호스트>'
    expected = ["ssh", "-n", "-o", "BatchMode=yes", "-i", "<키 경로>", "-p", "<포트>", "<사용자>@<호스트>"]
    assert srv.rngd_ssh_args({"RNGD_SSH": value}) == expected
    assert srv.rngd_ssh_args({"RNGD_SSH": "ssh " + value}) == expected


def test_model_status_friendly_missing_url(srv):
    result = srv.model_status("t", CFG, {}, opener=lambda *a, **kw: pytest.fail("must not call"))
    assert result["error"] is None  # 기존 응답 키는 그대로 둔다.
    assert CFG["base_url_env"] in result["friendly"]["message"]
    assert result["friendly"]["raw"] == "주소 설정 없음"


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("error", [ConnectionRefusedError, TimeoutError])
def test_model_status_friendly_connection_failure(srv, wrapped, error):
    from urllib.error import URLError
    exc = error(FAKE_KEY)
    if wrapped:
        exc = URLError(exc)
    result = srv.model_status("t", CFG, ENV, opener=opener_of(error=exc))
    assert result["error"] == type(exc).__name__
    assert result["friendly"]["message"] == "서버가 응답하지 않습니다."
    no_key(result)


# ── RNGD 터널 (step 6) ─────────────────────────────────────

TUNNEL_ENV = {**ENV, "RNGD_BASE_URL": "http://127.0.0.1:18000/v1", "RNGD_API_KEY": FAKE_KEY}
TUNNEL_ARGS = ["ssh", "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
               "-L", "18000:127.0.0.1:8000", "-i", "~/.ssh/fake", "-p", "22", "user@host"]


def test_rngd_ps_reads_elapsed_seconds(srv):
    seen = []
    out = ("+ 가상 표 +\n  777  1234 furiosa-llm /usr/local/bin/furiosa-llm serve Qwen/X --api-key abc123 --port 8000\n"
           "  778 furiosa-llm /usr/local/bin/furiosa-llm serve Qwen/Y --port 8000\n")

    def runner(args, timeout):
        seen.append(args[-1])
        return 0, out, ""
    r = srv.rngd_ps(ENV, runner=runner)
    assert "ps -eo pid,etimes,comm,args" in seen[0] and "furiosa-smi ps" in seen[0]
    assert r["models"] == [{"pid": 777, "model": "Qwen/X", "elapsed_s": 1234},
                           {"pid": 778, "model": "Qwen/Y", "elapsed_s": None}]
    assert "abc123" not in r["text"]


@pytest.mark.parametrize("url, port", [
    ("http://127.0.0.1:18000/v1", 18000), ("http://localhost:18001/v1", 18001),
    ("http://10.0.0.5:8000/v1", None), ("https://rngd.example.com:8000/v1", None),
    ("http://127.0.0.1/v1", None), ("http://127.0.0.1:포트/v1", None), ("", None), (None, None),
])
def test_tunnel_port(srv, url, port):
    env = {} if url is None else {"RNGD_BASE_URL": url}
    assert srv.tunnel_port(env) == port


@pytest.mark.parametrize("prefix", ["", "ssh ", "  ssh  "])
def test_tunnel_args(srv, prefix):
    args = srv.tunnel_args({**TUNNEL_ENV, "RNGD_SSH": prefix + ENV["RNGD_SSH"]})
    assert args == TUNNEL_ARGS
    assert srv.RNGD_REMOTE_PORT == 8000
    no_key(args)                                                    # RNGD_API_KEY 값을 넣지 않는다


def test_tunnel_args_none_without_ssh_or_local_port(srv):
    assert srv.tunnel_args({**TUNNEL_ENV, "RNGD_BASE_URL": "http://10.0.0.5:8000/v1"}) is None
    assert srv.tunnel_args({k: v for k, v in TUNNEL_ENV.items() if k != "RNGD_BASE_URL"}) is None
    assert srv.tunnel_args({k: v for k, v in TUNNEL_ENV.items() if k != "RNGD_SSH"}) is None
    assert srv.tunnel_args({**TUNNEL_ENV, "RNGD_SSH": "ssh"}) is None


class FakeSock:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_port_open_true_and_closes(srv):
    seen, socks = [], []

    def connector(address, timeout=None):
        seen.append((address, timeout))
        socks.append(FakeSock())
        return socks[-1]
    assert srv.port_open(18000, connector=connector) is True
    assert seen == [(("127.0.0.1", 18000), 0.5)] and socks[0].closed


@pytest.mark.parametrize("error", [ConnectionRefusedError, PermissionError, TimeoutError, OSError])
def test_port_open_false_on_os_errors(srv, error):
    def connector(address, timeout=None):
        raise error("가상")
    assert srv.port_open(18000, connector=connector, timeout=0.1) is False
