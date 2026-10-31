"""scripts/b_app_servers.py의 ServerActions 시험 (작업 화면 탭 ⑤ 서버, ADR-025).

네트워크·ssh·subprocess를 부르지 않는다. RunPod REST와 모델 서버 /v1/models는 가짜 opener, RNGD ssh는 가짜 runner,
4시간 감시 프로세스는 가짜 watchdog_spawner, 시각은 가짜 clock으로 바꾼다.
키(RunPod 키, RNGD 키, 앱이 만든 vLLM 키)는 어떤 응답·로그에도 나오면 안 된다 (CLAUDE.md CRITICAL).
"""
import importlib
import json
import re
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

    def __init__(self, up=()):
        self.up = {m: 700 + i for i, m in enumerate(up)}
        self.calls = []

    def __call__(self, args, timeout):
        self.calls.append(list(args))
        cmd = args[-1]
        if cmd.startswith("furiosa-smi ps"):
            rows = [f"  {pid} furiosa-llm /usr/bin/python3 /usr/local/bin/furiosa-llm serve {m} --devices npu:0 "
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


def make(srv, tmp_path, *, cloud=None, rngd=None, jobs=None, env=None, clock=None, watch=None):
    return srv.ServerActions(dict(ENV) if env is None else env, jobs or FakeJobs(), tmp_path / "manual" / "server_log.md",
                             opener=cloud or FakeCloud(), runner=rngd or FakeRngd(), watchdog_spawner=watch or FakeWatch(),
                             clock=clock or Clock(), sleep=lambda s: None, models_cfg=MODELS_CFG)


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
    assert st["rngd"]["ok"] and st["rngd"]["models"] == [{"pid": 700, "model": GPTOSS}]
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


def test_pod_delete_not_ours_warns_but_allows(srv, tmp_path):
    cloud = FakeCloud(pods=[pod_of("zzz999", "other", 30)])
    sa = make(srv, tmp_path, cloud=cloud)
    res = sa.propose("pod_delete", {"pod_id": "zzz999"})
    assert "이 도구가 만든 것이 아닙니다" in res["summary"] and res["warning"]
    assert sa.execute(res["token"])["ok"] is True                          # 막지는 않는다
    assert sa.status()["pods"] == []


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
    assert len(key) >= 32 and key not in SECRETS
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
