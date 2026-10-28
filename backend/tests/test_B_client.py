"""ChatClient의 NuExtract 요청 방식 (역할 B, ADR-010).

모델 서버와 네트워크를 부르지 않는다. ChatClient의 client를 가짜 객체로 바꾼다.
응답 예는 직접 만든 가짜 값이다 (D-43).
"""
import json
from types import SimpleNamespace

import openai
import pytest

from msds.extract import nuextract as nx
from msds.extract.client import ChatClient, load_model_config
from msds.extract.section_specs import response_schema

SYSTEM = "시스템 안내문"
USER = [{"type": "text", "text": "[3항 원문]\np1:L9 가상물질 갑 | 1234-56-6 | 10 ~ 20"}]
NU_TAG = "nuextract2_8b_runpod"

GOOD = {
    "composition": {"type": "혼합물", "no_hazardous_component": "false",
                    "lines": {"type": "p1:L7", "no_hazardous_component": None}},
    "components": [{"name": "가상물질 갑", "name_en": None, "synonyms": [], "cas_no": "1234-56-6", "ke_no": None,
                    "content": {"raw": "10 ~ 20", "value": None, "approx": None, "lower_op": ">=", "lower": "10",
                                "upper_op": "<=", "upper": 20, "unit": "%"},
                    "trade_secret": "false", "line": "p1:L9"}],
    "extras": [],
}


def resp(content: str, finish: str = "stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15))


class FakeCompletions:
    """받은 인자를 모으고, 미리 정한 응답을 차례로 돌려준다. 예외 객체면 던진다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("RUNPOD_VLLM_BASE_URL", "http://test/v1")
    monkeypatch.setenv("RUNPOD_VLLM_API_KEY", "test")
    monkeypatch.setenv("RNGD_BASE_URL", "http://test/v1")
    monkeypatch.setenv("RNGD_API_KEY", "test")
    monkeypatch.setattr(ChatClient, "_working_mode", {})


def make_client(cfg: dict, responses):
    client = ChatClient(cfg)
    fake = FakeCompletions(responses)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return client, fake.calls


def nu_call(responses, schema=None, cfg=None):
    client, calls = make_client(cfg or load_model_config(NU_TAG), responses)
    res = client.call(SYSTEM, USER, schema or response_schema(3), "sec03")
    return res, calls


# ── 요청 본문 ──────────────────────────────────────────

def test_nuextract_sends_one_user_message():
    res, calls = nu_call([resp(json.dumps(GOOD, ensure_ascii=False))])
    assert len(calls) == 1
    messages = calls[0]["messages"]
    assert messages == [{"role": "user", "content": USER}]
    assert messages[0]["content"] is USER
    assert all(m["role"] != "system" for m in messages)


def test_nuextract_template_in_chat_template_kwargs():
    schema = response_schema(3)
    _, calls = nu_call([resp(json.dumps(GOOD, ensure_ascii=False))], schema)
    kw = calls[0]
    tmpl = kw["extra_body"]["chat_template_kwargs"]["template"]
    assert isinstance(tmpl, str)
    assert json.loads(tmpl) == nx.template(schema)
    assert tmpl == json.dumps(nx.template(schema), ensure_ascii=False, indent=4)
    assert "response_format" not in kw
    assert "structured_outputs" not in kw["extra_body"]
    assert kw["temperature"] == 0
    assert kw["max_tokens"] == 8192
    assert kw["model"] == "numind/NuExtract-2.0-8B"


def test_nuextract_merges_tag_extra_body():
    base = load_model_config(NU_TAG)
    tag_extra = {"chat_template_kwargs": {"enable_thinking": False}, "top_k": 1}
    cfg = dict(base, params={"temperature": 0, "extra_body": tag_extra})
    _, calls = nu_call([resp(json.dumps(GOOD, ensure_ascii=False))], cfg=cfg)
    eb = calls[0]["extra_body"]
    assert eb["top_k"] == 1
    assert eb["chat_template_kwargs"]["enable_thinking"] is False
    assert isinstance(eb["chat_template_kwargs"]["template"], str)
    # 태그 설정의 extra_body는 그대로 남는다
    assert tag_extra == {"chat_template_kwargs": {"enable_thinking": False}, "top_k": 1}


# ── 응답 처리 ──────────────────────────────────────────

def test_nuextract_coerces_response():
    res, calls = nu_call([resp(json.dumps(GOOD, ensure_ascii=False))])
    assert res.ok and res.errors == []
    assert res.parsed["composition"]["no_hazardous_component"] is False
    assert res.parsed["components"][0]["content"]["lower"] == 10
    assert res.parsed["components"][0]["trade_secret"] is False
    assert res.mode == "nuextract_template"
    assert res.attempts == 1
    assert [(r["mode"], r["finish_reason"]) for r in res.requests] == [("nuextract_template", "stop")]
    assert res.requests[0]["usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_nuextract_not_json_no_retry():
    res, calls = nu_call([resp("성분표를 찾지 못했습니다")])
    assert not res.ok
    assert len(calls) == 1 and len(res.requests) == 1 and res.attempts == 1
    assert any("JSON으로 읽을 수 없음" in e for e in res.errors)


def test_nuextract_length_no_retry():
    res, calls = nu_call([resp('{"composition": {"type": ', "length")])
    assert not res.ok
    assert res.finish_reason == "length"
    assert len(calls) == 1 and len(res.requests) == 1
    assert any("출력 길이 한도" in e for e in res.errors)


def test_nuextract_validation_problem_no_retry():
    """형을 맞춰도 남는 검증 문제(null을 받지 않는 칸이 빔)는 다시 보내지 않고 실패로 둔다."""
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    res, calls = nu_call([resp('{"a": null}')], schema)
    assert not res.ok
    assert len(calls) == 1 and len(res.requests) == 1
    assert res.parsed == {"a": None}
    assert any("검증 실패" in e for e in res.errors)


class FakeBadRequest(openai.APIStatusError):
    """서버가 요청을 400으로 거부한 경우. 응답 객체 없이 상태 코드만 둔다."""

    def __init__(self, message: str):
        Exception.__init__(self, message)
        self.status_code = 400


def test_nuextract_rejected_request():
    res, calls = nu_call([FakeBadRequest("unknown chat_template_kwargs")])
    assert not res.ok
    assert len(calls) == 1
    assert any("거부됨" in e for e in res.errors)


# ── 회귀: request_style이 없는 태그 ─────────────────────

def test_other_tag_keeps_system_and_json_schema():
    schema = response_schema(3)
    client, calls = make_client(load_model_config("qwen3_30b_a3b_rngd"),
                                [resp(json.dumps(nx.coerce({}, schema)))])
    res = client.call(SYSTEM, USER, schema, "sec03")
    assert res.ok
    kw = calls[0]
    assert kw["messages"][0] == {"role": "system", "content": SYSTEM}
    assert kw["messages"][1] == {"role": "user", "content": USER}
    assert kw["response_format"]["type"] == "json_schema"
    assert "extra_body" not in kw
