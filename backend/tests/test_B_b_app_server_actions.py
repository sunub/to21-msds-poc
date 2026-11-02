"""scripts/b_app_servers.py의 ServerActions 시험 (작업 화면 탭 ⑤ 서버, ADR-025).

네트워크·ssh·subprocess를 부르지 않는다. RunPod REST와 모델 서버 /v1/models는 가짜 opener, RNGD ssh는 가짜 runner,
4시간 감시 프로세스는 가짜 watchdog_spawner, 시각은 가짜 clock으로 바꾼다. RNGD 터널은 가짜 connector(열린 포트 집합),
가짜 tunnel_spawner, 가짜 ps 글, 가짜 killer로 바꾼다(진짜 127.0.0.1 연결과 ps를 부르면 사용자 컴퓨터의 터널에 따라 결과가 달라진다).
키(RunPod 키, RNGD 키, 앱이 만든 vLLM 키)는 어떤 응답·로그에도 나오면 안 된다 (CLAUDE.md CRITICAL).
"""
import importlib
import json
import re
import signal
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_B_b_app_jobs import FakeSpawner, TAG, app, bj, call, ctx_of, manager, where  # noqa: F401  픽스처
from test_B_b_app_runs import env  # noqa: F401  픽스처
from test_B_compare_models import SCRIPTS, X01

FAKE_KEY = "FAKEKEY-runpod-SHOULD-NEVER-APPEAR-9f8e7d"          # 흔한 키 모양(sk-, rpa_)이 아니어도 가려져야 한다
RNGD_KEY = "FAKEKEY-rngd-client-SHOULD-NEVER-APPEAR-4c3b"
RNGD_REMOTE_KEY = "FAKEKEY-rngd-remote-SHOULD-NEVER-APPEAR-11aa"  # RNGD ps 글에 찍히는 --api-key 값
OLD_VLLM_KEY = "FAKEKEY-old-vllm-SHOULD-NEVER-APPEAR-5e6f"
SECRETS = (FAKE_KEY, RNGD_KEY, RNGD_REMOTE_KEY, OLD_VLLM_KEY)

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"
QWEN30 = "fake-org/Qwen3-30B-fake"
GPTOSS = "fake-org/gpt-oss-fake"
RNGD_URL = "http://127.0.0.1:18000/v1"
MODELS_CFG = {"models": {
    "claude": {"model": "fake-claude", "base_url_env": "LLM_BASE_URL", "api_key_env": "LLM_API_KEY"},
    "qwen3_30b_a3b_rngd": {"model": QWEN30, "base_url_env": "RNGD_BASE_URL", "api_key_env": "RNGD_API_KEY"},
    "gpt_oss_20b_rngd": {"model": GPTOSS, "base_url_env": "RNGD_BASE_URL", "api_key_env": "RNGD_API_KEY"},
    "qwen36_35b_runpod": {"model": MODEL, "base_url_env": "RUNPOD_VLLM_BASE_URL", "api_key_env": "RUNPOD_VLLM_API_KEY"}}}
ENV = {"RUNPOD_API_KEY": FAKE_KEY, "RNGD_SSH": "-i ~/.ssh/fake -p 22 user@host",
       "RNGD_BASE_URL": RNGD_URL, "RNGD_API_KEY": RNGD_KEY,
       "RUNPOD_VLLM_BASE_URL": "http://127.0.0.1:1/v1", "RUNPOD_VLLM_API_KEY": OLD_VLLM_KEY}
LOCK_RUN = {"mine": False, "pid": 101, "kind": "run", "run_name": "20261030_sections_가상_dev10_r2", "model": TAG,
            "doc": None}


@pytest.fixture
def srv(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_servers")


@pytest.fixture
def pod(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("pod")


class FakeResp:
    def __init__(self, payload):
        self._b = b"" if payload is None else json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def pod_of(pod_id, name, minutes, cost=2.49):
    return {"id": pod_id, "name": name, "desiredStatus": "RUNNING", "costPerHr": cost, "imageName": "가상",
            "gpuCount": 1, "lastStatusChange": (NOW - timedelta(minutes=minutes)).isoformat()}


class FakeCloud:
    """RunPod REST와 모델 서버의 /v1/models를 흉내 낸다. served에 없는 주소는 연결 거부."""

    def __init__(self, pods=(), served=None):
        self.pods = [dict(p) for p in pods]
        self.served = dict(served or {})
        self.requests = []

    def __call__(self, req, timeout=None):
        from pod import API
        url, method = req.full_url, req.get_method()
        body = json.loads(req.data) if req.data else None
        self.requests.append({"url": url, "method": method, "body": body, "auth": req.get_header("Authorization")})
        if url.startswith(API):
            path = url[len(API):]
            if path == "/pods" and method == "GET":
                return FakeResp(self.pods)
            if path == "/pods" and method == "POST":
                pid = f"newpod{sum(r['method'] == 'POST' for r in self.requests)}"
                self.pods.append({**pod_of(pid, body["name"], 0), "env": body["env"]})
                return FakeResp({"id": pid, "env": body["env"]})      # 진짜 RunPod도 env를 돌려준다
            if path.startswith("/pods/") and method == "DELETE":
                self.pods = [p for p in self.pods if p["id"] != path.rsplit("/", 1)[1]]
                return FakeResp(None)
            if path == "/networkvolumes":
                return FakeResp([])
        if url.endswith("/models"):
            base = url[:-len("/models")]
            if base in self.served:
                return FakeResp({"data": [{"id": m} for m in self.served[base]]})
            raise urllib.error.URLError(ConnectionRefusedError())
        raise AssertionError(f"모르는 요청: {method} {url}")

    def sent(self, method):
        return [r for r in self.requests if r["method"] == method]


class FakeRngd:
    """ssh runner. 떠 있는 모델을 기억하고 furiosa-smi ps·pgrep·kill·serve 명령에 답한다."""

    def __init__(self, up=(), elapsed=None):
        self.up = {m: 700 + i for i, m in enumerate(up)}
        self.elapsed = dict(elapsed or {})       # 모델 → 지난 초. 주면 ps 줄을 pid etimes comm args 모양으로 쓴다
        self.calls = []

    def __call__(self, args, timeout):
        self.calls.append(list(args))
        cmd = args[-1]
        if cmd.startswith("furiosa-smi ps"):
            rows = [f"  {pid} " + (f"{self.elapsed[m]} " if m in self.elapsed else "")
                    + f"furiosa-llm /usr/bin/python3 /usr/local/bin/furiosa-llm serve {m} --devices npu:0 "
                    f"--api-key {RNGD_REMOTE_KEY} --port 8000" for m, pid in self.up.items()]
            return 0, "+ 가상 furiosa-smi 표 +\n" + "\n".join(rows) + "\n", ""
        if cmd.startswith("pgrep"):
            pids = [str(p) for m, p in self.up.items() if f"serve {m}" in cmd]
            return (0 if pids else 1), "\n".join(pids), ""
        if cmd.startswith("kill -TERM"):
            dead = {int(x) for x in cmd.split()[2:]}
            self.up = {m: p for m, p in self.up.items() if p not in dead}
            return 0, "", ""
        if "setsid nohup" in cmd:
            self.up[re.search(r"serve (\S+)", cmd)[1]] = 900
            return 0, "", ""
        raise AssertionError(f"모르는 명령: {cmd}")


class FakeJobs:
    def __init__(self, running=()):
        self.now = list(running)
        self.python, self.backend_dir = Path("/가상/python"), Path("/가상/backend")

    def running(self):
        return list(self.now)


class FakeWatchProc:
    pid = 4242

    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


class FakeWatch:
    def __init__(self):
        self.calls, self.procs = [], []

    def __call__(self, argv, cwd):
        self.calls.append({"argv": list(argv), "cwd": Path(cwd)})
        self.procs.append(FakeWatchProc())
        return self.procs[-1]


class Clock:
    def __init__(self):
        self.t = NOW.timestamp()

    def __call__(self):
        return self.t


class FakeSock:
    def close(self):
        pass


class FakePorts:
    """가짜 connector(socket.create_connection 자리). open에 든 127.0.0.1 포트만 연결된다."""

    def __init__(self, open_=()):
        self.open = set(open_)
        self.calls = []

    def __call__(self, address, timeout=None):
        self.calls.append(address)
        if address[0] == "127.0.0.1" and address[1] in self.open:
            return FakeSock()
        raise ConnectionRefusedError()


class FakeTunnelProc:
    def __init__(self, pid, ports, port, code=None):
        self.pid, self.ports, self.port, self.code = pid, ports, port, code
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.ports.open.discard(self.port)
        self.code = -15


class FakeTunnelSpawner:
    """받은 argv를 적고 가짜 ssh 프로세스를 돌려준다. 기본은 -L의 포트를 연다. code를 주면 바로 끝나고, opens=False면 열지 않고 산다."""

    def __init__(self, ports, *, code=None, opens=True):
        self.ports, self.code, self.opens = ports, code, opens
        self.calls, self.procs = [], []

    def __call__(self, argv):
        self.calls.append(list(argv))
        port = int(argv[argv.index("-L") + 1].split(":")[0])
        if self.code is None and self.opens:
            self.ports.open.add(port)
        self.procs.append(FakeTunnelProc(5000 + len(self.procs), self.ports, port, self.code))
        return self.procs[-1]


class FakePs:
    def __init__(self, text=""):
        self.text = text

    def __call__(self):
        return self.text


class FakeKiller:
    """기록만 한다. ports와 port를 주면 그 포트를 닫는다(ssh가 끝난 것과 같다)."""

    def __init__(self, ports=None, port=None):
        self.ports, self.port, self.calls = ports, port, []

    def __call__(self, pid, sig):
        self.calls.append((pid, sig))
        if self.ports is not None:
            self.ports.open.discard(self.port)


def make(srv, tmp_path, *, cloud=None, rngd=None, jobs=None, env=None, clock=None, watch=None, env_file=None,
         ports=None, tunnel=None, ps=None, killer=None, sleep=None):
    ports = ports if ports is not None else FakePorts()                  # 기본은 모든 포트가 닫힘, ps 글은 비어 있음
    return srv.ServerActions(dict(ENV) if env is None else env, jobs or FakeJobs(), tmp_path / "manual" / "server_log.md",
                             opener=cloud or FakeCloud(), runner=rngd or FakeRngd(), watchdog_spawner=watch or FakeWatch(),
                             clock=clock or Clock(), sleep=sleep or (lambda s: None), models_cfg=MODELS_CFG,
                             env_file=env_file, tunnel_spawner=tunnel or FakeTunnelSpawner(ports), connector=ports,
                             ps=ps or FakePs(), killer=killer or FakeKiller())


def no_secret(*objs, extra=()):
    text = json.dumps(objs, ensure_ascii=False, default=str)
    for k in (*SECRETS, *extra):
        assert k not in text


def log_text(tmp_path) -> str:
    p = tmp_path / "manual" / "server_log.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def log_rows(tmp_path) -> list[str]:
    return [l for l in log_text(tmp_path).splitlines() if l.startswith("| 20")]


# ── 상태 ───────────────────────────────────────────────

def test_status_fields(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)], served={RNGD_URL: [GPTOSS]})
    st = make(srv, tmp_path, cloud=cloud, rngd=FakeRngd(up=[GPTOSS])).status()
    assert {"models", "pods", "volumes", "rngd", "running_jobs", "locked"} <= set(st)
    assert st["locked"] is False and st["running_jobs"] == []
    models = {m["tag"]: m for m in st["models"]}
    assert set(models) == {"qwen3_30b_a3b_rngd", "gpt_oss_20b_rngd", "qwen36_35b_runpod"}   # 실버용 태그는 보지 않는다
    assert models["gpt_oss_20b_rngd"]["match"] is True and models["gpt_oss_20b_rngd"]["where"] == "RNGD"
    assert models["qwen3_30b_a3b_rngd"]["match"] is False and models["qwen3_30b_a3b_rngd"]["model_served"] == GPTOSS
    assert models["qwen36_35b_runpod"]["reachable"] is False and models["qwen36_35b_runpod"]["where"] == "RunPod"
    p = st["pods"][0]
    assert (p["id"], p["minutes"], p["est_cost"], p["ours"]) == ("abc123", 83, 3.44, True)
    assert st["volumes"] == 0
    assert st["rngd"]["ok"] and st["rngd"]["models"] == [{"pid": 700, "model": GPTOSS, "elapsed_s": None}]
    assert [c["tag"] for c in st["rngd_choices"]] == ["qwen3_30b_a3b_rngd", "gpt_oss_20b_rngd"]
    assert st["rngd_choices"][0]["cards"] == 4 and st["rngd_choices"][1]["cards"] == 1
    no_secret(st)


def test_status_locked_when_run_is_running(srv, tmp_path):
    st = make(srv, tmp_path, jobs=FakeJobs([LOCK_RUN])).status()
    assert st["locked"] is True and st["running_jobs"] == [LOCK_RUN]
    assert "20261030_sections_가상_dev10_r2" in st["lock_reason"]


def test_compare_job_does_not_lock(srv, tmp_path):
    jobs = FakeJobs([{"mine": True, "id": "j1", "kind": "compare", "label": "비교", "pid": 5}])
    assert make(srv, tmp_path, jobs=jobs).status()["locked"] is False


def test_status_without_keys(srv, tmp_path):
    cloud = FakeCloud()
    st = make(srv, tmp_path, cloud=cloud, env={}).status()
    assert st["pods"] == [] and st["runpod_error"] == "RUNPOD_API_KEY 없음"
    assert st["rngd"]["ok"] is False and st["rngd"]["error"] == "RNGD_SSH 없음"
    assert not [r for r in cloud.requests if "runpod.io" in r["url"]]


@pytest.mark.parametrize("runpod_ok,rngd_ok", [(True, True), (True, False), (False, True), (False, False)])
@pytest.mark.parametrize("kind", [None, "run", "try", "compare"])
def test_status_can_by_management_connection_and_job(srv, tmp_path, runpod_ok, rngd_ok, kind):
    cloud = FakeCloud()  # 모델이 아직 없어도 관리 서버가 보이면 만들기·올리기는 가능하다.
    def opener(req, timeout=None):
        if not runpod_ok:
            raise urllib.error.URLError(ConnectionRefusedError())
        return cloud(req, timeout)
    runner = FakeRngd() if rngd_ok else lambda *a: (255, "", "Connection refused")
    jobs = FakeJobs([{**LOCK_RUN, "kind": kind}] if kind else [])
    result = make(srv, tmp_path, cloud=opener, rngd=runner, jobs=jobs).status()
    locked = kind in ("run", "try")
    assert result["can"] == {"pod_create": runpod_ok and not locked, "pod_delete": runpod_ok and not locked,
                             "rngd_up": rngd_ok and not locked, "rngd_down": rngd_ok and not locked,
                             "tunnel_open": True, "tunnel_close": False}   # 터널이 닫혀 있다(가짜 포트). 열기는 실행 중에도 된다
    assert set(result["why"]) == set(result["can"])
    for action, allowed in result["can"].items():
        assert bool(result["why"][action]) is not allowed
    no_secret(result)


def test_status_can_without_credentials(srv, tmp_path):
    result = make(srv, tmp_path, env={}).status()
    assert not any(result["can"].values())
    assert all(result["why"].values())
    assert result["friendly"]["raw"] == result["runpod_error"]
    assert "RNGD_SSH" in result["rngd"]["friendly"]["message"]
    assert result["ui_text"]["guide"]["advanced_off"]== "AI 켜기와 비용에서 모델을 준비하세요."


def test_status_friendly_runpod_certificate_and_rngd_masking(srv, tmp_path):
    import ssl
    def opener(*args, **kwargs):
        raise urllib.error.URLError(ssl.SSLCertVerificationError(FAKE_KEY))
    result = make(srv, tmp_path, cloud=opener,
                  rngd=lambda *a: (255, "", f"Connection refused {RNGD_KEY}")).status()
    assert "인증서를 확인하지 못했습니다" in result["friendly"]["message"]
    assert result["friendly"]["raw"] == result["runpod_error"]
    assert result["rngd"]["friendly"]["message"] == "모델 서버가 응답하지 않습니다."
    assert result["rngd"]["friendly"]["raw"] == result["rngd"]["error"]
    no_secret(result)


def test_status_shows_log_tail(srv, tmp_path):
    sa = make(srv, tmp_path)
    for i in range(12):
        srv.append_server_log(tmp_path / "manual" / "server_log.md", "pod_delete", target=f"pod{i}")
    tail = sa.status()["log_tail"]
    assert len(tail) == 10 and "pod11" in tail[-1] and not any("시각" in l for l in tail)


# ── Pod 지우기 ─────────────────────────────────────────

def test_propose_pod_delete_gives_token_and_summary(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)])
    res = make(srv, tmp_path, cloud=cloud).propose("pod_delete", {"pod_id": "abc123"})
    assert "code" not in res and len(res["token"]) >= 16
    assert "abc123" in res["summary"] and "83분" in res["summary"] and "$3.44" in res["summary"]
    assert "이 도구가 만든 것이 아닙니다" not in res["summary"]
    assert cloud.sent("DELETE") == []                                     # 요약만 하고 아직 지우지 않는다
    no_secret(res)


def test_propose_locked_is_409(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)])
    res = make(srv, tmp_path, cloud=cloud, jobs=FakeJobs([LOCK_RUN])).propose("pod_delete", {"pod_id": "abc123"})
    assert res["code"] == 409 and {"error", "running"} <= set(res) and "token" not in res
    assert res["running"] == [LOCK_RUN]


def test_execute_pod_delete_uses_token_once(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)])
    sa = make(srv, tmp_path, cloud=cloud)
    token = sa.propose("pod_delete", {"pod_id": "abc123"})["token"]
    res = sa.execute(token)
    assert res["ok"] is True and "code" not in res and res["result"]["gone"] is True
    assert [r["url"].rsplit("/", 1)[1] for r in cloud.sent("DELETE")] == ["abc123"]
    rows = log_rows(tmp_path)
    assert len(rows) == 1 and "pod_delete" in rows[0] and "abc123" in rows[0] and "83" in rows[0]
    assert res["log_line"] == rows[0]
    again = sa.execute(token)
    assert again["code"] == 400 and "error" in again
    assert len(cloud.sent("DELETE")) == 1 and len(log_rows(tmp_path)) == 1
    no_secret(res, again, log_text(tmp_path))


def test_execute_after_ten_minutes_is_410(srv, tmp_path):
    cloud, clock = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)]), Clock()
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    token = sa.propose("pod_delete", {"pod_id": "abc123"})["token"]
    clock.t += 11 * 60
    res = sa.execute(token)
    assert res["code"] == 410 and "error" in res
    assert cloud.sent("DELETE") == [] and log_rows(tmp_path) == []


def test_execute_wrong_token_is_400(srv, tmp_path):
    sa = make(srv, tmp_path)
    for bad in ("없는토큰", "", None, 123):
        assert sa.execute(bad)["code"] == 400


def test_execute_checks_lock_again(srv, tmp_path):
    cloud, jobs = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)]), FakeJobs()
    sa = make(srv, tmp_path, cloud=cloud, jobs=jobs)
    token = sa.propose("pod_delete", {"pod_id": "abc123"})["token"]
    jobs.now = [LOCK_RUN]                                                  # 확인을 누르기 전에 본 실행이 시작됨
    res = sa.execute(token)
    assert res["code"] == 409 and res["running"] == [LOCK_RUN] and cloud.sent("DELETE") == []


def test_pod_delete_not_ours_refused(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("zzz999", "other", 30)])
    sa = make(srv, tmp_path, cloud=cloud)
    res = sa.propose("pod_delete", {"pod_id": "zzz999"})
    assert res["code"] == 403 and "token" not in res                      # 사용자 결정 10/30 (ADR-028): 남의 Pod는 지우지 못한다
    assert "이 앱이 만든 서버가 아니라" in res["error"] and "할 일:" in res["error"]
    assert cloud.sent("DELETE") == [] and log_rows(tmp_path) == []
    p = sa.status()["pods"][0]
    assert (p["id"], p["ours"], p["owned"], p["deletable"]) == ("zzz999", False, False, False)


def test_status_marks_not_ours(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("zzz999", "other", 30), pod_of("abc123", "to21-b-qwen36", 5)])
    pods = {p["id"]: p for p in make(srv, tmp_path, cloud=cloud).status()["pods"]}
    assert pods["zzz999"]["ours"] is False and pods["abc123"]["ours"] is True


def test_propose_pod_delete_bad_input(srv, tmp_path):
    sa = make(srv, tmp_path, cloud=FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)]))
    assert sa.propose("pod_delete", {"pod_id": "없는pod"})["code"] == 400
    assert sa.propose("pod_delete", {"pod_id": "nope99"})["code"] == 404
    assert sa.propose("pod_delete", {})["code"] == 400
    assert sa.propose("다른_동작", {})["code"] == 400
    assert make(srv, tmp_path, env={}).propose("pod_delete", {"pod_id": "abc123"})["code"] == 400


# ── Pod 만들기 ─────────────────────────────────────────

def create(srv, pod, tmp_path, **kw):
    cloud, watch = kw.pop("cloud", FakeCloud()), FakeWatch()
    sa = make(srv, tmp_path, cloud=cloud, watch=watch, **kw)
    prop = sa.propose("pod_create", {})
    res = sa.execute(prop["token"])
    key = cloud.sent("POST")[0]["body"]["env"]["VLLM_API_KEY"]
    return sa, cloud, watch, prop, res, key


def test_execute_pod_create_sends_key_only_to_pod(srv, pod, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    assert "$2.49" in prop["summary"] and "4시간" in prop["summary"] and "RTX PRO 6000" in prop["summary"]
    body = cloud.sent("POST")[0]["body"]
    assert key == ENV["RUNPOD_VLLM_API_KEY"]                               # Pod 키는 .env 값이다 (앱을 다시 켜도 같은 키)
    assert body["name"].startswith("to21-b-")
    cmd = body["dockerStartCmd"][0]
    for part in (f"vllm serve {MODEL}", "--max-model-len 40960", "--max-num-seqs 64", "--gpu-memory-utilization 0.85",
                 "--limit-mm-per-prompt '{\"image\": 2}'", '--api-key "$VLLM_API_KEY"'):
        assert part in cmd, part
    assert key not in cmd
    assert res["ok"] is True and res["result"]["pod_id"] == "newpod1"
    assert res["result"]["url"] == pod.pod_url("newpod1")
    rows = log_rows(tmp_path)
    assert len(rows) == 1 and "pod_create" in rows[0] and "newpod1" in rows[0]
    no_secret(prop, res, log_text(tmp_path), extra=(key,))


def test_pod_create_starts_four_hour_watchdog(srv, pod, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    assert len(watch.calls) == 1
    argv = " ".join(watch.calls[0]["argv"])
    assert "sleep 14400" in argv and "scripts/pod.py delete newpod1" in argv
    assert watch.calls[0]["cwd"] == Path("/가상/backend")
    no_secret(watch.calls, extra=(key,))


def test_pod_create_session_env_for_jobs(srv, pod, tmp_path):
    sa = make(srv, tmp_path)
    assert sa.job_env() == {}
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    assert sa.job_env() == {"RUNPOD_VLLM_BASE_URL": pod.pod_url("newpod1"), "RUNPOD_VLLM_API_KEY": key}


def test_pod_create_shows_preparing_until_models_answer(srv, pod, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    st = sa.status()
    p = next(x for x in st["pods"] if x["id"] == "newpod1")
    assert p["state"] == "준비 중" and st["session"]["pod_id"] == "newpod1" and st["session"]["ready"] is False
    cloud.served[pod.pod_url("newpod1")] = [MODEL]
    st = sa.status()
    p = next(x for x in st["pods"] if x["id"] == "newpod1")
    assert p["state"] == "준비됨" and st["session"]["ready"] is True
    models = {m["tag"]: m for m in st["models"]}
    assert models["qwen36_35b_runpod"]["match"] is True
    asked = [r for r in cloud.requests if r["url"] == pod.pod_url("newpod1") + "/models"]
    assert asked and all(r["auth"] == f"Bearer {key}" for r in asked)      # 새 Pod는 앱이 만든 키로 묻는다
    no_secret(st, extra=(key,))


def test_delete_session_pod_stops_watchdog_and_forgets_key(srv, pod, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    token = sa.propose("pod_delete", {"pod_id": "newpod1"})["token"]
    assert sa.execute(token)["ok"] is True
    assert watch.procs[0].terminated is True
    assert sa.job_env() == {} and sa.status()["session"] is None


def test_propose_pod_create_without_runpod_key(srv, tmp_path):
    res = make(srv, tmp_path, env={k: v for k, v in ENV.items() if k != "RUNPOD_API_KEY"}).propose("pod_create", {})
    assert res["code"] == 400 and "RUNPOD_API_KEY" in res["error"]


def test_propose_pod_create_warns_about_live_pods(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 40)])
    res = make(srv, tmp_path, cloud=cloud).propose("pod_create", {})
    assert res["token"] and "abc123" in res["warning"]


# ── RNGD ───────────────────────────────────────────────

def test_rngd_down_logs_model_without_key(srv, tmp_path):
    rngd = FakeRngd(up=[GPTOSS])
    sa = make(srv, tmp_path, rngd=rngd)
    prop = sa.propose("rngd_down", {"model": GPTOSS})
    assert GPTOSS in prop["summary"] and prop["token"]
    assert not any(a[-1].startswith("kill") for a in rngd.calls)          # 요약만 하고 아직 내리지 않는다
    res = sa.execute(prop["token"])
    assert res["ok"] is True and res["result"]["killed"] == [700] and rngd.up == {}
    rows = log_rows(tmp_path)
    assert len(rows) == 1 and "rngd_down" in rows[0] and GPTOSS in rows[0]
    assert RNGD_REMOTE_KEY not in log_text(tmp_path)
    no_secret(prop, res, log_text(tmp_path))


def test_rngd_down_refuses_model_not_up(srv, tmp_path):
    sa = make(srv, tmp_path, rngd=FakeRngd(up=[GPTOSS]))
    assert sa.propose("rngd_down", {"model": QWEN30})["code"] == 404
    assert sa.propose("rngd_down", {"model": "x; rm -rf /"})["code"] == 400


def test_rngd_up_qwen30_uses_four_cards(srv, tmp_path):
    rngd = FakeRngd()
    sa = make(srv, tmp_path, rngd=rngd)
    prop = sa.propose("rngd_up", {"tag": "qwen3_30b_a3b_rngd"})
    assert QWEN30 in prop["summary"] and "4장" in prop["summary"] and not prop["warning"]
    res = sa.execute(prop["token"])
    serve = [a[-1] for a in rngd.calls if "setsid nohup" in a[-1]]
    assert len(serve) == 1 and f"serve {QWEN30} --devices npu:0,npu:1,npu:2,npu:3" in serve[0]
    assert res["ok"] is True and res["result"]["started"] is True
    rows = log_rows(tmp_path)
    assert len(rows) == 1 and "rngd_up" in rows[0] and QWEN30 in rows[0]
    no_secret(prop, res, log_text(tmp_path))


def test_rngd_up_warns_when_another_model_is_up(srv, tmp_path):
    prop = make(srv, tmp_path, rngd=FakeRngd(up=[GPTOSS])).propose("rngd_up", {"tag": "qwen3_30b_a3b_rngd"})
    assert prop["token"] and GPTOSS in prop["warning"]


def test_rngd_up_refuses_bad_tag_and_no_ssh(srv, tmp_path):
    sa = make(srv, tmp_path)
    assert sa.propose("rngd_up", {"tag": "claude"})["code"] == 400
    assert sa.propose("rngd_up", {"tag": "qwen36_35b_runpod"})["code"] == 400
    assert make(srv, tmp_path, rngd=FakeRngd(up=[GPTOSS])).propose("rngd_up", {"tag": "gpt_oss_20b_rngd"})["code"] == 400
    no_ssh = {k: v for k, v in ENV.items() if k != "RNGD_SSH"}
    assert make(srv, tmp_path, env=no_ssh).propose("rngd_up", {"tag": "gpt_oss_20b_rngd"})["code"] == 400
    assert make(srv, tmp_path, env=no_ssh).propose("rngd_down", {"model": GPTOSS})["code"] == 400


# ── 작업에 Pod 주소·키 넘기기 (JobManager extra_env) ──────

class EnvSpawner(FakeSpawner):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.envs = []

    def __call__(self, argv, log_path, cwd, extra_env=None):
        self.envs.append(extra_env)
        return super().__call__(argv, log_path, cwd)


def test_job_manager_passes_extra_env(bj, where):
    sp = EnvSpawner()
    m = manager(bj, where, sp)
    m.start_try(model=TAG, doc=X01, sections=[11], all_=False, pages_dir="../data/pages/version9", system_text=None,
                base_run=None, extra_env={"RUNPOD_VLLM_BASE_URL": "가상주소", "RUNPOD_VLLM_API_KEY": FAKE_KEY})
    m.start_run(model=TAG, docs=[X01], pages_dir="../data/pages/version9", run_name="환경", repeat=1,
                extra_env={"RUNPOD_VLLM_API_KEY": FAKE_KEY})
    assert sp.envs[0] == {"RUNPOD_VLLM_BASE_URL": "가상주소", "RUNPOD_VLLM_API_KEY": FAKE_KEY}
    assert sp.envs[1] == {"RUNPOD_VLLM_API_KEY": FAKE_KEY}
    for f in (where / "runs").rglob("*"):                                 # 상태 파일·로그에 키가 남지 않는다
        if f.is_file():
            assert FAKE_KEY not in f.read_text(encoding="utf-8", errors="ignore"), f
    assert FAKE_KEY not in json.dumps(m.list(), ensure_ascii=False)


# ── 앱 라우트 ──────────────────────────────────────────

def test_route_servers(srv, app, bj, where, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)])
    sa = make(srv, tmp_path, cloud=cloud)
    ctx = ctx_of(app, where, manager(bj, where), servers=sa)
    code, data = call(app, ctx, "GET", "/api/servers")
    assert code == 200 and data["pods"][0]["id"] == "abc123" and data["locked"] is False
    code, data = call(app, ctx, "POST", "/api/servers/execute", {"token": "틀린토큰"})
    assert code == 400 and data["error"]
    code, prop = call(app, ctx, "POST", "/api/servers/propose", {"action": "pod_delete", "params": {"pod_id": "abc123"}})
    assert code == 200 and prop["token"] and "code" not in prop
    code, res = call(app, ctx, "POST", "/api/servers/execute", {"token": prop["token"]})
    assert code == 200 and res["ok"] is True and len(cloud.sent("DELETE")) == 1
    assert call(app, ctx, "POST", "/api/servers/execute", {"token": prop["token"]})[0] == 400
    assert call(app, ctx, "POST", "/api/servers/propose", {"action": "pod_delete"})[0] == 400
    assert call(app, ctx, "POST", "/api/servers/propose", [1])[0] == 400
    no_secret(data, prop, res)


def test_route_servers_locked_and_expired(srv, app, bj, where, tmp_path):
    cloud, jobs, clock = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 83)]), FakeJobs(), Clock()
    ctx = ctx_of(app, where, manager(bj, where), servers=make(srv, tmp_path, cloud=cloud, jobs=jobs, clock=clock))
    body = {"action": "pod_delete", "params": {"pod_id": "abc123"}}
    token = call(app, ctx, "POST", "/api/servers/propose", body)[1]["token"]
    clock.t += 11 * 60
    assert call(app, ctx, "POST", "/api/servers/execute", {"token": token})[0] == 410
    jobs.now = [LOCK_RUN]
    code, data = call(app, ctx, "POST", "/api/servers/propose", body)
    assert code == 409 and data["running"] == [LOCK_RUN]


def test_route_servers_off(app, bj, where):
    ctx = ctx_of(app, where, manager(bj, where))
    assert call(app, ctx, "GET", "/api/servers")[0] == 503
    assert call(app, ctx, "POST", "/api/servers/execute", {"token": "x"})[0] == 503


def test_route_jobs_get_pod_env_after_create(srv, pod, app, bj, where, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    sp = EnvSpawner()
    ctx = ctx_of(app, where, manager(bj, where, sp), servers=sa)
    code, data = call(app, ctx, "POST", "/api/jobs/try", {"model": TAG, "doc": X01, "sections": [11],
                                                         "pages_dir": "../data/pages/version9"})
    assert code == 200
    assert sp.envs[0] == {"RUNPOD_VLLM_BASE_URL": pod.pod_url("newpod1"), "RUNPOD_VLLM_API_KEY": key}
    code, data = call(app, ctx, "GET", "/api/jobs")
    no_secret(data, extra=(key,))
    for f in (where / "runs").rglob("*"):
        if f.is_file():
            assert key not in f.read_text(encoding="utf-8", errors="ignore"), f


def test_route_jobs_without_session_send_no_env(srv, app, bj, where, tmp_path):
    sp = EnvSpawner()
    ctx = ctx_of(app, where, manager(bj, where, sp), servers=make(srv, tmp_path))
    call(app, ctx, "POST", "/api/jobs/try", {"model": TAG, "doc": X01, "sections": [11], "pages_dir": "../data/pages/version9"})
    assert sp.envs == [None]


def test_options_use_session_status(srv, pod, app, bj, where, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    cloud.served[pod.pod_url("newpod1")] = [MODEL]
    ctx = ctx_of(app, where, manager(bj, where), servers=sa, model_status=sa.model_status)
    models = {m["tag"]: m for m in call(app, ctx, "GET", "/api/options")[1]["models"]}
    assert models[TAG]["connected"] is True


# ── Pod 키는 .env, 다시 켜도 이어 쓰기, 켜진 시간·비용, 남의 Pod, 설정 다시 읽기 (step 5) ──

NEW_VLLM_KEY = "FAKEKEY-new-vllm-SHOULD-NEVER-APPEAR-8c7d"
POD_ENV_KEY = "FAKEKEY-pod-env-SHOULD-NEVER-APPEAR-3d2c"


def env_text(values: dict) -> str:
    return "".join(f"{k}={v}\n" for k, v in values.items())


def pod_gets(cloud) -> int:
    from pod import API
    return sum(r["method"] == "GET" and r["url"] == API + "/pods" for r in cloud.requests)


def test_pod_create_key_comes_from_env_and_never_leaks(srv, pod, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    assert key == ENV["RUNPOD_VLLM_API_KEY"]
    st = sa.status()
    assert st["session"]["pod_id"] == "newpod1" and st["session"]["adopted"] is False
    assert ENV["RUNPOD_VLLM_API_KEY"] not in json.dumps(sa._session, default=str)   # 세션에 키를 두지 않는다
    no_secret(prop, res, st, log_text(tmp_path), watch.calls)


@pytest.mark.parametrize("value", [None, ""])
def test_propose_pod_create_without_vllm_key_is_400(srv, tmp_path, value):
    env = {k: v for k, v in ENV.items() if k != "RUNPOD_VLLM_API_KEY"}
    if value is not None:
        env["RUNPOD_VLLM_API_KEY"] = value
    cloud = FakeCloud()
    res = make(srv, tmp_path, cloud=cloud, env=env).propose("pod_create", {})
    assert res["code"] == 400 and "token" not in res
    assert "RUNPOD_VLLM_API_KEY" in res["error"] and "할 일:" in res["error"] and "설정 다시 읽기" in res["error"]
    assert cloud.sent("POST") == []
    no_secret(res)


def test_execute_pod_create_rechecks_vllm_key(srv, tmp_path):
    env, cloud = dict(ENV), FakeCloud()
    sa = make(srv, tmp_path, cloud=cloud, env=env)
    token = sa.propose("pod_create", {})["token"]
    del env["RUNPOD_VLLM_API_KEY"]                                          # 요약을 본 뒤 설정에서 키가 빠짐
    res = sa.execute(token)
    assert res["code"] == 400 and res["ok"] is False and cloud.sent("POST") == [] and log_rows(tmp_path) == []


def test_restart_adopts_running_owned_pod(srv, pod, tmp_path):
    cloud = FakeCloud(pods=[pod_of("zzz999", "other", 10), pod_of("abc123", "to21-b-qwen36", 40)])
    sa = make(srv, tmp_path, cloud=cloud)                                   # 앱을 새로 켠 것과 같다(세션 없음)
    assert sa.job_env() == {"RUNPOD_VLLM_BASE_URL": pod.pod_url("abc123"),
                            "RUNPOD_VLLM_API_KEY": ENV["RUNPOD_VLLM_API_KEY"]}
    st = sa.status()
    assert st["session"]["pod_id"] == "abc123" and st["session"]["adopted"] is True
    assert st["session"]["others"] == []
    views = {p["id"]: p for p in st["pods"]}
    assert views["abc123"]["session"] is True and views["zzz999"]["session"] is False
    asked = [r for r in cloud.requests if r["url"] == pod.pod_url("abc123") + "/models"]
    assert asked and all(r["auth"] == f"Bearer {ENV['RUNPOD_VLLM_API_KEY']}" for r in asked)
    no_secret(st)


def test_restart_adopts_most_recent_owned_pod(srv, pod, tmp_path):
    stopped = {**pod_of("stop33", "to21-b-qwen36", 1), "desiredStatus": "EXITED"}
    cloud = FakeCloud(pods=[pod_of("old111", "to21-b-qwen36", 120), pod_of("new222", "to21-b-qwen36", 15),
                            pod_of("zzz999", "other", 5), stopped])
    sa = make(srv, tmp_path, cloud=cloud)
    assert sa.job_env()["RUNPOD_VLLM_BASE_URL"] == pod.pod_url("new222")
    session = sa.status()["session"]
    assert session["pod_id"] == "new222" and session["adopted"] is True and session["others"] == ["old111"]


def test_adoption_list_is_throttled(srv, pod, tmp_path):
    cloud, clock = FakeCloud(pods=[pod_of("zzz999", "other", 10)]), Clock()
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    assert sa.job_env() == {} and pod_gets(cloud) == 1
    clock.t += 29
    assert sa.job_env() == {} and sa.job_env() == {} and pod_gets(cloud) == 1   # 30초 안에는 목록을 다시 묻지 않는다
    cloud.pods.append(pod_of("abc123", "to21-b-qwen36", 0))
    clock.t += 2
    assert sa.job_env()["RUNPOD_VLLM_BASE_URL"] == pod.pod_url("abc123") and pod_gets(cloud) == 2
    sa.job_env()
    assert pod_gets(cloud) == 2                                             # 세션이 생기면 더 묻지 않는다


def test_adoption_needs_runpod_key_and_survives_errors(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 10)])
    sa = make(srv, tmp_path, cloud=cloud, env={k: v for k, v in ENV.items() if k != "RUNPOD_API_KEY"})
    assert sa.job_env() == {} and pod_gets(cloud) == 0

    def broken(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "x", {}, None)
    sa = make(srv, tmp_path, cloud=broken)
    assert sa.job_env() == {} and sa.status()["session"] is None


def test_job_env_follows_env_key(srv, pod, tmp_path):
    env = dict(ENV)
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path, env=env)
    env["RUNPOD_VLLM_API_KEY"] = NEW_VLLM_KEY                               # 설정 다시 읽기 뒤와 같다
    assert sa.job_env()["RUNPOD_VLLM_API_KEY"] == NEW_VLLM_KEY
    del env["RUNPOD_VLLM_API_KEY"]
    assert sa.job_env() == {}


def test_status_uptime_and_cost_from_rest_fields(srv, tmp_path):
    iso = {**pod_of("abc123", "to21-b-qwen36", 0), "lastStatusChange": None, "costPerHr": "2.49",
           "lastStartedAt": (NOW - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    js = {**pod_of("def456", "to21-b-qwen36", 0), "costPerHr": 2.49,
          "lastStatusChange": "Rented by User: Fri Oct 30 2026 07:00:00 GMT-0400 (Eastern Daylight Time)"}
    views = {p["id"]: p for p in make(srv, tmp_path, cloud=FakeCloud(pods=[iso, js])).status()["pods"]}
    for pid in ("abc123", "def456"):
        assert (views[pid]["uptime_s"], views[pid]["cost_est"], views[pid]["minutes"]) == (3600, 2.49, 60), pid


def test_status_uptime_from_server_log_when_rest_has_no_time(srv, tmp_path):
    log = tmp_path / "manual" / "server_log.md"
    log.parent.mkdir(parents=True)
    local = (NOW - timedelta(minutes=120)).astimezone().strftime("%Y-%m-%d %H:%M:%S")   # 기록은 로컬 시각이다
    older = (NOW - timedelta(minutes=500)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    log.write_text("| 시각 | 동작 | 대상 | 비고 |\n|---|---|---|---|\n"
                   f"| {older} | pod_delete | abc123 (to21-b-qwen36) | 가상 |\n"
                   f"| {local} | pod_create | abc123 (to21-b-qwen36) | 가상 |\n"
                   f"| {local} | pod_create | zzz999 (other) | 가상 |\n", encoding="utf-8")
    ours = {**pod_of("abc123", "to21-b-qwen36", 0), "lastStatusChange": None}
    other = {**pod_of("zzz999", "other", 0), "lastStatusChange": None}
    views = {p["id"]: p for p in make(srv, tmp_path, cloud=FakeCloud(pods=[ours, other])).status()["pods"]}
    assert views["abc123"]["uptime_s"] == 7200 and views["abc123"]["cost_est"] == 4.98
    assert views["abc123"]["minutes"] == 120 and views["abc123"]["est_cost"] == 4.98
    assert views["zzz999"]["uptime_s"] is None and views["zzz999"]["cost_est"] is None   # 남의 Pod는 기록으로 채우지 않는다


def test_status_hides_pod_env_from_rest(srv, tmp_path):
    cloud = FakeCloud(pods=[{**pod_of("abc123", "to21-b-qwen36", 10), "env": {"VLLM_API_KEY": POD_ENV_KEY}},
                            {**pod_of("zzz999", "other", 5), "env": {"VLLM_API_KEY": POD_ENV_KEY}}])
    sa = make(srv, tmp_path, cloud=cloud)
    st = sa.status()
    assert len(st["pods"]) == 2 and all("env" not in p for p in st["pods"])
    no_secret(st, sa.propose("pod_delete", {"pod_id": "abc123"}), extra=(POD_ENV_KEY,))


def test_pod_view_deletable_only_owned_and_unlocked(srv, tmp_path):
    pods = [pod_of("zzz999", "other", 30), pod_of("abc123", "to21-b-qwen36", 5)]
    views = {p["id"]: p for p in make(srv, tmp_path, cloud=FakeCloud(pods=pods)).status()["pods"]}
    assert (views["abc123"]["owned"], views["abc123"]["deletable"]) == (True, True)
    assert (views["zzz999"]["owned"], views["zzz999"]["deletable"]) == (False, False)
    locked = make(srv, tmp_path, cloud=FakeCloud(pods=pods), jobs=FakeJobs([LOCK_RUN])).status()["pods"]
    assert not any(p["deletable"] for p in locked) and [p["owned"] for p in locked] == [False, True]


def test_execute_pod_delete_rechecks_owner(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 30)])
    sa = make(srv, tmp_path, cloud=cloud)
    token = sa.propose("pod_delete", {"pod_id": "abc123"})["token"]
    cloud.pods = [pod_of("abc123", "someone-else", 30)]                    # 확인을 누르기 전에 목록이 바뀜
    res = sa.execute(token)
    assert res["code"] == 403 and res["ok"] is False and "할 일:" in res["error"]
    assert cloud.sent("DELETE") == [] and log_rows(tmp_path) == []
    token = sa.propose("pod_delete", {"pod_id": "abc123"})
    assert token["code"] == 403


def test_execute_pod_delete_refuses_pod_gone_from_list(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 30)])
    sa = make(srv, tmp_path, cloud=cloud)
    token = sa.propose("pod_delete", {"pod_id": "abc123"})["token"]
    cloud.pods = []                                                         # 주인을 확인할 수 없으면 지우지 않는다
    res = sa.execute(token)
    assert res["code"] == 404 and cloud.sent("DELETE") == []


def test_model_401_is_model_key_not_runpod_key(srv, tmp_path):
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
    st = srv.model_status("qwen36_35b_runpod", MODELS_CFG["models"]["qwen36_35b_runpod"], ENV, opener=opener)
    assert st["error"] == "HTTP 401"
    assert "모델 서버가 접속 키를 거절했습니다" in st["friendly"]["message"] and "RUNPOD_API_KEY" not in st["friendly"]["message"]
    no_secret(st)


def test_reload_env_applies_file_and_returns_names_only(srv, tmp_path):
    f = tmp_path / ".env"
    first = {"RUNPOD_API_KEY": FAKE_KEY, "RUNPOD_VLLM_API_KEY": OLD_VLLM_KEY, "RNGD_API_KEY": RNGD_KEY,
             "RNGD_SSH": "-p 2222 fakeuser@fakehost"}
    f.write_text(env_text(first), encoding="utf-8")
    env = {**first, "PATH": "/가상/bin"}                                     # 셸에서 온 이름은 .env에서 빠져도 지우지 않는다
    sa = make(srv, tmp_path, env=env, env_file=f)
    second = (f"RUNPOD_API_KEY={FAKE_KEY}\nRUNPOD_VLLM_API_KEY=\"{NEW_VLLM_KEY}\"\n"
              "RNGD_SSH=-p 2222 fakeuser@fakehost\n=값만\n")
    f.write_text(second, encoding="utf-8")
    res = sa.reload_env()
    assert res["ok"] is True
    assert env["RUNPOD_VLLM_API_KEY"] == NEW_VLLM_KEY and "RNGD_API_KEY" not in env and env["PATH"] == "/가상/bin"
    assert res["changed"] == ["RUNPOD_VLLM_API_KEY"] and res["removed"] == ["RNGD_API_KEY"]
    assert sorted(res["names"]) == ["RNGD_SSH", "RUNPOD_API_KEY", "RUNPOD_VLLM_API_KEY"]
    assert [p["line"] for p in res["problems"]] == [4] and res["problems"][0]["message"] and res["problems"][0]["fix"]
    assert f.read_text(encoding="utf-8") == second                          # 앱은 .env를 읽기만 한다
    no_secret(res, extra=(NEW_VLLM_KEY, "fakeuser@fakehost", "값만"))
    again = sa.reload_env()                                                 # 같은 파일을 다시 읽으면 바뀐 것이 없다
    assert again["changed"] == [] and again["removed"] == []


def test_reload_env_feeds_jobs_and_status(srv, pod, tmp_path):
    f = tmp_path / ".env"
    f.write_text(env_text(ENV), encoding="utf-8")
    env = dict(ENV)
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path, env=env, env_file=f)
    assert sa.status()["env_problems"] == []
    f.write_text(env_text({**ENV, "RUNPOD_VLLM_API_KEY": NEW_VLLM_KEY}) + "=값만\n", encoding="utf-8")
    sa.reload_env()
    assert sa.job_env()["RUNPOD_VLLM_API_KEY"] == NEW_VLLM_KEY
    st = sa.status()
    assert [p["line"] for p in st["env_problems"]] == [len(ENV) + 1]
    no_secret(st, extra=(NEW_VLLM_KEY, "값만"))


def test_reload_env_without_file(srv, tmp_path):
    sa = make(srv, tmp_path)
    res = sa.reload_env()
    assert res["ok"] is False and res["error"]
    assert sa.status()["env_problems"] == []
    missing = make(srv, tmp_path, env=dict(ENV), env_file=tmp_path / "없음.env")
    res = missing.reload_env()                                              # 파일이 없으면 이름이 없다(셸 값은 그대로)
    assert res["ok"] is True and res["names"] == [] and res["removed"] == []


def test_read_env_file_gives_values_and_bad_lines(srv, tmp_path):
    f = tmp_path / ".env"
    f.write_text("# 설명\nA=1\n=값만\nB=\"두 낱말\"\nC\n", encoding="utf-8")
    assert srv.read_env_file(f) == ({"A": "1", "B": "두 낱말"}, [3])
    assert srv.read_env_file(tmp_path / "없음") == ({}, [])


def test_route_reload_env(srv, app, bj, where, tmp_path):
    f = tmp_path / ".env"
    f.write_text(env_text({**ENV, "RUNPOD_VLLM_API_KEY": NEW_VLLM_KEY}), encoding="utf-8")
    env = dict(ENV)
    ctx = ctx_of(app, where, manager(bj, where), servers=make(srv, tmp_path, env=env, env_file=f))
    code, data = call(app, ctx, "POST", "/api/servers/reload_env")
    assert code == 200 and data["ok"] is True and data["changed"] == ["RUNPOD_VLLM_API_KEY"]
    assert env["RUNPOD_VLLM_API_KEY"] == NEW_VLLM_KEY
    assert call(app, ctx, "POST", "/api/servers/reload_env", {})[0] == 200
    no_secret(data, extra=(NEW_VLLM_KEY,))
    off = ctx_of(app, where, manager(bj, where))
    assert call(app, off, "POST", "/api/servers/reload_env")[0] == 503


# ── RNGD 터널 열기·닫기와 진단 (step 6) ─────────────────────

TUNNEL_PS = ("  4321  4321 ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 "
             "-L 18000:127.0.0.1:8000 -i /가상/.ssh/fake -p 22 user@host\n")
CLOSED = {"port": 18000, "open": False, "owned": False, "pid": None, "since": None}


def local_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def no_ssh_args(*objs):
    """명령 줄 인자(키 파일 경로·접속 대상)는 응답·기록에 나오지 않는다. 포트 번호만 보인다."""
    text = json.dumps(objs, ensure_ascii=False, default=str)
    for part in (".ssh/fake", "user@host", " -i ", "BatchMode", "ExitOnForwardFailure"):
        assert part not in text, part


def open_tunnel(srv, tmp_path, **kw):
    ports = kw.pop("ports", FakePorts())
    spawner = kw.pop("tunnel", FakeTunnelSpawner(ports))
    sa = make(srv, tmp_path, ports=ports, tunnel=spawner, **kw)
    prop = sa.propose("tunnel_open", {})
    return sa, ports, spawner, prop, sa.execute(prop["token"])


def test_tunnel_status_closed_without_tunnel(srv, tmp_path):
    assert make(srv, tmp_path).tunnel_status() == CLOSED
    no_port = make(srv, tmp_path, env={**ENV, "RNGD_BASE_URL": "http://10.0.0.5:8000/v1"}).tunnel_status()
    assert no_port == {**CLOSED, "port": None}


def test_tunnel_open_spawns_ssh_and_is_owned(srv, tmp_path):
    sa, ports, spawner, prop, res = open_tunnel(srv, tmp_path)
    assert "18000번" in prop["summary"] and "8000번" in prop["summary"] and "SSH 터널" in prop["summary"]
    assert res["ok"] is True and "code" not in res and 18000 in ports.open
    assert spawner.calls == [srv.tunnel_args(ENV)]
    st = sa.tunnel_status()
    assert st == {"port": 18000, "open": True, "owned": True, "pid": spawner.procs[0].pid, "since": local_iso(NOW.timestamp())}
    rows = log_rows(tmp_path)
    assert len(rows) == 1 and "tunnel_open" in rows[0] and "127.0.0.1:18000" in rows[0]
    assert res["log_line"] == rows[0]
    no_ssh_args(prop, res, st, log_text(tmp_path))
    no_secret(prop, res, st, log_text(tmp_path))


def test_tunnel_open_refusals(srv, tmp_path):
    spawner = FakeTunnelSpawner(FakePorts({18000}))
    already = make(srv, tmp_path, ports=spawner.ports, tunnel=spawner).propose("tunnel_open", {})
    assert already["code"] == 409 and "token" not in already and "18000" in already["error"]
    no_ssh = make(srv, tmp_path, env={k: v for k, v in ENV.items() if k != "RNGD_SSH"}).propose("tunnel_open", {})
    assert no_ssh["code"] == 400 and "RNGD_SSH" in no_ssh["error"]
    remote = make(srv, tmp_path, env={**ENV, "RNGD_BASE_URL": "http://10.0.0.5:8000/v1"}).propose("tunnel_open", {})
    assert remote["code"] == 400 and "RNGD_BASE_URL" in remote["error"] and "할 일:" in remote["error"]
    assert spawner.calls == [] and log_rows(tmp_path) == []
    no_secret(already, no_ssh, remote)


def test_tunnel_open_rechecks_port_before_spawning(srv, tmp_path):
    ports = FakePorts()
    spawner = FakeTunnelSpawner(ports)
    sa = make(srv, tmp_path, ports=ports, tunnel=spawner)
    token = sa.propose("tunnel_open", {})["token"]
    ports.open.add(18000)                                                   # 확인을 누르기 전에 다른 터미널이 열었다
    res = sa.execute(token)
    assert res["code"] == 409 and spawner.calls == [] and log_rows(tmp_path) == []


def test_tunnel_open_ssh_exits_early(srv, tmp_path):
    ports = FakePorts()
    sa, ports, spawner, prop, res = open_tunnel(srv, tmp_path, ports=ports, tunnel=FakeTunnelSpawner(ports, code=255))
    assert res["ok"] is False and "255" in res["error"] and "할 일:" in res["error"]
    assert 18000 not in ports.open and sa.tunnel_status() == CLOSED
    rows = log_rows(tmp_path)
    assert len(rows) == 1 and "tunnel_open" in rows[0] and "127.0.0.1:18000" in rows[0]
    no_ssh_args(res, log_text(tmp_path))
    no_secret(res, log_text(tmp_path))


def test_tunnel_open_gives_up_after_ten_seconds(srv, tmp_path):
    ports, waits = FakePorts(), []
    spawner = FakeTunnelSpawner(ports, opens=False)
    sa, ports, spawner, prop, res = open_tunnel(srv, tmp_path, ports=ports, tunnel=spawner, sleep=waits.append)
    assert res["ok"] is False and res["error"]
    assert spawner.procs[0].terminated is True                              # 남은 ssh를 끝낸다
    assert waits and set(waits) == {0.5} and sum(waits) <= 10
    assert sa.tunnel_status() == CLOSED


def test_tunnel_open_allowed_while_running(srv, tmp_path):
    sa, ports, spawner, prop, res = open_tunnel(srv, tmp_path, jobs=FakeJobs([LOCK_RUN]))
    assert "code" not in prop and prop["token"]                              # 여는 것은 돌고 있는 실행을 해치지 않는다
    assert res["ok"] is True and 18000 in ports.open
    st = sa.status()
    assert st["locked"] is True and st["can"]["tunnel_open"] is False and st["can"]["tunnel_close"] is False
    assert st["why"]["tunnel_open"] and "시험 중" in st["why"]["tunnel_close"]   # 이미 열림 / 실행 중이라 닫지 못함
    assert make(srv, tmp_path, jobs=FakeJobs([LOCK_RUN])).status()["can"]["tunnel_open"] is True


def test_tunnel_close_app_tunnel(srv, tmp_path):
    sa, ports, spawner, prop, res = open_tunnel(srv, tmp_path)
    assert sa.status()["can"]["tunnel_close"] is True
    prop = sa.propose("tunnel_close", {})
    assert prop["token"] and "18000번" in prop["summary"]
    assert spawner.procs[0].terminated is False                             # 요약만 하고 아직 닫지 않는다
    res = sa.execute(prop["token"])
    assert res["ok"] is True and spawner.procs[0].terminated is True and 18000 not in ports.open
    assert sa.tunnel_status() == CLOSED
    rows = log_rows(tmp_path)
    assert len(rows) == 2 and "tunnel_close" in rows[1] and "127.0.0.1:18000" in rows[1]
    no_ssh_args(prop, res, log_text(tmp_path))
    no_secret(prop, res, log_text(tmp_path))


def test_tunnel_close_adopts_ps_tunnel_after_restart(srv, tmp_path):
    ports = FakePorts({18000})
    killer = FakeKiller(ports, 18000)
    sa = make(srv, tmp_path, ports=ports, ps=FakePs("  9  9 bash\n" + TUNNEL_PS), killer=killer)   # 앱을 새로 켠 것과 같다
    assert sa.tunnel_status() == {"port": 18000, "open": True, "owned": True, "pid": 4321, "since": None}
    res = sa.execute(sa.propose("tunnel_close", {})["token"])
    assert killer.calls == [(4321, signal.SIGTERM)]
    assert res["ok"] is True and 18000 not in ports.open
    no_ssh_args(res, log_text(tmp_path))


@pytest.mark.parametrize("ps_text", [
    "",
    "  9  9 bash\n",
    TUNNEL_PS.replace("-L 18000:", "-L 19000:"),                           # 다른 포트
    TUNNEL_PS.replace(" -N ", " "),                                        # -N 없는 ssh(사람이 연 접속)
    TUNNEL_PS.replace(" ssh -N", " python3 -N"),                           # ssh가 아니다
])
def test_tunnel_close_refuses_tunnel_not_ours(srv, tmp_path, ps_text):
    killer = FakeKiller()
    sa = make(srv, tmp_path, ports=FakePorts({18000}), ps=FakePs(ps_text), killer=killer)
    assert sa.tunnel_status()["owned"] is False
    res = sa.propose("tunnel_close", {})
    assert res["code"] == 403 and "이 앱이 열지 않았습니다" in res["error"] and "할 일:" in res["error"]
    assert sa.status()["can"]["tunnel_close"] is False
    assert killer.calls == [] and log_rows(tmp_path) == []


def test_tunnel_close_rechecks_ps_before_kill(srv, tmp_path):
    ps, killer = FakePs(TUNNEL_PS), FakeKiller()
    sa = make(srv, tmp_path, ports=FakePorts({18000}), ps=ps, killer=killer)
    token = sa.propose("tunnel_close", {})["token"]
    ps.text = ""                                                            # 확인을 누르기 전에 그 ssh가 사라지고 다른 것이 포트를 씀
    res = sa.execute(token)
    assert res["code"] == 403 and killer.calls == [] and log_rows(tmp_path) == []


def test_tunnel_close_closed_is_404(srv, tmp_path):
    res = make(srv, tmp_path, ps=FakePs(TUNNEL_PS)).propose("tunnel_close", {})
    assert res["code"] == 404 and "token" not in res


def test_tunnel_close_locked_is_409(srv, tmp_path):
    jobs, killer = FakeJobs([LOCK_RUN]), FakeKiller()
    sa = make(srv, tmp_path, ports=FakePorts({18000}), ps=FakePs(TUNNEL_PS), killer=killer, jobs=jobs)
    res = sa.propose("tunnel_close", {})
    assert res["code"] == 409 and res["running"] == [LOCK_RUN]
    jobs.now = []
    token = sa.propose("tunnel_close", {})["token"]
    jobs.now = [LOCK_RUN]                                                   # 확인을 누르기 전에 본 실행이 시작됨
    assert sa.execute(token)["code"] == 409 and killer.calls == []


def rngd_failing(args, timeout):
    return 255, "", "ssh: connect to host 가상 port 22: Connection refused"


@pytest.mark.parametrize("case, up, ports, served, rngd_ok, diagnosis", [
    ("모델 없음+터널 열림", [], {18000}, {}, True, "no_model"),
    ("모델 없음+터널 닫힘", [], set(), {}, True, "no_model"),
    ("모델 있음+터널 닫힘", [QWEN30], set(), {}, True, "tunnel_closed"),
    ("터널 열림+기대 모델 응답", [QWEN30], {18000}, {RNGD_URL: [QWEN30]}, True, "ok"),
    ("터널 열림+모델 프로세스+연결 오류", [QWEN30], {18000}, {}, True, "loading"),
    ("ssh 실패+터널 열림+응답 없음", [], {18000}, {}, False, None),
])
def test_rngd_diagnosis(srv, tmp_path, case, up, ports, served, rngd_ok, diagnosis):
    rngd = FakeRngd(up=up, elapsed={QWEN30: 600}) if rngd_ok else rngd_failing
    st = make(srv, tmp_path, rngd=rngd, ports=FakePorts(ports), cloud=FakeCloud(served=served)).status()
    r = st["rngd"]
    assert r["diagnosis"] == diagnosis, case
    assert r["tunnel"] == {**CLOSED, "open": bool(ports)}
    if diagnosis == "loading":
        assert r["loading_since"] == local_iso(NOW.timestamp() - 600)
        assert "10분 지났습니다" in r["diagnosis_text"]["message"]
    elif diagnosis == "tunnel_closed":
        assert r["loading_since"] == local_iso(NOW.timestamp() - 600)    # 프로세스가 있으면 뜨기 시작한 시각을 준다
    else:
        assert r["loading_since"] is None
    if diagnosis is None:
        assert r["diagnosis_text"] is None
    else:
        assert set(r["diagnosis_text"]) == {"message", "fix"} and r["diagnosis_text"]["message"]
    no_secret(st)


def test_loading_since_uses_longest_running_process(srv, tmp_path):
    rngd = FakeRngd(up=[QWEN30, GPTOSS], elapsed={QWEN30: 300, GPTOSS: 1800})
    r = make(srv, tmp_path, rngd=rngd, ports=FakePorts({18000})).status()["rngd"]
    assert r["diagnosis"] == "loading" and r["loading_since"] == local_iso(NOW.timestamp() - 1800)
    assert "서버 기록" in r["diagnosis_text"]["fix"]                          # 25분이 넘었다


def test_loading_since_unknown_without_etimes(srv, tmp_path):
    r = make(srv, tmp_path, rngd=FakeRngd(up=[QWEN30]), ports=FakePorts({18000})).status()["rngd"]
    assert r["diagnosis"] == "loading" and r["loading_since"] is None
    assert r["models"] == [{"pid": 700, "model": QWEN30, "elapsed_s": None}]


def test_no_model_texts_do_not_blame_tunnel(srv, tmp_path):
    st = make(srv, tmp_path, rngd=FakeRngd(), ports=FakePorts()).status()
    assert st["rngd"]["diagnosis"] == "no_model"
    rngd_tags = [m for m in st["models"] if m["where"] == "RNGD"]
    assert len(rngd_tags) == 2
    for m in rngd_tags:
        assert "터널" not in m["friendly"]["message"] and "터널" not in m["friendly"]["fix"]
        assert m["friendly"]["message"] == st["rngd"]["diagnosis_text"]["message"]
        assert m["friendly"]["raw"]                                          # 원래 오류 종류는 남긴다
    runpod = next(m for m in st["models"] if m["where"] == "RunPod")
    assert runpod["friendly"]["message"] == "모델 서버가 응답하지 않습니다."            # RunPod 칸은 그대로
    no_secret(st)


def test_rngd_http_answer_is_not_loading(srv, tmp_path):
    cloud = FakeCloud()

    def opener(req, timeout=None):                                          # 서버가 떠서 키를 거절한다
        if req.full_url.startswith(RNGD_URL):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        return cloud(req, timeout)
    st = make(srv, tmp_path, rngd=FakeRngd(up=[QWEN30], elapsed={QWEN30: 60}), ports=FakePorts({18000}),
              cloud=opener).status()
    assert st["rngd"]["diagnosis"] is None
    qwen = next(m for m in st["models"] if m["tag"] == "qwen3_30b_a3b_rngd")
    assert qwen["friendly"]["message"] == "모델 서버가 접속 키를 거절했습니다."


def test_route_tunnel_open_close(srv, app, bj, where, tmp_path):
    ports = FakePorts()
    sa = make(srv, tmp_path, ports=ports, tunnel=FakeTunnelSpawner(ports))
    ctx = ctx_of(app, where, manager(bj, where), servers=sa)
    code, prop = call(app, ctx, "POST", "/api/servers/propose", {"action": "tunnel_open"})
    assert code == 200 and prop["token"]
    code, res = call(app, ctx, "POST", "/api/servers/execute", {"token": prop["token"]})
    assert code == 200 and res["ok"] is True
    code, data = call(app, ctx, "GET", "/api/servers")
    assert code == 200 and data["rngd"]["tunnel"]["open"] is True and data["rngd"]["tunnel"]["owned"] is True
    assert call(app, ctx, "POST", "/api/servers/propose", {"action": "tunnel_open"})[0] == 409
    code, prop = call(app, ctx, "POST", "/api/servers/propose", {"action": "tunnel_close"})
    assert code == 200 and call(app, ctx, "POST", "/api/servers/execute", {"token": prop["token"]})[0] == 200
    assert 18000 not in ports.open
    no_ssh_args(data)
    no_secret(data, prop, res)


# ── 사용 후 닫기: 지워진 Pod 잊기와 요청이 멈춘 Pod 자동 삭제 ─────────────────

class FakeText:
    def __init__(self, text):
        self._b = text.encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def metrics_text(*, running=0, waiting=0, prompt=0, generated=0):
    return (f'vllm:num_requests_running{{engine="0",model_name="m"}} {running}.0\n'
            f'vllm:num_requests_waiting{{engine="0",model_name="m"}} {waiting}.0\n'
            'vllm:num_requests_waiting_by_reason{engine="0",model_name="m",reason="capacity"} 9.0\n'
            f'vllm:prompt_tokens_total{{engine="0",model_name="m"}} {prompt}.0\n'
            f'vllm:generation_tokens_total{{engine="0",model_name="m"}} {generated}.0\n')


class MetricsCloud(FakeCloud):
    """FakeCloud에 Pod의 /metrics를 더한다. metrics에 없는 Pod는 아직 모델이 뜨지 않은 Pod다(404)."""

    def __init__(self, *a, metrics=None, **k):
        super().__init__(*a, **k)
        self.metrics = dict(metrics or {})

    def __call__(self, req, timeout=None):
        if req.full_url.endswith("/metrics"):
            pod_id = re.match(r"https://(\w+)-8000", req.full_url)[1]
            if pod_id not in self.metrics:
                raise urllib.error.HTTPError(req.full_url, 404, "not ready", None, None)
            return FakeText(self.metrics[pod_id])
        return super().__call__(req, timeout=timeout)


def ids(cloud):
    return [p["id"] for p in cloud.pods]


def test_status_forgets_session_when_pod_is_deleted_by_another_app(srv, pod, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], served={pod.pod_url("abc123"): [MODEL]})
    sa = make(srv, tmp_path, cloud=cloud)
    assert sa.status()["session"]["pod_id"] == "abc123"
    cloud.pods.clear()
    cloud.served.clear()
    st = sa.status()
    assert st["session"] is None and sa.job_env() == {}
    assert all(m["error"] != "HTTP 404" for m in st["models"])


def test_just_created_pod_missing_from_list_keeps_session_and_watchdog(srv, pod, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    cloud.pods.clear()
    assert sa.status()["session"]["pod_id"] == "newpod1" and watch.procs[0].terminated is False


def test_idle_guard_deletes_pod_after_twenty_minutes_without_requests(srv, pod, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()},
                         served={pod.pod_url("abc123"): [MODEL]})
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    assert sa.status()["session"]["pod_id"] == "abc123"
    assert sa.idle_tick() == []
    clock.t += srv.IDLE_SECONDS - 1
    assert sa.idle_tick() == [] and ids(cloud) == ["abc123"]
    clock.t += 1
    assert sa.idle_tick() == ["abc123"] and ids(cloud) == []
    assert sa.status()["session"] is None
    log = (tmp_path / "manual" / "server_log.md").read_text(encoding="utf-8")
    assert "pod_delete" in log and "요청 없이 20분" in log
    no_secret(log)


def test_automatic_close_is_reported_with_time_and_cost(srv, pod, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()},
                         served={pod.pod_url("abc123"): [MODEL]})
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    assert sa.status()["last_auto_close"] is None
    sa.idle_tick()
    clock.t += srv.IDLE_SECONDS
    assert sa.idle_tick() == ["abc123"]
    closed = sa.status()["last_auto_close"]
    assert closed["kind"] == "idle" and closed["limit_min"] == 20
    assert isinstance(closed["minutes"], int) and closed["cost"] is not None


def test_session_status_tells_idle_limit(srv, pod, tmp_path):
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()},
                         served={pod.pod_url("abc123"): [MODEL]})
    sa = make(srv, tmp_path, cloud=cloud, clock=Clock())
    assert sa.status()["session"]["idle_minutes"] == 20


def test_manual_delete_clears_automatic_close_note(srv, pod, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()},
                         served={pod.pod_url("abc123"): [MODEL]})
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    sa.status()
    sa.idle_tick()
    clock.t += srv.IDLE_SECONDS
    sa.idle_tick()
    cloud.pods.append(pod_of("def456", "to21-b-qwen36", 5))
    sa._do_pod_delete({"pod_id": "def456"})
    assert sa.status()["last_auto_close"] is None


def test_idle_guard_restarts_the_clock_when_tokens_or_requests_change(srv, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()})
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    sa.idle_tick()
    clock.t += srv.IDLE_SECONDS - 60
    cloud.metrics["abc123"] = metrics_text(prompt=10)
    assert sa.idle_tick() == []
    clock.t += srv.IDLE_SECONDS - 60
    cloud.metrics["abc123"] = metrics_text(prompt=10, running=1)
    assert sa.idle_tick() == []
    clock.t += srv.IDLE_SECONDS
    cloud.metrics["abc123"] = metrics_text(prompt=10, waiting=1)
    assert sa.idle_tick() == [] and ids(cloud) == ["abc123"]


def test_idle_guard_ignores_the_by_reason_waiting_line(srv, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()})
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    sa.idle_tick()
    clock.t += srv.IDLE_SECONDS
    assert sa.idle_tick() == ["abc123"]        # by_reason 줄의 9는 대기 요청이 아니다


def test_idle_guard_never_deletes_while_a_job_runs(srv, tmp_path):
    clock, jobs = Clock(), FakeJobs()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()})
    sa = make(srv, tmp_path, cloud=cloud, clock=clock, jobs=jobs)
    sa.idle_tick()
    jobs.now = [LOCK_RUN]
    clock.t += srv.IDLE_SECONDS * 3
    assert sa.idle_tick() == [] and ids(cloud) == ["abc123"]
    jobs.now = []
    clock.t += srv.IDLE_SECONDS - 1
    assert sa.idle_tick() == []                # 작업이 끝난 뒤부터 다시 잰다
    clock.t += 1
    assert sa.idle_tick() == ["abc123"]


def test_idle_guard_waits_longer_while_the_model_is_loading_then_gives_up(srv, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 0)])
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    sa.idle_tick()
    clock.t += srv.READY_LIMIT - 1
    assert sa.idle_tick() == [] and ids(cloud) == ["abc123"]
    clock.t += 1
    assert sa.idle_tick() == ["abc123"]
    assert "응답하지 않아" in (tmp_path / "manual" / "server_log.md").read_text(encoding="utf-8")


def test_idle_clock_starts_when_the_model_first_answers(srv, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 0)])
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    sa.idle_tick()
    clock.t += srv.READY_LIMIT - 60
    cloud.metrics["abc123"] = metrics_text()
    assert sa.idle_tick() == []
    clock.t += srv.IDLE_SECONDS - 1
    assert sa.idle_tick() == []
    clock.t += 1
    assert sa.idle_tick() == ["abc123"]


def test_idle_guard_never_touches_pods_of_others_or_stopped_pods(srv, tmp_path):
    clock = Clock()
    stopped = {**pod_of("old111", "to21-b-qwen36", 500), "desiredStatus": "EXITED"}
    cloud = MetricsCloud(pods=[pod_of("zzz999", "someone-else", 5), stopped])
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    sa.idle_tick()
    clock.t += srv.READY_LIMIT * 2
    assert sa.idle_tick() == [] and ids(cloud) == ["zzz999", "old111"]
    assert not cloud.sent("DELETE")


def test_idle_guard_survives_runpod_errors_and_missing_key(srv, tmp_path):
    def broken(req, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError())
    assert make(srv, tmp_path, cloud=broken).idle_tick() == []
    env = {k: v for k, v in ENV.items() if k != "RUNPOD_API_KEY"}
    assert make(srv, tmp_path, env=env).idle_tick() == []


def test_idle_guard_counts_down_in_the_pod_row(srv, pod, tmp_path):
    clock = Clock()
    cloud = MetricsCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)], metrics={"abc123": metrics_text()},
                         served={pod.pod_url("abc123"): [MODEL]})
    sa = make(srv, tmp_path, cloud=cloud, clock=clock)
    sa.status()
    sa.idle_tick()
    clock.t += 300
    row = next(p for p in sa.status()["pods"] if p["id"] == "abc123")
    assert row["auto_delete_min"] == srv.IDLE_SECONDS // 60 - 5


def test_app_start_turns_the_idle_guard_on():
    assert "servers.start_idle_guard()" in (SCRIPTS / "b_app.py").read_text(encoding="utf-8")


def test_pod_delete_summary_does_not_quote_the_company_server_wait(srv, pod, tmp_path):
    cloud = FakeCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)])
    summary = make(srv, tmp_path, cloud=cloud).propose("pod_delete", {"pod_id": "abc123"})["summary"]
    assert "15~25분" not in summary


def test_pod_start_command_deletes_itself_after_four_hours(srv, pod, tmp_path):
    sa, cloud, watch, prop, res, key = create(srv, pod, tmp_path)
    cmd = cloud.sent("POST")[0]["body"]["dockerStartCmd"][0]
    assert f'(sleep {srv.WATCHDOG_SECONDS}; runpodctl remove pod "$RUNPOD_POD_ID") & ' in cmd     # 11/2 실제 Pod로 확인
    assert "vllm serve " in cmd and "--api-key \"$VLLM_API_KEY\"" in cmd


def test_cost_text_quotes_the_real_auto_delete_limits(srv):
    bt = srv.bt
    for text in (bt.UI_TEXT["servers"]["compare"]["rented"]["cleanup"], bt.UI_TEXT["servers"]["confirm"]["create"]["cost"]):
        assert f"{srv.IDLE_SECONDS // 60}분" in text and f"{srv.WATCHDOG_SECONDS // 3600}시간" in text
    assert "예약을 확인" not in bt.UI_TEXT["servers"]["rented"]["scheduler"]


class DeadAddressCloud(FakeCloud):
    """모델 주소가 RunPod 프록시의 404를 돌려준다. 지워진 Pod의 주소가 .env에 남은 경우다."""

    def __call__(self, req, timeout=None):
        if req.full_url.endswith("/models") and req.full_url.split("/models")[0] not in self.served:
            raise urllib.error.HTTPError(req.full_url, 404, "not found", None, None)
        return super().__call__(req, timeout=timeout)


def test_dead_pod_address_left_in_env_reads_as_no_server_not_a_failure(srv, tmp_path):
    st = make(srv, tmp_path, cloud=DeadAddressCloud()).status()
    pod_row = next(m for m in st["models"] if m["where"] == "RunPod")
    assert pod_row["url_set"] is False and pod_row["error"] is None and pod_row["reachable"] is False
    assert not pod_row.get("friendly")


def test_session_pod_that_answers_404_is_still_reported(srv, pod, tmp_path):
    cloud = DeadAddressCloud(pods=[pod_of("abc123", "to21-b-qwen36", 5)])
    pod_row = next(m for m in make(srv, tmp_path, cloud=cloud).status()["models"] if m["where"] == "RunPod")
    assert pod_row["url_set"] is True and pod_row["error"] == "HTTP 404"       # 켜는 중인 우리 Pod는 숨기지 않는다


def test_company_server_404_is_not_hidden(srv, tmp_path):
    rows = make(srv, tmp_path, cloud=DeadAddressCloud()).status()["models"]
    assert all(m["url_set"] is True and m["error"] == "HTTP 404" for m in rows if m["where"] == "RNGD")
