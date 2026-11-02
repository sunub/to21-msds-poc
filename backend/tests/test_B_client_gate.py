"""모델 서버가 응답하지 않을 때 호출 수와 대기 (역할 B).

모델 서버와 네트워크를 부르지 않는다. ChatClient의 client를 가짜 객체로 바꾼다.
- SDK 자체 재시도는 끈다. 재시도는 _call_with_backoff 한 곳에서만 한다.
- 마지막 실패 뒤에는 기다리지 않는다.
- 한 클라이언트(문서 하나)의 항 호출은 연결 상태를 함께 본다. 실패 중에는 한 요청만 다시 보내 보고,
  연달아 정해진 차례만큼 실패하면 남은 호출을 보내지 않고 바로 실패시킨다.
"""
import threading
import time
from types import SimpleNamespace

import httpx
import openai
import pytest

from msds.extract.client import ChatClient, ServerUnreachable, load_model_config

SYSTEM = "시스템 안내문"
USER = [{"type": "text", "text": "가상 원문"}]
REQ = httpx.Request("POST", "http://test/v1/chat/completions")


def ok_resp(content: str = "가"):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))


def conn_error():
    return openai.APIConnectionError(request=REQ)


def status_error(code: int):
    return openai.APIStatusError(f"오류 {code}", response=httpx.Response(code, request=REQ), body=None)


class Fake:
    """받은 요청 수를 세고, 정한 응답을 차례로 돌려준다(다 쓰면 마지막 것을 되풀이). 예외 객체면 던진다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.count = 0
        self.lock = threading.Lock()

    def create(self, **kw):
        with self.lock:
            self.count += 1
            r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("RNGD_BASE_URL", "http://test/v1")
    monkeypatch.setenv("RNGD_API_KEY", "test")
    monkeypatch.setattr(ChatClient, "_working_mode", {})


def make(responses, first_delay: float = 0.01, rounds: int = 5):
    cfg = dict(load_model_config("qwen3_30b_a3b_rngd"), structured=["none"])
    cfg["run"] = {**cfg["run"], "backoff_first": first_delay, "unreachable_after": rounds}
    client = ChatClient(cfg)
    fake = Fake(responses)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return client, fake


def test_sdk_retries_off():
    client = ChatClient(load_model_config("qwen3_30b_a3b_rngd"))
    assert client.client.max_retries == 0


def test_gives_up_after_rounds_without_trailing_wait():
    client, fake = make([conn_error()], first_delay=0.2, rounds=2)
    t0 = time.monotonic()
    with pytest.raises(ServerUnreachable):
        client.call_text(SYSTEM, USER)
    elapsed = time.monotonic() - t0
    assert fake.count == 2
    # 실패 → 0.2초 대기 → 실패에서 멈춘다. 마지막에 0.4초를 더 기다리지 않는다
    assert 0.2 <= elapsed < 0.4


def test_after_down_no_more_requests():
    client, fake = make([conn_error()], rounds=2)
    with pytest.raises(ServerUnreachable):
        client.call_text(SYSTEM, USER)
    before = fake.count
    with pytest.raises(ServerUnreachable):
        client.call_text(SYSTEM, USER)
    assert fake.count == before


def test_down_shows_in_call_result_path():
    """구조화 호출(call)도 같은 관문을 지난다."""
    client, fake = make([conn_error()], rounds=2)
    with pytest.raises(ServerUnreachable):
        client.call(SYSTEM, USER, {"type": "object"}, "sec01")
    assert fake.count == 2


def test_recovers_after_one_failure():
    client, fake = make([conn_error(), ok_resp("돌아옴")])
    res = client.call_text(SYSTEM, USER)
    assert res.raw_text == "돌아옴" and fake.count == 2
    # 성공하면 연속 실패 수가 0으로 돌아가 다음 호출은 기다리지 않는다
    t0 = time.monotonic()
    client.call_text(SYSTEM, USER)
    assert time.monotonic() - t0 < 0.05


def test_server_error_and_rate_limit_count_as_failures():
    client, fake = make([status_error(502), status_error(429)], rounds=2)
    with pytest.raises(ServerUnreachable):
        client.call_text(SYSTEM, USER)
    assert fake.count == 2


def test_rejected_request_means_server_reached():
    """400 같은 응답은 서버가 살아 있다는 뜻이다. 연속 실패를 끊는다."""
    client, fake = make([conn_error(), status_error(400), conn_error(), ok_resp()], rounds=2)
    res = client.call_text(SYSTEM, USER)          # 연결 실패 → 400(거부)
    assert "거부됨" in res.errors[0]
    res = client.call_text(SYSTEM, USER)          # 연결 실패 한 번은 아직 멈출 만큼이 아니다
    assert res.raw_text == "가"


def test_concurrent_calls_share_one_retry_schedule():
    """16항이 동시에 실패해도 한 차례로 센다. 그 뒤로는 한 요청만 다시 보내 본다."""
    client, fake = make([conn_error()], first_delay=0.02, rounds=3)
    errors: list[Exception] = []
    start = threading.Barrier(16)

    def run():
        start.wait()
        try:
            client.call_text(SYSTEM, USER)
        except Exception as e:      # noqa: BLE001 — 스레드 밖에서 종류를 본다
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in threads)
    assert len(errors) == 16 and all(isinstance(e, ServerUnreachable) for e in errors)
    # 처음 함께 나간 요청(최대 16) + 다시 보내 본 2번. SDK·항마다 따로 재시도하면 16 × 3 이상이다
    assert fake.count <= 16 + 2


def test_unexpected_error_does_not_block_others():
    """다시 보내 보던 요청이 예상 밖 예외로 끝나도 다른 호출이 영원히 기다리지 않는다."""
    client, fake = make([conn_error(), ValueError("가짜 고장"), ok_resp()])
    with pytest.raises(ValueError):
        client.call_text(SYSTEM, USER)            # 연결 실패 → 다시 보냄 → 예상 밖 예외
    res = client.call_text(SYSTEM, USER)
    assert res.raw_text == "가"
