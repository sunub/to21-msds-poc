"""출력 한도에 걸린 묶음만 공백을 막아 한 번 더 보내기 (역할 B, ADR-017).

모델 서버와 네트워크를 부르지 않는다. ChatClient의 client를 가짜 객체로 바꾼다.
"""
from types import SimpleNamespace

import pytest

from msds.common.schema import to_strict
from msds.extract.client import ChatClient, load_model_config

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
SYSTEM = "시스템 안내문"
USER = [{"type": "text", "text": "문서"}]


def resp(content: str, finish: str = "stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15))


def ok():
    return resp('{"a": "x"}')


def cut():
    return resp('{"a": ', "length")


class FakeCompletions:
    """받은 인자를 모으고, 미리 정한 응답을 차례로 돌려준다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://test/v1")
    monkeypatch.setenv("VLLM_API_KEY", "test")
    monkeypatch.setattr(ChatClient, "_working_mode", {})


def compact_cfg() -> dict:
    """RNGD 태그와 같은 모양의 설정. 압축 재시도를 쓰는 태그는 재계획의 새 모델 태그와 함께 더한다."""
    return dict(load_model_config("qwen38"), token_param="max_completion_tokens",
                structured=["json_schema", "json_schema_compact", "none"])


def make_client(cfg: dict, responses):
    client = ChatClient(cfg)
    fake = FakeCompletions(responses)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return client, fake.calls


def test_compact_request_body():
    client, calls = make_client(compact_cfg(), [ok()])
    strict = to_strict(SCHEMA)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]
    client._request(messages, "json_schema_compact", "msds_b1", strict, 100)
    kw = calls[0]
    assert "response_format" not in kw
    assert kw["extra_body"]["structured_outputs"] == {"json": strict, "disable_any_whitespace": True}
    assert kw["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert kw["max_completion_tokens"] == 100
    # 태그 설정의 extra_body는 그대로 남는다
    assert client.cfg["params"]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_length_retries_with_compact():
    client, calls = make_client(compact_cfg(), [cut(), ok()])
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    assert res.ok
    assert res.mode == "json_schema_compact"
    assert res.attempts == 2
    assert len(calls) == 2
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert "response_format" not in calls[1]
    assert calls[1]["extra_body"]["structured_outputs"]["disable_any_whitespace"] is True
    for kw in calls:
        assert kw["messages"][0]["content"] == SYSTEM


def test_compact_not_remembered():
    client, calls = make_client(compact_cfg(), [cut(), ok(), ok()])
    client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b2")
    assert res.ok
    assert len(calls) == 3
    assert calls[2]["response_format"]["type"] == "json_schema"


def test_no_compact_without_config():
    cfg = dict(compact_cfg(), structured=["json_schema", "none"])
    client, calls = make_client(cfg, [cut()])
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    assert len(calls) == 1
    assert not res.ok
    assert res.finish_reason == "length"
    assert any("출력 길이 한도" in e for e in res.errors)


def test_requests_keep_length_hit_before_compact():
    """성공해도 출력 한도에 걸린 앞 요청이 요청 기록에 남는다. 거의 빈 응답도 지금은 성공으로 본다."""
    runaway = '{"a": ' + "\n" * 100
    client, _ = make_client(compact_cfg(), [resp(runaway, "length"), resp('{"a": ""}')])
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    assert res.ok and res.errors == []
    assert [(r["mode"], r["finish_reason"]) for r in res.requests] == [
        ("json_schema", "length"), ("json_schema_compact", "stop")]
    first = res.requests[0]
    assert first["usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert (first["chars"], first["whitespace"]) == (106, 101)
    assert first["head"] == runaway and first["tail"] == ""
    assert first["seconds"] >= 0


def test_request_record_keeps_head_and_tail():
    text = '{"a": "' + "가" * 1200 + '"}'
    client, _ = make_client(compact_cfg(), [resp(text)])
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    r = res.requests[0]
    assert r["head"] == text[:500] and r["tail"] == text[-500:]
    assert r["chars"] == len(text)


def test_requests_on_validation_retry():
    client, _ = make_client(compact_cfg(), [resp('{"b": 1}'), ok()])
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    assert res.ok
    assert [(r["mode"], r["head"]) for r in res.requests] == [("json_schema", '{"b": 1}'), ("json_schema", '{"a": "x"}')]


def test_no_compact_in_current_tags():
    for tag in ("qwen38", "gpt", "claude"):
        assert "json_schema_compact" not in (load_model_config(tag).get("structured") or [])


def compact_first_cfg() -> dict:
    return dict(compact_cfg(), structured=["json_schema_compact", "none"])


def test_compact_first_request_has_no_whitespace_and_no_response_format():
    client, calls = make_client(compact_first_cfg(), [ok()])
    client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    kw = calls[0]
    assert kw["extra_body"]["structured_outputs"]["disable_any_whitespace"] is True
    assert "response_format" not in kw


def test_compact_first_length_fails_after_one_request():
    client, calls = make_client(compact_first_cfg(), [cut()])
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    assert len(calls) == 1
    assert not res.ok


def test_compact_first_ok_reports_compact_mode():
    client, calls = make_client(compact_first_cfg(), [ok()])
    res = client.call(SYSTEM, USER, SCHEMA, "msds_b1")
    assert res.ok
    assert res.mode == "json_schema_compact"
