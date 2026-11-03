"""scripts/model_check.py 시험. 팀원이 SSH 없이 주소와 키로 공유 모델 서버를 확인한다. 네트워크는 가짜로 끼운다."""
import importlib
import io
import urllib.error

import pytest

from test_B_compare_models import SCRIPTS

KEY = "team-key-SHOULD-NEVER-APPEAR-9z"
MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"
CFG = {"tag": "qwen36_35b_runpod_48g", "model": MODEL, "server": {"max_model_len": 49152}}


@pytest.fixture
def mc(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("model_check")


def fake_request(models=None, error=None, chat_error=None):
    calls = []

    def request(url, key, body=None, timeout=15):
        calls.append((url, body))
        if error is not None:
            raise error
        if url.endswith("/models"):
            return {"data": models if models is not None else [{"id": MODEL, "max_model_len": 49152}]}
        if chat_error is not None:
            raise chat_error
        return {"choices": [{"message": {"content": "1"}}], "usage": {"completion_tokens": 1}}
    return request, calls


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b""))


def test_ok_reports_model_and_context(mc):
    request, calls = fake_request()
    res = mc.check("https://p-8000.proxy.runpod.net/v1", KEY, CFG, request=request)
    assert res.ok and res.model == MODEL and res.max_model_len == 49152
    assert calls[0][0] == "https://p-8000.proxy.runpod.net/v1/models"
    assert not res.warnings


def test_wrong_key_says_ask_admin(mc):
    request, _ = fake_request(error=http_error(401))
    res = mc.check("https://p/v1", KEY, CFG, request=request)
    assert not res.ok and "키" in res.problem and "관리자" in res.fix


def test_unreachable_says_pod_may_be_off_or_replaced(mc):
    request, _ = fake_request(error=urllib.error.URLError("Name or service not known"))
    res = mc.check("https://old-pod-8000.proxy.runpod.net/v1", KEY, CFG, request=request)
    assert not res.ok and "주소" in res.fix and "RUNPOD_VLLM_BASE_URL" in res.fix


def test_proxy_without_server_is_unreachable(mc):
    # 프록시는 Pod가 꺼졌거나 8000이 공개되지 않았으면 404·502를 준다
    request, _ = fake_request(error=http_error(502))
    res = mc.check("https://p/v1", KEY, CFG, request=request)
    assert not res.ok and "RUNPOD_VLLM_BASE_URL" in res.fix


def test_other_model_is_a_problem(mc):
    request, _ = fake_request(models=[{"id": "Qwen/Other", "max_model_len": 40960}])
    res = mc.check("https://p/v1", KEY, CFG, request=request)
    assert not res.ok and "Qwen/Other" in res.problem


def test_context_different_from_tag_is_warning(mc):
    # 서버가 다른 설정(예: A100용 40960)으로 떠 있으면 돌기는 하지만 시험 조건이 다르다
    request, _ = fake_request(models=[{"id": MODEL, "max_model_len": 40960}])
    res = mc.check("https://p/v1", KEY, CFG, request=request)
    assert res.ok and any("40960" in w and "49152" in w for w in res.warnings)


def test_generation_failure_is_reported(mc):
    request, _ = fake_request(chat_error=http_error(500))
    res = mc.check("https://p/v1", KEY, CFG, request=request)
    assert not res.ok and "생성" in res.problem


def test_main_never_prints_key(mc, monkeypatch, capsys):
    request, _ = fake_request(error=http_error(401))
    monkeypatch.setattr(mc, "_request", request)
    monkeypatch.setattr(mc, "load_model_config", lambda tag: {**CFG, "base_url_env": "B", "api_key_env": "K"})
    monkeypatch.setenv("B", "https://p/v1")
    monkeypatch.setenv("K", KEY)
    assert mc.main(["--tag", "qwen36_35b_runpod_48g"]) == 1
    out = "".join(capsys.readouterr())
    assert KEY not in out and "https://p/v1" in out


def test_main_explains_missing_env(mc, monkeypatch, capsys):
    monkeypatch.setattr(mc, "load_model_config", lambda tag: {**CFG, "base_url_env": "B", "api_key_env": "K"})
    monkeypatch.delenv("B", raising=False)
    monkeypatch.setenv("K", KEY)
    assert mc.main(["--tag", "x"]) == 1
    assert "B" in capsys.readouterr().err
