"""scripts/pod.py 시험 (RunPod REST). 네트워크를 부르지 않고 opener를 가짜로 끼운다. 키는 어디에도 나오면 안 된다 (CLAUDE.md CRITICAL)."""
import importlib
import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from test_B_compare_models import SCRIPTS

FAKE_KEY = "sk-test-SHOULD-NEVER-APPEAR-9f8e7d"
VLLM_KEY = "vllm-test-SHOULD-NEVER-APPEAR-1a2b3c"
ENV = {"RUNPOD_API_KEY": FAKE_KEY}


@pytest.fixture
def pod(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setenv("RUNPOD_API_KEY", FAKE_KEY)
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


class FakeOpener:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.requests = payload, error, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        if self.error:
            raise self.error
        return FakeResp(self.payload)


def no_key(*objs):
    assert FAKE_KEY not in json.dumps(objs, ensure_ascii=False, default=str)
    assert VLLM_KEY not in json.dumps(objs, ensure_ascii=False, default=str)


def test_api_key_missing_exits(pod):
    with pytest.raises(SystemExit, match="RUNPOD_API_KEY 없음"):
        pod.api_key({})


def test_request_sends_user_agent_and_authorization(pod):
    op = FakeOpener([])
    pod.request("GET", "/pods", opener=op)
    req = op.requests[0]
    assert req.get_header("User-agent") == "to21-b-pod/1.0"
    assert req.get_header("Authorization").startswith("Bearer ")
    assert req.full_url == pod.API + "/pods"


def test_http_error_becomes_runtime_error_without_key(pod):
    err = urllib.error.HTTPError(pod.API + "/pods", 403, "Forbidden", {}, io.BytesIO(b"x" * 500))
    with pytest.raises(RuntimeError) as e:
        pod.request("GET", "/pods", opener=FakeOpener(error=err))
    msg = str(e.value)
    assert "403" in msg and len(msg) < 300
    no_key(msg)


def test_create_pod_body_and_return(pod):
    op = FakeOpener({"id": "abc123"})
    pid = pod.create_pod("vllm serve x", VLLM_KEY, opener=op)
    assert pid == "abc123"
    body = json.loads(op.requests[0].data)
    assert body["env"] == {"VLLM_API_KEY": VLLM_KEY}
    assert body["cloudType"] == "SECURE" and body["gpuCount"] == 1 and body["volumeInGb"] == 0
    assert body["dockerEntrypoint"] == ["bash", "-c"] and body["dockerStartCmd"] == ["vllm serve x"]
    assert body["ports"] == ["8000/http"]


def test_list_pods_keeps_only_summary_fields(pod):
    op = FakeOpener([{"id": "a", "name": "n", "desiredStatus": "RUNNING", "costPerHr": 1.5, "env": {"VLLM_API_KEY": VLLM_KEY},
                      "imageName": "i", "gpuCount": 1, "lastStatusChange": "t"}])
    out = pod.list_pods(opener=op)
    assert set(out[0]) == {"id", "name", "desiredStatus", "costPerHr", "imageName", "gpuCount", "lastStatusChange",
                           "lastStartedAt"}
    no_key(out)


def test_volumes_and_delete_and_url(pod):
    assert pod.list_volumes(opener=FakeOpener([{"id": "v", "name": "n", "size": 5, "x": 1}])) == [{"id": "v", "name": "n", "size": 5}]
    op = FakeOpener(None)
    assert pod.delete_pod("abc", opener=op) is None
    assert op.requests[0].get_method() == "DELETE"
    assert pod.pod_url("abc") == "https://abc-8000.proxy.runpod.net/v1"


def test_brief_est_cost(pod):
    now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    started = (now - timedelta(minutes=90)).isoformat()
    b = pod.brief({"id": "a", "name": "n", "desiredStatus": "RUNNING", "costPerHr": 1.5, "lastStatusChange": started}, now=now)
    assert b["minutes"] == 90 and b["status"] == "RUNNING" and b["cost_per_hr"] == 1.5
    assert b["est_cost"] == round(1.5 * b["minutes"] / 60, 2) == 2.25


# RunPod REST의 Pod 시각은 lastStartedAt(ISO)과 lastStatusChange(JS 날짜 글)로 온다. 실제 API로 다시 확인하지 못해 두 모양을 모두 받는다
STARTED_NOW = datetime(2024, 7, 12, 20, 14, 40, 144000, tzinfo=timezone.utc)


def test_parse_time_iso_and_js_date(pod):
    assert pod._parse_time("2024-07-12T19:14:40.144Z") == datetime(2024, 7, 12, 19, 14, 40, 144000, tzinfo=timezone.utc)
    js = pod._parse_time("Rented by User: Fri Jul 12 2024 15:14:40 GMT-0400 (Eastern Daylight Time)")
    assert js == datetime(2024, 7, 12, 19, 14, 40, tzinfo=timezone.utc)
    assert pod._parse_time("Fri Jul 12 2024 15:14:40 GMT+0900") == datetime(2024, 7, 12, 6, 14, 40, tzinfo=timezone.utc)
    for bad in (None, "", "t", "Rented by User: 모름"):
        assert pod._parse_time(bad) is None


def test_brief_prefers_last_started_at(pod):
    b = pod.brief({"id": "a", "costPerHr": 0.74, "lastStartedAt": "2024-07-12T19:14:40.144Z",
                   "lastStatusChange": "Rented by User: Fri Jul 12 2024 10:00:00 GMT-0400 (Eastern Daylight Time)"},
                  now=STARTED_NOW)
    assert (b["uptime_s"], b["minutes"], b["est_cost"], b["cost_est"]) == (3600, 60, 0.74, 0.74)
    assert b["started"] == "2024-07-12T19:14:40.144Z"


def test_brief_js_date_and_cost_text(pod):
    b = pod.brief({"id": "a", "costPerHr": "2.49",
                   "lastStatusChange": "Rented by User: Fri Jul 12 2024 15:14:40 GMT-0400 (Eastern Daylight Time)"},
                  now=STARTED_NOW)
    assert b["cost_per_hr"] == 2.49 and b["uptime_s"] == 3600 and b["cost_est"] == b["est_cost"] == 2.49


def test_brief_unknown_cost_or_time(pod):
    b = pod.brief({"id": "a", "costPerHr": "모름", "lastStartedAt": "2024-07-12T19:14:40.144Z"}, now=STARTED_NOW)
    assert b["cost_per_hr"] is None and b["uptime_s"] == 3600 and b["cost_est"] is None and b["est_cost"] is None
    b = pod.brief({"id": "a", "costPerHr": 2.49, "lastStartedAt": "엉망", "lastStatusChange": None}, now=STARTED_NOW)
    assert b["uptime_s"] is None and b["minutes"] is None and b["cost_est"] is None


def test_main_list_stdout_has_no_key(pod, capsys, monkeypatch):
    monkeypatch.setattr(pod, "request", lambda *a, **k: [{"id": "a", "name": "n"}])
    pod.main(["list"])
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1
    no_key(out)


def test_main_create_prints_only_id(pod, capsys, monkeypatch, tmp_path):
    (tmp_path / "cmd.txt").write_text("vllm serve x", encoding="utf-8")
    (tmp_path / "key.txt").write_text(VLLM_KEY + "\n", encoding="utf-8")
    seen = {}

    def fake_create(start_cmd, vllm_key, **kw):
        seen["key"] = vllm_key
        return "newid"

    monkeypatch.setattr(pod, "create_pod", fake_create)
    pod.main(["create", "--start-cmd-file", str(tmp_path / "cmd.txt"), "--vllm-key-file", str(tmp_path / "key.txt")])
    out = capsys.readouterr().out
    assert out.strip() == "newid" and seen["key"] == VLLM_KEY
    no_key(out)


def test_main_delete_prints_deleted(pod, capsys, monkeypatch):
    monkeypatch.setattr(pod, "request", lambda *a, **k: None)
    pod.main(["delete", "abc"])
    assert capsys.readouterr().out.strip() == "deleted abc"


def test_env_example_has_new_lines():
    from pathlib import Path
    lines = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "RUNPOD_API_KEY=" in lines and "RNGD_SSH=" in lines
