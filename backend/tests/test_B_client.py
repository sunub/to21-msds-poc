"""ChatClient의 NuExtract 요청 방식 (역할 B, ADR-010).

모델 서버와 네트워크를 부르지 않는다. ChatClient의 client를 가짜 객체로 바꾼다.
응답 예는 직접 만든 가짜 값이다 (D-43).
"""
import base64
import json
from types import SimpleNamespace

import openai
import pymupdf
import pytest

from msds.extract import nuextract as nx
from msds.extract.client import ChatClient, image_part, load_model_config
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


def test_nuextract_examples_for_section_schema_name():
    from msds.extract import nuextract_examples as ex
    _, calls = nu_call([resp(json.dumps(GOOD, ensure_ascii=False))], response_schema(3))
    ctk = calls[0]["extra_body"]["chat_template_kwargs"]
    assert ctk["examples"] == [ex.example(3)]
    assert isinstance(ctk["template"], str)


def test_nuextract_no_examples_for_other_schema_name():
    client, calls = make_client(load_model_config(NU_TAG), [resp(json.dumps(GOOD, ensure_ascii=False))])
    client.call(SYSTEM, USER, response_schema(3), "msds_b1")
    ctk = calls[0]["extra_body"]["chat_template_kwargs"]
    assert "examples" not in ctk
    assert isinstance(ctk["template"], str)


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
    cfg = dict(load_model_config("qwen3_30b_a3b_rngd"), structured=["json_schema", "none"])
    client, calls = make_client(cfg,
                                [resp(json.dumps(nx.coerce({}, schema)))])
    res = client.call(SYSTEM, USER, schema, "sec03")
    assert res.ok
    kw = calls[0]
    assert kw["messages"][0] == {"role": "system", "content": SYSTEM}
    assert kw["messages"][1] == {"role": "user", "content": USER}
    assert kw["response_format"]["type"] == "json_schema"
    assert "extra_body" not in kw


# ── 필수 칸 줄이기 (require_all, ADR-017) ──────────────

# 직접 만든 작은 스키마. 행은 line만, 숫자 묶음은 raw만, 객체 칸은 lines만 필수다.
RELAX_SCHEMA = {
    "type": "object",
    "$defs": {
        "QM": {"type": "object",
               "properties": {"raw": {"type": ["string", "null"]}, "value": {"type": ["number", "null"]},
                              "unit": {"type": ["string", "null"]}},
               "required": ["raw"]},
    },
    "properties": {
        "info": {"type": "object",
                 "properties": {"kind": {"type": ["string", "null"], "x-to21": "메모"},
                                "lines": {"type": "object", "properties": {"kind": {"type": ["string", "null"]}}}},
                 "required": ["lines"]},
        "rows": {"type": "array",
                 "items": {"type": "object",
                           "properties": {"a": {"type": ["string", "null"]}, "b": {"$ref": "#/$defs/QM"},
                                          "line": {"type": "string"}},
                           "required": ["line"]}},
    },
    "required": ["rows"],
}
RELAX_OK = '{"rows": [{"line": "p1:L1"}]}'


def relaxed_schema() -> dict:
    from msds.extract.client import relax_required
    from msds.common.schema import to_strict
    return relax_required(to_strict(RELAX_SCHEMA), RELAX_SCHEMA)


def mode_cfg(*modes: str) -> dict:
    return dict(load_model_config("qwen3_30b_a3b_rngd"), structured=list(modes))


def test_require_all_default_sends_to_strict():
    from msds.common.schema import to_strict
    client, calls = make_client(mode_cfg("json_schema"), [resp(RELAX_OK)])
    res = client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03")
    assert res.ok
    sent = calls[0]["response_format"]["json_schema"]["schema"]
    assert sent == to_strict(RELAX_SCHEMA)
    assert sent["properties"]["rows"]["items"]["required"] == ["a", "b", "line"]


@pytest.mark.parametrize("mode", ["json_schema", "json_schema_compact", "json_object", "none"])
def test_require_all_true_same_request_as_default(mode):
    """require_all=True는 지금 요청과 글자 하나까지 같다."""
    client, calls = make_client(mode_cfg(mode), [resp(RELAX_OK), resp(RELAX_OK)])
    client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03")
    client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03", require_all=True)
    assert json.dumps(calls[0], ensure_ascii=False) == json.dumps(calls[1], ensure_ascii=False)


def test_require_all_false_json_schema_keeps_original_required():
    client, calls = make_client(mode_cfg("json_schema"), [resp(RELAX_OK)])
    client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03", require_all=False)
    sent = calls[0]["response_format"]["json_schema"]["schema"]
    assert sent == relaxed_schema()
    assert sent["required"] == ["rows"]
    info = sent["properties"]["info"]
    assert info["required"] == ["lines"]                       # 중첩 객체
    assert info["properties"]["lines"]["required"] == []       # 원래 required가 없는 객체
    row = sent["properties"]["rows"]["items"]
    assert row["required"] == ["line"]                         # 객체 배열의 행
    assert sent["$defs"]["QM"]["required"] == ["raw"]          # $defs 안 객체
    for obj in (sent, info, info["properties"]["lines"], row, sent["$defs"]["QM"]):
        assert obj["additionalProperties"] is False
    assert "x-to21" not in info["properties"]["kind"]          # to_strict가 뺀 키는 그대로 빠져 있다
    assert calls[0]["response_format"]["json_schema"]["strict"] is True


def test_require_all_false_json_schema_compact():
    client, calls = make_client(mode_cfg("json_schema_compact"), [resp(RELAX_OK)])
    res = client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03", require_all=False)
    assert res.ok
    so = calls[0]["extra_body"]["structured_outputs"]
    assert so == {"json": relaxed_schema(), "disable_any_whitespace": True}
    assert so["json"]["properties"]["rows"]["items"]["required"] == ["line"]
    assert "response_format" not in calls[0]


@pytest.mark.parametrize("mode", ["json_object", "none"])
def test_require_all_false_schema_hint(mode):
    from msds.common.schema import to_strict
    client, calls = make_client(mode_cfg(mode), [resp(RELAX_OK)])
    client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03", require_all=False)
    sys_text = calls[0]["messages"][0]["content"]
    assert sys_text.startswith(SYSTEM)
    assert json.dumps(relaxed_schema(), ensure_ascii=False) in sys_text
    assert json.dumps(to_strict(RELAX_SCHEMA), ensure_ascii=False) not in sys_text


# ── 공백 폭주로 한도에 걸리면 문법 없는 방식으로 한 번 더 (ADR-021) ──

SMALL = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
SMALL_OK = '{"a": "x"}'


def runaway(ratio: float) -> str:
    """앞 5자 '{"a":' 뒤에 공백을 붙여 공백 비율이 ratio인 잘린 응답 글을 만든다."""
    head = '{"a":'
    n = round(len(head) * ratio / (1 - ratio))
    return head + " " * n


def test_whitespace_fallback_to_json_object():
    cfg = load_model_config("qwen36_35b_runpod")
    assert cfg["structured"] == ["json_schema", "json_object", "none"]
    client, calls = make_client(cfg, [resp(runaway(0.8), "length"), resp(SMALL_OK)])
    res = client.call(SYSTEM, USER, SMALL, "sec02")
    assert res.ok and res.parsed == {"a": "x"}
    assert res.mode == "json_object"
    assert res.errors == []          # 성공하면 앞 시도의 오류를 넘기지 않는다 (압축 재시도와 같다)
    assert res.attempts == 2 and len(calls) == 2
    assert [(r["mode"], r["finish_reason"]) for r in res.requests] == [
        ("json_schema", "length"), ("json_object", "stop")]
    assert res.requests[0]["whitespace"] / res.requests[0]["chars"] == pytest.approx(0.8)
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["messages"][0]["content"] == SYSTEM
    assert calls[1]["response_format"] == {"type": "json_object"}
    sys_text = calls[1]["messages"][0]["content"]
    assert sys_text.startswith(SYSTEM) and "[응답 형식]" in sys_text
    assert client._working_mode[client.model] == "json_schema"


def test_whitespace_fallback_not_remembered_for_next_call():
    cfg = load_model_config("qwen36_35b_runpod")
    client, calls = make_client(cfg, [resp(runaway(0.8), "length"), resp(SMALL_OK), resp(SMALL_OK)])
    client.call(SYSTEM, USER, SMALL, "sec02")
    res = client.call(SYSTEM, USER, SMALL, "sec04")
    assert res.ok and res.mode == "json_schema"
    assert len(calls) == 3 and calls[2]["response_format"]["type"] == "json_schema"


def test_whitespace_fallback_to_none():
    cfg = dict(load_model_config("qwen36_35b_runpod"), structured=["json_schema", "none"])
    client, calls = make_client(cfg, [resp(runaway(0.5), "length"), resp(SMALL_OK)])
    res = client.call(SYSTEM, USER, SMALL, "sec02")
    assert res.ok and res.mode == "none"
    assert "response_format" not in calls[1]
    assert "[응답 형식]" in calls[1]["messages"][0]["content"]
    assert client._working_mode[client.model] == "json_schema"


def test_whitespace_fallback_failure_keeps_note():
    """넘어간 방식도 실패하면 오류 목록에 공백 폭주로 넘어간 사실이 남는다."""
    cfg = load_model_config("qwen36_35b_runpod")
    client, calls = make_client(cfg, [resp(runaway(0.8), "length"), resp('{"a": "가', "length")])
    res = client.call(SYSTEM, USER, SMALL, "sec02")
    assert not res.ok and len(calls) == 2
    assert "[json_schema] 공백 폭주로 한도에 걸림 → json_object으로 다시 보냄" in res.errors
    assert res.mode == "json_object" and res.finish_reason == "length"
    assert client._working_mode[client.model] == "json_schema"


def test_whitespace_fallback_not_for_long_output():
    """공백 비율이 0.5 미만인 한도 초과(정말 긴 출력)는 지금처럼 요청 1개로 실패한다."""
    cfg = load_model_config("qwen36_35b_runpod")
    client, calls = make_client(cfg, [resp(runaway(0.1), "length")])
    res = client.call(SYSTEM, USER, SMALL, "sec02")
    assert len(calls) == 1 and len(res.requests) == 1
    assert not res.ok and res.finish_reason == "length" and res.mode == "json_schema"
    assert any("출력 길이 한도" in e for e in res.errors)
    assert not any("공백 폭주" in e for e in res.errors)


def test_whitespace_fallback_needs_next_mode():
    cfg = dict(load_model_config("qwen36_35b_runpod"), structured=["json_schema"])
    client, calls = make_client(cfg, [resp(runaway(0.8), "length")])
    res = client.call(SYSTEM, USER, SMALL, "sec02")
    assert len(calls) == 1 and len(res.requests) == 1
    assert not res.ok and res.finish_reason == "length"
    assert not any("공백 폭주" in e for e in res.errors)


def test_whitespace_fallback_compact_rule_unchanged():
    """다음 방식이 json_schema_compact이면 공백 비율과 상관없이 지금 규칙(압축으로 한 번 더)을 따른다."""
    cfg = dict(load_model_config("qwen3_30b_a3b_rngd"), structured=["json_schema", "json_schema_compact", "none"])
    client, calls = make_client(cfg, [resp(runaway(0.8), "length"), resp(SMALL_OK)])
    res = client.call(SYSTEM, USER, SMALL, "sec02")
    assert res.ok and res.mode == "json_schema_compact"
    assert not any("공백 폭주" in e for e in res.errors)
    assert calls[1]["messages"][0]["content"] == SYSTEM


def test_require_all_false_response_without_optional_fields_ok():
    client, calls = make_client(mode_cfg("json_schema"), [resp(RELAX_OK)])
    res = client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03", require_all=False)
    assert res.ok and res.errors == []
    assert res.parsed == {"rows": [{"line": "p1:L1"}]}
    assert len(calls) == 1


def test_require_all_false_still_validates_with_original_schema():
    """줄인 스키마를 보내도 검증은 원래 스키마로 한다. 원래 필수 칸(line)이 빠지면 다시 요청한다."""
    client, calls = make_client(mode_cfg("json_schema"), [resp('{"rows": [{"a": "x"}]}'), resp(RELAX_OK)])
    res = client.call(SYSTEM, USER, RELAX_SCHEMA, "sec03", require_all=False)
    assert res.ok
    assert len(calls) == 2 and res.attempts == 2
    retry_note = calls[1]["messages"][-1]["content"]
    assert "형식에 맞지 않습니다" in retry_note and "line" in retry_note


def test_require_all_relax_required_new_copy():
    from msds.common.schema import to_strict
    from msds.extract.client import relax_required
    strict = to_strict(RELAX_SCHEMA)
    before = json.dumps(strict, ensure_ascii=False)
    original = json.dumps(RELAX_SCHEMA, ensure_ascii=False)
    out = relax_required(strict, RELAX_SCHEMA)
    assert json.dumps(strict, ensure_ascii=False) == before
    assert json.dumps(RELAX_SCHEMA, ensure_ascii=False) == original
    assert out is not strict
    assert out["properties"]["rows"]["items"] is not strict["properties"]["rows"]["items"]


def test_require_all_relax_required_drops_names_not_in_properties():
    """to_strict가 칸 이름째 뺀 칸(예: title)은 required에서도 뺀다."""
    from msds.common.schema import to_strict
    from msds.extract.client import relax_required
    schema = {"type": "object", "properties": {"title": {"type": "string"}, "name": {"type": "string"},
                                               "note": {"type": ["string", "null"]}},
              "required": ["title", "name"]}
    strict = to_strict(schema)
    assert "title" not in strict["properties"]
    out = relax_required(strict, schema)
    assert out["required"] == ["name"]
    assert out["additionalProperties"] is False


# ── 행 형식: 구조화 출력 없이 글로 받기 (call_text, ADR-019) ──

ROWS_TEXT = "### cmr\ncomp_name | line\n가상물질 갑 | p1:L9"


def test_call_text_sends_no_response_format():
    client, calls = make_client(load_model_config("qwen36_35b_runpod"), [resp(ROWS_TEXT)])
    res = client.call_text(SYSTEM, USER)
    assert len(calls) == 1
    kw = calls[0]
    assert "response_format" not in kw
    assert kw["messages"] == [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]
    assert kw["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}   # 태그의 extra_body는 그대로
    assert kw["max_tokens"] == 8192 and kw["temperature"] == 0
    assert res.raw_text == ROWS_TEXT and res.parsed is None and res.mode == "rows"
    assert res.finish_reason == "stop" and res.errors == [] and res.attempts == 1
    assert res.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert len(res.requests) == 1
    rec = res.requests[0]
    assert rec["mode"] == "rows" and rec["finish_reason"] == "stop"
    assert rec["chars"] == len(ROWS_TEXT) and rec["head"] == ROWS_TEXT


def test_call_text_ignores_structured_setting():
    """태그의 structured가 무엇이든 문법 강제(response_format, structured_outputs)를 보내지 않는다."""
    for mode in ("json_schema", "json_schema_compact", "json_object"):
        client, calls = make_client(mode_cfg(mode), [resp(ROWS_TEXT)])
        client.call_text(SYSTEM, USER, max_tokens=100)
        assert "response_format" not in calls[0] and "extra_body" not in calls[0]
        assert calls[0]["max_completion_tokens"] == 100


def test_call_text_length_keeps_text_and_records_error():
    client, calls = make_client(mode_cfg("json_schema"), [resp(ROWS_TEXT, finish="length")])
    res = client.call_text(SYSTEM, USER)
    assert len(calls) == 1
    assert res.raw_text == ROWS_TEXT and res.finish_reason == "length"
    assert len(res.errors) == 1 and "출력 길이 한도" in res.errors[0]


def test_call_text_rejected_request():
    client, calls = make_client(mode_cfg("none"), [FakeBadRequest("context too long")])
    res = client.call_text(SYSTEM, USER)
    assert len(calls) == 1
    assert res.raw_text == "" and res.mode == "rows"
    assert len(res.errors) == 1 and "거부됨" in res.errors[0]


# ── 쪽 이미지 줄이기 (2항 그림문자, ADR-019) ───────────

def fake_png(path, width: int, height: int):
    """시험에서 만든 회색 PNG. 실제 쪽 이미지(data/pages/)를 읽지 않는다 (D-43)."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pix.clear_with(200)
    pix.save(str(path))
    return path


def decoded(part: dict) -> pymupdf.Pixmap:
    url = part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    return pymupdf.Pixmap(base64.b64decode(url.removeprefix("data:image/png;base64,")))


@pytest.mark.parametrize("size", [(300, 120), (120, 300), (101, 77)])
def test_image_part_max_side_shrinks_long_side(tmp_path, size):
    part = image_part(fake_png(tmp_path / "p001.png", *size), max_side=50)
    pix = decoded(part)
    assert max(pix.width, pix.height) <= 50
    assert max(pix.width, pix.height) >= 49                          # 긴 변을 한도 가까이 맞춘다
    assert abs(pix.width / pix.height - size[0] / size[1]) < 0.1     # 가로세로 비율은 그대로
    assert part["type"] == "image_url" and part["image_url"]["detail"] == "high"


def test_image_part_max_side_small_image_unchanged(tmp_path):
    path = fake_png(tmp_path / "p001.png", 40, 30)
    part = image_part(path, max_side=50)
    assert base64.b64decode(part["image_url"]["url"].split(",", 1)[1]) == path.read_bytes()


def test_image_part_without_max_side_unchanged(tmp_path):
    path = fake_png(tmp_path / "p001.png", 300, 120)
    part = image_part(path, "low")
    assert base64.b64decode(part["image_url"]["url"].split(",", 1)[1]) == path.read_bytes()
    assert part["image_url"]["detail"] == "low"


def test_run_config_model_settings():
    q36 = load_model_config("qwen36_35b_runpod")
    assert q36["rows_sections"] == [3, 8, 9, 11, 12, 14, 15] and q36["image_input"] is True
    q30 = load_model_config("qwen3_30b_a3b_rngd")
    assert q30["rows_sections"] == [3, 8, 9, 11, 12, 14, 15] and "image_input" not in q30
    for tag in ("gpt_oss_20b_rngd", "qwen3vl4b_rngd", "nuextract2_8b_runpod"):
        assert "rows_sections" not in load_model_config(tag)
    # 행 형식의 출력 한도는 Qwen3.6에만 둔다. 없으면 max_tokens를 쓴다 (ADR-021)
    assert q36["rows_max_tokens"] == 16384
    for tag in ("qwen3_30b_a3b_rngd", "gpt_oss_20b_rngd", "qwen3vl4b_rngd", "nuextract2_8b_runpod"):
        assert "rows_max_tokens" not in load_model_config(tag)
